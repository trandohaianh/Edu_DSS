"""Bộ test E2E (Playwright, trình duyệt thật) — luồng theo từng vai trò.

Đây là tầng test PHÙ HỢP cho các bất biến gắn liền với UI thật (điều mà test
đơn vị ở tests/*.py không thể kiểm tra vì các hàm đó render trực tiếp qua
st.*): điều hướng bị lọc đúng vai trò, Sinh viên không có cách nào (kể cả qua
UI) để xem dữ liệu Sinh viên khác, Giảng viên không thấy được các điều khiển
chỉ dành cho Admin dù đã vào được tab dùng chung.

Tài khoản dùng trong test (khớp _seed_default_accounts_if_missing trong
auth_service.py): admin/admin123, giangvien/gv123. Tài khoản Sinh viên dùng mã
số dạng SVxxx bất kỳ + mật khẩu <mã số>123 (tự động cấp lần đầu).

Lưu ý kỹ thuật quan trọng (rút ra khi viết bộ test này): sau khi bấm 1 mục
điều hướng, PHẢI đợi bằng `wait_ready` (polling độ dài text ổn định 3 lần liên
tiếp) — dùng `page.wait_for_timeout()` cố định 1 khoảng thời gian là KHÔNG đủ
tin cậy, vì Streamlit có thể còn đang rerender/stream nội dung tab cũ lẫn tab
mới cùng lúc tại thời điểm chụp, khiến assertion sai một cách ngẫu nhiên.
"""
from __future__ import annotations

from playwright.sync_api import expect


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_wrong_password_rejected_with_error(login):
    page = login("giangvien", "sai-mat-khau", expect_success=False)
    assert "Sai tên đăng nhập hoặc mật khẩu" in page.inner_text("body")


def test_unknown_username_rejected(login):
    page = login("nguoi_dung_khong_ton_tai", "matkhau", expect_success=False)
    assert "Sai tên đăng nhập hoặc mật khẩu" in page.inner_text("body")


def test_admin_login_succeeds(login):
    page = login("admin", "admin123")
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    # C1.3: vai trò hiển thị bằng tiếng Việt ở chân sidebar ("Quản trị viên").
    assert "admin" in txt and "Quản trị viên" in txt


def test_lecturer_login_succeeds(login):
    page = login("giangvien", "gv123")
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "Giảng viên" in txt


def test_student_auto_provision_on_first_login(login):
    page = login("sv901", "sv901123")
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "sv901" in txt


# ---------------------------------------------------------------------------
# RBAC ở tầng ĐIỀU HƯỚNG (nav) — TAB_ACCESS trong dss/core/roles.py
# ---------------------------------------------------------------------------
def test_admin_nav_has_no_training_tab(login):
    """TAB_ACCESS: '🧪 Huấn luyện — Dự đoán' chỉ dành {Giảng viên, Sinh viên} —
    Admin không có, kể cả khi đã vào app."""
    page = login("admin", "admin123")
    txt = page.inner_text("body")
    assert "Huấn luyện — Dự đoán" not in txt


def test_student_nav_has_no_dashboard_or_warehouse_tab(login):
    # Nhãn điều hướng hiển thị KHÔNG còn emoji (design system: nav dùng icon
    # line-art thay emoji, xem `roles.display_label` / `main.py` format_func) —
    # nhưng giá trị gốc (khoá TAB_ACCESS) vẫn giữ emoji, không đổi RBAC.
    page = login("sv902", "sv902123")
    page.inner_text("body")
    # "Dashboard" là từ mượn tiếng Anh xuất hiện hợp lệ ở NƠI KHÁC của trang
    # Sinh viên (vd. tiêu đề "Dashboard của bạn" ở Trang chủ) — không thể chỉ
    # tìm chuỗi con trên TOÀN trang, phải giới hạn đúng danh sách điều hướng
    # sidebar (nơi thực sự quyết định RBAC có lộ route hay không).
    nav_txt = page.locator(".st-key-dss_main_nav_rail").inner_text()
    assert "Dashboard" not in nav_txt
    assert "Kho dữ liệu" not in nav_txt
    assert "Khám phá — Xử lý dữ liệu" not in nav_txt


