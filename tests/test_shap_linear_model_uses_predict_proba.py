"""X-1: compute_shap_local_explanation/compute_shap_summary dùng KernelExplainer
với model.predict() cho MỌI mô hình không phải cây (kể cả mô hình tuyến tính,
vd. Logistic Regression) — với bài toán phân loại, .predict() trả về NHÃN RỜI
RẠC (mã số lớp), không phải xác suất, nên SHAP giải thích sai đối tượng: mức
đóng góp vào MÃ SỐ NHÃN (không có ý nghĩa định lượng liên tục), không phải mức
đóng góp vào XÁC SUẤT dự đoán. Phải dùng predict_proba khi model hỗ trợ."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dss.services.model_service import compute_shap_local_explanation, compute_shap_summary


def _make_linear_pipeline():
    rng = np.random.RandomState(42)
    n = 80
    X = pd.DataFrame(
        {
            "diem_giua_ky": rng.uniform(0, 10, n),
            "diem_du_an": rng.uniform(0, 10, n),
        }
    )
    y = (X["diem_giua_ky"] + X["diem_du_an"] > 10).astype(int)

    class _TrackingLogisticRegression(LogisticRegression):
        predict_proba_call_count = 0
        predict_call_count = 0

        def predict_proba(self, X):
            type(self).predict_proba_call_count += 1
            return super().predict_proba(X)

        def predict(self, X):
            type(self).predict_call_count += 1
            return super().predict(X)

    preprocessor = ColumnTransformer([("num", StandardScaler(), list(X.columns))])
    model = _TrackingLogisticRegression(random_state=42)
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", model)])
    pipeline.fit(X, y)
    return pipeline, X, _TrackingLogisticRegression


def test_local_shap_explanation_calls_predict_proba_for_linear_classifier():
    pipeline, X, tracker_cls = _make_linear_pipeline()
    tracker_cls.predict_proba_call_count = 0
    shap_val, err = compute_shap_local_explanation(
        pipeline, X.iloc[[0]], X.iloc[:15], list(X.columns), problem_type="classification"
    )
    assert err is None
    assert shap_val is not None
    assert tracker_cls.predict_proba_call_count > 0, (
        "SHAP KernelExplainer cho mô hình tuyến tính không gọi predict_proba() — "
        "vẫn dùng predict() (nhãn rời rạc) làm hàm mục tiêu."
    )


def test_shap_summary_calls_predict_proba_for_linear_classifier():
    pipeline, X, tracker_cls = _make_linear_pipeline()
    tracker_cls.predict_proba_call_count = 0
    shap_summary, err = compute_shap_summary(
        pipeline, X.iloc[:15], list(X.columns), problem_type="classification", class_idx=None
    )
    assert err is None
    assert shap_summary is not None
    assert tracker_cls.predict_proba_call_count > 0
