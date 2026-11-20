"""Test cho 3 mảng mới của AI Learning Explainer (Mục 4, 6, 7, 8):
- Quy trình duyệt quiz (PENDING_LECTURER_APPROVAL -> APPROVE/REJECT/EDIT).
- MisconceptionRecord có cấu trúc, tồn tại lâu dài, ảnh hưởng giải thích sau.
- Socratic session có trạng thái thật (nhiều bước, không tiết lộ đáp án ngay
  trừ khi give_up/show_full_explanation).
- Version-safe retrieval hardening v1 -> v2 -> v3 + tra cứu bản lưu trữ.

Dùng model embedding thật (không mock) — theo đúng pattern test_learning_explainer.py.
"""

from __future__ import annotations

import uuid

import pytest

import dss.config as dss_config
from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider

    provider = MultiAIProvider()
    provider.get_embedding("khởi động model")
    return provider


@pytest.fixture()
def unique_course():
    return f"TEST_COURSE_{uuid.uuid4().hex[:8]}"


def _ingest(llm_integration, course_id, lesson_id, topic_id, content: str, title: str):
    return cms_repository.ingest_lecture_material(
        file_bytes=content.encode("utf-8"),
        file_name=f"{lesson_id}.txt",
        title=title,
        course_id=course_id,
        lesson_id=lesson_id,
        topic_id=topic_id,
        lecturer_id="GV_TEST",
        llm_integration=llm_integration,
        learning_outcome="Test outcome",
        difficulty="Standard",
    )


# ---------------------------------------------------------------------------
# Mục 7 — version-supersession v1 -> v2 -> v3 + tra cứu bản lưu trữ
# ---------------------------------------------------------------------------
def test_v1_v2_v3_supersession_and_archived_version_lookup(llm_integration, unique_course):
    lesson_id = f"lesson_ver3_{uuid.uuid4().hex[:8]}"
    v1 = _ingest(
        llm_integration, unique_course, lesson_id, "clustering", "K-Means bản v1: chưa có K-Means++.", "Bài v1"
    )
    _ingest(
        llm_integration,
        unique_course,
        lesson_id,
        "clustering",
        "K-Means bản v2: có K-Means++ khởi tạo tốt hơn.",
        "Bài v2",
    )
    v3 = _ingest(
        llm_integration,
        unique_course,
        lesson_id,
        "clustering",
        "K-Means bản v3: thêm phần đánh giá Silhouette Score.",
        "Bài v3",
    )

    assert len(v3.versions) == 3
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    assert len(chunks) >= 1
    assert all(c["document_id"] == v3.current_document_id for c in chunks)
    assert all("v1" not in c["title"] and "v2" not in c["title"] for c in chunks)

    archived = cms_repository.list_archived_versions(lesson_id)
    archived_docs = {a.document_id for a in archived}
    assert v1.current_document_id in archived_docs or v1.versions[0].document_id in archived_docs
    assert v3.current_document_id not in archived_docs


def test_excluded_document_id_removes_current_from_retrieval(llm_integration, unique_course):
    lesson_id = f"lesson_excl_{uuid.uuid4().hex[:8]}"
    lesson = _ingest(llm_integration, unique_course, lesson_id, "clustering", "Nội dung có lỗi cần loại bỏ.", "Bài lỗi")
    cms_repository.exclude_document(lesson_id, lesson.current_document_id)
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "Nội dung", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    assert chunks == []  # trung thực trả rỗng, KHÔNG rơi về bản cũ hơn


# ---------------------------------------------------------------------------
# Mục 6 — Quy trình duyệt quiz
# ---------------------------------------------------------------------------
def test_quiz_requires_approval_never_reaches_student_until_approved(llm_integration, unique_course):
    lesson_id = f"lesson_quizreview_{uuid.uuid4().hex[:8]}"
    lesson = _ingest(
        llm_integration, unique_course, lesson_id, "clustering", "K-Means dùng khoảng cách Euclid.", "Bài Quiz Review"
    )
    assert lesson.quiz_requires_approval is True  # mặc định bắt buộc duyệt

    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    blueprint, message = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)

    assert blueprint is None  # Sinh viên KHÔNG nhận được quiz chưa duyệt
    assert "duyệt" in message.lower()

    pending = learning_explainer.list_pending_quizzes(unique_course)
    assert any(p["lesson_id"] == lesson_id for p in pending)


def test_quiz_approve_then_student_receives_it(llm_integration, unique_course):
    lesson_id = f"lesson_quizapprove_{uuid.uuid4().hex[:8]}"
    _ingest(
        llm_integration,
        unique_course,
        lesson_id,
        "clustering",
        "K-Means dùng khoảng cách Euclid để gán cụm.",
        "Bài Quiz Approve",
    )
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    _, _ = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)

    pending = learning_explainer.list_pending_quizzes(unique_course)
    target = next(p for p in pending if p["lesson_id"] == lesson_id)
    ok = learning_explainer.review_quiz(target["queue_id"], "APPROVE", reviewer_id="GV_TEST", comment="Đạt yêu cầu.")
    assert ok

    blueprint, message = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    assert blueprint is not None
    assert message is None
    assert blueprint.status == "APPROVED"
    assert blueprint.reviewed_by == "GV_TEST"


