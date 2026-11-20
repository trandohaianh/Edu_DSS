"""dss/db/repositories/ai_token_usage_repository.py + token_tracker.py's
Postgres wiring (Phase 1C, priority item 10 — AI token usage). Skipped (not
faked) without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — AI token usage repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"TOKUSAGE_TEST_{uuid.uuid4().hex[:8]}", name="Token Usage Test Org")
        session.add(org)
        session.flush()
        return org.id


def test_record_and_load_all_records(org_id):
    from dss.db.repositories import ai_token_usage_repository as repo

    repo.record_usage(
        org_id,
        {
            "usage_id": f"use_{uuid.uuid4().hex[:12]}",
            "timestamp": "2026-09-18T10:00:00+00:00",
            "user_id": "sv001",
            "role": "Sinh viên",
            "request_type": "advisor_plan",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost": 0.0001,
        },
    )
    records = repo.load_all_records(org_id)
    assert len(records) == 1
    assert records[0]["user_id"] == "sv001"
    assert records[0]["total_tokens"] == 150


def test_cross_tenant_isolation(org_id):
    from dss.db.models import Organization
    from dss.db.repositories import ai_token_usage_repository as repo
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"TOKUSAGE_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    repo.record_usage(
        org_id,
        {
            "usage_id": f"use_{uuid.uuid4().hex[:12]}",
            "timestamp": "2026-09-18T10:00:00+00:00",
            "user_id": "sv001",
            "role": "Sinh viên",
            "request_type": "advisor_plan",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost": 0.0001,
        },
    )
    assert len(repo.load_all_records(org_id)) == 1
    assert len(repo.load_all_records(other_org_id)) == 0


def test_never_persists_secrets_or_api_keys(org_id):
    """The repository/model must not have any column that could hold an API
    key/Authorization header/full prompt — schema-level privacy check."""
    from dss.db.models import AiTokenUsage

    columns = {c.name for c in AiTokenUsage.__table__.columns}
    for forbidden in ("api_key", "authorization", "auth_header", "prompt", "secret"):
        assert forbidden not in columns


def test_token_tracker_record_usage_writes_to_postgres_when_enabled(org_id, monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_AI_TOKEN_USAGE_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.services import token_tracker

    record = token_tracker.record_usage(
        user_id="sv007",
        role="Sinh viên",
        request_type="advisor_plan",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=10,
        output_tokens=5,
    )
    assert record.total_tokens == 15

    from dss.db.repositories import ai_token_usage_repository as repo

    stored = repo.load_all_records(org_id)
    assert len(stored) == 1
    assert stored[0]["usage_id"] == record.usage_id


def test_token_tracker_does_not_dual_write_to_local_json(org_id, monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_AI_TOKEN_USAGE_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.services import token_tracker

    token_tracker.record_usage(
        user_id="sv008",
        role="Sinh viên",
        request_type="advisor_plan",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=10,
        output_tokens=5,
    )
    usage_file = tmp_path / "ai_token_usage.json"
    assert not usage_file.exists()


def test_token_tracker_local_mode_unaffected_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("EDUDSS_AI_TOKEN_USAGE_STORE", raising=False)
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.services import token_tracker

    token_tracker.clear_usage_records_for_tests()

    token_tracker.record_usage(
        user_id="sv009",
        role="Sinh viên",
        request_type="advisor_plan",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=10,
        output_tokens=5,
    )
    daily = token_tracker.get_user_daily_token_usage("sv009")
    assert daily == 15
    token_tracker.clear_usage_records_for_tests()


def test_token_tracker_aggregations_work_against_postgres(org_id, monkeypatch, tmp_path):
    """get_user_daily_token_usage / get_usage_summary must work unchanged
    against Postgres-sourced records — they only depend on _load_all_records()."""
    monkeypatch.setenv("EDUDSS_AI_TOKEN_USAGE_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.services import token_tracker

    token_tracker.record_usage(
        user_id="sv010",
        role="Sinh viên",
        request_type="advisor_plan",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=100,
        output_tokens=50,
    )
    assert token_tracker.get_user_daily_token_usage("sv010") == 150

    summary = token_tracker.get_usage_summary()
    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 150
