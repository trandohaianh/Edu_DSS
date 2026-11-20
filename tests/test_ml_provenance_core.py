"""Pure-logic tests for Workstream C ML provenance/drift (§18) — no database
required, always runs. DB-integration/RLS tests are in
tests/test_workstream_c_ml_provenance.py (gated like every other Postgres
acceptance suite in this repo)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dss.services import ml_provenance as mp

# ---------------------------------------------------------------------------
# Feature-schema fingerprint (§5)
# ---------------------------------------------------------------------------


def _base_schema_args():
    return dict(
        feature_names=["gpa", "attendance", "major"],
        feature_dtypes={"gpa": "float64", "attendance": "float64", "major": "object"},
        feature_roles={"gpa": "numeric", "attendance": "numeric", "major": "categorical"},
        target_definition="at_risk",
        model_task_type="classification",
    )


def test_feature_schema_fingerprint_is_deterministic():
    a = mp.compute_feature_schema_fingerprint(**_base_schema_args())
    b = mp.compute_feature_schema_fingerprint(**_base_schema_args())
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_feature_schema_fingerprint_changes_with_feature_order():
    args = _base_schema_args()
    reordered = dict(args, feature_names=["major", "gpa", "attendance"])
    assert mp.compute_feature_schema_fingerprint(**args) != mp.compute_feature_schema_fingerprint(**reordered)


def test_feature_schema_fingerprint_changes_with_dtype():
    args = _base_schema_args()
    changed = dict(args, feature_dtypes={**args["feature_dtypes"], "gpa": "int64"})
    assert mp.compute_feature_schema_fingerprint(**args) != mp.compute_feature_schema_fingerprint(**changed)


def test_feature_schema_fingerprint_changes_with_role():
    args = _base_schema_args()
    changed = dict(args, feature_roles={**args["feature_roles"], "attendance": "categorical"})
    assert mp.compute_feature_schema_fingerprint(**args) != mp.compute_feature_schema_fingerprint(**changed)


def test_feature_schema_fingerprint_changes_with_target():
    args = _base_schema_args()
    changed = dict(args, target_definition="dropout_risk")
    assert mp.compute_feature_schema_fingerprint(**args) != mp.compute_feature_schema_fingerprint(**changed)


def test_feature_schema_fingerprint_changes_with_task_type():
    args = _base_schema_args()
    changed = dict(args, model_task_type="regression")
    assert mp.compute_feature_schema_fingerprint(**args) != mp.compute_feature_schema_fingerprint(**changed)


def test_feature_schema_fingerprint_changes_with_preprocessing():
    args = _base_schema_args()
    a = mp.compute_feature_schema_fingerprint(**args, preprocessing_expectations={"numeric": "standard_scale"})
    b = mp.compute_feature_schema_fingerprint(**args, preprocessing_expectations={"numeric": "minmax_scale"})
    assert a != b


# ---------------------------------------------------------------------------
# Dataset fingerprint (§4)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_df():
    rng = np.random.RandomState(42)
    return pd.DataFrame(
        {
            "gpa": rng.uniform(1.5, 4.0, 300),
            "attendance": rng.uniform(0.5, 1.0, 300),
            "major": rng.choice(["CS", "Math", "Physics"], 300),
        }
    )


def test_dataset_fingerprint_is_deterministic(sample_df):
    a = mp.compute_dataset_fingerprint(sample_df)
    b = mp.compute_dataset_fingerprint(sample_df.copy())
    assert a["dataset_fingerprint"] == b["dataset_fingerprint"]
    assert a["schema_fingerprint"] == b["schema_fingerprint"]
    assert a["row_count"] == 300
    assert a["column_count"] == 3


def test_dataset_fingerprint_changes_when_content_changes(sample_df):
    baseline = mp.compute_dataset_fingerprint(sample_df)
    shifted = sample_df.copy()
    shifted["gpa"] = shifted["gpa"] + 1.0
    changed = mp.compute_dataset_fingerprint(shifted)
    assert baseline["dataset_fingerprint"] != changed["dataset_fingerprint"]
    # Schema (columns/dtypes) is unchanged even though content changed.
    assert baseline["schema_fingerprint"] == changed["schema_fingerprint"]


def test_dataset_fingerprint_schema_changes_when_columns_change(sample_df):
    baseline = mp.compute_dataset_fingerprint(sample_df)
    dropped = sample_df.drop(columns=["major"])
    changed = mp.compute_dataset_fingerprint(dropped)
    assert baseline["schema_fingerprint"] != changed["schema_fingerprint"]


def test_dataset_fingerprint_does_not_store_raw_rows(sample_df):
    result = mp.compute_dataset_fingerprint(sample_df)
    serialized = str(result)
    # Reproducibility evidence only — no raw row-level values should appear
    # (numeric_summary/null_stats are aggregates, not individual cell values).
    assert "numeric_summary" in result and "null_stats" in result
    assert len(serialized) < 5000  # order of magnitude smaller than the 300-row dataset


# ---------------------------------------------------------------------------
# Data drift (§6)
# ---------------------------------------------------------------------------


def test_identical_distribution_no_meaningful_drift(sample_df):
    result = mp.evaluate_data_drift(sample_df, sample_df.copy())
    assert result["overall_status"] == mp.STATUS_NO_DRIFT
    assert result["drifted_features"] == []


def test_intentionally_shifted_numeric_distribution_is_detected(sample_df):
    shifted = sample_df.copy()
    shifted["gpa"] = shifted["gpa"] + 5.0  # large, unmistakable shift
    result = mp.evaluate_data_drift(sample_df, shifted)
    assert result["overall_status"] == mp.STATUS_DRIFT_DETECTED
    assert "gpa" in result["drifted_features"]
    assert result["per_feature"]["gpa"]["drift_metric"] > mp.DEFAULT_PSI_DRIFT_THRESHOLD


def test_categorical_shift_is_detected(sample_df):
    shifted = sample_df.copy()
    shifted["major"] = "CS"  # collapse to a single category
    result = mp.evaluate_data_drift(sample_df, shifted)
    assert result["per_feature"]["major"]["status"] == mp.STATUS_DRIFT_DETECTED
    assert result["per_feature"]["major"]["feature_type"] == "categorical"


def test_insufficient_data_when_sample_too_small(sample_df):
    tiny_current = sample_df.head(5)
    result = mp.evaluate_data_drift(sample_df, tiny_current, min_samples=20)
    assert result["per_feature"]["gpa"]["status"] == mp.STATUS_INSUFFICIENT_DATA
    assert result["overall_status"] == mp.STATUS_INSUFFICIENT_DATA


def test_thresholds_are_configurable(sample_df):
    # A genuinely small shift (PSI ~0.02 on this distribution, well under the
    # default 0.10 warning band) — the same computed PSI value must cross
    # into WARNING/DRIFT_DETECTED once given a stricter (lower) threshold,
    # proving the threshold is actually consulted, not hardcoded.
    shifted = sample_df.copy()
    shifted["gpa"] = shifted["gpa"] + 0.05

    default = mp.evaluate_data_drift(sample_df, shifted)
    assert default["per_feature"]["gpa"]["status"] == mp.STATUS_NO_DRIFT

    strict = mp.evaluate_data_drift(sample_df, shifted, warning_threshold=0.001, drift_threshold=0.01)
    assert strict["per_feature"]["gpa"]["status"] in (mp.STATUS_WARNING, mp.STATUS_DRIFT_DETECTED)
    assert (
        strict["per_feature"]["gpa"]["drift_metric"] == default["per_feature"]["gpa"]["drift_metric"]
    )  # same metric, different threshold


def test_drift_evaluation_is_deterministic_on_repeat(sample_df):
    shifted = sample_df.copy()
    shifted["gpa"] = shifted["gpa"] + 1.0
    first = mp.evaluate_data_drift(sample_df, shifted)
    second = mp.evaluate_data_drift(sample_df, shifted)
    assert first["per_feature"]["gpa"]["drift_metric"] == second["per_feature"]["gpa"]["drift_metric"]
    assert first["overall_status"] == second["overall_status"]


# ---------------------------------------------------------------------------
# Performance drift (§7) — real labels only, never fabricated
# ---------------------------------------------------------------------------


def test_classification_degradation_detected_with_real_labels():
    rng = np.random.RandomState(0)
    y_true = rng.randint(0, 2, 200)
    y_pred_baseline = y_true.copy()  # perfect baseline
    y_pred_current = 1 - y_true  # completely inverted -> maximal degradation

    result = mp.evaluate_performance_drift("classification", y_true, y_pred_baseline, y_true, y_pred_current)
    assert result["overall_status"] == mp.STATUS_DRIFT_DETECTED
    assert result["metrics"]["accuracy"]["current"] < result["metrics"]["accuracy"]["baseline"]


def test_classification_no_degradation_when_performance_holds():
    rng = np.random.RandomState(0)
    y_true = rng.randint(0, 2, 200)
    result = mp.evaluate_performance_drift("classification", y_true, y_true, y_true, y_true)
    assert result["overall_status"] == mp.STATUS_NO_DRIFT


def test_regression_degradation_detected_with_real_labels():
    rng = np.random.RandomState(0)
    y_true = rng.uniform(0, 10, 200)
    y_pred_baseline = y_true + rng.normal(0, 0.1, 200)  # small baseline error
    y_pred_current = y_true + rng.normal(0, 5.0, 200)  # much larger current error

    result = mp.evaluate_performance_drift("regression", y_true, y_pred_baseline, y_true, y_pred_current)
    assert result["overall_status"] == mp.STATUS_DRIFT_DETECTED
    assert result["metrics"]["rmse"]["current"] > result["metrics"]["rmse"]["baseline"]


def test_missing_ground_truth_returns_not_evaluable_never_fabricated():
    result = mp.evaluate_performance_drift("classification", None, None, [1, 0, 1], [1, 0, 1])
    assert result["overall_status"] == mp.STATUS_NOT_EVALUABLE
    assert result["metrics"] == {}

    result2 = mp.evaluate_performance_drift("classification", [1, 0, 1], [1, 0, 1], None, None)
    assert result2["overall_status"] == mp.STATUS_NOT_EVALUABLE


def test_performance_drift_insufficient_data():
    result = mp.evaluate_performance_drift("classification", [1, 0], [1, 0], [1, 0], [0, 1], min_samples=20)
    assert result["overall_status"] == mp.STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Retraining decision boundary (§10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data_status,perf_status,expected",
    [
        (mp.STATUS_NO_DRIFT, mp.STATUS_NOT_EVALUABLE, mp.ACTION_NO_ACTION),
        (mp.STATUS_WARNING, mp.STATUS_NOT_EVALUABLE, mp.ACTION_REVIEW_REQUIRED),
        (mp.STATUS_DRIFT_DETECTED, mp.STATUS_NOT_EVALUABLE, mp.ACTION_REVIEW_REQUIRED),
        (mp.STATUS_NO_DRIFT, mp.STATUS_WARNING, mp.ACTION_REVIEW_REQUIRED),
        (mp.STATUS_NO_DRIFT, mp.STATUS_DRIFT_DETECTED, mp.ACTION_RETRAIN_RECOMMENDED),
        (mp.STATUS_DRIFT_DETECTED, mp.STATUS_DRIFT_DETECTED, mp.ACTION_RETRAIN_RECOMMENDED),
    ],
)
def test_recommend_action_boundary(data_status, perf_status, expected):
    assert mp.recommend_action(data_status, perf_status) == expected


def test_recommend_action_never_returns_an_automatic_promotion_action():
    # No matter what combination, the only possible values are advisory —
    # none of them is (or implies) "promote to production automatically".
    possible = {mp.ACTION_NO_ACTION, mp.ACTION_REVIEW_REQUIRED, mp.ACTION_RETRAIN_RECOMMENDED}
    for data_status in (mp.STATUS_NO_DRIFT, mp.STATUS_WARNING, mp.STATUS_DRIFT_DETECTED, mp.STATUS_INSUFFICIENT_DATA):
        for perf_status in (mp.STATUS_NO_DRIFT, mp.STATUS_WARNING, mp.STATUS_DRIFT_DETECTED, mp.STATUS_NOT_EVALUABLE):
            assert mp.recommend_action(data_status, perf_status) in possible
