"""R-4: khi bật st.session_state["allow_feature_engineering"]=True, trainer
sinh cột _fe_* (add_engineered_features) NGOÀI Pipeline sklearn — cột này lọt
vào feature_cols đã lưu, nhưng lúc dự đoán (form nhập tay/Production) không có
bước nào tự tính lại từ input thô, nên pipeline.predict() luôn lỗi "columns
are missing". Không có UI nào bật cờ này — khóa cứng tại nguồn để không ai vô
tình bật lại cho tới khi feature engineering được đưa vào Pipeline đúng chuẩn."""

from __future__ import annotations

import warnings

import pandas as pd
import pytest
import streamlit as st

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import RegressionTrainer


def test_feature_engineering_flag_never_adds_fe_columns_even_when_enabled():
    st.session_state["allow_feature_engineering"] = True
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, pipelines, eval_frames, trained_feats, *_ = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Linear Regression"], cv_folds=3, save_model=False
    )
    fe_cols = [c for c in trained_feats if c.startswith("_fe_")]
    assert not fe_cols, f"Feature engineering vẫn được bật dù đã yêu cầu khóa cứng: {fe_cols}"


def test_prediction_with_raw_features_only_succeeds_even_with_flag_enabled():
    st.session_state["allow_feature_engineering"] = True
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, pipelines, eval_frames, trained_feats, *_ = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Linear Regression"], cv_folds=3, save_model=False
    )
    pipeline = pipelines["Linear Regression"]
    raw_row = {c: float(df[c].mean()) for c in trained_feats}
    input_df = pd.DataFrame([raw_row])
    try:
        pred = pipeline.predict(input_df)
    except Exception as e:
        pytest.fail(f"Dự đoán bằng feature thô thất bại (R-4 tái hiện): {type(e).__name__}: {e}")
    assert pred is not None
