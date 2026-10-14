"""R-1: RegressionTrainer.train_and_evaluate loại ngoại lai (IQR) trên TOÀN BỘ
X TRƯỚC khi chia train/test — nên tập test CŨNG bị lọc ngoại lai, khiến chỉ số
đánh giá lạc quan hơn thực tế: khi dùng thật, sinh viên "bất thường" (thường
chính là nhóm rủi ro cần chú ý) vẫn đi vào mô hình dự đoán, nhưng KHÔNG BAO GIỜ
xuất hiện trong benchmark lúc huấn luyện. Phải chia train/test TRƯỚC, tính biên
IQR CHỈ trên train, và CHỈ lọc train — tập test giữ nguyên 100%."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import RegressionTrainer


def test_outlier_removal_does_not_shrink_test_set():
    df = generate_data()
    feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]
    reg = RegressionTrainer()

    _results_none, _pipes_none, _eval_none, _used_none, X_test_none, y_test_none, _xtrain_none = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Linear Regression"],
        cv_folds=3, save_model=False, outlier_method="none", test_size=0.2,
    )
    _results_iqr, _pipes_iqr, _eval_iqr, _used_iqr, X_test_iqr, y_test_iqr, _xtrain_iqr = reg.train_and_evaluate(
        df, feats, "diem_ky_sau", ["Linear Regression"],
        cv_folds=3, save_model=False, outlier_method="iqr", test_size=0.2,
    )

    assert len(X_test_iqr) == len(X_test_none), (
        f"Tập test bị thay đổi kích thước khi bật loại ngoại lai (IQR): "
        f"{len(X_test_iqr)} != {len(X_test_none)} — chứng tỏ ngoại lai đang bị lọc "
        "TRÊN CẢ tập test, không chỉ tập train."
    )
