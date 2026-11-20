"""Model service — Phase 2 của kế hoạch refactor EduDSS.

Toàn bộ hàm trong file này TRƯỚC ĐÂY nằm lẫn trong `dss/tabs/ml_hub.py` (2400+
dòng UI) — đây là phần LOGIC THUẦN của pipeline huấn luyện/đánh giá (không có
`st.markdown`/`st.button`/`st.selectbox` nào), nên di chuyển sang đây không đổi
hành vi, chỉ tách đúng ranh giới UI/business-logic theo yêu cầu refactor:

    UI (tabs/ml_hub.py) -> gọi -> model_service.run_training(...)

thay vì UI tự làm hết "load model -> preprocess -> train -> lưu session_state"
trong cùng 1 hàm.

Tác dụng phụ tích cực: `dss/core/auto_bootstrap.py` trước đây phải import
`_run_ml_hub_training`/`_find_leaky_feature_cols` từ `dss.tabs.ml_hub` — một vi
phạm phân lớp (core phụ thuộc ngược vào UI layer) đã bị phát hiện trong bản
đánh giá kiến trúc. Giờ `auto_bootstrap.py` import từ đây (`services/`), đúng
hướng phụ thuộc: UI -> services -> core.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from dss.core.target_utils import is_id_like

# Tách theo chức năng (giữ tên cũ qua re-export để `model_service.X` vẫn dùng được):
# - giải thích mô hình (SHAP, độ quan trọng đặc trưng): dss/services/model_explainability.py
# - bảng chỉ số và chọn mô hình tốt nhất:               dss/services/model_metrics.py
from dss.services.model_explainability import (  # noqa: F401
    _SHAP_TREE_MODEL_NAMES,
    _resolve_shap_feature_names,
    _shap_input_transformer,
    compute_shap_local_explanation,
    compute_shap_summary,
    get_production_feature_importance,
)
from dss.services.model_metrics import (  # noqa: F401
    CV_MAE_COL,
    CV_SCORE_COL,
    _has_complete_cv,
    build_metrics_dataframe,
    extract_failed_models,
    pick_best_model_name,
    resolve_ranking_col,
    safe_metric_value,
    update_hub_benchmark_and_build_comparison,
)


def drop_near_duplicate_columns(df, cols, corr_threshold=0.98):
    """G-2: loại cột GẦN NHƯ TRÙNG LẶP (|r| > corr_threshold) VỚI NHAU khỏi 1
    danh sách feature — vd. gpa_previous = diem_ky_nay / 2.5, tương quan ~0.9999,
    nhưng KHÔNG bị coi là rò rỉ dữ liệu với TARGET (nằm trong LEGITIMATE_PREDICTORS)
    nên vẫn lọt vào danh sách feature MẶC ĐỊNH cùng lúc với diem_ky_nay. Đây là
    kiểm tra KHÁC: trùng lặp giữa các FEATURE với nhau, không phải với target.
    Chỉ dùng cho danh sách MẶC ĐỊNH — KHÔNG xóa khỏi LEGITIMATE_PREDICTORS,
    người dùng vẫn tự chọn tay được cả 2 cột nếu muốn.

    Trả về (cols_đã_lọc, cols_bị_loại) — giữ nguyên thứ tự đầu vào, giữ cột
    xuất hiện TRƯỚC trong `cols` khi 2 cột trùng lặp nhau.
    """
    numeric_cols = [c for c in cols if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in cols if c not in numeric_cols]
    kept, dropped = [], []
    for col in numeric_cols:
        is_duplicate = False
        for chosen in kept:
            try:
                corr = df[col].corr(df[chosen])
            except Exception:
                corr = 0.0
            if pd.notna(corr) and abs(corr) > corr_threshold:
                is_duplicate = True
                break
        if is_duplicate:
            dropped.append(col)
        else:
            kept.append(col)
    # Giữ đúng thứ tự gốc của các cột được giữ lại (kept có thể lệch thứ tự vì
    # numeric_cols đã tách riêng khỏi non_numeric_cols ở trên).
    kept_set = set(kept) | set(non_numeric_cols)
    ordered_kept = [c for c in cols if c in kept_set]
    return ordered_kept, dropped


def resolve_saved_feature_cols(selected_features):
    """S-2: cột feature LƯU vào metadata Kho (wh.save_model_training) phải là
    cột PIPELINE THẬT SỰ dùng — tức `st.session_state.hub_feats` do run_training()
    ghi lại (sau khi trainer lọc rò rỉ dữ liệu qua filter_leakage_features) —
    KHÔNG PHẢI danh sách chọn thô trên UI (selected_features), vốn có thể còn
    chứa cột đã bị pipeline loại bỏ (vd. final_score khi target=diem_ky_sau).
    Lệch nhau khiến form dự đoán/Dashboard đọc metadata này đòi cột thừa hoặc
    báo "thiếu cột" một cách sai lệch. Fallback về selected_features chỉ khi
    hub_feats trống (chưa từng train trong phiên này).
    """
    hub_feats = st.session_state.get("hub_feats")
    return list(hub_feats) if hub_feats else list(selected_features)


def clear_prediction_training_state(prefix: str) -> None:
    """Xóa kết quả huấn luyện (pers / file / batch) để chạy lại với cấu hình khác."""
    for suffix in (
        "results",
        "pipelines",
        "labels",
        "feats",
        "type",
        "test_data",
        "X_train",
        "y_train",
        "eval_frames",
        "final_df",
        "pred_target_col",
    ):
        k = f"{prefix}_{suffix}"
        if k in st.session_state:
            del st.session_state[k]


def run_training(df, config, classification_trainer, regression_trainer, wh):
    """Huấn luyện một lần, ghi `hub_*` trong session_state — dùng chung cho mọi chế độ dự đoán."""
    target_col = config["target_col"]
    selected_features = config["selected_features"]
    problem_type = config["problem_type"]
    models_to_run = config["models_to_run"]
    test_size_val = config["test_size"]
    cv_folds_val = config["cv_folds"]
    balance_method_val = config["balance_method"]
    fs_method = config["fs_method"]
    k_features = config["k_features"]
    outlier_method = config["outlier_method"]
    scaler_type = config["scaler_type"]
    split_strategy = config.get("split_strategy", "random")
    time_col = config.get("time_col", None)
    data_source_type = config.get("data_source_type", getattr(df, "attrs", {}).get("data_source_type", "synthetic"))
    dataset_id = st.session_state.get("current_dataset_id", "unknown")

    # Lưu ý: KHÔNG tự chia train/test ở đây. Trước đây hàm này tự chia một lần độc lập với
    # lần chia bên trong classification_trainer/regression_trainer.train_and_evaluate — hai
    # lần chia tách biệt này chỉ tình cờ khớp nhau, và với phân loại còn lệch cả không gian
    # nhãn (y ở đây là chuỗi gốc, còn pipeline.predict() trả về mã số nội bộ), khiến biểu đồ
    # "Thực tế vs Dự đoán"/Confusion Matrix ở BƯỚC 6 so sánh sai lệch dữ liệu. Nay dùng đúng
    # tập test (và tập train thực sự đã fit) do chính trainer trả về.
    if problem_type == "Phân loại (Classification)":
        balance_method_to_use = balance_method_val if problem_type == "Phân loại (Classification)" else "none"
        results, pipelines, labels, trained_feats, X_test, y_test, X_train_used = (
            classification_trainer.train_and_evaluate(
                df,
                selected_features,
                target_col,
                models_to_run,
                training_strategy=config.get("training_strategy", "So sánh nhiều mô hình (Compare)"),
                balance_method=balance_method_to_use,
                fs_method=fs_method,
                k_features=k_features,
                test_size=test_size_val,
                cv_folds=cv_folds_val,
                save_model=False,
                split_strategy=split_strategy,
                time_col=time_col,
                data_source_type=data_source_type,
                _warehouse=wh,
                _dataset_id=dataset_id,
            )
        )
        st.session_state.hub_results = results
        st.session_state.hub_pipelines = pipelines
        st.session_state.hub_labels = labels
        st.session_state.hub_feats = trained_feats
        st.session_state.hub_type = "clf"
    else:
        results, pipelines, eval_frames, trained_feats, X_test, y_test, X_train_used = (
            regression_trainer.train_and_evaluate(
                df,
                selected_features,
                target_col,
                models_to_run,
                training_strategy=config.get("training_strategy", "So sánh nhiều mô hình (Compare)"),
                fs_method=fs_method,
                k_features=k_features,
                test_size=test_size_val,
                cv_folds=cv_folds_val,
                save_model=False,
                outlier_method=outlier_method,
                scaler_type=scaler_type,
                split_strategy=split_strategy,
                time_col=time_col,
                data_source_type=data_source_type,
                _warehouse=wh,
                _dataset_id=dataset_id,
            )
        )
        st.session_state.hub_results = results
        st.session_state.hub_pipelines = pipelines
        st.session_state.hub_eval_frames = eval_frames
        st.session_state.hub_feats = trained_feats
        st.session_state.hub_type = "reg"

    st.session_state.hub_test_data = (X_test, y_test)
    st.session_state.hub_X_train = X_train_used
    st.session_state.hub_target_col = target_col
    # Đánh dấu một lượt huấn luyện MỚI (dùng để auto-save mô hình đúng 1 lần cho
    # lượt này ở Bước 5, không lưu lặp lại mỗi khi trang rerun vì thao tác khác).
    st.session_state.hub_train_run_id = f"{datetime.now().timestamp()}_{target_col}"
    st.session_state.hub_benchmark_df = update_hub_benchmark_and_build_comparison(
        st.session_state.hub_results,
        st.session_state.hub_type,
        target_col,
    )
    wh.log_activity(
        "Huấn luyện (ML Hub)",
        f"Đã huấn luyện {len(models_to_run)} mô hình",
        {"cv": cv_folds_val, "test_size": test_size_val},
    )
    # Lưu Candidate NGAY sau khi train — trước đây việc lưu nằm trong panel con
    # "Cấu hình & Huấn luyện" của tab Dự đoán > Nhập tay, nên Model Registry chỉ
    # có bản ghi nếu panel đó được render.
    save_session_candidates(wh, selected_features)


def save_session_candidates(wh, selected_features):
    """Lưu toàn bộ model của lượt train hiện tại vào Kho ở trạng thái Candidate
    (auto_promote=False — Admin vẫn là người Promote lên Production). Chỉ lưu
    1 lần cho mỗi `hub_train_run_id`. Trả số model đã lưu."""
    run_id = st.session_state.get("hub_train_run_id")
    if not wh or not run_id or st.session_state.get("_hub_autosaved_run_id") == run_id:
        return 0
    pipelines = st.session_state.get("hub_pipelines") or {}
    results = st.session_state.get("hub_results") or {}
    hub_type = st.session_state.get("hub_type")
    best_name = pick_best_model_name(results, hub_type)
    saved = 0
    for name, pipeline in pipelines.items():
        try:
            wh.save_model_training(
                dataset_id=st.session_state.get("current_dataset_id", "unknown"),
                model_pipeline=pipeline,
                model_name=name,
                feature_cols=resolve_saved_feature_cols(selected_features),
                target_col=st.session_state.get("hub_target_col"),
                metrics=results.get(name, {}),
                class_labels=st.session_state.get("hub_labels") if hub_type == "clf" else None,
                is_best=(name == best_name),
                auto_promote=False,
            )
            saved += 1
        except Exception as e:
            from dss.core.logging_config import get_logger

            get_logger(__name__).warning("Không lưu được candidate '%s': %s", name, e)
    st.session_state._hub_autosaved_run_id = run_id
    st.session_state.hub_saved_candidate_count = saved
    return saved


def preview_feature_importance(df, feature_cols, target_col):
    """Ước lượng nhanh mức độ quan trọng của từng feature đối với `target_col`
    bằng 1 RandomForestRegressor TẠM THỜI — chỉ phục vụ khám phá dữ liệu (tab
    Khám phá), KHÔNG lưu, KHÔNG đăng ký vào Model Registry, KHÔNG phải model
    dùng để dự đoán. Trước đây đoạn `.fit()`/`RandomForestRegressor` này nằm
    trực tiếp trong `dss/tabs/eda.py` — tách ra đây để UI chỉ còn gọi service,
    không tự thực hiện tính toán ML. GIỮ NGUYÊN thuật toán/tham số cũ
    (n_estimators=100, random_state=42) — không đổi kết quả vì refactor.

    Trả về DataFrame ['Feature', 'Importance (%)'], sắp xếp giảm dần.
    """
    from sklearn.ensemble import RandomForestRegressor

    X = df[feature_cols].fillna(df[feature_cols].mean())
    y = df[target_col].fillna(df[target_col].mean())

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X, y)

    return pd.DataFrame(
        {
            "Feature": feature_cols,
            "Importance (%)": (model.feature_importances_ * 100).round(2),
        }
    ).sort_values("Importance (%)", ascending=False)


def run_preview_benchmark(df, selected_features, target_col, problem_type):
    """Benchmark nhanh (cross-validation) chất lượng 1 bộ Target/Features TRƯỚC
    khi huấn luyện chính thức — KHÔNG lưu, KHÔNG đăng ký vào Model Registry.

    QUY TẮC ĐÁNH GIÁ (EVALUATION GOVERNANCE):
    - Đây là đánh giá thăm dò nhanh (EXPLORATORY ONLY), không phải đánh giá
      Production chính thức (không thay thế cho test set evaluation chưa chạm).
    - Sử dụng ColumnTransformer tiền xử lý bên trong Pipeline để chống rò rỉ dữ liệu trong CV
      (thay vì pd.get_dummies toàn bộ dataset trước CV).
    """
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder

    from dss.config import _make_safe_cv_strategy
    from dss.core.data_helpers import create_shared_preprocessor

    X = df[selected_features].copy()
    y = df[target_col].copy()

    numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()
    preprocessor = create_shared_preprocessor(numeric_features, categorical_features)

    if problem_type == "Phân loại (Classification)":
        if y.dtype == "object" or y.dtype.name == "category":
            y_encoded = LabelEncoder().fit_transform(y.astype(str))
        else:
            y_encoded = y
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        pipeline = Pipeline([('preprocessor', preprocessor), ('model', model)])
        cv_strategy = _make_safe_cv_strategy(y_encoded, desired_folds=3, is_classification=True)
        scores = cross_val_score(pipeline, X, y_encoded, cv=cv_strategy, scoring="accuracy")
        metric_name = "Accuracy"
    else:
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        pipeline = Pipeline([('preprocessor', preprocessor), ('model', model)])
        cv_strategy = _make_safe_cv_strategy(y, desired_folds=3, is_classification=False)
        scores = cross_val_score(pipeline, X, y, cv=cv_strategy, scoring="r2")
        metric_name = "R2 Score"

    return {
        "metric_name": metric_name,
        "mean": float(scores.mean()),
        "std": float(scores.std()),
        "evaluation_type": "exploratory_only",
        "description": "Exploratory preview benchmark only - not for production claims",
    }


def model_lifecycle_badge_text(model: dict) -> str:
    """Audit 2026-09-15 (Issue MODELREG-001): warehouse.py::save_model_training
    /set_production_model ĐÃ ghi đúng 3 giá trị status ('candidate' | 'production'
    | 'archived') từ trước — UI trước đây chỉ đọc field nhị phân `is_production`
    nên gộp 'candidate' (chưa từng được duyệt) và 'archived' (từng là Production,
    đã bị thay thế) thành cùng 1 nhãn "Lưu trữ", làm mất đúng thông tin đã có sẵn
    trong dữ liệu. Record CŨ (trước khi field `status` tồn tại) không có key này
    — fallback về is_production để không phân loại sai dữ liệu lịch sử.

    Điểm gọi DUY NHẤT nên dùng ở mọi nơi hiển thị trạng thái model (warehouse_tab.py,
    admin_reports.py...) để không lệch nhau giữa các trang."""
    status = model.get("status")
    if status == "production" or model.get("is_production"):
        return "⭐ Production"
    if status == "candidate":
        return "🕓 Chờ duyệt (Candidate)"
    if status == "archived":
        return "🗂️ Lưu trữ (đã thay thế)"
    return "🗂️ Lưu trữ"  # record cũ thiếu field `status` — không suy diễn thêm


def resolve_production_for_prediction(wh, dataset_id, target_col):
    """Nguồn DUY NHẤT mà các tab Dự đoán (Nhập tay/Từ file/Hàng loạt) dùng để lấy
    model — luôn tra Model Registry (`model_registry.resolve_production`), KHÔNG
    bao giờ đọc `st.session_state.hub_pipelines` (vốn chỉ phản ánh lượt train/so
    sánh gần nhất của phiên hiện tại, có thể không phải bản Admin đã duyệt).

    Trả về dict {"status", "message", "pipeline", "feature_cols", "target_col",
    "model_name", "class_labels", "hub_type", "training_id", "version",
    "metrics"} khi status="ok"; các field model-specific là None khi status
    khác "ok".
    """
    from dss.services import model_registry

    _empty = {
        "pipeline": None,
        "feature_cols": None,
        "target_col": target_col,
        "model_name": None,
        "class_labels": None,
        "hub_type": None,
        "training_id": None,
        "version": None,
        "metrics": None,
    }

    result = model_registry.resolve_production(wh, dataset_id, target_col)
    if result["status"] != "ok":
        return {"status": result["status"], "message": result["message"], **_empty}

    meta = result["metadata"] or {}
    pipeline = result["pipeline"]
    metrics = meta.get("metrics") or {}
    if metrics.get("type") == "clustering":
        return {
            "status": "error",
            "message": "Bản Production hiện tại là mô hình phân cụm (KMeans), không dùng để dự đoán Target được.",
            **_empty,
        }

    # Cùng heuristic đã dùng ở warehouse_tab.py ("Sử dụng Mô hình này"): ưu tiên
    # đọc thẳng từ khoá metrics đặc trưng phân loại, chỉ fallback sang kiểm tra
    # predict_proba khi model cũ chưa lưu đủ các khoá này.
    is_clf = any(k in metrics for k in ("Accuracy", "F1 Score", "Precision", "Recall"))
    if not is_clf:
        model_step = getattr(pipeline, "named_steps", {}).get("model")
        is_clf = hasattr(model_step, "predict_proba")

    return {
        "status": "ok",
        "message": result["message"],
        "pipeline": pipeline,
        "feature_cols": list(meta.get("feature_cols") or []),
        "target_col": meta.get("target_col", target_col),
        "model_name": meta.get("model_name"),
        "class_labels": meta.get("class_labels"),
        "hub_type": "clf" if is_clf else "reg",
        "training_id": meta.get("training_id"),
        "version": meta.get("version"),
        "metrics": metrics,
    }


def resolve_model_for_prediction(wh, dataset_id, target_col, role=None):
    """Model dùng cho các tab Dự đoán.

    - Luôn ưu tiên bản Production trong Model Registry (giống
      resolve_production_for_prediction) — với Sinh viên đây là nguồn DUY NHẤT.
    - Giảng viên/Admin: nếu target CHƯA có Production dùng được, rơi về mô hình
      tốt nhất vừa train trong phiên (cùng target) để Giảng viên dự đoán/kiểm thử
      ngay, gắn source="session" để UI ghi rõ "chưa được Admin duyệt".

    Trả về cùng shape với resolve_production_for_prediction, thêm khoá "source"
    ("production" | "session" | None).
    """
    resolved = resolve_production_for_prediction(wh, dataset_id, target_col)
    if resolved["status"] == "ok":
        return {**resolved, "source": "production"}
    if role == "Sinh viên":
        return {**resolved, "source": None}

    pipelines = st.session_state.get("hub_pipelines") or {}
    hub_type = st.session_state.get("hub_type")
    if not pipelines or st.session_state.get("hub_target_col") != target_col or hub_type not in ("clf", "reg"):
        return {**resolved, "source": None}
    best_name = pick_best_model_name(st.session_state.get("hub_results") or {}, hub_type)
    if best_name not in pipelines:
        return {**resolved, "source": None}
    return {
        "status": "ok",
        "message": "Chưa có bản Production — đang dùng mô hình tốt nhất vừa huấn luyện trong phiên.",
        "pipeline": pipelines[best_name],
        "feature_cols": resolve_saved_feature_cols(st.session_state.get("hub_feats") or []),
        "target_col": target_col,
        "model_name": best_name,
        "class_labels": st.session_state.get("hub_labels") if hub_type == "clf" else None,
        "hub_type": hub_type,
        "training_id": None,
        "version": None,
        "metrics": (st.session_state.get("hub_results") or {}).get(best_name),
        "source": "session",
    }


def describe_prediction_model(resolved) -> str:
    """Một dòng mô tả model đang dùng để dự đoán (cho Giảng viên/Admin)."""
    if resolved.get("source") == "session":
        return (
            f"Mô hình đang dùng: **{resolved['model_name']}** — vừa huấn luyện trong phiên, "
            "**chưa được Admin duyệt lên Production** (chỉ Giảng viên thấy; Sinh viên/Dashboard "
            "vẫn chờ bản Production)."
        )
    return f"Mô hình đang dùng (Production — Model Registry): **{resolved['model_name']}** (v{resolved['version']})."


def compute_lecturer_dashboard_overview(df, wh, dataset_id, target_col, gpa_reference_col=None):
    """Tổng quan lớp học cho Lecturer Dashboard — dự đoán cho TOÀN BỘ lớp bằng
    ĐÚNG bản Production hiện tại (`resolve_production_for_prediction`, Model
    Registry — không train/predict rời rạc riêng cho dashboard này), rồi phân
    loại rủi ro theo phân vị của cột điểm tham chiếu trong CHÍNH dataset đang
    dùng — cùng cách đã dùng cho tư vấn AI cá nhân từng sinh viên (xem
    `ai_advisor.py`: phân vị 25%/50%, không phải ngưỡng GPA tuyệt đối, vì
    thang điểm dữ liệu có thể khác nhau).

    Chỉ hỗ trợ bài toán HỒI QUY (dự đoán điểm số liên tục) — target phân loại
    không có ngữ nghĩa "phân vị điểm số" rõ ràng để suy ra rủi ro, nên trả lỗi
    rõ ràng thay vì đoán bừa.

    Trả về dict:
      status: "ok" | "empty" | "error"
      message
      model_name, version, metric_name, metric_value (từ Model Registry)
      avg_predicted, risk_counts {"cao","trung bình","thấp"}
      high_risk_students: list[{id, current, predicted, top_factor}]
    """
    resolved = resolve_production_for_prediction(wh, dataset_id, target_col)
    if resolved["status"] != "ok":
        return {"status": resolved["status"], "message": resolved["message"]}

    if resolved["hub_type"] != "reg":
        return {
            "status": "error",
            "message": (
                "Dashboard rủi ro theo lớp hiện chỉ hỗ trợ bài toán hồi quy (dự đoán điểm số "
                "liên tục) — bản Production hiện tại là mô hình phân loại."
            ),
        }

    pipeline = resolved["pipeline"]
    feature_cols = resolved["feature_cols"]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        return {
            "status": "error",
            "message": f"Dataset hiện tại thiếu cột mà mô hình Production cần: {', '.join(missing)}",
        }

    try:
        raw_preds = pipeline.predict(df[feature_cols])
    except Exception as e:
        return {"status": "error", "message": f"Lỗi khi dự đoán: {e}"}

    gpa_ref_col = gpa_reference_col if gpa_reference_col in df.columns else resolved["target_col"]
    if gpa_ref_col not in df.columns:
        gpa_ref_col = None

    ref_series = df[gpa_ref_col].dropna() if gpa_ref_col else pd.Series(dtype=float)
    if len(ref_series) >= 5:
        q25, q50 = ref_series.quantile(0.25), ref_series.quantile(0.5)
    else:
        q25 = q50 = None

    def _classify(pred_value):
        if q25 is None:
            return "trung bình"
        if pred_value <= q25:
            return "cao"
        if pred_value <= q50:
            return "trung bình"
        return "thấp"

    id_col = next((c for c in df.columns if is_id_like(c)), df.columns[0])
    overall_avg = df[feature_cols].mean(numeric_only=True)

    risk_counts = {"cao": 0, "trung bình": 0, "thấp": 0}
    high_risk_rows = []
    for i in range(len(df)):
        pred_val = float(raw_preds[i])
        risk = _classify(pred_val)
        risk_counts[risk] += 1
        if risk == "cao":
            row = df.iloc[i]
            diffs = {}
            for f in feature_cols:
                v = row.get(f)
                avg = overall_avg.get(f)
                if pd.notna(v) and pd.notna(avg) and avg not in (0, None):
                    diffs[f] = (float(v) - float(avg)) / float(avg)
            top_factor = min(diffs, key=diffs.get) if diffs else None
            high_risk_rows.append(
                {
                    "id": row.get(id_col),
                    "current": row.get(gpa_ref_col) if gpa_ref_col else None,
                    "predicted": pred_val,
                    "top_factor": top_factor,
                }
            )

    high_risk_rows.sort(key=lambda r: r["predicted"])

    metrics = resolved.get("metrics") or {}
    metric_name = "R2 Score" if "R2 Score" in metrics else next(iter(metrics), None)
    metric_value = metrics.get(metric_name) if metric_name else None

    return {
        "status": "ok",
        "message": resolved["message"],
        "model_name": resolved["model_name"],
        "version": resolved["version"],
        "target_col": gpa_ref_col or resolved["target_col"],
        "metric_name": metric_name,
        "metric_value": metric_value,
        "avg_predicted": float(np.mean(raw_preds)) if len(raw_preds) else None,
        "risk_counts": risk_counts,
        "high_risk_students": high_risk_rows,
        # Toàn bộ giá trị dự đoán từng sinh viên (đã tính ở trên, KHÔNG tính lại) —
        # phục vụ biểu đồ phân bố (donut) ở Lecturer Home mà không cần dashboard
        # tự gọi lại pipeline.predict() lần 2.
        "predicted_values": [float(v) for v in raw_preds],
        # pipeline/feature_cols của bản Production ĐÃ RESOLVE ở trên — trả thêm
        # ra ngoài để Dashboard đọc feature_importances_ thật (xem
        # get_production_feature_importance) mà KHÔNG cần tự gọi lại
        # resolve_production_for_prediction() lần 2 (tránh tra Model Registry 2 lần).
        "pipeline": pipeline,
        "feature_cols": feature_cols,
    }


def classify_relative_risk(value, reference_series):
    """Mức rủi ro TƯƠNG ĐỐI dùng chung cho Trang chủ Sinh viên và Tư vấn AI:
    so `value` với phân vị 25%/50% của `reference_series` trong CHÍNH dữ liệu
    lớp hiện tại. Trả về "cao" / "trung bình" / "thấp", hoặc None khi không đủ
    dữ liệu tham chiếu (< 5 giá trị) hay `value` không phải số."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    ref = pd.Series(reference_series).dropna()
    if len(ref) < 5:
        return None
    q25, q50 = ref.quantile(0.25), ref.quantile(0.5)
    return "cao" if value <= q25 else ("trung bình" if value <= q50 else "thấp")


