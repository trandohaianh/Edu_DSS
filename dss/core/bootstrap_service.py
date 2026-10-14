"""Khởi tạo workspace sau đăng nhập — TÁCH BIỆT rõ giữa:

    (a) tiến trình UI thân thiện hiển thị cho người dùng (màn tải EduDSS,
        xem `dss/tabs/loading_screen.py`), và
    (b) công việc khởi tạo kỹ thuật THẬT (huấn luyện mặc định lần đầu, phân
        cụm mặc định — logic 100% giữ nguyên từ `auto_bootstrap.py` cũ).

Lớp UI chỉ biết map (percent, stage_key) -> câu tiếng Việt thân thiện; KHÔNG
biết gì về RandomForest/GridSearchCV/KMeans. Ngược lại, module này (và các
service nó gọi) không được vẽ bất kỳ UI kỹ thuật nào lên trang — nếu hàm
huấn luyện dùng chung (`run_training`, chứa nhiều `st.write/info/...` phục vụ
màn hình "Huấn luyện — Dự đoán" THỦ CÔNG của Giảng viên) được gọi Ở ĐÂY một
cách NGẦM, output kỹ thuật của nó bị nuốt an toàn và chuyển thành log (xem
`_suppress_streamlit_output`) — không sửa `trainers.py`/`run_training` (vẫn
cần hiển thị bình thường khi Giảng viên tự bấm huấn luyện thủ công).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from dss.core.logging_config import get_logger
from dss.core.target_utils import (
    filter_leakage_features,
    get_leaky_target_columns,
    infer_default_target_column,
    infer_problem_type,
)
from dss.services.model_service import find_leaky_feature_cols
from dss.services import clustering_service

_logger = get_logger(__name__)


class _NullWidget:
    """No-op thay cho 1 container/widget Streamlit — nuốt an toàn mọi lời gọi
    UI bên trong khi chạy Ở CHẾ ĐỘ NGẦM, không vẽ gì lên trang, không raise
    lỗi dù gọi thuộc tính/method/`with` block nào."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False


