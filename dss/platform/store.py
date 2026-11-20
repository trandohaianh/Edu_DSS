"""Transactional storage for the classroom and programme platform.

SQLite is a local development store. PostgreSQL uses the existing configured
engine and migrated schema; it never silently falls back or creates tables.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
import threading

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from dss.core.data_root import get_data_root
from dss.core.runtime_mode import is_production
from dss.platform.models import AuditEvent, PlatformBase

_engines = {}
_engine_lock = threading.Lock()


def get_platform_engine():
    mode = os.environ.get("EDUDSS_PLATFORM_STORE", "local").strip().lower()
    if mode not in {"local", "postgres"}:
        raise RuntimeError("EDUDSS_PLATFORM_STORE must be local or postgres.")
    if is_production() and mode != "postgres":
        raise RuntimeError("Production classroom storage requires EDUDSS_PLATFORM_STORE=postgres.")
    if mode == "postgres":
        from dss.db.session import get_engine
        engine = get_engine()
        if engine.dialect.name != "postgresql":
            raise RuntimeError("The configured platform database must be PostgreSQL.")
        return engine
    path = (get_data_root() / "learning_platform.sqlite3").resolve()
    with _engine_lock:
        key = str(path)
        if key not in _engines:
            path.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(
                "sqlite:///" + path.as_posix(),
                connect_args={"check_same_thread": False, "timeout": 30},
                future=True,
            )
            @event.listens_for(engine, "connect")
            def configure_connection(connection, record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
            PlatformBase.metadata.create_all(engine)
            _engines[key] = engine
        return _engines[key]


def reset_platform_engines():
    with _engine_lock:
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()


def _lock_id(kind, scope):
    return int.from_bytes(hashlib.blake2b(f"edudss-platform:{kind}:{scope}".encode(), digest_size=8).digest(), "big", signed=True)


@contextmanager
def platform_session(school_id=None, *, write=False, program_id=None, actor=None):
    engine = get_platform_engine()
    with Session(engine, expire_on_commit=False) as session:
        try:
            if engine.dialect.name == "sqlite":
                if write:
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                settings = {
                    "app.organization_id": str(school_id or ""),
                    "app.program_id": str(program_id or ""),
                    "app.actor_username": actor.username if actor is not None else "",
                    "app.principal_school_id": actor.school_id if actor is not None else "",
                    "app.actor_role": actor.role if actor is not None else "",
                    "app.platform_operator": "true" if actor is not None and actor.role == "Platform Admin" else "false",
                }
                for name, value in settings.items():
                    session.execute(text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value})
                if write:
                    # Global provisioning uses a stable registry key. When both
                    # scopes exist every writer acquires programme before school.
                    if program_id is not None:
                        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_id("program", program_id)})
                    if school_id is not None:
                        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_id("school", school_id)})
                    if program_id is None and school_id is None:
                        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_id("registry", "global")})
            yield session
            if write:
                session.commit()
            else:
                session.rollback()
        except BaseException:
            session.rollback()
            raise


def audit(session, actor, action, entity_id, *, school_id=None, program_id=None, details=None):
    row = AuditEvent(
        school_id=str(school_id) if school_id is not None else None,
        program_id=str(program_id) if program_id is not None else None,
        actor=f"{actor.school_id}:{actor.username}", action=action,
        entity_id=str(entity_id), details=dict(details or {}),
    )
    session.add(row)
    return row
