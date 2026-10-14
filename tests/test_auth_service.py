"""Regression suite — dss.services.auth_service (Authentication + RBAC decorator).

Mã hoá lại HÀNH VI THẬT đang chạy (không phải hành vi mong muốn) — nếu 1 test
ở đây fail sau này, đó là một thay đổi hành vi auth cần được XEM XÉT CÓ CHỦ Ý,
không phải regression âm thầm.
"""
from __future__ import annotations

import streamlit as st

from dss.services import auth_service


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------
def test_authenticate_seeded_admin_correct_password(isolated_users_file):
    auth_service._seed_default_accounts_if_missing()
    record = auth_service.authenticate("admin", "admin123")
    assert record is not None
    assert record["role"] == "Admin"


def test_authenticate_seeded_lecturer_correct_password(isolated_users_file):
    auth_service._seed_default_accounts_if_missing()
    record = auth_service.authenticate("giangvien", "gv123")
    assert record is not None
    assert record["role"] == "Giảng viên / CVHT"


def test_authenticate_wrong_password_rejected(isolated_users_file):
    auth_service._seed_default_accounts_if_missing()
    assert auth_service.authenticate("admin", "sai-mat-khau") is None


def test_authenticate_unknown_username_rejected(isolated_users_file):
    assert auth_service.authenticate("khong_ton_tai", "x") is None


def test_authenticate_empty_username_or_password_rejected(isolated_users_file):
    assert auth_service.authenticate("", "x") is None
    assert auth_service.authenticate("admin", "") is None
    assert auth_service.authenticate("", "") is None


def test_authenticate_username_case_insensitive(isolated_users_file):
    auth_service._seed_default_accounts_if_missing()
    record = auth_service.authenticate("ADMIN", "admin123")
    assert record is not None
    assert record["role"] == "Admin"


def test_authenticate_auto_provisions_valid_student_id(isolated_users_file):
    record = auth_service.authenticate("sv042", "sv042123")
    assert record is not None
    assert record["role"] == "Sinh viên"
    assert record["student_id"] == "SV042"
    assert record["auto_provisioned"] is True
    # Phải thật sự ghi xuống file — lần sau đăng nhập lại cùng tài khoản đó.
    assert isolated_users_file.exists()


def test_authenticate_auto_provision_wrong_password_rejected_not_created(isolated_users_file):
    """Mã số hợp lệ nhưng SAI mật khẩu quy ước (<id>123) -> KHÔNG được tự tạo
    tài khoản, KHÔNG được đăng nhập."""
    record = auth_service.authenticate("sv099", "mat-khau-sai")
    assert record is None
    # Không tạo file users.json nếu chưa từng có ai auto-provision/seed thành công.
    users = auth_service._load_users()
    assert "sv099" not in users


def test_authenticate_auto_provisioned_account_persists_across_calls(isolated_users_file):
    """Sau khi tự cấp tài khoản, lần đăng nhập kế tiếp phải dùng đúng bản ghi cũ
    (đi qua nhánh 'user đã tồn tại', không tự cấp lại / không đổi hash)."""
    first = auth_service.authenticate("sv007", "sv007123")
    second = auth_service.authenticate("sv007", "sv007123")
    assert first is not None and second is not None
    assert first["hash"] == second["hash"]
    # Sai mật khẩu ở lần đăng nhập THỨ HAI (sau khi đã có tài khoản) phải bị từ chối.
    assert auth_service.authenticate("sv007", "wrong") is None


def test_authenticate_never_logs_password(isolated_users_file, tmp_path, monkeypatch):
    """Không được để lộ mật khẩu vào file log kỹ thuật, kể cả khi log lỗi."""
    from dss.core import logging_config
    # PERF-002: logging_config không còn hằng số _LOG_DIR/_LOG_FILE mức module
    # (đã chuyển sang resolve qua get_data_root() bên trong _configure_once())
    # — buộc reconfigure với EDUDSS_DATA_ROOT trỏ vào tmp_path của chính test
    # này để log kỹ thuật ghi vào đây, không phải data_warehouse/logs thật.
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(logging_config, "_CONFIGURED", False)

    auth_service._seed_default_accounts_if_missing()
    secret_password = "s3cr3t-p4ssw0rd-should-not-leak"
    auth_service.authenticate("admin", secret_password)  # sai mật khẩu -> path log WARNING

    log_file = tmp_path / "logs" / "technical.log"
    if log_file.exists():
        content = log_file.read_text(encoding="utf-8")
        assert secret_password not in content


# ---------------------------------------------------------------------------
# require_role() — decorator chặn ở tầng hàm
# ---------------------------------------------------------------------------
def test_require_role_allows_matching_role(as_role):
    @auth_service.require_role("Admin")
    def sensitive_action():
        return "ok"

    as_role("Admin")
    assert sensitive_action() == "ok"


def test_require_role_blocks_non_matching_role(as_role):
    @auth_service.require_role("Admin")
    def sensitive_action():
        return "ok"

    as_role("Giảng viên / CVHT")
    try:
        sensitive_action()
        assert False, "đáng lẽ phải raise PermissionError"
    except PermissionError:
        pass


def test_require_role_blocks_when_not_logged_in():
    """Không có session nào (_auth_role không tồn tại) -> phải bị chặn, không
    được coi là 'role=None nên cho qua'."""
    @auth_service.require_role("Admin")
    def sensitive_action():
        return "ok"

    try:
        sensitive_action()
        assert False, "đáng lẽ phải raise PermissionError khi chưa đăng nhập"
    except PermissionError:
        pass


def test_require_role_supports_multiple_allowed_roles(as_role):
    @auth_service.require_role("Giảng viên / CVHT", "Admin")
    def shared_action():
        return "ok"

    as_role("Giảng viên / CVHT")
    assert shared_action() == "ok"
    as_role("Admin")
    assert shared_action() == "ok"
    as_role("Sinh viên")
    try:
        shared_action()
        assert False, "Sinh viên không nằm trong danh sách allowed_roles"
    except PermissionError:
        pass


# ---------------------------------------------------------------------------
# current_user() / logout()
# ---------------------------------------------------------------------------
def test_current_user_none_when_not_authenticated():
    assert auth_service.current_user() is None


def test_current_user_returns_session_identity(as_role):
    as_role("Sinh viên", username="sv001", student_id="SV001")
    user = auth_service.current_user()
    assert user == {"username": "sv001", "role": "Sinh viên", "student_id": "SV001"}


def test_logout_clears_auth_keys(as_role):
    as_role("Admin")
    auth_service.logout()
    assert auth_service.current_user() is None
    assert st.session_state.get("_auth_role") is None


def test_logout_clears_prefixed_session_state(as_role):
    as_role("Sinh viên", student_id="SV001")
    st.session_state["hub_results"] = {"fake": "data"}
    st.session_state["cluster_results_df"] = "fake_df"
    st.session_state["llm_type"] = "gemini"
    st.session_state["reminder_done_SV001_1"] = True
    st.session_state["unrelated_key_should_survive"] = "keep me"

    auth_service.logout()

    for k in ("hub_results", "cluster_results_df", "llm_type", "reminder_done_SV001_1"):
        assert k not in st.session_state
    assert st.session_state.get("unrelated_key_should_survive") == "keep me"


def test_logout_clears_api_key_widget_state(as_role):
    as_role("Admin")
    st.session_state["gemini_key_input"] = "sk-should-not-survive-logout"
    st.session_state["groq_key_input"] = "gsk-should-not-survive-logout"

    auth_service.logout()

    assert "gemini_key_input" not in st.session_state
    assert "groq_key_input" not in st.session_state
