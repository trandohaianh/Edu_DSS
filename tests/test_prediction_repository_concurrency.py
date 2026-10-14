"""Regression test for Issue CONCUR-001 (found via Workstream D's capacity
benchmark, tests/load/test_concurrency_capacity.py): concurrent FIRST use
of the same training_id must not raise IntegrityError — every concurrent
caller must get back the SAME model_version_id, and no duplicate row may
be created."""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_D_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_D_DATABASE_URL")
pytestmark = pytest.mark.skipif(not OWNER_URL or not APP_URL, reason="Workstream D PostgreSQL URLs are required")


@pytest.fixture
def org_id(monkeypatch):
    owner = create_engine(OWNER_URL)
    code = "concur_" + uuid.uuid4().hex[:8]
    with owner.begin() as conn:
        org = conn.execute(
            text("INSERT INTO organizations (org_code,name,is_active,created_at,updated_at) VALUES (:c,:n,true,now(),now()) RETURNING id"),
            {"c": code, "n": code},
        ).scalar_one()
    owner.dispose()
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    from dss.db.session import reset_engine_for_tests
    reset_engine_for_tests()
    yield org
    reset_engine_for_tests()


def test_concurrent_first_use_of_same_training_id_never_raises_and_resolves_to_one_row(org_id):
    from dss.db.repositories import prediction_repository

    training_id = "concur_test_" + uuid.uuid4().hex[:8]
    results = []
    errors = []

    def _save(i):
        try:
            return prediction_repository.save_prediction(
                organization_id=org_id, training_id=training_id, prediction_value=i,
            )
        except Exception as exc:
            errors.append(exc)
            raise

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_save, i) for i in range(20)]
        for future in as_completed(futures):
            results.append(future.result())

    assert not errors, f"concurrent first-use raised: {errors}"
    assert len(results) == 20

    app_engine = create_engine(APP_URL)
    with app_engine.begin() as conn:
        conn.execute(text("SET LOCAL app.organization_id=:o"), {"o": str(org_id)})
        version_count = conn.execute(
            text("SELECT count(*) FROM model_versions WHERE organization_id=:o AND training_id=:t"),
            {"o": org_id, "t": training_id},
        ).scalar_one()
        prediction_count = conn.execute(
            text("SELECT count(*) FROM predictions WHERE organization_id=:o"), {"o": org_id},
        ).scalar_one()
    app_engine.dispose()

    assert version_count == 1, "concurrent first-use created more than one ModelVersion row for the same training_id"
    assert prediction_count == 20
