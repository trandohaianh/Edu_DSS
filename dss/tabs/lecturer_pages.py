"""3 trang của Giảng viên / CVHT theo mockup `ui_reference/lecturer/`:
Phân tích rủi ro, Lịch sử tư vấn, Báo cáo (MVP_SCOPE §3, AC-GV-09..11).

- Chỉ ĐỌC dữ liệu thật. Không có số liệu viết cứng: mockup chỉ là khung, số trong
  mockup (ví dụ "Accuracy .875") là số cũ, không dùng.
- Phạm vi = bộ dữ liệu đang dùng (quyết định chủ dự án 21/11/2026).
- Rủi ro dùng ĐÚNG hàm của Trang chủ/Dashboard (`compute_lecturer_dashboard_overview`),
  nên số liệu giữa các trang luôn khớp nhau.
- Biến đổi dữ liệu nằm ở `dss/services/lecturer_reports.py` (có test riêng).
"""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st

from dss.core.data_helpers import feature_label
from dss.core.logging_config import get_logger
from dss.services import lecturer_reports as lr
from dss.services.auth_service import require_role
from dss.services.model_explainability import get_production_feature_importance
from dss.services.model_service import compute_lecturer_dashboard_overview
from dss.tabs import ui_kit

_logger = get_logger(__name__)
AI_TAB = "🤖 Tư vấn — AI (LLM)"
LECTURER_ROLE = "Giảng viên / CVHT"
_PLOT_CONFIG = {"displayModeBar": False}
_RISK_COLORS = {"Nguy cơ cao": "#D94B3F", "Nguy cơ trung bình": "#F3B21C", "Nguy cơ thấp": "#17A673"}


def _class_overview(df, wh) -> dict | None:
    """Tổng quan lớp, tính đúng như Trang chủ Giảng viên (`home.py`)."""
    from dss.tabs.home import _find_gpa_column

    gpa_col = _find_gpa_column(df)
    if not gpa_col:
        return {"status": "error", "message": "Dữ liệu lớp không có cột điểm để so sánh mức rủi ro."}
    try:
        return compute_lecturer_dashboard_overview(df, wh, st.session_state.get("current_dataset_id"), gpa_col)
    except Exception:
        _logger.exception("Không tính được tổng quan lớp học (trang giảng viên).")
        return {"status": "error", "message": "Không thể tính tổng quan lớp học."}


def _need_data(df, wh, action: str) -> bool:
    if df is None or wh is None:
        ui_kit.empty_state(
            "Chưa có dữ liệu lớp học.", hint=f"Chọn hoặc tải dữ liệu lớp học ở trang Kho dữ liệu để {action}."
        )
        return True
    return False


def _overview_unavailable(overview) -> bool:
    if overview and overview.get("status") == "ok":
        return False
    msg = (overview or {}).get("message") or "Chưa có mô hình Production cho lớp này."
    ui_kit.empty_state(
        "Chưa có kết quả dự đoán cho lớp.",
        hint=f"{msg} Admin cần duyệt một mô hình lên Production trong Kho dữ liệu.",
    )
    return True


def _excel_download(label: str, data: bytes | None, file_stem: str, key: str, primary: bool = False) -> bool:
    """Nút tải file Excel; báo lỗi rõ ràng nếu máy chủ thiếu thư viện ghi Excel."""
    if data is None:
        ui_kit.error_state(
            "Không tạo được file Excel",
            "Máy chủ thiếu thư viện ghi Excel (xlsxwriter hoặc openpyxl).",
            support_hint="Quản trị viên cài lại theo requirements.txt.",
        )
        return False
    st.download_button(
        label,
        data=data,
        file_name=f"{file_stem}_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary" if primary else "secondary",
        key=key,
    )
    return True


def _bar(df, x, y, colors=None, height=300, horizontal=False):
    fig = go.Figure(
        go.Bar(
            x=df[y] if horizontal else df[x],
            y=df[x] if horizontal else df[y],
            orientation="h" if horizontal else "v",
            marker_color=colors,
            text=df[y],
            textposition="auto",
        )
    )
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return fig