def student_risk_profile(wh, dataset_id, target_col, df, student_row):
    """Điểm căn cứ + mức rủi ro tương đối của 1 sinh viên — DÙNG CHUNG cho mọi
    nơi hiển thị rủi ro cá nhân (Trang chủ Sinh viên, Tư vấn AI) để 2 trang luôn
    cho cùng 1 kết quả. Căn cứ là dự đoán của bản Production (source="model")
    hoặc, khi chưa có, điểm hiện tại (source="observed" — KHÔNG gọi là dự đoán)."""
    info = predict_for_student(wh, dataset_id, target_col, student_row)
    info["risk_level"] = classify_relative_risk(info.get("value"), df[target_col]) if target_col in df.columns else None
    return info


def predict_for_student(wh, dataset_id, target_col, student_row):
    """K-3: "Điểm dự đoán" cho 1 sinh viên (Tư vấn AI) — nguồn DUY NHẤT được
    phép gọi là "dự đoán" là bản Production hồi quy hiện tại
    (`resolve_production_for_prediction`, giống `compute_lecturer_dashboard_overview`
    dùng cho Dashboard, để 2 nơi luôn thống nhất). TUYỆT ĐỐI KHÔNG được đọc thẳng
    cột target thật (vd. diem_ky_sau) từ dữ liệu rồi gọi đó là "dự đoán" — cột đó
    là đáp án thật trong dữ liệu mô phỏng, không phải kết quả suy luận của mô hình.

    Trả về dict:
      value: giá trị số (thang điểm 10)
      source: "model" (đã qua pipeline.predict) hoặc "observed" (chưa có Production
              phù hợp — dùng điểm hiện tại làm căn cứ tạm, KHÔNG phải dự đoán)
      model_name, version: chỉ khác None khi source="model"
    """
    resolved = resolve_production_for_prediction(wh, dataset_id, target_col)
    if resolved["status"] == "ok" and resolved["hub_type"] == "reg":
        feature_cols = resolved["feature_cols"] or []
        if feature_cols and all(c in student_row.index for c in feature_cols):
            try:
                row_df = pd.DataFrame([student_row[feature_cols]])
                value = float(resolved["pipeline"].predict(row_df)[0])
                return {
                    "value": value,
                    "source": "model",
                    "model_name": resolved["model_name"],
                    "version": resolved["version"],
                }
            except Exception:
                pass

    # Không có bản Production hồi quy dùng được -> dùng điểm HIỆN TẠI làm căn cứ
    # tạm (KHÔNG BAO GIỜ dùng target_col thật, kể cả khi nó có mặt trong dữ liệu).
    from dss.core.target_utils import get_leaky_target_columns

    forbidden = {str(c).lower() for c in get_leaky_target_columns(target_col)}
    forbidden.add(str(target_col).lower())
    observed_col = None
    for cand in ("diem_ky_nay", "gpa_previous", "prior_gpa"):
        if cand in student_row.index and cand.lower() not in forbidden and pd.notna(student_row.get(cand)):
            observed_col = cand
            break
    if observed_col is None:
        # Không có căn cứ nào: trả None, KHÔNG trả 0.0 (trước đây giao diện và prompt LLM coi như GPA 0 = rủi ro cao).
        return {"value": None, "source": "unavailable", "model_name": None, "version": None}
    raw_value = float(student_row[observed_col])
    # gpa_previous có thể ở thang 4 — quy đổi về thang 10 để cùng đơn vị với target.
    if observed_col in ("gpa_previous", "prior_gpa") and raw_value <= 4.0:
        raw_value *= 2.5
    return {"value": raw_value, "source": "observed", "model_name": None, "version": None}


