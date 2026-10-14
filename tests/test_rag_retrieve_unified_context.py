"""NHÓM F: rag_service.retrieve_unified_context — đường ống truy xuất DUY NHẤT
dùng để trích dẫn, đọc TRỰC TIẾP từ vector_store thật (không phải 19 tài liệu
viết cứng trong _init_enhanced_knowledge_base) và lọc CỨNG theo
document_governance.is_document_usable TRƯỚC khi xếp hạng/cắt top_k.

Dùng model embedding THẬT (giống test_rag_service.py) — hành vi cần kiểm
chứng (lọc tương đối, sàn tin cậy) phụ thuộc phân phối điểm cosine thật."""
from __future__ import annotations

import pytest

import dss.config as dss_config
from dss.services import document_approval_service as approval
from dss.services import rag_service
from dss.services import vector_store as vector_store_module
from dss.services.document_ingestion import ingest_document
from dss.services.rag_namespaces import NAMESPACE_LECTURER_SUPPORT, NAMESPACE_STUDENT_LEARNING


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider
    provider = MultiAIProvider()
    provider.get_embedding("khởi động model")
    return provider


@pytest.fixture(autouse=True)
def _isolated_vector_store(tmp_path, monkeypatch):
    from dss.services.vector_store import LocalVectorStore

    def _fake_get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING, force_local=False):
        return LocalVectorStore(base_dir=str(tmp_path), namespace=namespace)

    monkeypatch.setattr(vector_store_module, "get_vector_store", _fake_get_vector_store)
    return tmp_path


def _seed_document(llm_integration, *, title, content, status, uploaded_by="gv_a",
                    doc_type="bai_giang", namespace=NAMESPACE_STUDENT_LEARNING, course_id="CS101"):
    ingested = ingest_document(
        file_bytes=content.encode("utf-8"), file_name=f"{title}.txt", title=title,
        course_id=course_id, permission_scope=namespace, uploaded_by=uploaded_by, doc_type=doc_type,
    )
    for c in ingested.chunks:
        c.embedding = llm_integration.get_embedding(c.content)
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    vstore.add_chunks(ingested.chunks)

    if status == "APPROVED":
        approval.approve_document(
            document_id=ingested.document_id, namespace=namespace,
            actor_username="admin_1", actor_role="Admin",
        )
    elif status == "REJECTED":
        approval.reject_document(
            document_id=ingested.document_id, namespace=namespace,
            actor_username="admin_1", actor_role="Admin", review_note="test",
        )
    # status == "PENDING_REVIEW": không làm gì, giữ nguyên mặc định lúc ingest.
    return ingested.document_id


def test_approved_document_is_returned_for_matching_query(llm_integration):
    doc_id = _seed_document(
        llm_integration, title="Kỹ năng quản lý thời gian",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả, chia nhỏ thời gian ôn tập.",
        status="APPROVED",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "quản lý thời gian học tập hiệu quả", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "ok"
    assert any(c["document_id"] == doc_id for c in result["chunks"])
    assert all(c["status"] == "APPROVED" for c in result["chunks"])


def test_pending_document_never_returned_even_if_best_match(llm_integration):
    """Tài liệu CHƯA duyệt khớp nội dung gần như tuyệt đối với truy vấn nhưng
    vẫn KHÔNG được trả về — đây là điểm cốt lõi của bộ lọc CỨNG."""
    _seed_document(
        llm_integration, title="Kỹ năng quản lý thời gian (chưa duyệt)",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả, chia nhỏ thời gian ôn tập.",
        status="PENDING_REVIEW",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "quản lý thời gian học tập hiệu quả", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "NO_RELEVANT_EVIDENCE"
    assert result["chunks"] == []
    assert "chưa có tài liệu chính thức" in result["message"].lower()


def test_rejected_document_never_returned(llm_integration):
    _seed_document(
        llm_integration, title="Tài liệu bị từ chối",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả.",
        status="REJECTED",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "quản lý thời gian học tập hiệu quả", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "NO_RELEVANT_EVIDENCE"


def test_approved_document_beats_pending_document_with_same_content(llm_integration):
    """Trộn 1 tài liệu PENDING và 1 tài liệu APPROVED cùng nội dung khớp truy
    vấn — chỉ tài liệu APPROVED được trả về, tài liệu PENDING không chiếm chỗ
    trong top_k dù điểm tương đồng ngang nhau (lọc TRƯỚC khi cắt top_k)."""
    approved_id = _seed_document(
        llm_integration, title="Bài giảng đã duyệt",
        content="Cách quản lý thời gian học tập hiệu quả bằng phương pháp Pomodoro.",
        status="APPROVED", uploaded_by="gv_x",
    )
    _seed_document(
        llm_integration, title="Bài giảng chưa duyệt",
        content="Cách quản lý thời gian học tập hiệu quả bằng phương pháp Pomodoro.",
        status="PENDING_REVIEW", uploaded_by="gv_y",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "quản lý thời gian học tập hiệu quả", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=1,
    )
    assert result["status"] == "ok"
    assert len(result["chunks"]) == 1
    assert result["chunks"][0]["document_id"] == approved_id


def test_off_topic_query_against_approved_docs_returns_no_evidence(llm_integration):
    _seed_document(
        llm_integration, title="Kỹ năng quản lý thời gian",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả.",
        status="APPROVED",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "thời tiết hôm nay thế nào", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "NO_RELEVANT_EVIDENCE"


def test_permission_denied_for_role_without_namespace_access(llm_integration):
    result = rag_service.retrieve_unified_context(
        llm_integration, "bất kỳ câu hỏi nào", role="Sinh viên",
        namespace=NAMESPACE_LECTURER_SUPPORT, top_k=5,
    )
    assert result["status"] == "PERMISSION_DENIED"


def test_empty_knowledge_base_returns_honest_no_evidence(llm_integration):
    result = rag_service.retrieve_unified_context(
        llm_integration, "câu hỏi bất kỳ", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "NO_RELEVANT_EVIDENCE"
    assert result["chunks"] == []


def test_returned_chunk_carries_approval_metadata_for_citation(llm_integration):
    _seed_document(
        llm_integration, title="Kỹ năng quản lý thời gian",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả.",
        status="APPROVED",
    )
    result = rag_service.retrieve_unified_context(
        llm_integration, "quản lý thời gian học tập hiệu quả", role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING, top_k=5,
    )
    assert result["status"] == "ok"
    chunk = result["chunks"][0]
    assert chunk["approved_by"] == "admin_1"
    assert chunk["status"] == "APPROVED"
    citation = rag_service.format_document_citation(chunk)
    assert "admin_1" in citation
