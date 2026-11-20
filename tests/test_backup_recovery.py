"""Unit checks for the portable backup entry point; real restore is separate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ops import backup_recovery as br


def test_configuration_requires_postgresql_without_echoing_secret(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(br.BackupError, match="DATABASE_URL is required"):
        br._url("DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///secret")
    with pytest.raises(br.BackupError, match="PostgreSQL"):
        br._url("DATABASE_URL")


def test_native_command_keeps_password_out_of_argv(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://alice:very_private@localhost:5432/example")
    url = br._url("DATABASE_URL")
    prefix, env, address = br._connection(url, None)
    assert prefix == []
    assert env["PGPASSWORD"] == "very_private"
    assert "very_private" not in repr(address)
    assert "example" in address


def test_docker_command_does_not_pass_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://alice:very_private@localhost/example")
    prefix, env, address = br._connection(br._url("DATABASE_URL"), "db_1")
    assert prefix == ["docker", "exec", "-i", "db_1"]
    assert "very_private" not in repr((prefix, env, address))
    with pytest.raises(br.BackupError, match="Invalid Docker"):
        br._connection(br._url("DATABASE_URL"), "db;evil")


def test_backup_checksum_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://alice:private@localhost/example")

    def fake_run(program, url, docker_container, args, **kwargs):
        assert program == "pg_dump"
        kwargs["output_file"].write(b"custom postgres archive")
        return ""

    monkeypatch.setattr(br, "_run", fake_run)
    metadata = br.backup(tmp_path)
    assert metadata["size_bytes"] == 23
    manifest = next(tmp_path.glob("*.backup.json"))
    assert br.verify(manifest)[0] == metadata
    assert metadata["sha256"] == br.checksum(tmp_path / metadata["archive"])
    assert "private" not in json.dumps(metadata)


def test_corrupt_archive_rejected_before_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://alice:private@localhost/source")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://alice:private@localhost/target")
    archive = tmp_path / "fixture.dump"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "fixture.backup.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "pg_dump_custom",
                "database": "source",
                "archive": archive.name,
                "size_bytes": 7,
                "sha256": br.checksum(archive),
            }
        )
    )
    archive.write_bytes(b"corrupt")
    with patch.object(br, "_run") as run:
        with pytest.raises(br.BackupError, match="checksum or size mismatch"):
            br.restore(manifest)
        run.assert_not_called()


def test_restore_refuses_source_and_nonempty_target(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://alice:private@localhost/source")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://alice:private@localhost/source")
    with pytest.raises(br.BackupError, match="must differ"):
        br.restore(tmp_path / "missing.backup.json")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://alice:private@localhost/target")
    archive = tmp_path / "fixture.dump"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "fixture.backup.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "pg_dump_custom",
                "database": "source",
                "archive": archive.name,
                "size_bytes": 7,
                "sha256": br.checksum(archive),
            }
        )
    )
    with patch.object(br, "_run", return_value="1") as run:
        with pytest.raises(br.BackupError, match="not empty"):
            br.restore(manifest)
        assert run.call_count == 1


def test_missing_manifest_and_path_traversal_rejected(tmp_path):
    with pytest.raises(br.BackupError, match="missing"):
        br.verify(tmp_path / "missing.backup.json")
    manifest = tmp_path / "bad.backup.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "pg_dump_custom",
                "database": "source",
                "archive": "../outside.dump",
                "size_bytes": 1,
                "sha256": "x",
            }
        )
    )
    with pytest.raises(br.BackupError, match="unsafe"):
        br.verify(manifest)


def test_retention_dry_run_then_delete_only_verified_pairs(tmp_path, monkeypatch):
    archive = tmp_path / "old.dump"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "old.backup.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "pg_dump_custom",
                "database": "source",
                "archive": archive.name,
                "size_bytes": 7,
                "sha256": br.checksum(archive),
            }
        )
    )
    old = 1000000000
    os.utime(archive, (old, old))
    os.utime(manifest, (old, old))
    outside = tmp_path.parent / "outside.keep"
    outside.write_text("safe")
    assert br.retention(tmp_path, 1, dry_run=True) == [manifest.name]
    assert archive.exists()
    assert br.retention(tmp_path, 1, dry_run=False) == [manifest.name]
    assert not archive.exists() and not manifest.exists()
    assert outside.exists()
    outside.unlink()


def test_subprocess_failure_hides_stderr_secret(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://alice:private@localhost/example")
    monkeypatch.setattr(
        br.subprocess,
        "run",
        lambda *a, **k: br.subprocess.CompletedProcess(a[0], 1, stdout=b"", stderr=b"connection failed private"),
    )
    with pytest.raises(br.BackupError) as error:
        br._run("pg_dump", br._url("DATABASE_URL"), None, ["--format=custom"])
    assert "private" not in str(error.value)
    assert "pg_dump failed" in str(error.value)


def test_invalid_backup_directory_fails_without_creating_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://alice:private@localhost/example")
    invalid = tmp_path / "not_directory"
    invalid.write_text("existing file")
    with pytest.raises(br.BackupError, match="real directory"):
        br.backup(invalid)
    assert list(tmp_path.glob("*.dump")) == []


def test_cli_returns_nonzero_without_credentials(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert br.main(["backup", "--dir", str(tmp_path)]) == 1
    assert "DATABASE_URL is required" in capsys.readouterr().out