def compute_progress_note(current_value, student_row):
    """K-4: so sánh "tiến bộ" — current_value (điểm dự đoán/hiện tại, LUÔN thang
    10, xem `predict_for_student`) với điểm kỳ trước. Ưu tiên `diem_ky_nay` (đã ở
    thang 10, không cần quy đổi); chỉ dùng `gpa_previous` (thang 4) khi không có
    `diem_ky_nay`, và PHẢI quy đổi về thang 10 trước khi so sánh. So sánh lệch
    thang (vd. thang 10 với thang 4) khiến gần như MỌI sinh viên đều hiện ra
    "đang cải thiện" một cách giả tạo.

    Trả về (delta, progress_note_text). delta=None nếu không có dữ liệu kỳ trước.
    """
    prev_value = None
    if "diem_ky_nay" in student_row.index and pd.notna(student_row.get("diem_ky_nay")):
        prev_value = float(student_row["diem_ky_nay"])
    elif "gpa_previous" in student_row.index and pd.notna(student_row.get("gpa_previous")):
        raw = float(student_row["gpa_previous"])
        prev_value = raw * 2.5 if raw <= 4.0 else raw

    if prev_value is None:
        return None, "chưa có dữ liệu GPA kỳ trước"

    delta = float(current_value) - prev_value
    if delta > 0.15:
        return delta, f"đang cải thiện (+{delta:.2f} điểm so với kỳ trước)"
    if delta < -0.15:
        return delta, f"có dấu hiệu giảm ({delta:.2f} điểm so với kỳ trước)"
    return delta, "ổn định, chưa thay đổi đáng kể so với kỳ trước"


