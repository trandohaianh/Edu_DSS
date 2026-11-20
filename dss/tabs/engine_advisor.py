"""Authenticated queued advice and pre-generated lesson explanations."""

from __future__ import annotations

import uuid

import streamlit as st

from dss.services import engine_gateway as gateway


def _show_job(job):
    state = job.get("state", "PENDING")
    if state == "SUCCEEDED":
        result = job.get("result") or {}
        text = result.get("text") if isinstance(result, dict) else None
        if job.get("demo") or (isinstance(result, dict) and result.get("demo")):
            st.info("Nội dung minh họa từ dữ liệu hoặc bộ sinh thử nghiệm.")
        if isinstance(text, str) and text:
            st.markdown(text)
        else:
            st.info("Tác vụ đã hoàn tất; chưa có nội dung để hiển thị.")
    elif state == "FAILED":
        st.warning("Chưa hoàn tất tư vấn. Bạn có thể gửi yêu cầu mới sau khi dịch vụ sẵn sàng.")
    elif state == "DISPATCH_UNCERTAIN":
        st.warning("Chưa xác nhận được broker đã nhận tác vụ. Mã yêu cầu được giữ lại để gửi lại an toàn.")
    else:
        st.info("Tư vấn đang được chuẩn bị. Bấm cập nhật sau ít giây.")


