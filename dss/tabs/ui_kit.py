"""Bộ component UI dùng chung (C1.3 design system) — THUẦN TRÌNH BÀY, không
chứa logic nghiệp vụ, không gọi service/warehouse.

Mọi màu sắc đến từ token CSS trong `dss/styles/main.css` (class `.dss-*`) —
không còn mã màu hex rải rác trong style inline, nên cùng một component tự
đúng ở cả giao diện Sáng lẫn Tối. Chữ ký hàm giữ nguyên để không phải sửa các
nơi gọi hiện có.
"""

import html as _html
import re

import streamlit as st

# Bộ icon line-art (kiểu Feather) — giữ lại cho các nơi gọi cũ dùng
# `_icon_svg_span`; màu lấy từ `currentColor` (tự theo token của phần tử cha).
_ICON_SVG = {
    "home": "<path d='M3 9.5L12 3l9 6.5'/><path d='M5 9.5V20a1 1 0 0 0 1 1h3v-6h6v6h3a1 1 0 0 0 1-1V9.5'/>",
    "users": "<path d='M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2'/><circle cx='9' cy='7' r='4'/>"
    "<path d='M23 21v-2a4 4 0 0 0-3-3.87'/><path d='M16 3.13a4 4 0 0 1 0 7.75'/>",
    "cap": "<path d='M22 10L12 5 2 10l10 5 10-5z'/><path d='M6 12v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5'/>",
    "alert": "<path d='M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z'/>"
    "<line x1='12' y1='9' x2='12' y2='13'/><line x1='12' y1='17' x2='12.01' y2='17'/>",
    "target": "<circle cx='12' cy='12' r='10'/><circle cx='12' cy='12' r='6'/><circle cx='12' cy='12' r='2'/>",
    "chart": "<line x1='18' y1='20' x2='18' y2='10'/><line x1='12' y1='20' x2='12' y2='4'/>"
    "<line x1='6' y1='20' x2='6' y2='14'/>",
    "layers": "<polygon points='12 2 2 7 12 12 22 7 12 2'/><polyline points='2 17 12 22 22 17'/>"
    "<polyline points='2 12 12 17 22 12'/>",
    "clock": "<circle cx='12' cy='12' r='10'/><polyline points='12 6 12 12 16 14'/>",
    "edit": "<path d='M12 20h9'/><path d='M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z'/>",
    "search": "<circle cx='11' cy='11' r='8'/><line x1='21' y1='21' x2='16.65' y2='16.65'/>",
    "award": "<circle cx='12' cy='8' r='7'/><polyline points='8.21 13.89 7 23 12 20 17 23 15.79 13.88'/>",
    "chat": "<path d='M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7"
    "a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z'/>",
    "database": "<ellipse cx='12' cy='5' rx='9' ry='3'/><path d='M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5'/>"
    "<path d='M3 12c0 1.66 4 3 9 3s9-1.34 9-3'/>",
    "file": "<path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><polyline points='14 2 14 8 20 8'/>",
    "book": "<path d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/><path d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/>",
    "settings": "<circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 "
    "2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 "
    "9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 "
    "1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 "
    "0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 "
    "1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0 "
    "-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'/>",
}
_EMOJI_TO_ICON_KEY = {
    "🏠": "home",
    "👥": "users",
    "🎓": "cap",
    "⚠️": "alert",
    "🎯": "target",
    "📊": "chart",
    "🧩": "layers",
    "🕐": "clock",
    "✏️": "edit",
    "🔍": "search",
    "🏆": "award",
    "🤖": "chat",
    "💬": "chat",
    "🗄️": "database",
    "📁": "database",
    "📄": "file",
    "📚": "book",
    "⚙️": "settings",
    "🔧": "settings",
}
_LEADING_EMOJI_RE = re.compile(r"^(\S+)\s+")
# Ký tự trang trí đầu chuỗi (emoji/biểu tượng) — trạng thái giờ dùng chấm màu +
# chữ, nên bỏ biểu tượng lặp lại ở đầu nhãn (vd. "✅ Đã lưu" -> "Đã lưu").
_DECORATIVE_PREFIX_RE = re.compile(r"^(?:[☀-➿\U0001F000-\U0001FAFF⬀-⯿️‍]+\s*)+")


