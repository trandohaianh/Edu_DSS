"""Minimal tenant provisioning/configuration lifecycle for simulated deployment."""

from __future__ import annotations

from typing import Any

import streamlit as st
from sqlalchemy import text

from dss.core.observability import observed
from dss.db.models import Organization, OrganizationConfig, Subscription
from dss.db.repositories import audit_log_repository
from dss.db.session import session_scope, tenant_session_scope
from dss.services.auth_service import require_role


def _actor() -> str:
    return str(st.session_state.get("_auth_username") or "admin")


@require_role("Admin")
@observed("tenant.provision")
def provision_organization(
    org_code: str, name: str, *, domain: str | None = None, settings: dict[str, Any] | None = None
) -> int:
    with session_scope() as session:
        existing = session.query(Organization).filter_by(org_code=org_code).one_or_none()
        if existing:
            return existing.id
        row = Organization(org_code=org_code, name=name, domain=domain, is_active=True)
        session.add(row)
        session.flush()
        org_id = row.id
        session.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(org_id)})
        session.add(OrganizationConfig(organization_id=org_id, settings=settings or {}))
        session.add(Subscription(organization_id=org_id, plan="ENTERPRISE", status="ACTIVE", features_enabled=[]))
    audit_log_repository.record(
        "organization.provisioned",
        "organization",
        str(org_id),
        _actor(),
        organization_id=org_id,
        after={"org_code": org_code, "name": name, "active": True},
    )
    return org_id


@require_role("Admin")
@observed("tenant.configure")
def configure_organization(organization_id: int, settings: dict[str, Any]) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(OrganizationConfig).filter_by(organization_id=organization_id).one_or_none()
        before = dict(row.settings) if row else {}
        if row:
            row.settings = dict(settings)
        else:
            session.add(OrganizationConfig(organization_id=organization_id, settings=dict(settings)))
    audit_log_repository.record(
        "organization.configured",
        "organization",
        str(organization_id),
        _actor(),
        organization_id=organization_id,
        before=before,
        after=settings,
    )


def get_organization(organization_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        org = session.get(Organization, organization_id)
        if not org:
            return None
        cfg = session.query(OrganizationConfig).filter_by(organization_id=organization_id).one_or_none()
        return {
            "id": org.id,
            "org_code": org.org_code,
            "name": org.name,
            "domain": org.domain,
            "is_active": org.is_active,
            "settings": dict(cfg.settings) if cfg else {},
        }


@require_role("Admin")
@observed("tenant.set_active")
def set_organization_active(organization_id: int, active: bool) -> None:
    with session_scope() as session:
        org = session.get(Organization, organization_id)
        if not org:
            raise ValueError("organization not found")
        before = org.is_active
        org.is_active = bool(active)
    audit_log_repository.record(
        "organization.enabled" if active else "organization.disabled",
        "organization",
        str(organization_id),
        _actor(),
        organization_id=organization_id,
        before={"is_active": before},
        after={"is_active": bool(active)},
    )
