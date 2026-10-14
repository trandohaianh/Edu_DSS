"""Canonical schema contract — derived from the code, never from a historical snapshot (C1.2).

Before C1.2 the CI workflow and the backup test hard-coded "27 tables" and Alembic
head "797f72d1c666"; both went stale the moment new migrations landed. Every
consumer (CI schema gate, backup/restore acceptance, migration pre-check,
readiness) now asks THIS module what the schema should be:

- expected Alembic head(s): read from the migration graph under `dss/db/migrations/versions`;
- expected tables: SQLAlchemy metadata of `dss.db.models` + `alembic_version`.

Both come from the same checkout that is being deployed, so a new migration updates
the expectation automatically — and a model/migration mismatch is detected instead
of silently accepted.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
ALEMBIC_VERSION_TABLE = "alembic_version"


@lru_cache(maxsize=1)
def expected_heads() -> tuple[str, ...]:
    """Head revision(s) of the migration graph shipped with this code (normally exactly one)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ALEMBIC_INI))
    location = Path(config.get_main_option("script_location"))
    if not location.is_absolute():
        config.set_main_option("script_location", str(APP_ROOT / location))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def expected_head() -> str:
    heads = expected_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Migration graph must have exactly one head, found {len(heads)}: {heads}")
    return heads[0]


@lru_cache(maxsize=1)
def expected_tables() -> frozenset[str]:
    from dss.db.base import Base
    import dss.db.models  # noqa: F401  (registers every mapped table)

    return frozenset(set(Base.metadata.tables) | {ALEMBIC_VERSION_TABLE})


def database_revisions(engine) -> list[str]:
    from sqlalchemy import inspect, text

    if ALEMBIC_VERSION_TABLE not in inspect(engine).get_table_names(schema="public"):
        return []
    with engine.connect() as conn:
        return sorted(conn.execute(text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}")).scalars().all())


def database_tables(engine) -> set[str]:
    from sqlalchemy import inspect

    return set(inspect(engine).get_table_names(schema="public"))


def schema_report(engine) -> dict:
    """Compare a live database with the code's contract. Safe to log (names only)."""
    tables = database_tables(engine)
    revisions = database_revisions(engine)
    expected = expected_tables()
    missing = sorted(expected - tables)
    unexpected = sorted(tables - expected)
    heads = list(expected_heads())
    return {
        "expected_head": heads,
        "database_revision": revisions,
        "at_head": revisions == heads,
        "missing_tables": missing,
        "unexpected_tables": unexpected,
        "table_count": len(tables),
        "expected_table_count": len(expected),
        "compatible": revisions == heads and not missing,
    }


def assert_schema_matches(engine, allow_extra: Optional[Iterable[str]] = None) -> dict:
    report = schema_report(engine)
    extra = set(report["unexpected_tables"]) - set(allow_extra or ())
    if not report["at_head"] or report["missing_tables"] or extra:
        raise AssertionError(f"Schema does not match the code's migration contract: {report}")
    return report