# ------------------------------------------------------------------ 1. Phân tích rủi ro
@require_role(LECTURER_ROLE)  # chặn cả ở tầng hàm, không chỉ dựa vào menu (bước 7)
def render_risk_analysis_tab(df, wh) -> None:
    ui_kit.section_header("Phân tích rủi ro", "Theo dõi nhóm nguy cơ và các yếu tố ảnh hưởng chính của lớp.")
    if _need_data(df, wh, "phân tích rủi ro"):
        return
    ui_kit.render_synthetic_data_banner(df)
    overview = _class_overview(df, wh)
    if _overview_unavailable(overview):
        return

    counts = overview["risk_counts"]
    avg = overview.get("avg_predicted")
    ui_kit.kpi_row(
        [
            ("Nguy cơ cao", counts.get("cao", 0), ui_kit.RISK_RELATIVE_CAPTION, "danger"),
            ("Nguy cơ trung bình", counts.get("trung bình", 0), "Từ phân vị 25% đến 50% điểm dự đoán", "warning"),
            ("Nguy cơ thấp", counts.get("thấp", 0), "Trên phân vị 50% điểm dự đoán", "success"),
            ("Điểm dự đoán trung bình", f"{avg:.2f}" if avg is not None else "—", "Mô hình Production hiện tại"),
        ]
    )
    st.caption(
        "Mức rủi ro là xếp hạng **tương đối trong lớp** theo điểm dự đoán, không phải ngưỡng chính thức "
        f"của nhà trường. Mô hình: {overview.get('model_name')} v{overview.get('version')}."
    )

    col_dist, col_factor = st.columns([3, 2])
    with col_dist:
        ui_kit.card_title("Phân bố mức rủi ro")
        dist = lr.risk_distribution(overview)
        st.plotly_chart(
            _bar(dist, "Mức rủi ro", "Số sinh viên", colors=[_RISK_COLORS[m] for m in dist["Mức rủi ro"]]),
            width="stretch",
            key="lect_risk_dist",
            config=_PLOT_CONFIG,
        )
    with col_factor:
        ui_kit.card_title("Yếu tố ảnh hưởng nhiều nhất")
        imp = get_production_feature_importance(overview.get("pipeline"), overview.get("feature_cols") or [], top_n=6)
        if imp.empty:
            st.info("Mô hình đang dùng không cung cấp mức độ quan trọng của từng yếu tố.")
        else:
            imp = imp.assign(Feature=[feature_label(f) for f in imp["Feature"]])
            st.plotly_chart(
                _bar(imp, "Feature", "Importance (%)", colors="#2F5BD3", height=280, horizontal=True),
                width="stretch",
                key="lect_risk_factors",
                config=_PLOT_CONFIG,
            )
            st.caption("Mức độ quan trọng (%) đọc từ chính mô hình Production — không phải quan hệ nhân quả.")

    ui_kit.card_title("Sinh viên nguy cơ cao")
    table = lr.high_risk_table(overview, label_fn=feature_label)
    if table.empty:
        st.info("Không có sinh viên nào ở nhóm nguy cơ cao.")
        return
    st.dataframe(table, hide_index=True, width="stretch")
    pick = st.selectbox("Chọn sinh viên để xem phân tích", table["Mã SV"].tolist(), key="lect_risk_pick")
    if st.button("Xem phân tích", key="lect_risk_open_ai", type="primary"):
        st.session_state["llm_student_select"] = pick
        st.session_state["_pending_nav_target"] = AI_TAB
        st.rerun()


# ------------------------------------------------------------------ 2. Lịch sử tư vấn
@require_role(LECTURER_ROLE)  # chặn cả ở tầng hàm, không chỉ dựa vào menu (bước 7)
def render_consultation_history_tab(wh, current_username: str | None) -> None:
    ui_kit.section_header("Lịch sử tư vấn", "Theo dõi các phiên tư vấn đã lưu.")
    if wh is None:
        ui_kit.empty_state("Chưa kết nối kho dữ liệu.")
        return
    records = wh.get_history("advisor", limit=10000) or []
    if not records:
        ui_kit.empty_state("Chưa có phiên tư vấn nào.", hint="Các phiên tạo ở Trợ lý AI sẽ được lưu và hiện ở đây.")
        return

    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    with c1:
        student = st.text_input("Mã sinh viên", key="lect_hist_student", placeholder="Ví dụ: SV001")
    with c2:
        d_from = st.date_input(
            "Từ ngày", value=date.today() - timedelta(days=30), key="lect_hist_from", format="DD/MM/YYYY"
        )
    with c3:
        d_to = st.date_input("Đến ngày", value=date.today(), key="lect_hist_to", format="DD/MM/YYYY")
    with c4:
        mine = st.toggle("Chỉ phiên do tôi tư vấn", key="lect_hist_mine", disabled=not current_username)

    if d_from and d_to and d_from > d_to:
        st.warning("Ngày bắt đầu đang sau ngày kết thúc.")
        return
    rows = lr.filter_consultations(
        records, student_id=student, date_from=d_from, date_to=d_to, performed_by=current_username if mine else None
    )
    st.caption(
        f"{len(rows)} / {len(records)} phiên. Phiên lưu trước ngày 21/11/2026 không ghi người tư vấn "
        f"(hiện là \"{lr.UNKNOWN_ACTOR}\")."
    )
    if not rows:
        st.info("Không có phiên nào khớp bộ lọc.")
        return
    frame = lr.consultations_frame(rows)
    st.dataframe(frame, hide_index=True, width="stretch")
    _excel_download(
        "Xuất Excel", lr.build_report_workbook({"Lịch sử tư vấn": frame}), "lich_su_tu_van", "lect_hist_export"
    )
    with st.expander("Xem đầy đủ một phiên"):
        labels = [f"{r['Thời gian']} · {r['Mã SV']}" for _, r in frame.iterrows()]
        idx = st.selectbox("Phiên", range(len(rows)), format_func=lambda i: labels[i], key="lect_hist_pick")
        plan = rows[idx].get("generated_plan") or "(Phiên này không lưu nội dung kế hoạch.)"
        st.markdown(plan)