def resolve_predicted_output_col(df, target_col):
    """
    Tìm cột dự đoán trong DataFrame kết quả batch/file.
    Tránh KeyError khi đổi target hoặc còn session_state cũ.
    """
    if df is None or not hasattr(df, "columns") or target_col is None:
        return None
    preferred = f"Predicted_{target_col}"
    if preferred in df.columns:
        return preferred
    t_low = str(target_col).lower()
    for c in df.columns:
        s = str(c)
        if s.lower() == f"predicted_{t_low}":
            return c
    for c in df.columns:
        if str(c).startswith("Predicted_"):
            return c
    return None


def resolve_hub_train_config(train_config):
    """Ưu tiên config hiện tại; fallback từ `hub_*` khi nạp model từ Kho dữ liệu."""
    if isinstance(train_config, dict) and train_config.get("target_col") and train_config.get("selected_features"):
        return train_config

    target_col = st.session_state.get("hub_target_col")
    feats = st.session_state.get("hub_feats")
    hub_type = st.session_state.get("hub_type")
    if target_col and isinstance(feats, list) and feats:
        if hub_type == "clf":
            problem_type = "Phân loại (Classification)"
        elif hub_type == "reg":
            problem_type = "Hồi quy (Regression)"
        else:
            problem_type = "Unknown"
        return {
            "target_col": target_col,
            "selected_features": feats,
            "problem_type": problem_type,
        }
    return None


