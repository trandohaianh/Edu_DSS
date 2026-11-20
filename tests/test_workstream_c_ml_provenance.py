"""Real PostgreSQL/RLS acceptance tests for Workstream C ML provenance/drift.

Follows the exact same pattern as tests/test_workstream_b_persistence_closure.py
and tests/test_workstream_ab_postgres_integration.py: skipped unless real
PostgreSQL URLs are provided, `DATABASE_URL` set to the tenant's own
(non-superuser) app-role connection — never an owner/superuser bypass — so
every assertion here is a genuine RLS/tenant-isolation check, not a
trust-the-owner-connection check.
"""
from __future__ import annotations

import os
import uuid

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_C_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_C_DATABASE_URL")
pytestmark = pytest.mark.skipif(not OWNER_URL or not APP_URL, reason="Workstream C PostgreSQL URLs are required")


class _FakePipeline:
    """A minimal picklable stand-in for a fitted sklearn Pipeline — matches
    tests/test_model_registry.py's convention (these tests verify the
    PROVENANCE/REGISTRY layer, not ML algorithm correctness, which is
    covered elsewhere). Exposes `steps`/`get_params` like a real sklearn
    Pipeline so dss.services.ml_provenance's introspection functions behave
    the same way they would against a real one."""

    def __init__(self, tag, **params):
        self.tag = tag
        self._params = params
        self.steps = [("model", self)]

    def get_params(self, deep=False):
        return dict(self._params)

    def predict(self, X):
        return [self.tag] * len(X)


@pytest.fixture
def tenant(monkeypatch):
    owner = create_engine(OWNER_URL)
    code = "c_" + uuid.uuid4().hex[:10]
    with owner.begin() as conn:
        org = conn.execute(
            text("INSERT INTO organizations (org_code,name,is_active,created_at,updated_at) VALUES (:c,:n,true,now(),now()) RETURNING id"),
            {"c": code, "n": code},
        ).scalar_one()
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org))
    monkeypatch.setenv("EDUDSS_ML_PROVENANCE_STORE", "postgres")
    from dss.db.session import reset_engine_for_tests
    reset_engine_for_tests()
    yield org
    reset_engine_for_tests()
    owner.dispose()


@pytest.fixture
def warehouse(tmp_path):
    from dss.core.warehouse import DataWarehouse
    return DataWarehouse(base_path=str(tmp_path / "data_warehouse"))


def _sample_training_frame(n=100, seed=0):
    rng = np.random.RandomState(seed)
    return pd.DataFrame({
        "gpa": rng.uniform(1.5, 4.0, n),
        "attendance": rng.uniform(0.4, 1.0, n),
        "major": rng.choice(["CS", "Math"], n),
    })


def _train_and_save(warehouse, dataset_id="ds_gpa_v1", target_col="at_risk", model_name="RandomForest", tag="v1", X_train=None):
    return warehouse.save_model_training(
        dataset_id=dataset_id,
        model_pipeline=_FakePipeline(tag, n_estimators=50, max_depth=5),
        model_name=model_name,
        feature_cols=["gpa", "attendance", "major"],
        target_col=target_col,
        metrics={"accuracy": 0.87, "f1": 0.83},
        is_best=True,
        auto_promote=False,
        X_train=X_train if X_train is not None else _sample_training_frame(),
        y_train=pd.Series([0, 1] * 50),
        class_labels=[0, 1],  # makes this a classification run — see warehouse.py's model_task_type inference
        promoted_by="test_lecturer",
    )


