"""Real Streamlit classroom flows backed by the actual transactional services."""

from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from dss.platform.context import Actor
from dss.platform.store import reset_platform_engines
from dss.services import classroom_learning_service as learning
from dss.services import classroom_service as classes
from dss.tabs import classroom_tab as ui


def _render():
    from dss.tabs.classroom_tab import classroom_tab

    classroom_tab()


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    reset_platform_engines()
    admin = Actor("1", "admin", classes.ADMIN)
    teacher = Actor("1", "teacher", classes.TEACHER)
    student = Actor("1", "student", classes.STUDENT, "SV1")
    classroom = classes.create_class(admin, "LAW01", "LAW101", "Foundations", "2026")
    classes.assign_teacher(admin, classroom["id"], teacher.username)
    classes.enroll_student(admin, classroom["id"], student.student_id)
    questions = [
        {
            "question_id": "q1",
            "topic_id": "sources",
            "text": "Question 1",
            "options": ["A", "B"],
            "correct_answer_index": 0,
            "explanation": "Teacher-only explanation",
        },
        {
            "question_id": "q2",
            "topic_id": "cases",
            "text": "Question 2",
            "options": ["A", "B"],
            "correct_answer_index": 1,
            "explanation": "Teacher-only explanation",
        },
    ]
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: [])
    monkeypatch.setattr(ui, "current_actor", lambda: student)
    yield {"admin": admin, "teacher": teacher, "student": student, "class": classroom, "questions": questions}
    reset_platform_engines()


def _publish(workspace, maximum=2):
    assessment = learning.create_assessment(
        workspace["teacher"], workspace["class"]["id"], "Formative test", workspace["questions"], max_attempts=maximum
    )
    return learning.publish_assessment(workspace["teacher"], assessment["id"])


def _app():
    app = AppTest.from_function(_render, default_timeout=30).run()
    assert not app.exception
    assert not app.error, [item.value for item in app.error]
    return app


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_student_submits_real_attempt_marks_progress_reopens_and_retests(workspace):
    assessment = _publish(workspace)
    app = _app()
    assert app.header[0].value == "Lớp học và đánh giá"
    assert len(app.radio) == 2
    assert not app.json
    assert not app.metric
    app.radio[0].set_value(1)
    app.radio[1].set_value(0)
    _button(app, "Nộp bài và cập nhật kế hoạch").click().run(timeout=30)
    assert not app.exception and not app.error
    assert any("0/10" in item.value for item in app.success)
    assert len(app.checkbox) == 2
    results = learning.list_my_attempts(workspace["student"], workspace["class"]["id"])
    assert results[0]["score"] == 0
    assert results[0]["assessment_id"] == assessment["id"]
    # Topic scores must be visible to the student, including measured zero.
    assert any(
        "Chủ đề" in frame.value.columns and frame.value["Điểm / 10"].tolist() == [0, 0] for frame in app.dataframe
    )
    app.checkbox[0].check().run(timeout=30)
    assert not app.exception and not app.error
    first_plan = learning.get_my_plan(workspace["student"], workspace["class"]["id"])
    assert first_plan["completion"]["0"] is True
    reopened = _app()
    assert reopened.checkbox[0].value is True
    assert len(learning.list_my_attempts(workspace["student"], workspace["class"]["id"])) == 1
    # New runtime state does not auto-submit or consume another attempt.
    app = reopened
    assert len(app.radio) == 2
    app.radio[0].set_value(0)
    app.radio[1].set_value(1)
    _button(app, "Nộp bài và cập nhật kế hoạch").click().run(timeout=30)
    assert not app.exception and not app.error
    assert any("10/10" in item.value for item in app.success)
    assert not any(button.label == "Bắt đầu lượt làm tiếp theo" for button in app.button)
    plans = learning.list_my_plans(workspace["student"], workspace["class"]["id"])
    assert [plan["version"] for plan in plans] == [2, 1]
    assert plans[0]["completion"] == {}
    assert plans[1]["completion"] == {"0": True}


def test_form_requires_all_answers_and_next_attempt_resets_radio_values(workspace):
    _publish(workspace)
    app = _app()
    _button(app, "Nộp bài và cập nhật kế hoạch").click().run(timeout=30)
    assert any("trả lời đủ" in item.value for item in app.warning)
    assert learning.list_my_attempts(workspace["student"], workspace["class"]["id"]) == []
    app.radio[0].set_value(1)
    app.radio[1].set_value(0)
    _button(app, "Nộp bài và cập nhật kế hoạch").click().run(timeout=30)
    assert not app.exception and not app.error
    _button(app, "Bắt đầu lượt làm tiếp theo").click().run(timeout=30)
    assert not app.exception and not app.error
    assert [radio.value for radio in app.radio] == [None, None]
    assert len(learning.list_my_attempts(workspace["student"], workspace["class"]["id"])) == 1


