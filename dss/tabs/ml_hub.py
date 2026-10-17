"""Shared runtime imports for Streamlit tab modules."""
from dss.config import *  # noqa: F403
from dss.core.utils import (
    render_chart_guide,
    render_chart_guide_advanced,
    st_step_header,
    _make_safe_cv_strategy,
    _ensure_label_mapping,
)
from dss.core.data_helpers import feature_label
from dss.core.observability import predict_with_metrics
from dss.core.feature_utils import to_excel, create_feature_metrics_scatter_plots, render_save_export_buttons
from dss.core.target_utils import infer_default_target_column, infer_problem_type
from dss.tabs.eda import scatter_with_optional_ols
from dss.tabs import ui_kit

# Phase 2 refactor: logic huấn luyện/đánh giá THUẦN (không UI) đã chuyển sang
# services/model_service.py — file này (tabs/ml_hub.py) giờ chỉ còn UI, gọi
# xuống service thay vì tự định nghĩa. Giữ nguyên TÊN CŨ (alias) để không phải
# sửa hàng trăm lời gọi UI bên dưới trong cùng phase — xem model_service.py để
# đọc code thật.
from dss.services.model_service import (
    clear_prediction_training_state as _clear_prediction_training_state,
    run_training as _run_ml_hub_training,
    resolve_predicted_output_col as _resolve_predicted_output_col,
    safe_metric_value as _safe_metric_value,
    extract_failed_models as _extract_failed_models,
    build_metrics_dataframe as _build_metrics_dataframe,
    drop_near_duplicate_columns as _drop_near_duplicate_columns,
    pick_best_model_name as _pick_best_model_name,
    resolve_saved_feature_cols as _resolve_saved_feature_cols,
    update_hub_benchmark_and_build_comparison as _update_hub_benchmark_and_build_comparison,
    resolve_hub_train_config as _resolve_hub_train_config,
    assoc_strength as _assoc_strength,
    find_leaky_feature_cols as _find_leaky_feature_cols,
    training_target_change_handler as _training_target_change_handler,
    training_target_widget_callback as _training_target_widget_callback,
    resolve_production_for_prediction as _resolve_production_for_prediction,
    resolve_model_for_prediction as _resolve_model_for_prediction,
    describe_prediction_model as _describe_prediction_model,
    run_preview_benchmark as _run_preview_benchmark,
    compute_shap_local_explanation as _compute_shap_local_explanation,
    compute_shap_summary as _compute_shap_summary,
)


