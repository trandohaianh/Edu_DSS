"""Đăng nhập bằng Google qua OIDC native của Streamlit (st.login / st.user / st.logout).

Cấu hình nằm trong `.streamlit/secrets.toml` (mục [auth] và [auth.google]); trong container,
`ops/write_streamlit_secrets.py` sinh file này từ biến môi trường EDUDSS_GOOGLE_CLIENT_ID,
EDUDSS_GOOGLE_CLIENT_SECRET, EDUDSS_PUBLIC_URL và EDUDSS_AUTH_COOKIE_SECRET. Thiếu cấu hình thì
nút Google không hiện và cổng mật khẩu chạy như cũ.

Streamlit lo luồng OAuth (code flow + PKCE, kiểm tra chữ ký ID token của Google, cookie phiên
đã ký). Module này chỉ ánh xạ danh tính Google đã xác minh sang tài khoản EduDSS
(auth_service.resolve_google_user): Google chứng minh quyền sở hữu email, còn vai trò và phạm vi
dữ liệu vẫn do tài khoản EduDSS quyết định.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from dss.core.logging_config import get_logger

_logger = get_logger(__name__)
_ERROR_KEY = "_google_signin_error"


def configured() -> bool:
    try:
        auth = st.secrets.get("auth")
        google = auth.get("google") if auth else None
        return bool(google and google.get("client_id") and google.get("client_secret") and auth.get("redirect_uri"))
    except Exception:
        return False


def _claims() -> Optional[dict]:
    try:
        user = st.user
        if not user.get("is_logged_in"):
            return None
        return {k: user.get(k) for k in ("email", "email_verified", "name", "sub", "iss")}
    except Exception:
        return None


def pending_identity():
    """Nếu trình duyệt vừa đăng nhập Google: trả về tài khoản EduDSS tương ứng (hoặc None).

    Từ chối (email chưa gắn, bị khoá...) -> lưu thông báo để cổng đăng nhập hiển thị."""
    claims = _claims()
    if claims is None:
        return None
    from dss.core import metrics
    from dss.services import auth_service

    try:
        record = auth_service.resolve_google_user(claims)
    except auth_service.GoogleSignInRejected as exc:
        st.session_state[_ERROR_KEY] = str(exc)
        metrics.record_login("google", "rejected_" + exc.code)
        _logger.warning("Google sign-in bị từ chối: code=%s", exc.code)
        return None
    st.session_state.pop(_ERROR_KEY, None)
    metrics.record_login("google", "success")
    return record


def rejection_message() -> Optional[str]:
    return st.session_state.get(_ERROR_KEY) if _claims() is not None else None


def render_button() -> None:
    if not configured():
        return
    st.markdown("<div class='dss-login-divider'><span>hoặc</span></div>", unsafe_allow_html=True)
    message = rejection_message()
    if message:
        st.error(message)
        if st.button("Dùng tài khoản Google khác", key="google_switch_account", width="stretch"):
            st.session_state.pop(_ERROR_KEY, None)
            st.logout()
        return
    if st.button("Đăng nhập với Google", key="google_login_button", icon=":material/account_circle:", width="stretch"):
        st.login("google")


def logout() -> None:
    """Đăng xuất cả phiên Google (cookie OIDC của Streamlit) nếu có."""
    try:
        if st.user.get("is_logged_in"):
            st.logout()
    except Exception:
        pass
