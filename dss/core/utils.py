"""CV helpers, metrics, UI step headers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold


def _safe_n_splits(n_samples, desired_folds=5, min_folds=2):
    """Trả về số folds an toàn, tránh n_splits > n_samples."""
    n_samples = int(n_samples)
    desired_folds = int(desired_folds)
    if n_samples < min_folds:
        raise ValueError(
            f"Không đủ dữ liệu để cross-validation: cần >= {min_folds} mẫu, hiện có {n_samples}."
        )
    return max(min_folds, min(desired_folds, n_samples))


def _make_safe_cv_strategy(y, desired_folds=5, is_classification=False, random_state=42):
    """
    Tạo chiến lược CV an toàn theo dữ liệu thực tế.
    - Classification: ưu tiên StratifiedKFold; tự fallback sang KFold nếu class quá hiếm.
    - Regression: dùng KFold với n_splits <= số mẫu.
    """
    n_samples = len(y)
    n_splits = _safe_n_splits(n_samples, desired_folds=desired_folds, min_folds=2)
    if is_classification:
        class_counts = pd.Series(y).value_counts(dropna=False)
        min_class_samples = int(class_counts.min()) if not class_counts.empty else 0
        if min_class_samples >= 2:
            n_splits = max(2, min(n_splits, min_class_samples))
            return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        return KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    return KFold(n_splits=n_splits, shuffle=True, random_state=random_state)


def find_repeated_group_column(df, index=None, exclude=()):
    """Cột mã sinh viên dùng làm NHÓM khi chia dữ liệu, hoặc None.

    Dữ liệu dọc (prepare_longitudinal_dataset) có 1 dòng / (sinh viên, học kỳ): chia ngẫu nhiên
    theo dòng làm các học kỳ của CÙNG một sinh viên rơi vào cả train lẫn test (và mọi fold CV),
    điểm đánh giá lạc quan giả. Chỉ trả về cột khi có ít nhất một sinh viên xuất hiện > 1 dòng
    trong `index` — mỗi sinh viên 1 dòng thì giữ nguyên cách chia cũ."""
    from dss.core.target_utils import is_id_like

    excluded = {str(c) for c in exclude}
    rows = df if index is None else df.loc[index]
    for col in df.columns:
        if str(col) in excluded or not is_id_like(col):
            continue
        values = rows[col]
        if values.isna().any():
            continue
        if values.duplicated().any() and values.nunique() >= 2:
            return col
    return None


def group_holdout_split(n_samples, groups, test_size, random_state=42):
    """Chia train/test theo NHÓM (GroupShuffleSplit): mọi dòng của một sinh viên nằm trọn một phía.
    Trả về (train_pos, test_pos) là vị trí dòng."""
    from sklearn.model_selection import GroupShuffleSplit

    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_pos, test_pos = next(splitter.split(np.zeros((n_samples, 1)), groups=np.asarray(groups)))
    return train_pos, test_pos


def make_group_cv_splits(y, groups, desired_folds=5, is_classification=False, random_state=42):
    """Danh sách split CV theo NHÓM (StratifiedGroupKFold cho phân loại, GroupKFold cho hồi quy),
    tính sẵn thành list (train_pos, val_pos) để truyền thẳng vào GridSearchCV/cross_val_score —
    tương đương truyền `groups=` vào fit nhưng không phải đổi chữ ký các hàm dùng chung."""
    from sklearn.model_selection import GroupKFold, StratifiedGroupKFold

    groups = np.asarray(groups)
    n_groups = len(pd.unique(groups))
    if n_groups < 2:
        return None
    n_splits = max(2, min(int(desired_folds), n_groups))
    X_dummy = np.zeros((len(groups), 1))
    if is_classification:
        class_counts = pd.Series(np.asarray(y)).value_counts()
        if not class_counts.empty and int(class_counts.min()) >= 2:
            n_splits = max(2, min(n_splits, int(class_counts.min())))
            cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
            return [(tr, va) for tr, va in cv.split(X_dummy, np.asarray(y), groups)]
    cv = GroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    return [(tr, va) for tr, va in cv.split(X_dummy, np.asarray(y), groups)]


def _normalize_labels_for_metrics(y_true, y_pred):
    """
    Chuẩn hóa nhãn cho các metric phân loại để tránh lỗi
    `Mix of label input types (string and number)`.
    """
    y_true_arr = np.asarray(list(y_true), dtype=object)
    y_pred_arr = np.asarray(list(y_pred), dtype=object)
    y_true_safe = np.array([str(v) for v in y_true_arr], dtype=str)
    y_pred_safe = np.array([str(v) for v in y_pred_arr], dtype=str)
    labels = np.unique(np.concatenate([y_true_safe, y_pred_safe]))
    return y_true_safe, y_pred_safe, labels


def _ensure_label_mapping(labels_obj):
    """Chuẩn hóa nhãn về dict {mã nội bộ (int) -> tên nhãn gốc} để tra bằng `.get(code, ...)`.

    `labels_obj` (session_state.hub_labels) thường là mảng class_labels do trainer trả về,
    trong đó VỊ TRÍ (index) mới là mã nội bộ mà pipeline.predict() dùng — không phải giá trị
    phần tử. Vì vậy phải enumerate() để lấy đúng cặp (mã số -> tên gốc), không được lấy chính
    giá trị làm khóa (sẽ không bao giờ khớp với mã số nguyên do predict() trả về).
    """
    if isinstance(labels_obj, dict):
        return labels_obj
    if labels_obj is None:
        return {}
    if isinstance(labels_obj, np.ndarray):
        return {i: str(v) for i, v in enumerate(labels_obj.tolist())}
    if isinstance(labels_obj, (list, tuple, set, pd.Index)):
        return {i: str(v) for i, v in enumerate(labels_obj)}
    return {}


def _render_low_performance_guidance_cls(model_name, accuracy, train_accuracy):
    """Hiển thị gợi ý xử lý khi mô hình phân loại quá kém."""
    st.error(
        f"❌ `{model_name}` có hiệu năng quá thấp (Test Accuracy: {accuracy:.2%}, "
        f"Train Accuracy: {train_accuracy:.2%}). Tạm loại khỏi danh sách mô hình dùng tiếp."
    )
    st.markdown(
        """
