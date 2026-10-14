"""AI giải thích bài giảng (CMS) — UI cho cả 2 vai trò:
- Giảng viên/Admin: nạp bài giảng vào CMS, quản lý (bật/tắt AI, đánh dấu nguồn
  chính thức, FAQ, ghi chú, độ khó, chính sách AI theo bài học), duyệt quiz
  chờ xét (Review Queue), xem dashboard phân tích tương tác đầy đủ.
- Sinh viên: chọn Môn học -> Bài học -> hỏi AI giải thích (nhiều thao tác
  nhanh), Socratic mode có trạng thái thật, tạo quiz (qua đúng quy trình
  duyệt nếu Giảng viên yêu cầu).

Toàn bộ logic nằm ở dss/services/{cms_lecture_repository,learning_explainer}.py —
file này chỉ là UI/orchestration, đúng kiến trúc nhất quán của toàn app.
"""
from __future__ import annotations

from dss.config import *  # noqa: F403
from dss.tabs import ui_kit

from dss.security.upload_security import UploadValidationError, read_upload_within_size_limit, safe_document_name
from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer
from dss.services import privacy_service
from dss.core.data_helpers import TOPIC_SCORE_COLUMNS
from dss.core.logging_config import get_logger

_logger = get_logger(__name__)

_CMS_LECTURE_EXTENSIONS = {".txt", ".md", ".docx", ".pptx", ".pdf", ".json"}

_LEVEL_DISPLAY = {"Foundation": "Nền tảng", "Standard": "Tiêu chuẩn", "Advanced": "Nâng cao"}


# ============================================================================
# GIẢNG VIÊN / ADMIN
# ============================================================================
def _unique_labels(citations) -> list:
    """Nhãn nguồn KHÔNG trùng (giữ thứ tự) — nhiều đoạn trích cùng 1 bài giảng
    trước đây hiện thành nhiều nhãn giống hệt nhau."""
    return list(dict.fromkeys(c.label for c in citations))


def _render_demo_seed(role, llm_integration) -> None:
    """Chế độ demo + CMS trống: 1 nút nạp 3 bài giảng mẫu CS301 để demo ngay."""
    from dss.core.runtime_mode import synthetic_data_allowed
    from dss.services import demo_lectures

    if not synthetic_data_allowed() or cms_repository.list_lessons() or not demo_lectures.available():
        return
    with st.container(border=True):
        st.markdown("##### Chưa có bài giảng nào — dùng bài giảng mẫu để demo?")
        st.caption(
            "Nạp 3 bài mẫu môn CS301 (Hồi quy tuyến tính · Random Forest · Đánh giá mô hình) qua đúng "
            "quy trình nạp bài giảng bên dưới. Chỉ hiện ở chế độ demo."
        )
        if st.button("Nạp 3 bài giảng mẫu", key="cms_seed_demo", type="primary"):
            with st.spinner("Đang trích xuất, phân đoạn và tính vector cho 3 bài giảng..."):
                result = demo_lectures.seed(llm_integration, lecturer_id=str(role or "GV"))
            st.success(f"Đã nạp {sum(1 for _, new in result if new)} bài giảng mẫu. Sinh viên có thể hỏi AI ngay.")
            st.rerun()


