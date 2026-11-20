"""K-3 / K-4: "Điểm dự đoán" trong Tư vấn AI phải đến từ mô hình Production (khi
có), KHÔNG BAO GIỜ đọc thẳng cột target thật (diem_ky_sau) rồi gọi là "dự đoán";
và "tiến bộ" phải so sánh CÙNG THANG điểm với kỳ trước, không lệch thang 10/4.

Dùng warehouse THẬT (tmp_path, không mock) — đúng phong cách test_model_registry.py.
"""

from __future__ import annotations

import inspect
import warnings

import pandas as pd
import pytest

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import RegressionTrainer
from dss.services.model_service import compute_progress_note, predict_for_student
from dss.tabs import ai_advisor


# ---------------------------------------------------------------------------
# K-3: predict_for_student
# ---------------------------------------------------------------------------
def test_predict_for_student_uses_model_when_production_available(warehouse):
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, pipelines, *_ = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Linear Regression"], cv_folds=3, save_model=False
    )
    pipeline = pipelines["Linear Regression"]
    training_id, meta = warehouse.save_model_training(
        dataset_id="ds1",
        model_pipeline=pipeline,
        model_name="Linear Regression",
        feature_cols=feats,
        target_col="diem_ky_sau",
        metrics=results["Linear Regression"],
        is_best=True,
        auto_promote=False,
    )
    ok, _msg = warehouse.set_production_model(training_id, promoted_by="admin_test")
    assert ok is True

    student_row = df.iloc[0]
    result = predict_for_student(warehouse, "ds1", "diem_ky_sau", student_row)

    assert result["source"] == "model"
    assert result["model_name"] == "Linear Regression"
    expected = float(pipeline.predict(pd.DataFrame([student_row[feats]]))[0])
    assert result["value"] == pytest.approx(expected)
    # Giá trị dự đoán KHÔNG được trùng khớp tuyệt đối với đáp án thật trong dữ liệu
    # mô phỏng (nếu trùng do trùng hợp float thì test flaky — nhưng với nhiễu N(0,0.08)
    # trong generate_data(), xác suất trùng tuyệt đối là ~0).
    assert result["value"] != float(student_row["diem_ky_sau"])


def test_predict_for_student_without_production_uses_observed_not_target(warehouse):
    """Chưa có Production -> trả điểm HIỆN TẠI (quan sát được), KHÔNG BAO GIỜ
    dùng cột target thật (diem_ky_sau) làm căn cứ, kể cả khi nó có trong dữ liệu."""
    df = generate_data()
    student_row = df.iloc[0]
    result = predict_for_student(warehouse, "ds_empty", "diem_ky_sau", student_row)

    assert result["source"] == "observed"
    assert result["model_name"] is None
    assert result["value"] == pytest.approx(float(student_row["diem_ky_nay"]))
    assert result["value"] != float(student_row["diem_ky_sau"])


# ---------------------------------------------------------------------------
# K-4: compute_progress_note — so sánh cùng thang điểm
# ---------------------------------------------------------------------------
def test_compute_progress_note_detects_improvement_same_scale():
    row = pd.Series({"diem_ky_nay": 6.0})
    delta, note = compute_progress_note(7.0, row)
    assert delta == pytest.approx(1.0)
    assert "cải thiện" in note


def test_compute_progress_note_detects_decline_same_scale():
    row = pd.Series({"diem_ky_nay": 8.0})
    delta, note = compute_progress_note(6.0, row)
    assert delta == pytest.approx(-2.0)
    assert "giảm" in note


def test_compute_progress_note_detects_stable_same_scale():
    row = pd.Series({"diem_ky_nay": 7.0})
    delta, note = compute_progress_note(7.05, row)
    assert "ổn định" in note


def test_compute_progress_note_converts_gpa_previous_scale_4_to_10():
    # gpa_previous=3.10 (thang 4) tương đương 7.75 thang 10 — dự đoán 7.06 là
    # GIẢM nhẹ, không phải "+3.96 đang cải thiện" như công thức lệch thang cũ.
    row = pd.Series({"gpa_previous": 3.10})
    delta, note = compute_progress_note(7.06, row)
    assert delta == pytest.approx(7.06 - 3.10 * 2.5)
    assert delta < 0
    assert "giảm" in note


def test_k4_sample_data_improvement_rate_not_near_100_percent():
    """Tái hiện đúng kịch bản mô tả trong lỗi K-4: nếu so sánh predicted_gpa_llm
    (thang 10) với gpa_previous (thang 4) không quy đổi, gần 100% SV mẫu hiện ra
    "đang cải thiện". Sau khi so cùng thang (diem_ky_sau dự đoán vs diem_ky_nay),
    tỷ lệ phải hợp lý (không gần 100%)."""
    df = generate_data()
    old_buggy_delta = df["diem_ky_sau"] - df["gpa_previous"]
    old_improving_rate = float((old_buggy_delta > 0.15).mean())
    assert old_improving_rate > 0.95, "Bằng chứng lỗi lệch thang không còn tái hiện được trên dữ liệu mẫu."

    fixed_deltas = [compute_progress_note(row["diem_ky_sau"], row)[0] for _, row in df.iterrows()]
    fixed_improving_rate = sum(1 for d in fixed_deltas if d > 0.15) / len(fixed_deltas)
    assert fixed_improving_rate < 0.5, (
        f"Tỷ lệ 'đang cải thiện' sau khi sửa vẫn quá cao ({fixed_improving_rate:.2%}), có thể vẫn còn lệch thang."
    )


# ---------------------------------------------------------------------------
# Kiểm tra ai_advisor.py THẬT SỰ gọi các hàm trên (không chỉ import rồi bỏ đó)
# ---------------------------------------------------------------------------
def test_ai_advisor_does_not_read_target_column_directly_as_prediction():
    source = inspect.getsource(ai_advisor)
    assert "predicted_gpa_llm = student_data_llm_row.get(gpa_col_llm, 0.0)" not in source, (
        "ai_advisor.py vẫn đọc thẳng cột dữ liệu (có thể là target thật) làm "
        "\"điểm dự đoán\" thay vì gọi predict_for_student() qua mô hình Production."
    )
    assert "predict_for_student(" in source


def test_ai_advisor_progress_note_uses_shared_same_scale_function():
    source = inspect.getsource(ai_advisor)
    assert "delta = float(predicted_gpa_llm) - float(prev_gpa_value)" not in source, (
        "ai_advisor.py vẫn tự trừ trực tiếp predicted_gpa_llm (thang 10) cho "
        "gpa_previous (thang 4) mà không quy đổi cùng thang."
    )
    assert "compute_progress_note(" in source


def test_prompt_reflects_gpa_source_label_not_hardcoded_du_doan():
    """K-3: prompt LLM phải ghi đúng nhãn nguồn (model_service.gpa_label) —
    KHÔNG hard-code "Điểm dự đoán (GPA)" khi thực ra là điểm quan sát được."""
    from dss.core.models import MultiAIProvider

    advisor = MultiAIProvider.__new__(MultiAIProvider)
    prompt, *_ = advisor._prepare_personalized_advice_prompt(
        ["Cần cải thiện điểm danh"],
        6.5,
        [],
        student_profile={"risk_level": "cao", "gpa_label": "Điểm hiện tại (chưa có mô hình Production)"},
    )
    assert "Điểm hiện tại (chưa có mô hình Production)" in prompt
