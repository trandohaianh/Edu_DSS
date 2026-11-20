"""Classification, regression trainers and preprocessor."""
from __future__ import annotations

import math
from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.feature_selection import RFE, SelectKBest, mutual_info_classif
from sklearn.impute import KNNImputer, SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    make_scorer,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import label_binarize
from sklearn.model_selection import GridSearchCV, train_test_split  # noqa: F401

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


from dss.core import tuning
from sklearn.pipeline import Pipeline, Pipeline as SklearnPipeline
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, OneHotEncoder, StandardScaler

from dss.config import (
    IMB_LEARN_AVAILABLE,
    ImbPipeline,
    SMOTE,
    BorderlineSMOTE,
    ADASYN,
    SHAP_AVAILABLE,
    shap,
    st_shap,
    xgb,
    lgb,
    XGBOOST_AVAILABLE,
    LIGHTGBM_AVAILABLE,
)
from dss.core.logging_config import get_logger

_logger = get_logger(__name__)
from dss.core.feature_utils import FS_AVAILABLE, feature_selector
from dss.core.utils import (
    _make_safe_cv_strategy,
    _normalize_labels_for_metrics,
    find_repeated_group_column,
    group_holdout_split,
    make_group_cv_splits,
)
from dss.core.target_utils import (
    canonicalize_columns,
    COLUMN_ALIASES,
    filter_leakage_features,
    detect_temporal_column,
    temporal_train_test_split,
    get_leaky_target_columns,
    LEGITIMATE_PREDICTORS,
    HEURISTIC_TARGET_ACCURACY,
    HEURISTIC_OVERFIT_DIFF_MILD,
    HEURISTIC_OVERFIT_DIFF_SEVERE,
)


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


