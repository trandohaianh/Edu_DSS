"""Real tests for Workstream D's non-DB recovery manifest (§4.1) — actual
files on disk, actual SHA-256 checksums, actual corruption detection. No
database required."""

from __future__ import annotations

from pathlib import Path

from ops.non_db_recovery import build_manifest, verify_manifest, write_manifest


def _make_fake_data_root(tmp_path: Path) -> Path:
    data_root = tmp_path / "data_warehouse"
    (data_root / "models").mkdir(parents=True)
    (data_root / "datasets").mkdir(parents=True)
    (data_root / "models" / "train_abc123.joblib").write_bytes(b"fake model bytes for testing")
    (data_root / "datasets" / "ds_001_data.json").write_text('{"rows": 100}', encoding="utf-8")
    # A secret-looking file must NEVER end up in the manifest.
    (data_root / "models" / "credential_leak.secret").write_text("this-should-never-be-checksummed", encoding="utf-8")
    return data_root


def test_manifest_includes_real_files_and_checksums(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    manifest = build_manifest(data_root, app_root=Path(__file__).resolve().parents[1])

    all_paths = [e["path"] for entries in manifest["artifact_directories"].values() for e in entries]
    assert any("train_abc123.joblib" in p for p in all_paths)
    assert any("ds_001_data.json" in p for p in all_paths)
    assert manifest["total_files"] == 2
    assert manifest["python_version"]


def test_manifest_never_includes_secret_looking_files(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    manifest = build_manifest(data_root, app_root=Path(__file__).resolve().parents[1])

    all_paths = [e["path"] for entries in manifest["artifact_directories"].values() for e in entries]
    assert not any("secret" in p.lower() for p in all_paths)


def test_verify_manifest_succeeds_when_nothing_changed(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    manifest = build_manifest(data_root, app_root=Path(__file__).resolve().parents[1])
    manifest_path = write_manifest(manifest, tmp_path / "manifest.json")

    result = verify_manifest(manifest_path, data_root)
    assert result["status"] == "VERIFIED"
    assert result["mismatches"] == []
    assert result["missing"] == []
    assert result["verified_count"] == 2


def test_verify_manifest_detects_corruption(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    manifest = build_manifest(data_root, app_root=Path(__file__).resolve().parents[1])
    manifest_path = write_manifest(manifest, tmp_path / "manifest.json")

    # Corrupt the artifact AFTER the manifest was taken.
    (data_root / "models" / "train_abc123.joblib").write_bytes(b"CORRUPTED - different content entirely")

    result = verify_manifest(manifest_path, data_root)
    assert result["status"] == "CORRUPTED_OR_INCOMPLETE"
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["path"].endswith("train_abc123.joblib")
    assert result["mismatches"][0]["expected"] != result["mismatches"][0]["actual"]


def test_verify_manifest_detects_missing_file(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    manifest = build_manifest(data_root, app_root=Path(__file__).resolve().parents[1])
    manifest_path = write_manifest(manifest, tmp_path / "manifest.json")

    (data_root / "datasets" / "ds_001_data.json").unlink()

    result = verify_manifest(manifest_path, data_root)
    assert result["status"] == "CORRUPTED_OR_INCOMPLETE"
    assert any(p.endswith("ds_001_data.json") for p in result["missing"])


def test_manifest_records_alembic_head_and_dependency_checksum(tmp_path):
    data_root = _make_fake_data_root(tmp_path)
    app_root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(data_root, app_root=app_root)

    # Real Alembic head from the real migrations directory (no DB needed —
    # `alembic heads` only reads the version files on disk).
    assert manifest["alembic_head"] is not None
    assert len(manifest["alembic_head"]) > 0
    assert manifest["dependency_manifest_sha256"] is not None
