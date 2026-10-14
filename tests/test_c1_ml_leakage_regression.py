"""C1.1 — target leakage cannot re-enter CURRENT training.

The historical thesis artifact (R² 0.992) was a Linear Regression on the
synthetic `sample_data_v1` whose FEATURES included `xep_loai` — a grade band
derived from the target. These tests call the real trainers with the leaky
columns deliberately offered as features and assert they never reach the
fitted model, for the canonical target and its legacy alias.
"""
from __future__ import annotations

import warnings

import pytest

from dss.core.data_helpers import generate_data
from dss.core.target_utils import get_leaky_target_columns
from dss.core.trainers import ClassificationTrainer, RegressionTrainer

warnings.filterwarnings("ignore")

LEAKY = {"xep_loai", "grade", "diem_ky_sau", "final_score"}


@pytest.fixture(scope="module")
def df():
    data = generate_data(n_students=300)
    data["final_score"] = data["diem_ky_sau"]  # legacy alias present, as in the thesis dataset
    return data


@pytest.mark.parametrize("target", ["diem_ky_sau", "final_score"])
def test_regression_never_trains_on_target_derived_columns(df, target):
    offered = [c for c in df.columns if c != "student_id" and c != target]
    assert "xep_loai" in offered  # the exact historical mistake is offered on purpose
    _, pipelines, _, trained_feats, *_ = RegressionTrainer().train_and_evaluate(
        df, offered, target, ["Linear Regression"], cv_folds=3, save_model=False)
    assert not (set(trained_feats) & LEAKY), f"leaky features reached the model: {set(trained_feats) & LEAKY}"
    fitted = pipelines["Linear Regression"]
    n_in = getattr(fitted.named_steps.get("preprocessor", fitted), "n_features_in_", None)
    if n_in is not None:
        assert n_in == len(trained_feats)


def test_classification_on_grade_band_never_uses_the_score_it_derives_from(df):
    offered = [c for c in df.columns if c not in ("student_id", "xep_loai")]
    assert "diem_ky_sau" in offered
    _, _, _, trained_feats, *_ = ClassificationTrainer().train_and_evaluate(
        df, offered, "xep_loai", ["Logistic Regression (Softmax)"], cv_folds=3, save_model=False)
    assert not (set(trained_feats) & LEAKY)


def test_leakage_matrix_covers_alias_and_derived_band():
    for target in ("diem_ky_sau", "final_score", "xep_loai", "grade"):
        assert {"xep_loai", "diem_ky_sau"} <= set(get_leaky_target_columns(target)) | {target}
