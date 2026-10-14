"""PERF-002 (E2E) — chứng minh subprocess Streamlit thật (không chỉ tiến trình
pytest) cũng ghi vào thư mục cô lập, không phải data_warehouse/ thật.

Trước bản vá: base_url() spawn Streamlit KHÔNG truyền EDUDSS_DATA_ROOT trong
env của subprocess -> mọi thao tác qua UI (đăng nhập tự tạo tài khoản Sinh
viên, nạp bài giảng CMS...) ghi thẳng vào data_warehouse/ thật, dù bản thân
tiến trình pytest có được cô lập hay không (2 tiến trình khác nhau, mỗi tiến
trình có os.environ riêng)."""
from __future__ import annotations

from pathlib import Path

_REAL_DATA_WAREHOUSE = Path(__file__).resolve().parent.parent.parent / "data_warehouse"


def test_e2e_server_subprocess_uses_isolated_data_root(e2e_test_data_root, login):
    """Đăng nhập 1 tài khoản Sinh viên MỚI (kích hoạt auto-provision ghi vào
    users.json) qua UI thật, rồi xác nhận bản ghi đó nằm trong thư mục cô lập
    của SUBPROCESS (không phải tiến trình pytest), và không rò rỉ vào
    data_warehouse/users.json thật."""
    probe_username = "sv888"
    login(probe_username, "sv888123")

    isolated_users_file = e2e_test_data_root / "users.json"
    assert isolated_users_file.exists(), (
        "Subprocess Streamlit không ghi users.json vào EDUDSS_DATA_ROOT của nó — "
        "kiểm tra base_url() có truyền env=... cho subprocess.Popen hay không."
    )
    assert probe_username in isolated_users_file.read_text(encoding="utf-8").lower()

    real_users_file = _REAL_DATA_WAREHOUSE / "users.json"
    if real_users_file.exists():
        assert probe_username not in real_users_file.read_text(encoding="utf-8").lower(), (
            "RÒ RỈ PERF-002 (E2E): tài khoản Sinh viên do E2E tự tạo đã xuất hiện "
            "trong users.json THẬT."
        )
