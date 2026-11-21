"""E2E (Playwright, real browser) — C1.3 UI/UX redesign journeys.

Covers the critical journeys named in the C1.3 acceptance brief: login page
content, logout, theme switching, one primary journey per role, role-scoped
navigation, the AI degraded state and a narrow-viewport overflow check.
"""

from __future__ import annotations

import os
import socket

import pytest

_NAV = ".st-key-dss_main_nav_rail"
_FOOTER = ".st-key-dss_sidebar_footer"
_ADMIN_ONLY_LABELS = ("Người dùng", "Cấu hình AI", "Tích hợp LMS/CMS", "Báo cáo & giám sát", "Cài đặt", "Mô hình ML")


def _nav_text(page) -> str:
    return page.locator(_NAV).inner_text()


def _open(page, wait_ready, label):
    page.locator(_NAV).get_by_role("button", name=label, exact=True).first.click(timeout=30000)
    page.locator(f"{_NAV} button[kind='primary']", has_text=label).first.wait_for(timeout=60000)
    page.wait_for_timeout(1000)
    wait_ready(page, timeout=40)


def _app_bg(page) -> str:
    return page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=\"stAppViewContainer\"]')).backgroundColor"
    )


# ---------------------------------------------------------------- login / logout
def test_login_page_shows_provisioning_help_and_no_demo_or_dev_chrome(browser, base_url, wait_ready):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator("input[aria-label='Mật khẩu']").wait_for(timeout=90000)
        wait_ready(page)
        txt = page.inner_text("body")
        assert "không hỗ trợ tự đăng ký" in txt
        for forbidden in ("admin123", "gv123", "GPA dự đoán", "Deploy", "Traceback"):
            assert forbidden not in txt, forbidden
        assert page.locator("[data-testid='stSidebar']").is_hidden()
    finally:
        ctx.close()


def test_logout_returns_to_login_screen(login, wait_ready):
    page = login("giangvien", "gv123")
    page.locator(_FOOTER).get_by_role("button", name="Đăng xuất").click()
    page.locator("input[aria-label='Mật khẩu']").wait_for(timeout=30000)
    assert page.locator(_NAV).count() == 0


# ---------------------------------------------------------------- theme
def test_theme_switch_changes_real_colours_both_ways(login, wait_ready):
    page = login("giangvien", "gv123")
    footer = page.locator(_FOOTER)
    footer.get_by_role("button", name="Tối", exact=True).click()
    page.locator(".dss-marker.dss-theme-dark").wait_for(state="attached", timeout=20000)
    page.wait_for_timeout(800)
    assert _app_bg(page) == "rgb(15, 23, 42)"
    input_bg = page.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=\"stTextInput\"] [data-baseweb=\"input\"]')).backgroundColor"
    )
    assert input_bg != "rgb(255, 255, 255)", "Ô nhập liệu vẫn nền trắng ở chế độ tối"
    footer.get_by_role("button", name="Sáng", exact=True).click()
    page.locator(".dss-marker.dss-theme-light").wait_for(state="attached", timeout=20000)
    page.wait_for_timeout(800)
    assert _app_bg(page) == "rgb(248, 251, 255)"  # --bg-primary #F8FBFF (main.css, light)


# ---------------------------------------------------------------- role journeys
def test_student_primary_journey_and_nav_scope(login, wait_ready):
    page = login("sv911", "sv911123")
    txt = page.inner_text("body")
    assert "Xin chào, SV911" in txt
    assert "Việc nên làm tiếp theo" in txt
    nav = _nav_text(page)
    for label in _ADMIN_ONLY_LABELS + ("Dashboard", "Kho dữ liệu", "Khám phá dữ liệu"):
        assert label not in nav, f"Sinh viên thấy mục điều hướng {label!r}"
    _open(page, wait_ready, "Trợ lý AI")
    txt = page.inner_text("body")
    assert "Kế hoạch học tập" in txt
    assert "API key" not in txt and "Traceback" not in txt


