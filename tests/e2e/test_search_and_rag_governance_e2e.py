"""E2E (Playwright, trình duyệt thật): Search (Part A) + RAG Source Governance
UI (Part B) — UI/RAG consistency pass, phần 2, 2026-09-16.

Không lặp lại các test service-layer đã có ở test_search_service.py/
test_rag_source_governance.py — chỉ phủ hành vi CHỈ kiểm được qua UI thật:
điều hướng thật sau khi bấm "Xem phân tích", RBAC ở tầng điều hướng (Sinh
viên không thấy ô tìm kiếm), và các tab/badge phân loại nguồn hiển thị đúng
trên trang Quản lý tri thức.
"""
from __future__ import annotations


def _wait_ready(page, wait_ready_fn, timeout=25):
    wait_ready_fn(page, timeout=timeout)


def test_admin_search_exact_id_shows_result_card_not_raw_dataframe(login, wait_ready):
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    page.fill("input[aria-label='Tìm sinh viên theo mã số']", "SV002")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    txt = page.inner_text("body")
    assert "SV002" in txt
    assert "Sinh viên" in txt
    assert "Xem phân tích" in txt
    # Không được lộ tên cột kỹ thuật thô ra làm trải nghiệm chính
    assert "diem_ky_nay" not in txt
    assert "ty_le_diem_danh" not in txt


def test_admin_search_no_result_shows_honest_empty_state(login, wait_ready):
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    page.fill("input[aria-label='Tìm sinh viên theo mã số']", "SV_KHONG_TON_TAI_999")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    txt = page.inner_text("body")
    assert 'Không tìm thấy kết quả phù hợp với "SV_KHONG_TON_TAI_999"' in txt


def test_student_does_not_see_global_search_box(login, wait_ready):
    page = login("sv960", "sv960123")
    wait_ready(page, timeout=25)
    assert page.locator("input[aria-label='Tìm sinh viên theo mã số']").count() == 0


def test_lecturer_can_search_students(login, wait_ready):
    page = login("giangvien", "gv123")
    wait_ready(page, timeout=25)
    search_box = page.locator("input[aria-label='Tìm sinh viên theo mã số']")
    assert search_box.count() == 1, "Giảng viên phải có quyền tìm kiếm sinh viên (cùng phạm vi lớp đã thấy ở nơi khác)."
    search_box.fill("SV002")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)
    assert "SV002" in page.inner_text("body")


def test_search_result_action_navigates_to_ai_advisor_with_student_preselected(login, wait_ready):
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    page.fill("input[aria-label='Tìm sinh viên theo mã số']", "SV002")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    page.get_by_role("button", name="Xem phân tích", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(2000)
    wait_ready(page, timeout=25)

    txt = page.inner_text("body")
    assert "Tư vấn — AI (LLM)" in txt or "Chọn Sinh viên để tư vấn" in txt
    # Selectbox phải đã CHỌN SẴN đúng sinh viên vừa tìm — điều hướng thật, không
    # phải chỉ quay lại đúng trang cũ.
    assert "SV002" in txt


def test_knowledge_base_shows_source_classification_breakdown(login, wait_ready):
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    for attempt in range(3):
        page.locator("[data-testid='stSidebar']").get_by_role("button", name="Tài liệu", exact=False).first.click(timeout=15000)
        page.wait_for_timeout(2000)
        wait_ready(page, timeout=25)
        if "Tài liệu môn học" in page.inner_text("body"):
            break

    # KPI label được CSS text-transform:uppercase -- page.inner_text() phản
    # ánh đúng chữ ĐÃ ĐƯỢC RENDER (viết hoa), không phải chuỗi gốc trong code,
    # nên so sánh không phân biệt hoa/thường thay vì khớp nguyên văn.
    txt_lower = page.inner_text("body").lower()
    assert "tài liệu môn học" in txt_lower
    assert "nguồn tham khảo bổ sung" in txt_lower
    assert "dữ liệu demo" in txt_lower
    assert "learning explainer" in txt_lower  # dòng caption giải thích ưu tiên nguồn


def test_demo_tab_shows_source_category_and_honest_demo_wording(login, wait_ready):
    """`st.dataframe` render bảng bằng canvas (glide-data-grid) -- tên cột
    "Phân loại nguồn" trong bảng KHÔNG xuất hiện trong page.inner_text() dù
    hiển thị đúng trên màn hình (bài học đã rút ra từ lỗi ISO timestamp ở
    Model Registry). Kiểm tra qua phần expander (markdown/badge thật, không
    phải canvas) thay vì cột bảng."""
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    for attempt in range(3):
        page.locator("[data-testid='stSidebar']").get_by_role("button", name="Tài liệu", exact=False).first.click(timeout=15000)
        page.wait_for_timeout(2000)
        wait_ready(page, timeout=25)
        if "Tài liệu môn học" in page.inner_text("body"):
            break

    page.get_by_role("tab", name="Nguồn tham khảo & Demo", exact=False).first.click(timeout=15000)
    page.wait_for_timeout(1500)
    wait_ready(page, timeout=20)

    expander = page.get_by_text("Xem nội dung chi tiết + nguồn từng tài liệu", exact=False)
    assert expander.count() > 0
    expander.first.click(timeout=15000)
    page.wait_for_timeout(1000)

    txt = page.inner_text("body")
    # Mục B6: tài liệu demo phải nói rõ "Dữ liệu demo nội bộ", KHÔNG trình bày
    # GEN_REF như một trích dẫn học thuật thật.
    assert "Dữ liệu demo nội bộ" in txt
    assert "Minh họa chức năng truy xuất RAG" in txt
    # Vẫn phải còn ít nhất 1 nguồn tham khảo thật (Pomodoro/Feynman/Krashen/
    # Cornell) hiển thị đúng dạng trích dẫn có tác giả, phân biệt rõ với demo.
    assert "Nguồn tham khảo:" in txt
