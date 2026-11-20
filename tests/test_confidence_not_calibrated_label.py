"""P-7: predict_proba() là xác suất mô hình tự ước lượng, CHƯA HIỆU CHUẨN (chưa
qua CalibratedClassifierCV/Brier score) — trước đây gọi thẳng là "độ tin cậy"
(≥0.8 "cao", ≥0.6 "trung bình"), khiến người dùng hiểu nhầm đây là xác suất đã
kiểm định."""

from __future__ import annotations

import inspect

from dss.tabs import ml_hub


def test_personal_prediction_does_not_call_predict_proba_confidence_without_caveat():
    source = inspect.getsource(ml_hub)
    assert "độ tin cậy khoảng" not in source, (
        "ml_hub.py vẫn gọi predict_proba() là \"độ tin cậy\" mà không ghi rõ đây là xác suất mô hình CHƯA HIỆU CHUẨN."
    )
    assert "xác suất theo mô hình" in source
    assert "CHƯA HIỆU CHUẨN" in source or "chưa hiệu chuẩn" in source
