"""Bước 9: sao lưu hằng ngày trên máy chủ production (deploy/production/scheduled_backup.sh).

Kiểm tra tĩnh luôn chạy. Kiểm tra chạy thật cần một container PostgreSQL đã migrate (owner = superuser):
    EDUDSS_BACKUP_TEST_PG_CONTAINER=<tên container> EDUDSS_BACKUP_TEST_DB=<db> EDUDSS_BACKUP_TEST_DB_USER=<owner>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent
SCRIPT = APP / "deploy" / "production" / "scheduled_backup.sh"


def test_script_is_strict_and_matches_owner_decisions():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in src
    assert 'KEEP_DAYS="${EDUDSS_BACKUP_KEEP_DAYS:-14}"' in src  # chủ dự án chốt 14 ngày (22/11/2026)
    assert 'if [ -n "${EDUDSS_BACKUP_OFFSITE_CMD:-}" ]' in src  # chưa gửi ra ngoài máy chủ khi chưa cấu hình
    assert "pg_restore --no-owner --exit-on-error" in src  # diễn tập khôi phục thật, dừng ở lỗi đầu tiên
    assert "dropdb" in src and "last_status.json" in src


def test_timer_runs_nightly_outside_class_hours():
    timer = (APP / "deploy" / "production" / "systemd" / "edudss-backup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 02:30:00 Asia/Ho_Chi_Minh" in timer
    assert "Persistent=true" in timer
    service = (APP / "deploy" / "production" / "systemd" / "edudss-backup.service").read_text(encoding="utf-8")
    assert "scheduled_backup.sh" in service and "Type=oneshot" in service


def test_shell_files_keep_lf_line_endings():
    rules = (APP / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in rules


def test_file_backup_skips_lock_files_and_security_state(tmp_path, monkeypatch):
    from ops import pipeline

    root = tmp_path / "data"
    for rel, body in {
        "models/m.joblib": "m",
        "history/activity_history.json": "[]",
        "history/.history.lock": "",
        "locks/ai_token_usage.lock": "",
        "security/login_throttle.json": "{}",
        "ai_token_usage.json": "[]",
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(root))
    monkeypatch.setenv("EDUDSS_BACKUP_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    status, detail = pipeline.job_backup()
    assert status == "ok" and detail["restore_drill"] == "VERIFIED"
    with tarfile.open(next((tmp_path / "out").rglob("data_root.tar.gz"))) as tar:
        names = {m.name for m in tar.getmembers() if m.isfile()}
    assert names == {
        "data_root/models/m.joblib",
        "data_root/history/activity_history.json",
        "data_root/ai_token_usage.json",
    }


def _bash() -> str | None:
    for candidate in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            return candidate
    return None


@pytest.mark.skipif(
    not os.environ.get("EDUDSS_BACKUP_TEST_PG_CONTAINER") or _bash() is None,
    reason="cần EDUDSS_BACKUP_TEST_PG_CONTAINER (PostgreSQL đã migrate) và bash",
)
@pytest.mark.parametrize("db_ok", [True, False])
def test_scheduled_backup_end_to_end(tmp_path, db_ok):
    deploy = tmp_path / "deploy_path"
    (deploy / "deploy" / "production").mkdir(parents=True)
    db = os.environ.get("EDUDSS_BACKUP_TEST_DB", "edudss") if db_ok else "khong_ton_tai"
    user = os.environ.get("EDUDSS_BACKUP_TEST_DB_USER", "owner")
    (deploy / "deploy" / "production" / "production.env").write_text(
        f"DB_NAME={db}\nDB_OWNER_USER={user}\n", encoding="utf-8", newline="\n"
    )
    data = tmp_path / "data"
    (data / "models").mkdir(parents=True)
    (data / "models" / "m.joblib").write_text("m", encoding="utf-8")
    backups = tmp_path / "backups"
    (backups / "daily" / "20200101T000000Z").mkdir(parents=True)
    old = (backups / "daily" / "20200101T000000Z").stat()
    os.utime(backups / "daily" / "20200101T000000Z", (old.st_atime - 30 * 86400, old.st_mtime - 30 * 86400))

    env = dict(os.environ)
    env.update(
        MSYS_NO_PATHCONV="1",
        EDUDSS_ENV="test",
        EDUDSS_DATA_ROOT=str(data),
        EDUDSS_BACKUP_DIR=backups.as_posix(),  # C:/... dùng được cho cả bash và Python Windows
        EDUDSS_BACKUP_TEST_MODE="1",
        EDUDSS_BACKUP_TEST_PG_EXEC=f"docker exec -i {os.environ['EDUDSS_BACKUP_TEST_PG_CONTAINER']}",
        EDUDSS_BACKUP_TEST_PYTHON=sys.executable.replace("\\", "/"),
        PYTHONPATH=os.pathsep.join(filter(None, [str(APP), env.get("PYTHONPATH", "")])),
        PYTHONIOENCODING="utf-8",
    )
    proc = subprocess.run(
        [_bash(), SCRIPT.as_posix(), deploy.as_posix()],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    status = json.loads((backups / "last_status.json").read_text(encoding="utf-8"))
    days = sorted(p.name for p in (backups / "daily").iterdir())
    if db_ok:
        assert proc.returncode == 0, proc.stderr
        assert status["status"] == "ok"
        assert len(days) == 1 and not days[0].endswith(".FAILED")  # bản 30 ngày tuổi đã bị dọn
        day = backups / "daily" / days[0]
        assert list((day / "postgres").glob("*.dump")) and list((day / "files").rglob("data_root.tar.gz"))
        assert '"daily_backup_verified"' in proc.stdout
    else:
        assert proc.returncode != 0
        assert status["status"] == "failed" and status["step"] == "pg_dump"
        assert any(d.endswith(".FAILED") for d in days)