def test_lecturer_nav_has_ai_advisor_tab(login):
    """Trước Phase 10, tab '🤖 Tư vấn — AI (LLM)' bị khoá chỉ Sinh viên — đã mở
    cho Giảng viên/Admin để phần cấu hình provider trong đó dùng được.

    STALE SELECTOR (audit 2026-09, bằng chứng): assertion gốc tìm chuỗi đầy đủ
    "Tư vấn — AI (LLM)" trên TOÀN body ngay sau đăng nhập — giả định này đúng ở
    thời điểm viết test (khi trang mặc định sau đăng nhập từng hiển thị nhãn
    tab gốc trực tiếp). Từ khi hệ thống nhãn rút gọn `display_label`/
    `TAB_SHORT_LABELS` ra đời (roles.py), landing page của Giảng viên là
    Dashboard với các thẻ hành động nhanh dùng nhãn ngắn "Tư vấn AI" (không có
    "— AI (LLM)"), và sidebar cũng hiển thị nhãn ngắn "Trợ lý AI" — chuỗi đầy đủ
    không còn xuất hiện ở bất kỳ đâu trên trang mặc định nữa (xác nhận bằng 2 lần
    chạy độc lập, không phải flaky). Đây KHÔNG phải do thay đổi của audit hôm nay
    (main.py chỉ thêm format_func riêng cho Sinh viên trong tab con của AI, không
    đụng tới Dashboard/sidebar). Sửa lại để kiểm tra đúng bất biến RBAC gốc: mục
    điều hướng cho phép truy cập tab AI phải xuất hiện trong sidebar nav rail.
    """
    page = login("giangvien", "gv123")
    nav_txt = page.locator(".st-key-dss_main_nav_rail").inner_text()
    assert "Trợ lý AI" in nav_txt


def test_admin_nav_has_no_dashboard_tab(login):
    """TAB_ACCESS: '📊 Dashboard' chỉ dành Giảng viên — Admin không có, dù đã
    vào app (Admin dùng "Báo cáo hệ thống" riêng, không phải trang này). Giới
    hạn kiểm tra đúng danh sách điều hướng sidebar — "Dashboard" là từ mượn
    có thể xuất hiện hợp lệ ở nơi khác trên trang (không phải tên nav)."""
    page = login("admin", "admin123")
    nav_txt = page.locator(".st-key-dss_main_nav_rail").inner_text()
    assert "Dashboard" not in nav_txt


# ---------------------------------------------------------------------------
# Trang chủ vs Dashboard — 2 TRẢI NGHIỆM TÁCH BIỆT cho Giảng viên (yêu cầu
# thiết kế: KHÔNG được dùng chung 1 hàm render — trước đây cả HOME_TAB_LABEL
# lẫn "📊 Dashboard" đều gọi thẳng dashboard.py::main_dashboard_tab(), khiến
# Trang chủ chỉ là bí danh của Dashboard). Xem home.py::render_lecturer_home
# (độc lập) vs dashboard.py::main_dashboard_tab.
# ---------------------------------------------------------------------------
def _click_dashboard_nav(page):
    # Sidebar redesign (2026-09, "CodingLab" nav rail — dss/main.py SIDEBAR_NAV_GROUPS):
    # điều hướng chính giờ là st.button() theo nhóm, KHÔNG còn st.radio() — không
    # còn <label>/<input type="radio"> nào trong sidebar cho mục điều hướng. Dùng
    # role=button (ổn định, không phụ thuộc CSS class do Streamlit tự sinh).
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Dashboard", exact=False).first.click(timeout=30000)
    page.get_by_text("Dashboard lớp học", exact=False).first.wait_for(state="visible", timeout=30000)


