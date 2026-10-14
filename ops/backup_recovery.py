"""PostgreSQL custom-format backup and clean-target restore.

Credentials come only from DATABASE_URL / RESTORE_DATABASE_URL. Docker mode
uses the database container's local socket and requires local authentication
to work without a password; it never passes a password to docker's argv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url


class BackupError(Exception):
    pass


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def _url(name: str):
    raw = os.environ.get(name)
    if not raw:
        raise BackupError(f"{name} is required")
    try:
        url = make_url(raw)
    except Exception as exc:
        raise BackupError(f"{name} is invalid") from exc
    if not url.drivername.startswith("postgresql") or not url.database or not url.username:
        raise BackupError(f"{name} must identify a PostgreSQL database and user")
    return url


def _connection(url, docker_container: str | None):
    if docker_container:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", docker_container):
            raise BackupError("Invalid Docker container name")
        # Local socket authentication must be configured inside the DB
        # container. Do not pass PGPASSWORD via docker exec -e / argv.
        return ["docker", "exec", "-i", docker_container], {}, [
            "-U", url.username, "-d", url.database,
        ]
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("RESTORE_DATABASE_URL", None)
    env.setdefault("PGCONNECT_TIMEOUT", "10")
    if url.password:
        env["PGPASSWORD"] = url.password
    else:
        env.pop("PGPASSWORD", None)
    address = ["-h", url.host or "localhost", "-p", str(url.port or 5432),
               "-U", url.username, "-d", url.database]
    return [], env, address


def _run(program: str, url, docker_container: str | None, args: list[str],
         *, input_file=None, output_file=None) -> str:
    prefix, env, address = _connection(url, docker_container)
    cmd = [*prefix, program, *address, *args]
    try:
        result = subprocess.run(
            cmd, stdin=input_file, stdout=output_file or subprocess.PIPE,
            stderr=subprocess.PIPE, env=env or None, check=False,
        )
    except (OSError, ValueError) as exc:
        raise BackupError(f"{program} could not start; check PostgreSQL client tools") from exc
    if result.returncode:
        # Client stderr can contain connection strings or private SQL values.
        raise BackupError(f"{program} failed (exit {result.returncode}); check connection, permissions and target state")
    return result.stdout.decode("utf-8", errors="replace").strip() if output_file is None else ""


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_backup_dir(path: Path) -> Path:
    path = path.expanduser()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise BackupError("Backup directory cannot contain a symlink")
    path = path.resolve()
    if path.exists() and not path.is_dir():
        raise BackupError("Backup directory must be a real directory")
    return path


def backup(directory: Path, docker_container: str | None = None) -> dict:
    url = _url("DATABASE_URL")
    directory = _safe_backup_dir(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{re.sub('[^A-Za-z0-9_-]', '_', url.database)}-{stamp}-{uuid.uuid4().hex[:8]}"
    archive = directory / f"{name}.dump"
    temporary = directory / f".{name}.partial"
    manifest = directory / f"{name}.backup.json"
    started = time.monotonic()
    _emit("backup_started", database=url.database, timestamp=stamp)
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
            _run("pg_dump", url, docker_container,
                 ["--format=custom", "--no-owner"], output_file=out)
        if temporary.stat().st_size == 0:
            raise BackupError("pg_dump produced an empty archive")
        digest = checksum(temporary)
        temporary.replace(archive)
        metadata = {
            "format": "pg_dump_custom", "database": url.database,
            "timestamp_utc": stamp, "archive": archive.name,
            "size_bytes": archive.stat().st_size, "sha256": digest,
        }
        with os.fdopen(os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "w", encoding="utf-8") as out:
            json.dump(metadata, out, sort_keys=True, indent=2)
        _emit("backup_completed", database=url.database, timestamp=stamp,
              size_bytes=metadata["size_bytes"], sha256=digest,
              duration_seconds=round(time.monotonic() - started, 3))
        return metadata
    except Exception:
        temporary.unlink(missing_ok=True)
        if not manifest.exists():
            archive.unlink(missing_ok=True)
        raise


def verify(manifest_path: Path) -> tuple[dict, Path]:
    try:
        if manifest_path.is_symlink():
            raise BackupError("Backup manifest cannot be a symlink")
        manifest_path = manifest_path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise BackupError("Backup manifest is missing or inaccessible") from exc
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        archive_name = metadata["archive"]
        if (not isinstance(archive_name, str) or
                not re.fullmatch(r"[A-Za-z0-9_-]+\.dump", archive_name)):
            raise BackupError("Manifest archive name is unsafe")
        archive = manifest_path.parent / archive_name
        if archive.is_symlink() or not archive.is_file():
            raise BackupError("Backup archive is missing or is a symlink")
        if metadata["format"] != "pg_dump_custom":
            raise BackupError("Unsupported backup format")
        if (not isinstance(metadata["database"], str) or
                not re.fullmatch(r"[A-Za-z0-9_-]+", metadata["database"]) or
                not isinstance(metadata["sha256"], str) or
                not re.fullmatch(r"[a-f0-9]{64}", metadata["sha256"])):
            raise BackupError("Backup manifest metadata is invalid")
        if archive.stat().st_size != metadata["size_bytes"] or checksum(archive) != metadata["sha256"]:
            raise BackupError("Backup checksum or size mismatch")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise BackupError("Backup manifest is invalid") from exc
    _emit("backup_verified", database=metadata["database"],
          size_bytes=metadata["size_bytes"], sha256=metadata["sha256"])
    return metadata, archive


def restore(manifest_path: Path, docker_container: str | None = None) -> None:
    source_url = _url("DATABASE_URL")
    target_url = _url("RESTORE_DATABASE_URL")
    # Refuse matching names even with host aliases or separate hosts. This
    # conservative gate makes accidental in-place restore impossible.
    if source_url.database == target_url.database:
        raise BackupError("Restore target database name must differ from source")
    metadata, archive = verify(manifest_path)
    if metadata["database"] != source_url.database:
        raise BackupError("Backup database identifier does not match DATABASE_URL")
    started = time.monotonic()
    _emit("restore_started", database=target_url.database, source_database=source_url.database)
    # Refuse any existing user tables. The target database must already exist
    # and be empty; this command never drops or creates a database.
    count = _run("psql", target_url, docker_container,
                 ["-At", "-c", "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                  "WHERE c.relkind IN ('r','p') AND n.nspname NOT IN "
                  "('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'"])
    if count != "0":
        raise BackupError("Restore target is not empty")
    with archive.open("rb") as source:
        _run("pg_restore", target_url, docker_container,
             ["--exit-on-error", "--single-transaction", "--no-owner"], input_file=source)
    _emit("restore_completed", database=target_url.database,
          duration_seconds=round(time.monotonic() - started, 3), sha256=metadata["sha256"])


def retention(directory: Path, days: int, dry_run: bool = True) -> list[str]:
    if days < 1:
        raise BackupError("Retention days must be at least 1")
    directory = _safe_backup_dir(directory)
    if not directory.exists():
        return []
    cutoff = time.time() - days * 86400
    selected = []
    for manifest in directory.glob("*.backup.json"):
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_mtime >= cutoff:
            continue
        try:
            metadata, archive = verify(manifest)
        except BackupError:
            continue  # invalid pairs require manual investigation
        if archive.stat().st_mtime >= cutoff:
            continue
        selected.append(manifest.name)
        if not dry_run:
            archive.unlink()
            manifest.unlink()
    _emit("retention_scan", days=days, dry_run=dry_run, selected=selected)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-container", help="DB container with local socket auth and PostgreSQL client tools")
    commands = parser.add_subparsers(dest="command", required=True)
    backup_cmd = commands.add_parser("backup")
    backup_cmd.add_argument("--dir", type=Path, required=True)
    verify_cmd = commands.add_parser("verify")
    verify_cmd.add_argument("--manifest", type=Path, required=True)
    restore_cmd = commands.add_parser("restore")
    restore_cmd.add_argument("--manifest", type=Path, required=True)
    retention_cmd = commands.add_parser("retention")
    retention_cmd.add_argument("--dir", type=Path, required=True)
    retention_cmd.add_argument("--days", type=int, required=True)
    retention_cmd.add_argument("--execute", action="store_true", help="Delete verified expired pairs")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            backup(args.dir, args.docker_container)
        elif args.command == "verify":
            verify(args.manifest)
        elif args.command == "restore":
            restore(args.manifest, args.docker_container)
        else:
            retention(args.dir, args.days, not args.execute)
    except BackupError as exc:
        _emit("operation_failed", reason=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
