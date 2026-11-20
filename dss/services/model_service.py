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


_SHAP_TREE_MODEL_NAMES = {
    'RandomForestClassifier',
    'RandomForestRegressor',
    'GradientBoostingClassifier',
    'GradientBoostingRegressor',
    'XGBClassifier',
    'XGBRegressor',
    'LGBMClassifier',
    'LGBMRegressor',
    'DecisionTreeClassifier',
    'DecisionTreeRegressor',
    'ExtraTreesClassifier',
    'ExtraTreesRegressor',
}


def _resolve_shap_feature_names(preprocessor, feature_names, n_fallback):
    """Lấy tên cột SAU tiền xử lý để gắn nhãn cho các giá trị SHAP đã tính —
    THUẦN NHÃN HIỂN THỊ, không ảnh hưởng đến giá trị SHAP số học. `ColumnTransformer.
    get_feature_names_out(feature_names)` (truyền tên cột GỐC) hay ném
    `ValueError: input_features is not equal to feature_names_in_` vì thứ tự/tập
    cột truyền vào không khớp tuyệt đối với lúc fit — trong khi gọi KHÔNG tham số
    vẫn trả đúng tên (ColumnTransformer tự nhớ cột đã fit). Ưu tiên thử không
    tham số trước; chỉ rơi về "Feature N" khi cả 2 cách đều lỗi (vd. preprocessor
    không phải API sklearn chuẩn). Bỏ tiền tố kỹ thuật "num__"/"cat__"/"remainder__"
    của ColumnTransformer để hiển thị đúng tên cột gốc cho người dùng cuối."""
    try:
        names = list(preprocessor.get_feature_names_out())
    except Exception:
        try:
            names = list(preprocessor.get_feature_names_out(feature_names))
        except Exception:
            return [f"Feature {i}" for i in range(n_fallback)]
    return [n.split("__", 1)[1] if "__" in n else n for n in names]


def _shap_input_transformer(pipeline):
    """Toàn bộ các bước TRƯỚC 'model' (preprocessor -> feature_selection...) dưới dạng 1
    Pipeline chỉ-transform, bỏ bước sinh mẫu (SMOTE/ADASYN: chỉ chạy lúc fit, không có
    transform). Trước đây SHAP chỉ chạy preprocessor rồi đưa thẳng vào model, bỏ qua bước
    chọn đặc trưng (MI/RFE) -> model nhận sai số cột (lỗi shape) hoặc tên cột lệch."""
    from sklearn.pipeline import Pipeline as _SkPipeline

    steps = [
        (name, step)
        for name, step in pipeline.steps[:-1]
        if step is not None and step != "passthrough" and not hasattr(step, "fit_resample")
    ]
    if len(steps) == 1:
        return steps[0][1]
    return _SkPipeline(steps)


def compute_shap_local_explanation(pipeline, input_df, background_data, feature_names, problem_type="classification"):
    """Tính SHAP values cho 1 dòng dữ liệu (local explanation) — THUẦN TÍNH
    TOÁN, không vẽ biểu đồ. Trước đây nằm lẫn với code render trong
    `dss/tabs/ml_hub.py:render_shap_explanation` — tách phần tính toán ra đây
    theo yêu cầu refactor (UI chỉ còn gọi service rồi vẽ). GIỮ NGUYÊN toàn bộ
    logic/fallback cũ, không đổi kết quả.

    Trả về (shap_val, error_message) — shap_val=None kèm error_message khi
    không tính được (thiếu thư viện, pipeline không đúng chuẩn, lỗi khi tính).
    """
    try:
        import shap
    except ImportError:
        return None, "Thư viện `shap` chưa được cài (pip install shap)."

    try:
        model = pipeline.named_steps.get('model')
        preprocessor = pipeline.named_steps.get('preprocessor')
        if not model or not preprocessor:
            return None, "Pipeline không theo chuẩn chung (thiếu 'model' hoặc 'preprocessor'). Không thể dùng SHAP."

        transformer = _shap_input_transformer(pipeline)
        input_transformed = transformer.transform(input_df)
        background_transformed = transformer.transform(background_data)

        if background_transformed.shape[0] > 100:
            background_transformed = shap.sample(background_transformed, 100)

        feature_names_out = _resolve_shap_feature_names(transformer, feature_names, input_transformed.shape[1])

        if type(model).__name__ in _SHAP_TREE_MODEL_NAMES:
            explainer = shap.TreeExplainer(model)
        elif problem_type == "classification" and hasattr(model, "predict_proba"):
            # X-1: giải thích XÁC SUẤT (predict_proba), KHÔNG PHẢI nhãn rời rạc
            # (predict) — dùng .predict() làm hàm mục tiêu cho SHAP với phân loại
            # khiến shap values phản ánh biến động của mã số nhãn (không có ý
            # nghĩa định lượng liên tục), không phải mức đóng góp vào xác suất.
            explainer = shap.KernelExplainer(lambda x: model.predict_proba(np.asarray(x)), background_transformed)
        else:
            explainer = shap.KernelExplainer(lambda x: model.predict(np.asarray(x)), background_transformed)

        shap_values = explainer(input_transformed)

        if problem_type == "classification" and len(shap_values.shape) == 3:
            pred = model.predict(input_transformed)[0]
            if hasattr(model, "classes_"):
                classes_list = list(model.classes_)
                if pred in classes_list:
                    pred_class_index = classes_list.index(pred)
                elif isinstance(pred, (int, np.integer)) and 0 <= int(pred) < shap_values.shape[2]:
                    pred_class_index = int(pred)
                else:
                    pred_class_index = 0
            elif isinstance(pred, (int, np.integer)) and 0 <= int(pred) < shap_values.shape[2]:
                pred_class_index = int(pred)
            else:
                pred_class_index = 0
            shap_val = shap_values[:, :, pred_class_index]
        else:
            shap_val = shap_values

        try:
            shap_val.feature_names = list(feature_names_out)
        except Exception:
            pass

        return shap_val, None
    except Exception as e:
        return None, f"Không thể tính SHAP cho mô hình này: {e!s}"


