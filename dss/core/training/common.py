"""Thành phần dùng chung của các bộ huấn luyện: cân bằng lớp, PR-AUC, lưới tham số RF."""

from __future__ import annotations

import numpy as np
from sklearn.base import clone
from sklearn.metrics import (
    average_precision_score,
)
from sklearn.preprocessing import label_binarize

from dss.core.logging_config import get_logger


def apply_class_weight_balanced(model):
    """Trả về (model, đã_áp_dụng) với class_weight='balanced' nếu estimator hỗ trợ.

    Đây là phương án cân bằng lớp KHÔNG sinh dữ liệu giả, đối lập với SMOTE. Khi
    lớp thiểu số chỉ còn 2 mẫu, láng giềng cùng lớp duy nhất của mẫu này là mẫu
    kia, nên MỌI điểm SMOTE nội suy ra đều nằm trên đoạn thẳng nối hai mẫu đó —
    đo được: 996 mẫu sinh ra chỉ chiếm 1 chiều trong không gian 5 chiều. Nó làm
    mô hình tự tin hơn mà không thêm thông tin nào. class_weight thay vào đó chỉ
    tăng trọng số phạt khi đoán sai lớp hiếm, và chạy được ở mọi cỡ lớp.

    XGBoost đa lớp không nhận class_weight (chỉ có scale_pos_weight cho nhị phân),
    nên trả về cờ False để nơi gọi ghi log rõ thay vì âm thầm bỏ qua.
    """
    try:
        if "class_weight" in model.get_params():
            balanced = clone(model)
            balanced.set_params(class_weight="balanced")
            return balanced, True
    except Exception as exc:
        _logger.warning("Không đặt được class_weight: %s", exc)
    return model, False


def pr_auc_macro(y_true, y_proba, classes):
    """PR-AUC (average precision) trung bình macro theo kiểu một-chọi-phần-còn-lại.

    Vì sao cần bên cạnh F1-macro: F1 đo tại MỘT ngưỡng cố định. Với lớp thiểu số
    chỉ vài mẫu, recall của lớp đó chỉ nhận được vài giá trị rời rạc (2 mẫu -> 0,
    0.5 hoặc 1), nên F1-macro dịch rất mạnh chỉ vì một mẫu đoán đúng hay sai và
    không đủ ổn định để chọn mô hình. PR-AUC lấy trung bình trên toàn dải ngưỡng,
    tức đo khả năng XẾP ĐÚNG THỨ TỰ — đúng với cách sản phẩm được dùng, vì đầu ra
    của hệ thống là danh sách lớp xếp theo mức rủi ro chứ không phải nhãn nhị phân.

    Trả về None khi không tính được (thiếu xác suất, chỉ có một lớp trong tập test).
    """
    try:
        if y_proba is None:
            return None
        classes = list(classes)
        if len(classes) < 2:
            return None
        if len(classes) == 2:
            proba = np.asarray(y_proba)
            score = proba[:, 1] if proba.ndim == 2 and proba.shape[1] == 2 else proba
            return float(average_precision_score((np.asarray(y_true) == classes[1]).astype(int), score))
        y_bin = label_binarize(y_true, classes=classes)
        if y_bin.shape[1] != np.asarray(y_proba).shape[1]:
            return None
        return float(average_precision_score(y_bin, np.asarray(y_proba), average="macro"))
    except Exception as exc:
        _logger.warning("Không tính được PR-AUC: %s", exc)
        return None


# Dưới ngưỡng này (số mẫu của lớp ÍT NHẤT trong tập train), F1 tại một ngưỡng cố
# định dịch quá mạnh theo từng mẫu để dùng làm tiêu chí chọn mô hình, nên
# GridSearchCV chuyển sang PR-AUC. Chọn 20 vì ở cỡ đó một mẫu đổi recall của lớp
# thiểu số khoảng 5 điểm phần trăm — vẫn lớn nhưng đã đọc được; dưới nữa thì bước
# nhảy rời rạc lấn át chênh lệch thật giữa các mô hình.
PR_AUC_SELECTION_THRESHOLD = 20


def _pr_auc_macro_scorer(y_true, y_proba):
    """Bọc pr_auc_macro thành scorer cho GridSearchCV ở bài toán nhiều hơn 2 lớp.

    sklearn không có sẵn chuỗi scoring 'average_precision' cho đa lớp, nên dựng tay.
    Trả về 0.0 thay vì None khi không tính được, vì GridSearchCV cần một số để so sánh.
    """
    classes = np.unique(y_true)
    value = pr_auc_macro(y_true, y_proba, classes)
    return 0.0 if value is None else value


# Giữ tên logger cũ để cấu hình log và bộ lọc hiện có không đổi sau khi tách module.
_logger = get_logger("dss.core.trainers")


# Lưới Random Forest phân loại: đầy đủ (24 tổ hợp) cho dữ liệu nhỏ, gọn (8) cho dữ
# liệu lớn — trên 20.000 SV cả 2 chọn cùng tham số tốt nhất (xem dss/core/tuning.py).
RF_CLASSIFIER_GRID_FULL = {
    'model__n_estimators': [100, 200],
    'model__max_depth': [10, 20, None],
    'model__min_samples_split': [2, 5],
    'model__min_samples_leaf': [1, 2],
}


RF_CLASSIFIER_GRID_COMPACT = {
    'model__n_estimators': [100, 200],
    'model__max_depth': [10, None],
    'model__min_samples_split': [2],
    'model__min_samples_leaf': [1, 2],
}
