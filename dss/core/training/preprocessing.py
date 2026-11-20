"""Tiền xử lý dữ liệu dùng chung cho EDA và huấn luyện."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import KNNImputer, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from dss.core.training.common import _logger


class DataPreprocessor:
    """Quản lý việc xử lý và phân tích dữ liệu đầu vào."""

    def __init__(self):
        self.feature_metadata = {}
        # *** NÂNG CẤP: Pipeline xử lý cho cột số (numeric) ***
        self.numeric_transformer = Pipeline(
            steps=[
                ('imputer', KNNImputer(n_neighbors=5)),  # Dùng KNNImputer để điền giá trị thiếu
                ('scaler', StandardScaler()),  # Chuẩn hóa dữ liệu (đưa về cùng thang đo)
            ]
        )
        # *** NÂNG CẤP: Pipeline xử lý cho cột phân loại (categorical) ***
        self.categorical_transformer = Pipeline(
            steps=[
                # Dùng SimpleImputer
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ]
        )
        self.preprocessor = None

    def create_preprocessor(self, numeric_features, categorical_features):
        """Tạo một ColumnTransformer để áp dụng các pipeline xử lý khác nhau cho các loại cột khác nhau."""
        if ColumnTransformer is None:
            raise ImportError(
                "ColumnTransformer không khả dụng. Vui lòng cập nhật scikit-learn >= 0.20 để sử dụng tính năng này."
            )
        transformers = []
        if numeric_features:
            transformers.append(('num', self.numeric_transformer, numeric_features))
        if categorical_features:
            transformers.append(('cat', self.categorical_transformer, categorical_features))

        self.preprocessor = ColumnTransformer(
            transformers=transformers,
            remainder='passthrough',  # Giữ các cột không được xử lý
        )
        return self.preprocessor

    def fit_transform(self, df):
        """Hàm để fit và transform toàn bộ DataFrame."""
        numeric_features = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = df.select_dtypes(include=['object', 'category']).columns.tolist()
        # Bỏ các cột ID/Name khỏi preprocessor
        numeric_features = [col for col in numeric_features if 'id' not in col and 'name' not in col]
        categorical_features = [col for col in categorical_features if 'id' not in col and 'name' not in col]

        preprocessor = self.create_preprocessor(numeric_features, categorical_features)
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
            metadata['is_target_reg'] = 'score' in col_name.lower() or 'gpa' in col_name.lower()
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
                metadata['is_target_clf'] = 'grade' in col_name.lower() or 'xep_loai' in col_name.lower()
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

        outlier_info = {'method': method, 'columns_processed': numeric_cols, 'outliers_removed': {}, 'total_removed': 0}

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
            _logger.info(
                "Đã loại bỏ %d dòng outlier (%.2f%% dữ liệu). Còn lại %d dòng.",
                total_outliers,
                (total_outliers / initial_rows * 100),
                len(df_cleaned),
            )
        else:
            _logger.info("Không phát hiện outlier trong dữ liệu.")

        return df_cleaned, outlier_info
