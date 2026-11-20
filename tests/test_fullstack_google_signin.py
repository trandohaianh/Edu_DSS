"""Google Sign-In mapping, public-demo mode, admin account management, env admin bootstrap."""

from __future__ import annotations

import json

import pytest

from dss.core import runtime_mode
from dss.services import auth_service


def _claims(email, verified=True):
    return {"email": email, "email_verified": verified, "sub": "123", "iss": "https://accounts.google.com"}


@pytest.fixture
def clean_env(monkeypatch):
    for name in (
        "EDUDSS_ENV",
        "EDUDSS_MODE",
        "EDUDSS_PUBLIC_DEMO",
        "EDUDSS_GOOGLE_SELF_SIGNUP",
        "EDUDSS_SHOW_DEMO_CREDENTIALS",
        "EDUDSS_ALLOW_STUDENT_AUTOPROVISION",
        "EDUDSS_BOOTSTRAP_ADMIN_USER",
        "EDUDSS_BOOTSTRAP_ADMIN_PASSWORD",
        "EDUDSS_BOOTSTRAP_ADMIN_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    # EDUDSS_ENV không đặt = production (fail closed); bản demo công khai chạy ở development.
    monkeypatch.setenv("EDUDSS_ENV", "development")
    return monkeypatch


def test_public_demo_turns_off_every_anonymous_shortcut(clean_env):
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    clean_env.setenv("EDUDSS_SHOW_DEMO_CREDENTIALS", "1")
    assert runtime_mode.is_public_demo()
    assert not runtime_mode.demo_accounts_seed_allowed()
    assert not runtime_mode.student_autoprovision_allowed()
    assert not runtime_mode.demo_credentials_visible()
    assert runtime_mode.google_self_signup_allowed()
    assert runtime_mode.synthetic_data_allowed()


def test_public_demo_flag_is_ignored_in_production(clean_env):
    clean_env.setenv("EDUDSS_ENV", "production")
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    clean_env.setenv("EDUDSS_GOOGLE_SELF_SIGNUP", "1")
    assert not runtime_mode.is_public_demo()
    assert not runtime_mode.google_self_signup_allowed()


def test_public_demo_blocks_student_code_password_login(clean_env, isolated_users_file):
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    assert auth_service.authenticate("sv001", "sv001123") is None


def test_linked_email_signs_into_existing_account(clean_env, isolated_users_file, as_role):
    as_role("Admin", username="boss")
    auth_service.admin_create_account("gv.lan", "mat-khau-dai-123", "Giảng viên / CVHT", email="Lan@Truong.edu.vn")
    record = auth_service.resolve_google_user(_claims("lan@truong.edu.vn"))
    assert record["username"] == "gv.lan" and record["role"] == "Giảng viên / CVHT"


def test_unverified_or_missing_email_is_rejected(clean_env, isolated_users_file):
    with pytest.raises(auth_service.GoogleSignInRejected) as exc:
        auth_service.resolve_google_user(_claims("a@b.com", verified=False))
    assert exc.value.code == "email_unverified"
    with pytest.raises(auth_service.GoogleSignInRejected) as exc:
        auth_service.resolve_google_user({"email_verified": True})
    assert exc.value.code == "no_email"


def test_unknown_email_rejected_outside_public_demo(clean_env, isolated_users_file):
    with pytest.raises(auth_service.GoogleSignInRejected) as exc:
        auth_service.resolve_google_user(_claims("stranger@gmail.com"))
    assert exc.value.code == "not_linked"


def test_public_demo_self_signup_gets_own_synthetic_student(clean_env, isolated_users_file):
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    clean_env.setenv("EDUDSS_DEMO_STUDENT_POOL", "5")
    a = auth_service.resolve_google_user(_claims("a@gmail.com"))
    b = auth_service.resolve_google_user(_claims("b@gmail.com"))
    again = auth_service.resolve_google_user(_claims("A@gmail.com"))
    assert a["role"] == b["role"] == "Sinh viên"
    assert a["student_id"] != b["student_id"]
    assert again["username"] == a["username"] and again["student_id"] == a["student_id"]
    stored = json.loads(isolated_users_file.read_text(encoding="utf-8"))
    assert stored[a["username"]]["email"] == "a@gmail.com"
    # the random password is unknown to everyone: no password login to a Google-created account
    assert auth_service.authenticate(a["username"], a["student_id"].lower() + "123") is None


def test_public_demo_pool_exhaustion_is_reported(clean_env, isolated_users_file):
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    clean_env.setenv("EDUDSS_DEMO_STUDENT_POOL", "1")
    auth_service.resolve_google_user(_claims("first@gmail.com"))
    with pytest.raises(auth_service.GoogleSignInRejected) as exc:
        auth_service.resolve_google_user(_claims("second@gmail.com"))
    assert exc.value.code == "pool_exhausted"


def test_disabled_account_cannot_sign_in_with_google(clean_env, isolated_users_file, as_role):
    as_role("Admin", username="boss")
    auth_service.admin_create_account("gv.binh", "mat-khau-dai-123", "Giảng viên / CVHT", email="binh@x.vn")
    auth_service.admin_update_account("gv.binh", active=False)
    with pytest.raises(auth_service.GoogleSignInRejected) as exc:
        auth_service.resolve_google_user(_claims("binh@x.vn"))
    assert exc.value.code == "disabled"


def test_admin_account_management_rules(clean_env, isolated_users_file, as_role):
    as_role("Admin", username="boss")
    auth_service.admin_create_account("gv.an", "mat-khau-dai-123", "Giảng viên / CVHT", email="an@x.vn")
    with pytest.raises(ValueError):
        auth_service.admin_create_account("gv.an", "mat-khau-dai-123", "Admin")  # duplicate
    with pytest.raises(ValueError):
        auth_service.admin_create_account("gv.chi", "ngan", "Admin")  # weak password
    with pytest.raises(ValueError):
        auth_service.admin_create_account("sv.x", "mat-khau-dai-123", "Sinh viên")  # student needs id
    with pytest.raises(ValueError):
        auth_service.admin_create_account("gv.dung", "mat-khau-dai-123", "Admin", email="an@x.vn")  # email taken
    auth_service.admin_update_account("gv.an", role="Admin", email="")
    record = auth_service._load_users()["gv.an"]
    assert record["role"] == "Admin" and record["email"] is None
    auth_service.admin_reset_password("gv.an", "mat-khau-moi-456")
    assert auth_service.authenticate("gv.an", "mat-khau-moi-456") is not None
    with pytest.raises(ValueError):
        auth_service.admin_update_account("boss", active=False)  # no self-lockout


def test_account_management_requires_admin(clean_env, isolated_users_file, as_role):
    as_role("Giảng viên / CVHT")
    with pytest.raises(PermissionError):
        auth_service.admin_create_account("x.y", "mat-khau-dai-123", "Admin")


def test_bootstrap_admin_from_env_once(clean_env, isolated_users_file):
    clean_env.setenv("EDUDSS_PUBLIC_DEMO", "1")
    clean_env.setenv("EDUDSS_BOOTSTRAP_ADMIN_USER", "admin")
    clean_env.setenv("EDUDSS_BOOTSTRAP_ADMIN_PASSWORD", "short")
    assert auth_service.bootstrap_admin_from_env() is False  # < 12 chars refused
    clean_env.setenv("EDUDSS_BOOTSTRAP_ADMIN_PASSWORD", "a-very-long-password")
    clean_env.setenv("EDUDSS_BOOTSTRAP_ADMIN_EMAIL", "owner@gmail.com")
    assert auth_service.bootstrap_admin_from_env() is True
    assert auth_service.bootstrap_admin_from_env() is False  # never overwrites
    assert auth_service.authenticate("admin", "a-very-long-password")["role"] == "Admin"
    assert auth_service.authenticate("admin", "admin123") is None  # no demo seed in public demo
    assert auth_service.resolve_google_user(_claims("owner@gmail.com"))["username"] == "admin"


def test_streamlit_secrets_writer(tmp_path):
    from ops import write_streamlit_secrets as w

    assert w.build({}) is None
    env = {
        "EDUDSS_PUBLIC_URL": "https://edu.example.org/",
        "EDUDSS_GOOGLE_CLIENT_ID": "cid",
        "EDUDSS_GOOGLE_CLIENT_SECRET": "sec\"ret",
        "EDUDSS_AUTH_COOKIE_SECRET": "x" * 40,
    }
    text = w.build(env)
    import tomllib

    parsed = tomllib.loads(text)
    assert parsed["auth"]["redirect_uri"] == "https://edu.example.org/oauth2callback"
    assert parsed["auth"]["google"]["client_secret"] == 'sec"ret'
    with pytest.raises(SystemExit):
        w.build(dict(env, EDUDSS_AUTH_COOKIE_SECRET="short"))
    with pytest.raises(SystemExit):
        w.build(dict(env, EDUDSS_PUBLIC_URL="http://edu.example.org"))
