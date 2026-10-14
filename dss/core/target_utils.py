"""Centralized target management, alias canonicalization, leakage guard,
and temporal/longitudinal dataset helpers for EduDSS.
"""
from __future__ import annotations

import logging
from typing import Any, Tuple, List, Set, Optional
import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

# ============================================================================
# CANONICAL TARGETS & ALIASES
# ============================================================================
CANONICAL_TARGET_REGRESSION = "diem_ky_sau"
CANONICAL_REGRESSION_TARGET = CANONICAL_TARGET_REGRESSION
LEGACY_ALIAS_REGRESSION = "final_score"

CANONICAL_TARGET_CLASSIFICATION = "xep_loai"
CANONICAL_CLASSIFICATION_TARGET = CANONICAL_TARGET_CLASSIFICATION
LEGACY_ALIAS_CLASSIFICATION = "grade"

# Centralized alias mapping: {legacy_alias: canonical_target}
COLUMN_ALIASES = {
    LEGACY_ALIAS_REGRESSION: CANONICAL_TARGET_REGRESSION,
    LEGACY_ALIAS_CLASSIFICATION: CANONICAL_TARGET_CLASSIFICATION,
}

REVERSE_ALIASES = {
    CANONICAL_TARGET_REGRESSION: [LEGACY_ALIAS_REGRESSION],
    CANONICAL_TARGET_CLASSIFICATION: [LEGACY_ALIAS_CLASSIFICATION],
}

# ============================================================================
# TARGET LEAKAGE RELATION MATRIX
# ============================================================================
# TARGET_RELATED_COLUMNS defines columns that MUST NOT be in feature set X
# when a specific target is predicted.
# - If target is xep_loai: grade (alias), diem_ky_sau (direct generator),
#   final_score (alias of generator) must be excluded.
# - If target is diem_ky_sau: final_score (alias), xep_loai (derived),
#   grade (alias of derived) must be excluded.
TARGET_RELATED_COLUMNS = {
    CANONICAL_TARGET_CLASSIFICATION: {
        CANONICAL_TARGET_CLASSIFICATION,
        LEGACY_ALIAS_CLASSIFICATION,
        CANONICAL_TARGET_REGRESSION,
        LEGACY_ALIAS_REGRESSION,
    },
    CANONICAL_TARGET_REGRESSION: {
        CANONICAL_TARGET_REGRESSION,
        LEGACY_ALIAS_REGRESSION,
        CANONICAL_TARGET_CLASSIFICATION,
        LEGACY_ALIAS_CLASSIFICATION,
    },
    LEGACY_ALIAS_CLASSIFICATION: {
        CANONICAL_TARGET_CLASSIFICATION,
        LEGACY_ALIAS_CLASSIFICATION,
        CANONICAL_TARGET_REGRESSION,
        LEGACY_ALIAS_REGRESSION,
    },
    LEGACY_ALIAS_REGRESSION: {
        CANONICAL_TARGET_REGRESSION,
        LEGACY_ALIAS_REGRESSION,
        CANONICAL_TARGET_CLASSIFICATION,
        LEGACY_ALIAS_CLASSIFICATION,
    },
}

# Known legitimate predictors that must NEVER be removed automatically as leakage
# even if strongly correlated with the next-semester outcome.
LEGITIMATE_PREDICTORS = {
    "diem_ky_nay",
    "gpa_previous",
    "prior_gpa",
    "diem_giua_ky",
    "diem_du_an",
    "ty_le_diem_danh",
    "attendance",
    "so_gio_hoc_tuan",
    "study_hours",
}

ID_KEYWORDS = ["id", "code", "ma_", "_id", "stt", "no."]

# ============================================================================
# CLASSIFICATION BINS & LABELS (Prototype / Business Grouping)
# ============================================================================
# QUY ƯỚC PHÂN NHÓM HỌC LỰC / KINH DOANH (PROTOTYPE BUSINESS GROUPING):
# - [0.00, 3.99] -> "Yếu"
# - (3.99, 5.49] -> "Trung bình"
# - (5.49, 6.99] -> "Khá"
# - (6.99, 8.49] -> "Giỏi"
# - (8.49, 10.0] -> "Xuất sắc"
# Lưu ý: Đây là quy ước kinh doanh / thử nghiệm nội bộ của dự án EduDSS (chưa phải văn bản
# pháp lý quy định chính thức của Bộ GD&ĐT hay nhà trường).
CLASSIFICATION_BINS = [0.0, 3.99, 5.49, 6.99, 8.49, 10.0]
CLASSIFICATION_LABELS = ["Yếu", "Trung bình", "Khá", "Giỏi", "Xuất sắc"]

