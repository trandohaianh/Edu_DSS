"""Tăng tốc dò tham số không đổi độ chính xác (dss/core/tuning.py):
lưới/số fold theo cỡ dữ liệu + ghi nhớ tham số tốt nhất theo dấu vân tay dữ liệu."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dss.core import tuning

GRID = {"model__n_estimators": [10, 20], "model__max_depth": [3, None]}


@pytest.fixture(autouse=True)
def _fresh_cache():
    tuning.clear_cache()
    yield
    tuning.clear_cache()


def _data(n=300, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 4)), columns=list("abcd"))
    y = X["a"] * 2 + X["b"] + rng.normal(scale=0.1, size=n)
    return X, y


def _pipe():
    return Pipeline([("sc", StandardScaler()), ("model", RandomForestRegressor(random_state=0))])


def test_cv_folds_and_grid_depend_on_data_size():
    big = tuning.LARGE_DATA_ROWS
    assert tuning.effective_cv_folds(big - 1, 5) == 5
    assert tuning.effective_cv_folds(big, 5) == tuning.LARGE_DATA_CV_FOLDS
    assert tuning.effective_cv_folds(big, 2) == 2  # không bao giờ TĂNG số fold
    assert tuning.select_grid({"full": 1}, {"compact": 1}, big - 1) == {"full": 1}
    assert tuning.select_grid({"full": 1}, {"compact": 1}, big) == {"compact": 1}


def test_second_fit_on_same_data_skips_grid_search(monkeypatch):
    X, y = _data()
    cv = KFold(3, shuffle=True, random_state=0)
    p1, mean1, std1, best1 = tuning.tuned_fit("RF", _pipe(), GRID, X, y, cv, "neg_mean_absolute_error", sign=-1)

    def _fail(*a, **k):
        raise AssertionError("GridSearchCV không được chạy lại với cùng dữ liệu/cấu hình")

    monkeypatch.setattr(tuning, "GridSearchCV", _fail)
    p2, mean2, std2, best2 = tuning.tuned_fit("RF", _pipe(), GRID, X, y, cv, "neg_mean_absolute_error", sign=-1)
    assert best1 == best2 and (mean1, std1) == (mean2, std2) and mean1 > 0
    np.testing.assert_allclose(p1.predict(X), p2.predict(X))


def test_changed_data_triggers_new_search():
    X, y = _data()
    cv = KFold(3, shuffle=True, random_state=0)
    tuning.tuned_fit("RF", _pipe(), GRID, X, y, cv, "neg_mean_absolute_error")
    X2 = X.copy()
    X2.iloc[0, 0] += 1.0  # đổi đúng 1 ô
    tuning.tuned_fit("RF", _pipe(), GRID, X2, y, cv, "neg_mean_absolute_error")
    assert len(tuning._BEST_PARAMS_CACHE) == 2


def test_shared_estimator_is_not_mutated():
    model = RandomForestRegressor(random_state=0)
    pipe = Pipeline([("sc", StandardScaler()), ("model", model)])
    X, y = _data()
    tuning.tuned_fit("RF", pipe, GRID, X, y, KFold(3), "neg_mean_absolute_error")
    assert model.n_jobs is None and model.n_estimators == 100
