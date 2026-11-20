"""Engine/session factory — resolves the connection string from environment
variables ONLY, never hard-coded (Phase 1 explicit requirement).

Resolution order (first match wins):
1. DATABASE_URL (full SQLAlchemy URL, e.g. for a managed/cloud Postgres)
2. DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD (already documented in .env.example)

If neither is set, `get_engine()` raises — callers must handle this (the app
does not currently require Postgres to run; see PHASE1_REPORT.md).

Row Level Security (merged in from a second Phase 1 attempt found in this repo
— see PHASE1_REPORT.md): every tenant-scoped table has a `tenant_isolation`
RLS policy (migration `cbae9b411ed5`) keyed on the Postgres session variable
`app.organization_id`. `tenant_session_scope()` below sets that variable via
`SET LOCAL` (transaction-scoped, cleared automatically at commit/rollback) at
the start of every transaction it opens, and MUST be used instead of the
plain `session_scope()` for any query that touches tenant-scoped data.

CRITICAL: RLS is bypassed entirely by a PostgreSQL superuser or by the table
owner (unless FORCE ROW LEVEL SECURITY is set, which this migration does —
but a *superuser* bypasses RLS no matter what). The role the application
connects as (DB_USER / the credentials in DATABASE_URL) MUST be a
non-superuser role in any real deployment for this to provide a real
guarantee — see docker-compose.yml's `postgres` service, which uses whatever
DB_USER is provided and does not itself create a restricted role; a
deployment-time setup step (or a future migration) must create one.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _resolve_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    host = os.environ.get("DB_HOST")
    name = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD", "")
    port = os.environ.get("DB_PORT", "5432")

    if not (host and name and user):
        raise RuntimeError(
            "No PostgreSQL connection configured. Set DATABASE_URL, or all of "
            "DB_HOST/DB_NAME/DB_USER (DB_PASSWORD/DB_PORT optional), in the "
            "environment or .env — see .env.example. No credentials are "
            "hard-coded in this codebase by design."
        )
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_resolve_database_url(), pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Real transaction boundary: commits on success, rolls back on any
    exception, always closes — the pattern every repository method should use."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def tenant_session_scope(organization_id: int) -> Iterator[Session]:
    """Like `session_scope()`, but additionally scopes the transaction to one
    tenant via Postgres RLS (`SET LOCAL app.organization_id = ...`). Use this
    — never plain `session_scope()` — for any query touching a tenant-scoped
    table, so a forgotten `WHERE organization_id = ...` in application code
    fails closed (returns/affects zero rows) instead of leaking another
    tenant's data."""
    if not isinstance(organization_id, int):
        raise TypeError(f"organization_id must be int, got {type(organization_id)!r}")
    session = get_session_factory()()
    try:
        session.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(organization_id)})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_database_configured() -> bool:
    """Cheap check (no connection attempt) — used by callers that must not
    crash when Postgres isn't configured (this phase's app still runs on the
    existing JSON storage by default)."""
    if os.environ.get("DATABASE_URL"):
        return True
    return bool(os.environ.get("DB_HOST") and os.environ.get("DB_NAME") and os.environ.get("DB_USER"))


def reset_engine_for_tests() -> None:
    """Test-only: force re-resolution of the connection string (e.g. after
    monkeypatching env vars) and dispose the old engine's pool."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