# ============================================================================
# OVERFITTING HEURISTIC CONSTANTS (Project Heuristics)
# ============================================================================
# Các ngưỡng dưới đây là HEURISTICS ĐẶC THÙ CỦA DỰ ÁN EduDSS, không phải quy tắc ML phổ quát:
# - HEURISTIC_TARGET_ACCURACY: Ngưỡng kỳ vọng độ chính xác tối thiểu mục tiêu (80%)
# - HEURISTIC_OVERFIT_DIFF_MILD: Khoảng cách giữa Train và Test Accuracy > 10% cảnh báo overfitting nhẹ
# - HEURISTIC_OVERFIT_DIFF_SEVERE: Khoảng cách giữa Train và Test Accuracy > 15% cảnh báo dấu hiệu overfitting
# - Test Accuracy đạt 100% (1.0) được gắn cờ cảnh báo nghi ngờ rò rỉ dữ liệu hoặc điểm số bất thường,
#   tuyệt đối KHÔNG kết luận là mô hình overfitting chỉ dựa vào test accuracy = 100%.
HEURISTIC_TARGET_ACCURACY = 0.80
HEURISTIC_OVERFIT_DIFF_MILD = 0.10
HEURISTIC_OVERFIT_DIFF_SEVERE = 0.15


DEFAULT_TARGET_PREFERENCE = ["diem_ky_sau", "xep_loai", "final_score", "grade", "gpa"]


def infer_default_target_column(
    df: pd.DataFrame, preference_order: Optional[List[str]] = None
) -> str:
    """Suy luận cột target mặc định, ưu tiên các canonical target quen thuộc
    (diem_ky_sau, xep_loai, ...); fallback về cột đầu tiên nếu không khớp cột nào.

    Dùng chung cho UI cấu hình huấn luyện thủ công (`ml_hub.py`) và bootstrap
    huấn luyện mặc định ngầm sau đăng nhập (`bootstrap_service.py`) — trước đây
    hai nơi này copy-paste cùng một vòng lặp ưu tiên.
    """
    all_cols = df.columns.tolist()
    if not all_cols:
        raise ValueError("DataFrame không có cột nào để chọn target.")
    prefs = preference_order if preference_order is not None else DEFAULT_TARGET_PREFERENCE
    for pref in prefs:
        for col in all_cols:
            if col.lower() == pref or pref in col.lower():
                return col
    return all_cols[0]


def infer_problem_type(target_series: pd.Series) -> Optional[str]:
    """Suy luận loại bài toán (Phân loại/Hồi quy) từ kiểu dữ liệu và số lượng giá
    trị duy nhất của cột target đã chọn. Trả về None nếu không xác định được
    (vd. cột không phải numeric/object/category).

    Heuristic dùng chung cho UI huấn luyện thủ công và bootstrap huấn luyện mặc
    định ngầm — trước đây hai nơi này copy-paste cùng công thức ngưỡng.
    """
    n_samples = max(len(target_series), 1)
    n_unique = int(target_series.nunique(dropna=True))
    is_numeric = pd.api.types.is_numeric_dtype(target_series)
    is_integer_like = is_numeric and np.allclose(
        pd.to_numeric(target_series, errors="coerce").dropna() % 1, 0
    )
    cls_unique_threshold = max(20, int(0.05 * n_samples))
    if (
        target_series.dtype == "object"
        or target_series.dtype.name == "category"
        or (is_numeric and is_integer_like and n_unique <= cls_unique_threshold)
        or (is_numeric and n_unique <= 15)
    ):
        return "Phân loại (Classification)"
    if is_numeric:
        return "Hồi quy (Regression)"
    return None


def score_to_xep_loai(
    score_series: pd.Series,
    bins: Optional[List[float]] = None,
    labels: Optional[List[str]] = None,
) -> pd.Series:
    """Chuyển đổi điểm số liên tục thành xếp loại học lực theo quy tắc phân nhóm chuẩn.

    Note: Prototype classification grouping / business rule.
    """
    if bins is None:
        bins = CLASSIFICATION_BINS
    if labels is None:
        labels = CLASSIFICATION_LABELS

    return pd.cut(
        score_series,
        bins=bins,
        labels=labels,
        right=True,
        include_lowest=True,
    )


