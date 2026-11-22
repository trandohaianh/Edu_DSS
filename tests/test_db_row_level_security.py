"""Phase 1 (merged) — Row Level Security tenant isolation, verified for real.

Requires TWO separate PostgreSQL connection strings:
- DATABASE_URL (or DB_HOST/etc.) — the schema-owner connection used to apply
  migrations and set up test data (this role is typically a superuser and is
  NOT protected by RLS — do not use it to test isolation).
- DATABASE_APP_ROLE_URL — a genuinely non-superuser role with DML grants on
  the tenant tables. RLS is meaningless without this: superusers and table
  owners bypass RLS regardless of policies (FORCE ROW LEVEL SECURITY still
  lets a superuser through — only a superuser is unconditionally exempt).

To run locally (mirrors this session's own verification):
    docker run -d --name edudss_pg_test -e POSTGRES_PASSWORD=devtest_local_only \\
      -e POSTGRES_DB=edudss_db -e POSTGRES_USER=edudss -p 55433:5432 pgvector/pgvector:pg16
    DATABASE_URL=postgresql+psycopg2://edudss:devtest_local_only@localhost:55433/edudss_db \\
      python -m alembic upgrade head
    docker exec edudss_pg_test psql -U edudss -d edudss_db -c \\
      "CREATE ROLE edudss_app LOGIN PASSWORD 'app_role_devtest_only'; \\
       GRANT ALL ON ALL TABLES IN SCHEMA public TO edudss_app; \\
       GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO edudss_app;"
    DATABASE_URL=postgresql+psycopg2://edudss:devtest_local_only@localhost:55433/edudss_db \\
    DATABASE_APP_ROLE_URL=postgresql+psycopg2://edudss_app:app_role_devtest_only@localhost:55433/edudss_db \\
      pytest tests/test_db_row_level_security.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from dss.db.session import is_database_configured

_APP_ROLE_URL = os.environ.get("DATABASE_APP_ROLE_URL")

pytestmark = pytest.mark.skipif(
    not (is_database_configured() and _APP_ROLE_URL),
    reason=(
        "Real RLS verification requires both DATABASE_URL (schema owner) and "
        "DATABASE_APP_ROLE_URL (a genuine non-superuser role) — skipped, not faked. "
        "See this file's module docstring for local setup."
    ),
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_and_rls():
    """Self-sufficient regardless of test execution order or what state a
    previous test module left behind in the shared test database. Does NOT
    trust `alembic upgrade head`'s own idempotency check (which is based on
    the `alembic_version` bookkeeping row, not actual table existence) —
    another module in the same pytest session may have desynced the two
    (e.g. by using Base.metadata.create_all/drop_all directly, which never
    touches alembic_version). Unconditionally forces a known-good rebuild
    (drop everything, migrate from nothing) rather than trying to detect
    whether the existing state is already fine — cheap (a few hundred ms
    against a local/CI Postgres) and eliminates an entire class of
    cross-module test-ordering bugs for a one-time module-scoped cost."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text as sa_text

    import dss.db.models  # noqa: F401 — registers all tables on Base.metadata;

    # without this import, drop_all below silently no-ops when this file runs
    # standalone/first (Base.metadata starts empty until some module imports
    # dss.db.models — previously only true by accident of test collection order).
    from dss.db.base import Base
    from dss.db.session import get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    engine = get_engine()
    # Bảng nền tảng Lớp học (lp_*, migration d2e3a6102601) nằm trên metadata riêng — phải xoá cả chúng,
    # nếu không lần migrate lại báo "relation lp_audit_events already exists" (phát hiện ở bước 8, 22/11/2026).
    # Chính sách RLS của các bảng này tham chiếu chéo nhau nên phải DROP ... CASCADE.
    from dss.platform.models import PlatformBase

    with engine.begin() as conn:
        for table in PlatformBase.metadata.sorted_tables:
            conn.execute(sa_text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE IF EXISTS alembic_version"))

    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(app_root, "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture()
def app_engine():
    """A fresh engine connected as the NON-SUPERUSER app role — every test in
    this file must exercise RLS through this, never through the schema-owner
    connection (which would silently bypass RLS and produce a false pass)."""
    engine = create_engine(_APP_ROLE_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def two_orgs():
    """Creates 2 real organizations via the schema-owner connection (RLS
    doesn't apply to the `organizations` table itself, so any role can insert
    here) and returns their ids. Cleans up afterward."""
    from dss.db.session import get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    engine = get_engine()
    suffix = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        org_a_id = conn.execute(
            text(
                "INSERT INTO organizations (org_code, name, is_active, created_at, updated_at) "
                "VALUES (:code, :name, true, now(), now()) RETURNING id"
            ),
            {"code": f"RLS_A_{suffix}", "name": "RLS Test Org A"},
        ).scalar_one()
        org_b_id = conn.execute(
            text(
                "INSERT INTO organizations (org_code, name, is_active, created_at, updated_at) "
                "VALUES (:code, :name, true, now(), now()) RETURNING id"
            ),
            {"code": f"RLS_B_{suffix}", "name": "RLS Test Org B"},
        ).scalar_one()
    yield org_a_id, org_b_id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM students WHERE organization_id IN (:a, :b)"), {"a": org_a_id, "b": org_b_id})
        conn.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a_id, "b": org_b_id})


def _insert_student_as(engine, organization_id: int, student_code: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(organization_id)})
        conn.execute(
            text(
                "INSERT INTO students (organization_id, student_code, full_name, is_active, created_at, updated_at) "
                "VALUES (:org_id, :code, 'RLS Test Student', true, now(), now())"
            ),
            {"org_id": organization_id, "code": student_code},
        )