# ------------------------------------------------------------------ 3. Báo cáo
@require_role(LECTURER_ROLE)  # chặn cả ở tầng hàm, không chỉ dựa vào menu (bước 7)
def render_reports_tab(df, wh) -> None:
    ui_kit.section_header("Báo cáo", "Tổng hợp rủi ro, dự đoán và tư vấn của lớp.")
    if _need_data(df, wh, "xem báo cáo"):
        return
    ui_kit.render_synthetic_data_banner(df)
    overview = _class_overview(df, wh)
    ok = bool(overview and overview.get("status") == "ok")
    consultations = wh.get_history("advisor", limit=10000) or []
    label, value, caption = ui_kit.model_metric_display(
        overview.get("metric_name") if ok else None, overview.get("metric_value") if ok else None, df
    )
    ui_kit.kpi_row(
        [
            ("Sinh viên", len(df), "Trong bộ dữ liệu đang dùng"),
            (
                "Nguy cơ cao",
                overview["risk_counts"].get("cao", 0) if ok else "—",
                ui_kit.RISK_RELATIVE_CAPTION,
                "danger",
            ),
            (label, value, caption),
            ("Phiên tư vấn AI", len(consultations), "Toàn bộ phiên đã lưu"),
        ]
    )
    if not ok:
        _overview_unavailable(overview)

    col_risk, col_perf = st.columns(2)
    with col_risk:
        ui_kit.card_title("Tóm tắt rủi ro")
        dist = lr.risk_distribution(overview)
        if dist.empty:
            st.info("Chưa có kết quả dự đoán để tóm tắt rủi ro.")
        else:
            st.plotly_chart(
                _bar(dist, "Mức rủi ro", "Số sinh viên", colors=[_RISK_COLORS[m] for m in dist["Mức rủi ro"]]),
                width="stretch",
                key="lect_report_risk",
                config=_PLOT_CONFIG,
            )
    versions = lr.model_versions_frame(
        wh.list_models(),
        dataset_id=st.session_state.get("current_dataset_id"),
        target_col=overview.get("target_col") if ok else None,
    )
    with col_perf:
        ui_kit.card_title("Hiệu năng mô hình qua các phiên bản")
        plot_df = versions.dropna(subset=["Giá trị"]) if not versions.empty else versions
        if plot_df.empty:
            st.info("Chưa có mô hình nào được huấn luyện cho bộ dữ liệu này.")
        else:
            fig = go.Figure(
                go.Scatter(
                    x=[f"v{v}" for v in plot_df["Phiên bản"]],
                    y=plot_df["Giá trị"],
                    mode="lines+markers+text",
                    text=[f"{v:.3f}" for v in plot_df["Giá trị"]],
                    textposition="top center",
                )
            )
            fig.update_layout(
                height=300, margin=dict(l=10, r=10, t=20, b=10), yaxis_title=str(plot_df["Chỉ số"].iloc[-1])
            )
            st.plotly_chart(fig, width="stretch", key="lect_report_perf", config=_PLOT_CONFIG)
            st.caption("Chỉ số đo trên tập kiểm tra lúc huấn luyện từng phiên bản.")

    workbook = lr.build_report_workbook(
        {
            "Tổng hợp": lr.report_summary(overview, len(df), len(consultations)),
            "Phân bố rủi ro": lr.risk_distribution(overview),
            "Nguy cơ cao": lr.high_risk_table(overview, label_fn=feature_label),
            "Phiên bản mô hình": versions,
            "Lịch sử tư vấn": lr.consultations_frame(lr.filter_consultations(consultations)),
        }
    )
    if _excel_download("Xuất báo cáo (Excel)", workbook, "bao_cao_lop", "lect_report_export", primary=True):
        st.caption("File gồm 5 trang tính: Tổng hợp, Phân bố rủi ro, Nguy cơ cao, Phiên bản mô hình, Lịch sử tư vấn.")