def test_01_training_provenance_recorded_with_checksum_and_linkage(tenant, warehouse):
    import hashlib

    training_id, meta = _train_and_save(warehouse)

    from dss.services import model_registry
    provenance = model_registry.get_provenance(training_id, organization_id=tenant)
    assert provenance is not None, "provenance should be recorded when EDUDSS_ML_PROVENANCE_STORE=postgres"

    mv = provenance["model_version"]
    assert mv["training_id"] == training_id
    assert mv["dataset_id"] == "ds_gpa_v1"
    assert mv["target_col"] == "at_risk"
    assert mv["algorithm"] == "_FakePipeline"  # introspected from the pipeline's own class
    assert mv["hyperparameters"] == {"n_estimators": 50, "max_depth": 5}
    assert mv["python_version"]
    assert mv["status"] == "candidate"

    # Checksum matches the ACTUAL artifact on disk (matches warehouse.py's
    # own SHA-256, computed independently here to prove it's the real hash,
    # not just echoed back).
    with open(meta["model_path"], "rb") as f:
        real_sha256 = hashlib.sha256(f.read()).hexdigest()
    assert mv["artifact_checksum_sha256"] == real_sha256
    assert mv["artifact_checksum_sha256"] == meta["model_sha256"]

    assert provenance["dataset_provenance"]["row_count"] == 100
    assert set(provenance["dataset_provenance"]["feature_list"]) == {"gpa", "attendance", "major"}
    assert provenance["feature_schema_provenance"]["model_task_type"] == "classification"
    assert provenance["feature_schema_provenance"]["feature_names"] == ["gpa", "attendance", "major"]
    assert provenance["metrics"] == {"accuracy": 0.87, "f1": 0.83}


def test_02_dataset_and_feature_schema_fingerprints_deduplicate_across_trainings(tenant, warehouse):
    """Two separate training runs on the SAME dataset content and SAME
    feature contract must reuse the SAME dataset_provenance/
    feature_schema_provenance rows (deterministic fingerprint dedup), not
    create duplicate provenance rows for identical inputs."""
    same_frame = _sample_training_frame(seed=1)
    training_id_a, _ = _train_and_save(warehouse, model_name="ModelA", tag="a", X_train=same_frame)
    training_id_b, _ = _train_and_save(warehouse, model_name="ModelB", tag="b", X_train=same_frame)

    from dss.services import model_registry
    prov_a = model_registry.get_provenance(training_id_a, organization_id=tenant)
    prov_b = model_registry.get_provenance(training_id_b, organization_id=tenant)

    assert prov_a["dataset_provenance"]["id"] == prov_b["dataset_provenance"]["id"]
    assert prov_a["feature_schema_provenance"]["id"] == prov_b["feature_schema_provenance"]["id"]
    assert prov_a["model_version"]["id"] != prov_b["model_version"]["id"]  # distinct model versions


def test_03_different_dataset_content_produces_different_provenance(tenant, warehouse):
    training_id_a, _ = _train_and_save(warehouse, X_train=_sample_training_frame(seed=1))
    training_id_b, _ = _train_and_save(warehouse, X_train=_sample_training_frame(seed=2))

    from dss.services import model_registry
    prov_a = model_registry.get_provenance(training_id_a, organization_id=tenant)
    prov_b = model_registry.get_provenance(training_id_b, organization_id=tenant)
    assert prov_a["dataset_provenance"]["dataset_fingerprint"] != prov_b["dataset_provenance"]["dataset_fingerprint"]


def test_04_provenance_disabled_by_default_is_a_pure_no_op(tenant, warehouse, monkeypatch):
    """Flipping the flag back to local (the default) must not error and
    must not record anything — matches every other is_postgres_enabled
    feature's documented off-by-default contract."""
    monkeypatch.setenv("EDUDSS_ML_PROVENANCE_STORE", "local")
    training_id, _ = _train_and_save(warehouse, dataset_id="ds_disabled")

    from dss.services import model_registry
    assert model_registry.get_provenance(training_id, organization_id=tenant) is None


