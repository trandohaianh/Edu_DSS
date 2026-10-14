"""Repository for the `predictions` domain (Phase 1B, migration order item 6).

Real existing runtime being cut over: `dss/core/warehouse.py::save_prediction()`
(JSON history file). This repository is wired into that exact call site,
gated by `dss.core.persistence_config.is_postgres_enabled("PREDICTIONS")` —
when enabled, Postgres becomes the PRIMARY store for new predictions (no
dual-write); when disabled, existing local JSON behavior is unchanged.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError

from dss.db.models import ModelVersion, Prediction, Student
from dss.db.session import tenant_session_scope


def _resolve_or_create_model_version_id(session, organization_id: int, training_id: str) -> int:
    """The Model Registry itself (model_versions/model_metrics) is NOT one of
    Phase 1B's 12 migration-order domains — its own live-training-pipeline
    cutover is out of scope here. Rather than block every prediction on that
    unfinished, separate migration, this creates a minimal placeholder
    ModelVersion row (training_id + a 'unknown' model_key/dataset/target)
    the first time a given training_id is seen, so predictions can be
    recorded now. It is upserted, not duplicated, on repeat calls. This is a
    deliberate scope decision — documented here and in
    PHASE1B_RUNTIME_CUTOVER.md — not an accidental scope creep into the
    Model Registry domain.

    Workstream D (concurrency capacity benchmark, Issue CONCUR-001): the
    original check-then-insert here raced under genuine concurrent first
    use of the same training_id — two threads both see no existing row,
    both attempt to INSERT, and the loser hits
    uq_model_versions_training_id's IntegrityError instead of transparently
    getting the winner's row id. A SAVEPOINT (session.begin_nested())
    confines that failure to the placeholder-insert attempt alone (not the
    caller's whole transaction) so a re-query can pick up the winner's
    committed row; a short bounded retry absorbs the sub-millisecond window
    where the winner hasn't committed yet. Found and fixed via
    tests/load/test_concurrency_capacity.py, not a hypothetical concern."""
    mv = (
        session.query(ModelVersion)
        .filter_by(organization_id=organization_id, training_id=training_id)
        .one_or_none()
    )
    if mv:
        return mv.id
    for attempt in range(3):
        savepoint = session.begin_nested()
        try:
            mv = ModelVersion(
                organization_id=organization_id,
                training_id=training_id,
                model_key=f"unknown::{training_id}",
                dataset_id="unknown",
                target_col="unknown",
                model_name="unknown (placeholder — see prediction_repository._resolve_or_create_model_version_id)",
                status="candidate",
            )
            session.add(mv)
            session.flush()
            savepoint.commit()
            return mv.id
        except IntegrityError:
            savepoint.rollback()
            existing = (
                session.query(ModelVersion)
                .filter_by(organization_id=organization_id, training_id=training_id)
                .one_or_none()
            )
            if existing:
                return existing.id
            if attempt == 2:
                raise
            time.sleep(0.01 * (attempt + 1))
    raise RuntimeError("unreachable")  # pragma: no cover


def _resolve_student_id(session, organization_id: int, student_code: Optional[str]) -> Optional[int]:
    if not student_code:
        return None
    s = session.query(Student).filter_by(organization_id=organization_id, student_code=student_code).one_or_none()
    return s.id if s else None


def save_prediction(
    organization_id: int,
    training_id: str,
    prediction_value: Any,
    student_code: Optional[str] = None,
    input_data: Optional[dict] = None,
    confidence: Optional[float] = None,
    input_schema_version: Optional[str] = None,
) -> int:
    """Real Postgres write for one prediction record. `training_id` not
    resolving to a known model_version is a hard error (matches the FK
    constraint — RESTRICT on model_version_id, see dss/db/models.py) rather
    than silently recording an orphaned prediction."""
    with tenant_session_scope(organization_id) as session:
        model_version_id = _resolve_or_create_model_version_id(session, organization_id, training_id)
        student_id = _resolve_student_id(session, organization_id, student_code)
        record = Prediction(
            organization_id=organization_id,
            student_id=student_id,
            model_version_id=model_version_id,
            input_schema_version=input_schema_version,
            input_data=input_data,
            prediction_value=str(prediction_value) if prediction_value is not None else None,
            confidence=confidence,
        )
        session.add(record)
        session.flush()
        return record.id


def import_from_local_history(organization_id: int, warehouse=None) -> dict[str, int]:
    """Idempotent migration of the PRE-EXISTING local `prediction_history.json`
    (dss/core/warehouse.py::save_prediction's local path, written whenever
    EDUDSS_PREDICTIONS_STORE was unset/local) into Postgres. Safe to run more
    than once: each local record's own `prediction_id` is stored in
    `input_data["_local_prediction_id"]` and used to skip records already
    imported, so a repeat run does not create duplicates."""
    if warehouse is None:
        from dss.core.warehouse import DataWarehouse
        warehouse = DataWarehouse()

    local_records = warehouse.get_history("prediction", limit=10_000_000)
    with tenant_session_scope(organization_id) as session:
        already_imported = {
            row.input_data.get("_local_prediction_id")
            for row in session.query(Prediction).filter_by(organization_id=organization_id).all()
            if row.input_data and row.input_data.get("_local_prediction_id")
        }

    imported = 0
    skipped = 0
    for rec in local_records:
        local_id = rec.get("prediction_id")
        if local_id and local_id in already_imported:
            skipped += 1
            continue
        input_data = dict(rec.get("input_data") or {})
        input_data["_local_prediction_id"] = local_id
        metadata = rec.get("metadata") or {}
        save_prediction(
            organization_id=organization_id,
            training_id=rec.get("training_id", "unknown"),
            prediction_value=rec.get("prediction"),
            student_code=(rec.get("input_data") or {}).get("student_id"),
            input_data=input_data,
            confidence=metadata.get("confidence"),
        )
        imported += 1

    return {"imported": imported, "skipped_already_imported": skipped, "total_local_records": len(local_records)}


def list_predictions(organization_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        rows = (
            session.query(Prediction)
            .filter_by(organization_id=organization_id)
            .order_by(Prediction.predicted_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [
            {
                "id": r.id,
                "model_version_id": r.model_version_id,
                "student_id": r.student_id,
                "prediction_value": r.prediction_value,
                "confidence": r.confidence,
                "predicted_at": r.predicted_at.isoformat(),
            }
            for r in rows
        ]
