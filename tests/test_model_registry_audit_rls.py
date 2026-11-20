"""Regression test for Issue MODELREG-002 (found during final-candidate-v2
verification): `model_registry.promote()`'s audit-log write was silently
dropped in any RLS-enforced deployment.

Root cause: `_set_production_with_audit()` called
`audit_log_repository.record(..., organization_id=None)`. The `audit_logs`
table's RLS policy is `organization_id = current_setting('app.organization_id')`
for both `qual` and `WITH CHECK`. Under SQL NULL semantics, `NULL = NULL`
is NULL, never TRUE — so a non-superuser app-role connection (how the real
deployed app always connects, never as the schema owner) could NEVER
satisfy that WITH CHECK with organization_id=None. The write was rejected
and silently swallowed by `audit_log_repository.record()`'s own
intentionally-broad `except Exception` (by design, so a broken audit write
never blocks the actual promotion) — meaning every model promotion/
rollback audit entry was silently dropped, with no error surfaced anywhere.

Requires TWO real PostgreSQL connection strings, exactly like
test_db_row_level_security.py: DATABASE_URL (schema owner, used only to
read back and confirm the row — never to perform the write itself, or
this test would not have caught the bug) and DATABASE_APP_ROLE_URL (a
genuine non-superuser role — this is the connection the fix must work
through).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from dss.db.session import is_database_configured

_APP_ROLE_URL = os.environ.get("DATABASE_APP_ROLE_URL")

pytestmark = pytest.mark.skipif(
    not (is_database_configured() and _APP_ROLE_URL),
    reason="Requires DATABASE_URL (owner) and DATABASE_APP_ROLE_URL (non-superuser) — see test_db_row_level_security.py",
)


@pytest.fixture
def _organization_id():
    owner = create_engine(os.environ["DATABASE_URL"])
    with owner.begin() as conn:
        org_code = f"modelreg002-{uuid.uuid4().hex[:8]}"
        org_id = conn.execute(
            text(
                "INSERT INTO organizations (org_code, name, is_active, created_at, updated_at) "
                "VALUES (:c, :n, true, now(), now()) RETURNING id"
            ),
            {"c": org_code, "n": "MODELREG-002 regression"},
        ).scalar_one()
    owner.dispose()
    return org_id


def test_promote_audit_write_succeeds_through_the_real_app_role(_organization_id, monkeypatch):
    """Reproduces MODELREG-002 as it actually manifests: DATABASE_URL set to
    the APP ROLE (exactly how the real app connects), not the owner."""
    owner_url = os.environ["DATABASE_URL"]  # captured before monkeypatching below
    monkeypatch.setenv("DATABASE_URL", _APP_ROLE_URL)
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(_organization_id))
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    try:
        from dss.db.repositories import audit_log_repository
        from dss.services.model_registry import _resolve_organization_id_best_effort

        resolved = _resolve_organization_id_best_effort()
        assert resolved == _organization_id

        ok = audit_log_repository.record(
            action="model.promoted",
            target_type="model_version",
            target_id="regression-test-training-id",
            actor_username="modelreg002-test",
            organization_id=resolved,
            before={},
            after={"note": "MODELREG-002 regression"},
        )
        assert ok is True, "audit_log_repository.record() must succeed through the app role once organization_id is set"
    finally:
        reset_engine_for_tests()

    owner_direct = create_engine(owner_url)
    with owner_direct.connect() as conn:
        row = conn.execute(
            text(
                "SELECT organization_id, action, target_id FROM audit_logs "
                "WHERE organization_id=:o AND action='model.promoted' AND target_id='regression-test-training-id'"
            ),
            {"o": _organization_id},
        ).one()
    owner_direct.dispose()
    assert row.organization_id == _organization_id


def test_promote_without_organization_id_still_does_not_raise(monkeypatch):
    """Preserves pre-fix behavior for deployments that never set
    EDUDSS_ORGANIZATION_ID (e.g. the existing non-Postgres default) — the
    resolver must return None, not raise, and record() must still degrade
    gracefully rather than crash the caller."""
    monkeypatch.delenv("EDUDSS_ORGANIZATION_ID", raising=False)
    from dss.services.model_registry import _resolve_organization_id_best_effort

    assert _resolve_organization_id_best_effort() is None
