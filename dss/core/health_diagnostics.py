"""Liveness and readiness probes without paid calls or secret-bearing output."""

from __future__ import annotations

import os
from pathlib import Path

from dss.core.observability import observe


def liveness() -> dict:
    """A process-level indication only; it does not assert dependency health."""
    return {"status": "alive"}


def postgres_diagnostic() -> dict:
    from dss.db.session import get_engine, is_database_configured

    if not is_database_configured():
        return {"status": "not_configured", "required": False}
    try:
        from sqlalchemy import text

        with observe("db.health", backend="postgresql"):
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        return {"status": "ready", "required": True}
    except Exception:
        return {"status": "unavailable", "required": True}


def pgvector_diagnostic() -> dict:
    if not (os.environ.get("PGVECTOR_URL") or os.environ.get("EDUDSS_REQUIRE_PGVECTOR") == "1"):
        return {"status": "not_required", "required": False}
    try:
        from sqlalchemy import create_engine, text

        from dss.db.session import get_engine

        vector_url = os.environ.get("PGVECTOR_URL")
        engine = create_engine(vector_url, pool_pre_ping=True) if vector_url else get_engine()
        try:
            with observe("db.pgvector_health", backend="pgvector"):
                with engine.connect() as conn:
                    present = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
        finally:
            if vector_url:
                engine.dispose()
        return {"status": "ready" if present else "unavailable", "required": True}
    except Exception:
        return {"status": "unavailable", "required": True}


def ai_configuration_diagnostic() -> dict:
    configured = any(
        os.environ.get(key)
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "HF_TOKEN")
    )
    return {"status": "configured" if configured else "not_configured", "required": False}


def model_artifact_diagnostic() -> dict:
    from dss.core.data_root import get_data_root

    path = Path(get_data_root()) / "models"
    try:
        available = path.is_dir() and any(path.iterdir())
    except OSError:
        available = False
    return {"status": "available" if available else "not_available", "required": False}


def privacy_key_diagnostic() -> dict:
    """C1.1: in production the keyed pseudonymization secret is REQUIRED (fail closed).
    Reports only presence/validity — never the key or any part of it."""
    from dss.core.runtime_mode import is_production

    required = is_production()
    try:
        from dss.security.pseudonymization import pseudonymize

        pseudonymize("readiness-probe")
        return {"status": "ready", "required": required}
    except Exception:
        return {"status": "not_configured", "required": required}


def migration_diagnostic() -> dict:
    """C1.2: the database schema must be exactly at this code's Alembic head. Serving
    traffic against an older (or newer, unknown) schema is not safe."""
    from dss.db.session import is_database_configured

    if not is_database_configured():
        return {"status": "not_configured", "required": False}
    try:
        from dss.db.schema_contract import schema_report
        from dss.db.session import get_engine

        report = schema_report(get_engine())
        return {
            "status": "ready" if report["compatible"] else "incompatible",
            "required": True,
            "database_revision": report["database_revision"],
            "expected_head": report["expected_head"],
        }
    except Exception:
        return {"status": "unavailable", "required": True}


def production_configuration_diagnostic() -> dict:
    """C1.2: in production the environment contract must be complete (values never reported)."""
    from dss.core.runtime_mode import is_production

    if not is_production():
        return {"status": "ready", "required": False}
    missing = [
        name
        for name in ("DATABASE_URL", "EDUDSS_ORGANIZATION_ID", "EDUDSS_PSEUDONYM_KEY")
        if not os.environ.get(name, "").strip()
    ]
    return {"status": "ready" if not missing else "incomplete", "required": True, "missing": missing}


def readiness() -> dict:
    """Only configured required dependencies can make readiness false. Optional external
    AI providers never do: deterministic EduDSS stays ready without them."""
    checks = {
        "application": {"status": "ready", "required": True},
        "configuration": production_configuration_diagnostic(),
        "postgresql": postgres_diagnostic(),
        "pgvector": pgvector_diagnostic(),
        "migrations": migration_diagnostic(),
        "ai_configuration": ai_configuration_diagnostic(),
        "model_artifacts": model_artifact_diagnostic(),
        "privacy_key": privacy_key_diagnostic(),
    }
    ready = all(not value["required"] or value["status"] == "ready" for value in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}