def _icon_svg_span(icon, size=18, color="currentColor"):
    """HTML span icon line-art nếu `icon` khớp 1 emoji đã ánh xạ; nếu không
    khớp, trả về icon gốc (tương thích ngược với nơi gọi cũ)."""
    key = _EMOJI_TO_ICON_KEY.get((icon or "").strip())
    if not key:
        return icon
    return (
        f"<span style='display:inline-flex;vertical-align:-4px;color:{color};'>"
        f"<svg viewBox='0 0 24 24' width='{size}' height='{size}' fill='none' "
        f"stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
        f"{_ICON_SVG[key]}</svg></span>"
    )


def strip_decoration(text) -> str:
    """Bỏ emoji trang trí ở đầu chuỗi hiển thị (không đổi nội dung chữ)."""
    return _DECORATIVE_PREFIX_RE.sub("", str(text or "")).strip()


# Ánh xạ kind cũ -> biến thể trạng thái trong design system.
_STATUS_KINDS = {
    "success": "success",
    "verified": "success",
    "ready": "success",
    "warning": "warning",
    "danger": "danger",
    "error": "danger",
    "failed": "danger",
    "info": "info",
    "neutral": "neutral",
    "violet": "neutral",
    "purple": "neutral",
    "pending": "pending",
    "unavailable": "neutral",
}

# Nhãn chuẩn cho các trạng thái hệ thống — màu KHÔNG bao giờ là tín hiệu duy
# nhất: mỗi trạng thái luôn có chữ đi kèm.
STATUS_PRESETS = {
    "verified": ("Đã xác minh", "success"),
    "ready": ("Sẵn sàng", "success"),
    "pending": ("Đang chờ", "pending"),
    "warning": ("Cần chú ý", "warning"),
    "unavailable": ("Không khả dụng", "neutral"),
    "not_configured": ("Chưa cấu hình", "neutral"),
    "insufficient_evidence": ("Chưa đủ căn cứ", "warning"),
    "failed": ("Thất bại", "danger"),
    "not_checked": ("Chưa kiểm tra", "pending"),
}


def badge_html(text, kind="neutral"):
    """Chuỗi HTML 1 nhãn trạng thái (chấm màu + chữ) — ghép vào markdown khác."""
    variant = _STATUS_KINDS.get(kind, "neutral")
    label = _html.escape(strip_decoration(text)) if "<" not in str(text) else strip_decoration(text)
    return f"<span class='dss-status dss-status--{variant}'>{label}</span>"


def status_html(status_key: str, label: str | None = None) -> str:
    """Nhãn trạng thái chuẩn theo STATUS_PRESETS (vd. "ready", "not_configured")."""
    preset_label, kind = STATUS_PRESETS.get(status_key, (status_key, "neutral"))
    return badge_html(label or preset_label, kind)


def render_badge(text, kind="neutral"):
    st.markdown(badge_html(text, kind), unsafe_allow_html=True)


status_badge = render_badge


def render_status(status_key: str, label: str | None = None):
    st.markdown(status_html(status_key, label), unsafe_allow_html=True)


