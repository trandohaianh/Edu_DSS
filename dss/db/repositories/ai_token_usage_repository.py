"""Repository for the `ai_token_usage` domain (Phase 1C, priority item 10 —
"AI token usage").

Real existing runtime being cut over: `dss/services/token_tracker.py` (local
JSON, `{data_root}/ai_token_usage.json`, append-only, capped at 50,000
records, single read choke-point `_load_all_records()` used by every
aggregation function). This repository preserves that exact shape — callers
get back plain dicts identical to the local JSON records — so
`token_tracker.py`'s existing aggregation functions (daily usage, quota
check, budget status, usage summary) work unchanged against either backend.

NEVER stores API keys, Authorization headers, or full prompts — only
accounting metadata (provider, model, token counts, cost estimate), matching
`UsageRecord`'s existing fields exactly. `user_id` arrives already
anonymized by `token_tracker.record_usage()` (email-like ids are rewritten
to `user_<local-part>` before this repository ever sees them).
"""
from __future__ import annotations

from typing import Any, Optional

from dss.db.models import AiTokenUsage
from dss.db.session import tenant_session_scope


def record_usage(organization_id: int, record: dict[str, Any]) -> None:
    """`record` is a `dataclasses.asdict(UsageRecord)` dict — same shape
    `token_tracker.py` already builds for the local-JSON path."""
    from datetime import datetime

    with tenant_session_scope(organization_id) as session:
        row = AiTokenUsage(
            organization_id=organization_id,
            usage_id=record["usage_id"],
            timestamp=datetime.fromisoformat(record["timestamp"]),
            user_id=record["user_id"],
            role=record["role"],
            request_type=record["request_type"],
            provider=record["provider"],
            model=record["model"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
            total_tokens=record["total_tokens"],
            estimated_cost=record["estimated_cost"],
        )
        session.add(row)


def load_all_records(organization_id: int, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Returns records in the exact dict shape `token_tracker._load_all_records()`
    produces locally, so every existing aggregation function
    (get_user_daily_token_usage / check_user_quota / get_system_budget_status /
    get_usage_summary) works unchanged."""
    with tenant_session_scope(organization_id) as session:
        query = (
            session.query(AiTokenUsage)
            .filter_by(organization_id=organization_id)
            .order_by(AiTokenUsage.timestamp.asc())
        )
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        return [
            {
                "usage_id": r.usage_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "user_id": r.user_id,
                "role": r.role,
                "request_type": r.request_type,
                "provider": r.provider,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "estimated_cost": r.estimated_cost,
            }
            for r in rows
        ]
