"""Acceptance against an isolated migrated PostgreSQL, using a restricted app role."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

APP_URL = os.getenv("EDUDSS_PLATFORM_TEST_APP_URL")
OWNER_URL = os.getenv("EDUDSS_PLATFORM_TEST_OWNER_URL")
pytestmark = pytest.mark.skipif(not APP_URL or not OWNER_URL, reason="Isolated PostgreSQL owner/app URLs required")


@pytest.fixture
def pg(monkeypatch):
    from dss.db.session import reset_engine_for_tests
    from dss.platform.context import Actor
    from dss.services import classroom_service as classes
    from dss.services import program_allocation_service as programs

    seed = int(uuid4().hex[:8], 16) * 10 + 10000
    scopes = [str(seed + i) for i in range(3)]
    operator = Actor(scopes[0], "operator", "Platform Admin")
    manager = Actor(scopes[0], "manager", "Admin")
    analyst = Actor(scopes[0], "analyst", "Giảng viên / CVHT")
    admin = Actor(scopes[1], "admin", "Admin")
    other_admin = Actor(scopes[2], "admin", "Admin")
    teacher = Actor(scopes[1], "teacher", "Giảng viên / CVHT")
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "REAL_LMS")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", scopes[1])
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    monkeypatch.setenv("EDUDSS_PSEUDONYM_KEY", "isolated-stage23-test-only-key-1234567890")
    reset_engine_for_tests()
    owner = create_engine(OWNER_URL)
    app = create_engine(APP_URL)
    with app.connect() as connection:
        flags = connection.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert flags == (False, False)
    for index, scope in enumerate(scopes):
        programs.register_school(operator, scope, "Isolated school " + str(index))
    program = programs.create_program(operator, "pg-" + uuid4().hex, "Isolated programme", 10, 100)
    programs.grant_program_member(operator, program["id"], manager.school_id, manager.username, "manager")
    programs.grant_program_member(operator, program["id"], analyst.school_id, analyst.username, "analyst")
    programs.allocate_school(manager, program["id"], admin.school_id, 6, 60)
    programs.allocate_school(manager, program["id"], other_admin.school_id, 4, 40)
    first = classes.create_class(admin, "A", "LAW101", "First class", "2026")
    second = classes.create_class(other_admin, "B", "LAW101", "Other school", "2026")
    classes.assign_teacher(admin, first["id"], teacher.username)
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "1")
    yield dict(
        operator=operator,
        manager=manager,
        analyst=analyst,
        admin=admin,
        other_admin=other_admin,
        teacher=teacher,
        program=program,
        first=first,
        second=second,
        scopes=scopes,
        app=app,
    )
    reset_engine_for_tests()
    app.dispose()
    with owner.begin() as connection:
        connection.execute(
            text("DELETE FROM lp_audit_events WHERE school_id IN (:a,:b,:c) OR program_id=:p"),
            dict(a=scopes[0], b=scopes[1], c=scopes[2], p=program["id"]),
        )
        connection.execute(text("DELETE FROM lp_programs WHERE id=:id"), dict(id=program["id"]))
        connection.execute(
            text("DELETE FROM lp_schools WHERE id IN (:a,:b,:c)"), dict(a=scopes[0], b=scopes[1], c=scopes[2])
        )
    owner.dispose()


def _student(pg, code="SV1"):
    from dss.platform.context import Actor
    from dss.services import classroom_service as classes

    actor = Actor(pg["admin"].school_id, code, "Sinh viên", code)
    classes.enroll_student(pg["admin"], pg["first"]["id"], code)
    return actor


def _assessment(pg, maximum=3):
    from dss.services import classroom_learning_service as learning

    questions = [
        dict(
            question_id="q1",
            topic_id="sources",
            text="Approved question one",
            options=["A", "B"],
            correct_answer_index=0,
        ),
        dict(
            question_id="q2", topic_id="cases", text="Approved question two", options=["A", "B"], correct_answer_index=1
        ),
    ]
    draft = learning.create_assessment(pg["teacher"], pg["first"]["id"], "Assessment", questions, max_attempts=maximum)
    return learning.publish_assessment(pg["teacher"], draft["id"])


def test_migration_contract_and_forced_rls(pg):
    from dss.db.schema_contract import assert_schema_matches
    from dss.platform.models import PLATFORM_TABLES

    with create_engine(OWNER_URL).connect() as connection:
        assert_schema_matches(connection.engine)
        actual = dict(
            connection.execute(
                text(
                    "SELECT relname, relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname LIKE 'lp_%' AND relkind='r'"
                )
            ).all()
        )
    assert set(actual) == {table.name for table in PLATFORM_TABLES}
    assert all(actual.values())


def test_scope_denies_unscoped_and_cross_school_writes(pg):
    from dss.platform.models import Classroom
    from dss.platform.store import platform_session
    from dss.services import classroom_service as classes

    with pg["app"].connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM lp_classes")).scalar() == 0
    with platform_session(pg["admin"].school_id, actor=pg["admin"]) as session:
        ids = set(session.scalars(select(Classroom.id)).all())
        assert pg["first"]["id"] in ids and pg["second"]["id"] not in ids
    with pytest.raises(DBAPIError):
        with platform_session(pg["admin"].school_id, write=True, actor=pg["admin"]) as session:
            session.add(
                Classroom(school_id=pg["other_admin"].school_id, code="forbidden", course_id="X", title="X", term="X")
            )
            session.flush()
    with pytest.raises(PermissionError):
        classes.list_class_roster(pg["teacher"], pg["second"]["id"])
    # Transaction-local settings must not leak through the shared pool.
    with pg["app"].connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM lp_classes")).scalar() == 0


def test_student_live_submission_idempotency_and_saved_progress(pg):
    from dss.db.session import reset_engine_for_tests
    from dss.services import classroom_learning_service as learning

    student = _student(pg)
    assessment = _assessment(pg, maximum=1)
    assert "correct_answer_index" not in learning.list_assessments(student, pg["first"]["id"])[0]["questions"][0]

    def submit(_):
        return learning.submit_attempt(student, assessment["id"], [0, 0], "same-key")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(submit, range(4)))
    assert len({item["attempt"]["id"] for item in results}) == 1
    assert len({item["plan"]["id"] for item in results}) == 1
    assert results[0]["attempt"]["topic_scores"] == {"sources": 10, "cases": 0}
    record = results[0]["plan"]
    assert record["plan"]["source_attempt_id"] == results[0]["attempt"]["id"]
    learning.set_plan_activity_completed(student, record["id"], 0, True)
    reset_engine_for_tests()
    assert learning.get_my_plan(student, pg["first"]["id"])["completion"]["0"] is True
    with pytest.raises(ValueError):
        learning.submit_attempt(student, assessment["id"], [0, 0], "different-key")
    other = _student(pg, "SV2")
    with pytest.raises(PermissionError):
        learning.set_plan_activity_completed(other, record["id"], 0, True)


def test_quota_race_serializes_and_rollback_is_complete(pg):
    from dss.services import classroom_service as classes

    for number in range(5):
        _student(pg, "existing" + str(number))

    def enroll(code):
        try:
            classes.enroll_student(pg["admin"], pg["first"]["id"], code)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(enroll, ["racer-a", "racer-b"]))
    assert sorted(results) == [False, True]
    assert len(classes.list_class_roster(pg["admin"], pg["first"]["id"])) == 6
    with pytest.raises(ValueError):
        classes.import_enrollments(pg["admin"], pg["first"]["id"], ["bulk-a", "bulk-b"])
    assert len(classes.list_class_roster(pg["admin"], pg["first"]["id"])) == 6


def test_programme_rights_and_small_cohort_suppression(pg):
    from dataclasses import replace

    from dss.platform.models import Attempt, SchoolSummarySnapshot
    from dss.platform.store import platform_session
    from dss.services import classroom_learning_service as learning
    from dss.services import program_allocation_service as programs

    student = _student(pg)
    assessment = _assessment(pg)
    result = learning.submit_attempt(student, assessment["id"], [0, 0], "sensitive-attempt")
    for principal in (pg["operator"], replace(pg["manager"], school_id=pg["other_admin"].school_id)):
        with pytest.raises(PermissionError):
            programs.allocate_school(principal, pg["program"]["id"], pg["admin"].school_id, 6, 60)
        with pytest.raises(PermissionError):
            programs.list_program_reports(principal, pg["program"]["id"])
    programs.publish_school_summary(pg["admin"], pg["program"]["id"])
    reports = programs.list_program_reports(pg["analyst"], pg["program"]["id"])
    first = next(row for row in reports if row["school_id"] == pg["admin"].school_id)
    assert first["report_status"] == "suppressed"
    serialized = json.dumps(reports)
    assert student.student_id not in serialized
    assert result["attempt"]["id"] not in serialized
    assert "answers" not in serialized
    with platform_session(pg["analyst"].school_id, actor=pg["analyst"]) as session:
        assert session.scalars(select(Attempt)).all() == []
        assert session.scalars(select(SchoolSummarySnapshot)).all()
    with platform_session(pg["operator"].school_id, actor=pg["operator"]) as session:
        assert session.scalars(select(SchoolSummarySnapshot)).all() == []


def test_paused_allocation_denies_new_writes_keeps_history(pg, monkeypatch):
    from dss.services import classroom_learning_service as learning
    from dss.services import program_allocation_service as programs

    student = _student(pg)
    assessment = _assessment(pg)
    saved = learning.submit_attempt(student, assessment["id"], [0, 0], "before-pause")
    programs.allocate_school(pg["manager"], pg["program"]["id"], pg["admin"].school_id, 6, 60, status="suspended")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    assert learning.get_my_plan(student, pg["first"]["id"])["id"] == saved["plan"]["id"]
    with pytest.raises(PermissionError):
        learning.submit_attempt(student, assessment["id"], [0, 1], "after-pause")


def test_plain_pg_resource_reads_scope_course_namespace_without_embeddings(monkeypatch):
    from sqlalchemy.orm import Session

    from dss.db.models import Organization
    from dss.services.chunking_service import DocumentChunk
    from dss.services.vector_store import PgVectorStore

    owner = create_engine(OWNER_URL)
    stores = []
    with Session(owner) as session:
        organizations = [Organization(org_code="resource-" + uuid4().hex, name="Resource test") for _ in range(2)]
        session.add_all(organizations)
        session.flush()
        ids = [row.id for row in organizations]
        session.commit()
    try:
        document = "resource-" + uuid4().hex
        for index, organization in enumerate(ids):
            store = PgVectorStore(APP_URL, organization_id=organization, namespace="student_learning")
            stores.append(store)
            chunks = [
                DocumentChunk(
                    f"{document}-{organization}#c{position}",
                    document,
                    "LAW101",
                    f"school-{index}-section-{position}",
                    2,
                    {"chunk_index": position, "status": "APPROVED", "approved_by": "teacher"},
                    [1.0] + [0.0] * 383,
                )
                for position in (10, 2)
            ]
            assert store.add_chunks(chunks) == 2
        monkeypatch.setattr(
            stores[0], "search", lambda *args, **kwargs: pytest.fail("No vector search for plain content")
        )
        chunks = stores[0].get_document_chunks(document, course_id="LAW101")
        assert [row["content"] for row in chunks] == ["school-0-section-2", "school-0-section-10"]
        assert all("embedding" not in row for row in chunks)
        assert stores[0].get_document_chunks(document, course_id="OTHER") == []
        # Exercise the actual PostgreSQL CMS approval -> plan resource bridge.
        from dss.db.session import reset_engine_for_tests
        from dss.services import cms_lecture_repository as cms
        from dss.services.learning_plan_resources import approved_plan_resources

        monkeypatch.setenv("DATABASE_URL", APP_URL)
        monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(ids[0]))
        monkeypatch.setenv("EDUDSS_CMS_STORE", "postgres")
        monkeypatch.setenv("EDUDSS_RAG_STORE", "postgres")
        reset_engine_for_tests()
        lesson = cms.CMSLesson(
            lesson_id="LAW-L1",
            course_id="LAW101",
            topic_id="sources",
            lecturer_id="teacher",
            title="Official law",
            current_document_id=document,
        )
        cms._upsert_lesson(lesson)
        resources = approved_plan_resources("LAW101")
        assert [row["resource_id"] for row in resources] == [f"cms:LAW-L1:{document}"]
        reset_engine_for_tests()
        other_namespace = PgVectorStore(APP_URL, organization_id=ids[0], namespace="policy_admin")
        stores.append(other_namespace)
        assert other_namespace.get_document_chunks(document, course_id="LAW101") == []
    finally:
        for store in stores:
            if store._engine is not None:
                store._engine.dispose()
        with owner.begin() as connection:
            connection.execute(text("DELETE FROM organizations WHERE id IN (:a,:b)"), dict(a=ids[0], b=ids[1]))
        owner.dispose()