class ClassificationTrainer:
    """
    Class này CHỈ xử lý việc huấn luyện và đánh giá các mô hình Phân loại (Classification)
    cho Mô hình 1, đúng theo yêu cầu của bạn.
    """

    def __init__(self):
        # *** CHÚ THÍCH: Định nghĩa các mô hình Phân loại ***
        self.models = {
            'Logistic Regression (Softmax)': LogisticRegression(random_state=42, max_iter=1000),
            # *** NÂNG CẤP: Thêm class_weight='balanced' để xử lý mất cân bằng ***
            'Random Forest Classifier': RandomForestClassifier(
                n_estimators=80, random_state=42, class_weight='balanced'
            ),
        }
        if XGBOOST_AVAILABLE:
            self.models['XGBoost Classifier'] = xgb.XGBClassifier(
                random_state=42, use_label_encoder=False, eval_metric='mlogloss')
        if LIGHTGBM_AVAILABLE:
            self.models['LightGBM Classifier'] = lgb.LGBMClassifier(
                random_state=42, verbosity=-1)  # Thêm verbosity để tắt log

    # Không dùng @st.cache_data: hàm gọi widget Streamlit (st.write, nút lưu/xuất, …).
    def train_and_evaluate(
            _self,
            df,
            feature_cols,
            target_col,
            selected_models,
            training_strategy="So sánh nhiều mô hình (Compare)", # NEW: Chiến lược huấn luyện
            balance_method="none", # NEW: Cân bằng dữ liệu
            fs_method="none",      # NEW: Chọn đặc trưng
            k_features=20,         # NEW: Số đặc trưng
            test_size=0.2,         # NEW: Tỷ lệ test
            cv_folds=5,            # NEW: Số fold cross-validation
            save_model=True,       # NEW: Lưu mô hình
            _warehouse=None,       # NEW: Warehouse pipeline
            _dataset_id=None,      # NEW: Dataset ID
            split_strategy="random",
            time_col=None,
            data_source_type=None):
        """Huấn luyện và đánh giá các mô hình Phân loại đã chọn."""

        # *** FIX LỖI: Kiểm tra feature_cols không bị rỗng ***
        if not feature_cols:
            _logger.error("Lỗi Huấn luyện: Không có feature nào được chọn. Vui lòng kiểm tra lại cài đặt.")
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        _logger.info("Bắt đầu huấn luyện Phân loại cho cột: %s...", target_col)
        # Chuẩn bị dữ liệu: Canonicalize aliases và lọc rò rỉ dữ liệu (Target Leakage Guard)
        df_clean, _actions = canonicalize_columns(df, strict=False, return_actions=True)
        # C1.1: target có thể là alias cũ (vd. final_score) đã được canonicalize
        # thành cột chuẩn — đổi theo, thay vì KeyError khi dataset có cả hai cột.
        if target_col not in df_clean.columns and COLUMN_ALIASES.get(target_col) in df_clean.columns:
            target_col = COLUMN_ALIASES[target_col]
        available_features, _removed_leaks = filter_leakage_features(df_clean, target_col, feature_cols, return_removed=True)
        if _removed_leaks:
            _logger.info("Đã loại bỏ các cột rò rỉ/alias khỏi Phân loại (%s): %s", target_col, _removed_leaks)

        if not available_features:
            _logger.error("Lỗi: Không còn feature hợp lệ nào sau khi loại bỏ ID/Target/Aliases/Leakage!")
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        X = df_clean[available_features]
        y = df_clean[target_col]

        # Loại bỏ dòng trùng lặp hoàn toàn trước khi chia train/test: an toàn để làm 1 lần trên
        # toàn bộ dữ liệu (không dùng thống kê suy ra từ target nên không gây rò rỉ dữ liệu như
        # imputer/scaler), đồng thời tránh trường hợp cùng 1 bản ghi trùng lặp lọt vào cả train
        # lẫn test khiến mô hình "học thuộc" thay vì tổng quát hóa.
        dup_mask = pd.concat([X, y], axis=1).duplicated()
        if dup_mask.any():
            _logger.info("Đã loại %d dòng trùng lặp hoàn toàn trước khi huấn luyện.", int(dup_mask.sum()))
            X = X[~dup_mask]
            y = y[~dup_mask]

        # Dòng thiếu nhãn không dùng để học: nếu để lại, LabelEncoder biến NaN thành một "lớp" riêng
        # (target số) hoặc ném TypeError khi trộn chuỗi với NaN (target chữ). Nhánh hồi quy cũng làm vậy.
        label_mask = y.notna()
        if not label_mask.all():
            _logger.info("Đã loại %d dòng thiếu giá trị mục tiêu `%s`.", int((~label_mask).sum()), target_col)
            X = X[label_mask]
            y = y[label_mask]

        numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()
        from dss.core.data_helpers import create_shared_preprocessor  # import trễ: tránh vòng lặp import trainers<->data_helpers
        preprocessor = create_shared_preprocessor(
            numeric_features, categorical_features)

        # Chặn target không phù hợp cho phân loại (thường là dữ liệu kiểu hồi quy hoặc cột ID/mã).
        y_non_null = y.dropna()
        total_samples = len(y_non_null)
        unique_classes = y_non_null.nunique()
        unique_ratio = (unique_classes / total_samples) if total_samples > 0 else 1.0
        class_count_map = y_non_null.value_counts()
        min_class_samples = int(class_count_map.min()) if not class_count_map.empty else 0
        singleton_classes = int((class_count_map == 1).sum()) if not class_count_map.empty else 0

        if total_samples < 10:
            _logger.error("Không thể huấn luyện phân loại: số mẫu hợp lệ quá ít (< 10).")
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        is_regression_like = unique_ratio > 0.5
        has_too_many_classes = unique_classes > max(20, int(0.3 * total_samples))
        has_too_many_singletons = singleton_classes > int(0.3 * unique_classes) and min_class_samples < 2

        if unique_classes < 2:
            _logger.error("Cột mục tiêu `%s` chỉ có %d lớp nên không thể chạy phân loại.", target_col, unique_classes)
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        if is_regression_like or has_too_many_classes or has_too_many_singletons:
            _logger.error("Cột mục tiêu `%s` không phù hợp cho bài toán phân loại (%d/%d lớp).", target_col, unique_classes, total_samples)
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        # Mã hóa cột target (ví dụ: 'A', 'B', 'C' -> 0, 1, 2)
        le = LabelEncoder()
        y_encoded = le.fit_transform(y)
        class_labels = le.classes_

        # Kiểm tra xem có thể thực hiện stratify không
        from collections import Counter
        class_counts = Counter(y_encoded)
        stratify_param = y_encoded if all(
            count >= 2 for count in class_counts.values()) else None

        # Dữ liệu dọc (1 dòng / sinh viên / học kỳ): chia theo NHÓM sinh viên để không có sinh
        # viên nào vừa ở train vừa ở test/fold kiểm định. None = mỗi SV 1 dòng -> chia như cũ.
        group_col = find_repeated_group_column(df_clean, X.index, exclude=available_features)

        def _random_split():
            if group_col is not None:
                _logger.info("Chia train/test theo nhóm '%s' (GroupShuffleSplit): mỗi SV nằm trọn 1 phía.", group_col)
                tr_pos, te_pos = group_holdout_split(len(X), df_clean.loc[X.index, group_col], test_size)
                return X.iloc[tr_pos], X.iloc[te_pos], y_encoded[tr_pos], y_encoded[te_pos]
            return train_test_split(X, y_encoded, test_size=test_size, random_state=42, stratify=stratify_param)

        # Cải thiện: Chia train/test với test_size tùy chỉnh
        if split_strategy == "temporal":
            _time_col = time_col or detect_temporal_column(df_clean, feature_cols=available_features)
            if _time_col and _time_col in df_clean.columns:
                _logger.info("Sử dụng Temporal Split trên cột '%s' (train=quá khứ, test=tương lai)", _time_col)
                X_train, X_test, y_train_s, y_test_s = temporal_train_test_split(
                    X, pd.Series(y_encoded, index=X.index), df_clean.loc[X.index, _time_col], test_size=test_size
                )
                y_train = y_train_s.to_numpy()
                y_test = y_test_s.to_numpy()
            else:
                _logger.warning("Không tìm thấy cột thời gian để thực hiện Temporal Split; fallback sang Random Split.")
                X_train, X_test, y_train, y_test = _random_split()
        else:
            X_train, X_test, y_train, y_test = _random_split()

        # Giữ lại nhãn gốc (chuỗi) của tập test theo đúng chỉ số dòng — dùng để trả về ngoài
        # hàm cho biểu đồ/so sánh, tránh phải tự chia train/test lại một lần nữa ở nơi gọi
        # (dễ lệch với tập test thật sự đã dùng để đánh giá, và lệch cả không gian nhãn vì
        # pipeline.predict() trả về mã số nội bộ chứ không phải chuỗi gốc).
        y_test_original = y.loc[X_test.index]

        # Không tách riêng validation set nữa: GridSearchCV bên dưới đã tự làm K-fold
        # cross-validation trên chính tập train để chọn tham số tối ưu — validation set tĩnh
        # trước đây chỉ tốn ~15% dữ liệu train mà không phục vụ quyết định nào (không dùng để
        # chọn tham số, không dùng để xếp hạng mô hình). Dồn toàn bộ X_train cho huấn luyện.
        X_train_final = X_train

        # Remap nhãn theo chính tập train để đảm bảo label liên tiếp 0..K-1.
        # Điều này đặc biệt quan trọng cho XGBoost Classifier (không chấp nhận label rời rạc).
        train_label_encoder = LabelEncoder()
        y_train = train_label_encoder.fit_transform(y_train)
        y_train_final = y_train

        train_label_mapping = {
            int(old_label): int(new_label)
            for new_label, old_label in enumerate(train_label_encoder.classes_)
        }

        def _remap_with_unknown(arr, unknown_value=-1):
            remapped = np.array(
                [train_label_mapping.get(int(v), unknown_value) for v in arr],
                dtype=int
            )
            return remapped

        y_test = _remap_with_unknown(y_test)

        # Chỉ giữ các mẫu hợp lệ (nhãn xuất hiện trong train) khi đánh giá để tránh crash metric.
        valid_test_mask = y_test >= 0
        if not np.all(valid_test_mask):
            _logger.warning("Một phần mẫu test có nhãn không xuất hiện trong train, bỏ qua khi tính metric test.")

        # Cập nhật nhãn lớp theo encoder mới (vẫn giữ tên gốc để hiển thị).
        class_labels = le.classes_[train_label_encoder.classes_]
        
        from collections import Counter
        class_counts = Counter(y_train_final)
        min_class_samples = min(class_counts.values()) if class_counts else 0
        # Ước lượng số mẫu thiểu số còn lại trong mỗi fold train (để SMOTE không vỡ trong CV)
        safe_cv_for_sampling = max(2, min(int(cv_folds), min_class_samples)) if min_class_samples >= 2 else 2
        min_train_samples_per_fold = (
            min_class_samples - math.ceil(min_class_samples / safe_cv_for_sampling)
            if min_class_samples > 0
            else 0
        )
        # P-3: k mặc định khuyến nghị của SMOTE là 5 — trước đây cứng min(2, ...)
        # bất kể có đủ mẫu thiểu số hay không, làm giảm chất lượng oversampling
        # không cần thiết khi dữ liệu đủ lớn. Vẫn giữ điều kiện an toàn khi quá
        # ít mẫu (>= 2 mới bật SMOTE, xem điều kiện min_train_samples_per_fold bên dưới).
        k_neighbors = max(1, min(5, min_train_samples_per_fold - 1)) if min_train_samples_per_fold >= 2 else 0
        
        # Determine the Imblearn Sampler
        sampler = None
        # Lý do cân bằng lớp bị hạ cấp so với yêu cầu (None = chạy đúng như yêu cầu).
        balance_fallback_reason = None
        # Cách cân bằng THỰC SỰ được áp dụng. Khác balance_method khi bộ sinh mẫu
        # không chạy được ở cỡ lớp hiện tại và mã tự hạ cấp sang class_weight.
        balance_method_applied = balance_method
        if balance_method != "none" and IMB_LEARN_AVAILABLE:
            try:
                if balance_method == "class_weight":
                    # Không sinh mẫu — trọng số đặt trên chính estimator ở vòng lặp dưới.
                    sampler = None
                    _logger.info("Cân bằng lớp bằng class_weight='balanced' (không sinh dữ liệu giả).")
                elif min_train_samples_per_fold < 2:
                    # SMOTE/ADASYN cần >= 2 mẫu cùng lớp để nội suy. Trước đây chỗ này
                    # tắt cân bằng rồi chạy tiếp, nên người dùng YÊU CẦU cân bằng lớp mà
                    # nhận về mô hình không cân bằng, và báo cáo vẫn nói đã cân bằng.
                    # Nay tự hạ cấp sang class_weight: cách duy nhất còn chạy được ở cỡ
                    # lớp này vì nó tăng trọng số phạt chứ không nội suy mẫu mới.
                    _logger.warning(
                        "Lớp thiểu số chỉ còn %d mẫu trong mỗi fold train nên '%s' KHÔNG chạy được; "
                        "tự hạ cấp sang class_weight='balanced' (không cần sinh mẫu).",
                        min_train_samples_per_fold, balance_method,
                    )
                    sampler = None
                    balance_fallback_reason = (
                        f"'{balance_method}' cần >= 2 mẫu lớp thiểu số trong mỗi fold train, "
                        f"hiện chỉ có {min_train_samples_per_fold}; đã hạ cấp sang class_weight"
                    )
                    balance_method_applied = "class_weight"
                elif balance_method == "smote" and k_neighbors > 0:
                    sampler = SMOTE(random_state=42, k_neighbors=k_neighbors)
                    _logger.info("Đang áp dụng SMOTE (k_neighbors=%d) để cân bằng dữ liệu...", k_neighbors)
                elif balance_method == "borderline" and k_neighbors > 0:
                    sampler = BorderlineSMOTE(random_state=42, k_neighbors=k_neighbors)
                    _logger.info("Đang áp dụng BorderlineSMOTE (k_neighbors=%d)...", k_neighbors)
                elif balance_method == "adasyn" and k_neighbors > 0:
                    sampler = ADASYN(random_state=42, n_neighbors=k_neighbors)
                    _logger.info("Đang áp dụng ADASYN (n_neighbors=%d)...", k_neighbors)
                else:
                    if k_neighbors <= 0:
                        _logger.warning("Không thể áp dụng SMOTE vì class thiểu số có quá ít mẫu (<=1).")
            except Exception as e:
                _logger.warning("Không thể cân bằng dữ liệu: %s", e)
                sampler = None
        elif balance_method != "none" and not IMB_LEARN_AVAILABLE:
            _logger.warning("Thư viện imbalanced-learn chưa được cài đặt, không thể cân bằng dữ liệu.")

        results, trained_pipelines = {}, {} # Dùng để lưu kết quả và các pipeline đã huấn luyện
        failed_models = {}

        # P-4: mốc so sánh (baseline) — DummyClassifier đoán luôn lớp đa số, để
        # biết mô hình thật có thực sự học được gì hơn ngoài việc "đoán bừa theo
        # tỷ lệ lớp" hay không. Lưu dưới khóa "__baseline__" (build_metrics_dataframe
        # và pick_best_model_name đã lọc bỏ mọi khóa bắt đầu bằng "__" từ trước —
        # mốc này KHÔNG BAO GIỜ được chọn làm is_best/Candidate/Production).
        try:
            from sklearn.dummy import DummyClassifier
            baseline_pipeline = SklearnPipeline(steps=[
                ('preprocessor', preprocessor),
                ('model', DummyClassifier(strategy="most_frequent", random_state=42)),
            ])
            baseline_pipeline.fit(X_train_final, y_train_final)
            baseline_pred_full = baseline_pipeline.predict(X_test)
            if valid_test_mask.any():
                baseline_pred = np.asarray(baseline_pred_full)[valid_test_mask]
                baseline_test_eval = y_test[valid_test_mask]
                results["__baseline__"] = {
                    'Accuracy': accuracy_score(baseline_test_eval, baseline_pred),
                    'F1 Score (Macro)': f1_score(baseline_test_eval, baseline_pred, average='macro', zero_division=0),
                    'F1 Score (Weighted)': f1_score(baseline_test_eval, baseline_pred, average='weighted', zero_division=0),
                    'strategy': 'most_frequent',
                }
        except Exception as e:
            _logger.warning("Không thể tính mốc baseline (DummyClassifier): %s", str(e))

        # Lặp qua từng mô hình được chọn để huấn luyện
        for name in selected_models:
            if name not in _self.models:
                continue
            # clone(): trainer là @st.cache_resource dùng chung mọi phiên. Fit thẳng vào estimator gốc
            # thì lần huấn luyện của người này ghi đè mô hình đang dùng trong phiên của người khác.
            model = clone(_self.models[name])
            if balance_method_applied == "class_weight":
                model, cw_applied = apply_class_weight_balanced(model)
                if not cw_applied:
                    _logger.warning(
                        "%s không nhận tham số class_weight nên chạy KHÔNG cân bằng lớp; "
                        "hãy đọc kết quả của mô hình này tách khỏi các mô hình còn lại.",
                        name,
                    )
            try:
                # Chọn Pipeline phù hợp (ImbPipeline nếu có SMOTE, ngược lại dùng SklearnPipeline)
                PipelineClass = ImbPipeline if sampler is not None else SklearnPipeline
                
                # Setup steps cho pipeline
                steps = [('preprocessor', preprocessor)]
                if sampler:
                    steps.append(('sampler', sampler))
                
                # Áp dụng lựa chọn đặc trưng (Feature Selection)
                if fs_method != "none":
                    if fs_method == "mi":
                        # Mutual Information cần data sau preprocessor
                        # Bỏ qua RFE vì RFE yêu cầu model có coef_ hoặc feature_importances_
                        fs_step = SelectKBest(mutual_info_classif, k=min(k_features, len(X.columns)))
                        steps.append(('feature_selection', fs_step))
                        _logger.info("Đang áp dụng Mutual Information để chọn %d đặc trưng tốt nhất...", k_features)
                    elif fs_method == "rfe" and (name in ['Random Forest Classifier', 'XGBoost Classifier', 'LightGBM Classifier', 'Logistic Regression (Softmax)']):
                        rf_estimator = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
                        fs_step = RFE(estimator=rf_estimator, n_features_to_select=min(k_features, len(X.columns)))
                        steps.append(('feature_selection', fs_step))
                        _logger.info("Đang áp dụng RFE (với RF) để chọn %d đặc trưng tốt nhất...", k_features)
                
                steps.append(('model', model))
                
                # Tạo một pipeline hoàn chỉnh: xử lý dữ liệu -> [cân bằng] -> [chọn đặc trưng] -> huấn luyện mô hình
                pipeline = PipelineClass(steps=steps)
                
                # --- CẬP NHẬT: Ngăn lỗi phân chia n_splits > số lượng mẫu từng class (Dữ liệu imbalanced) ---
                # Đếm số lượng mẫu của class nhỏ nhất trong y_train_final
                from collections import Counter
                class_counts = Counter(y_train_final)
                min_class_samples = min(class_counts.values()) if class_counts else 0
                
                from sklearn.model_selection import StratifiedKFold, KFold
                # Dữ liệu lớn (>= tuning.LARGE_DATA_ROWS dòng train) -> tối đa 3 fold:
                # cùng độ chính xác, nhanh hơn (xem dss/core/tuning.py).
                cv_folds_eff = tuning.effective_cv_folds(len(X_train_final), cv_folds)
                # Điều chỉnh cv_folds cho class thiểu số
                safe_cv = min(cv_folds_eff, min_class_samples)
                
                train_groups = (
                    df_clean.loc[X_train_final.index, group_col].to_numpy() if group_col is not None else None
                )
                group_cv = (
                    make_group_cv_splits(y_train_final, train_groups, desired_folds=max(2, cv_folds_eff),
                                         is_classification=True)
                    if train_groups is not None and pd.Series(train_groups).duplicated().any() else None
                )
                if group_cv is not None:
                    # Fold theo nhóm sinh viên (StratifiedGroupKFold/GroupKFold): các học kỳ của
                    # cùng 1 SV không bị chia sang cả fold huấn luyện lẫn fold kiểm định.
                    cv_strategy = group_cv
                elif min_class_samples >= 2:
                    cv_strategy = StratifiedKFold(n_splits=max(2, safe_cv), shuffle=True, random_state=42)
                else:
                    # Rất mất cân bằng (có class chỉ 1 mẫu). Sklearn KFold sẽ lỗi. Bỏ qua KFold.
                    # Tạo duy nhất 1 split tĩnh (70% train, 30% val nội bộ cho GridSearch)
                    from sklearn.model_selection import train_test_split as tts_internal
                    idx_train, idx_val = tts_internal(
                        range(len(X_train_final)), test_size=0.3, random_state=42
                    )
                    cv_strategy = [(idx_train, idx_val)] 
                    _logger.warning("Cảnh báo: Dữ liệu quá mất cân bằng. Vô hiệu hóa Cross-Validation để chống lỗi.")
                    
                # Tiêu chí chọn mô hình cho GridSearchCV.
                #
                # F1 được tính tại MỘT ngưỡng cố định, nên khi lớp thiểu số chỉ còn vài
                # mẫu thì recall của lớp đó chỉ nhận được vài giá trị rời rạc: với 2 mẫu
                # là 0 / 0,5 / 1. Một mẫu đoán đúng hay sai làm macro-F1 tổng dịch tới
                # 1/số_lớp, tức khoảng 12 điểm phần trăm với 4 lớp. Chọn mô hình bằng con
                # số đó là chọn theo nhiễu.
                #
                # PR-AUC (average precision) lấy trung bình trên toàn dải ngưỡng nên
                # không phụ thuộc một điểm cắt, và nó đo đúng thứ sản phẩm này cần: khả
                # năng XẾP HẠNG sinh viên theo rủi ro để giảng viên gọi từ trên xuống,
                # chứ không phải nhãn nhị phân.
                n_classes_in_train = len(np.unique(y_train_final))
                min_class_count = int(pd.Series(y_train_final).value_counts().min())
                if min_class_count < PR_AUC_SELECTION_THRESHOLD:
                    clf_scoring = (
                        'average_precision' if n_classes_in_train == 2
                        else make_scorer(_pr_auc_macro_scorer, response_method='predict_proba')
                    )
                    _logger.info(
                        "Lớp thiểu số chỉ có %d mẫu (< %d) nên chọn mô hình bằng PR-AUC "
                        "thay vì F1: F1 tại một ngưỡng dịch quá mạnh theo từng mẫu ở cỡ này.",
                        min_class_count, PR_AUC_SELECTION_THRESHOLD,
                    )
                else:
                    clf_scoring = 'f1_macro' if n_classes_in_train > 2 else 'f1_weighted'

                # P-5: cv_mean/cv_std của tiêu chí tối ưu (lấy từ cv_results_ tại
                # best_index_) — chỉ có giá trị với nhánh THẬT SỰ chạy GridSearchCV
                # bên dưới; nhánh train trực tiếp (vd. XGBoost, xem P-1) giữ None.
                cv_mean, cv_std = None, None

                # Cải thiện: Sử dụng GridSearchCV với cross-validation an toàn (cv_strategy)
                if name == 'Random Forest Classifier':
                    # Lưới đầy đủ (24) cho dữ liệu nhỏ; lưới gọn (8) cho dữ liệu lớn — trên
                    # 20.000 SV cả 2 chọn cùng tham số tốt nhất (xem dss/core/tuning.py).
                    param_grid = tuning.select_grid(
                        full=RF_CLASSIFIER_GRID_FULL, compact=RF_CLASSIFIER_GRID_COMPACT,
                        n_train=len(X_train_final),
                    )
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                elif name == 'XGBoost Classifier' and XGBOOST_AVAILABLE and min_class_samples < cv_folds_eff:
                    # P-1: CHỈ bỏ qua GridSearchCV khi THẬT SỰ có nguy cơ thiếu lớp trong
                    # fold (lớp nhỏ nhất < số fold yêu cầu) — trước đây bỏ qua VÔ ĐIỀU KIỆN
                    # cho mọi tập dữ liệu, kể cả khi đủ mẫu/cân bằng để tối ưu an toàn như
                    # LightGBM/Random Forest.
                    # NOTE:
                    # Với tập dữ liệu nhiều lớp hiếm, GridSearchCV chia fold có thể làm nhãn
                    # trong từng fold train bị khuyết (không liên tiếp), XGBoost sẽ báo:
                    # "Invalid classes inferred from unique values of y".
                    # Để tránh crash toàn bộ pipeline, huấn luyện trực tiếp với tham số an toàn.
                    _logger.warning(
                        "XGBoost Classifier tạm bỏ qua GridSearchCV để tránh lỗi nhãn không liên tiếp "
                        "(lớp nhỏ nhất=%d < số fold yêu cầu=%d). Huấn luyện trực tiếp với bộ tham số ổn định.",
                        min_class_samples, cv_folds_eff
                    )
                    try:
                        pipeline.set_params(
                            model__n_estimators=200,
                            model__max_depth=5,
                            model__learning_rate=0.1
                        )
                    except Exception:
                        pass
                    pipeline.fit(X_train_final, y_train_final)
                    _logger.info(
                        "%s: Huấn luyện trực tiếp (không CV) với tham số an toàn (n_estimators=200, max_depth=5, learning_rate=0.1).",
                        name
                    )
                elif name == 'XGBoost Classifier' and XGBOOST_AVAILABLE:
                    # P-1: đủ mẫu ở lớp nhỏ nhất (>= số fold yêu cầu) — an toàn để tối ưu
                    # bằng GridSearchCV với lưới nhỏ tương đương LightGBM.
                    param_grid = {
                        'model__n_estimators': [100, 200],
                        'model__max_depth': [3, 5],
                        'model__learning_rate': [0.1]
                    }
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                elif name == 'LightGBM Classifier' and LIGHTGBM_AVAILABLE:
                    param_grid = {
                        'model__n_estimators': [100, 200],
                        'model__max_depth': [3, 5],
                        'model__learning_rate': [0.1]
                    }
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                elif name == 'Logistic Regression (Softmax)':
                    param_grid = {
                        'model__C': [0.1, 1.0, 10.0],
                        'model__solver': ['lbfgs']
                    }
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                else:
                    # Với các mô hình khác (nếu có), train trực tiếp
                    pipeline.fit(X_train_final, y_train_final)
                
                # Đánh giá cuối cùng trên test set
                y_pred_full = pipeline.predict(X_test)
                if not valid_test_mask.any():
                    _logger.error(
                        "%s: Không có mẫu test hợp lệ sau khi chuẩn hóa nhãn.",
                        name
                    )
                    failed_models[name] = "Không có mẫu test hợp lệ để đánh giá."
                    continue
                y_pred = np.asarray(y_pred_full)[valid_test_mask]
                y_test_eval = y_test[valid_test_mask]

                # Tính toán đầy đủ hệ thống metrics (Accuracy, Macro/Weighted F1, Precision, Recall, Confusion Matrix)
                accuracy = accuracy_score(y_test_eval, y_pred)
                f1_weighted = f1_score(y_test_eval, y_pred, average='weighted', zero_division=0)
                f1_macro = f1_score(y_test_eval, y_pred, average='macro', zero_division=0)
                precision_macro = precision_score(y_test_eval, y_pred, average='macro', zero_division=0)
                recall_macro = recall_score(y_test_eval, y_pred, average='macro', zero_division=0)
                conf_matrix = confusion_matrix(y_test_eval, y_pred).tolist()

                # PR-AUC: chỉ số ổn định hơn F1 khi lớp thiểu số rất ít mẫu, và là
                # tiêu chí ĐANG dùng để chọn mô hình ở cỡ lớp đó — nên phải báo cáo ra,
                # nếu không người đọc không kiểm lại được vì sao mô hình này được chọn.
                pr_auc = None
                try:
                    if hasattr(pipeline, 'predict_proba'):
                        proba_eval = np.asarray(pipeline.predict_proba(X_test))[valid_test_mask]
                        pr_auc = pr_auc_macro(
                            y_test_eval, proba_eval,
                            getattr(pipeline, 'classes_', np.unique(y_test_eval)),
                        )
                except Exception as exc:
                    _logger.warning("%s: không lấy được xác suất để tính PR-AUC: %s", name, exc)
                
                # *** KIỂM TRA OVERFITTING DỰA TRÊN HEURISTIC DỰ ÁN ***
                y_pred_train = pipeline.predict(X_train_final)
                train_accuracy = accuracy_score(y_train_final, y_pred_train)
                accuracy_diff = train_accuracy - accuracy
                
                is_overfitting = False
                suspicious_perfect_score = False

                if train_accuracy < 0.50:
                    _logger.warning("%s: UNDERFITTING! Train Accuracy = %.2f%%", name, train_accuracy * 100)
                elif train_accuracy >= 1.0 and accuracy_diff > HEURISTIC_OVERFIT_DIFF_MILD:
                    is_overfitting = True
                    _logger.warning("%s: DẤU HIỆU OVERFITTING! Train Accuracy = 100%%, Test = %.2f%%", name, accuracy * 100)
                
                if accuracy >= 1.0:
                    # Test accuracy đạt 100% là tín hiệu hiệu năng cao bất thường/nghi ngờ rò rỉ dữ liệu,
                    # KHÔNG kết luận cứng là Overfitting.
                    suspicious_perfect_score = True
                    _logger.warning("%s: CẢNH BÁO HIỆU NĂNG CAO BẤT THƯỜNG! Test Accuracy = 100%%. Đề nghị kiểm tra rò rỉ target.", name)
                elif accuracy_diff > HEURISTIC_OVERFIT_DIFF_SEVERE and train_accuracy > 0.60:
                    is_overfitting = True
                    _logger.warning("%s: DẤU HIỆU OVERFITTING (heuristic gap > %.0f%%)! Train: %.2f%%, Test: %.2f%%, Diff: %.2f%%", name, HEURISTIC_OVERFIT_DIFF_SEVERE * 100, train_accuracy * 100, accuracy * 100, accuracy_diff * 100)
                elif accuracy_diff > HEURISTIC_OVERFIT_DIFF_MILD and train_accuracy > 0.60:
                    _logger.info("%s: Overfitting nhẹ (heuristic gap > %.0f%%). Train: %.2f%%, Test: %.2f%%, Diff: %.2f%%", name, HEURISTIC_OVERFIT_DIFF_MILD * 100, train_accuracy * 100, accuracy * 100, accuracy_diff * 100)
                
                if accuracy < HEURISTIC_TARGET_ACCURACY:
                    _logger.info("%s: Độ chính xác %.2f%% < %.0f%% (ngưỡng mục tiêu dự án)", name, accuracy * 100, HEURISTIC_TARGET_ACCURACY * 100)
                severe_underfit = accuracy <= 0.01 or (train_accuracy <= 0.20 and accuracy <= 0.20)

                if severe_underfit:
                    _logger.warning(
                        "%s: Hiệu năng quá thấp (Test Accuracy: %.2f%%, Train Accuracy: %.2f%%). Tạm loại khỏi danh sách mô hình dùng tiếp.",
                        name, accuracy * 100, train_accuracy * 100
                    )
                    failed_models[name] = (
                        f"Hiệu năng quá thấp (Accuracy={accuracy:.4f}, Train={train_accuracy:.4f})"
                    )
                    continue
                # *** FIX LỖI: Tính toán labels trực tiếp từ y_test thay vì dùng toàn bộ class_labels ***
                y_test_metric, y_pred_metric, labels_in_test = _normalize_labels_for_metrics(y_test_eval, y_pred)
                report = classification_report(
                    y_test_metric,
                    y_pred_metric,
                    labels=labels_in_test,
                    target_names=labels_in_test.tolist(),
                    output_dict=True,
                    zero_division=0)
                results[name] = { # Lưu kết quả đầy đủ
                    'Accuracy': accuracy,
                    'Accuracy (Train)': train_accuracy,
                    'F1 Score (Macro)': f1_macro,
                    'PR-AUC (Macro)': pr_auc,
                    # Phân biệt YÊU CẦU và THỰC TẾ: bộ cân bằng không chạy được thì
                    # kết quả này KHÔNG phải kết quả đã cân bằng lớp, và phải nói rõ.
                    'balance_method': balance_method,
                    'balance_method_effective': (
                        'none' if (sampler is None and balance_method_applied not in ('none', 'class_weight'))
                        else balance_method_applied
                    ),
                    'balance_fallback_reason': balance_fallback_reason,
                    'F1 Score (Weighted)': f1_weighted,
                    'Precision (Macro)': precision_macro,
                    'Recall (Macro)': recall_macro,
                    'Confusion Matrix': conf_matrix,
                    'report': report,
                    'Overfitting': is_overfitting,
                    'Suspicious Perfect Score': suspicious_perfect_score,
                    'Accuracy Diff': accuracy_diff,
                    # P-5: cv_mean/cv_std của tiêu chí tối ưu trên tập TRAIN (None nếu
                    # mô hình không chạy GridSearchCV, vd. XGBoost — xem P-1).
                    'cv_mean': cv_mean,
                    'cv_std': cv_std}
                trained_pipelines[name] = pipeline
                
                if is_overfitting:
                    _logger.warning("Mô hình '%s' bị OVERFITTING! Train: %.2f%%, Test: %.2f%%", name, train_accuracy * 100, accuracy * 100)
                elif accuracy >= HEURISTIC_TARGET_ACCURACY and accuracy < 1.0:
                    _logger.info("ĐẠT MỤC TIÊU! Test Accuracy của '%s' = %.2f%%, Train = %.2f%%", name, accuracy * 100, train_accuracy * 100)
                elif accuracy >= 0.75:
                    _logger.info("Mô hình '%s' gần đạt mục tiêu: Test = %.2f%%, Train = %.2f%%", name, accuracy * 100, train_accuracy * 100)
                else:
                    _logger.warning("Chưa đạt mục tiêu: Test Accuracy của '%s' = %.2f%% < %.0f%%", name, accuracy * 100, HEURISTIC_TARGET_ACCURACY * 100)

                _logger.info(
                    "%s hoàn tất đánh giá: Train Acc=%.2f%%, Test Acc=%.2f%%, F1 Macro=%.4f, F1 Weighted=%.4f, Overfitting=%s",
                    name, train_accuracy * 100, accuracy * 100, f1_macro, f1_weighted, is_overfitting
                )

            except Exception as e:
                _logger.error("Lỗi khi huấn luyện mô hình '%s': %s", name, str(e), exc_info=True)
                failed_models[name] = str(e)
                
        # --- NEW: Thực hiện Ensemble nếu được yêu cầu ---
        if "Kết hợp" in training_strategy and len(trained_pipelines) >= 2:
            _logger.info("Đang xây dựng Mô hình Kết hợp (Ensemble)...")
            
            try:
                # Lọc ra các model từ pipeline
                base_models = []
                for name, pipeline in trained_pipelines.items():
                    base_models.append((name, pipeline.named_steps['model']))

                # Tạo meta-model bằng Voting Classifier
                from sklearn.ensemble import VotingClassifier

                # P-6: dùng CÙNG cấu trúc Pipeline với mô hình đơn (preprocessor +
                # sampler + feature_selection nếu có) — trước đây chỉ có
                # preprocessor, khiến VotingClassifier nhận input KHÔNG cùng
                # không gian đặc trưng mà các model con đã thực sự huấn luyện.
                _ens_pipeline_class = ImbPipeline if sampler is not None else SklearnPipeline
                _ens_steps = [('preprocessor', preprocessor)]
                if sampler:
                    _ens_steps.append(('sampler', sampler))
                if fs_method != "none":
                    if fs_method == "mi":
                        _ens_steps.append((
                            'feature_selection',
                            SelectKBest(mutual_info_classif, k=min(k_features, len(X.columns))),
                        ))
                    elif fs_method == "rfe":
                        _ens_rf_estimator = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
                        _ens_steps.append((
                            'feature_selection',
                            RFE(estimator=_ens_rf_estimator, n_features_to_select=min(k_features, len(X.columns))),
                        ))
                _ens_steps.append(('model', VotingClassifier(estimators=base_models, voting='soft')))
                voting_pipeline = _ens_pipeline_class(steps=_ens_steps)

                # Huấn luyện mô hình kết hợp (Train the ensemble)
                voting_pipeline.fit(X_train_final, y_train_final)

                # P-6: dùng CÙNG cách tính chỉ số + CÙNG lọc nhãn -1 (mẫu test có
                # nhãn không xuất hiện trong train) như mô hình đơn — trước đây
                # không lọc, và dùng khóa chỉ số khác (Precision/Recall/F1-Score/
                # Train Accuracy) so với các mô hình đơn (Precision (Macro)/...),
                # khiến bảng so sánh/xếp hạng không đọc được chỉ số của Ensemble.
                y_pred_voting_full = voting_pipeline.predict(X_test)
                y_pred_voting = np.asarray(y_pred_voting_full)[valid_test_mask]
                y_test_voting_eval = y_test[valid_test_mask]

                accuracy_voting = accuracy_score(y_test_voting_eval, y_pred_voting)
                f1_weighted_voting = f1_score(y_test_voting_eval, y_pred_voting, average='weighted', zero_division=0)
                f1_macro_voting = f1_score(y_test_voting_eval, y_pred_voting, average='macro', zero_division=0)
                precision_macro_voting = precision_score(y_test_voting_eval, y_pred_voting, average='macro', zero_division=0)
                recall_macro_voting = recall_score(y_test_voting_eval, y_pred_voting, average='macro', zero_division=0)

                y_test_metric_v, y_pred_metric_v, labels_in_test_v = _normalize_labels_for_metrics(
                    y_test_voting_eval, y_pred_voting
                )
                report_voting = classification_report(
                    y_test_metric_v,
                    y_pred_metric_v,
                    labels=labels_in_test_v,
                    target_names=labels_in_test_v.tolist(),
                    output_dict=True,
                    zero_division=0,
                )
                train_accuracy_voting = accuracy_score(y_train_final, voting_pipeline.predict(X_train_final))

                name_ensemble = "Khối Kết hợp (Voting Ensemble)"
                results[name_ensemble] = {
                    'Accuracy': accuracy_voting,
                    'Accuracy (Train)': train_accuracy_voting,
                    'F1 Score (Macro)': f1_macro_voting,
                    'F1 Score (Weighted)': f1_weighted_voting,
                    'Precision (Macro)': precision_macro_voting,
                    'Recall (Macro)': recall_macro_voting,
                    'Confusion Matrix': confusion_matrix(y_test_voting_eval, y_pred_voting).tolist(),
                    'report': report_voting,
                    'Overfitting': False,
                    'Suspicious Perfect Score': accuracy_voting >= 1.0,
                    'Accuracy Diff': train_accuracy_voting - accuracy_voting,
                }
                if accuracy_voting <= 0.0:
                    _logger.error("Mô hình kết hợp hiệu năng kém: Test Accuracy = %.2f%%", accuracy_voting * 100)
                    failed_models[name_ensemble] = f"Ensemble hiệu năng quá thấp (Accuracy={accuracy_voting:.4f})"
                elif accuracy_voting < 0.5:
                    _logger.warning("Mô hình kết hợp hiệu năng thấp: Test Accuracy = %.2f%%", accuracy_voting * 100)
                    trained_pipelines[name_ensemble] = voting_pipeline
                else:
                    _logger.info("Kết hợp thành công: Test Accuracy = %.2f%%", accuracy_voting * 100)
                    trained_pipelines[name_ensemble] = voting_pipeline
            except Exception as e:
                _logger.error("Lỗi khi xây dựng mô hình kết hợp: %s", str(e), exc_info=True)
                failed_models["Khối Kết hợp (Voting Ensemble)"] = str(e)
        
        # --- NEW: Lưu mô hình vào Warehouse ---
        if save_model and _warehouse and _dataset_id and trained_pipelines:
             _logger.info("Đang lưu các mô hình đã huấn luyện vào Kho dữ liệu...")
             for name, pipeline in trained_pipelines.items():
                 try:
                     metrics = results.get(name, {})
                     training_id, _ = _warehouse.save_model_training(
                         dataset_id=_dataset_id,
                         model_pipeline=pipeline,
                         model_name=name,
                         feature_cols=available_features,
                         target_col=target_col,
                         metrics=metrics,
                         class_labels=class_labels,
                         data_source_type=data_source_type or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
                         split_strategy=split_strategy,
                         prediction_horizon="next_semester",
                     )
                     _logger.info("Đã lưu '%s': ID %s", name, training_id)
                 except Exception as e:
                     _logger.warning("Không thể lưu '%s': %s", name, e)

        if failed_models:
            results["__failed_models__"] = failed_models
        _logger.info("Hoàn tất huấn luyện Phân loại.")
        return results, trained_pipelines, class_labels, available_features, X_test, y_test_original, X_train_final