def render_training_config_ui(df, classification_trainer, regression_trainer, key_prefix="config"):
    """UI cấu hình huấn luyện: target, features, models. Trả về dict hoặc None."""
    # ========================================================================
    # STEP 1: SELECT TARGET & FEATURES
    # ========================================================================
    _step1_card = st.container(border=True)
    _step1_card.markdown(
        "<div style='font-size:var(--fs-card-title);font-weight:800;color:var(--text-primary);'>1️⃣ Chọn Target &amp; Features</div>"
        "<p style='color:var(--text-secondary);margin:0.3rem 0 0.6rem;font-size:var(--fs-support);'>"
        "Target = cột cần dự đoán. Features = các cột đầu vào. Đổi Target xong danh sách Features tự làm mới — "
        "chỉ cần chọn một lần ở đây, dùng chung cho cả Nhập tay / Từ file / Hàng loạt.</p>",
        unsafe_allow_html=True,
    )

    with _step1_card.expander("Cấu hình dữ liệu", expanded=True):
        all_cols = df.columns.tolist()

        data_src_type = getattr(df, "attrs", {}).get("data_source_type", "synthetic")
        if data_src_type == "synthetic":
            ui_kit.data_strip("Dữ liệu mô phỏng (demo)", "chỉ dùng để minh hoạ quy trình ML, không phải kết quả học tập thật.")
        else:
            ui_kit.data_strip("Dữ liệu thực tế", "dữ liệu quan sát thật của sinh viên.", kind="success")

        target_from_explore = st.session_state.get("target_for_analysis")
        default_target_idx = 0

        if target_from_explore and target_from_explore in all_cols:
            default_target_idx = all_cols.index(target_from_explore)
        else:
            inferred_default_col = infer_default_target_column(df)
            if inferred_default_col in all_cols:
                default_target_idx = all_cols.index(inferred_default_col)

        if f"{key_prefix}_target" not in st.session_state:
            if target_from_explore and target_from_explore in all_cols:
                st.session_state[f"{key_prefix}_target"] = target_from_explore
            else:
                st.session_state[f"{key_prefix}_target"] = all_cols[default_target_idx]

        st.session_state["_training_target_cb_prefix"] = key_prefix
        st.session_state[f"{key_prefix}_all_cols_snapshot"] = list(all_cols)

        col_target, col_type = st.columns([2, 1], vertical_alignment="bottom")
        with col_target:
            target_col = st.selectbox(
                "Đầu ra (target/cột cần dự đoán):",
                all_cols,
                key=f"{key_prefix}_target",
                on_change=_training_target_widget_callback,
            )
        
        # Determine problem type automatically from selected target
        problem_type = "Unknown"
        if target_col:
            target_series = df[target_col]
            problem_type = infer_problem_type(target_series) or "Unknown"

            if problem_type == "Phân loại (Classification)":
                class_counts = target_series.value_counts(dropna=False)
                if not class_counts.empty:
                    min_class_size = int(class_counts.min())
                    n_classes = int(class_counts.shape[0])
                    rare_class_count = int((class_counts < 5).sum())
                    imbalance_ratio = float(class_counts.max() / max(min_class_size, 1))
                    if min_class_size < 2:
                        st.warning(
                            "Target có lớp chỉ 1 mẫu. Kết quả phân loại có thể rất kém và "
                            "không thể stratify train/test ổn định. Nên gộp lớp hiếm hoặc bổ sung dữ liệu."
                        )
                    elif rare_class_count > 0 or imbalance_ratio >= 10:
                        st.info(
                            f"Target hiện có {n_classes} lớp, {rare_class_count} lớp < 5 mẫu "
                            f"(mất cân bằng ~{imbalance_ratio:.1f}x). Nên bật cân bằng dữ liệu "
                            "hoặc gộp lớp hiếm để tránh precision/recall/f1 về 0."
                        )
        
        with col_type:
            problem_type_label = problem_type
            if problem_type == "Phân loại (Classification)":
                problem_type_label = "Phân loại"
            elif problem_type == "Hồi quy (Regression)":
                problem_type_label = "Hồi quy"
            st.markdown(f"**Loại bài toán (đang dùng):** {problem_type_label}")

        available_features = [col for col in all_cols if col != target_col]
        id_cols = [
            col for col in all_cols if "id" in str(col).lower() or "name" in str(col).lower()
        ]

        # Phát hiện rò rỉ dữ liệu (leakage): cột feature gắn kết gần như tuyệt đối với Target
        # thường là bản sao/suy ra trực tiếp từ Target dưới tên khác (vd. dữ liệu mẫu có
        # final_score/diem_ky_sau/xep_loai/grade đều cùng 1 giá trị) — nếu lọt vào feature,
        # RMSE/MAE/Accuracy sẽ đẹp giả tạo vì mô hình "nhìn thấy" đáp án chứ không thực sự học.
        leaky_cols = _find_leaky_feature_cols(df, target_col, id_cols)

        exclude_cols = id_cols + ["grade", "pass_fail", "status", "result"] + leaky_cols
        default_features = [c for c in available_features if c not in exclude_cols]

        # G-2: loại cột GẦN NHƯ TRÙNG LẶP với nhau (vd. gpa_previous ~ diem_ky_nay,
        # r~0.9999) khỏi danh sách feature MẶC ĐỊNH trên UI — không bị leaky_cols
        # loại vì không rò rỉ với Target, chỉ trùng lặp giữa các feature với nhau.
        default_features, _dropped_near_dup_ui = _drop_near_duplicate_columns(df, default_features)
        if _dropped_near_dup_ui:
            st.caption(
                "ℹ️ Đã tự bỏ chọn " + ", ".join(f"`{c}`" for c in _dropped_near_dup_ui)
                + " khỏi lựa chọn mặc định (tương quan rất cao với 1 cột đã chọn khác — "
                "gần như trùng lặp thông tin). Vẫn có thể tự chọn lại bên dưới."
            )

        if leaky_cols:
            st.warning(
                f"⚠️ Đã tự động **bỏ chọn** {len(leaky_cols)} cột có tương quan rất cao (≥0.95) "
                f"với Target — nghi ngờ là bản sao/suy ra trực tiếp từ Target (vd. cùng là điểm "
                f"số dưới tên khác). Dùng làm feature sẽ khiến kết quả đánh giá (RMSE/MAE/"
                f"Accuracy) đẹp giả tạo do rò rỉ dữ liệu: "
                + ", ".join(f"`{c}`" for c in leaky_cols)
                + ". Vẫn có thể tự chọn lại bên dưới nếu chắc chắn muốn dùng."
            )

        _fk = f"{key_prefix}_features_pick"
        if _fk not in st.session_state:
            st.session_state[_fk] = list(default_features)
        else:
            _prev = st.session_state[_fk]
            _clean = [c for c in _prev if c in available_features]
            if not _clean:
                st.session_state[_fk] = list(default_features)
            elif _clean != _prev:
                st.session_state[_fk] = _clean

        selected_features = st.multiselect(
            "Đầu vào (features/cột dùng để dự đoán):",
            options=available_features,
            key=_fk,
            help="Giữ nguyên hoặc bỏ chọn cột không muốn dùng. Đổi Target ở trên sẽ gợi ý lại danh sách.",
        )
        
        if selected_features:
            st.success(f"✅ Đã chọn **{len(selected_features)}** thuộc tính")

    if not target_col or not selected_features:
        st.warning("⚠️ Vui lòng chọn Target và ít nhất một Feature.")
        return None
        
    # ========================================================================
    # STEP 1.5: [NEW] EVALUATE TARGET & FEATURES
    # ========================================================================
    with st.expander("Đánh giá & So sánh Thuộc tính (Features/Target)", expanded=False):
        st.markdown(
            "Đây là bước **kiểm tra nhanh trước khi huấn luyện chính thức**. "
            "Hệ thống dùng mô hình nền **Random Forest** để ước tính xem bộ Features hiện tại có đang hỗ trợ dự báo tốt không."
        )
        st.info(
            "📌 Khối này giúp bạn tiết kiệm thời gian: nếu điểm thấp, bạn có thể chỉnh Target/Features trước, "
            "thay vì train đầy đủ rồi mới phát hiện kết quả chưa tốt."
        )
        with st.expander("ℹ️ Khối này dùng để làm gì? Cách đọc kết quả", expanded=False):
            st.markdown(
                """
                - **Mục đích:** thử nhanh chất lượng bộ dữ liệu đầu vào đang chọn.
                - **Không phải huấn luyện chính thức:** chỉ là benchmark nhanh để ra quyết định.
                - **Kết quả có dạng** `giá trị trung bình ± độ dao động`.

                **Nếu là Phân loại (Classification):**
                - Chỉ số hiển thị: `Accuracy`.
                - Gợi ý đọc nhanh:
                  - `> 80%`: khá tốt
                  - `60-80%`: tạm ổn, có thể cải thiện
                  - `< 60%`: nên xem lại Target/Features

                **Nếu là Hồi quy (Regression):**
                - Chỉ số hiển thị: `R2 Score`.
                - Gợi ý đọc nhanh:
                  - `> 0.80`: tốt
                  - `0.50-0.80`: dùng được nhưng còn dư địa cải thiện
                  - `< 0.50`: nên rà lại dữ liệu/đặc trưng

                **Ý nghĩa của phần `±`:**
                - Số này càng nhỏ thì kết quả càng ổn định giữa các lần chia dữ liệu (cross-validation).
                """
            )
        
        col_eval1, col_eval2 = st.columns([1, 1])
        with col_eval1:
            if st.button("🔍 Đánh giá bộ Features hiện tại", key=f"{key_prefix}_eval_current"):
                with st.spinner("Đang chạy thử nghiệm nghiệm chéo (Cross-Validation)..."):
                    try:
                        bench = _run_preview_benchmark(df, selected_features, target_col, problem_type)
                        if bench["metric_name"] == "Accuracy":
                            st.success(f"**Kết quả ước tính (Accuracy):** {bench['mean']:.2%} ± {bench['std']:.2%}")
                        else:
                            st.success(f"**Kết quả ước tính (R2 Score):** {bench['mean']:.4f} ± {bench['std']:.4f}")
                    except Exception as e:
                        ui_kit.report_error("Lỗi khi đánh giá", e)
        
        with col_eval2:
            st.caption(
                "Gợi ý: Nếu kết quả thấp (< 50% hoặc R2 < 0.3), thử đổi Target/Features trước khi tiến hành huấn luyện chính thức bên dưới."
            )

    # ========================================================================
    # STEP 2: TRAINING CONFIGURATION
    # ========================================================================
    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
    ui_kit.subsection_header("Huấn luyện mô hình", icon="2️⃣")
    with st.expander("Thuật ngữ nhanh (dùng khi demo)", expanded=False):
        st.markdown(
            """
- `CV / n_splits / K-fold`: số phần dùng để chia dữ liệu và kiểm định chéo. K càng lớn thì đánh giá thường ổn định hơn nhưng chạy lâu hơn.
- `n_estimators`: số cây trong Random Forest / XGBoost / LightGBM. Nhiều cây hơn thường ổn định hơn nhưng tốn thời gian hơn.
- `n_neighbors`: số hàng xóm dùng trong KNN/SMOTE/ADASYN.
- `n_jobs=-1`: tận dụng toàn bộ lõi CPU để train nhanh hơn.
- `test_size`: tỷ lệ dữ liệu giữ lại để kiểm tra mô hình.
- `regularization`: cơ chế "phạt" mô hình quá phức tạp để giảm overfitting.
- `C` (Logistic Regression): nghịch đảo độ phạt regularization (`C` nhỏ -> phạt mạnh, `C` lớn -> phạt yếu).
- `Accuracy / F1`: chỉ số chính cho bài toán phân loại.
- `RMSE / MAE / R2`: chỉ số chính cho bài toán hồi quy.
"""
        )
    
    with st.expander("Cấu hình huấn luyện (mô hình, CV, nâng cao)", expanded=False):
        if problem_type == "Phân loại (Classification)":
            available_models = list(classification_trainer.models.keys())
        else:
            available_models = list(regression_trainer.models.keys())

        st.markdown("**1. Thuật toán & chiến lược**")
        st.caption("Mặc định: **một mô hình** — nhanh, dễ hiểu. So sánh / Ensemble chậm hơn.")
        with st.expander("Chọn model theo kiểu dữ liệu (gợi ý thực chiến)", expanded=False):
            st.markdown(
                """
                - `Linear Regression`: tốt khi quan hệ gần tuyến tính, dữ liệu sạch, ít nhiễu.
                - `Random Forest`: tốt khi dữ liệu phi tuyến vừa phải, có tương tác giữa feature.
                - `XGBoost / LightGBM`: mạnh khi dữ liệu lớn hơn, quan hệ phức tạp, cần tuning tốt.
                - `Logistic Regression`: baseline nhanh cho phân loại; dữ liệu cần feature rõ ràng.
                - `Random Forest Classifier`: ổn định khi dữ liệu lẫn numeric/categorical và có nhiễu.

                **Checklist dữ liệu để model mạnh hơn:**
                1. Đủ số mẫu (ít nhất vài trăm dòng cho tree boosting).
                2. Target không bị lệch lớp quá nặng (với classification).
                3. Feature không lộ target (tránh data leakage).
                4. Cột số/cột phân loại được chuẩn hóa kiểu dữ liệu trước train.
                """
            )

        strategy_key = f"{key_prefix}_strategy"
        legacy_strategy_labels = {
            "🎯 Chọn 1 mô hình": "Chọn 1 mô hình",
            "📊 So sánh nhiều mô hình": "So sánh nhiều mô hình",
            "🤝 Kết hợp nhiều mô hình": "Kết hợp nhiều mô hình",
        }
        saved_strategy = st.session_state.get(strategy_key)
        if saved_strategy in legacy_strategy_labels:
            st.session_state[strategy_key] = legacy_strategy_labels[saved_strategy]

        training_strategy = st.radio(
            "Chiến lược:",
            [
                "Chọn 1 mô hình",
                "So sánh nhiều mô hình",
                "Kết hợp nhiều mô hình",
            ],
            index=0,
            horizontal=True,
            key=strategy_key,
            label_visibility="collapsed",
        )
        
        # Select Models based on strategy
        is_single = training_strategy == "Chọn 1 mô hình"
        is_ensemble = training_strategy == "Kết hợp nhiều mô hình"
        
        st.caption(f"Chọn Thuật toán ({'Chọn ít nhất 2' if is_ensemble else 'Chọn 1' if is_single else 'Chọn nhiều để so sánh'}):")
        
        if is_single:
            _def_m = (
                "Random Forest Classifier"
                if problem_type == "Phân loại (Classification)"
                else "Random Forest Regressor"
            )
            _idx = (
                available_models.index(_def_m) if _def_m in available_models else 0
            )
            selected_single_model = st.selectbox(
                "Mô hình:",
                available_models,
                index=_idx,
                key=f"{key_prefix}_models_single",
                label_visibility="collapsed",
            )
            models_to_run = [selected_single_model]
            
        else:
            # For Compare or Ensemble, use multiselect
            default_models = available_models[:3] if len(available_models) >= 3 else available_models
            if is_ensemble and len(default_models) < 2 and len(available_models) >= 2:
                default_models = available_models[:2]
                
            models_to_run = st.multiselect(
                "Các mô hình:", 
                available_models, 
                default=default_models, 
                key=f'{key_prefix}_models_multi',
                label_visibility="collapsed"
            )
        
        if not models_to_run:
            st.warning("⚠️ Vui lòng chọn ít nhất một mô hình.")
            return None
            
        if is_ensemble and len(models_to_run) < 2:
            st.warning("⚠️ Chiến lược [Kết hợp mô hình] yêu cầu chọn ít nhất **2 mô hình**.")
            return None

        # Advanced Configuration
        st.markdown("**⚙️ Cấu hình nâng cao (tham số):**")
        
        split_mode = None
        test_size_val = 0.2
        cv_folds_val = 5
        balance_method = "none"
        fs_method = "none"
        k_features = len(selected_features)
        outlier_method = "none"
        scaler_type = "StandardScaler"

        with st.expander("Tùy chỉnh tham số huấn luyện (bấm để mở rộng)", expanded=False):
            col_split1, col_split2 = st.columns(2)
            with col_split1:
                # 1. Train/Test Split Config
                st.markdown("##### 1. Chia dữ liệu (huấn luyện/kiểm tra)")
                
                # Gợi ý tỷ lệ dựa trên chiến lược
                suggested_split = "🤖 Tự động (80/20) - Đề xuất cho kết hợp/so sánh" if (is_ensemble or not is_single) else "🤖 Tự động (70/30) - Đề xuất cho 1 mô hình"
                
                split_mode = st.radio(
                    "Chế độ chia:",
                    [suggested_split, "🛠️ Tự điều chỉnh"],
                    horizontal=True,
                    key=f"{key_prefix}_split_mode"
                )
                
                if split_mode == suggested_split:
                    test_size_val = 0.2 if (is_ensemble or not is_single) else 0.3
                    st.info(
                        f"Dùng **{int((1-test_size_val)*100)}%** dữ liệu để huấn luyện và kiểm tra chéo; "
                        f"giữ lại **{int(test_size_val*100)}%** để đánh giá kết quả cuối."
                    )
                else:
                    test_size_val = st.slider(
                        "Phần dữ liệu giữ lại để đánh giá:", 0.1, 0.5, 0.2, 0.05,
                        key=f"{key_prefix}_split_slider"
                    )
                    st.info(
                        f"Dùng **{100-int(test_size_val*100)}%** dữ liệu để huấn luyện và kiểm tra chéo; "
                        f"giữ lại **{int(test_size_val*100)}%** để đánh giá kết quả cuối."
                    )
                
                # Save to session state for persistence if needed
                st.session_state[f'{key_prefix}_test_size'] = test_size_val

            with col_split2:
                # 2. Cross-Validation Config
                st.markdown("##### 2. Kiểm định chéo")
                
                # Gợi ý CV dựa trên chiến lược
                cv_options = [3, 5, 7, 10]
                default_cv_index = 1  # Mặc định 5-fold để tăng ổn định và độ chính xác
                st.caption(
                    "Số lượt kiểm tra chéo: mỗi lượt dùng một phần dữ liệu khác nhau để kiểm tra mô hình. "
                    "Càng nhiều lượt thì đánh giá càng kỹ nhưng chạy càng lâu; **5 lượt** thường cân bằng."
                )
                st.markdown(
                    """
                    - **3 lượt:** nhanh hơn, phù hợp với máy yếu hoặc cần thử nhanh.
                    - **5 lượt:** cân bằng giữa tốc độ và độ tin cậy.
                    - **7 hoặc 10 lượt:** đánh giá kỹ hơn nhưng tốn nhiều thời gian hơn.
                    - Nếu dữ liệu của một nhóm quá ít, hệ thống tự điều chỉnh số lượt để tránh lỗi.
                    """
                )
                cv_folds_val = st.selectbox(
                    "Số lượt kiểm tra chéo:",
                    cv_options,
                    index=default_cv_index,
                    key=f"{key_prefix}_cv_folds",
                    help="Ví dụ 5 lượt nghĩa là hệ thống huấn luyện và kiểm tra luân phiên 5 lần.",
                )

                st.caption(
                    "📝 Giải thích các ký hiệu hay gặp lúc train: "
                    "`n_splits/cv` = số phần kiểm định chéo, `n_estimators` = số cây, "
                    "`n_neighbors` = số hàng xóm, `n_jobs=-1` = dùng toàn bộ CPU."
                )

                # 3. Balancing (Classification Only)
                if problem_type == "Phân loại (Classification)":
                    st.markdown("##### 3. Cân bằng dữ liệu")
                    balance_labels = {
                        "none": "none (Không cân bằng lớp)",
                        "smote": "SMOTE (Tạo thêm mẫu cho lớp ít dữ liệu)",
                        "borderline": "BorderlineSMOTE (Ưu tiên tạo mẫu vùng ranh giới)",
                        "adasyn": "ADASYN (Tạo mẫu thích nghi theo độ khó)",
                        "class_weight": "class_weight (Tăng trọng số lớp ít — không sinh mẫu giả)",
                    }
                    balance_method = st.selectbox(
                        "Phương pháp:",
                        ["none", "smote", "borderline", "adasyn", "class_weight"],
                        format_func=lambda x: balance_labels.get(x, x),
                        key=f"{key_prefix}_balance",
                        help=(
                            "Kỹ thuật xử lý mất cân bằng lớp (class imbalance). "
                            "Khi lớp thiểu số chỉ còn vài mẫu, các biến thể SMOTE nội suy giữa "
                            "chính vài mẫu đó nên mẫu sinh ra nằm gọn trên một đoạn thẳng và gần "
                            "như không thêm thông tin; class_weight phù hợp hơn vì chỉ tăng mức "
                            "phạt khi đoán sai lớp hiếm, mô hình vẫn chỉ học từ mẫu thật."
                        )
                    )
            
            st.markdown("---")
            # 4. Feature Selection Config
            col_fs1, col_fs2 = st.columns(2)
            with col_fs1:
                fs_labels = {
                    "none": "none (Không chọn lọc đặc trưng)",
                    "mi": "MI - Thông tin tương hỗ",
                    "pe": "PE - Tương quan Pearson (tuyến tính)",
                    "pbc": "PBC - Tương quan điểm-nhị phân",
                    "rfe": "RFE - Loại dần đặc trưng",
                    "pc": "PC - Đóng góp theo thành phần chính",
                    "sc": "SC - Tương quan Spearman (thứ hạng)",
                    "rf_imp": "RF - Độ quan trọng từ rừng ngẫu nhiên",
                }
                fs_method = st.selectbox(
                    "Phương pháp chọn đặc trưng:", 
                    ["none", "mi", "pe", "pbc", "rfe", "pc", "sc", "rf_imp"], 
                    format_func=lambda x: fs_labels.get(x, x),
                    key=f"{key_prefix}_fs"
                )
            with col_fs2:
                # Ensure input is within bounds
                max_k = len(selected_features)
                default_k = min(10, max_k)
                if default_k < 1: default_k = 1
                
                k_features = st.number_input(
                    "Số đặc trưng giữ lại (k):", 
                    1, max_k, default_k, 
                    key=f"{key_prefix}_k"
                )

            # 5. Preprocessing (Regression Only / Optional) for consistency
            if problem_type == "Hồi quy (Regression)":
                st.markdown("---")
                st.markdown("##### 5. Tiền xử lý")
                st.caption(
                    "**IQR** (Interquartile Range) = **khoảng tứ phân vị** (Q3 − Q1): "
                    "Q1 là mức **tứ phân vị 25%**, Q3 là mức **tứ phân vị 75%**. "
                    "Ngoại lai (Tukey): giá trị nằm ngoài [Q1 − 1.5×IQR, Q3 + 1.5×IQR] trên các cột số; "
                    "một dòng có ít nhất một cột vi phạm sẽ bị loại khi huấn luyện."
                )
                st.caption(
                    "ℹ️ **Hai chỗ xử lý outlier không trùng nhau:** ở tab *Khám phá* là để làm sạch/xem nhanh "
                    "(lưu `cleaned_df`). ở đây là bật/tắt **lọc IQR ngay trong bước huấn luyện** trên bộ feature/target đã chọn. "
                    "Huấn luyện dùng dữ liệu đang mở (`current_df`), không tự động lấy bản `cleaned_df` — tránh rò rỉ dữ liệu. "
                    "Chỉ cần bật **một** nơi nếu không muốn lọc hai lần (hoặc thay `current_df` bằng bản đã làm sạch rồi tắt IQR ở đây)."
                )
                col_pp1, col_pp2 = st.columns(2)
                with col_pp1:
                    outlier_check = st.checkbox(
                        "🧹 Loại bỏ ngoại lai theo IQR (khoảng tứ phân vị)",
                        value=False,
                        key=f"{key_prefix}_outlier",
                        help=(
                            "IQR = Q3 − Q1 (khoảng giữa hai mức tứ phân vị). "
                            "Loại các dòng có giá trị ngoài [Q1−1.5×IQR, Q3+1.5×IQR] trên bất kỳ cột số nào."
                        ),
                    )
                    outlier_method = "iqr" if outlier_check else "none"
                with col_pp2:
                    scaler_labels = {
                        "StandardScaler": "Chuẩn hóa chuẩn (StandardScaler: mean=0, std=1)",
                        "RobustScaler": "Chuẩn hóa bền vững (RobustScaler: ít nhạy với ngoại lai)",
                        "MinMaxScaler": "Chuẩn hóa min-max (MinMaxScaler: đưa về [0,1])",
                    }
                    scaler_type = st.selectbox(
                        "Phương pháp chuẩn hóa:", 
                        ["StandardScaler", "RobustScaler", "MinMaxScaler"], 
                        index=0,
                        format_func=lambda x: scaler_labels.get(x, x),
                        key=f"{key_prefix}_scaler"
                    )

    from dss.core.target_utils import detect_temporal_column
    time_col = detect_temporal_column(df)
    split_strategy = "temporal" if time_col else "random"

    return {
        "target_col": target_col,
        "selected_features": selected_features,
        "problem_type": problem_type,
        "training_strategy": training_strategy,
        "models_to_run": models_to_run,
        "test_size": test_size_val,
        "cv_folds": cv_folds_val,
        "balance_method": balance_method,
        "fs_method": fs_method,
        "k_features": k_features,
        "outlier_method": outlier_method,
        "scaler_type": scaler_type,
        "split_strategy": split_strategy,
        "time_col": time_col,
        "data_source_type": getattr(df, "attrs", {}).get("data_source_type", "synthetic"),
    }


