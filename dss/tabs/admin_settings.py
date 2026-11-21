"""Các trang quản trị dành riêng cho Admin: Người dùng, Tích hợp LMS/CMS, Cài đặt.

C1.3: trước đây 3 khối này dồn chung 1 trang "Cài đặt". Tách thành 3 trang để
điều hướng Admin phản ánh đúng các nhóm việc; dữ liệu/service đứng sau KHÔNG
đổi (auth_service, subscription_service, lms_connector, lms_live_sync) và
không có chức năng nào được giả lập thêm.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from dss.core.data_helpers import is_production_environment
from dss.core.display_mapper import (
    SUBSCRIPTION_PLAN_TO_VIETNAMESE,
    map_subscription_status,
)
from dss.services import auth_service, subscription_service
from dss.tabs import ui_kit

_SUBSCRIPTION_STATUSES = ["ACTIVE", "EXPIRED", "SUSPENDED"]
_SUBSCRIPTION_PLANS = ["STARTER", "PROFESSIONAL", "ENTERPRISE"]


# ---------------------------------------------------------------------------
# Người dùng
# ---------------------------------------------------------------------------
def admin_users_tab():
    ui_kit.page_header(
        "Người dùng",
        subtitle="Tài khoản đang có trong hệ thống và vai trò được cấp.",
    )

    try:
        user_counts = auth_service.count_users_by_role()
        all_users = auth_service._load_users()
    except Exception:
        ui_kit.error_state(
            "Không đọc được danh sách tài khoản",
            "Kho tài khoản tạm thời không phản hồi. Không có dữ liệu nào bị thay đổi.",
            support_hint="Thử tải lại trang; nếu vẫn lỗi, kiểm tra kết nối cơ sở dữ liệu.",
        )
        return

    if user_counts:
        ui_kit.kpi_row(
            [("Tổng tài khoản", sum(user_counts.values()))]
            + [(role_name, count) for role_name, count in sorted(user_counts.items())]
        )

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        ui_kit.card_title("Danh sách tài khoản")
        if not all_users:
            ui_kit.empty_state(
                "Chưa có tài khoản nào.",
                hint="Tài khoản được cấp qua hệ thống quản lý học tập của Trường hoặc do Quản trị viên tạo.",
            )
        else:
            search = (
                st.text_input(
                    "Tìm theo tên đăng nhập hoặc mã sinh viên",
                    key="admin_users_search",
                    placeholder="Nhập từ khoá…",
                )
                .strip()
                .lower()
            )
            rows = []
            for uname, urec in all_users.items():
                sid = urec.get("student_id") or ""
                if search and search not in uname.lower() and search not in str(sid).lower():
                    continue
                rows.append(
                    {
                        "Tên đăng nhập": uname,
                        "Vai trò": urec.get("role", "—"),
                        "Email (đăng nhập Google)": urec.get("email") or "—",
                        "Mã sinh viên": sid or "—",
                        "Trạng thái": "Đã khoá" if urec.get("is_active", True) is False else "Hoạt động",
                        "Nguồn cấp": (
                            "Tự cấp qua Google (demo)"
                            if urec.get("auth_provider") == "google" or uname.startswith("g_")
                            else "Tự cấp khi đăng nhập (LMS)"
                            if urec.get("auto_provisioned")
                            else "Quản trị viên tạo"
                        ),
                    }
                )
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(420, 38 + 35 * len(rows)))
                st.caption(f"{len(rows)} / {len(all_users)} tài khoản")
            else:
                ui_kit.empty_state("Không có tài khoản khớp từ khoá.")

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    _admin_account_forms(all_users)
    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    _student_data_rights_panel()


def _data_rights_org_id() -> int | None:
    """Xuất/xoá dữ liệu chạy trên PostgreSQL của trường (data_lifecycle). Không cấu hình thì trả None."""
    import os

    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw.isdecimal() or not (os.environ.get("DATABASE_URL") or os.environ.get("DB_HOST")):
        return None
    return int(raw)


@auth_service.require_role("Admin")
def _student_data_rights_panel() -> None:
    """Bước 7, nhóm B: thực hiện yêu cầu của sinh viên — nhận bản sao dữ liệu, xoá dữ liệu."""
    import json

    from dss.services import data_lifecycle

    with st.expander("Yêu cầu về dữ liệu cá nhân của sinh viên", expanded=False):
        st.caption(
            "Dùng khi sinh viên yêu cầu nhận bản sao hoặc xoá dữ liệu. Điểm và hồ sơ học tập được GIỮ theo quy định "
            "lưu trữ của trường (gắn vào hồ sơ đã ẩn danh); hội thoại AI và kết quả dự đoán bị xoá; tên, mã và tài "
            "khoản được ẩn danh. Nhớ xoá cả ở hệ thống nguồn (LMS/phòng đào tạo), nếu không lần đồng bộ sau sẽ tạo lại."
        )
        org_id = _data_rights_org_id()
        if org_id is None:
            ui_kit.empty_state(
                "Chức năng này cần CSDL PostgreSQL của trường.",
                hint="Đặt DATABASE_URL và EDUDSS_ORGANIZATION_ID (bản triển khai production đã có sẵn).",
            )
            return
        code = st.text_input("Mã sinh viên", key="dr_student_code").strip()
        actor = st.session_state.get("_auth_username") or "admin"
        col_export, col_erase = st.columns(2)
        with col_export:
            if st.button("Chuẩn bị bản sao dữ liệu", key="dr_export_btn", disabled=not code):
                try:
                    payload = data_lifecycle.export_student_data(org_id, code)
                except data_lifecycle.StudentNotFound:
                    st.error("Không tìm thấy sinh viên này trong trường.")
                except Exception:  # noqa: BLE001
                    from dss.core.logging_config import get_logger

                    get_logger(__name__).exception("Xuất dữ liệu sinh viên thất bại.")
                    st.error("Không xuất được dữ liệu. Không có gì bị thay đổi.")
                else:
                    st.session_state["_dr_export"] = (code, json.dumps(payload, ensure_ascii=False, indent=2))
            ready = st.session_state.get("_dr_export")
            if ready and ready[0] == code:
                st.download_button(
                    "Tải file JSON",
                    data=ready[1].encode("utf-8"),
                    file_name="du_lieu_sinh_vien.json",
                    mime="application/json",
                    key="dr_export_download",
                )
        with col_erase:
            confirm = st.text_input("Gõ lại mã sinh viên để xác nhận xoá", key="dr_erase_confirm").strip()
            sure = st.checkbox("Tôi hiểu việc xoá không hoàn tác được", key="dr_erase_sure")
            if st.button(
                "Xoá dữ liệu sinh viên",
                key="dr_erase_btn",
                type="primary",
                disabled=not (code and confirm == code and sure),
            ):
                try:
                    report = data_lifecycle.erase_student_data(org_id, code, requested_by=actor)
                except data_lifecycle.StudentNotFound:
                    st.error("Không tìm thấy sinh viên này trong trường.")
                except Exception:  # noqa: BLE001
                    from dss.core.logging_config import get_logger

                    get_logger(__name__).exception("Xoá dữ liệu sinh viên thất bại.")
                    st.error("Không xoá được. Thao tác chạy trong một giao dịch nên không có gì bị xoá dở.")
                else:
                    st.session_state.pop("_dr_export", None)
                    summary = report.as_dict()
                    st.success(
                        f"Đã xoá {sum(summary['deleted'].values())} bản ghi, ẩn danh "
                        f"{sum(summary['anonymized'].values())} hồ sơ, giữ {sum(summary['retained'].values())} "
                        "bản ghi học tập. Đã ghi sổ kiểm toán."
                    )


def _admin_account_forms(all_users: dict) -> None:
    """Tạo tài khoản, gắn email Google, khoá/mở khoá, đổi vai trò, đặt lại mật khẩu.

    Mọi thao tác đi qua auth_service.admin_* (kiểm tra vai trò Admin ở tầng service + ghi nhật ký
    kiểm toán), chạy được với cả kho tài khoản PostgreSQL lẫn kho cục bộ."""
    col_new, col_edit = st.columns(2, gap="medium")
    with col_new, st.container(border=True):
        ui_kit.card_title("Tạo tài khoản")
        with st.form("admin_create_account", clear_on_submit=True, border=False):
            username = st.text_input("Tên đăng nhập", placeholder="vd. nguyenvana")
            role = st.selectbox("Vai trò", auth_service.ASSIGNABLE_ROLES, index=1)
            email = st.text_input(
                "Email Google (tuỳ chọn)",
                placeholder="ten@truong.edu.vn",
                help="Gắn email để người này đăng nhập bằng Google.",
            )
            student_id = st.text_input("Mã sinh viên (chỉ cho vai trò Sinh viên)")
            password = st.text_input("Mật khẩu ban đầu (≥ 10 ký tự)", type="password")
            if st.form_submit_button("Tạo tài khoản", type="primary"):
                try:
                    auth_service.admin_create_account(
                        username, password, role, email=email or None, student_id=student_id or None
                    )
                    st.success(f"Đã tạo tài khoản {username.strip().lower()}.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("Không tạo được tài khoản (lỗi kho dữ liệu). Không có gì bị thay đổi.")

    with col_edit, st.container(border=True):
        ui_kit.card_title("Sửa tài khoản")
        names = sorted(all_users)
        if not names:
            st.caption("Chưa có tài khoản để sửa.")
            return
        target = st.selectbox("Tài khoản", names, key="admin_edit_target")
        current = all_users.get(target, {})
        with st.form("admin_edit_account", border=False):
            new_email = st.text_input(
                "Email Google", value=current.get("email") or "", help="Để trống để gỡ liên kết Google."
            )
            roles = list(auth_service.ASSIGNABLE_ROLES)
            cur_role = current.get("role")
            new_role = st.selectbox("Vai trò", roles, index=roles.index(cur_role) if cur_role in roles else 0)
            active = st.toggle("Đang hoạt động", value=current.get("is_active", True) is not False)
            new_password = st.text_input("Đặt lại mật khẩu (để trống nếu không đổi)", type="password")
            if st.form_submit_button("Lưu thay đổi", type="primary"):
                try:
                    auth_service.admin_update_account(
                        target,
                        email=new_email,
                        active=active if active != (current.get("is_active", True) is not False) else None,
                        role=new_role if new_role != cur_role else None,
                    )
                    if new_password:
                        auth_service.admin_reset_password(target, new_password)
                    st.success("Đã lưu.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("Không lưu được (lỗi kho dữ liệu). Không có gì bị thay đổi.")


# ---------------------------------------------------------------------------
# Tích hợp LMS / CMS
# ---------------------------------------------------------------------------
def admin_integration_tab():
    ui_kit.page_header(
        "Tích hợp LMS/CMS",
        subtitle="Trạng thái kết nối với hệ thống quản lý học tập và nội dung của Trường.",
    )

    from dss.services.lms_connector import STATUS_DEMO, STATUS_PARTIAL, get_lms_repository

    try:
        status = get_lms_repository().get_integration_status()
    except Exception:
        status = None

    with st.container(border=True):
        ui_kit.card_title("Kết nối LMS")
        if status is None:
            ui_kit.error_state(
                "Không đọc được trạng thái bộ kết nối LMS",
                "Không có dữ liệu nào bị thay đổi.",
            )
        else:
            data_mode = status.get("data_mode_status")
            data_label = {
                STATUS_DEMO: ("Dữ liệu mô phỏng", "warning"),
                STATUS_PARTIAL: ("Kết nối một phần", "warning"),
            }.get(data_mode, (str(data_mode), "neutral"))
            st.markdown(
                "<div class='dss-kv'><span class='dss-kv-key'>Bộ kết nối</span>"
                f"<span class='dss-kv-value'>{status.get('component', 'LMS Connector')}</span></div>"
                "<div class='dss-kv'><span class='dss-kv-key'>Chế độ</span>"
                f"<span class='dss-kv-value'>{status.get('mode', '—')}</span></div>"
                "<div class='dss-kv'><span class='dss-kv-key'>Nguồn dữ liệu</span>"
                f"<span class='dss-kv-value'>{ui_kit.badge_html(*data_label)}</span></div>"
                "<div class='dss-kv'><span class='dss-kv-key'>Hệ thống LMS/CMS bên ngoài</span>"
                f"<span class='dss-kv-value'>{ui_kit.status_html('not_configured', 'Chưa kết nối')}</span></div>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Kiến trúc kết nối (lms_connector, cms_repository) đã có; phiên bản hiện tại "
                "chưa kết nối với một LMS/CMS bên ngoài thực tế. Mọi dữ liệu LMS trong hệ thống là dữ liệu mô phỏng."
            )

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    col_events, col_actions = st.columns([1.6, 1], gap="medium")
    with col_events:
        with st.container(border=True):
            ui_kit.card_title("Sự kiện đồng bộ gần đây")
            try:
                from dss.services.lms_live_sync import lms_live_sync_manager

                events = lms_live_sync_manager.get_event_history(limit=20)
            except Exception:
                events = None
            if events is None:
                ui_kit.error_state("Không đọc được nhật ký đồng bộ", "Không có dữ liệu nào bị thay đổi.")
            elif not events:
                ui_kit.empty_state(
                    "Chưa có sự kiện đồng bộ nào trong phiên chạy này.",
                    hint="Sự kiện mô phỏng có thể phát từ trang Kho dữ liệu (môi trường phát triển).",
                )
            else:
                ev_df = pd.DataFrame(
                    [
                        {
                            "Thời gian": ev.timestamp,
                            "Nguồn": ev.source,
                            "Sự kiện": ev.event_type,
                            "Sinh viên": ev.student_id,
                            "Kết quả": {"processed": "Đã xử lý", "failed": "Lỗi", "pending": "Đang chờ"}.get(
                                ev.status, ev.status
                            ),
                        }
                        for ev in events
                    ]
                )
                st.dataframe(ev_df, width="stretch", hide_index=True)
                n_failed = sum(1 for ev in events if ev.status == "failed")
                st.caption(f"{len(events)} sự kiện · {n_failed} lỗi · tất cả là sự kiện mô phỏng")

    with col_actions:
        with st.container(border=True):
            ui_kit.card_title("Đồng bộ dữ liệu mẫu")
            if is_production_environment():
                ui_kit.render_status("unavailable", "Đã tắt trong môi trường vận hành")
                st.caption("Nạp dữ liệu LMS mô phỏng bị vô hiệu hoá khi hệ thống chạy với dữ liệu thật.")
            else:
                st.caption(
                    "Nạp một bộ dữ liệu LMS mô phỏng vào phiên làm việc (thay cho dữ liệu đang mở). "
                    "Đây không phải dữ liệu LMS thật."
                )
                if st.button("Nạp dữ liệu LMS mô phỏng", key="admin_lms_sync_btn", type="secondary", width="stretch"):
                    from dss.core.data_helpers import generate_lms_data
                    from dss.core.init_app import clear_all_session_state_for_new_data
                    from dss.services.academic_persistence import persist_dataframe_if_configured

                    clear_all_session_state_for_new_data()
                    _lms_df, _lms_course, _lms_term = generate_lms_data()
                    persist_dataframe_if_configured(_lms_df, "LMS_SYNC", _lms_course, _lms_term)
                    st.session_state.current_df = _lms_df
                    st.session_state.current_dataset_id = f"lms_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    st.session_state.show_success_message = (
                        "Đã nạp dữ liệu LMS mô phỏng vào phiên làm việc (chưa phải dữ liệu LMS thật)."
                    )
                    st.rerun()


# ---------------------------------------------------------------------------
# Cài đặt (thuê bao tổ chức)
# ---------------------------------------------------------------------------
def admin_settings_tab():
    ui_kit.page_header(
        "Cài đặt",
        subtitle="Thông tin tổ chức và giấy phép sử dụng hệ thống.",
    )

    sub = subscription_service.get_organization_subscription()
    sub_status = sub.get("status", "ACTIVE")
    sub_plan = sub.get("plan", "ENTERPRISE")
    status_kind = "success" if sub_status == "ACTIVE" else ("danger" if sub_status == "EXPIRED" else "warning")

    with st.container(border=True):
        col_title, col_badge = st.columns([3, 1], vertical_alignment="center")
        with col_title:
            ui_kit.card_title(sub.get("org_name", "Tổ chức giáo dục"))
            st.caption(
                f"Mã tổ chức: {sub.get('org_id')} · Tên miền: {sub.get('domain')} · Liên hệ: {sub.get('admin_contact')}"
            )
        with col_badge:
            ui_kit.render_badge(map_subscription_status(sub_status), kind=status_kind)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            ui_kit.metric_card("Gói dịch vụ", SUBSCRIPTION_PLAN_TO_VIETNAMESE.get(sub_plan, sub_plan), height=96)
        with m2:
            ui_kit.metric_card("Trạng thái", map_subscription_status(sub_status), kind=status_kind, height=96)
        with m3:
            ui_kit.metric_card("Hết hạn", str(sub.get("expires_at", "—"))[:10], height=96)
        with m4:
            ui_kit.metric_card("Hạn ngạch sinh viên", f"{sub.get('max_students', 0):,}", height=96)

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    with st.expander("Điều chỉnh thuê bao", expanded=False):
        st.caption("Cập nhật trạng thái hợp đồng hoặc gia hạn chu kỳ giấy phép.")
        with st.form("admin_subscription_form", border=False):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                new_status = st.selectbox(
                    "Trạng thái thuê bao",
                    _SUBSCRIPTION_STATUSES,
                    index=_SUBSCRIPTION_STATUSES.index(sub_status) if sub_status in _SUBSCRIPTION_STATUSES else 0,
                    key="admin_sub_new_status",
                    format_func=map_subscription_status,
                )
            with f_col2:
                new_plan = st.selectbox(
                    "Gói dịch vụ",
                    _SUBSCRIPTION_PLANS,
                    index=_SUBSCRIPTION_PLANS.index(sub_plan) if sub_plan in _SUBSCRIPTION_PLANS else 2,
                    key="admin_sub_new_plan",
                    format_func=lambda p: SUBSCRIPTION_PLAN_TO_VIETNAMESE.get(p, p),
                )
            with f_col3:
                new_max_students = st.number_input(
                    "Hạn ngạch sinh viên tối đa",
                    min_value=100,
                    max_value=50000,
                    value=int(sub.get("max_students", 5000)),
                    step=500,
                    key="admin_sub_max_students",
                )
            confirm = st.checkbox(
                "Tôi xác nhận thay đổi này ảnh hưởng tới quyền truy cập của toàn bộ người dùng.",
                key="admin_sub_confirm",
            )
            submitted = st.form_submit_button("Lưu thay đổi", type="primary")
        if submitted:
            if not confirm:
                st.warning("Hãy đánh dấu xác nhận trước khi lưu thay đổi thuê bao.")
            else:
                try:
                    subscription_service.update_subscription_status(
                        status=new_status,
                        plan=new_plan,
                        max_students=new_max_students,
                    )
                except Exception:
                    ui_kit.error_state(
                        "Chưa lưu được thay đổi",
                        "Cấu hình thuê bao hiện tại vẫn giữ nguyên.",
                        support_hint="Thử lại sau; nếu vẫn lỗi, kiểm tra kết nối cơ sở dữ liệu.",
                    )
                else:
                    st.session_state.show_success_message = "Đã cập nhật cấu hình thuê bao."
                    st.rerun()