class RegressionTrainer:
    """
    Class này CHỈ xử lý việc huấn luyện và đánh giá các mô hình Hồi quy (Regression)
    cho Mô hình 2, đúng theo yêu cầu của bạn.
    
    SỬ DỤNG GRID SEARCH để tìm tham số tối ưu cho từng mô hình.
    """

    def __init__(self):
        # *** CHÚ THÍCH: Định nghĩa các mô hình Hồi quy với tham số cơ bản ***
        # Các tham số này sẽ được tối ưu bằng GridSearchCV
        self.models = {
            'Linear Regression': LinearRegression(),
            'Random Forest Regressor': RandomForestRegressor(
                n_estimators=80, random_state=42
            ),
        }
        if XGBOOST_AVAILABLE:
            self.models['XGBoost Regressor'] = xgb.XGBRegressor(
                random_state=42, objective='reg:squarederror')
        if LIGHTGBM_AVAILABLE:
            self.models['LightGBM Regressor'] = lgb.LGBMRegressor(
                random_state=42, verbosity=-1)
        
        # Định nghĩa grid search parameters cho từng mô hình — ĐÂY LÀ NGUỒN DUY
        # Lưới tham số gọn để giảm thời gian tìm kiếm; số lượt kiểm định chéo
        # vẫn do cv_folds quyết định và mặc định giữ ở 5.
        self.param_grids = {
            'Linear Regression': {},  # Linear Regression không có hyperparameter cần tune
            # Lưới đầy đủ (12); dữ liệu lớn dùng self._compact_param_grids (4) — xem dss/core/tuning.py.
            'Random Forest Regressor': {
                'model__n_estimators': [100, 200],
                'model__max_depth': [10, 20, None],
                'model__min_samples_split': [2, 5]
            },
        }
        self._compact_param_grids = {
            'Random Forest Regressor': {
                'model__n_estimators': [100, 200],
                'model__max_depth': [10, None],
                'model__min_samples_split': [2]
            },
        }
        if XGBOOST_AVAILABLE:
            self.param_grids['XGBoost Regressor'] = {
                'model__n_estimators': [100, 200],
                'model__max_depth': [3, 5],
                'model__learning_rate': [0.1]
        }
        if LIGHTGBM_AVAILABLE:
            self.param_grids['LightGBM Regressor'] = {
                'model__n_estimators': [100, 200],
                'model__max_depth': [3, 5],
                'model__learning_rate': [0.1]
            }

    # Không dùng @st.cache_data: hàm gọi widget Streamlit (render_save_export_buttons, st.write, …).
    def train_and_evaluate(
            _self,
            df,
            feature_cols,
            target_col,
            selected_models,
            training_strategy="So sánh nhiều mô hình (Compare)", # NEW: Chiến lược huấn luyện
            fs_method="none",
            k_features=20,
            test_size=0.2,
            cv_folds=5, 
            save_model=True,
            outlier_method="none", # NEW: Phương pháp loại bỏ ngoại lai
            scaler_type="StandardScaler", # NEW: Loại scaler
            _warehouse=None,
            _dataset_id=None,
            split_strategy="random",
            time_col=None,
            data_source_type=None):
        """
        Huấn luyện và đánh giá các mô hình Hồi quy đã chọn.
        
        Args:
            df: DataFrame chứa dữ liệu
            feature_cols: Danh sách các cột features
            target_col: Tên cột target
            selected_models: Danh sách tên các mô hình cần huấn luyện
            test_size: Tỷ lệ chia test (mặc định 0.2 = 20% test, 80% train). Có thể dùng 0.2, 0.3, etc.
            save_model: Tự động lưu mô hình sau khi huấn luyện (mặc định True)
            warehouse: DataWarehouse instance để lưu mô hình (nếu None thì không lưu)
            dataset_id: ID của dataset (cần thiết nếu save_model=True)
        
        QUY TRÌNH CHI TIẾT:
        -------------------
        1. CHUẨN BỊ DỮ LIỆU:
           - Tách features (X) và target (y)
           - Phân loại numeric và categorical features
           - Tạo preprocessor (KNNImputer + StandardScaler cho số, SimpleImputer + OneHotEncoder cho categorical)
        
        2. CHIA TẬP TRAIN/TEST:
           - Tỷ lệ chia có thể cấu hình (test_size, mặc định 0.2 = 20% test, 80% train)
           - Có thể dùng 0.2 (20-80), 0.3 (30-70), etc.
           - random_state=42 để đảm bảo kết quả có thể tái lập
        
        3. HUẤN LUYỆN MÔ HÌNH:
           - Tạo Pipeline: Preprocessor -> Model
           - Sử dụng GridSearchCV để tìm tham số tối ưu (chỉ trên tập Train)
           - Cross-validation trong GridSearchCV để tránh overfitting
        
        4. ĐÁNH GIÁ MÔ HÌNH:
           - Dự đoán trên tập Test (chưa từng thấy trong quá trình huấn luyện)
        
        5. TÍNH TOÁN CÁC METRIC:
           - RMSE (Root Mean Squared Error): sqrt(mean((y_true - y_pred)2))
             * Đơn vị: cùng đơn vị với target
             * Đặc điểm: Phạt nặng các lỗi lớn (do bình phương)
             * Cà ng thấp cà ng tốt
           
           - MAE (Mean Absolute Error): mean(|y_true - y_pred|)
             * Đơn vị: cùng đơn vị với target
             * Đặc điểm: Ít nhạy cảm với outlier hơn RMSE
             * Cà ng thấp cà ng tốt
           
           - R2 (R-squared / Coefficient of Determination): 1 - (SS_res / SS_tot)
             * SS_res = sum((y_true - y_pred)2)  # Tổng bình phương sai số
             * SS_tot = sum((y_true - y_mean)2)  # Tổng bình phương độ lệch so với trung bình
             * Giá trị: -inf đến 1
             * Ý nghĩa: Tỷ lệ phương sai của target được giải thích bởi mô hình
             * R2 = 1: Mô hình hoàn hảo
             * R2 = 0: Mô hình bằng với dự đoán trung bình
             * R2 < 0: Mô hình tệ hơn dự đoán trung bình
             * Cà ng gần 1 cà ng tốt
        """

        # *** FIX LỖI: Kiểm tra feature_cols không bị rỗng ***
        if not feature_cols:
            _logger.error("Lỗi Huấn luyện: Không có feature nào được chọn.")
            return {}, {}, {}, [], pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()  # cùng 7 giá trị như các nhánh khác

        _logger.info("Bắt đầu huấn luyện Hồi quy cho cột: %s...", target_col)
        
        # ========================================================================
        # BƯỚC 1: CHUẨN BỊ DỮ LIỆU
        # ========================================================================
        # Chuẩn bị dữ liệu: Canonicalize aliases và lọc rò rỉ dữ liệu (Target Leakage Guard)
        df_clean, _actions = canonicalize_columns(df, strict=False, return_actions=True)
        # C1.1: target có thể là alias cũ (vd. final_score) đã được canonicalize
        # thành cột chuẩn — đổi theo, thay vì KeyError khi dataset có cả hai cột.
        if target_col not in df_clean.columns and COLUMN_ALIASES.get(target_col) in df_clean.columns:
            target_col = COLUMN_ALIASES[target_col]
        available_features, _removed_leaks = filter_leakage_features(df_clean, target_col, feature_cols, return_removed=True)
        if _removed_leaks:
            _logger.info("Đã loại bỏ các cột rò rỉ/alias khỏi Hồi quy (%s): %s", target_col, _removed_leaks)

        if not available_features:
            _logger.error("Lỗi: Không còn feature hợp lệ nào sau khi loại bỏ ID/Target/Aliases/Leakage!")
            return {}, {}, {}, [], pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()  # cùng 7 giá trị như các nhánh khác

        X = df_clean[available_features].copy()
        y = df_clean[target_col].copy()

        # Kiểm tra dữ liệu thiếu trong target
        if y.isnull().any():
            _logger.warning("Phát hiện %d giá trị thiếu trong cột target '%s'. Đang loại bỏ...", y.isnull().sum(), target_col)
            valid_mask = ~y.isnull()
            X = X[valid_mask].copy()
            y = y[valid_mask].copy()

        # Loại bỏ dòng trùng lặp hoàn toàn trước khi chia train/test: an toàn để làm 1 lần trên
        # toàn bộ dữ liệu (không dùng thống kê suy ra từ target nên không gây rò rỉ dữ liệu như
        # imputer/scaler), đồng thời tránh trường hợp cùng 1 bản ghi trùng lặp lọt vào cả train
        # lẫn test khiến mô hình "học thuộc" thay vì tổng quát hóa.
        dup_mask = pd.concat([X, y], axis=1).duplicated()
        if dup_mask.any():
            _logger.info("Đã loại %d dòng trùng lặp hoàn toàn trước khi huấn luyện.", int(dup_mask.sum()))
            X = X[~dup_mask]
            y = y[~dup_mask]

        # Ghi nhận số mẫu trước bước loại ngoại lai để giải thích train/predict
        # R-1: KHÔNG loại ngoại lai ở đây nữa (trên toàn bộ X, TRƯỚC khi chia
        # train/test) — làm vậy khiến tập test CŨNG bị lọc ngoại lai, chỉ số
        # đánh giá lạc quan hơn thực tế (SV "bất thường"/nhóm rủi ro vẫn đi vào
        # mô hình khi dùng thật nhưng không bao giờ xuất hiện lúc benchmark).
        # Biên IQR giờ được tính CHỈ trên tập train (xem BƯỚC 2 bên dưới, SAU
        # khi chia train/test) và chỉ lọc train — tập test giữ nguyên 100%.
        st.session_state.last_outlier_method = outlier_method

        # Phân loại features
        numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()
        
        # Tạo preprocessor
        from dss.core.data_helpers import create_shared_preprocessor  # import trễ: tránh vòng lặp import trainers<->data_helpers
        preprocessor = create_shared_preprocessor(
            numeric_features, categorical_features, scaler_type=scaler_type)

        # ========================================================================
        # BƯỚC 2: CHIA TẬP TRAIN/TEST/VALIDATION
        # ========================================================================
        test_size = max(0.1, min(0.5, test_size))
        # Dữ liệu dọc (1 dòng / sinh viên / học kỳ): chia theo NHÓM sinh viên (xem nhánh phân loại).
        group_col = find_repeated_group_column(df_clean, X.index, exclude=available_features)
        if split_strategy == "temporal":
            _time_col = time_col or detect_temporal_column(df_clean, feature_cols=available_features)
            if _time_col and _time_col in df_clean.columns:
                _logger.info("Sử dụng Temporal Split trên cột '%s' (train=quá khứ, test=tương lai)", _time_col)
                X_train, X_test, y_train, y_test = temporal_train_test_split(
                    X, y, df_clean.loc[X.index, _time_col], test_size=test_size
                )
            else:
                _logger.warning("Không tìm thấy cột thời gian để thực hiện Temporal Split; fallback sang Random Split.")
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, 
                    test_size=test_size,
                    random_state=42,
                    shuffle=False
                )
        elif group_col is not None:
            _logger.info("Chia train/test theo nhóm '%s' (GroupShuffleSplit): mỗi SV nằm trọn 1 phía.", group_col)
            tr_pos, te_pos = group_holdout_split(len(X), df_clean.loc[X.index, group_col], test_size)
            X_train, X_test, y_train, y_test = X.iloc[tr_pos], X.iloc[te_pos], y.iloc[tr_pos], y.iloc[te_pos]
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, 
                test_size=test_size,
                random_state=42,
                shuffle=True
            )

        # Chỉ dùng target của TRAIN để phát hiện feature gần như là bản sao
        # của target. Tính corr trên toàn bộ y trước split sẽ làm label test
        # tham gia quyết định feature nào được giữ, khiến holdout không còn kín.
        try:
            numeric_train = X_train.select_dtypes(include=[np.number])
            if not numeric_train.empty and pd.api.types.is_numeric_dtype(y_train):
                correlations = numeric_train.corrwith(y_train).abs()
                protected = {name.lower() for name in LEGITIMATE_PREDICTORS}
                leaky_features = [
                    name for name in correlations[correlations > 0.99].index.tolist()
                    if str(name).lower() not in protected
                ]
                if leaky_features:
                    _logger.warning(
                        "DATA LEAKAGE DETECTED in train: features %s correlate > 0.99 "
                        "with target '%s' and were removed.", leaky_features, target_col,
                    )
                    X_train = X_train.drop(columns=leaky_features)
                    X_test = X_test.drop(columns=leaky_features)
                    X = X.drop(columns=leaky_features)
                    available_features = [name for name in available_features if name not in leaky_features]
                    if X_train.shape[1] == 0:
                        _logger.error("All training features were removed by the leakage guard.")
                        return {}, {}, {}, [], pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()
        except Exception as exc:
            _logger.warning("Could not run target-correlation leakage guard: %s", exc)
        
        X_train_final, y_train_final = X_train, y_train
        st.session_state.last_training_rows_before_outlier = int(len(X_train_final))
        st.session_state.last_training_rows_after_outlier = int(len(X_train_final))

        # R-1: Loại bỏ ngoại lai (Outlier Removal) - IQR Method — CHỈ trên tập
        # train, biên IQR CHỈ tính từ tập train (không dùng thống kê của test,
        # tránh rò rỉ thông tin phân bố test vào lúc huấn luyện). Tập test giữ
        # NGUYÊN 100% để đánh giá trung thực trên dữ liệu "như thật".
        if outlier_method == "iqr":
            try:
                numeric_cols_check = X_train_final.select_dtypes(include=[np.number]).columns
                if not numeric_cols_check.empty:
                    Q1 = X_train_final[numeric_cols_check].quantile(0.25)
                    Q3 = X_train_final[numeric_cols_check].quantile(0.75)
                    IQR = Q3 - Q1

                    # Xác định outlier: nằm ngoài [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
                    is_outlier = (
                        (X_train_final[numeric_cols_check] < (Q1 - 1.5 * IQR))
                        | (X_train_final[numeric_cols_check] > (Q3 + 1.5 * IQR))
                    ).any(axis=1)

                    initial_len = len(X_train_final)
                    X_train_final = X_train_final[~is_outlier]
                    y_train_final = y_train_final[~is_outlier]
                    st.session_state.last_training_rows_after_outlier = int(len(X_train_final))

                    removed_count = initial_len - len(X_train_final)
                    if removed_count > 0:
                        _logger.info("Đã loại bỏ %d mẫu ngoại lai trong TRAIN (IQR Method). Còn lại %d mẫu train.", removed_count, len(X_train_final))
                    else:
                        _logger.info("Không phát hiện mẫu ngoại lai nào trong train theo phương pháp IQR.")
            except Exception as e:
                _logger.warning("Lỗi khi loại bỏ ngoại lai: %s", str(e))

        _logger.info(
            "Kết quả chia dữ liệu thực tế: Train=%d (%.1f%%), Test=%d (%.1f%%).",
            len(X_train_final), len(X_train_final)/len(X)*100, len(X_test), len(X_test)/len(X)*100
        )
        
        # ========================================================================
        # FEATURE ENGINEERING TỰ ĐỘNG: Phát hiện và tạo features phù hợp với mọi loại dữ liệu
        # ========================================================================
        def add_engineered_features(X_df):
            """Thêm các features mới tự động phát hiện từ features hiện có - hoạt động với mọi loại dữ liệu.
            
            QUY TẮC PHÒNG CHỐNG RÒ RỈ DỮ LIỆU & TÍNH ĐÚNG ĐẮN ML:
            - Tuyệt đối không sử dụng Target, Alias (grade, final_score), hoặc Derived Targets để sinh feature.
            - Không gọi fillna(0) toàn bộ dữ liệu; các giá trị khuyết thiếu được giữ lại cho imputer trong Pipeline xử lý.
            - Bảo vệ mọi phép chia và căn bậc hai bằng epsilon (1e-6) để đảm bảo tính toán ổn định, deterministic.
            """
            X_eng = X_df.copy()
            numeric_cols = X_eng.select_dtypes(include=[np.number]).columns.tolist()
            
            # Lọc bỏ triệt để mọi cột liên quan đến target/alias/leakage
            forbidden_cols = {c.lower() for c in get_leaky_target_columns(target_col)}
            forbidden_cols.update({target_col.lower(), 'grade', 'final_score', 'xep_loai', 'diem_ky_sau', 'status', 'pass_fail'})
            safe_numeric_cols = [c for c in numeric_cols if c.lower() not in forbidden_cols]
            
            # 1. Tìm các cột có thể là điểm số (gpa, diem, mark, point, score) ngoại trừ target & aliases
            score_keywords = ['score', 'gpa', 'diem', 'mark', 'point', 'total']
            score_cols = [col for col in safe_numeric_cols 
                         if any(keyword in col.lower() for keyword in score_keywords)
                         and not any(f in col.lower() for f in ['final', 'grade', 'target', 'sau'])]
            
            # 2. Tìm các cột có thể là tỷ lệ (rate, ratio, percent, ty_le)
            rate_keywords = ['rate', 'ratio', 'percent', 'ty_le', 'attendance', 'diem_danh']
            rate_cols = [col for col in safe_numeric_cols 
                        if any(keyword in col.lower() for keyword in rate_keywords)]
            
            # 3. Tìm các cột có thể là số lượng/giờ (hour, time, so_gio, count, number)
            count_keywords = ['hour', 'time', 'so_gio', 'count', 'number', 'quantity', 'so_luong']
            count_cols = [col for col in safe_numeric_cols 
                         if any(keyword in col.lower() for keyword in count_keywords)]
            
            # 4. Tạo features từ điểm số
            if len(score_cols) >= 2:
                X_eng['_fe_sum_scores'] = X_eng[score_cols].sum(axis=1)
                X_eng['_fe_mean_scores'] = X_eng[score_cols].mean(axis=1)
                X_eng['_fe_max_scores'] = X_eng[score_cols].max(axis=1)
                X_eng['_fe_min_scores'] = X_eng[score_cols].min(axis=1)
                X_eng['_fe_std_scores'] = X_eng[score_cols].std(axis=1, ddof=0)
                
                for i, col1 in enumerate(score_cols[:3]):  # Giới hạn số lượng features tương tác
                    for col2 in score_cols[i+1:min(i+3, len(score_cols))]:
                        if col1 != col2:
                            X_eng[f'_fe_{col1}_x_{col2}'] = X_eng[col1] * X_eng[col2]
                            X_eng[f'_fe_{col1}_div_{col2}'] = X_eng[col1] / (X_eng[col2].abs() + 1e-6)
            
            # 5. Tạo features từ tỷ lệ và số lượng
            if len(rate_cols) > 0 and len(count_cols) > 0:
                for rate_col in rate_cols[:2]:
                    for count_col in count_cols[:2]:
                        X_eng[f'_fe_{rate_col}_x_{count_col}'] = X_eng[rate_col] * X_eng[count_col]
            
            # 6. Tạo polynomial features cho các cột numeric an toàn (top 3 by variance)
            if len(safe_numeric_cols) > 0:
                variances = X_eng[safe_numeric_cols].var()
                top_variance_cols = variances.nlargest(min(3, len(safe_numeric_cols))).index.tolist()
                for col in top_variance_cols:
                    X_eng[f'_fe_{col}_squared'] = X_eng[col] ** 2
                    # Căn bậc hai an toàn
                    pos_vals = np.maximum(0.0, pd.to_numeric(X_eng[col], errors='coerce'))
                    X_eng[f'_fe_{col}_sqrt'] = np.sqrt(pos_vals + 1e-6)
            
            # 7. Tương tác với điểm kỳ trước (nếu có biến dự báo hợp lệ như diem_ky_nay/ky_truoc)
            prior_keywords = ['ky_truoc', 'ky_nay', 'previous', 'prior']
            prior_cols = [col for col in safe_numeric_cols 
                          if any(keyword in col.lower() for keyword in prior_keywords)]
            if len(prior_cols) > 0 and len(score_cols) > 0:
                for p_col in prior_cols[:2]:
                    for s_col in score_cols[:2]:
                        if p_col != s_col:
                            X_eng[f'_fe_{p_col}_x_{s_col}'] = X_eng[p_col] * X_eng[s_col]
            
            # Không fillna(0) toàn bộ dữ liệu ở đây — để imputer trong Pipeline xử lý
            return X_eng
        
        # R-4 (CONFIRMED lỗi — xem app/reports/ml_correctness/REPORT.md): cột
        # _fe_* do add_engineered_features() sinh ra NẰM NGOÀI Pipeline sklearn.
        # Khi bật, các cột _fe_* lọt vào feature_cols được lưu, nhưng lúc DỰ
        # ĐOÁN (form nhập tay/Production) không có bước nào tự tính lại các cột
        # đó từ input thô — pipeline.predict() luôn lỗi "columns are missing".
        # Đã xác minh: KHÔNG có widget UI nào set 'allow_feature_engineering'
        # (grep toàn bộ app/dss không thấy nơi bật), nên đây vốn đã không bật
        # được qua luồng người dùng thật — TẠM KHÓA CỨNG tại đây (bỏ qua session_
        # state) để không ai vô tình bật lại (qua code/test) cho tới khi
        # add_engineered_features được đưa vào Pipeline bằng FunctionTransformer
        # (sửa đúng chuẩn, CHƯA làm — đây là "tắt hẳn tùy chọn" theo lựa chọn 2
        # trong yêu cầu xác minh, không phải lựa chọn 1 "đưa vào Pipeline").
        _R4_FEATURE_ENGINEERING_DISABLED = True
        if (not _R4_FEATURE_ENGINEERING_DISABLED) and st.session_state.get('allow_feature_engineering', False):
            X_train_final = add_engineered_features(X_train_final)
            X_test = add_engineered_features(X_test)
            X_train = add_engineered_features(X_train)

            # Lưu danh sách các features đã được tạo để sử dụng trong prediction
            st.session_state[f'feature_columns_{target_col}'] = X_train_final.columns.tolist()

            _logger.info("Đã thêm %d features mới từ feature engineering", len(X_train_final.columns) - len(X.columns))
        else:
            st.session_state[f'feature_columns_{target_col}'] = X_train_final.columns.tolist()
            _logger.info("Feature engineering đã bị tắt — sử dụng features gốc.")
        
        # ========================================================================
        # FEATURE SELECTION TỰ ĐỘNG: Loại bỏ features không quan trọng
        # --- NEW: Tích hợp Lựa chọn Đặc trưng ---
        features_to_train = X_train_final.columns.tolist()
        if fs_method != "none" and FS_AVAILABLE:
            _logger.info("Đang lựa chọn %d đặc trưng tốt nhất bằng %s...", k_features, fs_method)
            numeric_X_train = X_train_final.select_dtypes(include=np.number)
            if not numeric_X_train.empty:
                selected_numeric, _ = feature_selector(numeric_X_train, y_train_final, method=fs_method, k=k_features, task_type="regression")
                categorical_features_original = X_train_final.select_dtypes(exclude=np.number).columns.tolist()
                features_to_train = selected_numeric + categorical_features_original
                _logger.info("Các đặc trưng được chọn: %s", ', '.join(features_to_train))
            else:
                features_to_train = X_train_final.columns.tolist()

        # Cập nhật các tập dữ liệu với features đã chọn
        X_train_final = X_train_final[features_to_train]
        X_test = X_test[features_to_train]
        X_train = X_train[features_to_train]
        # Cập nhật lại preprocessor với features đã chuẩn bị
        numeric_features = X_train_final.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = X_train_final.select_dtypes(include=['object', 'category']).columns.tolist()
        from dss.core.data_helpers import create_shared_preprocessor  # import trễ: tránh vòng lặp import trainers<->data_helpers
        # R-2: PHẢI truyền lại scaler_type — thiếu tham số này khiến preprocessor
        # tạo lại sau bước Feature Selection luôn rơi về StandardScaler mặc định,
        # bất kể người dùng đã chọn MinMaxScaler/RobustScaler ở BƯỚC 1.
        preprocessor = create_shared_preprocessor(numeric_features, categorical_features, scaler_type=scaler_type)
        
        results, trained_pipelines = {}, {}
        failed_models = {}
        evaluation_frames = {}

        # P-4: mốc so sánh (baseline) — DummyRegressor luôn dự đoán bằng trung
        # bình tập train, để biết mô hình thật có thực sự học được gì hơn ngoài
        # "luôn đoán trung bình" hay không. Lưu dưới khóa "__baseline__"
        # (build_metrics_dataframe/pick_best_model_name đã lọc bỏ mọi khóa bắt
        # đầu bằng "__" từ trước — mốc này KHÔNG BAO GIỜ được chọn is_best/
        # Candidate/Production).
        try:
            from sklearn.dummy import DummyRegressor
            baseline_pipeline = Pipeline(steps=[
                ('preprocessor', preprocessor),
                ('model', DummyRegressor(strategy="mean")),
            ])
            baseline_pipeline.fit(X_train_final, y_train_final)
            baseline_pred = np.asarray(baseline_pipeline.predict(X_test)).flatten()
            y_test_arr = np.asarray(y_test).flatten()
            valid_baseline_mask = np.isfinite(y_test_arr) & np.isfinite(baseline_pred)
            if valid_baseline_mask.any():
                results["__baseline__"] = {
                    'RMSE': math.sqrt(mean_squared_error(y_test_arr[valid_baseline_mask], baseline_pred[valid_baseline_mask])),
                    'MAE': float(mean_absolute_error(y_test_arr[valid_baseline_mask], baseline_pred[valid_baseline_mask])),
                    'R2 Score': float(r2_score(y_test_arr[valid_baseline_mask], baseline_pred[valid_baseline_mask])),
                    'strategy': 'mean',
                }
        except Exception as e:
            _logger.warning("Không thể tính mốc baseline (DummyRegressor): %s", str(e))

        # ========================================================================
        # BƯỚC 3: HUẤN LUYỆN TỪNG MÔ HÌNH
        # ========================================================================
        for name in selected_models:
            if name not in _self.models:
                _logger.warning("Mô hình '%s' không có trong danh sách. Bỏ qua.", name)
                continue
            
            try:
                _logger.info("Đang huấn luyện: %s...", name)
                model = clone(_self.models[name])   # không fit vào estimator dùng chung (cache_resource)
                
                # Tạo pipeline: Preprocessor -> Model
                pipeline = Pipeline(
                    steps=[
                        ('preprocessor', preprocessor), 
                        ('model', model)
                    ]
                )
                
                # ====================================================================
                # SỬ DỤNG GRID SEARCH để tìm tham số tối ưu - CẢI THIỆN ĐỘ CHÍNH XÁC
                # ====================================================================
                # Nguồn DUY NHẤT cho param_grid là self.param_grids (định nghĩa trong
                # __init__) — audit 2026-09-15 (Issue ML-REG-001) đã gỡ bỏ khối ghi đè
                # trùng lặp từng nằm ở đây, xem ghi chú tại __init__.
                param_grid = tuning.select_grid(
                    full=_self.param_grids.get(name, {}),
                    compact=_self._compact_param_grids.get(name, _self.param_grids.get(name, {})),
                    n_train=len(X_train_final),
                )
                # P-5: cv_mean/cv_std của tiêu chí tối ưu (MAE, lấy từ cv_results_ tại
                # best_index_) — None nếu model không có param_grid (train trực tiếp).
                cv_mean, cv_std = None, None

                if param_grid:
                    # R-5 (POST_72H_MASTER_PRODUCTION_CLOSURE): HỢP ĐỒNG METRIC
                    # TƯỜNG MINH cho hồi quy — tuning (ở đây) và ranking cuối cùng
                    # (resolve_ranking_col() trong model_service.py) CỐ Ý dùng 2
                    # tiêu chí khác nhau, không phải sơ suất:
                    #   - Tuning: MAE (neg_mean_absolute_error) — ít nhạy ngoại lai
                    #     hơn, phù hợp để dò tham số ổn định trên nhiều fold nhỏ.
                    #   - Ranking/chọn model cuối: RMSE (PRIMARY) — phạt sai số lớn
                    #     nặng hơn, phù hợp bài toán cảnh báo sinh viên rủi ro (dự
                    #     đoán lệch 3 điểm với 1 sinh viên nguy hiểm hơn lệch 0.5
                    #     điểm với nhiều người). MAE/R2 là SECONDARY, vẫn hiển thị
                    #     song song để tham khảo.
                    #   - Cập nhật 2026-11: CHỌN model cuối theo CV MAE (cv_mean) trên
                    #     tập train khi mọi model đều có — RMSE test chỉ để báo cáo
                    #     (chọn theo test làm điểm test lạc quan). Xem resolve_ranking_col.
                    # refit=True (mặc định, đơn tiêu chí) nên KHÔNG có nhập nhằng
                    # multi-metric refit. Xem test_regression_metric_contract.py.
                    _logger.info("Đang tìm tham số tối ưu cho %s (GridSearchCV, CV=%d, scoring=MAE)...", name, cv_folds)
                    cv_strategy_reg = None
                    if group_col is not None:
                        _train_groups = df_clean.loc[X_train_final.index, group_col].to_numpy()
                        if pd.Series(_train_groups).duplicated().any():
                            # GroupKFold: các học kỳ của cùng 1 SV không rải sang cả fold train lẫn fold kiểm định.
                            cv_strategy_reg = make_group_cv_splits(
                                y_train_final, _train_groups,
                                desired_folds=tuning.effective_cv_folds(len(X_train_final), cv_folds),
                                is_classification=False,
                            )
                    if cv_strategy_reg is None:
                        cv_strategy_reg = _make_safe_cv_strategy(
                            y_train_final,
                            desired_folds=tuning.effective_cv_folds(len(X_train_final), cv_folds),
                            is_classification=False,
                        )
                    # GridSearchCV (refit=True) có ghi nhớ tham số tốt nhất — dss/core/tuning.py.
                    # neg_mean_absolute_error -> sign=-1 để cv_mean là MAE dương (dễ đọc).
                    best_pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final,
                        cv_strategy_reg, scoring="neg_mean_absolute_error", sign=-1.0,
                    )
                else:
                    # Không có tham số cần tune -> Huấn luyện trực tiếp
                    pipeline.fit(X_train_final, y_train_final)
                    best_pipeline = pipeline
                
                # ====================================================================
                # BƯỚC 4: ĐÁNH GIÁ MÔ HÌNH TRÊN TẬP TEST
                # ====================================================================
                # Dự đoán trên tập Test (chưa từng thấy trong quá trình huấn luyện)
                y_pred_test = best_pipeline.predict(X_test)

                # Dự đoán trên tập Train (chính là dữ liệu best_pipeline đã fit) để kiểm tra overfitting.
                y_pred_train = best_pipeline.predict(X_train_final)

                # ====================================================================
                # BƯỚC 5: TÍNH TOÁN CÁC METRIC CHI TIẾT
                # ====================================================================

                # *** FIX: Đảm bảo y_test và y_pred_test có cùng shape và kiểu dữ liệu ***
                y_test_clean = np.array(y_test).flatten() if hasattr(y_test, 'flatten') else np.array(y_test)
                y_pred_test_clean = np.array(y_pred_test).flatten() if hasattr(y_pred_test, 'flatten') else np.array(y_pred_test)
                y_train_clean = np.array(y_train_final).flatten() if hasattr(y_train_final, 'flatten') else np.array(y_train_final)
                y_pred_train_clean = np.array(y_pred_train).flatten() if hasattr(y_pred_train, 'flatten') else np.array(y_pred_train)
                
                # Kiểm tra và loại bỏ NaN/Inf
                valid_mask_test = np.isfinite(y_test_clean) & np.isfinite(y_pred_test_clean)
                valid_mask_train = np.isfinite(y_train_clean) & np.isfinite(y_pred_train_clean)
                
                if valid_mask_test.sum() == 0:
                    _logger.error("Không có giá trị hợp lệ để tính metrics cho mô hình '%s'", name)
                    continue
                
                y_test_valid = y_test_clean[valid_mask_test]
                y_pred_test_valid = y_pred_test_clean[valid_mask_test]
                y_train_valid = y_train_clean[valid_mask_train] if valid_mask_train.sum() > 0 else y_train_clean
                y_pred_train_valid = y_pred_train_clean[valid_mask_train] if valid_mask_train.sum() > 0 else y_pred_train_clean
                
                # RMSE (Root Mean Squared Error)
                # Công thức: sqrt(mean((y_true - y_pred)2))
                # Ý nghĩa: Căn bậc hai của trung bình bình phương sai số
                mse_test = mean_squared_error(y_test_valid, y_pred_test_valid)
                rmse_test = math.sqrt(mse_test) if mse_test >= 0 else 0.0
                
                # MAE (Mean Absolute Error)
                # Công thức: mean(|y_true - y_pred|)
                # Ý nghĩa: Trung bình giá trị tuyệt đối của sai số
                mae_test = mean_absolute_error(y_test_valid, y_pred_test_valid)
                
                # R2 Score (Coefficient of Determination)
                # Công thức: 1 - (SS_res / SS_tot)
                # SS_res = sum((y_true - y_pred)2)  # Tổng bình phương sai số
                # SS_tot = sum((y_true - y_mean)2)  # Tổng bình phương độ lệch so với trung bình
                # Ý nghĩa: Tỷ lệ phương sai của target được giải thích bởi mô hình
                try:
                    r2_test = r2_score(y_test_valid, y_pred_test_valid)
                    # Đảm bảo R2 không phải NaN hoặc Inf
                    if not np.isfinite(r2_test):
                        r2_test = 0.0
                except Exception as e:
                    _logger.warning("Không thể tính R2: %s. Đặt R2 = 0.0", e)
                    r2_test = 0.0
                
                try:
                    r2_train = r2_score(y_train_valid, y_pred_train_valid) if len(y_train_valid) > 0 else 0.0
                    if not np.isfinite(r2_train):
                        r2_train = 0.0
                except Exception:
                    r2_train = 0.0
                
                # Lưu kết quả
                results[name] = {
                    'RMSE': rmse_test,
                    'MAE': mae_test,
                    'R2 Score': r2_test,
                    'R2 Score (Train)': r2_train,
                    'MSE': mse_test,  # Thêm MSE để tham khảo
                    'Overfitting': (r2_train > 0.95 and r2_test < 0.5),
                    # P-5: cv_mean (MAE)/cv_std trên tập TRAIN qua GridSearchCV (None nếu
                    # model không có param_grid để tune).
                    'cv_mean': cv_mean,
                    'cv_std': cv_std,
                }
                trained_pipelines[name] = best_pipeline

                trained_pipelines[name] = best_pipeline
                
                # Tạo DataFrame để so sánh thực tế vs dự đoán (sử dụng dữ liệu đã làm sạch)
                evaluation_frames[name] = pd.DataFrame({
                    "Thực tế": y_test_valid,
                    "Dự đoán": y_pred_test_valid
                })
                
                _logger.info("Hoàn tất '%s': RMSE=%.4f, MAE=%.4f, R2=%.4f", name, rmse_test, mae_test, r2_test)
                
                # *** TỰ ĐỘNG LƯU MÔ HÌNH SAU KHI HUẤN LUYỆN ***
                if save_model and _warehouse is not None and _dataset_id is not None:
                    try:
                        model_metrics = {
                            'RMSE': float(rmse_test),
                            'MAE': float(mae_test),
                            'R2 Score': float(r2_test),
                            'R2 Score (Train)': float(r2_train),
                            'MSE': float(mse_test),
                            'test_size': float(test_size),
                            'n_train': len(X_train_final),
                            'n_test': len(X_test),
                        }
                        training_id, _ = _warehouse.save_model_training(
                            dataset_id=_dataset_id,
                            model_pipeline=best_pipeline,
                            model_name=name,
                            feature_cols=features_to_train,
                            target_col=target_col,
                            metrics=model_metrics,
                            data_source_type=data_source_type or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
                            split_strategy=split_strategy,
                            prediction_horizon="next_semester",
                        )
                        _logger.info("Mô hình đã được lưu tự động (ID: %s)", training_id)
                    except Exception as e:
                        _logger.warning("Không thể lưu mô hình tự động: %s", str(e))
                
                if r2_test >= 0.80:
                    _logger.info("ĐẠT MỤC TIÊU! R2 = %.2f%% >= 80%%", r2_test * 100)
                elif rmse_test <= 0.15:
                    _logger.info("ĐẠT MỤC TIÊU! RMSE = %.4f <= 0.15", rmse_test)
                elif r2_test >= 0.75:
                    _logger.info("Gần đạt mục tiêu: R2 = %.2f%%", r2_test * 100)
                elif r2_test < 0:
                    _logger.warning("Mô hình không hiệu quả: R2 = %.2f%%", r2_test * 100)
                else:
                    _logger.warning("Chưa đạt mục tiêu: R2 = %.2f%% < 80%%", r2_test * 100)
                
            except Exception as e:
                _logger.error("Lỗi khi huấn luyện mô hình '%s': %s", name, str(e), exc_info=True)
                failed_models[name] = str(e)
        
        # ========================================================================
        # XÂY DỰNG MÔ HÌNH KẾT HỢP (ENSEMBLE) THEO CHIẾN LƯỢC
        # ========================================================================
        # Kiểm tra xem có yêu cầu tạo ensemble không
        need_ensemble = "Kết hợp" in training_strategy and len(results) >= 2
        
        if need_ensemble:
            _logger.info("Đang kết hợp các mô hình để tạo ra dự đoán chung (Ensemble)...")
            try:
                from sklearn.ensemble import VotingRegressor, StackingRegressor

                base_models = [
                    (model_name, trained_pipelines[model_name])
                    for model_name in results.keys()
                    if not str(model_name).startswith("__") and model_name in trained_pipelines
                ]

                if len(base_models) < 2:
                    raise ValueError("Cần ít nhất 2 mô hình đã train thành công để tạo Ensemble.")

                # R-3: quyết định CHỌN Voting hay Stacking PHẢI dựa trên cross_val_score
                # trên TẬP TRAIN — trước đây so sánh voting_r2/stacking_r2 tính trên
                # chính X_test/y_test, tức là dùng tập test để CHỌN mô hình, khiến chỉ
                # số test không còn là đánh giá độc lập/trung thực nữa. Tập test chỉ
                # dùng để BÁO CÁO kết quả của ensemble ĐÃ CHỌN (bên dưới), không tham
                # gia vào quyết định chọn.
                from sklearn.model_selection import cross_val_score

                ens_cv_strategy = _make_safe_cv_strategy(y_train, desired_folds=cv_folds, is_classification=False)
                # Đánh giá chọn Voting/Stacking theo fold NHÓM sinh viên khi dữ liệu nhiều dòng / SV.
                # (cv nội bộ của StackingRegressor vẫn là KFold vì nó chạy trên tập con của từng fold.)
                ens_outer_cv = ens_cv_strategy
                if group_col is not None:
                    _ens_groups = df_clean.loc[X_train.index, group_col].to_numpy()
                    if pd.Series(_ens_groups).duplicated().any():
                        ens_outer_cv = make_group_cv_splits(y_train, _ens_groups, desired_folds=cv_folds) or ens_cv_strategy

                voting_model = VotingRegressor(estimators=base_models)
                voting_cv_r2 = float(np.mean(
                    cross_val_score(voting_model, X_train, y_train, cv=ens_outer_cv, scoring="r2")
                ))
                voting_cv_r2 = voting_cv_r2 if np.isfinite(voting_cv_r2) else -np.inf
                voting_model.fit(X_train, y_train)

                ensemble_name = "Auto-Ensemble (Voting)"
                ensemble_model = voting_model

                if voting_cv_r2 < 0.80:
                    _logger.info("Thử StackingRegressor (chính xác hơn)...")
                    stacking_model = StackingRegressor(
                        estimators=base_models,
                        final_estimator=Ridge(),
                        cv=ens_cv_strategy,
                        passthrough=False,
                    )
                    stacking_cv_r2 = float(np.mean(
                        cross_val_score(stacking_model, X_train, y_train, cv=ens_outer_cv, scoring="r2")
                    ))
                    stacking_cv_r2 = stacking_cv_r2 if np.isfinite(stacking_cv_r2) else -np.inf
                    stacking_model.fit(X_train, y_train)
                    if stacking_cv_r2 > voting_cv_r2:
                        ensemble_name = "Auto-Ensemble (Stacking)"
                        ensemble_model = stacking_model

                # Ensemble ĐÃ CHỌN xong (không dùng X_test/y_test ở trên) — giờ mới
                # đánh giá trên tập test để BÁO CÁO (không ảnh hưởng lựa chọn).
                y_test_ens = np.asarray(y_test).flatten()
                y_pred_ensemble_final = np.asarray(ensemble_model.predict(X_test)).flatten()
                valid_mask_final = np.isfinite(y_test_ens) & np.isfinite(y_pred_ensemble_final)
                if valid_mask_final.sum() == 0:
                    raise ValueError("Ensemble cuối cùng không tạo được dự đoán hợp lệ.")
                y_test_final = y_test_ens[valid_mask_final]
                y_pred_final = y_pred_ensemble_final[valid_mask_final]
                # Chỉ số BÁO CÁO trên tập test của ensemble ĐÃ CHỌN (xem giải thích
                # R-3 ở trên — không dùng để chọn Voting/Stacking).
                ensemble_rmse = math.sqrt(mean_squared_error(y_test_final, y_pred_final))
                ensemble_r2 = r2_score(y_test_final, y_pred_final)
                ensemble_r2 = ensemble_r2 if np.isfinite(ensemble_r2) else 0.0

                y_train_pred_ensemble = np.asarray(ensemble_model.predict(X_train)).flatten()
                y_train_ens = np.asarray(y_train).flatten()
                valid_mask_train_ens = np.isfinite(y_train_ens) & np.isfinite(y_train_pred_ensemble)
                r2_train_ens = (
                    r2_score(y_train_ens[valid_mask_train_ens], y_train_pred_ensemble[valid_mask_train_ens])
                    if valid_mask_train_ens.sum() > 0
                    else 0.0
                )
                if not np.isfinite(r2_train_ens):
                    r2_train_ens = 0.0

                results[ensemble_name] = {
                    'RMSE': float(ensemble_rmse),
                    'MAE': float(mean_absolute_error(y_test_final, y_pred_final)),
                    'R2 Score': float(ensemble_r2),
                    'R2 Score (Train)': float(r2_train_ens),
                    'MSE': float(ensemble_rmse ** 2),
                    'test_size': float(test_size),
                    'n_train': len(X_train_final),
                    'n_test': len(X_test),
                }

                if save_model and _warehouse is not None and _dataset_id is not None:
                    try:
                        training_id, _ = _warehouse.save_model_training(
                            dataset_id=_dataset_id,
                            model_pipeline=ensemble_model,
                            model_name=ensemble_name,
                            feature_cols=features_to_train,
                            target_col=target_col,
                            metrics=results[ensemble_name],
                            data_source_type=data_source_type or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
                            split_strategy=split_strategy,
                            prediction_horizon="next_semester",
                        )
                        _logger.info("Mô hình Ensemble đã lưu vào Kho (ID: %s)", training_id)
                    except Exception as e:
                        _logger.warning("Không thể lưu mô hình Ensemble: %s", str(e))
                trained_pipelines[ensemble_name] = ensemble_model

                evaluation_frames[ensemble_name] = pd.DataFrame({
                    "Thực tế": y_test.reset_index(drop=True),
                    "Dự đoán": pd.Series(ensemble_model.predict(X_test)).reset_index(drop=True)
                })
                _logger.info("%s: R2 = %.2f%%, RMSE = %.4f", ensemble_name, ensemble_r2 * 100, ensemble_rmse)
            except Exception as e:
                _logger.warning("Không thể tạo Auto-Ensemble: %s", str(e))
                failed_models["Khối Kết hợp (Auto-Ensemble)"] = str(e)
        
        if failed_models:
            results["__failed_models__"] = failed_models
        _logger.info("Hoàn tất huấn luyện %d mô hình.", len([k for k in results.keys() if not str(k).startswith('__')]))
        
        # *** LƯU KẾT QUẢ VÀO SESSION STATE ĐỂ TÁI SỬ DỤNG ***
        if 'regression_training_results' not in st.session_state:
            st.session_state.regression_training_results = {}
        
        training_key = f"{target_col}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.regression_training_results[training_key] = {
            'results': results,
            'pipelines': trained_pipelines,
            'evaluation_frames': evaluation_frames,
            'feature_cols': features_to_train,
            'target_col': target_col,
            'test_size': test_size,
            'timestamp': datetime.now().isoformat()
        }
        
        return results, trained_pipelines, evaluation_frames, features_to_train, X_test, y_test, X_train_final


