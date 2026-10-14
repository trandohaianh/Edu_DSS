"""DSS Streamlit app — routing and sidebar."""
from __future__ import annotations

import sys
from pathlib import Path

# Khi chạy `streamlit run dss/main.py`, Python chỉ thêm thư mục `dss/` vào sys.path.
# Thêm thư mục gốc project để `import dss.*` hoạt động.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_root_str = str(_PROJECT_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dss.config import apply_plotly_patches, inject_styles, install_display_text_filter, setup_page
from dss.core.data_helpers import generate_data, generate_lms_data, load_data
from dss.core.init_app import clear_all_session_state_for_new_data, init_trainers_and_warehouse
from dss.core import bootstrap_service
from dss.core.logging_config import get_logger
from dss.tabs import loading_screen
from dss.tabs.advisory import student_advisory_tab
from dss.tabs.learning_explainer_tab import learning_explainer_tab
from dss.tabs.ai_advisor import ai_advisor_tab
from dss.tabs.clustering import clustering_hybrid_tab
from dss.tabs.dashboard import main_dashboard_tab, render_dashboard_activity_feed
from dss.tabs.eda import data_exploration_tab
from dss.tabs.ml_hub import (
    batch_prediction_tab,
    file_prediction_tab,
    personal_prediction_tab,
    render_training_config_ui,
)
from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, filter_tabs_for_role, display_label, nav_label
from dss.config import THEME_LABELS, THEME_MODES, current_theme
from dss.services import auth_service, search_service, subscription_service
from dss.services import model_service
from dss.services.model_service import (
    build_metrics_dataframe as _build_metrics_dataframe,
    clear_prediction_training_state as _clear_prediction_training_state,
    run_training as _run_ml_hub_training,
    resolve_production_for_prediction,
    resolve_ranking_col as _resolve_ranking_col,
)
from dss.tabs.home import render_home_tab
from dss.tabs.warehouse_tab import warehouse_tab, model_registry_tab
from dss.tabs.admin_reports import admin_reports_tab
from dss.tabs.consultation_history import consultation_history_tab
from dss.tabs.knowledge_base import knowledge_base_tab, lecturer_document_approval_tab
from dss.tabs.ai_advisor import ai_configuration_tab
from dss.tabs.admin_settings import admin_settings_tab, admin_users_tab, admin_integration_tab
from dss.tabs.university_onboarding_tab import university_onboarding_tab
from dss.tabs import ui_kit


ROOT = Path(__file__).resolve().parent.parent
_main_logger = get_logger(__name__)

setup_page()
apply_plotly_patches()
install_display_text_filter()
inject_styles()

clf, reg, llm_integration, wh = init_trainers_and_warehouse()

# --- GIAO DIỆN SIDEBAR (THANH BÊN TRÁI) ---
# Nút toggle sidebar - đặt ở đầu sidebar
# --- GIAO DIỆN SIDEBAR (THANH BÊN TRÁI) ---
# Nút toggle sidebar - đặt ở main để luôn hiển thị

# --- ĐĂNG NHẬP (Phase 1 refactor) ---
# Thay cho render_role_switcher() (tự chọn vai trò, không mật khẩu) — mọi vai
# trò giờ đi qua ĐÚNG 1 cổng đăng nhập, danh tính lấy từ session đã xác thực,
# không còn tin bất kỳ tham số nào do người dùng tự chọn trên UI.
#
# Thanh sidebar (brand/menu) CHỈ dựng SAU khi đăng nhập thành công — trước đó
# màn hình login là 1 màn hình riêng, full-bleed, không có app-shell/sidebar
# nào lẫn vào (trước đây khối brand dưới đây render TRƯỚC gate, khiến 1 dải
# sidebar tối trống hiện ra ngay cả khi chưa đăng nhập).
_user = auth_service.render_login_gate()
if _user is None:
    st.stop()
current_role = _user["role"]
st.session_state["current_student_id"] = _user.get("student_id")

from dss.core.runtime_mode import synthetic_data_allowed
# Nhãn "dữ liệu mô phỏng" hiển thị theo CHÍNH dữ liệu của từng trang
# (ui_kit.render_synthetic_data_banner) — khung toàn cục cũ ở đây lặp lại cùng
# thông tin ngay phía trên nhãn đó và ghi sai khi đang dùng dữ liệu thật.

# Kiểm tra bản quyền thuê bao tổ chức (SaaS Entitlement Gate)
if not subscription_service.render_subscription_gate(current_role):
    if current_role == "Admin":
        st.warning("Thuê bao của tổ chức đang tạm khoá hoặc đã hết hạn. Vui lòng cập nhật thông tin hợp đồng.")
        if st.button("Mở cài đặt thuê bao", type="primary"):
            admin_settings_tab()
    st.stop()