**Gợi ý sửa nhanh để cải thiện:**
- Kiểm tra lại cột `target` (không bị sai kiểu, không lẫn mã định danh).
- Gộp/bỏ các lớp quá hiếm (class chỉ vài mẫu) hoặc thu thêm dữ liệu cho lớp đó.
- Bật cân bằng lớp (`SMOTE/BorderlineSMOTE`) khi dữ liệu lệch lớp mạnh.
- Tăng chất lượng feature: bỏ cột nhiễu, thêm feature liên quan nghiệp vụ.
- Với dữ liệu nhỏ, ưu tiên model đơn giản (`Logistic Regression`, `Random Forest`) trước.
"""
    )


def _explain_best_params(best_params):
    """Sinh mô tả ngắn cho các tham số tối ưu để hiển thị khi train."""
    if not best_params:
        return []
    explanations = []
    for full_key, value in best_params.items():
        param_name = str(full_key).split("__")[-1]
        if param_name == "n_estimators":
            explanations.append(
                f"- `{full_key} = {value}`: số cây của mô hình; tăng số cây thường ổn định hơn nhưng sẽ chạy chậm hơn."
            )
        elif param_name == "max_depth":
            explanations.append(
                f"- `{full_key} = {value}`: độ sâu tối đa của cây; sâu hơn học chi tiết hơn nhưng có thể tăng overfitting."
            )
        elif param_name == "min_samples_split":
            explanations.append(
                f"- `{full_key} = {value}`: số mẫu tối thiểu để tách node; giá trị lớn hơn giúp mô hình bớt chia quá nhỏ."
            )
        elif param_name == "min_samples_leaf":
            explanations.append(
                f"- `{full_key} = {value}`: số mẫu tối thiểu tại node lá; tăng giá trị này giúp dự đoán mượt và ít nhiễu hơn."
            )
        elif param_name == "learning_rate":
            explanations.append(
                f"- `{full_key} = {value}`: tốc độ học mỗi vòng boosting; nhỏ hơn thường ổn định hơn nhưng cần nhiều vòng hơn."
            )
        elif param_name == "C":
            explanations.append(
                f"- `{full_key} = {value}`: mức regularization của Logistic Regression. "
                "Regularization là cơ chế 'phạt' mô hình quá phức tạp để giảm overfitting. "
                "Trong Logistic Regression, `C` là nghịch đảo của độ phạt: `C` nhỏ -> phạt mạnh hơn (mô hình đơn giản hơn), "
                "`C` lớn -> phạt yếu hơn (mô hình linh hoạt hơn)."
            )
        elif param_name == "solver":
            explanations.append(
                f"- `{full_key} = {value}`: thuật toán tối ưu dùng để fit Logistic Regression."
            )
        else:
            explanations.append(
                f"- `{full_key} = {value}`: tham số tối ưu được chọn tự động bởi GridSearchCV."
            )
    return explanations


def st_step_header(text: str) -> None:
    """Tiêu đề bước thống nhất (nền gradient xanh->ngọc nhạt, viền trái xanh đậm)."""
    t = (text or "").strip()
    st.markdown(
        f"<div style='background:linear-gradient(90deg,#eef4ff 0%,#f0fdfa 100%);padding:10px 14px;border-radius:10px;"
        f"border:1px solid #cbd5e1;border-left:4px solid #2563eb;margin-bottom:1rem;box-shadow:0 1px 3px rgba(15,23,42,0.06);'>"
        f"<div style='margin:0;color:var(--text-primary);font-size:var(--fs-card-title);font-weight:700;line-height:1.4;'>{t}</div></div>",
        unsafe_allow_html=True,
    )


def render_chart_guide(section: str) -> None:
    """Hiển thị hướng dẫn ngắn giúp người dùng đọc đúng biểu đồ/sơ đồ."""
    guides = {
        "model_compare": (
            "📘 **Cách đọc đồ thị so sánh mô hình:** Mỗi cột là một mô hình. "
            "Cột càng cao càng tốt với **Accuracy/F1/R2**; cột càng thấp càng tốt với **RMSE/MAE**."
        ),
        "pred_vs_actual_reg": (
            "📘 **Cách đọc biểu đồ Thực tế vs Dự đoán (Hồi quy):** "
            "Điểm càng sát đường chéo đỏ thì dự đoán càng chính xác; điểm lệch xa là mẫu có sai số lớn."
        ),
        "pred_vs_actual_clf": (
            "📘 **Cách đọc Confusion Matrix (Phân loại):** "
            "Ô trên đường chéo chính là dự đoán đúng; ô ngoài đường chéo là dự đoán nhầm."
        ),
        "feature_scatter": (
            "📘 **Cách đọc biểu đồ tương quan đặc trưng:** "
            "Mỗi tab là một chỉ số đánh giá. Giá trị càng lớn (hoặc độ lớn càng cao) cho thấy feature ảnh hưởng mạnh hơn."
        ),
        "shap_summary": (
            "📘 **Cách đọc SHAP Summary:** Feature ở trên cùng thường quan trọng hơn. "
            "Màu đỏ/xanh biểu thị giá trị feature cao/thấp; điểm nằm xa 0 thể hiện tác động mạnh tới dự đoán."
        ),
    }
    msg = guides.get(section)
    if msg:
        st.info(msg)


def render_chart_guide_advanced(section: str) -> None:
    """Hiển thị phần giải thích nâng cao cho biểu đồ/sơ đồ."""
    details = {
        "model_compare": (
            "**Mẹo đọc nhanh:**\n"
            "- Với **hồi quy**: ưu tiên mô hình có **R2 cao**, **RMSE/MAE thấp**.\n"
            "- Với **phân loại**: ưu tiên **Accuracy/F1** cao; nếu dữ liệu lệch lớp, ưu tiên F1 hơn Accuracy.\n"
            "- So sánh chênh lệch giữa top 2 mô hình: nếu quá sát nhau, chọn mô hình đơn giản hơn để dễ vận hành."
        ),
        "pred_vs_actual_reg": (
            "**Cách diễn giải:**\n"
            "- Điểm nằm trên đường chéo: dự đoán gần đúng thực tế.\n"
            "- Cụm điểm loe rộng ở vùng giá trị cao cho thấy mô hình đang khó dự đoán ở nhóm đó.\n"
            "- Nếu sai số tăng khi target tăng: có thể thử log-transform target (lấy log của biến mục tiêu để nén thang đo) "
            "hoặc thêm feature tương tác (ví dụ `A*B`, `A/B`) để mô hình học quan hệ phi tuyến tốt hơn."
        ),
        "pred_vs_actual_clf": (
            "**Cách diễn giải Confusion Matrix:**\n"
            "- Đường chéo chính càng đậm càng tốt (dự đoán đúng nhiều).\n"
            "- Ô nhầm lẫn lớn nhất cho biết cặp lớp dễ bị nhầm — nên bổ sung feature tách 2 lớp này.\n"
            "- Xem thêm Precision/Recall theo từng lớp để biết mô hình đang thiên về bỏ sót hay báo nhầm."
        ),
        "feature_scatter": (
            "**Cách diễn giải feature metrics:**\n"
            "- Feature đứng top ổn định qua nhiều chỉ số thường đáng tin cậy hơn.\n"
            "- Nếu một feature chỉ cao ở 1 chỉ số nhưng thấp ở chỉ số khác, cần kiểm tra lại nhiễu/outlier.\n"
            "- Ở biểu đồ scatter: trục X = giá trị thật, trục Y = giá trị dự đoán; chấm càng gần đường chéo đỏ thì càng tốt.\n"
            "- Màu điểm thể hiện mức đóng góp theo từng metric (MI/PE/PBC/RFE/PC/SC/RF), điểm lớn là mẫu có sai số lớn.\n"
            "- Có thể dùng top features để rút gọn mô hình, tăng tốc train và giảm overfitting."
        ),
        "shap_summary": (
            "**Cách đọc SHAP chuyên sâu:**\n"
            "- Trục ngang là mức tác động lên dự đoán; càng xa 0 càng ảnh hưởng mạnh.\n"
            "- Màu đỏ (giá trị feature cao) nằm về bên phải nghĩa là feature cao làm tăng dự đoán.\n"
            "- Nếu một feature có điểm phân tán quá rộng, quan hệ với target có thể phi tuyến hoặc phụ thuộc feature khác."
        ),
    }
    content = details.get(section)
    if content:
        with st.expander("📖 Giải thích nâng cao", expanded=False):
            st.markdown(content)