# ============================================================================
# CANONICALIZATION LOGIC
# ============================================================================
def canonicalize_columns(
    df: pd.DataFrame, strict: bool = True, return_actions: bool = False
) -> pd.DataFrame | Tuple[pd.DataFrame, List[str]]:
    """Chuẩn hóa các cột target/alias về tên chuẩn canonical.

    Quy tắc xử lý:
    - CASE 1: Dataset có `grade` nhưng không có `xep_loai` -> rename thành `xep_loai`.
    - CASE 2: Dataset có `final_score` nhưng không có `diem_ky_sau` -> rename thành `diem_ky_sau`.
    - CASE 3: Dataset chỉ có `diem_ky_sau` -> tự động suy biến `xep_loai` theo ngưỡng chuẩn.
    - CASE 4: Có cả legacy alias và canonical target:
        + Nếu giá trị giống nhau: giữ canonical, loại bỏ duplicate alias.
        + Nếu khác nhau: báo lỗi (strict=True) hoặc warning dữ liệu không nhất quán.

    Returns:
        DataFrame hoặc (canonical_df, actions_log) nếu return_actions=True.
    """
    df_out = df.copy()
    actions = []

    # CASE 1 & Duplicate check: Classification target
    has_grade = LEGACY_ALIAS_CLASSIFICATION in df_out.columns
    has_xep_loai = CANONICAL_TARGET_CLASSIFICATION in df_out.columns

    if has_grade and not has_xep_loai:
        df_out = df_out.rename(columns={LEGACY_ALIAS_CLASSIFICATION: CANONICAL_TARGET_CLASSIFICATION})
        actions.append(f"Renamed alias '{LEGACY_ALIAS_CLASSIFICATION}' to canonical '{CANONICAL_TARGET_CLASSIFICATION}'")
    elif has_grade and has_xep_loai:
        s_grade = df_out[LEGACY_ALIAS_CLASSIFICATION].astype(str).str.strip().str.lower()
        s_xl = df_out[CANONICAL_TARGET_CLASSIFICATION].astype(str).str.strip().str.lower()
        is_same = (s_grade == s_xl).all()
        if not is_same:
            msg = (
                f"Xung đột dữ liệu (Data inconsistency): Cả '{LEGACY_ALIAS_CLASSIFICATION}' và "
                f"'{CANONICAL_TARGET_CLASSIFICATION}' cùng tồn tại nhưng có giá trị khác nhau!"
            )
            _logger.warning(msg)
            if strict:
                raise ValueError(msg)
        df_out = df_out.drop(columns=[LEGACY_ALIAS_CLASSIFICATION])
        actions.append(
            f"Removed duplicate alias '{LEGACY_ALIAS_CLASSIFICATION}', keeping canonical '{CANONICAL_TARGET_CLASSIFICATION}'"
        )

    # CASE 2 & Duplicate check: Regression target
    has_fs = LEGACY_ALIAS_REGRESSION in df_out.columns
    has_dks = CANONICAL_TARGET_REGRESSION in df_out.columns

    if has_fs and not has_dks:
        df_out = df_out.rename(columns={LEGACY_ALIAS_REGRESSION: CANONICAL_TARGET_REGRESSION})
        actions.append(f"Renamed alias '{LEGACY_ALIAS_REGRESSION}' to canonical '{CANONICAL_TARGET_REGRESSION}'")
    elif has_fs and has_dks:
        s_fs = pd.to_numeric(df_out[LEGACY_ALIAS_REGRESSION], errors="coerce")
        s_dks = pd.to_numeric(df_out[CANONICAL_TARGET_REGRESSION], errors="coerce")
        is_same = np.allclose(s_fs.dropna(), s_dks.dropna(), atol=1e-3, rtol=1e-3) and (len(s_fs.dropna()) == len(s_dks.dropna()) == len(df_out))
        if not is_same:
            msg = (
                f"Xung đột dữ liệu (Data inconsistency): Cả '{LEGACY_ALIAS_REGRESSION}' và "
                f"'{CANONICAL_TARGET_REGRESSION}' cùng tồn tại nhưng có giá trị khác nhau!"
            )
            _logger.warning(msg)
            if strict:
                raise ValueError(msg)
        df_out = df_out.drop(columns=[LEGACY_ALIAS_REGRESSION])
        actions.append(
            f"Removed duplicate alias '{LEGACY_ALIAS_REGRESSION}', keeping canonical '{CANONICAL_TARGET_REGRESSION}'"
        )

    # CASE 3: Tự động suy biến xep_loai khi có diem_ky_sau nhưng chưa có xep_loai
    if CANONICAL_TARGET_REGRESSION in df_out.columns and CANONICAL_TARGET_CLASSIFICATION not in df_out.columns:
        if pd.api.types.is_numeric_dtype(df_out[CANONICAL_TARGET_REGRESSION]):
            df_out[CANONICAL_TARGET_CLASSIFICATION] = score_to_xep_loai(df_out[CANONICAL_TARGET_REGRESSION])
            actions.append(
                f"Derived '{CANONICAL_TARGET_CLASSIFICATION}' from '{CANONICAL_TARGET_REGRESSION}' using standard score thresholds"
            )

    if return_actions:
        return df_out, actions
    return df_out


