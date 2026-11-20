"""dss/core/warehouse.py::save_prediction()/save_ai_consultation() — real
PostgreSQL wiring (Phase 1B, migration order items 6 and 8). Skipped (not
faked) without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — prediction/consultation Postgres-wiring tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"PRED_TEST_{uuid.uuid4().hex[:8]}", name="Prediction Test Org")
        session.add(org)
        session.flush()
        return org.id


@pytest.fixture()
def warehouse(tmp_path):
    from dss.core.warehouse import DataWarehouse

    return DataWarehouse(base_path=str(tmp_path / "data_warehouse"))


def test_save_prediction_writes_to_postgres_when_enabled(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_PREDICTIONS_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    prediction_id = warehouse.save_prediction(
        {
            "training_id": "tid_test_001",
            "inputs": {"student_id": "SV777"},
            "value": 8.5,
            "metadata": {"model_name": "RandomForest", "confidence": 0.91},
        }
    )
    assert prediction_id  # local id still returned for the activity-log caption

    from dss.db.repositories import prediction_repository

    rows = prediction_repository.list_predictions(org_id)
    assert len(rows) == 1
    assert rows[0]["prediction_value"] == "8.5"
    assert rows[0]["confidence"] == 0.91


def test_save_prediction_does_not_dual_write_to_local_json_when_postgres_enabled(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_PREDICTIONS_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    warehouse.save_prediction({"training_id": "tid_test_002", "value": 5.0, "metadata": {}})

    import json
    import os

    path = os.path.join(warehouse.history_path, "prediction_history.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            local_records = json.load(f)
        assert local_records == []  # nothing written locally — Postgres is the sole store


def test_save_prediction_local_mode_unaffected_by_default(warehouse, monkeypatch):
    """Default (no env var set) must behave exactly as before Phase 1B."""
    monkeypatch.delenv("EDUDSS_PREDICTIONS_STORE", raising=False)
    prediction_id = warehouse.save_prediction({"training_id": "tid_local", "value": 6.0, "metadata": {}})
    assert prediction_id

    import json
    import os

    path = os.path.join(warehouse.history_path, "prediction_history.json")
    with open(path, encoding="utf-8") as f:
        local_records = json.load(f)
    assert len(local_records) == 1
    assert local_records[0]["prediction_id"] == prediction_id


def test_save_consultation_writes_to_postgres_when_enabled(warehouse, org_id, monkeypatch):
    monkeypatch.setenv("EDUDSS_CONSULTATIONS_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    warehouse.save_ai_consultation(
        {
            "student_id": "SV888",
            "provider": "gemini",
            "model_name": "gemini-1.5-flash",
            "rag_query": "How to improve GPA?",
            "generated_plan": "Study more.",
        }
    )

    from dss.db.repositories import consultation_repository

    rows = consultation_repository.list_consultations(org_id)
    assert len(rows) == 1
    assert rows[0]["provider"] == "gemini"


def test_save_consultation_local_mode_unaffected_by_default(warehouse, monkeypatch):
    monkeypatch.delenv("EDUDSS_CONSULTATIONS_STORE", raising=False)
    consultation_id = warehouse.save_ai_consultation(
        {
            "student_id": "SV999",
            "provider": "groq",
            "generated_plan": "Practice daily.",
        }
    )
    assert consultation_id

    import json
    import os

    path = os.path.join(warehouse.history_path, "advisor_history.json")
    with open(path, encoding="utf-8") as f:
        local_records = json.load(f)
    assert len(local_records) == 1


def test_postgres_enabled_without_organization_id_fails_loudly(warehouse, monkeypatch):
    monkeypatch.setenv("EDUDSS_PREDICTIONS_STORE", "postgres")
    monkeypatch.delenv("EDUDSS_ORGANIZATION_ID", raising=False)
    with pytest.raises(RuntimeError, match="EDUDSS_ORGANIZATION_ID"):
        warehouse.save_prediction({"training_id": "tid_x", "value": 1.0, "metadata": {}})


def test_import_prediction_history_is_idempotent(warehouse, org_id, monkeypatch):
    """Migration safety: local JSON history existed BEFORE Postgres was
    enabled (the realistic incremental-cutover scenario) — import it, then
    import again, and confirm no duplicates."""
    monkeypatch.delenv("EDUDSS_PREDICTIONS_STORE", raising=False)
    warehouse.save_prediction(
        {
            "training_id": "tid_import_1",
            "inputs": {"student_id": "SV_IMPORT"},
            "value": 7.0,
            "metadata": {"confidence": 0.8},
        }
    )
    warehouse.save_prediction({"training_id": "tid_import_2", "value": 6.5, "metadata": {}})

    from dss.db.repositories import prediction_repository

    first = prediction_repository.import_from_local_history(org_id, warehouse=warehouse)
    assert first["imported"] == 2
    assert first["skipped_already_imported"] == 0

    second = prediction_repository.import_from_local_history(org_id, warehouse=warehouse)
    assert second["imported"] == 0
    assert second["skipped_already_imported"] == 2

    assert len(prediction_repository.list_predictions(org_id)) == 2


def test_import_prediction_history_empty_db_is_a_noop(warehouse, org_id):
    from dss.db.repositories import prediction_repository

    result = prediction_repository.import_from_local_history(org_id, warehouse=warehouse)
    assert result == {"imported": 0, "skipped_already_imported": 0, "total_local_records": 0}


def test_import_prediction_history_assigns_correct_tenant(warehouse, org_id, monkeypatch):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other_org = Organization(org_code=f"PRED_IMPORT_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    monkeypatch.delenv("EDUDSS_PREDICTIONS_STORE", raising=False)
    warehouse.save_prediction({"training_id": "tid_tenant_import", "value": 5.0, "metadata": {}})

    from dss.db.repositories import prediction_repository

    prediction_repository.import_from_local_history(org_id, warehouse=warehouse)

    assert len(prediction_repository.list_predictions(org_id)) == 1
    assert len(prediction_repository.list_predictions(other_org_id)) == 0  # never silently cross-assigned


def test_import_consultation_history_is_idempotent(warehouse, org_id, monkeypatch):
    monkeypatch.delenv("EDUDSS_CONSULTATIONS_STORE", raising=False)
    warehouse.save_ai_consultation({"student_id": "SV_IMPORT", "provider": "gemini", "generated_plan": "Plan A"})
    warehouse.save_ai_consultation({"student_id": "unknown", "provider": "groq", "generated_plan": "Plan B"})

    from dss.db.repositories import consultation_repository

    first = consultation_repository.import_from_local_history(org_id, warehouse=warehouse)
    assert first["imported"] == 2

    second = consultation_repository.import_from_local_history(org_id, warehouse=warehouse)
    assert second["imported"] == 0
    assert second["skipped_already_imported"] == 2
    assert len(consultation_repository.list_consultations(org_id)) == 2


def test_predictions_are_tenant_isolated(warehouse, org_id, monkeypatch):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other_org = Organization(org_code=f"PRED_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    monkeypatch.setenv("EDUDSS_PREDICTIONS_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    warehouse.save_prediction({"training_id": "tid_tenant", "value": 9.0, "metadata": {}})

    from dss.db.repositories import prediction_repository

    assert len(prediction_repository.list_predictions(org_id)) == 1
    assert len(prediction_repository.list_predictions(other_org_id)) == 0
