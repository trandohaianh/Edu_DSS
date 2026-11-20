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


# ------------------------------------------------------------------ audit 17/11/2026: ký artifact
def _train(wh):
    training_id, _ = wh.save_model_training(
        dataset_id="ds_sig",
        model_pipeline={"kind": "dummy"},
        model_name="RandomForest",
        feature_cols=["f1"],
        target_col="y",
        metrics={"R2 Score": 0.5},
        auto_promote=False,
    )
    return training_id


def _meta_path(wh, training_id):
    import os

    return os.path.join(wh.metadata_path, f"{training_id}_model.json")


def _rewrite(wh, training_id, **changes):
    path = _meta_path(wh, training_id)
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta.update(changes)
    for k in [k for k, v in changes.items() if v is None]:
        meta.pop(k, None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f)


def test_artifact_is_signed_and_signed_load_works(wh, monkeypatch):
    monkeypatch.setenv("EDUDSS_ARTIFACT_SIGNING_KEY", "k" * 40)
    tid = _train(wh)
    pipeline, meta, msg = wh.load_model_training(tid)
    assert pipeline == {"kind": "dummy"} and meta["model_hmac"] and msg == "Thành công"


def test_replacing_artifact_and_its_sha256_together_is_rejected(wh, monkeypatch):
    """Kẻ ghi được thư mục dữ liệu thay cả tệp lẫn mã băm: trước đây vẫn tải (joblib.load = chạy mã)."""
    import hashlib

    import joblib

    monkeypatch.setenv("EDUDSS_ARTIFACT_SIGNING_KEY", "k" * 40)
    tid = _train(wh)
    path = wh.models_path + f"/{tid}.joblib"
    joblib.dump({"kind": "evil"}, path)
    _rewrite(wh, tid, model_sha256=hashlib.sha256(open(path, "rb").read()).hexdigest())
    pipeline, _, msg = wh.load_model_training(tid)
    assert pipeline is None and "Chữ ký" in msg


def test_model_path_in_metadata_is_ignored(wh, monkeypatch, tmp_path_factory):
    import joblib

    monkeypatch.setenv("EDUDSS_ARTIFACT_SIGNING_KEY", "k" * 40)
    tid = _train(wh)
    outside = tmp_path_factory.mktemp("outside") / "evil.joblib"
    joblib.dump({"kind": "evil"}, outside)
    _rewrite(wh, tid, model_path=str(outside))
    pipeline, _, _ = wh.load_model_training(tid)
    assert pipeline == {"kind": "dummy"}  # tải tệp trong kho, không phải đường dẫn metadata
    assert wh.load_model_training("../../etc/passwd")[0] is None


def test_unsigned_legacy_artifact_is_refused_in_production_until_resigned(wh, monkeypatch):
    monkeypatch.setenv("EDUDSS_ARTIFACT_SIGNING_KEY", "k" * 40)
    tid = _train(wh)
    _rewrite(wh, tid, model_hmac=None)
    assert wh.load_model_training(tid)[0] == {"kind": "dummy"}  # ngoài production: vẫn tải (cảnh báo)
    from dss.core import runtime_mode

    monkeypatch.setattr(runtime_mode, "is_production", lambda: True)
    pipeline, _, msg = wh.load_model_training(tid)
    assert pipeline is None and "chưa được ký" in msg
    signed, skipped = wh.sign_legacy_models()
    assert signed == [tid] and skipped == []
    assert wh.load_model_training(tid)[0] == {"kind": "dummy"}
