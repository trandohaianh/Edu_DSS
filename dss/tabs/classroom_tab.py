"""Classroom workspace: official assignments, formative assessments and saved plans."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid

import streamlit as st

from dss.platform.context import current_actor
from dss.services import classroom_learning_service as learning
from dss.services import classroom_service as classes

_logger = logging.getLogger(__name__)


def _question_json(value):
    questions = json.loads(value)
    if not isinstance(questions, list):
        raise ValueError("Câu hỏi cần là một danh sách JSON.")
    return questions


def _manage_class(actor, classroom):
    class_id = classroom["id"]
    with st.expander("Danh sách và phân công"):
        st.dataframe(classes.list_class_roster(actor, class_id), hide_index=True)
        st.dataframe(classes.list_teaching_assignments(actor, class_id), hide_index=True)
        with st.form("class_teacher_" + class_id):
            username = st.text_input("Tên đăng nhập giảng viên")
            revoke = st.checkbox("Thu hồi phân công")
            if st.form_submit_button("Lưu phân công"):
                action = classes.revoke_teacher if revoke else classes.assign_teacher
                action(actor, class_id, username)
                st.rerun()
        with st.form("class_student_" + class_id):
            code = st.text_input("Mã sinh viên")
            remove = st.checkbox("Rút khỏi lớp")
            if st.form_submit_button("Lưu ghi danh"):
                action = classes.unenroll_student if remove else classes.enroll_student
                action(actor, class_id, code)
                st.rerun()
        st.caption("Nhập danh sách được trường cho phép xuất. Tệp UTF-8 có cột student_code; tối đa 1.000 dòng.")
        upload = st.file_uploader("Danh sách lớp CSV", type=["csv"], key="roster_csv_" + class_id)
        if upload is not None:
            rows = list(csv.DictReader(io.StringIO(upload.getvalue().decode("utf-8-sig"))))
            if not rows or len(rows) > 1000 or "student_code" not in rows[0]:
                st.warning("Cần từ 1 đến 1.000 dòng và cột student_code.")
            else:
                codes = [(row["student_code"] or "").strip() for row in rows]
                st.dataframe([{"student_code": code} for code in codes], hide_index=True)
                if st.button("Xác nhận nhập danh sách", key="import_" + class_id):
                    classes.import_enrollments(actor, class_id, codes)
                    st.rerun()
        new_status = "closed" if classroom["status"] == "active" else "active"
        if st.button("Đóng lớp" if new_status == "closed" else "Mở lại lớp", key="status_" + class_id):
            classes.set_class_status(actor, class_id, new_status)
            st.rerun()


def _question_editor(prefix, questions):
    result = []
    for index, question in enumerate(questions):
        key = f"{prefix}_q_{index}"
        st.markdown(f"**Câu {index + 1}**")
        topic = st.text_input("Chủ đề", value=question.get("topic_id", ""), key=key + "_topic")
        text = st.text_area("Nội dung câu hỏi", value=question.get("text", ""), key=key + "_text")
        choices = st.text_area(
            "Các lựa chọn, mỗi dòng một lựa chọn", value="\n".join(question.get("options", [])), key=key + "_options"
        )
        position = st.number_input(
            "Đáp án đúng (số thứ tự từ 1)",
            min_value=1,
            max_value=8,
            value=question.get("correct_answer_index", 0) + 1,
            key=key + "_correct",
        )
        explanation = st.text_area(
            "Giải thích đáp án (tùy chọn)", value=question.get("explanation", ""), key=key + "_explanation"
        )
        result.append(
            dict(
                question_id=question.get("question_id", f"q{index + 1}"),
                topic_id=topic,
                text=text,
                options=[line.strip() for line in choices.splitlines() if line.strip()],
                correct_answer_index=int(position) - 1,
                explanation=explanation,
            )
        )
    return result


def _author_assessments(actor, class_id, assessments):
    with st.expander("Soạn bài đánh giá"):
        st.caption("Mỗi câu có 2–8 lựa chọn. Giảng viên xác nhận nội dung, chủ đề và đáp án trước khi xuất bản.")
        count = st.number_input("Số câu hỏi", min_value=1, max_value=100, value=1, key="question_count_" + class_id)
        with st.form("assessment_compose_" + class_id):
            title = st.text_input("Tên bài đánh giá", key="compose_title_" + class_id)
            maximum = st.number_input(
                "Lượt làm tối đa", min_value=1, max_value=100, value=3, key="compose_maximum_" + class_id
            )
            questions = _question_editor(
                "compose_" + class_id, [{"question_id": f"q{i + 1}"} for i in range(int(count))]
            )
            if st.form_submit_button("Lưu bài đánh giá nháp"):
                learning.create_assessment(actor, class_id, title, questions, max_attempts=int(maximum))
                st.rerun()
    with st.expander("Nhập hàng loạt câu hỏi JSON"):
        st.caption(
            "Dùng khi trường đã có bộ câu hỏi xuất theo cấu trúc question_id, topic_id, text, options, correct_answer_index (bắt đầu từ 0), explanation."
        )
        with st.form("assessment_create_" + class_id):
            title = st.text_input("Tên bài nhập")
            questions = st.text_area("Danh sách câu hỏi JSON", height=180)
            maximum = st.number_input("Số lượt làm tối đa cho mỗi phiên bản", min_value=1, max_value=100, value=3)
            if st.form_submit_button("Nhập thành bản nháp"):
                learning.create_assessment(actor, class_id, title, _question_json(questions), max_attempts=int(maximum))
                st.rerun()
    statuses = {"draft": "Bản nháp", "published": "Đang mở", "closed": "Đã đóng"}
    for assessment in assessments:
        assessment_id = assessment["id"]
        with st.expander(f"{assessment['title']} · v{assessment['version']} · {statuses[assessment['status']]}"):
            if assessment["status"] == "draft":
                with st.form("edit_draft_" + assessment_id):
                    title = st.text_input("Tên bản nháp", value=assessment["title"], key="draft_title_" + assessment_id)
                    questions = _question_editor("draft_" + assessment_id, assessment["questions"])
                    maximum = st.number_input(
                        "Lượt làm tối đa",
                        min_value=1,
                        max_value=100,
                        value=assessment["max_attempts"],
                        key="draft_maximum_" + assessment_id,
                    )
                    if st.form_submit_button("Lưu thay đổi bản nháp"):
                        learning.update_assessment_draft(
                            actor, assessment_id, questions, title=title, max_attempts=int(maximum)
                        )
                        st.rerun()
                if st.button("Xuất bản", key="publish_" + assessment_id):
                    learning.publish_assessment(actor, assessment_id)
                    st.rerun()
            else:
                if assessment["status"] == "published" and st.button(
                    "Đóng bài đánh giá", key="close_assessment_" + assessment_id
                ):
                    learning.close_assessment(actor, assessment_id)
                    st.rerun()
                st.caption("Chỉnh sửa dưới đây tạo bản nháp mới; bài đã xuất bản được giữ nguyên.")
                with st.form("revise_" + assessment_id):
                    questions = _question_editor("revise_" + assessment_id, assessment["questions"])
                    if st.form_submit_button("Tạo phiên bản nháp mới"):
                        learning.revise_assessment(actor, assessment_id, questions)
                        st.rerun()


def _show_attempts(actor, class_id, assessments):
    attempts = learning.list_my_attempts(actor, class_id)
    if not attempts:
        return attempts
    by_id = {item["id"]: item for item in assessments}
    st.subheader("Kết quả đã lưu")
    st.dataframe(
        [
            {
                "Bài đánh giá": by_id.get(item["assessment_id"], {}).get("title", "Bài đã lưu"),
                "Phiên bản": by_id.get(item["assessment_id"], {}).get("version"),
                "Thời điểm": item["submitted_at"],
                "Điểm / 10": item["score"],
                "Số câu đúng": item["correct_count"],
                "Tổng số câu": item["total_count"],
            }
            for item in attempts
        ],
        hide_index=True,
    )
    st.caption("Kết quả từng chủ đề trong lượt làm mới nhất:")
    st.dataframe(
        [{"Chủ đề": topic, "Điểm / 10": score} for topic, score in attempts[0]["topic_scores"].items()], hide_index=True
    )
    return attempts


def _take_assessment(actor, class_id, assessments, attempts):
    published = [item for item in assessments if item["status"] == "published"]
    if not published:
        st.info("Chưa có bài đánh giá đang mở.")
        return
    by_id = {item["id"]: item for item in published}
    assessment_id = st.selectbox(
        "Chọn bài đánh giá",
        list(by_id),
        format_func=lambda key: f"{by_id[key]['title']} · v{by_id[key]['version']}",
        key="assessment_pick_" + actor.school_id + "_" + actor.username + "_" + class_id,
    )
    assessment = by_id[assessment_id]
    done = [item for item in attempts if item["assessment_id"] == assessment_id]
    st.caption(f"Đã dùng {len(done)}/{assessment['max_attempts']} lượt. Kết quả dùng để hỗ trợ học tập.")
    token_key = "submission_" + actor.school_id + "_" + actor.username + "_" + assessment_id
    completed_key = token_key + "_completed"
    if st.session_state.get(completed_key):
        if done:
            st.success(f"Đã lưu bài làm và kế hoạch học tập. Điểm: {done[0]['score']:g}/10.")
        if len(done) < assessment["max_attempts"]:
            if st.button("Bắt đầu lượt làm tiếp theo", key="new_attempt_" + token_key):
                st.session_state[token_key] = uuid.uuid4().hex
                st.session_state[completed_key] = False
                for index in range(len(assessment["questions"])):
                    st.session_state.pop(f"{token_key}_answer_{index}", None)
                st.rerun()
        else:
            st.info("Bạn đã dùng hết lượt làm của phiên bản này.")
        return
    if len(done) >= assessment["max_attempts"]:
        st.info("Bạn đã dùng hết lượt làm của phiên bản này.")
        return
    st.session_state.setdefault(token_key, uuid.uuid4().hex)
    with st.form("take_" + token_key):
        answers = []
        for index, question in enumerate(assessment["questions"]):
            answers.append(
                st.radio(
                    f"{index + 1}. {question['text']}",
                    range(len(question["options"])),
                    format_func=lambda option, choices=question["options"]: choices[option],
                    index=None,
                    key=f"{token_key}_answer_{index}",
                )
            )
        if st.form_submit_button("Nộp bài và cập nhật kế hoạch"):
            if any(answer is None for answer in answers):
                st.warning("Hãy trả lời đủ các câu trước khi nộp.")
            else:
                learning.submit_attempt(actor, assessment_id, answers, st.session_state[token_key])
                st.session_state[completed_key] = True
                st.rerun()


def _show_plans(actor, class_id):
    plans = learning.list_my_plans(actor, class_id)
    st.subheader("Kế hoạch học tập")
    if not plans:
        st.caption("Sau bài đánh giá đầu tiên, kế hoạch sẽ được lưu theo kết quả từng chủ đề.")
        return
    by_id = {item["id"]: item for item in plans}
    selected = st.selectbox(
        "Phiên bản kế hoạch",
        list(by_id),
        format_func=lambda key: f"v{by_id[key]['version']} · {by_id[key]['created_at'][:10]}",
        key="plan_pick_" + actor.school_id + "_" + actor.username + "_" + class_id,
    )
    record = by_id[selected]
    plan = record["plan"]
    for message in plan.get("missing_evidence", []):
        st.info(message)
    with st.expander("Căn cứ lập kế hoạch"):
        st.write(plan.get("evidence_used", []))
        source = plan.get("source_assessment", {})
        st.caption(f"Bài đánh giá: {source.get('title', '')} · v{source.get('version', '')}")
    for index, activity in enumerate(plan.get("activities", [])):
        st.write(activity["objective"])
        st.caption(activity["method"])
        for resource_id in activity.get("approved_resource_ids", []):
            detail = plan.get("resource_details", {}).get(resource_id, {})
            title = detail.get("title", resource_id)
            resource_key = f"plan_resource_{selected}_{index}_{resource_id}"
            with st.expander("Học liệu: " + title):
                if st.button("Đọc học liệu", key=resource_key + "_open"):
                    st.session_state[resource_key] = True
                if st.session_state.get(resource_key):
                    try:
                        resource = learning.get_plan_resource(actor, selected, resource_id)
                        if resource["kind"] == "cms_lesson":
                            st.markdown(resource["content"], unsafe_allow_html=False)
                        else:
                            st.link_button("Mở tài liệu được duyệt", resource["url"])
                    except (PermissionError, LookupError) as exc:
                        st.warning(str(exc))
        before = bool(record.get("completion", {}).get(str(index), False))
        after = st.checkbox("Đã hoàn thành hoạt động", value=before, key=f"class_plan_{selected}_{index}")
        if before != after:
            learning.set_plan_activity_completed(actor, selected, index, after)
            st.rerun()
    st.caption("Tiến độ hoạt động do bạn tự đánh dấu; kết quả từng chủ đề được ghi nhận qua bài đánh giá.")


def _staff_progress(actor, class_id):
    progress = learning.get_class_progress(actor, class_id)
    st.subheader("Tiến độ lớp")
    left, middle, right = st.columns(3)
    left.metric("Sinh viên trong lớp", progress["student_count"])
    middle.metric("Đã có bài làm", progress["assessed_students"])
    right.metric("Lượt làm", progress["attempt_count"])
    st.dataframe(
        [
            {
                "Mã sinh viên": item["student_code"],
                "Lượt làm": item["attempt_count"],
                "Điểm lượt mới nhất": item["latest_score"],
                "Thời điểm": item["latest_submitted_at"],
                "Phiên bản kế hoạch": item["plan_version"],
                "Hoạt động hoàn thành": item["completed_activities"],
                "Tổng hoạt động": item["total_activities"],
                "Cần xem xét hỗ trợ": item["needs_review"],
            }
            for item in progress["students"]
        ],
        hide_index=True,
    )
    st.caption(
        "Chủ đề dùng kết quả mới nhất đã ghi nhận của từng sinh viên. Chưa có bài làm được giữ là chưa có dữ liệu."
    )
    if progress["topic_summary"]:
        st.dataframe(
            [
                {
                    "Chủ đề": topic,
                    "Điểm trung bình / 10": values["average_score"],
                    "Sinh viên có kết quả": values["observed_students"],
                }
                for topic, values in progress["topic_summary"].items()
            ],
            hide_index=True,
        )
    with st.expander("Theo dõi hỗ trợ sinh viên"):
        roster = classes.list_class_roster(actor, class_id)
        if roster:
            with st.form("intervention_" + class_id):
                student = st.selectbox("Sinh viên cần hỗ trợ", [row["student_code"] for row in roster])
                reason = st.text_area("Căn cứ cần hỗ trợ")
                action = st.text_area("Hoạt động hỗ trợ của giảng viên")
                if st.form_submit_button("Lưu hoạt động hỗ trợ"):
                    classes.create_intervention(actor, class_id, student, reason, action)
                    st.rerun()
        for item in classes.list_interventions(actor, class_id):
            st.write(f"{item['student_code']} · {item['status']}")
            st.write(item["reason"])
            st.write(item["action"])
            if item["status"] == "open" and st.button("Đánh dấu đã xử lý", key="intervention_close_" + item["id"]):
                classes.close_intervention(actor, item["id"])
                st.rerun()


def classroom_tab():
    st.header("Lớp học và đánh giá")
    try:
        actor = current_actor()
        if actor.role == classes.ADMIN:
            with st.expander("Tạo lớp học"):
                with st.form("class_create"):
                    code = st.text_input("Mã lớp")
                    course = st.text_input("Mã học phần")
                    title = st.text_input("Tên lớp")
                    term = st.text_input("Học kỳ")
                    if st.form_submit_button("Tạo lớp"):
                        classes.create_class(actor, code, course, title, term)
                        st.rerun()
        rows = classes.list_my_classes(actor)
        if not rows:
            st.info("Chưa có lớp học được phân công hoặc ghi danh cho tài khoản này.")
            return
        by_id = {row["id"]: row for row in rows}
        class_id = st.selectbox(
            "Lớp học",
            list(by_id),
            format_func=lambda key: f"{by_id[key]['code']} · {by_id[key]['title']} · {by_id[key]['term']}",
            key="classroom_pick",
        )
        classroom = by_id[class_id]
        st.caption(f"Học phần {classroom['course_id']} · Trạng thái {classroom['status']}")
        if actor.role == classes.ADMIN:
            _manage_class(actor, classroom)
        assessments = learning.list_assessments(actor, class_id)
        if actor.role == classes.STUDENT:
            attempts = _show_attempts(actor, class_id, assessments)
            if classroom["status"] == "active":
                _take_assessment(actor, class_id, assessments, attempts)
            else:
                st.info("Lớp đã đóng. Bạn có thể xem kết quả và kế hoạch đã lưu.")
            _show_plans(actor, class_id)
            for item in classes.list_interventions(actor, class_id):
                st.info(item["action"])
        else:
            _staff_progress(actor, class_id)
            _author_assessments(actor, class_id, assessments)
    except (ValueError, LookupError, PermissionError) as exc:
        st.error(str(exc))
    except Exception:
        _logger.exception("Classroom workspace could not complete the operation.")
        st.error("Chưa thực hiện được thao tác lớp học. Vui lòng thử lại hoặc liên hệ quản trị viên.")
