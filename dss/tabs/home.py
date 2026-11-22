"""Trang chủ theo vai trò (Admin / Giảng viên / Sinh viên)."""

import plotly.graph_objects as go

from dss.config import *  # noqa: F403
from dss.core.data_helpers import feature_label
from dss.core.logging_config import get_logger
from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, filter_tabs_for_role
from dss.core.target_utils import is_id_like
from dss.services import llm_service
from dss.services.model_service import (
    compute_lecturer_dashboard_overview,
    compute_shap_local_explanation,
    resolve_production_for_prediction,
)
from dss.tabs import ui_kit

_logger = get_logger(__name__)

# Màu cột đóng góp tích cực / tiêu cực — tông trung bình, đọc được trên nền sáng
# lẫn nền tối (Plotly không đọc được biến CSS).
_POSITIVE_BAR = "#1E8E3E"
_NEGATIVE_BAR = "#D93025"
_NEUTRAL_BAR = "#2F5BD3"


@__import__("streamlit").cache_resource(show_spinner=False, max_entries=5000, ttl=3600)
def _cached_student_shap(_pipeline, training_id, input_df, background, feature_cols):
    """Bước 8 (22/11/2026): SHAP của Trang chủ Sinh viên tốn ~1 giây CPU mỗi lần trang vẽ lại. Lưu theo
    (bản mô hình Production, dòng dữ liệu đầu vào, nền so sánh) — đổi mô hình hoặc đổi dữ liệu là đổi khoá,
    nên không bao giờ dùng nhầm kết quả cũ. Chỉ đọc kết quả, không sửa."""
    return compute_shap_local_explanation(
        _pipeline, input_df, background, list(feature_cols), problem_type="regression"
    )


_GPA_COLUMNS = ["diem_ky_sau", "diem_ky_nay", "final_score", "gpa_previous", "gpa", "score", "total_score"]


def render_home_tab(role, wh=None, dashboard_mode=False, current_student_id=None, df=None, llm_integration=None):
    """Trang chủ theo vai trò.

    C1.3: màn giới thiệu "Bắt đầu khám phá" (hero marketing, huy hiệu công nghệ,
    "Đồ án tốt nghiệp") đã bị bỏ — người dùng vào thẳng trang chủ THẬT của vai
    trò mình. `dashboard_mode` giữ trong chữ ký để tương thích ngược."""
    _render_role_dashboard(role, wh, current_student_id, df, llm_integration=llm_integration)


def _render_role_dashboard(role, wh, current_student_id, df=None, llm_integration=None):
    """Trang chủ THẬT theo vai trò — mọi số liệu lấy từ warehouse/mô hình thật."""
    if role == "Admin":
        _render_admin_home_dashboard(wh, df)
    elif role == "Sinh viên":
        _render_student_home_dashboard(wh, current_student_id, df, llm_integration=llm_integration)
    else:
        render_lecturer_home(wh, df)


def _render_admin_home_dashboard(wh, df=None):
    if wh is None:
        ui_kit.page_header("Tổng quan hệ thống")
        ui_kit.error_state(
            "Không khởi tạo được kho dữ liệu",
            "Các số liệu tổng quan chưa thể hiển thị. Dữ liệu đã lưu không bị ảnh hưởng.",
            support_hint="Thử tải lại trang; nếu vẫn lỗi, kiểm tra cấu hình lưu trữ.",
        )
        return
    # Admin không có tab "Dashboard" riêng — dùng lại trang Báo cáo (KPI/biểu
    # đồ/hoạt động thật) làm trang tổng quan mặc định.
    from dss.tabs.admin_reports import admin_reports_tab

    admin_reports_tab(wh, df=df, as_home=True)


def _find_gpa_column(df):
    for col in _GPA_COLUMNS:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            return col
    return None


