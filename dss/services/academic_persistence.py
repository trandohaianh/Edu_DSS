"""Runtime academic persistence boundary used by UI/import/sync paths."""

from __future__ import annotations

import os

from dss.core.observability import observed
from dss.core.persistence_config import is_postgres_enabled


def current_organization_id() -> int:
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        raise RuntimeError("EDUDSS_ORGANIZATION_ID is required for PostgreSQL academic persistence")
    return int(raw)


@observed("academic.dataframe.persist")
def persist_dataframe_if_configured(df, course_code: str, course_title: str, term: str | None = None) -> dict | None:
    if not is_postgres_enabled("ACADEMIC"):
        return None
    from dss.db.repositories.academic_repository import import_dataframe

    return import_dataframe(current_organization_id(), df, course_code, course_title, term=term, replace_existing=True)
