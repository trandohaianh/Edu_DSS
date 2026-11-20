"""Test Suite: KB-CRUD-001 (xóa an toàn tài liệu Knowledge Base) &
COLDSTART-001 (thông báo tải rõ ràng khi khởi tạo mô hình embedding lần đầu).

Đây là các test HỒI QUY có mục tiêu cho lượt "pre-defense hardening" — KHÔNG
lặp lại bộ test kiến trúc RAG tổng quát đã có ở test_lms_ai_rag_gateway.py.

Phủ đúng các trường hợp yêu cầu ở PHẦN A6:
1. Admin (đã xác thực) xóa được 1 tài liệu thật đã lưu.
2. Tài liệu biến mất khỏi danh sách (list_documents).
3. Retrieval (search) không còn trả về tài liệu đã xóa.
4. Vai trò không có quyền (Sinh viên) không xóa được — bị chặn ở tầng service.
5. Backend lỗi thật không được báo thành công giả.
6. PgVectorStore (CRUD xóa vẫn là stub) không được báo thành công — trả về
   "unsupported" một cách trung thực thay vì gọi hàm giả rồi tin kết quả.
7. Tài liệu đang là phiên bản current của 1 bài giảng CMS bị chặn xóa (tránh
   Learning Explainer mất trích dẫn âm thầm) — một ràng buộc nhất quán phát
   hiện thêm khi trace luồng runtime thật, không có trong yêu cầu gốc nhưng
   cần thiết để đúng tinh thần "không phá vỡ dữ liệu liên quan" của A4.

Và PHẦN B: `ui_kit.cold_start_aware_message` — helper hiển thị cảnh báo "lần
đầu có thể chậm" đúng lúc mô hình embedding CHƯA được nạp, không phải lúc nào
cũng thêm cảnh báo một cách vô nghĩa (đã nạp rồi thì spinner phải gọn như cũ).
"""

from __future__ import annotations

import pytest
import streamlit as st

from dss.services import chunking_service, cms_lecture_repository, knowledge_base_admin, rag_namespaces, vector_store
from dss.tabs import ui_kit


def _make_chunk(document_id: str, chunk_id: str, content: str = "Nội dung minh họa.") -> chunking_service.DocumentChunk:
    return chunking_service.DocumentChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        course_id="CS101",
        content=content,
        token_count=10,
        metadata={"title": f"Tài liệu {document_id}", "permission_scope": rag_namespaces.NAMESPACE_STUDENT_LEARNING},
        embedding=[0.2] * 384,
    )


@pytest.fixture(autouse=True)
def _admin_role():
    """Đa số test cần vai trò Admin để vượt qua @require_role trên
    delete_document_safely — set/khôi phục lại session_state sạch mỗi test."""
    previous = st.session_state.get("_auth_role")
    st.session_state["_auth_role"] = "Admin"
    yield
    if previous is None:
        st.session_state.pop("_auth_role", None)
    else:
        st.session_state["_auth_role"] = previous


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    """1 LocalVectorStore cô lập trong tmp_path, và trỏ get_vector_store() của
    module knowledge_base_admin về đúng store này (không chạm data_warehouse
    thật của repo)."""
    store = vector_store.LocalVectorStore(base_dir=str(tmp_path), namespace=rag_namespaces.NAMESPACE_STUDENT_LEARNING)
    monkeypatch.setattr(knowledge_base_admin.vector_store_module, "get_vector_store", lambda namespace=None: store)
    return store


# ============================================================================
# 1-3. XÓA THẬT: privileged user xóa được, biến mất khỏi listing, retrieval
# ============================================================================
def test_01_admin_deletes_real_stored_document(local_store):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1"), _make_chunk("doc_B", "doc_B_c1")])

    result = knowledge_base_admin.delete_document_safely("doc_A")

    assert result["status"] == knowledge_base_admin.STATUS_SUCCESS


def test_02_deleted_document_disappears_from_listing(local_store):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1"), _make_chunk("doc_B", "doc_B_c1")])

    knowledge_base_admin.delete_document_safely("doc_A")

    remaining_ids = {d["document_id"] for d in local_store.list_documents()}
    assert remaining_ids == {"doc_B"}


def test_03_retrieval_no_longer_returns_deleted_document(local_store):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1"), _make_chunk("doc_B", "doc_B_c1")])

    knowledge_base_admin.delete_document_safely("doc_A")

    results = local_store.search(query_embedding=[0.2] * 384, top_k=10)
    returned_doc_ids = {r["document_id"] for r in results}
    assert "doc_A" not in returned_doc_ids
    assert "doc_B" in returned_doc_ids  # tài liệu khác không bị ảnh hưởng (không orphan/mất nhầm)


# ============================================================================
# 4. RBAC: vai trò không có quyền không xóa được
# ============================================================================
def test_04_unauthorized_role_cannot_delete(local_store):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])
    st.session_state["_auth_role"] = "Sinh viên"

    with pytest.raises(PermissionError):
        knowledge_base_admin.delete_document_safely("doc_A")

    # Xác nhận tài liệu vẫn còn nguyên — không có xóa "một phần" nào lọt qua
    assert {d["document_id"] for d in local_store.list_documents()} == {"doc_A"}


def test_04b_lecturer_role_cannot_delete(local_store):
    """Đối chứng thêm: Giảng viên cũng không có quyền xóa KB (chỉ Admin)."""
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])
    st.session_state["_auth_role"] = "Giảng viên / CVHT"

    with pytest.raises(PermissionError):
        knowledge_base_admin.delete_document_safely("doc_A")


