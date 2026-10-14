"""Shared runtime imports for Streamlit tab modules."""
from dss.config import *  # noqa: F403
from dss.core.data_helpers import feature_label
from dss.core.utils import (
    render_chart_guide,
    render_chart_guide_advanced,
    st_step_header,
)
from dss.core.init_app import clear_all_session_state_for_new_data
from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, filter_tabs_for_role
from dss.services import model_service
from dss.services.model_service import compute_lecturer_dashboard_overview
from dss.tabs import ui_kit


def _format_activity_timestamp(ts) -> str:
    if not ts:
        return "—"
    s = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)[:22]


def _dashboard_training_summary(ss):
    """Tóm tắt kết quả huấn luyện trong session (nếu có)."""
    out = []
    if "prediction_results" not in ss or not ss["prediction_results"]:
        return out
    pred_type = ss.get("prediction_type", "unknown")
    if pred_type == "classification":
        best_model_name, best_metrics = max(
            ss["prediction_results"].items(),
            key=lambda item: item[1].get("Accuracy", 0),
        )
        out.append(
            {
                "type": "Phân loại",
                "model": best_model_name,
                "metrics": {
                    "Accuracy": best_metrics.get("Accuracy"),
                    "F1": best_metrics.get("F1 Score (Weighted)"),
                },
            }
        )
    elif pred_type == "regression":
        best_model_name, best_metrics = max(
            ss["prediction_results"].items(),
            key=lambda item: item[1].get("R2 Score", 0),
        )
        out.append(
            {
                "type": "Hồi quy",
                "model": best_model_name,
                "metrics": {
                    "R2": best_metrics.get("R2 Score"),
                    "RMSE": best_metrics.get("RMSE"),
                    "MAE": best_metrics.get("MAE"),
                },
            }
        )
    return out


def render_dashboard_activity_feed(wh, ss):
    """Khối 'Hoạt động gần nhất' — luôn đọc mới từ warehouse + session."""
    latest_training = _dashboard_training_summary(ss)
    prediction_history_from_wh = wh.get_history("prediction", limit=5)
    activity_history = wh.get_merged_recent_activities(limit=25)
    has_batch_predictions = (
        "clf_batch_results_file" in ss or "reg_batch_results_file" in ss
    )

    if (
        activity_history
        or latest_training
        or prediction_history_from_wh
        or has_batch_predictions
    ):
        st.markdown("---")
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        with c1:
            st.markdown("### Hoạt động gần nhất")
        with c2:
            if st.button("🔄 Làm mới", key="dash_refresh_activity", help="Tải lại lịch sử từ kho"):
                st.rerun()
        st.caption(
            "Danh sách cập nhật theo kho dữ liệu; nếu bạn vừa thao tác ở tab khác, "
            "quay lại đây hoặc đợi vài giây (tự làm mới)."
        )

    if activity_history:
        st.markdown("#### Lịch sử thao tác")
        for act in activity_history:
            act_time = _format_activity_timestamp(act.get("timestamp"))
            atype = act.get("activity_type", "Hoạt động")
            desc = act.get("description", "")
            st.markdown(
                f"- **{atype}** · {desc} · _{act_time}_"
            )
        st.markdown("---")

    if latest_training:
        st.markdown("#### Huấn luyện (phiên hiện tại)")
        for item in latest_training:
            metrics = item["metrics"]
            if item["type"] == "Phân loại":
                acc = metrics.get("Accuracy") or 0
                f1_score = metrics.get("F1") or 0
                st.markdown(
                    f"- **{item['type']}** · Mô hình: `{item['model']}` · Accuracy: {acc:.4f} · F1: {f1_score:.4f}"
                )
            else:
                r2_val = metrics.get("R2")
                rmse_val = metrics.get("RMSE")
                st.markdown(
                    f"- **{item['type']}** · Mô hình: `{item['model']}` · R2: {(r2_val or 0):.3f} · RMSE: {(rmse_val or 0):.3f}"
                )

    if prediction_history_from_wh:
        st.markdown("#### Dự đoán cá nhân (kho)")
        for item in prediction_history_from_wh:
            predicted_at = _format_activity_timestamp(item.get("predicted_at"))
            meta = item.get("metadata") or {}
            model_name = meta.get("model_name", "unknown")

            if "label" in meta:
                label = item.get("prediction")
                probabilities = meta.get("probabilities")
                weak_features = meta.get("weak_features", [])
                st.markdown(
                    f"- **Phân loại** · Mô hình: `{model_name}` · Kết quả: **{label}** · {predicted_at}"
                )
                if probabilities:
                    probs_str = ", ".join(
                        [f"{k}: {v * 100:.1f}%" for k, v in probabilities.items()]
                    )
                    st.markdown(f"  - Xác suất: {probs_str}")
                if weak_features:
                    st.markdown(
                        f"  - Cần cải thiện: {', '.join(weak_features[:5])}"
                    )
            elif "value" in meta:
                value = item.get("prediction")
                try:
                    vdisp = f"{float(value):.2f}"
                except (TypeError, ValueError):
                    vdisp = str(value)
                grade_label = meta.get("grade_label", "")
                confidence_interval = meta.get("confidence_interval")
                st.markdown(
                    f"- **Hồi quy** · Mô hình: `{model_name}` · Dự đoán: **{vdisp}** ({grade_label}) · {predicted_at}"
                )
                if confidence_interval:
                    st.markdown(
                        f"  - Khoảng tin cậy (ước tính): ±{confidence_interval:.2f}"
                    )

    if "clf_batch_results_file" in ss:
        df_clf_batch = ss["clf_batch_results_file"]
        pred_cols = [
            c
            for c in df_clf_batch.columns
            if "dự_đoán" in c.lower() or "pred" in c.lower()
        ]
        if pred_cols:
            col = pred_cols[0]
            st.markdown("#### Dự đoán file (phân loại)")
            st.markdown(f"- Số bản ghi: **{len(df_clf_batch)}**")
            counts = df_clf_batch[col].value_counts()
            st.dataframe(counts.to_frame("Số lượng"), width="stretch")

    if "reg_batch_results_file" in ss:
        df_reg_batch = ss["reg_batch_results_file"]
        pred_cols = [
            c
            for c in df_reg_batch.columns
            if "dự_đoán" in c.lower() or "pred" in c.lower()
        ]
        if pred_cols:
            col = pred_cols[0]
            st.markdown("#### Dự đoán file (hồi quy)")
            st.markdown(f"- Số bản ghi: **{len(df_reg_batch)}**")
            st.markdown(
                f"- Giá trị trung bình dự đoán: **{df_reg_batch[col].mean():.2f}**"
            )