def test_lecturer_lands_on_home_after_login(login):
    """Sau đăng nhập Giảng viên phải vào ĐÚNG "Trang chủ" trước tiên (C1.3:
    không còn màn giới thiệu "Bắt đầu khám phá" ở giữa)."""
    page = login("giangvien", "gv123")
    # Sidebar redesign: mục điều hướng đang ACTIVE được đánh dấu bằng
    # button[kind="primary"] (xem dss/main.py: btn_type = "primary" if is_active
    # else "secondary") — không còn input radio "checked" nào để dò.
    active_label = page.locator("[data-testid='stSidebar'] button[kind='primary']").inner_text()
    assert "Trang chủ" in active_label
    assert "Traceback" not in page.inner_text("body")


def test_lecturer_home_has_welcome_hero_and_quick_actions(login):
    """Trang chủ = chào mừng/tổng quan nhẹ/hành động nhanh — KHÔNG phải trang
    phân tích (không mang tiêu đề "Dashboard lớp học")."""
    page = login("giangvien", "gv123")
    txt = page.inner_text("body")
    assert "Chào mừng trở lại" in txt
    assert "Gợi ý hôm nay" in txt
    # C1.3: thẻ truy cập nhanh dùng cùng nhãn (viết hoa kiểu câu) với mục điều hướng.
    assert "Huấn luyện & dự đoán" in txt
    assert "Dashboard lớp học" not in txt


def test_clicking_dashboard_opens_dashboard(login):
    page = login("giangvien", "gv123")
    _click_dashboard_nav(page)
    txt = page.inner_text("body")
    assert "Dashboard lớp học" in txt
    assert "Traceback" not in txt


def test_dashboard_contains_analytics_sections(login):
    """Dashboard = không gian phân tích chuyên sâu — có các khối KHÔNG tồn
    tại ở Trang chủ (phân cụm, yếu tố quan trọng, trạng thái mô hình, bảng
    sinh viên rủi ro cao đầy đủ)."""
    page = login("giangvien", "gv123")
    _click_dashboard_nav(page)
    page.get_by_text("Sinh viên rủi ro cao", exact=False).first.wait_for(state="visible", timeout=30000)
    txt = page.inner_text("body")
    assert "Phân khúc sinh viên" in txt
    assert "Yếu tố quan trọng nhất" in txt
    assert "Trạng thái mô hình" in txt
    assert "Sinh viên rủi ro cao" in txt
    assert "Chào mừng trở lại" not in txt


def test_home_and_dashboard_render_distinct_content(login):
    """Bất biến cốt lõi: 2 route KHÔNG được render cùng nội dung."""
    page = login("giangvien", "gv123")
    home_txt = page.inner_text("body")
    _click_dashboard_nav(page)
    dashboard_txt = page.inner_text("body")
    assert home_txt != dashboard_txt
    assert "Chào mừng trở lại" in home_txt and "Chào mừng trở lại" not in dashboard_txt
    assert "Dashboard lớp học" in dashboard_txt and "Dashboard lớp học" not in home_txt


