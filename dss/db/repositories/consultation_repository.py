"""Repository for the `consultations` domain (Phase 1B, migration order item 8).

Real existing runtime being cut over: `dss/core/warehouse.py::save_ai_consultation()`
(JSON history file). Wired at that exact call site, gated by
`dss.core.persistence_config.is_postgres_enabled("CONSULTATIONS")`.
"""
from __future__ import annotations

from typing import Any, Optional

from dss.db.models import Consultation, Student
from dss.db.session import tenant_session_scope


def save_consultation(
    organization_id: int,
    provider: str,
    student_code: Optional[str] = None,
    model: Optional[str] = None,
    question: Optional[str] = None,
    answer: Optional[str] = None,
    local_consultation_id: Optional[str] = None,
) -> int:
    with tenant_session_scope(organization_id) as session:
        student_id = None
        if student_code:
            s = session.query(Student).filter_by(organization_id=organization_id, student_code=student_code).one_or_none()
            student_id = s.id if s else None
        record = Consultation(
            organization_id=organization_id, student_id=student_id, provider=provider,
            model=model, question=question, answer=answer,
            local_consultation_id=local_consultation_id,
        )
        session.add(record)
        session.flush()
        return record.id


def import_from_local_history(organization_id: int, warehouse=None) -> dict[str, int]:
    """Idempotent migration of the PRE-EXISTING local `advisor_history.json`
    (dss/core/warehouse.py::save_ai_consultation's local path) into Postgres.
    Safe to run more than once — dedupes on `local_consultation_id`."""
    if warehouse is None:
        from dss.core.warehouse import DataWarehouse
        warehouse = DataWarehouse()

    local_records = warehouse.get_history("advisor", limit=10_000_000)
    with tenant_session_scope(organization_id) as session:
        already_imported = {
            row.local_consultation_id
            for row in session.query(Consultation).filter_by(organization_id=organization_id).all()
            if row.local_consultation_id
        }

    imported = 0
    skipped = 0
    for rec in local_records:
        local_id = rec.get("consultation_id")
        if local_id and local_id in already_imported:
            skipped += 1
            continue
        student_code = rec.get("student_id")
        save_consultation(
            organization_id=organization_id,
            provider=rec.get("provider", "unknown"),
            student_code=student_code if student_code and student_code != "unknown" else None,
            model=rec.get("model_name") or None,
            question=rec.get("rag_query") or None,
            answer=rec.get("generated_plan") or None,
            local_consultation_id=local_id,
        )
        imported += 1

    return {"imported": imported, "skipped_already_imported": skipped, "total_local_records": len(local_records)}


def list_consultations(organization_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        rows = (
            session.query(Consultation)
            .filter_by(organization_id=organization_id)
            .order_by(Consultation.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [
            {
                "id": r.id, "student_id": r.student_id, "provider": r.provider,
                "model": r.model, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