def _render_dashboard_toolbar_header():
    """Tiêu đề trang THẬT (không phải hero chào mừng — đó là của Trang chủ,
    xem `home.py::render_lecturer_home`). Dashboard là không gian PHÂN TÍCH
    CHUYÊN SÂU, khác hẳn mục đích "landing/welcome" của Trang chủ — tiêu đề
    dùng đúng `ui_kit.section_header` như 1 trang phân tích thông thường,
    không dùng lại hero. Nút "Chỉnh sửa dữ liệu" vẫn chỉ TOGGLE hiển thị khối
    chỉnh sửa điểm (không phải 1 expander khổng lồ dưới tiêu đề)."""
    col_title, col_toggle = st.columns([4, 1], vertical_alignment="bottom")
    with col_title:
        ui_kit.section_header(
            "Dashboard lớp học",
            subtitle="Phân tích chuyên sâu dữ liệu học tập và hiệu quả mô hình.",
            icon="📊",
        )
    with col_toggle:
        if st.button("✏️ Chỉnh sửa dữ liệu", key="toggle_grade_editor", width="stretch"):
            st.session_state["_show_grade_editor"] = not st.session_state.get("_show_grade_editor", False)


def _render_grade_editor(df, wh):
    """Khối chỉnh sửa điểm — logic GIỮ NGUYÊN 100% so với bản trước, chỉ đổi
    nơi hiển thị: giờ ẩn mặc định, chỉ hiện khi bấm nút toggle ở hero phía
    trên (session_state["_show_grade_editor"])."""
    if not st.session_state.get("_show_grade_editor", False):
        return
    with st.container(border=True):
        st.markdown("##### Chỉnh sửa điểm sinh viên")
        _gv_id_col = next((c for c in df.columns if 'id' in c.lower()), df.columns[0] if len(df.columns) else None)
        st.caption(
            "Sửa trực tiếp trên bảng rồi bấm Lưu. Hệ thống KHÔNG tự tính lại xếp loại/điểm suy ra "
            "từ các cột khác — vui lòng nhập nhất quán. Sau khi lưu, mô hình dự đoán và phân cụm "
            "mặc định sẽ tự huấn luyện lại trên điểm mới."
        )
        _editor_key = f"gv_grade_editor_{st.session_state.get('current_dataset_id', 'na')}"
        edited_df = st.data_editor(
            df,
            key=_editor_key,
            disabled=[_gv_id_col] if _gv_id_col else False,
            num_rows="fixed",
            width="stretch",
        )
        if st.button("💾 Lưu thay đổi điểm vào hệ thống", key="gv_save_grade_edits_btn", type="primary"):
            if edited_df.equals(df):
                st.info("Chưa có thay đổi nào để lưu.")
            else:
                clear_all_session_state_for_new_data()
                st.session_state.current_df = edited_df
                _save_ok = wh is None  # Không có warehouse cấu hình -> không có gì để lưu thất bại
                if wh is not None:
                    try:
                        _new_ds_id, _ = wh.save_dataset(
                            edited_df,
                            dataset_name=f"edited_{st.session_state.get('current_dataset_id', 'data')}",
                            description="Điểm đã được Giảng viên chỉnh sửa thủ công",
                            data_type="raw",
                        )
                        st.session_state.current_dataset_id = _new_ds_id
                        _save_ok = True
                    except Exception:
                        from dss.core.logging_config import get_logger
                        get_logger(__name__).exception("Lưu thay đổi điểm vào kho dữ liệu thất bại (mã EDSS-GRADE-SAVE-001).")
                # FINAL PRODUCTION GAP CLOSURE (Phần 3/4): KHÔNG hiện "Đã lưu"
                # nếu wh.save_dataset() thực ra đã lỗi thầm lặng — trước đây
                # luôn hiện thành công dù save that bai, khiến Giảng viên tưởng
                # thay đổi điểm đã được lưu lâu dài trong khi thực ra chỉ tồn
                # tại tạm thời trong phiên (mất khi tải lại trang/khởi động lại).
                if _save_ok:
                    st.session_state.show_success_message = "✅ Đã lưu thay đổi điểm! Mô hình sẽ tự huấn luyện lại."
                else:
                    st.session_state.show_error_message = (
                        "⚠️ Không thể lưu thay đổi điểm vào kho dữ liệu lâu dài — thay đổi chỉ "
                        "áp dụng tạm thời cho phiên làm việc này. Vui lòng thử lại hoặc liên hệ quản trị viên."
                    )
                st.rerun()


