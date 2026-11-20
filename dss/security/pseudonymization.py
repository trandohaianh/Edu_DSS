"""Keyed, tenant-scoped pseudonymization (C1.1).

Replaces a SHA-256 of a PUBLIC constant salt + student id, truncated to 6 hex chars —
and 24 bits of output, reversible by simply hashing every possible student code,
and identical across universities.

Scheme
------
master key   : EDUDSS_PSEUDONYM_KEY (>= 32 bytes; hex, base64 or raw text of >= 32 chars).
               Never stored in source, never logged.
tenant key   : HMAC-SHA256(master, "edudss/pseudonym/v{version}/org/{organization_id}")
pseudonym    : "Student_" + base32(HMAC-SHA256(tenant key, normalized student id))[:20]
               -> 100 bits: collision probability negligible for any realistic cohort.

Properties: deterministic per (key version, university, student) so records stay
linkable inside EduDSS; different universities never share pseudonyms; without the
secret key the mapping cannot be inverted by enumerating student codes.

Missing key:
- production (dss.core.runtime_mode.is_production): raises PseudonymKeyMissing —
  callers must not build an external AI payload (fail closed).
- development / test: a random key is generated ONCE and stored at
  <data_root>/security/pseudonym_dev.key (outside git; data_warehouse/ is ignored),
  so dev pseudonyms are stable across restarts without any constant in source.

Rotation: set EDUDSS_PSEUDONYM_KEY_VERSION=<n+1> together with a new key. Pseudonyms
change, so records keyed by the old pseudonym (token usage, learning-explainer
interactions, misconception records) must be re-keyed with a one-off job that computes
old->new while both keys are available — see C1_1_SECURITY_PRIVACY_HARDENING.md.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
import threading
from typing import Optional

PREFIX = "Student_"
OUTPUT_CHARS = 20  # base32 chars -> 100 bits
_MIN_KEY_BYTES = 32

_logger = logging.getLogger(__name__)
_lock = threading.Lock()
_dev_key_cache: Optional[bytes] = None


class PseudonymKeyMissing(RuntimeError):
    """Production without EDUDSS_PSEUDONYM_KEY: refuse to pseudonymize (fail closed)."""


def _decode_key(raw: str) -> bytes:
    raw = raw.strip()
    for decoder in (bytes.fromhex, base64.b64decode):
        try:
            value = decoder(raw)
            if len(value) >= _MIN_KEY_BYTES:
                return value
        except (ValueError, binascii.Error):
            pass
    value = raw.encode("utf-8")
    if len(value) >= _MIN_KEY_BYTES:
        return value
    raise PseudonymKeyMissing("EDUDSS_PSEUDONYM_KEY is too short (need >= 32 bytes).")


def _dev_key() -> bytes:
    global _dev_key_cache
    with _lock:
        if _dev_key_cache is not None:
            return _dev_key_cache
        try:
            from dss.core.data_root import get_data_root

            path = get_data_root() / "security" / "pseudonym_dev.key"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(secrets.token_hex(32), encoding="utf-8")
                _logger.warning("Generated a development pseudonymization key (not for production).")
            _dev_key_cache = bytes.fromhex(path.read_text(encoding="utf-8").strip())
        except OSError:
            _dev_key_cache = secrets.token_bytes(32)
            _logger.warning("Using an ephemeral in-memory development pseudonymization key.")
        return _dev_key_cache


def _master_key() -> bytes:
    raw = os.environ.get("EDUDSS_PSEUDONYM_KEY", "")
    if raw.strip():
        return _decode_key(raw)
    from dss.core.runtime_mode import is_production

    if is_production():
        raise PseudonymKeyMissing(
            "EDUDSS_PSEUDONYM_KEY is not configured; pseudonymization is unavailable in production."
        )
    return _dev_key()


def _organization_id(organization_id: Optional[int]) -> str:
    if organization_id is not None:
        return str(int(organization_id))
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    return raw or "default"


def key_version() -> int:
    try:
        return max(1, int(os.environ.get("EDUDSS_PSEUDONYM_KEY_VERSION", "1")))
    except ValueError:
        return 1


def pseudonymize(student_id: str, organization_id: Optional[int] = None) -> str:
    """Stable, keyed, tenant-scoped pseudonym for a student identifier."""
    if student_id is None or not str(student_id).strip():
        return f"{PREFIX}Learner"
    tenant_key = hmac.new(
        _master_key(),
        f"edudss/pseudonym/v{key_version()}/org/{_organization_id(organization_id)}".encode(),
        hashlib.sha256,
    ).digest()
    digest = hmac.new(tenant_key, str(student_id).strip().upper().encode("utf-8"), hashlib.sha256).digest()
    return PREFIX + base64.b32encode(digest).decode("ascii")[:OUTPUT_CHARS]


def reset_cache_for_tests() -> None:
    global _dev_key_cache
    with _lock:
        _dev_key_cache = None
