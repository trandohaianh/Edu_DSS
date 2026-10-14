"""E2E (Playwright, trình duyệt thật): KB-CRUD-001 (hộp thoại xác nhận xóa
tài liệu Knowledge Base) & COLDSTART-001 (Learning Explainer vẫn render đúng
cho cả Giảng viên và Sinh viên sau khi thêm cảnh báo tải lần đầu).

Seed dữ liệu qua ĐÚNG code path sản xuất (`vector_store.LocalVectorStore`,
KHÔNG mock) trực tiếp lên đĩa `data_warehouse/vector_stores/` — tiến trình
Streamlit thật (subprocess riêng trong `base_url` fixture) đọc lại từ đĩa mỗi
lần `get_vector_store()` được gọi, nên đây vẫn là một luồng thật đầu-cuối qua
UI, chỉ tránh đúng 1 điểm dễ vỡ (widget `st.file_uploader` của Playwright) để
không cộng dồn 2 nguồn flaky (upload widget + cold-start ~60s) vào 1 test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_APP_DIR = Path(__file__).resolve().parent.parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from dss.services import chunking_service, rag_namespaces, vector_store  # noqa: E402

_E2E_DOC_ID = "e2e_kb_delete_doc"


@pytest.fixture
def seeded_kb_document(e2e_test_data_root):
    """Ghi 1 tài liệu thật vào LocalVectorStore (namespace student_learning)
    trên đĩa — đúng đường dẫn mà tiến trình Streamlit thật đang đọc — rồi dọn
    lại sau test (idempotent: xóa tài liệu không tồn tại chỉ trả về False).

    PERF-002: phải truyền base_dir=e2e_test_data_root/"vector_stores" tường
    minh — tiến trình pytest và subprocess Streamlit của base_url giờ có 2
    EDUDSS_DATA_ROOT CÔ LẬP RIÊNG (đúng theo thiết kế, mỗi bên không được đụng
    vào dữ liệu thật/nhau), nên không truyền base_dir sẽ ghi vào thư mục cô lập
    của TIẾN TRÌNH PYTEST — nơi server thật không hề đọc tới — thay vì thư mục
    mà subprocess Streamlit của bài test này đang thực sự dùng."""
    store = vector_store.LocalVectorStore(
        base_dir=str(Path(e2e_test_data_root) / "vector_stores"),
        namespace=rag_namespaces.NAMESPACE_STUDENT_LEARNING,
    )
    chunk = chunking_service.DocumentChunk(
        chunk_id=f"{_E2E_DOC_ID}_c1",
        document_id=_E2E_DOC_ID,
        course_id="CS101",
        content="Tài liệu kiểm thử E2E cho chức năng xóa Knowledge Base.",
        token_count=12,
        metadata={"title": "Tài liệu kiểm thử E2E xóa KB", "permission_scope": rag_namespaces.NAMESPACE_STUDENT_LEARNING},
        embedding=[0.3] * 384,
    )
    store.add_chunks([chunk])
    yield _E2E_DOC_ID
    store.delete_document(_E2E_DOC_ID)  # dọn nếu test thất bại trước khi xóa qua UI


def _open_knowledge_base_tab(page):
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Tài liệu", exact=False).first.click(timeout=30000)
    page.get_by_text("Không Gian Tri Thức", exact=False).first.wait_for(state="visible", timeout=30000)
    page.get_by_role("tab", name="Không Gian Tri Thức", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(1200)


def _pick_seeded_document_in_delete_selectbox(page):
    """Kho `data_warehouse` thật đã tích lũy rất nhiều tài liệu qua nhiều lượt
    test khác nhau (ghi chú đã có sẵn trong `vector_store.py`) — selectbox
    "Chọn tài liệu cần xóa" có thể có hàng trăm lựa chọn, và tài liệu vừa seed
    không chắc là lựa chọn mặc định đầu tiên. Gõ để lọc thay vì giả định vị
    trí, giống hệt cách một Admin thật sẽ tìm tài liệu trong danh sách dài."""
    combo = page.get_by_label("Chọn tài liệu cần xóa:")
    combo.click(timeout=15000)
    combo.fill("kiểm thử E2E xóa KB")
    page.get_by_role("option", name="kiểm thử E2E xóa KB", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(500)


def test_admin_cancel_confirmation_does_not_delete(login, wait_ready, seeded_kb_document, e2e_test_data_root):
    page = login("admin", "admin123")
    _open_knowledge_base_tab(page)
    wait_ready(page, timeout=20)

    _pick_seeded_document_in_delete_selectbox(page)
    page.get_by_role("button", name="Xóa tài liệu", exact=False).first.click(timeout=15000)
    dialog = page.get_by_role("dialog")
    dialog.get_by_text("Thao tác này không thể hoàn tác", exact=False).first.wait_for(state="visible", timeout=15000)
    dialog.get_by_role("button", name="Hủy", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    # Tài liệu PHẢI còn nguyên sau khi hủy — kiểm tra qua chính backend thật
    # (đáng tin cậy hơn soi text trên 1 trang bảng ảo hóa hàng trăm dòng).
    # PERF-002: base_dir=e2e_test_data_root tường minh — đọc đúng nơi subprocess
    # Streamlit của bài test này đang ghi, không phải thư mục cô lập riêng của
    # tiến trình pytest (2 EDUDSS_DATA_ROOT tách biệt theo thiết kế).
    store = vector_store.LocalVectorStore(
        base_dir=str(Path(e2e_test_data_root) / "vector_stores"),
        namespace=rag_namespaces.NAMESPACE_STUDENT_LEARNING,
    )
    assert any(d["document_id"] == _E2E_DOC_ID for d in store.list_documents())
    assert "Đã xóa tài liệu khỏi Knowledge Base" not in page.inner_text("body")


def test_admin_confirm_deletion_removes_document_end_to_end(login, wait_ready, seeded_kb_document, e2e_test_data_root):
    page = login("admin", "admin123")
    _open_knowledge_base_tab(page)
    wait_ready(page, timeout=20)

    _pick_seeded_document_in_delete_selectbox(page)
    page.get_by_role("button", name="Xóa tài liệu", exact=False).first.click(timeout=15000)
    dialog = page.get_by_role("dialog")
    dialog.get_by_text("Thao tác này không thể hoàn tác", exact=False).first.wait_for(state="visible", timeout=15000)
    dialog.get_by_role("button", name="Xóa tài liệu", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "Đã xóa tài liệu khỏi Knowledge Base" in txt

    # Xác nhận qua chính backend thật — đây là bằng chứng quyết định, không chỉ
    # dòng thông báo trên UI. PERF-002: xem ghi chú base_dir ở test phía trên.
    store = vector_store.LocalVectorStore(
        base_dir=str(Path(e2e_test_data_root) / "vector_stores"),
        namespace=rag_namespaces.NAMESPACE_STUDENT_LEARNING,
    )
    assert not any(d["document_id"] == _E2E_DOC_ID for d in store.list_documents())


def test_student_cannot_reach_knowledge_base_tab_at_all(login):
    """RBAC lớp điều hướng: Sinh viên không có mục "Tài liệu" (nhãn hiện tại
    của tab quản lý tri thức/RAG, đổi tên ở Phần 43) trong sidebar (đối
    chứng cho @require_role ở tầng service đã kiểm ở test đơn vị)."""
    page = login("sv950", "sv950123")
    sidebar_text = page.locator("[data-testid='stSidebar']").inner_text()
    assert "Tài liệu" not in sidebar_text


# ---------------------------------------------------------------------------
# COLDSTART-001 — Learning Explainer vẫn render đúng cho Giảng viên & Sinh viên
# sau khi thêm message cảnh báo tải lần đầu (không đổi luồng điều hướng).
# ---------------------------------------------------------------------------
def _open_learning_explainer_as(page, wait_ready, tab_label: str):
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Trợ lý AI", exact=False).first.click(timeout=30000)
    wait_ready(page, timeout=25)
    page.get_by_text(tab_label, exact=False).first.click(timeout=15000)
    page.wait_for_timeout(1500)


def test_lecturer_learning_explainer_renders_without_traceback(login, wait_ready):
    page = login("giangvien", "gv123")
    _open_learning_explainer_as(page, wait_ready, "Giải thích Bài giảng")
    wait_ready(page, timeout=25)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "Nạp bài giảng mới vào CMS" in txt


def test_student_learning_explainer_renders_without_traceback(login, wait_ready):
    page = login("sv951", "sv951123")
    _open_learning_explainer_as(page, wait_ready, "Giải thích bài học")
    wait_ready(page, timeout=25)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    # Tùy dữ liệu CMS đã có sẵn hay chưa — cả 2 trạng thái đều là render THÀNH
    # CÔNG, không phải lỗi: có bài giảng để hỏi, hoặc empty-state hướng dẫn.
    assert ("Giải thích bài học" in txt) or ("Chưa có bài giảng nào để giải thích" in txt)