def assoc_strength(a: pd.Series, b: pd.Series) -> float:
    """Độ liên kết 0..1 giữa 2 cột, không phụ thuộc thứ tự mã hoá categorical.

    Dùng thước đo phù hợp theo kiểu dữ liệu thay vì ép LabelEncoder rồi tính Pearson —
    LabelEncoder gán số theo thứ tự bảng chữ cái nên phá vỡ quan hệ thứ tự của biến phân
    loại (vd. "Yếu"<"Giỏi" theo abc chứ không theo học lực), khiến 1 cột phân loại suy ra
    TRỰC TIẾP từ target (như xep_loai = pd.cut(diem_ky_sau)) vẫn bị tính ra tương quan
    thấp giả tạo và lọt qua kiểm tra.
    """
    a_num = pd.api.types.is_numeric_dtype(a)
    b_num = pd.api.types.is_numeric_dtype(b)
    if a_num and b_num:
        c = a.corr(b)
        return abs(c) if pd.notna(c) else 0.0
    if a_num != b_num:
        num_s, cat_s = (a, b) if a_num else (b, a)
        tmp = pd.DataFrame({"num": pd.to_numeric(num_s, errors="coerce"), "cat": cat_s}).dropna()
        if tmp.empty or tmp["cat"].nunique() < 2:
            return 0.0
        overall_mean = tmp["num"].mean()
        ss_total = ((tmp["num"] - overall_mean) ** 2).sum()
        if ss_total == 0:
            return 0.0
        ss_between = tmp.groupby("cat")["num"].apply(lambda g: len(g) * (g.mean() - overall_mean) ** 2).sum()
        return float(min(1.0, max(0.0, ss_between / ss_total)) ** 0.5)
    # cả 2 đều categorical -> Cramér's V (chi-square)
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if tmp.empty or tmp["a"].nunique() < 2 or tmp["b"].nunique() < 2:
        return 0.0
    try:
        from scipy.stats import chi2_contingency

        ct = pd.crosstab(tmp["a"], tmp["b"])
        chi2 = chi2_contingency(ct)[0]
        n = ct.to_numpy().sum()
        r, k = ct.shape
        denom = n * (min(r, k) - 1)
        return float((chi2 / denom) ** 0.5) if denom > 0 else 0.0
    except Exception:
        return 0.0


