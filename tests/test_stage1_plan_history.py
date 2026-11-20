"""Durability, authorization and isolation of the pilot plan store."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from dss.services import auth_service, learning_plan_history as history
from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_profile import StudentLearningProfile


@pytest.fixture
def history_context(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "local")
    actor = {"username": "sv1", "role": "Sinh viên", "student_id": "SV1"}
    monkeypatch.setattr(auth_service, "current_user", lambda: actor)
    return actor


def _plan(course="CS101"):
    return learning_plan_generator.generate_plan(
        StudentLearningProfile.build_from_lms_records(
            "SV1", course, {"quiz_score": 5, "assignment_score": 4},
        )
    )


def test_history_reopens_versions_and_idempotent_progress(history_context):
    first = _plan()
    saved = history.save_learning_plan("SV1", first)
    assert saved["plan"]["version"] == 1
    assert history.save_learning_plan("SV1", first) == saved
    second = history.save_learning_plan("SV1", _plan())
    assert second["plan"]["version"] == 2
    # Every operation opens a fresh connection; no session cache can satisfy this.
    records = history.list_learning_plans("SV1", course_id="CS101")
    assert len(records) == 2
    assert records[0]["plan"]["version"] == 2
    if records[0]["plan"]["activities"]:
        history.set_activity_completed("SV1", second["plan"]["plan_id"], 0, True)
        assert history.list_learning_plans("SV1")[0]["completion"]["0"] is True
        history.save_learning_plan("SV1", _plan())
        assert history.list_learning_plans("SV1")[0]["completion"] == {}


def test_history_versions_are_independent_per_course_and_school(history_context, monkeypatch):
    history.save_learning_plan("SV1", _plan("CS101"))
    history.save_learning_plan("SV1", _plan("DB201"))
    assert history.list_learning_plans("SV1", "DB201")[0]["plan"]["version"] == 1
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "2")
    assert history.list_learning_plans("SV1") == []
    assert history.save_learning_plan("SV1", _plan())["plan"]["version"] == 1
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    assert len(history.list_learning_plans("SV1")) == 2


def test_history_rejects_other_students_and_unscoped_roles(history_context):
    with pytest.raises(PermissionError):
        history.list_learning_plans("SV2")
    history_context["role"] = "Platform Admin"
    with pytest.raises(PermissionError):
        history.list_learning_plans("SV1")
    history_context["role"] = "Giảng viên / CVHT"
    with pytest.raises(PermissionError):
        history.save_learning_plan("SV1", _plan())


def test_history_requires_matching_owner_and_immutable_plan(history_context):
    plan = _plan()
    with pytest.raises(PermissionError):
        history.save_learning_plan("SV1", replace(plan, student_pseudonym="another-owner"))
    history.save_learning_plan("SV1", plan)
    with pytest.raises(ValueError, match="new version"):
        history.save_learning_plan("SV1", replace(plan, assessment_plan="changed"))


def test_history_filters_course_before_limit(history_context):
    history.save_learning_plan("SV1", _plan("CS101"))
    for _ in range(3):
        history.save_learning_plan("SV1", _plan("DB201"))
    assert history.list_learning_plans("SV1", "CS101", limit=1)[0]["plan"]["course_id"] == "CS101"


def test_concurrent_plan_saves_assign_unique_versions(history_context):
    plans = [_plan() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda plan: history.save_learning_plan("SV1", plan), plans))
    assert sorted(row["plan"]["version"] for row in results) == list(range(1, 9))
    assert len(history.list_learning_plans("SV1")) == 8


def test_duplicate_request_is_idempotent_under_concurrency(history_context):
    plan = _plan()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: history.save_learning_plan("SV1", plan), range(8)))
    assert {row["plan"]["version"] for row in results} == {1}
    assert len(history.list_learning_plans("SV1")) == 1


def test_production_does_not_fallback_to_local(history_context, monkeypatch):
    monkeypatch.setenv("EDUDSS_ENV", "production")
    with pytest.raises(RuntimeError, match="postgres"):
        history.list_learning_plans("SV1")
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "postgres")
    monkeypatch.delenv("EDUDSS_ORGANIZATION_ID")
    with pytest.raises(RuntimeError, match="ORGANIZATION"):
        history.list_learning_plans("SV1")


def test_bad_progress_and_missing_course_are_rejected(history_context):
    with pytest.raises(ValueError):
        history.save_learning_plan("SV1", replace(_plan(), course_id=""))
    saved = history.save_learning_plan("SV1", _plan())
    with pytest.raises(ValueError):
        history.set_activity_completed("SV1", saved["plan"]["plan_id"], -1, True)
    with pytest.raises(LookupError):
        history.set_activity_completed("SV1", "unknown", 0, True)

def test_case_distinct_student_codes_do_not_share_local_history(history_context):
    upper = history.save_learning_plan("SV1", _plan())
    history_context["student_id"] = "sv1"
    assert history.list_learning_plans("sv1") == []
    lower_profile = StudentLearningProfile.build_from_lms_records("sv1", "CS101", {"quiz_score": 4})
    lower = history.save_learning_plan("sv1", learning_plan_generator.generate_plan(lower_profile))
    assert lower["plan"]["version"] == 1
    assert history.list_learning_plans("sv1")[0]["plan"]["plan_id"] == lower["plan"]["plan_id"]
    history_context["student_id"] = "SV1"
    assert history.list_learning_plans("SV1")[0]["plan"]["plan_id"] == upper["plan"]["plan_id"]
