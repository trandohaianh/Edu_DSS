"""Canonical runtime environment contract — the ONE place that decides whether
EduDSS runs as production (C1.1).

Environment contract
--------------------
EDUDSS_ENV = development | test | production        (default: development)
    Governs every security / demo decision. An unrecognised value fails CLOSED
    (treated as production) so a typo can never re-enable demo shortcuts.

EDUDSS_MODE = DEMO_SYNTHETIC | REAL_LMS | LOCAL_OFFLINE  (data / operating mode)
    Kept for data-source and offline-routing behaviour. For backward
    compatibility REAL_LMS also implies production (it always meant "real users").

Opt-ins, honoured ONLY outside production (ignored in production):
    EDUDSS_SHOW_DEMO_CREDENTIALS=1       show the demo-account box on the login page
    EDUDSS_ALLOW_STUDENT_AUTOPROVISION=0 turn OFF <code>/<code>123 student auto-login
                                         (default: on in development/test for local demos)

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
    raw = os.environ.get("EDUDSS_ENV", ENV_DEVELOPMENT).strip().lower() or ENV_DEVELOPMENT
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


def demo_credentials_visible() -> bool:
    """Demo usernames/passwords are shown only when explicitly enabled outside production."""
    return (not is_production()) and _flag("EDUDSS_SHOW_DEMO_CREDENTIALS", False)


def student_autoprovision_allowed() -> bool:
    """Student `<code>` / `<code>123` auto-provision + login: never in production."""
    return (not is_production()) and _flag("EDUDSS_ALLOW_STUDENT_AUTOPROVISION", True)


def demo_accounts_seed_allowed() -> bool:
    return not is_production()


def synthetic_data_allowed() -> bool:
    """Sample/synthetic datasets and simulated LMS events."""
    return not is_production()


def demo_ai_allowed() -> bool:
    """Fabricated/'simulation' AI answers (rule-based demo plans)."""
    return not is_production()
