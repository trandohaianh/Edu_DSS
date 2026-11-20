"""Student-owned structured plans, available without an LLM or a GPA column."""
from __future__ import annotations

import os

import streamlit as st

from dss.core.logging_config import get_logger
from dss.services import auth_service, learning_plan_history
from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_profile import StudentLearningProfile
from dss.services.learning_plan_resources import approved_plan_resources

_logger = get_logger(__name__)


def course_id_from_record(record: dict) -> str:
    for key in ("course_id", "course_code"):
        value = record.get(key)
        if isinstance(value, str) and value.strip() and value.strip().lower() not in {"nan", "none"}:
            return value.strip()
    return os.environ.get("EDUDSS_COURSE_ID", "").strip()


def _show_plan(student_id: str, record: dict) -> None:
    plan = record["plan"]
    st.caption(f"Học phần {plan['course_id']} · Phiên bản {plan['version']} · {plan['created_at'][:10]}")
    for message in plan.get("missing_evidence", []):
        st.info(message)
    if plan.get("evidence_used"):
        with st.expander("Căn cứ của kế hoạch"):
            for evidence in plan["evidence_used"]:
                st.write(evidence)
    activities = plan.get("activities", [])
    for index, activity in enumerate(activities):
        st.write(activity["objective"])
        st.caption(activity["method"])
        duration = activity.get("duration_minutes")
        frequency = activity.get("frequency_per_week")
        if duration is not None and frequency is not None:
            st.caption(f"{frequency} lần/tuần · {duration} phút/lần")
        else:
            st.caption("Thời lượng và lịch học cần được xác nhận thêm.")
        for resource_id in activity.get("approved_resource_ids", []):
            details = plan.get("resource_details", {}).get(resource_id, {})
            st.caption("Học liệu được duyệt khi tạo kế hoạch: " + details.get("title", resource_id))
        if activity.get("reason"):
            st.caption(activity["reason"])
        key = f"structured_progress_{plan['plan_id']}_{index}"
        was_completed = bool(record.get("completion", {}).get(str(index), False))
        done = st.checkbox("Đã hoàn thành", value=was_completed, key=key)
        if done != was_completed:
            learning_plan_history.set_activity_completed(student_id, plan["plan_id"], index, done)
            st.rerun()
    if not activities:
        st.info("Chưa đủ bằng chứng để đề xuất hoạt động học tập cụ thể.")
    st.caption("Mục đã hoàn thành do bạn tự đánh dấu; kết quả học tập được đánh giá qua bài kiểm tra.")


def render_learning_plan_workspace(df) -> None:
    user = auth_service.current_user()
    if not user or user.get("role") != "Sinh viên" or not user.get("student_id"):
        return
    student_id = str(user["student_id"])
    with st.expander("Kế hoạch và tiến độ đã lưu", expanded=True):
        try:
            records = learning_plan_history.list_learning_plans(student_id)
        except (RuntimeError, PermissionError):
            _logger.exception("Learning plan history is not configured or authorized.")
            st.info("Lịch sử kế hoạch chưa sẵn sàng. Vui lòng liên hệ quản trị viên của trường.")
            return
        except Exception:
            _logger.exception("Learning plan history could not be loaded.")
            st.error("Chưa tải được lịch sử kế hoạch. Vui lòng thử lại.")
            return

        own_row = None
        if df is not None:
            id_column = next((c for c in ("student_id", "id", "Student ID", "ID") if c in df.columns), None)
            if id_column is not None:
                rows = df[df[id_column].astype(str) == student_id]
                if len(rows) > 1:
                    course_column = next((c for c in ("course_id", "course_code") if c in rows.columns), None)
                    if course_column:
                        courses = sorted({str(v) for v in rows[course_column].dropna()})
                        if courses:
                            selected_course = st.selectbox("Học phần", courses, key="structured_course")
                            rows = rows[rows[course_column].astype(str) == selected_course]
                    if len(rows) > 1:
                        st.info("Dữ liệu có nhiều bản ghi cho học phần này; trường cần chọn bản ghi đã đối soát trước khi lập kế hoạch.")
                        rows = rows.iloc[0:0]
                if len(rows) == 1:
                    own_row = rows.iloc[0].to_dict()

        if own_row is not None:
            course_id = course_id_from_record(own_row)
            if course_id:
                st.caption(f"Dữ liệu học phần: {course_id}")
                if st.button("Tạo kế hoạch từ dữ liệu hiện có", key="structured_plan_generate"):
                    try:
                        profile = StudentLearningProfile.build_from_lms_records(
                            student_id, course_id, own_row,
                        )
                        plan = learning_plan_generator.generate_plan(profile, approved_resources=approved_plan_resources(course_id))
                        learning_plan_history.save_learning_plan(student_id, plan)
                        st.success("Đã lưu phiên bản kế hoạch mới.")
                        st.rerun()
                    except Exception:
                        _logger.exception("Could not save structured learning plan.")
                        st.error("Chưa lưu được kế hoạch. Vui lòng thử lại hoặc liên hệ quản trị viên.")
            else:
                st.info("Dữ liệu chưa có mã học phần. Trường cần bổ sung mã trước khi tạo kế hoạch.")
        else:
            st.caption("Lịch sử vẫn có thể xem khi chưa có dữ liệu mới để lập kế hoạch.")

        if records:
            selected = st.selectbox(
                "Phiên bản kế hoạch", list(range(len(records))),
                format_func=lambda i: (
                    f"{records[i]['plan']['course_id']} — v{records[i]['plan']['version']} "
                    f"— {records[i]['plan']['created_at'][:10]}"
                ),
                key="structured_plan_history",
            )
            try:
                _show_plan(student_id, records[selected])
            except Exception:
                _logger.exception("Could not update learning plan progress.")
                st.error("Chưa lưu được tiến độ. Vui lòng thử lại.")
        else:
            st.caption("Bạn chưa có kế hoạch đã lưu.")
