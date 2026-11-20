"""EduDSS release gate — ONE deterministic pre-release entrypoint (C1.2).

    python tools/release_gate.py                      # all mandatory gates
    python tools/release_gate.py --skip docker_build  # e.g. reuse an already-built --image
    python tools/release_gate.py --image edudss:1.0.0-rc.1 --skip docker_build

Every database-touching gate runs against a THROWAWAY pgvector container started by this
script (tmpfs, random port, random passwords, removed at the end) — never a developer or
production database. Test logic is not duplicated: the gate orchestrates the existing
pytest suites and tools. Exit code 0 only if every mandatory gate passes; a JSON summary
is written to reports/release_gate/<timestamp>.json (no secrets).

Mandatory gates (in order):
  secret_scan        tools/secret_scan.py --history
  migrations         empty DB -> alembic upgrade head -> contract verify -> roundtrip
  regression         full pytest suite (E2E excluded) on PostgreSQL + non-superuser RLS role
  backup_restore     tests/test_backup_recovery_integration.py on dedicated source/target DBs
  docker_build       docker build with release identity build-args (lock drift fails the build)
  licenses           tools/license_inventory.py --check (inside the image)
  container_smoke    image + migrated DB, no AI keys: /livez, /readyz, /version, production
                     mode fails closed without the pseudonym key, readiness ok with it
  manifest           release manifest generated from the image and verified against /version
Advisory gates (reported; blocking only per the severity policy in RELEASE_PROCESS.md):
  dependency_audit   pip-audit on requirements.lock.txt (needs network)
  container_scan     Trivy image scan, HIGH/CRITICAL with a fix available (needs network)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
PY = sys.executable
PG_IMAGE = "pgvector/pgvector:pg16"
MANDATORY = [
    "secret_scan",
    "migrations",
    "regression",
    "backup_restore",
    "docker_build",
    "licenses",
    "container_smoke",
    "manifest",
]
ADVISORY = ["dependency_audit", "container_scan"]


def log(msg: str) -> None:
    print(f"[release-gate {dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, env=None, cwd=APP, timeout=None, capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, env=env, timeout=timeout, text=True, capture_output=capture, encoding="utf-8", errors="replace"
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ThrowawayPostgres:
    def __init__(self):
        self.name = f"edudss-gate-pg-{secrets.token_hex(3)}"
        self.port = free_port()
        self.admin_pw = secrets.token_urlsafe(18)
        self.app_pw = secrets.token_urlsafe(18)

    def url(self, db: str, role: str = "gate_admin") -> str:
        pw = self.admin_pw if role == "gate_admin" else self.app_pw
        return f"postgresql+psycopg2://{role}:{pw}@127.0.0.1:{self.port}/{db}"

    def psql(self, sql: str, db: str = "postgres", timeout_seconds: int = 120) -> None:
        deadline = time.monotonic() + timeout_seconds
        last = None
        while time.monotonic() < deadline:
            res = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "psql",
                    "-U",
                    "gate_admin",
                    "-d",
                    db,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-q",
                    "-c",
                    sql,
                ],
                capture=True,
            )
            if res.returncode == 0:
                return
            last = (res.stdout + res.stderr).strip() or f"psql exit={res.returncode}"
            transient = (
                "database system is shutting down" in last
                or "No such file or directory" in last
                or "server closed the connection unexpectedly" in last
                or "terminating connection due to administrator command" in last
                or "connection to server was lost" in last
                or "the database system is starting up" in last
            )
            if not transient:
                break
            time.sleep(1)
        logs = run(["docker", "logs", self.name], capture=True)
        raise RuntimeError(
            f"psql failed for db={db} after {timeout_seconds}s: {last}\n"
            f"--- container logs ---\n{(logs.stdout + logs.stderr)[-2000:]}"
        )

    def _wait_for_postgres(self, timeout_seconds: int = 180) -> None:
        deadline = time.monotonic() + timeout_seconds
        last = "pg_isready not yet executed"
        while time.monotonic() < deadline:
            res = run(["docker", "exec", self.name, "pg_isready", "-U", "gate_admin", "-d", "postgres"], capture=True)
            if res.returncode == 0:
                return
            last = (res.stdout + res.stderr).strip() or f"pg_isready exit={res.returncode}"
            time.sleep(1)
        logs = run(["docker", "logs", self.name], capture=True)
        raise RuntimeError(
            f"PostgreSQL did not become ready within {timeout_seconds}s: {last}\n"
            f"--- container logs ---\n{(logs.stdout + logs.stderr)[-2000:]}"
        )

    def _ensure_database(self, db: str) -> None:
        deadline = time.monotonic() + 60
        last = None
        while time.monotonic() < deadline:
            exists = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "psql",
                    "-U",
                    "gate_admin",
                    "-d",
                    "postgres",
                    "-Atqc",
                    f"SELECT 1 FROM pg_database WHERE datname = '{db}'",
                ],
                capture=True,
            )
            if exists.returncode == 0 and exists.stdout.strip() == "1":
                return
            res = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "psql",
                    "-U",
                    "gate_admin",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-q",
                    "-c",
                    f"CREATE DATABASE {db} OWNER gate_admin",
                ],
                capture=True,
            )
            if res.returncode == 0:
                return
            last = (res.stdout + res.stderr).strip() or f"create db exit={res.returncode}"
            if "already exists" in last.lower():
                return
            time.sleep(1)
        logs = run(["docker", "logs", self.name], capture=True)
        raise RuntimeError(
            f"Could not ensure database '{db}' within timeout: {last}\n"
            f"--- container logs ---\n{(logs.stdout + logs.stderr)[-2000:]}"
        )

    def _ensure_role(self, role: str, password: str) -> None:
        deadline = time.monotonic() + 60
        last = None
        while time.monotonic() < deadline:
            exists = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "psql",
                    "-U",
                    "gate_admin",
                    "-d",
                    "postgres",
                    "-Atqc",
                    f"SELECT 1 FROM pg_roles WHERE rolname = '{role}'",
                ],
                capture=True,
            )
            if exists.returncode == 0 and exists.stdout.strip() == "1":
                return
            res = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "psql",
                    "-U",
                    "gate_admin",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-q",
                    "-c",
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{password}'",
                ],
                capture=True,
            )
            if res.returncode == 0:
                return
            last = (res.stdout + res.stderr).strip() or f"create role exit={res.returncode}"
            if "already exists" in last.lower():
                return
            time.sleep(1)
        logs = run(["docker", "logs", self.name], capture=True)
        raise RuntimeError(
            f"Could not ensure role '{role}' within timeout: {last}\n"
            f"--- container logs ---\n{(logs.stdout + logs.stderr)[-2000:]}"
        )

    def __enter__(self):
        run(["docker", "rm", "-f", self.name], capture=True)
        res = run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.name,
                "-e",
                "POSTGRES_USER=gate_admin",
                "-e",
                f"POSTGRES_PASSWORD={self.admin_pw}",
                "-p",
                f"127.0.0.1:{self.port}:5432",
                "--tmpfs",
                "/var/lib/postgresql/data",
                PG_IMAGE,
            ],
            capture=True,
        )
        if res.returncode:
            raise RuntimeError(f"cannot start throwaway PostgreSQL: {res.stderr.strip()[:200]}")

        self._wait_for_postgres()
        self.psql("SELECT 1", db="postgres")
        for db in ("edudss_gate", "edudss_backup_source", "edudss_backup_restore"):
            self._ensure_database(db)
        self._ensure_role("edudss_app", self.app_pw)
        return self

    def grant_app_role(self, db: str) -> None:
        self.psql(
            f"GRANT CONNECT ON DATABASE {db} TO edudss_app; GRANT USAGE ON SCHEMA public TO edudss_app; "
            "GRANT ALL ON ALL TABLES IN SCHEMA public TO edudss_app; "
            "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO edudss_app; "
            "ALTER DEFAULT PRIVILEGES FOR ROLE gate_admin IN SCHEMA public GRANT ALL ON TABLES TO edudss_app; "
            "ALTER DEFAULT PRIVILEGES FOR ROLE gate_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO edudss_app",
            db=db,
        )

    def __exit__(self, *exc):
        run(["docker", "rm", "-f", self.name], capture=True)


def base_env(**extra) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
            "HF_TOKEN",
            "EDUDSS_PSEUDONYM_KEY",
            "EDUDSS_ENV",
            "EDUDSS_MODE",
            "DATABASE_URL",
        )
    }
    env.update({"EDUDSS_SKIP_DOTENV": "1", "PYTHONIOENCODING": "utf-8", **extra})
    return env


# ------------------------------------------------------------------------------ gates
def gate_secret_scan(ctx):
    return run([PY, "tools/secret_scan.py", str(REPO), "--history"], env=base_env()).returncode == 0, {}


def gate_migrations(ctx):
    env = base_env(DATABASE_URL=ctx["pg"].url("edudss_gate"))
    steps = {}
    for name, cmd in [
        ("precheck_empty", [PY, "-m", "ops.migration_check", "precheck"]),
        ("upgrade", [PY, "-m", "alembic", "upgrade", "head"]),
        ("verify", [PY, "-m", "ops.migration_check", "verify"]),
        ("roundtrip", [PY, "-m", "ops.migration_check", "roundtrip", "--confirm-disposable-database"]),
    ]:
        res = run(cmd, env=env, capture=True)
        steps[name] = res.returncode
        if res.returncode:
            print(res.stdout[-1500:], res.stderr[-1500:])
            return False, steps
    ctx["pg"].grant_app_role("edudss_gate")
    return True, steps


def gate_regression(ctx):
    pg = ctx["pg"]
    env = base_env(DATABASE_URL=pg.url("edudss_gate"), DATABASE_APP_ROLE_URL=pg.url("edudss_gate", "edudss_app"))
    started = time.monotonic()
    res = run(
        [PY, "-m", "pytest", "tests", "--ignore=tests/e2e", "-q", "-p", "no:cacheprovider", "-rfE"],
        env=env,
        capture=True,
    )
    tail = [
        line
        for line in res.stdout.splitlines()
        if " passed" in line or " failed" in line or line.startswith(("FAILED", "ERROR"))
    ]
    print("\n".join(tail[-15:]))
    return res.returncode == 0, {
        "summary": tail[-1] if tail else res.stdout[-300:],
        "seconds": round(time.monotonic() - started, 1),
    }


def gate_backup_restore(ctx):
    pg = ctx["pg"]
    src = pg.url("edudss_backup_source")
    up = run([PY, "-m", "alembic", "upgrade", "head"], env=base_env(DATABASE_URL=src), capture=True)
    if up.returncode:
        return False, {"source_migration": up.stderr[-400:]}
    env = base_env(
        PHASE13_SOURCE_URL=src,
        PHASE13_RESTORE_URL=pg.url("edudss_backup_restore"),
        PHASE13_APP_ROLE_URL=pg.url("edudss_backup_restore", "edudss_app"),
        PHASE13_DOCKER_CONTAINER=pg.name,
    )
    res = run(
        [PY, "-m", "pytest", "tests/test_backup_recovery_integration.py", "-q", "-p", "no:cacheprovider"],
        env=env,
        capture=True,
    )
    print(res.stdout.strip().splitlines()[-1] if res.stdout.strip() else res.stderr[-500:])
    return res.returncode == 0 and " passed" in res.stdout, {}


def gate_docker_build(ctx):
    sha = run(["git", "rev-parse", "HEAD"], capture=True).stdout.strip()
    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"], capture=True).stdout.strip()
    version = (APP / "VERSION").read_text(encoding="utf-8").strip()
    ctx["image"] = ctx.get("image") or f"edudss:{version}-{sha[:12]}{'-dirty' if dirty else ''}"
    build_time = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = run(
        [
            "docker",
            "build",
            "--build-arg",
            f"EDUDSS_GIT_SHA={sha}{'+dirty' if dirty else ''}",
            "--build-arg",
            f"EDUDSS_BUILD_TIME={build_time}",
            "--build-arg",
            f"EDUDSS_IMAGE_REF={ctx['image']}",
            "-t",
            ctx["image"],
            ".",
        ],
        capture=True,
    )
    lock_line = next(
        (l for l in res.stdout.splitlines() + res.stderr.splitlines() if "Dependency lock verified" in l), ""
    )
    if res.returncode:
        print(res.stderr[-2500:])
    return res.returncode == 0, {"image": ctx["image"], "lock": lock_line.strip()[-120:]}


def gate_licenses(ctx):
    res = run(
        ["docker", "run", "--rm", "--entrypoint", "python", ctx["image"], "tools/license_inventory.py", "--check"],
        capture=True,
    )
    print(res.stdout.strip()[-800:])
    return res.returncode == 0, {}


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")
    except Exception:
        return None, None


def _start_app(ctx, name: str, extra_env: dict) -> int:
    port = free_port()
    pg = ctx["pg"]
    db_url = f"postgresql+psycopg2://edudss_app:{pg.app_pw}@host.docker.internal:{pg.port}/edudss_gate"
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--add-host",
        "host.docker.internal:host-gateway",
        "-p",
        f"127.0.0.1:{port}:8081",
        "-e",
        f"DATABASE_URL={db_url}",
        "-e",
        "EDUDSS_REQUIRE_PGVECTOR=1",
        "-e",
        "EDUDSS_IDENTITY_STORE=postgres",
        "-e",
        "EDUDSS_ORGANIZATION_ID=1",
    ]
    for key, value in extra_env.items():
        cmd += ["-e", f"{key}={value}"]
    res = run(cmd + [ctx["image"]], capture=True)
    if res.returncode:
        raise RuntimeError(res.stderr[-300:])
    return port


def _wait(url: str, want: int, seconds: int = 240):
    deadline = time.monotonic() + seconds
    last = (None, None)
    while time.monotonic() < deadline:
        last = _get(url)
        if last[0] == want:
            return last
        time.sleep(3)
    return last


def gate_container_smoke(ctx):
    details, ok = {}, True
    try:
        port = _start_app(ctx, "edudss-gate-app", {})
        ctx["app_port"] = port
        code, body = _wait(f"http://127.0.0.1:{port}/livez", 200)
        details["livez"] = code
        code, body = _wait(f"http://127.0.0.1:{port}/readyz", 200)
        details["readyz"] = code
        details["readyz_checks"] = {k: v.get("status") for k, v in (body or {}).get("checks", {}).items()}
        details["ai_required"] = ((body or {}).get("checks", {}).get("ai_configuration") or {}).get("required")
        code, version = _get(f"http://127.0.0.1:{port}/version")
        details["version"] = (version or {}).get("release", {}).get("version")
        uid = run(["docker", "exec", "edudss-gate-app", "id", "-u"], capture=True).stdout.strip()
        details["uid"] = uid
        env_keys = run(
            [
                "docker",
                "exec",
                "edudss-gate-app",
                "sh",
                "-c",
                "env | grep -cE '^(OPENAI|GEMINI|GROQ|GOOGLE)_API_KEY=' || true",
            ],
            capture=True,
        ).stdout.strip()
        content = run(
            [
                "docker",
                "exec",
                "edudss-gate-app",
                "sh",
                "-c",
                "ls -d '/app/dữ liệu' /app/.env /app/reports 2>/dev/null | wc -l; "
                "grep -rIl --exclude='release_gate.py' 'Employee Code' /app 2>/dev/null | wc -l",
            ],
            capture=True,
        ).stdout.split()
        details.update(
            {
                "ai_keys_in_env": env_keys,
                "forbidden_paths": content[0] if content else "?",
                "employee_header_files": content[1] if len(content) > 1 else "?",
            }
        )
        ok = (
            details["livez"] == 200
            and details["readyz"] == 200
            and details["ai_required"] is False
            and uid == "999"
            and env_keys == "0"
            and details["forbidden_paths"] == "0"
            and details["employee_header_files"] == "0"
        )
        # production must fail closed without the pseudonym key, and be ready with it
        p1 = _start_app(ctx, "edudss-gate-prod-nokey", {"EDUDSS_ENV": "production"})
        code, body = _wait(f"http://127.0.0.1:{p1}/readyz", 503, 180)
        details["production_without_key_readyz"] = code
        details["production_without_key_privacy"] = ((body or {}).get("checks", {}).get("privacy_key") or {}).get(
            "status"
        )
        p2 = _start_app(
            ctx, "edudss-gate-prod-key", {"EDUDSS_ENV": "production", "EDUDSS_PSEUDONYM_KEY": secrets.token_hex(32)}
        )
        code, body = _wait(f"http://127.0.0.1:{p2}/readyz", 200, 240)
        details["production_with_key_readyz"] = code
        ok = ok and details["production_without_key_readyz"] == 503 and details["production_with_key_readyz"] == 200
    except Exception as exc:
        details["error"] = str(exc)[:300]
        ok = False
    finally:
        for name in ("edudss-gate-prod-nokey", "edudss-gate-prod-key"):
            run(["docker", "rm", "-f", name], capture=True)
    print(json.dumps(details, ensure_ascii=False))
    return ok, details


def gate_manifest(ctx):
    out_dir = APP / "reports" / "release_gate"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"release-manifest-{ctx['stamp']}.json"
    evidence = [str(p.relative_to(APP)) for p in [APP / "requirements.lock.txt", APP / "THIRD_PARTY_NOTICES.md"]]
    gen = run(
        [
            PY,
            "tools/release_manifest.py",
            "generate",
            "--image",
            ctx["image"],
            "--out",
            str(manifest_path),
            "--evidence",
            *evidence,
        ],
        capture=True,
    )
    if gen.returncode:
        print(gen.stderr[-800:])
        return False, {}
    ver = run(
        [
            PY,
            "tools/release_manifest.py",
            "verify",
            "--manifest",
            str(manifest_path),
            "--url",
            f"http://127.0.0.1:{ctx['app_port']}/version",
        ],
        capture=True,
    )
    print(ver.stdout.strip())
    ctx["manifest"] = str(manifest_path.relative_to(APP))
    return ver.returncode == 0, {"manifest": ctx["manifest"]}


def gate_dependency_audit(ctx):
    res = run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{APP}:/src:ro",
            "--entrypoint",
            "sh",
            "python:3.11.16-slim-trixie",
            "-c",
            "pip install -q pip-audit >/dev/null 2>&1 && pip-audit --no-deps --disable-pip -r "
            "/src/requirements.lock.txt -f json 2>/dev/null",
        ],
        capture=True,
    )
    try:
        data = json.loads(res.stdout[res.stdout.index("{") :])
    except (ValueError, IndexError):
        return None, {"error": "pip-audit unavailable (offline?)", "stderr": res.stderr[-300:]}
    vulns = [
        {"package": d["name"], "version": d["version"], "id": v["id"], "fix": v.get("fix_versions") or []}
        for d in data.get("dependencies", [])
        for v in d.get("vulns", [])
    ]
    print(json.dumps({"vulnerabilities": len(vulns), "items": vulns[:40]}, indent=1))
    return len(vulns) == 0, {"vulnerabilities": vulns}


def gate_container_scan(ctx):
    sock = "//var/run/docker.sock" if os.name == "nt" else "/var/run/docker.sock"
    res = run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{sock}:/var/run/docker.sock",
            "aquasec/trivy:latest",
            "image",
            "--quiet",
            "--scanners",
            "vuln",
            "--severity",
            "HIGH,CRITICAL",
            "--ignore-unfixed",
            "--format",
            "json",
            ctx["image"],
        ],
        capture=True,
    )
    try:
        data = json.loads(res.stdout)
    except ValueError:
        return None, {"error": "trivy unavailable (offline?)", "stderr": res.stderr[-300:]}
    findings = [
        {
            "target": r.get("Target"),
            "pkg": v.get("PkgName"),
            "installed": v.get("InstalledVersion"),
            "fixed": v.get("FixedVersion"),
            "id": v.get("VulnerabilityID"),
            "severity": v.get("Severity"),
        }
        for r in data.get("Results", [])
        for v in r.get("Vulnerabilities") or []
    ]
    print(json.dumps({"high_critical_fixable": len(findings), "items": findings[:40]}, indent=1))
    return len(findings) == 0, {"findings": findings}


GATES = {name: globals()[f"gate_{name}"] for name in MANDATORY + ADVISORY}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EduDSS release gate")
    parser.add_argument("--skip", nargs="*", default=[], choices=MANDATORY + ADVISORY)
    parser.add_argument("--image", help="use an already-built image (implies --skip docker_build)")
    parser.add_argument("--no-advisory", action="store_true", help="skip network-dependent advisory scans")
    args = parser.parse_args(argv)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    ctx = {"stamp": stamp, "image": args.image}
    skip = set(args.skip) | ({"docker_build"} if args.image else set()) | (set(ADVISORY) if args.no_advisory else set())
    results = {}
    try:
        with ThrowawayPostgres() as pg:
            ctx["pg"] = pg
            for name in MANDATORY + ADVISORY:
                if name in skip:
                    results[name] = {"status": "SKIPPED"}
                    continue
                if name in ("licenses", "container_smoke", "manifest", "container_scan") and not ctx.get("image"):
                    results[name] = {"status": "NOT_RUN", "reason": "no image"}
                    continue
                if name == "manifest" and "app_port" not in ctx:
                    results[name] = {"status": "NOT_RUN", "reason": "container_smoke did not run"}
                    continue
                log(f"gate {name} ...")
                started = time.monotonic()
                ok, details = GATES[name](ctx)
                status = "PASS" if ok else ("UNAVAILABLE" if ok is None else "FAIL")
                results[name] = {
                    "status": status,
                    "mandatory": name in MANDATORY,
                    "seconds": round(time.monotonic() - started, 1),
                    **details,
                }
                log(f"gate {name}: {status}")
    finally:
        run(["docker", "rm", "-f", "edudss-gate-app"], capture=True)
    failed = [n for n, r in results.items() if n in MANDATORY and r["status"] not in ("PASS", "SKIPPED")]
    summary = {"stamp": stamp, "image": ctx.get("image"), "failed_mandatory": failed, "gates": results}
    out = APP / "reports" / "release_gate" / f"release-gate-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"summary -> {out.relative_to(APP)}; failed mandatory gates: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
