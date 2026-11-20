"""Legacy Knowledge Seed — chuyển 19 tài liệu viết cứng cũ
(`MultiAIProvider._init_enhanced_knowledge_base`) thành dữ liệu SEED trong kho
tri thức thật (`vector_store`), theo đúng yêu cầu NHÓM F mục 4:

    "19 tài liệu viết cứng được chuyển thành dữ liệu seed trong kho với
    status = PENDING_REVIEW, issuer = 'Tài liệu mẫu nội bộ EduDSS',
    approved_by = None. Gỡ APPROVED / source_verified tự gán trong code.
    Muốn dùng chúng thì Admin phải duyệt qua giao diện, có bản ghi audit."

`_init_enhanced_knowledge_base` vẫn giữ nguyên (nhiều test hồi quy đang kiểm
chứng hành vi tìm kiếm của `find_relevant_documents_rag` trên chính dict đó —
xem `tests/test_rag_service.py`), nhưng KHÔNG còn là nguồn trích dẫn cho Tư
vấn AI (đã chuyển sang `rag_service.retrieve_unified_context`, xem
`ai_advisor.py`). Hàm ở đây SAO CHÉP nội dung 19 tài liệu đó vào vector_store
thật — idempotent (không seed lại nếu đã tồn tại), yêu cầu `llm_integration`
để tính embedding THẬT (không có đường tắt/embedding giả)."""

from __future__ import annotations

from typing import Any, Optional

from dss.core.logging_config import get_logger
from dss.services import document_ingestion
from dss.services import vector_store as vector_store_module
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

_logger = get_logger(__name__)

SEED_ISSUER = "Tài liệu mẫu nội bộ EduDSS"
SEED_UPLOADED_BY = "system_seed"
_SEED_ID_PREFIX = "legacy_seed_"


def seed_legacy_knowledge_base_documents(
    llm_integration: Any,
    *,
    namespace: str = NAMESPACE_STUDENT_LEARNING,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    force: bool = False,
) -> int:
    """Nạp 19 tài liệu mẫu cũ vào vector_store thật (idempotent theo
    `document_id = "legacy_seed_{id_gốc}"`). Trả về số tài liệu ĐÃ nạp mới
    trong lần gọi này (0 nếu đã seed đủ từ trước và `force=False`).

    LUÔN gắn `status=PENDING_REVIEW` — không có đường nào seed thẳng thành
    APPROVED, kể cả các tài liệu trước đây tự nhận "đã duyệt" trong code
    (doc_003/004/009/016, xem F-0b) — Admin phải duyệt lại THẬT qua
    `document_approval_service` để chúng có thể được trích dẫn.
    """
    provider = _get_or_build_provider(llm_integration)
    legacy_docs = provider._init_enhanced_knowledge_base()["documents"]

    vstore = vector_store_module.get_vector_store(namespace=namespace)
    existing_ids = {d["document_id"] for d in vstore.list_documents()}

    seeded = 0
    for doc in legacy_docs:
        seed_doc_id = f"{_SEED_ID_PREFIX}{doc['id']}"
        if not force and seed_doc_id in existing_ids:
            continue

        ingested = document_ingestion.ingest_document(
            file_bytes=str(doc.get("content", "")).encode("utf-8"),
            file_name=f"{doc['id']}.txt",
            title=doc.get("title", doc["id"]),
            course_id="GEN_COURSE",
            permission_scope=doc.get("permission_scope", namespace),
            uploaded_by=SEED_UPLOADED_BY,
            doc_type="huong_dan_hoc_tap",
            issuer=SEED_ISSUER,
            official_ref=doc.get("reference", ""),
        )
        _rekey_to_seed_id(ingested, seed_doc_id)
        for c in ingested.chunks:
            c.embedding = llm_integration.get_embedding(c.content, embedding_model_name)
        vstore.add_chunks(ingested.chunks, embedding_model_name=embedding_model_name)
        seeded += 1
        _logger.info("Đã seed tài liệu mẫu cũ '%s' vào vector_store (%s).", seed_doc_id, namespace)

    return seeded


def _rekey_to_seed_id(ingested, seed_doc_id: str) -> None:
    """`ingest_document` luôn sinh document_id ngẫu nhiên (uuid) — đổi lại
    thành id ổn định theo tài liệu gốc để lần seed SAU nhận ra đã tồn tại
    (idempotent), không tạo bản trùng mỗi lần gọi."""
    old_doc_id = ingested.document_id
    ingested.document_id = seed_doc_id
    for c in ingested.chunks:
        c.document_id = seed_doc_id
        c.chunk_id = c.chunk_id.replace(old_doc_id, seed_doc_id, 1)
        c.metadata["document_id"] = seed_doc_id


def _get_or_build_provider(llm_integration: Any):
    """`_init_enhanced_knowledge_base` chỉ đọc `self` cho hằng số tĩnh (không
    dùng trạng thái instance nào) — nếu `llm_integration` không phải chính
    `MultiAIProvider` (vd. 1 wrapper/mock trong test), tạo 1 instance rỗng chỉ
    để gọi hàm này, KHÔNG dùng để tính embedding thật (việc đó vẫn dùng
    `llm_integration.get_embedding` được truyền vào)."""
    from dss.core.models import MultiAIProvider

    if hasattr(llm_integration, "_init_enhanced_knowledge_base"):
        return llm_integration
    return MultiAIProvider.__new__(MultiAIProvider)
