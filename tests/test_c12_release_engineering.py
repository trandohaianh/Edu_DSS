"""C1.2 release engineering: schema contract, release identity, operator endpoints,
readiness semantics, migration pre-check, release manifest verification, release-gate
exit codes, and the artifact/deploy contracts. No network, no Docker, no provider keys."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ schema contract
def _heads_by_scanning_migration_files() -> set[str]:
    """Independent derivation: revisions that no other migration names as down_revision."""
    revisions, parents = set(), set()
    for path in (APP / "dss" / "db" / "migrations" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r"^revision\s*(?::\s*str)?\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M)
        down = re.search(r"^down_revision\s*(?::[^=]+)?=\s*(.+)$", text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.update(re.findall(r"['\"]([0-9a-f]+)['\"]", down.group(1)))
    return revisions - parents


def test_schema_contract_head_is_derived_from_the_migration_graph():
    from dss.db import schema_contract

    assert set(schema_contract.expected_heads()) == _heads_by_scanning_migration_files()
    assert len(schema_contract.expected_heads()) == 1
    assert schema_contract.expected_head() == schema_contract.expected_heads()[0]


def test_schema_contract_tables_come_from_metadata():
    from dss.db import schema_contract
    from dss.db.base import Base

    tables = schema_contract.expected_tables()
    assert "alembic_version" in tables
    assert set(Base.metadata.tables) <= tables
    from dss.platform.models import PlatformBase

    assert tables == frozenset(set(Base.metadata.tables) | set(PlatformBase.metadata.tables) | {"alembic_version"})


def _strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def test_no_hard_coded_schema_snapshot_in_ci_or_backup_test():
    backup_test = (APP / "tests" / "test_backup_recovery_integration.py").read_text(encoding="utf-8")
    code = _strip_comments(backup_test)
    assert not re.search(r"(==|\[)\s*['\"]797f72d1c666['\"]", code)
    assert "== 27" not in code
    assert "schema_contract" in backup_test

    # The release-gate workflow lives at the monorepo root (one level above app/).
    # The standalone Edu_DSS repository does not ship it, so that half is skipped there.
    candidates = [
        APP.parent / ".github" / "workflows" / "edudss-release-gate.yml",
        APP / ".github" / "workflows" / "edudss-release-gate.yml",
    ]
    workflow_path = next((c for c in candidates if c.is_file()), None)
    if workflow_path is None:
        pytest.skip("edudss-release-gate.yml only exists in the monorepo layout")
    workflow = workflow_path.read_text(encoding="utf-8")
    code = _strip_comments(workflow)
    assert not re.search(r"(==|\[)\s*['\"]797f72d1c666['\"]", code)
    assert "== 27" not in code
    assert "ops.migration_check" in workflow


def test_schema_report_flags_empty_and_stale_databases(monkeypatch):
    from dss.db import schema_contract as sc

    head = list(sc.expected_heads())
    monkeypatch.setattr(sc, "database_tables", lambda engine: set())
    monkeypatch.setattr(sc, "database_revisions", lambda engine: [])
    empty = sc.schema_report(object())
    assert empty["compatible"] is False and empty["at_head"] is False
    assert set(empty["missing_tables"]) == set(sc.expected_tables())

    monkeypatch.setattr(sc, "database_tables", lambda engine: set(sc.expected_tables()))
    monkeypatch.setattr(sc, "database_revisions", lambda engine: ["0000deadbeef"])
    stale = sc.schema_report(object())
    assert stale["compatible"] is False and stale["missing_tables"] == []

    monkeypatch.setattr(sc, "database_revisions", lambda engine: head)
    ok = sc.schema_report(object())
    assert ok["compatible"] is True and ok["at_head"] is True
    sc.assert_schema_matches(object())


# ------------------------------------------------------------------ release identity
SECRETISH = re.compile(r"(sk-|gsk_|AIza|hf_|password|postgresql\+|://[^/]*@|[A-Za-z]:\\|/home/|/Users/)", re.I)


def test_release_identity_is_canonical_and_contains_no_secrets(monkeypatch):
    monkeypatch.setenv("EDUDSS_GIT_SHA", "a" * 40)
    monkeypatch.setenv("EDUDSS_BUILD_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:secretpw@db:5432/x")
    from dss.core import release

    release._git_sha.cache_clear()
    ident = release.release_identity()
    version = (APP / "VERSION").read_text(encoding="utf-8").strip()
    assert ident["version"] == version
    assert re.fullmatch(r"\d+\.\d+\.\d+-rc\.\d+", version), "C1.2 ships a release candidate, not a final 1.0.0"
    assert ident["release_channel"] == "release-candidate"
    assert ident["git_sha"] == "a" * 40
    assert ident["build_time"] == "2026-01-01T00:00:00Z"
    from dss.db.schema_contract import expected_heads

    assert ident["alembic_head"] == list(expected_heads())
    lock = APP / "requirements.lock.txt"
    assert ident["dependency_lock"] == "sha256:" + hashlib.sha256(lock.read_bytes()).hexdigest()
    assert ident["rag_config_version"].startswith("ragcfg-")
    assert ident["config_schema_version"]
    blob = json.dumps(ident)
    assert not SECRETISH.search(blob), blob
    assert "secretpw" not in blob
    release._git_sha.cache_clear()


def test_rag_config_version_is_stable_and_sensitive_to_config(monkeypatch):
    from dss.core import release

    first = release.rag_config_version()
    assert first == release.rag_config_version()
    monkeypatch.setattr(release, "EMBEDDING_DIM", 768)
    assert release.rag_config_version() != first


# ------------------------------------------------------------------ readiness semantics
def _stub_readiness(monkeypatch, **overrides):
    from dss.core import health_diagnostics as hd

    ready = {"status": "ready", "required": True}
    defaults = {
        "production_configuration_diagnostic": {"status": "ready", "required": False},
        "postgres_diagnostic": ready,
        "pgvector_diagnostic": ready,
        "migration_diagnostic": ready,
        "ai_configuration_diagnostic": {"status": "not_configured", "required": False},
        "model_artifact_diagnostic": {"status": "not_available", "required": False},
        "privacy_key_diagnostic": {"status": "ready", "required": False},
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(hd, name, lambda value=value: dict(value))
    return hd


def test_readiness_does_not_depend_on_optional_ai_providers(monkeypatch):
    hd = _stub_readiness(monkeypatch)
    result = hd.readiness()
    assert result["status"] == "ready"
    assert result["checks"]["ai_configuration"] == {"status": "not_configured", "required": False}


@pytest.mark.parametrize(
    "check,value",
    [
        ("migration_diagnostic", {"status": "incompatible", "required": True}),
        (
            "production_configuration_diagnostic",
            {"status": "incomplete", "required": True, "missing": ["EDUDSS_PSEUDONYM_KEY"]},
        ),
        ("privacy_key_diagnostic", {"status": "not_configured", "required": True}),
        ("postgres_diagnostic", {"status": "unavailable", "required": True}),
    ],
)
def test_readiness_fails_on_required_dependency(monkeypatch, check, value):
    hd = _stub_readiness(monkeypatch, **{check: value})
    assert hd.readiness()["status"] == "not_ready"


def test_production_configuration_reports_names_only(monkeypatch):
    from dss.core import health_diagnostics as hd

    monkeypatch.setenv("EDUDSS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:pw@h/db")
    monkeypatch.delenv("EDUDSS_ORGANIZATION_ID", raising=False)
    monkeypatch.delenv("EDUDSS_PSEUDONYM_KEY", raising=False)
    result = hd.production_configuration_diagnostic()
    assert result["status"] == "incomplete" and result["required"] is True
    assert result["missing"] == ["EDUDSS_ORGANIZATION_ID", "EDUDSS_PSEUDONYM_KEY"]
    assert "pw" not in json.dumps(result)


def test_migration_diagnostic_detects_incompatible_schema(monkeypatch):
    from dss.core import health_diagnostics as hd
    from dss.db import schema_contract, session

    monkeypatch.setattr(session, "is_database_configured", lambda: True)
    monkeypatch.setattr(session, "get_engine", lambda: object())
    monkeypatch.setattr(
        schema_contract,
        "schema_report",
        lambda engine: {"compatible": False, "database_revision": ["old"], "expected_head": ["new"]},
    )
    assert hd.migration_diagnostic()["status"] == "incompatible"
    monkeypatch.setattr(
        schema_contract,
        "schema_report",
        lambda engine: {"compatible": True, "database_revision": ["new"], "expected_head": ["new"]},
    )
    assert hd.migration_diagnostic()["status"] == "ready"


def test_release_gate_retries_on_transient_postgres_startup_errors(monkeypatch):
    from tools.release_gate import ThrowawayPostgres

    calls = {"count": 0}

    def fake_run(cmd, env=None, cwd=None, timeout=None, capture=False):
        if cmd[:2] == ["docker", "logs"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        assert cmd[:3] == ["docker", "exec", "stub-pg"]
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(cmd, 1, "", "server closed the connection unexpectedly")
        return subprocess.CompletedProcess(cmd, 0, "1\n", "")

    monkeypatch.setattr("tools.release_gate.run", fake_run)
    pg = ThrowawayPostgres()
    pg.name = "stub-pg"
    pg.psql("SELECT 1", db="postgres")
    assert calls["count"] == 2


# ------------------------------------------------------------------ HTTP endpoints
@pytest.fixture()
def health_server(monkeypatch):
    from dss.core import health_server as hs

    monkeypatch.setattr(hs, "_CACHE_SECONDS", 0)
    hs._cache.clear()
    server = hs.serve(port=0, host="127.0.0.1")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield hs, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read())


def test_livez_reflects_only_the_ui_process(health_server, monkeypatch):
    hs, base = health_server
    monkeypatch.setattr(hs, "streamlit_alive", lambda: True)
    from dss.core import health_diagnostics

    monkeypatch.setattr(health_diagnostics, "readiness", lambda: pytest.fail("livez must not check dependencies"))
    code, headers, body = _get(base + "/livez")
    assert code == 200 and body["status"] == "alive"
    assert headers.get("Cache-Control") == "no-store"
    monkeypatch.setattr(hs, "streamlit_alive", lambda: False)
    assert _get(base + "/livez")[0] == 503


def test_readyz_status_codes(health_server, monkeypatch):
    hs, base = health_server
    from dss.core import health_diagnostics

    monkeypatch.setattr(hs, "streamlit_alive", lambda: True)
    monkeypatch.setattr(health_diagnostics, "readiness", lambda: {"status": "ready", "checks": {}})
    code, _, body = _get(base + "/readyz")
    assert code == 200 and body["status"] == "ready" and "environment" in body
    hs._cache.clear()
    monkeypatch.setattr(
        health_diagnostics,
        "readiness",
        lambda: {"status": "not_ready", "checks": {"migrations": {"status": "incompatible"}}},
    )
    assert _get(base + "/readyz")[0] == 503
    hs._cache.clear()
    monkeypatch.setattr(health_diagnostics, "readiness", lambda: {"status": "ready", "checks": {}})
    monkeypatch.setattr(hs, "streamlit_alive", lambda: False)
    code, _, body = _get(base + "/readyz")
    assert code == 503 and body["checks"]["ui"]["status"] == "unavailable"


def test_version_endpoint_and_unknown_route(health_server, monkeypatch):
    hs, base = health_server
    from dss.core import release

    monkeypatch.setattr(release, "runtime_state", lambda: {"database": None})
    release.release_identity()  # warm the heavy dss.config import outside the HTTP timeout
    code, _, body = _get(base + "/version")
    assert code == 200 and body["release"]["product"] == "EduDSS"
    assert _get(base + "/nope")[0] == 404


def test_probe_cli_exit_codes(health_server, monkeypatch, capsys):
    hs, base = health_server
    monkeypatch.setenv("EDUDSS_HEALTH_PORT", base.rsplit(":", 1)[1])
    monkeypatch.setattr(hs, "streamlit_alive", lambda: True)
    assert hs.main(["probe", "livez"]) == 0
    monkeypatch.setattr(hs, "streamlit_alive", lambda: False)
    assert hs.main(["probe", "livez"]) == 1
    monkeypatch.setenv("EDUDSS_HEALTH_PORT", "1")
    assert hs.main(["probe", "readyz"]) == 1
    assert "unreachable" in capsys.readouterr().out


# ------------------------------------------------------------------ migration pre-check
def _load_tool(name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, APP / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_precheck_refuses_unknown_revision(monkeypatch, capsys):
    from dss.db.schema_contract import expected_heads
    from ops import migration_check as mc

    base = {"expected_head": list(expected_heads()), "missing_tables": [], "unexpected_tables": [], "pending": []}
    monkeypatch.setattr(mc, "status", lambda: {**base, "database_revision": ["ffffffffffff"], "at_head": False})
    assert mc.precheck() == 2
    monkeypatch.setattr(mc, "status", lambda: {**base, "database_revision": [], "at_head": False})
    assert mc.precheck() == 0
    monkeypatch.setattr(mc, "status", lambda: {**base, "database_revision": list(expected_heads()), "at_head": True})
    assert mc.precheck() == 0
    assert '"action": "none"' in capsys.readouterr().out


def test_migration_roundtrip_refused_without_confirmation_or_in_production(monkeypatch):
    from ops import migration_check as mc

    monkeypatch.setattr(mc, "_engine", lambda: pytest.fail("must not connect"))
    assert mc.roundtrip(False) == 2
    monkeypatch.setenv("EDUDSS_ENV", "production")
    assert mc.roundtrip(True) == 2


def test_downgrade_audit_marks_destructive_migrations():
    from ops import migration_check as mc

    audit = mc.pending_revisions([])
    assert audit, "every migration must be listed for an empty database"
    assert any(item["downgrade_destroys_data"] for item in audit)


# ------------------------------------------------------------------ release manifest
def test_release_manifest_verify_detects_mismatch():
    rm = _load_tool("release_manifest")
    release = {
        "version": "1.0.0-rc.1",
        "git_sha": "abc",
        "dependency_lock": "sha256:1",
        "alembic_head": ["h"],
        "config_schema_version": "2",
        "rag_config_version": "ragcfg-1",
    }
    manifest = {"release": release}
    good = {"release": dict(release), "runtime": {"database": {"at_head": True}}}
    assert rm.verify(manifest, good) == []
    wrong_sha = {"release": {**release, "git_sha": "def"}, "runtime": {}}
    assert any(p.startswith("git_sha") for p in rm.verify(manifest, wrong_sha))
    stale_db = {"release": dict(release), "runtime": {"database": {"at_head": False, "database_revision": ["old"]}}}
    assert any("not at release head" in p for p in rm.verify(manifest, stale_db))


# ------------------------------------------------------------------ release gate exit code
def test_release_gate_returns_nonzero_when_a_mandatory_gate_fails(monkeypatch, tmp_path):
    rg = _load_tool("release_gate")

    class FakePG:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(rg, "ThrowawayPostgres", FakePG)
    monkeypatch.setattr(rg, "run", lambda *a, **k: None)
    monkeypatch.setattr(rg, "APP", tmp_path)
    calls = []

    def passing(name):
        def gate(ctx):
            calls.append(name)
            if name == "docker_build":
                ctx["image"] = "edudss:test"
            if name == "container_smoke":
                ctx["app_port"] = 1
            return True, {}

        return gate

    for name in rg.MANDATORY + rg.ADVISORY:
        monkeypatch.setitem(rg.GATES, name, passing(name))
    assert rg.main([]) == 0
    assert calls == rg.MANDATORY + rg.ADVISORY
    monkeypatch.setitem(rg.GATES, "migrations", lambda ctx: (False, {}))
    assert rg.main([]) == 1
    monkeypatch.setitem(rg.GATES, "migrations", passing("migrations"))
    monkeypatch.setitem(rg.GATES, "dependency_audit", lambda ctx: (None, {}))  # advisory, offline
    assert rg.main([]) == 0
    summary = json.loads(sorted((tmp_path / "reports" / "release_gate").glob("release-gate-*.json"))[-1].read_text())
    assert summary["gates"]["dependency_audit"]["status"] == "UNAVAILABLE"


# ------------------------------------------------------------------ artifact contracts
def test_dockerfile_pins_base_by_digest_and_enforces_the_lock():
    dockerfile = (APP / "Dockerfile").read_text(encoding="utf-8")
    base = re.search(r"^FROM\s+(\S+)", dockerfile, re.M).group(1)
    assert re.fullmatch(r"python:3\.11\.\d+-slim-\w+@sha256:[0-9a-f]{64}", base)
    assert "requirements.lock.txt" in dockerfile
    assert "HEALTHCHECK" in dockerfile and "/livez" in dockerfile
    assert "EDUDSS_GIT_SHA" in dockerfile and "org.opencontainers.image.revision" in dockerfile


def test_lock_is_fully_pinned_and_cpu_only():
    lines = [
        l.strip()
        for l in (APP / "requirements.lock.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    assert len(lines) > 50
    assert all(re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[^=\s]+", l) for l in lines), "every entry must be an exact pin"
    names = {l.split("==")[0].lower() for l in lines}
    assert not any(n.startswith(("nvidia-", "triton")) for n in names)
    assert "torch==2.10.0+cpu" in lines
    direct = [
        l
        for l in (APP / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith(("#", "-"))
    ]
    for req in direct:
        name = re.split(r"[<>=!~\[; ]", req.strip(), 1)[0].lower().replace("_", "-")
        assert name in {n.replace("_", "-") for n in names}, f"{name} missing from lock"


def test_production_compose_runs_one_immutable_image_and_never_builds():
    compose = (APP / "deploy" / "production" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "build:" not in compose
    assert compose.count("image: ${EDUDSS_IMAGE:?") == 2  # migrate + app: same artifact
    assert "ops.migration_check precheck" in compose
    deploy = (APP / "deploy" / "production" / "remote_deploy.sh").read_text(encoding="utf-8")
    assert "@sha256:" in deploy and "refusing mutable image reference" in deploy


def test_third_party_notices_cover_the_lock():
    notices = (APP / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for line in (APP / "requirements.lock.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            assert f"| {name} | {version} |" in notices
    assert "- BLOCKED: none" in notices
    lic = _load_tool("license_inventory")
    assert lic.classify("GNU Affero General Public License v3") == "BLOCKED"
    assert lic.classify("GNU General Public License v3 (GPLv3)") == "BLOCKED"
    assert lic.classify("GNU Lesser General Public License v2 or later (LGPLv2+)") == "REVIEW"
    assert lic.classify("MIT") == "ALLOWED"