@contextmanager
def _suppress_streamlit_output():
    """Trong lúc khởi tạo NGẦM: st.write/info/success/warning/error được
    CHUYỂN THÀNH log kỹ thuật thật (không mất thông tin cho người vận hành —
    xem yêu cầu thiết kế "technical logs still exist"); mọi widget tương tác
    (expander/columns/metric/chart/dataframe/button/spinner...) bị nuốt an
    toàn — không vẽ gì lên trang. Khôi phục nguyên trạng `streamlit` module
    ngay khi xong (finally), không ảnh hưởng bất kỳ lời gọi `st.*` nào khác
    đang/sẽ chạy ở ngữ cảnh khác (vd. tab "Huấn luyện — Dự đoán" thủ công)."""
    _text_levels = {
        "write": logging.INFO,
        "info": logging.INFO,
        "success": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    _widget_names = (
        "expander", "columns", "metric", "plotly_chart", "dataframe",
        "download_button", "button", "spinner", "progress", "caption",
        "markdown", "subheader", "header",
    )
    _originals: dict[str, object] = {}

    def _make_text_fn(level):
        def _fn(*args, **kwargs):
            if args:
                try:
                    _logger.log(level, "[bootstrap-ngầm] %s", str(args[0])[:500])
                except Exception:
                    pass
            return None
        return _fn

    def _columns_fn(spec=1, *_a, **_k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_NullWidget() for _ in range(max(int(n), 1))]

    for _name, _level in _text_levels.items():
        _originals[_name] = getattr(st, _name)
        setattr(st, _name, _make_text_fn(_level))
    for _name in _widget_names:
        _originals[_name] = getattr(st, _name)
        if _name == "columns":
            setattr(st, _name, _columns_fn)
        elif _name == "button":
            setattr(st, _name, lambda *a, **k: False)
        else:
            setattr(st, _name, lambda *a, **k: _NullWidget())

    try:
        yield
    finally:
        for _name, _fn in _originals.items():
            setattr(st, _name, _fn)


def _detect_default_training_config(df):
    """Suy luận target/feature mặc định — ưu tiên canonical target (diem_ky_sau, xep_loai),
    lọc rò rỉ dữ liệu (target leakage) nhưng bảo toàn feature hợp lệ (diem_ky_nay)."""
    all_cols = df.columns.tolist()
    target_col = infer_default_target_column(df)
    problem_type = infer_problem_type(df[target_col])

    if not problem_type:
        return None

    available_features = [c for c in all_cols if c != target_col]
    id_cols = [c for c in all_cols if "id" in str(c).lower() or "name" in str(c).lower()]

    clean_features = filter_leakage_features(df, target_col, available_features)
    leaky_cols = find_leaky_feature_cols(df, target_col, id_cols)
    exclude_cols = set(id_cols + ["grade", "pass_fail", "status", "result"] + leaky_cols)
    exclude_cols.update(get_leaky_target_columns(target_col))

    selected_features = [
        c for c in clean_features
        if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])
    ]
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
            len(dropped_near_dup), dropped_near_dup,
        )

    if not selected_features:
        return None

    model_name = (
        "Random Forest Classifier"
        if problem_type == "Phân loại (Classification)"
        else "Random Forest Regressor"
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
                _logger.info("Tái sử dụng mô hình Production từ Kho dữ liệu: %s (dataset=%s, target=%s)", model_name, dataset_id, target_col)
                return
        except Exception as e:
            _logger.warning("Không thể đọc mô hình Production từ Kho dữ liệu: %s", e)

    # SECTION 24: Tuyệt đối không tự động chạy GridSearchCV/huấn luyện mô hình khi khởi động/đăng nhập.
    # Chỉ tái sử dụng mô hình Production từ Kho dữ liệu nếu ĐÃ ĐƯỢC Admin phê duyệt trước đó.
    _logger.info(
        "Khởi tạo workspace: Không tự động chạy GridSearchCV khi đăng nhập. "
        "Mô hình cần được Giảng viên huấn luyện tường minh qua ML Hub."
    )



def _bootstrap_default_clustering(df):
    if "cluster_results_df" in st.session_state and st.session_state.get("cluster_results_df") is not None:
        return
    # C-1: dùng hàm chọn cột mặc định DÙNG CHUNG với clustering.py (UI) — loại
    # bí danh/target, nhận diện tên cột tiếng Việt, loại cột gần trùng lặp.
    cluster_cols = clustering_service.select_default_cluster_features(df)
    if not cluster_cols:
        _logger.info("Bỏ qua phân cụm mặc định — không có cột số phù hợp.")
        return

    _logger.info("Bắt đầu phân cụm mặc định (ngầm): %d đặc trưng.", len(cluster_cols))
    cluster_preprocessor, X_processed = clustering_service.preprocess_features(df, cluster_cols)
    k_optimal = min(4, max(2, len(df) // 10))
    kmeans, clusters = clustering_service.run_kmeans(X_processed, k_optimal)
    _quality = clustering_service.compute_cluster_quality_metrics(X_processed, clusters)

    st.session_state.cluster_preprocessor = cluster_preprocessor
    st.session_state.cluster_selected_cols = cluster_cols
    st.session_state.cluster_X_processed = X_processed
    st.session_state.cluster_results_df = df.copy()
    st.session_state.cluster_results_df["cluster"] = clusters
    st.session_state.cluster_kmeans_model = kmeans
    st.session_state.cluster_k_optimal = k_optimal
    st.session_state.cluster_quality_silhouette = _quality["silhouette"]
    st.session_state.cluster_quality_db = _quality["davies_bouldin"]
    st.session_state.cluster_train_run_id = f"{datetime.now().timestamp()}_{k_optimal}"
    _logger.info("Hoàn tất phân cụm mặc định (ngầm): k=%d.", k_optimal)


def initialize_workspace(role, df, wh, classification_trainer, regression_trainer, progress_callback=None):
    """Khởi tạo workspace sau đăng nhập. Báo tiến độ qua
    `progress_callback(percent, stage_key)` — lớp UI (loading_screen.py) map
    `stage_key` sang câu tiếng Việt thân thiện. KHÔNG train lại nếu dataset
    này ĐÃ có kết quả (`hub_results`/`cluster_results_df` đã tồn tại) — giữ
    đúng hành vi idempotent của `auto_bootstrap_analytics` cũ, không train lại
    chỉ vì người dùng đăng nhập/mở lại trang.
    """
    def _report(pct, stage):
        if progress_callback:
            try:
                progress_callback(pct, stage)
            except Exception:
                _logger.exception("Lỗi trong progress_callback (bỏ qua, không chặn khởi tạo).")

    _report(10, "auth_ready")

    if df is None:
        _report(100, "workspace_ready")
        return
    _report(30, "dataset_ready")

    dataset_id = st.session_state.get("current_dataset_id")
    already_done = st.session_state.get("_auto_bootstrap_done_for") == dataset_id
    st.session_state["_auto_bootstrap_done_for"] = dataset_id
    _report(50, "artifacts_checked")

    if not already_done:
        with _suppress_streamlit_output():
            try:
                _bootstrap_default_training(df, wh, classification_trainer, regression_trainer)
            except Exception:
                _logger.exception("Lỗi khi tự động huấn luyện mô hình mặc định — bỏ qua, Giảng viên có thể tự huấn luyện thủ công.")
    _report(70, "model_ready")

    if not already_done:
        with _suppress_streamlit_output():
            try:
                _bootstrap_default_clustering(df)
            except Exception:
                _logger.exception("Lỗi khi tự động phân cụm mặc định — bỏ qua, Giảng viên có thể tự phân cụm thủ công.")
    _report(90, "role_data_ready")

    _report(100, "workspace_ready")