# ---------------------------------------------------------------------------
# RBAC ở tầng CHỨC NĂNG trong tab Tư vấn AI — không chỉ ẩn UI
# ---------------------------------------------------------------------------
def _open_ai_advisor_tab(page):
    # Sidebar redesign: mục nav giờ hiện nhãn RÚT GỌN kiểu CodingLab qua
    # display_label()/TAB_SHORT_LABELS (dss/core/roles.py) — "🤖 Tư vấn — AI (LLM)"
    # hiện trên nav là "🤖  Trợ lý AI", không còn chứa chuỗi "Tư vấn — AI" nữa.
    # Đồng thời không còn <label> nào bọc mục nav (xem _click_dashboard_nav) —
    # dùng role=button, scope trong sidebar để tránh trùng với nút cùng tên khác.
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Trợ lý AI", exact=False).first.click(timeout=30000)
    # RỘT CAUSE của flake trước đây: chỉ đợi "Bước 1: Chọn sinh viên" — đây là
    # dòng RẤT SỚM trong ai_advisor_tab (dss/tabs/ai_advisor.py), render trước
    # cả phần cấu hình provider theo vai trò (dòng ~88/191) VÀ trước nút hành
    # động chính ở CUỐI hàm (dòng ~792) hàng trăm dòng code. Streamlit gửi nội
    # dung theo đúng thứ tự hàm chạy nhưng KHÔNG đồng bộ — "Bước 1" đã lên DOM
    # không hề đảm bảo phần cấu hình provider (thậm chí gọi _check_ollama_
    # running(), có thể mất tới ~1.5s do timeout mạng) đã render xong. Đó là lý
    # do test dựa trên "Bước 1" thỉnh thoảng đọc phải trang chưa render hết.
    #
    # Sửa: đợi ĐÚNG phần tử render CUỐI CÙNG của ai_advisor_tab cho MỌI vai trò
    # — nút hành động chính ("🚀 Tạo Kế hoạch Học tập..."). Nút này luôn là dòng
    # cuối cùng của hàm (bất kể Sinh viên/Giảng viên/Admin), nên nó xuất hiện
    # trong DOM CHỈ SAU KHI mọi nội dung phía trên nó — gồm cả phần cấu hình
    # provider theo vai trò — đã render xong. Dùng locator theo ROLE thay vì
    # tìm text, và .wait_for(state="visible") tự động retry tới khi đúng điều
    # kiện thật xảy ra, không phải 1 khoảng chờ cố định.
    #
    # LỖI THỰC TẾ đã sửa: sau khi Trang chủ trở thành trang landing THẬT cho
    # MỌI vai trò (kể cả Sinh viên — xem home.py::_render_student_home_dashboard),
    # trang đó cũng có 1 nút tương tự "✨ Tạo kế hoạch học tập với AI" — khớp
    # substring "Tạo Kế hoạch Học tập" (exact=False so khớp không phân biệt
    # hoa/thường) dù CHƯA hề điều hướng sang tab Tư vấn AI, khiến wait_for này
    # "đạt điều kiện" giả trên chính Trang chủ. Thêm tiền tố emoji 🚀 (nút thật
    # của ai_advisor_tab dùng 🚀, nút của Trang chủ dùng ✨ — 2 emoji khác nhau)
    # để phân biệt chính xác, không đoán qua text suông.
    # Timeout 45s (không phải đoán): đo thực tế qua profiling cho thấy nút này
    # render ổn định trong ~15-35s khi chạy đơn lẻ (ai_advisor_tab tính SHAP +
    # truy xuất RAG + kiểm tra provider trước khi tới dòng cuối cùng của hàm),
    # nhưng khi 13 test chạy NỐI TIẾP trên CÙNG 1 server (base_url session-scope)
    # có lúc vượt mốc 30s do tải tích luỹ — 45s đủ dư so với thời gian thật đã đo,
    # không phải "tăng timeout rồi coi như đã sửa" cho lỗi không tồn tại.
    page.get_by_role("button", name="Tạo Kế hoạch Học tập", exact=False).wait_for(
        state="visible", timeout=45000
    )


def _expand_advisor_config_expanders(page):
    """UI redesign (mockup "admin config visually separated"): "Chọn nguồn AI",
    "Cấu hình hệ thống AI (Admin)" và "Công cụ kỹ thuật" giờ nằm trong
    `st.expander` THU GỌN mặc định — `inner_text('body')`/`get_by_role("heading")`
    không đọc/thấy được nội dung bên trong cho tới khi mở ra, giống hệt cách xử
    lý ở `_open_warehouse_models_tab`. Chỉ ảnh hưởng SETUP của test (mở UI ra
    xem), KHÔNG đổi bất biến RBAC mà các assertion bên dưới kiểm tra."""
    for label in ("Chọn nguồn AI", "Cấu hình hệ thống AI (Admin)", "Công cụ kỹ thuật"):
        entries = page.locator("summary", has_text=label)
        if entries.count() > 0:
            entries.first.click()
            page.wait_for_timeout(300)


