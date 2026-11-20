"""Real PostgreSQL/pgvector acceptance tests for Workstream B."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_B_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_B_DATABASE_URL")
pytestmark = pytest.mark.skipif(not OWNER_URL or not APP_URL, reason="Workstream B PostgreSQL URLs are required")


@pytest.fixture
def tenant(monkeypatch):
    owner = create_engine(OWNER_URL)
    code = "b_" + uuid.uuid4().hex[:10]
    with owner.begin() as conn:
        org = conn.execute(
            text(
                "INSERT INTO organizations (org_code,name,is_active,created_at,updated_at) VALUES (:c,:n,true,now(),now()) RETURNING id"
            ),
            {"c": code, "n": code},
        ).scalar_one()
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org)})
        conn.execute(
            text(
                "INSERT INTO subscriptions (organization_id,plan,status,max_students,max_courses,max_ai_requests_month,max_storage_mb,features_enabled,created_at,updated_at) VALUES (:o,'ENTERPRISE','ACTIVE',20,20,3,100,'[]',now(),now())"
            ),
            {"o": org},
        )
        for role in ("Admin", "Giảng viên / CVHT", "Sinh viên"):
            conn.execute(
                text(
                    "INSERT INTO roles (name,created_at,updated_at) VALUES (:r,now(),now()) ON CONFLICT (name) DO NOTHING"
                ),
                {"r": role},
            )
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org))
    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    yield org
    reset_engine_for_tests()
    owner.dispose()


def _academic_records(org):
    return [
        ("students", {"organization_id": org, "student_external_id": "stu-1", "display_name": "Student One"}),
        (
            "lecturers",
            {
                "organization_id": org,
                "lecturer_external_id": "lec-1",
                "display_name": "Lecturer One",
                "department": "CS",
            },
        ),
        (
            "courses",
            {
                "organization_id": org,
                "course_external_id": "course-1",
                "lecturer_external_id": "lec-1",
                "title": "Data",
            },
        ),
        (
            "enrollments",
            {
                "organization_id": org,
                "enrollment_external_id": "enroll-1",
                "student_external_id": "stu-1",
                "course_external_id": "course-1",
            },
        ),
        (
            "assignments",
            {
                "organization_id": org,
                "assignment_external_id": "assign-1",
                "course_external_id": "course-1",
                "title": "Project",
            },
        ),
        (
            "submissions",
            {
                "organization_id": org,
                "submission_external_id": "submit-1",
                "assignment_external_id": "assign-1",
                "student_external_id": "stu-1",
                "status": "submitted",
            },
        ),
        (
            "grades",
            {
                "organization_id": org,
                "grade_external_id": "grade-1",
                "submission_external_id": "submit-1",
                "student_external_id": "stu-1",
                "course_external_id": "course-1",
                "score": 81,
            },
        ),
        (
            "attendance",
            {
                "organization_id": org,
                "attendance_external_id": "att-1",
                "student_external_id": "stu-1",
                "course_external_id": "course-1",
                "present": True,
                "occurred_at": "2026-01-01T00:00:00+00:00",
            },
        ),
        (
            "activities",
            {
                "organization_id": org,
                "activity_external_id": "act-1",
                "student_external_id": "stu-1",
                "course_external_id": "course-1",
                "activity_type": "lesson.viewed",
                "duration_seconds": 60,
                "occurred_at": "2026-01-01T00:00:00+00:00",
            },
        ),
    ]


def test_external_id_upserts_create_repeat_update_and_wrong_tenant(tenant):
    from dss.db.repositories.domain_persistence_repository import list_external, upsert_external

    for resource, record in _academic_records(tenant):
        assert upsert_external(tenant, resource, record)["created"]
    for resource, record in _academic_records(tenant):
        assert not upsert_external(tenant, resource, record)["created"]
    changed = {**_academic_records(tenant)[0][1], "display_name": "Updated Student"}
    assert not upsert_external(tenant, "students", changed)["created"]
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    assert all(len(list_external(tenant, r)) == 1 for r, _ in _academic_records(tenant))
    with pytest.raises(ValueError, match="organization_id"):
        upsert_external(tenant, "students", {**changed, "organization_id": tenant + 1})


def test_sync_cursor_and_webhook_inbox_survive_engine_restart(tenant):
    from dss.db.repositories import domain_persistence_repository as repo

    repo.set_sync_state(tenant, "simulator", "students", cursor="2026-01-01T00:00:00Z", status="success")
    event = {
        "organization_id": tenant,
        "event_id": "evt-1",
        "event_type": "grade.updated",
        "external_entity_id": "grade-1",
        "source_timestamp": "2026-01-02T00:00:00Z",
        "payload": {"score": 90},
    }
    assert repo.receive_event(tenant, "simulator", event)["status"] == "received"
    repo.mark_event(tenant, "evt-1", status="processed")
    assert repo.receive_event(tenant, "simulator", event)["status"] == "duplicate"
    older = {**event, "event_id": "evt-old", "source_timestamp": "2026-01-01T00:00:00Z"}
    assert repo.receive_event(tenant, "simulator", older)["status"] == "out_of_order"
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    assert repo.get_sync_state(tenant, "simulator", "students")["cursor"].startswith("2026-01-01")
    assert repo.receive_event(tenant, "simulator", event)["status"] == "duplicate"


def test_cms_content_and_real_pgvector_replace_delete_lifecycle(tenant):
    from dss.db.repositories import domain_persistence_repository as repo
    from dss.services.chunking_service import DocumentChunk
    from dss.services.cms_rag_lifecycle import invalidate_content, upsert_and_reindex
    from dss.services.vector_store import PgVectorStore

    store = PgVectorStore(APP_URL, organization_id=tenant)
    old = [0.001] * 384
    old[2] = 1.0
    new = [0.001] * 384
    new[7] = 1.0
    content = {
        "organization_id": tenant,
        "content_external_id": "content-1",
        "title": "Lesson",
        "body": "old content",
        "version": 1,
    }
    chunks = [
        DocumentChunk(
            chunk_id="old-chunk",
            document_id="doc-old",
            course_id="course-1",
            content="old content",
            token_count=2,
            embedding=old,
            metadata={"title": "Lesson"},
        )
    ]
    upsert_and_reindex(tenant, content, chunks, store)
    assert store.search(old, top_k=5)[0]["chunk_id"] == "old-chunk"
    content.update(body="new content", version=2)
    chunks = [
        DocumentChunk(
            chunk_id="new-chunk",
            document_id="doc-new",
            course_id="course-1",
            content="new content",
            token_count=2,
            embedding=new,
            metadata={"title": "Lesson"},
        )
    ]
    upsert_and_reindex(tenant, content, chunks, store)
    assert store.search(new, top_k=5)[0]["chunk_id"] == "new-chunk"
    assert all(x["chunk_id"] != "old-chunk" for x in store.search(old, top_k=20))
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    store = PgVectorStore(APP_URL, organization_id=tenant)
    assert repo.get_cms_content(tenant, "content-1")["version"] == 2
    assert store.search(new, top_k=5)[0]["chunk_id"] == "new-chunk"
    assert invalidate_content(tenant, "content-1", store)
    assert store.search(new, top_k=20) == [] and repo.get_cms_content(tenant, "content-1")["status"] == "invalidated"


def test_user_admin_lifecycle_hashing_and_audit(tenant, monkeypatch):
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {"_auth_role": "Admin", "_auth_username": "root-admin"})
    from dss.services import user_management_service as users

    created = users.create_user(tenant, "closure-user", "secret-one", "Sinh viên", student_id="stu-1")
    assert "secret-one" not in str(created)
    assert users.update_user(tenant, "closure-user", email="safe@example.test")["email"] == "safe@example.test"
    assert users.change_role(tenant, "closure-user", "Giảng viên / CVHT")["role"] == "Giảng viên / CVHT"
    users.reset_password(tenant, "closure-user", "secret-two")
    assert users.set_user_active(tenant, "closure-user", False)["is_active"] is False
    from dss.services.auth_service import authenticate

    assert authenticate("closure-user", "secret-two") is None
    users.set_user_active(tenant, "closure-user", True)
    assert authenticate("closure-user", "secret-two") is not None
    from dss.db.repositories.audit_log_repository import list_for_target

    actions = {x["action"] for x in list_for_target("user", "closure-user")}
    assert {
        "user.created",
        "user.updated",
        "user.role_changed",
        "user.password_reset",
        "user.disabled",
        "user.enabled",
    } <= actions
    assert "secret-one" not in str(list_for_target("user", "closure-user")) and "secret-two" not in str(
        list_for_target("user", "closure-user")
    )


def test_quota_below_at_over_reset_and_tenant_isolation(tenant):
    from dss.db.repositories.quota_repository import QuotaExceededError, consume, get_usage, reset

    assert consume(tenant, "AI_REQUESTS_MONTH", 3, 2, period_key="2026-01") == 2
    assert consume(tenant, "AI_REQUESTS_MONTH", 3, 1, period_key="2026-01") == 3
    with pytest.raises(QuotaExceededError):
        consume(tenant, "AI_REQUESTS_MONTH", 3, 1, period_key="2026-01")
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    assert get_usage(tenant, "AI_REQUESTS_MONTH", period_key="2026-01") == 3
    reset(tenant, "AI_REQUESTS_MONTH", period_key="2026-01")
    assert get_usage(tenant, "AI_REQUESTS_MONTH", period_key="2026-01") == 0


def test_quota_first_use_is_concurrency_safe(tenant):
    from dss.db.repositories.quota_repository import QuotaExceededError, consume, get_usage

    def attempt(_):
        try:
            consume(tenant, "CONCURRENT_REQUESTS", 5, 1, period_key="lifetime")
            return "accepted"
        except QuotaExceededError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    assert outcomes.count("accepted") == 5
    assert outcomes.count("rejected") == 3
    assert get_usage(tenant, "CONCURRENT_REQUESTS", period_key="lifetime") == 5


def test_new_tables_force_rls_cross_tenant_all_operations(tenant):
    app = create_engine(APP_URL)
    with app.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(tenant)})
        conn.execute(
            text(
                "INSERT INTO quota_usage (organization_id,quota_key,period_key,used,created_at,updated_at) VALUES (:o,'storage','lifetime',1,now(),now())"
            ),
            {"o": tenant},
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM quota_usage WHERE organization_id=:o"), {"o": tenant + 999}
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(text("UPDATE quota_usage SET used=9 WHERE organization_id=:o"), {"o": tenant + 999}).rowcount
            == 0
        )
        assert conn.execute(text("DELETE FROM quota_usage WHERE organization_id=:o"), {"o": tenant + 999}).rowcount == 0
        with pytest.raises(Exception):
            conn.execute(
                text(
                    "INSERT INTO quota_usage (organization_id,quota_key,period_key,used,created_at,updated_at) VALUES (:o,'x','x',1,now(),now())"
                ),
                {"o": tenant + 999},
            )
    app.dispose()


def test_tenant_provision_config_disable_and_assigned_user(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {"_auth_role": "Admin", "_auth_username": "platform-admin"})
    monkeypatch.setenv("DATABASE_URL", OWNER_URL)
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    from dss.services import tenant_service

    org = tenant_service.provision_organization(
        "provision-" + uuid.uuid4().hex[:8], "Provisioned University", settings={"timezone": "UTC"}
    )
    tenant_service.configure_organization(org, {"timezone": "Asia/Bangkok"})
    reset_engine_for_tests()
    assert tenant_service.get_organization(org)["settings"]["timezone"] == "Asia/Bangkok"
    from dss.db.repositories.user_repository import UserRepository

    UserRepository(org).create_user("assigned-user", "safe-password", "Sinh viên")
    tenant_service.set_organization_active(org, False)
    assert tenant_service.get_organization(org)["is_active"] is False
    assert UserRepository(org).get_user_by_username("assigned-user") is None
    tenant_service.set_organization_active(org, True)
    assert UserRepository(org).get_user_by_username("assigned-user") is not None
    reset_engine_for_tests()


def test_cms_runtime_selector_reads_and_updates_postgres(tenant, monkeypatch):
    monkeypatch.setenv("EDUDSS_CMS_STORE", "postgres")
    from dss.services import cms_lecture_repository as cms

    lesson = cms.create_or_get_lesson("course-1", "lesson-1", "topic-1", "lec-1", "Initial")
    lesson.title = "Updated"
    cms._upsert_lesson(lesson)
    assert cms.get_lesson("lesson-1").title == "Updated"
    assert [x.lesson_id for x in cms.list_lessons("course-1")] == ["lesson-1"]


def test_academic_dataframe_runtime_cutover(tenant, monkeypatch):
    import pandas as pd

    monkeypatch.setenv("EDUDSS_ACADEMIC_STORE", "postgres")
    from dss.services.academic_persistence import persist_dataframe_if_configured

    result = persist_dataframe_if_configured(
        pd.DataFrame([{"student_id": "df-1", "diem_ky_nay": 8.5}]), "df-course", "DataFrame Course", "2026.1"
    )
    assert result["students_imported"] == 1 and result["academic_records_imported"] == 1


def test_ai_request_quota_uses_subscription_limit(tenant, monkeypatch):
    monkeypatch.setenv("EDUDSS_SUBSCRIPTION_STORE", "postgres")
    from dss.db.repositories.quota_repository import QuotaExceededError
    from dss.services.subscription_service import consume_ai_request_quota

    assert consume_ai_request_quota() == 1
    assert consume_ai_request_quota() == 2
    assert consume_ai_request_quota() == 3
    with pytest.raises(QuotaExceededError):
        consume_ai_request_quota()
