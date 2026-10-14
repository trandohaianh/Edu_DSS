"""Lưới dò tham số theo cỡ dữ liệu (dss/core/tuning.py):
- dữ liệu nhỏ: lưới ĐẦY ĐỦ (RF phân loại 24, RF hồi quy 12) — ở đây lưới quyết
  định độ chính xác và chạy vẫn nhanh;
- dữ liệu lớn (>= tuning.LARGE_DATA_ROWS): lưới GỌN (8 / 4) + tối đa 3 fold —
  đo trên 20.000 SV, chọn cùng tham số tốt nhất với lưới đầy đủ."""
from __future__ import annotations

import ast
import inspect
import itertools

import pytest

from dss.core import trainers, tuning
from dss.core.trainers import ClassificationTrainer, RegressionTrainer
from dss.config import XGBOOST_AVAILABLE, LIGHTGBM_AVAILABLE


def _combination_count(grid: dict) -> int:
    if not grid:
        return 0
    return len(list(itertools.product(*grid.values())))


def test_random_forest_regressor_full_and_compact_grids():
    trainer = RegressionTrainer()
    assert _combination_count(trainer.param_grids["Random Forest Regressor"]) == 12
    assert _combination_count(trainer._compact_param_grids["Random Forest Regressor"]) == 4


def test_compact_grid_is_subset_of_full_grid():
    trainer = RegressionTrainer()
    full, compact = trainer.param_grids["Random Forest Regressor"], trainer._compact_param_grids["Random Forest Regressor"]
    assert all(set(v) <= set(full[k]) for k, v in compact.items())
    assert all(set(v) <= set(trainers.RF_CLASSIFIER_GRID_FULL[k]) for k, v in trainers.RF_CLASSIFIER_GRID_COMPACT.items())


def test_linear_regression_has_no_grid_search():
    trainer = RegressionTrainer()
    assert trainer.param_grids["Linear Regression"] == {}


def test_regression_trainer_has_single_source_of_truth_for_param_grids():
    """Lưới hồi quy chỉ định nghĩa ở __init__ (3 lưới đầy đủ + 1 lưới gọn RF)."""
    source = inspect.getsource(RegressionTrainer)
    assert source.count("'model__n_estimators'") == 4


@pytest.mark.parametrize("model_name,expected_combinations,requires", [
    ("Random Forest Regressor", 12, None),
    ("XGBoost Regressor", 4, "xgboost"),
    ("LightGBM Regressor", 4, "lightgbm"),
])
def test_exact_combination_counts_for_all_boosting_models(model_name, expected_combinations, requires):
    if requires == "xgboost" and not XGBOOST_AVAILABLE:
        pytest.skip("xgboost không cài trong môi trường này")
    if requires == "lightgbm" and not LIGHTGBM_AVAILABLE:
        pytest.skip("lightgbm không cài trong môi trường này")
    trainer = RegressionTrainer()
    grid = trainer.param_grids.get(model_name)
    assert grid is not None, f"{model_name} phải có param_grid (đã cài đặt package tương ứng)"
    assert _combination_count(grid) == expected_combinations


def test_large_data_fit_count_is_bounded():
    trainer = RegressionTrainer()
    n = tuning.LARGE_DATA_ROWS
    grid = tuning.select_grid(trainer.param_grids["Random Forest Regressor"],
                              trainer._compact_param_grids["Random Forest Regressor"], n)
    assert _combination_count(grid) * tuning.effective_cv_folds(n, 5) == 4 * 3


def test_classification_grids():
    assert _combination_count(trainers.RF_CLASSIFIER_GRID_FULL) == 24
    assert _combination_count(trainers.RF_CLASSIFIER_GRID_COMPACT) == 8
    tree = ast.parse(inspect.getsource(ClassificationTrainer))
    literal_grids = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "param_grid" for t in node.targets):
            try:
                literal_grids.append(ast.literal_eval(node.value))
            except (ValueError, TypeError):
                continue
    # XGBoost, LightGBM (4 tổ hợp) và Logistic Regression (3).
    assert sorted(_combination_count(g) for g in literal_grids) == [3, 4, 4]
