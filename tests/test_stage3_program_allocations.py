"""Programme roles, budget races and aggregate reporting boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import pytest

from dss.platform.context import Actor
from dss.platform import store
from dss.platform.models import SchoolSummarySnapshot
from dss.services import classroom_service as classes
from dss.services import program_allocation_service as programs

OPS = Actor("100", "ops", "Platform Admin")
MANAGER = Actor("100", "manager", "Admin")
ANALYST = Actor("100", "analyst", "Admin")
SCHOOL = Actor("1", "school-admin", "Admin")


@pytest.fixture
def program(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    store.reset_platform_engines()
    for scope in ("100", "1", "2"):
        programs.register_school(OPS, scope, "School " + scope)
    program = programs.create_program(OPS, "PILOT", "Pilot", 10, 100)
    for actor, role in ((MANAGER, "manager"), (ANALYST, "analyst")):
        programs.grant_program_member(OPS, program["id"], actor.school_id, actor.username, role)
    yield program
    store.reset_platform_engines()


def test_no_implicit_authority_and_membership_is_school_scoped(program):
    for actor in (OPS, ANALYST, Actor("2", MANAGER.username, "Admin")):
        with pytest.raises(PermissionError):
            programs.allocate_school(actor, program["id"], "1", 5)
    with pytest.raises(PermissionError):
        programs.list_program_reports(OPS, program["id"])
    assert programs.list_programs(OPS)[0]["program_role"] is None
    programs.revoke_program_member(OPS, program["id"], "100", MANAGER.username)
    assert programs.list_programs(MANAGER) == []


@pytest.mark.parametrize("bad", [-1, True, False, 1.5, "3", None, 2**31])
def test_invalid_capacity_values_fail_before_mutation(program, bad):
    with pytest.raises(ValueError):
        programs.allocate_school(MANAGER, program["id"], "1", bad)
    with pytest.raises(ValueError):
        programs.create_program(OPS, "INVALID", "Invalid", bad)


def test_budget_reservations_serialize_and_ai_budget_is_enforced(program):
    def allocate(scope):
        try:
            programs.allocate_school(MANAGER, program["id"], scope, 6, 60)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(allocate, ["1", "2"])) == [False, True]
    allocations = programs.list_allocations(MANAGER, program["id"])
    assert len(allocations) == 1
    other = "1" if allocations[0]["school_id"] == "2" else "2"
    with pytest.raises(ValueError):
        programs.allocate_school(MANAGER, program["id"], other, 1, 41)
    with pytest.raises(ValueError):
        programs.set_program_budget(OPS, program["id"], 5, 100)


def test_allocation_cannot_shrink_below_actual_distinct_usage(program):
    classroom = classes.create_class(SCHOOL, "A", "LAW101", "Law", "2026")
    classes.import_enrollments(SCHOOL, classroom["id"], ["PRIVATE1", "PRIVATE2", "PRIVATE3"])
    programs.allocate_school(MANAGER, program["id"], "1", 5)
    with pytest.raises(ValueError):
        programs.allocate_school(MANAGER, program["id"], "1", 2)
    assert programs.list_allocations(MANAGER, program["id"])[0]["seats"] == 5


def test_snapshot_suppression_freshness_and_allowlist(program):
    classroom = classes.create_class(SCHOOL, "A", "LAW101", "Law", "2026")
    classes.import_enrollments(SCHOOL, classroom["id"], ["PRIVATE1", "PRIVATE2", "PRIVATE3"])
    programs.allocate_school(MANAGER, program["id"], "1", 10)
    assert programs.list_program_reports(ANALYST, program["id"])[0]["metrics"] is None
    snapshot = programs.publish_school_summary(SCHOOL, program["id"])
    assert all(snapshot["metrics"][key] is None for key in programs.LEARNER_METRICS)
    assert "PRIVATE" not in json.dumps(programs.list_program_reports(ANALYST, program["id"]))
    classes.import_enrollments(SCHOOL, classroom["id"], ["PRIVATE4", "PRIVATE5"])
    assert programs.list_program_reports(ANALYST, program["id"])[0]["metrics"]["enrolled_students"] is None
    newer = programs.publish_school_summary(SCHOOL, program["id"])
    assert newer["metrics"]["enrolled_students"] == 5
    with store.platform_session("1", program_id=program["id"], write=True, actor=SCHOOL) as session:
        row = session.get(SchoolSummarySnapshot, newer["id"])
        for published in session.query(SchoolSummarySnapshot).filter_by(program_id=program["id"], school_id="1"):
            published.as_of = datetime.now(timezone.utc) - timedelta(days=2)
        row.metrics = {"active_classes": 1, "enrolled_students": 1, "student_names": ["PRIVATE"]}
    report = programs.list_program_reports(ANALYST, program["id"])[0]
    assert report["report_status"] == "stale"
    assert report["metrics"]["enrolled_students"] is None
    assert "PRIVATE" not in json.dumps(report)
    for invalid in (0, 1, 4, True):
        with pytest.raises(ValueError):
            programs.publish_school_summary(SCHOOL, program["id"], min_cohort=invalid)


def test_only_manager_can_pause_and_pause_blocks_new_publication(program):
    programs.allocate_school(MANAGER, program["id"], "1", 5)
    with pytest.raises(PermissionError):
        programs.set_program_status(OPS, program["id"], "paused")
    programs.set_program_status(MANAGER, program["id"], "paused")
    with pytest.raises(PermissionError):
        programs.publish_school_summary(SCHOOL, program["id"])
    assert programs.list_school_programs(SCHOOL)[0]["program_status"] == "paused"