def compute_shap_summary(pipeline, background_data, feature_names, problem_type="classification", class_idx=None):
    """Tính SHAP values toàn cục (summary/beeswarm).

    HỖ TRỢ ĐA LỚP (MULTI-CLASS SUPPORT):
    - Không mặc định luôn lấy class 1.
    - Cho phép chọn class cụ thể qua `class_idx`.
    - Khi có nhiều hơn 2 lớp và class_idx=None, tổng hợp trung bình độ lớn tuyệt đối
      qua tất cả các lớp (mean absolute impact), hoặc trích xuất đúng lát cắt của lớp đã chọn.
    """
    try:
        import shap
    except ImportError:
        return None, "Thư viện `shap` chưa được cài (pip install shap)."

    try:
        model = pipeline.named_steps.get('model')
        preprocessor = pipeline.named_steps.get('preprocessor')
        if not model or not preprocessor:
            return None, "Pipeline không theo chuẩn chung. Không thể dùng SHAP."

        transformer = _shap_input_transformer(pipeline)
        background_transformed = transformer.transform(background_data)

        feature_names_out = _resolve_shap_feature_names(transformer, feature_names, background_transformed.shape[1])

        if type(model).__name__ in _SHAP_TREE_MODEL_NAMES:
            explainer = shap.TreeExplainer(model)
        elif problem_type == "classification" and hasattr(model, "predict_proba"):
            # X-1: xem giải thích ở compute_shap_local_explanation phía trên.
            sample_data = shap.sample(background_transformed, 50)
            explainer = shap.KernelExplainer(lambda x: model.predict_proba(np.asarray(x)), sample_data)
        else:
            sample_data = shap.sample(background_transformed, 50)
            explainer = shap.KernelExplainer(lambda x: model.predict(np.asarray(x)), sample_data)

        shap_values = explainer(background_transformed)

        if problem_type == "classification" and len(shap_values.shape) == 3:
            n_classes = shap_values.shape[2]
            if class_idx is not None and 0 <= int(class_idx) < n_classes:
                shap_val = shap_values[:, :, int(class_idx)]
            elif n_classes == 2:
                shap_val = shap_values[:, :, 1]
            else:
                # Multi-class (>2 lớp, ví dụ 5 lớp: Yếu / Trung bình / Khá / Giỏi / Xuất sắc):
                # Tổng hợp trung bình độ lớn tuyệt đối ảnh hưởng của từng feature
                try:
                    import copy

                    shap_val = copy.deepcopy(shap_values[:, :, 0])
                    shap_val.values = np.abs(shap_values.values).mean(axis=-1)
                    if hasattr(shap_values, 'base_values') and shap_values.base_values is not None:
                        shap_val.base_values = np.mean(shap_values.base_values, axis=-1)
                except Exception:
                    shap_val = shap_values[:, :, 0]
        else:
            shap_val = shap_values

        try:
            shap_val.feature_names = list(feature_names_out)
        except Exception:
            pass

        return shap_val, None
    except Exception as e:
        return None, f"Không thể tính SHAP cho mô hình này: {e!s}"


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


