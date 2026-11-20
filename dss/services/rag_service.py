"""RAG service — Đường ống truy xuất tri thức nâng cao cho hệ sinh thái EduDSS LMS.

Bao gồm:
1. `retrieve_documents`: Giữ 100% tương thích ngược với các tab và test hiện hành.
2. `retrieve_context`: Đường ống truy xuất sản xuất tuân thủ quy chuẩn LMS:
   - Phân quyền theo Namespace (student_learning, lecturer_support, admin_operations)
   - Lọc tương đối và kiểm tra sàn tin cậy (Confidence floor)
   - Trạng thái `NO_RELEVANT_EVIDENCE`: Nếu không có tài liệu nào đủ độ tin cậy,
     trả về danh sách rỗng kèm mã trạng thái rõ ràng, KHÔNG ép buộc trả về tài liệu lạc đề.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Optional

import dss.config as dss_config
from dss.core.observability import observe
from dss.services import rag_namespaces
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

# NHÓM F: số ứng viên lấy thêm (over-fetch) trước khi lọc theo
# document_governance.is_document_usable — PHẢI lọc TRƯỚC khi cắt xuống top_k
# cuối cùng (không phải sau), nếu không tài liệu PENDING/REJECTED điểm cao có
# thể chiếm hết chỗ trong top_k, đẩy tài liệu APPROVED điểm thấp hơn ra ngoài.
# Quy mô kho tri thức 1 trường/môn học thực tế chỉ vài chục-vài trăm chunk nên
# over-fetch 1 lượng lớn (bao trọn gần hết kho) vẫn nhanh với CẢ 2 backend
# (LocalVectorStore tính toàn bộ trong RAM; PgVectorStore dùng ORDER BY...LIMIT
# có index, không quét full-scan).
_GOVERNANCE_OVERFETCH_MULTIPLIER = 10
_GOVERNANCE_OVERFETCH_CAP = 300


def format_document_citation(doc: Dict[str, Any]) -> str:
    """E-4 / NHÓM F: nhãn trích dẫn tài liệu hiển thị cho người dùng — phải ghi
    rõ LOẠI nguồn và tình trạng duyệt, không trình bày mọi tài liệu như nhau.

    2 loại tài liệu có thể tới đây:
    - Từ kho tri thức thật (`vector_store`, qua `retrieve_unified_context`) —
      đã đi qua `document_governance.is_document_usable` nên LUÔN đã duyệt
      thật; hiển thị kèm `issuer`/`official_ref`/`approved_by` để người đọc
      biết CHÍNH XÁC ai/đơn vị nào đã xác nhận nội dung này.
    - Từ kho tri thức nội bộ cũ (`_init_enhanced_knowledge_base`, `source ==
      "knowledge_base"`) — đa số chưa qua kiểm duyệt thật (`source_verified=False`).
    """
    title = str(doc.get("title") or "Tài liệu")
    source = doc.get("source")
    status = doc.get("status")

    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else doc
    if status == "APPROVED" and metadata.get("approved_by"):
        issuer = metadata.get("issuer") or ""
        official_ref = metadata.get("official_ref") or ""
        approved_by = metadata.get("approved_by")
        parts = [p for p in (issuer, official_ref) if p]
        extra = f" ({', '.join(parts)})" if parts else ""
        return f"{title}{extra} — đã kiểm duyệt bởi {approved_by}"

    source_verified = doc.get("source_verified")
    if source == "knowledge_base":
        if status == "APPROVED" and source_verified:
            return f"{title} (Tài liệu mẫu nội bộ — đã kiểm duyệt)"
        return f"{title} (Tài liệu mẫu nội bộ — CHƯA kiểm duyệt)"
    return title


def retrieve_unified_context(
    llm_integration,
    query_text: str,
    role: str = "Sinh viên",
    namespace: Optional[str] = None,
    top_k: int = 5,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    hf_token=None,
    document_ids: Optional[set] = None,
    confidence_floor: float = dss_config.RAG_LOW_CONFIDENCE_FLOOR,
) -> Dict[str, Any]:
    """NHÓM F — Đường ống truy xuất DUY NHẤT dùng để TRÍCH DẪN cho cả Tư vấn AI
    và Giải thích bài giảng: truy vấn TRỰC TIẾP kho tri thức thật
    (`vector_store.get_vector_store`, nơi tài liệu do Admin/Giảng viên tải lên
    qua tab "Quản lý tri thức" được lưu) — KHÔNG còn đọc
    `MultiAIProvider._init_enhanced_knowledge_base` (19 tài liệu viết cứng) cho
    mục đích trích dẫn (F-0a/F-0b đã xác minh: luồng cũ tách rời hoàn toàn khỏi
    kho thật, và 4/19 tài liệu tự nhận "đã duyệt" mà không có người duyệt thật).

    Quy trình:
    1. Kiểm tra quyền namespace theo vai trò (giống `retrieve_context`).
    2. Tính embedding câu truy vấn, lấy dư ứng viên (over-fetch) từ vector_store.
    3. Lọc CỨNG bằng `document_governance.is_document_usable` — CHỈ tài liệu
       APPROVED thật (có approved_by), chưa hết hạn, đã tới hiệu lực — TRƯỚC
       khi cắt xuống top_k (không phải sau).
    4. Áp sàn tin cậy (confidence floor) như `retrieve_context` — không ép trả
       về tài liệu không liên quan.
    5. Không có tài liệu hợp lệ nào -> trả `NO_RELEVANT_EVIDENCE` kèm thông báo
       trung thực "chưa có tài liệu chính thức được duyệt", KHÔNG bịa nội dung.
    """
    target_ns = namespace or NAMESPACE_STUDENT_LEARNING
    if not rag_namespaces.is_namespace_allowed(role, target_ns):
        return {
            "status": "PERMISSION_DENIED",
            "chunks": [],
            "message": f"Vai trò '{role}' không có quyền truy cập không gian tri thức '{target_ns}'.",
        }

    from dss.services import document_governance as gov
    from dss.services import vector_store as vector_store_module

    with observe("rag.retrieve_unified", top_k=top_k, backend="vector_store") as metric:
        query_embedding = llm_integration.get_embedding(query_text, embedding_model_name, hf_token)
        if query_embedding is None:
            metric["error"] = "embedding_failed"
            return {
                "status": "NO_RELEVANT_EVIDENCE",
                "chunks": [],
                "message": "Không tính được embedding cho câu truy vấn.",
            }

        vstore = vector_store_module.get_vector_store(namespace=target_ns)
        overfetch_k = min(_GOVERNANCE_OVERFETCH_CAP, max(top_k * _GOVERNANCE_OVERFETCH_MULTIPLIER, top_k))
        candidates = vstore.search(query_embedding, top_k=overfetch_k, document_ids=document_ids)

        now = datetime.now(UTC)
        # NHÓM F: mọi chunk trong 1 lượt tìm phải CÙNG embedding_model — nếu
        # lẫn model (vd. tài liệu cũ được nạp bằng model khác), điểm cosine
        # similarity giữa các không gian vector khác nhau KHÔNG có ý nghĩa so
        # sánh — báo lỗi rõ ràng thay vì âm thầm so sánh sai.
        seen_models = {c.get("embedding_model") for c in candidates if c.get("embedding_model")}
        if len(seen_models) > 1:
            metric["error"] = "mixed_embedding_models"
            return {
                "status": "ERROR",
                "chunks": [],
                "message": (
                    "Kho tri thức có tài liệu dùng nhiều embedding model khác nhau "
                    f"({sorted(seen_models)}) — không thể so sánh độ tương đồng đúng. "
                    "Cần tính lại embedding cho toàn bộ tài liệu bằng CÙNG 1 model."
                ),
            }

        usable = [c for c in candidates if gov.is_document_usable(c.get("metadata") or {}, now=now)]
        usable = usable[:top_k]
        metric["candidate_count"] = len(candidates)
        metric["usable_count"] = len(usable)

        if not usable:
            return {
                "status": "NO_RELEVANT_EVIDENCE",
                "chunks": [],
                "message": "Chưa có tài liệu chính thức được duyệt cho vấn đề này — vui lòng liên hệ cố vấn học tập.",
            }

        top_score = float(usable[0].get("relevance_score", 0.0))
        is_low_confidence = top_score < confidence_floor

        if is_low_confidence:
            return {
                "status": "NO_RELEVANT_EVIDENCE",
                "chunks": [],
                "top_score": top_score,
                "message": (
                    f"Điểm tương đồng cao nhất ({top_score:.2f}) không đạt ngưỡng tin cậy "
                    f"tối thiểu ({confidence_floor:.2f}) trong số tài liệu ĐÃ DUYỆT."
                ),
            }

        processed_chunks = []
        for c in usable:
            chunk = dict(c)
            chunk["namespace"] = target_ns
            chunk["low_confidence"] = False
            # Đưa các trường quản trị lên cấp ngoài để citation_service/UI đọc
            # trực tiếp không cần lặn vào "metadata" (khớp cách format_document_citation
            # và citation_service.verify_citations đang đọc doc.get(...)).
            meta = chunk.get("metadata") or {}
            chunk["status"] = meta.get("status")
            chunk["issuer"] = meta.get("issuer")
            chunk["official_ref"] = meta.get("official_ref")
            chunk["approved_by"] = meta.get("approved_by")
            chunk["approved_at"] = meta.get("approved_at")
            chunk["doc_type"] = meta.get("doc_type")
            processed_chunks.append(chunk)

        metric["result_count"] = len(processed_chunks)
        return {
            "status": "ok",
            "chunks": processed_chunks,
            "top_score": top_score,
            "low_confidence": False,
            "message": f"Đã tìm thấy {len(processed_chunks)} tài liệu đã duyệt liên quan.",
        }


def retrieve_documents(
    llm_integration,
    query_text: str,
    top_k: int = 5,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    hf_token=None,
    use_warehouse_data: bool = True,
    runtime_documents=None,
):
    """Truy vấn tài liệu liên quan qua `MultiAIProvider.find_relevant_documents_rag`.

    Tương thích ngược 100% cho các test hồi quy và code hiện tại.
    """
    base_kwargs = dict(
        query_text=query_text,
        top_k=top_k,
        embedding_model_name=embedding_model_name,
        hf_token=hf_token,
        use_warehouse_data=use_warehouse_data,
    )
    with observe("rag.retrieve", top_k=top_k, backend="provider") as metric:
        try:
            result = llm_integration.find_relevant_documents_rag(**base_kwargs, runtime_documents=runtime_documents)
        except TypeError:
            result = llm_integration.find_relevant_documents_rag(**base_kwargs)
            metric["fallback"] = "signature"
        metric["result_count"] = len(result)
        return result


def retrieve_context(
    llm_integration,
    query_text: str,
    role: str = "Sinh viên",
    namespace: Optional[str] = None,
    top_k: int = 5,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    use_warehouse_data: bool = True,
    runtime_documents=None,
    confidence_floor: float = dss_config.RAG_LOW_CONFIDENCE_FLOOR,
    strict_confidence: bool = True,
) -> Dict[str, Any]:
    """Đường ống truy xuất RAG nâng cao cho môi trường LMS sản xuất.

    Quy trình:
    1. Lọc quyền Namespace theo vai trò (Role-based namespace permission)
    2. Truy xuất tài liệu liên quan từ kho tri thức
    3. Kiểm tra độ tin cậy (Confidence check):
       - Nếu điểm của tài liệu đứng đầu thấp hơn `confidence_floor` và `strict_confidence=True`:
         Trả về trạng thái `NO_RELEVANT_EVIDENCE` và danh sách rỗng.
         Tuyệt đối không ép buộc trả về tài liệu không liên quan vào prompt của LLM.
    """
    target_ns = namespace or NAMESPACE_STUDENT_LEARNING
    if not rag_namespaces.is_namespace_allowed(role, target_ns):
        return {
            "status": "PERMISSION_DENIED",
            "chunks": [],
            "message": f"Vai trò '{role}' không có quyền truy cập không gian tri thức '{target_ns}'.",
        }

    # Lấy tài liệu từ provider
    raw_docs = retrieve_documents(
        llm_integration,
        query_text=query_text,
        top_k=top_k,
        embedding_model_name=embedding_model_name,
        use_warehouse_data=use_warehouse_data,
        runtime_documents=runtime_documents,
    )

    if not raw_docs:
        return {
            "status": "NO_RELEVANT_EVIDENCE",
            "chunks": [],
            "message": "Không tìm thấy tài liệu nào trong kho tri thức.",
        }

    top_score = float(raw_docs[0].get("relevance_score", 0.0))
    is_low_confidence = bool(raw_docs[0].get("low_confidence", False)) or (top_score < confidence_floor)

    if strict_confidence and is_low_confidence:
        return {
            "status": "NO_RELEVANT_EVIDENCE",
            "chunks": [],
            "top_score": top_score,
            "message": f"Điểm tương đồng cao nhất ({top_score:.2f}) không đạt ngưỡng tin cậy tối thiểu ({confidence_floor:.2f}).",
        }

    # Bổ sung namespace và metadata chuẩn hóa cho từng chunk
    processed_chunks = []
    for d in raw_docs:
        c = dict(d)
        c["namespace"] = target_ns
        c["low_confidence"] = is_low_confidence
        processed_chunks.append(c)

    return {
        "status": "ok",
        "chunks": processed_chunks,
        "top_score": top_score,
        "low_confidence": is_low_confidence,
        "message": f"Đã tìm thấy {len(processed_chunks)} tài liệu liên quan.",
    }
