"""C1.3 — UI/UX redesign: regression tests for the design system, role
navigation, authentication UI and honest status rendering.

Rendering is exercised with Streamlit's AppTest (real script execution, real
widgets) where behaviour matters; static checks are used only for invariants
that are properties of the source (token definitions, no hard-coded colours).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest

APP = Path(__file__).resolve().parent.parent
MAIN_CSS = APP / "dss" / "styles" / "main.css"

REQUIRED_TOKENS = [
    "--bg-primary",
    "--bg-secondary",
    "--surface",
    "--surface-hover",
    "--surface-elevated",
    "--text-primary",
    "--text-secondary",
    "--text-muted",
    "--text-inverse",
    "--border",
    "--border-strong",
    "--primary",
    "--primary-hover",
    "--primary-soft",
    "--success",
    "--success-soft",
    "--warning",
    "--warning-soft",
    "--danger",
    "--danger-soft",
    "--info",
    "--info-soft",
    "--shadow-sm",
    "--shadow-md",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
]
# Colour tokens that must be redefined for dark mode (shape tokens need not be).
DARK_COLOUR_TOKENS = [t for t in REQUIRED_TOKENS if not t.startswith("--radius")]


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    return css[start : css.index("}", start)]


# ---------------------------------------------------------------- design tokens
def test_root_defines_every_required_token():
    root = _block(MAIN_CSS.read_text(encoding="utf-8"), ":root {")
    missing = [t for t in REQUIRED_TOKENS if f"{t}:" not in root]
    assert not missing, f"Thiếu token trong :root: {missing}"


def test_dark_mode_redefines_every_colour_token():
    css = MAIN_CSS.read_text(encoding="utf-8")
    dark = _block(css, ":root:has(.dss-theme-dark) {")
    missing = [t for t in DARK_COLOUR_TOKENS if f"{t}:" not in dark]
    assert not missing, f"Chế độ tối chưa định nghĩa lại: {missing}"


def test_component_library_has_no_hard_coded_colours():
    """ui_kit là nguồn component dùng chung — màu phải đến từ token CSS để
    cùng 1 component đúng ở cả sáng lẫn tối."""
    source = (APP / "dss" / "tabs" / "ui_kit.py").read_text(encoding="utf-8")
    hexes = re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", source)
    assert not hexes, f"ui_kit.py còn mã màu hex: {sorted(set(hexes))}"


@pytest.mark.parametrize(
    "rel",
    [
        "dss/tabs/home.py",
        "dss/tabs/admin_settings.py",
        "dss/tabs/admin_reports.py",
        "dss/tabs/dashboard.py",
        "dss/tabs/loading_screen.py",
        "dss/services/auth_service.py",
        "dss/main.py",
    ],
)
def test_redesigned_pages_have_no_hex_in_inline_styles(rel):
    source = (APP / rel).read_text(encoding="utf-8")
    offenders = [m.group(0)[:80] for m in re.finditer(r"style=(['\"])(.*?)\1", source, re.S) if "#" in m.group(2)]
    assert not offenders, f"{rel}: style inline còn mã màu hex: {offenders}"


def test_every_python_css_class_is_defined_in_main_css():
    css = MAIN_CSS.read_text(encoding="utf-8")
    defined = set(re.findall(r"\.([a-zA-Z][\w-]+)", css))
    undefined = {}
    for f in (APP / "dss").rglob("*.py"):
        for m in re.finditer(r"class=['\"]([^'\"{}]+)['\"]", f.read_text(encoding="utf-8")):
            for cls in m.group(1).split():
                if cls not in defined:
                    undefined.setdefault(cls, set()).add(f.name)
    assert not undefined, f"Class dùng trong Python nhưng không có trong main.css: {undefined}"


# ---------------------------------------------------------------- navigation / roles
def _sidebar_nav_groups():
    """Đọc SIDEBAR_NAV_GROUPS từ main.py (không chạy toàn bộ app)."""
    from dss.core import roles

    tree = ast.parse((APP / "dss" / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SIDEBAR_NAV_GROUPS" for t in node.targets):
            return eval(
                compile(ast.Expression(node.value), "main.py", "eval"),
                # Mọi hằng *_TAB_LABEL của roles.py (không liệt kê tay, để thêm trang mới
                # như 3 trang giảng viên không phải sửa test này).
                {name: getattr(roles, name) for name in dir(roles) if name.endswith("_TAB_LABEL")},
            )
    raise AssertionError("Không tìm thấy SIDEBAR_NAV_GROUPS trong main.py")


def test_sidebar_groups_only_reference_tabs_the_role_may_open():
    from dss.core.roles import ALL_TABS, filter_tabs_for_role

    for role, groups in _sidebar_nav_groups().items():
        allowed = set(filter_tabs_for_role(ALL_TABS, role))
        listed = [tab for _title, items in groups for tab in items]
        leaked = [t for t in listed if t not in allowed]
        assert not leaked, f"Nhóm điều hướng của {role} liệt kê tab không được phép: {leaked}"
        assert set(listed) == allowed, f"{role}: tab được phép nhưng không có trong nhóm nào: {allowed - set(listed)}"


def test_new_admin_pages_are_admin_only():
    from dss.core.roles import ALL_TABS, TAB_ACCESS, filter_tabs_for_role

    for tab in ("👥 Người dùng", "🔗 Tích hợp LMS/CMS"):
        assert tab in ALL_TABS
        assert TAB_ACCESS[tab] == {"Admin"}
    for role in ("Sinh viên", "Giảng viên / CVHT"):
        visible = filter_tabs_for_role(ALL_TABS, role)
        for admin_only in (
            "👥 Người dùng",
            "🔗 Tích hợp LMS/CMS",
            "⚙️ Cấu hình AI",
            "🔧 Cài đặt",
            "📈 Báo cáo hệ thống",
            "🗄️ Model Registry",
            "📚 Quản lý tri thức (RAG)",
        ):
            assert admin_only not in visible, f"{role} không được thấy {admin_only}"
    student = filter_tabs_for_role(ALL_TABS, "Sinh viên")
    for staff_only in ("📊 Dashboard", "📦 Kho dữ liệu", "🔍 Khám phá — Xử lý dữ liệu", "📄 Duyệt tài liệu"):
        assert staff_only not in student


def test_nav_labels_are_role_aware_and_emoji_free():
    from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, ROLES, filter_tabs_for_role, nav_label

    emoji = re.compile(r"[\u2600-\u27BF\U0001F000-\U0001FAFF]")
    for role in ROLES:
        for tab in filter_tabs_for_role(ALL_TABS, role):
            label = nav_label(tab, role)
            assert label and not emoji.search(label), (role, tab, label)
    assert nav_label(HOME_TAB_LABEL, "Admin") == "Tổng quan"
    assert nav_label("🧪 Huấn luyện — Dự đoán", "Sinh viên") == "Dự đoán kết quả"
    assert nav_label("🧪 Huấn luyện — Dự đoán", "Giảng viên / CVHT") == "Huấn luyện & dự đoán"


# ---------------------------------------------------------------- login / provisioning (AppTest)
LOGIN_SCRIPT = """
from dss.services import auth_service
user = auth_service.render_login_gate()
import streamlit as st
if user is not None:
    st.write("LOGGED_IN", user["username"], user["role"])
