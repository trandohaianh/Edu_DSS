"""dss/db/repositories/recommendation_repository.py — real PostgreSQL
integration tests (Phase 1B, migration order item 7). Skipped (not faked)
without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.repositories import recommendation_repository as repo
from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — recommendation repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"RECO_TEST_{uuid.uuid4().hex[:8]}", name="Recommendation Test Org")
        session.add(org)
        session.flush()
        return org.id


def test_save_recommendation_creates_student_and_row(org_id):
    rec_id = repo.save_recommendation(org_id, "SV001", "career_path", "Hãy học thêm về Python.")
    assert rec_id

    results = repo.list_recommendations(org_id, student_code="SV001")
    assert len(results) == 1
    assert results[0]["content"] == "Hãy học thêm về Python."
    assert results[0]["recommendation_type"] == "career_path"


def test_save_recommendation_reuses_existing_student(org_id):
    from dss.db.models import Student
    from dss.db.session import session_scope

    repo.save_recommendation(org_id, "SV002", "career_path", "Gợi ý 1")
    repo.save_recommendation(org_id, "SV002", "career_path", "Gợi ý 2")

    with session_scope() as session:
        students = session.query(Student).filter_by(organization_id=org_id, student_code="SV002").all()
    assert len(students) == 1  # not duplicated across two save calls

    results = repo.list_recommendations(org_id, student_code="SV002")
    assert len(results) == 2  # each recommendation IS a new append-only row


def test_recommendations_not_idempotent_by_design(org_id):
    """Re-generating the same advice text twice creates two rows — a
    recommendation is a point-in-time event, matching academic_records."""
    repo.save_recommendation(org_id, "SV003", "career_path", "Cùng một nội dung")
    repo.save_recommendation(org_id, "SV003", "career_path", "Cùng một nội dung")
    assert len(repo.list_recommendations(org_id, student_code="SV003")) == 2


def test_cross_tenant_isolation(org_id):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"RECO_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    repo.save_recommendation(org_id, "SV004", "career_path", "Nội dung org A")

    assert len(repo.list_recommendations(org_id)) == 1
    assert len(repo.list_recommendations(other_org_id)) == 0
