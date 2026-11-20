"""Adaptive Learning & Diagnosis Test Suite for EduDSS.

Validates:
1. Extraction of StudentLearningProfile across academic, question, behavioral, and trajectory dimensions.
2. DiagnosisEngine hypotheses generation across standard educational categories.
3. Structured StudentLearningPlan generation with individualized dosage (not fixed 8h/20 exercises).
4. Verified resource catalog resolution and URL validation.
5. Zero PII leakage in profile features.
"""
import pytest
from dss.services.learning_profile import StudentLearningProfile
from dss.services.diagnosis_engine import DiagnosisEngine, CATEGORY_LOW_PRACTICE, CATEGORY_SLOW_RESPONSE
from dss.services.learning_plan import learning_plan_generator, StudentLearningPlan
from dss.services.resource_catalog import resource_catalog



@pytest.fixture
def approved_cs101_resource(monkeypatch):
    from dss.services.resource_catalog import ResourceItem
    item = ResourceItem(
        resource_id="cs101_python_approved", title="Python practice", type="lms_material",
        provider="Faculty", url="https://school.example.edu/cs101/python",
        course="CS101", topic="Python", level="Beginner", language="vi", duration="",
        verified_at="2026-10-20T00:00:00+00:00", reviewed_by="test_teacher", status="APPROVED",
    )
    monkeypatch.setattr(resource_catalog, "_resources", {item.resource_id: item})
    return item


def test_student_learning_profile_zero_pii():
    """Verify that student name, email, and raw ID are never used as model features."""
    raw_lms_data = {
        "name": "Nguyen Van A",
        "email": "vana@university.edu.vn",
        "student_id": "SV001234",
        "quiz_score": 6.5,
        "assignment_score": 5.0,
        "exam_score": 4.5,
        "active_days": 12,
        "login_freq": 2.5,
        "avg_response_time": 95.0,  # Slow response
        "practice_freq": 0.8,      # Low practice
    }
    
    profile = StudentLearningProfile.build_from_lms_records(
        student_id="SV001234",
        course_id="CS101",
        raw_lms_data=raw_lms_data,
    )
    
    profile_dict = profile.to_dict()
    assert "name" not in profile_dict
    assert "email" not in profile_dict
    assert profile.student_pseudonym != "SV001234"
    assert "SV001234" not in profile.student_pseudonym


def test_diagnosis_engine_standard_categories():
    """Verify that DiagnosisEngine infers structured hypotheses instead of arbitrary guessing."""
    raw_lms_data = {
        "quiz_score": 4.5,
        "assignment_score": 4.0,
        "exam_score": 4.0,
        "active_days": 6,
        "practice_freq": 0.5,       # Triggers LOW_PRACTICE
        "avg_response_time": 105.0,  # Triggers SLOW_RESPONSE (>90s)
        "accuracy_rate": 0.45,
    }
    profile = StudentLearningProfile.build_from_lms_records(
        student_id="SV_DIAG_01",
        course_id="CS101",
        raw_lms_data=raw_lms_data,
    )
    
    engine = DiagnosisEngine()
    diagnoses = engine.diagnose_student(profile)
    
    assert len(diagnoses) > 0
    categories = [hyp.category for d in diagnoses for hyp in d.hypotheses]
    assert CATEGORY_LOW_PRACTICE in categories
    assert CATEGORY_SLOW_RESPONSE in categories
    
    # Check that each diagnosis has concrete evidence and a recommended diagnostic
    for d in diagnoses:
        assert len(d.evidence) > 0
        assert len(d.hypotheses) > 0
        assert d.recommended_diagnostic != ""


def test_learning_plan_individualized_dosage(approved_cs101_resource):
    """Verify that learning plans calculate dosage adaptively rather than using fixed numbers."""
    DiagnosisEngine()
    
    # Student A: mild gap, fast velocity
    profile_a = StudentLearningProfile.build_from_lms_records(
        student_id="SV_A",
        course_id="CS101",
        raw_lms_data={"quiz_score": 7.0, "assignment_score": 6.5, "exam_score": 6.0, "learning_velocity": 1.4, "practice_freq": 2.5, "session_duration": 45, "topic_scores": {"Python": 4}},
    )
    plan_a = learning_plan_generator.generate_plan(profile_a)
    
    # Student B: severe gaps, slow velocity
    profile_b = StudentLearningProfile.build_from_lms_records(
        student_id="SV_B",
        course_id="CS101",
        raw_lms_data={"quiz_score": 3.5, "assignment_score": 3.0, "exam_score": 3.0, "learning_velocity": 0.6, "practice_freq": 0.5, "active_days": 4, "session_duration": 45, "topic_scores": {"Python": 2}},
    )
    plan_b = learning_plan_generator.generate_plan(profile_b)
    
    hours_a = plan_a.success_metrics.get("weekly_study_hours_target", 0)
    hours_b = plan_b.success_metrics.get("weekly_study_hours_target", 0)
    
    # Student B needs significantly more intensive intervention dosage than Student A
    assert hours_b > hours_a, f"Expected hours_b ({hours_b}) > hours_a ({hours_a})"


def test_verified_resource_catalog_item_urls(approved_cs101_resource):
    """Verify that all resources attached to plan activities exist in catalog with valid URLs."""
    profile = StudentLearningProfile.build_from_lms_records(
        student_id="SV_RES",
        course_id="CS101",
        raw_lms_data={"quiz_score": 4.0, "exam_score": 4.0, "topic_scores": {"Python": 3}},
    )
    plan = learning_plan_generator.generate_plan(profile)
    
    assert len(plan.activities) > 0
    for act in plan.activities:
        assert act.approved_resource_ids == [approved_cs101_resource.resource_id]
        for res_id in act.approved_resource_ids:
            res = resource_catalog.get_resource(res_id)
            assert res is not None, f"Resource {res_id} not found in catalog"
            assert res.url.startswith("https://") or res.url.startswith("http://")
            assert res.status == "APPROVED"
