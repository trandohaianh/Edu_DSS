"""Real PostgreSQL acceptance tests for Stage 2 (University Onboarding).

Same conventions as tests/test_workstream_ab_postgres_integration.py: real
HTTP against a local-subprocess LMS/CMS simulator (the accepted Workstream
A simulator, unmodified), DATABASE_URL pointed at the non-superuser app
role for every write, and a genuine deterministic acceptance scenario
(§2.10 of the Stage 2 spec): University A already exists; University B is
onboarded through this module ONLY (no source copying, no second
implementation, no data inserted behind the service's back); both remain
operational and mutually isolated.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_ONBOARDING_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_ONBOARDING_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not OWNER_URL or not APP_URL, reason="University onboarding PostgreSQL URLs are required"
)
APP_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _application_database():
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = APP_URL or ""
    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    yield
    reset_engine_for_tests()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="module")
def simulator():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulator.lms_cms_simulator", "--host", "127.0.0.1", "--port", str(port)],
        cwd=APP_ROOT,
    )
    url = f"http://127.0.0.1:{port}"
    import time

    for _ in range(80):
        try:
            if requests.get(url + "/health", timeout=0.2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)
    else:
        proc.terminate()
        pytest.fail("simulator did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=5)


def _free_port():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(autouse=True)
def _seed_roles_once():
    owner = create_engine(OWNER_URL)
    with owner.begin() as conn:
        for role in ("Admin", "Giảng viên / CVHT", "Sinh viên", "Platform Admin"):
            conn.execute(
                text(
                    "INSERT INTO roles (name,created_at,updated_at) VALUES (:r,now(),now()) ON CONFLICT (name) DO NOTHING"
                ),
                {"r": role},
            )
    owner.dispose()


@pytest.fixture
def as_platform_admin(monkeypatch):
    import streamlit as st

    st.session_state["_auth_role"] = "Platform Admin"
    yield
    st.session_state.pop("_auth_role", None)


def _bootstrap_university_a(owner_url: str) -> int:
    """University A 'already exists' — created directly (as it would be by
    an earlier onboarding, or a pre-existing deployment), NOT through the
    module under test, so this test genuinely proves B's onboarding doesn't
    disturb an independently-existing A."""
    owner = create_engine(owner_url)
    code = "uniA_" + uuid.uuid4().hex[:8]
    with owner.begin() as conn:
        org_id = conn.execute(
            text(
                "INSERT INTO organizations (org_code,name,is_active,lifecycle_status,deployment_mode,created_at,updated_at) "
                "VALUES (:c,:n,true,'ACTIVE','MULTI_TENANT_SAAS',now(),now()) RETURNING id"
            ),
            {"c": code, "n": "University A"},
        ).scalar_one()
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_id)})
        conn.execute(
            text(
                "INSERT INTO subscriptions (organization_id,plan,status,max_students,max_courses,max_ai_requests_month,max_storage_mb,features_enabled,created_at,updated_at) "
                "VALUES (:o,'ENTERPRISE','ACTIVE',100,100,100,1000,'[]',now(),now())"
            ),
            {"o": org_id},
        )
    owner.dispose()
    return org_id


def test_01_onboard_university_b_while_university_a_remains_operational(simulator, as_platform_admin, monkeypatch):
    """The core §2.10 acceptance scenario, in one deterministic test."""
    from dss.db.repositories import university_repository as repo
    from dss.services import university_onboarding as onboarding

    org_a = _bootstrap_university_a(OWNER_URL)

    # --- Onboard University B, entirely through the service under test ---
    org_code_b = "uniB_" + uuid.uuid4().hex[:8]
    org_b = onboarding.provision_university(org_code_b, "University B", deployment_mode="MULTI_TENANT_SAAS")
    assert repo.get_organization(org_b)["lifecycle_status"] == "SETUP"

    onboarding.create_university_admin(org_b, "admin_uniB", "uniB_admin_pw_123")
    assert repo.get_organization(org_b)["lifecycle_status"] == "CONFIGURING"

    cred_ref = f"TEST_LMS_TOKEN_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(cred_ref, "sim-token-org-b")
    onboarding.configure_connector(
        org_b,
        connector_type="simulated_lms_cms",
        external_organization_id="org-b",
        base_url=simulator,
        credential_reference=cred_ref,
    )

    conn_result = onboarding.test_connection(org_b)
    assert conn_result["status"] == "SUCCESS", conn_result

    mapping_result = onboarding.validate_mapping(org_b)
    assert mapping_result["status"] == "VALID", mapping_result

    sync_result = onboarding.run_initial_sync(org_b)
    assert sync_result["status"] == "SUCCESS", sync_result
    assert sync_result["results"]["students"]["fetched"] > 0

    activation = onboarding.activate_university(org_b)
    assert activation.activated, activation.reasons
    assert repo.get_organization(org_b)["lifecycle_status"] == "ACTIVE"

    # --- University A remains completely untouched and operational ---
    org_a_after = repo.get_organization(org_a)
    assert org_a_after["lifecycle_status"] == "ACTIVE"

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_b)})
        b_students = conn.execute(
            text("SELECT count(*) FROM students WHERE organization_id=:o"), {"o": org_b}
        ).scalar_one()
        a_visible_from_b = conn.execute(
            text("SELECT count(*) FROM students WHERE organization_id=:o"), {"o": org_a}
        ).scalar_one()
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_a)})
        b_visible_from_a = conn.execute(
            text("SELECT count(*) FROM students WHERE organization_id=:o"), {"o": org_b}
        ).scalar_one()
    app_engine.dispose()

    assert b_students > 0  # B genuinely synced its own data
    assert a_visible_from_b == 0  # B cannot see A's data (RLS)
    assert b_visible_from_a == 0  # A cannot see B's data (RLS)


def test_02_activation_gate_blocks_incomplete_onboarding_with_actionable_reasons(as_platform_admin):
    from dss.db.repositories import university_repository as repo
    from dss.services import university_onboarding as onboarding

    org_id = onboarding.provision_university("uniC_" + uuid.uuid4().hex[:8], "University C (incomplete)")

    result = onboarding.activate_university(org_id)
    assert result.activated is False
    assert any("Admin" in r for r in result.reasons)
    assert any("connector" in r.lower() for r in result.reasons)
    assert repo.get_organization(org_id)["lifecycle_status"] != "ACTIVE"


def test_03_test_connection_reports_honest_failures_not_fabricated_success(simulator, as_platform_admin, monkeypatch):
    from dss.services import university_onboarding as onboarding

    org_id = onboarding.provision_university("uniD_" + uuid.uuid4().hex[:8], "University D")

    # Wrong token -> 401
    bad_cred = f"TEST_BAD_TOKEN_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(bad_cred, "not-a-real-token")
    onboarding.configure_connector(org_id, "simulated_lms_cms", "org-a", simulator, bad_cred)
    result = onboarding.test_connection(org_id)
    assert result["status"] == "FAILED"
    assert result["http_status"] == 401

    # Valid token, wrong external org claimed -> 403
    good_cred = f"TEST_GOOD_TOKEN_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(good_cred, "sim-token-org-a")
    onboarding.configure_connector(
        org_id, "simulated_lms_cms", "org-b", simulator, good_cred
    )  # token is for org-a, claims org-b
    result = onboarding.test_connection(org_id)
    assert result["status"] == "FAILED"
    assert result["http_status"] == 403

    # Credential reference doesn't resolve at all (env var unset)
    onboarding.configure_connector(
        org_id, "simulated_lms_cms", "org-a", simulator, f"TEST_UNSET_{uuid.uuid4().hex[:8]}"
    )
    result = onboarding.test_connection(org_id)
    assert result["status"] == "FAILED"
    assert "did not resolve" in result["detail"]

    # Server error scenario (real simulator scenario injection)
    onboarding.configure_connector(org_id, "simulated_lms_cms", "org-a", simulator, good_cred)
    monkeypatch.setenv(good_cred, "sim-token-org-a")
    result = onboarding.test_connection(org_id, scenario="500")
    assert result["status"] == "FAILED"
    assert result["http_status"] == 500

    # Genuine success
    result = onboarding.test_connection(org_id)
    assert result["status"] == "SUCCESS"
    assert result["http_status"] == 200


def test_04_configure_connector_rejects_raw_secret_as_credential_reference(as_platform_admin):
    from dss.services import university_onboarding as onboarding

    org_id = onboarding.provision_university("uniE_" + uuid.uuid4().hex[:8], "University E")
    with pytest.raises(ValueError, match="credential_reference"):
        onboarding.configure_connector(
            org_id,
            "simulated_lms_cms",
            "org-a",
            "http://localhost:8765",
            credential_reference="sim-token-org-a-actual-secret-value-pasted-directly this has spaces",
        )


def test_05_disable_university_preserves_data_does_not_delete(simulator, as_platform_admin, monkeypatch):
    from dss.db.repositories import university_repository as repo
    from dss.services import university_onboarding as onboarding

    org_id = onboarding.provision_university("uniF_" + uuid.uuid4().hex[:8], "University F")
    onboarding.create_university_admin(org_id, "admin_uniF", "uniF_admin_pw_123")
    cred_ref = f"TEST_TOKEN_F_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(cred_ref, "sim-token-org-a")
    onboarding.configure_connector(org_id, "simulated_lms_cms", "org-a", simulator, cred_ref)
    onboarding.test_connection(org_id)
    onboarding.validate_mapping(org_id)
    onboarding.run_initial_sync(org_id)
    onboarding.activate_university(org_id)

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_id)})
        before = conn.execute(
            text("SELECT count(*) FROM students WHERE organization_id=:o"), {"o": org_id}
        ).scalar_one()
    app_engine.dispose()
    assert before > 0

    repo.disable_organization(org_id)
    assert repo.get_organization(org_id)["lifecycle_status"] == "DISABLED"

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_id)})
        after = conn.execute(text("SELECT count(*) FROM students WHERE organization_id=:o"), {"o": org_id}).scalar_one()
    app_engine.dispose()
    assert after == before  # disabling never deletes tenant data

    repo.enable_organization(org_id)
    assert repo.get_organization(org_id)["lifecycle_status"] == "ACTIVE"


def test_06_repeat_initial_sync_is_idempotent(simulator, as_platform_admin, monkeypatch):
    from dss.services import university_onboarding as onboarding

    org_id = onboarding.provision_university("uniG_" + uuid.uuid4().hex[:8], "University G")
    cred_ref = f"TEST_TOKEN_G_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(cred_ref, "sim-token-org-a")
    onboarding.configure_connector(org_id, "simulated_lms_cms", "org-a", simulator, cred_ref)

    first = onboarding.run_initial_sync(org_id)
    second = onboarding.run_initial_sync(org_id)
    assert first["status"] == second["status"] == "SUCCESS"
    assert all(v["changed"] == 0 for v in second["results"].values())


def test_07_non_superuser_cross_tenant_connector_and_mapping_isolated(simulator, as_platform_admin, monkeypatch):
    """Genuine RLS check on the NEW tables (lms_connector_configs,
    lms_mapping_profiles) using the non-superuser app role — not an
    owner/superuser bypass."""
    from dss.services import university_onboarding as onboarding

    org_h = onboarding.provision_university("uniH_" + uuid.uuid4().hex[:8], "University H")
    cred_ref = f"TEST_TOKEN_H_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(cred_ref, "sim-token-org-a")
    onboarding.configure_connector(org_h, "simulated_lms_cms", "org-a", simulator, cred_ref)
    onboarding.validate_mapping(org_h)

    org_i = onboarding.provision_university("uniI_" + uuid.uuid4().hex[:8], "University I")

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_i)})
        connector_visible = conn.execute(
            text("SELECT count(*) FROM lms_connector_configs WHERE organization_id=:o"), {"o": org_h}
        ).scalar_one()
        mapping_visible = conn.execute(
            text("SELECT count(*) FROM lms_mapping_profiles WHERE organization_id=:o"), {"o": org_h}
        ).scalar_one()
    app_engine.dispose()
    assert connector_visible == 0
    assert mapping_visible == 0
