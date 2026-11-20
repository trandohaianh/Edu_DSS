"""Concurrency-safe tenant quota accounting."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from sqlalchemy import text

from dss.core.observability import observed
from dss.db.models import QuotaUsage, Subscription
from dss.db.repositories import audit_log_repository
from dss.db.session import tenant_session_scope


class QuotaExceededError(RuntimeError):
    def __init__(self, quota_key: str, limit: int, used: int, requested: int):
        super().__init__(f"quota {quota_key} exceeded: used={used} requested={requested} limit={limit}")
        self.quota_key = quota_key
        self.limit = limit
        self.used = used
        self.requested = requested


def _period(quota_key: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("%Y-%m") if quota_key.endswith("_MONTH") else "lifetime"


@observed("quota.consume", metadata=lambda organization_id, quota_key, amount=1, **kwargs: {"quota_key": quota_key})
def consume(
    organization_id: int, quota_key: str, limit: int | None, amount: int = 1, *, period_key: str | None = None
) -> int:
    if amount < 0:
        raise ValueError("quota amount must be non-negative")
    key = period_key or _period(quota_key)
    with tenant_session_scope(organization_id) as session:
        # A row lock cannot protect the first increment because the counter row
        # does not exist yet. Serialize each tenant/key/period before selecting
        # so concurrent first-use requests cannot race into a unique violation
        # or lose an increment.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:quota_identity, :organization_id))"),
            {"quota_identity": f"{quota_key}:{key}", "organization_id": organization_id},
        )
        row = (
            session.query(QuotaUsage)
            .filter_by(organization_id=organization_id, quota_key=quota_key, period_key=key)
            .with_for_update()
            .one_or_none()
        )
        used = row.used if row else 0
        if limit is not None and used + amount > limit:
            audit_log_repository.record(
                "quota.exceeded",
                "quota",
                quota_key,
                "system",
                organization_id=organization_id,
                before={"used": used},
                after={"requested": amount, "limit": limit},
            )
            raise QuotaExceededError(quota_key, limit, used, amount)
        if row is None:
            row = QuotaUsage(organization_id=organization_id, quota_key=quota_key, period_key=key, used=amount)
            session.add(row)
        else:
            row.used += amount
        session.flush()
        return row.used


def get_usage(organization_id: int, quota_key: str, *, period_key: str | None = None) -> int:
    key = period_key or _period(quota_key)
    with tenant_session_scope(organization_id) as session:
        row = (
            session.query(QuotaUsage)
            .filter_by(organization_id=organization_id, quota_key=quota_key, period_key=key)
            .one_or_none()
        )
        return row.used if row else 0


def reset(organization_id: int, quota_key: str, *, period_key: str | None = None) -> None:
    key = period_key or _period(quota_key)
    with tenant_session_scope(organization_id) as session:
        row = (
            session.query(QuotaUsage)
            .filter_by(organization_id=organization_id, quota_key=quota_key, period_key=key)
            .with_for_update()
            .one_or_none()
        )
        if row:
            row.used = 0
    audit_log_repository.record(
        "quota.reset",
        "quota",
        quota_key,
        "system",
        organization_id=organization_id,
        after={"period_key": key, "used": 0},
    )


def subscription_limit(organization_id: int, field: str) -> int | None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
        return None if row is None else getattr(row, field)
