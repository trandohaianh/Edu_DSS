"""Shared runtime imports for Streamlit tab modules."""

import plotly.graph_objects as go

from dss.config import *  # noqa: F403
from dss.core.data_helpers import feature_label
from dss.core.feature_utils import render_save_export_buttons, to_excel
from dss.core.logging_config import get_logger
from dss.core.target_utils import is_id_like

_logger = get_logger(__name__)

# Phase 2 refactor (hoàn tất): toàn bộ tính toán thuần (tiền xử lý, Elbow/
# Silhouette, K-Means, PCA, thống kê điểm mạnh/yếu, gợi ý cosine similarity...)
# đã chuyển sang services/clustering_service.py — file này giờ chỉ còn UI.
from dss.services import clustering_service
from dss.tabs import ui_kit


def clustering_hybrid_tab(df, wh=None, role="Giảng viên / CVHT", current_student_id=None):
    """Tab phân cụm và gợi ý hybrid — bố cục dashboard 3 vùng (cấu hình / đánh
    giá / diễn giải) thay vì các bước xếp chồng dọc như trước."""
    ui_kit.render_synthetic_data_banner(df)  # E-1: cảnh báo rõ khi đang xem dữ liệu mô phỏng
    # Student Role Audit (2026-09): "Phân cụm" (clustering) là thuật ngữ kỹ
    # thuật — Sinh viên chỉ cần biết mình thuộc nhóm học tập nào và nên làm gì,
    # không cần thấy tên thuật toán. Giảng viên/Admin vẫn thấy tiêu đề kỹ thuật
    # đầy đủ vì họ thực sự cấu hình/chạy K-Means.
    if role == "Sinh viên":
        ui_kit.section_header(
            "Nhóm học tập của bạn",
            subtitle="Xem bạn thuộc nhóm nào trong lớp và gợi ý cải thiện phù hợp. Nhóm được gom tự động theo "
            "mức độ tương đồng của kết quả học tập — không phải xếp loại hay đánh giá chính thức.",
            icon="🔬",
        )
    else:
        ui_kit.section_header(
            "Phân cụm & Gợi ý",
            subtitle="Phân cụm sinh viên (K-Means) và gợi ý học tập. Cụm là phân khúc theo độ tương đồng dữ liệu — "
            "công cụ khám phá, không phải phân loại sinh viên chính thức.",
            icon="🔬",
        )
    if role != "Sinh viên":
        with st.expander("Hướng dẫn chi tiết từng bước (bấm để xem)", expanded=False):
            st.markdown(
                """
                **Bước 1 - Chọn đặc trưng để phân cụm**
                - Chỉ chọn cột **dạng số** liên quan đến năng lực/hành vi học tập (điểm, GPA, giờ học, số bài làm...).
                - Không chọn cột định danh như `id`, `student_id`, tên sinh viên.
                - Nên chọn khoảng **3 đến 8 cột** để cụm dễ ổn định và dễ diễn giải.

                **Bước 2 - Elbow + Silhouette và chốt K đề xuất**
                - Chọn khoảng K, bấm **Vẽ Elbow + Silhouette & chốt K đề xuất**.
                - Hệ thống vẽ **Elbow** (Inertia) và **Silhouette**; **K đề xuất** = K có Silhouette cao nhất (dễ chọn hơn chỉ nhìn Elbow).
                - Bấm **Áp dụng K đề xuất** để điền sẵn K ở bước 3, hoặc tự chỉnh K nếu muốn diễn giải nghiệp vụ khác.

                **Bước 3 - Chạy K-Means và kiểm tra chất lượng**
                - Kiểm tra ô K (đã áp dụng đề xuất nếu bạn bấm nút), rồi bấm **Chạy Phân cụm K-Means**.
                - Nếu có nhiều K gần nhau, ưu tiên K vừa có chỉ số ổn vừa dễ giải thích theo bối cảnh lớp học.
                - Khi kết quả chưa rõ, thử lại với bộ đặc trưng khác (bỏ cột nhiễu, thêm cột phản ánh học tập tốt hơn).

                **Bước 4 - Đọc dashboard và rút gợi ý**
                - Xem **biểu đồ Radar** so sánh các cụm (cần ít nhất 2 đặc trưng), phân bố cụm, chân dung cụm (điểm mạnh/yếu), rồi đọc bảng can thiệp theo mức ưu tiên.
                - Ở phần gợi ý cá nhân, hệ thống tìm bạn học tương tự theo **độ tương đồng cosine**.
                - Ở phần gợi ý cụm tham chiếu, hệ thống đề xuất cụm mạnh hơn để học hỏi.

                **Mẹo khi báo cáo**
                - Trình bày theo thứ tự: **chọn đặc trưng -> chọn K -> kiểm tra chất lượng -> diễn giải cụm -> đề xuất hành động**.
                """
            )

    if len(df) > 2000:
        st.caption("Silhouette được ước lượng trên mẫu tối đa 2.000 bản ghi để giảm thời gian tính.")
    has_results = 'cluster_results_df' in st.session_state

    # ============================================================================
    # HÀNG KPI TRÊN CÙNG — trạng thái cấu hình/phân cụm hiện tại, nhìn 1 lần là biết.
    # ============================================================================
    n_selected_feats = len(st.session_state.get('cluster_selected_cols', []) or [])
    current_k = st.session_state.get('cluster_k_optimal')
    n_clusters_now = int(st.session_state['cluster_results_df']['cluster'].nunique()) if has_results else None
    _quality_sil = st.session_state.get("cluster_quality_silhouette")
    _quality_db = st.session_state.get("cluster_quality_db")
    # Sinh viên KHÔNG được xem thẻ "Dataset: X SV" — đó là quy mô TOÀN LỚP, không
    # phải dữ liệu của riêng họ (dễ gây hiểu nhầm "đây là dữ liệu của tôi").
    # Thay bằng thông tin liên quan tới CHÍNH sinh viên: nhóm học tập họ thuộc về.
    if role == "Sinh viên":
        _own_cluster_label = "—"
        _own_goal = "Cải thiện kỹ năng & Ôn tập"
        if has_results and current_student_id:
            _cdf = st.session_state["cluster_results_df"]
            _id_col_kpi = next((c for c in ("student_id", "id", "Student ID", "ID") if c in _cdf.columns), None)
            if _id_col_kpi is not None:
                _own_rows = _cdf[_cdf[_id_col_kpi].astype(str) == str(current_student_id)]
                if not _own_rows.empty:
                    _cl_num = int(_own_rows.iloc[0]['cluster'])
                    _own_cluster_label = f"Cụm {_cl_num}"
                    _own_goal = f"Nâng cao GPA & Đồ án Cụm {_cl_num}"
        first_card = (
            "Nhóm học tập của bạn",
            _own_cluster_label,
            "Nhóm học tập được phân bổ theo hồ sơ học tập",
            "purple",
        )
        ui_kit.kpi_row(
            [
                first_card,
                (
                    "Trạng thái",
                    "Đã phân nhóm" if _own_cluster_label != "—" else "Chưa phân nhóm",
                    "Trạng thái phân cụm K-Means",
                    "success" if _own_cluster_label != "—" else "warning",
                ),
                (
                    "Mục tiêu học tập",
                    _own_goal,
                    "Mục tiêu trọng tâm cho học kỳ",
                    "purple" if _own_cluster_label != "—" else "warning",
                ),
            ]
        )
    else:
        first_card = ("Dataset", f"{len(df):,} SV", "Tổng số sinh viên trong tập dữ liệu phân tích", "purple")
        ui_kit.kpi_row(
            [
                first_card,
                (
                    "Đặc trưng đã chọn",
                    n_selected_feats if n_selected_feats else "—",
                    "Số lượng biến số tham gia phân cụm",
                    None,
                ),
                (
                    "Số cụm (k)",
                    n_clusters_now if n_clusters_now is not None else (current_k or "—"),
                    "Số nhóm phân tách tối ưu",
                    None,
                ),
                (
                    "Silhouette",
                    f"{_quality_sil:.3f}" if _quality_sil is not None else "—",
                    "Mức độ tách biệt giữa các cụm. Càng gần 1 càng tốt (tách biệt rõ).",
                    "success",
                ),
                (
                    "Davies-Bouldin",
                    f"{_quality_db:.3f}" if _quality_db is not None else "—",
                    "Mức độ chồng lấn giữa các cụm. Càng thấp càng tốt (ít trùng lặp).",
                    None,
                ),
            ]
        )
    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

    selected_cols_cluster = []
    X_processed = None

    if role != "Sinh viên":
        # ========================================================================
        # 3 VÙNG CHÍNH: CẤU HÌNH (trái) — ĐÁNH GIÁ MÔ HÌNH (giữa) — DIỄN GIẢI (phải)
        # ========================================================================
        col_left, col_center, col_right = st.columns([1, 1.3, 1], gap="medium")

        with col_left:
            with st.container(border=True):
                st.markdown("##### Cấu hình phân cụm")

                all_numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                all_numeric_cols = [
                    col
                    for col in all_numeric_cols
                    if 'id' not in col.lower() and 'pca' not in col.lower() and 'cluster' not in col.lower()
                ]
                # C-1: dùng hàm chọn cột mặc định DÙNG CHUNG (loại bí danh/target,
                # nhận diện cả tên cột tiếng Việt, loại cột gần trùng lặp) — xem
                # clustering_service.select_default_cluster_features. Danh sách
                # TÙY CHỌN (all_numeric_cols) vẫn giữ nguyên mọi cột số để người
                # dùng tự chọn thủ công nếu muốn, chỉ phần MẶC ĐỊNH được lọc.
                default_cluster_features = clustering_service.select_default_cluster_features(df)

                selected_cols_cluster = st.multiselect(
                    "Đặc trưng dùng để phân cụm:",
                    all_numeric_cols,
                    default=default_cluster_features,
                    help="Chỉ chọn cột dạng số phản ánh năng lực/hành vi học tập.",
                    key="cluster_features",
                )

                if not selected_cols_cluster:
                    st.warning("⚠️ Chọn ít nhất một đặc trưng để tiếp tục.")
                else:
                    st.caption(f"✅ Đã chọn {len(selected_cols_cluster)} đặc trưng.")
                    with st.spinner("Đang chuẩn hóa dữ liệu..."):
                        cluster_preprocessor, X_processed = clustering_service.preprocess_features(
                            df, selected_cols_cluster
                        )
                        st.session_state.cluster_preprocessor = cluster_preprocessor
                        st.session_state.cluster_selected_cols = selected_cols_cluster
                        st.session_state.cluster_X_processed = X_processed

                    st.markdown("---")
                    st.markdown("**Tìm K tối ưu (Elbow + Silhouette)**")
                    k_range_start = st.number_input("K bắt đầu:", min_value=2, max_value=5, value=2, key="k_start")
                    k_range_end = st.number_input("K kết thúc:", min_value=6, max_value=15, value=10, key="k_end")

                    if k_range_start >= k_range_end:
                        st.error("⚠️ K bắt đầu phải nhỏ hơn K kết thúc.")
                    elif st.button("📊 Vẽ Elbow + Silhouette", type="secondary", key="draw_elbow", width="stretch"):
                        with st.spinner(f"Đang tính từ K={k_range_start} đến K={k_range_end}..."):
                            progress_bar = st.progress(0)
                            result = clustering_service.compute_elbow_silhouette(
                                X_processed,
                                k_range_start,
                                k_range_end,
                                progress_callback=lambda frac: progress_bar.progress(frac),
                            )
                            progress_bar.empty()

                            st.session_state.elbow_calculated = True
                            st.session_state.elbow_k_range = result["k_list"]
                            st.session_state.elbow_inertia = result["inertia"]
                            st.session_state.elbow_silhouette = result["silhouette"]
                            st.session_state.cluster_k_elbow_suggest = result["suggested_k_elbow"]
                            st.session_state.cluster_k_sil_best = result["suggested_k_sil"]
                            st.session_state.cluster_k_recommended = result["recommended_k"]
                            st.session_state.cluster_k_recommended_reason = result["reason"]
                            st.session_state.cluster_structure_warning = result.get("warning")
                            st.rerun()

                    rec_k_now = st.session_state.get("cluster_k_recommended")
                    if rec_k_now is not None:
                        st.success(f"K đề xuất: **{rec_k_now}**")
                        if st.session_state.get("cluster_structure_warning"):
                            st.warning(st.session_state.cluster_structure_warning)
                        st.caption(st.session_state.get("cluster_k_recommended_reason", ""))
                        if st.button(f"✅ Áp dụng K = {rec_k_now}", key="apply_recommended_k", width="stretch"):
                            st.session_state.k_cluster = int(rec_k_now)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("**Chạy phân cụm**")
                    k_optimal = st.number_input(
                        "Số cụm (K):",
                        min_value=2,
                        max_value=15,
                        value=4,
                        help="Số cụm bạn muốn chia dữ liệu thành.",
                        key="k_cluster",
                    )
                    if st.button("🚀 Chạy Phân cụm K-Means", type="primary", key="run_cluster", width="stretch"):
                        with st.spinner(f"Đang chạy K-Means với K={k_optimal}..."):
                            kmeans, clusters = clustering_service.run_kmeans(X_processed, k_optimal)
                            _quality = clustering_service.compute_cluster_quality_metrics(X_processed, clusters)
                            st.session_state.cluster_results_df = df.copy()
                            st.session_state.cluster_results_df['cluster'] = clusters
                            st.session_state.cluster_kmeans_model = kmeans
                            st.session_state.cluster_k_optimal = k_optimal
                            st.session_state.cluster_quality_silhouette = _quality["silhouette"]
                            st.session_state.cluster_quality_db = _quality["davies_bouldin"]
                            st.session_state.cluster_train_run_id = f"{datetime.now().timestamp()}_{k_optimal}"
                        st.success(f"✅ Đã phân {len(df)} sinh viên vào {k_optimal} cụm.")
                        st.rerun()

        with col_center:
            with st.container(border=True):
                st.markdown("##### Đánh giá mô hình")
                if st.session_state.get('elbow_calculated', False):
                    if st.session_state.get("elbow_silhouette") is None:
                        st.caption("ℹ️ Phiên trước chỉ có Elbow. Bấm lại **Vẽ Elbow + Silhouette** để có đủ dữ liệu.")
                    fig_elbow = px.line(
                        x=st.session_state.elbow_k_range,
                        y=st.session_state.elbow_inertia,
                        title="Elbow — Inertia theo K",
                        labels={'x': 'Số cụm (K)', 'y': 'Inertia'},
                        markers=True,
                    )
                    fig_elbow.update_traces(
                        mode='lines+markers', line=dict(width=3, color='#1976d2'), marker=dict(size=9, color='#1976d2')
                    )
                    fig_elbow.update_layout(
                        height=300, hovermode='x unified', template='plotly_white', margin=dict(t=40, b=10)
                    )
                    st.plotly_chart(fig_elbow, width="stretch", key="elbow_chart_cached")

                    sil_list = st.session_state.get("elbow_silhouette")
                    if sil_list is not None and len(sil_list) == len(st.session_state.elbow_k_range):
                        fig_sil = px.line(
                            x=st.session_state.elbow_k_range,
                            y=sil_list,
                            title="Silhouette theo K (càng cao càng tách cụm rõ)",
                            labels={"x": "Số cụm (K)", "y": "Silhouette score"},
                            markers=True,
                        )
                        fig_sil.update_traces(
                            mode="lines+markers",
                            line=dict(width=3, color="#0d9488"),
                            marker=dict(size=9, color="#0d9488"),
                        )
                        fig_sil.update_layout(
                            height=280, hovermode="x unified", template="plotly_white", margin=dict(t=40, b=10)
                        )
                        st.plotly_chart(fig_sil, width="stretch", key="silhouette_chart_cached")

                        compare_df = pd.DataFrame(
                            {
                                "K": st.session_state.elbow_k_range,
                                "Inertia": np.round(st.session_state.elbow_inertia, 2),
                                "Silhouette": np.round(sil_list, 3),
                            }
                        )
                        with st.expander("Bảng so sánh K", expanded=False):
                            st.dataframe(compare_df, width="stretch", hide_index=True)
                            ke = st.session_state.get("cluster_k_elbow_suggest")
                            ks = st.session_state.get("cluster_k_sil_best")
                            st.caption(
                                f"Elbow (tham khảo): **{ke if ke is not None else '—'}** · Silhouette tốt nhất: **{ks if ks is not None else '—'}**"
                            )
                else:
                    ui_kit.empty_state(
                        "Chưa có kết quả Elbow/Silhouette.",
                        hint="Bấm \"Vẽ Elbow + Silhouette\" ở panel Cấu hình bên trái.",
                    )

                if has_results:
                    st.markdown("---")
                    df_results_kpi = st.session_state.cluster_results_df
                    k_now = st.session_state.get('cluster_k_optimal', df_results_kpi['cluster'].nunique())
                    cluster_counts_dist = df_results_kpi['cluster'].value_counts().sort_index()
                    fig_dist = px.bar(
                        x=cluster_counts_dist.index.astype(str),
                        y=cluster_counts_dist.values,
                        labels={'x': 'Cụm', 'y': 'Số SV'},
                        title=f"Phân bố sinh viên theo cụm (K={k_now})",
                        color=cluster_counts_dist.index.astype(str),
                        color_discrete_sequence=px.colors.qualitative.Set3,
                    )
                    fig_dist.update_layout(
                        showlegend=False, template='plotly_white', height=280, margin=dict(t=40, b=10)
                    )
                    st.plotly_chart(fig_dist, width="stretch", key="cluster_distribution_chart")

        with col_right:
            with st.container(border=True):
                st.markdown("##### Diễn giải cụm")
                if not has_results:
                    ui_kit.empty_state(
                        "Chưa có kết quả phân cụm.",
                        hint="Chạy phân cụm ở panel Cấu hình bên trái để xem diễn giải tại đây.",
                    )
                else:
                    df_results_r = st.session_state.cluster_results_df
                    selected_cols_r = st.session_state.cluster_selected_cols
                    overall_avg_r = df[selected_cols_r].mean()
                    overall_std_r = df[selected_cols_r].std()
                    cluster_mean_df_r = clustering_service.compute_cluster_means(df_results_r, selected_cols_r)
                    for cid in sorted(cluster_mean_df_r.index):
                        cdata = cluster_mean_df_r.loc[cid]
                        cavg = cdata[selected_cols_r]
                        strengths_r, weaknesses_r = clustering_service.compute_strengths_weaknesses(
                            cavg, overall_avg_r, overall_std=overall_std_r
                        )
                        st.markdown(f"**Cụm {cid}** · {int(cdata['Số lượng SV'])} SV")
                        if strengths_r:
                            st.caption(f"✅ Mạnh: {', '.join(feature_label(c) for c in strengths_r[:2])}")
                        if weaknesses_r:
                            st.caption(f"⚠️ Yếu: {', '.join(feature_label(c) for c in weaknesses_r[:2])}")
                        if not strengths_r and not weaknesses_r:
                            st.caption("Không có điểm nổi bật rõ ràng.")
                        st.markdown("")
                    if wh:
                        st.markdown("---")
                        st.markdown("**💾 Lưu vào Kho dữ liệu**")
                        render_save_export_buttons(
                            df_results_r, "clustered_data", wh, "cluster_tab", data_type="clustered"
                        )
                        cluster_run_id = st.session_state.get("cluster_train_run_id")
                        if "cluster_kmeans_model" in st.session_state:
                            if st.session_state.get("_cluster_model_autosaved_run_id") != cluster_run_id:
                                try:
                                    dataset_id_ref = st.session_state.get("current_dataset_id", "unknown_cluster_data")
                                    training_id, _ = wh.save_model_training(
                                        dataset_id_ref,
                                        st.session_state.cluster_kmeans_model,
                                        "KMeans_Clustering_Model",
                                        st.session_state.cluster_selected_cols,
                                        "cluster",
                                        {"k": st.session_state.cluster_k_optimal, "type": "clustering"},
                                    )
                                    st.session_state._cluster_model_autosaved_run_id = cluster_run_id
                                    st.success(f"✅ Đã lưu model. ID: `{training_id[:16]}...`")
                                except Exception as e:
                                    ui_kit.report_error("❌ Lỗi lưu model", e)
                            else:
                                st.caption("✅ Model của lượt chạy này đã được lưu.")

        if not selected_cols_cluster:
            return

    elif not has_results:
        st.info(
            "ℹ️ Giảng viên chưa chạy phân cụm cho dữ liệu này — hãy quay lại sau khi "
            "Giảng viên đã hoàn tất cấu hình phân cụm."
        )
        return
    else:
        df_results_sv = st.session_state.cluster_results_df
        _sv_id_col = next((c for c in df_results_sv.columns if is_id_like(c)), df_results_sv.columns[0])
        _sv_rows = df_results_sv[df_results_sv[_sv_id_col] == current_student_id]
        with st.container(border=True):
            if not _sv_rows.empty:
                _sv_cluster = _sv_rows.iloc[0]['cluster']
                _sv_cluster_size = int((df_results_sv['cluster'] == _sv_cluster).sum())
                st.markdown(f"##### 📍 Bạn thuộc **Cụm {_sv_cluster}**")
                st.caption(
                    f"Cụm này hiện có {_sv_cluster_size} sinh viên có hồ sơ học tập tương đồng với bạn. "
                    "Xem \"Chân dung cụm\" và gợi ý bên dưới để biết đặc điểm chung của nhóm."
                )
            else:
                st.warning("⚠️ Không tìm thấy cụm của bạn trong kết quả phân cụm hiện tại.")

    # ============================================================================
    # VÙNG DƯỚI: trực quan hóa (PCA), chân dung cụm chi tiết, gợi ý hybrid.
    # Đây là các phân tích SÂU, để full-width thay vì nhồi vào 1 cột hẹp.
    # ============================================================================
    if 'cluster_results_df' in st.session_state:
        df_results = st.session_state.cluster_results_df
        selected_cols = st.session_state.cluster_selected_cols
        X_processed = st.session_state.cluster_X_processed

        st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

        if role != "Sinh viên":
            with st.container(border=True):
                st.markdown("##### Trực quan hóa phân cụm (PCA)")
                st.caption(
                    "PCA giảm chiều dữ liệu để nhìn nhóm sinh viên trực quan. Cần ít nhất 2 cột số để vẽ mặt phẳng 2D."
                )
                n_samples_pca, n_features_pca = X_processed.shape
                with st.spinner("Đang tính toán PCA..."):
                    pca_result = clustering_service.compute_pca(X_processed)
                if pca_result is None:
                    st.error("⚠️ Không đủ dữ liệu để chạy PCA (số mẫu hoặc số đặc trưng = 0).")
                else:
                    n_comp_pca = pca_result["n_components"]
                    X_pca = pca_result["X_pca"]
                    variance_explained = pca_result["variance_explained"]
                    total_variance = pca_result["total_variance"]
                    df_results_pca = df_results.copy()

                    hover_name = None
                    for col in ['student_id', 'id', 'student_name', 'name']:
                        if col in df_results_pca.columns:
                            hover_name = col
                            break

                    if n_comp_pca == 1:
                        df_results_pca["pca1"] = X_pca.ravel()
                        st.warning(
                            "ℹ️ Đang phân cụm với **1 đặc trưng** — sklearn không cho PCA 2 thành phần "
                            f"(cần n_components ≤ min(n_mẫu, n_đặc_trưng) = {min(n_samples_pca, n_features_pca)}). "
                            "Chọn thêm cột số ở panel Cấu hình để có biểu đồ PCA 2D."
                        )
                        fig_pca = px.scatter(
                            df_results_pca,
                            x=np.arange(len(df_results_pca)),
                            y="pca1",
                            color=df_results_pca["cluster"].astype(str),
                            color_discrete_sequence=px.colors.qualitative.Set3,
                            hover_name=hover_name,
                            hover_data=selected_cols[:5],
                            title="Phân bố cụm (PCA 1D — chỉ PC1)",
                            labels={
                                "x": "Thứ tự hàng",
                                "y": f"PC1 ({variance_explained[0] * 100:.1f}% phương sai)",
                                "color": "Cụm",
                            },
                        )
                        fig_pca.update_traces(
                            marker=dict(size=8, opacity=0.7, line=dict(width=1, color="DarkSlateGrey")),
                            selector=dict(mode="markers"),
                        )
                        fig_pca.update_layout(
                            height=480,
                            template="plotly_white",
                            legend=dict(title="Cụm", orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
                        )
                        st.plotly_chart(fig_pca, width="stretch", key="cluster_pca_plot_1d")
                    else:
                        df_results_pca["pca1"] = X_pca[:, 0]
                        df_results_pca["pca2"] = X_pca[:, 1]
                        st.caption(
                            f"📈 PCA giải thích {total_variance:.1f}% phương sai "
                            f"(PC1: {variance_explained[0] * 100:.1f}%, PC2: {variance_explained[1] * 100:.1f}%)."
                        )
                        fig_pca = px.scatter(
                            df_results_pca,
                            x="pca1",
                            y="pca2",
                            color=df_results_pca["cluster"].astype(str),
                            color_discrete_sequence=px.colors.qualitative.Set3,
                            hover_name=hover_name,
                            hover_data=selected_cols[:5],
                            title="Phân bố cụm sinh viên (PCA 2D)",
                            labels={
                                "pca1": f"PC1 ({variance_explained[0] * 100:.1f}%)",
                                "pca2": f"PC2 ({variance_explained[1] * 100:.1f}%)",
                                "cluster": "Cụm",
                            },
                        )
                        fig_pca.update_traces(
                            marker=dict(size=8, opacity=0.7, line=dict(width=1, color="DarkSlateGrey")),
                            selector=dict(mode="markers"),
                        )
                        fig_pca.update_layout(
                            height=480,
                            template="plotly_white",
                            legend=dict(title="Cụm", orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
                        )
                        st.plotly_chart(fig_pca, width="stretch", key="cluster_pca_plot")

        st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

        # --- CHÂN DUNG CỤM (bảng đầy đủ + radar + mô tả từng cụm) ---
        with st.container(border=True):
            st.markdown("##### Chân dung các nhóm học tập")
            st.caption("Giá trị trung bình của các đặc trưng trong từng cụm.")
            cluster_mean_df = clustering_service.compute_cluster_means(df_results, selected_cols)
            # Bảng hiển thị dùng bản sao đổi tên cột sang nhãn tiếng Việt — cluster_mean_df
            # GỐC (chỉ mục theo tên cột thô) vẫn giữ nguyên vì các đoạn bên dưới còn tra cứu
            # theo đúng tên cột gốc (selected_cols).
            cluster_mean_display = cluster_mean_df.rename(columns={c: feature_label(c) for c in selected_cols})
            st.dataframe(cluster_mean_display, width="stretch", height=250)

            if len(selected_cols) >= 3:
                try:
                    means_radar = df_results.groupby("cluster")[selected_cols].mean().sort_index()
                    mins_r = means_radar.min(axis=0)
                    maxs_r = means_radar.max(axis=0)
                    rng_r = (maxs_r - mins_r).replace(0, np.nan).fillna(1.0)
                    norm_radar = ((means_radar - mins_r) / rng_r).clip(0, 1).fillna(0.5)

                    theta_labels = [feature_label(c) for c in selected_cols]
                    palette = px.colors.qualitative.Set3

                    fig_radar = go.Figure()
                    for i, cl_id in enumerate(norm_radar.index):
                        r_vals = norm_radar.loc[cl_id, selected_cols].astype(float).tolist()
                        r_closed = r_vals + [r_vals[0]]
                        theta_closed = theta_labels + [theta_labels[0]]
                        fig_radar.add_trace(
                            go.Scatterpolar(
                                r=r_closed,
                                theta=theta_closed,
                                fill="toself",
                                name=f"Cụm {cl_id}",
                                line_color=palette[i % len(palette)],
                                opacity=0.55,
                            )
                        )
                    fig_radar.update_layout(
                        title="So sánh chân dung cụm (Radar — đã chuẩn hóa theo trục [0, 1])",
                        polar=dict(
                            radialaxis=dict(
                                visible=True, range=[0, 1], tickmode="linear", tick0=0, dtick=0.25, tickformat=".2f"
                            ),
                            angularaxis=dict(direction="clockwise", rotation=90),
                        ),
                        height=480,
                        template="plotly_white",
                        legend=dict(orientation="h", yanchor="bottom", y=-0.15, x=0.5, xanchor="center"),
                        margin=dict(t=60, b=80),
                    )
                    st.plotly_chart(fig_radar, width="stretch", key="cluster_radar_chart")
                except Exception:
                    _logger.exception("Lỗi khi vẽ radar chart phân cụm.")
                    st.warning("⚠️ Không thể hiển thị biểu đồ radar với dữ liệu/đặc trưng hiện tại.")
            elif len(selected_cols) >= 1:
                try:
                    means_bar = df_results.groupby("cluster")[selected_cols].mean().sort_index()
                    overall_means = df[selected_cols].mean()
                    bar_data = []
                    for cl_id in means_bar.index:
                        for c in selected_cols:
                            bar_data.append(
                                {
                                    "Nhóm": f"Cụm {cl_id}",
                                    "Đặc trưng": feature_label(c),
                                    "Điểm trung bình": round(float(means_bar.loc[cl_id, c]), 2),
                                }
                            )
                    for c in selected_cols:
                        bar_data.append(
                            {
                                "Nhóm": "Trung bình toàn khoá",
                                "Đặc trưng": feature_label(c),
                                "Điểm trung bình": round(float(overall_means[c]), 2),
                            }
                        )
                    bar_df = pd.DataFrame(bar_data)
                    fig_bar = px.bar(
                        bar_df,
                        x="Đặc trưng",
                        y="Điểm trung bình",
                        color="Nhóm",
                        barmode="group",
                        text="Điểm trung bình",
                        title="So sánh giá trị trung bình giữa các nhóm và toàn khoá",
                        color_discrete_sequence=px.colors.qualitative.Safe,
                        height=420,
                    )
                    fig_bar.update_traces(textposition="outside")
                    fig_bar.update_layout(
                        template="plotly_white",
                        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
                        margin=dict(t=50, b=60),
                        yaxis=dict(title="Điểm trung bình", range=[0, max(bar_df["Điểm trung bình"]) * 1.25]),
                    )
                    st.plotly_chart(fig_bar, width="stretch", key="cluster_bar_chart")
                except Exception:
                    _logger.exception("Lỗi khi vẽ grouped bar chart phân cụm.")
                    st.warning("⚠️ Không thể hiển thị biểu đồ cột đối sánh với dữ liệu hiện tại.")
            else:
                st.info("ℹ️ Cần chọn ít nhất 1 đặc trưng để trực quan hóa.")

            st.markdown(
                """
                <div style="background:var(--bg-secondary);border:1px solid var(--border);border-left:4px solid var(--primary);padding:12px 16px;border-radius:8px;margin-top:10px;margin-bottom:14px;">
                    <div style="font-weight:700;color:var(--text-primary);font-size:var(--fs-body);margin-bottom:4px;display:flex;align-items:center;gap:6px;">
                        <span>📖</span> <span>Chú thích đồ thị & Hướng dẫn phân tích</span>
                    </div>
                    <ul style="margin:0;padding-left:18px;font-size:var(--fs-support);color:var(--text-primary);line-height:1.55;">
                        <li><b>Ý nghĩa thang đo:</b> Các giá trị hiển thị mức độ thành tích trung bình của từng nhóm sinh viên đối với các môn/chỉ số học tập trọng yếu.</li>
                        <li><b>Mục tiêu đối sánh:</b> Nhóm có chỉ số cao hơn mức trung bình toàn khoá đại diện cho thế mạnh vượt trội; các chỉ số thấp hơn trung bình là trọng tâm cần lập kế hoạch can thiệp bồi dưỡng.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

            overall_avg = df[selected_cols].mean()
            overall_std = df[selected_cols].std()
            for cluster_id in sorted(cluster_mean_df.index):
                cluster_data = cluster_mean_df.loc[cluster_id]
                cluster_avg_features = cluster_data[selected_cols]
                strengths, weaknesses = clustering_service.compute_strengths_weaknesses(
                    cluster_avg_features, overall_avg, overall_std=overall_std
                )
                with st.expander(f"📌 Cụm {cluster_id} ({int(cluster_data['Số lượng SV'])} sinh viên)"):
                    col_desc1, col_desc2 = st.columns(2)
                    with col_desc1:
                        if strengths:
                            st.success(f"**Điểm mạnh:** {', '.join(strengths[:3])}")
                        else:
                            st.info("**Điểm mạnh:** Không có điểm nổi bật")
                    with col_desc2:
                        if weaknesses:
                            st.warning(f"**Điểm yếu:** {', '.join(weaknesses[:3])}")
                        else:
                            st.info("**Điểm yếu:** Không có điểm yếu rõ ràng")
                    st.markdown("**Giá trị trung bình các features:**")
                    for feature in selected_cols[:5]:
                        cluster_val = cluster_avg_features[feature]
                        overall_val = overall_avg[feature]
                        diff_pct = ((cluster_val - overall_val) / overall_val * 100) if overall_val != 0 else 0
                        if diff_pct > 5:
                            st.markdown(f"- **{feature}:** {cluster_val:.2f} (↑ {diff_pct:.1f}% so với TB)")
                        elif diff_pct < -5:
                            st.markdown(f"- **{feature}:** {cluster_val:.2f} (↓ {abs(diff_pct):.1f}% so với TB)")
                        else:
                            st.markdown(f"- **{feature}:** {cluster_val:.2f} (≈ TB)")

        st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

        # --- GỢI Ý HYBRID (theo cụm + cá nhân) ---
        with st.container(border=True):
            st.markdown("##### Gợi ý học tập dành cho bạn")
            try:
                available_clusters = sorted(df_results['cluster'].unique().tolist())
                if not available_clusters:
                    st.warning("⚠️ Không có cụm nào để phân tích. Vui lòng chạy phân cụm trước.")
                else:
                    if role == "Sinh viên":
                        _sv_id_col_rec = next((c for c in df_results.columns if is_id_like(c)), df_results.columns[0])
                        _sv_rows_rec = df_results[df_results[_sv_id_col_rec] == current_student_id]
                        cluster_to_analyze = _sv_rows_rec.iloc[0]['cluster'] if not _sv_rows_rec.empty else None
                        if cluster_to_analyze is not None:
                            st.info(f"👤 Đang xem gợi ý cho Cụm của bạn: **Cụm {cluster_to_analyze}**")
                    else:
                        _cl_idx = st.session_state.get('cluster_select_index', 0)
                        _cl_idx = max(0, min(_cl_idx, len(available_clusters) - 1))
                        cluster_to_analyze = st.selectbox(
                            "Chọn Cụm (Cluster) để phân tích:",
                            available_clusters,
                            index=_cl_idx,
                            help="Chọn cụm bạn muốn xem phân tích chi tiết.",
                            key="rec_cluster_select_key",
                        )
                        if cluster_to_analyze in available_clusters:
                            st.session_state.cluster_select_index = available_clusters.index(cluster_to_analyze)

                    if cluster_to_analyze is not None:
                        df_cluster_only = df_results[df_results['cluster'] == cluster_to_analyze].copy()

                        if df_cluster_only.empty:
                            st.warning(f"⚠️ Cụm {cluster_to_analyze} không có dữ liệu.")
                        else:
                            cluster_avg = df_cluster_only[selected_cols].mean()
                            overall_avg = df[selected_cols].mean()
                            overall_std = df[selected_cols].std()

                            st.markdown(f"###### 📊 Phân tích Cụm {cluster_to_analyze}")
                            diff_pct_series = clustering_service.compute_diff_pct(cluster_avg, overall_avg)
                            comparison_df = pd.DataFrame(
                                {
                                    'Cụm (TB)': cluster_avg,
                                    'Toàn lớp (TB)': overall_avg,
                                    'Chênh lệch': (cluster_avg - overall_avg).round(2),
                                    'Chênh lệch (%)': diff_pct_series,
                                }
                            )
                            # Đổi tên chỉ mục (tên cột dữ liệu thô) sang nhãn tiếng Việt thân
                            # thiện trước khi hiển thị — không để lộ snake_case (vd. gpa_previous).
                            comparison_df.index = [feature_label(c) for c in comparison_df.index]
                            st.dataframe(comparison_df, width="stretch", height=250)

                            cluster_strengths, cluster_weaknesses = clustering_service.compute_strengths_weaknesses(
                                cluster_avg, overall_avg, overall_std=overall_std
                            )
                            col_str, col_wk = st.columns(2)
                            with col_str:
                                if cluster_strengths:
                                    st.success(
                                        f"**✅ Điểm mạnh:** {', '.join(feature_label(c) for c in cluster_strengths[:5])}"
                                    )
                                else:
                                    st.info("**✅ Điểm mạnh:** Không có điểm nổi bật")
                            with col_wk:
                                if cluster_weaknesses:
                                    st.warning(
                                        f"**⚠️ Điểm yếu:** {', '.join(feature_label(c) for c in cluster_weaknesses[:5])}"
                                    )
                                else:
                                    st.info("**⚠️ Điểm yếu:** Không có điểm yếu rõ ràng")

                            st.markdown("###### Kế hoạch can thiệp theo cụm (ưu tiên)")
                            intervention_df = clustering_service.compute_intervention_plan(
                                diff_pct_series, selected_cols
                            )
                            st.dataframe(
                                intervention_df,
                                column_config={
                                    "Chỉ số": st.column_config.TextColumn("Chỉ số", width="medium"),
                                    "Chênh lệch so với nhóm (%)": st.column_config.NumberColumn(
                                        "Chênh lệch (%)", width="small", format="%.1f%%"
                                    ),
                                    "Mức ưu tiên": st.column_config.TextColumn("Mức ưu tiên", width="small"),
                                    "Hành động gợi ý": st.column_config.TextColumn("Hành động gợi ý", width="large"),
                                },
                                use_container_width=True,
                                height=240,
                                hide_index=True,
                            )

                            high_priority = intervention_df[intervention_df["Mức ưu tiên"] == "Cao"]["Chỉ số"].tolist()
                            medium_priority = intervention_df[intervention_df["Mức ưu tiên"] == "Trung bình"][
                                "Chỉ số"
                            ].tolist()
                            st.markdown(
                                "<div style='background:var(--surface);color:var(--text-primary);padding:12px 14px;border-radius:10px;margin-top:8px;border:1px solid var(--border);'>"
                                f"<span style='color:var(--text-primary) !important;'><b>📌 Tóm tắt hành động cụm {cluster_to_analyze}:</b></span><br>"
                                f"<span style='color:var(--text-primary) !important;'>- Ưu tiên cao: {', '.join(high_priority[:4]) if high_priority else 'Không có'}</span><br>"
                                f"<span style='color:var(--text-primary) !important;'>- Ưu tiên trung bình: {', '.join(medium_priority[:4]) if medium_priority else 'Không có'}</span><br>"
                                f"<span style='color:var(--text-primary) !important;'>- Quy mô cụm: {len(df_cluster_only)} sinh viên</span>"
                                "</div>",
                                unsafe_allow_html=True,
                            )

                            st.markdown("---")
                            st.markdown("###### Gợi ý cá nhân (dựa trên hồ sơ học tập tương tự)")

                            student_id_col = None
                            for col in ['student_id', 'id', 'student_name', 'name']:
                                if col in df_cluster_only.columns:
                                    student_id_col = col
                                    break

                            if student_id_col is None:
                                st.info(
                                    "ℹ️ Để dùng gợi ý cá nhân, dữ liệu cần cột định danh sinh viên (student_id, id, student_name, hoặc name)."
                                )
                            else:
                                student_ids = df_cluster_only[student_id_col].unique().tolist()
                                if not student_ids:
                                    st.warning(f"⚠️ Cụm {cluster_to_analyze} không có sinh viên nào để chọn.")
                                else:
                                    if role == "Sinh viên":
                                        student_id_to_analyze = current_student_id
                                        st.caption(f"👤 Phân tích chi tiết cho: **{student_id_to_analyze}**")
                                    else:
                                        student_session_key = (
                                            f"rec_student_select_key_{str(cluster_to_analyze).replace(' ', '_')}"
                                        )
                                        idx_key = f"{student_session_key}_idx"
                                        sel_key = f"{student_session_key}_select"
                                        if idx_key not in st.session_state:
                                            st.session_state[idx_key] = 0
                                        student_index = st.session_state.get(idx_key, 0)
                                        student_index = min(student_index, len(student_ids) - 1) if student_ids else 0
                                        student_id_to_analyze = st.selectbox(
                                            f"👨‍🎓 Chọn Sinh viên trong Cụm {cluster_to_analyze}:",
                                            student_ids,
                                            index=student_index,
                                            help="Chọn sinh viên để xem phân tích chi tiết và gợi ý học tập.",
                                            key=sel_key,
                                        )
                                        if student_id_to_analyze in student_ids:
                                            st.session_state[idx_key] = student_ids.index(student_id_to_analyze)

                                    if student_id_to_analyze:
                                        try:
                                            student_row = df_cluster_only[
                                                df_cluster_only[student_id_col] == student_id_to_analyze
                                            ]
                                            if student_row.empty:
                                                st.error(
                                                    f"⚠️ Không tìm thấy dữ liệu cho sinh viên `{student_id_to_analyze}`."
                                                )
                                            else:
                                                student_data = student_row[selected_cols].iloc[0]
                                                student_comparison_df = pd.DataFrame(
                                                    {
                                                        'Chỉ số': [feature_label(c) for c in selected_cols],
                                                        'Sinh viên': [
                                                            round(float(student_data[c]), 2) for c in selected_cols
                                                        ],
                                                        'Cụm (TB)': [
                                                            round(float(cluster_avg[c]), 2) for c in selected_cols
                                                        ],
                                                        'Toàn lớp (TB)': [
                                                            round(float(overall_avg[c]), 2) for c in selected_cols
                                                        ],
                                                        'Chênh lệch vs Cụm': [
                                                            f"{(student_data[c] - cluster_avg[c]):+.2f}"
                                                            for c in selected_cols
                                                        ],
                                                        'Chênh lệch vs Toàn lớp': [
                                                            f"{(student_data[c] - overall_avg[c]):+.2f}"
                                                            for c in selected_cols
                                                        ],
                                                    }
                                                )
                                                st.markdown(f"**📊 Phân tích Sinh viên `{student_id_to_analyze}`:**")
                                                st.dataframe(
                                                    student_comparison_df,
                                                    column_config={
                                                        "Chỉ số": st.column_config.TextColumn("Chỉ số", width="medium"),
                                                        "Sinh viên": st.column_config.NumberColumn(
                                                            "Sinh viên", width="small"
                                                        ),
                                                        "Cụm (TB)": st.column_config.NumberColumn(
                                                            "Cụm (TB)", width="small"
                                                        ),
                                                        "Toàn lớp (TB)": st.column_config.NumberColumn(
                                                            "Toàn lớp (TB)", width="small"
                                                        ),
                                                        "Chênh lệch vs Cụm": st.column_config.TextColumn(
                                                            "Lệch Cụm", width="small"
                                                        ),
                                                        "Chênh lệch vs Toàn lớp": st.column_config.TextColumn(
                                                            "Lệch Toàn lớp", width="small"
                                                        ),
                                                    },
                                                    use_container_width=True,
                                                    height=220,
                                                    hide_index=True,
                                                )

                                                student_weaknesses_vs_cluster = (
                                                    (student_data < cluster_avg * 0.9)
                                                    .index[student_data < cluster_avg * 0.9]
                                                    .tolist()
                                                )
                                                student_weaknesses_vs_overall = (
                                                    (student_data < overall_avg * 0.9)
                                                    .index[student_data < overall_avg * 0.9]
                                                    .tolist()
                                                )
                                                student_strengths = (
                                                    (student_data > cluster_avg * 1.1)
                                                    .index[student_data > cluster_avg * 1.1]
                                                    .tolist()
                                                )

                                                st.markdown("**Gợi ý và khuyến nghị**")
                                                if student_weaknesses_vs_cluster:
                                                    st.warning(
                                                        f"Cần cải thiện (so với cụm {cluster_to_analyze}) cho `{student_id_to_analyze}`: {', '.join(feature_label(c) for c in student_weaknesses_vs_cluster[:5])}"
                                                    )
                                                elif student_weaknesses_vs_overall:
                                                    st.info(
                                                        f"So với toàn lớp: `{student_id_to_analyze}` đang cần cố gắng thêm ở: {', '.join(feature_label(c) for c in student_weaknesses_vs_overall[:5])}"
                                                    )
                                                else:
                                                    st.success(
                                                        f"`{student_id_to_analyze}` có kết quả học tập ổn định, đạt tốt so với cụm và toàn lớp."
                                                    )
                                                if student_strengths:
                                                    st.success(
                                                        f"Điểm mạnh nổi trội của `{student_id_to_analyze}`: {', '.join(feature_label(c) for c in student_strengths[:5])}"
                                                    )

                                                st.markdown("**🎯 Gợi ý học tập cộng tác theo nhóm**")
                                                with st.container(border=True):
                                                    cl_str_names = (
                                                        [feature_label(c) for c in cluster_strengths[:3]]
                                                        if cluster_strengths
                                                        else []
                                                    )
                                                    cl_wk_names = (
                                                        [feature_label(c) for c in cluster_weaknesses[:3]]
                                                        if cluster_weaknesses
                                                        else []
                                                    )
                                                    st.markdown(
                                                        f"**Nhóm học tập Cụm {cluster_to_analyze}** (`{len(df_cluster_only)} sinh viên`)"
                                                    )
                                                    col_g1, col_g2 = st.columns(2)
                                                    with col_g1:
                                                        if cl_str_names:
                                                            st.success(
                                                                f"**Thế mạnh tập thể:** {', '.join(cl_str_names)}"
                                                            )
                                                        else:
                                                            st.info(
                                                                "**Thế mạnh tập thể:** Nền tảng học tập cơ bản ổn định, tinh thần học đều"
                                                            )
                                                    with col_g2:
                                                        if cl_wk_names:
                                                            st.warning(
                                                                f"**Trọng tâm bứt phá:** {', '.join(cl_wk_names)}"
                                                            )
                                                        else:
                                                            st.info(
                                                                "**Trọng tâm bứt phá:** Rèn luyện kỹ năng thực hành và đồ án nâng cao"
                                                            )
                                                    st.caption(
                                                        f"💡 **Khuyến nghị hoạt động:** Khuyến khích thành lập nhóm học tập 3–4 bạn trong Cụm {cluster_to_analyze} để cùng ôn tập và trao đổi tài liệu tự học."
                                                    )

                                                try:
                                                    st.markdown("**🧭 Bạn học có hồ sơ tương tự**")
                                                    n_rows = len(df_results)
                                                    if X_processed.shape[0] != n_rows:
                                                        if role == "Sinh viên":
                                                            st.warning(
                                                                "Dữ liệu phân cụm đã thay đổi — vui lòng liên hệ Giảng viên để cập nhật lại nhóm học tập."
                                                            )
                                                        else:
                                                            st.warning(
                                                                "Số hàng dữ liệu không khớp ma trận đặc trưng lúc phân cụm. Nhấn lại **Chạy Phân cụm K-Means**."
                                                            )
                                                    else:
                                                        pos_mask = (
                                                            df_results[student_id_col].values == student_id_to_analyze
                                                        )
                                                        student_positions = np.flatnonzero(pos_mask)
                                                        if student_positions.size == 0:
                                                            st.info(
                                                                "Không xác định được vị trí hàng của sinh viên trong bảng."
                                                            )
                                                        else:
                                                            student_pos = int(student_positions[0])
                                                            cluster_mask = (
                                                                df_results["cluster"].values == cluster_to_analyze
                                                            )
                                                            cluster_pos = np.flatnonzero(cluster_mask)
                                                            cset = set(cluster_pos.tolist())
                                                            if student_pos not in cset:
                                                                st.info(
                                                                    "Sinh viên không thuộc cụm đang xem hoặc dữ liệu đã thay đổi — chạy lại phân cụm."
                                                                )
                                                            elif len(cluster_pos) < 2:
                                                                st.info(
                                                                    "Không đủ sinh viên trong cụm để gợi ý tương tự (cần ít nhất 2)."
                                                                )
                                                            else:
                                                                neighbors = clustering_service.find_similar_students(
                                                                    X_processed, cluster_pos, student_pos, top_k=5
                                                                )
                                                                if neighbors:
                                                                    id_col_nn = None
                                                                    for col in (
                                                                        "student_id",
                                                                        "id",
                                                                        "student_name",
                                                                        "name",
                                                                    ):
                                                                        if col in df_results.columns:
                                                                            id_col_nn = col
                                                                            break
                                                                    rows = []
                                                                    for gpos, score in neighbors:
                                                                        n_row = df_results.iloc[gpos]
                                                                        neighbor_id = (
                                                                            n_row[id_col_nn] if id_col_nn else str(gpos)
                                                                        )
                                                                        n_scores = n_row[selected_cols]
                                                                        top_feat = (
                                                                            n_scores.astype(float).idxmax()
                                                                            if len(selected_cols) > 0
                                                                            else "—"
                                                                        )
                                                                        top_val = (
                                                                            round(float(n_scores[top_feat]), 1)
                                                                            if top_feat != "—"
                                                                            else 0
                                                                        )
                                                                        rows.append(
                                                                            {
                                                                                "Mã SV bạn học": str(neighbor_id),
                                                                                "Độ tương đồng": f"{score * 100:.1f}%",
                                                                                "Môn thế mạnh nổi trội": f"{feature_label(top_feat)} ({top_val}đ)",
                                                                                "Đề xuất ghép nhóm": "Cùng tiến độ — Ghép đôi Study Buddy ôn tập & làm bài lab",
                                                                            }
                                                                        )
                                                                    st.dataframe(
                                                                        pd.DataFrame(rows),
                                                                        column_config={
                                                                            "Mã SV bạn học": st.column_config.TextColumn(
                                                                                "Mã bạn học", width="small"
                                                                            ),
                                                                            "Độ tương đồng": st.column_config.TextColumn(
                                                                                "Độ tương đồng", width="small"
                                                                            ),
                                                                            "Môn thế mạnh nổi trội": st.column_config.TextColumn(
                                                                                "Môn thế mạnh nổi trội", width="medium"
                                                                            ),
                                                                            "Đề xuất ghép nhóm": st.column_config.TextColumn(
                                                                                "Đề xuất kết nối học tập", width="large"
                                                                            ),
                                                                        },
                                                                        use_container_width=True,
                                                                        height=220,
                                                                        hide_index=True,
                                                                    )
                                                                else:
                                                                    st.info(
                                                                        "Không đủ dữ liệu trong cụm để gợi ý bạn học tương tự."
                                                                    )
                                                except Exception:
                                                    st.info(
                                                        "Không thể tính gợi ý content-based do hạn chế dữ liệu hoặc cấu trúc."
                                                    )

                                                try:
                                                    st.markdown("**🧩 Gợi ý cụm tham chiếu (học từ cụm mạnh hơn)**")
                                                    cluster_means_all = df_results.groupby('cluster')[
                                                        selected_cols
                                                    ].mean()
                                                    best_ref = None
                                                    if cluster_weaknesses:
                                                        best_ref = clustering_service.find_reference_cluster(
                                                            cluster_means_all, cluster_to_analyze, cluster_weaknesses
                                                        )
                                                    if best_ref is not None:
                                                        st.info(
                                                            f"🌟 **Cụm tham chiếu để học hỏi — Cụm {best_ref}:** Cụm {best_ref} có điểm trung bình cao nhất ở các tiêu chí mà "
                                                            f"Cụm {cluster_to_analyze} đang cần cải thiện ({', '.join(feature_label(w) for w in cluster_weaknesses[:3])}). "
                                                            f"Sinh viên nên tham gia các buổi trao đổi học thuật chéo giữa hai cụm."
                                                        )
                                                    else:
                                                        top_cluster = cluster_means_all.mean(axis=1).idxmax()
                                                        if top_cluster != cluster_to_analyze:
                                                            st.success(
                                                                f"🌟 **Cụm hình mẫu bứt phá — Cụm {top_cluster}:** Hiện Cụm {cluster_to_analyze} đang có phong độ học tập ổn định. "
                                                                f"Để nâng bậc lên nhóm sinh viên xuất sắc, bạn có thể tham khảo phương pháp tự học và tham gia các seminar chuyên đề của Cụm {top_cluster}."
                                                            )
                                                        else:
                                                            st.success(
                                                                f"🏆 **Cụm {cluster_to_analyze} đang dẫn đầu toàn khóa về các chỉ số học tập!** "
                                                                f"Hãy tiếp tục giữ vững phong độ, đồng thời phát huy vai trò hướng dẫn/chia sẻ kinh nghiệm học tập cho các bạn sinh viên cụm khác."
                                                            )
                                                except Exception:
                                                    st.info("Không thể xác định cụm tham chiếu do hạn chế dữ liệu.")
                                        except (IndexError, KeyError, Exception) as e:
                                            ui_kit.report_error("⚠️ Lỗi khi phân tích sinh viên. Vui lòng thử lại.", e)
            except Exception as e:
                ui_kit.report_error("⚠️ Lỗi khi xử lý cụm. Vui lòng thử lại hoặc chạy lại phân cụm.", e)

        # --- BẢNG SINH VIÊN THEO CỤM + XUẤT FILE ---
        # Sinh viên KHÔNG được thấy danh sách/điểm số của sinh viên khác (rò rỉ
        # danh tính + dữ liệu bạn học) — chỉ Giảng viên/Admin xem được bảng đầy
        # đủ; Sinh viên chỉ thấy đúng 1 dòng của chính mình (đã hiển thị ở khối
        # "Bạn thuộc Cụm ..." phía trên) nên bỏ qua hẳn bảng này.
        if role != "Sinh viên":
            with st.container(border=True):
                st.markdown("##### Danh sách sinh viên theo cụm")
                _display_cols = [c for c in df_results.columns if c != 'cluster']
                _cluster_filter = st.selectbox(
                    "Lọc theo cụm:",
                    ["Tất cả"] + [str(c) for c in sorted(df_results['cluster'].unique())],
                    key="cluster_table_filter",
                )
                _table_df = (
                    df_results
                    if _cluster_filter == "Tất cả"
                    else df_results[df_results['cluster'].astype(str) == _cluster_filter]
                )
                st.dataframe(_table_df[['cluster'] + _display_cols], width="stretch", height=320)

                st.caption(
                    "Dataset và Model KMeans đã được tự động lưu vào Kho dữ liệu ở panel Diễn giải cụm phía trên."
                )
                _xbytes = to_excel(st.session_state.cluster_results_df)
                if _xbytes:
                    st.download_button(
                        label="📥 Xuất file Excel (.xlsx)",
                        data=_xbytes,
                        file_name=f"cluster_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="cluster_export_xlsx_step5",
                    )