def model_1_classification_tab(df, classification_trainer):
    pass


def render_shap_explanation(pipeline, input_df, background_data, feature_names, problem_type="classification"):
    """SHAP local explanation cho pipeline (classification/regression) — UI
    THUẦN TRÌNH BÀY: tính toán SHAP thật nằm ở `model_service.compute_shap_
    local_explanation` (tách theo yêu cầu refactor, không đổi kết quả)."""
    if not SHAP_AVAILABLE or shap is None:
        st.warning("Thư viện `shap` chưa được cài (pip install shap).")
        return
    if not st_shap:
        st.warning("Thư viện `streamlit-shap` chưa được cài đặt để hiển thị biểu đồ.")
        return

    st.write("⏳ Đang tính toán SHAP (có thể mất vài giây)...")
    shap_val, err = _compute_shap_local_explanation(
        pipeline, input_df, background_data, feature_names, problem_type
    )
    if shap_val is None:
        st.warning(err or "Không thể hiển thị giải thích SHAP cho mô hình này.")
        return

    st.markdown("##### Phân tích Tác động của các Đặc trưng (SHAP Waterfall Plot):")
    st.caption("Biểu đồ Waterfall giải thích tại sao mô hình lại đưa ra kết quả như vậy. "
               "Các thanh màu đỏ 🔴 làm tăng dự đoán, thanh màu xanh 🔵 làm giảm dự đoán so với giá trị cơ sở (E[f(x)]).")
    try:
        st_shap(shap.plots.waterfall(shap_val[0]), height=400)
    except Exception as e:
        ui_kit.report_error("Không thể hiển thị giải thích SHAP cho mô hình này", e, level="warning")