def page_header(title, subtitle=None, badge_text=None, badge_kind="neutral", icon=None):
    """Tiêu đề cấp trang. `icon` giữ trong chữ ký để tương thích ngược — không render."""
    badge = f" {badge_html(badge_text, badge_kind)}" if badge_text else ""
    subtitle_html = f"<p class='dss-page-subtitle'>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"<div class='dss-page-header'><div class='dss-page-header-row'>"
        f"<h1 class='dss-page-title'>{strip_decoration(title)}</h1>{badge}</div>{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def section_header(title, subtitle=None, icon=None):
    """Tiêu đề mở đầu 1 trang nội dung (mỗi tab dùng 1 lần ở đầu trang).

    Hiển thị ở cấp "tiêu đề trang" vì đây là tiêu đề chính của từng trang
    trong ứng dụng. `icon` giữ trong chữ ký để tương thích ngược — không render."""
    subtitle_html = f"<p class='dss-page-subtitle'>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"<div class='dss-page-header'><h1 class='dss-page-title'>{strip_decoration(title)}</h1>{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def subsection_header(title, subtitle=None, icon=None):
    """Tiêu đề 1 khu vực bên trong trang."""
    subtitle_html = f"<p class='dss-section-subtitle'>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"<div class='dss-section-header'><h2 class='dss-section-title'>{strip_decoration(title)}</h2>"
        f"{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def card_title(title):
    st.markdown(f"<div class='dss-card-title'>{strip_decoration(title)}</div>", unsafe_allow_html=True)


_KPI_KIND_MARKER_CLASS = {
    "success": "dss-kpi-marker-success",
    "warning": "dss-kpi-marker-warning",
    "danger": "dss-kpi-marker-danger",
    "purple": "dss-kpi-marker-default",
}


def kpi_row(items):
    """items: list of (label, value), (label, value, help_text) hoặc
    (label, value, help_text, kind). Chỉ trạng thái (success/warning/danger)
    mới có vạch màu bên trái — KPI thường không tô màu trang trí."""
    if not items:
        return
    import hashlib

    _row_key = "dss_kpi_" + hashlib.md5(repr([str(i[0]) for i in items]).encode("utf-8")).hexdigest()[:10]
    with st.container(key=_row_key):
        _kpi_columns(items)


def _kpi_columns(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        help_text = item[2] if len(item) > 2 else None
        kind = item[3] if len(item) > 3 else None
        # Không tô vạch trạng thái cho ô chưa có giá trị ("—") — màu trạng thái
        # chỉ xuất hiện khi thật sự có số liệu để đánh giá.
        if str(value).strip() in ("", "—", "-", "None", "nan"):
            kind = None
        with col:
            marker_class = _KPI_KIND_MARKER_CLASS.get(kind, "dss-kpi-marker-default")
            st.markdown(f"<div class='dss-marker {marker_class}'></div>", unsafe_allow_html=True)
            st.metric(strip_decoration(label), value, help=help_text)


def metric_card(label, value, delta=None, help_text=None, kind=None, height=115):
    """Thẻ metric đơn. `height` giữ để tương thích ngược (dùng làm min-height)."""
    kind_class = f" metric-card--{kind}" if kind in ("success", "warning", "danger") else ""
    delta_html = ""
    if delta:
        direction = "down" if str(delta).startswith("-") else "up"
        delta_html = f"<span class='metric-card-delta metric-card-delta--{direction}'>{delta}</span>"
    help_html = f"<div class='metric-card-footer'>{help_text}</div>" if help_text else ""
    st.markdown(
        f"<div class='metric-card{kind_class}' style='min-height:{int(height)}px;'>"
        f"<div class='metric-card-label'>{strip_decoration(label)}</div>"
        f"<div style='display:flex;align-items:baseline;'>"
        f"<span class='metric-card-value'>{value}</span>{delta_html}</div>"
        f"{help_html}</div>",
        unsafe_allow_html=True,
    )


_NOTICE_TITLES = {
    "info": "Thông báo",
    "warning": "Cần chú ý",
    "danger": "Sự cố",
    "success": "Hoàn tất",
}


def alert_box(message, kind="info", title=None):
    """Thông báo nội tuyến (info / warning / danger / success) — luôn có tiêu đề chữ."""
    kind = kind if kind in _NOTICE_TITLES else "info"
    title_text = title or _NOTICE_TITLES[kind]
    st.markdown(
        f"<div class='dss-notice dss-notice--{kind}' role='status'>"
        f"<div class='dss-notice-title'>{strip_decoration(title_text)}</div>"
        f"<div class='dss-notice-body'>{message}</div></div>",
        unsafe_allow_html=True,
    )


def render_synthetic_data_banner(df):
    """E-1: nhãn CỐ ĐỊNH khi dữ liệu đang dùng là MÔ PHỎNG (Synthetic/Demo) —
    hiển thị ở đầu mọi trang phân tích/dự đoán đọc dữ liệu đó để không ai nhầm
    số liệu giả là số liệu sinh viên thật."""
    from dss.core.data_helpers import is_synthetic_data

    if is_synthetic_data(df):
        data_strip(
            "Dữ liệu mô phỏng (demo)",
            "số liệu, biểu đồ và tư vấn trên trang này không phản ánh sinh viên thật.",
        )


def data_strip(label, text, kind="info"):
    """Nhãn 1 dòng mảnh ở đầu trang (thay cho khung st.info to chiếm chỗ)."""
    st.markdown(
        f"<div class='dss-data-strip dss-data-strip-{kind}'><strong>{label}</strong> · {text}</div>",
        unsafe_allow_html=True,
    )


def empty_state(message, icon=None, hint=None):
    """Trạng thái rỗng trung thực — dùng khi thật sự chưa có dữ liệu.
    `icon` giữ trong chữ ký để tương thích ngược — không render."""
    hint_html = f"<div class='dss-empty-hint'>{hint}</div>" if hint else ""
    st.markdown(
        f"<div class='dss-empty' role='status'><div class='dss-empty-title'>{strip_decoration(message)}</div>"
        f"{hint_html}</div>",
        unsafe_allow_html=True,
    )


def error_state(title, message, support_hint=None):
    """Trạng thái lỗi thân thiện — không hiện traceback. `message` nên nói rõ
    chuyện gì xảy ra và dữ liệu có an toàn không; `support_hint` là việc người
    dùng có thể làm tiếp."""
    support = f"<div class='dss-error-hint'>{support_hint}</div>" if support_hint else ""
    st.markdown(
        f"<div class='dss-error' role='alert'><div class='dss-error-title'>{strip_decoration(title)}</div>"
        f"<div class='dss-error-body'>{message}</div>{support}</div>",
        unsafe_allow_html=True,
    )


def report_error(message, exc=None, level="error"):
    """Báo lỗi cho người dùng KHÔNG kèm nội dung exception thô (có thể lộ
    đường dẫn, câu SQL, cấu hình) — chi tiết kỹ thuật chỉ ghi vào log."""
    from dss.core.logging_config import get_logger

    get_logger("dss.ui").error("UI error: %s", strip_decoration(message), exc_info=exc if exc is not None else False)
    text = strip_decoration(message).rstrip(" .:") + ". Chi tiết kỹ thuật đã được ghi vào nhật ký hệ thống."
    (st.warning if level == "warning" else st.error)(text)


def unavailable_state(title, message, support_hint=None):
    """Dịch vụ tạm không khả dụng (timeout / provider lỗi) — khác với lỗi dữ liệu."""
    alert_box(
        message + (f"<br><span class='dss-muted'>{support_hint}</span>" if support_hint else ""),
        kind="warning",
        title=title,
    )


def cold_start_aware_message(llm_integration, base_message: str) -> str:
    """Nối thêm cảnh báo "lần đầu có thể chậm" vào message của `st.spinner(...)`
    nếu mô hình embedding CHƯA từng được nạp trong tiến trình này
    (COLDSTART-001)."""
    try:
        already_loaded = bool(getattr(llm_integration, "embedding_model", None))
    except Exception:
        already_loaded = False
    if already_loaded:
        return base_message
    return (
        f"{base_message} Lần mở đầu tiên có thể mất thêm khoảng 1 phút để "
        "khởi tạo mô hình — vui lòng chờ, hệ thống không bị treo."
    )


def loading_state(message="Đang xử lý dữ liệu học tập..."):
    """Trạng thái đang tải (tĩnh) cho khu vực chưa có dữ liệu trả về."""
    st.markdown(
        f"<div class='dss-loading' role='status' aria-live='polite'>"
        f"<span class='dss-spinner' aria-hidden='true'></span><span>{strip_decoration(message)}</span></div>",
        unsafe_allow_html=True,
    )


def recommendation_card(
    issue: str,
    evidence: str,
    priority: str,
    action: str,
    timeframe: str,
    expected_result: str,
    recheck_condition: str = None,
    source: str = None,
):
    """Thẻ khuyến nghị học tập có cấu trúc (vấn đề / bằng chứng / hành động)."""
    priority_kind = (
        "danger"
        if priority in ("Cao", "Khẩn cấp", "HIGH")
        else ("warning" if priority in ("Trung bình", "MEDIUM") else "info")
    )
    priority_label = (
        "Ưu tiên cao"
        if priority_kind == "danger"
        else ("Ưu tiên trung bình" if priority_kind == "warning" else "Ưu tiên thông thường")
    )

    recheck_html = (
        f"<div class='dss-recommendation-action'><b>Đánh giá lại:</b> {recheck_condition}</div>"
        if recheck_condition
        else ""
    )
    source_html = f"<div class='dss-recommendation-meta'>Cơ sở dữ liệu: {source}</div>" if source else ""

    st.markdown(
        f"<div class='dss-recommendation-card'>"
        f"<div class='dss-recommendation-head'>"
        f"<div class='dss-recommendation-title'>{strip_decoration(issue)}</div>"
        f"<div>{badge_html(priority_label, priority_kind)}</div></div>"
        f"<div class='dss-recommendation-evidence'><b>Bằng chứng:</b><br>{evidence}</div>"
        f"<div class='dss-recommendation-action'><b>Hành động:</b> {action}</div>"
        f"{recheck_html}"
        f"<div class='dss-recommendation-footer'>"
        f"<div><b>Thời gian:</b> {timeframe}</div>"
        f"<div><b>Kỳ vọng:</b> {expected_result}</div></div>"
        f"{source_html}</div>",
        unsafe_allow_html=True,
    )


def diagnosis_card(
    status_title: str,
    summary: str = None,
    evidences: list = None,
    concerns: list = None,
    recommendation: str = None,
    kind: str = "info",
):
    """Thẻ chẩn đoán học tập — không lộ enum kỹ thuật."""
    ev_list_html = ""
    if evidences:
        ev_items = "".join(f"<li>{ev}</li>" for ev in evidences)
        ev_list_html = (
            f"<div class='dss-diagnosis-evidence'><b>Bằng chứng:</b>"
            f"<ul style='margin:4px 0 0;padding-left:20px;'>{ev_items}</ul></div>"
        )
    concern_html = ""
    if concerns:
        c_items = "".join(f"<li>{c}</li>" for c in concerns)
        concern_html = (
            f"<div class='dss-diagnosis-concern'><b>Điểm cần chú ý:</b>"
            f"<ul style='margin:4px 0 0;padding-left:20px;'>{c_items}</ul></div>"
        )
    rec_html = (
        f"<div class='dss-recommendation-action'><b>Khuyến nghị:</b> {recommendation}</div>" if recommendation else ""
    )
    summary_html = f"<div class='dss-diagnosis-desc'>{summary}</div>" if summary else ""
    st.markdown(
        f"<div class='dss-diagnosis-card'>"
        f"<div class='dss-diagnosis-title'>{strip_decoration(status_title)}</div>"
        f"{summary_html}{ev_list_html}{concern_html}{rec_html}</div>",
        unsafe_allow_html=True,
    )


def source_citation_badge(source_name: str, section: str = None, page: str = None):
    """Nhãn trích dẫn nguồn (RAG/CMS)."""
    details = []
    if section:
        details.append(section)
    if page:
        details.append(f"trang {page}" if not str(page).lower().startswith("slide") else str(page))
    detail_str = f" ({', '.join(details)})" if details else ""
    return f"<span class='dss-citation'>{source_name}{detail_str}</span>"


def coming_soon(title, description, icon=None):
    """Khối đánh dấu rõ ràng chức năng CHƯA có service/dữ liệu thật đứng sau —
    thay vì dựng số liệu giả. `icon` giữ để tương thích ngược — không render."""
    st.markdown(
        f"<div class='dss-notice dss-notice--info'>"
        f"<div class='dss-notice-title'>{strip_decoration(title)} "
        f"<span class='dss-status dss-status--pending dss-status--plain'>Chưa có trong phiên bản này</span></div>"
        f"<div class='dss-notice-body'>{description}</div></div>",
        unsafe_allow_html=True,
    )


# FINAL REMEDIATION PASS Mục 5 (K-2): mọi "Mức rủi ro" được tính bằng PHÂN VỊ
# điểm dự đoán trong CHÍNH lớp/tập dữ liệu hiện tại — KHÔNG phải ngưỡng tuyệt
# đối. Dùng chung 1 câu duy nhất ở mọi nơi hiển thị rủi ro.
RELATIVE_RISK_DISCLAIMER = (
    "Mức rủi ro so sánh **tương đối trong lớp/tập dữ liệu hiện tại** (theo phân vị "
    "điểm dự đoán) — không phải ngưỡng tuyệt đối hay đánh giá chính thức của nhà trường."
)

# C1.1 (claim safety): R² KHÔNG phải "độ chính xác" và không hiển thị dạng %;
# nguồn dữ liệu (mô phỏng hay dữ liệu đã tải lên) luôn được nêu rõ.
RISK_RELATIVE_CAPTION = "Nhóm 25% có điểm dự đoán thấp nhất lớp (xếp hạng tương đối, không phải xác suất)"


def model_metric_display(metric_name, metric_value, df=None):
    """Trả về (nhãn, giá trị, chú thích) cho thẻ chỉ số mô hình."""
    from dss.core.data_helpers import is_synthetic_data

    if metric_name == "R2 Score":
        label = "R² (tập kiểm tra)"
    elif metric_name:
        label = f"{metric_name} (tập kiểm tra)"
    else:
        label = "Chỉ số mô hình"
    value = f"{metric_value:.3f}" if isinstance(metric_value, (int, float)) else "—"
    if df is not None and is_synthetic_data(df):
        caption = "Đo trên dữ liệu MÔ PHỎNG — không phải độ chính xác đã kiểm chứng trên sinh viên thật"
    else:
        caption = "Đo trên tập kiểm tra của dữ liệu đang dùng — chưa phải kiểm định độc lập"
    return label, value, caption
