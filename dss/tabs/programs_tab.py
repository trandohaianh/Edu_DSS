"""Programme provisioning, explicit membership, allocations and school aggregates."""
from __future__ import annotations

import json
import logging
import streamlit as st

from dss.platform.context import current_actor
from dss.services import program_allocation_service as programs

_logger = logging.getLogger(__name__)
_STATUS = {"active": "Đang hoạt động", "paused": "Tạm dừng", "closed": "Đã đóng",
           "suspended": "Tạm dừng", "revoked": "Đã thu hồi"}
_REPORT_STATUS = {"not_reported": "Chưa gửi", "stale": "Cần cập nhật",
                  "suppressed": "Ẩn một phần", "current": "Đã cập nhật"}


def _provision(actor):
    st.subheader("Thiết lập chương trình")
    st.caption("Quản trị nền tảng tạo chương trình và giao quyền. Quyền cấp phát và xem báo cáo được giao riêng cho từng chương trình.")
    with st.expander("Đăng ký trường"):
        with st.form("program_register_school"):
            school_id = st.text_input("Mã trường trên hệ thống", help="Số định danh trùng với cấu hình máy chủ của trường.")
            name = st.text_input("Tên trường")
            if st.form_submit_button("Đăng ký trường"):
                programs.register_school(actor, school_id, name)
                st.rerun()
    with st.expander("Tạo chương trình"):
        with st.form("program_create"):
            code = st.text_input("Mã chương trình")
            name = st.text_input("Tên chương trình")
            seats = st.number_input("Tổng số suất sinh viên", min_value=0, value=1000, step=1)
            ai = st.number_input("Ngân sách AI dự kiến", min_value=0, value=0, step=1, help="Mức phân bổ dự kiến; chưa đo mức sử dụng hay tính phí nhà cung cấp.")
            if st.form_submit_button("Tạo chương trình"):
                programs.create_program(actor, code, name, int(seats), int(ai))
                st.rerun()


def _members(actor, program):
    with st.expander("Phân quyền chương trình"):
        with st.form("program_member_" + program["id"]):
            school = st.text_input("Mã trường quản lý tài khoản", key="member_school_" + program["id"])
            username = st.text_input("Tên đăng nhập", key="member_user_" + program["id"])
            role = st.selectbox("Quyền trong chương trình", ["manager", "analyst"], format_func=lambda value: "Quản lý cấp phát và báo cáo" if value == "manager" else "Chỉ xem báo cáo")
            revoke = st.checkbox("Thu hồi quyền", key="member_revoke_" + program["id"])
            if st.form_submit_button("Lưu quyền chương trình"):
                if revoke:
                    programs.revoke_program_member(actor, program["id"], school, username)
                else:
                    programs.grant_program_member(actor, program["id"], school, username, role)
                st.rerun()


def _manage(actor, program):
    program_id = program["id"]
    st.subheader("Cấp phát cho trường")
    st.caption("Suất sinh viên được kiểm tra khi ghi danh. Ngân sách AI hiện dùng để lập phân bổ, chưa phải số liệu tiêu thụ.")
    st.dataframe([{
        "Trường": row["school_name"], "Mã trường": row["school_id"],
        "Suất sinh viên": row["seats"], "Ngân sách AI phân bổ": row["ai_budget"],
        "Trạng thái": _STATUS[row["status"]],
    } for row in programs.list_allocations(actor, program_id)], hide_index=True)
    schools = programs.list_school_directory(actor, program_id=program_id)
    if schools:
        by_id = {row["id"]: row for row in schools}
        with st.form("program_allocate_" + program_id):
            school = st.selectbox("Trường nhận cấp phát", list(by_id), format_func=lambda key: f"{by_id[key]['name']} ({key})")
            seats = st.number_input("Suất sinh viên", min_value=0, value=0, step=1, key="allocate_seats_" + program_id)
            ai = st.number_input("Ngân sách AI phân bổ", min_value=0, value=0, step=1, key="allocate_ai_" + program_id)
            status = st.selectbox("Trạng thái cấp phát", ["active", "suspended", "revoked"], format_func=lambda value: {"active": "Đang cấp", "suspended": "Tạm dừng", "revoked": "Thu hồi"}[value])
            if st.form_submit_button("Lưu cấp phát"):
                programs.allocate_school(actor, program_id, school, int(seats), int(ai), status=status)
                st.rerun()
    with st.form("program_status_" + program_id):
        status = st.selectbox("Trạng thái chương trình", ["active", "paused", "closed"], index=["active", "paused", "closed"].index(program["status"]), format_func=lambda value: _STATUS[value])
        if st.form_submit_button("Lưu trạng thái chương trình"):
            programs.set_program_status(actor, program_id, status)
            st.rerun()


