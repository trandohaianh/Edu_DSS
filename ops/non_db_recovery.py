"""Non-database recovery inventory (Workstream D, §4.1).

Phase 13 (`ops/backup_recovery.py`) already covers PostgreSQL backup/
restore/verify — real `pg_dump`/checksum/manifest, genuinely tested. This
module covers what that one does NOT: everything else needed to
reconstruct a working deployment — model artifacts, datasets, CMS source
references, application version, dependency manifest, and Alembic head —
coordinated into ONE manifest alongside a reference to the matching DB
backup (never a copy of the DB backup itself; this module never touches
PostgreSQL).

Deliberately NOT covered (do not claim otherwise): plaintext secrets/
credentials are NEVER included in this manifest or copied anywhere by
this module — `.env` files, API keys, and connector `credential_reference`
values are excluded by construction (only file paths and checksums of the
non-secret artifact directories listed in `NON_DB_ARTIFACT_DIRS` are
walked; nothing under a name matching `SECRET_EXCLUDE_PATTERNS` is
included even if it appears there).
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ops.backup_recovery import checksum

# Relative to the app's data root (dss.core.data_root.get_data_root()).
# "logs" is deliberately excluded — operational logs are not required to
# reconstruct a deployment and may incidentally contain request metadata.
NON_DB_ARTIFACT_DIRS = (
    "models",
    "datasets",
    "raw_data",
    "processed_data",
    "training_data",
    "evaluation_data",
    "metadata",
    "embeddings",
)

SECRET_EXCLUDE_PATTERNS = ("*.env", "*.pem", "*.key", "*secret*", "*credential*")


def _is_excluded(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name.lower(), pat) for pat in SECRET_EXCLUDE_PATTERNS)


def _get_code_commit() -> Optional[str]:
    # Reuses the exact same best-effort resolution Workstream C's ML
    # provenance already implements (env var override for a Docker image
    # with no .git directory, falling back to a real dev-checkout lookup).
    from dss.services.ml_provenance import get_code_commit

    return get_code_commit()


def _alembic_head(app_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]
    except Exception:
        pass
    return None


def _requirements_checksum(app_root: Path) -> Optional[str]:
    req = app_root / "requirements.txt"
    return checksum(req) if req.exists() else None


def build_manifest(
    data_root: Path,
    app_root: Path,
    db_backup_manifest: Optional[Path] = None,
    backup_id: Optional[str] = None,
) -> dict[str, Any]:
    """Walks the non-DB artifact directories under `data_root`, computes a
    SHA-256 checksum per file (reusing
    ops.backup_recovery.checksum — the exact same hash algorithm Phase 13's
    DB backup already uses, for one consistent verification story), and
    combines everything with application/schema provenance into one
    coordinated manifest. Does not copy any file — this is an inventory
    with integrity checksums, not a second copy of the data (see module
    docstring's non-goals)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_id = backup_id or f"nondb-{stamp}"

    artifacts: dict[str, list[dict[str, Any]]] = {}
    total_files = 0
    total_bytes = 0
    for rel_dir in NON_DB_ARTIFACT_DIRS:
        directory = data_root / rel_dir
        if not directory.exists():
            artifacts[rel_dir] = []
            continue
        entries = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink() or _is_excluded(path):
                continue
            entries.append(
                {
                    "path": str(path.relative_to(data_root)).replace("\\", "/"),
                    "size_bytes": path.stat().st_size,
                    "sha256": checksum(path),
                }
            )
            total_files += 1
            total_bytes += path.stat().st_size
        artifacts[rel_dir] = entries

    manifest = {
        "backup_id": backup_id,
        "timestamp_utc": stamp,
        "application_commit": _get_code_commit(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "alembic_head": _alembic_head(app_root),
        "dependency_manifest_sha256": _requirements_checksum(app_root),
        "db_backup_manifest_reference": str(db_backup_manifest) if db_backup_manifest else None,
        "artifact_directories": artifacts,
        "total_files": total_files,
        "total_bytes": total_bytes,
    }
    return manifest


def write_manifest(manifest: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as f:
        json.dump(manifest, f, sort_keys=True, indent=2)
    return destination


def verify_manifest(manifest_path: Path, data_root: Path) -> dict[str, Any]:
    """Re-checksums every file the manifest references and compares.
    Returns a result dict — never raises for a mismatch (that IS the
    result being reported), only for a structurally unreadable manifest."""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    mismatches: list[dict[str, str]] = []
    missing: list[str] = []
    verified_count = 0
    for rel_dir, entries in manifest.get("artifact_directories", {}).items():
        for entry in entries:
            full_path = data_root / entry["path"]
            if not full_path.exists():
                missing.append(entry["path"])
                continue
            actual = checksum(full_path)
            if actual != entry["sha256"]:
                mismatches.append({"path": entry["path"], "expected": entry["sha256"], "actual": actual})
                continue
            verified_count += 1

    status = "VERIFIED" if not mismatches and not missing else "CORRUPTED_OR_INCOMPLETE"
    return {
        "status": status,
        "verified_count": verified_count,
        "mismatches": mismatches,
        "missing": missing,
        "total_expected": sum(len(v) for v in manifest.get("artifact_directories", {}).values()),
    }
