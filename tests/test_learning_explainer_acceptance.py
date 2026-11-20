"""14 test chấp nhận cuối cùng cho AI Learning Explainer bản production-hoá
(Mục 14 của yêu cầu). Đánh số ĐÚNG theo thứ tự liệt kê trong yêu cầu — một số
khía cạnh đã có test chi tiết hơn ở các file khác (test_learning_explainer.py,
test_learning_explainer_policy.py, test_resolve_explanation_level.py,
test_learning_explainer_workflows.py); file này là điểm quy chiếu DUY NHẤT liệt
kê đủ 14 mục, tái dùng service layer, KHÔNG viết lại logic.
"""
from __future__ import annotations

import uuid

import pytest

import dss.config as dss_config
from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer
from dss.services.learning_profile import QuestionLevelEvidence, StudentLearningProfile


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


def _ingest(llm_integration, course_id, lesson_id, topic_id, content, title):
    return cms_repository.ingest_lecture_material(
        file_bytes=content.encode("utf-8"), file_name=f"{lesson_id}.txt", title=title,
        course_id=course_id, lesson_id=lesson_id, topic_id=topic_id, lecturer_id="GV_TEST",
        llm_integration=llm_integration, learning_outcome="Test outcome", difficulty="Standard",
    )


# 1. Mastery thấp -> Foundation; mastery cao -> Advanced
def test_01_low_and_high_mastery_give_different_levels():
    profile_low = StudentLearningProfile(student_pseudonym="p1", course_id="C", question_level=QuestionLevelEvidence(subskill_mastery={"t": 0.15}))
    profile_high = StudentLearningProfile(student_pseudonym="p2", course_id="C", question_level=QuestionLevelEvidence(subskill_mastery={"t": 0.92}))
    low = learning_explainer.resolve_explanation_level("s1", "C", "l1", "t", learning_profile=profile_low)
    high = learning_explainer.resolve_explanation_level("s2", "C", "l1", "t", learning_profile=profile_high)
    assert low.level == "Foundation"
    assert high.level == "Advanced"


# 2. CMS_ONLY từ chối nội dung không được hỗ trợ (không có trong CMS)
def test_02_cms_only_rejects_unsupported_content(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    cms_repository.create_or_get_lesson(unique_course, lesson_id, "topic_x", "GV_TEST", "Bài trống")
    result = learning_explainer.generate_explanation(
        llm_integration, "Một câu hỏi hoàn toàn ngoài phạm vi", unique_course, lesson_id, "topic_x", "Standard",
        mode=learning_explainer.CMS_ONLY,
    )
    assert result.has_cms_content is False
    assert "chưa có trong tài liệu môn học hiện tại" in result.answer


# 3. Trả lời bổ sung chỉ xuất hiện SAU khi người dùng chủ động chọn (opt-in) —
# mặc định CMS_ONLY không tự ý trộn kiến thức ngoài phạm vi.
def test_03_supplementary_mode_is_opt_in_not_default():
    prompt_cms_only = learning_explainer.build_system_prompt("Standard", False, [], [], mode=learning_explainer.CMS_ONLY)
    prompt_supplementary = learning_explainer.build_system_prompt("Standard", False, [], [], mode=learning_explainer.CMS_PLUS_SUPPLEMENTARY)
    assert "KHÔNG" in prompt_cms_only or "không được" in prompt_cms_only.lower() or "chỉ trả lời" in prompt_cms_only.lower()
    assert prompt_cms_only != prompt_supplementary


# 4. Socratic không tiết lộ đáp án ngay (trừ bước tổng hợp cuối)
def test_04_socratic_does_not_leak_answer_immediately():
    from dss.services import learning_explainer_policy as policy
    leaked = "Đáp án là X."
    result = policy.validate_socratic_no_immediate_answer(leaked, is_final_synthesis_step=False)
    assert not result.is_valid
    result_final = policy.validate_socratic_no_immediate_answer(leaked, is_final_synthesis_step=True)
    assert result_final.is_valid


# 5. Misconception tồn tại lâu dài và làm thay đổi giải thích SAU đó
def test_05_misconception_persists_and_changes_next_explanation_prompt():
    student = f"stu_{uuid.uuid4().hex[:8]}"
    learning_explainer.record_misconception(student, "COURSE_ACC", "topic_k", "Nhầm K-Means với classification", "evidence", hint="K-Means là unsupervised.")
    active = learning_explainer.get_active_misconception(student, "COURSE_ACC", "topic_k")
    assert active is not None
    prompt_with = learning_explainer.build_system_prompt("Standard", False, [], [], active_misconception=active)
    prompt_without = learning_explainer.build_system_prompt("Standard", False, [], [], active_misconception=None)
    assert prompt_with != prompt_without
    assert "K-Means là unsupervised." in prompt_with


# 6. Giảng viên duyệt quiz -> Sinh viên nhận được
def test_06_lecturer_approves_quiz_then_student_receives(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "K-Means dùng khoảng cách Euclid.", "Bài Accept06")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5)
    learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    pending = learning_explainer.list_pending_quizzes(unique_course)
    target = next(p for p in pending if p["lesson_id"] == lesson_id)
    learning_explainer.review_quiz(target["queue_id"], "APPROVE", reviewer_id="GV_TEST")
    blueprint, message = learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    assert blueprint is not None and blueprint.status == "APPROVED"


