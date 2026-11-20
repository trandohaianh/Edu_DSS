"""NHÓM F: legacy_knowledge_seed — chuyển 19 tài liệu viết cứng cũ thành dữ
liệu SEED trong kho tri thức thật, ở trạng thái PENDING_REVIEW. Đây là con
đường ĐÚNG để nội dung mẫu cũ (vd. doc_003 — Pomodoro) trở nên hợp lệ cho
trích dẫn: seed -> Admin duyệt THẬT (có audit log) -> retrieve_unified_context
mới trả về được. Bổ sung cho test_rag_service.py::
test_real_lms_mode_filters_unverified_documents (đã cập nhật theo F-0b)."""

from __future__ import annotations

import pytest

import dss.config as dss_config
from dss.services import document_approval_service as approval
from dss.services import document_governance as gov
from dss.services import legacy_knowledge_seed, rag_service
from dss.services import vector_store as vector_store_module
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


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


def test_seed_creates_19_pending_review_documents(llm_integration):
    seeded = legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
    assert seeded == 19

    vstore = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    docs = vstore.list_documents()
    assert len(docs) == 19
    for d in docs:
        assert d["status"] == gov.STATUS_PENDING_REVIEW
        assert d["approved_by"] is None
        assert d["issuer"] == legacy_knowledge_seed.SEED_ISSUER
        assert d["document_id"].startswith("legacy_seed_")


def test_seed_is_idempotent_does_not_duplicate(llm_integration):
    first = legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
    second = legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
    assert first == 19
    assert second == 0  # đã tồn tại đủ -> không seed lại

    vstore = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    assert len(vstore.list_documents()) == 19


_DOC_003_MATCHING_QUERY = "Lập lịch học tập hàng tuần ưu tiên môn khó ôn tập đều đặn Pomodoro"


def test_seeded_doc_003_not_citable_before_real_approval(llm_integration):
    """Ngay sau khi seed (chưa ai duyệt), doc_003 (Pomodoro) KHÔNG được trích
    dẫn — đúng tinh thần F-0b (không còn tự nhận đã duyệt), dù nội dung khớp
    gần như tuyệt đối với truy vấn (điểm tương đồng ~0.93 khi đã duyệt — xem
    test dưới)."""
    legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
    result = rag_service.retrieve_unified_context(
        llm_integration,
        _DOC_003_MATCHING_QUERY,
        role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING,
        top_k=5,
    )
    assert result["status"] == "NO_RELEVANT_EVIDENCE"


def test_legacy_document_becomes_citable_after_real_approval(llm_integration):
    """Con đường ĐÚNG: seed -> Admin duyệt THẬT (có audit log) ->
    retrieve_unified_context mới trả về được, kèm approved_by rõ ràng."""
    legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
    ok, msg = approval.approve_document(
        document_id="legacy_seed_doc_003",
        namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_that",
        actor_role="Admin",
    )
    assert ok is True, msg

    result = rag_service.retrieve_unified_context(
        llm_integration,
        _DOC_003_MATCHING_QUERY,
        role="Sinh viên",
        namespace=NAMESPACE_STUDENT_LEARNING,
        top_k=5,
    )
    assert result["status"] == "ok"
    assert any(c["document_id"] == "legacy_seed_doc_003" for c in result["chunks"])
    matched = next(c for c in result["chunks"] if c["document_id"] == "legacy_seed_doc_003")
    assert matched["approved_by"] == "admin_that"
    assert matched["issuer"] == legacy_knowledge_seed.SEED_ISSUER
