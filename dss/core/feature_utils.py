"""Feature selection and export helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.feature_selection import RFE, SelectFromModel, mutual_info_classif, mutual_info_regression
from sklearn.impute import KNNImputer
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder

from dss.config import OPENPYXL_AVAILABLE, XLSXWRITER_AVAILABLE
from dss.core.utils import _safe_n_splits, st_step_header

try:
    # imbalanced-learn (tùy chọn) cho SMOTE/Borderline/ADASYN
    from imblearn.over_sampling import ADASYN, SMOTE, SVMSMOTE, BorderlineSMOTE  # type: ignore

    IMBLEARN_AVAILABLE = True
except Exception:
    SMOTE = BorderlineSMOTE = SVMSMOTE = ADASYN = None
    IMBLEARN_AVAILABLE = False

# feature selection imports (sklearn)
try:
    from scipy.stats import pearsonr, pointbiserialr, spearmanr
    from sklearn.decomposition import PCA as _PCA
    from sklearn.ensemble import RandomForestClassifier as _RFC
    from sklearn.ensemble import RandomForestRegressor as _RFR
    from sklearn.feature_selection import (
        RFE,
        SelectFromModel,
        SelectKBest,
        mutual_info_classif,
        mutual_info_regression,
    )
    from sklearn.linear_model import LassoCV

    FS_AVAILABLE = True
except Exception:
    mutual_info_classif = mutual_info_regression = RFE = SelectFromModel = SelectKBest = (None, None, None, None, None)
    LassoCV = None
    _RFC = _RFR = _PCA = None
    pointbiserialr = spearmanr = pearsonr = None
    FS_AVAILABLE = False


def rf_feature_importance(X, y, task_type="classification", n_estimators=200, random_state=42):
    """Đánh giá tầm quan trọng biến bằng RandomForest (fast, interpretable).
    Trả về DataFrame gồm columns=['feature','importance'] sắp xếp giảm dần.
    - task_type: "classification" hoặc "regression"
    """
    if not FS_AVAILABLE:
        raise ImportError("Thiếu sklearn.feature_selection / RandomForest. Không thể tính RF importance.")
    try:
        if task_type == "classification":
            model = _RFC(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)
        else:
            model = _RFR(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)
        # Fit trên dữ liệu (đổi NaN thành 0 tạm thời)
        X_fit = X.fillna(0) if isinstance(X, pd.DataFrame) else X
        model.fit(X_fit, y)
        importances = model.feature_importances_
        features = X.columns.tolist() if isinstance(X, pd.DataFrame) else [f"f{i}" for i in range(X.shape[1])]
        imp_df = pd.DataFrame({"feature": features, "importance": importances})
        imp_df = imp_df.sort_values("importance", ascending=False).reset_index(drop=True)
        return imp_df, model
    except Exception:
        raise


def select_by_mutual_info(X, y, k=20, task_type="classification"):
    """SelectKBest dựa trên Mutual Information.
    - task_type: classification/regression
    - Trả về list các feature được chọn (k hoặc hết nếu thiếu)
    """
    if not FS_AVAILABLE:
        raise ImportError("sklearn.feature_selection không khả dụng.")
    try:
        # Mã hóa cột categorical (string) thành số trước — mutual_info_* yêu cầu input toàn số.
        categorical_mask = [not pd.api.types.is_numeric_dtype(X[col]) for col in X.columns]
        X_enc = X.copy()
        for col, is_cat in zip(X.columns, categorical_mask):
            if is_cat:
                X_enc[col] = LabelEncoder().fit_transform(X_enc[col].astype(str))
        if task_type == "classification":
            mi = mutual_info_classif(X_enc.fillna(0), y, discrete_features=categorical_mask)
        else:
            mi = mutual_info_regression(X_enc.fillna(0), y, discrete_features=categorical_mask)
        mi_series = pd.Series(mi, index=X.columns).sort_values(ascending=False)
        k = min(k, len(mi_series))
        return mi_series.index[:k].tolist(), mi_series
    except Exception:
        raise


def select_by_pointbiserial_or_pearson(X, y, k=20):
    """PBC: Point-Biserial correlation nếu target là binary (0/1).
    Nếu target không phải binary, dùng Pearson absolute correlation.
    Trả về top-k features.
    """
    if pointbiserialr is None:
        raise ImportError("scipy.stats.pointbiserialr không khả dụng.")
    try:
        corr_list = {}
        # detect binary
        unique_y = pd.Series(y).dropna().unique()
        is_binary = len(unique_y) == 2
        for col in X.columns:
            try:
                xi = pd.to_numeric(X[col], errors='coerce').fillna(0)
                if is_binary:
                    # ensure y numeric 0/1
                    y_num = (
                        pd.Series(y).map({unique_y[0]: 0, unique_y[1]: 1})
                        if not pd.api.types.is_numeric_dtype(pd.Series(y))
                        else pd.Series(y)
                    )
                    r, p = pointbiserialr(y_num.fillna(0), xi)
                    corr_list[col] = abs(r)
                else:
                    # Pearson
                    r = xi.corr(pd.Series(y).astype(float))
                    corr_list[col] = abs(r if not np.isnan(r) else 0.0)
            except Exception:
                corr_list[col] = 0.0
        corr_s = pd.Series(corr_list).sort_values(ascending=False)
        k = min(k, len(corr_s))
        return corr_s.index[:k].tolist(), corr_s
    except Exception:
        raise


def select_by_rfe(X, y, estimator=None, k=20, task_type="classification", step=1):
    """RFE selection: dùng estimator (nếu None -> RandomForest).
    Trả về list feature.
    """
    if RFE is None:
        raise ImportError("sklearn.feature_selection.RFE không khả dụng.")
    if estimator is None:
        estimator = (
            _RFC(n_estimators=150, random_state=42, n_jobs=-1)
            if task_type == "classification"
            else _RFR(n_estimators=150, random_state=42, n_jobs=-1)
        )
    try:
        n_features_to_select = min(k, X.shape[1])
        selector = RFE(estimator, n_features_to_select=n_features_to_select, step=step)
        selector = selector.fit(X.fillna(0), y)
        selected = [f for f, s in zip(X.columns, selector.support_) if s]
        ranking = pd.Series(selector.ranking_, index=X.columns).sort_values()
        return selected, ranking
    except Exception:
        raise


def select_by_selectfrommodel(X, y, task_type="classification", threshold="median"):
    """SC: SelectFromModel sử dụng LassoCV (regression) hoặc RandomForest (classification).
    Trả về selected features và importance Series.
    """
    if SelectFromModel is None:
        raise ImportError("SelectFromModel không khả dụng.")
    try:
        if task_type == "classification":
            base = _RFC(n_estimators=200, random_state=42, n_jobs=-1)
        else:
            safe_cv = _safe_n_splits(len(y), desired_folds=5, min_folds=2)
            base = LassoCV(cv=safe_cv, random_state=42)
        selector = SelectFromModel(base, threshold=threshold)
        selector.fit(X.fillna(0), y)
        selected = [f for f, s in zip(X.columns, selector.get_support()) if s]
        # get importances or coefficients
        try:
            importances = pd.Series(
                getattr(selector.estimator_, "feature_importances_", getattr(selector.estimator_, "coef_", [])),
                index=X.columns,
            )
        except Exception:
            importances = pd.Series(0, index=X.columns)
        importances = importances.abs().sort_values(ascending=False)
        return selected, importances
    except Exception:
        raise


def select_by_pca_loadings(X, k=20, n_components=3):
    """PC: Dùng PCA để tìm các features đóng góp lớn vào các thành phần chính.
    - Ý tưởng: tính absolute loading trung bình trên n_components đầu, chọn top-k features.
    Trả về list features và DataFrame loadings.
    """
    if _PCA is None:
        raise ImportError("sklearn.decomposition.PCA không khả dụng.")
    try:
        Xc = X.fillna(0)
        pca = _PCA(n_components=min(n_components, Xc.shape[1]))
        pca.fit(Xc)
        # components_: shape (n_components, n_features)
        loadings = pd.DataFrame(np.abs(pca.components_), columns=Xc.columns)
        mean_loading = loadings.mean(axis=0).sort_values(ascending=False)
        k = min(k, len(mean_loading))
        return mean_loading.index[:k].tolist(), mean_loading
    except Exception:
        raise


def select_by_pearson(X, y, k=20):
    """PE: Pearson Correlation - đo tương quan tuyến tính giữa features và target.
    Trả về top-k features dựa trên absolute Pearson correlation.

    Parameters:
    -----------
    X : DataFrame
        Features (đặc trưng đầu vào)
    y : Series
        Target (biến mục tiêu)
    k : int
        Số lượng features tốt nhất cần trả về

    Returns:
    --------
    tuple : (selected_features_list, correlation_series)
        - selected_features_list: Danh sách k features có correlation cao nhất
        - correlation_series: Series chứa correlation của tất cả features

    Giải thích:
    -----------
    Pearson Correlation đo mức độ tương quan tuyến tính giữa feature và target.
    Giá trị từ -1 đến 1:
    - 1: Tương quan dương hoàn hảo (tăng cùng nhau)
    - -1: Tương quan âm hoàn hảo (tăng/giảm ngược nhau)
    - 0: Không có tương quan tuyến tính
    """
    try:
        corr_list = {}  # Dictionary lưu correlation của mỗi feature
        y_series = pd.to_numeric(pd.Series(y), errors="coerce").fillna(0.0)
        y_values = y_series.to_numpy(dtype=float)

        # Target hằng số thì correlation của mọi feature coi như bằng 0.
        if y_series.nunique(dropna=False) <= 1:
            zero_series = pd.Series(0.0, index=X.columns).sort_values(ascending=False)
            k = min(k, len(zero_series))
            return zero_series.index[:k].tolist(), zero_series

        # Duyệt qua từng feature
        for col in X.columns:
            try:
                # Chuyển feature về numeric và fill NaN = 0
                xi = pd.to_numeric(X[col], errors='coerce').fillna(0.0)
                if xi.nunique(dropna=False) <= 1:
                    corr_list[col] = 0.0
                    continue
                # Dùng numpy corrcoef để giảm overhead scipy trong vòng lặp lớn.
                r = np.corrcoef(xi.to_numpy(dtype=float), y_values)[0, 1]
                # Lưu absolute correlation (bỏ dấu, chỉ quan tâm độ mạnh)
                corr_list[col] = abs(r) if not np.isnan(r) else 0.0
            except Exception:
                # Nếu có lỗi, gán correlation = 0
                corr_list[col] = 0.0

        # Chuyển thành Series và sắp xếp giảm dần
        corr_s = pd.Series(corr_list).sort_values(ascending=False)

        # Đảm bảo k không vượt quá số features có
        k = min(k, len(corr_s))

        # Trả về top-k features và toàn bộ correlation series
        return corr_s.index[:k].tolist(), corr_s
    except Exception:
        raise


def select_by_spearman(X, y, k=20):
    """SC: Spearman Correlation - đo tương quan đơn điệu (monotonic) giữa features và target.
    Không yêu cầu quan hệ tuyến tính, phù hợp cho dữ liệu có phân phối không chuẩn.
    Trả về top-k features dựa trên absolute Spearman correlation.

    Parameters:
    -----------
    X : DataFrame
        Features (đặc trưng đầu vào)
    y : Series
        Target (biến mục tiêu)
    k : int
        Số lượng features tốt nhất cần trả về

    Returns:
    --------
    tuple : (selected_features_list, correlation_series)
        - selected_features_list: Danh sách k features có correlation cao nhất
        - correlation_series: Series chứa correlation của tất cả features

    Giải thích:
    -----------
    Spearman Correlation đo mức độ tương quan đơn điệu (không nhất thiết tuyến tính).
    Khác với Pearson:
    - Pearson: Yêu cầu quan hệ tuyến tính
    - Spearman: Chỉ cần quan hệ đơn điệu (tăng hoặc giảm cùng nhau)
    Phù hợp khi dữ liệu không có phân phối chuẩn hoặc có outliers.
    """
    try:
        corr_list = {}  # Dictionary lưu correlation của mỗi feature
        y_series = pd.to_numeric(pd.Series(y), errors="coerce").fillna(0.0)
        if y_series.nunique(dropna=False) <= 1:
            zero_series = pd.Series(0.0, index=X.columns).sort_values(ascending=False)
            k = min(k, len(zero_series))
            return zero_series.index[:k].tolist(), zero_series
        y_rank = y_series.rank(method="average").to_numpy(dtype=float)

        # Duyệt qua từng feature
        for col in X.columns:
            try:
                # Chuyển feature về numeric và fill NaN = 0
                xi = pd.to_numeric(X[col], errors='coerce').fillna(0.0)
                if xi.nunique(dropna=False) <= 1:
                    corr_list[col] = 0.0
                    continue
                xi_rank = xi.rank(method="average").to_numpy(dtype=float)
                # Spearman = Pearson trên rank.
                r = np.corrcoef(xi_rank, y_rank)[0, 1]
                # Lưu absolute correlation (bỏ dấu)
                corr_list[col] = abs(r) if not np.isnan(r) else 0.0
            except Exception:
                # Nếu có lỗi, gán correlation = 0
                corr_list[col] = 0.0

        # Chuyển thành Series và sắp xếp giảm dần
        corr_s = pd.Series(corr_list).sort_values(ascending=False)

        # Đảm bảo k không vượt quá số features có
        k = min(k, len(corr_s))

        # Trả về top-k features và toàn bộ correlation series
        return corr_s.index[:k].tolist(), corr_s
    except Exception:
        raise


def calculate_all_feature_metrics(X, y, task_type="classification", k=20, n_estimators_rf=200, random_state=42):
    """Tính toán tất cả các metrics đánh giá tương quan đặc trưng cùng lúc.

    Parameters:
    -----------
    X : DataFrame
        Features (đặc trưng đầu vào)
    y : Series
        Target (biến mục tiêu)
    task_type : str
        "classification" hoặc "regression"
    k : int
        Số lượng features cho RFE
    n_estimators_rf : int
        Số cây trong Random Forest để tính importance
    random_state : int
        Random seed để đảm bảo tái lập kết quả

    Returns:
    --------
    DataFrame : Bảng chứa tất cả metrics cho mỗi feature
        Các cột: feature, MI, PE, PBC, RFE, PC, SC, RF_importance

    Metrics được tính:
    -------------------
    - MI (Mutual Information): Lượng thông tin chung giữa feature và target
    - PE (Pearson Correlation): Tương quan tuyến tính
    - PBC (Point-Biserial/Pearson): Tương quan cho binary target
    - RFE (Recursive Feature Elimination): Ranking từ RFE
    - PC (PCA Loadings): Đóng góp vào các thành phần chính
    - SC (Spearman Correlation): Tương quan đơn điệu
    - RF Importance: Tầm quan trọng từ Random Forest
    """
    # Kiểm tra thư viện có sẵn không
    if not FS_AVAILABLE:
        raise ImportError("Thiếu các thư viện cần thiết cho feature selection.")

    all_features = X.columns.tolist()  # Lấy danh sách tất cả features

    # Mã hóa các cột không phải số (categorical/string, vd. "xep_loai") thành số TRƯỚC khi
    # tính toán. Nếu không, mutual_info_classif/PCA/Pearson... bên dưới sẽ ném ValueError
    # ("could not convert string to float"), bị except nuốt và toàn bộ bảng metrics âm thầm
    # trả về 0.0000 — đánh lừa người dùng rằng feature không liên quan gì tới target.
    categorical_mask = []
    if not X.select_dtypes(exclude=[np.number]).empty:
        X = X.copy()
        for col in X.columns:
            if not pd.api.types.is_numeric_dtype(X[col]):
                X[col] = LabelEncoder().fit_transform(X[col].astype(str))
                categorical_mask.append(True)
            else:
                categorical_mask.append(False)
    else:
        categorical_mask = [False] * len(all_features)

    # ========================================================================
    # BƯỚC 1: TÍNH MI (Mutual Information) - Lượng thông tin chung giữa feature và target
    # ========================================================================
    try:
        if task_type == "classification":
            # Dùng mutual_info_classif cho classification
            mi_scores = mutual_info_classif(
                X.fillna(0), y, discrete_features=categorical_mask, random_state=random_state
            )
        else:
            # Dùng mutual_info_regression cho regression
            mi_scores = mutual_info_regression(
                X.fillna(0), y, discrete_features=categorical_mask, random_state=random_state
            )
        # Chuyển thành Series với index là tên features
        mi_series = pd.Series(mi_scores, index=all_features)
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        mi_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 2: TÍNH PE (Pearson Correlation) - Tương quan tuyến tính
    # ========================================================================
    try:
        # Gọi hàm select_by_pearson, lấy tất cả features (k=len(all_features))
        _, pe_series = select_by_pearson(X, y, k=len(all_features))
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        pe_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 3: TÍNH PBC (Point-Biserial/Pearson) - Tương quan cho binary target
    # ========================================================================
    try:
        # Gọi hàm select_by_pointbiserial_or_pearson, lấy tất cả features
        _, pbc_series = select_by_pointbiserial_or_pearson(X, y, k=len(all_features))
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        pbc_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 4: TÍNH RFE (Recursive Feature Elimination) - Ranking từ RFE
    # ========================================================================
    try:
        # Gọi hàm select_by_rfe để lấy ranking (ranking thấp = tốt hơn)
        _, rfe_ranking = select_by_rfe(X, y, k=k, task_type=task_type)
        # Chuyển ranking thành score: ranking thấp hơn = score cao hơn
        # Công thức: score = 1 / (ranking + 1) để đảo ngược (ranking 1 -> score cao nhất)
        rfe_score = pd.Series(1.0 / (rfe_ranking + 1), index=all_features)
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        rfe_score = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 5: TÍNH PC (PCA Loadings) - Đóng góp vào các thành phần chính
    # ========================================================================
    try:
        # Gọi hàm select_by_pca_loadings, dùng 3 components đầu tiên
        _, pc_series = select_by_pca_loadings(X, k=len(all_features), n_components=3)
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        pc_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 6: TÍNH SC (Spearman Correlation) - Tương quan đơn điệu
    # ========================================================================
    try:
        # Gọi hàm select_by_spearman, lấy tất cả features
        _, sc_series = select_by_spearman(X, y, k=len(all_features))
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        sc_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 7: TÍNH RF Importance - Tầm quan trọng từ Random Forest
    # ========================================================================
    try:
        # Gọi hàm rf_feature_importance để tính importance từ Random Forest
        rf_imp_df, _ = rf_feature_importance(
            X, y, task_type=task_type, n_estimators=n_estimators_rf, random_state=random_state
        )
        # Chuyển DataFrame thành Series với index là feature names
        rf_series = pd.Series(rf_imp_df.set_index('feature')['importance'])
        # Đảm bảo tất cả features có giá trị (reindex và fill 0 cho features thiếu)
        rf_series = rf_series.reindex(all_features, fill_value=0.0)
    except Exception:
        # Nếu có lỗi, gán tất cả = 0
        rf_series = pd.Series(0.0, index=all_features)

    # ========================================================================
    # BƯỚC 8: TẠO DATAFRAME TỔNG HỢP TẤT CẢ METRICS
    # ========================================================================
    metrics_df = pd.DataFrame(
        {
            'feature': all_features,  # Tên features
            'MI': mi_series.values,  # Mutual Information scores
            'PE': pe_series.values,  # Pearson Correlation scores
            'PBC': pbc_series.values,  # Point-Biserial/Pearson scores
            'RFE': rfe_score.values,  # RFE scores (đã chuyển từ ranking)
            'PC': pc_series.values,  # PCA Loadings scores
            'SC': sc_series.values,  # Spearman Correlation scores
            'RF_importance': rf_series.values,  # Random Forest Importance scores
        }
    )

    # Trả về DataFrame chứa tất cả metrics
    return metrics_df


def feature_selector(X, y, method="mi", k=20, task_type="classification", **kwargs):
    """Wrapper để gọi các phương pháp feature selection:
    method in ["mi","pe","pbc","rfe","pc","sc","rf_imp"]
    Trả về (selected_features, details_series_or_df)
    """
    method = (method or "mi").lower()
    if method == "mi":
        return select_by_mutual_info(X, y, k=k, task_type=task_type)
    if method == "pe":
        return select_by_pearson(X, y, k=k)
    if method == "pbc":
        return select_by_pointbiserial_or_pearson(X, y, k=k)
    if method == "rfe":
        return select_by_rfe(X, y, k=k, task_type=task_type, **kwargs)
    if method == "pc":
        return select_by_pca_loadings(X, k=k, n_components=kwargs.get("n_components", 3))
    if method == "sc":
        # SC có thể là Spearman hoặc SelectFromModel, ưu tiên Spearman
        try:
            return select_by_spearman(X, y, k=k)
        except Exception:
            # Nếu Spearman thất bại, fallback về SelectFromModel
            return select_by_selectfrommodel(X, y, task_type=task_type, threshold=kwargs.get("threshold", "median"))
    if method == "rf_imp":
        rf_df, _ = rf_feature_importance(
            X,
            y,
            task_type=task_type,
            n_estimators=kwargs.get("n_estimators", 200),
            random_state=kwargs.get("random_state", 42),
        )
        top_k = rf_df.head(k)
        return top_k['feature'].tolist(), pd.Series(rf_df.set_index('feature')['importance'])
    raise ValueError("Phương pháp chọn feature không hợp lệ.")


def render_feature_method_explanation():
    """Hiển thị giải thích ý nghĩa của các phương pháp đánh giá đặc trưng."""
    with st.expander("ℹ️ Tìm hiểu về các chỉ số đánh giá đặc trưng (Feature Metrics)"):
        st.markdown("""
        **1. MI (Mutual Information - Thông tin tương hỗ):**
        - **Ý nghĩa:** Đo lường mức độ phụ thuộc giữa hai biến. MI = 0 nghĩa là hai biến độc lập.
        - **Ưu điểm:** Phát hiện được cả mối quan hệ **phi tuyến tính** phức tạp (ví dụ: hình sin, hình parabol).
        - **Khi nào dùng:** Luôn nên dùng như chỉ số mặc định.
        
        **2. PE (Pearson Correlation - Tương quan tuyến tính):**
        - **Ý nghĩa:** Đo mức độ quan hệ tuyến tính (đường thẳng). Giá trị từ -1 đến 1.
        - **Ưu điểm:** Đơn giản, phổ biến.
        - **Hạn chế:** Chỉ phát hiện được quan hệ đường thẳng. Nếu dữ liệu hình chữ U, PE có thể bằng 0 dù có quan hệ chặt chẽ.
        
        **3. RFE (Recursive Feature Elimination - Loại bỏ đệ quy):**
        - **Cách làm:** Huấn luyện mô hình, loại bỏ feature yếu nhất, rồi lặp lại.
        - **Ý nghĩa:** Tìm ra tập hợp features "tinh gọn" nhất mà vẫn giữ được độ chính xác.
        - **Ưu điểm:** Rất chính xác vì dùng chính mô hình để đánh giá.
        
        **4. RF Importance (Random Forest Importance):**
        - **Ý nghĩa:** Dựa trên mô hình Rừng ngẫu nhiên để xem feature nào được dùng nhiều nhất để ra quyết định.
        - **Ưu điểm:** Mạnh mẽ, thực tế, phản ánh đúng cách mô hình "nhìn" dữ liệu.
        
        **👉 Mẹo chọn Features:**
        - **Giữ lại:** Features có MI cao hoặc RF Importance cao.
        - **Xem xét:** Features có PE cao (tương quan mạnh).
        - **Loại bỏ:** Features có tất cả các chỉ số đều thấp (gần 0).
        """)


def create_feature_metrics_scatter_plots(X, y, y_pred, task_type="classification", random_state=42):
    """Scatter plots colored by per-metric feature scores (MI, PE, PBC, RFE, PC, SC, RF)."""
    try:
        # BƯỚC 1: metrics
        metrics_df = calculate_all_feature_metrics(
            X, y, task_type=task_type, k=min(20, X.shape[1]), random_state=random_state
        )

        # BƯỚC 2: errors
        if task_type == "regression":
            errors = np.abs(y - y_pred)
        else:
            errors = (y != y_pred).astype(int)

        plot_data = pd.DataFrame(
            {
                'y_true': y.values if hasattr(y, 'values') else y,
                'y_pred': y_pred,
                'error': errors,
            }
        )

        X_numeric = X.select_dtypes(include=[np.number]).fillna(0)
        scatter_figures = {}
        metric_names = ['MI', 'PE', 'PBC', 'RFE', 'PC', 'SC', 'RF_importance']

        for metric_name in metric_names:
            if metric_name not in metrics_df.columns:
                continue

            metric_scores = metrics_df.set_index('feature')[metric_name]
            X_normalized = (X_numeric - X_numeric.min()) / (X_numeric.max() - X_numeric.min() + 1e-8)
            weights = metric_scores.reindex(X_normalized.columns).fillna(0)
            sample_scores = (X_normalized * weights).mean(axis=1).values
            plot_data[f'{metric_name}_score'] = sample_scores

            fig = px.scatter(
                plot_data,
                x='y_true',
                y='y_pred',
                color=f'{metric_name}_score',
                size='error',
                hover_data=[f'{metric_name}_score'],
                title=f'Biểu đồ phân tán: thực tế vs dự đoán (màu theo {metric_name})',
                labels={
                    'y_true': 'Giá trị thực tế',
                    'y_pred': 'Giá trị dự đoán',
                    f'{metric_name}_score': f'Điểm {metric_name}',
                },
                color_continuous_scale='Viridis',
            )

            if task_type == "regression":
                min_val = min(plot_data['y_true'].min(), plot_data['y_pred'].min())
                max_val = max(plot_data['y_true'].max(), plot_data['y_pred'].max())
                fig.add_shape(
                    type='line',
                    x0=min_val,
                    y0=min_val,
                    x1=max_val,
                    y1=max_val,
                    line=dict(color='red', dash='dash', width=2),
                )

            fig.update_layout(height=500, template='plotly_white', showlegend=True)
            scatter_figures[metric_name] = fig

        return scatter_figures, metrics_df

    except Exception as e:
        import warnings

        warnings.warn(f"Scatter plots with feature metrics failed: {e!s}")
        return {}, pd.DataFrame()


@st.cache_data(show_spinner=False)
def to_excel(df):
    """Chuyển DataFrame sang bytes file Excel (dùng cho nút tải xuống).

    Args:
        df (pd.DataFrame): DataFrame can chuyen

    Returns:
        bytes: Dữ liệu Excel dạng bytes, hoặc None nếu lỗi

    Note:
        Ưu tiên `xlsxwriter`, nếu không thì `openpyxl`. Docstring này TỪNG ghi
        "dùng @st.cache_data" nhưng decorator thực tế chưa có (phát hiện ở Phase
        8 refactor) — bytes Excel bị dựng lại từ đầu mỗi lần rerun dù dữ liệu
        không đổi. Đã thêm decorator thật.
    """
    output = BytesIO()
    if XLSXWRITER_AVAILABLE:
        engine = 'xlsxwriter'
    elif OPENPYXL_AVAILABLE:
        engine = 'openpyxl'
    else:
        st.error(
            "⚠️ Không thể tạo file Excel vì thiếu cả 'xlsxwriter' và 'openpyxl'. Vui lòng cài đặt thêm `pip install xlsxwriter openpyxl`."
        )
        return None
    try:
        with pd.ExcelWriter(output, engine=engine) as writer:
            df.to_excel(writer, index=False, sheet_name='Predictions')
        return output.getvalue()
    except Exception as exc:
        st.error(f"⚠️ Không thể tạo file Excel: {exc}")
        return None


def render_save_export_buttons(
    df_result, file_name_prefix="result", warehouse=None, key_suffix="", data_type="processed"
):
    """Tự động lưu vào Kho Dữ liệu (auto-save, không cần bấm nút) và hiển thị nút xuất Excel."""
    col_save, col_export = st.columns(2)

    # Auto-save vào Kho Dữ liệu — chỉ lưu lại khi nội dung df_result thực sự
    # thay đổi (so sánh qua hash), tránh tạo bản ghi trùng lặp ở mỗi lần rerun.
    with col_save:
        if warehouse:
            sig_key = f"_autosave_sig_{file_name_prefix}_{key_suffix}"
            id_key = f"_autosave_id_{file_name_prefix}_{key_suffix}"
            try:
                content_sig = hashlib.md5(
                    pd.util.hash_pandas_object(df_result, index=True).values.tobytes()
                ).hexdigest()
            except Exception:
                content_sig = f"{df_result.shape}_{list(df_result.columns)}"

            if st.session_state.get(sig_key) != content_sig:
                try:
                    dataset_name = f"{file_name_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    dataset_id, meta = warehouse.save_dataset(
                        df_result,
                        dataset_name=dataset_name,
                        description=f"Dữ liệu được tự động lưu từ chức năng {file_name_prefix}",
                        data_type=data_type,
                    )
                    st.session_state[sig_key] = content_sig
                    st.session_state[id_key] = dataset_id
                    st.success(f"✅ Đã tự động lưu vào Kho Dữ liệu! ID: `{dataset_id}`")
                except Exception as e:
                    st.error(f"❌ Lỗi khi tự động lưu vào kho: {e}")
            else:
                st.caption(f"✅ Đã tự động lưu vào Kho Dữ liệu (ID: `{st.session_state.get(id_key)}`).")
        else:
            st.caption("⚠️ Kho dữ liệu chưa được khởi tạo để lưu trữ.")

    # Nút Xuất Excel
    with col_export:
        excel_data = to_excel(df_result)
        if excel_data:
            st.download_button(
                label="📥 Tải xuống Excel (.xlsx)",
                data=excel_data,
                file_name=f"{file_name_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.ms-excel",
                key=f"btn_download_{file_name_prefix}_{key_suffix}",
            )


def create_detailed_evaluation_excel(results, evaluation_frames, target_col, model_name=None):
    """Tạo file Excel đánh giá chi tiết với metrics và so sánh thực tế vs dự đoán.

    Args:
        results (dict): Metrics theo từng mô hình
        evaluation_frames (dict): DataFrame so sánh thực tế vs dự đoán
        target_col (str): Tên cột target
        model_name (str, optional): Tên mô hình cụ thể (None = tất cả)

    Returns:
        bytes: Du lieu Excel hoac None neu loi
    """
    output = BytesIO()
    if not XLSXWRITER_AVAILABLE and not OPENPYXL_AVAILABLE:
        st.error("⚠️ Không thể tạo file Excel vì thiếu cả 'xlsxwriter' và 'openpyxl'.")
        return None

    engine = 'xlsxwriter' if XLSXWRITER_AVAILABLE else 'openpyxl'

    try:
        with pd.ExcelWriter(output, engine=engine) as writer:
            # Sheet 1: Tổng quan Metrics
            metrics_data = []
            for name, metrics in results.items():
                if model_name is None or name == model_name:
                    metrics_data.append(
                        {
                            'Mô hình': name,
                            'RMSE': metrics.get('RMSE', 0),
                            'MAE': metrics.get('MAE', 0),
                            'R2 Score (Test)': metrics.get('R2 Score', 0),
                            'R2 Score (Train)': metrics.get('R2 Score (Train)', 0),
                            'MSE': metrics.get('MSE', 0),
                            'Test Size': metrics.get('test_size', 'N/A'),
                            'Số mẫu Train': metrics.get('n_train', 'N/A'),
                            'Số mẫu Test': metrics.get('n_test', 'N/A'),
                            'Số mẫu Validation': metrics.get('n_val', 'N/A'),
                        }
                    )

            if metrics_data:
                metrics_df = pd.DataFrame(metrics_data)
                metrics_df.to_excel(writer, index=False, sheet_name='Tổng quan Metrics')

            # Sheet 2-N: So sánh Thực tế vs Dự đoán cho từng mô hình
            for name, eval_df in evaluation_frames.items():
                if model_name is None or name == model_name:
                    if eval_df is not None and not eval_df.empty:
                        # Tính toán thêm các metrics chi tiết
                        eval_df = eval_df.copy()
                        eval_df['Sai số'] = eval_df['Thực tế'] - eval_df['Dự đoán']
                        eval_df['Sai số tuyệt đối'] = abs(eval_df['Sai số'])
                        eval_df['Sai số phần trăm'] = (eval_df['Sai số'] / (eval_df['Thực tế'] + 1e-6)) * 100

                        # Sắp xếp theo sai số tuyệt đối (lớn nhất trước)
                        eval_df = eval_df.sort_values('Sai số tuyệt đối', ascending=False)

                        sheet_name = name[:31] if len(name) <= 31 else name[:28] + '...'  # Excel sheet name limit
                        eval_df.to_excel(writer, index=False, sheet_name=sheet_name)

        return output.getvalue()
    except Exception as exc:
        st.error(f"⚠️ Không thể tạo file Excel đánh giá: {exc}")
        import traceback

        st.code(traceback.format_exc())
        return None


def fill_missing_values(df_input):
    """Dien gia tri thieu: cot so = KNNImputer, cot chuoi/category = mode."""
    if df_input is None or df_input.empty:
        return df_input
    df_filled = df_input.copy()
    numeric_cols = df_filled.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        numeric_data = df_filled[numeric_cols].copy()
        if len(df_filled) >= 2:
            n_neighbors = max(1, min(5, len(df_filled) - 1))
            knn_imputer = KNNImputer(n_neighbors=n_neighbors, weights="distance")
            imputed_numeric = knn_imputer.fit_transform(numeric_data)
            df_filled[numeric_cols] = pd.DataFrame(imputed_numeric, columns=numeric_cols, index=df_filled.index)
        else:
            # Fallback cho dữ liệu quá ít mẫu để KNN hoạt động ổn định.
            df_filled[numeric_cols] = numeric_data.fillna(numeric_data.mean())

        # Trường hợp cột số bị thiếu hoàn toàn có thể còn NaN sau KNN.
        if df_filled[numeric_cols].isnull().values.any():
            df_filled[numeric_cols] = df_filled[numeric_cols].fillna(df_filled[numeric_cols].median()).fillna(0)
    categorical_cols = df_filled.select_dtypes(include=['object', 'category']).columns
    if len(categorical_cols) > 0:
        mode_df = df_filled[categorical_cols].mode(dropna=True)
        if not mode_df.empty:
            df_filled[categorical_cols] = df_filled[categorical_cols].fillna(mode_df.iloc[0])
        else:
            df_filled[categorical_cols] = df_filled[categorical_cols].fillna('')
    return df_filled


def render_feature_analysis(df, feature_cols, target_col, task_type="classification"):
    """Hien thi phan tich chi tiet feature so voi target (correlation, importance)."""
    if not feature_cols:
        st.info("Chưa chọn feature nào để phân tích.")
        return
    if target_col not in df.columns:
        st.warning("Không tìm thấy cột target trong dữ liệu để phân tích.")
        return

    st.markdown("### 📊 Phân tích Chi tiết Từng Feature")

    target_series = df[target_col]
    if task_type == "classification":
        try:
            target_encoded = LabelEncoder().fit_transform(target_series.astype(str).fillna("Unknown"))
        except Exception:
            target_encoded = None
    else:
        target_encoded = (
            target_series
            if pd.api.types.is_numeric_dtype(target_series)
            else pd.to_numeric(target_series, errors='coerce')
        )

    # Tính feature importance nếu có thể
    feature_importance = {}
    try:
        if task_type == "regression" and pd.api.types.is_numeric_dtype(target_series):
            from sklearn.ensemble import RandomForestRegressor

            X_temp = df[feature_cols].select_dtypes(include=[np.number]).fillna(0)
            y_temp = target_series.fillna(target_series.mean())
            if len(X_temp.columns) > 0 and len(X_temp) > 10:
                rf_temp = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
                rf_temp.fit(X_temp, y_temp)
                for idx, feat in enumerate(X_temp.columns):
                    feature_importance[feat] = rf_temp.feature_importances_[idx]
        elif task_type == "classification":
            from sklearn.ensemble import RandomForestClassifier

            X_temp = df[feature_cols].select_dtypes(include=[np.number]).fillna(0)
            if len(X_temp.columns) > 0 and len(X_temp) > 10:
                rf_temp = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
                rf_temp.fit(X_temp, target_encoded)
                for idx, feat in enumerate(X_temp.columns):
                    feature_importance[feat] = rf_temp.feature_importances_[idx]
    except Exception:
        pass

    summary_rows = []
    for col in feature_cols:
        if col not in df.columns:
            continue
        col_data = df[col]

        # Xác định loại dữ liệu
        if pd.api.types.is_numeric_dtype(col_data):
            data_type = "Numeric (Số)"
            data_type_detail = f"Kiểu: {col_data.dtype!s}"
            why_selected = "Feature số có thể biểu diễn mối quan hệ tuyến tính và phi tuyến với target"
        elif pd.api.types.is_object_dtype(col_data) or pd.api.types.is_categorical_dtype(col_data):
            data_type = "Categorical (Phân loại)"
            data_type_detail = f"Kiểu: {col_data.dtype!s}, {col_data.nunique()} giá trị duy nhất"
            why_selected = "Feature phân loại giúp mô hình phân biệt các nhóm khác nhau"
        else:
            data_type = "Other"
            data_type_detail = f"Kiểu: {col_data.dtype!s}"
            why_selected = "Cần xử lý trước khi sử dụng"

        missing_pct = col_data.isna().mean() * 100

        # Tính correlation
        corr = np.nan
        corr_strength = "N/A"
        try:
            if pd.api.types.is_numeric_dtype(col_data) and isinstance(target_encoded, np.ndarray):
                valid_mask = ~pd.isna(col_data) & ~pd.isna(target_encoded)
                if valid_mask.sum() > 2:
                    corr = np.corrcoef(col_data[valid_mask], target_encoded[valid_mask])[0, 1]
                    if abs(corr) > 0.7:
                        corr_strength = "Rất mạnh"
                    elif abs(corr) > 0.5:
                        corr_strength = "Mạnh"
                    elif abs(corr) > 0.3:
                        corr_strength = "Trung bình"
                    elif abs(corr) > 0.1:
                        corr_strength = "Yếu"
                    else:
                        corr_strength = "Rất yếu"
        except Exception:
            corr = np.nan

        # Lấy importance
        importance_val = feature_importance.get(col, np.nan)
        importance_pct = f"{importance_val * 100:.2f}%" if not np.isnan(importance_val) else "N/A"
        if not np.isnan(importance_val):
            if importance_val > 0.15:
                importance_level = "Rất cao"
            elif importance_val > 0.10:
                importance_level = "Cao"
            elif importance_val > 0.05:
                importance_level = "Trung bình"
            else:
                importance_level = "Thấp"
        else:
            importance_level = "N/A"

        # Thống kê mô tả
        if pd.api.types.is_numeric_dtype(col_data):
            stats_desc = f"Min: {col_data.min():.2f}, Max: {col_data.max():.2f}, Mean: {col_data.mean():.2f}"
        else:
            top_values = col_data.value_counts().head(3)
            stats_desc = f"Top 3: {', '.join([f'{k}({v})' for k, v in top_values.items()])}"

        summary_rows.append(
            {
                "Feature": col,
                "Loại dữ liệu": data_type,
                "Chi tiết": data_type_detail,
                "Lý do chọn": why_selected,
                "Thiếu (%)": f"{missing_pct:.1f}",
                "Thống kê": stats_desc,
                "Tương quan": f"{corr:.3f}" if not np.isnan(corr) else "N/A",
                "Mức độ tương quan": corr_strength,
                "Importance (%)": importance_pct,
                "Mức ảnh hưởng": importance_level,
            }
        )

    if not summary_rows:
        st.info("Không đủ dữ liệu để phân tích các feature đã chọn.")
        return

    # Hiển thị bảng chi tiết
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, width="stretch", hide_index=True, height=400)

    # Giải thích chi tiết
    st.markdown("""
    #### Giải thích chi tiết

    **1. Loại dữ liệu:** Numeric vs Categorical; categorical can encode (OneHotEncoder).

    **2. Lý do chọn:** Feature được chọn theo khả năng dự đoán target; so với phân loại.

    **3. Mức ảnh hưởng:** Tương quan (|Corr|) và Importance (Random Forest).

    **4. Khuyến nghị:** Ưu tiên giữ feature corr/importance cao; xử lý missing trước khi train.
    """)

    # Vẽ biểu đồ importance nếu có
    if feature_importance:
        importance_df = pd.DataFrame(
            {'Feature': list(feature_importance.keys()), 'Importance': list(feature_importance.values())}
        ).sort_values('Importance', ascending=False)

        fig_imp = px.bar(
            importance_df,
            x='Feature',
            y='Importance',
            title='📊 Feature Importance (Tầm quan trọng của từng feature)',
            color='Importance',
            color_continuous_scale='Viridis',
            text='Importance',
        )
        fig_imp.update_traces(texttemplate='%{text:.3f}', textposition='outside')
        fig_imp.update_layout(height=400, xaxis_tickangle=-45)
        st.plotly_chart(fig_imp, width="stretch")
        st.caption("Biểu đồ này cho thấy feature nào quan trọng nhất trong việc dự đoán target.")


def explain_models_and_recommend(results):
    st.markdown("---")
    st.header("🧠 Phân tích & Gợi ý Chọn Mô hình")

    col_guide, col_rec = st.columns([1, 1])

    with col_guide:
        st.subheader("📚 Từ điển Mô hình")
        with st.expander("📖 Xem giải thích các mô hình", expanded=False):
            st.markdown("""
            **1. Linear Regression:** Đơn giản, nhanh; dùng khi quan hệ gần tuyến tính.

            **2. Ridge / Lasso:** Có regularization, giảm overfitting; nhiều feature hoặc nhiễu.

            **3. Random Forest:** Phi tuyến, mạnh; mô hình nặng hơn.

            **4. Gradient Boosting (XGBoost/LightGBM):** Độ chính xác cao trên bảng xếp hạng.

            **5. Ensemble (Stacking/Voting):** Kết hợp nhiều mô hình.
            """)

    with col_rec:
        st.subheader("💡 Gợi ý cho bạn")
        if not results:
            st.info("Chưa có kết quả huấn luyện để phân tích.")
            return

        # Tìm model tốt nhất dựa trên R2 Score
        best_model_name = "Unknown"
        best_r2 = -999.0

        try:
            # Lọc chỉ lấy các entry có R2 Score (bỏ qua entry meta nếu có)
            model_candidates = {k: v for k, v in results.items() if isinstance(v, dict) and 'R2 Score' in v}
            if model_candidates:
                best_model = max(model_candidates.items(), key=lambda x: x[1].get('R2 Score', -999.0))
                best_model_name = best_model[0]
                best_r2 = best_model[1].get('R2 Score', -999.0)
        except Exception:
            pass

        if best_r2 == -999.0:
            st.warning("⚠️ Không tìm thấy metric đánh giá hợp lệ.")
            return

        st.info(f"🏆 **Mô hình tốt nhất hiện tại:** `{best_model_name}`")

        if best_r2 < 0:
            st.error(
                "⚠️ **Cảnh báo thông minh:** R2 âm nghĩa là mô hình **tệ hơn cả đoán bừa**. \n\n**Nguyên nhân:** Target không liên quan input hoặc dữ liệu quá nhiễu."
            )
        elif best_r2 < 0.5:
            st.warning(
                "⚠️ **Hiệu suất thấp:** R2 dưới 50%. Hãy thử **thêm features mới** hoặc **thu thập thêm dữ liệu**."
            )
        else:
            st.success(f"✅ **Kết quả khả quan:** Giải thích được {best_r2:.1%} sự biến thiên.")
            if "Linear" in best_model_name or "Ridge" in best_model_name:
                st.markdown("ℹ️ Dữ liệu có tính **tuyến tính cao**.")
            elif "Forest" in best_model_name or "Boost" in best_model_name:
                st.markdown("ℹ️ Dữ liệu **phức tạp/phi tuyến tính**.")

        # Check overfitting
        if best_model_name in model_candidates:
            train_r2 = model_candidates[best_model_name].get('R2 Score (Train)', best_r2)
            if (train_r2 - best_r2) > 0.15:
                st.warning(
                    f"⚠️ **Phát hiện Overfitting:** Train ({train_r2:.2f}) > Test ({best_r2:.2f}). Dùng Ridge/Lasso hoặc giảm max_depth."
                )
