"""dss/services/subscription_service.py — real PostgreSQL wiring (Phase 1B,
migration order item 9). Skipped (not faked) without a configured database.
"""
from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — subscription Postgres-wiring tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"SUB_TEST_{uuid.uuid4().hex[:8]}", name="Subscription Test Org")
        session.add(org)
        session.flush()
        return org.id


def test_get_subscription_creates_default_in_postgres_when_enabled(org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_SUBSCRIPTION_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    from dss.services import subscription_service

    sub = subscription_service.get_organization_subscription()
    assert sub["status"] == "ACTIVE"
    assert sub["plan"] == "ENTERPRISE"


def test_update_status_persists_in_postgres(org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_SUBSCRIPTION_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    from dss.services import subscription_service

    subscription_service.get_organization_subscription()  # ensure row exists
    ok = subscription_service.update_subscription_status("SUSPENDED")
    assert ok is True

    sub = subscription_service.get_organization_subscription()
    assert sub["status"] == "SUSPENDED"


def test_local_mode_unaffected_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("EDUDSS_SUBSCRIPTION_STORE", raising=False)
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.services import subscription_service

    sub = subscription_service.get_organization_subscription()
    assert sub["status"] == "ACTIVE"
    assert (tmp_path / "subscription.json").exists()


def test_subscriptions_are_tenant_isolated(org_id, monkeypatch):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other_org = Organization(org_code=f"SUB_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    monkeypatch.setenv("EDUDSS_SUBSCRIPTION_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    from dss.services import subscription_service
    subscription_service.update_subscription_status("SUSPENDED")

    from dss.db.repositories import subscription_repository
    org_a_sub = subscription_repository.get_or_create_subscription(org_id)
    org_b_sub = subscription_repository.get_or_create_subscription(other_org_id)
    assert org_a_sub["status"] == "SUSPENDED"
    assert org_b_sub["status"] == "ACTIVE"  # unaffected by org A's update
