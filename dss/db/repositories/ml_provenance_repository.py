"""Repository for ML governance provenance/drift (Workstream C).

Gated by `dss.core.persistence_config.is_postgres_enabled("ML_PROVENANCE")`
— unlike every other repository in this package, this one does NOT replace
an existing local store: dss/core/warehouse.py's joblib+JSON storage remains
the primary, unconditional model artifact store. This repository only
mirrors structured metadata for governance/queryability. See that flag's
comment in dss/core/persistence_config.py and
dss/services/ml_provenance.py's module docstring for the full rationale.

Every public function here upserts (never duplicates) on its natural key, so
calling `record_model_version` more than once for the same
(organization_id, training_id) — e.g. once from provenance recording at
training time, once later from prediction_repository's pre-existing
placeholder-creation path — updates the SAME row rather than creating a
second one; whichever call has real data "wins" over a placeholder.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from dss.db.models import DatasetProvenance, DriftEvaluation, FeatureSchemaProvenance, ModelMetric, ModelVersion
from dss.db.session import tenant_session_scope


def record_dataset_provenance(
    organization_id: int,
    dataset_id: str,
    source_type: str,
    schema_fingerprint: str,
    dataset_fingerprint: str,
    row_count: int,
    column_count: int,
    feature_list: list[str],
    logical_name: Optional[str] = None,
    source_reference: Optional[str] = None,
    target_column: Optional[str] = None,
    null_stats: Optional[dict] = None,
    numeric_summary: Optional[dict] = None,
    lineage_metadata: Optional[dict] = None,
    ingestion_at: Optional[datetime] = None,
) -> int:
    """Upserts on (organization_id, dataset_id, dataset_fingerprint) — the
    same dataset_id evolving over time produces new rows (new fingerprint),
    not overwritten history."""
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(DatasetProvenance)
            .filter_by(organization_id=organization_id, dataset_id=dataset_id, dataset_fingerprint=dataset_fingerprint)
            .one_or_none()
        )
        if existing:
            return existing.id
        row = DatasetProvenance(
            organization_id=organization_id,
            dataset_id=dataset_id,
            logical_name=logical_name,
            source_type=source_type,
            source_reference=source_reference,
            row_count=row_count,
            column_count=column_count,
            schema_fingerprint=schema_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            target_column=target_column,
            feature_list=list(feature_list),
            null_stats=null_stats,
            numeric_summary=numeric_summary,
            lineage_metadata=lineage_metadata,
            ingestion_at=ingestion_at,
        )
        session.add(row)
        session.flush()
        return row.id


def record_feature_schema_provenance(
    organization_id: int,
    fingerprint: str,
    feature_names: list[str],
    feature_dtypes: dict[str, str],
    feature_roles: dict[str, str],
    model_task_type: str,
    target_definition: Optional[str] = None,
    preprocessing_expectations: Optional[dict] = None,
) -> int:
    """Upserts on (organization_id, fingerprint) — deterministically the
    same row for the same input contract, by construction."""
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(FeatureSchemaProvenance)
            .filter_by(organization_id=organization_id, fingerprint=fingerprint)
            .one_or_none()
        )
        if existing:
            return existing.id
        row = FeatureSchemaProvenance(
            organization_id=organization_id,
            fingerprint=fingerprint,
            feature_names=list(feature_names),
            feature_dtypes=feature_dtypes,
            feature_roles=feature_roles,
            target_definition=target_definition,
            model_task_type=model_task_type,
            preprocessing_expectations=preprocessing_expectations,
        )
        session.add(row)
        session.flush()
        return row.id


def record_model_version(
    organization_id: int,
    training_id: str,
    model_key: str,
    dataset_id: str,
    target_col: str,
    model_name: str,
    status: str = "candidate",
    algorithm: Optional[str] = None,
    dataset_version: Optional[str] = None,
    owner: Optional[str] = None,
    feature_schema: Optional[dict] = None,
    artifact_path: Optional[str] = None,
    artifact_checksum_sha256: Optional[str] = None,
    dataset_provenance_id: Optional[int] = None,
    feature_schema_provenance_id: Optional[int] = None,
    hyperparameters: Optional[dict] = None,
    code_commit: Optional[str] = None,
    python_version: Optional[str] = None,
    library_versions: Optional[dict] = None,
    created_by: Optional[str] = None,
) -> int:
    """Upserts on (organization_id, training_id) — real provenance data
    always overwrites a pre-existing placeholder row created by
    prediction_repository._resolve_or_create_model_version_id (same natural
    key), never creates a duplicate ModelVersion for the same training run."""
    with tenant_session_scope(organization_id) as session:
        row = (
            session.query(ModelVersion)
            .filter_by(organization_id=organization_id, training_id=training_id)
            .one_or_none()
        )
        if row is None:
            row = ModelVersion(organization_id=organization_id, training_id=training_id)
            session.add(row)
        row.model_key = model_key
        row.dataset_id = dataset_id
        row.target_col = target_col
        row.model_name = model_name
        row.status = status
        row.algorithm = algorithm
        row.dataset_version = dataset_version
        row.owner = owner
        row.feature_schema = feature_schema
        row.artifact_path = artifact_path
        row.artifact_checksum_sha256 = artifact_checksum_sha256
        row.dataset_provenance_id = dataset_provenance_id
        row.feature_schema_provenance_id = feature_schema_provenance_id
        row.hyperparameters = hyperparameters
        row.code_commit = code_commit
        row.python_version = python_version
        row.library_versions = library_versions
        row.created_by = created_by
        session.flush()
        return row.id


def record_model_metrics(organization_id: int, model_version_id: int, metrics: dict[str, float]) -> int:
    """Replaces (not accumulates) the metric rows for this model_version_id
    — a repeat call with updated metrics for the same version reflects the
    latest evaluation, matching the single-source-of-truth principle already
    used elsewhere in this schema (e.g. model_versions.status)."""
    with tenant_session_scope(organization_id) as session:
        session.query(ModelMetric).filter(
            ModelMetric.model_version_id == model_version_id,
            ModelMetric.model_version_id.in_(session.query(ModelVersion.id).filter_by(organization_id=organization_id)),
        ).delete(synchronize_session=False)
        count = 0
        for name, value in (metrics or {}).items():
            if not isinstance(value, (int, float)):
                continue
            session.add(
                ModelMetric(model_version_id=model_version_id, metric_name=str(name), metric_value=float(value))
            )
            count += 1
        session.flush()
        return count


def record_drift_evaluation(
    organization_id: int,
    model_version_id: int,
    evaluation_type: str,
    overall_status: str,
    recommended_action: str,
    details: dict,
    thresholds_used: dict,
    baseline_dataset_provenance_id: Optional[int] = None,
    current_window_description: Optional[dict] = None,
    evaluated_by: Optional[str] = None,
    evaluated_at: Optional[datetime] = None,
) -> int:
    with tenant_session_scope(organization_id) as session:
        row = DriftEvaluation(
            organization_id=organization_id,
            model_version_id=model_version_id,
            evaluation_type=evaluation_type,
            baseline_dataset_provenance_id=baseline_dataset_provenance_id,
            current_window_description=current_window_description,
            thresholds_used=thresholds_used,
            overall_status=overall_status,
            recommended_action=recommended_action,
            details=details,
            evaluated_at=evaluated_at or datetime.now(UTC),
            evaluated_by=evaluated_by,
        )
        session.add(row)
        session.flush()
        return row.id


def get_model_provenance(organization_id: int, training_id: str) -> Optional[dict[str, Any]]:
    """The MODEL -> VERSION -> DATASET -> FEATURE SCHEMA -> METRICS ->
    ARTIFACT -> DRIFT HISTORY -> STATUS chain (§9), read back as one dict."""
    with tenant_session_scope(organization_id) as session:
        mv = (
            session.query(ModelVersion)
            .filter_by(organization_id=organization_id, training_id=training_id)
            .one_or_none()
        )
        if mv is None:
            return None
        dataset = session.get(DatasetProvenance, mv.dataset_provenance_id) if mv.dataset_provenance_id else None
        feature_schema_prov = (
            session.get(FeatureSchemaProvenance, mv.feature_schema_provenance_id)
            if mv.feature_schema_provenance_id
            else None
        )
        metrics = {m.metric_name: m.metric_value for m in mv.metrics}
        drift_history = (
            session.query(DriftEvaluation)
            .filter_by(organization_id=organization_id, model_version_id=mv.id)
            .order_by(DriftEvaluation.evaluated_at.desc())
            .all()
        )
        return {
            "model_version": {
                "id": mv.id,
                "training_id": mv.training_id,
                "model_key": mv.model_key,
                "dataset_id": mv.dataset_id,
                "target_col": mv.target_col,
                "model_name": mv.model_name,
                "algorithm": mv.algorithm,
                "status": mv.status,
                "artifact_path": mv.artifact_path,
                "artifact_checksum_sha256": mv.artifact_checksum_sha256,
                "hyperparameters": mv.hyperparameters,
                "code_commit": mv.code_commit,
                "python_version": mv.python_version,
                "library_versions": mv.library_versions,
                "created_by": mv.created_by,
                "trained_at": mv.trained_at.isoformat() if mv.trained_at else None,
            },
            "dataset_provenance": (
                {
                    "id": dataset.id,
                    "dataset_id": dataset.dataset_id,
                    "row_count": dataset.row_count,
                    "column_count": dataset.column_count,
                    "schema_fingerprint": dataset.schema_fingerprint,
                    "dataset_fingerprint": dataset.dataset_fingerprint,
                    "feature_list": dataset.feature_list,
                }
                if dataset
                else None
            ),
            "feature_schema_provenance": (
                {
                    "id": feature_schema_prov.id,
                    "fingerprint": feature_schema_prov.fingerprint,
                    "feature_names": feature_schema_prov.feature_names,
                    "feature_dtypes": feature_schema_prov.feature_dtypes,
                    "feature_roles": feature_schema_prov.feature_roles,
                    "model_task_type": feature_schema_prov.model_task_type,
                    "preprocessing_expectations": feature_schema_prov.preprocessing_expectations,
                }
                if feature_schema_prov
                else None
            ),
            "metrics": metrics,
            "drift_history": [
                {
                    "id": d.id,
                    "evaluation_type": d.evaluation_type,
                    "overall_status": d.overall_status,
                    "recommended_action": d.recommended_action,
                    "evaluated_at": d.evaluated_at.isoformat(),
                }
                for d in drift_history
            ],
        }
