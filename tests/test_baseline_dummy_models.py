"""P-4: không có mốc so sánh (baseline) — không cách nào biết mô hình thật có
thực sự học được gì hơn "đoán bừa theo lớp đa số" (phân loại) / "luôn đoán
trung bình" (hồi quy) hay không. Thêm DummyClassifier/DummyRegressor dưới khóa
"__baseline__" — không bao giờ được xếp hạng/chọn làm is_best."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer, RegressionTrainer
from dss.services.model_service import build_metrics_dataframe, pick_best_model_name


def test_classification_results_include_baseline_marker():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(df, feats, "xep_loai", ["Logistic Regression (Softmax)"], cv_folds=3, save_model=False)
    assert "__baseline__" in results
    assert "Accuracy" in results["__baseline__"]


def test_regression_results_include_baseline_marker():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, *_ = reg.train_and_evaluate(df, feats, "diem_ky_sau", ["Linear Regression"], cv_folds=3, save_model=False)
    assert "__baseline__" in results
    assert "R2 Score" in results["__baseline__"]


def test_baseline_never_picked_as_best_model_classification():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(df, feats, "xep_loai", ["Logistic Regression (Softmax)", "Random Forest Classifier"], cv_folds=3, save_model=False)
    assert pick_best_model_name(results, "clf") != "__baseline__"


def test_baseline_excluded_from_metrics_dataframe():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, *_ = reg.train_and_evaluate(df, feats, "diem_ky_sau", ["Linear Regression"], cv_folds=3, save_model=False)
    metrics_df = build_metrics_dataframe(results, "reg")
    assert "__baseline__" not in metrics_df.index