def find_leaky_feature_cols(df: pd.DataFrame, target_col: str, id_cols: list, threshold: float = 0.95) -> list:
    """Tìm các cột gắn kết gần như tuyệt đối với Target hoặc là alias/derived target (rò rỉ dữ liệu),
    nhưng KHÔNG loại bỏ các feature dự báo hợp lệ như `diem_ky_nay`."""
    if target_col not in df.columns:
        return []
    from dss.core.target_utils import LEGITIMATE_PREDICTORS, get_leaky_target_columns

    leaky_cols = set()

    # 1. Cột mục tiêu cấm theo quy chuẩn alias/derived target
    forbidden = get_leaky_target_columns(target_col)
    for col in df.columns:
        if col != target_col and (col.lower() in forbidden or col in forbidden):
            leaky_cols.add(col)

    # 2. Kiểm tra tương quan/liên kết thống kê
    target_series = df[target_col]
    try:
        for col in df.columns:
            if col == target_col or col in id_cols or col in leaky_cols:
                continue
            if col.lower() in LEGITIMATE_PREDICTORS:
                # Không bao giờ lọc các biến dự báo hợp lệ (như diem_ky_nay)
                continue
            col_series = df[col]
            if not pd.api.types.is_numeric_dtype(col_series) and col_series.nunique(dropna=True) > 50:
                continue  # cột text tự do — bỏ qua
            if assoc_strength(target_series, col_series) >= threshold:
                leaky_cols.add(col)
    except Exception:
        pass
    return list(leaky_cols)