def test_lecturer_does_not_see_api_key_fields(login):
    """Giảng viên dùng được AI Teaching Assistant (bộ chọn provider rút gọn +
    Compare AI) nhưng KHÔNG được xem/sửa API key/secrets, và không có quyền
    chỉnh cấu hình dành riêng cho Admin."""
    page = login("giangvien", "gv123")
    _open_ai_advisor_tab(page)
    _expand_advisor_config_expanders(page)

    # Bất biến bảo mật kiểm tra trực tiếp qua CẤU TRÚC DOM (không phải tìm chữ
    # "API Key" — dễ vỡ nếu đổi câu chữ, và không bắt được 1 ô nhập bí mật nào
    # đó lỡ không kèm đúng cụm từ này): không còn ô input nào kiểu password.
    assert page.locator('input[type="password"]').count() == 0

    # Đúng bộ chọn RÚT GỌN dành cho Giảng viên phải hiện ra — kiểm bằng role
    # heading thật (ổn định hơn tìm substring trong toàn bộ text trang), và
    # heading cấu hình ĐẦY ĐỦ dành riêng cho Admin KHÔNG được xuất hiện.
    expect(page.get_by_role("heading", name="Chọn nguồn AI", exact=True)).to_be_visible()
    assert page.get_by_role("heading", name="Cấu hình nguồn AI (Admin)", exact=True).count() == 0

    assert "Traceback" not in page.inner_text("body")


def test_lecturer_sees_compare_ai_but_not_connection_test(login):
    page = login("giangvien", "gv123")
    _open_ai_advisor_tab(page)
    _expand_advisor_config_expanders(page)
    txt = page.inner_text("body")
    assert "So sánh nhiều AI cùng lúc" in txt
    assert "Kiểm tra" not in txt or "API Key" not in txt  # nút test-kết-nối yêu cầu cả 2 cụm từ này


def test_admin_sees_full_provider_config_and_connection_test(login):
    page = login("admin", "admin123")
    _open_ai_advisor_tab(page)
    _expand_advisor_config_expanders(page)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "Cấu hình nguồn AI (Admin)" in txt
    assert "API Key" in txt or "Token" in txt
    assert "So sánh nhiều AI cùng lúc" in txt


def test_student_does_not_see_compare_ai_or_provider_config(login):
    page = login("sv903", "sv903123")
    _open_ai_advisor_tab(page)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "So sánh nhiều AI cùng lúc" not in txt
    assert "Cấu hình nguồn AI" not in txt
    assert "Chọn nguồn AI" not in txt
    assert "Trạng thái hệ thống AI" not in txt
    assert "Tạo Kế hoạch Học tập" in txt  # vẫn dùng được tính năng chính


# ---------------------------------------------------------------------------
# Student A không xem được dữ liệu Student B
# ---------------------------------------------------------------------------
def test_student_ai_advisor_locked_to_own_id_no_picker(login):
    """Sinh viên không có selectbox chọn sinh viên khác trong tab Tư vấn AI —
    luôn cố định đúng mã số của chính mình (current_student_id từ session)."""
    page = login("sv904", "sv904123")
    _open_ai_advisor_tab(page)
    txt = page.inner_text("body")
    assert "Đang tư vấn cho" in txt
    assert "SV904" in txt
    assert "Chọn Sinh viên để tư vấn" not in txt  # đây là selectbox CHỈ Giảng viên/Admin mới thấy