def render_lecturer_home(wh, df=None):
    """Trang chủ Giảng viên — trả lời "Điều gì cần tôi chú ý?". ĐỘC LẬP với
    "📊 Dashboard" (dashboard.py::main_dashboard_tab — không gian phân tích
    chuyên sâu), KHÔNG gọi lại hàm đó. Chỉ .predict() bằng bản Production có
    sẵn (compute_lecturer_dashboard_overview), không huấn luyện gì."""
    from dss.tabs.dashboard import _render_lecturer_kpi_row, _render_quick_actions

    _username = st.session_state.get("_auth_username") or ""
    st.markdown(
        "<div class='dss-lect-hero'>"
        f"<div class='dss-lect-hero-welcome'>Chào mừng trở lại{', ' + ui_kit._html.escape(_username) if _username else ''}</div>"
        "<h1 class='dss-lect-hero-title'>Tổng quan lớp học</h1>"
        "<p class='dss-lect-hero-sub'>Những sinh viên và chỉ số cần bạn chú ý trong dữ liệu lớp hiện tại.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    if df is None or wh is None:
        ui_kit.empty_state(
            "Chưa có dữ liệu lớp học để tổng hợp.",
            hint="Chọn hoặc tải dữ liệu lớp học ở trang Kho dữ liệu để xem tổng quan tại đây.",
        )
        return

    ui_kit.render_synthetic_data_banner(df)

    gpa_col_name = _find_gpa_column(df)
    overview = None
    if gpa_col_name:
        try:
            overview = compute_lecturer_dashboard_overview(
                df, wh, st.session_state.get("current_dataset_id"), gpa_col_name
            )
        except Exception:
            _logger.exception("Không tính được tổng quan lớp học (Trang chủ Giảng viên).")
            overview = {"status": "error", "message": "Không thể tính tổng quan lớp học."}
    _has_overview = bool(overview and overview.get("status") == "ok")

    avg_predicted = overview.get("avg_predicted") if _has_overview else None
    n_high_risk = overview["risk_counts"]["cao"] if _has_overview else None
    metric_value = overview.get("metric_value") if _has_overview else None
    metric_name = overview.get("metric_name") if _has_overview else None
    _metric_label, _metric_display, _metric_caption = ui_kit.model_metric_display(metric_name, metric_value, df)

    _render_lecturer_kpi_row(
        [
            ("", "blue", "Sinh viên trong dữ liệu", f"{len(df):,}", "Toàn bộ bộ dữ liệu đang chọn"),
            (
                "",
                "red" if n_high_risk else "neutral",
                "Sinh viên cần chú ý",
                n_high_risk if n_high_risk is not None else "—",
                (
                    f"{n_high_risk / len(df):.1%} tổng số · {ui_kit.RISK_RELATIVE_CAPTION}"
                    if n_high_risk is not None and len(df)
                    else "Chưa có mô hình dự đoán"
                ),
            ),
            (
                "",
                "green",
                "Điểm trung bình dự đoán",
                f"{avg_predicted:.2f}" if avg_predicted is not None else "—",
                "Theo mô hình đang dùng (Production)",
            ),
            ("", "purple", _metric_label, _metric_display, _metric_caption),
        ]
    )
    if n_high_risk is not None:
        st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
    elif overview and overview.get("status") == "error":
        ui_kit.alert_box(
            "Không tính được chỉ số rủi ro lúc này. Dữ liệu lớp học không bị thay đổi.",
            kind="warning",
            title="Tổng quan chưa đầy đủ",
        )

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    col_attn, col_next = st.columns([1.3, 1], gap="medium")
    with col_attn:
        with st.container(border=True):
            ui_kit.card_title("Sinh viên cần chú ý")
            if _has_overview and overview["high_risk_students"]:
                rows_html = []
                for _r in overview["high_risk_students"][:6]:
                    _sid = ui_kit._html.escape(str(_r["id"]))
                    rows_html.append(
                        "<div class='dss-lect-attn-row'>"
                        f"<div class='dss-lect-attn-avatar' aria-hidden='true'>{_sid[:2].upper()}</div>"
                        f"<div class='dss-lect-attn-id'>{_sid}</div>"
                        f"<span class='dss-lect-attn-badge'>{ui_kit.badge_html('Nhóm rủi ro cao (tương đối)', 'danger')}</span>"
                        "</div>"
                    )
                st.markdown("".join(rows_html), unsafe_allow_html=True)
                _more = len(overview["high_risk_students"]) - 6
                if _more > 0:
                    st.caption(f"Còn {_more} sinh viên khác — xem đầy đủ ở Dashboard.")
            elif _has_overview:
                ui_kit.empty_state("Không có sinh viên nào thuộc nhóm rủi ro cao trong dữ liệu này.")
            else:
                ui_kit.empty_state(
                    "Chưa xác định được sinh viên cần chú ý.",
                    hint="Cần một mô hình dự đoán điểm (Production) cho bộ dữ liệu này — huấn luyện ở trang Huấn luyện & dự đoán.",
                )

    with col_next:
        with st.container(border=True):
            ui_kit.card_title("Gợi ý hôm nay")
            if _has_overview and n_high_risk:
                _insight_text = (
                    f"{n_high_risk} sinh viên ({n_high_risk / len(df):.1%}) đang ở nhóm có điểm dự đoán thấp nhất lớp. "
                    "Xem yếu tố ảnh hưởng của từng em ở Dashboard trước khi liên hệ."
                )
            elif _has_overview:
                _insight_text = "Không có sinh viên nào ở nhóm rủi ro cao trong lớp này."
            else:
                _insight_text = (
                    "Chưa có mô hình Production để phân tích rủi ro lớp học — huấn luyện mô hình để xem gợi ý tại đây."
                )
            st.markdown(f"<p class='dss-muted' style='margin:0 0 12px;'>{_insight_text}</p>", unsafe_allow_html=True)
            if "📊 Dashboard" in filter_tabs_for_role(ALL_TABS, "Giảng viên / CVHT"):
                if st.button("Mở Dashboard", key="lect_home_open_dashboard", type="primary", width="stretch"):
                    st.session_state["_pending_nav_target"] = "📊 Dashboard"
                    st.rerun()

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    ui_kit.subsection_header("Truy cập nhanh")
    _render_quick_actions()


def _next_actions_for_student(student_row, negatives, df):
    """Việc nên làm tiếp theo — suy ra TRỰC TIẾP từ dữ liệu thật của sinh viên
    (yếu tố đóng góp âm lớn nhất, tỷ lệ điểm danh), không bịa hạn chót/khoá học."""
    actions = []
    for name, _value in (negatives or [])[:2]:
        actions.append(
            (f"Cải thiện: {feature_label(name)}", "Yếu tố này đang kéo điểm dự báo của bạn xuống nhiều nhất.")
        )
    attendance = student_row.get("ty_le_diem_danh") if "ty_le_diem_danh" in df.columns else None
    try:
        if attendance is not None and float(attendance) < 0.8:
            actions.append(
                ("Tăng tỷ lệ điểm danh", f"Hiện tại {float(attendance) * 100:.0f}% — nên duy trì từ 80% trở lên.")
            )
    except (TypeError, ValueError):
        pass
    return actions


def _render_student_home_dashboard(wh, current_student_id, df=None, llm_integration=None):
    """Trang chủ Sinh viên — trả lời 3 câu hỏi: Tôi đang học thế nào? Điều gì
    cần chú ý? Tôi nên làm gì tiếp theo? Không lộ thuật ngữ kỹ thuật (mô hình,
    provider, embedding...)."""
    ui_kit.page_header(
        f"Xin chào, {ui_kit._html.escape(str(current_student_id))}" if current_student_id else "Trang chủ",
        subtitle="Tổng quan học tập của bạn trong dữ liệu lớp hiện tại.",
    )
    if not current_student_id:
        ui_kit.error_state(
            "Không xác định được mã sinh viên của bạn",
            "Tài khoản hiện tại chưa gắn với mã sinh viên nào nên chưa thể hiển thị dữ liệu học tập.",
            support_hint="Vui lòng đăng nhập lại hoặc liên hệ Giảng viên/Quản trị viên.",
        )
        return
    if wh is None or df is None:
        ui_kit.empty_state("Chưa có dữ liệu lớp học để phân tích.")
        return

    id_col = next((c for c in df.columns if is_id_like(c)), df.columns[0])
    _rows = df[df[id_col].astype(str) == str(current_student_id)]
    if _rows.empty:
        ui_kit.empty_state(
            "Không tìm thấy dữ liệu của bạn trong bộ dữ liệu hiện tại.",
            hint="Liên hệ Giảng viên/Quản trị viên nếu bạn nghĩ đây là nhầm lẫn.",
        )
        return
    student_row = _rows.iloc[0]
    ui_kit.render_synthetic_data_banner(df)

    gpa_col = _find_gpa_column(df)
    dataset_id = st.session_state.get("current_dataset_id")
    resolved = None
    if gpa_col:
        try:
            resolved = resolve_production_for_prediction(wh, dataset_id, gpa_col)
        except Exception:
            _logger.exception("Không tải được mô hình Production cho Trang chủ Sinh viên.")
            resolved = {"status": "error", "message": "Không thể tải mô hình Production."}

    predicted_gpa = None
    risk_level = None
    shap_val = None
    positives = []
    negatives = []
    if resolved and resolved.get("status") == "ok" and resolved.get("hub_type") == "reg":
        feature_cols = resolved["feature_cols"]
        if not [c for c in feature_cols if c not in df.columns]:
            input_df = student_row[feature_cols].to_frame().T
            try:
                predicted_gpa = float(resolved["pipeline"].predict(input_df)[0])
            except Exception:
                _logger.exception("Dự đoán điểm cho Trang chủ Sinh viên thất bại.")
                predicted_gpa = None
            if predicted_gpa is not None:
                background = df[feature_cols].dropna().head(100)
                if resolved.get("training_id"):
                    shap_val, _err = _cached_student_shap(
                        resolved["pipeline"], resolved["training_id"], input_df, background, tuple(feature_cols)
                    )
                else:  # không có mã bản mô hình thì không có khoá cache an toàn
                    shap_val, _err = compute_shap_local_explanation(
                        resolved["pipeline"], input_df, background, feature_cols, problem_type="regression"
                    )
    # Mức rủi ro: CÙNG căn cứ và CÙNG định nghĩa với trang Tư vấn AI
    # (model_service.student_risk_profile) — dự đoán Production nếu có, nếu không
    # thì điểm hiện tại (ghi rõ là "theo điểm hiện tại", không gọi là dự đoán).
    risk_basis = None
    if gpa_col:
        try:
            from dss.services.model_service import student_risk_profile

            _risk_info = student_risk_profile(wh, dataset_id, gpa_col, df, student_row)
            risk_level = _risk_info.get("risk_level")
            risk_basis = _risk_info.get("source")
        except Exception:
            _logger.exception("Không tính được mức rủi ro cho Trang chủ Sinh viên.")
    if shap_val is not None:
        try:
            pairs = sorted(
                zip(list(shap_val[0].feature_names), list(shap_val[0].values)), key=lambda p: p[1], reverse=True
            )
            positives = [p for p in pairs if p[1] > 0][:5]
            negatives = sorted([p for p in pairs if p[1] < 0], key=lambda p: p[1])[:5]
        except Exception:
            shap_val = None

    # --- 1. Tôi đang học thế nào? — dải tóm tắt (chỉ số THẬT có trong dữ liệu) ---
    _class_avg = df[gpa_col].mean() if gpa_col else None
    _attendance = student_row.get('ty_le_diem_danh')
    _risk_kind = {"cao": "danger", "trung bình": "warning", "thấp": "success"}.get(risk_level, "neutral")
    _stats = []
    # Điểm HIỆN TẠI (không dùng cột mục tiêu của mô hình như "điểm kỳ sau").
    _current_col = next(
        (
            c
            for c in ("diem_ky_nay", "gpa_previous", "gpa", "score")
            if c in df.columns and c != gpa_col and pd.api.types.is_numeric_dtype(df[c])
        ),
        None,
    )
    if _current_col is not None and pd.notna(student_row.get(_current_col)):
        _stats.append(("Điểm hiện tại", f"{float(student_row.get(_current_col)):.2f}"))
    if predicted_gpa is not None:
        _stats.append(("Điểm dự báo", f"{predicted_gpa:.2f}"))
    if _class_avg is not None:
        _stats.append(("Trung bình lớp", f"{_class_avg:.2f}"))
    if isinstance(_attendance, (int, float)):
        _stats.append(("Điểm danh", f"{float(_attendance) * 100:.0f}%"))
    _sid_html = ui_kit._html.escape(str(current_student_id))
    st.markdown(
        "<div class='dss-summary'>"
        "<div class='dss-summary-identity'>"
        f"<span class='dss-avatar' aria-hidden='true'>{_sid_html[:2].upper()}</span>"
        f"<div style='min-width:0;'><div class='dss-summary-name'>{_sid_html}</div>"
        "<div class='dss-summary-meta'>Mức rủi ro: "
        + (
            ui_kit.badge_html(risk_level.capitalize(), _risk_kind)
            if risk_level
            else ui_kit.status_html("unavailable", "Chưa xác định")
        )
        + "</div></div></div>"
        + "".join(
            f"<div class='dss-summary-stat'><div class='dss-summary-stat-label'>{lbl}</div>"
            f"<div class='dss-summary-stat-value'>{val}</div></div>"
            for lbl, val in _stats
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    if risk_level:
        _basis = (
            "Căn cứ: điểm dự báo của mô hình đang dùng."
            if risk_basis == "model"
            else "Căn cứ: điểm hiện tại (lớp chưa có mô hình dự đoán)."
        )
        st.caption(f"{_basis} {ui_kit.RELATIVE_RISK_DISCLAIMER}")

    col_left, col_center, col_right = st.columns([1, 1.2, 1], gap="medium")

    with col_left:
        with st.container(border=True, key="student_home_card_forecast"):
            ui_kit.card_title("Điểm dự báo")
            if predicted_gpa is not None:
                # Đồng hồ 1 màu (không chia vùng đỏ/vàng/xanh) — vì mức rủi ro là
                # xếp hạng TƯƠNG ĐỐI trong lớp, không có ngưỡng tuyệt đối để tô màu.
                _gauge_max = max(float(df[gpa_col].max()) * 1.05, predicted_gpa * 1.05, 1.0)
                fig_gauge = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=predicted_gpa,
                        number={"font": {"size": 34}, "valueformat": ".2f"},
                        gauge={
                            "axis": {"range": [0, _gauge_max]},
                            "bar": {"color": _NEUTRAL_BAR},
                            "bgcolor": "rgba(138,148,166,0.18)",
                            "borderwidth": 0,
                        },
                    )
                )
                fig_gauge.update_layout(height=190, margin=dict(t=16, b=0, l=24, r=24))
                st.plotly_chart(fig_gauge, width="stretch", key="student_dash_gauge", config={"displayModeBar": False})
                ui_kit.render_badge(f"Rủi ro: {risk_level or '—'}", _risk_kind)
                st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
                if _class_avg is not None:
                    _gap = predicted_gpa - _class_avg
                    st.markdown(
                        f"<div class='dss-kv'><span class='dss-kv-key'>Trung bình lớp</span><span class='dss-kv-value'>{_class_avg:.2f}</span></div>"
                        f"<div class='dss-kv'><span class='dss-kv-key'>Chênh lệch so với lớp</span><span class='dss-kv-value'>{_gap:+.2f}</span></div>",
                        unsafe_allow_html=True,
                    )
                st.caption("Dự báo từ mô hình của lớp — tham khảo để định hướng, không phải kết quả chính thức.")
            else:
                ui_kit.empty_state(
                    "Chưa có điểm dự báo.",
                    hint="Giảng viên cần kích hoạt mô hình dự đoán điểm cho lớp của bạn.",
                )
            if 'ty_le_diem_danh' in df.columns:
                try:
                    _att = min(max(float(student_row.get('ty_le_diem_danh', 0)), 0.0), 1.0)
                    st.progress(_att, text=f"Tỷ lệ điểm danh: {_att * 100:.0f}%")
                except (TypeError, ValueError):
                    pass
            if 'so_gio_hoc_tuan' in df.columns:
                st.caption(f"Số giờ tự học mỗi tuần: {student_row.get('so_gio_hoc_tuan')}")

    # --- 2. Điều gì cần chú ý? ---
    with col_center:
        with st.container(border=True, key="student_home_card_factors"):
            ui_kit.card_title("Yếu tố ảnh hưởng đến điểm dự báo")
            if shap_val is not None and (positives or negatives):
                st.caption(
                    "Mức đóng góp của từng yếu tố vào điểm dự báo — cho biết yếu tố nào kéo điểm lên hay xuống, "
                    "không phải quan hệ nhân quả."
                )
                for _title, _items, _color, _fmt in (
                    ("Đang giúp điểm của bạn", positives, _POSITIVE_BAR, "+{:.2f}"),
                    ("Đang kéo điểm của bạn xuống", negatives, _NEGATIVE_BAR, "{:.2f}"),
                ):
                    st.markdown(
                        f"<div class='dss-muted' style='font-weight:600;margin-top:8px;'>{_title}</div>",
                        unsafe_allow_html=True,
                    )
                    if not _items:
                        st.caption("Không có yếu tố nổi bật.")
                        continue
                    _names = [feature_label(n) for n, _ in _items]
                    _vals = [v for _, v in _items]
                    _fig = go.Figure(
                        go.Bar(
                            x=_vals,
                            y=_names,
                            orientation="h",
                            marker_color=_color,
                            text=[_fmt.format(v) for v in _vals],
                            textposition="auto",
                            hovertemplate="%{y}: %{x:.3f}<extra></extra>",
                        )
                    )
                    _fig.update_layout(
                        height=30 * len(_names) + 36,
                        margin=dict(t=4, b=4, l=4, r=8),
                        showlegend=False,
                        xaxis_title=None,
                        yaxis_title=None,
                        yaxis=dict(autorange="reversed", automargin=True),
                    )
                    st.plotly_chart(
                        _fig, width="stretch", key=f"student_dash_factors_{_color}", config={"displayModeBar": False}
                    )
            else:
                ui_kit.empty_state(
                    "Chưa có phân tích yếu tố ảnh hưởng.",
                    hint="Cần có điểm dự báo trước (xem thẻ bên trái).",
                )

    # --- 3. Tôi nên làm gì tiếp theo? ---
    with col_right:
        with st.container(border=True, key="student_home_card_ai"):
            ui_kit.card_title("Việc nên làm tiếp theo")
            _actions = _next_actions_for_student(student_row, negatives, df)
            if _actions:
                st.markdown(
                    "".join(
                        f"<div class='dss-list-row'><div style='min-width:0;'>"
                        f"<div class='dss-list-row-main' style='white-space:normal;'>{ui_kit._html.escape(t)}</div>"
                        f"<div class='dss-list-row-meta'>{ui_kit._html.escape(d)}</div></div></div>"
                        for t, d in _actions
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Chưa có việc cần ưu tiên từ dữ liệu hiện tại.")

            try:
                consultations = wh.get_history("advisor", limit=10000)
            except Exception:
                _logger.exception("Không đọc được lịch sử tư vấn cho Trang chủ Sinh viên.")
                consultations = []
            my_consultations = sorted(
                [c for c in consultations if str(c.get("student_id")) == str(current_student_id)],
                key=lambda c: c.get("created_at", ""),
                reverse=True,
            )
            st.markdown("<div class='dss-spacer-8'></div>", unsafe_allow_html=True)
            if my_consultations:
                latest = my_consultations[0]
                st.caption(f"Kế hoạch học tập gần nhất · {latest.get('created_at', '')}")
                _plan = (latest.get("generated_plan") or "")[:220]
                st.markdown(_plan + ("…" if len(latest.get("generated_plan") or "") > 220 else ""))
            if st.button("Lập kế hoạch học tập", key="student_dash_goto_ai", type="primary", width="stretch"):
                target_tabs = [t for t in filter_tabs_for_role(ALL_TABS, "Sinh viên") if t != HOME_TAB_LABEL]
                _ai_tab = next((t for t in target_tabs if "Tư vấn" in t), target_tabs[0] if target_tabs else None)
                if _ai_tab:
                    st.session_state["_pending_nav_target"] = _ai_tab
                    st.rerun()

            # --- Hỏi nhanh Trợ lý AI (1 lượt). Hệ thống TỰ chọn nguồn AI sẵn
            # sàng; câu hỏi được ghép ngữ cảnh ĐÃ tối thiểu hoá (C1.1) — không
            # gửi mã sinh viên hay điểm chính xác ra nhà cung cấp AI. ---
            st.markdown("<div class='dss-spacer-8'></div>", unsafe_allow_html=True)
            _quick_q = st.text_input(
                "Hỏi nhanh Trợ lý AI",
                placeholder="Ví dụ: Tôi nên ưu tiên môn nào tuần này?",
                key="student_dash_quick_ask",
            )
            if st.button("Gửi câu hỏi", key="student_dash_quick_ask_btn", width="stretch") and _quick_q.strip():
                _auto = llm_service.resolve_auto_provider(llm_integration) if llm_integration is not None else None
                if not _auto:
                    ui_kit.unavailable_state(
                        "Trợ lý AI trực tuyến chưa sẵn sàng",
                        "Hiện chưa có dịch vụ AI nào được cấu hình để trả lời câu hỏi tự do. Không có câu hỏi nào được gửi đi.",
                        support_hint="Bạn vẫn có thể dùng nút \"Lập kế hoạch học tập\" ở trên.",
                    )
                else:
                    _weakest = negatives[0][0] if negatives else None
                    from dss.services.privacy_service import build_quick_question_prompt

                    _context = build_quick_question_prompt(risk_level, predicted_gpa, _weakest, _quick_q)
                    _kwargs = {"model_name": _auto["model_name"]}
                    if _auto["provider_key"] in ("gemini", "groq", "openai"):
                        _kwargs["api_key"] = _auto["api_key"]
                    elif _auto["provider_key"] == "ollama":
                        from dss.core.models import ollama_base_url

                        _kwargs["base_url"] = ollama_base_url()
                    elif _auto["provider_key"] == "huggingface":
                        _kwargs["hf_token"] = _auto["api_key"]
                    with st.spinner("Trợ lý AI đang trả lời…"):
                        try:
                            from dss.services.llm_gateway import LLMGateway
                            from dss.services.privacy_service import privacy_service

                            _gw = LLMGateway(llm_integration)
                            _stream = _gw.stream_generate(
                                prompt=_context,
                                user_id=privacy_service.generate_pseudonym(str(current_student_id)),
                                # Trước C1.3 dòng này đọc biến `role` KHÔNG tồn tại trong
                                # hàm này -> NameError -> luôn rơi vào nhánh lỗi bên dưới.
                                role="Sinh viên",
                                request_type="home_quick_chat",
                                provider=_auto["provider_key"],
                                model=_auto.get("model_name") or "default",
                                **_kwargs,
                            )
                            with st.container(border=True):
                                st.write_stream(_stream)
                            st.caption("Câu trả lời do AI tạo để tham khảo — không phải quyết định học vụ chính thức.")
                        except Exception:
                            _logger.exception("Dashboard quick-ask failed")
                            ui_kit.unavailable_state(
                                "Chưa nhận được câu trả lời",
                                "Dịch vụ AI không phản hồi lúc này. Dữ liệu của bạn không bị thay đổi.",
                                support_hint="Vui lòng thử lại sau ít phút.",
                            )
