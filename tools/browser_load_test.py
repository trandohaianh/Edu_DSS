"""Bước 8 — thử tải N phiên trình duyệt thật đồng thời vào EduDSS (Streamlit).

Mỗi phiên = 1 browser context riêng (cookie/phiên riêng), đăng nhập 1 tài khoản sinh viên demo khác nhau
(svNNN, mật khẩu theo quy ước demo cục bộ), chờ Trang chủ hiện, rồi bấm sang 1 trang khác và chờ hiện.
Đo: thời gian mở trang đăng nhập, thời gian từ bấm Đăng nhập tới khi Trang chủ hiện, thời gian chuyển trang.

Chạy: python tools/browser_load_test.py BASE_URL N [start_index]   (đặt PYTHONIOENCODING=utf-8 trên Windows)
Kết quả bước 8: docs/testing/STEP8_SYSTEM_TEST_REPORT.md §4.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time

from playwright.async_api import async_playwright

BASE, N = sys.argv[1], int(sys.argv[2])
START = int(sys.argv[3]) if len(sys.argv) > 3 else 1
TIMEOUT_MS = 180_000


async def one(browser, i, results, start_gate):
    user = f"sv{i:03d}"
    rec = {"user": user, "ok": False}
    ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
    page = await ctx.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    try:
        await start_gate.wait()
        t0 = time.perf_counter()
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_selector("input[aria-label='Mật khẩu']")
        rec["open_login_s"] = time.perf_counter() - t0
        await page.fill("input[aria-label='Tên đăng nhập / Mã số sinh viên']", user)
        await page.fill("input[aria-label='Mật khẩu']", user + "123")
        t1 = time.perf_counter()
        await page.get_by_role("button", name="Đăng nhập", exact=False).click()
        await page.get_by_text(f"Xin chào, {user.upper()}").wait_for()
        rec["login_to_home_s"] = time.perf_counter() - t1
        t2 = time.perf_counter()
        await page.get_by_text("Trợ lý AI", exact=True).first.click()
        await page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=TIMEOUT_MS
        )
        await page.wait_for_timeout(300)
        await page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=TIMEOUT_MS
        )
        rec["navigate_s"] = time.perf_counter() - t2
        rec["ok"] = True
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        results.append(rec)
        await ctx.close()


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return round(values[k], 2)


async def main():
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--renderer-process-limit=60"])
        gate = asyncio.Event()
        tasks = [asyncio.create_task(one(browser, START + k, results, gate)) for k in range(N)]
        await asyncio.sleep(1)
        wall0 = time.perf_counter()
        gate.set()
        await asyncio.gather(*tasks)
        wall = time.perf_counter() - wall0
        await browser.close()
    ok = [r for r in results if r["ok"]]
    summary = {
        "sessions": N,
        "ok": len(ok),
        "errors": N - len(ok),
        "error_rate_pct": round(100 * (N - len(ok)) / N, 1),
        "wall_s": round(wall, 1),
    }
    for key in ("open_login_s", "login_to_home_s", "navigate_s"):
        vals = [r[key] for r in results if key in r]
        summary[key] = {
            "p50": pct(vals, 50),
            "p95": pct(vals, 95),
            "max": pct(vals, 100),
            "mean": round(statistics.mean(vals), 2) if vals else None,
        }
    summary["sample_errors"] = sorted({r["error"] for r in results if "error" in r})[:5]
    print(json.dumps(summary, ensure_ascii=False, indent=1))


asyncio.run(main())
