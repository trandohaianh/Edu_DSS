"""Repository for the `subscriptions` domain (Phase 1B, migration order item 9).

Real existing runtime being cut over: `dss/services/subscription_service.py`
(single JSON file, `data_warehouse/subscription.json`). Wired behind
`dss.core.persistence_config.is_postgres_enabled("SUBSCRIPTION")`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from dss.db.models import Organization, Subscription
from dss.db.session import tenant_session_scope


def _row_to_dict(session, row: Subscription) -> dict[str, Any]:
    """Shape matches dss/services/subscription_service.py's existing JSON dict
    contract (org_id/org_name/plan/status/expires_at/max_students/
    features_enabled) so check_entitlement()/render_subscription_gate() work
    unmodified regardless of which backend is active."""
    org = session.get(Organization, row.organization_id)
    return {
        "org_id": org.org_code if org else None,
        "org_name": org.name if org else None,
        "plan": row.plan,
        "status": row.status,
        "max_students": row.max_students,
        "max_courses": row.max_courses,
        "max_ai_requests_month": row.max_ai_requests_month,
        "max_storage_mb": row.max_storage_mb,
        "features_enabled": row.features_enabled or [],
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "expires_at": row.end_date.isoformat() if row.end_date else None,
    }


def get_or_create_subscription(organization_id: int, defaults: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    defaults = defaults or {}
    with tenant_session_scope(organization_id) as session:
        row = session.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            row = Subscription(
                organization_id=organization_id,
                plan=defaults.get("plan", "ENTERPRISE"),
                status=defaults.get("status", "ACTIVE"),
                max_students=defaults.get("max_students", 5000),
                max_courses=defaults.get("max_courses", 150),
                features_enabled=defaults.get("features_enabled", []),
            )
            session.add(row)
            session.flush()
        return _row_to_dict(session, row)


def update_status(
    organization_id: int, status: str, plan: Optional[str] = None, max_students: Optional[int] = None
) -> dict[str, Any]:
    valid_statuses = ("ACTIVE", "EXPIRED", "SUSPENDED")
    if status not in valid_statuses:
        raise ValueError(f"Trạng thái không hợp lệ: {status}. Hợp lệ: {valid_statuses}")
    with tenant_session_scope(organization_id) as session:
        row = session.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            raise ValueError(
                f"No subscription row for organization {organization_id} — call get_or_create_subscription first"
            )
        row.status = status
        if plan:
            row.plan = plan
        if max_students is not None:
            row.max_students = max_students
        session.flush()
        return _row_to_dict(session, row)