# 7. Quiz bị từ chối KHÔNG BAO GIỜ tới Sinh viên
def test_07_rejected_quiz_never_reaches_student(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "K-Means dùng khoảng cách Euclid.", "Bài Reject07")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5)
    learning_explainer.request_lesson_quiz(unique_course, lesson_id, chunks, num_questions=1)
    pending = learning_explainer.list_pending_quizzes(unique_course)
    target = next(p for p in pending if p["lesson_id"] == lesson_id)
    learning_explainer.review_quiz(target["queue_id"], "REJECT", reviewer_id="GV_TEST")
    assert learning_explainer.get_latest_approved_quiz(lesson_id) is None


# 8. Retrieval CHỈ dùng phiên bản hiện tại (current-version-only)
def test_08_retrieval_uses_current_version_only(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "Bản v1 nội dung cũ.", "Bài v1 test08")
    v2 = _ingest(llm_integration, unique_course, lesson_id, "clustering", "Bản v2 nội dung mới cập nhật.", "Bài v2 test08")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "nội dung", course_id=unique_course, lesson_id=lesson_id, top_k=5)
    assert all(c["document_id"] == v2.current_document_id for c in chunks)


# 9. Truy xuất chéo môn học bị chặn
def test_09_cross_course_retrieval_blocked(llm_integration, unique_course):
    other_course = unique_course + "_OTHER"
    lesson_a = f"lesson_{uuid.uuid4().hex[:8]}"
    lesson_b = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_a, "t", "Nội dung riêng của môn A.", "Bài A test09")
    _ingest(llm_integration, other_course, lesson_b, "t", "Nội dung riêng của môn B.", "Bài B test09")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "Nội dung riêng", course_id=unique_course, lesson_id=lesson_a, top_k=5)
    assert all(c["course_id"] == unique_course for c in chunks)


# 10. Tương tác cập nhật learning profile / độ khó cá nhân hoá kỳ sau (vòng phản hồi)
def test_10_interaction_updates_future_explanation_level():
    student_id = f"real_student_{uuid.uuid4().hex[:8]}"
    from dss.services.privacy_service import generate_pseudonym
    pseudonym = generate_pseudonym(student_id)
    topic_id = f"topic_{uuid.uuid4().hex[:8]}"
    course_id = "COURSE_FEEDBACK"
    for _ in range(4):
        learning_explainer.log_interaction(pseudonym, course_id, "lessonX", topic_id, "câu hỏi", "Standard", True, quiz_correct=True)
    result = learning_explainer.resolve_explanation_level(student_id, course_id, "lessonX", topic_id, learning_profile=None, df=None)
    assert result.source == "quiz_history"
    assert result.level == "Advanced"  # 4/4 đúng -> mastery 1.0 -> Advanced


# 11. Lecturer analytics tổng hợp đúng
def test_11_lecturer_analytics_aggregates_correctly():
    course_id = f"ANALYTICS_{uuid.uuid4().hex[:8]}"
    learning_explainer.log_interaction("Student_A", course_id, "lessonY", "topicY", "câu hỏi 1", "Foundation", True)
    learning_explainer.log_interaction("Student_B", course_id, "lessonY", "topicY", "câu hỏi 2", "Standard", True)
    learning_explainer.log_interaction("Student_C", course_id, "lessonZ", "topicZ", "câu hỏi 3", "Advanced", False)
    analytics = learning_explainer.get_lecturer_analytics(course_id)
    assert analytics["total_questions"] == 3
    assert dict(analytics["top_topics"])["lessonY"] == 2
    assert analytics["no_cms_rate"] == round(1 / 3, 3)


# 12. Trích dẫn thân thiện, có căn cứ nguồn, không lộ id nội bộ
def test_12_citation_friendly_and_source_backed(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "t", "Nội dung minh hoạ trích dẫn test12.", "Bài Citation test12")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "minh hoạ", course_id=unique_course, lesson_id=lesson_id, top_k=3)
    citation = learning_explainer._format_friendly_citation(chunks[0])
    assert "chunk_" not in citation.label and "vector" not in citation.label.lower()
    assert lesson_id not in citation.label or "Bài Citation test12" in citation.label


# 13. Nội dung chat riêng tư KHÔNG bị lộ trong analytics tổng hợp
def test_13_private_chat_text_not_exposed_in_aggregated_analytics():
    course_id = f"PRIVACY_{uuid.uuid4().hex[:8]}"
    secret_question = "Đây là câu hỏi RIÊNG TƯ chứa thông tin cá nhân XYZ123"
    learning_explainer.log_interaction("Student_Secret", course_id, "lessonP", "topicP", secret_question, "Standard", True)
    analytics = learning_explainer.get_lecturer_analytics(course_id)
    assert "XYZ123" not in str(analytics["top_topics"])
    assert "XYZ123" not in str(analytics["misconceptions"])
    assert "Student_Secret" not in str(analytics)


# 14. Rò rỉ hồ sơ chéo sinh viên bị ngăn chặn (misconception/level của SV này
# không ảnh hưởng SV khác dù cùng course/topic)
def test_14_cross_student_profile_leakage_prevented():
    course_id = "COURSE_LEAK_TEST"
    topic_id = "topic_leak"
    student_a = f"real_a_{uuid.uuid4().hex[:8]}"
    student_b = f"real_b_{uuid.uuid4().hex[:8]}"
    from dss.services.privacy_service import generate_pseudonym
    pseudonym_a = generate_pseudonym(student_a)
    learning_explainer.record_misconception(pseudonym_a, course_id, topic_id, "Ngộ nhận riêng của A", "evidence A", hint="hint A")

    active_for_a = learning_explainer.get_active_misconception(pseudonym_a, course_id, topic_id)
    active_for_b = learning_explainer.get_active_misconception(generate_pseudonym(student_b), course_id, topic_id)
    assert active_for_a is not None
    assert active_for_b is None  # Sinh viên B không thấy ngộ nhận của Sinh viên A