def render_shap_summary(pipeline, background_data, feature_names, problem_type="classification"):
    """SHAP global summary (feature importance) — UI THUẦN TRÌNH BÀY: tính
    toán thật nằm ở `model_service.compute_shap_summary`."""
    if not SHAP_AVAILABLE or shap is None:
        st.warning("Thư viện `shap` chưa được cài (pip install shap).")
        return
    if not st_shap:
        st.warning("Thư viện `streamlit-shap` chưa được cài đặt để hiển thị biểu đồ.")
        return

    st.write("⏳ Đang tính toán SHAP Summary (có thể mất vài phút tùy dữ liệu)...")
    shap_val, err = _compute_shap_summary(pipeline, background_data, feature_names, problem_type)
    if shap_val is None:
        st.warning(err or "Không thể hiển thị giải thích SHAP cho mô hình này.")
        return

    st.markdown("##### Biểu đồ SHAP Summary (Bee Swarm Plot)")
    st.caption("Biểu đồ này hiển thị Top các đặc trưng quan trọng nhất đối với toàn bộ tập dữ liệu. "
               "Mỗi điểm trên biểu đồ là một giá trị SHAP của một mẫu dữ liệu cho một feature nhất định.")
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 6))
        shap.plots.beeswarm(shap_val, show=False)
        st.pyplot(fig)
        plt.close(fig)
    except Exception as e:
        ui_kit.report_error("Không thể hiển thị giải thích SHAP cho mô hình này", e, level="warning")


