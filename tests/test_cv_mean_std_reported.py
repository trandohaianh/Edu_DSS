"""P-5: chỉ có MỘT lần chia holdout (train/test) để đánh giá — chỉ số trên tập
test có thể lệch do may rủi cách chia dữ liệu (đặc biệt với tập nhỏ). Cần lưu
thêm cv_mean/cv_std (từ chính GridSearchCV đã chạy trên tập train) để biết mức
ổn định của mô hình qua nhiều fold, hiển thị cạnh chỉ số trên tập test."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer, RegressionTrainer


def test_classification_grid_search_models_report_cv_mean_std():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(
        df, feats, "xep_loai", ["Random Forest Classifier"], cv_folds=3, save_model=False
    )
    m = results["Random Forest Classifier"]
    assert m.get("cv_mean") is not None
    assert m.get("cv_std") is not None
    assert 0.0 <= m["cv_mean"] <= 1.0


def test_regression_grid_search_models_report_cv_mean_std():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()
    results, *_ = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Random Forest Regressor"], cv_folds=3, save_model=False
    )
    m = results["Random Forest Regressor"]
    assert m.get("cv_mean") is not None
    assert m.get("cv_std") is not None
    assert m["cv_mean"] >= 0.0  # MAE dương
