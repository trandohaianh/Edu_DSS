"""Stage 1 evidence correctness: missing inputs, scope, approval and diagnostics."""

from __future__ import annotations

import pytest

from dss.services import learning_plan
from dss.services.diagnosis_engine import (
    CATEGORY_INSUFFICIENT_DATA,
    CATEGORY_KNOWLEDGE_GAP,
    CATEGORY_LOW_PRACTICE,
    CATEGORY_MASTERY_ON_TRACK,
    diagnosis_engine,
)
from dss.services.diagnostic_assessment import (
    AssessmentBlueprint,
    DiagnosticQuestion,
    diagnostic_service,
)
from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_profile import (
    AcademicEvidence,
    BehavioralEvidence,
    LearningTrajectory,
    QuestionLevelEvidence,
    StudentLearningProfile,
)


def profile(raw=None):
    return StudentLearningProfile.build_from_lms_records("SV_STAGE1", "CS101", raw or {})


def categories(value):
    return {hyp.category for item in diagnosis_engine.diagnose_student(value) for hyp in item.hypotheses}


def resource(resource_id="valid", **overrides):
    return {
        "resource_id": resource_id,
        "course": "CS101",
        "topic": "Python",
        "status": "APPROVED",
        "url": "https://school.example.edu/python",
        "is_demo": False,
        **overrides,
    }


@pytest.fixture(autouse=True)
def isolated_catalog(monkeypatch):
    monkeypatch.setattr(learning_plan.resource_catalog, "_resources", {})
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PSEUDONYM_KEY", "ab" * 32)


def test_empty_profile_does_not_fabricate_observations_or_mastery():
    value = profile()
    assert value.academic.quiz_average is None
    assert value.question_level.accuracy_rate is None
    assert value.behavioral.active_days_last_month is None
    assert value.trajectory.delayed_retention_rate is None
    assert value.trajectory.score_trend is None
    assert value.evidence_sources == {}
    assert categories(value) == {CATEGORY_INSUFFICIENT_DATA}
    plan = learning_plan_generator.generate_plan(value)
    assert plan.course_id == "CS101"
    assert plan.evidence_used == []
    assert plan.strengths == []
    assert plan.weaknesses == []
    assert plan.success_metrics == {}
    assert plan.missing_evidence
    assert all(item.duration_minutes is None and item.frequency_per_week is None for item in plan.activities)
    prompt = learning_plan_generator.render_plan_to_prompt(plan)
    assert "None phút" not in prompt
    assert "Chưa đủ dữ liệu" in prompt


@pytest.mark.parametrize("invalid", [-1, 11, float("nan"), float("inf"), -float("inf"), True, "bad", ""])
def test_invalid_scores_are_unknown_and_tracked(invalid):
    value = profile({"quiz_score": invalid})
    assert value.academic.quiz_average is None
    assert "academic.quiz_average" in value.invalid_fields
    assert "academic.quiz_average" not in value.evidence_sources


@pytest.mark.parametrize(
    "field,value",
    [
        ("accuracy_rate", 1.2),
        ("retention_rate", -0.1),
        ("active_days", 32),
        ("active_days", 1.5),
        ("hint_count", 0.5),
        ("video_completion", float("nan")),
        ("session_duration", "invalid"),
    ],
)
def test_invalid_metrics_do_not_break_diagnosis_or_plan(field, value):
    item = profile({field: value})
    assert item.invalid_fields
    assert categories(item) == {CATEGORY_INSUFFICIENT_DATA}
    assert learning_plan_generator.generate_plan(item).success_metrics == {}


def test_valid_zero_is_evidence_not_missing():
    value = profile(
        {
            "quiz_score": 0,
            "assignment_score": 0,
            "exam_score": 0,
            "accuracy_rate": 0,
            "active_days": 0,
            "practice_freq": 0,
            "hint_count": 0,
            "avg_response_time": 0,
            "retention_rate": 0,
        }
    )
    assert value.academic.quiz_average == 0
    assert value.question_level.accuracy_rate == 0
    assert value.question_level.hint_requests_count == 0
    assert value.behavioral.active_days_last_month == 0
    assert CATEGORY_KNOWLEDGE_GAP in categories(value)
    assert CATEGORY_LOW_PRACTICE in categories(value)
    assert CATEGORY_MASTERY_ON_TRACK not in categories(value)
    assert any(entry == "Điểm quiz: 0/10" for entry in learning_plan_generator.generate_plan(value).evidence_used)


def test_semantically_different_legacy_columns_are_not_relabelled():
    value = profile({"diem_chuyen_can": 8, "diem_giua_ky": 7})
    assert value.academic.quiz_average is None
    assert value.academic.assignment_average is None
    assert categories(value) == {CATEGORY_INSUFFICIENT_DATA}


def test_partial_good_observation_cannot_claim_mastery_on_track():
    value = profile({"assignment_score": 9})
    assert categories(value) == {CATEGORY_INSUFFICIENT_DATA}


def test_direct_dataclasses_validate_finite_ranges():
    assert AcademicEvidence(quiz_average=float("nan")).quiz_average is None
    assert QuestionLevelEvidence(accuracy_rate=2).accuracy_rate is None
    assert BehavioralEvidence(active_days_last_month=40).active_days_last_month is None
    assert LearningTrajectory(learning_velocity=0).learning_velocity is None
    assert AcademicEvidence(topic_scores={"bad": "invalid", "zero": 0}).topic_scores == {"zero": 0}