def test_05_drift_evaluation_persisted_and_queryable(tenant, warehouse):
    training_id, _ = _train_and_save(warehouse, dataset_id="ds_drift")
    baseline = _sample_training_frame(seed=3)
    current = baseline.copy()
    current["gpa"] = current["gpa"] + 5.0  # unmistakable numeric drift
    y_true = np.random.RandomState(3).randint(0, 2, 100)

    from dss.services import model_registry
    result = model_registry.evaluate_drift(
        training_id, baseline, current,
        y_true_baseline=y_true, y_pred_baseline=y_true,
        y_true_current=y_true, y_pred_current=1 - y_true,
        task_type="classification", organization_id=tenant, evaluated_by="test_admin",
    )
    assert result["data_drift"]["overall_status"] == "DRIFT_DETECTED"
    assert result["performance_drift"]["overall_status"] == "DRIFT_DETECTED"
    assert result["recommended_action"] == "RETRAIN_RECOMMENDED"

    provenance = model_registry.get_provenance(training_id, organization_id=tenant)
    history = provenance["drift_history"]
    assert len(history) == 2  # one data_drift row, one performance_drift row
    assert {h["evaluation_type"] for h in history} == {"data_drift", "performance_drift"}
    assert all(h["recommended_action"] == "RETRAIN_RECOMMENDED" for h in history)


def test_06_missing_ground_truth_recorded_as_not_evaluable_never_fabricated(tenant, warehouse):
    training_id, _ = _train_and_save(warehouse, dataset_id="ds_no_labels")
    baseline = _sample_training_frame(seed=4)
    current = baseline.copy()

    from dss.services import model_registry
    result = model_registry.evaluate_drift(training_id, baseline, current, organization_id=tenant)
    assert result["performance_drift"]["overall_status"] == "PERFORMANCE_DRIFT_NOT_EVALUABLE"

    provenance = model_registry.get_provenance(training_id, organization_id=tenant)
    perf_row = next(h for h in provenance["drift_history"] if h["evaluation_type"] == "performance_drift")
    assert perf_row["overall_status"] == "PERFORMANCE_DRIFT_NOT_EVALUABLE"


def test_07_non_superuser_cross_tenant_provenance_and_drift_isolated(tenant, warehouse, monkeypatch):
    """Second organization, same APP_URL (non-superuser) connection —
    genuine RLS check, not a schema-owner bypass (see module docstring)."""
    org_a = tenant
    training_id_a, _ = _train_and_save(warehouse, dataset_id="ds_isolation_a")
    baseline = _sample_training_frame(seed=5)
    from dss.services import model_registry
    model_registry.evaluate_drift(training_id_a, baseline, baseline.copy(), organization_id=org_a)

    owner = create_engine(OWNER_URL)
    with owner.begin() as conn:
        org_b = conn.execute(
            text("INSERT INTO organizations (org_code,name,is_active,created_at,updated_at) VALUES (:c,:n,true,now(),now()) RETURNING id"),
            {"c": "c_org_b_" + uuid.uuid4().hex[:8], "n": "org_b"},
        ).scalar_one()
    owner.dispose()

    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_b))
    from dss.db.session import reset_engine_for_tests
    reset_engine_for_tests()

    # Org B, using the SAME non-superuser app role, must not be able to read
    # org A's provenance/drift rows at all — RLS fails closed to "not found",
    # not to an error or to org A's real data.
    assert model_registry.get_provenance(training_id_a, organization_id=org_b) is None

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id = :o"), {"o": str(org_b)})
        cross_tenant_count = conn.execute(text("SELECT count(*) FROM dataset_provenance")).scalar_one()
        cross_tenant_drift_count = conn.execute(text("SELECT count(*) FROM drift_evaluations")).scalar_one()
    app_engine.dispose()
    assert cross_tenant_count == 0
    assert cross_tenant_drift_count == 0


def test_08_algorithm_and_library_versions_introspected(tenant, warehouse):
    training_id, _ = _train_and_save(warehouse, dataset_id="ds_introspect")
    from dss.services import model_registry
    provenance = model_registry.get_provenance(training_id, organization_id=tenant)
    library_versions = provenance["model_version"]["library_versions"]
    assert "numpy" in library_versions
    assert "pandas" in library_versions
    assert "scikit-learn" in library_versions