def _reports(actor, program):
    st.subheader("Báo cáo tổng hợp của trường")
    st.caption("Trường chủ động gửi số liệu tổng hợp. Nhóm nhỏ được ẩn; thời điểm cập nhật được giữ nguyên để phân biệt báo cáo cũ.")
    reports = programs.list_program_reports(actor, program["id"])
    labels = {
        "active_classes": "Lớp đang mở", "enrolled_students": "Sinh viên ghi danh",
        "assessed_students": "Sinh viên đã đánh giá", "students_with_plans": "Sinh viên có kế hoạch",
        "attempt_count": "Lượt làm bài", "open_interventions": "Hỗ trợ đang mở",
        "completed_interventions": "Hỗ trợ đã xử lý",
    }
    table = []
    for row in reports:
        item = {"Trường": row["school_name"],
                "Báo cáo": _REPORT_STATUS[row["report_status"]],
                "Cập nhật (UTC)": row["as_of"] or "Chưa gửi"}
        for key, label in labels.items():
            value = (row["metrics"] or {}).get(key)
            item[label] = str(value) if value is not None else ("Chưa có" if row["metrics"] is None else "Ẩn")
        table.append(item)
    st.dataframe(table, hide_index=True)
    if reports:
        st.download_button("Tải báo cáo tổng hợp JSON", data=json.dumps(reports, ensure_ascii=False, indent=2), file_name="program-summary.json", mime="application/json", key="download_reports_" + program["id"])


def _school_publishing(actor):
    own = programs.list_school_programs(actor)
    if not own:
        st.info("Trường chưa được cấp phát vào chương trình nào.")
        return
    st.subheader("Chương trình của trường")
    for row in own:
        with st.container(border=True):
            st.write(f"{row['program_code']} · {row['program_name']}")
            st.caption(f"Chương trình: {_STATUS[row['program_status']]} · Cấp phát: {_STATUS[row['allocation_status']]} · {row['seats']} suất")
            if row["program_status"] == "active" and row["allocation_status"] == "active":
                if st.button("Gửi báo cáo tổng hợp", key="publish_school_" + row["program_id"]):
                    programs.publish_school_summary(actor, row["program_id"], min_cohort=5)
                    st.success("Đã gửi báo cáo tổng hợp. Các ô có nhóm dưới 5 sinh viên được ẩn.")
            else:
                st.caption("Cấp phát đang dừng; có thể xem lịch sử học tập, chưa thể mở hoạt động mới.")


def programs_tab():
    st.header("Chương trình và cấp phát")
    try:
        actor = current_actor()
        if actor.role == "Platform Admin":
            _provision(actor)
        if actor.role == "Admin":
            _school_publishing(actor)
        available = programs.list_programs(actor)
        if not available:
            if actor.role != "Admin":
                st.info("Tài khoản chưa được phân quyền vào chương trình nào.")
            return
        by_id = {row["id"]: row for row in available}
        program_id = st.selectbox("Chương trình", list(by_id), format_func=lambda key: f"{by_id[key]['code']} · {by_id[key]['name']}", key="program_pick")
        program = by_id[program_id]
        st.caption(f"Trạng thái: {_STATUS[program['status']]} · Quỹ suất: {program['seat_budget']}")
        if actor.role == "Platform Admin":
            _members(actor, program)
        role = program.get("program_role")
        if role == "manager":
            _manage(actor, program)
        if role in {"manager", "analyst"}:
            _reports(actor, program)
    except (ValueError, LookupError, PermissionError) as exc:
        st.error(str(exc))
    except Exception:
        _logger.exception("Programme workspace could not complete the operation.")
        st.error("Chưa thực hiện được thao tác chương trình. Vui lòng thử lại hoặc liên hệ quản trị viên.")
