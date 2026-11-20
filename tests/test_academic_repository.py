"""dss/db/repositories/academic_repository.py — real PostgreSQL integration
tests. Skipped (not faked) without a configured database — see
tests/test_db_schema.py's module docstring for local setup.
"""

from __future__ import annotations

import uuid

import pandas as pd
import pytest

from dss.db.repositories import academic_repository as repo
from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — academic repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"ACAD_TEST_{uuid.uuid4().hex[:8]}", name="Academic Test Org")
        session.add(org)
        session.flush()
        return org.id


def _demo_df(n=5):
    return pd.DataFrame(
        {
            "student_id": [f"SV{i:03d}" for i in range(1, n + 1)],
            "diem_giua_ky": [7.5] * n,
            "diem_ky_nay": [8.0] * n,
            "diem_du_an": [7.0] * n,
            "diem_ky_sau": [7.8] * n,
            "ty_le_diem_danh": [0.9] * n,
        }
    )


def test_upsert_student_is_idempotent(org_id):
    id1 = repo.upsert_student(org_id, "SV001", "Nguyen Van A")
    id2 = repo.upsert_student(org_id, "SV001", "Nguyen Van A")
    assert id1 == id2
    assert repo.count_students(org_id) == 1


def test_same_student_code_across_two_orgs_is_allowed(org_id):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org_b = Organization(org_code=f"ACAD_TEST_B_{uuid.uuid4().hex[:8]}", name="Org B")
        session.add(org_b)
        session.flush()
        org_b_id = org_b.id

    repo.upsert_student(org_id, "SV999", "Student A")
    repo.upsert_student(org_b_id, "SV999", "Student B")
    assert repo.count_students(org_id) == 1
    assert repo.count_students(org_b_id) == 1


def test_import_dataframe_creates_students_enrollments_and_records(org_id):
    df = _demo_df(5)
    result = repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS", term="HK1")
    assert result["students_imported"] == 5
    assert result["enrollments_imported"] == 5
    assert result["academic_records_imported"] == 5 * 5  # 5 score columns per student
    assert repo.count_students(org_id) == 5


def test_repeat_import_is_idempotent_for_students_and_enrollments(org_id):
    """MIGRATION SAFETY: importing the same DataFrame twice must not
    duplicate students or enrollments (only academic_records grow, and only
    when replace_existing=False is intentionally used to represent 'a new
    sync happened')."""
    df = _demo_df(5)
    repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS")
    repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS")
    assert repo.count_students(org_id) == 5  # not 10

    from dss.db.models import Enrollment
    from dss.db.session import session_scope

    with session_scope() as session:
        enrollment_count = session.query(Enrollment).filter_by(organization_id=org_id).count()
    assert enrollment_count == 5  # not 10


def test_repeat_import_with_replace_existing_does_not_duplicate_academic_records(org_id):
    df = _demo_df(5)
    repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS", replace_existing=True)
    result2 = repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS", replace_existing=True)
    assert result2["academic_records_imported"] == 25

    from dss.db.models import AcademicRecord
    from dss.db.session import session_scope

    with session_scope() as session:
        total = session.query(AcademicRecord).filter_by(organization_id=org_id).count()
    assert total == 25  # not 50 — replace_existing cleared the first batch


def test_import_skips_invalid_rows_without_crashing(org_id):
    """A NaN/invalid student_id must be skipped, not imported as a garbage
    record and not crash the whole import."""
    df = _demo_df(3)
    df.loc[1, "student_id"] = float("nan")
    result = repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS")
    assert result["students_imported"] == 2  # row with NaN student_id skipped


def test_import_missing_required_column_raises_clear_error(org_id):
    df = pd.DataFrame({"not_the_right_column": [1, 2, 3]})
    with pytest.raises(ValueError, match="student_id"):
        repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS")


def test_empty_dataframe_import_succeeds_with_zero_counts(org_id):
    df = pd.DataFrame({"student_id": []})
    result = repo.import_dataframe(org_id, df, course_code="CS301", course_title="Intro to CS")
    assert result["students_imported"] == 0
    assert result["enrollments_imported"] == 0


def test_cross_tenant_import_never_assigns_data_to_wrong_org(org_id):
    """Never silently assign cross-tenant data: importing for org_id must not
    make the data visible/counted under any other organization."""
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other_org = Organization(org_code=f"ACAD_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    repo.import_dataframe(org_id, _demo_df(4), course_code="CS301", course_title="Intro to CS")
    assert repo.count_students(other_org_id) == 0
    assert repo.count_students(org_id) == 4
