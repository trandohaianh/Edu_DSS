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
    performed_by: Optional[str] = None,
    performed_by_role: Optional[str] = None,
    details: Optional[dict] = None,
    created_at: Optional[str] = None,
) -> int:
    from dss.db.repositories.academic_repository import resolve_or_create_student_id

    with tenant_session_scope(organization_id) as session:
        record = Consultation(
            organization_id=organization_id,
            student_id=resolve_or_create_student_id(session, organization_id, student_code),
            provider=provider,
            model=model,
            question=question,
            answer=answer,
            local_consultation_id=local_consultation_id,
            performed_by=str(performed_by)[:128] if performed_by else None,
            performed_by_role=str(performed_by_role)[:64] if performed_by_role else None,
            details=details or None,
        )
        if created_at:
            from dss.db.repositories.prediction_repository import _parse_ts

            record.created_at = _parse_ts(created_at)
        session.add(record)
        session.flush()
        return record.id


_DETAIL_KEYS = ("predicted_gpa", "weaknesses", "embedding_model", "top_documents", "metadata")


def details_from_local(rec: dict[str, Any]) -> dict[str, Any]:
    """Các trường của advisor_history.json không có cột riêng (bước 9)."""
    return {k: rec.get(k) for k in _DETAIL_KEYS if rec.get(k) not in (None, "", [], {})}


def list_history(organization_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Bước 9: lịch sử tư vấn theo ĐÚNG dạng bản ghi của advisor_history.json, để
    `DataWarehouse.get_history("advisor")` và các trang đang đọc nó chạy không đổi khi
    EDUDSS_CONSULTATIONS_STORE=postgres."""
    with tenant_session_scope(organization_id) as session:
        rows = (
            session.query(Consultation, Student.student_code)
            .outerjoin(Student, Student.id == Consultation.student_id)
            .filter(Consultation.organization_id == organization_id)
            .order_by(Consultation.created_at.desc(), Consultation.id.desc())
            .limit(limit)
            .all()
        )
        out = []
        for r, student_code in rows:
            details = dict(r.details or {})
            out.append(
                {
                    "consultation_id": r.local_consultation_id or f"pg-{r.id}",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "student_id": student_code or "unknown",
                    "predicted_gpa": details.get("predicted_gpa"),
                    "weaknesses": details.get("weaknesses", []),
                    "provider": r.provider,
                    "model_name": r.model or "",
                    "embedding_model": details.get("embedding_model", ""),
                    "rag_query": r.question or "",
                    "top_documents": details.get("top_documents", []),
                    "generated_plan": r.answer or "",
                    "metadata": details.get("metadata", {}),
                    "performed_by": r.performed_by,
                    "performed_by_role": r.performed_by_role,
                }
            )
        return out


def import_from_local_history(organization_id: int, warehouse=None) -> dict[str, int]:
    """Idempotent migration of the PRE-EXISTING local `advisor_history.json`
    (dss/core/warehouse.py::save_ai_consultation's local path) into Postgres.
    Safe to run more than once — dedupes on `local_consultation_id`."""
    if warehouse is None:
        from dss.core.warehouse import DataWarehouse

        warehouse = DataWarehouse()

    # Bước 9: đọc thẳng tệp — get_history("advisor") trả dữ liệu PostgreSQL khi kho này đã bật postgres.
    local_records = warehouse.read_history_file("advisor", limit=10_000_000)
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
            performed_by=rec.get("performed_by"),
            performed_by_role=rec.get("performed_by_role"),
            details=details_from_local(rec),
            created_at=rec.get("created_at"),
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
                "id": r.id,
                "student_id": r.student_id,
                "provider": r.provider,
                "model": r.model,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
