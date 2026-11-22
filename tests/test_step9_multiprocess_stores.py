"""Bước 9: nhiều tiến trình Streamlit (sau Caddy) cùng ghi các kho JSON cục bộ mà không mất bản ghi."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from dss.core.file_lock import InterProcessLock

_APP_ROOT = Path(__file__).resolve().parent.parent
PROCESSES = 4
WRITES_PER_PROCESS = 25

_CHILD = textwrap.dedent(
    """
    import sys
    from dss.services import token_tracker
    from dss.core.warehouse import DataWarehouse

    tag, writes, wh_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    wh = DataWarehouse(base_path=wh_path)
    print("ready", flush=True)
    sys.stdin.readline()  # mọi tiến trình bắt đầu ghi cùng lúc
    for i in range(writes):
        token_tracker.record_usage(f"{tag}-{i}", "Sinh viên", "advisor_plan", "openai", "gpt-x", 10, 5)
        wh.log_activity("test", f"{tag}-{i}")
    """
)


def _run_writers(tmp_path: Path) -> Path:
    env = dict(os.environ)
    env["EDUDSS_DATA_ROOT"] = str(tmp_path / "root")
    env["EDUDSS_ENV"] = "test"
    env.pop("EDUDSS_AI_TOKEN_USAGE_STORE", None)
    env.pop("EDUDSS_ACTIVITY_STORE", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_APP_ROOT), env.get("PYTHONPATH", "")]))
    wh_path = tmp_path / "wh"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, f"p{n}", str(WRITES_PER_PROCESS), str(wh_path)],
            cwd=_APP_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for n in range(PROCESSES)
    ]
    try:
        for p in procs:
            assert p.stdout.readline().strip() == "ready", p.stderr.read()
        for p in procs:
            p.stdin.write("go\n")
            p.stdin.flush()
        for p in procs:
            _out, err = p.communicate(timeout=240)
            assert p.returncode == 0, err
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
    return wh_path


def test_four_processes_writing_at_once_lose_no_records(tmp_path):
    wh_path = _run_writers(tmp_path)
    expected = {f"p{n}-{i}" for n in range(PROCESSES) for i in range(WRITES_PER_PROCESS)}

    usage = json.loads((tmp_path / "root" / "ai_token_usage.json").read_text(encoding="utf-8"))
    assert {r["user_id"] for r in usage} == expected
    assert len(usage) == len(expected)

    history = json.loads((wh_path / "history" / "activity_history.json").read_text(encoding="utf-8"))
    assert {r["description"] for r in history} == expected
    assert len(history) == len(expected)


def test_lock_is_reentrant_and_follows_the_current_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    lock = InterProcessLock.named("demo")
    with lock:
        with lock:  # lồng nhau trong cùng luồng không được treo (subscription_service gọi lồng)
            pass
    assert (tmp_path / "locks" / "demo.lock").exists()


def test_stores_no_longer_use_process_local_locks():
    from dss.services import (
        cms_lecture_repository,
        learning_explainer,
        regulation_store,
        subscription_service,
        token_tracker,
    )

    for lock in (
        token_tracker._LOCK,
        learning_explainer._LOG_LOCK,
        learning_explainer._QUIZ_LOCK,
        learning_explainer._MISCONCEPTION_LOCK,
        cms_lecture_repository._LOCK,
        regulation_store._lock,
        subscription_service._SUB_LOCK,
    ):
        assert isinstance(lock, InterProcessLock)


def test_production_proxy_keeps_each_browser_on_one_app_replica():
    caddy = (_APP_ROOT / "deploy" / "production" / "Caddyfile").read_text(encoding="utf-8")
    assert "dynamic a app 8501" in caddy  # mọi bản `app` đang chạy
    assert "lb_policy cookie edudss_lb" in caddy  # phiên Streamlit nằm trong bộ nhớ của một tiến trình
    assert "header_up X-Real-IP {remote_host}" in caddy  # bước 7: khoá đăng nhập theo IP thật

    compose = (_APP_ROOT / "deploy" / "production" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "replicas: ${EDUDSS_APP_REPLICAS:-3}" in compose
    assert "EDUDSS_LB_COOKIE_SECRET" in compose

    deploy = (_APP_ROOT / "deploy" / "production" / "remote_deploy.sh").read_text(encoding="utf-8")
    assert '--index "$i" app' in deploy  # chỉ báo sẵn sàng khi mọi bản qua /readyz