def test_lecturer_primary_journey_and_nav_scope(login, wait_ready):
    page = login("giangvien", "gv123")
    assert "Tổng quan lớp học" in page.inner_text("body")
    nav = _nav_text(page)
    for label in _ADMIN_ONLY_LABELS:
        assert label not in nav, f"Giảng viên thấy mục điều hướng {label!r}"
    _open(page, wait_ready, "Dashboard")
    page.get_by_text("Dashboard lớp học", exact=False).first.wait_for(timeout=30000)


def test_admin_primary_journey(login, wait_ready):
    page = login("admin", "admin123")
    txt = page.inner_text("body")
    assert "Tổng quan hệ thống" in txt and "Cần xử lý" in txt
    assert "Dashboard" not in _nav_text(page)
    _open(page, wait_ready, "Người dùng")
    page.get_by_text("Danh sách tài khoản", exact=False).first.wait_for(timeout=30000)
    _open(page, wait_ready, "Tích hợp LMS/CMS")
    txt = page.inner_text("body")
    assert "Chưa kết nối" in txt and "Trực tuyến" not in txt
    _open(page, wait_ready, "Cấu hình AI")
    page.get_by_text("Trạng thái provider", exact=False).first.wait_for(timeout=30000)
    assert "Kết nối được" not in page.inner_text("body")  # nothing was checked yet


# ---------------------------------------------------------------- AI degraded state
def _ollama_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", 11434)) == 0


