"""Canonical runtime environment contract — the ONE place that decides whether
EduDSS runs as production (C1.1).

Environment contract
--------------------
EDUDSS_ENV = development | test | production        (default when unset: production)
    Governs every security / demo decision. An unset OR unrecognised value fails CLOSED
    (treated as production) so a forgotten variable or a typo on a hosted server can never
    re-enable the demo accounts (admin/admin123, giangvien/gv123, <code>/<code>123 student login).
    Local development must opt in explicitly: EDUDSS_ENV=development (see .env.example).

EDUDSS_MODE = DEMO_SYNTHETIC | REAL_LMS | LOCAL_OFFLINE  (data / operating mode)
    Kept for data-source and offline-routing behaviour. For backward
    compatibility REAL_LMS also implies production (it always meant "real users").

Opt-ins, honoured ONLY outside production (ignored in production):
    EDUDSS_SHOW_DEMO_CREDENTIALS=1       show the demo-account box on the login page
    EDUDSS_ALLOW_STUDENT_AUTOPROVISION=0 turn OFF <code>/<code>123 student auto-login
                                         (default: on in development/test for local demos)

EDUDSS_PUBLIC_DEMO=1 (outside production only) — a public Internet demo on synthetic data:
    keeps synthetic data and the rule-based fallbacks, but turns OFF every shortcut that would let
    an anonymous visitor log in as someone else: no seeded admin/giangvien accounts, no
    <code>/<code>123 student auto-login, no demo-credential box. Visitors sign in with Google and
    get their own synthetic student; staff accounts come from EDUDSS_BOOTSTRAP_ADMIN_* and the
    admin "Người dùng" page.

Production disables, regardless of any opt-in:
    demo credential display · student auto-provision/auto-login · demo account seeding ·
    synthetic sample data / simulated LMS events · demo (fabricated) AI answers ·
    unapproved knowledge-base documents.
"""

from __future__ import annotations

import logging
import os

ENV_DEVELOPMENT = "development"
ENV_TEST = "test"
ENV_PRODUCTION = "production"
_KNOWN_ENVS = {ENV_DEVELOPMENT, ENV_TEST, ENV_PRODUCTION}

_logger = logging.getLogger(__name__)
_warned_unknown = set()


def current_env() -> str:
    raw = os.environ.get("EDUDSS_ENV", "").strip().lower()
    if not raw:
        if "" not in _warned_unknown:
            _warned_unknown.add("")
            _logger.warning(
                "EDUDSS_ENV is not set; running as production (fail closed). "
                "Set EDUDSS_ENV=development for local demo accounts and synthetic data."
            )
        return ENV_PRODUCTION
    if raw not in _KNOWN_ENVS:
        if raw not in _warned_unknown:
            _warned_unknown.add(raw)
            _logger.warning("EDUDSS_ENV has an unrecognised value; treating as production (fail closed).")
        return ENV_PRODUCTION
    return raw


def is_production() -> bool:
    """True for EDUDSS_ENV=production (or any unknown value) or EDUDSS_MODE=REAL_LMS."""
    if current_env() == ENV_PRODUCTION:
        return True
    return os.environ.get("EDUDSS_MODE", "DEMO_SYNTHETIC").strip().upper() == "REAL_LMS"


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_public_demo() -> bool:
    """Public Internet demo on synthetic data (never true in production)."""
    return (not is_production()) and _flag("EDUDSS_PUBLIC_DEMO", False)


def demo_credentials_visible() -> bool:
    """Demo usernames/passwords are shown only when explicitly enabled outside production."""
    return (not is_production()) and not is_public_demo() and _flag("EDUDSS_SHOW_DEMO_CREDENTIALS", False)


def student_autoprovision_allowed() -> bool:
    """Student `<code>` / `<code>123` auto-provision + login: never in production or a public demo."""
    return (not is_production()) and not is_public_demo() and _flag("EDUDSS_ALLOW_STUDENT_AUTOPROVISION", True)


def demo_accounts_seed_allowed() -> bool:
    return not is_production() and not is_public_demo()


def google_self_signup_allowed() -> bool:
    """A first Google sign-in with an unknown e-mail may create a Student account bound to an
    unclaimed SYNTHETIC student. Only where synthetic data exists (never production)."""
    if is_production():
        return False
    return is_public_demo() or _flag("EDUDSS_GOOGLE_SELF_SIGNUP", False)


def synthetic_data_allowed() -> bool:
    """Sample/synthetic datasets and simulated LMS events."""
    return not is_production()


def demo_ai_allowed() -> bool:
    """Fabricated/'simulation' AI answers (rule-based demo plans)."""
    return not is_production()
