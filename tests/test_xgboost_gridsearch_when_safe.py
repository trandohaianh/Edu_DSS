"""P-1: XGBoost Classifier bỏ qua GridSearchCV VÔ ĐIỀU KIỆN — kể cả khi dữ
liệu đủ lớn/cân bằng để tối ưu an toàn như LightGBM/Random Forest. Chỉ nên bỏ
qua khi THẬT SỰ có nguy cơ thiếu lớp trong fold (lớp nhỏ nhất < số fold yêu
cầu); ngược lại phải tối ưu bằng GridSearchCV với lưới nhỏ tương đương LightGBM."""
from __future__ import annotations

import inspect
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer, XGBOOST_AVAILABLE
import pytest


def test_source_no_longer_skips_gridsearch_unconditionally():
    source = inspect.getsource(ClassificationTrainer.train_and_evaluate)
    assert "elif name == 'XGBoost Classifier' and XGBOOST_AVAILABLE:\n                    # NOTE:" not in source
    assert "min_class_samples < cv_folds" in source


@pytest.mark.skipif(not XGBOOST_AVAILABLE, reason="xgboost chưa cài đặt")
def test_xgboost_still_skips_gridsearch_on_rare_class_sample_data():
    """Đối chứng: trên dữ liệu mẫu (lớp "Yếu" chỉ 2 mẫu, cv_folds mặc định=5),
    hành vi AN TOÀN (bỏ qua GridSearchCV) phải được giữ nguyên."""
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(
        df, feats, "xep_loai", ["XGBoost Classifier"], cv_folds=5, save_model=False
    )
    assert "XGBoost Classifier" in results
    assert results["XGBoost Classifier"].get("cv_mean") is None


@pytest.mark.skipif(not XGBOOST_AVAILABLE, reason="xgboost chưa cài đặt")
def test_xgboost_uses_gridsearch_when_enough_minority_samples():
    """Trên dữ liệu đủ mẫu (lớp nhỏ nhất >= số fold), XGBoost PHẢI được tối ưu
    bằng GridSearchCV (cv_mean có giá trị) thay vì luôn train trực tiếp."""
    rng = np.random.RandomState(42)
    n_majority, n_minority = 340, 60
    n = n_majority + n_minority
    df = pd.DataFrame({
        "f1": rng.normal(0, 1, n),
        "f2": rng.normal(0, 1, n),
        "f3": rng.normal(0, 1, n),
        "target": ["A"] * n_majority + ["B"] * n_minority,
    }).sample(frac=1.0, random_state=42).reset_index(drop=True)

    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(
        df, ["f1", "f2", "f3"], "target", ["XGBoost Classifier"], cv_folds=3, save_model=False
    )
    assert "XGBoost Classifier" in results
    assert results["XGBoost Classifier"].get("cv_mean") is not None, (
        "XGBoost vẫn bỏ qua GridSearchCV dù lớp thiểu số (60 mẫu) >> số fold (3)."
    )
