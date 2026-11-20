"""Shared runtime imports for Streamlit tab modules."""

from dss.config import *  # noqa: F403
from dss.core.runtime_mode import synthetic_data_allowed
from dss.core.target_utils import is_id_like
from dss.security.upload_security import UploadValidationError, parse_tabular_upload
from dss.services import model_registry
from dss.services.model_service import model_lifecycle_badge_text as _model_lifecycle_badge_text
from dss.tabs import ui_kit


def warehouse_tab(warehouse, role=None):
    """Tab quản lý kho dữ liệu."""
    is_admin = role == "Admin"
    ui_kit.section_header(
        "Kho dữ liệu",
        subtitle="Quản lý dataset, mô hình và lịch sử.",
        icon="📦",
    )

    # Kiểm tra kho dữ liệu
    if warehouse is None:
        st.error("Lỗi: Không thể khởi tạo kho dữ liệu.")
        return

    tab_datasets, tab_models, tab_history = st.tabs(
        ["📊 Datasets (Dữ liệu)", "🧠 AI Models (Mô hình)", "📜 History (Lịch sử)"]
    )

    # --- TAB DATASETS ---
    with tab_datasets:
        ui_kit.subsection_header(
            "Quản lý dữ liệu",
            subtitle="Tải lên, xem trước và quản lý các tập dữ liệu đang lưu trong kho.",
            icon="📊",
        )

        # Production Demo Policy (audit 2026-09): 2 nút nạp dữ liệu giả lập/mẫu
        # này là công cụ DEV/TEST — không được phép tồn tại trong REAL_LMS (người
        # dùng thật không được có cách nào tự bơm dữ liệu tổng hợp vào phiên làm
        # việc, kể cả Giảng viên/Admin).
        if not synthetic_data_allowed():
            st.info(
                "Chế độ REAL_LMS: nạp dữ liệu mẫu/giả lập đã bị tắt. Dữ liệu chỉ được nạp qua "
                "kết nối LMS thật hoặc tải tệp thật bên dưới."
            )
        else:
            # Thao tác nạp dữ liệu nhanh: Đồng bộ LMS & Dữ liệu mẫu
            c_sync1, c_sync2 = st.columns(2)
            with c_sync1:
                if st.button(
                    "🔄 Đồng bộ dữ liệu từ LMS (Giả lập)", key="wh_sync_lms_btn", type="primary", width="stretch"
                ):
                    from dss.core.data_helpers import generate_lms_data
                    from dss.core.init_app import clear_all_session_state_for_new_data

                    clear_all_session_state_for_new_data()
                    _lms_df, _lms_course, _lms_term = generate_lms_data()
                    from dss.services.academic_persistence import persist_dataframe_if_configured

                    persist_dataframe_if_configured(_lms_df, "LMS_SYNC", _lms_course, _lms_term)
                    st.session_state.current_df = _lms_df
                    st.session_state.current_dataset_id = f"lms_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    try:
                        ds_id, _ = warehouse.save_dataset(
                            _lms_df,
                            dataset_name=f"lms_sync_{_lms_course}_{_lms_term}",
                            description=f"Đồng bộ giả lập từ LMS — {_lms_course}, {_lms_term}",
                            data_type="raw",
                        )
                        st.session_state.current_dataset_id = ds_id
                        # FINAL PRODUCTION GAP CLOSURE (Phần 3/4): dữ liệu VẪN dùng được
                        # trong phiên này (current_df đã gán ở trên) ngay cả khi warehouse
                        # save thất bại — nhưng phải nói RÕ chưa lưu lâu dài, không hiện
                        # "Đã đồng bộ" như thể mọi thứ hoàn tất.
                        st.session_state.show_success_message = "✅ Đã đồng bộ dữ liệu từ LMS (giả lập)!"
                    except Exception:
                        from dss.core.logging_config import get_logger

                        get_logger(__name__).exception(
                            "Luu dataset dong bo LMS vao kho that bai (ma EDSS-LMS-SYNC-SAVE-001)."
                        )
                        st.session_state.show_error_message = (
                            "⚠️ Đã nạp dữ liệu LMS (giả lập) cho phiên làm việc này, nhưng KHÔNG lưu "
                            "được vào kho dữ liệu lâu dài — dữ liệu sẽ mất nếu tải lại trang. Vui lòng "
                            "thử lại hoặc liên hệ quản trị viên."
                        )
                    st.rerun()
            with c_sync2:
                if st.button(
                    "📊 Dùng dữ liệu mẫu LMS-scale 20.000 SV (Synthetic)", key="wh_sample_data_btn", width="stretch"
                ):
                    from dss.core.data_helpers import generate_data
                    from dss.core.init_app import clear_all_session_state_for_new_data

                    df_sample = generate_data(n_students=20000, random_state=42)
                    clear_all_session_state_for_new_data()
                    st.session_state.current_df = df_sample
                    st.session_state.current_dataset_id = "sample_data_lms_scale_v1"
                    st.session_state.current_dataset_name = "Dữ liệu mẫu LMS-scale 20.000 SV"
                    st.session_state.current_dataset_source = "DỮ LIỆU MÔ PHỎNG / SYNTHETIC"
                    try:
                        warehouse.log_activity(
                            "Tải Dữ liệu",
                            "Sử dụng dữ liệu mẫu LMS-scale 20k",
                            {"rows": len(df_sample), "cols": len(df_sample.columns)},
                        )
                    except Exception:
                        pass
                    st.session_state.show_success_message = "✅ Đã tải dữ liệu mẫu LMS-scale 20.000 SV thành công!"
                    st.rerun()

        if st.session_state.get("current_dataset_id") == "sample_data_lms_scale_v1":
            _active_sample = st.session_state.get("current_df")
            st.info(
                f"Đang dùng: **Dữ liệu mẫu LMS-scale 20.000 SV** · "
                f"**{len(_active_sample):,} dòng** · DỮ LIỆU MÔ PHỎNG / SYNTHETIC"
                if _active_sample is not None
                else "Dữ liệu mẫu chưa được tải."
            )

        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        # Production Demo Policy (audit 2026-09): phân hệ này CÓ ghi rõ "giả
        # lập" ở mọi nút/nhãn (không dán nhãn "Live" giả như khối LMS/CMS ở
        # admin_settings.py đã sửa) nhưng vẫn GHI ĐÈ trực tiếp lên dataset
        # đang mở bằng giá trị ngẫu nhiên — không phù hợp để bật trong REAL_LMS
        # dù có gắn nhãn giả lập, vì có thể làm hỏng dữ liệu lớp học thật.
        if not synthetic_data_allowed():
            st.caption("Chế độ REAL_LMS: mô phỏng sự kiện LMS thời gian thực đã bị tắt.")
        else:
            # Phân hệ LMS Live Push & Webhook Stream thời gian thực
            with st.expander("📡 LMS Realtime Live Push & Webhook Stream (Giả lập)", expanded=False):
                st.markdown(
                    "Đồng bộ sự kiện thời gian thực từ LMS (Moodle Webhook / Canvas LTI) — "
                    "cập nhật trực tiếp điểm thi, điểm danh vào dataset đang mở mà không cần nạp lại file."
                )
                from dss.services.lms_live_sync import lms_live_sync_manager

                cur_df = st.session_state.get("current_df")
                id_col_w = next((c for c in cur_df.columns if is_id_like(c)), None) if cur_df is not None else None
                student_list = (
                    cur_df[id_col_w].dropna().astype(str).unique().tolist()
                    if (cur_df is not None and id_col_w)
                    else ["SV2025_001"]
                )

                lw_col1, lw_col2 = st.columns([1.5, 2], gap="medium")
                with lw_col1:
                    st.markdown("**⚡ Bắn sự kiện LMS giả lập**")
                    sel_sv_live = st.selectbox("Chọn sinh viên nhận sự kiện:", student_list[:30], key="wh_live_sv_sel")

                    btn_col_a, btn_col_b = st.columns(2)
                    with btn_col_a:
                        if st.button("📝 Điểm thi mới (Moodle)", key="wh_push_moodle_btn", width="stretch"):
                            import random

                            new_grade = round(random.uniform(7.5, 9.8), 2)
                            evt, updated_df, msg = lms_live_sync_manager.simulate_moodle_grade_push(
                                sel_sv_live, new_grade, cur_df
                            )
                            if updated_df is not None:
                                st.session_state.current_df = updated_df
                            st.session_state.show_success_message = f"✅ [Moodle Webhook] {msg}"
                            st.rerun()

                    with btn_col_b:
                        if st.button("🕒 Điểm danh mới (Canvas)", key="wh_push_canvas_btn", width="stretch"):
                            import random

                            new_att = round(random.uniform(0.85, 1.0), 2)
                            evt, updated_df, msg = lms_live_sync_manager.simulate_canvas_attendance_push(
                                sel_sv_live, new_att, cur_df
                            )
                            if updated_df is not None:
                                st.session_state.current_df = updated_df
                            st.session_state.show_success_message = f"✅ [Canvas LTI Event] {msg}"
                            st.rerun()

                with lw_col2:
                    st.markdown("**📜 Nhật ký sự kiện thời gian thực (Live Event Stream)**")
                    events = lms_live_sync_manager.get_event_history(limit=5)
                    if events:
                        for ev in events:
                            badge_color = "#10B981" if ev.status == "processed" else "#EF4444"
                            st.markdown(
                                f"<div style='border-left: 3px solid {badge_color}; background:var(--bg-secondary); padding:0.4rem 0.6rem; border-radius:4px; margin-bottom:4px; font-size:var(--fs-caption);'>"
                                f"<b>[{ev.source}]</b> {ev.student_id} · <b>{ev.event_type}</b> · {ev.description} "
                                f"<span style='color:var(--text-secondary); float:right;'>{ev.timestamp}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("Chưa có sự kiện live stream nào. Hãy bấm các nút bên trái để phát sự kiện.")

        # 1. Thêm Dataset mới
        with st.expander("Thêm Dataset Mới vào Kho", expanded=False):
            upload_file = st.file_uploader("Tải lên file CSV hoặc Excel:", type=["csv", "xlsx", "xls"])
            new_name = st.text_input("Tên Dataset (Tùy chọn):", placeholder="Mặc định: Tên file gốc")
            new_desc = st.text_area("Mô tả:", placeholder="Ví dụ: Dữ liệu điểm thi HK1 2023")

            # [NEW] Chọn loại dữ liệu (Mở rộng theo yêu cầu)
            data_type_mapping = {
                "Dữ liệu thô (Raw)": "raw",
                "Dữ liệu đã xử lý (Processed)": "processed",
                "Dữ liệu sau Huấn luyện (Training)": "training",
                "Dữ liệu Đánh giá/Kết quả (Evaluation)": "evaluation",
                "Dữ liệu Gợi ý (Advisor)": "advisor",
            }

            data_type_option = st.selectbox("Loại dữ liệu:", list(data_type_mapping.keys()), index=0)

            # Auto-save ngay khi có file mới được tải lên — không cần bấm nút Lưu.
            # Dùng chữ ký (tên + kích thước) của file để chỉ lưu đúng 1 lần cho mỗi
            # file, tránh tạo dataset trùng lặp ở các lần rerun sau (khi gõ mô tả...).
            if upload_file:
                _upload_sig = f"{upload_file.name}_{upload_file.size}"
                if st.session_state.get("_autosave_sig_upload_dataset") != _upload_sig:
                    try:
                        parsed_upload = parse_tabular_upload(upload_file)
                        df_new = parsed_upload.frame

                        final_name = new_name if new_name else os.path.splitext(parsed_upload.name)[0]

                        # Xác định data_type từ mapping
                        selected_type = data_type_mapping[data_type_option]

                        # Gọi hàm save chung (thay vì chỉ save_processed_data)
                        ds_id, _ = warehouse.save_dataset(
                            df_new, dataset_name=final_name, description=new_desc, data_type=selected_type
                        )

                        # Tự động set làm active dataset
                        st.session_state.current_df = df_new
                        st.session_state.current_dataset_id = ds_id
                        st.session_state.cleaned_df = None  # Reset cleaning state
                        st.session_state["_autosave_sig_upload_dataset"] = _upload_sig

                        st.success(f"✅ Đã tự động thêm dataset và đặt làm dữ liệu hiện tại! ID: {ds_id}")
                        st.rerun()
                    except UploadValidationError as exc:
                        st.error(str(exc))
                    except Exception:
                        st.error("❌ Không thể lưu dataset. Vui lòng thử lại hoặc liên hệ quản trị viên.")
                else:
                    st.caption("✅ File này đã được tự động lưu vào kho.")

        # 2. Danh sách Dataset theo 5 loại mục
        datasets = warehouse.list_datasets()

        if datasets:
            total_rows = sum(int(ds.get("n_rows") or 0) for ds in datasets)
            ui_kit.kpi_row(
                [
                    ("Tổng số dataset", len(datasets)),
                    ("Tổng số dòng dữ liệu", f"{total_rows:,}"),
                ]
            )
            st.markdown("<div style='height:0.4rem;'></div>", unsafe_allow_html=True)

        # Định nghĩa 6 loại dữ liệu
        data_categories = {
            "raw": "Dữ liệu Thô (Raw)",
            "processed": "Dữ liệu sau Khám phá (Explored)",
            "training": "Dữ liệu sau Huấn luyện (Trained)",
            "clustered": "Dữ liệu sau Phân cụm (Clustered)",
            "evaluation": "Dữ liệu Đánh giá (Evaluation)",
            "advisor": "Dữ liệu Gợi ý (Advisor)",
        }

        # Phân loại datasets
        grouped_datasets = {k: [] for k in data_categories}
        grouped_datasets['other'] = []  # Cho các loại cũ hoặc không xác định

        if datasets:
            for ds in datasets:
                dtype = ds.get('data_type', 'other')
                # Map các loại cũ nếu cần (nếu có)

                if dtype in grouped_datasets:
                    grouped_datasets[dtype].append(ds)
                else:
                    grouped_datasets['other'].append(ds)

        # Tạo tabs cho các loại dữ liệu
        tabs_list = list(data_categories.values()) + ["Khác"]
        cat_tabs = st.tabs(tabs_list)

        for i, (cat_key, cat_name) in enumerate(data_categories.items()):
            with cat_tabs[i]:
                ds_list = grouped_datasets[cat_key]
                if not ds_list:
                    st.info(f"Chưa có {cat_name} nào.")
                else:
                    for ds in ds_list:
                        with st.expander(f"📁 {ds['dataset_name']} (ID: `{ds['dataset_id']}`)", expanded=False):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write(f"📅 **Tạo:** {ds['created_at']}")
                            with col2:
                                st.write(f"🔢 **Rows:** {ds['n_rows']}")
                            with col3:
                                st.write(f"📋 **Cols:** {ds['n_cols']}")

                            st.write(f"📝 **Mô tả:** {ds.get('description', '')}")

                            col_act1, col_act2, col_act3 = st.columns(3)
                            with col_act1:
                                if st.button(
                                    "🚀 Sử dụng Dữ liệu này", key=f"use_ds_{ds['dataset_id']}", type="primary"
                                ):
                                    df_load, meta = warehouse.load_dataset(ds['dataset_id'])
                                    if df_load is not None:
                                        st.session_state.current_df = df_load
                                        st.session_state.current_dataset_id = ds['dataset_name']
                                        st.session_state.cleaned_df = None  # Reset cleaning state
                                        if 'target_for_analysis' in st.session_state:
                                            del st.session_state.target_for_analysis

                                        # Thông báo và hướng dẫn
                                        st.success(f"✅ Đã tải dữ liệu '{ds['dataset_name']}'!")
                                        st.info(
                                            "💡 Bạn có thể chuyển sang các tab 'Khám phá', 'Huấn luyện' hoặc 'Phân cụm' để làm việc với dữ liệu này."
                                        )
                                        # Không rerun ngay để user đọc thông báo, hoặc rerun nếu muốn trải nghiệm mượt
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Lỗi: {meta}")

                                with st.expander("Chỉnh sửa Mô tả"):
                                    new_desc_edit = st.text_input(
                                        "Mô tả mới:", value=ds.get('description', ''), key=f"desc_{ds['dataset_id']}"
                                    )
                                    # Auto-save: gõ xong (Enter/rời ô nhập) là tự lưu, không cần bấm nút.
                                    if new_desc_edit != ds.get('description', ''):
                                        success, msg = warehouse.update_dataset_description(
                                            ds['dataset_id'], new_desc_edit
                                        )
                                        if success:
                                            st.success(f"✅ Đã tự động lưu mô tả mới. {msg}")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(msg)

                            with col_act2:
                                # Download logic
                                dataset_path = os.path.join(warehouse.data_path, f"{ds['dataset_id']}.csv")
                                if os.path.exists(dataset_path):
                                    with open(dataset_path, "rb") as f:
                                        st.download_button(
                                            "📥 Tải xuống CSV",
                                            f,
                                            file_name=f"{ds['dataset_name']}.csv",
                                            mime="text/csv",
                                            key=f"dl_csv_{ds['dataset_id']}",
                                        )

                            with col_act3:
                                if st.button("🗑️ Xóa", key=f"del_{ds['dataset_id']}", type="primary"):
                                    try:
                                        dataset_path = os.path.join(warehouse.data_path, f"{ds['dataset_id']}.csv")
                                        metadata_path = os.path.join(
                                            warehouse.metadata_path, f"{ds['dataset_id']}_data.json"
                                        )
                                        if os.path.exists(dataset_path):
                                            os.remove(dataset_path)
                                        if os.path.exists(metadata_path):
                                            os.remove(metadata_path)
                                        st.success("Đã xóa!")
                                        st.rerun()
                                    except Exception as e:
                                        ui_kit.report_error("Lỗi xóa", e)

        # Tab Khác
        with cat_tabs[-1]:
            if not grouped_datasets['other']:
                st.info("Không có dataset loại khác.")
            else:
                for ds in grouped_datasets['other']:
                    # (Copy logic hiển thị - để ngắn gọn tôi dùng lại function hoặc code block tương tự, nhưng ở đây tôi flatten code ra)
                    # Để code ngắn gọn, tôi hiển thị đơn giản hơn hoặc copy lại block trên.
                    # Vì tool replace giới hạn, tôi sẽ copy block hiển thị.
                    with st.expander(f"📁 {ds['dataset_name']} (ID: `{ds['dataset_id']}`)", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"📅 **Tạo:** {ds['created_at']}")
                        with col2:
                            st.write(f"🔢 **Rows:** {ds['n_rows']}")
                        with col3:
                            st.write(f"📋 **Cols:** {ds['n_cols']}")

                        st.write(f"Type: `{ds.get('data_type')}`")

                        if st.button("🚀 Sử dụng Dữ liệu này", key=f"use_ds_other_{ds['dataset_id']}", type="primary"):
                            df_load, meta = warehouse.load_dataset(ds['dataset_id'])
                            if df_load is not None:
                                st.session_state.current_df = df_load
                                st.session_state.current_dataset_id = ds['dataset_name']
                                st.session_state.cleaned_df = None
                                if 'target_for_analysis' in st.session_state:
                                    del st.session_state.target_for_analysis
                                st.success(f"Đã tải dữ liệu '{ds['dataset_name']}'!")
                                st.rerun()

                        # Download (Simplified)
                        dataset_path = os.path.join(warehouse.data_path, f"{ds['dataset_id']}.csv")
                        if os.path.exists(dataset_path):
                            with open(dataset_path, "rb") as f:
                                st.download_button(
                                    "📥 Tải xuống CSV",
                                    f,
                                    file_name=f"{ds['dataset_name']}.csv",
                                    mime="text/csv",
                                    key=f"dl_csv_other_{ds['dataset_id']}",
                                )

                        # Xóa
                        if st.button("🗑️ Xóa", key=f"del_other_{ds['dataset_id']}"):
                            try:
                                dataset_path = os.path.join(warehouse.data_path, f"{ds['dataset_id']}.csv")
                                metadata_path = os.path.join(warehouse.metadata_path, f"{ds['dataset_id']}_data.json")
                                if os.path.exists(dataset_path):
                                    os.remove(dataset_path)
                                if os.path.exists(metadata_path):
                                    os.remove(metadata_path)
                                st.success("Đã xóa!")
                                st.rerun()
                            except Exception as e:
                                ui_kit.report_error("Chưa xoá được bộ dữ liệu", e)

    # Tab hiển thị các mô hình đã lưu — "Quản lý mô hình" (Admin xem/Promote/Rollback,
    # Giảng viên xem + huấn luyện ở tab riêng, KHÔNG tự Promote/Rollback — RBAC không đổi,
    # chỉ đổi phần trình bày bên dưới).
    with tab_models:
        ui_kit.subsection_header(
            "Quản lý mô hình",
            subtitle=(
                "Model Registry — mỗi cặp Dataset + Target chỉ có đúng 1 bản Production tại "
                "1 thời điểm (nguồn duy nhất được dùng để dự đoán). Model mới huấn luyện tốt "
                "nhất được lưu ở trạng thái Candidate (chờ duyệt) — chỉ Admin mới có quyền "
                "Promote lên Production; các version cũ vẫn được giữ để xem lại hoặc rollback."
            ),
            icon="🧠",
        )
        models = warehouse.list_models()
        if not models:
            ui_kit.empty_state(
                "Chưa có mô hình nào trong kho.",
                hint="Giảng viên huấn luyện mô hình ở tab \"Huấn luyện — Dự đoán\"; model sẽ tự đăng ký vào đây.",
            )
        else:
            n_production = sum(1 for m in models if m.get("is_production"))
            n_datasets = len({m.get("dataset_id") for m in models if m.get("dataset_id")})
            ui_kit.kpi_row(
                [
                    ("Tổng số mô hình", len(models)),
                    ("Đang Production", n_production),
                    ("Dataset có mô hình", n_datasets),
                ]
            )
            st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

            # --- Spotlight các mô hình đang Production (mỗi cặp Dataset+Target
            # chỉ có đúng 1 bản) — thuần hiển thị, dùng lại đúng field đã có sẵn
            # trong `models` (is_production/metrics/version), không gọi thêm logic. ---
            production_models = [m for m in models if m.get("is_production")]
            if production_models:
                st.markdown("##### Mô hình đang Production")
                prod_cols = st.columns(min(len(production_models), 3))
                _metric_priority = ("Accuracy", "F1 Score", "R2 Score", "RMSE", "MAE")
                for i, m in enumerate(production_models):
                    with prod_cols[i % len(prod_cols)]:
                        with st.container(border=True):
                            st.markdown(f"**{m['model_name']}**")
                            st.caption(
                                f"Target: `{m['target_col']}`" + (f" · v{m.get('version')}" if m.get("version") else "")
                            )
                            _metrics = m.get("metrics", {}) or {}
                            _mk = next((k for k in _metric_priority if k in _metrics), None)
                            if _mk:
                                _mv = _metrics[_mk]
                                st.metric(_mk, f"{_mv:.3f}" if isinstance(_mv, (int, float)) else _mv)
                st.markdown("---")

            st.markdown("##### Tất cả phiên bản")
            for idx, model in enumerate(models):
                is_production = bool(model.get("is_production"))
                version = model.get("version")
                _lifecycle_text = _model_lifecycle_badge_text(model)
                badge = ui_kit.badge_html(_lifecycle_text, "success" if is_production else "neutral")
                version_label = f" · v{version}" if version else ""
                st.markdown(
                    f"<div style='margin:0.3rem 0 -0.7rem;'>{badge}</div>",
                    unsafe_allow_html=True,
                )
                with st.expander(
                    f"🤖 {model['model_name']} (ID: `{model['training_id']}`){version_label}",
                    expanded=False,
                ):
                    st.write(f"**Target:** `{model['target_col']}` | **Time:** {model['trained_at']}")
                    st.json(model['metrics'])

                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        if st.button("🤖 Sử dụng Mô hình này", key=f"use_model_{idx}", type="primary"):
                            pipeline, meta, msg = warehouse.load_model_training(model['training_id'])
                            if pipeline:
                                model_name = model.get("model_name", "Model từ kho")
                                model_meta = meta or {}
                                metrics = model_meta.get("metrics", model.get("metrics", {})) or {}
                                feature_cols = model_meta.get("feature_cols", model.get("feature_cols", [])) or []
                                target_col = model_meta.get("target_col", model.get("target_col", "unknown"))

                                if metrics.get("type") == "clustering":
                                    st.warning(
                                        "⚠️ Đây là mô hình **phân cụm (KMeans)**, không phải mô hình Phân loại/Hồi quy — "
                                        "không thể nạp vào tab Dự đoán. Hãy dùng lại mô hình này ở tab **Phân cụm**."
                                    )
                                else:
                                    is_clf = any(k in metrics for k in ("Accuracy", "F1 Score", "Precision", "Recall"))
                                    if not is_clf:
                                        model_step = getattr(pipeline, "named_steps", {}).get("model")
                                        is_clf = hasattr(model_step, "predict_proba")

                                    st.session_state.hub_pipelines = {model_name: pipeline}
                                    st.session_state.hub_results = {model_name: metrics}
                                    st.session_state.hub_feats = list(feature_cols)
                                    st.session_state.hub_target_col = target_col
                                    st.session_state.hub_type = "clf" if is_clf else "reg"
                                    st.session_state.hub_loaded_from_warehouse = True
                                    st.session_state.hub_loaded_training_id = model.get("training_id")

                                    if is_clf:
                                        # Ưu tiên tên lớp gốc đã lưu cùng model (đúng thứ tự mã số
                                        # nội bộ). model.classes_ chỉ còn mã số (0..K-1), không phải
                                        # tên gốc, nên chỉ dùng làm phương án dự phòng cho model cũ
                                        # lưu trước khi hệ thống hỗ trợ lưu class_labels.
                                        saved_class_labels = model_meta.get("class_labels") or model.get("class_labels")
                                        if saved_class_labels:
                                            st.session_state.hub_labels = list(saved_class_labels)
                                        else:
                                            classes = None
                                            model_step = getattr(pipeline, "named_steps", {}).get("model")
                                            if model_step is not None and hasattr(model_step, "classes_"):
                                                classes = list(model_step.classes_)
                                            if classes:
                                                st.warning(
                                                    "⚠️ Mô hình này được lưu trước khi hệ thống hỗ trợ lưu tên lớp gốc — "
                                                    "kết quả dự đoán sẽ hiển thị mã số nội bộ thay vì tên lớp thật."
                                                )
                                                st.session_state.hub_labels = classes
                                            else:
                                                st.session_state.hub_labels = []
                                    else:
                                        st.session_state.hub_labels = {}

                                    # Đồng bộ key đang dùng ở form train để tab Dự đoán hoạt động ngay.
                                    if target_col:
                                        st.session_state["train_hub_target"] = target_col
                                    if isinstance(feature_cols, list) and feature_cols:
                                        st.session_state["train_hub_features_pick"] = list(feature_cols)

                                    # Nếu metadata có dataset gốc, tự nạp để người dùng dự đoán ngay.
                                    linked_dataset_id = model_meta.get("dataset_id")
                                    if linked_dataset_id:
                                        df_linked, _meta_ds = warehouse.load_dataset(linked_dataset_id)
                                        if isinstance(df_linked, pd.DataFrame) and not df_linked.empty:
                                            st.session_state.current_df = df_linked
                                            st.session_state.current_dataset_id = linked_dataset_id

                                    st.success(
                                        f"Mô hình '{model_name}' đã được nạp vào phiên dự đoán. "
                                        "Bạn có thể sang tab **Huấn luyện — Dự đoán** và dùng ngay."
                                    )
                            else:
                                st.error(f"Lỗi: {msg}")

                    with col_m2:
                        # Download Model
                        if st.button("📥 Tải Model (.pkl)", key=f"dl_model_{idx}"):
                            try:
                                model_path = os.path.join(warehouse.models_path, f"{model['training_id']}.pkl")
                                if os.path.exists(model_path):
                                    with open(model_path, "rb") as f:
                                        st.download_button(
                                            "Click để tải",
                                            f,
                                            file_name=f"{model['model_name']}.pkl",
                                            key=f"real_dl_model_{idx}",
                                        )
                                else:
                                    st.error("File model không tồn tại.")
                            except Exception as e:
                                ui_kit.report_error("Không chuẩn bị được tệp mô hình để tải xuống", e)

                    with col_m2:
                        if st.button("🗑️ Xóa Model", key=f"del_model_{idx}", type="primary"):
                            try:
                                model_path = os.path.join(warehouse.models_path, f"{model['training_id']}.pkl")
                                meta_path = os.path.join(warehouse.metadata_path, f"{model['training_id']}_model.json")
                                if os.path.exists(model_path):
                                    os.remove(model_path)
                                if os.path.exists(meta_path):
                                    os.remove(meta_path)
                                st.success("Đã xóa model!")
                                st.rerun()
                            except Exception as e:
                                ui_kit.report_error("Lỗi xóa", e)

                    with col_m3:
                        if is_production:
                            st.caption("⭐ Đang là bản Production hiện tại.")
                        elif not is_admin:
                            # Quyết định RBAC: đặt/đổi Production model chỉ Admin được làm
                            # (model_registry.promote/rollback chặn ở tầng hàm — nút này chỉ
                            # ẩn đi để Giảng viên không thấy 1 nút luôn báo lỗi quyền).
                            st.caption("🔒 Chỉ Admin được đổi bản Production.")
                        else:
                            if st.button("⭐ Đặt làm Production (rollback)", key=f"promote_model_{idx}"):
                                ok, msg = model_registry.promote(warehouse, model["training_id"])
                                if ok:
                                    st.success(f"✅ Đã đặt '{model['model_name']}' (v{version}) làm Production.")
                                    st.rerun()
                                else:
                                    st.error(f"Lỗi: {msg}")

    # Tab hiển thị lịch sử các lần huấn luyện và dự đoán
    with tab_history:
        ui_kit.subsection_header(
            "Lịch sử hoạt động",
            subtitle="Toàn bộ các lần huấn luyện và dự đoán đã thực hiện trong hệ thống.",
            icon="📜",
        )
        history = warehouse.get_history('training')
        if not history:
            ui_kit.empty_state("Chưa có lịch sử huấn luyện.")
        else:
            for item in history:
                st.markdown(
                    '<div class="history-item">'
                    f"<strong>Model:</strong> {item['model_name']}<br>"
                    f"<strong>Training ID:</strong> <code>{item['training_id']}</code><br>"
                    f"<strong>Time:</strong> {item['trained_at']}</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("#### Lịch sử Dự đoán")
        prediction_history = warehouse.get_history('prediction')
        if not prediction_history:
            ui_kit.empty_state("Chưa có lịch sử dự đoán.")
        else:
            for item in prediction_history:
                prediction_type = "Phân loại" if 'label' in item['metadata'] else "Hồi quy"
                predicted_value_display = item['prediction']
                if isinstance(predicted_value_display, float):
                    predicted_value_display = f"{predicted_value_display:.2f}"
                st.markdown(
                    '<div class="history-item" style="border-left:4px solid var(--primary)">'
                    f"<strong>Type:</strong> {prediction_type}<br>"
                    f"<strong>Model:</strong> {item['metadata'].get('model_name', 'unknown')}<br>"
                    f"<strong>Result:</strong> {predicted_value_display}<br>"
                    f"<strong>Time:</strong> {item['predicted_at']}</div>",
                    unsafe_allow_html=True,
                )


def model_registry_tab(warehouse):
    """Model Registry — trang riêng CHỈ Admin, hiển thị TOÀN BỘ phiên bản mô
    hình dạng bảng gọn (không phải các thẻ expander như "Kho dữ liệu > AI
    Models") — đúng yêu cầu thiết kế "full table with status badges". Dùng lại
    NGUYÊN `warehouse.list_models()` (không thêm logic/nghiệp vụ mới); hành vi
    promote/rollback vẫn chỉ có ở "Kho dữ liệu > AI Models" (đã có RBAC qua
    `model_registry.promote/rollback`) — trang này THUẦN XEM, tránh 2 nơi cùng
    có nút hành động dễ gây nhầm "làm ở đâu mới đúng".

    LƯU Ý VỀ TRẠNG THÁI (sửa lại 2026-09-15, Issue MODELREG-001 — ghi chú cũ ở
    đây từng nói "không có Candidate tách biệt" nhưng ĐÃ LỖI THỜI):
    warehouse.py::save_model_training()/set_production_model() ghi field
    `status` với ĐÚNG 3 giá trị thật — 'candidate' (huấn luyện xong, CHƯA
    được Admin duyệt — KHÔNG BAO GIỜ tự động lên Production, xem Mục 4/
    should_promote trong save_model_training), 'production' (đang phục vụ dự
    đoán), 'archived' (từng là Production, đã bị thay bởi bản mới hơn). Bảng
    dưới đây giờ đọc đúng field này qua `_model_lifecycle_badge_text()` —
    record cũ thiếu field `status` (trước khi field này tồn tại) fallback an
    toàn về nhị phân is_production, không suy diễn thêm.
    """
    ui_kit.section_header(
        "Model Registry",
        subtitle="Toàn bộ phiên bản mô hình đã huấn luyện trong hệ thống — chỉ xem, không thao tác ở đây.",
        icon="🗄️",
    )
    st.write(
        "Model Registry quản lý các phiên bản mô hình đã huấn luyện, giúp theo dõi mô hình chờ duyệt, đang được sử dụng và đã lưu trữ."
    )
    st.caption(
        "Chờ duyệt (Candidate) → Đang sử dụng (Production) → Lưu trữ (Archived). Trang này chỉ dùng để theo dõi; thao tác chuyển phiên bản nằm trong Kho dữ liệu > AI Models."
    )
    if warehouse is None:
        st.error("Lỗi: Không thể khởi tạo kho dữ liệu.")
        return

    models = warehouse.list_models()
    if not models:
        ui_kit.empty_state(
            "Chưa có mô hình nào trong hệ thống.",
            hint="Giảng viên huấn luyện mô hình ở tab \"Huấn luyện — Dự đoán\"; model sẽ tự đăng ký vào đây.",
        )
        return

    n_production = sum(1 for m in models if m.get("is_production"))
    n_candidate = sum(1 for m in models if m.get("status") == "candidate" and not m.get("is_production"))
    n_datasets = len({m.get("dataset_id") for m in models if m.get("dataset_id")})
    ui_kit.kpi_row(
        [
            ("Tổng số phiên bản", len(models)),
            ("Đang Production", n_production),
            ("Chờ duyệt (Candidate)", n_candidate),
            ("Dataset có mô hình", n_datasets),
        ]
    )
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    def _humanize_trained_at(raw: str) -> str:
        """Bảng Model Registry trước đây hiển thị thẳng ISO timestamp thô
        (vd. "2026-09-09T22:36:00.587897") — vì st.dataframe render bảng lớn
        bằng canvas (glide-data-grid) nên lỗi này không lộ ra qua kiểm tra
        page.inner_text() thông thường, chỉ thấy được qua ảnh chụp màn hình
        thật. Định dạng lại theo kiểu Việt Nam dd/mm/yyyy HH:MM."""
        if not raw or raw == "—":
            return "—"
        try:
            dt = datetime.fromisoformat(str(raw))
            return dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            return str(raw)

    _metric_priority = ("Accuracy", "F1 Score", "R2 Score", "RMSE", "MAE")
    _rows = []
    for m in models:
        _metrics = m.get("metrics", {}) or {}
        _mk = next((k for k in _metric_priority if k in _metrics), None)
        _mv = _metrics.get(_mk) if _mk else None
        _rows.append(
            {
                "Trạng thái": _model_lifecycle_badge_text(m),
                "Model": m.get("model_name", "—"),
                "Dataset": m.get("dataset_id", "—") or "—",
                "Target": m.get("target_col", "—"),
                "Version": m.get("version") or "—",
                "Chỉ số chính": f"{_mk} = {_mv:.3f}" if isinstance(_mv, (int, float)) else "—",
                "Huấn luyện lúc": _humanize_trained_at(m.get("trained_at", "—")),
                "Mã huấn luyện": str(m.get("training_id") or "—")[:24]
                + ("…" if len(str(m.get("training_id") or "")) > 24 else ""),
            }
        )
    _df_registry = pd.DataFrame(_rows).sort_values("Trạng thái")
    st.dataframe(_df_registry, width="stretch", hide_index=True, height=min(70 + 36 * len(_rows), 560))
    st.caption(
        "Để đổi bản Production hoặc rollback, vào **Kho dữ liệu > AI Models** "
        "(chỉ Admin thấy nút thao tác, theo đúng RBAC hiện có)."
    )

    # D-1 (POST_72H_MASTER_PRODUCTION_CLOSURE, Câu 85): kiểm tra drift THEO
    # YÊU CẦU — trước đợt này evaluate_drift() đã cài đặt/test đầy đủ nhưng
    # KHÔNG có UI nào gọi tới (drift "tồn tại nhưng chưa ai bấm nút bao giờ").
    # KHÔNG có scheduler nền trong ứng dụng Streamlit này -> chỉ làm on-demand,
    # không tuyên bố giám sát tự động liên tục.
    st.markdown("---")
    with st.expander("🔍 Kiểm tra Drift (theo yêu cầu — không phải giám sát tự động)"):
        st.caption(
            "So sánh train-split vs. test-split GỐC của mô hình đã chọn — đây là kiểm tra "
            "sanity, KHÔNG PHẢI drift trên dữ liệu vận hành thật (môi trường demo chưa có "
            "luồng dữ liệu sản xuất mới sau triển khai)."
        )
        _drift_options = {
            f"{m.get('model_name', '?')} v{m.get('version', '?')} ({m.get('training_id', '')[:12]}…)": m.get(
                "training_id"
            )
            for m in models
        }
        _drift_choice = st.selectbox(
            "Chọn mô hình để kiểm tra:", list(_drift_options.keys()), key="drift_check_model_choice"
        )
        if st.button("Chạy kiểm tra Drift", key="run_drift_check_btn"):
            _drift_result = model_registry.run_on_demand_drift_check(_drift_options[_drift_choice], warehouse)
            if _drift_result.get("status") in ("ERROR", "INSUFFICIENT_DATA"):
                st.warning(_drift_result.get("message", "Không thể kiểm tra drift cho mô hình này."))
            else:
                _dd = _drift_result["data_drift"]
                _pd_res = _drift_result["performance_drift"]
                st.write(f"**Thời điểm kiểm tra:** {_drift_result.get('checked_at', '—')}")
                st.write(
                    f"**Phiên bản mô hình:** v{_drift_result.get('model_version', '—')} · **Dataset:** {_drift_result.get('dataset_id', '—')}"
                )
                st.write(f"**Data drift:** {_dd.get('overall_status', '—')}")
                st.write(f"**Performance drift:** {_pd_res.get('overall_status', '—')}")
                st.write(f"**Khuyến nghị:** {_drift_result.get('recommended_action', '—')}")
                st.info(_drift_result["window_note"])
