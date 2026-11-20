"""Regression suite — RBAC ở TẦNG HÀM trên các thao tác nhạy cảm cụ thể.

Khác với test_auth_service.py (kiểm tra decorator require_role() một cách
tổng quát), file này gọi THẲNG từng hàm nhạy cảm thật trong app (bỏ qua UI
hoàn toàn) và xác nhận nó tự chặn đúng vai trò — đúng tinh thần "kiểm tra ở cả
navigation lẫn chức năng bên trong, không chỉ ẩn UI" đã yêu cầu.

Ma trận quyền đang mã hoá (đúng theo code hiện tại, KHÔNG phải suy diễn):
    - Admin duy nhất: xem/nhập API key thật (Cấu hình nguồn AI Admin), test kết
      nối provider, đặt/đổi model Production (model_registry.promote/rollback),
      đặt provider/model mặc định hệ thống (admin_ai_config).
    - Giảng viên + Admin: bộ chọn provider rút gọn (không xem key), So sánh AI.
    - Sinh viên: không quyền nào ở trên.
"""

from __future__ import annotations

import pytest

from dss.services import admin_ai_config, model_registry
from dss.tabs import ai_advisor

ALL_ROLES = ["Sinh viên", "Giảng viên / CVHT", "Admin"]


def _expect_permission_error_or_pass(fn, should_allow):
    """Gọi fn(); nếu should_allow=False bắt buộc phải PermissionError. Nếu
    should_allow=True, PermissionError là FAIL nhưng lỗi khác (vd. thiếu tham
    số hợp lệ vì ta truyền None/[] giả) được coi là 'đã qua được lớp auth'."""
    try:
        fn()
    except PermissionError:
        assert not should_allow, "bị chặn nhầm dù role được phép"
        return
    except Exception:
        assert should_allow, "lẽ ra phải bị PermissionError nhưng lại chạy tiếp và lỗi kiểu khác"
        return
    assert should_allow, "lẽ ra phải bị PermissionError nhưng lại chạy xong"


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_admin_provider_config_is_admin_only(as_role, role, should_allow):
    as_role(role)
    _expect_permission_error_or_pass(lambda: ai_advisor._render_admin_provider_config(None, [], {}), should_allow)


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_connection_test_is_admin_only(as_role, role, should_allow):
    as_role(role)
    _expect_permission_error_or_pass(
        lambda: ai_advisor._run_connection_test(None, "huggingface", "x", "", "", "Hugging Face (Local/Cloud)"),
        should_allow,
    )


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", True),
        ("Admin", True),
    ],
)
def test_teacher_provider_picker_open_to_lecturer_and_admin(as_role, role, should_allow):
    as_role(role)
    _expect_permission_error_or_pass(lambda: ai_advisor._render_teacher_provider_picker(None, {}), should_allow)


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", True),
        ("Admin", True),
    ],
)
def test_compare_ai_open_to_lecturer_and_admin(as_role, role, should_allow):
    as_role(role)
    _expect_permission_error_or_pass(lambda: ai_advisor._run_compare_ai(None, [], [], 5.0, {}, []), should_allow)


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_admin_ai_config_set_default_provider_is_admin_only(
    as_role, role, should_allow, isolated_default_provider_file
):
    as_role(role)
    _expect_permission_error_or_pass(
        lambda: admin_ai_config.set_default_provider("gemini", "gemini-3.6-flash"), should_allow
    )


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_admin_ai_config_clear_default_provider_is_admin_only(
    as_role, role, should_allow, isolated_default_provider_file
):
    as_role(role)
    _expect_permission_error_or_pass(lambda: admin_ai_config.clear_default_provider(), should_allow)


def test_admin_ai_config_get_default_provider_has_no_role_restriction(as_role, isolated_default_provider_file):
    """Đọc cấu hình mặc định là hành động ĐỌC, không nhạy cảm (không lộ secret
    nào) — mọi vai trò (kể cả chưa đăng nhập) đều gọi được, không có decorator
    nào chặn. Ghi lại rõ ràng để không ai lỡ thêm nhầm require_role vào đây."""
    assert admin_ai_config.get_default_provider() is None  # chưa set gì


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_model_registry_promote_is_admin_only(as_role, role, should_allow, warehouse):
    as_role(role)
    _expect_permission_error_or_pass(lambda: model_registry.promote(warehouse, "khong-ton-tai"), should_allow)


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("Sinh viên", False),
        ("Giảng viên / CVHT", False),
        ("Admin", True),
    ],
)
def test_model_registry_rollback_is_admin_only(as_role, role, should_allow, warehouse):
    as_role(role)
    _expect_permission_error_or_pass(lambda: model_registry.rollback(warehouse, "khong-ton-tai"), should_allow)


def test_model_registry_read_actions_have_no_role_restriction(as_role, warehouse):
    """get_production/list_versions là ĐỌC — không có decorator nào chặn (mọi
    vai trò cần xem được model đang dùng để dự đoán)."""
    as_role("Sinh viên")
    assert model_registry.get_production(warehouse, "ds1", "target1") == (None, None)
    assert model_registry.list_versions(warehouse, "ds1", "target1") == []