def training_target_change_handler(key_prefix: str, all_cols: list) -> None:
    """Đồng bộ target khám phá + reset Features khi đổi Target (tránh widget key gắn theo tên cột)."""
    val = st.session_state.get(f"{key_prefix}_target")
    if not val:
        return
    st.session_state.target_for_analysis = val
    st.session_state.target_corr_select = val
    st.session_state.target_imp_select = val
    av = [c for c in all_cols if c != val]
    id_cols = [c for c in all_cols if is_id_like(c) or "name" in str(c).lower()]
    leaky_cols = []
    _cur_df = st.session_state.get("current_df")
    if isinstance(_cur_df, pd.DataFrame) and val in _cur_df.columns:
        leaky_cols = find_leaky_feature_cols(_cur_df, val, id_cols)
    else:
        from dss.core.target_utils import get_leaky_target_columns

        leaky_cols = list(get_leaky_target_columns(val))
    exclude_cols = set(id_cols + ["grade", "pass_fail", "status", "result"] + leaky_cols)
    st.session_state[f"{key_prefix}_features_pick"] = [c for c in av if c not in exclude_cols]


def training_target_widget_callback() -> None:
    """Callback ổn định cho selectbox Target (không dùng lambda mỗi lần rerun)."""
    kp = st.session_state.get("_training_target_cb_prefix")
    if not kp:
        return
    cols = st.session_state.get(f"{kp}_all_cols_snapshot")
    if cols is None:
        return
    training_target_change_handler(kp, list(cols))