"""


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.error] + [e.label for e in at.expander]
    return "\n".join(str(p) for p in parts)


@pytest.fixture
def dev_env(monkeypatch, isolated_users_file):
    for var in ("EDUDSS_MODE", "EDUDSS_SHOW_DEMO_CREDENTIALS", "EDUDSS_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EDUDSS_ENV", "development")
    return isolated_users_file


def test_login_page_has_no_fabricated_metrics_and_explains_provisioning(dev_env):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(LOGIN_SCRIPT, default_timeout=60).run()
    assert not at.exception
    text = _texts(at)
    for fake in ("GPA dự đoán", "6.8", "3 ưu tiên", "AI Recommendation"):
        assert fake not in text, f"Trang đăng nhập còn số liệu minh hoạ giả: {fake!r}"
    assert "không hỗ trợ tự đăng ký" in text
    assert not [b for b in at.button if "đăng ký" in (b.label or "").lower()], "Không được có nút đăng ký giả"
    labels = [t.label for t in at.text_input]
    assert labels == ["Tên đăng nhập / Mã số sinh viên", "Mật khẩu"]


def test_login_validation_wrong_password_and_success(dev_env):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(LOGIN_SCRIPT, default_timeout=60).run()
    at.button[0].click().run()  # form submit with empty fields
    assert any("Vui lòng nhập tên đăng nhập và mật khẩu" in e.value for e in at.error)
    assert "_authenticated" not in at.session_state

    at.text_input[0].input("giangvien")
    at.text_input[1].input("sai-mat-khau")
    at.button[0].click().run()
    assert any("Sai tên đăng nhập hoặc mật khẩu" in e.value for e in at.error)
    assert "_authenticated" not in at.session_state

    at.text_input[1].input("gv123")
    at.button[0].click().run()
    assert at.session_state["_authenticated"] is True
    assert at.session_state["_auth_role"] == "Giảng viên / CVHT"
    assert any("LOGGED_IN" in str(m.value) for m in at.markdown)


def test_logout_clears_identity_and_ui_state(as_role):
    import streamlit as st

    from dss.services import auth_service

    as_role("Admin", username="admin")
    st.session_state["_app_started"] = True
    st.session_state["gemini_key_input"] = "should-not-survive"
    auth_service.logout()
    assert auth_service.current_user() is None
    assert "_app_started" not in st.session_state
    assert "gemini_key_input" not in st.session_state


# ---------------------------------------------------------------- errors never leak internals
def test_report_error_does_not_render_exception_text():
    from streamlit.testing.v1 import AppTest

    # AppTest.from_function writes the script with the OS default encoding
    # (cp1252 on Windows) — keep the function body ASCII-only.
    def script():
        from dss.tabs import ui_kit

        ui_kit.report_error("Save failed", RuntimeError("SECRET C:/internal/path.sql"))

    at = AppTest.from_function(script, default_timeout=30).run()
    assert not at.exception
    rendered = " ".join(e.value for e in at.error)
    assert "Save failed" in rendered
    assert "SECRET" not in rendered and "path.sql" not in rendered


def test_no_raw_exception_interpolation_left_in_user_facing_errors():
    offenders = []
    pattern = re.compile(r"st\.(?:error|warning)\(f\"[^\"\n]*\{(?:str\()?(?:e|ex|err|exc)\)?\}")
    for f in (APP / "dss" / "tabs").glob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{f.name}:{n}")
    assert not offenders, f"Còn hiển thị nội dung exception thô: {offenders}"


# ---------------------------------------------------------------- AI configuration never shows keys
class _FakeLLM:
    SECRET = "AIzaSyFAKE-KEY-0000000000000000001234"

    def get_api_key_from_secrets(self, provider):
        return self.SECRET if provider == "gemini" else None


def test_ai_configuration_never_renders_api_keys_and_is_honest_about_status():
    from streamlit.testing.v1 import AppTest

    def script():
        import streamlit as st

        st.session_state["_auth_role"] = "Admin"
        from dss.tabs.ai_advisor import ai_configuration_tab
        from tests.test_c1_3_ui_design_system import _FakeLLM

        ai_configuration_tab(_FakeLLM())

    at = AppTest.from_function(script, default_timeout=60).run()
    assert not at.exception
    text = _texts(at)
    assert _FakeLLM.SECRET not in text and _FakeLLM.SECRET[-4:] not in text
    assert "Đã có khoá" in text  # gemini configured
    assert "Chưa cấu hình" in text  # groq/openai not configured
    assert "Chưa kiểm tra" in text  # no connection claimed without a real check
    assert "Kết nối được" not in text


# ---------------------------------------------------------------- admin pages: no fake success
def test_admin_operational_checks_report_real_gaps_only():
    from dss.tabs.admin_reports import _operational_checks

    synthetic = pd.DataFrame({"x": [1, 2]})
    synthetic.attrs["data_source_type"] = "synthetic"
    checks = _operational_checks([], [], synthetic, None)
    titles = [c[1] for c in checks]
    assert "Đang dùng dữ liệu mô phỏng" in titles
    assert "Chưa có mô hình Production" in titles
    assert all(kind != "success" for kind, *_ in checks)

    real = pd.DataFrame({"x": [1, 2]})
    real.attrs["data_source_type"] = "uploaded"
    checks = _operational_checks([], [{"is_production": True}], real, None)
    titles = [c[1] for c in checks]
    assert "Đang dùng dữ liệu mô phỏng" not in titles
    assert "Chưa có mô hình Production" not in titles
    assert "LMS/CMS chưa kết nối" in titles  # still honest: no real LMS connection exists


def test_admin_integration_page_does_not_claim_a_live_connection():
    from streamlit.testing.v1 import AppTest

    def script():
        from dss.tabs.admin_settings import admin_integration_tab

        admin_integration_tab()

    at = AppTest.from_function(script, default_timeout=60).run()
    assert not at.exception
    text = _texts(at)
    assert "Chưa kết nối" in text
    assert "Trực tuyến" not in text and "Live Webhook" not in text


def test_admin_users_page_lists_accounts_and_crud_is_wired(dev_env):
    """Trước bản full-stack, trang này cố ý KHÔNG có nút Tạo/Khoá vì chưa có service nào phía
    sau (tránh CRUD giả). Nay form gọi auth_service.admin_* thật (kiểm tra vai trò Admin ở tầng
    service + nhật ký kiểm toán): bấm Tạo phải thật sự tạo tài khoản."""
    from streamlit.testing.v1 import AppTest

    from dss.services import auth_service

    auth_service._seed_default_accounts_if_missing()

    def script():
        from dss.tabs.admin_settings import admin_users_tab

        admin_users_tab()

    at = AppTest.from_function(script, default_timeout=60)
    at.session_state["_authenticated"] = True
    at.session_state["_auth_role"] = "Admin"
    at.session_state["_auth_username"] = "admin"
    at.run()
    assert not at.exception
    assert len(at.dataframe) == 1
    listed = set(at.dataframe[0].value["Tên đăng nhập"])
    assert {"admin", "giangvien"} <= listed
    labels = {t.label: t for t in at.text_input}
    labels["Tên đăng nhập"].input("gv.moi")
    labels["Mật khẩu ban đầu (≥ 10 ký tự)"].input("mat-khau-dai-123")
    labels["Email Google (tuỳ chọn)"].input("gv.moi@truong.edu.vn")
    next(b for b in at.button if b.label == "Tạo tài khoản").click().run()
    assert not at.exception
    created = auth_service._load_users()["gv.moi"]
    assert created["role"] == "Giảng viên / CVHT" and created["email"] == "gv.moi@truong.edu.vn"


# ---------------------------------------------------------------- student home
def test_student_home_quick_ask_no_longer_reads_undefined_role_variable():
    """Trước C1.3, nhánh hỏi nhanh gọi `role=role or ...` với `role` KHÔNG tồn
    tại trong hàm -> NameError -> luôn hiện lỗi. Không được còn biến tự do nào
    tên `role` trong hàm này."""
    import inspect
    import textwrap

    from dss.tabs import home

    tree = ast.parse(textwrap.dedent(inspect.getsource(home._render_student_home_dashboard)))
    fn = tree.body[0]
    params = {a.arg for a in fn.args.args}
    assigned = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    loads = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert "role" not in loads - params - assigned


def test_student_next_actions_come_from_student_data_only():
    from dss.tabs.home import _next_actions_for_student

    df = pd.DataFrame({"ty_le_diem_danh": [0.6], "so_gio_hoc_tuan": [5]})
    actions = _next_actions_for_student(df.iloc[0], [("so_gio_hoc_tuan", -0.4)], df)
    titles = [a[0] for a in actions]
    assert any("Cải thiện" in t for t in titles)
    assert "Tăng tỷ lệ điểm danh" in titles
    assert _next_actions_for_student(pd.DataFrame({"a": [1]}).iloc[0], [], pd.DataFrame({"a": [1]})) == []
