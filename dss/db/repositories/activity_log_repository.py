"""Repository for the `activity_logs` domain (Phase 1C, priority item 9 —
"evaluation/training history" / user-facing activity feed).

Real existing runtime being cut over: `dss/core/warehouse.py::log_activity()`
(local JSON, `{data_root}/history/activity_history.json` +
`{data_root}/history/activities.json`). The `activity_logs` table already
existed in the Phase 1 schema (`ActivityLog` in dss/db/models.py, mirroring
`log_activity`'s exact fields) but had no repository or live call site until
this phase — a pure schema-only domain being completed here, not a redesign.

Distinct from `dss/db/repositories/audit_log_repository.py` (the SECURITY
trail for sensitive admin actions like model promote/rollback, already
live-wired since Phase 1) — this is the separate USER-FACING "recent
activity" feed shown in dashboards, matching `ActivityLog`'s own docstring.
"""

from __future__ import annotations

from typing import Any, Optional

from dss.db.models import ActivityLog
from dss.db.session import tenant_session_scope


def record_activity(
    organization_id: int,
    action_type: str,
    description: str,
    details: Optional[dict] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> int:
    """Not idempotent by design — an activity entry is a point-in-time
    event, matching academic_records'/recommendations' append-only
    semantics established in Phase 1B.

    Bước 9: `username` (người đang đăng nhập) được đổi thành users.id trong cùng tổ chức, để
    data_lifecycle.erase_student_data ẩn được nội dung hoạt động của sinh viên đó."""
    with tenant_session_scope(organization_id) as session:
        if user_id is None and username:
            from sqlalchemy import func

            from dss.db.models import User

            user_id = (
                session.query(User.id)
                .filter(User.organization_id == organization_id, func.lower(User.username) == str(username).lower())
                .scalar()
            )
        row = ActivityLog(
            organization_id=organization_id,
            user_id=user_id,
            action_type=action_type,
            description=description,
            details=details or {},
        )
        session.add(row)
        session.flush()
        return row.id


def get_recent_activities(organization_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        rows = (
            session.query(ActivityLog)
            .filter_by(organization_id=organization_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "action": r.action_type,
                "details": r.description,
                "metadata": r.details or {},
                "timestamp": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def import_from_local_history(organization_id: int, warehouse=None) -> dict[str, int]:
    """Idempotent migration of the PRE-EXISTING local `activity_history.json`
    into Postgres — dedupes on the local record's own `activity_id` (stored
    in `details["_local_activity_id"]`), matching the exact pattern used by
    prediction_repository.import_from_local_history / consultation_repository's
    equivalent."""
    if warehouse is None:
        from dss.core.warehouse import DataWarehouse

        warehouse = DataWarehouse()

    # Bước 9: đọc thẳng tệp — get_history("activity") trả dữ liệu PostgreSQL khi kho này đã bật postgres.
    local_records = warehouse.read_history_file("activity", limit=10_000_000)
    with tenant_session_scope(organization_id) as session:
        already_imported = {
            row.details.get("_local_activity_id")
            for row in session.query(ActivityLog).filter_by(organization_id=organization_id).all()
            if row.details and row.details.get("_local_activity_id")
        }

    imported = 0
    skipped = 0
    for rec in local_records:
        local_id = rec.get("activity_id")
        if local_id and local_id in already_imported:
            skipped += 1
            continue
        details = dict(rec.get("details") or {})
        details["_local_activity_id"] = local_id
        record_activity(
            organization_id=organization_id,
            action_type=rec.get("activity_type", "unknown"),
            description=rec.get("description", ""),
            details=details,
        )
        imported += 1

    return {"imported": imported, "skipped_already_imported": skipped, "total_local_records": len(local_records)}
