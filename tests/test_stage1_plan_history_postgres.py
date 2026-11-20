"""Live PostgreSQL/RLS checks; requires an isolated migrated test database."""
from concurrent.futures import ThreadPoolExecutor
import os
import uuid

import pytest

APP_URL = os.getenv("WORKSTREAM_AB_DATABASE_URL") or os.getenv("WORKSTREAM_ONBOARDING_DATABASE_URL")
OWNER_URL = os.getenv("WORKSTREAM_AB_OWNER_URL") or os.getenv("WORKSTREAM_ONBOARDING_OWNER_URL")
pytestmark = pytest.mark.skipif(not APP_URL or not OWNER_URL, reason="Isolated PostgreSQL owner/app test URLs required")


@pytest.fixture
def pg_history(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from dss.db.models import Organization
    from dss.db.session import reset_engine_for_tests
    from dss.services import auth_service

    owner_engine = create_engine(OWNER_URL)
    with Session(owner_engine) as session:
        schools = [Organization(org_code=f"stage1-{uuid.uuid4().hex}", name="Stage 1 isolated test") for _ in range(2)]
        session.add_all(schools)
        session.flush()
        ids = [school.id for school in schools]
        session.commit()
    with create_engine(APP_URL).connect() as connection:
        assert not connection.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")).scalar()
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(ids[0]))
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "postgres")
    student_code = f"stage1-{uuid.uuid4().hex[:24]}"
    monkeypatch.setattr(auth_service, "current_user", lambda: {
        "username": student_code, "student_id": student_code, "role": "Sinh viên",
    })
    reset_engine_for_tests()
    try:
        yield ids, student_code
    finally:
        reset_engine_for_tests()
        with owner_engine.begin() as connection:
            # Only the synthetic school rows created by this fixture are removed.
            connection.execute(text("DELETE FROM organizations WHERE id IN (:a,:b)"), {"a": ids[0], "b": ids[1]})
        owner_engine.dispose()


def _plan(student_code, course="CS101"):
    from dss.services.learning_plan import learning_plan_generator
    from dss.services.learning_profile import StudentLearningProfile
    return learning_plan_generator.generate_plan(
        StudentLearningProfile.build_from_lms_records(student_code, course, {"quiz_score": 4}),
    )


def test_postgres_first_owner_concurrent_versions_and_retries(pg_history):
    from dss.services import learning_plan_history as history
    _, student_code = pg_history
    plans = [_plan(student_code) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        saved = list(executor.map(lambda plan: history.save_learning_plan(student_code, plan), plans))
    assert sorted(record["plan"]["version"] for record in saved) == list(range(1, 7))
    first = plans[0]
    with ThreadPoolExecutor(max_workers=4) as executor:
        retries = list(executor.map(lambda _: history.save_learning_plan(student_code, first), range(4)))
    assert len({record["plan"]["version"] for record in retries}) == 1
    assert len(history.list_learning_plans(student_code)) == 6


def test_postgres_school_isolation_course_versions_and_progress(pg_history, monkeypatch):
    from dss.services import learning_plan_history as history
    schools, student_code = pg_history
    first = history.save_learning_plan(student_code, _plan(student_code))
    history.set_activity_completed(student_code, first["plan"]["plan_id"], 0, True)
    assert history.list_learning_plans(student_code)[0]["completion"]["0"] is True
    assert history.save_learning_plan(student_code, _plan(student_code, "DB201"))["plan"]["version"] == 1
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(schools[1]))
    assert history.list_learning_plans(student_code) == []
    with pytest.raises(LookupError):
        history.set_activity_completed(student_code, first["plan"]["plan_id"], 0, True)
    assert history.save_learning_plan(student_code, _plan(student_code))["plan"]["version"] == 1
