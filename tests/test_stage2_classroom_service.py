"""School enrollment transactions and capacity enforcement."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy.exc import IntegrityError
from dss.platform.context import Actor
from dss.platform.models import ClassEnrollment, Program, SchoolAllocation
from dss.platform import store
from dss.services import classroom_service as classes

ADMIN = Actor("1", "admin", "Admin")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    store.reset_platform_engines()
    yield
    store.reset_platform_engines()


def classroom(code="LAW-A"):
    return classes.create_class(ADMIN, code, "LAW101", "Law", "2026")


def allocate(cap=2):
    with store.platform_session("1", write=True, actor=ADMIN) as session:
        program = Program(code="P", name="Pilot", seat_budget=20, ai_budget=0)
        session.add(program)
        session.flush()
        row = SchoolAllocation(program_id=program.id, school_id="1", seats=cap, ai_budget=0)
        session.add(row)
        session.flush()
        return program.id, row.id


def test_roster_is_atomic_and_distinct_across_classes():
    first, second = classroom(), classroom("LAW-B")
    allocate(2)
    assert classes.import_enrollments(ADMIN, first["id"], [" SV1 ", "SV1"])["added"] == 1
    classes.enroll_student(ADMIN, second["id"], "SV1")
    with pytest.raises(ValueError):
        classes.import_enrollments(ADMIN, first["id"], ["SV2", "SV3"])
    with pytest.raises(ValueError):
        classes.import_enrollments(ADMIN, first["id"], ["SV2", ""])
    assert classes.list_class_roster(ADMIN, first["id"]) == [{"student_code": "SV1", "active": True}]
    assert classes.import_enrollments(ADMIN, first["id"], ["SV1", "SV2"])["unchanged"] == 1
    classes.unenroll_student(ADMIN, first["id"], "SV2")
    assert classes.import_enrollments(ADMIN, first["id"], ["SV2"])["reactivated"] == 1


def test_concurrent_enrollment_never_oversubscribes():
    row = classroom()
    allocate(2)
    def enroll(index):
        try:
            classes.enroll_student(ADMIN, row["id"], "SV" + str(index))
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(enroll, range(8))) == 2
    assert len(classes.list_class_roster(ADMIN, row["id"])) == 2


@pytest.mark.parametrize("allocation_status,program_status", [
    ("suspended", "active"), ("revoked", "active"), ("active", "paused"), ("active", "closed"),
])
def test_disabled_allocations_preserve_reads_and_block_writes(allocation_status, program_status):
    row = classroom()
    classes.enroll_student(ADMIN, row["id"], "SV1")
    program_id, allocation_id = allocate()
    with store.platform_session("1", write=True, actor=ADMIN) as session:
        session.get(Program, program_id).status = program_status
        session.get(SchoolAllocation, allocation_id).status = allocation_status
    assert len(classes.list_class_roster(ADMIN, row["id"])) == 1
    with pytest.raises(PermissionError):
        classes.enroll_student(ADMIN, row["id"], "SV2")


def test_reopening_class_rolls_back_if_over_capacity():
    first, second = classroom(), classroom("LAW-B")
    classes.enroll_student(ADMIN, first["id"], "SV1")
    classes.enroll_student(ADMIN, second["id"], "SV2")
    classes.set_class_status(ADMIN, second["id"], "closed")
    allocate(1)
    with pytest.raises(ValueError):
        classes.set_class_status(ADMIN, second["id"], "active")
    assert next(row for row in classes.list_my_classes(ADMIN) if row["id"] == second["id"])["status"] == "closed"


def test_official_assignment_and_cross_school_foreign_key():
    row = classroom()
    teacher = Actor("1", "teacher", "Giảng viên / CVHT")
    classes.assign_teacher(ADMIN, row["id"], teacher.username)
    assert classes.list_teaching_assignments(ADMIN, row["id"])[0]["active"] is True
    classes.revoke_teacher(ADMIN, row["id"], teacher.username)
    assert classes.list_my_classes(teacher) == []
    other = Actor("2", "admin", "Admin")
    classes.create_class(other, "OTHER", "LAW101", "Other", "2026")
    with pytest.raises(IntegrityError):
        with store.platform_session("2", write=True, actor=other) as session:
            session.add(ClassEnrollment(school_id="2", class_id=row["id"], student_code="SV1"))
            session.flush()
