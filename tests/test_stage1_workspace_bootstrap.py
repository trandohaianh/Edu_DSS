"""Login hydrates approved artifacts without training or process-wide UI mutation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import streamlit as st

from dss.core import bootstrap_service
from dss.services import clustering_service


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(bootstrap_service, "_detect_default_training_config", lambda _df: {
        "target_col": "diem_ky_sau", "selected_features": ["diem_ky_nay"],
        "problem_type": "Hồi quy (Regression)",
    })
    st.session_state["current_dataset_id"] = "pilot"
    return SimpleNamespace(
        role="Sinh viên", df=pd.DataFrame({"diem_ky_nay": [5, 6, 7], "diem_ky_sau": [6, 7, 8]}),
        warehouse=SimpleNamespace(get_production_model=Mock(return_value=(None, None))),
        clf=SimpleNamespace(train_and_evaluate=Mock()),
        reg=SimpleNamespace(train_and_evaluate=Mock()),
    )


def initialize(context, callback=None):
    bootstrap_service.initialize_workspace(
        context.role, context.df, context.warehouse, context.clf, context.reg, callback,
    )


@pytest.mark.parametrize("role", ["Sinh viên", "Giảng viên / CVHT", "Admin"])
def test_login_never_computes_clusters_or_trains(context, monkeypatch, role):
    context.role = role
    spies = []
    for name in ("preprocess_features", "run_kmeans", "compute_cluster_quality_metrics", "silhouette_score"):
        spy = Mock(side_effect=AssertionError("Unexpected login computation"))
        monkeypatch.setattr(clustering_service, name, spy)
        spies.append(spy)
    progress = []
    initialize(context, lambda percent, stage: progress.append((percent, stage)))
    for spy in spies:
        spy.assert_not_called()
    context.clf.train_and_evaluate.assert_not_called()
    context.reg.train_and_evaluate.assert_not_called()
    assert "cluster_results_df" not in st.session_state
    assert progress[-1] == (100, "workspace_ready")


def test_artifact_hydration_never_monkeypatches_streamlit(context):
    pipeline = object()
    names = ("write", "info", "columns", "spinner", "dataframe")
    originals = {name: getattr(st, name) for name in names}

    def load(*_args):
        for name in names:
            assert getattr(st, name) is originals[name]
        return pipeline, {"model_name": "Approved", "metrics": {"mae": .4}, "feature_cols": ["diem_ky_nay"]}

    context.warehouse.get_production_model.side_effect = load
    initialize(context)
    assert st.session_state["hub_pipelines"] == {"Approved": pipeline}
    assert st.session_state["hub_type"] == "reg"
    for name in names:
        assert getattr(st, name) is originals[name]


def test_same_dataset_is_not_reloaded(context):
    initialize(context)
    initialize(context)
    context.warehouse.get_production_model.assert_called_once_with("pilot", "diem_ky_sau")


def test_unavailable_artifact_does_not_trigger_training(context):
    context.warehouse.get_production_model.side_effect = OSError("Unavailable")
    progress = []
    initialize(context, lambda percent, stage: progress.append((percent, stage)))
    context.clf.train_and_evaluate.assert_not_called()
    context.reg.train_and_evaluate.assert_not_called()
    assert progress[-1] == (100, "workspace_ready")


def test_empty_dataset_is_ready_without_artifact_access(context):
    context.df = None
    progress = []
    initialize(context, lambda percent, stage: progress.append((percent, stage)))
    context.warehouse.get_production_model.assert_not_called()
    assert progress[-1] == (100, "workspace_ready")


def test_large_silhouette_uses_deterministic_bounded_sample(monkeypatch):
    import numpy as np
    values = np.zeros((3000, 2))
    labels = np.arange(3000) % 2
    score = Mock(return_value=.4)
    monkeypatch.setattr(clustering_service, "silhouette_score", score)
    metrics = clustering_service.compute_cluster_quality_metrics(values, labels)
    assert metrics["silhouette"] == .4
    assert metrics["silhouette_sample_size"] == 2000
    assert score.call_args.kwargs["sample_size"] == 2000
    assert score.call_args.kwargs["random_state"] == 42