def personal_prediction_tab(
    df, classification_trainer, regression_trainer, wh, train_config=None, role=None
):
    """Phiếu nhập tay; `train_config` từ khối cấu hình chung."""
    ui_kit.subsection_header(
        "Dự đoán — Nhập tay",
        subtitle=(
            "Điền thông tin học tập của bạn để xem dự đoán từ mô hình đang dùng cho lớp."
            if role == "Sinh viên"
            else "Nhập tay thông tin một sinh viên để xem dự đoán. Chỉ số đánh giá mô hình xem ở tab **Kết quả đánh giá mô hình**."
        ),
        icon="👤",
    )

    _personal_prediction_student_form(df, wh, train_config, role=role)


def _personal_prediction_student_form(df, wh, train_config=None, role=None):
    """Phiếu nhập tay (Streamlit form — một lần bấm gửi), dùng chung cho Sinh
    viên và tab "Phiếu thông tin — Sinh viên" của Giảng viên.

    Model dùng để dự đoán: `model_service.resolve_model_for_prediction` — bản
    Production trong Model Registry luôn được ưu tiên (Admin Promote/Rollback có
    hiệu lực NGAY). Sinh viên CHỈ dùng Production; Giảng viên được rơi về mô
    hình vừa train trong phiên khi target chưa có Production."""
    ui_kit.alert_box(
        "Điền <strong>từng mục</strong> đúng với tình trạng học tập của bạn, rồi bấm "
        "<strong>Gửi &amp; xem kết quả dự đoán</strong>. Kết quả chỉ suy ra từ mô hình đã huấn luyện — "
        "hệ thống <em>không</em> huấn luyện lại.",
        kind="info",
        title="Phiếu nhập thông tin",
    )

    config = _resolve_hub_train_config(train_config)
    dataset_id = st.session_state.get("current_dataset_id")
    target_col = config["target_col"] if config else None

    if not target_col:
        # Student Product Acceptance audit (2026-09): thông báo cũ luôn chỉ
        # Sinh viên "Vào tab Huấn luyện mô hình" — nhưng Sinh viên KHÔNG có
        # tab đó (main.py: tab_train_ml = None cho vai trò này) nên đây là
        # hướng dẫn dẫn tới một điểm không tồn tại, gây bế tắc thật sự.
        if role == "Sinh viên":
            st.info(
                "Chưa có mục tiêu dự đoán được cấu hình cho lớp của bạn. "
                "Vui lòng chờ Giảng viên thiết lập, hoặc liên hệ Giảng viên/Admin nếu việc này kéo dài."
            )
        else:
            st.info(
                "Chưa xác định được Target để dự đoán. Vào tab **Huấn luyện mô hình** để "
                "chọn Target/Features, hoặc chờ hệ thống tự động phát hiện sau khi có dữ liệu."
            )
        return

    resolved = _resolve_model_for_prediction(wh, dataset_id, target_col, role=role)
    if resolved["status"] == "empty":
        st.info(f"📭 {resolved['message']}")
        return
    if resolved["status"] == "error":
        st.error(f"❌ {resolved['message']}")
        return

    best_pipeline = resolved["pipeline"]
    trained_features = resolved["feature_cols"]
    hub_type = resolved["hub_type"]
    class_labels = resolved["class_labels"]

    st.markdown("---")
    if role == "Sinh viên":
        # Sinh viên không cần biết thuật ngữ kỹ thuật "Production"/"Model Registry"/
        # số phiên bản — chỉ cần biết đây là kết quả từ mô hình chính thức của hệ
        # thống (đúng yêu cầu thiết kế "minimal model info, no technical ML UI").
        st.caption("Phân tích bằng mô hình EduDSS hiện hành.")
    else:
        st.caption(_describe_prediction_model(resolved))
    if role == "Sinh viên":
        st.info(f"🎯 Mục tiêu dự đoán hiện tại: **{feature_label(target_col)}**.")
    else:
        st.info(
            f"🎯 Mục tiêu dự đoán hiện tại: **{feature_label(target_col)}**. "
            "Kết quả ở tab này dùng mô hình ghi ở dòng trên cho đúng cột mục tiêu này."
        )

    # E-6: form dự đoán trước đây LUÔN điền sẵn bằng trung bình lớp — sinh viên
    # bấm gửi mà không sửa gì sẽ vô tình nhận "dự đoán" cho MỘT SINH VIÊN TRUNG
    # BÌNH, không phải của chính họ. Nếu sinh viên đã đăng nhập có dòng dữ liệu
    # của CHÍNH họ trong dataset hiện tại, điền sẵn bằng dữ liệu đó thay vì
    # trung bình lớp, và ghi rõ nguồn điền sẵn cho từng trường hợp.
    _own_student_row = None
    if role == "Sinh viên":
        _own_student_id = st.session_state.get("current_student_id")
        _id_col_for_prefill = next((c for c in df.columns if "id" in str(c).lower()), None)
        if _own_student_id and _id_col_for_prefill:
            _own_match = df[df[_id_col_for_prefill].astype(str) == str(_own_student_id)]
            if not _own_match.empty:
                _own_student_row = _own_match.iloc[0]

    st.markdown("### Các mục trên phiếu")
    st.caption("Mỗi dòng là một thông tin cần nhập (số hoặc chọn trong danh sách).")

    predict_values: dict = {}
    with st.form("pers_manual_predict_form"):
        for idx, col_name in enumerate(trained_features, start=1):
            if col_name not in df.columns:
                st.warning(f"Mục `{feature_label(col_name)}` không còn trong dữ liệu — liên hệ giảng viên.")
                continue
            if pd.api.types.is_numeric_dtype(df[col_name]):
                _own_value = (
                    _own_student_row.get(col_name)
                    if _own_student_row is not None and col_name in _own_student_row.index
                    else None
                )
                if _own_value is not None and pd.notna(_own_value):
                    _m = float(_own_value)
                    _prefill_source = "dữ liệu của bạn"
                else:
                    try:
                        _m = float(df[col_name].mean())
                    except Exception:
                        _m = 0.0
                    _prefill_source = (
                        "giá trị trung bình lớp — CHƯA có dữ liệu của bạn, vui lòng sửa lại cho đúng"
                        if role == "Sinh viên"
                        else "giá trị trung bình lớp"
                    )
                try:
                    lo = float(df[col_name].min())
                    hi = float(df[col_name].max())
                    _help = (
                        f"Đang điền sẵn bằng {_prefill_source}. "
                        f"Trong dữ liệu mẫu thường nằm khoảng [{lo:g}, {hi:g}] (chỉ tham khảo)."
                    )
                except Exception:
                    _help = f"Đang điền sẵn bằng {_prefill_source}."
                predict_values[col_name] = st.number_input(
                    f"{idx}. {feature_label(col_name)}",
                    value=_m,
                    help=_help,
                    key=f"pers_predict_num_{col_name}",
                )
            else:
                _opts = df[col_name].dropna().unique().tolist()
                predict_values[col_name] = st.selectbox(
                    f"{idx}. {feature_label(col_name)}",
                    _opts,
                    key=f"pers_predict_sel_{col_name}",
                    help="Chọn một giá trị có trong dữ liệu đã dùng khi huấn luyện.",
                )
        submitted_predict = st.form_submit_button(
            "✉️ Gửi & xem kết quả dự đoán",
            type="primary",
            width="stretch",
        )

    if submitted_predict:
        _missing = [c for c in trained_features if c not in predict_values]
        if _missing:
            st.error(f"❌ Thiếu giá trị cho: {', '.join(_missing)}")
        else:
            confidence = None
            top_label = None
            try:
                input_df = pd.DataFrame([predict_values])
                prediction = predict_with_metrics(best_pipeline, input_df)[0]
            except Exception as e:
                ui_kit.report_error("❌ Lỗi khi dự đoán", e)
            else:
                label = None
                col_result1, col_result2 = st.columns([1, 1])
                with col_result1:
                    st.markdown("#### Kết quả cho phiếu của bạn")
                    if hub_type == "clf":
                        labels_map = _ensure_label_mapping(class_labels)
                        label = labels_map.get(prediction, str(prediction))
                        st.success(f"**Dự đoán: {label}**")

                        try:
                            proba = best_pipeline.predict_proba(input_df)[0]
                            proba_dict = {
                                labels_map.get(i, str(i)): proba[i]
                                for i in range(len(proba))
                            }
                            top_label, confidence = sorted(
                                proba_dict.items(),
                                key=lambda x: x[1],
                                reverse=True
                            )[0]
                            st.markdown("**Xác suất:**")
                            for lbl, prob in sorted(proba_dict.items(), key=lambda x: x[1], reverse=True):
                                st.write(f"- {lbl}: {prob*100:.2f}%")
                        except Exception:
                            pass
                    else:
                        st.success(f"**Dự đoán: {prediction:.2f}**")

                with col_result2:
                    st.markdown("#### Bạn đã nhập")
                    input_display = pd.DataFrame({
                        "Mục": list(predict_values.keys()),
                        "Giá trị": list(predict_values.values()),
                    })
                    st.dataframe(input_display, width="stretch", hide_index=True)

                    if wh:
                        st.markdown("#### Lưu phiếu (tùy chọn)")
                        save_data = predict_values.copy()
                        save_data["prediction_result"] = prediction
                        if hub_type == "clf" and label is not None:
                            save_data["prediction_label"] = label
                        df_save = pd.DataFrame([save_data])
                        render_save_export_buttons(
                            df_save,
                            "personal_prediction",
                            wh,
                            "pers_pred_single",
                            data_type="prediction",
                        )

                st.markdown("---")
                st.markdown("#### Kết luận & gợi ý cho sinh viên")
                if hub_type == "clf":
                    final_label = label if label is not None else str(prediction)
                    if confidence is None:
                        st.success(
                            f"Kết luận: Bạn được dự đoán thuộc nhóm **{final_label}** cho mục tiêu **{feature_label(target_col)}**."
                        )
                        st.caption("Mô hình này không trả về xác suất nên chưa đánh giá được mức độ chắc chắn.")
                    else:
                        # P-7: predict_proba() là XÁC SUẤT THEO MÔ HÌNH, CHƯA HIỆU CHUẨN
                        # (chưa qua CalibratedClassifierCV) — không phải "độ tin cậy" đã kiểm
                        # định, tránh gây hiểu nhầm số này phản ánh đúng xác suất thật.
                        st.success(
                            f"Kết luận: Bạn được dự đoán thuộc nhóm **{final_label}** "
                            f"(xác suất theo mô hình: **{confidence*100:.1f}%**)."
                        )
                        st.caption("⚠️ Đây là xác suất mô hình tự ước lượng, CHƯA HIỆU CHUẨN — không nên coi là % chắc chắn tuyệt đối.")
                        # C1.1: điểm CHƯA hiệu chuẩn không được diễn giải thành "độ tin cậy"
                        # (≥0.8 ≠ "khá ổn định"). Chỉ nêu thứ hạng tương đối giữa các lớp.
                        st.info(
                            "Con số này chỉ cho biết mô hình nghiêng về nhóm nào hơn so với các nhóm khác; "
                            "không phải xác suất thực tế đã kiểm chứng. Luôn kết hợp với đánh giá của giảng viên/cố vấn học tập."
                        )
                else:
                    st.success(
                        f"Kết luận: Giá trị dự đoán cho **{feature_label(target_col)}** là **{float(prediction):.2f}**."
                    )
                    st.info(
                        "Đây là giá trị ước lượng từ dữ liệu hiện tại. "
                        "Nên xem như công cụ hỗ trợ ra quyết định, không thay thế đánh giá học vụ chính thức."
                    )

                with st.expander("Giải thích mô hình (nâng cao — SHAP)", expanded=False):
                    # Dùng mẫu từ chính dataset hiện tại làm nền cho SHAP — KHÔNG
                    # dùng `hub_X_train` của phiên (có thể thuộc 1 lượt train khác,
                    # feature set khác với bản Production vừa resolve ở trên).
                    background_data = df[trained_features].dropna().head(100)
                    render_shap_explanation(
                        pipeline=best_pipeline,
                        input_df=input_df,
                        background_data=background_data,
                        feature_names=trained_features,
                        problem_type="classification" if hub_type == "clf" else "regression",
                    )


