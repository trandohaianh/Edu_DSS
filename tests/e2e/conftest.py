"""Fixtures cho bộ test E2E (Playwright, luồng thật theo từng vai trò).

Khởi 1 server Streamlit thật DUY NHẤT cho cả phiên test (session-scoped) —
nhanh hơn nhiều so với khởi lại cho từng test case, và đúng với cách app THẬT
được vận hành (1 tiến trình, nhiều session trình duyệt độc lập).

Mỗi test dùng 1 `browser.new_context()` RIÊNG (không chỉ 1 tab mới) để mô
phỏng đúng 2 người dùng khác nhau — Streamlit cấp session server-side theo kết
nối WebSocket của context, không theo tab.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from dss.core.data_root import DATA_ROOT_ENV_VAR  # noqa: E402

_APP_DIR = Path(__file__).resolve().parent.parent.parent
_PYTHON = str(_APP_DIR.parent / ".venv" / "Scripts" / "python.exe")

# Đường dẫn EDUDSS_DATA_ROOT của subprocess Streamlit đang chạy phiên E2E hiện
# tại — set bởi fixture `base_url`, đọc bởi fixture `e2e_test_data_root` (test
# tự-kiểm-chứng cô lập không có cách nào khác để biết giá trị này vì nó chỉ
# tồn tại trong `env` truyền cho Popen, không phải os.environ của tiến trình
# pytest cha).
_current_e2e_data_root: Path | None = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_listening(port: int, timeout: float = 40.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError(f"Server Streamlit không lên cổng {port} sau {timeout}s")


@pytest.fixture(scope="session")
def base_url():
    """PERF-002 (2026-09-17): trước bản vá này, tiến trình Streamlit con được
    spawn KHÔNG nhận EDUDSS_DATA_ROOT (kế thừa nguyên môi trường của pytest),
    nên dù pytest tự nó có cô lập hay không, SERVER THẬT vẫn ghi thẳng vào
    data_warehouse/ thật — CMS lessons/quiz/users... test E2E tạo ra tồn tại
    vĩnh viễn sau khi test xong. Chỉ xoá tay 2 filename cố định (users.json,
    ai_default_provider.json) trước/sau là băng bó phần ngọn, không phải cô
    lập thật (không đụng tới cms/lessons_registry.json, quiz_review_queue.json,
    datasets/models/training history...).

    Sửa tận gốc: tạo 1 thư mục tạm RIÊNG cho phiên E2E này và truyền qua biến
    môi trường EDUDSS_DATA_ROOT của chính subprocess Streamlit (không phải của
    tiến trình pytest cha) — server thật đọc biến này qua get_data_root() (xem
    dss/core/data_root.py) giống hệt cơ chế non-E2E, nên mọi dữ liệu E2E sinh
    ra (kể cả những gì Playwright click qua UI, không chỉ những gì pytest gọi
    trực tiếp) nằm gọn trong thư mục tạm này và biến mất khi test xong."""
    global _current_e2e_data_root
    test_data_root = Path(tempfile.mkdtemp(prefix="edudss_e2e_"))
    _current_e2e_data_root = test_data_root
    env = os.environ.copy()
    env[DATA_ROOT_ENV_VAR] = str(test_data_root)
    # Cách ly khỏi API key / Ollama THẬT trên máy chạy test (app/.env): đặt rỗng
    # để load_dotenv(override=False) không nạp key thật — kết quả E2E không phụ
    # thuộc việc máy có key hay có cài Ollama hay không.
    for _key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "HF_TOKEN",
        "OLLAMA_API_KEY",
        "OLLAMA_HOST",
    ):
        env[_key] = ""
    env["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"  # cổng không có dịch vụ -> Ollama "chưa chạy"

    port = _free_port()
    proc = subprocess.Popen(
        [_PYTHON, "-m", "streamlit", "run", "run_dss.py", "--server.port", str(port), "--server.headless", "true"],
        cwd=str(_APP_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_listening(port)
        yield f"http://localhost:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(test_data_root, ignore_errors=True)


@pytest.fixture(scope="session")
def e2e_test_data_root(base_url):
    """Đường dẫn thư mục tạm mà subprocess Streamlit của phiên E2E này đang
    dùng làm EDUDSS_DATA_ROOT — dùng cho test tự-kiểm-chứng cô lập (Section 10:
    chứng minh môi trường test THẬT SỰ có sinh dữ liệu, không phải 'cô lập giả'
    bằng cách ngừng ghi gì cả)."""
    assert _current_e2e_data_root is not None, "base_url chưa chạy — thứ tự fixture sai"
    return _current_e2e_data_root


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _wait_ready(page, timeout=45):
    start = time.time()
    last = -1
    stable = 0
    while time.time() - start < timeout:
        n = len(page.inner_text("body"))
        # Trong lúc Streamlit đang chạy lại (chỉ báo "Running" hiện), nội dung CŨ
        # cũng "đứng yên" — không được coi là đã sẵn sàng (gây lỗi chập chờn: đọc
        # nhầm trang trước khi trang mới vẽ xong).
        if page.locator('[data-testid="stStatusWidget"]').count():
            stable = 0
            last = -1
            page.wait_for_timeout(700)
            continue
        if n == last and n > 50:
            stable += 1
            if stable >= 3:
                return True
        else:
            stable = 0
        last = n
        page.wait_for_timeout(700)
    return False


@pytest.fixture
def login(browser, base_url):
    """login(username, password) -> Page đã đăng nhập, đã qua CTA trang chủ,
    sẵn sàng thao tác. Mỗi lời gọi tạo 1 browser context MỚI (mô phỏng 1 người
    dùng độc lập, không chia sẻ cookie/session với lần gọi khác trong CÙNG
    test hay test khác)."""
    contexts = []

    def _do_login(username: str, password: str, expect_success: bool = True):
        context = browser.new_context(viewport={"width": 1500, "height": 1400})
        contexts.append(context)
        page = context.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        _wait_ready(page)
        page.fill("input[aria-label='Tên đăng nhập / Mã số sinh viên']", username)
        page.fill("input[aria-label='Mật khẩu']", password)
        page.get_by_role("button", name="Đăng nhập", exact=False).click()
        page.wait_for_timeout(2000)

        if not expect_success:
            return page

        # C1.3: không còn màn giới thiệu "Bắt đầu khám phá" — sau đăng nhập
        # người dùng vào thẳng ứng dụng; chờ thanh điều hướng thật xuất hiện
        # (màn tải khởi tạo workspace có thể mất tới vài phút ở lần đầu).
        page.locator(".st-key-dss_main_nav_rail").wait_for(state="visible", timeout=240000)
        _wait_ready(page)
        return page

    yield _do_login

    for c in contexts:
        c.close()


@pytest.fixture
def wait_ready():
    return _wait_ready
