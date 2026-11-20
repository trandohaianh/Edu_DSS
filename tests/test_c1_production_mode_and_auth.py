"""C1.1 — one canonical production switch; every demo shortcut is off in production;
authentication hardening (versioned PBKDF2, persistent lockout)."""
from __future__ import annotations

import importlib
import json

import pytest

from dss.core import runtime_mode
from dss.services import auth_service


@pytest.fixture
def env(monkeypatch):
    for name in ("EDUDSS_ENV", "EDUDSS_MODE", "EDUDSS_SHOW_DEMO_CREDENTIALS", "EDUDSS_ALLOW_STUDENT_AUTOPROVISION",
                 "EDUDSS_IDENTITY_STORE", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)

    def set_env(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
    return set_env


# ---------------------------------------------------------------- the switch
@pytest.mark.parametrize("values,expected", [
    ({}, True),                                # unset fails CLOSED (audit 2026-11): no silent dev defaults
    ({"EDUDSS_ENV": "development"}, False),
    ({"EDUDSS_ENV": "test"}, False),
    ({"EDUDSS_ENV": "production"}, True),
    ({"EDUDSS_ENV": "PRODUCTION"}, True),
    ({"EDUDSS_ENV": "prod"}, True),            # unknown value fails CLOSED
    ({"EDUDSS_ENV": "staging"}, True),         # unknown value fails CLOSED
    ({"EDUDSS_MODE": "REAL_LMS"}, True),       # legacy real-users mode still means production
    ({"EDUDSS_ENV": "development", "EDUDSS_MODE": "REAL_LMS"}, True),
])
def test_single_production_predicate(env, values, expected):
    env(**values)
    assert runtime_mode.is_production() is expected
    from dss.core.data_helpers import is_production_environment
    assert is_production_environment() is expected  # the legacy helper delegates to the same switch


@pytest.mark.parametrize("prod_env", [{"EDUDSS_ENV": "production"}, {"EDUDSS_MODE": "REAL_LMS"}])
def test_production_disables_every_demo_shortcut_even_when_opted_in(env, prod_env):
    env(**prod_env, EDUDSS_SHOW_DEMO_CREDENTIALS="1", EDUDSS_ALLOW_STUDENT_AUTOPROVISION="1")
    assert runtime_mode.demo_credentials_visible() is False
    assert runtime_mode.student_autoprovision_allowed() is False
    assert runtime_mode.demo_accounts_seed_allowed() is False
    assert runtime_mode.synthetic_data_allowed() is False
    assert runtime_mode.demo_ai_allowed() is False


def test_demo_credentials_hidden_in_development_unless_explicitly_enabled(env):
    env(EDUDSS_ENV="development")
    assert runtime_mode.demo_credentials_visible() is False
    env(EDUDSS_SHOW_DEMO_CREDENTIALS="1")
    assert runtime_mode.demo_credentials_visible() is True


# ---------------------------------------------------------------- login page render
LOGIN_SCRIPT = """
from dss.services import auth_service
auth_service.render_login_gate()
"""


def _rendered_text(at) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.label for e in at.expander]
    return "\n".join(str(p) for p in parts)


@pytest.mark.parametrize("prod_env", [{"EDUDSS_ENV": "production"}, {"EDUDSS_MODE": "REAL_LMS"}])
def test_production_login_page_never_renders_demo_credentials(env, prod_env):
    from streamlit.testing.v1 import AppTest
    env(**prod_env, EDUDSS_SHOW_DEMO_CREDENTIALS="1")
    at = AppTest.from_string(LOGIN_SCRIPT, default_timeout=30).run()
    text = _rendered_text(at)
    for secret in ("admin123", "gv123", "<mã số>123", "&lt;mã số&gt;123", "giangvien / "):
        assert secret not in text
    assert not at.exception


def test_development_login_page_shows_demo_box_only_when_enabled(env):
    from streamlit.testing.v1 import AppTest
    env(EDUDSS_ENV="development")
    hidden = _rendered_text(AppTest.from_string(LOGIN_SCRIPT, default_timeout=30).run())
    assert "admin123" not in hidden
    env(EDUDSS_SHOW_DEMO_CREDENTIALS="1")
    shown = _rendered_text(AppTest.from_string(LOGIN_SCRIPT, default_timeout=30).run())
    assert "admin123" in shown


# ---------------------------------------------------------------- auto-provision / auto-login
@pytest.mark.parametrize("prod_env", [{"EDUDSS_ENV": "production"}, {"EDUDSS_MODE": "REAL_LMS"}])
def test_production_rejects_student_auto_login(env, prod_env):
    env(**prod_env)
    assert auth_service.authenticate("SV777", "SV777123") is None
    users = auth_service._load_users()
    assert "sv777" not in users  # no account was created


def test_development_auto_provision_can_be_switched_off(env):
    env(EDUDSS_ENV="development", EDUDSS_ALLOW_STUDENT_AUTOPROVISION="0")
    assert auth_service.authenticate("SV778", "SV778123") is None


