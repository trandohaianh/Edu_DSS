"""FINAL REMEDIATION PASS — Mục 3: Giảng viên trước đây KHÔNG có lối vào UI
nào để duyệt tài liệu môn mình phụ trách (tab "Quản lý tri thức (RAG)" chỉ
Admin thấy được, dù backend document_approval_service đã hỗ trợ vai trò
Giảng viên từ đợt NHÓM F). Kiểm tra:
1. TAB_ACCESS cấp đúng tab "📄 Duyệt tài liệu" hẹp cho Giảng viên (không cấp
   toàn bộ "Quản lý tri thức (RAG)" — vẫn Admin-only).
2. `list_pending_documents_for_approver` chỉ trả về tài liệu actor THỰC SỰ
   được phép duyệt (lọc UI) — và dù bộ lọc UI có bị bỏ qua, backend
   (approve_document/reject_document) vẫn tự từ chối hành động không hợp lệ
   (fail-closed, không phụ thuộc UI)."""

from __future__ import annotations

import inspect

import pytest

from dss.core import roles
from dss.services import cms_lecture_repository
from dss.services import document_approval_service as approval
from dss.services import vector_store as vector_store_module
from dss.services.document_ingestion import ingest_document
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


@pytest.fixture(autouse=True)
def _isolated_vector_store(tmp_path, monkeypatch):
    from dss.services.vector_store import LocalVectorStore

    def _fake_get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING, force_local=False):
        return LocalVectorStore(base_dir=str(tmp_path), namespace=namespace)

    monkeypatch.setattr(vector_store_module, "get_vector_store", _fake_get_vector_store)
    return tmp_path


def _upload_pending_doc(
    *,
    doc_type="bai_giang",
    uploaded_by="gv_a",
    course_id="CS101",
    namespace=NAMESPACE_STUDENT_LEARNING,
    title="Bài giảng 1",
):
    ingested = ingest_document(
        file_bytes="Nội dung bài giảng mẫu.".encode(),
        file_name=f"{title}.txt",
        title=title,
        course_id=course_id,
        uploaded_by=uploaded_by,
        doc_type=doc_type,
        permission_scope=namespace,
    )
    for c in ingested.chunks:
        c.embedding = [0.1, 0.2, 0.3]
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    vstore.add_chunks(ingested.chunks)
    return ingested.document_id


def test_tab_access_grants_narrow_approval_tab_to_lecturer_not_full_kb_admin_page():
    assert "Giảng viên / CVHT" in roles.TAB_ACCESS["📄 Duyệt tài liệu"]
    assert "Sinh viên" not in roles.TAB_ACCESS["📄 Duyệt tài liệu"]
    # Trang Admin đầy đủ (xóa/nạp tài liệu/duyệt toàn hệ thống) vẫn PHẢI
    # Admin-only — trang mới không thay thế/nới quyền trang cũ.
    assert roles.TAB_ACCESS["📚 Quản lý tri thức (RAG)"] == {"Admin"}


def test_list_pending_documents_for_approver_excludes_course_lecturer_does_not_teach():
    _upload_pending_doc(uploaded_by="gv_a", course_id="CS999")
    result = approval.list_pending_documents_for_approver(
        NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b",
        actor_role="Giảng viên / CVHT",
    )
    assert result == []


def test_list_pending_documents_for_approver_excludes_self_uploaded():
    cms_lecture_repository.create_or_get_lesson(
        course_id="CS201",
        lesson_id="CS201_L1_selfup",
        topic_id="intro",
        lecturer_id="gv_a",
        title="Giới thiệu",
    )
    _upload_pending_doc(uploaded_by="gv_a", course_id="CS201")
    result = approval.list_pending_documents_for_approver(
        NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_a",
        actor_role="Giảng viên / CVHT",
    )
    assert result == [], "Giảng viên không được thấy chính tài liệu mình tải lên trong hàng đợi duyệt của mình."


def test_list_pending_documents_for_approver_excludes_quy_che_doc_type():
    cms_lecture_repository.create_or_get_lesson(
        course_id="CS301",
        lesson_id="CS301_L1_quyche",
        topic_id="intro",
        lecturer_id="gv_b",
        title="Giới thiệu",
    )
    _upload_pending_doc(uploaded_by="admin_x", course_id="CS301", doc_type="quy_che")
    result = approval.list_pending_documents_for_approver(
        NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b",
        actor_role="Giảng viên / CVHT",
    )
    assert result == [], "Giảng viên không có thẩm quyền duyệt loại tài liệu 'quy_che'."


def test_list_pending_documents_for_approver_includes_own_course_material():
    cms_lecture_repository.create_or_get_lesson(
        course_id="CS401",
        lesson_id="CS401_L1_owncourse",
        topic_id="intro",
        lecturer_id="gv_b",
        title="Giới thiệu",
    )
    doc_id = _upload_pending_doc(uploaded_by="gv_a", course_id="CS401", doc_type="bai_giang")
    result = approval.list_pending_documents_for_approver(
        NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b",
        actor_role="Giảng viên / CVHT",
    )
    assert [d["document_id"] for d in result] == [doc_id]


def test_backend_still_rejects_even_if_ui_filter_were_bypassed():
    """Dù trang UI có lỗi hiển thị/bỏ qua bộ lọc `list_pending_documents_for_approver`,
    approve_document() vẫn PHẢI tự kiểm tra lại và từ chối — đây là biên bảo
    mật THẬT, không phải riêng bộ lọc UI."""
    doc_id = _upload_pending_doc(uploaded_by="gv_a", course_id="CS999")
    ok, msg = approval.approve_document(
        document_id=doc_id,
        namespace=NAMESPACE_STUDENT_LEARNING,
        actor_username="gv_b",
        actor_role="Giảng viên / CVHT",
    )
    assert ok is False


def test_lecturer_approval_tab_does_not_expose_delete_or_upload_or_admin_namespace():
    """Trang mới cho Giảng viên phải HẸP: không có nút xóa tài liệu, không có
    form nạp tài liệu mới, và không đụng tới namespace admin_operations —
    những chức năng đó vẫn chỉ nằm trong trang Admin-only "Quản lý tri thức"."""
    from dss.tabs import knowledge_base

    source = inspect.getsource(knowledge_base.lecturer_document_approval_tab)
    assert "NAMESPACE_ADMIN_OPERATIONS" not in source
    assert "_confirm_delete_document_dialog" not in source
    assert "ingest_document" not in source
    assert "document_approval_service.approve_document" in source
    assert "document_approval_service.reject_document" in source
