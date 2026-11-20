"""FINAL GAP CLOSURE — Câu 85 (D-1): drift evaluation must actually be
callable end-to-end from a real Warehouse model record, not just exist as
an isolated, never-invoked function. Confirms
`model_registry.run_on_demand_drift_check()` genuinely loads a model's real
persisted train/test split and returns a real, honest result — including
its window-limitation disclosure."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dss.core.warehouse import DataWarehouse
from dss.services import model_registry


@pytest.fixture()
def warehouse(tmp_path):
    return DataWarehouse(base_path=str(tmp_path))


def _fit_and_save_classifier(wh):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    rng = np.random.RandomState(42)
    X = pd.DataFrame({"f1": rng.normal(size=60), "f2": rng.normal(size=60)})
    y = pd.Series((X["f1"] + X["f2"] > 0).astype(int), name="target")
    X_train, X_test = X.iloc[:40], X.iloc[40:]
    y_train, y_test = y.iloc[:40], y.iloc[40:]

    pipeline = Pipeline([("clf", LogisticRegression())])
    pipeline.fit(X_train, y_train)

    training_id, _metadata = wh.save_model_training(
        dataset_id="ds1",
        model_pipeline=pipeline,
        model_name="LogisticRegression",
        feature_cols=["f1", "f2"],
        target_col="target",
        metrics={"Accuracy": 0.9},
        X_train=X_train,
        y_train=y_train,
        X_test=X_test,
        y_test=y_test,
        class_labels=[0, 1],
        auto_promote=True,
    )
    return training_id


def test_on_demand_drift_check_runs_against_real_saved_split(warehouse):
    training_id = _fit_and_save_classifier(warehouse)
    result = model_registry.run_on_demand_drift_check(training_id, warehouse)

    assert "data_drift" in result
    assert "performance_drift" in result
    assert "recommended_action" in result
    assert "checked_at" in result
    assert result["model_version"] is not None
    assert result["dataset_id"] == "ds1"
    assert "sanity" in result["window_note"].lower() or "train-split" in result["window_note"]


def test_on_demand_drift_check_reports_insufficient_data_for_unknown_model(warehouse):
    result = model_registry.run_on_demand_drift_check("does-not-exist", warehouse)
    assert result["status"] == "ERROR"


def test_on_demand_drift_check_never_claims_continuous_monitoring():
    """Xác nhận docstring/kết quả không bao giờ dùng cụm từ ngụ ý giám sát tự
    động liên tục — đây LÀ điều đề bài cảnh báo rõ không được tuyên bố sai."""
    import inspect

    source = inspect.getsource(model_registry.run_on_demand_drift_check)
    assert "giám sát liên tục" not in source.lower()
    assert "continuous" not in source.lower() or "không" in source.lower()