def test_production_does_not_seed_demo_accounts(env):
    env(EDUDSS_ENV="production")
    assert auth_service._seed_default_accounts_into({}) is False


# ---------------------------------------------------------------- password hashing
def test_new_hashes_are_self_describing_600k():
    stored, salt = auth_service._hash_password("correct horse")
    scheme, iterations, digest = stored.split("$")
    assert scheme == "pbkdf2_sha256" and int(iterations) >= 600_000 and len(digest) == 64
    assert auth_service._verify_password("correct horse", stored, salt)
    assert not auth_service._verify_password("wrong", stored, salt)
    assert not auth_service.password_needs_rehash(stored)
    assert len(stored) <= 128  # fits users.password_hash


def test_legacy_hash_still_verifies_and_is_upgraded_on_login(env):
    import hashlib
    import os
    env(EDUDSS_ENV="development")
    salt = os.urandom(16)
    legacy = hashlib.pbkdf2_hmac("sha256", b"legacy-pass", salt, 200_000).hex()
    assert auth_service._verify_password("legacy-pass", legacy, salt.hex())
    assert auth_service.password_needs_rehash(legacy)

    users = auth_service._load_users()
    users["legacy_user"] = {"username": "legacy_user", "role": "Giảng viên / CVHT", "student_id": None,
                            "hash": legacy, "salt": salt.hex(), "auto_provisioned": False}
    auth_service._save_users(users)
    assert auth_service.authenticate("legacy_user", "legacy-pass") is not None
    upgraded = auth_service._load_users()["legacy_user"]["hash"]
    assert upgraded.startswith("pbkdf2_sha256$600000$")
    assert auth_service.authenticate("legacy_user", "legacy-pass") is not None


# ---------------------------------------------------------------- persistent lockout
def test_lockout_survives_restart_and_stores_no_plain_username(env):
    from dss.core.data_root import get_data_root
    from dss.security import login_throttle
    env(EDUDSS_ENV="development")
    name = "brute_target_c1"
    login_throttle.reset(name)
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        assert auth_service.authenticate(name, "wrong-password") is None
    with pytest.raises(auth_service.AccountLockedError):
        auth_service.authenticate(name, "wrong-password")

    importlib.reload(login_throttle)  # simulate a fresh process: no in-memory state
    locked, remaining = login_throttle.is_locked(name)
    assert locked and remaining > 0

    raw = (get_data_root() / "security" / "login_throttle.json").read_text(encoding="utf-8")
    assert name not in raw and "wrong-password" not in raw
    assert isinstance(json.loads(raw), dict)
    login_throttle.reset(name)
    assert login_throttle.is_locked(name) == (False, 0)


# ------------------------------------------------------------------ audit 17/11/2026: khoá theo máy khách
def test_failed_logins_from_one_client_do_not_lock_the_account_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    from dss.security import login_throttle as t
    name = "admin-lock-probe"
    t.reset(name)
    for _ in range(t.MAX_FAILED_ATTEMPTS):
        t.record_failure(name, "203.0.113.7")
    assert t.is_locked(name, "203.0.113.7")[0] is True       # kẻ dò bị khoá
    assert t.is_locked(name, "198.51.100.2") == (False, 0)   # quản trị ở máy khác vẫn vào được
    t.reset(name, "198.51.100.2")                            # đăng nhập đúng ở máy khác không gỡ khoá kẻ dò
    assert t.is_locked(name, "203.0.113.7")[0] is True
    t.reset(name)                                            # quản trị đặt lại mật khẩu: xoá mọi bộ đếm
    assert t.is_locked(name, "203.0.113.7") == (False, 0)


def test_distributed_guessing_still_locks_the_whole_account(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    from dss.security import login_throttle as t
    name = "admin-distributed"
    t.reset(name)
    for i in range(t.GLOBAL_MAX_FAILED):
        t.record_failure(name, f"10.0.{i // 250}.{i % 250}")
    assert t.is_locked(name, "192.0.2.99")[0] is True        # 50 lần sai từ nhiều máy: khoá cả tài khoản


def test_unknown_client_keeps_the_strict_per_account_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    from dss.security import login_throttle as t
    name = "no-client"
    t.reset(name)
    for _ in range(t.MAX_FAILED_ATTEMPTS):
        t.record_failure(name)
    assert t.is_locked(name)[0] and t.is_locked(name, "192.0.2.1")[0]


def test_successful_login_does_not_refill_the_distributed_guessing_budget(tmp_path, monkeypatch):
    """Rà soát bảo mật 17/11/2026: trước đây đăng nhập đúng xoá cả bộ đếm chung của tài khoản."""
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    from dss.security import login_throttle as t
    name = "admin-refill"
    t.reset(name)
    for i in range(t.GLOBAL_MAX_FAILED - 1):
        t.record_failure(name, f"10.1.{i // 250}.{i % 250}")
    t.reset(name, "192.0.2.10")                               # chủ tài khoản đăng nhập đúng
    t.record_failure(name, "10.9.9.9")                        # lần sai thứ 50 vẫn khoá cả tài khoản
    assert t.is_locked(name, "192.0.2.99")[0] is True