def get_production_feature_importance(pipeline, feature_cols, top_n=8):
    """Đọc mức độ quan trọng đặc trưng TỪ CHÍNH mô hình Production đã huấn
    luyện sẵn (`estimator.feature_importances_`) — KHÔNG fit thêm bất kỳ mô
    hình nào (khác hẳn `preview_feature_importance()` ở trên vốn fit 1
    RandomForest tạm thời mỗi lần gọi). Dùng cho Dashboard/Home — nơi không
    được phép tự train chỉ vì người dùng mở trang.

    LỖI THỰC TẾ đã sửa: độ dài `feature_importances_` là số cột SAU tiền xử
    lý (`preprocessor`), KHÔNG PHẢI số cột gốc trong `feature_cols` (vd. cột
    hạng mục bị loại/mã hoá lại khiến 12 cột gốc -> 11 cột sau xử lý) — so
    sánh trực tiếp 2 độ dài này làm panel báo "không hỗ trợ" SAI cho cả mô
    hình cây thật sự có chỉ số này. Dùng lại đúng hàm map tên cột sau tiền xử
    lý đã có cho SHAP (`_resolve_shap_feature_names`) thay vì tự so độ dài.

    Trả về DataFrame ['Feature', 'Importance (%)'] (rỗng nếu estimator không
    hỗ trợ feature_importances_, ví dụ LinearRegression/LogisticRegression).
    """
    try:
        model = getattr(pipeline, "named_steps", {}).get("model")
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return pd.DataFrame(columns=["Feature", "Importance (%)"])
        preprocessor = getattr(pipeline, "named_steps", {}).get("preprocessor")
        if preprocessor is not None:
            names = _resolve_shap_feature_names(preprocessor, feature_cols, len(importances))
        else:
            names = (
                list(feature_cols)
                if len(feature_cols) == len(importances)
                else [f"Feature {i}" for i in range(len(importances))]
            )
        _df = pd.DataFrame({"Feature": names, "Importance (%)": (np.asarray(importances) * 100).round(2)}).sort_values(
            "Importance (%)", ascending=False
        )
        return _df.head(top_n)
    except Exception:
        return pd.DataFrame(columns=["Feature", "Importance (%)"])


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


def safe_metric_value(v):
    """Chuẩn hóa metric về float hữu hạn; lỗi -> NaN."""
    try:
        v = float(v)
        if np.isfinite(v):
            return v
    except Exception:
        pass
    return np.nan


def extract_failed_models(results):
    """Lấy danh sách model lỗi train từ results meta."""
    if not isinstance(results, dict):
        return {}
    failed = results.get("__failed_models__", {})
    return failed if isinstance(failed, dict) else {}


