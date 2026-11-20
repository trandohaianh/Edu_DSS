"""Persistent brute-force protection for logins (C1.1).

Before C1.1 failed attempts and lockouts lived in process memory: a restart
cleared every lockout, and each worker process had its own counter. For the
dedicated single-host deployment this store keeps the state in one JSON file
under the data root, guarded by an OS-level file lock, so it:

- survives application restarts;
- is shared by every process on the same host (e.g. several Streamlit workers);
- stores only a SHA-256 of the username (no plain usernames, no passwords).

Known limitation (documented in C1_1_SECURITY_PRIVACY_HARDENING.md): replicas on
DIFFERENT hosts do not share this file. Multi-host deployments need the same
contract backed by PostgreSQL — out of scope until more than one host exists.
If the file cannot be used at all, the store degrades to in-process memory and
logs a warning (never disables protection).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes
WINDOW_SECONDS = 900

_logger = logging.getLogger(__name__)
_thread_lock = threading.Lock()
_memory_state: dict = {}


def _key(username: str) -> str:
    return hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()


def _state_path() -> Optional[Path]:
    try:
        from dss.core.data_root import get_data_root
        path = get_data_root() / "security" / "login_throttle.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


@contextlib.contextmanager
def _locked_state():
    """Yield the mutable state dict under a cross-process lock; persist on exit."""
    path = _state_path()
    with _thread_lock:
        if path is None:
            yield _memory_state
            return
        lock_path = path.with_suffix(".lock")
        try:
            lock_file = open(lock_path, "a+")
        except OSError:
            _logger.warning("Login throttle file unavailable; using in-process memory (protection kept).")
            yield _memory_state
            return
        try:
            _os_lock(lock_file)
            try:
                state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (OSError, ValueError):
                state = {}
            yield state
            _prune(state)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            _os_unlock(lock_file)
            lock_file.close()


def _os_lock(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _os_unlock(f) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _prune(state: dict) -> None:
    now = time.time()
    for k in list(state):
        entry = state[k]
        window = entry.get("w", WINDOW_SECONDS)
        entry["attempts"] = [t for t in entry.get("attempts", []) if now - t < window]
        if not entry["attempts"] and entry.get("locked_until", 0) <= now:
            del state[k]


# Audit 17/11/2026: khoá theo TÊN ĐĂNG NHẬP cho phép bất kỳ ai khoá ``admin`` 15 phút bằng 5 lần gõ sai. Nay khi biết
# máy khách (``client``: IP lấy từ kết nối, xem auth_service._client_id), 5 lần sai chỉ khoá CẶP (tài khoản, máy
# khách) đó; người dùng thật ở máy khác vẫn đăng nhập được. Chống dò mật khẩu phân tán bằng trần chung theo tài
# khoản: GLOBAL_MAX_FAILED lần sai trong GLOBAL_WINDOW_SECONDS (mọi máy khách cộng lại) thì khoá tài khoản như cũ.
# Không biết máy khách (client=None) thì giữ đúng hành vi cũ: 5 lần sai khoá cả tài khoản.
GLOBAL_MAX_FAILED = 50
GLOBAL_WINDOW_SECONDS = 3600


def _pair_key(username: str, client: str) -> str:
    return hashlib.sha256(f"{username.strip().lower()}|{client}".encode("utf-8")).hexdigest()


def _locked_left(state: dict, key: str, now: float) -> int:
    until = state.get(key, {}).get("locked_until", 0)
    return int(until - now) if now < until else 0


def is_locked(username: str, client: Optional[str] = None) -> tuple[bool, int]:
    now = time.time()
    with _locked_state() as state:
        left = _locked_left(state, _key(username), now)
        if client:
            left = max(left, _locked_left(state, _pair_key(username, client), now))
    return (True, left) if left > 0 else (False, 0)


def _bump(state: dict, key: str, owner: str, now: float, limit: int, window: int) -> bool:
    entry = state.setdefault(key, {"attempts": [], "locked_until": 0})
    entry["u"], entry["w"] = owner, window
    entry["attempts"] = [t for t in entry["attempts"] if now - t < window] + [now]
    if len(entry["attempts"]) >= limit:
        entry["locked_until"] = now + LOCKOUT_SECONDS
        entry["attempts"] = []
        return True
    return False


def record_failure(username: str, client: Optional[str] = None) -> bool:
    """Record one failed attempt. Returns True if this attempt triggered a lockout."""
    now = time.time()
    owner = _key(username)
    with _locked_state() as state:
        if not client:
            return _bump(state, owner, owner, now, MAX_FAILED_ATTEMPTS, WINDOW_SECONDS)
        pair = _bump(state, _pair_key(username, client), owner, now, MAX_FAILED_ATTEMPTS, WINDOW_SECONDS)
        whole = _bump(state, owner, owner, now, GLOBAL_MAX_FAILED, GLOBAL_WINDOW_SECONDS)
        return pair or whole


def reset(username: str, client: Optional[str] = None) -> None:
    """Đăng nhập đúng: xoá bộ đếm của cặp (tài khoản, máy khách); bộ đếm chung tự hết hạn theo cửa sổ. client=None
    (quản trị đặt lại mật khẩu): xoá mọi bộ đếm của tài khoản ở mọi máy khách."""
    owner = _key(username)
    with _locked_state() as state:
        if client:
            # Đăng nhập đúng KHÔNG xoá bộ đếm chung: kẻ dò phân tán không được thêm 49 lần thử mỗi khi chủ tài khoản vào.
            state.pop(_pair_key(username, client), None)
        else:
            state.pop(owner, None)
            for k in [k for k, v in state.items() if isinstance(v, dict) and v.get("u") == owner]:
                del state[k]
