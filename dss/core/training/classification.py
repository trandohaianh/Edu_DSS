"""Bộ huấn luyện bài toán phân loại (xếp loại sinh viên)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (
    RandomForestClassifier,
)
from sklearn.feature_selection import RFE, SelectKBest, mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    make_scorer,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GridSearchCV, train_test_split  # noqa: F401
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.preprocessing import LabelEncoder

from dss.config import (
    ADASYN,
    IMB_LEARN_AVAILABLE,
    LIGHTGBM_AVAILABLE,
    SMOTE,
    XGBOOST_AVAILABLE,
    BorderlineSMOTE,
    ImbPipeline,
    lgb,
    xgb,
)
from dss.core import tuning
from dss.core.target_utils import (
    COLUMN_ALIASES,
    HEURISTIC_OVERFIT_DIFF_MILD,
    HEURISTIC_OVERFIT_DIFF_SEVERE,
    HEURISTIC_TARGET_ACCURACY,
    canonicalize_columns,
    detect_temporal_column,
    filter_leakage_features,
    temporal_train_test_split,
)
from dss.core.training.common import (
    PR_AUC_SELECTION_THRESHOLD,
    RF_CLASSIFIER_GRID_COMPACT,
    RF_CLASSIFIER_GRID_FULL,
    _logger,
    _pr_auc_macro_scorer,
    apply_class_weight_balanced,
    pr_auc_macro,
)
from dss.core.utils import (
    _normalize_labels_for_metrics,
    find_repeated_group_column,
    group_holdout_split,
    make_group_cv_splits,
)


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
                random_state=42, use_label_encoder=False, eval_metric='mlogloss'
            )
        if LIGHTGBM_AVAILABLE:
            self.models['LightGBM Classifier'] = lgb.LGBMClassifier(
                random_state=42, verbosity=-1
            )  # Thêm verbosity để tắt log

    # Không dùng @st.cache_data: hàm gọi widget Streamlit (st.write, nút lưu/xuất, …).
    def train_and_evaluate(
        _self,
        df,
        feature_cols,
        target_col,
        selected_models,
        training_strategy="So sánh nhiều mô hình (Compare)",  # NEW: Chiến lược huấn luyện
        balance_method="none",  # NEW: Cân bằng dữ liệu
        fs_method="none",  # NEW: Chọn đặc trưng
        k_features=20,  # NEW: Số đặc trưng
        test_size=0.2,  # NEW: Tỷ lệ test
        cv_folds=5,  # NEW: Số fold cross-validation
        save_model=True,  # NEW: Lưu mô hình
        _warehouse=None,  # NEW: Warehouse pipeline
        _dataset_id=None,  # NEW: Dataset ID
        split_strategy="random",
        time_col=None,
        data_source_type=None,
    ):
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
        available_features, _removed_leaks = filter_leakage_features(
            df_clean, target_col, feature_cols, return_removed=True
        )
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
        from dss.core.data_helpers import (
            create_shared_preprocessor,  # import trễ: tránh vòng lặp import trainers<->data_helpers
        )

        preprocessor = create_shared_preprocessor(numeric_features, categorical_features)

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
            _logger.error(
                "Cột mục tiêu `%s` không phù hợp cho bài toán phân loại (%d/%d lớp).",
                target_col,
                unique_classes,
                total_samples,
            )
            return {}, {}, [], [], pd.DataFrame(), pd.Series(dtype=object), pd.DataFrame()

        # Mã hóa cột target (ví dụ: 'A', 'B', 'C' -> 0, 1, 2)
        le = LabelEncoder()
        y_encoded = le.fit_transform(y)
        class_labels = le.classes_

        # Kiểm tra xem có thể thực hiện stratify không
        from collections import Counter

        class_counts = Counter(y_encoded)
        stratify_param = y_encoded if all(count >= 2 for count in class_counts.values()) else None

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
            int(old_label): int(new_label) for new_label, old_label in enumerate(train_label_encoder.classes_)
        }

        def _remap_with_unknown(arr, unknown_value=-1):
            remapped = np.array([train_label_mapping.get(int(v), unknown_value) for v in arr], dtype=int)
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
            min_class_samples - math.ceil(min_class_samples / safe_cv_for_sampling) if min_class_samples > 0 else 0
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
                        min_train_samples_per_fold,
                        balance_method,
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

        results, trained_pipelines = {}, {}  # Dùng để lưu kết quả và các pipeline đã huấn luyện
        failed_models = {}

        # P-4: mốc so sánh (baseline) — DummyClassifier đoán luôn lớp đa số, để
        # biết mô hình thật có thực sự học được gì hơn ngoài việc "đoán bừa theo
        # tỷ lệ lớp" hay không. Lưu dưới khóa "__baseline__" (build_metrics_dataframe
        # và pick_best_model_name đã lọc bỏ mọi khóa bắt đầu bằng "__" từ trước —
        # mốc này KHÔNG BAO GIỜ được chọn làm is_best/Candidate/Production).
        try:
            from sklearn.dummy import DummyClassifier

            baseline_pipeline = SklearnPipeline(
                steps=[
                    ('preprocessor', preprocessor),
                    ('model', DummyClassifier(strategy="most_frequent", random_state=42)),
                ]
            )
            baseline_pipeline.fit(X_train_final, y_train_final)
            baseline_pred_full = baseline_pipeline.predict(X_test)
            if valid_test_mask.any():
                baseline_pred = np.asarray(baseline_pred_full)[valid_test_mask]
                baseline_test_eval = y_test[valid_test_mask]
                results["__baseline__"] = {
                    'Accuracy': accuracy_score(baseline_test_eval, baseline_pred),
                    'F1 Score (Macro)': f1_score(baseline_test_eval, baseline_pred, average='macro', zero_division=0),
                    'F1 Score (Weighted)': f1_score(
                        baseline_test_eval, baseline_pred, average='weighted', zero_division=0
                    ),
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
                    elif fs_method == "rfe" and (
                        name
                        in [
                            'Random Forest Classifier',
                            'XGBoost Classifier',
                            'LightGBM Classifier',
                            'Logistic Regression (Softmax)',
                        ]
                    ):
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

                from sklearn.model_selection import StratifiedKFold

                # Dữ liệu lớn (>= tuning.LARGE_DATA_ROWS dòng train) -> tối đa 3 fold:
                # cùng độ chính xác, nhanh hơn (xem dss/core/tuning.py).
                cv_folds_eff = tuning.effective_cv_folds(len(X_train_final), cv_folds)
                # Điều chỉnh cv_folds cho class thiểu số
                safe_cv = min(cv_folds_eff, min_class_samples)

                train_groups = (
                    df_clean.loc[X_train_final.index, group_col].to_numpy() if group_col is not None else None
                )
                group_cv = (
                    make_group_cv_splits(
                        y_train_final, train_groups, desired_folds=max(2, cv_folds_eff), is_classification=True
                    )
                    if train_groups is not None and pd.Series(train_groups).duplicated().any()
                    else None
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

                    idx_train, idx_val = tts_internal(range(len(X_train_final)), test_size=0.3, random_state=42)
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
                        'average_precision'
                        if n_classes_in_train == 2
                        else make_scorer(_pr_auc_macro_scorer, response_method='predict_proba')
                    )
                    _logger.info(
                        "Lớp thiểu số chỉ có %d mẫu (< %d) nên chọn mô hình bằng PR-AUC "
                        "thay vì F1: F1 tại một ngưỡng dịch quá mạnh theo từng mẫu ở cỡ này.",
                        min_class_count,
                        PR_AUC_SELECTION_THRESHOLD,
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
                        full=RF_CLASSIFIER_GRID_FULL,
                        compact=RF_CLASSIFIER_GRID_COMPACT,
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
                        min_class_samples,
                        cv_folds_eff,
                    )
                    try:
                        pipeline.set_params(model__n_estimators=200, model__max_depth=5, model__learning_rate=0.1)
                    except Exception:
                        pass
                    pipeline.fit(X_train_final, y_train_final)
                    _logger.info(
                        "%s: Huấn luyện trực tiếp (không CV) với tham số an toàn (n_estimators=200, max_depth=5, learning_rate=0.1).",
                        name,
                    )
                elif name == 'XGBoost Classifier' and XGBOOST_AVAILABLE:
                    # P-1: đủ mẫu ở lớp nhỏ nhất (>= số fold yêu cầu) — an toàn để tối ưu
                    # bằng GridSearchCV với lưới nhỏ tương đương LightGBM.
                    param_grid = {
                        'model__n_estimators': [100, 200],
                        'model__max_depth': [3, 5],
                        'model__learning_rate': [0.1],
                    }
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                elif name == 'LightGBM Classifier' and LIGHTGBM_AVAILABLE:
                    param_grid = {
                        'model__n_estimators': [100, 200],
                        'model__max_depth': [3, 5],
                        'model__learning_rate': [0.1],
                    }
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                elif name == 'Logistic Regression (Softmax)':
                    param_grid = {'model__C': [0.1, 1.0, 10.0], 'model__solver': ['lbfgs']}
                    pipeline, cv_mean, cv_std, _ = tuning.tuned_fit(
                        name, pipeline, param_grid, X_train_final, y_train_final, cv_strategy, clf_scoring
                    )
                else:
                    # Với các mô hình khác (nếu có), train trực tiếp
                    pipeline.fit(X_train_final, y_train_final)

                # Đánh giá cuối cùng trên test set
                y_pred_full = pipeline.predict(X_test)
                if not valid_test_mask.any():
                    _logger.error("%s: Không có mẫu test hợp lệ sau khi chuẩn hóa nhãn.", name)
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
                            y_test_eval,
                            proba_eval,
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
                    _logger.warning(
                        "%s: DẤU HIỆU OVERFITTING! Train Accuracy = 100%%, Test = %.2f%%", name, accuracy * 100
                    )

                if accuracy >= 1.0:
                    # Test accuracy đạt 100% là tín hiệu hiệu năng cao bất thường/nghi ngờ rò rỉ dữ liệu,
                    # KHÔNG kết luận cứng là Overfitting.
                    suspicious_perfect_score = True
                    _logger.warning(
                        "%s: CẢNH BÁO HIỆU NĂNG CAO BẤT THƯỜNG! Test Accuracy = 100%%. Đề nghị kiểm tra rò rỉ target.",
                        name,
                    )
                elif accuracy_diff > HEURISTIC_OVERFIT_DIFF_SEVERE and train_accuracy > 0.60:
                    is_overfitting = True
                    _logger.warning(
                        "%s: DẤU HIỆU OVERFITTING (heuristic gap > %.0f%%)! Train: %.2f%%, Test: %.2f%%, Diff: %.2f%%",
                        name,
                        HEURISTIC_OVERFIT_DIFF_SEVERE * 100,
                        train_accuracy * 100,
                        accuracy * 100,
                        accuracy_diff * 100,
                    )
                elif accuracy_diff > HEURISTIC_OVERFIT_DIFF_MILD and train_accuracy > 0.60:
                    _logger.info(
                        "%s: Overfitting nhẹ (heuristic gap > %.0f%%). Train: %.2f%%, Test: %.2f%%, Diff: %.2f%%",
                        name,
                        HEURISTIC_OVERFIT_DIFF_MILD * 100,
                        train_accuracy * 100,
                        accuracy * 100,
                        accuracy_diff * 100,
                    )

                if accuracy < HEURISTIC_TARGET_ACCURACY:
                    _logger.info(
                        "%s: Độ chính xác %.2f%% < %.0f%% (ngưỡng mục tiêu dự án)",
                        name,
                        accuracy * 100,
                        HEURISTIC_TARGET_ACCURACY * 100,
                    )
                severe_underfit = accuracy <= 0.01 or (train_accuracy <= 0.20 and accuracy <= 0.20)

                if severe_underfit:
                    _logger.warning(
                        "%s: Hiệu năng quá thấp (Test Accuracy: %.2f%%, Train Accuracy: %.2f%%). Tạm loại khỏi danh sách mô hình dùng tiếp.",
                        name,
                        accuracy * 100,
                        train_accuracy * 100,
                    )
                    failed_models[name] = f"Hiệu năng quá thấp (Accuracy={accuracy:.4f}, Train={train_accuracy:.4f})"
                    continue
                # *** FIX LỖI: Tính toán labels trực tiếp từ y_test thay vì dùng toàn bộ class_labels ***
                y_test_metric, y_pred_metric, labels_in_test = _normalize_labels_for_metrics(y_test_eval, y_pred)
                report = classification_report(
                    y_test_metric,
                    y_pred_metric,
                    labels=labels_in_test,
                    target_names=labels_in_test.tolist(),
                    output_dict=True,
                    zero_division=0,
                )
                results[name] = {  # Lưu kết quả đầy đủ
                    'Accuracy': accuracy,
                    'Accuracy (Train)': train_accuracy,
                    'F1 Score (Macro)': f1_macro,
                    'PR-AUC (Macro)': pr_auc,
                    # Phân biệt YÊU CẦU và THỰC TẾ: bộ cân bằng không chạy được thì
                    # kết quả này KHÔNG phải kết quả đã cân bằng lớp, và phải nói rõ.
                    'balance_method': balance_method,
                    'balance_method_effective': (
                        'none'
                        if (sampler is None and balance_method_applied not in ('none', 'class_weight'))
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
                    'cv_std': cv_std,
                }
                trained_pipelines[name] = pipeline

                if is_overfitting:
                    _logger.warning(
                        "Mô hình '%s' bị OVERFITTING! Train: %.2f%%, Test: %.2f%%",
                        name,
                        train_accuracy * 100,
                        accuracy * 100,
                    )
                elif accuracy >= HEURISTIC_TARGET_ACCURACY and accuracy < 1.0:
                    _logger.info(
                        "ĐẠT MỤC TIÊU! Test Accuracy của '%s' = %.2f%%, Train = %.2f%%",
                        name,
                        accuracy * 100,
                        train_accuracy * 100,
                    )
                elif accuracy >= 0.75:
                    _logger.info(
                        "Mô hình '%s' gần đạt mục tiêu: Test = %.2f%%, Train = %.2f%%",
                        name,
                        accuracy * 100,
                        train_accuracy * 100,
                    )
                else:
                    _logger.warning(
                        "Chưa đạt mục tiêu: Test Accuracy của '%s' = %.2f%% < %.0f%%",
                        name,
                        accuracy * 100,
                        HEURISTIC_TARGET_ACCURACY * 100,
                    )

                _logger.info(
                    "%s hoàn tất đánh giá: Train Acc=%.2f%%, Test Acc=%.2f%%, F1 Macro=%.4f, F1 Weighted=%.4f, Overfitting=%s",
                    name,
                    train_accuracy * 100,
                    accuracy * 100,
                    f1_macro,
                    f1_weighted,
                    is_overfitting,
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
                        _ens_steps.append(
                            (
                                'feature_selection',
                                SelectKBest(mutual_info_classif, k=min(k_features, len(X.columns))),
                            )
                        )
                    elif fs_method == "rfe":
                        _ens_rf_estimator = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
                        _ens_steps.append(
                            (
                                'feature_selection',
                                RFE(estimator=_ens_rf_estimator, n_features_to_select=min(k_features, len(X.columns))),
                            )
                        )
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
                precision_macro_voting = precision_score(
                    y_test_voting_eval, y_pred_voting, average='macro', zero_division=0
                )
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
                        data_source_type=data_source_type
                        or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
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
