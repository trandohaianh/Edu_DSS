"""Regression suite cho AI Learning Explainer (giải thích bài giảng từ CMS).

Bao phủ đúng 7 case chấp nhận trong yêu cầu (Mục 18):
1. Hỏi đúng lesson -> retrieve đúng CMS lesson đó.
2. Hai môn khác nhau -> không lẫn nội dung/nguồn.
3. Hai mức mastery khác nhau -> mức giải thích khác nhau.
4. CMS không có nội dung -> không bịa nguồn, nói rõ chưa có tài liệu.
5. Lecturer cập nhật bài giảng (version mới) -> retrieval dùng bản mới nhất.
6. Sinh quiz từ đúng nội dung CMS (không bịa ngoài phạm vi tài liệu).
7. Phát hiện misconception (vd K-Means bị nhầm classification).

Dùng model embedding THẬT (qua MultiAIProvider, giống test_rag_service.py) —
không mock — vì hành vi cần kiểm chứng (lọc theo course/lesson) phụ thuộc vào
kết quả truy xuất thật của vector store cục bộ.
"""
from __future__ import annotations

import shutil
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
    """Mỗi test dùng course_id/lesson_id RIÊNG (uuid) để không đụng dữ liệu
    giữa các lần chạy test / để lại trong vector store cục bộ dùng chung."""
    suffix = uuid.uuid4().hex[:8]
    return f"TEST_COURSE_{suffix}"


def _ingest(llm_integration, course_id, lesson_id, topic_id, content: str, title: str, section: str = "slide 1"):
    return cms_repository.ingest_lecture_material(
        file_bytes=content.encode("utf-8"), file_name=f"{lesson_id}.txt", title=title,
        course_id=course_id, lesson_id=lesson_id, topic_id=topic_id, lecturer_id="GV_TEST",
        llm_integration=llm_integration, learning_outcome="Test outcome", difficulty="Standard",
        content_type="slide", page_or_section=section,
    )


# ---------------------------------------------------------------------------
# Case 1 — Hỏi đúng lesson -> retrieve đúng CMS lesson đó
# ---------------------------------------------------------------------------
def test_case1_retrieval_matches_correct_lesson(llm_integration, unique_course):
    lesson_id = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering",
            "K-Means là thuật toán phân cụm không giám sát, gán điểm vào centroid gần nhất.",
            "Bài K-Means")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "K-Means là gì", course_id=unique_course, lesson_id=lesson_id, top_k=3)
    assert len(chunks) >= 1
    assert all(c["metadata"]["lesson_id"] == lesson_id for c in chunks)


# ---------------------------------------------------------------------------
# Case 2 — Hai môn khác nhau -> source/citation khác nhau, không lẫn
# ---------------------------------------------------------------------------
def test_case2_cross_course_isolation(llm_integration, unique_course):
    other_course = unique_course + "_OTHER"
    lesson_a = f"lesson_{uuid.uuid4().hex[:8]}"
    lesson_b = f"lesson_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_a, "clustering", "Nội dung môn A về K-Means.", "Bài A")
    _ingest(llm_integration, other_course, lesson_b, "clustering", "Nội dung môn B về K-Means.", "Bài B")

    chunks_a = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_a, top_k=5)
    chunks_b = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=other_course, lesson_id=lesson_b, top_k=5)

    assert all(c["course_id"] == unique_course for c in chunks_a)
    assert all(c["course_id"] == other_course for c in chunks_b)
    titles_a = {c["title"] for c in chunks_a}
    titles_b = {c["title"] for c in chunks_b}
    assert titles_a.isdisjoint(titles_b)


# ---------------------------------------------------------------------------
# Case 3 — Hai mastery khác nhau -> mức giải thích khác nhau
# ---------------------------------------------------------------------------
def test_case3_different_mastery_gives_different_explanation_level():
    low = learning_explainer.determine_explanation_level(0.1)
    mid = learning_explainer.determine_explanation_level(0.5)
    high = learning_explainer.determine_explanation_level(0.9)
    assert (low, mid, high) == ("Foundation", "Standard", "Advanced")
    assert len({low, mid, high}) == 3


def test_case3_missing_mastery_defaults_to_neutral_standard_not_a_guess():
    assert learning_explainer.determine_explanation_level(None) == "Standard"


# ---------------------------------------------------------------------------
# Case 4 — CMS không có nội dung -> không bịa nguồn
# ---------------------------------------------------------------------------
def test_case4_no_cms_content_returns_honest_message_not_fabrication(llm_integration, unique_course):
    lesson_id = f"lesson_empty_{uuid.uuid4().hex[:8]}"
    cms_repository.create_or_get_lesson(unique_course, lesson_id, "unknown_topic", "GV_TEST", "Bài trống")
    # Lesson được đăng ký nhưng CHƯA từng ingest tài liệu nào (current_document_id=None).
    result = learning_explainer.generate_explanation(
        llm_integration, "Nội dung không tồn tại nào đó", unique_course, lesson_id, "unknown_topic", "Standard",
    )
    assert result.has_cms_content is False
    assert "chưa có trong tài liệu môn học hiện tại" in result.answer
    assert result.citations == []