@pytest.mark.skipif(
    any(os.environ.get(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY")) or _ollama_running(),
    reason="Cần môi trường KHÔNG có nguồn AI nào để kiểm tra trạng thái suy giảm",
)
def test_student_quick_ask_shows_unavailable_state_without_ai_provider(login, wait_ready):
    page = login("sv912", "sv912123")
    page.get_by_label("Hỏi nhanh Trợ lý AI").fill("Tôi nên ưu tiên môn nào?")
    page.get_by_role("button", name="Gửi câu hỏi").click()
    page.get_by_text("Trợ lý AI trực tuyến chưa sẵn sàng", exact=False).first.wait_for(timeout=30000)
    txt = page.inner_text("body")
    assert "Không có câu hỏi nào được gửi đi" in txt
    assert "Traceback" not in txt


# ---------------------------------------------------------------- responsive
@pytest.mark.parametrize("width,height", [(1366, 768), (1024, 768)])
def test_no_horizontal_page_overflow_on_laptop_viewports(browser, base_url, wait_ready, width, height):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    try:
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator("input[aria-label='Mật khẩu']").wait_for(timeout=90000)
        page.fill("input[aria-label='Tên đăng nhập / Mã số sinh viên']", "giangvien")
        page.fill("input[aria-label='Mật khẩu']", "gv123")
        page.get_by_role("button", name="Đăng nhập").click()
        page.locator(_NAV).wait_for(state="visible", timeout=240000)
        wait_ready(page)
        overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"Tràn ngang {overflow}px ở {width}x{height}"
    finally:
        ctx.close()


# ---------------------------------------------------------------- phone (AC-SV-09)
_MOBILE_NAV = ".st-key-dss_mobile_nav"
_STUDENT_PHONE_PAGES = {
    "Trang chủ": "Xin chào",
    "Dự đoán": "Dự đoán kết quả học tập",
    "Kế hoạch": "Kế hoạch học tập",
    "Lịch sử": "Lịch sử tư vấn",
}
_LAYOUT_PROBE = """() => {
    const h = document.querySelector('[data-testid="stMain"] h1, [data-testid="stMain"] h2');
    const sb = document.querySelector('[data-testid="stSidebar"]');
    return {
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        headingX: h ? h.getBoundingClientRect().x : null,
        sidebarRight: sb ? sb.getBoundingClientRect().right : 0,
    };
}"""


@pytest.mark.parametrize("width,height", [(375, 812), (430, 932)])
def test_student_pages_usable_on_phone(browser, base_url, wait_ready, width, height):
    """AC-SV-09: 4 trang chính của sinh viên dùng được trên điện thoại.

    Không tràn ngang, sidebar thu gọn không che mép trái nội dung, và thanh điều
    hướng trên cùng (dss/main.py MOBILE_NAV_ITEMS) chuyển được cả 4 trang.
    """
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=True, has_touch=True)
    try:
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator("input[aria-label='Mật khẩu']").wait_for(timeout=90000)
        page.fill("input[aria-label='Tên đăng nhập / Mã số sinh viên']", "sv913")
        page.fill("input[aria-label='Mật khẩu']", "sv913123")
        page.get_by_role("button", name="Đăng nhập").click()
        nav = page.locator(_MOBILE_NAV)
        nav.wait_for(state="visible", timeout=240000)
        wait_ready(page)
        # initial_sidebar_state="auto": trên màn hẹp Streamlit tự thu gọn sidebar. Nếu vì lý do
        # nào đó nó đang mở thì đóng lại như người dùng (nút đóng chỉ bấm được khi sidebar mở).
        sidebar = page.locator("[data-testid='stSidebar']")
        if sidebar.get_attribute("aria-expanded") == "true":
            page.locator("[data-testid='stSidebarCollapseButton'] button").click()
            page.wait_for_timeout(800)
        assert sidebar.get_attribute("aria-expanded") == "false", "Sidebar không thu gọn trên điện thoại"
        for label, heading in _STUDENT_PHONE_PAGES.items():
            nav.get_by_role("button", name=label, exact=True).click(timeout=30000)
            page.locator(f"{_MOBILE_NAV} button[kind='primary']", has_text=label).wait_for(timeout=60000)
            wait_ready(page, timeout=40)
            # Tìm trong vùng nội dung (sidebar thu gọn cũng có chữ "Lịch sử tư vấn" nhưng bị ẩn).
            page.locator("[data-testid='stMain']").get_by_text(heading, exact=False).first.wait_for(timeout=30000)
            probe = page.evaluate(_LAYOUT_PROBE)
            assert probe["overflow"] <= 1, f"{label}: tràn ngang {probe['overflow']}px ở {width}px"
            assert probe["sidebarRight"] <= 1, f"{label}: sidebar thu gọn còn che {probe['sidebarRight']}px"
            assert probe["headingX"] is not None and probe["headingX"] >= 8, f"{label}: tiêu đề bị che mép trái"
            buttons = nav.get_by_role("button")
            for i in range(buttons.count()):
                assert buttons.nth(i).bounding_box()["height"] >= 40, "Nút điều hướng thấp hơn 40px, khó chạm"
    finally:
        ctx.close()


def test_mobile_nav_hidden_on_desktop(login, wait_ready):
    """Thanh điều hướng điện thoại không được hiện trên máy tính (giao diện desktop giữ nguyên)."""
    page = login("sv914", "sv914123")
    assert page.locator(_MOBILE_NAV).count() == 1
    assert page.locator(_MOBILE_NAV).is_hidden()
    assert page.locator(_NAV).is_visible()


# ---------------------------------------------------------------- 3 trang giảng viên (AC-GV-09..11)
def test_lecturer_pages_open_without_error_and_are_hidden_from_students(login, wait_ready):
    page = login("giangvien", "gv123")
    for label in ("Phân tích rủi ro", "Báo cáo", "Lịch sử tư vấn"):
        _open(page, wait_ready, label)
        main = page.locator("[data-testid='stMain']")
        main.locator("h1", has_text=label).first.wait_for(timeout=30000)
        assert page.locator("[data-testid='stException']").count() == 0, f"{label}: có traceback"
        assert "Traceback" not in main.inner_text()
    student = login("sv915", "sv915123")
    nav = _nav_text(student)
    for label in ("Phân tích rủi ro", "Báo cáo"):
        assert label not in nav, f"Sinh viên thấy {label!r}"
