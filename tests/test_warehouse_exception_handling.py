"""ARCH-WH-001 (audit 2026-09): warehouse.py's list_datasets()/list_models()/
get_evaluation_data_for_rag() used `except BaseException: pass` to skip
corrupted metadata files -- this also silently swallows KeyboardInterrupt/
SystemExit/GeneratorExit, not just real file-corruption errors. Narrowed to
`except Exception` (still skips corrupted files, no longer eats control-flow
exceptions) plus a warning log for observability."""
from __future__ import annotations

import inspect
import json

import pytest

from dss.core.warehouse import DataWarehouse


@pytest.fixture()
def wh(tmp_path):
    return DataWarehouse(base_path=str(tmp_path))


def test_list_datasets_skips_corrupted_json_without_crashing(wh):
    good_path = wh.metadata_path + "/good_data.json"
    bad_path = wh.metadata_path + "/bad_data.json"
    with open(good_path, "w", encoding="utf-8") as f:
        json.dump({"created_at": "2026-01-01", "dataset_id": "good"}, f)
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("{this is not valid json")

    datasets = wh.list_datasets()
    assert len(datasets) == 1
    assert datasets[0]["dataset_id"] == "good"


def test_list_models_skips_corrupted_json_without_crashing(wh):
    good_path = wh.metadata_path + "/good_model.json"
    bad_path = wh.metadata_path + "/bad_model.json"
    with open(good_path, "w", encoding="utf-8") as f:
        json.dump({"trained_at": "2026-01-01", "model_name": "good"}, f)
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("{this is not valid json")

    models = wh.list_models()
    assert len(models) == 1
    assert models[0]["model_name"] == "good"


def test_warehouse_source_no_longer_uses_base_exception():
    import dss.core.warehouse as warehouse_module

    source = inspect.getsource(warehouse_module)
    assert "except BaseException:" not in source
