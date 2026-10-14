"""NHÓM F: document_approval_service — quy trình duyệt tài liệu RAG.

Kiểm tra: chặn tự duyệt, thẩm quyền theo vai trò/loại tài liệu, giảng viên chỉ
duyệt được môn mình đứng tên dạy trong CMS, và mỗi quyết định chuyển đúng
trạng thái (PENDING_REVIEW -> APPROVED/REJECTED/RETIRED)."""
from __future__ import annotations

import pytest

from dss.services import cms_lecture_repository
from dss.services import document_approval_service as approval
from dss.services import document_governance as gov
from dss.services import vector_store as vector_store_module
from dss.services.document_ingestion import ingest_document
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


@pytest.fixture(autouse=True)
def _isolated_vector_store(tmp_path, monkeypatch):
    """Trỏ get_vector_store về LocalVectorStore trong thư mục tạm — không dùng
    is_postgres_enabled thật (đã bị autouse EDUDSS_DATA_ROOT cô lập rồi, nhưng
    force_local để không phụ thuộc biến môi trường DB trong CI/máy khác)."""
    from dss.services.vector_store import LocalVectorStore

    def _fake_get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING, force_local=False):
        return LocalVectorStore(base_dir=str(tmp_path), namespace=namespace)

    monkeypatch.setattr(vector_store_module, "get_vector_store", _fake_get_vector_store)
    return tmp_path


def _upload_pending_doc(*, doc_type="bai_giang", uploaded_by="gv_a", course_id="CS101"):
    ingested = ingest_document(
        file_bytes="Nội dung bài giảng mẫu.".encode("utf-8"),
        file_name="bai1.txt",
        title="Bài giảng 1",
        course_id=course_id,
        uploaded_by=uploaded_by,
        doc_type=doc_type,
    )
    for c in ingested.chunks:
        c.embedding = [0.1, 0.2, 0.3]
    vstore = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    vstore.add_chunks(ingested.chunks)
    return ingested.document_id


def test_uploader_cannot_approve_own_document():
    doc_id = _upload_pending_doc(uploaded_by="gv_a")
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_a", actor_role="Admin",
    )
    assert ok is False
    assert "tự duyệt" in msg.lower()


def test_student_can_never_approve():
    doc_id = _upload_pending_doc(uploaded_by="gv_a")
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="sv_b", actor_role="Sinh viên",
    )
    assert ok is False


def test_lecturer_cannot_approve_quy_che_doc_type():
    doc_id = _upload_pending_doc(uploaded_by="admin_x", doc_type="quy_che")
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_a", actor_role="Giảng viên / CVHT",
    )
    assert ok is False


def test_lecturer_cannot_approve_course_they_do_not_teach():
    doc_id = _upload_pending_doc(uploaded_by="gv_a", doc_type="bai_giang", course_id="CS999")
    # gv_b không đứng tên dạy CS999 trong CMS -> bị từ chối
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b", actor_role="Giảng viên / CVHT",
    )
    assert ok is False
    assert "phụ trách" in msg.lower()


def test_lecturer_can_approve_course_they_teach():
    cms_lecture_repository.create_or_get_lesson(
        course_id="CS101", lesson_id="CS101_L1", topic_id="intro",
        lecturer_id="gv_b", title="Giới thiệu",
    )
    doc_id = _upload_pending_doc(uploaded_by="gv_a", doc_type="bai_giang", course_id="CS101")
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b", actor_role="Giảng viên / CVHT",
    )
    assert ok is True

    docs = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING).list_documents()
    doc = next(d for d in docs if d["document_id"] == doc_id)
    assert doc["status"] == gov.STATUS_APPROVED
    assert doc["approved_by"] == "gv_b"
    assert doc["approved_at"] is not None


def test_admin_can_approve_any_valid_document():
    doc_id = _upload_pending_doc(uploaded_by="gv_a", doc_type="quy_che")
    ok, msg = approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin",
    )
    assert ok is True


def test_reject_requires_a_reason():
    doc_id = _upload_pending_doc(uploaded_by="gv_a")
    ok, msg = approval.reject_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin", review_note="",
    )
    assert ok is False
    assert "lý do" in msg.lower()


def test_reject_sets_status_rejected_with_note():
    doc_id = _upload_pending_doc(uploaded_by="gv_a")
    ok, msg = approval.reject_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin", review_note="Nội dung chưa chính xác.",
    )
    assert ok is True
    docs = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING).list_documents()
    doc = next(d for d in docs if d["document_id"] == doc_id)
    assert doc["status"] == gov.STATUS_REJECTED
    assert doc["review_note"] == "Nội dung chưa chính xác."
    assert doc["approved_by"] is None


def test_retire_previously_approved_document():
    doc_id = _upload_pending_doc(uploaded_by="gv_a")
    approval.approve_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin",
    )
    ok, msg = approval.retire_document(
        document_id=doc_id, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin", review_note="Hết hiệu lực.",
    )
    assert ok is True
    docs = vector_store_module.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING).list_documents()
    doc = next(d for d in docs if d["document_id"] == doc_id)
    assert doc["status"] == gov.STATUS_RETIRED


def test_approve_nonexistent_document_fails_gracefully():
    ok, msg = approval.approve_document(
        document_id="doc_khong_ton_tai", namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin",
    )
    assert ok is False
    assert "không tìm thấy" in msg.lower()


def test_list_pending_documents_only_returns_pending():
    doc_pending = _upload_pending_doc(uploaded_by="gv_a", course_id="CS200")
    doc_approved = _upload_pending_doc(uploaded_by="gv_c", course_id="CS201")
    approval.approve_document(
        document_id=doc_approved, namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="admin_1", actor_role="Admin",
    )
    pending_ids = {d["document_id"] for d in approval.list_pending_documents(NAMESPACE_STUDENT_LEARNING)}
    assert doc_pending in pending_ids
    assert doc_approved not in pending_ids