def test_quiz_rejected_never_reaches_student(llm_integration, unique_course):
    lesson_id = f"lesson_quizreject_{uuid.uuid4().hex[:8]}"
    _ingest(
        llm_integration, unique_course, lesson_id, "clustering", "K-Means dùng khoảng cách Euclid.", "Bài Quiz Reject"
    )
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)

    pending = learning_explainer.list_pending_quizzes(unique_course)
    target = next(p for p in pending if p["lesson_id"] == lesson_id)
    learning_explainer.review_quiz(
        target["queue_id"], "REJECT", reviewer_id="GV_TEST", comment="Câu hỏi không rõ ràng."
    )

    blueprint, message = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    assert blueprint is None
    assert "duyệt" in message.lower() or "mới" in message.lower()  # sẽ tạo bản mới khác, không dùng lại bản bị từ chối


def test_quiz_not_required_when_lesson_policy_disables_approval(llm_integration, unique_course):
    lesson_id = f"lesson_quiznoreview_{uuid.uuid4().hex[:8]}"
    _ingest(
        llm_integration,
        unique_course,
        lesson_id,
        "clustering",
        "K-Means dùng khoảng cách Euclid.",
        "Bài Quiz No Review",
    )
    cms_repository.set_policy_flag(lesson_id, "quiz_requires_approval", False)
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5
    )
    blueprint, message = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    assert blueprint is not None
    assert message is None


# ---------------------------------------------------------------------------
# Mục 8 — MisconceptionRecord có cấu trúc, ảnh hưởng giải thích sau
# ---------------------------------------------------------------------------
def test_misconception_record_persists_and_increments_occurrence():
    student = f"stu_{uuid.uuid4().hex[:8]}"
    course_id = "COURSE_MISC"
    learning_explainer.record_misconception(
        student,
        course_id,
        "clustering",
        "Nhầm K-Means với classification",
        "trả lời sai lần 1",
        hint="K-Means là unsupervised.",
    )
    learning_explainer.record_misconception(
        student,
        course_id,
        "clustering",
        "Nhầm K-Means với classification",
        "trả lời sai lần 2",
        hint="K-Means là unsupervised.",
    )

    active = learning_explainer.get_active_misconception(student, course_id, "clustering")
    assert active is not None
    assert active["occurrence_count"] == 2
    assert active["label"] == "Nhầm K-Means với classification"
    assert active["hint"] == "K-Means là unsupervised."


def test_misconception_resolved_no_longer_active():
    student = f"stu_{uuid.uuid4().hex[:8]}"
    course_id = "COURSE_MISC"
    learning_explainer.record_misconception(
        student, course_id, "clustering", "Nhầm K-Means với classification", "trả lời sai", hint="hint"
    )
    learning_explainer.resolve_misconception(
        student, course_id, "clustering", "Nhầm K-Means với classification", "trả lời đúng ở lần sau"
    )
    assert learning_explainer.get_active_misconception(student, course_id, "clustering") is None


def test_no_misconception_returns_none_not_error():
    assert learning_explainer.get_active_misconception("stu_none", "COURSE_MISC", "unknown_topic") is None


# ---------------------------------------------------------------------------
# Mục 4 — Socratic session có trạng thái thật
# ---------------------------------------------------------------------------
def test_socratic_session_progresses_through_multiple_steps(llm_integration, unique_course):
    lesson_id = f"lesson_socratic_{uuid.uuid4().hex[:8]}"
    _ingest(
        llm_integration,
        unique_course,
        lesson_id,
        "k-means",
        "K-Means là thuật toán phân cụm không giám sát, gán điểm vào centroid gần nhất, lặp lại tới khi hội tụ.",
        "Bài Socratic",
    )

    session = learning_explainer.start_socratic_session("k-means")
    assert session.current_step == 0
    assert session.completion_status == "IN_PROGRESS"

    session, result1 = learning_explainer.advance_socratic_session(
        llm_integration,
        session,
        "start",
        unique_course,
        lesson_id,
        "Standard",
    )
    assert len(session.history) == 1
    assert session.completion_status == "IN_PROGRESS"

    session, result2 = learning_explainer.advance_socratic_session(
        llm_integration,
        session,
        "answer",
        unique_course,
        lesson_id,
        "Standard",
        learner_answer="Em nghĩ K-Means là classification có nhãn",
    )
    assert session.current_step == 1
    assert len(session.history) == 2
    assert session.misconception is not None  # phát hiện đúng ngộ nhận K-Means/classification

    session, result3 = learning_explainer.advance_socratic_session(
        llm_integration,
        session,
        "hint",
        unique_course,
        lesson_id,
        "Standard",
    )
    assert session.hint_count == 1

    session, final_result = learning_explainer.advance_socratic_session(
        llm_integration,
        session,
        "show_full_explanation",
        unique_course,
        lesson_id,
        "Standard",
    )
    assert session.completion_status == "COMPLETED"
    assert final_result.has_cms_content is True
