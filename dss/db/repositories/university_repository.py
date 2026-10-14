"""Repository for university (organization) lifecycle, LMS connector
configuration, and canonical mapping profiles (Stage 2 — University
Onboarding).

`organizations` itself carries no `organization_id` column (it IS the
tenant boundary, not a tenant-scoped table) and has no RLS policy — every
function here that creates or reads an organization row by id uses plain
`session_scope()`, never `tenant_session_scope()`, which would require an
organization_id to scope by before one exists. Connector-config and
mapping-profile functions DO use `tenant_session_scope()` (both tables are
real tenant-scoped tables with the standard `tenant_isolation` RLS
policy — see the `35d62f0c6002_university_onboarding` migration).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from dss.db.models import LmsConnectorConfig, LmsMappingProfile, Organization
from dss.db.session import session_scope, tenant_session_scope

LIFECYCLE_STATUSES = ("SETUP", "CONFIGURING", "READY", "ACTIVE", "DISABLED", "ERROR")
DEPLOYMENT_MODES = ("MULTI_TENANT_SAAS", "DEDICATED")


def create_organization(
    org_code: str,
    name: str,
    domain: Optional[str] = None,
    deployment_mode: str = "MULTI_TENANT_SAAS",
) -> int:
    """Provisions a new university/tenant in SETUP status. Does not create
    an admin, connector, or any tenant data — those are separate, explicit
    steps (see dss/services/university_onboarding.py)."""
    if deployment_mode not in DEPLOYMENT_MODES:
        raise ValueError(f"Unknown deployment_mode: {deployment_mode}")
    with session_scope() as session:
        org = Organization(
            org_code=org_code, name=name, domain=domain, is_active=True,
            lifecycle_status="SETUP", deployment_mode=deployment_mode,
        )
        session.add(org)
        session.flush()
        return org.id


def get_organization(organization_id: int) -> Optional[dict[str, Any]]:
    with session_scope() as session:
        org = session.get(Organization, organization_id)
        return _org_to_dict(org) if org else None


def get_organization_by_code(org_code: str) -> Optional[dict[str, Any]]:
    with session_scope() as session:
        org = session.query(Organization).filter_by(org_code=org_code).one_or_none()
        return _org_to_dict(org) if org else None


def list_organizations() -> list[dict[str, Any]]:
    with session_scope() as session:
        return [_org_to_dict(o) for o in session.query(Organization).order_by(Organization.id).all()]


def set_lifecycle_status(organization_id: int, status: str) -> None:
    if status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Unknown lifecycle_status: {status}")
    with session_scope() as session:
        org = session.get(Organization, organization_id)
        if org is None:
            raise ValueError(f"No such organization: {organization_id}")
        org.lifecycle_status = status


def disable_organization(organization_id: int) -> None:
    """Sets DISABLED — never deletes any tenant data. `is_active` is left
    alone deliberately (it already has independent meaning elsewhere in
    this codebase); `lifecycle_status` is the onboarding-flow's own state."""
    set_lifecycle_status(organization_id, "DISABLED")


def enable_organization(organization_id: int) -> None:
    """Re-enables a previously-disabled organization back to ACTIVE. Does
    not re-run activation validation — see
    dss/services/university_onboarding.py::activate_university for that."""
    set_lifecycle_status(organization_id, "ACTIVE")


def _org_to_dict(org: Organization) -> dict[str, Any]:
    return {
        "id": org.id, "org_code": org.org_code, "name": org.name, "domain": org.domain,
        "is_active": org.is_active, "lifecycle_status": org.lifecycle_status,
        "deployment_mode": org.deployment_mode,
    }


# ---------------------------------------------------------------------------
# LMS connector configuration
# ---------------------------------------------------------------------------