def build_metrics_dataframe(results, hub_type):
    """
    Tạo metrics_df chỉ gồm model hợp lệ (lọc bỏ meta/NaN),
    tránh hiển thị model 0.00 giả.
    Ưu tiên hiển thị F1 Score (Macro) cho bài toán phân loại đa lớp.
    """
    rows = []
    for name, m in (results or {}).items():
        if not isinstance(m, dict) or str(name).startswith("__"):
            continue
        if hub_type == "clf":
            acc = safe_metric_value(m.get("Accuracy"))
            f1_weighted = safe_metric_value(m.get("F1 Score (Weighted)", m.get("F1-Score")))
            f1_macro = safe_metric_value(m.get("F1 Score (Macro)", m.get("F1 Macro")))
            if np.isnan(acc):
                continue
            report = m.get("report") if isinstance(m.get("report"), dict) else {}
            macro_avg = report.get("macro avg", {}) if isinstance(report, dict) else {}
            weighted_avg = report.get("weighted avg", {}) if isinstance(report, dict) else {}

            if np.isnan(f1_macro) and isinstance(macro_avg, dict):
                f1_macro = safe_metric_value(macro_avg.get("f1-score"))

            precision_val = safe_metric_value(
                m.get("Precision (Macro)", m.get("Precision (Weighted)", m.get("Precision")))
            )
            recall_val = safe_metric_value(m.get("Recall (Macro)", m.get("Recall (Weighted)", m.get("Recall"))))

            # Fallback: lấy từ classification_report
            if np.isnan(precision_val):
                precision_val = safe_metric_value(macro_avg.get("precision", weighted_avg.get("precision")))
            if np.isnan(recall_val):
                recall_val = safe_metric_value(macro_avg.get("recall", weighted_avg.get("recall")))
            if np.isnan(f1_weighted):
                f1_weighted = safe_metric_value(weighted_avg.get("f1-score", macro_avg.get("f1-score")))

            rows.append(
                {
                    "Model": name,
                    "F1 Score (Macro)": f1_macro if not np.isnan(f1_macro) else f1_weighted,
                    # PR-AUC là tiêu chí CHỌN mô hình khi lớp thiểu số quá ít mẫu
                    # (xem PR_AUC_SELECTION_THRESHOLD trong dss/core/trainers.py).
                    # Tiêu chí dùng để chọn thì phải hiện trong bảng, nếu không
                    # người đọc báo cáo không kiểm lại được lựa chọn.
                    "PR-AUC (Macro)": safe_metric_value(m.get("PR-AUC (Macro)")),
                    "Accuracy": acc,
                    "Precision": precision_val,
                    "Recall": recall_val,
                    "F1 Score (Weighted)": f1_weighted,
                    # Điểm CV (trung bình các fold trên tập TRAIN, đúng tiêu chí GridSearchCV
                    # đã tối ưu) — dùng để CHỌN mô hình, xem resolve_ranking_col.
                    CV_SCORE_COL: safe_metric_value(m.get("cv_mean")),
                }
            )
        else:
            r2 = safe_metric_value(m.get("R2 Score"))
            rmse = safe_metric_value(m.get("RMSE"))
            mae = safe_metric_value(m.get("MAE"))
            # Regression bắt buộc có R2 + ít nhất 1 sai số hợp lệ
            if np.isnan(r2) or (np.isnan(rmse) and np.isnan(mae)):
                continue
            rows.append(
                {
                    "Model": name,
                    "R2 Score": r2,
                    "RMSE": rmse,
                    "MAE": mae,
                    # MAE trung bình CV trên tập TRAIN (tiêu chí tuning) — dùng để CHỌN mô hình.
                    CV_MAE_COL: safe_metric_value(m.get("cv_mean")),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("Model")


CV_SCORE_COL = "CV Score (Train)"
CV_MAE_COL = "CV MAE (Train)"


def _has_complete_cv(metrics_df, col):
    return col in metrics_df.columns and len(metrics_df) > 0 and bool(metrics_df[col].notna().all())


def resolve_ranking_col(metrics_df, hub_type):
    """Cột dùng để xếp hạng model + hướng sắp xếp — DÙNG CHUNG cho MỌI nơi cần biết
    "model nào tốt nhất" (biểu đồ/bảng xếp hạng ở main.py, is_best khi lưu Kho qua
    pick_best_model_name, benchmark, Model Registry). KHÔNG được hard-code lại tiêu
    chí xếp hạng ở nơi khác (S-1) — 2 nơi dùng 2 tiêu chí khác nhau sẽ khiến UI đề
    xuất 1 model còn Kho đánh dấu is_best cho model khác trên CÙNG 1 lượt huấn luyện.
    Với classification: ưu tiên F1 Score (Macro) làm tiêu chí chọn model (đặc biệt khi
    mất cân bằng lớp), fallback sang Accuracy nếu không có. Cả 2 metric vẫn hiển thị song song.

    R-5 (POST_72H_MASTER_PRODUCTION_CLOSURE): với hồi quy, RMSE là PRIMARY ranking
    metric (CỐ Ý khác với MAE dùng để tuning trong trainers.py's GridSearchCV — xem
    comment "HỢP ĐỒNG METRIC TƯỜNG MINH" tại đó) — RMSE phạt sai số lớn nặng hơn,
    phù hợp bài toán cảnh báo rủi ro học tập. MAE/R2 Score là SECONDARY, vẫn hiển
    thị song song. Test: test_regression_metric_contract.py.

    Cập nhật 2026-11: khi MỌI mô hình trong bảng có điểm CV (cv_mean), xếp hạng theo điểm CV
    đó (phân loại: tiêu chí GridSearchCV, cao hơn tốt hơn; hồi quy: CV MAE, thấp hơn tốt hơn).
    Các tiêu chí test ở trên chỉ còn là phương án dự phòng khi thiếu điểm CV.
    """
    # Chọn mô hình theo điểm CROSS-VALIDATION trên tập train (đã tính khi GridSearchCV), KHÔNG
    # theo điểm test: chọn theo test rồi báo cáo chính điểm test đó là lạc quan có hệ thống (người
    # thắng được chọn vì may mắn trên đúng tập test). Chỉ số test vẫn hiển thị nguyên vẹn. Chỉ
    # rơi về tiêu chí test cũ khi có mô hình THIẾU điểm CV (vd. XGBoost train trực tiếp, Ensemble)
    # — trộn mô hình có/không có CV trong một bảng xếp hạng thì không so sánh được.
    if hub_type == "clf":
        if _has_complete_cv(metrics_df, CV_SCORE_COL):
            return CV_SCORE_COL, False
        if "F1 Score (Macro)" in metrics_df.columns and metrics_df["F1 Score (Macro)"].notna().any():
            return "F1 Score (Macro)", False
        return "Accuracy", False
    if _has_complete_cv(metrics_df, CV_MAE_COL):
        return CV_MAE_COL, True
    sort_col = "RMSE" if "RMSE" in metrics_df.columns and metrics_df["RMSE"].notna().any() else "R2 Score"
    return sort_col, sort_col == "RMSE"


def pick_best_model_name(results, hub_type):
    """Trả tên model tốt nhất trong 1 lượt huấn luyện (theo đúng tiêu chí bảng xếp
    hạng đang hiển thị cho người dùng), hoặc None nếu không có model hợp lệ nào.
    Dùng để tự động chọn bản Production khi lưu nhiều model cùng lúc vào Warehouse.
    """
    metrics_df = build_metrics_dataframe(results, hub_type)
    if metrics_df.empty:
        return None
    sort_col, ascending = resolve_ranking_col(metrics_df, hub_type)
    return metrics_df.sort_values(sort_col, ascending=ascending).index[0]


def update_hub_benchmark_and_build_comparison(results, hub_type, target_col):
    """
    Lưu benchmark mỗi lần train và trả bảng Before vs After.
    """
    metrics_df = build_metrics_dataframe(results, hub_type)
    if metrics_df.empty:
        return pd.DataFrame()

    sort_col, asc = resolve_ranking_col(metrics_df, hub_type)

    best_row = metrics_df.sort_values(sort_col, ascending=asc).iloc[0]
    best_model = metrics_df.sort_values(sort_col, ascending=asc).index[0]
    current = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "target_col": target_col,
        "hub_type": hub_type,
        "best_model": best_model,
        "R2 Score": safe_metric_value(best_row.get("R2 Score")),
        "RMSE": safe_metric_value(best_row.get("RMSE")),
        "MAE": safe_metric_value(best_row.get("MAE")),
        "Accuracy": safe_metric_value(best_row.get("Accuracy")),
        # Trainer chỉ sinh "F1 Score (Macro)"/"(Weighted)"; đọc khoá "F1 Score" trần luôn ra NaN.
        # Dùng Macro — cùng tiêu chí resolve_ranking_col dùng để chọn mô hình tốt nhất.
        "F1 Score": safe_metric_value(best_row.get("F1 Score (Macro)", best_row.get("F1 Score"))),
    }

    history = st.session_state.get("hub_benchmark_history", [])
    previous = None
    if isinstance(history, list):
        for item in reversed(history):
            if isinstance(item, dict) and item.get("target_col") == target_col and item.get("hub_type") == hub_type:
                previous = item
                break
    else:
        history = []

    history.append(current)
    st.session_state.hub_benchmark_history = history[-30:]

    if previous is None:
        return pd.DataFrame(
            [
                {"Chỉ số": "R2 Score", "Before": np.nan, "After": current["R2 Score"], "Δ (%)": np.nan},
                {"Chỉ số": "RMSE", "Before": np.nan, "After": current["RMSE"], "Δ (%)": np.nan},
                {"Chỉ số": "MAE", "Before": np.nan, "After": current["MAE"], "Δ (%)": np.nan},
                {"Chỉ số": "Accuracy", "Before": np.nan, "After": current["Accuracy"], "Δ (%)": np.nan},
                {"Chỉ số": "F1 Score", "Before": np.nan, "After": current["F1 Score"], "Δ (%)": np.nan},
            ]
        )

    rows = []
    for metric in ("R2 Score", "RMSE", "MAE", "Accuracy", "F1 Score"):
        before = safe_metric_value(previous.get(metric))
        after = safe_metric_value(current.get(metric))
        delta = np.nan
        if np.isfinite(before) and abs(before) > 1e-12 and np.isfinite(after):
            delta = (after - before) / abs(before) * 100.0
        rows.append({"Chỉ số": metric, "Before": before, "After": after, "Δ (%)": delta})
    return pd.DataFrame(rows)


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
