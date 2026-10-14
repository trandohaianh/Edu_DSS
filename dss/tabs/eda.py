import hashlib
from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

from dss.config import OPENPYXL_AVAILABLE, XLSXWRITER_AVAILABLE
from dss.core.data_helpers import feature_label
from dss.core.feature_utils import fill_missing_values
from dss.core.feature_utils import render_feature_analysis, to_excel
from dss.core.feature_utils import render_feature_method_explanation, render_save_export_buttons
from dss.core.trainers import DataPreprocessor
from dss.core.utils import st_step_header
from dss.core.warehouse import DataWarehouse
from dss.security.upload_security import UploadValidationError, parse_tabular_upload
from dss.services import model_service
from dss.tabs import ui_kit


def data_analysis_tab(df):
    """Tab phan tich du lieu tu dong."""
    st.header("🔬 Phân tích Dữ liệu Tự động")
    st.markdown("Hệ thống sẽ tự động phân tích các cột trong dữ liệu của bạn để xác định loại dữ liệu, giá trị thiếu, và các thông tin thống kê cơ bản.")

    # Khởi tạo DataPreprocessor nếu chưa có
    if 'data_preprocessor' not in st.session_state:
        st.session_state.data_preprocessor = DataPreprocessor()

    preprocessor = st.session_state.data_preprocessor

    # Cho phép xem trước dữ liệu thô
    with st.expander("Xem trước 5 dòng dữ liệu đầu tiên"):
        st.dataframe(df.head())

    if st.button("🚀 Bắt đầu Phân tích Dữ liệu", type="primary"):
        with st.spinner("Đang phân tích..."):
            feature_metadata = preprocessor.analyze_dataframe(df)
            st.session_state.feature_metadata = feature_metadata
            st.success("✅ Phân tích hoàn tất!")

    # Hiển thị kết quả phân tích chi tiết cho từng cột nếu đã chạy
    if 'feature_metadata' in st.session_state:
        st.markdown("---")
        st.subheader("Kết quả Phân tích Chi tiết")
        metadata = st.session_state.feature_metadata

        for col_name, meta in metadata.items():
            with st.expander(f"**{col_name}** - `{meta.get('type', 'N/A').upper()}`"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(
                        f"- **Kiểu dữ liệu:** `{meta.get('type', 'N/A')}`")
                    st.markdown(
                        f"- **Số giá trị duy nhất:** `{meta.get('unique', 'N/A')}`")
                with col_b:
                    st.markdown(
                        f"- **Số giá trị thiếu:** `{meta.get('missing', 'N/A')}`")

                if meta.get('type') == 'numeric':
                    st.markdown("**Thống kê:**")

                    def _fmt_stat(v):
                        if v is None:
                            return "NA"
                        try:
                            return f"{float(v):.2f}"
                        except (TypeError, ValueError):
                            return str(v)

                    _min_s = _fmt_stat(meta.get('min'))
                    _max_s = _fmt_stat(meta.get('max'))
                    _mean_s = _fmt_stat(meta.get('mean'))
                    _std_s = _fmt_stat(meta.get('std'))
                    st.markdown(
                        f"Min: `{_min_s}` | Max: `{_max_s}` | Mean: `{_mean_s}` | Std: `{_std_s}`"
                    )
                    # Biểu đồ phân phối
                    try:
                        fig_hist = px.histogram(
                            df, x=col_name, nbins=30, title=f"Phân phối {col_name}")
                        fig_hist.update_layout(
                            template='plotly_white', height=300)
                        st.plotly_chart(
                            fig_hist,
                            width="stretch",
                            key=f"analysis_hist_{col_name}")
                    except Exception:
                        pass
                elif meta.get('type') == 'categorical':
                    st.markdown("**Các giá trị phổ biến:**")
                    st.json(meta.get('values', []))
                    # Biểu đồ tần suất
                    try:
                        freq = df[col_name].value_counts().reset_index()
                        freq.columns = [col_name, 'count']
                        fig_bar = px.bar(
                            freq, x=col_name, y='count', title=f"Tần suất {col_name}")
                        fig_bar.update_layout(
                            template='plotly_white', height=300)
                        st.plotly_chart(
                            fig_bar,
                            width="stretch",
                            key=f"analysis_bar_{col_name}")
                    except Exception:
                        pass
        # Phân tích tổng hợp nâng cao
        st.markdown("---")
        st.subheader("Phân tích Nâng cao")
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols:
            # Vẽ ma trận tương quan (heatmap) để xem mối quan hệ giữa các cột số
            try:
                corr = df[num_cols].corr(numeric_only=True)
                fig_corr = px.imshow(
                    corr,
                    text_auto=False,
                    color_continuous_scale='RdBu_r',
                    origin='lower',
                    title="Ma trận Tương quan (Numeric Features)")
                fig_corr.update_layout(height=500, template='plotly_white')
                st.plotly_chart(
                    fig_corr,
                    width="stretch",
                    key="analysis_corr_heatmap")
            except Exception:
                pass # Bỏ qua nếu có lỗi
            # Thiếu dữ liệu
            try:
                miss_ratio = df.isna().mean().sort_values(ascending=False)
                st.markdown("**Tỉ lệ thiếu dữ liệu theo cột:**")
                st.dataframe(miss_ratio.to_frame("missing_ratio").style.format(
                    {'missing_ratio': '{:.1%}'}), width="stretch", height=320)
                # Heatmap thiếu dữ liệu (giới hạn kích thước)
                if df.shape[0] <= 2000 and df.shape[1] <= 100:
                    miss_matrix = df.isna().astype(int).values
                    fig_miss = px.imshow(
                        miss_matrix, aspect='auto', color_continuous_scale=[
                            '#ffffff', '#d32f2f'], title="Bản đồ Thiếu dữ liệu (1=Thiếu, 0=Đủ)")
                    fig_miss.update_layout(
                        height=320,
                        template='plotly_white',
                        coloraxis_showscale=False)
                    st.plotly_chart(
                        fig_miss,
                        width="stretch",
                        key="missing_dist_heatmap")
            except Exception:
                pass
            # Phân tích tương quan giữa các feature và cột target (nếu phát hiện được)
            try:
                # Ưu tiên metadata đánh dấu target
                target_candidates = [c for c, m in metadata.items() if m.get(
                    'is_target_reg') or m.get('is_target_clf')]
                if not target_candidates:
                    for c in df.columns:
                        if any(k in c.lower()
                               for k in ['final_score', 'gpa', 'grade']):
                            target_candidates.append(c)
                if target_candidates:
                    target_col = target_candidates[0]
                    st.markdown(f"**Liên hệ với Target:** `{target_col}`")
                    if target_col in df.columns and pd.api.types.is_numeric_dtype(
                            df[target_col]):
                        corr_target = df[num_cols + [target_col]].corr(numeric_only=True)[target_col].drop(
                            target_col).sort_values(key=lambda s: s.abs(), ascending=False).head(15)
                        st.dataframe(
                            corr_target.to_frame("corr_with_target").round(3),
                            width="stretch",
                            height=360)
                    elif target_col in df.columns:
                        agg = df.groupby(target_col)[num_cols].mean().round(2)
                        st.dataframe(agg, width="stretch", height=360)
            except Exception:
                pass
    else:
        st.info("Nhấn nút 'Bắt đầu Phân tích Dữ liệu' để xem chi tiết về các cột.")


def scatter_with_optional_ols(df=None, x=None, y=None, **px_kwargs):
    """Create a scatter plot with OLS trendline if statsmodels is available.
    Falls back to adding a numpy linear fit line if statsmodels is not installed.
    Accepts either (df, x=str, y=str) or (x=array/Series, y=array/Series).
    """
    try:
        if df is not None and isinstance(x, str) and isinstance(y, str):
            fig = px.scatter(df, x=x, y=y, trendline="ols", **px_kwargs)
        else:
            fig = px.scatter(x=x, y=y, trendline="ols", **px_kwargs)
        return fig
    except Exception as e:
        # Fallback when statsmodels isn't available or import fails inside plotly trendline
        if not (isinstance(e, (ImportError, ModuleNotFoundError)) or 'statsmodels' in str(e).lower()):
            # Not related to statsmodels — re-raise
            raise
        # Otherwise, fall back to simple linear fit using numpy
        if df is not None and isinstance(x, str) and isinstance(y, str):
            fig = px.scatter(df, x=x, y=y, **px_kwargs)
            x_vals = pd.to_numeric(df[x], errors='coerce').dropna()
            y_vals = pd.to_numeric(df[y], errors='coerce').loc[x_vals.index]
        else:
            # Handle array-like inputs - FIX: Align by position (reset index)
            x_series = pd.Series(x).reset_index(drop=True)
            y_series = pd.Series(y).reset_index(drop=True)
            
            # Coerce to numeric
            x_vals = pd.to_numeric(x_series, errors='coerce')
            y_vals = pd.to_numeric(y_series, errors='coerce')
            
            # Filter NaNs jointly
            mask = x_vals.notna() & y_vals.notna()
            x_vals = x_vals[mask]
            y_vals = y_vals[mask]
            
            fig = px.scatter(x=x_vals, y=y_vals, **px_kwargs)
        try:
            if len(x_vals) >= 2:
                coef = np.polyfit(x_vals, y_vals, 1)
                xs = np.linspace(x_vals.min(), x_vals.max(), 100)
                ys = np.polyval(coef, xs)
                fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='red', dash='dash'), name='Trendline (Linear)'))
        except Exception:
            pass
        # Show small note about missing dependency
        fig.update_layout(annotations=[dict(text='(No statsmodels installed — using linear fit)', xref='paper', yref='paper', x=0.01, y=0.99, showarrow=False, font=dict(size=10, color='gray'))])
        return fig


