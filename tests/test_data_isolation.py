"""PERF-002 — chứng minh cơ chế cô lập dữ liệu test hoạt động THẬT, không phải
'cô lập giả' (test đơn giản ngừng ghi gì cả rồi coi như đã cô lập).

3 nhóm test:
1. Đơn vị cho `get_data_root()`/`is_isolated_test_environment()` (dss/core/data_root.py).
2. Chứng minh 1 repository thật (cms_lecture_repository) khi ghi dữ liệu trong
   phiên pytest này thực sự nằm trong thư mục cô lập, và tuyệt đối không xuất
   hiện trong data_warehouse/ thật (đọc thẳng đường dẫn cố định, không qua
   get_data_root(), để không tự lừa chính mình).
3. Chứng minh autouse fixture `_isolated_data_root` (tests/conftest.py) đang
   thực sự active trong phiên hiện tại — nếu ai đó vô tình xoá/tắt fixture đó,
   test này phải FAIL ngay thay vì để PERF-002 âm thầm tái diễn.
"""

from __future__ import annotations

from pathlib import Path

from dss.core.data_root import DATA_ROOT_ENV_VAR, get_data_root, is_isolated_test_environment

_REAL_DATA_WAREHOUSE = Path(__file__).resolve().parent.parent / "data_warehouse"


def test_isolated_session_is_active_for_this_test_run():
    """Nếu fixture autouse `_isolated_data_root` (tests/conftest.py) bị xoá
    hoặc tắt nhầm, test này FAIL ngay — đây chính là 'phanh tay' cho PERF-002."""
    assert is_isolated_test_environment(), (
        "EDUDSS_DATA_ROOT không được set trong phiên pytest này — cơ chế cô lập "
        "test (PERF-002) đã bị tắt/xoá, mọi test khác đang ghi thẳng vào "
        "data_warehouse/ thật."
    )


def test_get_data_root_resolves_env_var_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv(DATA_ROOT_ENV_VAR, str(tmp_path))
    assert get_data_root() == tmp_path


def test_get_data_root_defaults_to_real_app_dir_when_unset(monkeypatch):
    """Runtime BÌNH THƯỜNG (không set biến môi trường) phải ra đúng
    data_warehouse/ thật — hành vi mặc định cho người dùng thật KHÔNG đổi."""
    monkeypatch.delenv(DATA_ROOT_ENV_VAR, raising=False)
    assert get_data_root() == _REAL_DATA_WAREHOUSE
    assert not is_isolated_test_environment()


def test_cms_repository_writes_into_isolated_root_not_real_app():
    """Ghi 1 lesson thật qua đúng code path production (không mock), rồi chứng
    minh 2 điều: (a) nó nằm trong thư mục cô lập hiện tại, (b) tuyệt đối không
    xuất hiện trong lessons_registry.json THẬT (đọc thẳng path cố định)."""
    from dss.services import cms_lecture_repository as cms_repository

    probe_course_id = "ISOLATION_PROBE_COURSE_do_not_leak"
    lesson = cms_repository.create_or_get_lesson(
        course_id=probe_course_id,
        lesson_id="isolation_probe_lesson",
        topic_id="probe",
        lecturer_id="probe_lecturer",
        title="Isolation probe — should never reach the real app",
    )
    assert lesson.course_id == probe_course_id

    # (a) thực sự nằm trong thư mục cô lập của get_data_root() hiện tại.
    isolated_registry = get_data_root() / "cms" / "lessons_registry.json"
    assert isolated_registry.exists()
    assert probe_course_id in isolated_registry.read_text(encoding="utf-8")

    # (b) tuyệt đối không rò rỉ vào data_warehouse/cms/lessons_registry.json THẬT.
    real_registry = _REAL_DATA_WAREHOUSE / "cms" / "lessons_registry.json"
    if real_registry.exists():
        assert probe_course_id not in real_registry.read_text(encoding="utf-8"), (
            "RÒ RỈ PERF-002: bản ghi test đã xuất hiện trong lessons_registry.json THẬT."
        )
    # Thư mục cô lập phải khác thư mục thật (nếu trùng thì test này vô nghĩa).
    assert get_data_root() != _REAL_DATA_WAREHOUSE


def test_auth_service_users_file_isolated_by_default():
    """Không cần fixture isolated_users_file riêng — autouse EDUDSS_DATA_ROOT
    đã đủ để users.json (kể cả tài khoản Sinh viên auto-provision khi login)
    không chạm data_warehouse/users.json thật."""
    from dss.services import auth_service

    auth_service.authenticate("sv999", "sv999123")  # auto-provision demo
    isolated_users = get_data_root() / "users.json"
    assert isolated_users.exists()

    real_users = _REAL_DATA_WAREHOUSE / "users.json"
    if real_users.exists():
        assert "sv999" not in real_users.read_text(encoding="utf-8").lower()


def test_data_warehouse_class_defaults_into_isolated_root():
    """DataWarehouse() không tham số phải tự resolve qua get_data_root() —
    không cần ai truyền base_path tường minh mới được cô lập."""
    from dss.core.warehouse import DataWarehouse

    wh = DataWarehouse()
    assert Path(wh.base_path) == get_data_root()
    assert Path(wh.base_path) != _REAL_DATA_WAREHOUSE