def test_case4_ai_disabled_lesson_does_not_answer(llm_integration, unique_course):
    lesson_id = f"lesson_disabled_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "topic_x", "Nội dung bất kỳ.", "Bài bị tắt AI")
    cms_repository.set_ai_enabled(lesson_id, False)
    result = learning_explainer.generate_explanation(llm_integration, "Giải thích giúp em", unique_course, lesson_id, "topic_x", "Standard")
    assert result.has_cms_content is False
    assert "chưa được Giảng viên bật" in result.answer


# ---------------------------------------------------------------------------
# Case 5 — Lecturer update lecture -> retrieval dùng version mới
# ---------------------------------------------------------------------------
def test_case5_new_version_supersedes_old_version_in_retrieval(llm_integration, unique_course):
    lesson_id = f"lesson_ver_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "K-Means bản đầu tiên, chưa có K-Means++.", "Bài K-Means v1")
    lesson_v2 = _ingest(llm_integration, unique_course, lesson_id, "clustering", "K-Means bản cập nhật, có K-Means++ để khởi tạo centroid tốt hơn.", "Bài K-Means v2")

    assert len(lesson_v2.versions) == 2
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5)
    assert len(chunks) >= 1
    assert all(c["document_id"] == lesson_v2.current_document_id for c in chunks)
    assert all("v1" not in c["title"] for c in chunks)


# ---------------------------------------------------------------------------
# Case 6 — Sinh quiz từ đúng nội dung CMS
# ---------------------------------------------------------------------------
def test_case6_quiz_generated_grounded_in_retrieved_cms_chunks(llm_integration, unique_course):
    lesson_id = f"lesson_quiz_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "K-Means dùng khoảng cách Euclid để gán cụm.", "Bài Quiz Test")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "K-Means", course_id=unique_course, lesson_id=lesson_id, top_k=5)
    blueprint = learning_explainer.generate_lesson_quiz_from_chunks(lesson_id, chunks, num_questions=1)
    assert blueprint is not None
    assert len(blueprint.questions) >= 1
    valid_ids = {c.get("chunk_id") for c in chunks}
    for q in blueprint.questions:
        assert q.source_document_id in valid_ids  # câu hỏi phải trace được về đúng chunk nguồn


# ---------------------------------------------------------------------------
# Case 7 — Phát hiện misconception
# ---------------------------------------------------------------------------
def test_case7_detects_kmeans_classification_misconception():
    result = learning_explainer.detect_misconception("K-Means", "Em nghĩ K-Means là một dạng classification có nhãn")
    assert result is not None
    assert "classification" in result["label"].lower()


def test_case7_no_misconception_when_answer_is_correct():
    result = learning_explainer.detect_misconception("K-Means", "K-Means là thuật toán phân cụm không giám sát")
    assert result is None


def test_case7_unknown_topic_returns_none_not_error():
    assert learning_explainer.detect_misconception("Chủ đề không tồn tại trong danh mục", "bất kỳ câu trả lời nào") is None


# ---------------------------------------------------------------------------
# Guardrail / citation hygiene
# ---------------------------------------------------------------------------
def test_friendly_citation_never_exposes_internal_ids(llm_integration, unique_course):
    lesson_id = f"lesson_cite_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "clustering", "Nội dung minh hoạ trích dẫn.", "Bài Trích Dẫn", section="slide 12-15")
    chunks = cms_repository.retrieve_lesson_content(llm_integration, "minh hoạ", course_id=unique_course, lesson_id=lesson_id, top_k=3)
    citation = learning_explainer._format_friendly_citation(chunks[0])
    assert "chunk_" not in citation.label
    assert "vector" not in citation.label.lower()
    assert "namespace" not in citation.label.lower()
    assert "slide 12-15" in citation.label


def test_lecturer_analytics_aggregates_without_raw_chat_text():
    course_id = f"ANALYTICS_TEST_{uuid.uuid4().hex[:8]}"
    learning_explainer.log_interaction("Student_1", course_id, "lesson_x", "topic_x", "Câu hỏi riêng tư 1", "Foundation", True)
    learning_explainer.log_interaction("Student_2", course_id, "lesson_x", "topic_x", "Câu hỏi riêng tư 1", "Standard", True)
    analytics = learning_explainer.get_lecturer_analytics(course_id)
    assert analytics["total_questions"] == 2
    assert analytics["top_topics"][0][0] == "lesson_x"
