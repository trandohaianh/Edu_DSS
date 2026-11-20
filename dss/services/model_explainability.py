"""Giải thích mô hình: SHAP cục bộ/tổng thể và độ quan trọng đặc trưng của mô hình đã huấn luyện.

Tách từ dss/services/model_service.py; tên cũ vẫn import được từ model_service.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

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
