"""Run PostgreSQL acceptance in a new labelled container; never use an existing DB."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="pgvector/pgvector:pg16")
    parser.add_argument(
        "--tests",
        nargs="+",
        default=[
            "tests/test_stage23_platform_postgres.py",
            "tests/test_stage1_plan_history_postgres.py",
            "tests/test_bootstrap_identity.py",
        ],
    )
    parser.add_argument("--skip-roundtrip", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    token = uuid.uuid4().hex
    name, label = "edudss-stage23-" + token[:16], "edu.edudss.acceptance.run"
    admin_password, owner_password, app_password = [secrets.token_hex(24) for _ in range(3)]
    sensitive = [admin_password, owner_password, app_password]
    engines, created = [], False

    def redact(value):
        for secret in sorted(sensitive, key=len, reverse=True):
            value = value.replace(secret, "<redacted>")
        return value

    def run(argv, env=None, timeout=300, quiet=False):
        result = subprocess.run(
            argv, cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        output = redact((result.stdout or "") + (result.stderr or ""))
        if not quiet and output.strip():
            print(output.rstrip(), flush=True)
        if result.returncode:
            raise RuntimeError("Command failed: " + argv[0] + " (exit " + str(result.returncode) + ")")
        return result.stdout.strip()

    def migration_env(url):
        env = dict(os.environ)
        env.update(
            DATABASE_URL=url, EDUDSS_ENV="test", EDUDSS_MODE="DEMO_SYNTHETIC", PYTHONUTF8="1", PYTHONIOENCODING="utf-8"
        )
        return env

    def migrate(url, action, revision):
        run(
            [sys.executable, "-B", "-m", "alembic", "-c", str(root / "alembic.ini"), action, revision],
            env=migration_env(url),
        )

    try:
        run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                label + "=" + token,
                "--env",
                "POSTGRES_PASSWORD=" + admin_password,
                "--env",
                "POSTGRES_DB=edudss_acceptance",
                "--publish",
                "127.0.0.1::5432",
                "--tmpfs",
                "/var/lib/postgresql/data:rw",
                args.image,
            ],
            quiet=True,
        )
        created = True
        metadata = json.loads(run(["docker", "inspect", name], quiet=True))[0]
        binding = metadata["NetworkSettings"]["Ports"]["5432/tcp"][0]
        if binding["HostIp"] != "127.0.0.1":
            raise RuntimeError("Acceptance database must bind exclusively to loopback.")
        port = int(binding["HostPort"])

        def url(username, password):
            return URL.create(
                "postgresql+psycopg2",
                username=username,
                password=password,
                host="127.0.0.1",
                port=port,
                database="edudss_acceptance",
            ).render_as_string(hide_password=False)

        admin_url, owner_url, app_url = (
            url("postgres", admin_password),
            url("acceptance_owner", owner_password),
            url("acceptance_app", app_password),
        )
        sensitive.extend([admin_url, owner_url, app_url])
        admin = create_engine(admin_url, pool_pre_ping=True)
        engines.append(admin)
        deadline = time.monotonic() + 60
        while True:
            try:
                with admin.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("Ephemeral PostgreSQL did not become ready.") from None
                time.sleep(0.5)
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            # Owner is privileged for migrations/fixture cleanup, never used by runtime.
            connection.exec_driver_sql(
                "CREATE ROLE acceptance_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS PASSWORD '"
                + owner_password
                + "'"
            )
            connection.exec_driver_sql(
                "CREATE ROLE acceptance_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '"
                + app_password
                + "'"
            )
            connection.exec_driver_sql("ALTER DATABASE edudss_acceptance OWNER TO acceptance_owner")
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            connection.exec_driver_sql("GRANT ALL ON SCHEMA public TO acceptance_owner")
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO acceptance_app")
        print("Migrating isolated PostgreSQL.", flush=True)
        migrate(owner_url, "upgrade", "head")
        owner = create_engine(owner_url)
        engines.append(owner)

        def grant_runtime():
            with owner.begin() as connection:
                connection.exec_driver_sql(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO acceptance_app"
                )
                connection.exec_driver_sql("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO acceptance_app")
                connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE acceptance_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO acceptance_app"
                )
                connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE acceptance_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO acceptance_app"
                )

        grant_runtime()
        env = dict(os.environ)
        env.update(
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
            EDUDSS_ENV="test",
            EDUDSS_MODE="DEMO_SYNTHETIC",
            DATABASE_URL=app_url,
            EDUDSS_PLATFORM_STORE="postgres",
            EDUDSS_PLATFORM_TEST_OWNER_URL=owner_url,
            EDUDSS_PLATFORM_TEST_APP_URL=app_url,
            EDUDSS_BOOTSTRAP_TEST_OWNER_URL=owner_url,
            EDUDSS_BOOTSTRAP_TEST_ALLOW_WRITE="1",
            WORKSTREAM_AB_OWNER_URL=owner_url,
            WORKSTREAM_AB_DATABASE_URL=app_url,
            WORKSTREAM_ONBOARDING_OWNER_URL=owner_url,
            WORKSTREAM_ONBOARDING_DATABASE_URL=app_url,
        )
        print("Running restricted-role PostgreSQL acceptance.", flush=True)
        run(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                *args.tests,
                "--tb=short",
                "--basetemp=.pytest_cache/stage23-" + token[:12],
            ],
            env=env,
            timeout=900,
        )
        if not args.skip_roundtrip:
            old_tables = [
                table
                for table in inspect(owner).get_table_names(schema="public")
                if not table.startswith("lp_") and table != "alembic_version"
            ]

            def counts():
                with admin.connect() as connection:
                    quote = admin.dialect.identifier_preparer.quote
                    return {
                        table: connection.exec_driver_sql("SELECT count(*) FROM public." + quote(table)).scalar_one()
                        for table in old_tables
                    }

            before = counts()
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            config = Config(str(root / "alembic.ini"))
            config.set_main_option("script_location", str(root / "dss" / "db" / "migrations"))
            graph = ScriptDirectory.from_config(config)
            previous = graph.get_revision(graph.get_current_head()).down_revision
            if not isinstance(previous, str):
                raise RuntimeError("Expected a single previous migration revision.")
            migrate(owner_url, "downgrade", previous)
            if counts() != before:
                raise RuntimeError("Downgrade changed existing non-platform row counts.")
            migrate(owner_url, "upgrade", "head")
            grant_runtime()
            if counts() != before:
                raise RuntimeError("Upgrade changed existing non-platform row counts.")
            print("Migration roundtrip preserved existing tables and row counts.", flush=True)
        print("Stage 2/3 isolated PostgreSQL acceptance passed.", flush=True)
        return 0
    except Exception as exc:
        print(redact(str(exc)), file=sys.stderr, flush=True)
        return 1
    finally:
        for engine in engines:
            engine.dispose()
        if created:
            try:
                items = json.loads(run(["docker", "inspect", name], quiet=True, timeout=30))
                owned = (
                    len(items) == 1
                    and items[0]["Name"] == "/" + name
                    and items[0]["Config"]["Labels"].get(label) == token
                )
                if owned:
                    run(["docker", "rm", "--force", name], quiet=True, timeout=60)
                else:
                    print("Skipped cleanup: container ownership could not be verified.", file=sys.stderr)
            except Exception:
                print("Acceptance container cleanup did not finish; inspect its run label.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