def file_prediction_tab(
    df, classification_trainer, regression_trainer, wh, train_config=None,
    role=None, current_student_id=None,
):
    """Dự đoán cho 1 dòng dữ liệu đã có sẵn trong dataset — dùng mô hình
    Production hiện tại trong Model Registry. LƯU Ý (audit 2026-09): tab này
    KHÔNG có file uploader nào — tên "Từ file" gây hiểu lầm. Xem
    _render_prediction_source_header()/tiêu đề tab tương ứng ở main.py."""
    ui_kit.subsection_header(
        "Dự đoán — Dữ liệu đã có",
        subtitle="Chọn một dòng có sẵn trong dữ liệu lớp để áp dụng mô hình hiện hành.",
        icon="🗂️",
    )
    # Student Product Acceptance audit (2026-09): 2 thông báo bên dưới TRƯỚC
    # ĐÂY luôn chỉ tới tab "Huấn luyện mô hình"/"Kho dữ liệu" — cả 2 tab này
    # KHÔNG tồn tại với Sinh viên (main.py: tab_train_ml = None, và Sinh viên
    # không có mục "Kho dữ liệu" trong sidebar), khiến Sinh viên bị dẫn tới
    # một hướng dẫn bế tắc không thể thực hiện được.
    if role == "Sinh viên":
        st.info("ℹ️ Kết quả dự đoán dùng mô hình chính thức hiện tại của lớp bạn — không cần thao tác huấn luyện gì thêm.")
    else:
        st.info(
            "⬅️ **Huấn luyện** thực hiện ở tab **Huấn luyện mô hình** (không train lại ở đây)."
        )
    config = _resolve_hub_train_config(train_config)
    dataset_id = st.session_state.get("current_dataset_id")
    target_col = config["target_col"] if config else None
    if not target_col:
        if role == "Sinh viên":
            st.warning("⚠️ Chưa có mục tiêu dự đoán được cấu hình cho lớp của bạn. Vui lòng chờ Giảng viên thiết lập.")
        else:
            st.warning(
                "⚠️ Hoàn tất **Target & Features** trong tab **Huấn luyện mô hình**, hoặc nạp model từ **Kho dữ liệu**."
            )
        return
    # Production trong Model Registry được ưu tiên; Giảng viên rơi về mô hình
    # vừa train khi chưa có Production (xem resolve_model_for_prediction).
    # So sánh chỉ số các mô hình nằm ở tab "Kết quả đánh giá mô hình".
    resolved = _resolve_model_for_prediction(wh, dataset_id, target_col, role=role)

    st.markdown("---")
    if resolved["status"] == "empty":
        st.info(f"📭 {resolved['message']}")
    elif resolved["status"] == "error":
        st.error(f"❌ {resolved['message']}")
    else:
        pipeline = resolved["pipeline"]
        feature_cols = resolved["feature_cols"]
        hub_type_prod = resolved["hub_type"]
        class_labels_prod = resolved["class_labels"]
        st.caption(
            "Phân tích bằng mô hình EduDSS hiện hành." if role == "Sinh viên"
            else _describe_prediction_model(resolved)
        )
        st.markdown("#### Chọn Sinh viên để Dự đoán")

        # Tìm cột ID
        id_col = next((c for c in df.columns if 'id' in c.lower()), df.columns[0])
        student_ids = df[id_col].unique()

        if role == "Sinh viên":
            # Sinh viên chỉ được xem dự đoán của chính mình — không hiện danh
            # sách để chọn sang mã số khác.
            selected_id = current_student_id
            st.info(f"👤 Đang xem dự đoán của bạn: **{selected_id}**")
        else:
            col_sel, col_info = st.columns([2, 1])
            with col_sel:
                selected_id = st.selectbox(
                    "Chọn ID Sinh viên:",
                    student_ids,
                    key='file_student_sel',
                    help="Chọn một sinh viên từ danh sách để xem dự đoán"
                )

            with col_info:
                student_count = len(student_ids)
                st.metric("Tổng số sinh viên", student_count)

        if st.button("🔮 Dự đoán cho Sinh viên này", key="file_pred_btn", type="primary", width="stretch"):
            student_row = df[df[id_col] == selected_id]
            missing_feats = [c for c in feature_cols if c not in student_row.columns]
            if missing_feats:
                st.error(f"❌ Dataset hiện tại thiếu cột mà mô hình cần: {', '.join(missing_feats)}")
            elif not student_row.empty:
                input_data = student_row[feature_cols]
                pred = predict_with_metrics(pipeline, input_data)[0]

                col_result1, col_result2 = st.columns([1, 1])
                with col_result1:
                    st.markdown("#### Kết quả Dự đoán:")
                    if hub_type_prod == "clf":
                        labels_map = _ensure_label_mapping(class_labels_prod)
                        lbl = labels_map.get(pred, str(pred))
                        st.success(f"**Dự đoán: {lbl}**")

                        # Hiển thị xác suất nếu có
                        try:
                            proba = pipeline.predict_proba(input_data)[0]
                            proba_dict = {
                                labels_map.get(i, str(i)): proba[i]
                                for i in range(len(proba))
                            }
                            st.markdown("**Xác suất:**")
                            for lbl, prob in sorted(proba_dict.items(), key=lambda x: x[1], reverse=True):
                                st.write(f"- {lbl}: {prob*100:.2f}%")
                        except Exception:
                            pass
                    else:
                        st.success(f"**Dự đoán: {pred:.2f}**")

                    # So sánh với thực tế nếu có
                    if target_col in student_row.columns:
                        actual = student_row[target_col].values[0]
                        if hub_type_prod == "clf":
                            st.info(f"**Giá trị thực tế:** {actual}")
                        else:
                            error = abs(float(actual) - float(pred))
                            st.info(f"**Giá trị thực tế:** {actual} | **Sai số:** {error:.2f}")

                with col_result2:
                    st.markdown("#### Thông tin Sinh viên:")
                    input_display = pd.DataFrame({
                        'Thuộc tính': list(input_data.columns),
                        'Giá trị': [input_data[col].values[0] for col in input_data.columns]
                    })
                    st.dataframe(input_display, width="stretch", hide_index=True)


