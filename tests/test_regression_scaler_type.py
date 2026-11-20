"""R-2: RegressionTrainer.train_and_evaluate tạo preprocessor 2 LẦN — lần đầu
(BƯỚC 1) đúng truyền scaler_type, nhưng lần 2 (sau bước Feature Selection, LUÔN
chạy dù fs_method="none") gọi lại create_shared_preprocessor(...) KHÔNG kèm
scaler_type, nên preprocessor thật sự dùng để fit luôn là StandardScaler mặc
định — mọi lựa chọn scaler_type khác (MinMaxScaler, RobustScaler) trên UI
không có tác dụng gì với hồi quy.
"""

from __future__ import annotations

import warnings

import pytest
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import RegressionTrainer


@pytest.mark.parametrize(
    "scaler_type,expected_cls",
    [
        ("StandardScaler", StandardScaler),
        ("MinMaxScaler", MinMaxScaler),
        ("RobustScaler", RobustScaler),
    ],
)
def test_regression_pipeline_uses_selected_scaler_type(scaler_type, expected_cls):
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, pipelines, *_ = reg.train_and_evaluate(
        df,
        feats,
        "diem_ky_sau",
        ["Linear Regression"],
        cv_folds=3,
        save_model=False,
        scaler_type=scaler_type,
    )
    pipeline = pipelines["Linear Regression"]
    preprocessor = pipeline.named_steps["preprocessor"]
    numeric_pipeline = {name: trans for name, trans, _cols in preprocessor.transformers}["num"]
    actual_scaler = numeric_pipeline.named_steps["scaler"]
    assert isinstance(actual_scaler, expected_cls), (
        f"scaler_type={scaler_type!r} được chọn nhưng pipeline thật sự dùng "
        f"{type(actual_scaler).__name__} — tham số scaler_type không được "
        "truyền tới lần tạo preprocessor thứ 2 sau bước Feature Selection."
    )