def test_student_can_reopen_results_and_progress_for_closed_class(workspace):
    assessment = _publish(workspace)
    result = learning.submit_attempt(workspace["student"], assessment["id"], [1, 0], "pre-close")
    classes.set_class_status(workspace["admin"], workspace["class"]["id"], "closed")
    app = _app()
    assert not app.radio
    assert any(item.value == "Kết quả đã lưu" for item in app.subheader)
    assert len(app.checkbox) == 2
    app.checkbox[0].check().run(timeout=30)
    assert not app.exception and not app.error
    assert learning.get_my_plan(workspace["student"], workspace["class"]["id"])["id"] == result["plan"]["id"]
    assert _app().checkbox[0].value is True


def test_teacher_can_save_draft_then_publish_without_creating_a_revision(workspace, monkeypatch):
    monkeypatch.setattr(ui, "current_actor", lambda: workspace["teacher"])
    draft = learning.create_assessment(
        workspace["teacher"], workspace["class"]["id"], "Initial draft", workspace["questions"]
    )
    app = _app()
    assert len(app.metric) == 3
    assert not any(button.label == "Tạo phiên bản nháp mới" for button in app.button)
    changed = deepcopy(workspace["questions"])
    changed[0]["text"] = "Corrected question"
    next(item for item in app.text_input if item.key == "draft_title_" + draft["id"]).set_value("Updated draft")
    next(item for item in app.text_area if item.key == "draft_" + draft["id"] + "_q_0_text").set_value(
        "Corrected question"
    )
    _button(app, "Lưu thay đổi bản nháp").click().run(timeout=30)
    assert not app.exception and not app.error
    saved = learning.get_assessment(workspace["teacher"], draft["id"])
    assert saved["version"] == 1 and saved["title"] == "Updated draft"
    assert saved["questions"][0]["text"] == "Corrected question"
    _button(app, "Xuất bản").click().run(timeout=30)
    assert not app.exception and not app.error
    assert learning.get_assessment(workspace["teacher"], draft["id"])["status"] == "published"
    assert any(button.label == "Tạo phiên bản nháp mới" for button in app.button)


def test_student_opens_actual_approved_cms_content_and_revocation_hides_it(workspace, monkeypatch):
    from dss.services import cms_lecture_repository as cms
    from dss.services import vector_store
    from dss.services.chunking_service import DocumentChunk

    monkeypatch.setenv("EDUDSS_CMS_STORE", "local")
    monkeypatch.setenv("EDUDSS_RAG_STORE", "local")
    lesson = cms.CMSLesson(
        lesson_id="lesson-1",
        course_id="LAW101",
        topic_id="sources",
        lecturer_id="teacher",
        title="Official source lesson",
        current_document_id="doc-1",
    )
    cms._upsert_lesson(lesson)
    text = "# Approved reading\nOfficial lesson content.\n<script>never_execute()</script>"
    store = vector_store.get_vector_store()
    store.add_chunks(
        [
            DocumentChunk(
                chunk_id="doc-1#c0",
                document_id="doc-1",
                course_id="LAW101",
                content=text,
                token_count=20,
                metadata={
                    "title": "Official source lesson",
                    "status": "APPROVED",
                    "approved_by": "teacher",
                    "chunk_index": 0,
                },
                embedding=[1.0, 0.0],
            )
        ]
    )
    monkeypatch.setattr(
        learning, "_load_resources", lambda actor, course_id: learning.approved_plan_resources(course_id)
    )
    assessment = _publish(workspace)
    saved = learning.submit_attempt(workspace["student"], assessment["id"], [1, 0], "read-material")
    app = _app()
    _button(app, "Đọc học liệu").click().run(timeout=30)
    assert not app.exception and not app.error
    rendered = next(item for item in app.markdown if "Official lesson content." in item.value)
    assert rendered.value == text
    assert rendered.proto.allow_html is False
    assert not app.radio or len(learning.list_my_attempts(workspace["student"], workspace["class"]["id"])) == 1
    cms.mark_official_source("lesson-1", False)
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert any("no longer approved" in item.value for item in app.warning)
    assert not any("Official lesson content." in item.value for item in app.markdown)
    assert learning.get_my_plan(workspace["student"], workspace["class"]["id"])["id"] == saved["plan"]["id"]


def test_teacher_can_compose_questions_using_plain_fields(workspace, monkeypatch):
    monkeypatch.setattr(ui, "current_actor", lambda: workspace["teacher"])
    app = _app()
    prefix = "compose_" + workspace["class"]["id"]
    next(item for item in app.text_input if item.key == "compose_title_" + workspace["class"]["id"]).set_value(
        "Form-created assessment"
    )
    next(item for item in app.text_input if item.key == prefix + "_q_0_topic").set_value("sources")
    next(item for item in app.text_area if item.key == prefix + "_q_0_text").set_value("Approved question from form")
    next(item for item in app.text_area if item.key == prefix + "_q_0_options").set_value(
        chr(10).join(["First option", "Second option"])
    )
    _button(app, "Lưu bài đánh giá nháp").click().run(timeout=30)
    assert not app.exception and not app.error
    rows = learning.list_assessments(workspace["teacher"], workspace["class"]["id"])
    assert len(rows) == 1 and rows[0]["status"] == "draft"
    assert rows[0]["questions"][0]["correct_answer_index"] == 0