# ============================================================================
# TARGET LEAKAGE GUARD
# ============================================================================
def get_leaky_target_columns(target_col: str) -> Set[str]:
    """Trả về tập hợp các cột có liên hệ trực tiếp với target và gây rò rỉ dữ liệu."""
    target_clean = str(target_col).strip().lower()
    for k, forbidden_set in TARGET_RELATED_COLUMNS.items():
        if target_clean == k.lower():
            return set(forbidden_set)

    # If target matches one of the canonicals through substring or alias
    if "xep_loai" in target_clean or "grade" in target_clean:
        return set(TARGET_RELATED_COLUMNS[CANONICAL_TARGET_CLASSIFICATION])
    if "diem_ky_sau" in target_clean or "final_score" in target_clean:
        return set(TARGET_RELATED_COLUMNS[CANONICAL_TARGET_REGRESSION])

    # Default fallback: target itself and its potential aliases
    res = {target_col}
    if target_col in COLUMN_ALIASES:
        res.add(COLUMN_ALIASES[target_col])
    if target_col in REVERSE_ALIASES:
        res.update(REVERSE_ALIASES[target_col])
    return res


def filter_leakage_features(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: List[str],
    return_removed: bool = False,
) -> List[str] | Tuple[List[str], List[str]]:
    """Loại bỏ các cột gây rò rỉ dữ liệu (target, aliases, derived targets, ID columns).

    BẢO VỆ TUYỆT ĐỐI: `diem_ky_nay` và các legitimate predictors khác KHÔNG BAO GIỜ bị loại.

    Returns:
        clean_features nếu return_removed=False, hoặc (clean_features, removed_features) nếu return_removed=True.
    """
    forbidden_targets = get_leaky_target_columns(target_col)
    clean_features = []
    removed_features = []

    for col in feature_cols:
        col_str = str(col)
        col_lower = col_str.lower()

        # 1. Check if column is the target or a forbidden target-derived/alias column
        if col in forbidden_targets or col_lower in {f.lower() for f in forbidden_targets}:
            removed_features.append(col)
            continue

        # 2. Check if column is ID-like
        if any(k in col_lower for k in ID_KEYWORDS) and col_lower not in LEGITIMATE_PREDICTORS:
            removed_features.append(col)
            continue

        # 3. Legitimate predictors (diem_ky_nay, etc.) are always preserved
        if col in df.columns:
            clean_features.append(col)

    if return_removed:
        return clean_features, removed_features
    return clean_features


# ============================================================================
# TEMPORAL & LONGITUDINAL HELPERS
# ============================================================================
TEMPORAL_KEYWORDS = ["semester", "hoc_ky", "ky_hoc", "nam_hoc", "year", "timestamp", "time", "date"]


def detect_temporal_column(df: pd.DataFrame) -> Optional[str]:
    """Tìm cột chứa thông tin thời gian hoặc học kỳ trong DataFrame nếu có."""
    for col in df.columns:
        col_lower = str(col).lower()
        if any(k in col_lower for k in TEMPORAL_KEYWORDS):
            return col
    return None