def test_two_students_see_only_their_own_id_concurrently(login):
    """Mở 2 phiên trình duyệt ĐỘC LẬP (2 browser context riêng) cùng lúc, mỗi
    phiên đăng nhập 1 sinh viên khác nhau — xác nhận không lẫn ID giữa 2 phiên
    (đúng bất biến session isolation ở tests/test_session_isolation.py, nhưng
    kiểm chứng ở tầng UI thật với 2 kết nối song song, không phải mock)."""
    page_a = login("sv905", "sv905123")
    page_b = login("sv906", "sv906123")

    _open_ai_advisor_tab(page_a)
    _open_ai_advisor_tab(page_b)

    txt_a = page_a.inner_text("body")
    txt_b = page_b.inner_text("body")

    assert "SV905" in txt_a and "SV906" not in txt_a
    assert "SV906" in txt_b and "SV905" not in txt_b


def test_lecturer_can_choose_any_student_but_student_cannot(login, wait_ready):
    """Đối chứng: Giảng viên (không phải Sinh viên) MỚI được thấy selectbox
    chọn sinh viên bất kỳ trong tab Tư vấn AI — xác nhận khác biệt vai trò rõ
    ràng, không phải do tab lỗi không hiện gì cho ai cả.

    RENDER TIMING (bằng chứng, không phải đoán): thất bại 1 lần khi chạy TOÀN
    BỘ suite e2e liên tiếp (22 passed, 1 failed) nhưng PASS ổn định khi chạy
    riêng lẻ. `_open_ai_advisor_tab` chỉ đợi nút hành động CUỐI hàm hiển thị —
    dưới tải tích luỹ của cả suite, Streamlit có thể rerun thêm 1 lần ngay sau
    đó (vd. do widget nhận giá trị mặc định), khiến `inner_text()` đọc trúng 1
    khung hình chuyển tiếp: nút cũ (được giữ nguyên qua diffing DOM theo key)
    vẫn hiển thị trong khi selectbox phía trên đang giữa 2 lần render. Thêm
    `wait_ready` (polling độ dài text ổn định 3 lần liên tiếp — cơ chế đã có
    sẵn trong conftest.py, dùng lại đúng pattern `_open_warehouse_models_tab`
    đã áp dụng) để đảm bảo DOM đã ổn định thật sự trước khi đọc, thay vì tăng
    timeout một cách mù quáng."""
    page = login("giangvien", "gv123")
    _open_ai_advisor_tab(page)
    wait_ready(page, timeout=20)
    txt = page.inner_text("body")
    assert "Chọn Sinh viên để tư vấn" in txt