def _render_lecturer_kpi_row(items):
    """Hàng thẻ KPI của Trang chủ/Dashboard Giảng viên. items: (icon, kind,
    label, value, caption) — `icon` giữ trong bộ để tương thích ngược, không
    render (C1.3: bỏ ô icon tô màu trang trí). Chỉ kind "red" (chỉ số rủi ro)
    có vạch trạng thái bên trái."""
    cards_html = []
    for _icon, kind, label, value, caption in items:
        accent = " dss-lect-kpi-card--danger" if kind == "red" else ""
        cards_html.append(
            f"<div class='dss-lect-kpi-card{accent}'>"
            "<div class='dss-lect-kpi-body'>"
            f"<span class='dss-lect-kpi-label'>{label}</span>"
            f"<strong class='dss-lect-kpi-value'>{value}</strong>"
            f"<small class='dss-lect-kpi-caption'>{caption}</small>"
            "</div></div>"
        )
    st.markdown(f"<div class='dss-lect-kpi-row'>{''.join(cards_html)}</div>", unsafe_allow_html=True)


def _bucket_predicted_scores(predicted_values):
    """Chia giá trị dự đoán thành 4 nhóm hiệu suất — DÙNG NGƯỠNG THẬT của
    thang điểm 10 (phổ biến ở VN, dữ liệu mẫu/LMS giả lập của hệ thống đều
    theo thang này) khi giá trị nằm trong khoảng hợp lý; nếu dữ liệu người
    dùng tải lên ở thang điểm khác (vd. 0-100, 0-4— không đoán được), tự
    chuyển sang chia theo tứ phân vị của CHÍNH dữ liệu đó thay vì áp bừa
    ngưỡng thang 10 — không suy diễn thang điểm khi không chắc chắn."""
    arr = np.asarray([v for v in predicted_values if pd.notna(v)], dtype=float)
    if len(arr) == 0:
        return []
    vmax = float(np.max(arr))
    vmin = float(np.min(arr))
    if vmin >= -0.5 and vmax <= 10.5:
        bins = [
            ("Giỏi (≥ 8.0)", int((arr >= 8.0).sum()), "#16A34A"),
            ("Khá (6.5 - 7.9)", int(((arr >= 6.5) & (arr < 8.0)).sum()), "#2563EB"),
            ("Trung bình (5.0 - 6.4)", int(((arr >= 5.0) & (arr < 6.5)).sum()), "#F59E0B"),
            ("Yếu (< 5.0)", int((arr < 5.0).sum()), "#EF4444"),
        ]
    else:
        q1, q2, q3 = np.quantile(arr, [0.25, 0.5, 0.75])
        bins = [
            (f"Nhóm cao nhất (≥ {q3:.2f})", int((arr >= q3).sum()), "#16A34A"),
            (f"Nhóm khá ({q2:.2f} - {q3:.2f})", int(((arr >= q2) & (arr < q3)).sum()), "#2563EB"),
            (f"Nhóm trung bình ({q1:.2f} - {q2:.2f})", int(((arr >= q1) & (arr < q2)).sum()), "#F59E0B"),
            (f"Nhóm thấp nhất (< {q1:.2f})", int((arr < q1).sum()), "#EF4444"),
        ]
    return [b for b in bins if b[1] > 0] or bins


def _render_quick_actions(current_role="Giảng viên / CVHT"):
    """Truy cập nhanh tới các trang THẬT đã có (không tạo route mới) — dùng
    lại cơ chế `_pending_nav_target`."""
    _qa_items = [
        ("cluster", "Phân cụm & gợi ý", "Nhóm sinh viên theo kết quả và hành vi học tập.", "Phân cụm", "Mở phân cụm"),
        ("train", "Huấn luyện & dự đoán", "Huấn luyện, đánh giá và chạy mô hình dự đoán kết quả học tập.", "Huấn luyện", "Mở huấn luyện"),
        ("ai", "Trợ lý AI", "Lập kế hoạch hỗ trợ cá nhân hoá cho từng sinh viên, có dẫn nguồn.", "Tư vấn", "Mở Trợ lý AI"),
    ]
    _qa_cols = st.columns(3, gap="medium")
    _tabs_for_role = filter_tabs_for_role(ALL_TABS, current_role)
    for _col, (_kind, _title, _desc, _match, _cta) in zip(_qa_cols, _qa_items):
        with _col:
            with st.container(border=True, key=f"lect_quick_{_kind}"):
                st.markdown(
                    f"<div class='dss-lect-quick-title'>{_title}</div>"
                    f"<p class='dss-lect-quick-desc'>{_desc}</p>",
                    unsafe_allow_html=True,
                )
                if st.button(_cta, key=f"lect_quick_btn_{_kind}", width="stretch"):
                    _target = next((t for t in _tabs_for_role if _match in t and t != HOME_TAB_LABEL), None)
                    if _target:
                        st.session_state["_pending_nav_target"] = _target
                        st.rerun()