class DataPreprocessor:
    """Quản lý việc xử lý và phân tích dữ liệu đầu vào."""

    def __init__(self):
        self.feature_metadata = {}
        # *** NÂNG CẤP: Pipeline xử lý cho cột số (numeric) ***
        self.numeric_transformer = Pipeline(steps=[
            ('imputer', KNNImputer(n_neighbors=5)),  # Dùng KNNImputer để điền giá trị thiếu
            ('scaler', StandardScaler()) # Chuẩn hóa dữ liệu (đưa về cùng thang đo)
        ])
        # *** NÂNG CẤP: Pipeline xử lý cho cột phân loại (categorical) ***
        self.categorical_transformer = Pipeline(steps=[
            # Dùng SimpleImputer
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
        ])
        self.preprocessor = None

    def create_preprocessor(self, numeric_features, categorical_features):
        """Tạo một ColumnTransformer để áp dụng các pipeline xử lý khác nhau cho các loại cột khác nhau."""
        if ColumnTransformer is None:
            raise ImportError(
                "ColumnTransformer không khả dụng. Vui lòng cập nhật scikit-learn >= 0.20 để sử dụng tính năng này.")
        transformers = []
        if numeric_features:
            transformers.append(
                ('num', self.numeric_transformer, numeric_features))
        if categorical_features:
            transformers.append(
                ('cat', self.categorical_transformer, categorical_features))

        self.preprocessor = ColumnTransformer(
            transformers=transformers,
            remainder='passthrough'  # Giữ các cột không được xử lý
        )
        return self.preprocessor

    def fit_transform(self, df):
        """Hàm để fit và transform toàn bộ DataFrame."""
        numeric_features = df.select_dtypes(
            include=[np.number]).columns.tolist()
        categorical_features = df.select_dtypes(
            include=['object', 'category']).columns.tolist()
        # Bỏ các cột ID/Name khỏi preprocessor
        numeric_features = [
            col for col in numeric_features if 'id' not in col and 'name' not in col]
        categorical_features = [
            col for col in categorical_features if 'id' not in col and 'name' not in col]

        preprocessor = self.create_preprocessor(
            numeric_features, categorical_features)
        return preprocessor.fit_transform(df)

    def analyze_column(self, col_data, col_name):
        """Phân tích một cột dữ liệu để lấy các thông tin cơ bản (metadata)."""
        metadata = {'name': col_name, 'type': str(col_data.dtype)}
        if pd.api.types.is_numeric_dtype(col_data):
            metadata['type'] = 'numeric'
            metadata['missing'] = col_data.isnull().sum()
            metadata['mean'] = col_data.mean()
            metadata['std'] = col_data.std()
            metadata['min'] = col_data.min()
            metadata['max'] = col_data.max()
            metadata['is_target_reg'] = 'score' in col_name.lower(
            ) or 'gpa' in col_name.lower()
            metadata['is_target_clf'] = False
        elif pd.api.types.is_object_dtype(col_data) or pd.api.types.is_categorical_dtype(col_data):
            metadata['type'] = 'categorical'
            metadata['missing'] = col_data.isnull().sum()
            metadata['unique'] = col_data.nunique()
            metadata['values'] = col_data.unique().tolist()
            # Tự động phát hiện cột xếp loại (target cho classification)
            if 5 < metadata['unique'] < 15:  # Giả định cột có 5-15 giá trị duy nhất
                metadata['is_target_clf'] = False  # Giảm khả năng chọn nhầm
            else:
                metadata['is_target_clf'] = 'grade' in col_name.lower(
                ) or 'xep_loai' in col_name.lower()
            metadata['is_target_reg'] = False
        else:
            metadata['type'] = 'other'
            metadata['missing'] = col_data.isnull().sum()
        return metadata

    def analyze_dataframe(self, df):
        """Phân tích toàn bộ các cột trong DataFrame và lưu metadata."""
        self.feature_metadata = {}
        for col in df.columns:
            self.feature_metadata[col] = self.analyze_column(df[col], col)
        return self.feature_metadata

    def handle_outliers(self, df, numeric_cols=None, method='iqr', z_threshold=3.0, iqr_factor=1.5):
        """
        XỬ LÝ OUTLIER CHUYÊN NGHIỆP - Sử dụng nhiều phương pháp:
        
        Phương pháp 1: IQR (Interquartile Range) - Phương pháp hộp (Box Plot)
        - Tính Q1 (25%), Q3 (75%), IQR = Q3 - Q1
        - Outlier: < Q1 - 1.5*IQR hoặc > Q3 + 1.5*IQR
        - Phù hợp cho dữ liệu không phân phối chuẩn
        
        Phương pháp 2: Z-Score (Standard Score)
        - Z = (x - mean) / std
        - Outlier: |Z| > threshold (thường là 3)
        - Phù hợp cho dữ liệu phân phối chuẩn
        
        Parameters:
        -----------
        df : DataFrame
            Dữ liệu cần xử lý
        numeric_cols : list, optional
            Danh sách các cột số cần xử lý. Nếu None, tự động lấy tất cả cột số
        method : str, default 'iqr'
            Phương pháp xử lý: 'iqr', 'zscore', hoặc 'both'
        z_threshold : float, default 3.0
            Ngưỡng Z-score để xác định outlier
        iqr_factor : float, default 1.5
            Hệ số IQR (thường là 1.5 hoặc 3.0)
        
        Returns:
        --------
        df_cleaned : DataFrame
            Dữ liệu đã loại bỏ outlier
        outlier_info : dict
            Thông tin về số lượng outlier đã loại bỏ
        """
        df_cleaned = df.copy()
        initial_rows = len(df_cleaned)
        
        # Tự động lấy các cột số nếu không chỉ định
        if numeric_cols is None:
            numeric_cols = df_cleaned.select_dtypes(include=[np.number]).columns.tolist()
            # Loại bỏ các cột ID
            numeric_cols = [col for col in numeric_cols if 'id' not in col.lower()]
        
        if not numeric_cols:
            _logger.warning("Không tìm thấy cột số để xử lý outlier.")
            return df_cleaned, {}
        
        outlier_info = {
            'method': method,
            'columns_processed': numeric_cols,
            'outliers_removed': {},
            'total_removed': 0
        }
        
        # Tạo mask để đánh dấu các dòng outlier
        outlier_mask = pd.Series([False] * len(df_cleaned), index=df_cleaned.index)
        
        for col in numeric_cols:
            if col not in df_cleaned.columns:
                continue
                
            col_data = df_cleaned[col].dropna()
            if len(col_data) == 0:
                continue
            
            col_outlier_mask = pd.Series([False] * len(df_cleaned), index=df_cleaned.index)
            
            # Phương pháp IQR
            if method in ['iqr', 'both']:
                Q1 = col_data.quantile(0.25)
                Q3 = col_data.quantile(0.75)
                IQR = Q3 - Q1
                
                if IQR > 0:  # Tránh chia cho 0
                    lower_bound = Q1 - iqr_factor * IQR
                    upper_bound = Q3 + iqr_factor * IQR
                    col_outlier_mask_iqr = (df_cleaned[col] < lower_bound) | (df_cleaned[col] > upper_bound)
                    col_outlier_mask = col_outlier_mask | col_outlier_mask_iqr
            
            # Phương pháp Z-Score
            if method in ['zscore', 'both']:
                mean = col_data.mean()
                std = col_data.std()
                
                if std > 0:  # Tránh chia cho 0
                    z_scores = np.abs((df_cleaned[col] - mean) / std)
                    col_outlier_mask_zscore = z_scores > z_threshold
                    col_outlier_mask = col_outlier_mask | col_outlier_mask_zscore
            
            # Cập nhật mask tổng
            outlier_mask = outlier_mask | col_outlier_mask
            outlier_info['outliers_removed'][col] = col_outlier_mask.sum()
        
        # Loại bỏ các dòng có outlier
        total_outliers = outlier_mask.sum()
        if total_outliers > 0:
            df_cleaned = df_cleaned[~outlier_mask].copy()
            outlier_info['total_removed'] = total_outliers
            _logger.info("Đã loại bỏ %d dòng outlier (%.2f%% dữ liệu). Còn lại %d dòng.", total_outliers, (total_outliers/initial_rows*100), len(df_cleaned))
        else:
            _logger.info("Không phát hiện outlier trong dữ liệu.")
        
        return df_cleaned, outlier_info