def _student_advice(course, state_key):
    with st.expander("Dự đoán và bài tập gợi ý", expanded=True):
        prediction = gateway.get_predictions(course)
        if prediction.get("source") == "synthetic":
            st.info("Dữ liệu mô phỏng dùng để thử nghiệm, không phải hồ sơ học tập thật.")
        if prediction.get("stale_data"):
            st.warning("Dữ liệu đã cũ. Kết quả này cần được cập nhật trước khi dùng để ra quyết định.")
        st.caption("Mốc dữ liệu: " + str(prediction.get("reference_at") or "chưa xác định"))
        if prediction.get("grade") is not None:
            st.metric("Điểm dự báo", f'{prediction["grade"]:.2f}')
        st.caption("Dự báo có sai số; cần đối chiếu với bài đánh giá và giảng viên.")
        for text in prediction.get("missing_evidence", []):
            st.info(str(text))
        recommendations = gateway.get_recommendations(course)
        rows = recommendations.get("items", [])
        if rows:
            st.dataframe(
                [
                    {
                        "Bài tập": item["item_id"],
                        "Chủ đề": item["topic_id"],
                        "Lý do": item.get("reason", ""),
                    }
                    for item in rows
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Chưa có bài tập đáp ứng điều kiện tiên quyết.")
    request_key = state_key + ":request_id"
    if st.button("Tạo tư vấn học tập", type="primary", key=state_key + ":new"):
        request_id = st.session_state.get(request_key)
        if not isinstance(request_id, str) or not request_id:
            request_id = uuid.uuid4().hex
            st.session_state[request_key] = request_id
        try:
            response = gateway.request_advice(course, request_id)
            st.session_state[state_key] = response["job"]["job_id"]
        except gateway.EngineUnavailable as exc:
            if exc.job_id:
                st.session_state[state_key] = exc.job_id
            st.warning(str(exc))
        except gateway.EngineGatewayError:
            # VD 422 "khoá idempotency đã dùng cho yêu cầu khác" sau khi mô hình được huấn luyện lại: bỏ request_id cũ,
            # nếu không mọi lần bấm sau đều gửi lại đúng khoá đó và bị từ chối mãi.
            st.session_state.pop(request_key, None)
            st.warning(
                "Yêu cầu tư vấn chưa được nhận (mô hình có thể vừa được cập nhật). Hãy bấm lại để gửi yêu cầu mới."
            )
    job_id = st.session_state.get(state_key)
    request_id = st.session_state.get(request_key)
    if job_id:
        st.button("Cập nhật tư vấn", key=state_key + ":refresh")
        try:
            job = gateway.get_job(course, job_id)
        except gateway.EngineUnavailable as exc:
            st.warning(str(exc))
        else:
            _show_job(job)
            if job.get("state") == "DISPATCH_UNCERTAIN" and request_id:
                if st.button("Gửi lại yêu cầu chưa xác nhận", key=state_key + ":retry_dispatch"):
                    try:
                        response = gateway.request_advice(course, request_id)
                        st.session_state[state_key] = response["job"]["job_id"]
                    except gateway.EngineUnavailable as exc:
                        if exc.job_id:
                            st.session_state[state_key] = exc.job_id
                        st.warning(str(exc))
            elif job.get("state") in {"SUCCEEDED", "FAILED"}:
                st.session_state.pop(request_key, None)


def _student_lessons(course, state_key):
    from dss.services import cms_lecture_repository as cms

    lessons = [lesson for lesson in cms.list_lessons(course_id=course) if lesson.ai_enabled]
    if not lessons:
        st.info("Chưa có bài giảng được chuẩn bị cho học phần.")
        return
    selected = st.selectbox("Bài học", lessons, format_func=lambda lesson: lesson.title, key=state_key + ":lesson")
    paragraphs = gateway.list_cached_paragraphs(course, selected.lesson_id)
    if not paragraphs:
        st.info("Bài giảng cần được giảng viên duyệt và đồng bộ trước khi xem giải thích.")
        return
    selected_part = st.selectbox(
        "Đoạn bài học", paragraphs, format_func=lambda part: part["preview"], key=state_key + ":paragraph"
    )
    response = gateway.get_cached_explanation(course, selected.lesson_id, selected_part["paragraph_id"])
    if response.get("state") != "READY":
        st.info(response["text"])
        st.button("Cập nhật giải thích", key=state_key + ":lesson-refresh")
        return
    st.markdown(response["original_text"])
    st.divider()
    if response.get("demo"):
        st.info("Giải thích minh họa từ bộ sinh thử nghiệm.")
    st.markdown(response["text"])


def _staff_upload(course, llm_integration):
    from dss.security.upload_security import read_upload_within_size_limit, safe_document_name
    from dss.services import cms_lecture_repository as cms

    with st.expander("Nạp bài giảng để chuẩn bị giải thích"):
        with st.form("engine:upload"):
            title = st.text_input("Tiêu đề bài giảng")
            lesson_id = st.text_input("Mã bài học")
            topic = st.text_input("Chủ đề")
            uploaded = st.file_uploader("Tài liệu", type=["txt", "md", "pdf", "docx", "pptx", "json"])
            submitted = st.form_submit_button("Nạp và chuẩn bị giải thích")
        if submitted:
            if not uploaded or not title.strip() or not lesson_id.strip():
                st.warning("Cần tài liệu, tiêu đề và mã bài học.")
                return
            actor = gateway.authorize_staff_course(course)
            filename, _ = safe_document_name(
                uploaded.name, allowed_extensions={".txt", ".md", ".pdf", ".docx", ".pptx", ".json"}
            )
            cms.ingest_lecture_material(
                file_bytes=read_upload_within_size_limit(uploaded),
                file_name=filename,
                title=title.strip(),
                course_id=course,
                lesson_id=lesson_id.strip(),
                topic_id=topic.strip(),
                lecturer_id=actor.username,
                llm_integration=llm_integration,
            )
            st.success("Đã lưu tài liệu. Giải thích được chuẩn bị trước; sinh viên xem sau khi tài liệu được duyệt.")


def _staff(course, llm_integration):
    from dss.services import cms_lecture_repository as cms

    _staff_upload(course, llm_integration)
    st.caption("Duyệt nguồn tài liệu tại mục Duyệt tài liệu, sau đó đồng bộ phiên bản được duyệt tại đây.")
    lessons = cms.list_lessons(course_id=course)
    if lessons:
        selected = st.selectbox(
            "Bài giảng cần đồng bộ", lessons, format_func=lambda lesson: lesson.title, key="engine:staff-lesson"
        )
        retry = st.checkbox("Thử lại các đoạn chuẩn bị thất bại", key="engine:retry-failed")
        if st.button("Đồng bộ trạng thái duyệt và chuẩn bị giải thích", key="engine:sync"):
            result = gateway.sync_lesson(course, selected.lesson_id, retry_failed=retry)
            if result.get("approved"):
                st.success("Đã đồng bộ phiên bản được duyệt. Các đoạn đang chờ sẽ được xử lý trong hàng đợi.")
            else:
                st.info("Đã đồng bộ. Sinh viên chỉ xem được giải thích sau khi tài liệu được duyệt.")
    with st.expander("Theo dõi các hồ sơ đã có trong mô hình"):
        offset = st.number_input("Vị trí bắt đầu", min_value=0, step=50, key="engine:risk-offset")
        if st.button("Xem dự báo của học phần", key="engine:risk"):
            result = gateway.get_class_risk(course, offset=int(offset), limit=50)
            st.caption(
                "Các hồ sơ trong dữ liệu đã huấn luyện; chưa thay thế danh sách lớp chính thức. Mốc dữ liệu: "
                + str(result.get("reference_at", ""))
            )
            rows = result.get("items", [])
            if rows:
                st.dataframe(
                    [
                        {
                            "Mã sinh viên": item["student_id"],
                            "Điểm dự báo": item.get("grade"),
                            "Nhóm rủi ro dự báo": item.get("risk"),
                            "Dữ liệu đã cũ": item.get("stale_data"),
                        }
                        for item in rows
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("Chưa có hồ sơ tại vị trí này.")
    if gateway._actor().role == "Admin":
        if st.button("Xem trạng thái hàng đợi học phần", key="engine:queue"):
            result = gateway.get_queue(course)
            st.metric("Tác vụ đang chờ hoặc xử lý", result.get("pending", 0))
            if result.get("jobs"):
                st.dataframe(result["jobs"], hide_index=True, use_container_width=True)
    if st.button("Xem báo cáo đánh giá mô hình", key="engine:leaderboard"):
        report = gateway.get_leaderboard(course)
        for name, label in [("regression", "Dự báo điểm"), ("classification", "Phân loại mức độ rủi ro")]:
            section = report.get(name, {})
            st.subheader(label)
            rows = section.get("leaderboard")
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption("Kết quả kiểm định cần được xác nhận bằng dữ liệu thật trước khi triển khai rộng.")


def engine_advisor_tab(llm_integration=None):
    st.header("Hỗ trợ học tập")
    try:
        actor = gateway._actor()
        courses = gateway.available_courses()
        if not courses:
            st.info("Chưa có học phần được phân công hoặc ghi danh. Quản trị viên cần thiết lập lớp học trước.")
            return
        course = st.selectbox("Học phần", courses, key="engine:course")
        key = f"engine:{actor.school_id}:{actor.username}:{course}"
        if actor.role == "Sinh viên":
            view = st.radio("Nội dung", ["Tư vấn học tập", "Giải thích bài học"], horizontal=True, key="engine:view")
            if view == "Tư vấn học tập":
                _student_advice(course, key)
            else:
                _student_lessons(course, key)
        else:
            _staff(course, llm_integration)
    except gateway.EngineNotReady as exc:
        st.info(str(exc))
    except (gateway.EngineGatewayError, PermissionError, ValueError) as exc:
        st.warning(str(exc))
