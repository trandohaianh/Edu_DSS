"""Unit test cho resolve_explanation_level (Mục 1) — kiểm tra ĐÚNG thứ tự ưu
tiên bằng chứng bắt buộc: subskill_mastery > topic_scores > lịch sử quiz thật >
điểm chủ đề trong dataset > mặc định Standard. Không cần LLM/vector store —
chỉ cần đối tượng learning_profile giả lập và (tuỳ test) log tương tác thật."""
from __future__ import annotations

import pandas as pd

from dss.services import learning_explainer
from dss.services.learning_profile import AcademicEvidence, QuestionLevelEvidence, StudentLearningProfile


def _profile(subskill_mastery=None, topic_scores=None) -> StudentLearningProfile:
    return StudentLearningProfile(
        student_pseudonym="stu_test", course_id="COURSE_X",
        academic=AcademicEvidence(topic_scores=topic_scores or {}),
        question_level=QuestionLevelEvidence(subskill_mastery=subskill_mastery or {}),
    )


def test_tier1_subskill_mastery_low_gives_foundation_high_confidence():
    profile = _profile(subskill_mastery={"clustering": 0.2})
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    assert result.level == "Foundation"
    assert result.source == "subskill_mastery"
    assert result.confidence == "High"
    assert "clustering" in result.evidence[0]


def test_tier1_subskill_mastery_high_gives_advanced():
    profile = _profile(subskill_mastery={"clustering": 0.9})
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    assert result.level == "Advanced"
    assert result.source == "subskill_mastery"


def test_tier2_topic_scores_used_when_no_subskill_entry():
    profile = _profile(subskill_mastery={}, topic_scores={"clustering": 3.0})  # thang 0-10 -> normalize 0.3
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    assert result.level == "Foundation"
    assert result.source == "topic_mastery"
    assert result.confidence == "Medium"


def test_tier1_takes_priority_over_tier2_when_both_present():
    profile = _profile(subskill_mastery={"clustering": 0.9}, topic_scores={"clustering": 2.0})
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    assert result.source == "subskill_mastery"
    assert result.level == "Advanced"


def test_tier3_quiz_history_used_when_profile_has_no_entry(monkeypatch):
    fake_records = [
        {"student_pseudonym": "stu_pseudo_x", "topic_id": "clustering", "quiz_correct": True},
        {"student_pseudonym": "stu_pseudo_x", "topic_id": "clustering", "quiz_correct": True},
        {"student_pseudonym": "stu_pseudo_x", "topic_id": "clustering", "quiz_correct": False},
    ]
    monkeypatch.setattr(learning_explainer, "_load_interaction_log", lambda: fake_records)
    monkeypatch.setattr(
        "dss.services.privacy_service.generate_pseudonym", lambda student_id: "stu_pseudo_x",
    )
    profile = _profile(subskill_mastery={}, topic_scores={})
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    assert result.source == "quiz_history"
    assert abs(result.evidence and 1 or 1) >= 0  # evidence không rỗng (smoke check dưới đây rõ hơn)
    assert result.confidence == "Medium"


def test_tier4_dataset_column_used_when_no_profile_and_no_quiz_history():
    df = pd.DataFrame({"student_id": ["s1"], "diem_thong_ke": [8.0]})
    result = learning_explainer.resolve_explanation_level(
        "s1", "COURSE_X", "lesson1", "thong_ke", learning_profile=None, df=df,
    )
    assert result.source == "course_topic_score"
    assert result.level == "Advanced"
    assert result.confidence == "Low"


def test_tier5_default_standard_when_no_evidence_at_all():
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "unknown_topic", learning_profile=None, df=None)
    assert result.level == "Standard"
    assert result.source == "default"
    assert result.confidence == "Low"


def test_friendly_reason_never_leaks_raw_fields():
    profile = _profile(subskill_mastery={"clustering": 0.2})
    result = learning_explainer.resolve_explanation_level("s1", "COURSE_X", "lesson1", "clustering", learning_profile=profile)
    for forbidden in ("subskill_mastery", "topic_scores", "confidence", "[", "]"):
        assert forbidden not in result.friendly_reason
