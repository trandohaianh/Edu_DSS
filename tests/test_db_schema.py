"""Phase 1 (PostgreSQL persistence) tests.

These tests require a real PostgreSQL + pgvector instance — they are SKIPPED
(not failed) when none is configured, so the existing 489-test baseline is
never put at risk by Phase 1 (Postgres is additive this phase, not required to
run the app or its existing tests). To run these locally:

    docker run -d --name edudss_pg_test -e POSTGRES_PASSWORD=devtest_local_only \\
      -e POSTGRES_DB=edudss_db -e POSTGRES_USER=edudss -p 55433:5432 pgvector/pgvector:pg16
    DATABASE_URL=postgresql+psycopg2://edudss:devtest_local_only@localhost:55433/edudss_db \\
      pytest tests/test_db_schema.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from dss.db.session import is_database_configured, reset_engine_for_tests

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured (DATABASE_URL / DB_HOST+DB_NAME+DB_USER) — Phase 1 tests skipped, not faked",
)


@pytest.fixture(scope="module", autouse=True)
def _fresh_schema():
    """Ensures the schema exists via Base.metadata.create_all — verifies
    ORM-level schema correctness. Migration mechanics themselves (alembic
    upgrade/downgrade) are verified separately in
    test_migration_upgrade_downgrade_cycle below.

    Deliberately does NOT drop tables on teardown: this test database is
    ephemeral (a disposable Docker container — see this file's module
    docstring), and other test modules in the same pytest session
    (test_db_row_level_security.py) rely on the schema — including the RLS
    policies, which are not part of Base.metadata and would NOT be recreated
    by create_all — still being present after this module's tests finish.
    Alembic's own `alembic_version` bookkeeping table is also untouched by
    Base.metadata operations, so a destructive drop here would desync it from
    the actual tables without any other module noticing until it tried to use
    them."""
    reset_engine_for_tests()
    from dss.db import (
        models,  # noqa: F401  (import registers all tables on Base.metadata — without this, Base.metadata is empty and create_all() silently creates nothing)
    )
    from dss.db.base import Base
    from dss.db.session import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield engine


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def test_all_20_tables_exist(_fresh_schema):
    inspector = inspect(_fresh_schema)
    tables = set(inspector.get_table_names())
    expected = {
        "organizations",
        "roles",
        "permissions",
        "role_permissions",
        "users",
        "subscriptions",
        "students",
        "lecturers",
        "courses",
        "enrollments",
        "academic_records",
        "model_versions",
        "model_metrics",
        "predictions",
        "recommendations",
        "consultations",
        "rag_documents",
        "rag_chunks",
        "audit_logs",
        "activity_logs",
    }
    missing = expected - tables
    assert not missing, f"Missing tables: {missing}"


def test_organization_unique_org_code_enforced():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    code = _unique("ORG")
    with session_scope() as session:
        session.add(Organization(org_code=code, name="Test Univ A"))

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(Organization(org_code=code, name="Duplicate code, different name"))


def test_user_foreign_key_to_organization_enforced():
    from dss.db.models import Role, User
    from dss.db.session import session_scope

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            role = session.query(Role).first()
            if role is None:
                role = Role(name=_unique("role"))
                session.add(role)
                session.flush()
            session.add(
                User(
                    organization_id=999_999_999,  # does not exist
                    username=_unique("ghost_user"),
                    password_hash="x",
                    password_salt="y",
                    role_id=role.id,
                )
            )


def test_student_unique_code_per_organization_not_globally():
    """Same student_code in TWO DIFFERENT organizations must be allowed (this
    is exactly the multi-tenant isolation Phase 5 will build on) — only
    duplicate within the SAME organization must be rejected."""
    from dss.db.models import Organization, Student
    from dss.db.session import session_scope

    code = _unique("SV")
    org_a_name = _unique("University A")
    with session_scope() as session:
        org_a = Organization(org_code=_unique("ORG_A"), name=org_a_name)
        org_b = Organization(org_code=_unique("ORG_B"), name=_unique("University B"))
        session.add_all([org_a, org_b])
        session.flush()
        session.add(Student(organization_id=org_a.id, student_code=code, full_name="Nguyen Van A"))
        session.add(Student(organization_id=org_b.id, student_code=code, full_name="Tran Thi B"))
    # No exception -> same code across 2 orgs is allowed (tenant-scoped uniqueness, not global)

    # True duplicate (same org, same code) must be rejected.
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            existing_org_a = session.query(Organization).filter(Organization.name == org_a_name).one()
            session.add(
                Student(organization_id=existing_org_a.id, student_code=code, full_name="Duplicate in same org")
            )


def test_model_version_training_id_unique():
    from dss.db.models import ModelVersion, Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=_unique("ORG"), name="Test Univ")
        session.add(org)
        session.flush()
        tid = _unique("training")
        session.add(
            ModelVersion(
                organization_id=org.id,
                training_id=tid,
                model_key="ds::target",
                dataset_id="ds",
                target_col="target",
                model_name="RandomForest",
            )
        )

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            org2 = session.query(Organization).first()
            session.add(
                ModelVersion(
                    organization_id=org2.id,
                    training_id=tid,
                    model_key="other::target",
                    dataset_id="other",
                    target_col="target",
                    model_name="XGBoost",
                )
            )


def test_rag_chunk_embedding_column_is_real_pgvector(_fresh_schema):
    """Confirms the embedding column is a genuine pgvector column (not a JSON
    fallback) when pgvector is actually available, per Phase 2's requirement
    that embeddings be a first-class, indexable vector type."""
    from dss.db import models

    assert models._VECTOR_AVAILABLE, "pgvector package not available — install pgvector to satisfy Phase 2"
    inspector = inspect(_fresh_schema)
    columns = {c["name"]: c for c in inspector.get_columns("rag_chunks")}
    assert "embedding" in columns


def test_audit_log_repository_records_and_reads_back():
    from dss.db.repositories import audit_log_repository

    target_id = _unique("training")
    ok = audit_log_repository.record(
        action="model.promoted",
        target_type="model_version",
        target_id=target_id,
        actor_username="admin_test",
        before={"production_training_id": None},
        after={"production_training_id": target_id},
    )
    assert ok is True

    history = audit_log_repository.list_for_target("model_version", target_id)
    assert len(history) == 1
    assert history[0]["action"] == "model.promoted"
    assert history[0]["actor_username"] == "admin_test"
    assert history[0]["before"] == {"production_training_id": None}


def test_seed_script_is_idempotent():
    from dss.db import seed
    from dss.db.models import Organization, User
    from dss.db.session import session_scope

    seed.run_seed()
    seed.run_seed()  # must not raise, must not duplicate

    with session_scope() as session:
        org_count = session.query(Organization).filter_by(org_code="DEMO_UNIV").count()
        user_count = session.query(User).count()
    assert org_count == 1
    assert user_count >= 3  # admin, giangvien, sv001 seeded, plus whatever other tests added


def test_migration_upgrade_downgrade_cycle():
    """Verifies the ACTUAL alembic migration (not just Base.metadata.create_all)
    applies cleanly and rolls back cleanly, against a schema this test owns
    exclusively (drops everything first so it isn't polluted by the
    module-level _fresh_schema fixture's own tables)."""
    from alembic import command
    from alembic.config import Config

    from dss.db.base import Base
    from dss.db.session import get_engine

    engine = get_engine()
    # Bảng lp_* nằm trên metadata riêng (dss/platform/models.py): xoá cả chúng, giống test_db_row_level_security,
    # nếu không lần migrate lại báo "relation lp_audit_events already exists" (bước 9, 22/11/2026).
    from dss.platform.models import PlatformBase

    with engine.begin() as conn:
        for table in PlatformBase.metadata.sorted_tables:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
    Base.metadata.drop_all(engine)  # clean slate — alembic must create everything itself
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(app_root, "alembic.ini"))

    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert "rag_chunks" in inspector.get_table_names()
    assert "audit_logs" in inspector.get_table_names()

    command.downgrade(cfg, "base")
    inspector = inspect(engine)
    remaining = set(inspector.get_table_names()) - {"alembic_version"}
    assert not remaining, f"downgrade left tables behind: {remaining}"

    # Restore via Alembic itself (not Base.metadata.create_all) — this test
    # just downgraded to "base", so alembic_version now correctly reflects
    # that; using create_all here would silently desync alembic_version from
    # the actual tables (tables exist, but Alembic thinks none are applied),
    # which breaks any other test module in the same pytest session that
    # trusts `alembic upgrade head` to be a reliable no-op/repair when already
    # at head (see test_db_row_level_security.py's _ensure_schema_and_rls).
    command.upgrade(cfg, "head")
