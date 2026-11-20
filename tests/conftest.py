"""Fixtures dùng chung cho bộ test hồi quy EduDSS.

PERF-002 (2026-09-17): trước bản vá này, việc cô lập dữ liệu test khỏi
`data_warehouse/` thật là OPT-IN từng test (`isolated_users_file`,
`isolated_default_provider_file`, `warehouse`) — bất kỳ test nào không tự yêu
cầu 1 trong 3 fixture đó (vd. toàn bộ tests/test_learning_explainer*.py, không
có fixture nào cho cms_lecture_repository/learning_explainer's stores) sẽ ghi
THẲNG vào kho dữ liệu thật đang dùng cho dev server. Đây là nguyên nhân gốc
khiến data_warehouse/cms/lessons_registry.json tích lũy 743 bản ghi test.

Sửa tận gốc: mọi service/repository (xem dss/core/data_root.py) giờ resolve
đường dẫn ghi-được qua `get_data_root()`, đọc biến môi trường
EDUDSS_DATA_ROOT MỖI LẦN cần dùng (không cache mức module). Fixture
`_isolated_data_root` dưới đây set biến đó tới 1 thư mục tạm DUY NHẤT cho toàn
bộ phiên pytest, TRƯỚC khi bất kỳ test nào chạy (autouse, session-scoped) —
nên mặc định MỌI test tự động cô lập hoàn toàn, không cần khai báo gì thêm.
Các fixture opt-in cũ (isolated_users_file, isolated_default_provider_file,
warehouse) vẫn giữ lại cho test muốn 1 file/thư mục RIÊNG (khác nhau giữa các
test trong cùng phiên), nhưng KHÔNG còn là cơ chế chống-ghi-vào-app-thật duy
nhất — lớp phòng thủ chính giờ là autouse ở dưới.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Found during Workstream A+B+C+CPU integration verification (2026-09-22):
# dss/core/logging_config.py's _configure_once() binds its RotatingFileHandler
# to get_data_root() at FIRST USE, memoized for the whole process (see that
# module's own docstring — the invariant it documents is "as long as
# EDUDSS_DATA_ROOT is set before the first logger use"). pytest's COLLECTION
# phase imports most of dss/ (many modules call get_logger(__name__) at
# module scope) BEFORE any fixture ever runs — including the session-scoped
# _isolated_data_root fixture below. In a worktree that already had a
# data_warehouse/logs/technical.log file (i.e. every worktree that had ever
# run anything before), this was invisible: the pollution guard's directory
# comparison only tracks filenames, not content, for the "logs" bucket, so
# more bytes appended to an already-existing file went undetected. In a
# genuinely fresh worktree (no pre-existing technical.log), the guard
# correctly caught it — real log content was written to the real
# data_warehouse/ before test isolation had a chance to apply. Setting
# EDUDSS_DATA_ROOT here, at the very top of the root conftest module (the
# first thing pytest imports), closes the gap at its actual source instead
# of narrowing what the pollution guard checks.
os.environ.setdefault("EDUDSS_DATA_ROOT", tempfile.mkdtemp(prefix="edudss_pytest_collection_"))
# EDUDSS_ENV không đặt = production (fail closed). Bộ test chạy ở chế độ "test" trừ khi test tự đặt khác.
os.environ.setdefault("EDUDSS_ENV", "test")

_APP_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import streamlit as st  # noqa: E402

from dss.core.data_root import DATA_ROOT_ENV_VAR  # noqa: E402

_REAL_DATA_WAREHOUSE = _APP_ROOT / "data_warehouse"

# Các file JSON đơn (so sánh theo nội dung — băm sha256) và các thư mục nhiều
# file (so sánh theo DANH SÁCH tên file tương đối — phát hiện file mới bị thêm/
# xoá, không quan tâm nội dung bên trong từng file mô hình/dataset nhị phân).
_REAL_STORE_FILES = [
    "users.json",
    "ai_default_provider.json",
    "subscription.json",
    "ai_token_usage.json",
    "cms/lessons_registry.json",
    "cms/quiz_review_queue.json",
    "cms/interaction_log.json",
    "cms/misconception_records.json",
]
_REAL_STORE_DIRS = [
    "models",
    "datasets",
    "raw_data",
    "processed_data",
    "training_data",
    "evaluation_data",
    "metadata",
    "history",
    "embeddings",
    "vector_stores",
    "logs",
]


def _snapshot_real_data_warehouse() -> dict:
    """PERF-002 Section 14 — chụp trạng thái CỦA data_warehouse/ THẬT (đường
    dẫn cố định, KHÔNG qua get_data_root(), để không bị ảnh hưởng bởi
    EDUDSS_DATA_ROOT) — dùng để chứng minh test không hề đụng vào nó."""
    import hashlib

    snapshot: dict = {"files": {}, "dirs": {}}
    for rel in _REAL_STORE_FILES:
        f = _REAL_DATA_WAREHOUSE / rel
        if f.exists():
            snapshot["files"][rel] = hashlib.sha256(f.read_bytes()).hexdigest()
        else:
            snapshot["files"][rel] = None
    for rel in _REAL_STORE_DIRS:
        d = _REAL_DATA_WAREHOUSE / rel
        if d.exists():
            snapshot["dirs"][rel] = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
        else:
            snapshot["dirs"][rel] = []
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def _pollution_guard():
    """PERF-002 Section 14 — bảo vệ VĨNH VIỄN chống PERF-002 tái diễn: chụp
    trạng thái data_warehouse/ THẬT trước phiên pytest, chạy toàn bộ test, rồi
    so sánh lại — bất kỳ thay đổi nào (kể cả chỉ 1 bản ghi mới trong 1 JSON,
    hoặc 1 file mới trong thư mục models/datasets/...) đều FAIL rõ ràng, nêu
    đích danh store nào bị đụng vào, thay vì âm thầm trôi qua như trước đây."""
    before = _snapshot_real_data_warehouse()
    yield
    after = _snapshot_real_data_warehouse()
    changed_files = {
        rel: (before["files"][rel], after["files"][rel])
        for rel in _REAL_STORE_FILES
        if before["files"][rel] != after["files"][rel]
    }
    changed_dirs = {
        rel: {
            "added": sorted(set(after["dirs"][rel]) - set(before["dirs"][rel])),
            "removed": sorted(set(before["dirs"][rel]) - set(after["dirs"][rel])),
        }
        for rel in _REAL_STORE_DIRS
        if set(before["dirs"][rel]) != set(after["dirs"][rel])
    }
    assert not changed_files and not changed_dirs, (
        "PERF-002 REGRESSION: test suite đã ghi vào data_warehouse/ THẬT thay vì "
        "thư mục cô lập (EDUDSS_DATA_ROOT). Store bị đụng: "
        f"files={changed_files!r} dirs={changed_dirs!r}"
    )


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_root():
    """PERF-002: cô lập TOÀN BỘ tiến trình pytest khỏi data_warehouse/ thật.

    Set EDUDSS_DATA_ROOT TRƯỚC test đầu tiên (autouse, session-scoped) sang 1
    thư mục tạm — mọi store (CMS lesson registry, quiz queue, interaction log,
    users.json, token usage, subscription, vector store, DataWarehouse dataset/
    model/training history...) tự động ghi vào đó thay vì kho dữ liệu thật,
    vì tất cả đều resolve đường dẫn qua get_data_root() tại thời điểm gọi, chứ
    không phải hằng số tính 1 lần lúc import."""
    previous = os.environ.get(DATA_ROOT_ENV_VAR)
    tmp_root = Path(tempfile.mkdtemp(prefix="edudss_pytest_"))
    os.environ[DATA_ROOT_ENV_VAR] = str(tmp_root)
    try:
        yield tmp_root
    finally:
        if previous is None:
            os.environ.pop(DATA_ROOT_ENV_VAR, None)
        else:
            os.environ[DATA_ROOT_ENV_VAR] = previous
        shutil.rmtree(tmp_root, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_session_state():
    """`st.session_state` là 1 singleton toàn cục ngay cả ở bare mode (ngoài
    runtime Streamlit thật) — xoá sạch TRƯỚC và SAU mỗi test để test này không
    vô tình đọc/để lại state cho test khác. Đây cũng chính là hành vi ta đang
    kiểm chứng cho "session isolation" — mỗi phiên (ở đây là mỗi test) phải bắt
    đầu từ trạng thái sạch."""
    st.session_state.clear()
    yield
    st.session_state.clear()


@pytest.fixture
def as_role():
    """Giả lập 1 phiên đã đăng nhập với vai trò cho trước — set đúng key mà
    `auth_service`/`require_role` đọc (`_auth_role`), không phải tự chế key
    riêng cho test."""

    def _set(role: str, username: str = "test_user", student_id: str | None = None):
        st.session_state["_authenticated"] = True
        st.session_state["_auth_role"] = role
        st.session_state["_auth_username"] = username
        st.session_state["_auth_student_id"] = student_id

    return _set


@pytest.fixture
def isolated_users_file(tmp_path, monkeypatch):
    """Trỏ `auth_service._users_path()` sang file tạm RIÊNG cho test này (khác
    thư mục tạm dùng chung cả phiên của `_isolated_data_root` ở trên) — dùng
    khi 1 test cần 1 users.json sạch, không lẫn với auto-provision của test
    khác trong CÙNG phiên pytest."""
    from dss.services import auth_service

    fake_path = tmp_path / "users.json"
    monkeypatch.setattr(auth_service, "_users_path", lambda: fake_path)
    return fake_path


@pytest.fixture
def isolated_default_provider_file(tmp_path, monkeypatch):
    """Trỏ `admin_ai_config._config_path()` sang file tạm riêng cho test này."""
    from dss.services import admin_ai_config

    fake_path = tmp_path / "ai_default_provider.json"
    monkeypatch.setattr(admin_ai_config, "_config_path", lambda: fake_path)
    return fake_path


@pytest.fixture
def warehouse(tmp_path):
    """1 DataWarehouse thật (đúng class đang dùng trong app) nhưng trỏ vào thư
    mục tạm — không đụng `data_warehouse/` thật, nhưng vẫn thực thi đúng code
    thật (không mock)."""
    from dss.core.warehouse import DataWarehouse

    return DataWarehouse(base_path=str(tmp_path / "data_warehouse"))