def main_dashboard_tab(df, wh=None):
    """Dashboard tổng quan: KPI, phân tích điểm, xếp loại. KHÔNG phải Trang chủ
    (xem `home.py::render_lecturer_home` — trang chào mừng/tổng quan nhẹ
    riêng biệt, KHÔNG gọi hàm này) — đây là không gian phân tích chuyên sâu:
    KPI dày đặc, rủi ro + phân cụm + phân bố điểm + yếu tố quan trọng + bảng
    sinh viên rủi ro cao đầy đủ (tìm kiếm/export/xem chi tiết)."""
    ui_kit.render_synthetic_data_banner(df)  # E-1: cảnh báo rõ khi đang xem dữ liệu mô phỏng
    _render_dashboard_toolbar_header()
    _render_grade_editor(df, wh)

    # Tìm cột GPA/Điểm số (dùng lại ở cả KPI mới lẫn phần phân tích chi tiết bên dưới)
    gpa_col_name = None
    for col in ['diem_ky_sau', 'diem_ky_nay', 'final_score', 'gpa_previous', 'gpa', 'score', 'total_score']:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            gpa_col_name = col
            break

    grade_col_name = None
    for col in ['xep_loai', 'grade', 'classification', 'rank', 'level']:
        if col in df.columns:
            grade_col_name = col
            break

    # Dùng lại ở phần "Phân tích chi tiết" bên dưới (histogram điểm số).
    avg_gpa = df[gpa_col_name].mean() if gpa_col_name and pd.api.types.is_numeric_dtype(df[gpa_col_name]) else 0.0

    # ========================================================================
    # TỔNG QUAN LỚP HỌC — KPI + rủi ro + cụm, dựng từ bản Production hiện tại
    # trong Model Registry (model_service.compute_lecturer_dashboard_overview),
    # KHÔNG train/predict riêng cho dashboard này.
    # ========================================================================
    dataset_id = st.session_state.get("current_dataset_id")
    overview = None
    if wh is not None and gpa_col_name:
        try:
            overview = compute_lecturer_dashboard_overview(df, wh, dataset_id, gpa_col_name)
        except Exception:
            overview = {"status": "error", "message": "Không thể tính tổng quan lớp học."}

    avg_predicted = overview.get("avg_predicted") if overview and overview.get("status") == "ok" else None
    n_high_risk = overview["risk_counts"]["cao"] if overview and overview.get("status") == "ok" else None
    metric_value = overview.get("metric_value") if overview and overview.get("status") == "ok" else None
    metric_name = overview.get("metric_name") if overview and overview.get("status") == "ok" else None
    _has_overview = bool(overview and overview.get("status") == "ok")

    # KPI dùng `ui_kit.kpi_row` (viền trái màu — component DÙNG CHUNG với các
    # trang phân tích khác như Báo cáo/Phân cụm) — CỐ Ý khác kiểu icon-tile
    # của Trang chủ để 2 trang phân biệt rõ ràng khi nhìn (yêu cầu thiết kế:
    # "shared components: yes, same page layout: no"). Không bịa % thay đổi
    # so với "kỳ trước" (không có dữ liệu kỳ trước thật để so sánh).
    _metric_label, _metric_display, _metric_caption = ui_kit.model_metric_display(metric_name, metric_value, df)
    ui_kit.kpi_row(
        [
            ("👥 Tổng số sinh viên", f"{len(df):,}", None, None),
            ("🎓 GPA dự đoán trung bình", f"{avg_predicted:.2f}" if avg_predicted is not None else "—", None, "success"),
            ("⚠️ Nguy cơ học tập cao", n_high_risk if n_high_risk is not None else "—", ui_kit.RISK_RELATIVE_CAPTION, "danger"),
            (f"🎯 {_metric_label}", _metric_display, _metric_caption, "purple"),
        ]
    )

    if overview and overview.get("status") == "empty":
        ui_kit.empty_state(
            "Chưa có mô hình Production để dự đoán rủi ro cho lớp học này.",
            hint="Huấn luyện mô hình ở tab \"Huấn luyện — Dự đoán\" — mô hình tốt nhất sẽ được lưu ở trạng thái Candidate, chờ Admin duyệt lên Production.",
        )
    elif overview and overview.get("status") == "error":
        ui_kit.empty_state("Không thể tính rủi ro theo lớp.", hint=overview.get("message"))

    # --- HÀNG PHÂN TÍCH 1: Rủi ro (~60%) | Phân cụm/Phân khúc (~40%) ---
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
    col_risk, col_cluster = st.columns([1.5, 1.0], gap="medium")

    with col_risk:
        with st.container(border=True):
            st.markdown("##### Phân bố mức độ rủi ro hiện tại")
            if _has_overview:
                risk_counts = overview["risk_counts"]
                fig_risk = px.bar(
                    x=["Cao", "Trung bình", "Thấp"],
                    y=[risk_counts["cao"], risk_counts["trung bình"], risk_counts["thấp"]],
                    labels={"x": "Mức rủi ro", "y": "Số sinh viên"},
                    color=["Cao", "Trung bình", "Thấp"],
                    color_discrete_map={"Cao": "#ef4444", "Trung bình": "#f59e0b", "Thấp": "#10b981"},
                )
                fig_risk.update_layout(showlegend=False, template="plotly_white", height=300, margin=dict(t=10, b=10))
                st.plotly_chart(fig_risk, width="stretch", key="lecturer_dash_risk_bar")
                st.caption(
                    "Rủi ro dựa trên phân vị 25%/50% của điểm dự đoán so với chính lớp học này "
                    "(cùng cách tính đã dùng cho tư vấn AI cá nhân). Không có dữ liệu nhiều học kỳ để "
                    "vẽ xu hướng theo thời gian — hiển thị phân bố hiện tại thay vì bịa số liệu quá khứ."
                )
            else:
                ui_kit.empty_state("Chưa có dữ liệu rủi ro.", hint="Cần một mô hình Production hồi quy cho lớp này.")

    with col_cluster:
        with st.container(border=True):
            st.markdown("##### Phân khúc sinh viên (K-Means)")
            _cluster_df = st.session_state.get("cluster_results_df")
            _cluster_feats = st.session_state.get("cluster_selected_cols") or []
            if _cluster_df is not None and "cluster" in _cluster_df.columns:
                _counts = _cluster_df["cluster"].value_counts().sort_index()
                fig_cl = px.pie(
                    values=_counts.values,
                    names=[f"Cụm {c}" for c in _counts.index],
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_cl.update_layout(template="plotly_white", height=300, margin=dict(t=10, b=10))
                st.plotly_chart(fig_cl, width="stretch", key="lecturer_dash_cluster_pie")
                st.caption(f"{len(_counts)} cụm · dữ liệu từ tab \"Phân cụm — Gợi ý\".")
            else:
                ui_kit.empty_state(
                    "Chưa có kết quả phân cụm.",
                    hint="Chạy phân cụm ở tab \"Phân cụm — Gợi ý\" để xem phân khúc sinh viên tại đây.",
                )

    # --- HÀNG PHÂN TÍCH 2: Phân bố GPA dự đoán | Yếu tố quan trọng nhất ---
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
    col_gpa, col_factors = st.columns([1.0, 1.0], gap="medium")

    with col_gpa:
        with st.container(border=True):
            st.markdown("##### Phân bố GPA dự đoán")
            _predicted_values = overview.get("predicted_values") if _has_overview else None
            if _predicted_values:
                _bins = _bucket_predicted_scores(_predicted_values)
                fig_gpa = go.Figure(
                    data=[
                        go.Pie(
                            labels=[b[0] for b in _bins],
                            values=[b[1] for b in _bins],
                            hole=0.55,
                            marker=dict(colors=[b[2] for b in _bins]),
                            textinfo="percent",
                            sort=False,
                        )
                    ]
                )
                fig_gpa.update_layout(
                    template="plotly_white", height=300, margin=dict(t=10, b=10),
                    showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.35, font=dict(size=9)),
                    annotations=[dict(text=f"{len(_predicted_values):,}<br>sinh viên", x=0.5, y=0.5, font_size=14, showarrow=False)],
                )
                st.plotly_chart(fig_gpa, width="stretch", key="lecturer_dash_gpa_donut")
                st.caption(f"Phân loại theo điểm dự đoán (`{overview['target_col']}`) của chính lớp học này.")
            else:
                ui_kit.empty_state("Chưa có dữ liệu để phân bố.", hint="Cần một mô hình Production hồi quy cho lớp này.")

    with col_factors:
        with st.container(border=True):
            st.markdown("##### Yếu tố quan trọng nhất")
            _fi_df = pd.DataFrame()
            if _has_overview and overview.get("pipeline") is not None and overview.get("feature_cols"):
                _fi_df = model_service.get_production_feature_importance(overview["pipeline"], overview["feature_cols"])
            if not _fi_df.empty:
                fig_fi = px.bar(
                    _fi_df.sort_values("Importance (%)"), x="Importance (%)", y="Feature",
                    orientation="h", text="Importance (%)",
                )
                fig_fi.update_traces(marker_color="#1d4ed8", textposition="outside")
                fig_fi.update_layout(template="plotly_white", height=300, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_fi, width="stretch", key="lecturer_dash_feature_importance")
                st.caption(
                    f"Đọc trực tiếp từ mô hình Production hiện tại (`{overview['model_name']}`) — "
                    "KHÔNG huấn luyện thêm mô hình nào để vẽ biểu đồ này."
                )
            else:
                ui_kit.empty_state(
                    "Mô hình Production hiện tại không hỗ trợ mức độ quan trọng đặc trưng.",
                    hint="Chỉ các mô hình dạng cây (Random Forest, XGBoost, LightGBM...) mới có chỉ số này.",
                )

    # --- Trạng thái mô hình (thông tin vận hành — không phải KPI nghiệp vụ) ---
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("##### Trạng thái mô hình & dữ liệu")
        _mcol1, _mcol2, _mcol3 = st.columns(3)
        if _has_overview:
            _mcol1.metric("Mô hình Production", overview.get("model_name") or "—")
            _mcol1.caption(f"Version {overview.get('version')}" if overview.get("version") else "")
        else:
            _mcol1.metric("Mô hình Production", "—")
        _recent_for_status = wh.get_recent_activities(limit=1) if wh else []
        _mcol2.metric("Hoạt động gần nhất", _format_activity_timestamp(_recent_for_status[0].get("timestamp")) if _recent_for_status else "—")
        _missing_pct = float(df.isna().mean().mean() * 100) if len(df.columns) else 0.0
        _mcol3.metric("Dữ liệu thiếu (trung bình)", f"{_missing_pct:.1f}%")

    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        _hdr_title, _hdr_search, _hdr_export = st.columns([2.2, 2, 1], vertical_alignment="bottom")
        with _hdr_title:
            st.markdown("##### Sinh viên rủi ro cao")
            st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
        if overview and overview.get("status") == "ok" and overview["high_risk_students"]:
            _rows_all = overview["high_risk_students"]
            with _hdr_search:
                _hr_query = st.text_input(
                    " ", placeholder="🔎 Tìm theo mã SV...",
                    label_visibility="collapsed", key="highrisk_table_search",
                )
            _rows = [r for r in _rows_all if not _hr_query or _hr_query.lower() in str(r["id"]).lower()][:20]
            _table_df = pd.DataFrame(
                [
                    {
                        "Mã SV": r["id"],
                        "Điểm hiện tại": round(r["current"], 2) if isinstance(r["current"], (int, float)) else r["current"],
                        "Điểm dự báo": round(r["predicted"], 2),
                        "Mức rủi ro": "🔴 Cao",
                        "Yếu tố chính": r["top_factor"] or "—",
                    }
                    for r in _rows
                ]
            )
            with _hdr_export:
                st.download_button(
                    "📥 Export",
                    data=_table_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="sinh_vien_rui_ro_cao.csv",
                    mime="text/csv",
                    key="export_highrisk_csv",
                    width="stretch",
                )
            if _table_df.empty:
                ui_kit.empty_state(f"Không tìm thấy sinh viên khớp \"{_hr_query}\".")
            else:
                # Chọn 1 dòng = "View Details" thật (không phải cột nút giả) — Streamlit
                # dataframe hỗ trợ chọn dòng qua on_select/selection_mode (>=1.35). Bấm
                # dòng nào sẽ mở panel chi tiết + nút điều hướng thẳng sang Tư vấn AI cho
                # đúng sinh viên đó, tái dùng cơ chế `_pending_nav_target` đã có sẵn.
                _event = st.dataframe(
                    _table_df,
                    width="stretch",
                    hide_index=True,
                    height=min(400, 60 + 35 * len(_table_df)),
                    on_select="rerun",
                    selection_mode="single-row",
                    key="lecturer_high_risk_table",
                )
                st.caption(f"Hiển thị {len(_rows)} / {len(_rows_all)} sinh viên rủi ro cao — chọn 1 dòng để xem chi tiết.")

                _selected_rows = list(_event.selection.get("rows", [])) if _event and getattr(_event, "selection", None) else []
                if _selected_rows:
                    _sel = _table_df.iloc[_selected_rows[0]]
                    with st.container(border=True):
                        st.markdown(f"**Chi tiết sinh viên `{_sel['Mã SV']}`**")
                        dcol1, dcol2, dcol3 = st.columns(3)
                        dcol1.metric("Điểm hiện tại", _sel["Điểm hiện tại"])
                        dcol2.metric("Điểm dự báo", _sel["Điểm dự báo"])
                        dcol3.metric("Mức rủi ro", "Cao")
                        st.caption(f"Yếu tố chính cần cải thiện: **{_sel['Yếu tố chính']}**")
                        if st.button("🤖 Xem tư vấn AI cho sinh viên này", key="goto_ai_from_highrisk"):
                            st.session_state["llm_student_select"] = _sel["Mã SV"]
                            _target_tabs = [t for t in filter_tabs_for_role(ALL_TABS, "Giảng viên / CVHT") if t != HOME_TAB_LABEL]
                            _ai_tab = next((t for t in _target_tabs if "Tư vấn" in t), None)
                            if _ai_tab:
                                st.session_state["_pending_nav_target"] = _ai_tab
                                st.rerun()
        elif overview and overview.get("status") == "ok":
            ui_kit.empty_state("Không có sinh viên nào ở mức rủi ro cao trong lớp này.")
        else:
            ui_kit.empty_state("Chưa có dữ liệu để liệt kê sinh viên rủi ro cao.")

    st.markdown("---")

    # ========================================================================
    # PHÂN TÍCH CHI TIẾT (thứ cấp, dưới phần Tổng quan ở trên) — giữ nguyên
    # tính năng thống kê/biểu đồ điểm số & xếp loại đã có, chỉ đổi vị trí để
    # phần Tổng quan (KPI/rủi ro/cụm) theo mockup luôn là nội dung chính hiện
    # ra đầu tiên.
    # ========================================================================
    ui_kit.subsection_header("Phân tích chi tiết điểm số & xếp loại", icon="🔍")
    tab_scores, tab_grades, tab_more = st.tabs([
        "📊 Phân tích Điểm số",
        "🏆 Phân tích Xếp loại",
        "📈 Thêm thông tin"
    ])

    # ========================================================================
    # TAB 1: PHÂN TÍCH ĐIỂM SỐ
    # ========================================================================
    with tab_scores:
        st.markdown("### Phân tích Điểm số")
        st.markdown("**Mục đích:** Hiểu phân bố điểm số của lớp (phân phối, trung vị, outlier)")
        
        if gpa_col_name and pd.api.types.is_numeric_dtype(df[gpa_col_name]):
            # Hiển thị bảng thống kê chi tiết trước (ngắn, dễ hiểu)
            st.markdown("#### Thống kê Chi tiết")
            desc_stats = df[gpa_col_name].describe()
            desc_df = pd.DataFrame({
                'Chỉ số': ['Số lượng', 'Trung bình', 'Độ lệch chuẩn', 'Min', 'Q1 (25%)', 'Trung vị (50%)', 'Q3 (75%)', 'Max'],
                'Giá trị': [
                    f"{int(desc_stats['count'])}",
                    f"{desc_stats['mean']:.2f}",
                    f"{desc_stats['std']:.2f}",
                    f"{desc_stats['min']:.2f}",
                    f"{desc_stats['25%']:.2f}",
                    f"{desc_stats['50%']:.2f}",
                    f"{desc_stats['75%']:.2f}",
                    f"{desc_stats['max']:.2f}"
                ]
            })
            st.dataframe(desc_df, width="stretch", hide_index=True)
            st.caption("📌 **Giải thích:** Trung bình = tổng điểm / số SV; Độ lệch chuẩn = độ phân tán; Q1/Q3 = tứ phân vị")

            # Chỉ hiển thị 2 biểu đồ (không quá nhiều)
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Phân bố Điểm số (Histogram)")
                st.markdown("*Xem hình dạng phân phối, có bao nhiêu SV đạt từng khoảng điểm*")
                fig_score = px.histogram(
                    df,
                    x=gpa_col_name,
                    nbins=25,
                    title=f"Phân bố {feature_label(gpa_col_name)}",
                    labels={gpa_col_name: 'Điểm số', 'count': 'Số sinh viên'},
                    color_discrete_sequence=['#2563EB']
                )
                # Thêm đường trung bình
                fig_score.add_vline(
                    x=avg_gpa,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"TB: {avg_gpa:.2f}",
                    annotation_position="top right"
                )
                fig_score.update_layout(
                    template='plotly_white',
                    height=380,
                    bargap=0.1,
                    showlegend=False
                )
                st.plotly_chart(fig_score, width="stretch", key="dash_score_hist")

            with col2:
                st.markdown("#### Biểu đồ hộp (Phân tích giá trị ngoại lai)")
                st.markdown("*Xem các giá trị ngoại lai (outlier) và phân vị*")
                fig_box = px.box(
                    df,
                    y=gpa_col_name,
                    title=f"Biểu đồ hộp — {feature_label(gpa_col_name)}",
                    labels={gpa_col_name: 'Điểm số'},
                    color_discrete_sequence=['#10B981']
                )
                fig_box.update_layout(
                    template='plotly_white',
                    height=380,
                    showlegend=False
                )
                st.plotly_chart(fig_box, width="stretch", key="dash_score_box")

        else:
            ui_kit.empty_state(
                "Không tìm thấy cột điểm số.",
                hint="Kiểm tra dữ liệu có các cột: diem_ky_sau, diem_ky_nay, final_score, gpa, score.",
            )

    # ========================================================================
    # TAB 2: PHÂN TÍCH XẾP LOẠI
    # ========================================================================
    with tab_grades:
        st.markdown("### Phân tích Xếp loại")
        st.markdown("**Mục đích:** Hiểu cơ cấu xếp loại (có bao nhiêu A, B, C, D, F)")
        
        if grade_col_name and grade_col_name in df.columns:
            # Tính toán tần suất xếp loại
            try:
                unique_grades = df[grade_col_name].unique()
                if all(str(g).upper() in ['A', 'B', 'C', 'D', 'F'] for g in unique_grades):
                    grade_order = ['A', 'B', 'C', 'D', 'F']
                    grade_counts = df[grade_col_name].value_counts().reindex(grade_order).fillna(0)
                else:
                    grade_counts = df[grade_col_name].value_counts().sort_index()
            except:
                grade_counts = df[grade_col_name].value_counts().sort_index()

            # Bảng thống kê
            st.markdown("#### Thống kê Chi tiết Xếp loại")
            grade_stats_df = pd.DataFrame({
                'Xếp loại': grade_counts.index.astype(str),
                'Số SV': grade_counts.values.astype(int),
                'Tỷ lệ (%)': (grade_counts.values / len(df) * 100).round(1),
                'Tích lũy (%)': (grade_counts.values.cumsum() / len(df) * 100).round(1)
            })
            st.dataframe(grade_stats_df, width="stretch", hide_index=True)
            st.caption("📌 **Giải thích:** Tỷ lệ = (Số SV loại này / Tổng SV) × 100; Tích lũy = tổng tỷ lệ từ đầu đến dòng này")

            st.markdown("---")
            
            # Hiển thị 2 biểu đồ (Bar + Pie, không quá nhiều)
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Số lượng theo Xếp loại (Bar Chart)")
                st.markdown("*So sánh số SV ở mỗi xếp loại*")
                fig_grade = px.bar(
                    x=grade_counts.index.astype(str),
                    y=grade_counts.values,
                    title=f"Phân bố xếp loại",
                    labels={'x': 'Xếp loại', 'y': 'Số SV'},
                    color=grade_counts.index.astype(str),
                    text_auto=True,
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig_grade.update_layout(
                    xaxis_type='category',
                    template='plotly_white',
                    height=380,
                    showlegend=False
                )
                st.plotly_chart(fig_grade, width="stretch", key="dash_grade_bar")

            with col2:
                st.markdown("#### Tỷ lệ Xếp loại (Pie Chart)")
                st.markdown("*Nhìn nhanh tỷ lệ phần trăm mỗi xếp loại*")
                fig_pie = px.pie(
                    values=grade_counts.values,
                    names=grade_counts.index.astype(str),
                    title=f"Tỷ lệ xếp loại (%)",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    hole=0.3  # Doughnut chart, dễ nhìn hơn
                )
                fig_pie.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    hovertemplate='<b>%{label}</b><br>Số SV: %{value}<br>Tỷ lệ: %{percent}<extra></extra>'
                )
                fig_pie.update_layout(
                    template='plotly_white',
                    height=380
                )
                st.plotly_chart(fig_pie, width="stretch", key="dash_grade_pie")

        else:
            ui_kit.empty_state("Không tìm thấy cột xếp loại (ví dụ: 'grade').", hint="Bỏ qua tab này.")

    # ========================================================================
    # TAB 3: THÊM THÔNG TIN & GỢI Ý
    # ========================================================================
    with tab_more:
        st.markdown("### Thêm Thông tin & Gợi ý Tiếp theo")
        
        # Phần A: Feature khác (tùy chọn)
        st.markdown("#### Phân tích Features Khác")
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        other_numeric_cols = [col for col in numeric_cols
                              if col != gpa_col_name
                              and 'id' not in col.lower()
                              and 'pca' not in col.lower()
                              and 'cluster' not in col.lower()][:5]

        if other_numeric_cols:
            st.markdown("*Chọn một feature để xem phân bố của nó:*")
            col_select, col_spacer = st.columns([2, 1])
            with col_select:
                selected_feature = st.selectbox(
                    "Feature để phân tích:",
                    other_numeric_cols,
                    key="dash_feature_select",
                    label_visibility="collapsed"
                )
            
            fig_feature = px.histogram(
                df,
                x=selected_feature,
                nbins=20,
                title=f"Phân bố '{selected_feature}'",
                labels={selected_feature: selected_feature, 'count': 'Số SV'},
                color_discrete_sequence=['var(--primary-color)']
            )
            fig_feature.update_layout(template='plotly_white', height=340)
            st.plotly_chart(fig_feature, width="stretch", key="dash_other_feature")
        else:
            st.info("Không có feature số nào khác để phân tích.")

        st.markdown("---")
        
        # Phần B: Gợi ý tiếp theo
        st.markdown("#### Các bước tiếp theo đề xuất")
        st.markdown("""
        **Để tiếp tục phân tích và dự đoán:**

        1. Khám phá dữ liệu (tab tương ứng): missing, outlier, correlation.
        2. Huấn luyện mô hình: chọn target, features, so sánh metrics.
        3. Phân cụm: nhóm sinh viên theo similarity.
        4. AI tư vấn: cần API key nếu dùng LLM.
        """)
        
        st.markdown("---")
        
        # ========================================================================
        # PHẦN QUY TRÌNH CHI TIẾT CỦA HỆ THỐNG (ĐỂ BÁO CÁO)
        # ========================================================================
        st.markdown("### Quy trình chi tiết của hệ thống DSS")
        st.markdown("**Quy trình đầy đủ từ tải dữ liệu đến dự đoán kết quả:**")
        
        with st.expander("Xem quy trình chi tiết & cách thức hoạt động", expanded=False):
            st.markdown("""
            Quy trình DSS: tải dữ liệu -> xử lý -> EDA -> chọn target/features -> huấn luyện -> đánh giá -> dự đoán.
            Luu trong thu muc data_warehouse (datasets, models, metadata).
            """)
        
        st.info("✨ **Mẹo:** Click vào các tab khác để truy cập từng chức năng!")