def prepare_longitudinal_dataset(
    df: pd.DataFrame,
    student_id_col: str = "student_id",
    time_col: str = "semester",
    score_col: str = "diem_ky_nay",
    target_future_col: str = CANONICAL_TARGET_REGRESSION,
    target_metric_col: Optional[str] = None,
    drop_na_target: bool = False,
) -> pd.DataFrame:
    """Tạo tập dữ liệu chuỗi thời gian (Longitudinal / Temporal Dataset) từ quan sát lịch sử:

        X_t (thông tin học kỳ t) ──> Y_(t+1) (kết quả thực tế học kỳ t+1)

    Mỗi sinh viên có nhiều học kỳ:
        SV001 kỳ 1 features ──> SV001 kỳ 2 observed score (diem_ky_sau)
        SV001 kỳ 2 features ──> SV001 kỳ 3 observed score (diem_ky_sau)
    Học kỳ cuối cùng của sinh viên (chưa có kết quả tương lai) sẽ có target là NaN
    và không dùng để huấn luyện (dùng để dự đoán tương lai).
    """
    effective_score = target_metric_col if target_metric_col is not None else score_col
    if student_id_col not in df.columns or time_col not in df.columns or effective_score not in df.columns:
        raise ValueError(
            f"Dataset thiếu một trong các cột bắt buộc: '{student_id_col}', '{time_col}', '{effective_score}'"
        )

    df_sorted = df.sort_values(by=[student_id_col, time_col]).copy()
    # Shift outcome of next semester for the same student
    df_sorted[target_future_col] = df_sorted.groupby(student_id_col)[effective_score].shift(-1)
    
    if drop_na_target:
        df_sorted = df_sorted.dropna(subset=[target_future_col]).copy()
        
    if target_future_col == CANONICAL_TARGET_REGRESSION and "xep_loai" not in df_sorted.columns:
        valid_mask = ~df_sorted[target_future_col].isna()
        df_sorted.loc[valid_mask, "xep_loai"] = score_to_xep_loai(df_sorted.loc[valid_mask, target_future_col])

    df_sorted.attrs["data_source_type"] = "real"
    df_sorted.attrs["split_strategy"] = "temporal"
    return df_sorted


def temporal_train_test_split(
    df_or_X: pd.DataFrame,
    y_or_time: Any = None,
    time_series: Any = None,
    test_size: float = 0.2,
    time_col: Optional[str] = None,
    test_ratio: Optional[float] = None,
) -> Any:
    """Chia tập train/test theo trật tự thời gian (quá khứ -> TRAIN, tương lai -> TEST).

    Hỗ trợ 2 cú pháp:
    1. train_df, test_df = temporal_train_test_split(df, time_col="hoc_ky", test_ratio=0.33)
    2. X_train, X_test, y_train, y_test = temporal_train_test_split(X, y, time_series, test_size=0.2)
    """
    effective_ratio = test_ratio if test_ratio is not None else test_size

    # Cú pháp 1: Chia DataFrame theo tên cột
    if time_col is not None or (isinstance(y_or_time, str) and y_or_time in df_or_X.columns):
        col = time_col or y_or_time
        time_vals = df_or_X[col]
        sorted_times = sorted(time_vals.unique())
        n_test_times = max(1, int(round(len(sorted_times) * effective_ratio)))
        split_cutoff = sorted_times[-n_test_times]

        train_df = df_or_X[df_or_X[col] < split_cutoff].copy()
        test_df = df_or_X[df_or_X[col] >= split_cutoff].copy()
        return train_df, test_df

    # Cú pháp 2: Chia X, y theo time_series
    X = df_or_X
    y = y_or_time
    t_series = time_series
    if t_series is None:
        t_series = pd.Series(range(len(X)), index=X.index)

    sorted_idx = t_series.sort_values().index
    split_point = int(len(sorted_idx) * (1.0 - effective_ratio))
    train_idx = sorted_idx[:split_point]
    test_idx = sorted_idx[split_point:]

    return X.loc[train_idx], X.loc[test_idx], y.loc[train_idx], y.loc[test_idx]


def validate_evaluation_target(
    df: pd.DataFrame,
    target_col: str,
    data_source_type: str = "real",
) -> Tuple[bool, str]:
    """Kiểm tra tính hợp lệ của target trong Real/Evaluation Mode.

    Trong REAL / EVALUATION MODE:
    - Target phải tồn tại và được quan sát trong dataset.
    - Tuyệt đối không tự tạo/tính bằng công thức mô phỏng.
    - Nếu không có target: báo rõ dataset không đủ điều kiện cho longitudinal evaluation.
    """
    if target_col not in df.columns:
        # Check if alias exists
        if target_col == CANONICAL_TARGET_REGRESSION and LEGACY_ALIAS_REGRESSION in df.columns:
            return True, f"Target '{target_col}' có thể suy ra từ alias '{LEGACY_ALIAS_REGRESSION}'"
        if target_col == CANONICAL_TARGET_CLASSIFICATION and LEGACY_ALIAS_CLASSIFICATION in df.columns:
            return True, f"Target '{target_col}' có thể suy ra từ alias '{LEGACY_ALIAS_CLASSIFICATION}'"
        return False, (
            f"Dataset không đủ điều kiện cho longitudinal evaluation: "
            f"Thiếu cột kết quả thực tế quan sát được '{target_col}'. "
            "Hệ thống không tự tạo target để đảm bảo tính khách quan."
        )

    target_s = df[target_col].dropna()
    if len(target_s) == 0:
        return False, f"Cột target '{target_col}' hoàn toàn rỗng trong dataset."

    return True, "Target hợp lệ"
