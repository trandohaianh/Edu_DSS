"""Màn hình tải EduDSS — DUY NHẤT dùng chung cho cả 3 vai trò (Giảng viên/
Sinh viên/Admin), thay thế toàn bộ log kỹ thuật (train/test split,
GridSearchCV, KMeans, SHAP...) từng lộ ra màn hình sau đăng nhập bằng 1 trải
nghiệm tải chuyên nghiệp, nhất quán. Lớp UI này CHỈ ánh xạ (percent,
stage_key) -> câu tiếng Việt thân thiện — không biết gì, và không được phép
biết gì, về thuật toán ML bên dưới (xem `dss/core/bootstrap_service.py`)."""
from __future__ import annotations

import streamlit as st

# Ánh xạ stage_key (từ bootstrap_service, thuần kỹ thuật) -> câu tiếng Việt
# thân thiện. Đây là "bức tường" duy nhất giữa 2 lớp — nếu sau này bootstrap
# đổi tên nội bộ, chỉ cần sửa map này.
_STAGE_MESSAGES = {
    "auth_ready": "Đang xác thực phiên đăng nhập...",
    "dataset_ready": "Đang tải dữ liệu học tập...",
    "artifacts_checked": "Đang chuẩn bị dữ liệu phân tích...",
    "model_ready": "Đang kiểm tra mô hình dự đoán...",
    "role_data_ready": "Đang chuẩn bị các gợi ý cá nhân hóa...",
    "workspace_ready": "Sẵn sàng!",
}

_ROLE_TITLES = {
    "Giảng viên / CVHT": "Đang chuẩn bị bảng điều khiển giảng viên...",
    "Sinh viên": "Đang chuẩn bị không gian học tập của bạn",
    "Admin": "Đang chuẩn bị trung tâm quản trị...",
}


def get_role_title(role: str | None) -> str:
    if not role:
        return "Đang chuẩn bị không gian làm việc..."
    return _ROLE_TITLES.get(role, "Đang chuẩn bị không gian làm việc...")


def stage_message(stage_key: str, role: str | None = None, percent: int = 0) -> str:
    """Câu trạng thái thân thiện cho 1 stage — KHÔNG BAO GIỜ chứa tên thuật
    toán/thư viện/tên cột kỹ thuật, chỉ mô tả trừu tượng hoá."""
    return _STAGE_MESSAGES.get(stage_key, "Đang chuẩn bị không gian làm việc...")


_LOGO_SVG = (
    "<svg viewBox='0 0 24 24' width='26' height='26' fill='none' stroke='currentColor' "
    "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
    "<path d='M3.5 8.7 12 4l8.5 4.7L12 13.4 3.5 8.7Z' stroke-linejoin='round'></path>"
    "<path d='M6.7 10.7v4.1c0 1.9 2.4 3.4 5.3 3.4s5.3-1.5 5.3-3.4v-4.1'></path>"
    "</svg>"
)

_ERROR_ICON_SVG = (
    "<svg viewBox='0 0 24 24' width='40' height='40' fill='none' stroke='currentColor' "
    "stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>"
    "<circle cx='12' cy='12' r='9.2'></circle>"
    "<line x1='12' y1='7.5' x2='12' y2='13'></line>"
    "<circle cx='12' cy='16.3' r='0.9' fill='currentColor' stroke='none'></circle>"
    "</svg>"
)


def render_loading_screen(progress: int, message: str, role: str | None = None) -> None:
    """Vẽ TOÀN BỘ vùng nội dung bằng màn tải EduDSS — gọi hàm này thay cho
    việc để lộ sidebar/log huấn luyện/nội dung dở dang phía sau. `progress`:
    0-100. `message`: câu trạng thái thân thiện ĐÃ ánh xạ (xem `stage_message`
    ở trên) — hàm này không tự suy luận câu chữ, chỉ vẽ.

    LỖI THỰC TẾ đã sửa: hàm này được gọi NHIỀU LẦN trong CÙNG 1 lượt chạy
    script (1 lần cho mỗi mốc tiến độ: 10/30/50/70/90/100%). Dùng
    `st.container(key=...)` cố định cho nội dung này từng khiến Streamlit ném
    `StreamlitDuplicateElementKey` ở MỌI lần gọi thứ 2 trở đi (khoá phần tử
    dùng chung cho toàn bộ 1 lượt script, không phải theo từng placeholder) —
    lỗi này bị nuốt im lặng bởi try/except ở bootstrap_service, khiến MÀN TẢI
    KHÔNG BAO GIỜ THỰC SỰ HIỆN RA dù bootstrap chạy đúng ngầm phía sau. Không
    cần `key=` ở đây — nội dung THUẦN HIỂN THỊ (không widget tương tác), nằm
    trong `st.empty()` của nơi gọi (`main.py`), tự đủ để "thay thế nội dung
    trước đó" mà không cần khoá phần tử. Marker `.dss-loading-screen` dùng để
    CSS `:has()` phát hiện đúng màn hình này (giống cơ chế `.dss-login-marker`
    của trang đăng nhập), không phải Streamlit key."""
    pct = max(0, min(100, int(progress)))
    role_title = get_role_title(role)
    st.markdown(
        f"""
        <div class="dss-loading-screen">
            <div class="dss-loading-logo-chip">{_LOGO_SVG}</div>
            <div class="dss-loading-brand">EduDSS</div>
            <div class="dss-loading-brand-sub">Educational Decision Support System</div>
            <div class="dss-loading-title">{role_title}</div>
            <div class="dss-loading-subtitle">Việc này thường chỉ mất vài giây.</div>
            <div class="dss-loading-progress-row">
                <div class="dss-loading-progress-track">
                    <div class="dss-loading-progress-fill" style="width:{pct}%;"></div>
                </div>
                <div class="dss-loading-progress-pct">{pct}%</div>
            </div>
            <div class="dss-loading-status-line">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_error_screen(error_code: str = "EDSS-INIT-001") -> tuple[bool, bool]:
    """Màn lỗi khi khởi tạo workspace thất bại — KHÔNG hiện traceback cho
    người dùng (traceback thật đã được log kỹ thuật ở nơi gọi). Trả về
    (retry_clicked, logout_clicked) để `main.py` xử lý điều hướng thật."""
    with st.container(key="dss_loading_screen_error"):
        st.markdown(
            f"""
            <div class="dss-loading-logo-chip dss-loading-logo-chip-error">{_LOGO_SVG}</div>
            <div class="dss-loading-error-icon">{_ERROR_ICON_SVG}</div>
            <div class="dss-loading-title">Không thể chuẩn bị hệ thống</div>
            <div class="dss-loading-subtitle">Đã xảy ra lỗi khi tải dữ liệu hoặc mô hình. Dữ liệu đã lưu không bị thay đổi — bạn có thể thử lại hoặc đăng xuất.</div>
            """,
            unsafe_allow_html=True,
        )
        col_retry, col_logout = st.columns(2, gap="small")
        with col_retry:
            retry_clicked = st.button("Thử lại", key="dss_loading_retry_btn", type="primary", width="stretch")
        with col_logout:
            logout_clicked = st.button("Đăng xuất", key="dss_loading_logout_btn", width="stretch")
        st.markdown(
            f"<div class='dss-loading-error-code'>Mã lỗi: {error_code}</div>",
            unsafe_allow_html=True,
        )
    return retry_clicked, logout_clicked
