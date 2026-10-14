"""Canonical release identity — the ONE place that answers "what exact EduDSS is running?" (C1.2).

Two layers, deliberately separate:

1. `release_identity()` — immutable facts about the BUILD (same for every deployment of
   one image): semantic version (app/VERSION), Git SHA, build time, image reference,
   expected Alembic head, dependency-lock fingerprint, embedding/RAG configuration,
   configuration-schema version. Baked into the image at build time via build args
   (EDUDSS_GIT_SHA, EDUDSS_BUILD_TIME, EDUDSS_IMAGE_REF); in a developer checkout the
   Git SHA is read from git and marked "+dirty" when the tree has local changes.

2. `runtime_state()` — facts about THIS deployment right now: database revision (and
   whether it matches the code), production ML model identifiers, RAG index fingerprint.

Neither contains secrets, credentials, hostnames or filesystem paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

APP_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = APP_ROOT / "VERSION"
LOCK_FILE = APP_ROOT / "requirements.lock.txt"

# Version of the environment-variable contract (dss/core/runtime_mode.py + deploy/production).
# Bump when a required variable is added/renamed so operators can match config to release.
CONFIG_SCHEMA_VERSION = "2"   # 1 = pre-C1.1, 2 = EDUDSS_ENV + EDUDSS_PSEUDONYM_KEY contract

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def app_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0+unknown"
    except OSError:
        return "0.0.0+unknown"


@lru_cache(maxsize=1)
def _git_sha() -> str:
    baked = os.environ.get("EDUDSS_GIT_SHA", "").strip()
    if baked:
        return baked
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=APP_ROOT, capture_output=True,
                             text=True, timeout=5, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=APP_ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _file_fingerprint(path: Path) -> Optional[str]:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def rag_configuration() -> Dict[str, Any]:
    from dss import config as dss_config
    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "chunk_size": getattr(dss_config, "DEFAULT_CHUNK_SIZE", None),
        "chunk_overlap": getattr(dss_config, "DEFAULT_CHUNK_OVERLAP", None),
        "top_k": getattr(dss_config, "RAG_TOP_K_DEFAULT", None),
    }


def rag_config_version() -> str:
    """Stable identifier of how the index is BUILT; changes force a re-index."""
    blob = json.dumps(rag_configuration(), sort_keys=True).encode("utf-8")
    return "ragcfg-" + hashlib.sha256(blob).hexdigest()[:12]


def release_identity() -> Dict[str, Any]:
    from dss.db.schema_contract import expected_heads
    version = app_version()
    return {
        "product": "EduDSS",
        "version": version,
        "release_channel": "release-candidate" if "-rc" in version else ("development" if "+" in version else "release"),
        "git_sha": _git_sha(),
        "build_time": os.environ.get("EDUDSS_BUILD_TIME", "").strip() or "unbuilt (developer checkout)",
        "image": os.environ.get("EDUDSS_IMAGE_REF", "").strip() or None,
        "alembic_head": list(expected_heads()),
        "dependency_lock": _file_fingerprint(LOCK_FILE),
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "rag_config_version": rag_config_version(),
        "ml": {"bundled_models": "none — models are trained per deployment and tracked in the model registry"},
    }


def _production_models() -> Dict[str, str]:
    """{dataset::target -> training_id} of models promoted to production in THIS deployment."""
    try:
        from dss.core.data_root import get_data_root
        path = get_data_root() / "metadata" / "_production_index.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _rag_index_fingerprint(engine) -> Dict[str, Any]:
    from sqlalchemy import text
    org = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    with engine.begin() as conn:
        if org:
            conn.execute(text("SET LOCAL app.organization_id = :o"), {"o": org})
        rows = conn.execute(text(
            "SELECT document_id, COALESCE(content_hash, ''), status FROM rag_documents "
            "WHERE is_current ORDER BY document_id")).fetchall()
    approved = [r for r in rows if r[2] == "APPROVED"]
    digest = hashlib.sha256("|".join(f"{r[0]}:{r[1]}" for r in approved).encode("utf-8")).hexdigest()[:16]
    return {"documents_current": len(rows), "documents_approved": len(approved),
            "approved_fingerprint": f"rag-{digest}" if approved else None}


def runtime_state() -> Dict[str, Any]:
    state: Dict[str, Any] = {"production_models": _production_models(), "database": None, "rag_index": None}
    try:
        from dss.db.session import get_engine, is_database_configured
        if is_database_configured():
            from dss.db.schema_contract import schema_report
            engine = get_engine()
            report = schema_report(engine)
            state["database"] = {k: report[k] for k in ("database_revision", "expected_head", "at_head",
                                                          "missing_tables", "compatible")}
            try:
                state["rag_index"] = _rag_index_fingerprint(engine)
            except Exception:
                state["rag_index"] = {"status": "unavailable"}
    except Exception:
        state["database"] = {"status": "unavailable"}
    return state


def version_document() -> Dict[str, Any]:
    """Machine-readable document for /version and the release manifest check."""
    return {"release": release_identity(), "runtime": runtime_state()}


def display_string() -> str:
    ident = release_identity()
    return f"EduDSS {ident['version']} · {str(ident['git_sha'])[:12]} · DB {','.join(ident['alembic_head'])}"
