"""P-3: k_neighbors của SMOTE bị cứng min(2, ...) bất kể có đủ mẫu thiểu số hay
không — làm giảm chất lượng oversampling một cách không cần thiết khi dữ liệu
đủ lớn. sklearn/imblearn khuyến nghị mặc định k_neighbors=5; chỉ nên giảm khi
THẬT SỰ thiếu mẫu (điều kiện an toàn vẫn giữ nguyên)."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

from dss.core.trainers import ClassificationTrainer

try:
    from imblearn.over_sampling import SMOTE  # noqa: F401

    IMBLEARN_AVAILABLE = True
except Exception:
    IMBLEARN_AVAILABLE = False


def _make_imbalanced_df(n_majority=340, n_minority=60, random_state=42):
    rng = np.random.RandomState(random_state)
    n = n_majority + n_minority
    df = pd.DataFrame(
        {
            "f1": rng.normal(0, 1, n),
            "f2": rng.normal(0, 1, n),
            "f3": rng.normal(0, 1, n),
            "target": ["A"] * n_majority + ["B"] * n_minority,
        }
    )
    return df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)


@pytest.mark.skipif(not IMBLEARN_AVAILABLE, reason="imbalanced-learn chưa cài đặt")
def test_smote_k_neighbors_uses_up_to_5_when_enough_minority_samples():
    df = _make_imbalanced_df()
    clf = ClassificationTrainer()
    results, pipelines, *_ = clf.train_and_evaluate(
        df,
        ["f1", "f2", "f3"],
        "target",
        ["Logistic Regression (Softmax)"],
        balance_method="smote",
        cv_folds=5,
        save_model=False,
    )
    pipeline = pipelines["Logistic Regression (Softmax)"]
    sampler = pipeline.named_steps.get("sampler")
    assert sampler is not None, "SMOTE sampler không được áp dụng dù đủ mẫu thiểu số."
    assert sampler.k_neighbors > 2, (
        f"k_neighbors={sampler.k_neighbors} vẫn bị giới hạn cứng ở 2 dù dữ liệu đủ "
        "mẫu thiểu số để dùng k lớn hơn (tối đa 5)."
    )
    assert sampler.k_neighbors <= 5