def upsert_connector_config(
    organization_id: int,
    connector_type: str,
    base_url: Optional[str] = None,
    auth_mode: Optional[str] = None,
    credential_reference: Optional[str] = None,
    external_organization_id: Optional[str] = None,
    timeout_seconds: float = 2.0,
    retry_policy: Optional[dict] = None,
    enabled_resources: Optional[list[str]] = None,
    sync_mode: str = "incremental",
) -> int:
    """Upserts the ONE connector configuration for this organization (see
    the migration's `uq_lms_connector_configs_org` unique constraint — one
    connector per tenant today, matching the accepted simulated-LMS/CMS
    architecture; nothing here prevents relaxing this to many-per-tenant
    later if a real deployment needs two source systems).

    NEVER pass a plaintext secret as `credential_reference` — it must be a
    reference (env var name / secrets-manager key), never the secret
    itself. This function does not validate that (it has no way to know
    what a "real" reference looks like), but callers (the onboarding
    service, the UI) must never construct one from a raw pasted secret."""
    with tenant_session_scope(organization_id) as session:
        row = session.query(LmsConnectorConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            row = LmsConnectorConfig(organization_id=organization_id)
            session.add(row)
        row.connector_type = connector_type
        row.base_url = base_url
        row.auth_mode = auth_mode
        row.credential_reference = credential_reference
        row.external_organization_id = external_organization_id
        row.timeout_seconds = timeout_seconds
        row.retry_policy = retry_policy
        row.enabled_resources = enabled_resources
        row.sync_mode = sync_mode
        row.configuration_status = "DRAFT"
        session.flush()
        return row.id


def get_connector_config(organization_id: int) -> Optional[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        row = session.query(LmsConnectorConfig).filter_by(organization_id=organization_id).one_or_none()
        return _connector_to_dict(row) if row else None


def record_connection_test_result(
    organization_id: int, status: str, detail: str, tested_at: Optional[datetime] = None,
) -> None:
    """`detail` must never contain a raw credential — callers pass a short,
    human-readable outcome description (e.g. "HTTP 401: invalid token"),
    never the request/response body verbatim (which could echo a token)."""
    with tenant_session_scope(organization_id) as session:
        row = session.query(LmsConnectorConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            raise ValueError(f"No connector configured for organization {organization_id}")
        row.last_connection_status = status
        row.last_connection_at = tested_at or datetime.now(timezone.utc)
        row.last_connection_detail = detail[:2000] if detail else None
        row.configuration_status = "VALID" if status == "SUCCESS" else "INVALID"


def record_successful_sync(organization_id: int, synced_at: Optional[datetime] = None) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(LmsConnectorConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            raise ValueError(f"No connector configured for organization {organization_id}")
        row.last_successful_sync_at = synced_at or datetime.now(timezone.utc)


def set_mapping_profile(organization_id: int, mapping_profile_id: int) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(LmsConnectorConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            raise ValueError(f"No connector configured for organization {organization_id}")
        row.mapping_profile_id = mapping_profile_id


def _connector_to_dict(row: LmsConnectorConfig) -> dict[str, Any]:
    return {
        "id": row.id, "connector_type": row.connector_type, "base_url": row.base_url,
        "auth_mode": row.auth_mode, "credential_reference": row.credential_reference,
        "external_organization_id": row.external_organization_id, "timeout_seconds": row.timeout_seconds,
        "retry_policy": row.retry_policy, "enabled_resources": row.enabled_resources,
        "sync_mode": row.sync_mode, "mapping_profile_id": row.mapping_profile_id,
        "last_connection_status": row.last_connection_status,
        "last_connection_at": row.last_connection_at.isoformat() if row.last_connection_at else None,
        "last_successful_sync_at": row.last_successful_sync_at.isoformat() if row.last_successful_sync_at else None,
        "configuration_status": row.configuration_status,
    }


# ---------------------------------------------------------------------------
# Canonical mapping profiles
# ---------------------------------------------------------------------------

def save_mapping_profile(organization_id: int, name: str, resource_mappings: dict, validation_status: str) -> int:
    with tenant_session_scope(organization_id) as session:
        row = LmsMappingProfile(
            organization_id=organization_id, name=name, resource_mappings=resource_mappings,
            validation_status=validation_status,
            validated_at=datetime.now(timezone.utc) if validation_status == "VALID" else None,
        )
        session.add(row)
        session.flush()
        return row.id


def get_mapping_profile(organization_id: int, mapping_profile_id: int) -> Optional[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        row = session.get(LmsMappingProfile, mapping_profile_id)
        if row is None or row.organization_id != organization_id:
            return None
        return {
            "id": row.id, "name": row.name, "resource_mappings": row.resource_mappings,
            "validation_status": row.validation_status,
            "validated_at": row.validated_at.isoformat() if row.validated_at else None,
        }
