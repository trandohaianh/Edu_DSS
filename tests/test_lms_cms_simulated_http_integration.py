"""Real HTTP integration tests for the separate LMS/CMS simulator process."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from dss.integrations.lms_cms_connector import (
    ExternalIdMapper, InMemoryIntegrationBoundary, IntegrationError,
    LMSCMSConnector, WebhookProcessor, WebhookReceiver,
)

APP_ROOT = Path(__file__).resolve().parents[1]
TOKEN_A = "sim-token-org-a"
SECRET = "simulator-webhook-secret"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return sock.getsockname()[1]


@pytest.fixture(scope="module")
def simulator_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulator.lms_cms_simulator", "--host", "127.0.0.1", "--port", str(port)],
        cwd=APP_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        if proc.poll() is not None:
            out, err = proc.communicate(); pytest.fail(f"simulator exited: {out} {err}")
        try:
            if requests.get(url + "/health", timeout=.2).status_code == 200: break
        except requests.RequestException: time.sleep(.05)
    else: proc.terminate(); pytest.fail("simulator failed to start")
    yield url
    proc.terminate()
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired: proc.kill()


@pytest.fixture
def connector(simulator_url):
    return LMSCMSConnector(simulator_url, TOKEN_A, "org-a", timeout=.2, max_attempts=3)


def test_separate_process_health(connector):
    assert connector.health() == {"status": "ok", "service": "simulated-university-lms-cms"}


def test_authentication_401(simulator_url):
    bad = LMSCMSConnector(simulator_url, "invalid", "org-a", max_attempts=1)
    with pytest.raises(IntegrationError) as exc: bad.fetch("courses")
    assert (exc.value.code, exc.value.status) == ("unauthorized", 401)


def test_wrong_tenant_403(simulator_url):
    bad = LMSCMSConnector(simulator_url, TOKEN_A, "org-b", max_attempts=1)
    with pytest.raises(IntegrationError) as exc: bad.fetch("courses")
    assert (exc.value.code, exc.value.status) == ("tenant_forbidden", 403)


def test_unknown_endpoint_404(connector):
    with pytest.raises(IntegrationError) as exc: connector._get("/api/unknown", {})
    assert (exc.value.code, exc.value.status) == ("not_found", 404)


def test_paginated_all_resources_and_stable_relationships(connector):
    courses = connector.fetch("courses", page_size=1)
    enrollments = connector.fetch("enrollments", page_size=2)
    assert len(courses) == 2 and len(enrollments) == 8
    assert {e["course_external_id"] for e in enrollments} <= {c["course_external_id"] for c in courses}
    assert all(x["organization_id"] == "org-a" for x in courses + enrollments)


def test_incremental_sync(connector):
    all_rows = connector.fetch("content")
    later = connector.fetch("content", updated_since=all_rows[0]["updated_at"])
    assert len(later) == 1 and later[0]["updated_at"] > all_rows[0]["updated_at"]


def test_duplicate_records_are_deduplicated(connector):
    rows = connector.fetch("courses", page_size=10, duplicate=True)
    assert len(rows) == 2


def test_mapping_is_stable_and_tenant_specific():
    mapper = ExternalIdMapper()
    first = mapper.resolve("org-a", "students", "stu-A-01")
    assert first == mapper.resolve("org-a", "students", "stu-A-01")
    assert first != mapper.resolve("org-b", "students", "stu-A-01")


def test_sync_is_idempotent_and_covers_contract(connector):
    boundary = InMemoryIntegrationBoundary()
    first = connector.sync(boundary); second = connector.sync(boundary)
    assert set(first) == {"users","students","lecturers","courses","enrollments","assignments","submissions","grades","attendance","activities","content"}
    assert all(value > 0 for value in first.values())
    assert all(value == 0 for value in second.values())


def test_429_retries_then_succeeds(connector):
    assert len(connector.fetch("courses", scenario="429")) == 2


def test_500_is_structured_after_retries(connector):
    with pytest.raises(IntegrationError) as exc: connector.fetch("courses", scenario="500")
    assert exc.value.code == "server_error" and exc.value.retryable


def test_timeout_is_structured(simulator_url):
    slow = LMSCMSConnector(simulator_url, TOKEN_A, "org-a", timeout=.03, max_attempts=2)
    with pytest.raises(IntegrationError) as exc: slow.fetch("courses", scenario="timeout")
    assert exc.value.code == "timeout" and exc.value.retryable


def test_malformed_json_rejected(connector):
    with pytest.raises(IntegrationError) as exc: connector.fetch("courses", scenario="malformed")
    assert exc.value.code == "malformed_json"


def test_schema_invalid_payload_rejected(connector):
    with pytest.raises(IntegrationError) as exc:
        connector.fetch("courses", scenario="invalid_payload")
    assert exc.value.code == "invalid_payload"


def _deliver(simulator_url, receiver, mode="normal"):
    response = requests.post(
        simulator_url + "/api/webhooks/deliver",
        headers={"Authorization": f"Bearer {TOKEN_A}", "X-Organization-ID": "org-a"},
        json={"callback_url": receiver.url, "mode": mode}, timeout=5,
    )
    response.raise_for_status(); return response.json()["deliveries"]


def _receiver(transient_failures=0):
    boundary = InMemoryIntegrationBoundary(); processor = WebhookProcessor("org-a", SECRET, boundary); receiver = WebhookReceiver(processor, transient_failures=transient_failures); receiver.start(); return boundary, processor, receiver


def test_normal_webhook_delivery_and_cms_rag_hook(simulator_url):
    boundary, processor, receiver = _receiver()
    try:
        deliveries = _deliver(simulator_url, receiver)
        assert [x["status"] for x in deliveries] == [200, 200, 200]
        assert len(processor.seen_events) == 3
        assert boundary.rag_invalidations == ["content-A-01"]
        assert any(x["operation"] == "rag.invalidate_and_reindex.requested" for x in boundary.audit)
    finally: receiver.stop()


def test_duplicate_webhook_event_is_idempotent(simulator_url):
    boundary, processor, receiver = _receiver()
    try:
        deliveries = _deliver(simulator_url, receiver, "duplicate")
        assert [x["status"] for x in deliveries] == [200, 200]
        assert len(processor.seen_events) == 1
        assert len(boundary.records["submissions"]) == 1
    finally: receiver.stop()


def test_out_of_order_event_does_not_overwrite_newer(simulator_url):
    boundary, processor, receiver = _receiver()
    try:
        deliveries = _deliver(simulator_url, receiver, "out_of_order")
        assert all(x["status"] == 200 for x in deliveries)
        assert len(processor.seen_events) == 2 and len(boundary.records["grades"]) == 1
        assert sum(x["operation"] == "upsert" for x in boundary.audit) == 1
    finally: receiver.stop()


def test_webhook_retry_on_429(simulator_url):
    boundary, processor, receiver = _receiver(transient_failures=2)
    try:
        delivery = _deliver(simulator_url, receiver, "duplicate")[0]
        assert delivery == {"event_id": "evt-A-submission-1", "status": 200, "attempts": 3}
    finally: receiver.stop()


@pytest.mark.parametrize("mode,expected", [("invalid",400),("wrong_tenant",403)])
def test_invalid_and_wrong_tenant_webhooks(simulator_url, mode, expected):
    boundary, processor, receiver = _receiver()
    try: assert _deliver(simulator_url, receiver, mode)[0]["status"] == expected
    finally: receiver.stop()
    assert not processor.seen_events and not any(boundary.records[x] for x in boundary.records)


def test_webhook_invalid_signature_rejected():
    boundary = InMemoryIntegrationBoundary(); processor = WebhookProcessor("org-a", SECRET, boundary)
    assert processor.process(b"{}", "wrong") == (401, {"status":"invalid_signature"})


def test_tenant_a_and_b_cannot_be_confused(simulator_url, connector):
    other = LMSCMSConnector(simulator_url, "sim-token-org-b", "org-b")
    a_ids = {x["student_external_id"] for x in connector.fetch("students")}
    b_ids = {x["student_external_id"] for x in other.fetch("students")}
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)


def test_admin_lecturer_student_role_journeys(connector):
    boundary = InMemoryIntegrationBoundary(); counts = connector.sync(boundary)
    # Admin observes health, executes complete sync and can inspect the integration audit.
    assert connector.health()["status"] == "ok" and sum(counts.values()) > 0 and boundary.audit
    # Lecturer sees their synchronized courses and related academic facts.
    lecturer_id = next(iter(boundary.records["lecturers"].values()))["lecturer_external_id"]
    lecturer_courses = [x for x in boundary.records["courses"].values() if x["lecturer_external_id"] == lecturer_id]
    assert lecturer_courses
    course_id = lecturer_courses[0]["course_external_id"]
    assert any(x["course_external_id"] == course_id for x in boundary.records["grades"].values())
    assert any(x["course_external_id"] == course_id for x in boundary.records["attendance"].values())
    assert any(x["course_external_id"] == course_id for x in boundary.records["activities"].values())
    # Student sees only their own synchronized enrollment, grade, attendance and activity.
    student_id = next(iter(boundary.records["students"].values()))["student_external_id"]
    assert any(x["student_external_id"] == student_id for x in boundary.records["enrollments"].values())
    assert any(x["student_external_id"] == student_id for x in boundary.records["grades"].values())
    assert any(x["student_external_id"] == student_id for x in boundary.records["attendance"].values())
    assert any(x["student_external_id"] == student_id for x in boundary.records["activities"].values())