def test_cross_tenant_read_returns_zero_rows_not_error(app_engine, two_orgs):
    """The exact scenario the original spec calls out by name: a query scoped
    to the WRONG tenant must not see the other tenant's row — not raise, not
    partially succeed, just see nothing, as if the row didn't exist."""
    org_a_id, org_b_id = two_orgs
    student_code = f"SV_{uuid.uuid4().hex[:8]}"
    _insert_student_as(app_engine, org_a_id, student_code)

    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_b_id)})
        rows = conn.execute(
            text("SELECT id FROM students WHERE student_code = :code"), {"code": student_code}
        ).fetchall()
    assert rows == [], "RLS FAILED: tenant B's session could see tenant A's student row"

    # Sanity: the SAME row IS visible to the correct tenant, proving the
    # emptiness above is real isolation, not e.g. the insert itself failing.
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_a_id)})
        rows = conn.execute(
            text("SELECT id FROM students WHERE student_code = :code"), {"code": student_code}
        ).fetchall()
    assert len(rows) == 1


def test_cross_tenant_update_affects_zero_rows(app_engine, two_orgs):
    org_a_id, org_b_id = two_orgs
    student_code = f"SV_{uuid.uuid4().hex[:8]}"
    _insert_student_as(app_engine, org_a_id, student_code)

    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_b_id)})
        result = conn.execute(
            text("UPDATE students SET full_name = 'Hacked' WHERE student_code = :code"),
            {"code": student_code},
        )
        assert result.rowcount == 0, "RLS FAILED: tenant B's session updated tenant A's student row"


def test_cross_tenant_delete_affects_zero_rows(app_engine, two_orgs):
    """Integration gate Step 8: University B must not be able to DELETE
    University A's tenant-owned data — completes the read/insert/update
    coverage above with the one CRUD operation this file didn't yet test
    directly (only used internally for fixture teardown)."""
    org_a_id, org_b_id = two_orgs
    student_code = f"SV_{uuid.uuid4().hex[:8]}"
    _insert_student_as(app_engine, org_a_id, student_code)

    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_b_id)})
        result = conn.execute(text("DELETE FROM students WHERE student_code = :code"), {"code": student_code})
        assert result.rowcount == 0, "RLS FAILED: tenant B's session deleted tenant A's student row"

    # Sanity: the row still exists for the correct tenant.
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_a_id)})
        rows = conn.execute(
            text("SELECT id FROM students WHERE student_code = :code"), {"code": student_code}
        ).fetchall()
    assert len(rows) == 1


def test_cross_tenant_insert_rejected_by_with_check(app_engine, two_orgs):
    """WITH CHECK, not just USING — a session scoped to org B must not be
    able to INSERT a row that claims to belong to org A."""
    from sqlalchemy.exc import DBAPIError

    org_a_id, org_b_id = two_orgs
    with pytest.raises(DBAPIError, match="row-level security"):
        with app_engine.begin() as conn:
            conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_b_id)})
            conn.execute(
                text(
                    "INSERT INTO students (organization_id, student_code, full_name, is_active, created_at, updated_at) "
                    "VALUES (:org_id, :code, 'Attacker', true, now(), now())"
                ),
                {"org_id": org_a_id, "code": f"INJECT_{uuid.uuid4().hex[:8]}"},
            )


def test_unscoped_session_sees_nothing(app_engine, two_orgs):
    """If application code forgets to call tenant_session_scope() at all (no
    app.organization_id set for the session), the fail-closed behavior must
    be zero rows, not an error and not all tenants' rows."""
    org_a_id, _org_b_id = two_orgs
    student_code = f"SV_{uuid.uuid4().hex[:8]}"
    _insert_student_as(app_engine, org_a_id, student_code)

    with app_engine.begin() as conn:
        # No SET LOCAL app.organization_id at all this time.
        rows = conn.execute(
            text("SELECT id FROM students WHERE student_code = :code"), {"code": student_code}
        ).fetchall()
    assert rows == [], "RLS FAILED: an unscoped session (no app.organization_id set) saw tenant data"


def test_superuser_connection_is_not_protected_by_rls():
    """Documents, with a real assertion (not just a comment), exactly why
    DATABASE_URL (the schema-owner/superuser role) must never be the role the
    running application connects as in production."""
    from dss.db.session import get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    engine = get_engine()
    with engine.connect() as conn:
        is_super = conn.execute(text("SELECT usesuper FROM pg_user WHERE usename = current_user")).scalar_one()
    assert is_super is True, (
        "DATABASE_URL's role is not a superuser in this environment — good for production, "
        "but this test's own assumption (that DATABASE_URL is the unrestricted schema-owner "
        "role, separate from DATABASE_APP_ROLE_URL) no longer holds; re-check test setup."
    )