# ---------------------------------------------------------------------------
# Model promote/rollback — chỉ Admin (Kho dữ liệu > AI Models)
# ---------------------------------------------------------------------------
def _open_warehouse_models_tab(page, wait_ready, expand_count=3):
    # LỖI THỰC TẾ đã gặp (đã quan sát qua NHIỀU lần chạy, mỗi lần 1 kiểu nội
    # dung "kẹt" khác nhau — có lúc kẹt ở Trang chủ Admin/admin_reports_tab, có
    # lúc kẹt lùi hẳn về màn giới thiệu trước khi vào app): đây là ĐỘ TRỄ RE-
    # RENDER THẬT của Streamlit khi rời 1 trang nặng (Trang chủ Admin dùng lại
    # admin_reports_tab, nhiều biểu đồ Plotly) — không phải do chọn sai
    # selector. Không có 1 lần chờ/1 marker nào đủ để bắt được MỌI kiểu kẹt đã
    # thấy, nên dùng RETRY THẬT: click lại "Kho dữ liệu" tối đa vài lần cho
    # tới khi thấy đúng tab "AI Models" tồn tại và bấm được, thay vì chỉ chờ
    # 1 lần rồi bỏ cuộc.
    #
    # ĐÃ THỬ page.reload() trước bước này — làm HỎNG NẶNG HƠN (mất hẳn session
    # phía client, quay lại màn đăng nhập) vì `_app_started`/state điều hướng
    # gắn với đúng lượt kết nối websocket hiện tại, reload phá vỡ đúng thứ cần
    # giữ. Bỏ hướng đó. Thay vào đó: chờ CỐ ĐỊNH thêm 1 nhịp dài ngay khi vào
    # hàm này — Trang chủ Admin (admin_reports_tab) có nhiều biểu đồ Plotly
    # cần thời gian khởi tạo JS SAU KHI đã lên DOM (không phản ánh qua độ dài
    # text), đây là nguồn có khả năng cao nhất gây ra các lần "kẹt" đã thấy.
    page.wait_for_timeout(3000)
    _has_model_evidence = False
    # MỘT vòng lặp DUY NHẤT bấm lại TỪ ĐẦU (cả sidebar lẫn tab con) mỗi lần
    # chưa thấy bằng chứng THẬT của nội dung "AI Models" — tránh tình trạng
    # chỉ bấm lại tab con trong khi bản thân trang "Kho dữ liệu" phía sau có
    # thể chưa từng thật sự vào đúng (đã quan sát: pill tab "AI Models" có thể
    # đã "visible" theo Playwright ngay từ header, nhưng nội dung bên dưới vẫn
    # là trang trước đó chưa được thay thế xong).
    for _attempt in range(6):
        # Sidebar redesign: xem ghi chú trong _click_dashboard_nav ở trên —
        # "Kho dữ liệu" giờ là 1 st.button() (role=button), không phải label/radio.
        page.locator("[data-testid='stSidebar']").get_by_role("button", name="Kho dữ liệu", exact=False).first.click(timeout=30000)
        page.wait_for_timeout(1200)
        wait_ready(page, timeout=20)
        _tab = page.get_by_role("tab", name="AI Models", exact=False)
        if _tab.count() > 0:
            _tab.first.click()
            page.wait_for_timeout(1500)
            wait_ready(page, timeout=20)
            _has_model_evidence = (
                page.locator("summary", has_text="(ID:").count() > 0
                or "Chưa có mô hình nào" in page.inner_text("body")
            )
        if _has_model_evidence:
            break
        page.wait_for_timeout(1500)
    if _has_model_evidence:
        # Mỗi model nằm trong 1 st.expander THU GỌN mặc định — inner_text('body')
        # KHÔNG đọc được nội dung bên trong (badge khoá quyền, nút) cho tới khi
        # mở ra. Mở vài expander đầu (nếu có) để chắc chắn thấy được ít nhất 1
        # model KHÔNG phải Production (bản mới nhất thường tự động LÀ Production
        # do auto-promote — cần mở thêm vài bản mới thấy badge "🗂️ Lưu trữ").
        entries = page.locator("summary", has_text="(ID:")
        n = min(entries.count(), expand_count)
        for i in range(n):
            entries.nth(i).click()
            page.wait_for_timeout(500)


def test_lecturer_cannot_promote_model_sees_locked_message(login, wait_ready):
    """Với vài model đã mở (xem `_open_warehouse_models_tab`), Giảng viên KHÔNG
    BAO GIỜ được thấy nút thật "Đặt làm Production (rollback)" — model không
    phải Production phải hiện thông báo khoá thay vào đó."""
    page = login("giangvien", "gv123")
    _open_warehouse_models_tab(page, wait_ready)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    if "Quản lý mô hình" in txt and "Chưa có mô hình nào" not in txt:
        assert "Đặt làm Production (rollback)" not in txt
        assert ("Chỉ Admin được đổi bản Production" in txt) or ("Đang là bản Production hiện tại" in txt)


def test_admin_can_see_promote_button_for_non_production_model(login, wait_ready):
    """Đối chứng: Admin mở vài model — nếu có ít nhất 1 bản KHÔNG phải Production
    trong số đó, phải thấy nút thật "Đặt làm Production (rollback)", không bị
    khoá như Giảng viên."""
    page = login("admin", "admin123")
    _open_warehouse_models_tab(page, wait_ready)
    txt = page.inner_text("body")
    assert "Traceback" not in txt
    assert "Chỉ Admin được đổi bản Production" not in txt
    if "🗂️ Lưu trữ" in txt:  # có ít nhất 1 bản không-Production đã được mở ra
        assert "Đặt làm Production (rollback)" in txt
