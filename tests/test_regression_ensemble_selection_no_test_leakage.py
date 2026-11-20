"""R-3: RegressionTrainer chọn giữa Voting Ensemble và Stacking Ensemble bằng
cách so sánh voting_r2/stacking_r2 TÍNH TRÊN CHÍNH X_test/y_test — tức là dùng
tập test để ra QUYẾT ĐỊNH chọn mô hình, không còn là đánh giá độc lập/trung
thực nữa (data leakage kiểu "chọn theo tập test"). Phải so sánh bằng
cross_val_score trên tập TRAIN; tập test chỉ dùng để BÁO CÁO mô hình đã chọn."""

from __future__ import annotations

import inspect
import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import RegressionTrainer
from dss.core.training import regression as regression_module


def test_ensemble_selection_does_not_reference_test_set_in_source():
    """Nguồn hàm KHÔNG được so sánh voting_r2/stacking_r2 (tính từ X_test/y_test)
    để quyết định chọn Stacking hay Voting — phải dùng cross_val_score trên train."""
    source = inspect.getsource(RegressionTrainer.train_and_evaluate)
    assert "if stacking_r2 > voting_r2:" not in source, (
        "Vẫn còn so sánh voting_r2/stacking_r2 (tính trên X_test/y_test) để CHỌN "
        "ensemble — đây chính là dùng tập test để ra quyết định chọn mô hình."
    )
    assert "cross_val_score" in source


def test_ensemble_training_runs_end_to_end_with_selection_from_cv():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, pipelines, *_ = reg.train_and_evaluate(
        df,
        feats,
        "diem_ky_sau",
        ["Linear Regression", "Random Forest Regressor"],
        training_strategy="Kết hợp (Ensemble)",
        cv_folds=3,
        save_model=False,
    )
    ensemble_names = [k for k in results if str(k).startswith("Auto-Ensemble")]
    assert ensemble_names, f"Không có ensemble nào được tạo: {list(results)}"
    ensemble_name = ensemble_names[0]
    assert "R2 Score" in results[ensemble_name]
    assert ensemble_name in pipelines


def test_correlation_leakage_guard_uses_training_labels_only(monkeypatch):
    import numpy as np
    import pandas as pd

    # Exact target copy in train, unrelated in test. A full-data correlation
    # check can let test labels change whether this feature is removed.
    y = np.arange(60, dtype=float)
    candidate = y.copy()
    candidate[40:] = -candidate[40:]
    frame = pd.DataFrame(
        {
            "snapshot_leak": candidate,
            "independent_feature": np.random.default_rng(7).normal(size=len(y)),
            "next_score": y,
        }
    )

    def fixed_split(X, target, **kwargs):
        return X.iloc[:40], X.iloc[40:], target.iloc[:40], target.iloc[40:]

    # RegressionTrainer nằm ở dss.core.training.regression: patch nơi hàm được dùng.
    monkeypatch.setattr(regression_module, "train_test_split", fixed_split)
    results, pipelines, _, trained_features, *_ = RegressionTrainer().train_and_evaluate(
        frame,
        ["snapshot_leak", "independent_feature"],
        "next_score",
        ["Linear Regression"],
        cv_folds=2,
        save_model=False,
    )

    assert results and pipelines
    assert "snapshot_leak" not in trained_features
    assert "independent_feature" in trained_features