def _render_lecturer_upload(role, llm_integration) -> None:
    _render_demo_seed(role, llm_integration)
    st.markdown("##### 📤 Nạp bài giảng mới vào CMS")
    st.caption("Tài liệu nạp ở đây trở thành NGUỒN CHÍNH mà AI dùng để giải thích cho Sinh viên — không phải kiến thức chung của LLM.")

    with st.form("cms_upload_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            course_id = st.text_input("Mã môn học", value="CS301", key="cms_course_id")
            lesson_id = st.text_input("Mã bài học (duy nhất)", key="cms_lesson_id")
        with c2:
            topic_id = st.text_input("Chủ đề (topic_id)", key="cms_topic_id")
            title = st.text_input("Tiêu đề bài giảng", key="cms_title")
        with c3:
            content_type = st.selectbox("Loại nội dung", ["slide", "pdf", "note", "document", "transcript", "exercise", "example"], key="cms_content_type")
            difficulty = st.selectbox("Độ khó bài giảng", ["Foundation", "Standard", "Advanced"], index=1, key="cms_difficulty")
        learning_outcome = st.text_area("Learning outcome (mục tiêu bài học)", key="cms_outcome")
        page_or_section = st.text_input("Trang/mục (vd: 'slide 12-15')", key="cms_section")
        uploaded_file = st.file_uploader("Tệp bài giảng", type=["txt", "md", "docx", "pptx", "pdf", "json"], key="cms_file")

        if st.form_submit_button("🚀 Nạp bài giảng", type="primary") and uploaded_file and lesson_id and title:
            spinner_msg = ui_kit.cold_start_aware_message(llm_integration, "Đang trích xuất, phân đoạn và tính vector...")
            try:
                safe_name, _ = safe_document_name(
                    getattr(uploaded_file, "name", None), allowed_extensions=_CMS_LECTURE_EXTENSIONS
                )
                file_bytes = read_upload_within_size_limit(uploaded_file)
                with st.spinner(spinner_msg):
                    lesson = cms_repository.ingest_lecture_material(
                        file_bytes=file_bytes, file_name=safe_name, title=title,
                        course_id=course_id, lesson_id=lesson_id, topic_id=topic_id, lecturer_id=str(role or "GV"),
                        llm_integration=llm_integration, learning_outcome=learning_outcome, difficulty=difficulty,
                        content_type=content_type, page_or_section=page_or_section,
                    )
                st.success(f"✅ Đã nạp '{title}' — phiên bản {len(lesson.versions)} của bài học `{lesson_id}`.")
            except UploadValidationError as exc:
                st.error(str(exc))
            except Exception:
                st.error("Lỗi khi nạp bài giảng. Vui lòng thử lại hoặc liên hệ quản trị viên.")


def _render_lesson_management(filter_course: str) -> None:
    st.markdown("##### 📚 Quản lý bài giảng & Chính sách AI theo bài học")
    _t0 = perf_mark("_render_lesson_management: before list_lessons")
    lessons = cms_repository.list_lessons(course_id=filter_course or None)
    perf_mark(f"_render_lesson_management: after list_lessons ({len(lessons)} lessons)", _t0)
    if not lessons:
        ui_kit.empty_state("Chưa có bài giảng nào trong CMS.", icon="📭")
        return

    for lesson in lessons:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.markdown(f"**{lesson.title}** — `{lesson.course_id}/{lesson.lesson_id}` ({len(lesson.versions)} phiên bản)")
                st.caption(f"Chủ đề: {lesson.topic_id or '—'} · Mục tiêu: {lesson.learning_outcome or '—'}")
            with c2:
                new_enabled = st.checkbox("Bật AI", value=lesson.ai_enabled, key=f"cms_ai_toggle_{lesson.lesson_id}")
                if new_enabled != lesson.ai_enabled:
                    cms_repository.set_ai_enabled(lesson.lesson_id, new_enabled)
                    st.rerun()
            with c3:
                new_official = st.checkbox("Nguồn chính thức", value=lesson.official_source, key=f"cms_official_{lesson.lesson_id}")
                if new_official != lesson.official_source:
                    cms_repository.mark_official_source(lesson.lesson_id, new_official)
                    st.rerun()

            with st.expander("Chính sách AI cho bài học này (Mục 11)"):
                pc1, pc2, pc3, pc4 = st.columns(4)
                flags = [
                    ("supplementary_allowed", "Cho phép kiến thức bổ sung", pc1),
                    ("socratic_allowed", "Cho phép Socratic", pc2),
                    ("quiz_allowed", "Cho phép tạo quiz", pc3),
                    ("quiz_requires_approval", "Quiz cần GV duyệt", pc4),
                ]
                for field_name, label, col in flags:
                    with col:
                        current_value = getattr(lesson, field_name)
                        new_value = st.checkbox(label, value=current_value, key=f"cms_flag_{field_name}_{lesson.lesson_id}")
                        if new_value != current_value:
                            cms_repository.set_policy_flag(lesson.lesson_id, field_name, new_value)
                            st.rerun()

                new_difficulty = st.selectbox("Độ khó", ["Foundation", "Standard", "Advanced"],
                                               index=["Foundation", "Standard", "Advanced"].index(lesson.difficulty),
                                               key=f"cms_diff_{lesson.lesson_id}")
                if new_difficulty != lesson.difficulty:
                    cms_repository.update_difficulty(lesson.lesson_id, new_difficulty)

                term, preferred = st.columns(2)
                with term:
                    term_word = st.text_input("Thuật ngữ hay bị dùng sai", key=f"cms_term_{lesson.lesson_id}")
                with preferred:
                    preferred_word = st.text_input("Thuật ngữ Giảng viên muốn dùng thay", key=f"cms_preferred_{lesson.lesson_id}")
                if st.button("Thêm thuật ngữ ưu tiên", key=f"cms_term_btn_{lesson.lesson_id}") and term_word and preferred_word:
                    cms_repository.add_preferred_terminology(lesson.lesson_id, term_word, preferred_word)
                    st.rerun()
                if lesson.preferred_terminology:
                    st.caption("Thuật ngữ ưu tiên: " + " | ".join(f"{t['term']} → {t['preferred']}" for t in lesson.preferred_terminology))

                note = st.text_input("Thêm ghi chú giải thích cho AI tham khảo", key=f"cms_note_input_{lesson.lesson_id}")
                if st.button("Thêm ghi chú", key=f"cms_note_btn_{lesson.lesson_id}") and note:
                    cms_repository.add_explanation_note(lesson.lesson_id, note)
                    st.rerun()

                faq_q = st.text_input("Câu hỏi FAQ", key=f"cms_faq_q_{lesson.lesson_id}")
                faq_a = st.text_input("Trả lời FAQ", key=f"cms_faq_a_{lesson.lesson_id}")
                if st.button("Thêm FAQ", key=f"cms_faq_btn_{lesson.lesson_id}") and faq_q and faq_a:
                    cms_repository.add_faq(lesson.lesson_id, faq_q, faq_a)
                    st.rerun()

                if lesson.explanation_notes:
                    st.caption("Ghi chú hiện có: " + " | ".join(lesson.explanation_notes))
                if lesson.faq:
                    st.caption(f"{len(lesson.faq)} câu FAQ đã lưu.")

                archived = cms_repository.list_archived_versions(lesson.lesson_id)
                if archived:
                    st.caption("Phiên bản lưu trữ (không còn dùng cho retrieval): " +
                               ", ".join(f"v{a.version} ({a.uploaded_at[:10]})" for a in archived))
                    exclude_pick = st.selectbox(
                        "Loại 1 phiên bản khỏi retrieval (nếu phát hiện lỗi)", ["—"] + [f"v{a.version}" for a in lesson.versions],
                        key=f"cms_exclude_pick_{lesson.lesson_id}",
                    )
                    if exclude_pick != "—" and st.button("Loại bỏ phiên bản này", key=f"cms_exclude_btn_{lesson.lesson_id}"):
                        target_version = next(v for v in lesson.versions if f"v{v.version}" == exclude_pick)
                        cms_repository.exclude_document(lesson.lesson_id, target_version.document_id)
                        st.rerun()


def _render_quiz_review_queue(filter_course: str, reviewer_id: str) -> None:
    st.markdown("##### 🧾 Hàng đợi duyệt câu hỏi Quiz (Quiz Review Queue)")
    st.caption("Xem xét, chỉnh sửa và phê duyệt các câu hỏi trắc nghiệm AI sinh từ bài giảng trước khi hiển thị cho sinh viên.")
    _tq0 = perf_mark("_render_quiz_review_queue: before list_pending_quizzes")
    pending = learning_explainer.list_pending_quizzes(filter_course or None)
    perf_mark(f"_render_quiz_review_queue: after list_pending_quizzes ({len(pending)} pending)", _tq0)
    if not pending:
        ui_kit.empty_state("Không có bộ câu hỏi nào đang chờ duyệt.", icon="✅", hint="Tất cả câu hỏi đã được xử lý hoặc bài học không yêu cầu duyệt trước.")
        return

    for item in pending:
        lesson = cms_repository.get_lesson(item["lesson_id"])
        lesson_title = lesson.title if lesson else item["lesson_id"]
        learning_outcome = lesson.learning_outcome if lesson and lesson.learning_outcome else "Chưa có chuẩn đầu ra cụ thể"
        difficulty = _LEVEL_DISPLAY.get(lesson.difficulty, lesson.difficulty) if lesson else "Tiêu chuẩn"
        q_id = item["queue_id"]

        with st.container(border=True):
            hdr_col1, hdr_col2 = st.columns([3, 1])
            with hdr_col1:
                st.markdown(f"#### 📝 {lesson_title} · `{item.get('course_id', 'CS')}`")
                st.caption(f"**Chuẩn đầu ra:** {learning_outcome} · **Độ khó:** {difficulty} · **Gửi lúc:** {item['submitted_at'][:16].replace('T', ' ')}")
            with hdr_col2:
                ui_kit.render_badge("Chờ giảng viên duyệt", kind="warning")

            questions = item["blueprint"]["questions"]
            st.markdown(f"**Danh sách {len(questions)} câu hỏi được đề xuất:**")

            for i, q in enumerate(questions):
                st.markdown(f"**Câu {i + 1}:** {q['question_text']}")
                opts_cols = st.columns(len(q['options']))
                for opt_idx, opt in enumerate(q['options']):
                    with opts_cols[opt_idx]:
                        if opt_idx == q['correct_answer_index']:
                            st.success(f"**[Đúng]** {opt}")
                        else:
                            st.info(f"{opt}")
                st.caption(f"💡 **Giải thích:** {q.get('explanation', '—')}")
                st.markdown(
                    f"<div style='margin-bottom:0.6rem;'>{ui_kit.source_citation_badge(lesson_title, section='Bài giảng chính thức')}</div>",
                    unsafe_allow_html=True,
                )

            comment = st.text_input("Ghi chú nhận xét của Giảng viên:", key=f"quiz_review_comment_{q_id}")

            with st.expander("✏️ Chỉnh sửa câu hỏi trước khi duyệt (Edit)", expanded=False):
                edited_questions = []
                for i, q in enumerate(questions):
                    st.markdown(f"**Chỉnh sửa Câu {i + 1}:**")
                    ed_text = st.text_input(f"Nội dung câu {i + 1}:", value=q["question_text"], key=f"edit_q_text_{q_id}_{i}")
                    ed_opts = []
                    for opt_idx, opt in enumerate(q["options"]):
                        ed_opt = st.text_input(f"Lựa chọn {opt_idx + 1}:", value=opt, key=f"edit_q_opt_{q_id}_{i}_{opt_idx}")
                        ed_opts.append(ed_opt)
                    ed_correct = st.number_input(
                        f"Vị trí đáp án đúng (1 đến {len(q['options'])}):",
                        min_value=1,
                        max_value=len(q["options"]),
                        value=int(q["correct_answer_index"]) + 1,
                        key=f"edit_q_correct_{q_id}_{i}",
                    ) - 1
                    ed_exp = st.text_area(f"Giải thích câu {i + 1}:", value=q.get("explanation", ""), key=f"edit_q_exp_{q_id}_{i}")
                    edited_questions.append({
                        "question_text": ed_text,
                        "options": ed_opts,
                        "correct_answer_index": int(ed_correct),
                        "explanation": ed_exp,
                        "source_document_id": q.get("source_document_id", ""),
                        "question_id": q.get("question_id", f"q_{i}"),
                        "difficulty": q.get("difficulty", "Standard"),
                    })
                if st.button("💾 Lưu bản sửa & Phê duyệt", key=f"quiz_save_edit_{q_id}", type="primary"):
                    learning_explainer.review_quiz(
                        q_id, "EDIT", reviewer_id=reviewer_id, comment=comment or "Đã chỉnh sửa nội dung bởi giảng viên",
                        edited_questions=edited_questions,
                    )
                    st.success("✅ Đã cập nhật và phê duyệt bộ câu hỏi thành công!")
                    st.rerun()

            btn_c1, btn_c2 = st.columns([1, 1])
            with btn_c1:
                if st.button("✅ Phê duyệt nguyên bản (Approve)", key=f"quiz_approve_{q_id}", type="primary", width="stretch"):
                    learning_explainer.review_quiz(q_id, "APPROVE", reviewer_id=reviewer_id, comment=comment)
                    st.success("✅ Đã phê duyệt bộ quiz cho bài học.")
                    st.rerun()
            with btn_c2:
                if st.button("❌ Từ chối bộ câu hỏi (Reject)", key=f"quiz_reject_{q_id}", width="stretch"):
                    learning_explainer.review_quiz(q_id, "REJECT", reviewer_id=reviewer_id, comment=comment or "Không đạt yêu cầu")
                    st.warning("Đã từ chối bộ câu hỏi.")
                    st.rerun()
    perf_mark(f"_render_quiz_review_queue: TOTAL render loop ({len(pending)} items)", _tq0)


def _render_lecturer_analytics(filter_course: str) -> None:
    st.markdown("##### 📊 Dashboard phân tích tương tác Sinh viên")
    fc1, fc2 = st.columns(2)
    with fc1:
        analytics_course = st.text_input("Mã môn học cần xem phân tích", value=filter_course or "CS301", key="cms_analytics_course")
    with fc2:
        lesson_filter = st.text_input("Lọc theo mã bài học (để trống = tất cả bài trong môn)", key="cms_analytics_lesson")

    if not st.button("Xem phân tích", key="cms_run_analytics"):
        return
    analytics = learning_explainer.get_lecturer_analytics(analytics_course)
    if analytics["total_questions"] == 0:
        ui_kit.empty_state("Chưa có tương tác nào được ghi nhận cho môn này.", icon="📭")
        return

    ui_kit.kpi_row([
        ("Tổng số câu hỏi", analytics["total_questions"]),
        ("Tỷ lệ hỏi ngoài phạm vi CMS", f"{analytics['no_cms_rate'] * 100:.0f}%"),
    ])
    lc, mc = st.columns(2)
    with lc:
        st.markdown("**Bài học được hỏi nhiều nhất:**")
        for lesson_id, count in analytics["top_topics"]:
            if lesson_filter and lesson_id != lesson_filter:
                continue
            st.caption(f"• {lesson_id}: {count} lượt hỏi")
    with mc:
        if analytics["misconceptions"]:
            st.markdown("**Ngộ nhận phổ biến:**")
            for label, count in analytics["misconceptions"]:
                st.caption(f"⚠️ {label}: {count} lượt")
        else:
            st.caption("Chưa phát hiện ngộ nhận phổ biến nào.")

    if analytics["top_questions"]:
        with st.expander("Câu hỏi được hỏi nhiều nhất (đã ẩn thông tin sinh viên)"):
            for q, count in analytics["top_questions"]:
                st.caption(f"• \"{q[:120]}\" — {count} lượt")

    st.caption(
        "Lưu ý: phân tích chỉ hiển thị số liệu TỔNG HỢP — không hiển thị nội dung chat riêng tư của từng "
        "sinh viên theo mặc định (Mục 13)."
    )


def _render_lecturer_view(df, role, llm_integration) -> None:
    _t0 = perf_mark("_render_lecturer_view: ENTER")
    filter_course = st.text_input("Lọc theo mã môn học (để trống = xem tất cả)", key="cms_filter_course")
    sub_tabs = st.tabs(["📤 Nạp & Quản lý", "🧾 Duyệt Quiz", "📊 Dashboard phân tích"])
    with sub_tabs[0]:
        _render_lecturer_upload(role, llm_integration)
        _t1 = perf_mark("_render_lecturer_view: after _render_lecturer_upload", _t0)
        _render_lesson_management(filter_course)
        perf_mark("_render_lecturer_view: after _render_lesson_management", _t1)
    with sub_tabs[1]:
        _t2 = perf_mark("_render_lecturer_view: before _render_quiz_review_queue")
        _render_quiz_review_queue(filter_course, reviewer_id=str(role or "GV"))
        perf_mark("_render_lecturer_view: after _render_quiz_review_queue", _t2)
    with sub_tabs[2]:
        _render_lecturer_analytics(filter_course)
    perf_mark("_render_lecturer_view: TOTAL", _t0)


# ============================================================================
# SINH VIÊN
# ============================================================================
def _infer_topic_mastery(df, current_student_id: str, topic_id: str):
    """Ước lượng mastery 0-1 từ CỘT ĐIỂM CHỦ ĐỀ thật nếu topic_id khớp — trung
    thực trả về None (không đoán) nếu không có dữ liệu khớp. Dùng làm fallback
    tier cuối cùng cho resolve_explanation_level() khi không có learning_profile."""
    if not current_student_id or not topic_id:
        return None
    id_col = next((c for c in df.columns if "id" in c.lower()), None)
    if not id_col:
        return None
    matching_col = next((c for c in TOPIC_SCORE_COLUMNS if topic_id.lower() in c.lower() or topic_id.lower() in TOPIC_SCORE_COLUMNS[c].lower()), None)
    if not matching_col or matching_col not in df.columns:
        return None
    rows = df[df[id_col].astype(str) == str(current_student_id)]
    if rows.empty:
        return None
    try:
        return float(rows.iloc[0][matching_col]) / 10.0
    except (TypeError, ValueError):
        return None


def _resolve_level_for_student(df, current_student_id, course_id, lesson_id, topic_id):
    """Mục 1 — dùng resolve_explanation_level() thật thay vì so khớp cột đơn lẻ
    trực tiếp trong UI. UI chỉ hiển thị friendly_reason, KHÔNG hiện field kỹ thuật."""
    learning_prof = None
    try:
        from dss.services.learning_profile import StudentLearningProfile
        if current_student_id and df is not None:
            id_col = next((c for c in df.columns if "id" in c.lower()), None)
            if id_col:
                rows = df[df[id_col].astype(str) == str(current_student_id)]
                if not rows.empty:
                    row_dict = rows.iloc[0].to_dict()
                    learning_prof = StudentLearningProfile.build_from_lms_records(
                        student_id=str(current_student_id), course_id=course_id, raw_lms_data=row_dict,
                    )
    except Exception:
        learning_prof = None
    return learning_explainer.resolve_explanation_level(
        str(current_student_id or "guest"), course_id, lesson_id, topic_id, learning_profile=learning_prof, df=df,
    )


def _render_socratic_panel(llm_integration, course_id, lesson, explanation_level, pseudonym) -> None:
    session_key = f"explainer_socratic_session_{lesson.lesson_id}"
    if session_key not in st.session_state:
        st.session_state[session_key] = learning_explainer.start_socratic_session(lesson.topic_id or lesson.title)
        st.session_state[session_key], first_result = learning_explainer.advance_socratic_session(
            llm_integration, st.session_state[session_key], "start", course_id, lesson.lesson_id, explanation_level,
            user_id=pseudonym,
        )

    session = st.session_state[session_key]
    for turn in session.history:
        if turn.get("learner_answer"):
            with st.chat_message("user"):
                st.markdown(turn["learner_answer"])
        with st.chat_message("assistant"):
            st.markdown(turn["ai_response"])

    if session.completion_status != "IN_PROGRESS":
        ui_kit.render_badge(f"Phiên Socratic đã kết thúc ({session.completion_status})", kind="success")
        if st.button("Bắt đầu phiên Socratic mới", key=f"socratic_restart_{lesson.lesson_id}"):
            del st.session_state[session_key]
            st.rerun()
        return

    learner_answer = st.chat_input("Trả lời câu hỏi gợi mở của AI...", key=f"socratic_input_{lesson.lesson_id}")
    a1, a2, a3, a4 = st.columns(4)
    action = None
    with a1:
        if st.button("💡 Gợi ý (Hint)", key=f"socratic_hint_{lesson.lesson_id}", width="stretch"):
            action = "hint"
    with a2:
        if st.button("📖 Giải thích thêm", key=f"socratic_more_{lesson.lesson_id}", width="stretch"):
            action = "explain_more"
    with a3:
        if st.button("🏳️ Em chịu thua", key=f"socratic_giveup_{lesson.lesson_id}", width="stretch"):
            action = "give_up"
    with a4:
        if st.button("✅ Hiện giải thích đầy đủ", key=f"socratic_full_{lesson.lesson_id}", width="stretch"):
            action = "show_full_explanation"

    if learner_answer:
        action = "answer"

    if action:
        with st.spinner("AI đang xử lý..."):
            updated_session, result = learning_explainer.advance_socratic_session(
                llm_integration, session, action, course_id, lesson.lesson_id, explanation_level,
                learner_answer=learner_answer, user_id=pseudonym,
            )
        if updated_session.misconception:
            learning_explainer.record_misconception(
                pseudonym, course_id, lesson.topic_id or lesson.title,
                updated_session.misconception["label"], learner_answer or "", hint=updated_session.misconception["hint"],
            )
        st.session_state[session_key] = updated_session
        learning_explainer.log_interaction(
            pseudonym, course_id, lesson.lesson_id, lesson.topic_id, learner_answer or f"[Socratic:{action}]",
            explanation_level, result.has_cms_content,
        )
        st.rerun()


def _render_quiz_panel(llm_integration, course_id, lesson, explanation_level, pseudonym) -> None:
    if not lesson.quiz_allowed:
        return
    st.markdown("---")
    if st.button("📝 Tạo quiz kiểm tra kiến thức từ bài này", key="explainer_gen_quiz"):
        spinner_msg = ui_kit.cold_start_aware_message(llm_integration, "Đang tra cứu nội dung bài giảng...")
        try:
            with st.spinner(spinner_msg):
                chunks = cms_repository.retrieve_lesson_content(llm_integration, lesson.title, course_id=course_id, lesson_id=lesson.lesson_id, top_k=8)
        except Exception:
            # COLDSTART-001/B5: lỗi khởi tạo (vd. mô hình embedding không tải được)
            # phải kết thúc spinner và báo lỗi thân thiện — không được để trang
            # trông như treo mãi, và không được âm thầm chuyển sang nội dung demo giả.
            st.error("Không thể tra cứu nội dung bài giảng lúc này. Vui lòng thử lại sau.")
            chunks = None
        if chunks is not None:
            if not chunks:
                st.warning("Chưa đủ nội dung bài giảng để tạo câu hỏi luyện tập cho bài này.")
            else:
                blueprint, message = learning_explainer.request_lesson_quiz(course_id, lesson.lesson_id, chunks, num_questions=3)
                if blueprint is None:
                    st.info(f"ℹ️ {message}")
                st.session_state[f"explainer_quiz_{lesson.lesson_id}"] = blueprint

    blueprint = st.session_state.get(f"explainer_quiz_{lesson.lesson_id}")
    if blueprint:
        st.markdown("##### 🧪 Quiz kiểm tra nhanh")
        answers = {}
        for i, q in enumerate(blueprint.questions):
            st.markdown(f"**Câu {i + 1}.** {q.question_text}")
            answers[i] = st.radio("Chọn đáp án:", q.options, key=f"explainer_quiz_q_{lesson.lesson_id}_{i}", label_visibility="collapsed")
        if st.button("Nộp bài", key=f"explainer_quiz_submit_{lesson.lesson_id}"):
            active_misconception = learning_explainer.get_active_misconception(pseudonym, course_id, lesson.topic_id or lesson.title)
            for i, q in enumerate(blueprint.questions):
                is_correct = q.options.index(answers[i]) == q.correct_answer_index if answers.get(i) in q.options else False
                if not is_correct:
                    misconception = learning_explainer.detect_misconception(lesson.topic_id or lesson.title, answers.get(i, ""))
                    st.error(f"Câu {i + 1}: Chưa đúng. {q.explanation}")
                    if misconception:
                        st.warning(f"💡 {misconception['label']}: {misconception['hint']}")
                        learning_explainer.record_misconception(
                            pseudonym, course_id, lesson.topic_id or lesson.title, misconception["label"], answers.get(i, ""), hint=misconception["hint"],
                        )
                    learning_explainer.log_interaction(pseudonym, course_id, lesson.lesson_id, lesson.topic_id, q.question_text, explanation_level, True, misconception=misconception, quiz_correct=False)
                else:
                    st.success(f"Câu {i + 1}: Chính xác!")
                    learning_explainer.log_interaction(pseudonym, course_id, lesson.lesson_id, lesson.topic_id, q.question_text, explanation_level, True, quiz_correct=True)
            if active_misconception and all(q.options.index(answers[i]) == q.correct_answer_index for i, q in enumerate(blueprint.questions) if answers.get(i) in q.options):
                learning_explainer.resolve_misconception(
                    pseudonym, course_id, lesson.topic_id or lesson.title, active_misconception["label"],
                    "Trả lời đúng toàn bộ quiz kiểm tra sau khi từng bị phát hiện ngộ nhận này.",
                )


def _render_student_view(df, role, current_student_id, llm_integration) -> None:
    lessons = cms_repository.list_lessons()
    if not lessons:
        ui_kit.empty_state(
            "Chưa có bài giảng nào để giải thích.", icon="📭",
            hint="Giảng viên cần nạp bài giảng trước khi Sinh viên có thể dùng AI giải thích.",
        )
        return

    courses = sorted({l.course_id for l in lessons})
    course_id = st.selectbox("Môn học", courses, key="explainer_course_pick")
    course_lessons = [l for l in lessons if l.course_id == course_id]
    lesson_titles = {l.title: l for l in course_lessons}
    chosen_title = st.selectbox("Bài học", list(lesson_titles.keys()), key="explainer_lesson_pick")
    lesson = lesson_titles[chosen_title]

    if not lesson.ai_enabled:
        st.warning("AI giải thích hiện chưa được Giảng viên bật cho bài học này.")
        return

    pseudonym = privacy_service.generate_pseudonym(str(current_student_id or "guest"))
    level_resolution = _resolve_level_for_student(df, current_student_id, course_id, lesson.lesson_id, lesson.topic_id)
    explanation_level = level_resolution.level

    c1, c2 = st.columns([2, 1])
    with c1:
        st.info(f"📖 **{lesson.title}** · Mục tiêu: {lesson.learning_outcome or '—'}")
        st.caption(f"🧭 {level_resolution.friendly_reason}")
    with c2:
        ui_kit.render_badge(f"Mức giải thích: {_LEVEL_DISPLAY[explanation_level]}", kind="info")
        socratic_mode = st.checkbox("🧑‍🏫 Học bằng câu hỏi gợi mở (Socratic)", key="explainer_socratic", value=False,
                                     disabled=not lesson.socratic_allowed)
        if not lesson.socratic_allowed:
            st.caption("Giảng viên chưa bật Socratic cho bài này.")

    if socratic_mode and lesson.socratic_allowed:
        st.markdown("##### 🧑‍🏫 Chế độ Socratic — AI sẽ hỏi gợi mở, không đưa đáp án ngay")
        _render_socratic_panel(llm_integration, course_id, lesson, explanation_level, pseudonym)
        _render_quiz_panel(llm_integration, course_id, lesson, explanation_level, pseudonym)
        return

    # ---- Chat thường (không Socratic) ----
    chat_key = f"explainer_chat_{lesson.lesson_id}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
    chat_history = st.session_state[chat_key]

    supplementary_flag_key = f"explainer_supplementary_{lesson.lesson_id}"
    if supplementary_flag_key not in st.session_state:
        st.session_state[supplementary_flag_key] = False

    st.markdown("##### 💬 Trợ giảng AI giải thích bài học")
    quick_actions = [
        "💡 Giải thích dễ hơn",
        "🔍 Cho ví dụ minh họa",
        "📐 Giải thích công thức",
        "⚖️ So sánh khái niệm",
        "📝 Tạo câu hỏi luyện tập",
        "❓ Kiểm tra em đã hiểu chưa",
    ]
    qcols = st.columns(3)
    pending_q = None
    for i, qa in enumerate(quick_actions):
        with qcols[i % 3]:
            if st.button(qa, key=f"explainer_quick_{i}", use_container_width=True):
                pending_q = qa

    if pending_q == "📝 Tạo câu hỏi luyện tập":
        chunks = cms_repository.retrieve_lesson_content(llm_integration, lesson.title, course_id=course_id, lesson_id=lesson.lesson_id, top_k=8)
        if not chunks:
            st.warning("Chưa đủ nội dung bài giảng để tạo câu hỏi luyện tập cho bài này.")
        else:
            blueprint, message = learning_explainer.request_lesson_quiz(course_id, lesson.lesson_id, chunks, num_questions=3)
            if blueprint is None:
                st.info(f"ℹ️ {message}")
            st.session_state[f"explainer_quiz_{lesson.lesson_id}"] = blueprint
            st.rerun()

    chat_box = st.container(height=550)
    with chat_box:
        if not chat_history:
            st.caption("Chưa có câu hỏi nào — hãy bấm các nút gợi ý nhanh ở trên hoặc nhập câu hỏi bên dưới.")
        for msg in chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("citations"):
                    cit_html = "".join(ui_kit.source_citation_badge(str(c)) for c in msg["citations"])
                    st.markdown(
                        f"<div style='margin-top:0.4rem;display:flex;flex-wrap:wrap;gap:0.25rem;'>{cit_html}</div>",
                        unsafe_allow_html=True,
                    )

    typed_q = st.chat_input("Hỏi AI về bài học này (bài giảng, khái niệm, công thức, ví dụ)...", key="explainer_chat_input")
    question = pending_q or typed_q

    if question and question != "📝 Tạo câu hỏi luyện tập":
        chat_history.append({"role": "user", "content": question})
        active_misconception = learning_explainer.get_active_misconception(pseudonym, course_id, lesson.topic_id or lesson.title)
        mode = learning_explainer.CMS_PLUS_SUPPLEMENTARY if (st.session_state[supplementary_flag_key] and lesson.supplementary_allowed) else learning_explainer.CMS_ONLY
        spinner_msg = ui_kit.cold_start_aware_message(llm_integration, "Đang tra cứu bài giảng và soạn giải thích...")
        with st.spinner(spinner_msg):
            try:
                result = learning_explainer.generate_explanation(
                    llm_integration, question, course_id, lesson.lesson_id, lesson.topic_id, explanation_level,
                    socratic_mode=False, mode=mode, active_misconception=active_misconception,
                    user_id=pseudonym,
                )
                learning_explainer.log_interaction(
                    pseudonym, course_id, lesson.lesson_id, lesson.topic_id, question, explanation_level, result.has_cms_content,
                )
                answer_text = result.answer
                if result.hallucinated_citations:
                    answer_text += "\n\n*(⚠️ Một số nguồn nêu ra có thể không khớp đúng tài liệu đã nạp.)*"
                chat_history.append({"role": "assistant", "content": answer_text, "citations": _unique_labels(result.citations)})

                # Mục 3 — chỉ đề nghị nút "giải thích thêm" khi CMS_ONLY thực sự KHÔNG có nội dung
                if not result.has_cms_content and lesson.supplementary_allowed and mode == learning_explainer.CMS_ONLY:
                    st.session_state[f"explainer_offer_supplementary_{lesson.lesson_id}"] = question
            except Exception:
                _logger.exception("Giải thích bài giảng: gọi AI thất bại (lesson=%s)", lesson.lesson_id)
                err_msg = "Trợ lý AI hiện chưa sẵn sàng. Vui lòng thử lại sau hoặc liên hệ quản trị viên."
                chat_history.append({"role": "assistant", "content": err_msg, "citations": []})
        st.rerun()

    offer_key = f"explainer_offer_supplementary_{lesson.lesson_id}"
    if st.session_state.get(offer_key):
        st.info("Nội dung này chưa có trong bài giảng. Bạn có muốn AI giải thích thêm bằng kiến thức bổ sung không?")
        oc1, oc2 = st.columns(2)
        with oc1:
            if st.button("✅ Có, giải thích với kiến thức bổ sung", key=f"explainer_accept_supp_{lesson.lesson_id}"):
                pending_question = st.session_state.pop(offer_key)
                st.session_state[supplementary_flag_key] = True
                active_misconception = learning_explainer.get_active_misconception(pseudonym, course_id, lesson.topic_id or lesson.title)
                spinner_msg = ui_kit.cold_start_aware_message(llm_integration, "Đang soạn giải thích bổ sung...")
                try:
                    with st.spinner(spinner_msg):
                        result = learning_explainer.generate_explanation(
                            llm_integration, pending_question, course_id, lesson.lesson_id, lesson.topic_id, explanation_level,
                            socratic_mode=False, mode=learning_explainer.CMS_PLUS_SUPPLEMENTARY, active_misconception=active_misconception,
                            user_id=pseudonym,
                        )
                    chat_history.append({"role": "assistant", "content": result.answer, "citations": _unique_labels(result.citations)})
                except Exception:
                    _logger.exception("Giải thích bổ sung: gọi AI thất bại (lesson=%s)", lesson.lesson_id)
                    err_msg = "Trợ lý AI hiện chưa sẵn sàng. Vui lòng thử lại sau hoặc liên hệ quản trị viên."
                    chat_history.append({"role": "assistant", "content": err_msg, "citations": []})
                st.rerun()
        with oc2:
            if st.button("❌ Không, chỉ dùng nội dung bài giảng", key=f"explainer_decline_supp_{lesson.lesson_id}"):
                st.session_state.pop(offer_key, None)
                st.rerun()

    _render_quiz_panel(llm_integration, course_id, lesson, explanation_level, pseudonym)


def learning_explainer_tab(df, role=None, current_student_id=None, llm_integration=None) -> None:
    # PERF-001 (dev/test only, xem dss/config.py::perf_mark)
    _perf_t0 = perf_mark("learning_explainer_tab: ENTER")
    # Student Information Architecture (audit 2026-09): bỏ tên hệ thống viết
    # tắt "(CMS)" khỏi tiêu đề Sinh viên nhìn thấy — chỉ có ý nghĩa với
    # Giảng viên/Admin (người thực sự quản trị nội dung trong CMS).
    if role in ("Giảng viên / CVHT", "Admin"):
        # FINAL PRODUCTION GAP CLOSURE (Phần 21/41): bỏ "(CMS)" khỏi tiêu đề
        # Giảng viên/Admin — cùng nguyên tắc đã áp dụng cho Sinh viên.
        ui_kit.section_header(
            "Giải thích bài giảng",
            subtitle="AI ưu tiên tuyệt đối nội dung bài giảng thật của Giảng viên — không phải chatbot kiến thức chung.",
        )
        _render_lecturer_view(df, role, llm_integration)
        perf_mark("learning_explainer_tab: EXIT (lecturer)", _perf_t0)
    else:
        ui_kit.section_header(
            "Giải thích bài học",
            subtitle="Hỏi AI về nội dung bài giảng thật của Giảng viên — không phải chatbot kiến thức chung.",
        )
        _render_student_view(df, role, current_student_id, llm_integration)
        perf_mark("learning_explainer_tab: EXIT (student)", _perf_t0)
