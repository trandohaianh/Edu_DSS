"""Real PostgreSQL/pgvector restore proof; requires dedicated empty databases.

Set PHASE13_SOURCE_URL, PHASE13_RESTORE_URL, PHASE13_APP_ROLE_URL, and
PHASE13_DOCKER_CONTAINER (or install PostgreSQL client binaries on PATH).
The source must have current migrations; the target must exist and be empty.
This test never drops a database and must never target production.
"""
from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ops import backup_recovery as br

pytestmark = pytest.mark.skipif(
    not all(os.environ.get(key) for key in (
        "PHASE13_SOURCE_URL", "PHASE13_RESTORE_URL", "PHASE13_APP_ROLE_URL",
    )),
    reason="Dedicated Phase 13 PostgreSQL source, empty target and app-role URLs required",
)


def _hot_vector(index: int) -> list[float]:
    vector = [0.001] * 384
    vector[index] = 1.0
    return vector


def _fixture(source_url: str, app_role: str):
    from dss.db.models import (
        ActivityLog, AdminAiConfig, AiTokenUsage, CmsLesson, Consultation,
        Course, Enrollment, ModelMetric, ModelVersion, Organization,
        Prediction, Role, Student, Subscription, User,
    )
    from dss.services.auth_service import _hash_password
    from dss.services.chunking_service import DocumentChunk
    from dss.services.vector_store import PgVectorStore

    engine = create_engine(source_url)
    with Session(engine) as session, session.begin():
        role = Role(name="phase13_test_student", description="Synthetic recovery fixture")
        session.add(role)
        session.flush()
        orgs = [
            Organization(org_code="PHASE13_A", name="Synthetic A"),
            Organization(org_code="PHASE13_B", name="Synthetic B"),
        ]
        session.add_all(orgs)
        session.flush()
        for n, org in enumerate(orgs):
            password_hash, password_salt = _hash_password(f"phase13-safe-{n}")
            user = User(organization_id=org.id, username=f"phase13_user_{n}",
                        password_hash=password_hash, password_salt=password_salt,
                        role_id=role.id, email=f"fixture{n}@example.invalid",
                        is_active=(n == 0), auto_provisioned=False)
            student = Student(organization_id=org.id, student_code=f"P13_STU_{n}",
                              full_name=f"Synthetic Student {n}", user_id=None)
            course = Course(organization_id=org.id, course_code=f"P13_COURSE_{n}",
                            title=f"Synthetic Course {n}", semester="2026F")
            subscription = Subscription(organization_id=org.id, plan="TEST", status="ACTIVE")
            model = ModelVersion(
                organization_id=org.id, training_id=f"p13_train_{n}",
                model_key=f"p13_dataset_{n}::target", dataset_id=f"p13_dataset_{n}",
                target_col="target", model_name="synthetic", status="candidate",
                artifact_path=f"external/p13_train_{n}.joblib",
            )
            session.add_all([user, student, course, subscription, model])
            session.flush()
            student.user_id = user.id
            session.add_all([
                Enrollment(organization_id=org.id, student_id=student.id, course_id=course.id),
                ModelMetric(model_version_id=model.id, metric_name="accuracy", metric_value=0.9),
                Prediction(organization_id=org.id, student_id=student.id,
                           model_version_id=model.id, prediction_value="pass"),
                Consultation(organization_id=org.id, student_id=student.id,
                             provider="synthetic", question="fixture", answer="fixture"),
                CmsLesson(organization_id=org.id, lesson_id=f"p13_lesson_{n}",
                          course_id=f"P13_COURSE_{n}", title=f"Synthetic Lesson {n}"),
                ActivityLog(organization_id=org.id, user_id=user.id,
                            action_type="phase13.synthetic",
                            description=f"Synthetic activity {n}",
                            details={"fixture": n}),
                AiTokenUsage(
                    organization_id=org.id, usage_id=f"phase13_usage_{n}",
                    timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    user_id=f"phase13_user_{n}", role=role.name,
                    request_type="recovery_test", provider="synthetic-provider",
                    model="synthetic-model", input_tokens=10 + n,
                    output_tokens=5 + n, total_tokens=15 + 2 * n,
                    estimated_cost=0.0,
                ),
                AdminAiConfig(organization_id=org.id,
                              provider_key="synthetic-provider",
                              model_name=f"synthetic-model-{n}"),
            ])
        org_ids = [org.id for org in orgs]
    with engine.begin() as conn:
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_role}"))
        conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {app_role}"))
        conn.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {app_role}"))
    for n, org_id in enumerate(org_ids):
        store = PgVectorStore(source_url, organization_id=org_id)
        store.add_chunks([
            DocumentChunk(chunk_id=f"p13_{n}_near", document_id=f"p13_doc_{n}",
                          course_id=f"P13_COURSE_{n}", content="synthetic near",
                          token_count=2, metadata={"title": f"Fixture {n}", "source": "test"},
                          embedding=_hot_vector(5)),
            DocumentChunk(chunk_id=f"p13_{n}_far", document_id=f"p13_doc_{n}",
                          course_id=f"P13_COURSE_{n}", content="synthetic far",
                          token_count=2, metadata={"title": f"Fixture {n}", "source": "test"},
                          embedding=_hot_vector(50)),
        ])
    return org_ids