# Tự động nạp dữ liệu mẫu nếu CHƯA có dữ liệu nào trong phiên, bất kể vai trò
# nào đang xem trước. Sinh viên không có nút tải dữ liệu ở sidebar (đúng thiết
# kế — không phải tác nhân của use case "Tải dữ liệu") — nhưng nếu chưa ai
# (Giảng viên/Admin) tải gì trong phiên này, Sinh viên sẽ bị kẹt hoàn toàn
# (mọi tab đều báo "chưa có dữ liệu"). Tự nạp sẵn dữ liệu mẫu một lần để tránh
# tình huống đó — Giảng viên/Admin vẫn có thể thay bằng dữ liệu thật bất cứ lúc nào.
# Đặt TRƯỚC màn tải (bên dưới) vì bootstrap cần có `current_df` để biết phải
# chuẩn bị gì.
if 'current_df' not in st.session_state:
    # Production Demo Policy (audit 2026-09): TUYỆT ĐỐI không âm thầm nạp dữ
    # liệu tổng hợp (synthetic) làm ngầm định trong môi trường REAL_LMS — hiện
    # CHƯA có connector LMS thật nào được nối dây thật sự (xem
    # dss/services/lms_connector.py: chỉ có STATUS_DEMO/MOCK/FUTURE_REAL, không
    # có luồng tự động nạp dữ liệu LMS thật vào current_df ở đây). Trung thực
    # báo "chưa có dữ liệu" còn hơn để người dùng thật nhìn nhầm số liệu giả là
    # số liệu thật. Hành vi DEMO_SYNTHETIC (mặc định, dev/test) giữ nguyên 100%.
    from dss.core.runtime_mode import synthetic_data_allowed
    if not synthetic_data_allowed():
        ui_kit.page_header("Chưa có dữ liệu học tập")
        ui_kit.error_state(
            "Chưa kết nối dữ liệu LMS",
            "Hệ thống đang chạy ở chế độ REAL_LMS nhưng chưa có dữ liệu LMS thật nào được "
            "kết nối cho phiên này. Không có dữ liệu mô phỏng nào được hiển thị thay thế.",
            support_hint="Vui lòng liên hệ Quản trị viên để hoàn tất tích hợp LMS trước khi sử dụng.",
        )
        if st.button("Đăng xuất", key="btn_logout_no_data"):
            auth_service.logout()
            st.rerun()
        st.stop()
    # Dữ liệu demo mặc định của ứng dụng phải khớp với benchmark quy mô LMS giả lập:
    # 20.000 sinh viên mô phỏng. Dữ liệu này vẫn là synthetic/demo và phải được
    # nhãn rõ ràng trong UI theo chính sách minh bạch dữ liệu.
    st.session_state.current_df = generate_data(n_students=20000, random_state=42)
    st.session_state.current_dataset_id = "sample_data_lms_scale_v1"

# ============================================================================
# MÀN TẢI EDUDSS — thay thế TOÀN BỘ sidebar + log kỹ thuật bootstrap/huấn
# luyện từng lộ ra ngay sau đăng nhập (yêu cầu thiết kế: "loading screen phải
# THAY THẾ nội dung trang, không phải che tạm/ẩn bằng CSS"). Áp dụng NHẤT QUÁN
# cho cả 3 vai trò: Giảng viên, Sinh viên, Admin ngay sau khi đăng nhập thành công.
# Tiến độ THẬT theo từng giai đoạn khởi tạo thật (không phải sleep() giả) — xem
# `bootstrap_service.initialize_workspace`.
# ============================================================================
_bootstrap_dataset_id = st.session_state.get("current_dataset_id")
_ready_key = f"{_user['username']}::{current_role}::{_bootstrap_dataset_id}"
if st.session_state.get("_workspace_ready_for") != _ready_key:
    _loading_slot = st.empty()

    def _on_bootstrap_progress(pct, stage_key):
        with _loading_slot.container():
            loading_screen.render_loading_screen(
                pct, loading_screen.stage_message(stage_key, current_role, pct), current_role,
            )

    try:
        bootstrap_service.initialize_workspace(
            current_role, st.session_state.current_df, wh, clf, reg,
            progress_callback=_on_bootstrap_progress,
        )
        st.session_state["_workspace_ready_for"] = _ready_key
        _loading_slot.empty()
        st.rerun()
    except Exception:
        _main_logger.exception("Lỗi khởi tạo workspace sau đăng nhập (mã EDSS-INIT-001).")
        with _loading_slot.container():
            _retry_clicked, _logout_clicked = loading_screen.render_error_screen(error_code="EDSS-INIT-001")
        if _retry_clicked:
            st.rerun()
        if _logout_clicked:
            auth_service.logout()
            st.rerun()
        st.stop()

