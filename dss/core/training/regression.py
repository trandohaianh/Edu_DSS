"""Bộ huấn luyện bài toán hồi quy (dự đoán điểm)."""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.base import clone
from sklearn.ensemble import (
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GridSearchCV, train_test_split  # noqa: F401
from sklearn.pipeline import Pipeline

from dss.config import (
    LIGHTGBM_AVAILABLE,
    XGBOOST_AVAILABLE,
    lgb,
    xgb,
)
from dss.core import tuning
from dss.core.feature_utils import FS_AVAILABLE, feature_selector
from dss.core.target_utils import (
    COLUMN_ALIASES,
    LEGITIMATE_PREDICTORS,
    canonicalize_columns,
    detect_temporal_column,
    filter_leakage_features,
    get_leaky_target_columns,
    temporal_train_test_split,
)
from dss.core.training.common import (
    _logger,
)
from dss.core.utils import (
    _make_safe_cv_strategy,
    find_repeated_group_column,
    group_holdout_split,
    make_group_cv_splits,
)


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
            'Random Forest Regressor': RandomForestRegressor(n_estimators=80, random_state=42),
        }
        if XGBOOST_AVAILABLE:
            self.models['XGBoost Regressor'] = xgb.XGBRegressor(random_state=42, objective='reg:squarederror')
        if LIGHTGBM_AVAILABLE:
            self.models['LightGBM Regressor'] = lgb.LGBMRegressor(random_state=42, verbosity=-1)

        # Định nghĩa grid search parameters cho từng mô hình — ĐÂY LÀ NGUỒN DUY
        # Lưới tham số gọn để giảm thời gian tìm kiếm; số lượt kiểm định chéo
        # vẫn do cv_folds quyết định và mặc định giữ ở 5.
        self.param_grids = {
            'Linear Regression': {},  # Linear Regression không có hyperparameter cần tune
            # Lưới đầy đủ (12); dữ liệu lớn dùng self._compact_param_grids (4) — xem dss/core/tuning.py.
            'Random Forest Regressor': {
                'model__n_estimators': [100, 200],
                'model__max_depth': [10, 20, None],
                'model__min_samples_split': [2, 5],
            },
        }
        self._compact_param_grids = {
            'Random Forest Regressor': {
                'model__n_estimators': [100, 200],
                'model__max_depth': [10, None],
                'model__min_samples_split': [2],
            },
        }
        if XGBOOST_AVAILABLE:
            self.param_grids['XGBoost Regressor'] = {
                'model__n_estimators': [100, 200],
                'model__max_depth': [3, 5],
                'model__learning_rate': [0.1],
            }
        if LIGHTGBM_AVAILABLE:
            self.param_grids['LightGBM Regressor'] = {
                'model__n_estimators': [100, 200],
                'model__max_depth': [3, 5],
                'model__learning_rate': [0.1],
            }

    # Không dùng @st.cache_data: hàm gọi widget Streamlit (render_save_export_buttons, st.write, …).
    def train_and_evaluate(
        _self,
        df,
        feature_cols,
        target_col,
        selected_models,
        training_strategy="So sánh nhiều mô hình (Compare)",  # NEW: Chiến lược huấn luyện
        fs_method="none",
        k_features=20,
        test_size=0.2,
        cv_folds=5,
        save_model=True,
        outlier_method="none",  # NEW: Phương pháp loại bỏ ngoại lai
        scaler_type="StandardScaler",  # NEW: Loại scaler
        _warehouse=None,
        _dataset_id=None,
        split_strategy="random",
        time_col=None,
        data_source_type=None,
    ):
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
            return (
                {},
                {},
                {},
                [],
                pd.DataFrame(),
                pd.Series(dtype=float),
                pd.DataFrame(),
            )  # cùng 7 giá trị như các nhánh khác

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
        available_features, _removed_leaks = filter_leakage_features(
            df_clean, target_col, feature_cols, return_removed=True
        )
        if _removed_leaks:
            _logger.info("Đã loại bỏ các cột rò rỉ/alias khỏi Hồi quy (%s): %s", target_col, _removed_leaks)

        if not available_features:
            _logger.error("Lỗi: Không còn feature hợp lệ nào sau khi loại bỏ ID/Target/Aliases/Leakage!")
            return (
                {},
                {},
                {},
                [],
                pd.DataFrame(),
                pd.Series(dtype=float),
                pd.DataFrame(),
            )  # cùng 7 giá trị như các nhánh khác

        X = df_clean[available_features].copy()
        y = df_clean[target_col].copy()

        # Kiểm tra dữ liệu thiếu trong target
        if y.isnull().any():
            _logger.warning(
                "Phát hiện %d giá trị thiếu trong cột target '%s'. Đang loại bỏ...", y.isnull().sum(), target_col
            )
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
        from dss.core.data_helpers import (
            create_shared_preprocessor,  # import trễ: tránh vòng lặp import trainers<->data_helpers
        )

        preprocessor = create_shared_preprocessor(numeric_features, categorical_features, scaler_type=scaler_type)

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
                    X, y, test_size=test_size, random_state=42, shuffle=False
                )
        elif group_col is not None:
            _logger.info("Chia train/test theo nhóm '%s' (GroupShuffleSplit): mỗi SV nằm trọn 1 phía.", group_col)
            tr_pos, te_pos = group_holdout_split(len(X), df_clean.loc[X.index, group_col], test_size)
            X_train, X_test, y_train, y_test = X.iloc[tr_pos], X.iloc[te_pos], y.iloc[tr_pos], y.iloc[te_pos]
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, shuffle=True
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
                    name
                    for name in correlations[correlations > 0.99].index.tolist()
                    if str(name).lower() not in protected
                ]
                if leaky_features:
                    _logger.warning(
                        "DATA LEAKAGE DETECTED in train: features %s correlate > 0.99 "
                        "with target '%s' and were removed.",
                        leaky_features,
                        target_col,
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
        st.session_state.last_training_rows_before_outlier = len(X_train_final)
        st.session_state.last_training_rows_after_outlier = len(X_train_final)

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
                    st.session_state.last_training_rows_after_outlier = len(X_train_final)

                    removed_count = initial_len - len(X_train_final)
                    if removed_count > 0:
                        _logger.info(
                            "Đã loại bỏ %d mẫu ngoại lai trong TRAIN (IQR Method). Còn lại %d mẫu train.",
                            removed_count,
                            len(X_train_final),
                        )
                    else:
                        _logger.info("Không phát hiện mẫu ngoại lai nào trong train theo phương pháp IQR.")
            except Exception as e:
                _logger.warning("Lỗi khi loại bỏ ngoại lai: %s", str(e))

        _logger.info(
            "Kết quả chia dữ liệu thực tế: Train=%d (%.1f%%), Test=%d (%.1f%%).",
            len(X_train_final),
            len(X_train_final) / len(X) * 100,
            len(X_test),
            len(X_test) / len(X) * 100,
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
            forbidden_cols.update(
                {target_col.lower(), 'grade', 'final_score', 'xep_loai', 'diem_ky_sau', 'status', 'pass_fail'}
            )
            safe_numeric_cols = [c for c in numeric_cols if c.lower() not in forbidden_cols]

            # 1. Tìm các cột có thể là điểm số (gpa, diem, mark, point, score) ngoại trừ target & aliases
            score_keywords = ['score', 'gpa', 'diem', 'mark', 'point', 'total']
            score_cols = [
                col
                for col in safe_numeric_cols
                if any(keyword in col.lower() for keyword in score_keywords)
                and not any(f in col.lower() for f in ['final', 'grade', 'target', 'sau'])
            ]

            # 2. Tìm các cột có thể là tỷ lệ (rate, ratio, percent, ty_le)
            rate_keywords = ['rate', 'ratio', 'percent', 'ty_le', 'attendance', 'diem_danh']
            rate_cols = [col for col in safe_numeric_cols if any(keyword in col.lower() for keyword in rate_keywords)]

            # 3. Tìm các cột có thể là số lượng/giờ (hour, time, so_gio, count, number)
            count_keywords = ['hour', 'time', 'so_gio', 'count', 'number', 'quantity', 'so_luong']
            count_cols = [col for col in safe_numeric_cols if any(keyword in col.lower() for keyword in count_keywords)]

            # 4. Tạo features từ điểm số
            if len(score_cols) >= 2:
                X_eng['_fe_sum_scores'] = X_eng[score_cols].sum(axis=1)
                X_eng['_fe_mean_scores'] = X_eng[score_cols].mean(axis=1)
                X_eng['_fe_max_scores'] = X_eng[score_cols].max(axis=1)
                X_eng['_fe_min_scores'] = X_eng[score_cols].min(axis=1)
                X_eng['_fe_std_scores'] = X_eng[score_cols].std(axis=1, ddof=0)

                for i, col1 in enumerate(score_cols[:3]):  # Giới hạn số lượng features tương tác
                    for col2 in score_cols[i + 1 : min(i + 3, len(score_cols))]:
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
            prior_cols = [col for col in safe_numeric_cols if any(keyword in col.lower() for keyword in prior_keywords)]
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
                selected_numeric, _ = feature_selector(
                    numeric_X_train, y_train_final, method=fs_method, k=k_features, task_type="regression"
                )
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
        from dss.core.data_helpers import (
            create_shared_preprocessor,  # import trễ: tránh vòng lặp import trainers<->data_helpers
        )

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

            baseline_pipeline = Pipeline(
                steps=[
                    ('preprocessor', preprocessor),
                    ('model', DummyRegressor(strategy="mean")),
                ]
            )
            baseline_pipeline.fit(X_train_final, y_train_final)
            baseline_pred = np.asarray(baseline_pipeline.predict(X_test)).flatten()
            y_test_arr = np.asarray(y_test).flatten()
            valid_baseline_mask = np.isfinite(y_test_arr) & np.isfinite(baseline_pred)
            if valid_baseline_mask.any():
                results["__baseline__"] = {
                    'RMSE': math.sqrt(
                        mean_squared_error(y_test_arr[valid_baseline_mask], baseline_pred[valid_baseline_mask])
                    ),
                    'MAE': float(
                        mean_absolute_error(y_test_arr[valid_baseline_mask], baseline_pred[valid_baseline_mask])
                    ),
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
                model = clone(_self.models[name])  # không fit vào estimator dùng chung (cache_resource)

                # Tạo pipeline: Preprocessor -> Model
                pipeline = Pipeline(steps=[('preprocessor', preprocessor), ('model', model)])

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
                                y_train_final,
                                _train_groups,
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
                        name,
                        pipeline,
                        param_grid,
                        X_train_final,
                        y_train_final,
                        cv_strategy_reg,
                        scoring="neg_mean_absolute_error",
                        sign=-1.0,
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
                y_pred_test_clean = (
                    np.array(y_pred_test).flatten() if hasattr(y_pred_test, 'flatten') else np.array(y_pred_test)
                )
                y_train_clean = (
                    np.array(y_train_final).flatten() if hasattr(y_train_final, 'flatten') else np.array(y_train_final)
                )
                y_pred_train_clean = (
                    np.array(y_pred_train).flatten() if hasattr(y_pred_train, 'flatten') else np.array(y_pred_train)
                )

                # Kiểm tra và loại bỏ NaN/Inf
                valid_mask_test = np.isfinite(y_test_clean) & np.isfinite(y_pred_test_clean)
                valid_mask_train = np.isfinite(y_train_clean) & np.isfinite(y_pred_train_clean)

                if valid_mask_test.sum() == 0:
                    _logger.error("Không có giá trị hợp lệ để tính metrics cho mô hình '%s'", name)
                    continue

                y_test_valid = y_test_clean[valid_mask_test]
                y_pred_test_valid = y_pred_test_clean[valid_mask_test]
                y_train_valid = y_train_clean[valid_mask_train] if valid_mask_train.sum() > 0 else y_train_clean
                y_pred_train_valid = (
                    y_pred_train_clean[valid_mask_train] if valid_mask_train.sum() > 0 else y_pred_train_clean
                )

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
                evaluation_frames[name] = pd.DataFrame({"Thực tế": y_test_valid, "Dự đoán": y_pred_test_valid})

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
                            data_source_type=data_source_type
                            or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
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
                from sklearn.ensemble import StackingRegressor, VotingRegressor

                base_models = [
                    (model_name, trained_pipelines[model_name])
                    for model_name in results
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
                        ens_outer_cv = (
                            make_group_cv_splits(y_train, _ens_groups, desired_folds=cv_folds) or ens_cv_strategy
                        )

                voting_model = VotingRegressor(estimators=base_models)
                voting_cv_r2 = float(
                    np.mean(cross_val_score(voting_model, X_train, y_train, cv=ens_outer_cv, scoring="r2"))
                )
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
                    stacking_cv_r2 = float(
                        np.mean(cross_val_score(stacking_model, X_train, y_train, cv=ens_outer_cv, scoring="r2"))
                    )
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
                    'MSE': float(ensemble_rmse**2),
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
                            data_source_type=data_source_type
                            or getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
                            split_strategy=split_strategy,
                            prediction_horizon="next_semester",
                        )
                        _logger.info("Mô hình Ensemble đã lưu vào Kho (ID: %s)", training_id)
                    except Exception as e:
                        _logger.warning("Không thể lưu mô hình Ensemble: %s", str(e))
                trained_pipelines[ensemble_name] = ensemble_model

                evaluation_frames[ensemble_name] = pd.DataFrame(
                    {
                        "Thực tế": y_test.reset_index(drop=True),
                        "Dự đoán": pd.Series(ensemble_model.predict(X_test)).reset_index(drop=True),
                    }
                )
                _logger.info("%s: R2 = %.2f%%, RMSE = %.4f", ensemble_name, ensemble_r2 * 100, ensemble_rmse)
            except Exception as e:
                _logger.warning("Không thể tạo Auto-Ensemble: %s", str(e))
                failed_models["Khối Kết hợp (Auto-Ensemble)"] = str(e)

        if failed_models:
            results["__failed_models__"] = failed_models
        _logger.info("Hoàn tất huấn luyện %d mô hình.", len([k for k in results if not str(k).startswith('__')]))

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
            'timestamp': datetime.now().isoformat(),
        }

        return results, trained_pipelines, evaluation_frames, features_to_train, X_test, y_test, X_train_final
