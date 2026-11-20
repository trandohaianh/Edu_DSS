"""Consumers tolerate missing observations and respect the declared score scales."""
import pytest

from dss.services.learning_profile import AcademicEvidence, StudentLearningProfile
from dss.services import learning_explainer
from dss.services.report_service import build_demo_study_plan


@pytest.mark.parametrize("velocity", [None, float("nan"), "invalid", 0])
def test_demo_plan_does_not_crash_or_invent_dosage_for_missing_velocity(velocity):
    text, weeks = build_demo_study_plan(
        "SV1", 5.0, ["Python"],
        {"learning_profile": {"trajectory": {"learning_velocity": velocity}}},
    )
    assert weeks
    assert "Chưa đủ dữ liệu" in text
    assert "None" not in text
    assert "nan" not in text


def test_topic_score_of_one_is_one_out_of_ten():
    profile = StudentLearningProfile(
        "pseudo", "CS101", academic=AcademicEvidence(topic_scores={"loops": 1.0}),
    )
    result = learning_explainer.resolve_explanation_level("SV1", "CS101", "lesson", "loops", learning_profile=profile)
    assert result.source == "topic_mastery"
    assert result.level == "Foundation"


def test_invalid_mutated_subskill_falls_back_to_valid_topic():
    profile = StudentLearningProfile(
        "pseudo", "CS101", academic=AcademicEvidence(topic_scores={"loops": 8.0}),
    )
    profile.question_level.subskill_mastery["loops"] = float("nan")
    result = learning_explainer.resolve_explanation_level("SV1", "CS101", "lesson", "loops", learning_profile=profile)
    assert result.source == "topic_mastery"
    assert result.level == "Advanced"

def test_multiple_topics_do_not_multiply_a_weekly_budget():
    from dss.services.learning_plan import learning_plan_generator
    from dss.services.learning_profile import BehavioralEvidence, LearningTrajectory
    profile = StudentLearningProfile(
        "pseudo", "CS101",
        academic=AcademicEvidence(topic_scores={"loops": 3, "functions": 4}),
        behavioral=BehavioralEvidence(average_session_duration_minutes=45, practice_frequency_per_week=3),
        trajectory=LearningTrajectory(learning_velocity=1),
    )
    resources = [
        {"resource_id": topic, "course_id": "CS101", "topic_id": topic,
         "status": "APPROVED", "url": "https://school.example.edu/" + topic}
        for topic in ("loops", "functions")
    ]
    plan = learning_plan_generator.generate_plan(profile, approved_resources=resources)
    assert all(activity.frequency_per_week is None for activity in plan.activities)
    assert "weekly_study_hours_target" not in plan.success_metrics

def test_csv_json_topic_measurements_preserve_valid_zero_and_sources():
    profile = StudentLearningProfile.build_from_lms_records(
        "SV1", "CS101", {"topic_scores": '{"loops": 0, "functions": 7.5}'},
    )
    assert profile.academic.topic_scores == {"loops": 0, "functions": 7.5}
    assert profile.evidence_sources["topic_scores"] == "topic_scores"
    assert "topic_scores" not in profile.invalid_fields


def test_invalid_csv_json_is_unknown_not_executable():
    profile = StudentLearningProfile.build_from_lms_records(
        "SV1", "CS101", {"topic_scores": "__import__('os').getcwd()"},
    )
    assert profile.academic.topic_scores == {}
    assert "topic_scores" in profile.invalid_fields
