"""FINAL PRODUCTION GAP CLOSURE Phần 43 — chụp ảnh màn hình THẬT các trang
chính (Login + 3 vai trò) để có bằng chứng thị giác thật trước khi tuyên bố
"visually accepted" (đúng nguyên tắc Phần 50: không được nói đã accept nếu
chưa nhìn screenshot).

An toàn: dùng ĐÚNG cơ chế `tests/e2e/conftest.py` đã có sẵn — cổng do OS tự
cấp (`_free_port()`, KHÔNG BAO GIỜ trùng cổng giả lập 72h), EDUDSS_DATA_ROOT
CÔ LẬP trong thư mục tạm riêng (không đụng data_warehouse/ thật), tự dọn dẹp
(terminate subprocess + xoá thư mục tạm) khi xong dù có lỗi giữa chừng.

Chạy: PYTHONIOENCODING=utf-8 python tools/capture_ui_screenshots.py
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

sys.path.insert(0, ".")
from dss.core.data_root import DATA_ROOT_ENV_VAR  # noqa: E402

from playwright.sync_api import sync_playwright

_APP_DIR = Path(__file__).resolve().parent.parent
_PYTHON = str(_APP_DIR.parent / ".venv" / "Scripts" / "python.exe")
_OUT_DIR = _APP_DIR / "reports" / "production_readiness" / "ui_screenshots"


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
    raise RuntimeError(f"Server Streamlit khong len cong {port} sau {timeout}s")


def _wait_ready(page, timeout=45):
    start = time.time()
    last = -1
    stable = 0
    while time.time() - start < timeout:
        n = len(page.inner_text("body"))
        if n == last and n > 50:
            stable += 1
            if stable >= 3:
                return True
        else:
            stable = 0
        last = n
        page.wait_for_timeout(700)
    return False


def _click_nav(page, label_substr: str) -> bool:
    try:
        btn = page.get_by_role("button", name=label_substr, exact=False).first
        if btn.count() == 0:
            return False
        btn.click()
        page.wait_for_timeout(1800)
        _wait_ready(page)
        return True
    except Exception as e:
        print(f"  [WARN] khong bam duoc nav '{label_substr}': {type(e).__name__}")
        return False


def main():
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    test_data_root = Path(tempfile.mkdtemp(prefix="edudss_ui_screenshot_"))
    env = os.environ.copy()
    env[DATA_ROOT_ENV_VAR] = str(test_data_root)
    env.pop("DATABASE_URL", None)
    env.pop("PGVECTOR_URL", None)

    port = _free_port()
    print(f"Khoi dong Streamlit tren cong tam {port} (EDUDSS_DATA_ROOT co lap: {test_data_root})")
    proc = subprocess.Popen(
        [_PYTHON, "-m", "streamlit", "run", "run_dss.py",
         "--server.port", str(port), "--server.headless", "true"],
        cwd=str(_APP_DIR), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait_listening(port)
        base_url = f"http://localhost:{port}"

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                # --- LOGIN ---
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                page = ctx.new_page()
                page.goto(base_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                _wait_ready(page)
                page.screenshot(path=str(_OUT_DIR / "00_login.png"), full_page=True)
                print("Da chup: 00_login.png")
                ctx.close()

                accounts = [
                    ("sinh_vien", "SV001", "sv001123"),
                    ("giang_vien", "giangvien", "gv123"),
                    ("admin", "admin", "admin123"),
                ]
                nav_targets = {
                    "sinh_vien": ["Trang chủ", "Dự đoán", "Tư vấn", "Phân cụm"],
                    "giang_vien": ["Trang chủ", "Dashboard", "Sinh viên", "Tài liệu"],
                    "admin": ["Trang chủ", "Tài liệu", "Cài đặt"],
                }
                for role_key, username, password in accounts:
                    print(f"--- Vai tro: {role_key} ({username}) ---")
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = ctx.new_page()
                    page.goto(base_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1200)
                    _wait_ready(page)
                    try:
                        page.fill("input[aria-label='Tên đăng nhập / Mã số sinh viên']", username)
                        page.fill("input[aria-label='Mật khẩu']", password)
                        page.get_by_role("button", name="Đăng nhập", exact=False).click()
                        page.wait_for_timeout(2500)
                        _wait_ready(page, timeout=60)
                    except Exception as e:
                        print(f"  [LOI] dang nhap that bai cho {role_key}: {type(e).__name__}: {e}")
                        page.screenshot(path=str(_OUT_DIR / f"{role_key}_LOGIN_FAILED.png"), full_page=True)
                        ctx.close()
                        continue

                    page.screenshot(path=str(_OUT_DIR / f"01_{role_key}_landing.png"), full_page=True)
                    print(f"  Da chup: 01_{role_key}_landing.png")

                    # Trang chu (landing) can bam "Bat dau kham pha" truoc khi
                    # sidebar dieu huong day du xuat hien (_app_started gate).
                    _click_nav(page, "Bắt đầu khám phá")
                    page.screenshot(path=str(_OUT_DIR / f"02_{role_key}_app_home.png"), full_page=True)
                    print(f"  Da chup: 02_{role_key}_app_home.png")

                    for i, target in enumerate(nav_targets.get(role_key, []), start=3):
                        ok = _click_nav(page, target)
                        fname = f"0{i}_{role_key}_{target.replace(' ', '_')}.png"
                        page.screenshot(path=str(_OUT_DIR / fname), full_page=True)
                        print(f"  Da chup: {fname} (nav_click_ok={ok})")

                    ctx.close()
            finally:
                browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(test_data_root, ignore_errors=True)
        print("Da dung Streamlit tam va don dep EDUDSS_DATA_ROOT tam.")


if __name__ == "__main__":
    main()
