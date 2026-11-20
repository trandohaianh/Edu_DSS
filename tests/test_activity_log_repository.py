"""dss/db/repositories/activity_log_repository.py + warehouse.py's Postgres
wiring for the user-facing activity feed (Phase 1C, priority item 9).
Skipped (not faked) without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — activity log repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"ACTLOG_TEST_{uuid.uuid4().hex[:8]}", name="Activity Log Test Org")
        session.add(org)
        session.flush()
        return org.id


@pytest.fixture()
def warehouse(tmp_path):
    from dss.core.warehouse import DataWarehouse

    return DataWarehouse(base_path=str(tmp_path / "data_warehouse"))


def test_record_and_get_recent_activities(org_id):
    from dss.db.repositories import activity_log_repository as repo

    repo.record_activity(org_id, "Dự đoán", "Dự đoán cho 1 bản ghi", {"prediction_id": "abc"})
    activities = repo.get_recent_activities(org_id)
    assert len(activities) == 1
    assert activities[0]["action"] == "Dự đoán"
    assert activities[0]["metadata"]["prediction_id"] == "abc"


def test_cross_tenant_isolation(org_id):
    from dss.db.models import Organization
    from dss.db.repositories import activity_log_repository as repo
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"ACTLOG_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    repo.record_activity(org_id, "Test", "org A activity")
    assert len(repo.get_recent_activities(org_id)) == 1
    assert len(repo.get_recent_activities(other_org_id)) == 0


def test_warehouse_log_activity_writes_to_postgres_when_enabled(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_ACTIVITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    warehouse.log_activity("Huấn luyện", "Huấn luyện mô hình mới", {"model": "Ridge"})

    from dss.db.repositories import activity_log_repository as repo

    activities = repo.get_recent_activities(org_id)
    assert len(activities) == 1
    assert activities[0]["action"] == "Huấn luyện"


def test_warehouse_log_activity_does_not_dual_write_to_local_json(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_ACTIVITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    warehouse.log_activity("Test", "no dual write")

    import json
    import os

    path = os.path.join(warehouse.history_path, "activity_history.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == []


def test_warehouse_log_activity_local_mode_unaffected_by_default(warehouse, monkeypatch):
    monkeypatch.delenv("EDUDSS_ACTIVITY_STORE", raising=False)
    activity_id = warehouse.log_activity("Test", "local mode still works")
    assert activity_id

    activities = warehouse.get_recent_activities()
    assert len(activities) == 1
    assert activities[0]["action"] == "Test"


def test_warehouse_get_merged_recent_activities_reads_postgres_when_enabled(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_ACTIVITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    warehouse.log_activity("Merged Test", "should appear in merged feed")
    merged = warehouse.get_merged_recent_activities()
    assert len(merged) == 1
    assert merged[0]["activity_type"] == "Merged Test"


def test_import_activity_history_is_idempotent(warehouse, org_id, monkeypatch):
    monkeypatch.delenv("EDUDSS_ACTIVITY_STORE", raising=False)
    warehouse.log_activity("Import1", "first")
    warehouse.log_activity("Import2", "second")

    from dss.db.repositories import activity_log_repository as repo

    first = repo.import_from_local_history(org_id, warehouse=warehouse)
    assert first["imported"] == 2
    second = repo.import_from_local_history(org_id, warehouse=warehouse)
    assert second["imported"] == 0
    assert second["skipped_already_imported"] == 2
    assert len(repo.get_recent_activities(org_id)) == 2
