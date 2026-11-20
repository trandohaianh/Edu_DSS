"""Bảng chỉ số đánh giá mô hình và quy tắc chọn mô hình tốt nhất (F1/PR-AUC, MAE, CV).

Tách từ dss/services/model_service.py; tên cũ vẫn import được từ model_service.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st


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
