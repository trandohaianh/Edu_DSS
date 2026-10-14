"""Release-time database migration checks (C1.2).

    python -m ops.migration_check status      # JSON: DB revision vs code head, table contract
    python -m ops.migration_check precheck    # before `alembic upgrade head` in a deployment
    python -m ops.migration_check verify      # after the upgrade: schema must match the code
    python -m ops.migration_check roundtrip --confirm-disposable-database
                                              # CI/staging only: head -> base -> head on an EMPTY db

The database URL comes only from DATABASE_URL (the migration/owner role). Output never
contains credentials. Exit code 0 = OK, 1 = check failed, 2 = unsafe / refused.

Rollback policy (see C1_2_RELEASE_ENGINEERING.md): every migration has a downgrade(),
but all of them DROP tables/columns, i.e. downgrade destroys data. Production schema
rollback is therefore "restore the pre-deploy backup" or "ship a forward fix" — never
`alembic downgrade` against live data. `roundtrip` exists to prove the migration graph is
mechanically reversible on a disposable database, nothing more.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _engine():
    from sqlalchemy import create_engine
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return create_engine(url, pool_pre_ping=True)


def _script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from dss.db.schema_contract import ALEMBIC_INI
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def _destructive_downgrade(revision) -> bool:
    source = Path(revision.path).read_text(encoding="utf-8")
    body = source.split("def downgrade", 1)[-1]
    return bool(re.search(r"drop_table|drop_column|DROP\s+(TABLE|COLUMN)", body))


def pending_revisions(current: list[str]) -> list[dict]:
    script = _script_directory()
    head = script.get_current_head()
    base = current[0] if current else "base"
    if current and current[0] == head:
        return []
    revisions = list(script.iterate_revisions(head, base if base != "base" else "base"))
    return [{"revision": r.revision, "message": (r.doc or "").strip().splitlines()[0][:100] if r.doc else "",
             "downgrade_destroys_data": _destructive_downgrade(r)}
            for r in reversed([r for r in revisions if r.revision != base])]


def status() -> dict:
    from dss.db.schema_contract import schema_report
    report = schema_report(_engine())
    report["pending"] = pending_revisions(report["database_revision"])
    return report


def precheck() -> int:
    """Safe to run `alembic upgrade head`? DB must be at head or at an ancestor of head."""
    report = status()
    script = _script_directory()
    known = {r.revision for r in script.walk_revisions()}
    current = report["database_revision"]
    if len(current) > 1:
        return _out({"ok": False, "reason": "multiple revisions in database", **report}, 2)
    if current and current[0] not in known:
        return _out({"ok": False, "reason": "database revision is unknown to this code "
                     "(database is AHEAD of this release or from another branch) — do not deploy", **report}, 2)
    return _out({"ok": True, "action": "none" if report["at_head"] else "upgrade", **report}, 0)


def verify() -> int:
    report = status()
    return _out({"ok": report["compatible"] and not report["unexpected_tables"], **report},
                0 if report["compatible"] and not report["unexpected_tables"] else 1)


def roundtrip(confirmed: bool) -> int:
    from dss.core.runtime_mode import is_production
    from dss.db.schema_contract import database_tables
    if not confirmed or is_production():
        return _out({"ok": False, "reason": "roundtrip destroys data; needs --confirm-disposable-database "
                     "and a non-production environment"}, 2)
    engine = _engine()
    if database_tables(engine) - {"alembic_version"}:
        before = status()
        if before["database_revision"] and not before["at_head"]:
            return _out({"ok": False, "reason": "database is not at head"}, 2)
    from alembic import command
    from alembic.config import Config
    from dss.db.schema_contract import ALEMBIC_INI, assert_schema_matches
    config = Config(str(ALEMBIC_INI))
    command.upgrade(config, "head")
    assert_schema_matches(engine)
    command.downgrade(config, "base")
    leftover = sorted(database_tables(engine) - {"alembic_version"})
    command.upgrade(config, "head")
    report = assert_schema_matches(engine)
    return _out({"ok": not leftover, "leftover_after_downgrade_to_base": leftover, **report}, 0 if not leftover else 1)


def _out(payload: dict, code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("precheck")
    sub.add_parser("verify")
    rt = sub.add_parser("roundtrip")
    rt.add_argument("--confirm-disposable-database", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "status":
        return _out(status(), 0)
    if args.cmd == "precheck":
        return precheck()
    if args.cmd == "verify":
        return verify()
    return roundtrip(args.confirm_disposable_database)


if __name__ == "__main__":
    sys.exit(main())