def batch_prediction_tab(
    df, classification_trainer, regression_trainer, wh, train_config=None
):
    """Dự đoán hàng loạt (chỉ Giảng viên/Admin) — xem resolve_model_for_prediction."""
    ui_kit.subsection_header(
        "Dự đoán — Hàng loạt",
        subtitle="Áp dụng mô hình hiện hành cho toàn bộ danh sách.",
        icon="📊",
    )
    st.info(
        "⬅️ **Huấn luyện** ở tab **Huấn luyện mô hình**. Ở đây chỉ chạy dự đoán hàng loạt trên dataset hiện tại."
    )
    config = _resolve_hub_train_config(train_config)
    dataset_id = st.session_state.get("current_dataset_id")
    target_col = config["target_col"] if config else None
    if not target_col:
        st.warning(
            "⚠️ Hoàn tất **Target & Features** trong tab **Huấn luyện mô hình**, hoặc nạp model từ **Kho dữ liệu**."
        )
        return
    # Tab này chỉ hiện với Giảng viên/Admin (main.py ẩn với Sinh viên).
    resolved = _resolve_model_for_prediction(wh, dataset_id, target_col, role="Giảng viên")

    st.markdown("---")
    if resolved["status"] == "empty":
        st.info(f"📭 {resolved['message']}")
    elif resolved["status"] == "error":
        st.error(f"❌ {resolved['message']}")
    else:
        pipeline = resolved["pipeline"]
        feature_cols = resolved["feature_cols"]
        hub_type_prod = resolved["hub_type"]
        class_labels_prod = resolved["class_labels"]
        model_name_prod = resolved["model_name"]
        st.markdown("#### Dự đoán Toàn bộ File")
        st.caption(_describe_prediction_model(resolved))

        missing_feats = [c for c in feature_cols if c not in df.columns]
        if missing_feats:
            st.error(f"❌ Dataset hiện tại thiếu cột mà mô hình cần: {', '.join(missing_feats)}")
        else:
            col_info, col_btn = st.columns([2, 1])
            with col_info:
                st.info(f"📊 Sẽ dự đoán cho **{len(df)}** sinh viên trong file bằng mô hình **{model_name_prod}**")
            with col_btn:
                if st.button("🔮 Chạy Dự đoán cho toàn bộ Dataset", key="batch_run_pred", type="primary", width="stretch"):
                    with st.spinner("⏳ Đang dự đoán..."):
                        full_data = df[feature_cols]
                        all_preds = predict_with_metrics(pipeline, full_data)

                        df_result = df.copy()
                        if hub_type_prod == "clf":
                            labels_map = _ensure_label_mapping(class_labels_prod)
                            pred_labels = [labels_map.get(p, str(p)) for p in all_preds]
                            df_result[f"Predicted_{target_col}"] = pred_labels
                        else:
                            df_result[f"Predicted_{target_col}"] = all_preds

                        st.session_state.batch_final_df = df_result
                        st.session_state.batch_pred_target_col = target_col

                        # Ghi log activity
                        wh.log_activity(
                            "Dự đoán",
                            f"Dự đoán hàng loạt cho {len(df)} bản ghi bằng mô hình {model_name_prod}",
                        )

                        st.success("✅ Dự đoán hoàn tất!")

            if 'batch_final_df' in st.session_state:
                st.markdown("#### Kết quả Dự đoán")
                st.dataframe(st.session_state.batch_final_df, width="stretch", height=400)

                _bdf = st.session_state.batch_final_df
                _saved_tgt = st.session_state.get("batch_pred_target_col", target_col)
                pred_col = _resolve_predicted_output_col(_bdf, _saved_tgt) or _resolve_predicted_output_col(_bdf, target_col)
                if pred_col is None:
                    st.warning(
                        "Không tìm thấy cột dự đoán (Predicted_…). "
                        "Có thể dữ liệu trong session là từ lần chạy cũ — hãy bấm **Chạy Dự đoán cho toàn bộ Dataset** lại."
                    )

                col_stat1, col_stat2 = st.columns(2)
                with col_stat1:
                    st.metric("Tổng số bản ghi", len(_bdf))
                with col_stat2:
                    if pred_col is not None:
                        if hub_type_prod == "clf":
                            unique_preds = _bdf[pred_col].nunique()
                            st.metric("Số lớp dự đoán", unique_preds)
                        else:
                            avg_pred = pd.to_numeric(_bdf[pred_col], errors="coerce").mean()
                            st.metric("Giá trị trung bình", f"{avg_pred:.2f}" if pd.notna(avg_pred) else "—")
                    else:
                        st.metric("Thống kê dự đoán", "—")

                st.markdown("---")
                st.markdown("#### Lưu & Xuất Kết quả")
                render_save_export_buttons(_bdf, "batch_prediction", wh, "batch_pred", data_type="training")

                # --- SHAP EXPLANATION (GLOBAL) ---
                st.markdown("---")
                # Mẫu nền lấy từ chính dataset hiện tại (khớp đúng feature_cols của
                # bản Production vừa resolve), KHÔNG dùng `hub_X_train` của phiên.
                background_data = df[feature_cols].dropna().head(500)
                if len(background_data) > 300:
                    background_data = background_data.sample(300, random_state=42)

                st.markdown("#### Giải thích mô hình toàn cục (Global Explainability - SHAP)")
                render_chart_guide("shap_summary")
                render_chart_guide_advanced("shap_summary")
                st.caption("Biểu đồ SHAP Summary (hoặc Beeswarm) cho thấy mức độ quan trọng tổng thể của các đặc trưng (features) đối với toàn bộ dữ liệu mẫu. Tính toán này có thể mất chút thời gian.")
                if st.button("📊 Xem Phân tích Tầm quan trọng (SHAP Summary)", key="shap_summary_btn"):
                    render_shap_summary(
                        pipeline=pipeline,
                        background_data=background_data,
                        feature_names=feature_cols,
                        problem_type="classification" if hub_type_prod == "clf" else "regression"
                    )


def model_2_regression_tab(df, regression_trainer):
    """Placeholder tab hoi quy (logic o file_prediction / batch / personal)."""
    pass