def data_exploration_tab(df, wh=None):
    """Tab khám phá và xử lý dữ liệu."""
    ui_kit.section_header(
        "Khám phá — Xử lý dữ liệu",
        subtitle="Quy trình: phát hiện → xử lý → so sánh → chọn features.",
        icon="🔍",
    )
    with st.expander("Từ điển nhanh thuật ngữ (Anh -> Việt)", expanded=False):
        st.markdown(
            "- `drop_duplicates` (**xóa dòng trùng lặp**)\n"
            "- `fillna` (**điền giá trị thiếu**)\n"
            "- `KNNImputer` (**điền thiếu theo K mẫu gần nhất**)\n"
            "- `outlier` (**giá trị ngoại lai**)\n"
            "- `IQR` (**khoảng tứ phân vị, dùng phát hiện outlier**)\n"
            "- `feature` (**biến đầu vào**) và `target` (**biến mục tiêu**)"
        )

    # ========================================================================
    # TỔNG QUAN DỮ LIỆU — KPI + 3 cột (nguồn / xem trước / chất lượng), theo
    # đúng bố cục mockup thay vì bảng cảnh báo màu xếp dọc như trước.
    # ========================================================================
    dup_count = int(df.duplicated().sum())
    miss_total = int(df.isnull().sum().sum())
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()

    ui_kit.kpi_row(
        [
            ("Số dòng", f"{len(df):,}"),
            ("Số cột", len(df.columns)),
            ("Giá trị thiếu", miss_total),
            ("Dòng trùng lặp", dup_count),
        ]
    )
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    col_source, col_preview, col_quality = st.columns([1, 1.6, 1], gap="medium")

    with col_source:
        with st.container(border=True):
            st.markdown("##### Nguồn dữ liệu")
            st.caption(f"Đang dùng: `{st.session_state.get('current_dataset_id', '—')}`")
            st.caption("Tải dữ liệu khác hoặc đồng bộ LMS ở tab **Kho dữ liệu**.")
            st.markdown("---")
            st.markdown("**Kiểu dữ liệu**")
            st.write(f"🔢 Cột số: {len(numeric_cols)}")
            st.write(f"🔤 Cột phân loại: {len(categorical_cols)}")

    with col_preview:
        with st.container(border=True):
            st.markdown("##### Xem trước dữ liệu")
            num_rows = st.selectbox(
                "Số dòng hiển thị:",
                [10, 20, 50, 100, "Tất cả"],
                index=0,
                key="sample_rows_select",
                label_visibility="collapsed",
            )
            display_df = df if num_rows == "Tất cả" else df.head(num_rows)
            st.dataframe(display_df, width="stretch", height=320)
            st.caption(f"Hiển thị {len(display_df)}/{len(df)} dòng.")

    with col_quality:
        with st.container(border=True):
            st.markdown("##### Chất lượng dữ liệu")
            missing_stats = df.isnull().sum()
            missing_cols = missing_stats[missing_stats > 0].sort_values(ascending=False)
            if len(missing_cols) > 0:
                missing_df = pd.DataFrame({
                    'Cột': missing_cols.index,
                    'Thiếu': missing_cols.values,
                    '%': (missing_cols.values / len(df) * 100).round(1),
                })
                st.dataframe(missing_df, width="stretch", hide_index=True, height=200)
            else:
                ui_kit.empty_state("Không có giá trị thiếu.", icon="✅")
            if dup_count > 0:
                st.warning(f"🔄 {dup_count} dòng trùng lặp.")
            else:
                st.success("✓ Không có dòng trùng lặp.")

    st.markdown("---")

    # ========================================================================
    # PHẦN 2: XỬ LÝ DỮ LIỆU (MỘT NÚT)
    # ========================================================================
    st_step_header("Bước 2: Xử lý dữ liệu")
    st.markdown("*Chọn các bước cần làm, rồi nhấn nút xử lý một lần duy nhất:*")

    _opt_outlier_iqr = "Xử lý outlier (IQR — khoảng tứ phân vị)"
    col_left, col_right = st.columns([2, 1], vertical_alignment="bottom")
    with col_left:
        process_options = st.multiselect(
            "Chọn bước xử lý:",
            ["Loại bỏ trùng lặp", "Xử lý giá trị thiếu", _opt_outlier_iqr],
            default=["Loại bỏ trùng lặp", "Xử lý giá trị thiếu"],
            key="data_process_options",
            help=(
                "IQR (Interquartile Range) = khoảng tứ phân vị (Q3 − Q1): "
                "Q1 là mức tứ phân vị 25%, Q3 là mức tứ phân vị 75%. "
                "Ngoại lai theo Tukey: nằm ngoài [Q1 − 1.5×IQR, Q3 + 1.5×IQR]."
            ),
        )
    
    with col_right:
        run_processing = st.button("🚀 Xử lý", type="primary", width="stretch")

    if run_processing:
        df_processed = df.copy()
        log_list = []
        changes_summary = []  # Lưu chi tiết thay đổi
        def _safe_pct(part, whole):
            if whole == 0:
                return 0.0
            return (part / whole) * 100

        with st.spinner("⏳ Đang xử lý dữ liệu..."):
            # Loại bỏ trùng lặp
            if "Loại bỏ trùng lặp" in process_options:
                before = len(df_processed)
                duplicate_before = int(df_processed.duplicated().sum())
                df_processed = df_processed.drop_duplicates().reset_index(drop=True)
                removed = before - len(df_processed)
                log_list.append(f"✓ Loại bỏ {removed} dòng trùng")
                changes_summary.append({
                    'Bước': 'Loại bỏ trùng lặp',
                    'Trước': f"{before:,} dòng",
                    'Sau': f"{len(df_processed):,} dòng",
                    'Thay đổi': f"-{removed:,} dòng ({_safe_pct(removed, before):.1f}%)",
                    'Mô tả': (
                        f"Phát hiện {duplicate_before:,} dòng trùng lặp hoàn toàn trên toàn bộ cột. "
                        f"Đã loại bỏ {removed:,} dòng bằng `drop_duplicates()`, còn lại {len(df_processed):,} dòng."
                    ),
                    'Chi tiết': [
                        "Mục tiêu: Loại bỏ các bản ghi giống hệt nhau để tránh thiên lệch thống kê và huấn luyện.",
                        "Phạm vi áp dụng: So sánh toàn bộ cột của từng dòng.",
                        "Kỹ thuật: Dùng `drop_duplicates()` để giữ lại bản ghi xuất hiện đầu tiên.",
                        f"Kết quả: {duplicate_before:,} dòng trùng phát hiện, {removed:,} dòng đã loại bỏ, còn {len(df_processed):,} dòng."
                    ]
                })

            # Xử lý giá trị thiếu
            if "Xử lý giá trị thiếu" in process_options:
                missing_by_col_before = df_processed.isnull().sum()
                missing_before = df_processed.isnull().sum().sum()
                numeric_cols_missing = df_processed.select_dtypes(include=[np.number]).columns.tolist()
                categorical_cols_missing = df_processed.select_dtypes(include=['object', 'category']).columns.tolist()
                num_missing_before = int(df_processed[numeric_cols_missing].isnull().sum().sum()) if numeric_cols_missing else 0
                cat_missing_before = int(df_processed[categorical_cols_missing].isnull().sum().sum()) if categorical_cols_missing else 0
                df_processed = fill_missing_values(df_processed)
                missing_after = df_processed.isnull().sum().sum()
                missing_by_col_after = df_processed.isnull().sum()
                impacted_cols = [c for c in df_processed.columns if int(missing_by_col_before.get(c, 0)) > int(missing_by_col_after.get(c, 0))]
                num_missing_after = int(df_processed[numeric_cols_missing].isnull().sum().sum()) if numeric_cols_missing else 0
                cat_missing_after = int(df_processed[categorical_cols_missing].isnull().sum().sum()) if categorical_cols_missing else 0
                log_list.append("✓ Xử lý giá trị thiếu (KNN cho số + mode cho phân loại)")
                changes_summary.append({
                    'Bước': 'Xử lý giá trị thiếu',
                    'Trước': f"{missing_before:,} giá trị thiếu",
                    'Sau': f"{missing_after:,} giá trị thiếu",
                    'Thay đổi': f"-{missing_before-missing_after:,} giá trị",
                    'Mô tả': (
                        f"Đã điền {missing_before-missing_after:,} giá trị thiếu. "
                        f"Cột số ({len(numeric_cols_missing)} cột): điền bằng KNNImputer dựa trên các mẫu tương tự "
                        f"({num_missing_before:,} → {num_missing_after:,}). "
                        f"Cột phân loại ({len(categorical_cols_missing)} cột): điền theo mode/giá trị xuất hiện nhiều nhất "
                        f"({cat_missing_before:,} → {cat_missing_after:,}). "
                        f"Số cột bị thiếu được xử lý: {len(impacted_cols)}."
                    ),
                    'Chi tiết': [
                        "Mục tiêu: Hoàn thiện dữ liệu để tránh lỗi khi phân tích/vẽ biểu đồ/huấn luyện.",
                        f"Phạm vi áp dụng: {len(numeric_cols_missing)} cột số và {len(categorical_cols_missing)} cột phân loại.",
                        "Kỹ thuật cột số: Điền NaN bằng KNNImputer (dùng n_neighbors động, tối đa 5, trọng số theo khoảng cách).",
                        "Kỹ thuật cột phân loại: Điền NaN bằng giá trị xuất hiện nhiều nhất (mode).",
                        f"Kết quả: Tổng thiếu {missing_before:,} → {missing_after:,}; số cột có thiếu được xử lý: {len(impacted_cols)}."
                    ]
                })

            # Xử lý outlier (tên mục cũ "Xử lý outlier" vẫn nhận để tương thích phiên cũ)
            if _opt_outlier_iqr in process_options or "Xử lý outlier" in process_options:
                try:
                    before_outlier = len(df_processed)
                    prep_obj = DataPreprocessor()
                    df_processed, outlier_info = prep_obj.handle_outliers(
                        df_processed, method='iqr', z_threshold=3.0
                    )
                    removed = outlier_info.get('total_removed', 0)
                    if removed > 0:
                        log_list.append(f"✓ Loại bỏ {removed} dòng outlier")
                        outlier_by_col = outlier_info.get('outliers_removed', {})
                        outlier_by_col = {k: int(v) for k, v in outlier_by_col.items() if int(v) > 0}
                        top_outlier_cols = sorted(outlier_by_col.items(), key=lambda x: x[1], reverse=True)[:5]
                        top_outlier_text = ", ".join([f"{col}: {cnt:,}" for col, cnt in top_outlier_cols]) if top_outlier_cols else "Không có cột nào vượt ngưỡng đáng kể"
                        changes_summary.append({
                            'Bước': 'Xử lý outlier',
                            'Trước': f"{before_outlier:,} dòng",
                            'Sau': f"{len(df_processed):,} dòng",
                            'Thay đổi': f"-{removed:,} dòng ({_safe_pct(removed, before_outlier):.1f}%)",
                            'Mô tả': (
                                f"Dùng IQR cho các cột số: outlier nếu nằm ngoài [Q1 - 1.5*IQR, Q3 + 1.5*IQR]. "
                                f"Bất kỳ dòng nào có ít nhất 1 giá trị outlier đều bị loại. "
                                f"Kết quả: loại {removed:,} dòng trên {before_outlier:,} dòng ban đầu. "
                                f"Các cột có nhiều outlier nhất: {top_outlier_text}."
                            ),
                            'Chi tiết': [
                                "Mục tiêu: Giảm ảnh hưởng của các giá trị cực đoan gây méo thống kê và mô hình.",
                                "Phạm vi áp dụng: Chỉ trên các cột số.",
                                "Ngưỡng IQR: IQR = Q3 - Q1; giữ giá trị trong [Q1 - 1.5*IQR, Q3 + 1.5*IQR].",
                                "Quy tắc loại dòng: Nếu một dòng có ít nhất 1 cột số vượt ngưỡng, dòng đó bị loại.",
                                f"Kết quả: {before_outlier:,} → {len(df_processed):,} dòng; đã loại {removed:,} dòng ({_safe_pct(removed, before_outlier):.1f}%).",
                                f"Cột ảnh hưởng nhiều nhất: {top_outlier_text}."
                            ]
                        })
                    else:
                        changes_summary.append({
                            'Bước': 'Xử lý outlier',
                            'Trước': f"{before_outlier:,} dòng",
                            'Sau': f"{len(df_processed):,} dòng",
                            'Thay đổi': "Không có outlier",
                            'Mô tả': 'Không phát hiện giá trị ngoại lai đáng kể trong dữ liệu.',
                            'Chi tiết': [
                                "Mục tiêu: Kiểm tra và loại bỏ giá trị cực đoan theo IQR.",
                                "Phạm vi áp dụng: Các cột số trong dữ liệu hiện tại.",
                                "Kết quả: Không có dòng nào vi phạm ngưỡng IQR nên giữ nguyên toàn bộ dữ liệu."
                            ]
                        })
                except Exception as e:
                    log_list.append(f"⚠️ Lỗi xử lý outlier: {str(e)}")

            st.session_state.cleaned_df = df_processed
            st.success("✅ Xử lý hoàn tất!")
            
            # Ghi log activity
            if wh is not None:
                wh.log_activity("Làm sạch Dữ liệu", f"Tự động xử lý {len(log_list)} bước tiền xử lý", {"changes": len(changes_summary)})
            
            # Hiển thị tóm tắt thay đổi
            st.markdown("---")
            st.markdown("### Tóm tắt các thay đổi:")
            for log in log_list:
                st.write(f"  {log}")
            
            # Hiển thị bảng chi tiết thay đổi
            if changes_summary:
                st.markdown("---")
                st.markdown("#### Chi tiết từng bước xử lý:")
                changes_df = pd.DataFrame(changes_summary)
                changes_df['Chi tiết'] = changes_df['Chi tiết'].apply(
                    lambda items: ' • '.join(
                        str(item).removeprefix('Mục tiêu: ').strip() for item in items
                    ) if isinstance(items, list) else str(items).removeprefix('Mục tiêu: ')
                )
                st.dataframe(changes_df, width="stretch", hide_index=True)
                
                # Giải thích rõ ràng
                st.markdown("---")
                st.markdown("#### Giải thích chi tiết:")
                for change in changes_summary:
                    with st.expander(f"📌 {change['Bước']}", expanded=False):
                        st.markdown(f"**Trước khi xử lý:** {change['Trước']}")
                        st.markdown(f"**Sau khi xử lý:** {change['Sau']}")
                        st.markdown(f"**Thay đổi:** {change['Thay đổi']}")
                        st.markdown(f"**Mô tả:** {change['Mô tả']}")
                        detail_items = change.get('Chi tiết', [])
                        if detail_items:
                            st.markdown("**Diễn giải từng bước:**")
                            for item in detail_items:
                                st.markdown(f"- {str(item).removeprefix('Mục tiêu: ')}")

                # Xuất báo cáo xử lý dữ liệu theo đúng số liệu vừa chạy
                st.markdown("---")
                st.markdown("#### Xuất báo cáo xử lý")
                report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                overview_before = {
                    "Số dòng": int(len(df)),
                    "Số cột": int(df.shape[1]),
                    "Giá trị thiếu": int(df.isnull().sum().sum()),
                    "Dòng trùng lặp": int(df.duplicated().sum())
                }
                overview_after = {
                    "Số dòng": int(len(df_processed)),
                    "Số cột": int(df_processed.shape[1]),
                    "Giá trị thiếu": int(df_processed.isnull().sum().sum()),
                    "Dòng trùng lặp": int(df_processed.duplicated().sum())
                }

                report_lines = [
                    "# Bao cao xu ly du lieu",
                    "",
                    f"- Thoi gian tao bao cao: {report_time}",
                    f"- Cac buoc duoc chon: {', '.join(process_options) if process_options else 'Khong chon buoc nao'}",
                    "",
                    "## Tong quan truoc/sau",
                    "",
                    f"- So dong: {overview_before['Số dòng']:,} -> {overview_after['Số dòng']:,}",
                    f"- So cot: {overview_before['Số cột']:,} -> {overview_after['Số cột']:,}",
                    f"- Gia tri thieu: {overview_before['Giá trị thiếu']:,} -> {overview_after['Giá trị thiếu']:,}",
                    f"- Dong trung lap: {overview_before['Dòng trùng lặp']:,} -> {overview_after['Dòng trùng lặp']:,}",
                    "",
                    "## Chi tiet tung buoc xu ly",
                    ""
                ]

                for idx, change in enumerate(changes_summary, 1):
                    report_lines.extend([
                        f"### Buoc {idx}: {change['Bước']}",
                        f"- Truoc khi xu ly: {change['Trước']}",
                        f"- Sau khi xu ly: {change['Sau']}",
                        f"- Thay doi: {change['Thay đổi']}",
                        f"- Mo ta chi tiet: {change['Mô tả']}",
                        "- Dien giai tung buoc:",
                        *[f"  - {line}" for line in change.get('Chi tiết', [])],
                        ""
                    ])

                report_lines.extend([
                    "## Nhat ky thao tac",
                    ""
                ])
                for log in log_list:
                    report_lines.append(f"- {log}")

                report_md = "\n".join(report_lines)
                st.session_state.latest_processing_report_md = report_md

                st.download_button(
                    "📄 Tải báo cáo xử lý (.md)",
                    data=report_md.encode("utf-8"),
                    file_name=f"data_processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key="download_processing_report_md"
                )
            
            st.caption("💾 **Lưu ý:** Bản dữ liệu đã được lưu vào `st.session_state.cleaned_df` để sử dụng cho các bước kế tiếp.")

    st.markdown("---")

    # ========================================================================
    # PHẦN 3: SO SÁNH TRƯỚC/SAU
    # ========================================================================
    target_for_analysis = st.session_state.get('target_for_analysis')

    st_step_header("Bước 3: So sánh trước & sau")
    if 'cleaned_df' in st.session_state and st.session_state.cleaned_df is not None:
        # st.markdown("### Bước 3: So sánh Trước & Sau")
        df_clean = st.session_state.cleaned_df

        # Tính toán thống kê nhất quán để dùng chung cho bảng/metric/biểu đồ
        before_stats = {
            'Số dòng': int(len(df)),
            'Số cột': int(df.shape[1]),
            'Giá trị thiếu': int(df.isnull().sum().sum()),
            'Dòng trùng lặp': int(df.duplicated().sum())
        }
        after_stats = {
            'Số dòng': int(len(df_clean)),
            'Số cột': int(df_clean.shape[1]),
            'Giá trị thiếu': int(df_clean.isnull().sum().sum()),
            'Dòng trùng lặp': int(df_clean.duplicated().sum())
        }

        def _format_delta(before_val, after_val, with_percent=True):
            delta = after_val - before_val
            sign = "+" if delta > 0 else ""
            if with_percent:
                pct = (delta / before_val * 100) if before_val != 0 else (100.0 if delta > 0 else 0.0)
                return f"{sign}{delta:,} ({pct:.1f}%)"
            return f"{sign}{delta:,}"

        st.markdown("#### Bảng So sánh Chi tiết:")
        comparison_data = {
            'Chỉ số': ['Số dòng', 'Số cột', 'Giá trị thiếu', 'Dòng trùng lặp'],
            'Trước xử lý': [
                f"{before_stats['Số dòng']:,}",
                f"{before_stats['Số cột']:,}",
                f"{before_stats['Giá trị thiếu']:,}",
                f"{before_stats['Dòng trùng lặp']:,}"
            ],
            'Sau xử lý': [
                f"{after_stats['Số dòng']:,}",
                f"{after_stats['Số cột']:,}",
                f"{after_stats['Giá trị thiếu']:,}",
                f"{after_stats['Dòng trùng lặp']:,}"
            ],
            'Thay đổi': [
                _format_delta(before_stats['Số dòng'], after_stats['Số dòng'], with_percent=True),
                _format_delta(before_stats['Số cột'], after_stats['Số cột'], with_percent=True),
                _format_delta(before_stats['Giá trị thiếu'], after_stats['Giá trị thiếu'], with_percent=True),
                _format_delta(before_stats['Dòng trùng lặp'], after_stats['Dòng trùng lặp'], with_percent=True)
            ]
        }
        comparison_df = pd.DataFrame(comparison_data)
        st.dataframe(comparison_df, width="stretch", hide_index=True)
        
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Dòng (gốc)", f"{before_stats['Số dòng']:,}")
        with col2:
            st.metric("Dòng (sau xử lý)", f"{after_stats['Số dòng']:,}", delta=_format_delta(before_stats['Số dòng'], after_stats['Số dòng'], with_percent=False))
        with col3:
            st.metric("Thiếu (gốc)", f"{before_stats['Giá trị thiếu']:,}")
        with col4:
            st.metric("Thiếu (sau xử lý)", f"{after_stats['Giá trị thiếu']:,}", delta=_format_delta(before_stats['Giá trị thiếu'], after_stats['Giá trị thiếu'], with_percent=False))
        
        # Giải thích rõ ràng
        st.markdown("---")
        st.markdown("#### Giải thích sự khác biệt:")
        changes_explained = []
        if after_stats['Số dòng'] != before_stats['Số dòng']:
            changes_explained.append(
                f"**Số dòng:** Từ {before_stats['Số dòng']:,} xuống {after_stats['Số dòng']:,} "
                f"({_format_delta(before_stats['Số dòng'], after_stats['Số dòng'], with_percent=True)}). "
                "Nguyên nhân chính là loại bỏ trùng lặp và/hoặc loại bỏ outlier."
            )
        if after_stats['Số cột'] != before_stats['Số cột']:
            changes_explained.append(
                f"**Số cột:** Từ {before_stats['Số cột']:,} xuống {after_stats['Số cột']:,} "
                f"({_format_delta(before_stats['Số cột'], after_stats['Số cột'], with_percent=True)}). "
                "Điều này xảy ra khi có bước thêm/bớt cột trong pipeline xử lý."
            )
        if after_stats['Giá trị thiếu'] != before_stats['Giá trị thiếu']:
            changes_explained.append(
                f"**Giá trị thiếu:** Từ {before_stats['Giá trị thiếu']:,} xuống {after_stats['Giá trị thiếu']:,} "
                f"({_format_delta(before_stats['Giá trị thiếu'], after_stats['Giá trị thiếu'], with_percent=True)}). "
                "Các giá trị thiếu được điền theo KNNImputer (cột số) và mode (cột phân loại)."
            )
        if after_stats['Dòng trùng lặp'] != before_stats['Dòng trùng lặp']:
            changes_explained.append(
                f"**Dòng trùng lặp:** Từ {before_stats['Dòng trùng lặp']:,} xuống {after_stats['Dòng trùng lặp']:,} "
                f"({_format_delta(before_stats['Dòng trùng lặp'], after_stats['Dòng trùng lặp'], with_percent=True)})."
            )
        
        if changes_explained:
            for explanation in changes_explained:
                st.info(explanation)
        else:
            st.success("✅ Dữ liệu không có thay đổi đáng kể sau xử lý.")
        
        # ========================================================================
        # ĐỒ THỊ SO SÁNH TRƯỚC/SAU
        # ========================================================================
        st.markdown("---")
        st.markdown("#### Đồ thị So sánh Trước & Sau Xử lý:")
        
        # Tạo dữ liệu cho đồ thị
        comparison_chart_data = {
            'Chỉ số': ['Số dòng', 'Số cột', 'Giá trị thiếu', 'Dòng trùng lặp'],
            'Trước xử lý': [
                before_stats['Số dòng'],
                before_stats['Số cột'],
                before_stats['Giá trị thiếu'],
                before_stats['Dòng trùng lặp']
            ],
            'Sau xử lý': [
                after_stats['Số dòng'],
                after_stats['Số cột'],
                after_stats['Giá trị thiếu'],
                after_stats['Dòng trùng lặp']
            ]
        }
        comparison_chart_df = pd.DataFrame(comparison_chart_data)
        
        # Đồ thị cột so sánh
        fig_comparison = px.bar(
            comparison_chart_df,
            x='Chỉ số',
            y=['Trước xử lý', 'Sau xử lý'],
            barmode='group',
            title='📊 So sánh Trước & Sau Xử lý Dữ liệu',
            labels={'value': 'Giá trị', 'variable': 'Thời điểm'},
            color_discrete_map={'Trước xử lý': '#ef4444', 'Sau xử lý': '#22c55e'},
            text_auto=True
        )
        fig_comparison.update_layout(
            height=400,
            xaxis_tickangle=-45,
            template='plotly_white',
            legend=dict(title="Thời điểm", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_comparison, width="stretch")
        
        # Đồ thị cột so sánh phần trăm thay đổi
        if before_stats['Số dòng'] > 0:
            percent_changes = {
                'Số dòng': ((after_stats['Số dòng'] - before_stats['Số dòng']) / max(before_stats['Số dòng'], 1) * 100),
                'Số cột': ((after_stats['Số cột'] - before_stats['Số cột']) / max(before_stats['Số cột'], 1) * 100),
                'Giá trị thiếu': ((after_stats['Giá trị thiếu'] - before_stats['Giá trị thiếu']) / max(before_stats['Giá trị thiếu'], 1) * 100),
                'Dòng trùng lặp': ((after_stats['Dòng trùng lặp'] - before_stats['Dòng trùng lặp']) / max(before_stats['Dòng trùng lặp'], 1) * 100)
            }
            
            percent_df = pd.DataFrame({
                'Chỉ số': list(percent_changes.keys()),
                'Thay đổi (%)': list(percent_changes.values())
            })
            
            fig_percent = px.bar(
                percent_df,
                x='Chỉ số',
                y='Thay đổi (%)',
                title='📈 Phần trăm Thay đổi sau Xử lý',
                text='Thay đổi (%)',
                labels={'Thay đổi (%)': 'Thay đổi (%)'}
            )
            fig_percent.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_percent.update_layout(
                height=350,
                xaxis_tickangle=-45,
                template='plotly_white'
            )
            st.plotly_chart(fig_percent, width="stretch")
    else:
        st.info("ℹ️ Bước này sẽ hiển thị sau khi dữ liệu được xử lý ở Bước 2.")

    # --- CẤU HÌNH NÂNG CAO & SCATTER PLOT (MỚI) ---
    if 'cleaned_df' in st.session_state and st.session_state.cleaned_df is not None:
        df_clean = st.session_state.cleaned_df
        st.markdown("---")
        st.subheader("Cấu hình nâng cao")
        st.markdown("""
        Luồng xử lý đang áp dụng:
        1) Loại bỏ dòng trùng lặp hoàn toàn (nếu bật).
        2) Điền thiếu cho cột số bằng KNNImputer (k mẫu gần nhất) và cột phân loại theo mode.
        3) Loại bỏ outlier theo IQR: ngoài [Q1 - 1.5*IQR, Q3 + 1.5*IQR].
        Mọi bảng/biểu đồ trong phần so sánh đều dùng cùng một bộ thống kê trước/sau để đảm bảo khớp số liệu.
        """)

        st.markdown("#### Phân tích Phân bố & Tương quan (Scatter Plot)")
        st.markdown("Biểu đồ phân tán (Scatter Plot) giúp bạn nhìn thấy mối quan hệ giữa hai biến sau khi đã làm sạch dữ liệu. Bạn có thể phát hiện các cụm (clusters) hoặc xu hướng tuyến tính.")

        numeric_cols_clean = df_clean.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols_clean) >= 2:
            col_scatter1, col_scatter2, col_scatter3 = st.columns([1, 1, 1])
            with col_scatter1:
                x_axis_adv = st.selectbox("Chọn trục X:", numeric_cols_clean, index=0,
                                          format_func=feature_label, key="adv_scatter_x")
            with col_scatter2:
                y_axis_adv = st.selectbox("Chọn trục Y:", numeric_cols_clean,
                                          index=1 if len(numeric_cols_clean) > 1 else 0,
                                          format_func=feature_label, key="adv_scatter_y")
            with col_scatter3:
                color_col_adv = st.selectbox("Màu sắc (phân nhóm):", ["None"] + df_clean.columns.tolist(), index=0, key="adv_scatter_color")
            
            # Vẽ biểu đồ
            color_arg = None if color_col_adv == "None" else color_col_adv
            
            try:
                # Sử dụng helper function để tự động xử lý khi thiếu statsmodels
                fig_scatter_adv = scatter_with_optional_ols(
                    df=df_clean, 
                    x=x_axis_adv, 
                    y=y_axis_adv, 
                    color=color_arg,
                    title=f"Tương quan: {x_axis_adv} vs {y_axis_adv}",
                    template="plotly_white",
                    opacity=0.7
                )
                st.plotly_chart(fig_scatter_adv, width="stretch")
            except Exception as e:
                ui_kit.report_error("Không thể vẽ biểu đồ", e)
        else:
            st.info("⚠️ Cần ít nhất 2 cột số để vẽ biểu đồ Scatter.")

    st.markdown("---")
    st_step_header("Bước 4: Chọn features")

    if 'cleaned_df' in st.session_state and st.session_state.cleaned_df is not None:
        df_clean = st.session_state.cleaned_df
        
        with st.expander("Xem Phân tích Tương quan & Mức độ Quan trọng (Feature Selection)", expanded=False):
            # Hiển thị giải thích các phương pháp
            render_feature_method_explanation()
            
            st.markdown("*Xem features nào ảnh hưởng đến target, chọn features quan trọng:*")

            tab_corr, tab_importance = st.tabs(["📊 Tương quan", "🎯 Importance"])

            with tab_corr:
                numeric_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()
                numeric_cols = [c for c in numeric_cols if 'id' not in c.lower()]

                if len(numeric_cols) > 1:
                    corr_matrix = df_clean[numeric_cols].corr()

                    # Heatmap
                    fig_corr = px.imshow(
                        corr_matrix,
                        text_auto='.2f',
                        color_continuous_scale='RdBu',
                        title="Ma trận Tương quan"
                    )
                    fig_corr.update_layout(height=600)
                    st.plotly_chart(fig_corr, width="stretch")

                    st.caption("**Giải thích:** Giá trị gần 1 = tương quan dương mạnh; gần -1 = tương quan âm mạnh; gần 0 = không tương quan")

                    def sync_explore_corr_target():
                        val = st.session_state.target_corr_select
                        st.session_state.target_for_analysis = val
                        for prefix in ['pers', 'file', 'batch', 'config']:
                            st.session_state[f'{prefix}_target'] = val

                    # Chọn target để phân tích chi tiết
                    selected_target = st.selectbox(
                        "Chọn Target để xem features ảnh hưởng:",
                        numeric_cols,
                        key="target_corr_select",
                        on_change=sync_explore_corr_target
                    )
                    
                    if "target_for_analysis" not in st.session_state:
                        st.session_state.target_for_analysis = selected_target
                        for prefix in ['pers', 'file', 'batch', 'config']:
                            st.session_state[f'{prefix}_target'] = selected_target

                    target_for_analysis = selected_target

                    # Bar chart tương quan với target
                    corr_with_target = corr_matrix[selected_target].sort_values(ascending=False)
                    corr_with_target = corr_with_target[corr_with_target.index != selected_target]

                    fig_bar = px.bar(
                        x=corr_with_target.index,
                        y=corr_with_target.values,
                        title=f"Features ảnh hưởng đến {selected_target}",
                        color=corr_with_target.values,
                        color_continuous_scale='RdYlGn',
                        text=corr_with_target.values.round(2)
                    )
                    fig_bar.update_traces(texttemplate='%{text}', textposition='outside')
                    fig_bar.update_layout(height=400, xaxis_tickangle=-45)
                    st.plotly_chart(fig_bar, width="stretch")
                    st.caption(f"Các cột nằm ngoà i phạm vi ±0.3 có ảnh hưởng thấp đến `{selected_target}`.")

                    # Gợi ý features mạnh
                    strong_features = corr_with_target[abs(corr_with_target) > 0.3]
                    if len(strong_features) > 0:
                        st.success(f"✅ **{len(strong_features)} features có tương quan mạnh (>0.3):**")
                        st.info(", ".join(strong_features.index.tolist()))
                        st.caption("Ưu tiên giữ lại các features có tương quan mạnh để mô hình ổn định hơn.")
                else:
                    st.info("ℹ️ Cần ít nhất 2 cột số để tính tương quan")

            with tab_importance:
                numeric_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()
                numeric_cols = [c for c in numeric_cols if 'id' not in c.lower()]
                
                if len(numeric_cols) > 1:
                    def sync_explore_imp_target():
                        val = st.session_state.target_imp_select
                        st.session_state.target_for_analysis = val
                        for prefix in ['pers', 'file', 'batch', 'config']:
                            st.session_state[f'{prefix}_target'] = val

                    selected_target_imp = st.selectbox(
                        "Chọn Target để tính Importance:",
                        numeric_cols,
                        key="target_imp_select",
                        on_change=sync_explore_imp_target
                    )

                    try:
                        feature_cols = [c for c in numeric_cols if c != selected_target_imp]
                        importance_df = model_service.preview_feature_importance(
                            df_clean, feature_cols, selected_target_imp
                        )

                        # Bảng importance
                        st.dataframe(importance_df, width="stretch", hide_index=True)
                        st.caption("**Giải thích:** Mức độ quan trọng của feature trong dự đoán target (tính từ Random Forest)")

                        # Biểu đồ
                        fig_imp = px.bar(
                            importance_df.head(15),
                            x='Feature',
                            y='Importance (%)',
                            title=f"Top 15 Features quan trọng",
                            color='Importance (%)',
                            color_continuous_scale='Viridis',
                            text='Importance (%)'
                        )
                        fig_imp.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                        fig_imp.update_layout(height=400, xaxis_tickangle=-45)
                        st.plotly_chart(fig_imp, width="stretch")
                        st.caption("Các cột nằm trên cùng biểu đồ là ứng viên tốt để đưa vào huấn luyện.")

                        # Gợi ý
                        important = importance_df[importance_df['Importance (%)'] > 1.0]
                        if len(important) > 0:
                            st.success(f"✅ **{len(important)} features có Importance > 1%:**")
                            st.info(", ".join(important['Feature'].tolist()))
                            st.caption("Các gợi ý trên sẽ được dùng để đề xuất cấu hình mô hình ở bước huấn luyện.")

                    except Exception as e:
                        ui_kit.report_error("Không tính được mức độ quan trọng của các đặc trưng", e)
                else:
                    st.info("ℹ️ Cần ít nhất 2 cột số")

        st.markdown("---")
        st.info("💡 **Kế tiếp:** Đi đến tab **🧪 Huấn luyện** để sử dụng dữ liệu sạch này!")

    else:
        st.info("ℹ️ Bước này sẽ hiển thị sau khi dữ liệu được xử lý ở Bước 2.")
    
    # Phân tích chi tiết từng thuộc tính - CẢI THIỆN
    st.markdown("---")
    st.markdown("#### Phân tích Chi tiết Từng Thuộc tính")
    st.markdown("**Chọn một thuộc tính để xem phân tích chi tiết, thống kê mô tả, phân phối và mối quan hệ với các biến khác.**")
    
    selected_feature_detail = st.selectbox(
        "Chọn thuộc tính để phân tích chi tiết:",
        df.columns.tolist(),
        key="feature_detail_select"
    )
    
    if selected_feature_detail:
        col_detail = df[selected_feature_detail]
        
        # Thông tin tổng quan
        st.markdown(f"### 📊 Phân tích Chi tiết: **{selected_feature_detail}**")
        
        info_col1, info_col2, info_col3, info_col4 = st.columns(4)
        with info_col1:
            st.metric("Kiểu dữ liệu", str(col_detail.dtype))
        with info_col2:
            st.metric("Số giá trị duy nhất", col_detail.nunique())
        with info_col3:
            missing_count = col_detail.isnull().sum()
            missing_pct = (missing_count / len(col_detail) * 100)
            st.metric("Giá trị thiếu", f"{missing_count} ({missing_pct:.1f}%)")
        with info_col4:
            if pd.api.types.is_numeric_dtype(col_detail):
                st.metric("Phạm vi", f"{col_detail.min():.2f} - {col_detail.max():.2f}")
            else:
                st.metric("Giá trị phổ biến nhất", str(col_detail.mode().iloc[0]) if len(col_detail.mode()) > 0 else "N/A")
        
        col1_detail, col2_detail = st.columns(2)
        
        with col1_detail:
            st.markdown("**📈 Thống kê Mô tả:**")
            if pd.api.types.is_numeric_dtype(col_detail):
                stats = col_detail.describe()
                stats_df = stats.to_frame('Giá trị')
                # Thêm thêm các thống kê
                stats_df.loc['Phương sai'] = col_detail.var()
                stats_df.loc['Độ lệch chuẩn'] = col_detail.std()
                stats_df.loc['Độ lệch'] = col_detail.skew()
                stats_df.loc['Độ nhọn'] = col_detail.kurtosis()
                st.dataframe(stats_df, width="stretch")
                
                # Phân tích outlier
                Q1 = col_detail.quantile(0.25)
                Q3 = col_detail.quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                outliers = col_detail[(col_detail < lower_bound) | (col_detail > upper_bound)]
                if len(outliers) > 0:
                    st.warning(f"⚠️ Phát hiện {len(outliers)} giá trị ngoại lai (outliers) - {len(outliers)/len(col_detail)*100:.1f}%")
            else:
                st.write(f"**Kiểu dữ liệu:** {col_detail.dtype}")
                st.write(f"**Số giá trị duy nhất:** {col_detail.nunique()}")
                st.write(f"**Giá trị thiếu:** {col_detail.isnull().sum()} ({col_detail.isnull().sum()/len(col_detail)*100:.1f}%)")
                value_counts = col_detail.value_counts().head(15)
                value_counts_df = value_counts.to_frame('Số lượng')
                value_counts_df['Tỷ lệ (%)'] = (value_counts_df['Số lượng'] / len(col_detail) * 100).round(2)
                st.dataframe(value_counts_df, width="stretch")
        
        with col2_detail:
            st.markdown("**📊 Phân phối & Trực quan hóa:**")
            if pd.api.types.is_numeric_dtype(col_detail):
                # Histogram
                fig_dist = px.histogram(
                    df,
                    x=selected_feature_detail,
                    nbins=30,
                    title=f"Phân phối {selected_feature_detail}",
                    color_discrete_sequence=['#2563EB'],
                    labels={selected_feature_detail: selected_feature_detail, 'count': 'Số lượng'}
                )
                fig_dist.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig_dist, width="stretch")
                
                # Box plot
                fig_box = px.box(
                    df,
                    y=selected_feature_detail,
                    title=f"Box Plot - {selected_feature_detail}",
                    color_discrete_sequence=['#10B981']
                )
                fig_box.update_layout(height=250, showlegend=False)
                st.plotly_chart(fig_box, width="stretch")
            else:
                fig_bar = px.bar(
                    x=col_detail.value_counts().head(15).index,
                    y=col_detail.value_counts().head(15).values,
                    title=f"Top 15 giá trị phổ biến của {selected_feature_detail}",
                    labels={'x': selected_feature_detail, 'y': 'Số lượng'},
                    color_discrete_sequence=['#10B981']
                )
                fig_bar.update_layout(height=300, xaxis_tickangle=-45, showlegend=False)
                st.plotly_chart(fig_bar, width="stretch")
        
        # Phân tích tương quan với target và các features khác
        st.markdown("---")
        st.markdown("**🔗 Phân tích Tương quan & Mối quan hệ:**")
        
        if target_for_analysis and pd.api.types.is_numeric_dtype(col_detail):
            if selected_feature_detail != target_for_analysis:
                corr_col1, corr_col2 = st.columns(2)
                
                with corr_col1:
                    correlation = df[[selected_feature_detail, target_for_analysis]].corr().iloc[0, 1]
                    if abs(correlation) > 0.7:
                        corr_level = "Rất mạnh"
                        corr_color = "#22c55e"
                    elif abs(correlation) > 0.5:
                        corr_level = "Mạnh"
                        corr_color = "#3b82f6"
                    elif abs(correlation) > 0.3:
                        corr_level = "Trung bình"
                        corr_color = "#f59e0b"
                    else:
                        corr_level = "Yếu"
                        corr_color = "#ef4444"
                    
                    st.markdown(
                        f"<div style='padding:1rem;border-left:4px solid {corr_color};background:var(--bg-secondary);'>"
                        f"<p><strong>He so tuong quan voi {target_for_analysis}:</strong></p>"
                        f"<h3 style='color:{corr_color}'>{correlation:.4f}</h3>"
                        f"<p>Muc do: <strong>{corr_level}</strong></p></div>",
                        unsafe_allow_html=True,
                    )
                
                with corr_col2:
                    # Scatter plot với trend line (sử dụng helper để tránh lỗi nếu statsmodels không có sẵn)
                    fig_scatter_detail = scatter_with_optional_ols(
                        df=df,
                        x=selected_feature_detail,
                        y=target_for_analysis,
                        title=f"Tương quan: {selected_feature_detail} ↔ {target_for_analysis}",
                        color_discrete_sequence=['var(--primary-color)'],
                        labels={selected_feature_detail: selected_feature_detail, target_for_analysis: target_for_analysis}
                    )
                    fig_scatter_detail.update_layout(height=350, showlegend=False)
                    st.plotly_chart(fig_scatter_detail, width="stretch")
        
        # Phân tích tương quan với tất cả các features số khác
        if pd.api.types.is_numeric_dtype(col_detail):
            numeric_cols_all = df.select_dtypes(include=[np.number]).columns.tolist()
            numeric_cols_all = [c for c in numeric_cols_all if c != selected_feature_detail]
            
            if len(numeric_cols_all) > 0:
                st.markdown("**📊 Ma trận Tương quan với các Features khác:**")
                corr_with_others = df[numeric_cols_all + [selected_feature_detail]].corr()[selected_feature_detail].sort_values(ascending=False)
                corr_with_others = corr_with_others[corr_with_others.index != selected_feature_detail]
                
                if len(corr_with_others) > 0:
                    fig_corr_bar = px.bar(
                        x=corr_with_others.index,
                        y=corr_with_others.values,
                        title=f"Tương quan của {selected_feature_detail} với các Features khác",
                        labels={'x': 'Feature', 'y': 'Hệ số tương quan'},
                        color=corr_with_others.values,
                        color_continuous_scale='RdYlGn'
                    )
                    fig_corr_bar.update_layout(height=400, xaxis_tickangle=-45, showlegend=False)
                    st.plotly_chart(fig_corr_bar, width="stretch")
                    
                    # Top features tương quan mạnh
                    strong_corr = corr_with_others[abs(corr_with_others) > 0.3]
                    if len(strong_corr) > 0:
                        st.success(f"✅ **{len(strong_corr)} features có tương quan mạnh (|r| > 0.3) với {selected_feature_detail}:**")
                        for feat, corr_val in strong_corr.items():
                            st.write(f"  • **{feat}**: {corr_val:.3f}")
        
        elif not target_for_analysis:
            st.info("⚠️ Hãy chọn một cột target trong phần *Chọn Features* để xem tương quan chi tiết.")
    
    # ========================================================================
    # PHẦN 5: FEATURE ENGINEERING & GIẢI THÍCH CHI TIẾT
    # ========================================================================
    st.markdown("---")
    st_step_header("Bước 5: Feature engineering & giải thích chi tiết")
    
    tab_fe_explain, tab_fe_add = st.tabs(["📚 Giải thích feature engineering", "➕ Tạo features mới"])
    
    with tab_fe_explain:
        st.markdown(
            "<div><h3>Feature Engineering</h3><p>Tạo đặc trưng mới từ dữ liệu gốc để cải thiện mô hình.</p></div>",
            unsafe_allow_html=True,
        )
        
        # Giải thích các loại features được tạo
        st.markdown("#### Các loại features được tạo tự động")
        
        feature_types = [
            {
                "name": "1. Features Từ Điểm Số (Score-based Features)",
                "description": "Tạo các features từ điểm số như tổng điểm, điểm trung bình, điểm cao nhất/thấp nhất",
                "impact": "Cao",
                "reason": "Điểm số là chỉ số trực tiếp phản ánh năng lực học tập. Tổng điểm và điểm trung bình giúp mô hình hiểu được tổng thể năng lực, trong khi điểm cao/thấp giúp phát hiện điểm mạnh/yếu.",
                "example": "Nếu có các cột: math_score, physics_score, chemistry_score → Tạo: total_score, avg_score, max_score, min_score"
            },
            {
                "name": "2. Features Từ Tỷ Lệ & Số Lượng (Ratio & Count Features)",
                "description": "Tính tỷ lệ giữa các giá trị, số lượng giá trị lớn hơn trung bình, tỷ lệ phần trăm",
                "impact": "Trung bình - Cao",
                "reason": "Tỷ lệ giúp chuẩn hóa dữ liệu và loại bỏ ảnh hưởng của quy mô. Ví dụ: tỷ lệ điểm toán/điểm lý giúp so sánh công bằng giữa các môn học khác nhau.",
                "example": "Nếu có math_score và physics_score → Tạo: math_physics_ratio, scores_above_mean_count"
            },
            {
                "name": "3. Features Polynomial (Đa thức)",
                "description": "Tạo các features bậc 2, 3 từ các cột quan trọng nhất (top 3 cột có phương sai cao nhất)",
                "impact": "Trung bình",
                "reason": "Polynomial features giúp mô hình nắm bắt các mối quan hệ phi tuyến tính. Ví dụ: nếu điểm số có mối quan hệ bậc 2 với GPA, polynomial features sẽ giúp mô hình học được điều này.",
                "example": "Nếu có gpa → Tạo: gpa^2, gpa^3 (nếu gpa là một trong top 3 cột quan trọng)"
            },
            {
                "name": "4. Features Từ Dữ Liệu Phân Loại (Categorical Features)",
                "description": "Chuyển đổi dữ liệu phân loại thành dạng số (Label Encoding, One-Hot Encoding)",
                "impact": "Cao",
                "reason": "Mô hình ML chỉ làm việc với số. Chuyển đổi dữ liệu phân loại (như giới tính, lớp học) thành số giúp mô hình hiểu được các nhóm khác nhau và tác động của chúng đến kết quả.",
                "example": "Nếu có gender: 'Male', 'Female' → Chuyển thành: 0, 1 hoặc tạo: gender_Male, gender_Female"
            },
            {
                "name": "5. Features Từ Dữ Liệu Thời Gian (Time-based Features)",
                "description": "Trích xuất năm, tháng, ngày, thứ trong tuần từ cột ngày tháng",
                "impact": "Trung bình",
                "reason": "Thời gian có thể ảnh hưởng đến kết quả (ví dụ: học kỳ mùa thu có thể khác mùa xuân). Trích xuất các thành phần thời gian giúp mô hình phát hiện các mẫu theo mùa hoặc theo thời gian.",
                "example": "Nếu có enrollment_date: '2023-09-15' → Tạo: enrollment_year=2023, enrollment_month=9, enrollment_day=15"
            },
            {
                "name": "6. Features Tương Tác (Interaction Features)",
                "description": "Tạo features từ tích/chia các cột quan trọng với nhau",
                "impact": "Trung bình - Cao",
                "reason": "Tương tác giữa các features có thể quan trọng hơn từng feature riêng lẻ. Ví dụ: điểm toán × điểm lý có thể dự đoán tốt hơn khả năng học STEM so với chỉ điểm toán hoặc chỉ điểm lý.",
                "example": "Nếu có math_score và physics_score → Tạo: math_physics_interaction = math_score × physics_score"
            }
        ]
        
        for feat_type in feature_types:
            with st.expander(f"**{feat_type['name']}**", expanded=False):
                st.markdown(f"**Mô tả:** {feat_type['description']}")
                
                col_impact, col_reason = st.columns([1, 2])
                with col_impact:
                    if feat_type['impact'] == "Cao":
                        st.success(f"**Mức độ ảnh hưởng:** {feat_type['impact']} ⭐⭐⭐")
                    elif feat_type['impact'] == "Trung bình - Cao":
                        st.info(f"**Mức độ ảnh hưởng:** {feat_type['impact']} ⭐⭐")
                    else:
                        st.info(f"**Mức độ ảnh hưởng:** {feat_type['impact']} ⭐")
                
                with col_reason:
                    st.markdown(f"**Tại sao quan trọng?**")
                    st.markdown(f"<p style='color: var(--text-secondary); line-height: 1.6;'>{feat_type['reason']}</p>", unsafe_allow_html=True)
                
                st.markdown(f"**Ví dụ:** {feat_type['example']}")
        
        # Giải thích về mức độ ảnh hưởng
        st.markdown("---")
        st.markdown("#### Mức độ ảnh hưởng của features")
        
        impact_explanation = (
            "<div><h4>Mức độ ảnh hưởng</h4><ul>"
            "<li>Cao: tác động mạnh tới kết quả.</li>"
            "<li>Trung bình: cải thiện ổn định.</li></ul></div>"
        )
        st.markdown(impact_explanation, unsafe_allow_html=True)
        
        # Giải thích về các loại dữ liệu
        st.markdown("---")
        st.markdown("#### Các loại dữ liệu & cách xử lý")
        
        data_types = [
            {
                "type": "Dữ Liệu Số (Numeric)",
                "subtypes": ["Số nguyên (int)", "Số thực (float)"],
                "handling": "Chuẩn hóa (StandardScaler), xử lý outlier, tạo polynomial features",
                "impact": "Cao - Đây là loại dữ liệu quan trọng nhất cho ML",
                "why": "Mô hình ML hoạt động tốt nhất với dữ liệu số đã được chuẩn hóa. Dữ liệu số trực tiếp phản ánh các đặc tính đo lường được."
            },
            {
                "type": "Dữ Liệu Phân Loại (Categorical)",
                "subtypes": ["Nhãn (Labels)", "Danh mục (Categories)"],
                "handling": "Label Encoding, One-Hot Encoding, Target Encoding",
                "impact": "Cao - Quan trọng cho phân loại và nhóm",
                "why": "Dữ liệu phân loại chứa thông tin về nhóm/loại, rất quan trọng để phân biệt các đối tượng khác nhau. Ví dụ: giới tính, lớp học, khoa."
            },
            {
                "type": "Dữ Liệu Thời Gian (DateTime)",
                "subtypes": ["Ngày tháng", "Thời gian"],
                "handling": "Trích xuất năm/tháng/ngày, tính khoảng cách thời gian",
                "impact": "Trung bình - Quan trọng nếu có mẫu theo thời gian",
                "why": "Thời gian có thể ảnh hưởng đến kết quả (mùa học, năm học). Trích xuất thành phần thời gian giúp phát hiện các mẫu theo mùa."
            },
            {
                "type": "Dữ Liệu Văn Bản (Text)",
                "subtypes": ["Tên", "Mô tả", "Ghi chú"],
                "handling": "Bỏ qua hoặc chuyển thành số (nếu cần)",
                "impact": "Thấp - Thường không dùng trực tiếp",
                "why": "Văn bản khó xử lý trực tiếp. Thường chỉ dùng làm định danh (ID) hoặc bỏ qua trừ khi có kỹ thuật NLP."
            }
        ]
        
        for data_type in data_types:
            with st.expander(f"**{data_type['type']}**", expanded=False):
                st.markdown(f"**Các loại phụ:** {', '.join(data_type['subtypes'])}")
                st.markdown(f"**Cách xử lý:** {data_type['handling']}")
                
                if data_type['impact'].startswith("Cao"):
                    st.success(f"**Mức độ ảnh hưởng:** {data_type['impact']}")
                elif data_type['impact'].startswith("Trung bình"):
                    st.info(f"**Mức độ ảnh hưởng:** {data_type['impact']}")
                else:
                    st.warning(f"**Mức độ ảnh hưởng:** {data_type['impact']}")
                
                st.markdown(f"**Tại sao:** {data_type['why']}")
        
        # Tổng kết
        st.markdown("---")
        st.markdown(
            "<div><h4>Luu y</h4><ul>"
            "<li>Đây là các gợi ý tham khảo — hệ thống không tự động tạo features, bạn cần tự chọn cột/phép toán ở tab \"Tạo features mới\" bên cạnh.</li>"
            "<li>Có thể thêm feature trong phần dự đoán.</li></ul></div>",
            unsafe_allow_html=True,
        )
    
    with tab_fe_add:
        st.markdown(
            "<div><h3>Tạo Feature Mới</h3><p>Thêm vào dataset để dùng khi dự đoán.</p></div>",
            unsafe_allow_html=True,
        )
        
        # Chọn loại feature muốn tạo
        feature_creation_type = st.radio(
            "Chọn loại feature muốn tạo:",
            ["Từ các cột hiện có (Tính toán)", "Nhập giá trị thủ công (Cho từng dòng)"],
            key="fe_creation_type"
        )
        
        if feature_creation_type == "Từ các cột hiện có (Tính toán)":
            st.markdown("#### Tính Toán Features Mới")
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            
            if len(numeric_cols) < 2:
                st.warning("⚠️ Cần ít nhất 2 cột số để tạo features mới.")
            else:
                col1_fe, col2_fe = st.columns(2)
                
                with col1_fe:
                    st.markdown("**Chọn các cột để tính toán:**")
                    selected_cols_fe = st.multiselect(
                        "Cột số:",
                        numeric_cols,
                        key="fe_selected_cols"
                    )
                
                with col2_fe:
                    st.markdown("**Chọn phép toán:**")
                    operation = st.selectbox(
                        "Phép toán:",
                        ["Tổng (+)", "Hiệu (-)", "Tích (*)", "Thương (/)", "Trung bình", "Max", "Min", "Độ lệch chuẩn"],
                        key="fe_operation"
                    )
                
                if selected_cols_fe and len(selected_cols_fe) >= 2:
                    # Hiển thị giải thích về phép toán
                    operation_explanations = {
                        "Tổng (+)": {
                            "formula": f"{' + '.join(selected_cols_fe)}",
                            "why": "Tổng hợp nhiều features giúp tạo ra một chỉ số tổng hợp, ví dụ: tổng điểm các môn học phản ánh tổng thể năng lực.",
                            "impact": "Có thể cải thiện độ chính xác 2-5% nếu các features gốc có tương quan với target."
                        },
                        "Hiệu (-)": {
                            "formula": f"{selected_cols_fe[0]} - {selected_cols_fe[1]}",
                            "why": "Hiệu số giúp phát hiện sự chênh lệch, ví dụ: chênh lệch điểm giữa hai môn học có thể phản ánh điểm mạnh/yếu.",
                            "impact": "Có thể cải thiện độ chính xác 1-4% nếu sự chênh lệch có ý nghĩa với target."
                        },
                        "Tích (*)": {
                            "formula": f"{' × '.join(selected_cols_fe)}",
                            "why": "Tích số giúp phát hiện tương tác giữa các features, ví dụ: điểm toán × điểm lý có thể dự đoán tốt khả năng STEM.",
                            "impact": "Có thể cải thiện độ chính xác 3-8% nếu có tương tác quan trọng giữa các features."
                        },
                        "Thương (/)": {
                            "formula": f"{selected_cols_fe[0]} / {selected_cols_fe[1]}",
                            "why": "Tỷ lệ giúp chuẩn hóa và so sánh tương đối, ví dụ: tỷ lệ điểm toán/điểm văn phản ánh thiên hướng học tập.",
                            "impact": "Có thể cải thiện độ chính xác 2-6% nếu tỷ lệ có ý nghĩa với target."
                        },
                        "Trung bình": {
                            "formula": f"({'+'.join(selected_cols_fe)}) / {len(selected_cols_fe)}",
                            "why": "Trung bình giúp tạo chỉ số đại diện, giảm ảnh hưởng của outliers và làm mô hình ổn định hơn.",
                            "impact": "Có thể cải thiện độ chính xác 1-3% và làm mô hình ổn định hơn."
                        },
                        "Max": {
                            "formula": f"max({', '.join(selected_cols_fe)})",
                            "why": "Giá trị lớn nhất phản ánh điểm mạnh, ví dụ: điểm cao nhất trong các môn cho thấy năng lực tốt nhất.",
                            "impact": "Có thể cải thiện độ chính xác 1-4% nếu điểm mạnh quan trọng với target."
                        },
                        "Min": {
                            "formula": f"min({', '.join(selected_cols_fe)})",
                            "why": "Giá trị nhỏ nhất phản ánh điểm yếu, ví dụ: điểm thấp nhất cho thấy môn học cần cải thiện.",
                            "impact": "Có thể cải thiện độ chính xác 1-4% nếu điểm yếu quan trọng với target."
                        },
                        "Độ lệch chuẩn": {
                            "formula": f"std({', '.join(selected_cols_fe)})",
                            "why": "Độ lệch chuẩn phản ánh sự biến thiên, ví dụ: độ lệch chuẩn điểm các môn cho thấy tính nhất quán trong học tập.",
                            "impact": "Có thể cải thiện độ chính xác 1-3% nếu sự biến thiên có ý nghĩa với target."
                        }
                    }
                    
                    if operation in operation_explanations:
                        exp = operation_explanations[operation]
                        st.markdown(
                            "<div class='dss-notice dss-notice--info'>"
                            f"<div class='dss-notice-title'>Phép toán: {operation}</div>"
                            f"<p class='dss-notice-body' style='margin:4px 0;'><strong>Công thức:</strong> <code>{exp['formula']}</code></p>"
                            f"<p class='dss-notice-body' style='margin:4px 0;'><strong>Lý do:</strong> {exp['why']}</p>"
                            f"<p class='dss-notice-body' style='margin:4px 0;'><strong>Ảnh hưởng:</strong> {exp['impact']}</p></div>",
                            unsafe_allow_html=True,
                        )
                    
                    new_feature_name = st.text_input(
                        "Tên feature mới:",
                        value=f"{operation.lower().replace(' ', '_')}_{'_'.join(selected_cols_fe[:2])}",
                        key="fe_new_name"
                    )
                    
                    if st.button("➕ Tạo Feature Mới", key="fe_create_btn"):
                        try:
                            if operation == "Tổng (+)":
                                df[new_feature_name] = df[selected_cols_fe].sum(axis=1)
                            elif operation == "Hiệu (-)":
                                df[new_feature_name] = df[selected_cols_fe[0]] - df[selected_cols_fe[1]]
                            elif operation == "Tích (*)":
                                df[new_feature_name] = df[selected_cols_fe].prod(axis=1)
                            elif operation == "Thương (/)":
                                df[new_feature_name] = df[selected_cols_fe[0]] / (df[selected_cols_fe[1]] + 1e-10)  # Tránh chia 0
                            elif operation == "Trung bình":
                                df[new_feature_name] = df[selected_cols_fe].mean(axis=1)
                            elif operation == "Max":
                                df[new_feature_name] = df[selected_cols_fe].max(axis=1)
                            elif operation == "Min":
                                df[new_feature_name] = df[selected_cols_fe].min(axis=1)
                            elif operation == "Độ lệch chuẩn":
                                df[new_feature_name] = df[selected_cols_fe].std(axis=1)
                            
                            # Cập nhật session state
                            st.session_state.current_df = df
                            st.success(f"✅ Đã tạo feature mới: **{new_feature_name}**")
                            st.info(f"Feature này sẽ có sẵn trong phần dự đoán. Bạn có thể xem trong bảng dữ liệu bên dưới.")
                            st.dataframe(df[[new_feature_name] + selected_cols_fe].head(10), width="stretch")
                            st.rerun()
                        except Exception as e:
                            ui_kit.report_error("❌ Lỗi khi tạo feature", e)
        
        else:  # Nhập giá trị thủ công
            st.markdown("#### Nhập Features Mới Thủ Công")
            st.markdown(
                "<div class='dss-notice dss-notice--warning'>"
                "<div class='dss-notice-title'>Thêm feature từ bên ngoài</div>"
                "<p class='dss-notice-body' style='margin:0;'>Bổ sung cột mới; đảm bảo số dòng khớp với dataset.</p></div>",
                unsafe_allow_html=True,
            )
            
            new_manual_feature = st.text_input(
                "Tên feature mới:",
                key="fe_manual_name"
            )
            
            if new_manual_feature:
                st.markdown(f"**Nhập giá trị cho feature: {new_manual_feature}**")
                st.caption(f"Cần nhập {len(df)} giá trị (tương ứng với {len(df)} dòng dữ liệu)")
                
                # Cho phép nhập từ file hoặc nhập tay
                input_method = st.radio(
                    "Cách nhập:",
                    ["Tải từ file CSV", "Nhập tay (từng giá trị)"],
                    key="fe_input_method"
                )
                
                if input_method == "Tải từ file CSV":
                    uploaded_feature_file = st.file_uploader(
                        "Tải file CSV chứa giá trị feature mới (cột đầu tiên sẽ được dùng):",
                        type=["csv"],
                        key="fe_upload_file"
                    )
                    
                    if uploaded_feature_file:
                        try:
                            feature_df = parse_tabular_upload(
                                uploaded_feature_file, allowed_extensions={".csv"}
                            ).frame
                            if len(feature_df) == len(df):
                                df[new_manual_feature] = feature_df.iloc[:, 0].values
                                st.session_state.current_df = df
                                st.success(f"✅ Đã thêm feature **{new_manual_feature}** từ file!")
                                st.dataframe(df[[new_manual_feature]].head(10), width="stretch")
                                st.rerun()
                            else:
                                st.error(f"❌ Số dòng không khớp! File có {len(feature_df)} dòng, nhưng dataset có {len(df)} dòng.")
                        except UploadValidationError as exc:
                            st.error(str(exc))
                        except Exception:
                            st.error("❌ Không thể đọc file CSV hợp lệ.")
                
                else:  # Nhập tay
                    st.warning("⚠️ Nhập tay từng giá trị có thể mất thời gian nếu dataset lớn. Khuyến nghị dùng file CSV.")
                    if len(df) <= 50:  # Chỉ cho phép nhập tay nếu dataset nhỏ
                        values_input = st.text_area(
                            f"Nhập {len(df)} giá trị (mỗi giá trị một dòng):",
                            height=200,
                            key="fe_manual_values"
                        )
                        
                        if values_input:
                            values_list = [line.strip() for line in values_input.strip().split('\n')]
                            if len(values_list) == len(df):
                                try:
                                    # Thử chuyển thành số, nếu không được thì giữ nguyên string
                                    numeric_values = []
                                    for v in values_list:
                                        try:
                                            numeric_values.append(float(v))
                                        except:
                                            numeric_values.append(v)
                                    df[new_manual_feature] = numeric_values
                                    st.session_state.current_df = df
                                    st.success(f"✅ Đã thêm feature **{new_manual_feature}**!")
                                    st.dataframe(df[[new_manual_feature]].head(10), width="stretch")
                                    st.rerun()
                                except Exception as e:
                                    ui_kit.report_error("Không thêm được đặc trưng mới — dữ liệu hiện tại được giữ nguyên", e)
                            else:
                                st.error(f"❌ Số giá trị không khớp! Cần {len(df)} giá trị, nhưng bạn nhập {len(values_list)}.")
                    else:
                        st.info(f"ℹ️ Dataset quá lớn ({len(df)} dòng). Vui lòng sử dụng file CSV để thêm feature.")
        
        # Hiển thị các features đã tạo
        st.markdown("---")
        st.markdown("### 5. Kiểm tra Dữ liệu Đã xử lý")
        st.dataframe(df.head(10))
        st.info(f"Kích thước hiện tại: {df.shape[0]} dòng, {df.shape[1]} cột")

        # [NEW] Nút lưu vào kho
        if wh:
            st.markdown("---")
            st.markdown("#### Lưu Dữ liệu Đã xử lý vào Kho")
            render_save_export_buttons(df, "explored_data", wh, "explore_tab", data_type="processed")
            
        st.markdown("#### Danh Sách Features Hiện Có")
        st.dataframe(pd.DataFrame({
            'Tên Feature': df.columns.tolist(),
            'Kiểu Dữ Liệu': [str(df[col].dtype) for col in df.columns],
            'Số Giá Trị Thiếu': [df[col].isnull().sum() for col in df.columns],
            'Số Giá Trị Duy Nhất': [df[col].nunique() for col in df.columns]
        }), width="stretch", hide_index=True)
    
    
    # ========================================================================
    # BƯỚC 6: TỔNG HỢP & LƯU TRỮ (KHO DỮ LIỆU)
    # ========================================================================
    st.markdown("---")
    st_step_header("Bước 6: Tổng hợp & lưu trữ")
    
    st.markdown(
        "<div class='dss-notice dss-notice--success'>"
        "<div class='dss-notice-title'>Hoàn thành xử lý dữ liệu</div>"
        "<p class='dss-notice-body' style='margin:0;'>Dữ liệu sẵn sàng cho huấn luyện hoặc phân cụm.</p></div>",
        unsafe_allow_html=True,
    )
    
    # Hiển thị dữ liệu cuối cùng
    final_df = st.session_state.get('cleaned_df')
    if final_df is None:
        final_df = df
    
    if final_df is not None:
        st.dataframe(final_df.head(100), width="stretch")
        st.caption(f"Hiển thị 100 dòng đầu tiên của dữ liệu đã xử lý ({len(final_df)} dòng, {len(final_df.columns)} cột)")
    else:
        st.warning("⚠️ Không có dữ liệu để hiển thị.")
    
    col_save, col_export = st.columns(2)
    
    with col_save:
        if wh:
            dataset_name_input = st.text_input("Tên Dataset (để lưu vào kho):", value=f"processed_data_{datetime.now().strftime('%Y%m%d_%H%M')}")
            try:
                _final_df_sig = hashlib.md5(
                    pd.util.hash_pandas_object(final_df, index=True).values.tobytes()
                ).hexdigest()
            except Exception:
                _final_df_sig = f"{final_df.shape}_{list(final_df.columns)}"
            if st.session_state.get("_autosave_sig_final_processed") != _final_df_sig:
                try:
                    dataset_id, meta = wh.save_processed_data(
                        final_df,
                        dataset_name=dataset_name_input,
                        description="Dữ liệu sau khi xử lý và làm sạch từ Data Exploration Tab"
                    )
                    st.session_state["_autosave_sig_final_processed"] = _final_df_sig
                    st.session_state["_autosave_id_final_processed"] = dataset_id
                    st.success(f"✅ Đã tự động lưu vào Kho Dữ liệu! ID: `{dataset_id}`")
                except Exception as e:
                    ui_kit.report_error("❌ Lỗi khi tự động lưu", e)
            else:
                st.caption(f"✅ Đã tự động lưu vào Kho Dữ liệu (ID: `{st.session_state.get('_autosave_id_final_processed')}`).")
        else:
            st.warning("⚠️ Không tìm thấy kết nối Kho Dữ liệu (Data Warehouse).")
            
    with col_export:
        # Xuất Excel
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False, sheet_name='Processed Data')
        
        st.download_button(
            label="📥 Xuất file Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"processed_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.ms-excel"
        )
