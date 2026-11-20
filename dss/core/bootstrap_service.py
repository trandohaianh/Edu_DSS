"""Lightweight login initialization: reuse approved models; no implicit analytics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dss.core.logging_config import get_logger
from dss.core.target_utils import (
    filter_leakage_features,
    get_leaky_target_columns,
    infer_default_target_column,
    infer_problem_type,
    is_id_like,
)
from dss.services.model_service import find_leaky_feature_cols

_logger = get_logger(__name__)


def _detect_default_training_config(df):
    """Suy luận target/feature mặc định — ưu tiên canonical target (diem_ky_sau, xep_loai),
    lọc rò rỉ dữ liệu (target leakage) nhưng bảo toàn feature hợp lệ (diem_ky_nay)."""
    all_cols = df.columns.tolist()
    target_col = infer_default_target_column(df)
    problem_type = infer_problem_type(df[target_col])

    if not problem_type:
        return None

    available_features = [c for c in all_cols if c != target_col]
    id_cols = [c for c in all_cols if is_id_like(c) or "name" in str(c).lower()]

    clean_features = filter_leakage_features(df, target_col, available_features)
    leaky_cols = find_leaky_feature_cols(df, target_col, id_cols)
    exclude_cols = set(id_cols + ["grade", "pass_fail", "status", "result"] + leaky_cols)
    exclude_cols.update(get_leaky_target_columns(target_col))

    selected_features = [c for c in clean_features if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])]
    if "diem_ky_nay" in df.columns and "diem_ky_nay" not in selected_features and target_col != "diem_ky_nay":
        selected_features.append("diem_ky_nay")

    # G-2: loại cột GẦN NHƯ TRÙNG LẶP với nhau (vd. gpa_previous ~ diem_ky_nay,
    # r~0.9999) khỏi danh sách feature MẶC ĐỊNH — không bị filter_leakage_features
    # loại vì không rò rỉ với TARGET, chỉ trùng lặp giữa các feature với nhau.
    from dss.services.model_service import drop_near_duplicate_columns

    selected_features, dropped_near_dup = drop_near_duplicate_columns(df, selected_features)
    if dropped_near_dup:
        _logger.info(
            "Đã loại %d feature gần như trùng lặp khỏi cấu hình huấn luyện mặc định: %s",
            len(dropped_near_dup),
            dropped_near_dup,
        )

    if not selected_features:
        return None

    model_name = (
        "Random Forest Classifier" if problem_type == "Phân loại (Classification)" else "Random Forest Regressor"
    )
    data_source_type = getattr(df, "attrs", {}).get("data_source_type", "synthetic")
    return {
        "target_col": target_col,
        "selected_features": selected_features,
        "problem_type": problem_type,
        "training_strategy": "Chọn 1 mô hình",
        "models_to_run": [model_name],
        "test_size": 0.2,
        "cv_folds": 3,
        "balance_method": "none",
        "fs_method": "none",
        "k_features": len(selected_features),
        "outlier_method": "none",
        "scaler_type": "StandardScaler",
        "data_source_type": data_source_type,
        "split_strategy": "random",
    }


def _bootstrap_default_training(df, wh, classification_trainer, regression_trainer):
    if "hub_results" in st.session_state and st.session_state.get("hub_results"):
        return
    auto_config = _detect_default_training_config(df)
    if not auto_config:
        _logger.info("Bỏ qua huấn luyện mặc định — không suy luận được target/feature phù hợp.")
        return

    target_col = auto_config["target_col"]
    dataset_id = st.session_state.get("current_dataset_id", "default")

    # Tái sử dụng mô hình Production từ Kho dữ liệu nếu đã có
    if wh and dataset_id:
        try:
            prod_pipeline, prod_meta = wh.get_production_model(dataset_id, target_col)
            if prod_pipeline and prod_meta:
                model_name = prod_meta.get("model_name", "Production Model")
                st.session_state.hub_pipelines = {model_name: prod_pipeline}
                st.session_state.hub_results = {model_name: prod_meta.get("metrics", {})}
                st.session_state.hub_feats = prod_meta.get("feature_cols", auto_config["selected_features"])
                st.session_state.hub_target_col = target_col
                st.session_state.hub_type = "clf" if "Phân loại" in auto_config["problem_type"] else "reg"
                if "class_labels" in prod_meta:
                    st.session_state.hub_labels = prod_meta["class_labels"]
                _logger.info(
                    "Tái sử dụng mô hình Production từ Kho dữ liệu: %s (dataset=%s, target=%s)",
                    model_name,
                    dataset_id,
                    target_col,
                )
                return
        except Exception as e:
            _logger.warning("Không thể đọc mô hình Production từ Kho dữ liệu: %s", e)

    # SECTION 24: Tuyệt đối không tự động chạy GridSearchCV/huấn luyện mô hình khi khởi động/đăng nhập.
    # Chỉ tái sử dụng mô hình Production từ Kho dữ liệu nếu ĐÃ ĐƯỢC Admin phê duyệt trước đó.
    _logger.info(
        "Khởi tạo workspace: Không tự động chạy GridSearchCV khi đăng nhập. "
        "Mô hình cần được Giảng viên huấn luyện tường minh qua ML Hub."
    )


def initialize_workspace(role, df, wh, classification_trainer, regression_trainer, progress_callback=None):
    """Hydrate approved artifacts only; expensive analytics are explicit actions."""

    def report(percent, stage):
        if progress_callback:
            try:
                progress_callback(percent, stage)
            except Exception:
                _logger.exception("Không cập nhật được tiến độ khởi tạo.")

    report(10, "auth_ready")
    if df is None:
        report(100, "workspace_ready")
        return
    report(30, "dataset_ready")
    dataset_id = st.session_state.get("current_dataset_id")
    already_done = st.session_state.get("_auto_bootstrap_done_for") == dataset_id
    report(50, "artifacts_checked")
    if not already_done:
        try:
            _bootstrap_default_training(df, wh, classification_trainer, regression_trainer)
        except Exception:
            _logger.exception("Không thể nạp mô hình đã duyệt; tiếp tục mà không huấn luyện ngầm.")
        st.session_state["_auto_bootstrap_done_for"] = dataset_id
    report(70, "model_ready")
    report(90, "role_data_ready")
    report(100, "workspace_ready")
