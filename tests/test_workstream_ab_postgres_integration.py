"""A+B acceptance through real HTTP, PostgreSQL/RLS and pgvector."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_AB_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_AB_DATABASE_URL")
pytestmark = pytest.mark.skipif(not OWNER_URL or not APP_URL, reason="A+B PostgreSQL URLs required")
APP_ROOT = Path(__file__).resolve().parents[1]
SECRET = "simulator-webhook-secret"


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


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def simulator():
    external = os.getenv("WORKSTREAM_AB_SIMULATOR_URL")
    if external:
        for _ in range(80):
            try:
                if requests.get(external + "/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.05)
        else:
            pytest.fail("external simulator did not become healthy")
        yield external, None
        return
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulator.lms_cms_simulator", "--host", "127.0.0.1", "--port", str(port)], cwd=APP_ROOT
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            if requests.get(url + "/health", timeout=0.2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)
    else:
        proc.terminate()
        pytest.fail("simulator did not start")
    yield url, proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def tenants():
    owner = create_engine(OWNER_URL)
    ids = {}
    with owner.begin() as conn:
        for role in ("Admin", "Giảng viên / CVHT", "Sinh viên"):
            conn.execute(
                text(
                    "INSERT INTO roles (name,created_at,updated_at) VALUES (:r,now(),now()) ON CONFLICT (name) DO NOTHING"
                ),
                {"r": role},
            )
        for external in ("org-a", "org-b"):
            code = f"ab-{external}-{uuid.uuid4().hex[:8]}"
            org = conn.execute(
                text(
                    "INSERT INTO organizations (org_code,name,is_active,created_at,updated_at) VALUES (:c,:n,true,now(),now()) RETURNING id"
                ),
                {"c": code, "n": external},
            ).scalar_one()
            conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org)})
            conn.execute(
                text(
                    "INSERT INTO subscriptions (organization_id,plan,status,max_students,max_courses,max_ai_requests_month,max_storage_mb,features_enabled,created_at,updated_at) VALUES (:o,'ENTERPRISE','ACTIVE',100,100,100,1000,'[]',now(),now())"
                ),
                {"o": org},
            )
            ids[external] = org
    owner.dispose()
    return ids


def _services(simulator_url, tenants, external):
    from dss.integrations.lms_cms_connector import LMSCMSConnector
    from dss.integrations.postgres_lms_cms import PersistentSyncService, PostgresIntegrationBoundary

    token = "sim-token-org-a" if external == "org-a" else "sim-token-org-b"
    connector = LMSCMSConnector(simulator_url, token, external, timeout=0.3, max_attempts=3)
    boundary = PostgresIntegrationBoundary.create(tenants[external], external, APP_URL)
    return connector, boundary, PersistentSyncService(connector, boundary)


def _deliver(simulator_url, receiver_url, mode="normal"):
    response = requests.post(
        simulator_url + "/api/webhooks/deliver",
        headers={"Authorization": "Bearer sim-token-org-a", "X-Organization-ID": "org-a"},
        json={"callback_url": receiver_url, "mode": mode},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["deliveries"]


def test_01_full_incremental_idempotent_sync_and_restart(simulator, tenants):
    simulator_url, proc = simulator
    services = {external: _services(simulator_url, tenants, external) for external in tenants}
    first = {external: service.sync_all(page_size=1) for external, (_, _, service) in services.items()}
    assert all(result["fetched"] > 0 for per_org in first.values() for result in per_org.values())
    assert first["org-a"]["enrollments"]["fetched"] == 8

    owner = create_engine(OWNER_URL)
    expected = {
        "users": 6,
        "students": 4,
        "lecturers": 2,
        "courses": 2,
        "enrollments": 8,
        "assignments": 2,
        "submissions": 8,
        "grades": 8,
        "attendance": 8,
        "learning_activities": 8,
        "cms_content": 2,
    }
    with owner.connect() as conn:
        for external, org in tenants.items():
            for table, count in expected.items():
                assert (
                    conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE organization_id=:o"), {"o": org}
                    ).scalar_one()
                    == count
                )

    second = {external: service.sync_all(page_size=2) for external, (_, _, service) in services.items()}
    assert all(result["changed"] == 0 for per_org in second.values() for result in per_org.values())

    headers = {"Authorization": "Bearer sim-token-org-a", "X-Organization-ID": "org-a"}
    mutation = requests.post(
        simulator_url + "/api/admin/mutate",
        headers=headers,
        json={
            "resource": "students",
            "external_id": "stu-A-01",
            "changes": {"display_name": "Student A Updated", "updated_at": "2026-01-16T00:00:00+00:00"},
        },
        timeout=3,
    )
    mutation.raise_for_status()
    # Move only this resource's cursor back to prove HTTP updated_since processing.
    from dss.db.repositories.domain_persistence_repository import get_sync_state, set_sync_state

    set_sync_state(
        tenants["org-a"], "simulated-lms-cms", "students", cursor="2026-01-15T08:13:00+00:00", status="success"
    )
    incremental = services["org-a"][2].sync_resource("students", incremental=True, page_size=1)
    assert incremental["fetched"] == 1 and incremental["cursor"] == "2026-01-16T00:00:00+00:00"
    with owner.connect() as conn:
        assert (
            conn.execute(
                text("SELECT full_name FROM students WHERE organization_id=:o AND external_id='stu-A-01'"),
                {"o": tenants["org-a"]},
            ).scalar_one()
            == "Student A Updated"
        )

    from dss.db.session import reset_engine_for_tests

    reset_engine_for_tests()
    restarted = _services(simulator_url, tenants, "org-a")[2]
    assert restarted.sync_resource("students", incremental=True)["fetched"] == 0
    assert get_sync_state(tenants["org-a"], "simulated-lms-cms", "students")["cursor"] == "2026-01-16T00:00:00+00:00"

    # Overlapping attempts serialize and remain duplicate-free.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: restarted.sync_resource("courses", incremental=False, page_size=1), range(2)))
    with owner.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM courses WHERE organization_id=:o"), {"o": tenants["org-a"]}
            ).scalar_one()
            == 2
        )
    owner.dispose()


def test_02_real_http_webhook_durable_inbox_and_cms_rag(simulator, tenants):
    simulator_url, _ = simulator
    connector, boundary, _ = _services(simulator_url, tenants, "org-a")
    from dss.integrations.lms_cms_connector import WebhookReceiver
    from dss.integrations.postgres_lms_cms import DurableWebhookProcessor, deterministic_embedding

    processor = DurableWebhookProcessor(tenants["org-a"], "org-a", SECRET, boundary)
    advertised = os.getenv("WORKSTREAM_AB_WEBHOOK_ADVERTISED_HOST")
    receiver = WebhookReceiver(processor, host="0.0.0.0" if advertised else "127.0.0.1", advertised_host=advertised)
    receiver.start()
    try:
        deliveries = _deliver(simulator_url, receiver.url)
        assert [item["status"] for item in deliveries] == [200, 200, 200]
        duplicate = _deliver(simulator_url, receiver.url, "duplicate")
        assert [item["status"] for item in duplicate] == [200, 200]
        ordered = _deliver(simulator_url, receiver.url, "out_of_order")
        assert [item["status"] for item in ordered] == [200, 200]
    finally:
        receiver.stop()

    owner = create_engine(OWNER_URL)
    org = tenants["org-a"]
    with owner.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM webhook_inbox WHERE organization_id=:o"), {"o": org}).scalar_one()
            == 4
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM webhook_inbox WHERE organization_id=:o AND processing_status='processed'"),
                {"o": org},
            ).scalar_one()
            == 3
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM webhook_inbox WHERE organization_id=:o AND processing_status='out_of_order'"
                ),
                {"o": org},
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("SELECT score FROM grades WHERE organization_id=:o AND external_id='grade-A-1-1'"), {"o": org}
            ).scalar_one()
            != 1
        )
        content = conn.execute(
            text(
                "SELECT version,rag_document_id FROM cms_content WHERE organization_id=:o AND external_id='content-A-01'"
            ),
            {"o": org},
        ).one()
        assert content.version == 2 and content.rag_document_id == "content-A-01:v2"
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM rag_chunks c JOIN rag_documents d ON d.id=c.document_id WHERE d.organization_id=:o AND d.document_id='content-A-01:v1'"
                ),
                {"o": org},
            ).scalar_one()
            == 0
        )
    results = boundary.vector_store.search(deterministic_embedding("Updated deterministic lesson for org-a."), top_k=5)
    assert results[0]["document_id"] == "content-A-01:v2"
    assert all(result["document_id"] != "content-A-01:v1" for result in results)

    # New processor instance after application restart still sees duplicate inbox state.
    restarted = DurableWebhookProcessor(org, "org-a", SECRET, boundary)
    receiver = WebhookReceiver(restarted, host="0.0.0.0" if advertised else "127.0.0.1", advertised_host=advertised)
    receiver.start()
    try:
        assert _deliver(simulator_url, receiver.url, "duplicate")[0]["status"] == 200
    finally:
        receiver.stop()
    with owner.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM webhook_inbox WHERE organization_id=:o AND event_id='evt-A-submission-1'"),
                {"o": org},
            ).scalar_one()
            == 1
        )
    owner.dispose()


def test_03_non_superuser_rls_and_same_external_id_is_tenant_scoped(simulator, tenants):
    simulator_url, _ = simulator
    from dss.db.repositories.domain_persistence_repository import upsert_external

    for org in tenants.values():
        upsert_external(
            org, "students", {"organization_id": org, "student_external_id": "shared-student", "display_name": "Shared"}
        )
    app = create_engine(APP_URL)
    a, b = tenants["org-a"], tenants["org-b"]
    with app.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(a)})
        assert conn.execute(text("SELECT count(*) FROM students WHERE organization_id=:b"), {"b": b}).scalar_one() == 0
        assert conn.execute(text("UPDATE students SET full_name='x' WHERE organization_id=:b"), {"b": b}).rowcount == 0
        assert conn.execute(text("DELETE FROM students WHERE organization_id=:b"), {"b": b}).rowcount == 0
        with pytest.raises(Exception):
            conn.execute(
                text(
                    "INSERT INTO students (organization_id,student_code,external_id,full_name,is_active,created_at,updated_at) VALUES (:b,'attack','attack','attack',true,now(),now())"
                ),
                {"b": b},
            )
    app.dispose()


def test_04_failed_sync_preserves_cursor_and_recovers(simulator, tenants):
    simulator_url, _ = simulator
    _, _, service = _services(simulator_url, tenants, "org-a")
    from dss.db.repositories.domain_persistence_repository import get_sync_state

    before = get_sync_state(tenants["org-a"], "simulated-lms-cms", "courses")["cursor"]
    with pytest.raises(Exception):
        service.sync_resource("courses", incremental=True, scenario="500")
    failed = get_sync_state(tenants["org-a"], "simulated-lms-cms", "courses")
    assert failed["cursor"] == before and failed["status"] == "failed"
    assert service.sync_resource("courses", incremental=True)["cursor"] == before
