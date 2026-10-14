"""Trang "Báo cáo hệ thống" — CHỈ Admin (xem `dss/core/roles.py: TAB_ACCESS`).

Toàn bộ số liệu lấy từ dữ liệu thật đã ghi trong kho (`warehouse`) — không
hard-code số liệu, không tạo dữ liệu giả để khớp mockup. Không gọi thêm bất kỳ
service ghi/sửa nào — trang này CHỈ ĐỌC.
"""
import os

from dss.config import *  # noqa: F403
from dss import config as dss_config
from dss.config import GEMINI_AVAILABLE, GROQ_AVAILABLE, OLLAMA_AVAILABLE, OPENAI_AVAILABLE
from dss.core.models import _check_ollama_running
from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, filter_tabs_for_role
from dss.services import auth_service
from dss.services.model_service import compute_lecturer_dashboard_overview, model_lifecycle_badge_text
from dss.tabs import ui_kit


def _dir_size_mb(path: str) -> float:
    """Dung lượng thật (MB) của 1 thư mục trong kho — quét đệ quy bằng
    os.path.getsize, không ước lượng/giả định. Trả 0.0 nếu thư mục không tồn
    tại hoặc rỗng (không phải lỗi)."""
    total = 0
    if not path or not os.path.isdir(path):
        return 0.0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return total / (1024 * 1024)


def _operational_checks(datasets, models, df, b_status):
    """Danh sách cảnh báo vận hành — MỖI mục suy ra từ trạng thái thật, không
    có mục "thành công" mặc định."""
    from dss.core.data_helpers import is_synthetic_data

    checks = []
    n_production = sum(1 for m in models if m.get("is_production"))
    if df is None:
        checks.append(("warning", "Chưa có dữ liệu học tập", "Chưa có bộ dữ liệu nào được nạp cho phiên làm việc."))
    elif is_synthetic_data(df):
        checks.append(("warning", "Đang dùng dữ liệu mô phỏng",
                       "Số liệu trên hệ thống chưa phản ánh sinh viên thật."))
    if n_production == 0:
        checks.append(("warning", "Chưa có mô hình Production",
                       "Dự đoán và cảnh báo rủi ro chưa khả dụng cho Giảng viên/Sinh viên."))
    checks.append(("neutral", "LMS/CMS chưa kết nối",
                   "Chưa có kết nối tới hệ thống quản lý học tập thật của Trường."))
    providers_checked = [st.session_state.get(f"_admin_ai_health_{k}") for k in ("gemini", "groq", "openai")]
    if not any(providers_checked):
        checks.append(("pending", "Chưa kiểm tra kết nối AI",
                       "Trạng thái nhà cung cấp AI chưa được kiểm tra trong phiên này (trang Cấu hình AI)."))
    elif not any(h and h.get("category") == "READY" for h in providers_checked):
        checks.append(("warning", "Không có nhà cung cấp AI trực tuyến nào sẵn sàng",
                       "Các chức năng dựa trên tính toán và quy tắc vẫn hoạt động; phần diễn giải bằng AI bị hạn chế."))
    if b_status and b_status.get("alert_message"):
        checks.append(("danger" if "exceeded" in b_status.get("status", "") else "warning",
                       "Ngân sách AI", ui_kit.strip_decoration(b_status["alert_message"])))
    return checks


