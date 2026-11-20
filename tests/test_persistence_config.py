"""dss/core/persistence_config.py — the incremental-cutover feature-flag seam
merged in from a second, parallel session's Phase 1 work (see
reports/production_readiness/PHASE1_REPORT.md's "Merge" section). Real gate,
not a placeholder: defaults to `None` (the existing, working JSON-backed
path) for every feature unless explicitly opted into via an env var, and
fails loudly and immediately (not with a confusing later AttributeError) if
that opt-in is ever selected before the Postgres-backed path actually exists.
IDENTITY is now wired for real (Phase 1C) — see
tests/test_user_repository.py for its full integration coverage; SUBSCRIPTION
remains unwired via this gate (see dss/core/persistence_config.py's own
docstring for why).
"""

from __future__ import annotations

import pytest

from dss.core.persistence_config import repository_for


def test_defaults_to_local_for_identity(monkeypatch):
    monkeypatch.delenv("EDUDSS_IDENTITY_STORE", raising=False)
    assert repository_for("IDENTITY") is None


def test_defaults_to_local_for_subscription(monkeypatch):
    monkeypatch.delenv("EDUDSS_SUBSCRIPTION_STORE", raising=False)
    assert repository_for("SUBSCRIPTION") is None


def test_unknown_feature_rejected():
    with pytest.raises(ValueError, match="unknown persistence feature"):
        repository_for("NOT_A_REAL_FEATURE")


def test_invalid_store_value_rejected(monkeypatch):
    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "mongodb")
    with pytest.raises(ValueError, match="local or postgres"):
        repository_for("IDENTITY")


def test_postgres_mode_returns_real_repository_for_identity(monkeypatch):
    """Phase 1C: IDENTITY is now wired for real — selecting postgres mode
    (with the required org id resolved) returns an actual
    UserRepository, not a placeholder/NotImplementedError."""
    from dss.db.repositories.user_repository import UserRepository

    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    repo = repository_for("IDENTITY")
    assert isinstance(repo, UserRepository)
    assert repo.organization_id == 1


def test_postgres_mode_for_identity_fails_loudly_without_org_id(monkeypatch):
    """Still fails immediately and clearly — never silently defaults to some
    other organization — if EDUDSS_ORGANIZATION_ID isn't set."""
    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.delenv("EDUDSS_ORGANIZATION_ID", raising=False)
    with pytest.raises(RuntimeError, match="EDUDSS_ORGANIZATION_ID"):
        repository_for("IDENTITY")


def test_postgres_mode_fails_loudly_for_subscription_too(monkeypatch):
    monkeypatch.setenv("EDUDSS_SUBSCRIPTION_STORE", "postgres")
    with pytest.raises(NotImplementedError, match="incomplete"):
        repository_for("SUBSCRIPTION")