def _snapshot(engine):
    tables = sorted(inspect(engine).get_table_names(schema="public"))
    with engine.connect() as conn:
        counts = {name: conn.execute(text(f'SELECT count(*) FROM public."{name}"')).scalar_one()
                  for name in tables}
        revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        dimensions = conn.execute(text(
            "SELECT chunk_id, vector_dims(embedding) FROM rag_chunks ORDER BY chunk_id"
        )).fetchall()
        records = conn.execute(text(
            "SELECT o.org_code, s.student_code, c.course_code, e.student_id, e.course_id "
            "FROM enrollments e JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id "
            "JOIN organizations o ON o.id=e.organization_id ORDER BY o.org_code"
        )).fetchall()
        model_rows = conn.execute(text(
            "SELECT training_id, artifact_path FROM model_versions ORDER BY training_id"
        )).fetchall()
        phase1c_rows = {
            "users": conn.execute(text(
                "SELECT o.org_code,u.username,r.name,u.is_active,u.auto_provisioned,"
                "length(u.password_hash),length(u.password_salt) FROM users u "
                "JOIN organizations o ON o.id=u.organization_id "
                "JOIN roles r ON r.id=u.role_id ORDER BY o.org_code"
            )).fetchall(),
            "activity": conn.execute(text(
                "SELECT o.org_code,a.action_type,a.description,a.details FROM activity_logs a "
                "JOIN organizations o ON o.id=a.organization_id ORDER BY o.org_code"
            )).fetchall(),
            "usage": conn.execute(text(
                "SELECT o.org_code,a.usage_id,a.user_id,a.provider,a.model,a.input_tokens,"
                "a.output_tokens,a.total_tokens FROM ai_token_usage a "
                "JOIN organizations o ON o.id=a.organization_id ORDER BY o.org_code"
            )).fetchall(),
            "config": conn.execute(text(
                "SELECT o.org_code,a.provider_key,a.model_name FROM admin_ai_config a "
                "JOIN organizations o ON o.id=a.organization_id ORDER BY o.org_code"
            )).fetchall(),
        }
        policies = conn.execute(text(
            "SELECT tablename, policyname FROM pg_policies WHERE schemaname='public' "
            "ORDER BY tablename, policyname"
        )).fetchall()
        flags = conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('students','rag_documents','rag_chunks','users',"
            "'activity_logs','ai_token_usage','admin_ai_config') ORDER BY relname"
        )).fetchall()
        indexes = conn.execute(text(
            "SELECT tablename, indexname FROM pg_indexes WHERE schemaname='public' "
            "ORDER BY tablename, indexname"
        )).fetchall()
    return {
        "tables": tables, "counts": counts, "revision": list(revisions),
        "dimensions": [tuple(x) for x in dimensions],
        "relationships": [tuple(x) for x in records],
        "models": [tuple(x) for x in model_rows],
        "phase1c": {key: [tuple(x) for x in rows] for key, rows in phase1c_rows.items()},
        "policies": [tuple(x) for x in policies], "rls_flags": [tuple(x) for x in flags],
        "indexes": [tuple(x) for x in indexes],
    }