def test_resources_require_exact_course_topic_and_approval():
    supplied = [resource(f"valid-{number}") for number in range(4)] + [
        resource("wrong-course", course="CS101-ADVANCED"),
        resource("wrong-topic", topic="Python Advanced"),
        resource("unapproved", status="PENDING_REVIEW"),
        resource("bad-url", url="javascript:alert(1)"),
    ]
    plan = learning_plan_generator.generate_plan(profile({"topic_scores": {"Python": 3}}), approved_resources=supplied)
    assert plan.activities[0].approved_resource_ids == [f"valid-{number}" for number in range(4)]
    assert plan.activities[0].duration_minutes is None


def test_demo_resources_are_excluded_in_real_mode(monkeypatch):
    monkeypatch.setenv("EDUDSS_MODE", "REAL_LMS")
    supplied = [
        resource("real"),
        resource("demo", is_demo=True),
        resource("res_prog_python_01"),
        resource("synthetic", data_source="synthetic"),
    ]
    plan = learning_plan_generator.generate_plan(profile({"topic_scores": {"Python": 3}}), approved_resources=supplied)
    assert plan.activities[0].approved_resource_ids == ["real"]


def test_verified_cms_without_fake_url_and_only_matching_snapshot():
    cms = resource(
        "cms:lesson:doc",
        url="",
        course_id="CS101",
        topic_id="Python",
        source_kind="cms_lesson",
        verified_cms=True,
        title="Official lesson",
        lesson_id="lesson",
        document_id="doc",
    )
    wrong_duplicate = {**cms, "course_id": "OTHER", "title": "Wrong course title", "document_id": "wrong"}
    plan = learning_plan_generator.generate_plan(
        profile({"topic_scores": {"Python": 3}}),
        approved_resources=[cms, wrong_duplicate, {**cms, "resource_id": "unverified", "verified_cms": False}],
    )
    assert plan.activities[0].approved_resource_ids == ["cms:lesson:doc"]
    assert plan.resource_details == {
        "cms:lesson:doc": {
            "title": "Official lesson",
            "lesson_id": "lesson",
            "document_id": "doc",
        }
    }


def test_no_matching_resource_does_not_invent_schedule():
    plan = learning_plan_generator.generate_plan(
        profile(
            {
                "topic_scores": {"Python": 3},
                "practice_freq": 1,
                "learning_velocity": 0.8,
                "session_duration": 30,
            }
        )
    )
    assert plan.activities[0].approved_resource_ids == []
    assert plan.activities[0].duration_minutes is None
    assert plan.activities[0].frequency_per_week is None
    assert plan.success_metrics == {}


def blueprint(status="APPROVED"):
    question = DiagnosticQuestion(
        question_id="q1",
        topic="Python",
        subskill="loops",
        question_text="Example",
        options=["A", "B"],
        correct_answer_index=0,
        source_document_id="doc",
        explanation="Source-backed example",
    )
    return AssessmentBlueprint("diag1", "Python", "unknown", 1, ["doc"], [question], status)


def test_first_diagnostic_does_not_average_against_fake_prior():
    value = profile()
    result = diagnostic_service.process_student_response(value, blueprint(), [0], [], [])
    assert result["accuracy_score"] == 1
    assert value.question_level.accuracy_rate == 1
    assert value.question_level.average_response_time_seconds is None
    assert value.question_level.hint_requests_count is None
    assert value.evidence_sources["question_level.accuracy_rate"] == "diagnostic:diag1"


def test_diagnostic_zero_time_and_hints_preserved_and_invalid_unknown():
    value = profile()
    result = diagnostic_service.process_student_response(value, blueprint(), [1], [0], [0])
    assert result["accuracy_score"] == 0
    assert result["average_response_time"] == 0
    assert result["hints_used"] == 0
    result = diagnostic_service.process_student_response(value, blueprint(), [0], [float("nan")], [-1])
    assert result["average_response_time"] is None
    assert result["hints_used"] is None


@pytest.mark.parametrize("status,answers", [("DRAFT", [0]), ("APPROVED", []), ("APPROVED", [5])])
def test_unapproved_or_incomplete_diagnostic_does_not_mutate_profile(status, answers):
    value = profile()
    with pytest.raises(ValueError):
        diagnostic_service.process_student_response(value, blueprint(status), answers, [], [])
    assert value.question_level.accuracy_rate is None


def test_finite_extreme_inputs_do_not_overflow_schedule_arithmetic():
    value = profile(
        {
            "topic_scores": {"Python": 3},
            "practice_freq": 1e308,
            "session_duration": 1e308,
            "learning_velocity": 0.4,
        }
    )
    plan = learning_plan_generator.generate_plan(value, approved_resources=[resource()])
    assert plan.activities[0].duration_minutes == 75
    assert plan.activities[0].frequency_per_week == 5


def test_malformed_resource_id_cannot_break_snapshot_filter():
    malformed = resource(["not", "an", "identifier"])
    plan = learning_plan_generator.generate_plan(
        profile({"topic_scores": {"Python": 3}}),
        approved_resources=[malformed],
    )
    assert plan.activities[0].approved_resource_ids == []
    assert plan.resource_details == {}


def test_absent_diagnostic_telemetry_container_is_unknown():
    value = profile()
    result = diagnostic_service.process_student_response(value, blueprint(), [0], None, None)
    assert result["average_response_time"] is None
    assert result["hints_used"] is None