# ============================================================================
# APP SHELL (C1.3) — sidebar: thương hiệu · điều hướng theo vai trò · hồ sơ/giao
# diện/đăng xuất. Chỉ dựng SAU khi xác thực và workspace đã sẵn sàng.
# ============================================================================
st.sidebar.markdown(
    """
<div class="dss-sidebar-shell">
    <div class="dss-sidebar-brand-row">
        <span class="dss-sidebar-brand-logo">ED</span>
        <div>
            <p class="dss-sidebar-brand-name">EduDSS</p>
            <p class="dss-sidebar-brand-sub">Hỗ trợ quyết định học tập</p>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# Nhóm điều hướng theo MỤC TIÊU của từng vai trò. Giá trị là khoá tab gốc
# (TAB_ACCESS trong dss/core/roles.py) — nhãn hiển thị lấy qua nav_label(),
# nên đổi tên hiển thị không ảnh hưởng RBAC. Tiêu đề nhóm hiển thị dạng chữ
# hoa nhỏ (CSS), giữ nguyên chuỗi gốc.
SIDEBAR_NAV_GROUPS = {
    "Sinh viên": [
        ("TỔNG QUAN", [HOME_TAB_LABEL]),
        # "Lịch sử tư vấn" là lịch sử các lượt dùng Trợ lý AI — đi cùng nhóm
        # TRỢ LÝ AI (gom theo mục tiêu người dùng, không theo thứ tự tạo tab).
        ("HỌC TẬP & PHÂN TÍCH", ["🧪 Huấn luyện — Dự đoán", "🔬 Phân cụm — Gợi ý"]),
        ("TRỢ LÝ AI", ["🤖 Tư vấn — AI (LLM)", "📝 Lịch sử tư vấn"]),
    ],
    "Giảng viên / CVHT": [
        ("TỔNG QUAN", [HOME_TAB_LABEL, "📊 Dashboard"]),
        ("PHÂN TÍCH LỚP HỌC", ["🔍 Khám phá — Xử lý dữ liệu", "🧪 Huấn luyện — Dự đoán", "🔬 Phân cụm — Gợi ý"]),
        ("HỖ TRỢ & TÀI LIỆU", ["🤖 Tư vấn — AI (LLM)", "📄 Duyệt tài liệu", "📦 Kho dữ liệu"]),
    ],
    "Admin": [
        ("TỔNG QUAN", [HOME_TAB_LABEL]),
        ("NGƯỜI DÙNG & DỮ LIỆU", ["👥 Người dùng", "📦 Kho dữ liệu", "🔍 Khám phá — Xử lý dữ liệu"]),
        ("TRI THỨC & AI", ["📚 Quản lý tri thức (RAG)", "⚙️ Cấu hình AI", "🤖 Tư vấn — AI (LLM)"]),
        ("VẬN HÀNH", ["🔗 Tích hợp LMS/CMS", "🗄️ Model Registry", "📈 Báo cáo hệ thống", "🔧 Cài đặt"]),
    ],
}

# Không còn màn giới thiệu "Bắt đầu khám phá" giữa đăng nhập và ứng dụng —
# người dùng vào thẳng Trang chủ theo vai trò. Cờ `_app_started` giữ lại vì
# logout()/E2E vẫn tham chiếu tới nó.
st.session_state["_app_started"] = True

tabs_list = filter_tabs_for_role(ALL_TABS, current_role)
_pending_nav = st.session_state.pop("_pending_nav_target", None)
if _pending_nav in tabs_list:
    st.session_state["main_nav_radio"] = _pending_nav
elif st.session_state.get("main_nav_radio") not in tabs_list:
    st.session_state["main_nav_radio"] = tabs_list[0] if tabs_list else None

selected_nav_tab = st.session_state.get("main_nav_radio", tabs_list[0] if tabs_list else None)
groups = SIDEBAR_NAV_GROUPS.get(current_role, [("ĐIỀU HƯỚNG", tabs_list)])


def _render_nav_item(tab_key: str) -> None:
    if st.button(
        nav_label(tab_key, current_role),
        key=f"nav_btn_{tab_key}",
        type="primary" if tab_key == selected_nav_tab else "secondary",
        use_container_width=True,
    ):
        st.session_state["main_nav_radio"] = tab_key
        st.rerun()


rendered_tabs = set()
with st.sidebar.container(key="dss_main_nav_rail"):
    for grp_index, (grp_title, grp_items) in enumerate(groups):
        valid_items = [it for it in grp_items if it in tabs_list]
        if not valid_items:
            continue
        # Nhóm đầu chỉ có 1 mục (Trang chủ/Tổng quan) không cần tiêu đề lặp lại.
        if not (grp_index == 0 and len(valid_items) == 1):
            st.markdown(f'<div class="dss-sidebar-group-title">{grp_title}</div>', unsafe_allow_html=True)
        for it in valid_items:
            rendered_tabs.add(it)
            _render_nav_item(it)

    remaining_tabs = [it for it in tabs_list if it not in rendered_tabs]
    if remaining_tabs:
        st.markdown('<div class="dss-sidebar-group-title">KHÁC</div>', unsafe_allow_html=True)
        for it in remaining_tabs:
            _render_nav_item(it)

# Chân sidebar — dựng NGAY sau menu (trước nội dung trang) để luôn hiện kể cả
# khi trang con gọi st.stop().
_ROLE_DISPLAY = {"Giảng viên / CVHT": "Giảng viên / Cố vấn học tập", "Sinh viên": "Sinh viên", "Admin": "Quản trị viên"}
with st.sidebar.container(key="dss_sidebar_footer"):
    _uname = str(_user.get("username") or "")
    st.markdown(
        "<div class='dss-profile'>"
        f"<span class='dss-profile-avatar' aria-hidden='true'>{ui_kit._html.escape(_uname[:1].upper() or '?')}</span>"
        "<div style='min-width:0;'>"
        f"<div class='dss-profile-name'>{ui_kit._html.escape(_uname)}</div>"
        f"<div class='dss-profile-role'>{_ROLE_DISPLAY.get(current_role, current_role)}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    _active_theme = current_theme()
    _theme_choice = st.segmented_control(
        "Giao diện",
        options=list(THEME_MODES),
        format_func=lambda m: THEME_LABELS[m],
        default=_active_theme,
        key="sidebar_theme_mode",
        width="stretch",
    )
    if _theme_choice and _theme_choice != _active_theme:
        st.session_state["dss_theme"] = _theme_choice
        st.rerun()
    if st.button("Đăng xuất", key="btn_logout", use_container_width=True):
        auth_service.logout()
        st.rerun()


# Thông báo kết quả thao tác của lượt chạy trước (lưu/nạp dữ liệu...).
if 'show_success_message' in st.session_state:
    st.success(ui_kit.strip_decoration(st.session_state.show_success_message))
    del st.session_state.show_success_message  # Xóa thông báo sau khi hiển thị

# FINAL PRODUCTION GAP CLOSURE (Phần 3/4, "'success' giả"): counterpart trung
# thực của show_success_message — luồng lưu thất bại hiện đúng lỗi thay vì
# "Đã lưu" giả.
if 'show_error_message' in st.session_state:
    st.session_state.show_error_message = ui_kit.strip_decoration(st.session_state.show_error_message)
    st.error(st.session_state.show_error_message)
    del st.session_state.show_error_message

df = st.session_state.current_df if 'current_df' in st.session_state else None


def _render_no_data_state(action_text: str) -> None:
    """Trạng thái rỗng thống nhất khi trang cần dữ liệu lớp học nhưng chưa có."""
    ui_kit.empty_state(
        "Chưa có dữ liệu học tập",
        hint=f"Cần một bộ dữ liệu lớp học để {action_text}.",
    )
    if "📦 Kho dữ liệu" in tabs_list and st.button("Mở Kho dữ liệu", key="goto_warehouse_from_empty", type="primary"):
        st.session_state["_pending_nav_target"] = "📦 Kho dữ liệu"
        st.rerun()


if True:  # khối nội dung trang (giữ thụt lề cũ để diff gọn)
    selected_main_tab = selected_nav_tab if selected_nav_tab in tabs_list else (tabs_list[0] if tabs_list else None)

    # Thanh công cụ phía trên — CHỈ có ô tìm sinh viên cho vai trò được phép
    # (search_service.ROLES_ALLOWED_STUDENT_SEARCH). Không còn chấm "Hệ thống
    # hoạt động" (không dựa trên kiểm tra sức khoẻ thật) hay chuông đếm hoạt
    # động (không phải thông báo thật).
    _tb_query = ""
    if current_role in search_service.ROLES_ALLOWED_STUDENT_SEARCH:
        with st.container(key="dss_topbar"):
            _tb_spacer, _tb_search = st.columns([2.2, 1], vertical_alignment="center")
            with _tb_search:
                _tb_query = st.text_input(
                    "Tìm sinh viên theo mã số",
                    placeholder="Tìm sinh viên theo mã số…",
                    label_visibility="collapsed", key="topbar_student_search",
                )
    if current_role in search_service.ROLES_ALLOWED_STUDENT_SEARCH and _tb_query:
        _search_results = search_service.search_students(df, _tb_query, role=current_role)
        with st.container(border=True):
            if not _search_results:
                st.caption(search_service.format_empty_state_message(_tb_query))
                st.caption("Hãy kiểm tra lại mã sinh viên hoặc từ khóa tìm kiếm.")
            else:
                st.caption(f"{len(_search_results)} kết quả cho \"{_tb_query}\"")
                for _result in _search_results:
                    _rcol_info, _rcol_action = st.columns([4, 1.4], vertical_alignment="center")
                    with _rcol_info:
                        _name_part = f" — {_result.student_name}" if _result.student_name else ""
                        st.markdown(f"**{_result.student_id}**{_name_part} · Sinh viên")
                        if _result.metrics:
                            st.caption(" · ".join(f"{lbl}: {val}" for lbl, val in _result.metrics))
                    with _rcol_action:
                        if st.button(
                            "Xem phân tích", key=f"tb_search_action_{_result.student_id}",
                            width="stretch",
                        ):
                            # Điều hướng THẬT: đặt sẵn lựa chọn cho selectbox "Chọn
                            # Sinh viên để tư vấn" của tab Trợ lý AI rồi chuyển sang
                            # tab đó (Mục A4 — chỉ hiện đích thực sự hỗ trợ được).
                            st.session_state["llm_student_select"] = _result.student_id
                            st.session_state["_pending_nav_target"] = "🤖 Tư vấn — AI (LLM)"
                            st.rerun()

    # --- TAB TRANG CHỦ ---
    if selected_main_tab == HOME_TAB_LABEL:
        render_home_tab(
            current_role,
            wh,
            dashboard_mode=True,
            current_student_id=st.session_state.get("current_student_id"),
            df=df,
            llm_integration=llm_integration,
        )

    # --- TAB DASHBOARD (không gian phân tích chuyên sâu — TÁCH BIỆT với
    # HOME_TAB_LABEL "Trang chủ" phía trên, xem home.py::render_lecturer_home) ---
    elif selected_main_tab == "📊 Dashboard":
        if df is not None:
            main_dashboard_tab(df, wh)
            ss = st.session_state  # type: ignore
            _frag = getattr(st, "fragment", None)
            if _frag is not None:
                from datetime import timedelta

                @_frag(run_every=timedelta(seconds=25))
                def _dashboard_live_activity():
                    # Dùng lại singleton `wh` (Phase 8) thay vì tạo DataWarehouse()
                    # mới mỗi 25s — fragment vẫn có quyền truy cập biến module-level
                    # này qua closure như phần còn lại của main.py.
                    render_dashboard_activity_feed(wh, st.session_state)

                _dashboard_live_activity()
            else:
                render_dashboard_activity_feed(wh, ss)
        else:
            _render_no_data_state("xem Dashboard lớp học")

    # --- TAB KHÁM PHÁ ---
    # --- TAB KHÁM PHÁ ---
    elif selected_main_tab == "🔍 Khám phá — Xử lý dữ liệu":
        if df is not None:
            data_exploration_tab(df, wh)
        else:
            _render_no_data_state("khám phá và xử lý dữ liệu")

    # --- TAB HUẤN LUYỆN ---
    # --- TAB HUẤN LUYỆN ---
    elif selected_main_tab == "🧪 Huấn luyện — Dự đoán":
        if df is not None:
            # Student Role Audit (2026-09): Sinh viên chỉ có phiếu dự đoán cá
            # nhân (xem nhánh `current_role == "Sinh viên"` bên dưới — không có
            # tab Huấn luyện/GridSearchCV nào), nên tiêu đề trang phải phản ánh
            # đúng trải nghiệm đó thay vì luôn nói "Huấn luyện" cho mọi vai trò.
            if current_role == "Sinh viên":
                ui_kit.section_header(
                    "Dự đoán kết quả học tập của bạn",
                    subtitle="Nhập thông tin học tập để xem dự đoán từ mô hình đang dùng cho lớp bạn.",
                    icon="🧪",
                )
            else:
                ui_kit.section_header(
                    "Huấn luyện & Dự đoán",
                    subtitle="Sử dụng học máy để dự đoán kết quả học tập.",
                    icon="🧪",
                )

            # Student Role Audit (2026-09): thông báo kỹ thuật (pipeline/CV) và
            # từ điển thuật ngữ ML (GridSearchCV, overfitting, data leakage...)
            # chỉ có ý nghĩa với người THỰC SỰ huấn luyện mô hình (Giảng viên/
            # Admin) — Sinh viên chỉ điền phiếu và xem dự đoán, không cần thấy
            # thuật ngữ này (Section 39: tránh phơi bày chi tiết kỹ thuật không
            # phục vụ mục tiêu của Sinh viên).
            if current_role != "Sinh viên":
                # Thông báo về dữ liệu — trạng thái ngắn gọn thay cho khối HTML màu
                # cũ (đúng yêu cầu bỏ "old instruction boxes" kiểu notebook).
                # Chuẩn chống leakage: luôn train từ dữ liệu gốc và để tiền xử lý nằm trong pipeline/CV.
                cleaned_df = st.session_state.get('cleaned_df')
                if cleaned_df is not None:
                    ui_kit.render_badge("✅ Đã có dữ liệu làm sạch để tham khảo — huấn luyện vẫn dùng dữ liệu gốc, tiền xử lý nằm trong pipeline CV (chống rò rỉ dữ liệu).", kind="success")
                else:
                    ui_kit.render_badge("ℹ️ Chưa có dữ liệu làm sạch sẵn — hệ thống dùng dữ liệu gốc, tiền xử lý sau khi chia train/test trong pipeline CV.", kind="info")

                # Hướng dẫn nhanh + từ điển thuật ngữ — gộp vào 1 expander phụ trợ
                # DUY NHẤT, thu gọn mặc định, đặt dưới cùng của phần mở đầu để không
                # chiếm chỗ màn hình chính (nội dung KHÔNG đổi, chỉ gộp trình bày).
                with st.expander("Quy trình thực hiện & từ điển thuật ngữ", expanded=False):
                    st.markdown("""
                    <ol style='color: var(--text-primary); line-height: 2; margin: 0;'>
                        <li><strong>Khám phá dữ liệu</strong> ở tab trước và kiểm tra thống kê sau làm sạch</li>
                        <li><strong>Chọn Target & Features</strong> theo mục tiêu bài toán (hệ thống tự động phát hiện loại bài toán)</li>
                        <li><strong>Huấn luyện mô hình</strong> (so sánh nhiều mô hình hoặc chọn 1 mô hình yêu thích)</li>
                        <li><strong>Đánh giá</strong> bằng MAE / RMSE / R2 và xem biểu đồ dự đoán so với thực tế</li>
                        <li><strong>Thực hiện dự đoán</strong> cho từng sinh viên hoặc toàn bộ lớp, sau đó tải kết quả</li>
                    </ol>
                    """, unsafe_allow_html=True)
                    st.markdown(
                        "---\n"
                        "- `train_test_split` (**chia dữ liệu train/test**)\n"
                        "- `cross-validation (CV)` (**kiểm định chéo**)\n"
                        "- `GridSearchCV` (**tìm tham số tối ưu bằng lưới + CV**)\n"
                        "- `Pipeline` (**chuỗi xử lý: tiền xử lý -> mô hình**)\n"
                        "- `Accuracy` (**độ chính xác tổng thể**), `F1-score` (**điểm cân bằng Precision/Recall**)\n"
                        "- `MAE` (**sai số tuyệt đối trung bình**), `RMSE` (**căn sai số bình phương trung bình**), `R2` (**mức giải thích biến thiên**)\n"
                        "- `overfitting` (**quá khớp**), `underfitting` (**thiếu khớp**), `data leakage` (**rò rỉ dữ liệu**)"
                    )
            df_train = df

            # Phase 8 refactor: KHÔNG tạo lại clf/reg/wh ở đây nữa — dùng đúng 3
            # singleton đã lấy từ init_trainers_and_warehouse() (dòng ~58, cache_
            # resource). Trước đây dòng này tạo bộ instance MỚI mỗi lần rerun,
            # trùng với bug "double-instantiation" đã ghi nhận ở app/5.py cũ.

            train_config = None
            if current_role == "Sinh viên":
                # Sinh viên chỉ có 1 khu vực (dự đoán) — không cần thanh tab 1 mục.
                tab_predict_ml = st.container()
                tab_train_ml = None
            else:
                st.caption(
                    "**Huấn luyện mô hình**: chọn Target, Features, tham số và chạy train một lần. "
                    "**Dự đoán**: chỉ dùng mô hình đã train — Nhập tay / Từ file / Hàng loạt."
                )
                tab_eval_ml, tab_train_ml, tab_predict_ml = st.tabs(
                    ["Kết quả đánh giá mô hình", "Huấn luyện mô hình", "Dự đoán"]
                )
                with tab_eval_ml:
                    from dss.tabs.evaluation_report import evaluation_report_tab
                    evaluation_report_tab()

            if tab_train_ml is not None:
                with tab_train_ml:
                    # Bố cục: TOP (tóm tắt ngữ cảnh) -> 3 CỘT (Cấu hình | Chạy huấn
                    # luyện & Đánh giá | Kết quả mô hình/Model Registry) -> BOTTOM
                    # (bảng so sánh đầy đủ + mức độ quan trọng đặc trưng). Toàn bộ
                    # widget/callback GIỮ NGUYÊN so với bản trước — chỉ đổi vị trí
                    # hiển thị theo đúng yêu cầu bố cục (không đổi business logic).
                    train_config = render_training_config_ui(
                        df_train, clf, reg, key_prefix="train_hub"
                    )

                    _target_for_status = train_config["target_col"] if train_config else None
                    _prod_status = None
                    if _target_for_status:
                        try:
                            _prod_status = resolve_production_for_prediction(
                                wh, st.session_state.get("current_dataset_id"), _target_for_status
                            )
                        except Exception:
                            _prod_status = {"status": "error", "message": "Không thể tra Model Registry."}

                    # --- TOP: tóm tắt ngữ cảnh (Dataset / Task / Thuật toán / Production) ---
                    with st.container(border=True):
                        _tcol1, _tcol2, _tcol3, _tcol4 = st.columns(4)
                        with _tcol1.container(key="ml_hub_dataset_metric"):
                            st.caption("Dataset")
                            st.markdown(
                                f"**{st.session_state.get('current_dataset_id', '—') or '—'}**"
                            )
                        _tcol2.metric("Target", _target_for_status or "—")
                        _tcol3.metric(
                            "Chiến lược huấn luyện",
                            train_config.get("training_strategy", "—") or "—" if train_config else "—",
                        )
                        if _prod_status and _prod_status.get("status") == "ok":
                            _tcol4.metric("Production", f"{_prod_status['model_name']} (v{_prod_status['version']})")
                        elif _prod_status and _prod_status.get("status") == "empty":
                            _tcol4.metric("Production", "Chưa có")
                        else:
                            _tcol4.metric("Production", "—")

                    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
                    col_train_exec, col_train_result = st.columns([1.3, 1], gap="medium")

                    with col_train_exec:
                        with st.container(border=True):
                            st.markdown("##### Chạy huấn luyện & Đánh giá")
                            if not train_config:
                                st.warning("⚠️ Chọn đủ **Target** và ít nhất **một Feature** ở panel cấu hình phía trên để huấn luyện.")
                            else:
                                training_strategy = train_config.get(
                                    "training_strategy", "So sánh nhiều mô hình (Compare)"
                                )
                                btn_train = "Tiến hành: Huấn luyện (Single)"
                                if "So sánh" in training_strategy:
                                    btn_train = "Tiến hành: So sánh các mô hình"
                                elif "Kết hợp" in training_strategy:
                                    btn_train = "Tiến hành: Huấn luyện & kết hợp (Ensemble)"

                                if st.button(btn_train, key="ml_hub_train_btn", type="primary", width="stretch"):
                                    with st.spinner(
                                        "Đang huấn luyện và đánh giá mô hình... "
                                        "Thời gian có thể lâu hơn khi chọn nhiều mô hình."
                                    ):
                                        _clear_prediction_training_state("hub")
                                        _run_ml_hub_training(df_train, train_config, clf, reg, wh)
                                    # Tab "Kết quả đánh giá mô hình" được render TRƯỚC tab này trong
                                    # cùng lượt chạy — rerun để nó hiển thị ngay kết quả vừa train.
                                    st.session_state.hub_train_flash = True
                                    st.rerun()
                                if st.session_state.pop("hub_train_flash", False):
                                    st.success(
                                        "✅ Huấn luyện xong. Xem chỉ số ở tab **Kết quả đánh giá mô hình**; "
                                        "dự đoán ở tab **Dự đoán**."
                                    )

                                with st.expander("Xóa kết quả hub (huấn luyện lại từ đầu)", expanded=False):
                                    if st.button(
                                        "Xóa kết quả huấn luyện đang lưu trong phiên",
                                        key="hub_reset_train",
                                        type="secondary",
                                    ):
                                        _clear_prediction_training_state("hub")
                                        st.rerun()

                    with col_train_result:
                        with st.container(border=True):
                            st.markdown("##### Kết quả mô hình / Model Registry")
                            if _target_for_status:
                                if _prod_status and _prod_status.get("status") == "ok":
                                    st.success(
                                        f"**{_prod_status['model_name']}** (v{_prod_status['version']}) đang là Production "
                                        f"cho target `{_target_for_status}`."
                                    )
                                elif _prod_status and _prod_status.get("status") == "empty":
                                    st.info(f"Chưa có Production cho target `{_target_for_status}`. Huấn luyện bên trái để tạo bản đầu tiên.")
                                else:
                                    st.warning((_prod_status or {}).get("message", "Không xác định được trạng thái Production."))
                            else:
                                st.caption("Chọn Target ở panel cấu hình để xem trạng thái Production tương ứng.")

                            if "hub_results" in st.session_state and st.session_state.hub_results:
                                st.markdown("---")
                                current_results = st.session_state.hub_results
                                current_hub_type = st.session_state.get("hub_type", "clf")
                                model_metrics_df = _build_metrics_dataframe(current_results, current_hub_type)
                                if not model_metrics_df.empty:
                                    # S-1: cùng tiêu chí xếp hạng với pick_best_model_name (is_best khi lưu Kho).
                                    rank_metric, rank_ascending = _resolve_ranking_col(model_metrics_df, current_hub_type)
                                    ranked_models_df = model_metrics_df.sort_values(rank_metric, ascending=rank_ascending)
                                    suggested_model = ranked_models_df.index[0]
                                    st.metric(
                                        "🏆 Mô hình tốt nhất",
                                        suggested_model,
                                        f"{rank_metric}: {ranked_models_df.iloc[0][rank_metric]:.4f}",
                                        delta_color="off",
                                    )
                                    _saved_n = st.session_state.get("hub_saved_candidate_count") or 0
                                    st.caption(
                                        f"Đã huấn luyện **{len(model_metrics_df)}** mô hình"
                                        + (f", lưu **{_saved_n}** bản Candidate vào Kho" if _saved_n else "")
                                        + ". Bảng so sánh đầy đủ và biểu đồ ở tab **Kết quả đánh giá mô hình**."
                                    )
                                    if not (_prod_status and _prod_status.get("status") == "ok"):
                                        st.caption(
                                            "ℹ️ Chưa có Production: Giảng viên vẫn dự đoán được ở tab **Dự đoán** bằng "
                                            "mô hình tốt nhất này; Sinh viên/Dashboard dùng được sau khi Admin Promote."
                                        )
                                else:
                                    st.warning("Không có metrics hợp lệ. Vui lòng kiểm tra cấu hình và huấn luyện lại.")

                    # --- BOTTOM: bảng so sánh đầy đủ + mức độ quan trọng đặc trưng ---
                    if "hub_results" in st.session_state and st.session_state.hub_results:
                        _bottom_metrics_df = _build_metrics_dataframe(
                            st.session_state.hub_results, st.session_state.get("hub_type", "clf")
                        )
                        if not _bottom_metrics_df.empty:
                            st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
                            col_bottom_fi = st.container()
                            with col_bottom_fi:
                                with st.container(border=True):
                                    st.markdown("##### Mức độ quan trọng đặc trưng")
                                    _fi_target2 = train_config["target_col"] if train_config else None
                                    # CHỈ cột số — preview_feature_importance() fit RandomForest, không tự
                                    # encode cột dạng chữ (vd. "xep_loai": Giỏi/Khá...), người dùng vẫn có
                                    # thể chọn cột này làm Feature ở panel cấu hình (dùng cho model chính
                                    # có encoder riêng), nhưng panel ước lượng nhanh này phải lọc lại.
                                    _fi_feats2 = [
                                        c for c in (train_config.get("selected_features", []) if train_config else [])
                                        if c in df_train.columns and pd.api.types.is_numeric_dtype(df_train[c])
                                    ]
                                    if _fi_target2 and len(_fi_feats2) >= 2:
                                        try:
                                            _fi_df2 = model_service.preview_feature_importance(df_train, _fi_feats2, _fi_target2).head(8)
                                            _fig_fi2 = px.bar(
                                                _fi_df2.sort_values("Importance (%)"), x="Importance (%)", y="Feature",
                                                orientation="h", text="Importance (%)",
                                            )
                                            _fig_fi2.update_traces(marker_color="#0d9488", textposition="outside")
                                            _fig_fi2.update_layout(template="plotly_white", height=280, margin=dict(t=10, b=10), showlegend=False)
                                            st.plotly_chart(_fig_fi2, width="stretch", key="ml_hub_feature_importance")
                                        except Exception as _fi_ex2:
                                            # Cắt ngắn thông điệp lỗi — 1 số ValueError của sklearn/pandas nhúng
                                            # nguyên mảng giá trị không hợp lệ vào message, có thể dài hàng nghìn
                                            # ký tự nếu render thẳng (đã gặp thực tế với cột dạng chữ lọt vào đây).
                                            ui_kit.empty_state("Không thể tính mức độ quan trọng đặc trưng.", hint=str(_fi_ex2)[:200])
                                    else:
                                        ui_kit.empty_state("Cần ít nhất 2 features để tính mức độ quan trọng.")

            with tab_predict_ml:
                before_outlier_rows = st.session_state.get("last_training_rows_before_outlier")
                after_outlier_rows = st.session_state.get("last_training_rows_after_outlier")
                outlier_mode_used = st.session_state.get("last_outlier_method", "none")
                if before_outlier_rows is not None and after_outlier_rows is not None:
                    st.info(
                        "📌 Lưu ý số mẫu: Huấn luyện dùng "
                        f"**{after_outlier_rows}** mẫu"
                        + (
                            f" (sau khi loại ngoại lai từ {before_outlier_rows} mẫu)"
                            if str(outlier_mode_used).lower() == "iqr"
                            else f" (không loại ngoại lai, ban đầu {before_outlier_rows} mẫu)"
                        )
                        + ". Các tab Dự đoán chạy trên **toàn bộ dữ liệu đầu vào** bạn cung cấp, "
                          "nên số mẫu dự đoán có thể lớn hơn số mẫu đã dùng huấn luyện."
                    )
                _sv_id = st.session_state.get("current_student_id")
                if current_role == "Sinh viên":
                    # "Hàng loạt" xuất dự đoán CẢ LỚP cùng lúc — không có ý
                    # nghĩa thu hẹp về 1 sinh viên nên ẩn hẳn với Sinh viên.
                    pred_tab_manual, pred_tab_single = st.tabs(
                        ["Dự đoán — Nhập tay", "Dự đoán — Dữ liệu đã có"]
                    )
                    pred_tab_batch = None
                else:
                    pred_tab_manual, pred_tab_single, pred_tab_batch = st.tabs(
                        [
                            "Dự đoán — Nhập tay",
                            "Dự đoán — Dữ liệu đã có",
                            "Dự đoán — Hàng loạt",
                        ]
                    )

                with pred_tab_manual:
                    personal_prediction_tab(df_train, clf, reg, wh, train_config, role=current_role)

                with pred_tab_single:
                    file_prediction_tab(df_train, clf, reg, wh, train_config, role=current_role, current_student_id=_sv_id)

                if pred_tab_batch is not None:
                    with pred_tab_batch:
                        batch_prediction_tab(df_train, clf, reg, wh, train_config)
        else:
            _render_no_data_state("huấn luyện và dự đoán")

    # --- TAB PHÂN CỤM & GỢI Ý ---
    # --- TAB PHÂN CỤM & GỢI Ý ---
    elif selected_main_tab == "🔬 Phân cụm — Gợi ý":
        if df is not None:
            clustering_hybrid_tab(df, wh, role=current_role, current_student_id=st.session_state.get("current_student_id"))
        else:
            _render_no_data_state("phân cụm sinh viên")

    # --- TAB TƯ VẤN AI ---
    # --- TAB TƯ VẤN AI ---
    elif selected_main_tab == "🤖 Tư vấn — AI (LLM)":
        if df is not None:
            llm_tabs_list = [
                "🤖 Tư vấn — AI (LLM)",
                "🧭 Tư vấn — Định hướng",
                "📖 Giải thích Bài giảng (CMS)",
            ]
            # Student Information Architecture (audit 2026-09): nhãn kỹ thuật
            # "AI (LLM)" / "CMS" chỉ có ý nghĩa với Giảng viên/Admin (người cấu
            # hình provider/nạp bài giảng). Sinh viên cần thấy MỤC TIÊU của
            # mình, không phải tên công nghệ đứng sau.
            _student_llm_tab_labels = {
                "🤖 Tư vấn — AI (LLM)": "Kế hoạch học tập",
                "🧭 Tư vấn — Định hướng": "Hướng nghiệp",
                "📖 Giải thích Bài giảng (CMS)": "Giải thích bài học",
            }

            def _llm_tab_label(tab_key: str) -> str:
                if current_role == "Sinh viên":
                    return _student_llm_tab_labels.get(tab_key, display_label(tab_key))
                return display_label(tab_key)

            with st.container(key="dss_llm_nav_rail"):
                selected_llm_tab = st.radio(
                    " ",
                    llm_tabs_list,
                    horizontal=True,
                    label_visibility="collapsed",
                    key="llm_nav_radio",
                    format_func=_llm_tab_label,
                )

            _sv_id_llm = st.session_state.get("current_student_id")
            if selected_llm_tab == llm_tabs_list[0]:
                ai_advisor_tab(df, llm_integration, role=current_role, current_student_id=_sv_id_llm, wh=wh)

            elif selected_llm_tab == llm_tabs_list[1]:
                student_advisory_tab(df, role=current_role, current_student_id=_sv_id_llm)

            elif selected_llm_tab == llm_tabs_list[2]:
                learning_explainer_tab(df, role=current_role, current_student_id=_sv_id_llm, llm_integration=llm_integration)
        else:
            _render_no_data_state("sử dụng Trợ lý AI")

    # --- TAB KHO DỮ LIỆU ---
    # --- TAB KHO DỮ LIỆU ---
    elif selected_main_tab == "📦 Kho dữ liệu":
        warehouse_tab(wh, role=current_role)

    # --- TAB MODEL REGISTRY (Admin) ---
    elif selected_main_tab == "🗄️ Model Registry":
        model_registry_tab(wh)

    # --- TAB QUẢN LÝ TRI THỨC / RAG (Admin) ---
    elif selected_main_tab == "📚 Quản lý tri thức (RAG)":
        knowledge_base_tab(llm_integration)

    # --- TAB DUYỆT TÀI LIỆU (Giảng viên / CVHT) ---
    elif selected_main_tab == "📄 Duyệt tài liệu":
        lecturer_document_approval_tab()

    # --- TAB CẤU HÌNH AI (Admin) ---
    elif selected_main_tab == "⚙️ Cấu hình AI":
        ai_configuration_tab(llm_integration)

    # --- TAB BÁO CÁO HỆ THỐNG (Admin) ---
    elif selected_main_tab == "📈 Báo cáo hệ thống":
        admin_reports_tab(wh, df=df)

    # --- TAB LỊCH SỬ TƯ VẤN (Sinh viên) ---
    elif selected_main_tab == "📝 Lịch sử tư vấn":
        consultation_history_tab(wh, current_student_id=st.session_state.get("current_student_id"))

    # --- TAB CÀI ĐẶT (Admin) ---
    elif selected_main_tab == "🔧 Cài đặt":
        admin_settings_tab()

    # --- TAB NGƯỜI DÙNG (Admin) ---
    elif selected_main_tab == "👥 Người dùng":
        admin_users_tab()

    # --- TAB TÍCH HỢP LMS/CMS (Admin) ---
    elif selected_main_tab == "🔗 Tích hợp LMS/CMS":
        admin_integration_tab()

    # --- TAB ONBOARDING TRƯỜNG ĐẠI HỌC (Platform Admin, Stage 2) ---
    elif selected_main_tab == "🏛️ Onboarding Trường Đại học":
        university_onboarding_tab()
