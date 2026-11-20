"""Trang "Kết quả đánh giá mô hình".

Hai phần, tách bạch nguồn số liệu:
1. Lượt huấn luyện trong phiên (`st.session_state.hub_*`, do
   model_service.run_training ghi) — NƠI DUY NHẤT hiển thị bảng so sánh
   MAE/RMSE/R² (hoặc Accuracy/F1...) và biểu đồ Thực tế vs Dự đoán.
2. Báo cáo đánh giá đã xác minh: `dss/assets/evaluation_snapshot.json`, sinh
   bởi `reports/portfolio/evidence/run_portfolio_eval.py`. Không tự tính —
   nếu snapshot không có, ghi chú ngắn trung thực.
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dss.core.data_helpers import feature_label
from dss.services.model_service import build_metrics_dataframe, extract_failed_models, resolve_ranking_col
from dss.tabs import ui_kit

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "assets" / "evaluation_snapshot.json"
_BAR = "#2F5BD3"
_BAR_MUTED = "#9AA0A6"


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def fmt3(value) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "—"


def _data_note(snap: dict) -> None:
    data = snap.get("data", {})
    if str(data.get("origin", "")).upper() == "SYNTHETIC":
        ui_kit.alert_box(
            "Kết quả đánh giá trên dữ liệu sinh viên mô phỏng. Đây không phải độ chính xác "
            "đã kiểm chứng trên sinh viên thật hay độ chính xác vận hành.",
            kind="info",
            title="Nguồn dữ liệu",
        )
    meta = snap.get("meta", {})
    st.caption(
        f"{data.get('rows', '—')} sinh viên · chia train/test {snap['classification']['train_size']}/"
        f"{snap['classification']['test_size']} (random_state=42) · đánh giá ngày {meta.get('evaluated_at', '—')} · "
        f"mã nguồn {str(meta.get('git_sha', '—'))[:12]}"
    )


def _classification(snap: dict) -> None:
    cls = snap["classification"]
    best = cls["best_model_by_app_ranking"]
    m = cls["models"][best]
    ui_kit.subsection_header(
        "Phân loại xếp loại học tập",
        subtitle=f"Mô hình tốt nhất theo F1-macro: {best} · {cls['test_size']} sinh viên trong tập kiểm tra.",
    )
    ui_kit.kpi_row(
        [
            ("Accuracy", fmt3(m["accuracy"])),
            ("Precision (macro)", fmt3(m["precision_macro"])),
            ("Recall (macro)", fmt3(m["recall_macro"])),
            ("F1-score (macro)", fmt3(m["f1_macro"])),
        ]
    )
    col_cmp, col_cm = st.columns([1.1, 1], gap="medium")
    with col_cmp:
        with st.container(border=True):
            ui_kit.card_title("So sánh mô hình (F1-macro, cùng tập kiểm tra)")
            rows = sorted(cls["models"].items(), key=lambda kv: kv[1]["f1_macro"])
            fig = go.Figure(
                go.Bar(
                    x=[v["f1_macro"] for _, v in rows],
                    y=[k for k, _ in rows],
                    orientation="h",
                    marker_color=[_BAR if k == best else _BAR_MUTED for k, _ in rows],
                    text=[fmt3(v["f1_macro"]) for _, v in rows],
                    textposition="auto",
                    hovertemplate="%{y}: %{x:.3f}<extra></extra>",
                )
            )
            fig.update_layout(height=260, margin=dict(t=8, b=8, l=8, r=8), xaxis=dict(range=[0, 1]))
            st.plotly_chart(fig, width="stretch", key="eval_model_compare", config={"displayModeBar": False})
            table = pd.DataFrame(
                [
                    {
                        "Mô hình": k,
                        "Accuracy": fmt3(v["accuracy"]),
                        "Precision": fmt3(v["precision_macro"]),
                        "Recall": fmt3(v["recall_macro"]),
                        "F1-macro": fmt3(v["f1_macro"]),
                    }
                    for k, v in sorted(cls["models"].items(), key=lambda kv: -kv[1]["f1_macro"])
                ]
            )
            st.dataframe(table, hide_index=True, width="stretch")
    with col_cm:
        with st.container(border=True):
            ui_kit.card_title(f"Ma trận nhầm lẫn — {best}")
            labels = cls["class_labels"]
            cm = m["confusion_matrix"]
            fig = px.imshow(
                cm,
                x=labels,
                y=labels,
                text_auto=True,
                color_continuous_scale="Blues",
                labels=dict(x="Dự đoán", y="Thực tế", color="Số SV"),
            )
            fig.update_layout(height=330, margin=dict(t=8, b=8, l=8, r=8), coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch", key="eval_confusion", config={"displayModeBar": False})
            dist = cls.get("class_distribution_full", {})
            if dist:
                rare = [f"{k}: {v}" for k, v in dist.items() if v < 20]
                if rare:
                    st.caption(
                        "Lớp rất ít mẫu trong toàn bộ dữ liệu ("
                        + ", ".join(rare)
                        + ") — chỉ số macro dao động mạnh theo vài mẫu."
                    )


def _regression(snap: dict) -> None:
    reg = snap["regression"]
    best = reg["best_model_by_app_ranking"]
    m = reg["models"][best]
    ui_kit.subsection_header(
        "Hồi quy điểm học kỳ sau",
        subtitle=f"Mô hình tốt nhất theo RMSE: {best} · {reg['test_size']} sinh viên trong tập kiểm tra.",
    )
    ui_kit.kpi_row([("MAE", fmt3(m["mae"])), ("RMSE", fmt3(m["rmse"])), ("R²", fmt3(m["r2"]))])
    st.caption(
        "R² cao phản ánh cách dữ liệu mô phỏng được sinh (điểm kỳ sau ≈ tổ hợp tuyến tính của các đặc trưng "
        "cộng nhiễu nhỏ) — không phải bằng chứng dự đoán chính xác trên sinh viên thật."
    )
    table = pd.DataFrame(
        [
            {"Mô hình": k, "MAE": fmt3(v["mae"]), "RMSE": fmt3(v["rmse"]), "R²": fmt3(v["r2"])}
            for k, v in sorted(reg["models"].items(), key=lambda kv: kv[1]["rmse"])
        ]
    )
    st.dataframe(table, hide_index=True, width="stretch")


def _clustering(snap: dict) -> None:
    cl = snap["clustering"]
    ui_kit.subsection_header(
        "Phân cụm sinh viên (K-Means)",
        subtitle="Phân khúc theo độ tương đồng dữ liệu — công cụ khám phá, không phải phân loại chính thức.",
    )
    ui_kit.kpi_row(
        [
            ("Số cụm (K)", str(cl["k_selected"])),
            ("Silhouette", fmt3(cl["silhouette"])),
            ("Davies-Bouldin", fmt3(cl["davies_bouldin"])),
        ]
    )
    col_dist, col_sweep = st.columns(2, gap="medium")
    with col_dist:
        with st.container(border=True):
            ui_kit.card_title("Số sinh viên mỗi cụm")
            sizes = cl["cluster_sizes"]
            pct = cl["cluster_pct"]
            keys = sorted(sizes, key=lambda k: int(k))
            fig = go.Figure(
                go.Bar(
                    x=[f"Cụm {k}" for k in keys],
                    y=[sizes[k] for k in keys],
                    marker_color=_BAR,
                    text=[f"{sizes[k]} ({pct[k]:.1f}%)" for k in keys],
                    textposition="auto",
                )
            )
            fig.update_layout(height=260, margin=dict(t=8, b=8, l=8, r=8))
            st.plotly_chart(fig, width="stretch", key="eval_cluster_sizes", config={"displayModeBar": False})
    with col_sweep:
        with st.container(border=True):
            ui_kit.card_title("Silhouette theo K (tham khảo)")
            sweep = cl.get("silhouette_sweep_k2_8", {})
            if sweep:
                ks = sorted(sweep, key=int)
                fig = go.Figure(
                    go.Scatter(
                        x=[int(k) for k in ks],
                        y=[sweep[k] for k in ks],
                        mode="lines+markers",
                        line=dict(color=_BAR),
                        hovertemplate="K=%{x}: %{y:.3f}<extra></extra>",
                    )
                )
                fig.update_layout(
                    height=260, margin=dict(t=8, b=8, l=8, r=8), xaxis_title="K", yaxis_title="Silhouette"
                )
                st.plotly_chart(fig, width="stretch", key="eval_cluster_sweep", config={"displayModeBar": False})
            st.caption(f"K mặc định của hệ thống: {cl.get('k_rule', '—')}. Silhouette thấp cho thấy cấu trúc cụm yếu.")


def _explainability(snap: dict) -> None:
    exp = snap.get("explainability", {})
    shap_block = exp.get("regression_shap", {})
    ui_kit.subsection_header(
        "Giải thích mô hình (SHAP)",
        subtitle=f"Mức đóng góp trung bình |SHAP| của từng đặc trưng vào điểm dự đoán — mô hình {shap_block.get('model', '—')}. "
        "SHAP mô tả đóng góp vào dự đoán, không phải quan hệ nhân quả.",
    )
    top = shap_block.get("top", [])
    if not top:
        ui_kit.empty_state("Chưa có kết quả SHAP trong báo cáo đánh giá.", hint=shap_block.get("error"))
        return
    col_shap, col_imp = st.columns([1.2, 1], gap="medium")
    with col_shap:
        with st.container(border=True):
            ui_kit.card_title("Mức đóng góp trung bình |SHAP| (hồi quy)")
            rows = list(reversed(top[:10]))
            fig = go.Figure(
                go.Bar(
                    x=[r["mean_abs_shap"] for r in rows],
                    y=[feature_label(r["feature"]) for r in rows],
                    orientation="h",
                    marker_color=_BAR,
                    text=[fmt3(r["mean_abs_shap"]) for r in rows],
                    textposition="auto",
                )
            )
            fig.update_layout(height=360, margin=dict(t=8, b=8, l=8, r=8))
            st.plotly_chart(fig, width="stretch", key="eval_shap", config={"displayModeBar": False})
    with col_imp:
        with st.container(border=True):
            imp = exp.get("classification", {})
            ui_kit.card_title(f"Độ quan trọng đặc trưng — {imp.get('model', 'phân loại')}")
            if imp.get("top"):
                table = pd.DataFrame(
                    [
                        {"Đặc trưng": feature_label(r["feature"]), "Độ quan trọng": f"{r['importance_pct']:.1f}%"}
                        for r in imp["top"][:10]
                    ]
                )
                st.dataframe(table, hide_index=True, width="stretch")
            else:
                ui_kit.empty_state("Mô hình không cung cấp độ quan trọng đặc trưng.")


def _decode_clf_pred(y_pred):
    """pipeline.predict() phân loại trả mã nội bộ 0..K-1 — giải mã về nhãn gốc."""
    labels = st.session_state.get("hub_labels")
    arr = np.asarray(labels) if labels is not None else np.asarray([])
    if arr.size:
        try:
            return arr[np.asarray(y_pred).astype(int)]
        except Exception:
            pass
    return y_pred


def _session_results() -> bool:
    """Kết quả lượt huấn luyện gần nhất trong phiên. Trả False nếu chưa có."""
    results = st.session_state.get("hub_results")
    hub_type = st.session_state.get("hub_type")
    if not results or hub_type not in ("clf", "reg"):
        return False
    metrics_df = build_metrics_dataframe(results, hub_type)
    target = st.session_state.get("hub_target_col", "—")
    task = "Phân loại" if hub_type == "clf" else "Hồi quy"
    ui_kit.subsection_header(
        "Lượt huấn luyện gần nhất",
        subtitle=f"Target: {feature_label(target)} · {task} · chỉ số đo trên tập kiểm tra (test).",
    )
    failed = extract_failed_models(results)
    if failed:
        st.caption("Mô hình huấn luyện lỗi: " + "; ".join(f"{k} ({str(v)[:80]})" for k, v in failed.items()))
    if metrics_df.empty:
        ui_kit.empty_state(
            "Không có chỉ số hợp lệ cho lượt huấn luyện này.",
            hint="Kiểm tra Target/Features hoặc giảm số fold CV rồi huấn luyện lại.",
        )
        return True

    rank_col, asc = resolve_ranking_col(metrics_df, hub_type)
    ranked = metrics_df.sort_values(rank_col, ascending=asc)
    best = ranked.index[0]
    best_row = ranked.loc[best]
    st.markdown(f"Mô hình tốt nhất (theo {rank_col}): **{best}**")
    ui_kit.kpi_row([(c, fmt3(best_row[c])) for c in ranked.columns[:4]])
    saved = st.session_state.get("hub_saved_candidate_count")
    if saved:
        st.caption(
            f"Đã lưu {saved} mô hình vào Kho (Candidate). Giảng viên dự đoán được ngay ở tab **Dự đoán** "
            "bằng mô hình tốt nhất; Sinh viên/Dashboard dùng bản Production sau khi Admin Promote."
        )

    col_tbl, col_chart = st.columns([1.2, 1], gap="medium")
    with col_tbl:
        with st.container(border=True):
            ui_kit.card_title(f"So sánh các mô hình (xếp theo {rank_col})")
            st.dataframe(ranked.style.format("{:.4f}"), width="stretch")
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
                ranked.to_excel(writer, sheet_name="Metrics")
            st.download_button(
                "Tải bảng chỉ số (.xlsx)",
                data=out.getvalue(),
                file_name=f"training_report_{datetime.now():%Y%m%d_%H%M}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="eval_session_export",
            )
    with col_chart:
        with st.container(border=True):
            ui_kit.card_title(rank_col)
            fig = go.Figure(
                go.Bar(
                    x=ranked[rank_col],
                    y=ranked.index.astype(str),
                    orientation="h",
                    marker_color=[_BAR if k == best else _BAR_MUTED for k in ranked.index],
                    text=[fmt3(v) for v in ranked[rank_col]],
                    textposition="auto",
                    hovertemplate="%{y}: %{x:.4f}<extra></extra>",
                )
            )
            fig.update_layout(height=260, margin=dict(t=8, b=8, l=8, r=8), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, width="stretch", key="eval_session_rank", config={"displayModeBar": False})

    test_data = st.session_state.get("hub_test_data")
    pipelines = st.session_state.get("hub_pipelines") or {}
    options = [m for m in ranked.index if m in pipelines]
    if not (isinstance(test_data, tuple) and options):
        return True
    X_test, y_test = test_data
    with st.container(border=True):
        model = st.selectbox("Xem chi tiết mô hình", options, index=0, key="eval_session_model")
        try:
            y_pred = pipelines[model].predict(X_test)
        except Exception as e:
            ui_kit.empty_state("Không dự đoán được trên tập kiểm tra.", hint=str(e)[:200])
            return True
        if hub_type == "reg":
            ui_kit.card_title(f"Thực tế vs Dự đoán — {model}")
            y_true = np.asarray(y_test, dtype=float)
            y_hat = np.asarray(y_pred, dtype=float)
            lo, hi = float(min(y_true.min(), y_hat.min())), float(max(y_true.max(), y_hat.max()))
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=y_true,
                    y=y_hat,
                    mode="markers",
                    marker=dict(color=_BAR, opacity=0.6),
                    hovertemplate="Thực tế %{x:.2f} · Dự đoán %{y:.2f}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=_BAR_MUTED, dash="dash"), hoverinfo="skip"
                )
            )
            fig.update_layout(
                height=380,
                margin=dict(t=8, b=8, l=8, r=8),
                showlegend=False,
                xaxis_title="Thực tế",
                yaxis_title="Dự đoán",
            )
            st.plotly_chart(fig, width="stretch", key="eval_session_scatter", config={"displayModeBar": False})
            st.caption("Điểm càng gần đường chéo, dự đoán càng sát thực tế.")
        else:
            from sklearn.metrics import confusion_matrix

            y_true = [str(v) for v in y_test]
            y_hat = [str(v) for v in _decode_clf_pred(y_pred)]
            labels = sorted(set(y_true) | set(y_hat))
            ui_kit.card_title(f"Ma trận nhầm lẫn — {model}")
            fig = px.imshow(
                confusion_matrix(y_true, y_hat, labels=labels),
                x=labels,
                y=labels,
                text_auto=True,
                color_continuous_scale="Blues",
                labels=dict(x="Dự đoán", y="Thực tế", color="Số SV"),
            )
            fig.update_layout(height=360, margin=dict(t=8, b=8, l=8, r=8), coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch", key="eval_session_cm", config={"displayModeBar": False})
    return True


def evaluation_report_tab() -> None:
    ui_kit.page_header(
        "Kết quả đánh giá mô hình",
        subtitle="Chỉ số của lượt huấn luyện gần nhất và báo cáo đánh giá đã xác minh của EduDSS.",
    )
    if not _session_results():
        ui_kit.empty_state(
            "Chưa huấn luyện mô hình nào trong phiên này.",
            hint="Sang tab Huấn luyện mô hình, chọn Target/Features và bấm Tiến hành.",
        )

    snap = load_snapshot()
    if not snap:
        st.caption("Chưa có báo cáo đánh giá đã xác minh (chạy reports/portfolio/evidence/run_portfolio_eval.py).")
        return
    with st.expander("Báo cáo đánh giá đã xác minh (tham chiếu trên tập dữ liệu chuẩn)", expanded=False):
        _data_note(snap)
        t_cls, t_reg, t_clu, t_shap = st.tabs(["Phân loại", "Hồi quy", "Phân cụm", "Giải thích (SHAP)"])
        with t_cls:
            _classification(snap)
        with t_reg:
            _regression(snap)
        with t_clu:
            _clustering(snap)
        with t_shap:
            _explainability(snap)