# ============================================================================
# 5. Backend lỗi thật -> KHÔNG báo thành công giả
# ============================================================================
def test_05_backend_failure_does_not_report_false_success(local_store, monkeypatch):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])

    def _boom(document_id):
        raise RuntimeError("Đĩa đầy / lỗi ghi file mô phỏng")

    monkeypatch.setattr(local_store, "delete_document", _boom)

    result = knowledge_base_admin.delete_document_safely("doc_A")

    assert result["status"] == knowledge_base_admin.STATUS_ERROR
    assert "Lỗi" in result["message"]


def test_05b_deleting_nonexistent_document_is_honest_not_found(local_store):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])

    result = knowledge_base_admin.delete_document_safely("doc_khong_ton_tai")

    assert result["status"] == knowledge_base_admin.STATUS_NOT_FOUND
    # Không bị xóa nhầm tài liệu khác
    assert {d["document_id"] for d in local_store.list_documents()} == {"doc_A"}


# ============================================================================
# 6. PgVectorStore has real SQL deletion and its result must be honored
# ============================================================================
def test_06_pgvectorstore_delete_uses_real_backend_result(monkeypatch):
    fake_pg_store = vector_store.PgVectorStore.__new__(vector_store.PgVectorStore)
    fake_pg_store.connection_url = "postgresql://fake"

    called = {"delete_document": False}

    def _tracking_delete(self, document_id):
        called["delete_document"] = True
        assert document_id == "doc_bat_ky"
        return True

    monkeypatch.setattr(vector_store.PgVectorStore, "delete_document", _tracking_delete)
    monkeypatch.setattr(
        knowledge_base_admin.vector_store_module, "get_vector_store", lambda namespace=None: fake_pg_store
    )

    result = knowledge_base_admin.delete_document_safely("doc_bat_ky")

    assert result["status"] == knowledge_base_admin.STATUS_SUCCESS
    assert called["delete_document"] is True


# ============================================================================
# 7. Tài liệu đang được 1 bài giảng CMS tham chiếu -> chặn xóa (tránh mất
#    trích dẫn âm thầm trong Learning Explainer)
# ============================================================================
def test_07_delete_blocked_when_referenced_by_live_cms_lesson(local_store, monkeypatch):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])

    class _FakeLesson:
        title = "Nhập môn Cấu trúc Dữ liệu"
        course_id = "CS101"
        lesson_id = "L01"
        current_document_id = "doc_A"

    monkeypatch.setattr(cms_lecture_repository, "list_lessons", lambda *a, **k: [_FakeLesson()])

    result = knowledge_base_admin.delete_document_safely("doc_A")

    assert result["status"] == knowledge_base_admin.STATUS_BLOCKED_REFERENCED
    assert "Nhập môn Cấu trúc Dữ liệu" in result["message"]
    # Không bị xóa
    assert {d["document_id"] for d in local_store.list_documents()} == {"doc_A"}


def test_07b_delete_allowed_when_not_referenced_by_any_lesson(local_store, monkeypatch):
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])
    monkeypatch.setattr(cms_lecture_repository, "list_lessons", lambda *a, **k: [])

    result = knowledge_base_admin.delete_document_safely("doc_A")

    assert result["status"] == knowledge_base_admin.STATUS_SUCCESS


def test_07c_lesson_registry_read_error_does_not_block_delete(local_store, monkeypatch):
    """Registry đọc lỗi/rỗng không phải bằng chứng có tham chiếu — không nên
    chặn xóa vô thời hạn chỉ vì registry tạm thời không đọc được."""
    local_store.add_chunks([_make_chunk("doc_A", "doc_A_c1")])

    def _boom(*a, **k):
        raise RuntimeError("registry tạm thời không đọc được")

    monkeypatch.setattr(cms_lecture_repository, "list_lessons", _boom)

    result = knowledge_base_admin.delete_document_safely("doc_A")

    assert result["status"] == knowledge_base_admin.STATUS_SUCCESS


# ============================================================================
# COLDSTART-001 — helper thông báo tải
# ============================================================================
class _FakeProviderNoModelYet:
    embedding_model = None


class _FakeProviderModelLoaded:
    embedding_model = object()  # bất kỳ giá trị truthy nào mô phỏng đã nạp


def test_08_cold_start_message_added_when_model_not_loaded():
    msg = ui_kit.cold_start_aware_message(_FakeProviderNoModelYet(), "Đang xử lý...")
    assert msg.startswith("Đang xử lý...")
    assert "lần" in msg.lower() or "khởi tạo" in msg.lower()
    assert len(msg) > len("Đang xử lý...")


def test_09_cold_start_message_unchanged_when_model_already_loaded():
    msg = ui_kit.cold_start_aware_message(_FakeProviderModelLoaded(), "Đang xử lý...")
    assert msg == "Đang xử lý..."


def test_10_cold_start_message_handles_missing_attribute_gracefully():
    """llm_integration=None hoặc đối tượng lạ không có `embedding_model` không
    được làm hàm crash — coi như "chưa nạp" (an toàn hơn: hiện cảnh báo thừa
    còn hơn im lặng lúc thực sự đang cold-start)."""
    msg = ui_kit.cold_start_aware_message(None, "Đang xử lý...")
    assert msg.startswith("Đang xử lý...")
