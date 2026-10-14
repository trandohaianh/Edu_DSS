"""P-6: Khối Kết hợp (Voting Ensemble) phân loại — (1) dùng khóa chỉ số KHÁC
mô hình đơn (Precision/Recall/F1-Score/Train Accuracy thay vì Precision (Macro)/
.../F1 Score (Macro)/Accuracy (Train)), khiến bảng so sánh/xếp hạng không đọc
được; (2) không lọc nhãn -1 (mẫu test có nhãn không xuất hiện trong train) như
mô hình đơn; (3) Pipeline chỉ có preprocessor, bỏ qua sampler/feature_selection
mà các model con đã thực sự dùng khi huấn luyện riêng lẻ."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer
from dss.services.model_service import build_metrics_dataframe


def _make_imbalanced_df(n_majority=340, n_minority=60, random_state=42):
    """Đủ mẫu thiểu số để SMOTE thực sự được kích hoạt (khác dữ liệu mẫu
    generate_data(), nơi lớp "Yếu" chỉ có 2 mẫu nên SMOTE tự tắt an toàn cho
    CẢ model đơn lẫn ensemble — không phân biệt được lỗi P-6 cần kiểm chứng)."""
    rng = np.random.RandomState(random_state)
    n = n_majority + n_minority
    df = pd.DataFrame({
        "f1": rng.normal(0, 1, n),
        "f2": rng.normal(0, 1, n),
        "f3": rng.normal(0, 1, n),
        "target": ["A"] * n_majority + ["B"] * n_minority,
    })
    return df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)


def test_voting_ensemble_uses_same_metric_keys_as_single_models():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    clf = ClassificationTrainer()
    results, pipelines, *_ = clf.train_and_evaluate(
        df, feats, "xep_loai",
        ["Logistic Regression (Softmax)", "Random Forest Classifier"],
        training_strategy="Kết hợp (Ensemble)",
        cv_folds=3, save_model=False,
    )
    ensemble_names = [k for k in results if "Kết hợp" in str(k)]
    assert ensemble_names, f"Không có Voting Ensemble nào được tạo: {list(results)}"
    ensemble_metrics = results[ensemble_names[0]]
    single_metrics = results["Logistic Regression (Softmax)"]
    # Cùng bộ khóa chỉ số cốt lõi với mô hình đơn -> build_metrics_dataframe đọc được.
    for key in ("Accuracy", "F1 Score (Macro)", "F1 Score (Weighted)", "Precision (Macro)", "Recall (Macro)", "Accuracy (Train)"):
        assert key in ensemble_metrics, f"Ensemble thiếu khóa '{key}' mà mô hình đơn có: {list(ensemble_metrics)}"
        assert key in single_metrics

    metrics_df = build_metrics_dataframe(results, "clf")
    assert ensemble_names[0] in metrics_df.index, (
        "build_metrics_dataframe không đọc được Ensemble do lệch khóa chỉ số."
    )


def test_voting_ensemble_pipeline_includes_sampler_when_balance_method_used():
    df = _make_imbalanced_df()
    clf = ClassificationTrainer()
    results, pipelines, *_ = clf.train_and_evaluate(
        df, ["f1", "f2", "f3"], "target",
        ["Logistic Regression (Softmax)", "Random Forest Classifier"],
        training_strategy="Kết hợp (Ensemble)",
        balance_method="smote",
        cv_folds=3, save_model=False,
    )
    ensemble_names = [k for k in results if "Kết hợp" in str(k)]
    assert ensemble_names
    ensemble_pipeline = pipelines[ensemble_names[0]]
    single_pipeline = pipelines["Logistic Regression (Softmax)"]
    has_sampler_single = "sampler" in single_pipeline.named_steps
    has_sampler_ensemble = "sampler" in ensemble_pipeline.named_steps
    assert has_sampler_single is True, "Tiền đề test sai: model đơn không có sampler dù balance_method=smote."
    assert has_sampler_ensemble == has_sampler_single, (
        "Pipeline của Ensemble không đồng bộ bước sampler với mô hình đơn "
        f"(đơn={has_sampler_single}, ensemble={has_sampler_ensemble})."
    )
