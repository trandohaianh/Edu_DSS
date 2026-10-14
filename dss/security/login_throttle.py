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
        entry["attempts"] = [t for t in entry.get("attempts", []) if now - t < WINDOW_SECONDS]
        if not entry["attempts"] and entry.get("locked_until", 0) <= now:
            del state[k]


def is_locked(username: str) -> tuple[bool, int]:
    now = time.time()
    with _locked_state() as state:
        until = state.get(_key(username), {}).get("locked_until", 0)
    return (True, int(until - now)) if now < until else (False, 0)


def record_failure(username: str) -> bool:
    """Record one failed attempt. Returns True if this attempt triggered a lockout."""
    now = time.time()
    with _locked_state() as state:
        entry = state.setdefault(_key(username), {"attempts": [], "locked_until": 0})
        entry["attempts"] = [t for t in entry["attempts"] if now - t < WINDOW_SECONDS] + [now]
        if len(entry["attempts"]) >= MAX_FAILED_ATTEMPTS:
            entry["locked_until"] = now + LOCKOUT_SECONDS
            entry["attempts"] = []
            return True
    return False


def reset(username: str) -> None:
    with _locked_state() as state:
        state.pop(_key(username), None)
