"""Classification, regression trainers and preprocessor.

Giữ nguyên đường import cũ ``dss.core.trainers``. Mã thật đã được tách theo chức năng:

- ``dss.core.training.common``         cân bằng lớp, PR-AUC, lưới tham số RF
- ``dss.core.training.classification`` ``ClassificationTrainer``
- ``dss.core.training.regression``     ``RegressionTrainer``
- ``dss.core.training.preprocessing``  ``DataPreprocessor``

Mô hình đã lưu (joblib) tham chiếu tên cũ vẫn nạp được vì các lớp được re-export ở đây.
Khi cần monkeypatch một hàm thư viện mà bộ huấn luyện dùng (VD ``train_test_split``),
patch ở module con nơi nó được dùng, không patch ở đây.
"""

from __future__ import annotations

from dss.config import LIGHTGBM_AVAILABLE, SHAP_AVAILABLE, XGBOOST_AVAILABLE
from dss.core.training.classification import ClassificationTrainer
from dss.core.training.common import (
    PR_AUC_SELECTION_THRESHOLD,
    RF_CLASSIFIER_GRID_COMPACT,
    RF_CLASSIFIER_GRID_FULL,
    _pr_auc_macro_scorer,
    apply_class_weight_balanced,
    pr_auc_macro,
)
from dss.core.training.preprocessing import DataPreprocessor
from dss.core.training.regression import RegressionTrainer

__all__ = [
    "LIGHTGBM_AVAILABLE",
    "PR_AUC_SELECTION_THRESHOLD",
    "RF_CLASSIFIER_GRID_COMPACT",
    "RF_CLASSIFIER_GRID_FULL",
    "SHAP_AVAILABLE",
    "XGBOOST_AVAILABLE",
    "ClassificationTrainer",
    "DataPreprocessor",
    "RegressionTrainer",
    "_pr_auc_macro_scorer",
    "apply_class_weight_balanced",
    "pr_auc_macro",
]
