"""AuditLogRepository — the security audit trail Phase 0 found does not exist
anywhere in the codebase today.

Design constraint (matches the existing app's own pattern elsewhere, e.g.
`subscription_service.check_entitlement`'s "không crash" requirement): most of
the 489 existing tests, and the live app in its default configuration, run
with NO PostgreSQL configured at all (Phase 1 is additive — see
dss/db/__init__.py). `record()` must never raise or block a caller (e.g.
`model_registry.promote()`) just because Postgres isn't configured; it logs a
warning via the existing technical logger and returns `False` instead.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from dss.core.logging_config import get_logger
from dss.db.models import AuditLog
from dss.db.session import is_database_configured, session_scope, tenant_session_scope

_logger = get_logger(__name__)


def record(
    action: str,
    target_type: str,
    target_id: str,
    actor_username: str,
    organization_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
) -> bool:
    """Write one immutable audit record. Returns True on success, False if
    Postgres isn't configured or the write failed (never raises to the caller
    — an audit-log failure must not break the action being audited)."""
    if not is_database_configured():
        _logger.warning(
            "AuditLogRepository.record() skipped (no PostgreSQL configured): action=%s target=%s:%s",
            action, target_type, target_id,
        )
        return False
    try:
        scope = tenant_session_scope(organization_id) if organization_id is not None else session_scope()
        with scope as session:
            session.add(
                AuditLog(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    actor_username=actor_username,
                    action=action,
                    target_type=target_type,
                    target_id=str(target_id),
                    before=before,
                    after=after,
                )
            )
        return True
    except Exception:
        _logger.exception(
            "AuditLogRepository.record() failed: action=%s target=%s:%s", action, target_type, target_id
        )
        return False


def list_for_target(target_type: str, target_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read-only: audit history for one target (e.g. one model_version, one
    user), newest first. Returns [] if Postgres isn't configured."""
    if not is_database_configured():
        return []
    raw_org = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    scope = tenant_session_scope(int(raw_org)) if raw_org else session_scope()
    with scope as session:
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.target_type == target_type, AuditLog.target_id == str(target_id))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "actor_username": r.actor_username,
                "action": r.action,
                "before": r.before,
                "after": r.after,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
