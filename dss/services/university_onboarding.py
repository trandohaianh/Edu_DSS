"""University onboarding orchestration (Stage 2).

Product direction this module exists to prove: ONE EduDSS codebase, ONE
Docker image, serving multiple universities as configuration/data, never
as a source-code fork. Onboarding a new university means inserting rows
(organization, connector config, mapping profile, admin user) through
this module — never copying `app/`, never writing a second
implementation, never hand-editing another organization's data behind
this service's back.

Connector strategy: today, exactly one `connector_type` is real —
"simulated_lms_cms", backed by `dss.integrations.lms_cms_connector` and
`dss.integrations.postgres_lms_cms` (accepted Workstream A+B
infrastructure, untouched by this module). `_build_connector()` below is
the ONE place that maps a stored `LmsConnectorConfig` row to a live
connector object; adding real Moodle/Canvas/custom-SIS support means
adding a case here (and a real adapter module) — not touching
provisioning, activation, mapping validation, or the UI, all of which
only ever see the canonical resource/record shape. No Moodle/Canvas
adapter exists yet; claiming otherwise would be false and this module
does not.

Deployment-mode metadata (`Organization.deployment_mode`,
MULTI_TENANT_SAAS | DEDICATED) is exactly that — metadata read by
whoever operates a given deployment. This module never provisions cloud
infrastructure for either mode; both modes run the identical Docker
image and codebase, differing only in how many organizations one running
instance happens to serve.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from dss.core.logging_config import get_logger
from dss.db.repositories import university_repository as repo
from dss.db.repositories.user_repository import UserRepository
from dss.services.auth_service import require_role

_logger = get_logger(__name__)

# The accepted simulator's own fixed universe (see
# simulator/lms_cms_simulator.py::TOKENS) — exactly two external tenants
# exist to onboard against today. A real adapter for a real LMS would not
# have this constraint; this is a property of the ACCEPTED SIMULATOR, not
# of this onboarding service.
SIMULATED_EXTERNAL_ORGS = ("org-a", "org-b")

CANONICAL_RESOURCES = (
    "users", "students", "lecturers", "courses", "enrollments",
    "assignments", "submissions", "grades", "attendance", "activities", "content",
)


@dataclass
class ActivationResult:
    activated: bool
    reasons: list[str] = field(default_factory=list)


def _resolve_credential(credential_reference: Optional[str]) -> Optional[str]:
    """Resolves a stored credential *reference* (an env var name) to its
    actual secret value at call time. Never returns the reference itself
    if it fails to resolve — returns None, forcing an honest connection
    failure rather than sending a literal env-var-name as a bearer token."""
    if not credential_reference:
        return None
    return os.environ.get(credential_reference)


@require_role("Platform Admin")
def provision_university(
    org_code: str, name: str, domain: Optional[str] = None,
    deployment_mode: str = "MULTI_TENANT_SAAS",
) -> int:
    """Step 1 of onboarding: create the tenant row, status SETUP. Creates
    nothing else — no admin, no connector, no data."""
    org_id = repo.create_organization(org_code, name, domain, deployment_mode)
    _logger.info("university provisioned: org_id=%s org_code=%s deployment_mode=%s", org_id, org_code, deployment_mode)
    return org_id


@require_role("Platform Admin")
def create_university_admin(organization_id: int, username: str, password: str) -> dict[str, Any]:
    """Creates the initial Admin user for a newly-provisioned university.
    Reuses the existing, already-tested UserRepository (real password
    hashing/salting — no plaintext password is ever persisted or logged).
    """
    record = UserRepository(organization_id).create_user(username, password, role_name="Admin")
    repo.set_lifecycle_status(organization_id, "CONFIGURING")
    _logger.info("university admin created: org_id=%s username=%s", organization_id, username)
    return {"username": record.get("username", username), "role": "Admin", "organization_id": organization_id}


@require_role("Platform Admin")
def configure_connector(
    organization_id: int,
    connector_type: str,
    external_organization_id: str,
    base_url: str,
    credential_reference: str,
    enabled_resources: Optional[list[str]] = None,
    auth_mode: str = "bearer_token",
    timeout_seconds: float = 2.0,
    sync_mode: str = "incremental",
    retry_policy: Optional[dict] = None,
) -> int:
    """Step 3: stores connector configuration. `credential_reference` MUST
    be an environment-variable name (or secrets-manager key), never a raw
    token — see LmsConnectorConfig's docstring. Raises ValueError if given
    something that is obviously a raw secret rather than a reference (a
    plain heuristic: a real env var name is a short identifier; anything
    containing whitespace or exceeding a sane identifier length is
    rejected as likely-a-pasted-secret)."""
    if not credential_reference or " " in credential_reference or len(credential_reference) > 128:
        raise ValueError(
            "credential_reference must be an environment variable name (e.g. 'EDUDSS_LMS_TOKEN_UNIB'), "
            "never a raw token/secret."
        )
    connector_id = repo.upsert_connector_config(
        organization_id=organization_id, connector_type=connector_type, base_url=base_url,
        auth_mode=auth_mode, credential_reference=credential_reference,
        external_organization_id=external_organization_id, timeout_seconds=timeout_seconds,
        retry_policy=retry_policy or {"max_attempts": 3}, enabled_resources=list(enabled_resources or CANONICAL_RESOURCES),
        sync_mode=sync_mode,
    )
    _logger.info("connector configured: org_id=%s connector_type=%s external_org=%s", organization_id, connector_type, external_organization_id)
    return connector_id


def _build_connector(config: dict[str, Any]):
    """The ONE place a stored config becomes a live connector object. Only
    "simulated_lms_cms" is real today."""
    if config["connector_type"] != "simulated_lms_cms":
        raise NotImplementedError(
            f"connector_type={config['connector_type']!r} has no real adapter yet — "
            "only 'simulated_lms_cms' (Workstream A+B's accepted simulator) is implemented."
        )
    from dss.integrations.lms_cms_connector import LMSCMSConnector

    token = _resolve_credential(config["credential_reference"])
    if not token:
        raise ValueError(
            f"credential_reference {config['credential_reference']!r} did not resolve to a value "
            "(environment variable not set) — cannot build a connector without a real credential."
        )
    return LMSCMSConnector(
        config["base_url"], token, config["external_organization_id"],
        timeout=config["timeout_seconds"], max_attempts=3,
    )


@require_role("Platform Admin")
def test_connection(organization_id: int, scenario: Optional[str] = None) -> dict[str, Any]:
    """Step 5: a REAL HTTP call against the configured connector — never a
    fabricated "Connected". `scenario` (only meaningful against the
    accepted simulator) lets the same code path be exercised for
    500/429/timeout/malformed as it would be for a genuine success, so
    this function's honesty is itself testable — see
    tests/test_university_onboarding.py."""
    from dss.integrations.lms_cms_connector import IntegrationError

    config = repo.get_connector_config(organization_id)
    if config is None:
        result = {"status": "FAILED", "detail": "No connector configured for this organization."}
        return result

    try:
        connector = _build_connector(config)
    except (NotImplementedError, ValueError) as exc:
        detail = str(exc)
        repo.record_connection_test_result(organization_id, "FAILED", detail)
        return {"status": "FAILED", "detail": detail}

    try:
        connector.fetch((config["enabled_resources"] or CANONICAL_RESOURCES)[0], page_size=1, scenario=scenario)
        repo.record_connection_test_result(organization_id, "SUCCESS", "Connected: fetched a sample record.")
        return {"status": "SUCCESS", "detail": "Connected: fetched a sample record.", "http_status": 200}
    except IntegrationError as exc:
        detail = f"{exc.code}: {exc}" if not exc.status else f"HTTP {exc.status} ({exc.code}): {exc}"
        repo.record_connection_test_result(organization_id, "FAILED", detail)
        return {"status": "FAILED", "detail": detail, "http_status": exc.status, "code": exc.code, "retryable": exc.retryable}


@require_role("Platform Admin")
def validate_mapping(organization_id: int) -> dict[str, Any]:
    """Step 4 (mapping) — fetches one real sample record per enabled
    resource and checks the canonical ID field
    (dss.integrations.lms_cms_connector.ID_FIELDS) is actually present.
    This is real validation against real fetched data, not a static
    assumption that the simulator's shape matches EduDSS's canonical
    shape — a future non-simulator adapter that omits a required field
    would be caught here exactly the same way."""
    from dss.integrations.lms_cms_connector import ID_FIELDS, IntegrationError

    config = repo.get_connector_config(organization_id)
    if config is None:
        return {"status": "INVALID", "resource_mappings": {}, "reason": "No connector configured."}

    try:
        connector = _build_connector(config)
    except (NotImplementedError, ValueError) as exc:
        return {"status": "INVALID", "resource_mappings": {}, "reason": str(exc)}

    resource_mappings: dict[str, Any] = {}
    overall_valid = True
    for resource in (config["enabled_resources"] or CANONICAL_RESOURCES):
        required_field = ID_FIELDS.get(resource)
        if required_field is None:
            resource_mappings[resource] = {"status": "invalid", "reason": f"unknown canonical resource: {resource}"}
            overall_valid = False
            continue
        try:
            sample = connector.fetch(resource, page_size=1)
        except IntegrationError as exc:
            resource_mappings[resource] = {"status": "invalid", "reason": f"fetch failed: {exc.code}"}
            overall_valid = False
            continue
        records = sample.get("data") if isinstance(sample, dict) else sample
        records = records if isinstance(records, list) else []
        if not records:
            resource_mappings[resource] = {"status": "invalid", "reason": "no sample records returned", "required_fields": [required_field]}
            overall_valid = False
            continue
        present = required_field in records[0]
        resource_mappings[resource] = {
            "status": "valid" if present else "invalid",
            "required_fields": [required_field],
            "missing_fields": [] if present else [required_field],
        }
        overall_valid = overall_valid and present

    status = "VALID" if overall_valid else "INVALID"
    mapping_profile_id = repo.save_mapping_profile(organization_id, name="default", resource_mappings=resource_mappings, validation_status=status)
    repo.set_mapping_profile(organization_id, mapping_profile_id)
    return {"status": status, "resource_mappings": resource_mappings, "mapping_profile_id": mapping_profile_id}


@require_role("Platform Admin")
def run_initial_sync(organization_id: int) -> dict[str, Any]:
    """Step 6: a real, full (non-incremental) sync of every enabled
    resource, through the accepted A+B PersistentSyncService/
    PostgresIntegrationBoundary — the SAME code path Workstream A+B's own
    acceptance tests exercise, not a parallel implementation.

    page_size=100 (POST_72H_MASTER_PRODUCTION_CLOSURE, incremental-sync
    investigation): the previous default of 3 meant a 10,000-record
    resource required ~3,334 HTTP round trips (this is exactly what made
    the 72h simulation's periodic incremental sync exceed its 600s
    timeout on 25/25 scheduled attempts — see
    INCREMENTAL_SYNC_ROOT_CAUSE_AND_FIX.md). 100 matches the real test
    simulator's own documented page_size cap (`simulator/lms_cms_simulator.py`)
    and is not itself the root cause fix (that is the simulation-only
    Moodle-proxy tooling not honoring `updated_since`, out of EduDSS's
    own scope) — but it is a real, independently-justified reduction in
    round-trip amplification regardless of server-side filtering
    behavior."""
    from dss.integrations.postgres_lms_cms import PersistentSyncService, PostgresIntegrationBoundary

    config = repo.get_connector_config(organization_id)
    if config is None:
        return {"status": "FAILED", "detail": "No connector configured."}

    connector = _build_connector(config)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"status": "FAILED", "detail": "DATABASE_URL is not configured; cannot sync into PostgreSQL."}

    boundary = PostgresIntegrationBoundary.create(organization_id, config["external_organization_id"], database_url)
    service = PersistentSyncService(connector, boundary)
    results = service.sync_all(page_size=100, incremental=False)
    repo.record_successful_sync(organization_id)
    _logger.info("initial sync completed: org_id=%s resources=%s", organization_id, list(results.keys()))
    return {"status": "SUCCESS", "results": results}


@require_role("Platform Admin")
def run_incremental_sync(organization_id: int) -> dict[str, Any]:
    """Post-activation re-sync — same service, incremental=True (only
    records updated since the last recorded cursor)."""
    from dss.integrations.postgres_lms_cms import PersistentSyncService, PostgresIntegrationBoundary

    config = repo.get_connector_config(organization_id)
    if config is None:
        return {"status": "FAILED", "detail": "No connector configured."}
    connector = _build_connector(config)
    database_url = os.environ.get("DATABASE_URL")
    boundary = PostgresIntegrationBoundary.create(organization_id, config["external_organization_id"], database_url)
    service = PersistentSyncService(connector, boundary)
    results = service.sync_all(page_size=100, incremental=True)
    repo.record_successful_sync(organization_id)
    return {"status": "SUCCESS", "results": results}


@require_role("Platform Admin")
def activate_university(organization_id: int, accept_without_sync: bool = False) -> ActivationResult:
    """Step 7 — the activation gate (§2.7): READY/ACTIVE is never granted
    merely because a row exists. Checks, in order, and collects EVERY
    failing reason (not just the first) so the caller gets one actionable
    list instead of a fix-one-fail-again loop:

    - organization exists and is not already DISABLED
    - at least one Admin user exists for this organization
    - a connector configuration exists
    - the connector's last connection test succeeded
    - a mapping profile exists and is VALID
    - the initial sync succeeded, UNLESS accept_without_sync=True is
      explicitly passed (a documented, deliberate override for an org
      that intentionally has no data yet — never a silent default)
    """
    reasons: list[str] = []

    org = repo.get_organization(organization_id)
    if org is None:
        return ActivationResult(False, [f"Organization {organization_id} does not exist."])
    if org["lifecycle_status"] == "DISABLED":
        reasons.append("Organization is DISABLED — re-enable before activating.")

    admin_count = UserRepository(organization_id).count_users_by_role().get("Admin", 0)
    if admin_count < 1:
        reasons.append("No Admin user exists for this organization.")

    config = repo.get_connector_config(organization_id)
    if config is None:
        reasons.append("No LMS/CMS connector is configured.")
    else:
        if config["last_connection_status"] != "SUCCESS":
            reasons.append("Connector's last connection test did not succeed — run Test Connection.")
        if config["configuration_status"] != "VALID":
            reasons.append(f"Connector configuration_status is {config['configuration_status']!r}, expected VALID.")
        if config["mapping_profile_id"] is None:
            reasons.append("No canonical mapping profile is linked to this connector.")
        else:
            mapping = repo.get_mapping_profile(organization_id, config["mapping_profile_id"])
            if mapping is None or mapping["validation_status"] != "VALID":
                reasons.append("Canonical mapping profile is not VALID — run mapping validation.")
        if config["last_successful_sync_at"] is None and not accept_without_sync:
            reasons.append(
                "No successful initial sync recorded — run Initial Sync, or explicitly pass "
                "accept_without_sync=True if this organization intentionally has no data yet."
            )

    if reasons:
        _logger.warning("activation blocked: org_id=%s reasons=%s", organization_id, reasons)
        return ActivationResult(False, reasons)

    repo.set_lifecycle_status(organization_id, "ACTIVE")
    _logger.info("university activated: org_id=%s", organization_id)
    return ActivationResult(True, [])