def test_real_backup_restore_pgvector_rls_and_application(tmp_path, monkeypatch):
    import re
    from dss.core.health_diagnostics import readiness
    from dss.db.repositories.academic_repository import list_students
    from dss.db.session import reset_engine_for_tests
    from dss.services.vector_store import PgVectorStore

    source_url = os.environ["PHASE13_SOURCE_URL"]
    target_url = os.environ["PHASE13_RESTORE_URL"]
    app_url = os.environ["PHASE13_APP_ROLE_URL"]
    docker_container = os.environ.get("PHASE13_DOCKER_CONTAINER")
    app_role = create_engine(app_url).url.username
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", app_role)
    source = create_engine(source_url)
    target = create_engine(target_url)
    app = create_engine(app_url)
    assert not inspect(target).get_table_names(schema="public")
    org_a, org_b = _fixture(source_url, app_role)
    expected = _snapshot(source)
    assert expected["counts"]["rag_chunks"] == 4
    assert expected["counts"]["predictions"] == 2
    assert expected["counts"]["consultations"] == 2
    assert expected["counts"]["subscriptions"] == 2
    assert expected["counts"]["cms_lessons"] == 2
    assert expected["counts"]["users"] == 2
    assert expected["counts"]["activity_logs"] == 2
    assert expected["counts"]["ai_token_usage"] == 2
    assert expected["counts"]["admin_ai_config"] == 2
    # C1.2: expectations come from the code's migration contract, not a historical
    # snapshot (this line used to hard-code head 797f72d1c666 and 27 tables).
    from dss.db import schema_contract
    assert expected["revision"] == list(schema_contract.expected_heads())
    assert set(expected["tables"]) == set(schema_contract.expected_tables())
    before = PgVectorStore(source_url, organization_id=org_a).search(_hot_vector(5), top_k=2)
    assert [row["chunk_id"] for row in before] == ["p13_0_near", "p13_0_far"]

    monkeypatch.setenv("DATABASE_URL", source_url)
    monkeypatch.setenv("RESTORE_DATABASE_URL", target_url)
    metadata = br.backup(tmp_path, docker_container)
    manifest = next(tmp_path.glob("*.backup.json"))
    assert metadata["sha256"] == br.verify(manifest)[0]["sha256"]
    started = time.monotonic()
    br.restore(manifest, docker_container)
    restore_seconds = round(time.monotonic() - started, 3)
    verification_started = time.monotonic()
    actual = _snapshot(target)
    assert actual == expected
    # Restored database satisfies the same migration contract (head + every table).
    schema_contract.assert_schema_matches(target)
    assert all(dim == 384 for _, dim in actual["dimensions"])
    assert all(enabled and forced for _, enabled, forced in actual["rls_flags"])
    assert actual["policies"]
    assert len(actual["relationships"]) == 2
    assert actual["phase1c"] == expected["phase1c"]

    # The intended runtime role, not the schema-owning superuser, proves RLS.
    with app.begin() as conn:
        assert not conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")).scalar_one()
        conn.execute(text("SET LOCAL app.organization_id = :id"), {"id": str(org_a)})
        assert conn.execute(text("SELECT student_code FROM students")).scalars().all() == ["P13_STU_0"]
        assert conn.execute(text("SELECT count(*) FROM rag_documents")).scalar_one() == 1
        for table in ("users", "activity_logs", "ai_token_usage", "admin_ai_config"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1
            assert conn.execute(text(
                f"UPDATE {table} SET organization_id=organization_id WHERE organization_id=:other"
            ), {"other": org_b}).rowcount == 0
            assert conn.execute(text(
                f"DELETE FROM {table} WHERE organization_id=:other"
            ), {"other": org_b}).rowcount == 0
        assert conn.execute(text("UPDATE students SET full_name='blocked' WHERE student_code='P13_STU_1'")).rowcount == 0
        assert conn.execute(text("DELETE FROM students WHERE student_code='P13_STU_1'")).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        with app.begin() as conn:
            conn.execute(text("SET LOCAL app.organization_id = :id"), {"id": str(org_a)})
            conn.execute(text(
                "INSERT INTO students (organization_id, student_code, full_name, is_active, created_at, updated_at) "
                "VALUES (:id, 'P13_FORBIDDEN', 'blocked', true, now(), now())"
            ), {"id": org_b})
    forbidden_inserts = {
        "users": (
            "INSERT INTO users (organization_id,username,password_hash,password_salt,role_id,"
            "is_active,auto_provisioned,created_at,updated_at) "
            "VALUES (:id,'p13_forbidden_user','x','x',"
            "(SELECT id FROM roles WHERE name='phase13_test_student'),true,false,now(),now())"
        ),
        "activity_logs": (
            "INSERT INTO activity_logs (organization_id,action_type,description,details,created_at) "
            "VALUES (:id,'forbidden','forbidden','{}',now())"
        ),
        "ai_token_usage": (
            "INSERT INTO ai_token_usage (organization_id,usage_id,timestamp,user_id,role,"
            "request_type,provider,model,input_tokens,output_tokens,total_tokens,estimated_cost) "
            "VALUES (:id,'p13_forbidden_usage',now(),'safe','safe','safe','safe','safe',1,1,2,0)"
        ),
        "admin_ai_config": (
            "INSERT INTO admin_ai_config (organization_id,provider_key,model_name,created_at,updated_at) "
            "VALUES (:id,'safe','safe',now(),now())"
        ),
    }
    for statement in forbidden_inserts.values():
        with pytest.raises(DBAPIError, match="row-level security"):
            with app.begin() as conn:
                conn.execute(text("SET LOCAL app.organization_id = :id"), {"id": str(org_a)})
                conn.execute(text(statement), {"id": org_b})
    with app.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :id"), {"id": str(org_b)})
        assert conn.execute(text("SELECT student_code FROM students")).scalars().all() == ["P13_STU_1"]
        assert conn.execute(text("SELECT count(*) FROM rag_documents")).scalar_one() == 1
        for table in ("users", "activity_logs", "ai_token_usage", "admin_ai_config"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1

    after = PgVectorStore(app_url, organization_id=org_a).search(_hot_vector(5), top_k=2)
    assert [row["chunk_id"] for row in after] == [row["chunk_id"] for row in before]
    assert after[0]["metadata"] == before[0]["metadata"]
    assert PgVectorStore(app_url, organization_id=org_b).search(_hot_vector(5), top_k=2)[0]["chunk_id"] == "p13_1_near"
    verification_seconds = round(time.monotonic() - verification_started, 3)

    # Application repository and readiness point at the restored database.
    monkeypatch.setenv("DATABASE_URL", app_url)
    monkeypatch.setenv("EDUDSS_REQUIRE_PGVECTOR", "1")
    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_a))
    reset_engine_for_tests()
    app_started = time.monotonic()
    assert readiness()["status"] == "ready"
    assert [x["student_code"] for x in list_students(org_a)] == ["P13_STU_0"]
    from dss.services import auth_service
    restored_user = auth_service.authenticate("phase13_user_0", "phase13-safe-0")
    assert restored_user is not None
    assert restored_user["role"] == "phase13_test_student"
    assert auth_service.authenticate("phase13_user_0", "invalid-safe-password") is None
    from dss.db.repositories.activity_log_repository import get_recent_activities
    from dss.db.repositories.ai_token_usage_repository import load_all_records
    from dss.db.repositories.admin_ai_config_repository import get_config
    assert get_recent_activities(org_a)[0]["action"] == "phase13.synthetic"
    assert load_all_records(org_a)[0]["total_tokens"] == 15
    assert get_config(org_a) == {
        "provider_key": "synthetic-provider", "model_name": "synthetic-model-0",
    }
    app_seconds = round(time.monotonic() - app_started, 3)
    print(f"PHASE13_RESTORE_SECONDS={restore_seconds}")
    print(f"PHASE13_VERIFICATION_SECONDS={verification_seconds}")
    print(f"PHASE13_APP_READ_SECONDS={app_seconds}")
    print(f"PHASE13_ARCHIVE_BYTES={metadata['size_bytes']}")
    reset_engine_for_tests()
    source.dispose()
    target.dispose()
    app.dispose()