def admin_reports_tab(warehouse, df=None, as_home=False):
    """`as_home=True`: bản rút gọn dùng làm Trang chủ Admin (Tổng quan)."""
    if as_home:
        ui_kit.page_header("Tổng quan hệ thống", subtitle="Người dùng, dữ liệu, mô hình và những việc cần xử lý.")
    else:
        ui_kit.page_header("Báo cáo & giám sát", subtitle="Số liệu vận hành, mô hình và chi phí AI của toàn hệ thống.")

    if warehouse is None:
        ui_kit.error_state(
            "Không khởi tạo được kho dữ liệu",
            "Chưa thể đọc số liệu hệ thống. Dữ liệu đã lưu không bị ảnh hưởng.",
            support_hint="Thử tải lại trang; nếu vẫn lỗi, kiểm tra cấu hình lưu trữ.",
        )
        return

    try:
        datasets = warehouse.list_datasets()
        models = warehouse.list_models()
        consultations = warehouse.get_history("advisor", limit=10000)
        user_counts = auth_service.count_users_by_role()
    except Exception:
        ui_kit.error_state(
            "Không đọc được số liệu hệ thống",
            "Kho dữ liệu hoặc kho tài khoản không phản hồi. Không có dữ liệu nào bị thay đổi.",
            support_hint="Thử tải lại trang sau ít phút.",
        )
        return
    n_production = sum(1 for m in models if m.get("is_production"))
    n_total_users = sum(user_counts.values())

    from dss.services import token_tracker
    try:
        b_status = token_tracker.get_system_budget_status()
    except Exception:
        b_status = None

    overview = None
    if df is not None and not as_home:
        gpa_col = next(
            (c for c in ['diem_ky_sau', 'diem_ky_nay', 'final_score', 'gpa_previous', 'gpa', 'score'] if c in df.columns),
            None,
        )
        if gpa_col:
            try:
                overview = compute_lecturer_dashboard_overview(
                    df, warehouse, st.session_state.get("current_dataset_id"), gpa_col
                )
            except Exception:
                overview = None
    n_high_risk = overview["risk_counts"]["cao"] if overview and overview.get("status") == "ok" else None

    ui_kit.kpi_row(
        [
            ("Người dùng", n_total_users, "Tổng số tài khoản trong hệ thống"),
            ("Sinh viên trong dữ liệu", f"{len(df):,}" if df is not None else "—", "Bộ dữ liệu đang mở"),
            ("Mô hình Production", n_production, "Mô hình đang dùng cho dự đoán", "success" if n_production else "warning"),
            ("Lượt tư vấn AI", len(consultations), "Tổng số lượt đã lưu"),
        ]
    )

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    col_checks, col_status = st.columns([1.2, 1], gap="medium")
    with col_checks:
        with st.container(border=True):
            ui_kit.card_title("Cần xử lý")
            checks = _operational_checks(datasets, models, df, b_status)
            st.markdown(
                "".join(
                    f"<div class='dss-list-row'><div style='min-width:0;flex:1;'>"
                    f"<div class='dss-list-row-main' style='white-space:normal;'>{title}</div>"
                    f"<div class='dss-list-row-meta'>{detail}</div></div>"
                    f"{ui_kit.badge_html({'warning': 'Cần chú ý', 'danger': 'Nghiêm trọng', 'pending': 'Chưa kiểm tra', 'neutral': 'Chưa có'}.get(kind, kind), kind)}</div>"
                    for kind, title, detail in checks
                ),
                unsafe_allow_html=True,
            )
    with col_status:
        with st.container(border=True):
            ui_kit.card_title("Trạng thái thành phần")
            _providers = (("gemini", "Gemini"), ("groq", "Groq"), ("openai", "OpenAI"))
            rows = []
            for _key, _name in _providers:
                _health = st.session_state.get(f"_admin_ai_health_{_key}")
                if not _health:
                    badge = ui_kit.status_html("not_checked")
                elif _health.get("category") == "READY":
                    badge = ui_kit.status_html("ready", _health.get("friendly_label"))
                else:
                    badge = ui_kit.badge_html(_health.get("friendly_label", "Không khả dụng"), "danger")
                rows.append((f"AI · {_name}", badge))
            if dss_config._local_llm_libs_loaded:
                _embed = ui_kit.status_html("verified", "Đã nạp") if dss_config.HF_AVAILABLE else ui_kit.status_html("failed", "Lỗi tải thư viện")
            else:
                _embed = ui_kit.badge_html("Đã cài, chưa nạp", "pending") if dss_config.HF_AVAILABLE else ui_kit.status_html("not_configured", "Chưa cài")
            rows.append(("Tìm kiếm tài liệu (embedding)", _embed))
            rows.append(("Tích hợp LMS/CMS", ui_kit.status_html("not_configured", "Chưa kết nối")))
            rows.append(("Mô hình dự đoán", ui_kit.badge_html(f"{n_production} Production", "success") if n_production else ui_kit.status_html("warning", "Chưa có")))
            st.markdown(
                "".join(f"<div class='dss-kv'><span class='dss-kv-key'>{k}</span><span class='dss-kv-value'>{v}</span></div>" for k, v in rows),
                unsafe_allow_html=True,
            )
            st.caption("Trạng thái AI lấy từ lần \"Kiểm tra kết nối\" gần nhất ở trang Cấu hình AI.")

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        ui_kit.card_title("Hoạt động gần đây")
        try:
            activities = warehouse.get_recent_activities(limit=8 if as_home else 20)
        except Exception:
            activities = None
        if activities is None:
            ui_kit.error_state("Không đọc được nhật ký hoạt động", "Không có dữ liệu nào bị thay đổi.")
        elif not activities:
            ui_kit.empty_state("Chưa có hoạt động nào được ghi nhận.")
        else:
            _act_df = pd.DataFrame(
                [{"Thời gian": a.get("timestamp", ""), "Hành động": a.get("action", ""), "Chi tiết": a.get("details", "")} for a in activities]
            )
            st.dataframe(_act_df, width="stretch", hide_index=True, height=min(320, 38 + 35 * len(_act_df)))

    if as_home:
        return

    # ------------------------------------------------------------------
    # Báo cáo chi tiết (chỉ trang "Báo cáo & giám sát")
    # ------------------------------------------------------------------
    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    ui_kit.subsection_header("Dữ liệu & mô hình")
    if n_high_risk is not None:
        ui_kit.kpi_row([
            ("Sinh viên rủi ro cao (dữ liệu hiện tại)", n_high_risk, ui_kit.RELATIVE_RISK_DISCLAIMER, "danger"),
            ("Bộ dữ liệu trong kho", len(datasets)),
            ("Mô hình trong kho", len(models)),
        ])
        st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
    col_left, col_right = st.columns(2, gap="medium")
    with col_left:
        with st.container(border=True):
            ui_kit.card_title("Bộ dữ liệu theo loại")
            if not datasets:
                ui_kit.empty_state("Chưa có bộ dữ liệu nào trong kho.")
            else:
                type_counts = pd.Series([d.get("data_type", "other") for d in datasets]).value_counts()
                fig = px.bar(x=type_counts.index, y=type_counts.values, labels={"x": "Loại dữ liệu", "y": "Số lượng"})
                fig.update_traces(marker_color="#1A73E8")
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with col_right:
        with st.container(border=True):
            ui_kit.card_title("Mô hình theo trạng thái")
            if not models:
                ui_kit.empty_state("Chưa có mô hình nào trong kho.")
            else:
                # MODELREG-001: dùng chung hàm phân loại 3 trạng thái với warehouse_tab.py.
                status_counts = pd.Series([model_lifecycle_badge_text(m) for m in models]).value_counts()
                fig = px.bar(x=status_counts.index, y=status_counts.values, labels={"x": "Trạng thái", "y": "Số lượng"})
                fig.update_traces(marker_color="#1A73E8")
                fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    col_perf, col_storage = st.columns([1.3, 1], gap="medium")
    with col_perf:
        with st.container(border=True):
            ui_kit.card_title("Chỉ số mô hình Production")
            _prod_models = [m for m in models if m.get("is_production") and m.get("metrics", {}).get("type") != "clustering"]
            if not _prod_models:
                ui_kit.empty_state("Chưa có mô hình Production.")
            else:
                for m in _prod_models:
                    st.markdown(f"**{m['model_name']}** · mục tiêu `{m.get('target_col', '—')}`")
                    _metrics = m.get("metrics", {}) or {}
                    _keys = [k for k in ("R2 Score", "RMSE", "MAE", "Accuracy", "F1 Score", "Precision", "Recall") if k in _metrics]
                    st.markdown(
                        "".join(
                            f"<div class='dss-kv'><span class='dss-kv-key'>{'R² (tập kiểm tra)' if _k == 'R2 Score' else _k}</span>"
                            f"<span class='dss-kv-value'>{f'{_metrics[_k]:.3f}' if isinstance(_metrics[_k], (int, float)) else _metrics[_k]}</span></div>"
                            for _k in _keys[:4]
                        ),
                        unsafe_allow_html=True,
                    )
                st.caption("Đo trên tập kiểm tra của dữ liệu huấn luyện — không phải kiểm định độc lập trên sinh viên thật.")
    with col_storage:
        with st.container(border=True):
            ui_kit.card_title("Dung lượng lưu trữ")
            _storage_items = [
                ("Bộ dữ liệu", _dir_size_mb(getattr(warehouse, "data_path", None))),
                ("Mô hình", _dir_size_mb(getattr(warehouse, "models_path", None))),
                ("Chỉ mục tài liệu", _dir_size_mb(getattr(warehouse, "embeddings_path", None))),
            ]
            st.markdown(
                "".join(f"<div class='dss-kv'><span class='dss-kv-key'>{_label}</span><span class='dss-kv-value'>{_mb:.1f} MB</span></div>" for _label, _mb in _storage_items),
                unsafe_allow_html=True,
            )

    st.markdown("<div class='dss-spacer-16'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        ui_kit.card_title("Sử dụng AI & chi phí")
        if b_status is None:
            ui_kit.error_state("Không đọc được số liệu token", "Không có dữ liệu nào bị thay đổi.")
        else:
            if b_status.get("alert_message"):
                st.warning(ui_kit.strip_decoration(b_status["alert_message"]))
            tk1, tk2, tk3, tk4 = st.columns(4)
            tk1.metric("Tokens hôm nay", f"{b_status['daily_tokens']:,}")
            tk2.metric("Chi phí hôm nay (USD)", f"${b_status['daily_cost']:.4f}", help=f"Ngân sách ngày: ${b_status['daily_budget']:.2f}")
            tk3.metric("Tokens tháng này", f"{b_status['monthly_tokens']:,}")
            tk4.metric("Chi phí tháng (USD)", f"${b_status['monthly_cost']:.4f}", help=f"Ngân sách tháng: ${b_status['monthly_budget']:.2f}")
            st.caption("Chi phí là ước tính từ số token ghi nhận ở LLM Gateway, không phải hoá đơn của nhà cung cấp.")
