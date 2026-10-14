"""Regression suite — Model Registry (single source of truth cho model Production)
và xử lý model thiếu/hỏng trong dss/core/warehouse.py.

Dùng warehouse THẬT (fixture `warehouse`, trỏ vào thư mục tmp_path) — không
mock — để test đi đúng luồng file .joblib + metadata JSON thật đang chạy trong
app. "Model" ở đây chỉ cần là 1 object picklable bất kỳ (joblib.dump chấp nhận
mọi object Python, không bắt buộc phải là sklearn thật) vì các test này KIỂM
TRA REGISTRY, không kiểm tra thuật toán ML.
"""
from __future__ import annotations

import json

import pytest


class _FakePipeline:
    """Đại diện tối giản cho 1 model đã train — chỉ cần picklable."""
    def __init__(self, tag):
        self.tag = tag

    def predict(self, X):
        return [self.tag] * len(X)


def _save(warehouse, dataset_id, target_col, model_name, tag, is_best=True):
    # training_id giờ duy nhất tuyệt đối nhờ uuid4 (xem warehouse.save_model_training)
    return warehouse.save_model_training(
        dataset_id=dataset_id,
        model_pipeline=_FakePipeline(tag),
        model_name=model_name,
        feature_cols=["f1", "f2"],
        target_col=target_col,
        metrics={"R2 Score": 0.8},
        is_best=is_best,
        auto_promote=False,
    )


# ---------------------------------------------------------------------------
# Model Governance (Mục 4: Loại bỏ auto-promotion, chỉ Admin duyệt Production)
# ---------------------------------------------------------------------------
def test_save_with_is_best_true_remains_candidate(warehouse):
    """Mục 4: Huấn luyện mô hình tốt nhất (is_best=True) chỉ tạo CANDIDATE,
    TUYỆT ĐỐI không tự động nhảy lên Production."""
    training_id, meta = _save(warehouse, "ds1", "final_score", "RF", "v1", is_best=True)
    assert meta["is_production"] is False
    assert meta["status"] == "candidate"
    assert meta["is_best_candidate"] is True
    pipeline, prod_meta = warehouse.get_production_model("ds1", "final_score")
    assert pipeline is None and prod_meta is None


def test_save_with_is_best_false_remains_candidate(warehouse):
    _training_id, meta = _save(warehouse, "ds1", "final_score", "RF", "v1", is_best=False)
    assert meta["is_production"] is False
    assert meta["status"] == "candidate"
    pipeline, prod_meta = warehouse.get_production_model("ds1", "final_score")
    assert pipeline is None and prod_meta is None


def test_acceptance_rule_production_a_train_better_b_stays_a_until_admin_promotes(warehouse):
    """TEST CHẤP NHẬN BẮT BUỘC (Mục 4):
    Production = A
    Giảng viên huấn luyện B (metric tốt hơn, is_best=True)
    Production VẪN PHẢI LÀ A.
    Admin duyệt promote B -> Production mới thành B.
    """
    id_a, _ = _save(warehouse, "ds1", "final_score", "RF", "model-A", is_best=True)
    # Admin duyệt model A lên Production
    ok, _ = warehouse.set_production_model(id_a, promoted_by="admin", promotion_reason="Initial baseline")
    assert ok is True

    # Kiểm tra Production hiện tại là A
    pipeline, prod_meta = warehouse.get_production_model("ds1", "final_score")
    assert prod_meta["training_id"] == id_a
    assert pipeline.tag == "model-A"

    # Giảng viên huấn luyện model B (tốt hơn, is_best=True)
    id_b, meta_b = _save(warehouse, "ds1", "final_score", "XGB", "model-B", is_best=True)
    assert meta_b["is_production"] is False
    assert meta_b["status"] == "candidate"

    # Production VẪN PHẢI BẢO TOÀN LÀ A
    pipeline_check, prod_check = warehouse.get_production_model("ds1", "final_score")
    assert prod_check["training_id"] == id_a
    assert pipeline_check.tag == "model-A"

    # Admin duyệt B
    ok_promote, _ = warehouse.set_production_model(id_b, promoted_by="admin", promotion_reason="Approved better metrics")
    assert ok_promote is True

    # Production CHÍNH THỨC TRỞ THÀNH B
    pipeline_final, prod_final = warehouse.get_production_model("ds1", "final_score")
    assert prod_final["training_id"] == id_b
    assert pipeline_final.tag == "model-B"

    # Model A chuyển sang archived
    versions = warehouse.list_model_versions("ds1", "final_score")
    by_id = {v["training_id"]: v for v in versions}
    assert by_id[id_a]["is_production"] is False
    assert by_id[id_a]["status"] == "archived"
    assert by_id[id_b]["is_production"] is True
    assert by_id[id_b]["status"] == "production"


def test_multi_model_batch_all_remain_candidates(warehouse):
    """Lưu nhiều model cùng đợt huấn luyện -> Tất cả đều là candidate,
    chỉ model tốt nhất được đánh dấu is_best_candidate=True nhưng không ai tự thành Production."""
    _id_a, meta_a = _save(warehouse, "ds1", "final_score", "Logistic", "a", is_best=False)
    id_b, meta_b = _save(warehouse, "ds1", "final_score", "RandomForest", "b", is_best=True)
    _id_c, meta_c = _save(warehouse, "ds1", "final_score", "XGBoost", "c", is_best=False)

    assert meta_a["is_production"] is False
    assert meta_b["is_production"] is False
    assert meta_b["is_best_candidate"] is True
    assert meta_c["is_production"] is False

    pipeline, prod_meta = warehouse.get_production_model("ds1", "final_score")
    assert pipeline is None and prod_meta is None


def test_different_target_cols_have_independent_production(warehouse):
    id_reg, _ = _save(warehouse, "ds1", "final_score", "RF", "reg-model", is_best=True)
    id_clf, _ = _save(warehouse, "ds1", "pass_fail", "RFClassifier", "clf-model", is_best=True)

    # Admin duyệt độc lập cho từng target
    warehouse.set_production_model(id_reg, promoted_by="admin")
    warehouse.set_production_model(id_clf, promoted_by="admin")

    reg_pipeline, _ = warehouse.get_production_model("ds1", "final_score")
    clf_pipeline, _ = warehouse.get_production_model("ds1", "pass_fail")
    assert reg_pipeline.tag == "reg-model"
    assert clf_pipeline.tag == "clf-model"



def test_version_number_increments_per_model_key(warehouse):
    _id1, meta1 = _save(warehouse, "ds1", "final_score", "RF", "v1")
    _id2, meta2 = _save(warehouse, "ds1", "final_score", "RF", "v2")
    _id3, meta3 = _save(warehouse, "ds1", "final_score", "RF", "v3")
    assert (meta1["version"], meta2["version"], meta3["version"]) == (1, 2, 3)

    # Target khác -> version riêng, bắt đầu lại từ 1.
    _id4, meta4 = _save(warehouse, "ds1", "other_target", "RF", "v1-other")
    assert meta4["version"] == 1


# ---------------------------------------------------------------------------
# Manual promote/rollback (dùng qua model_registry ở màn hình UI)
# ---------------------------------------------------------------------------
def test_manual_rollback_to_older_version(warehouse):
    id1, _ = _save(warehouse, "ds1", "final_score", "RF", "old-but-good")
    _id2, _ = _save(warehouse, "ds1", "final_score", "RF", "new-but-bad")

    ok, msg = warehouse.set_production_model(id1)
    assert ok is True

    pipeline, prod_meta = warehouse.get_production_model("ds1", "final_score")
    assert prod_meta["training_id"] == id1
    assert pipeline.tag == "old-but-good"


# ---------------------------------------------------------------------------
# Model thiếu / hỏng — KHÔNG được crash, phải trả lỗi rõ ràng
# ---------------------------------------------------------------------------
def test_get_production_model_when_none_set_returns_none_none(warehouse):
    assert warehouse.get_production_model("khong-ton-tai", "target") == (None, None)


def test_load_model_training_missing_id_returns_graceful_error(warehouse):
    pipeline, metadata, msg = warehouse.load_model_training("khong-ton-tai-id")
    assert pipeline is None and metadata is None
    assert "Không tìm thấy" in msg


def test_load_model_training_corrupted_metadata_returns_graceful_error(warehouse):
    training_id, _meta = _save(warehouse, "ds1", "final_score", "RF", "v1")
    # Ghi đè metadata bằng JSON hỏng.
    import os
    meta_path = os.path.join(warehouse.metadata_path, f"{training_id}_model.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("{ đây không phải JSON hợp lệ ][")

    pipeline, metadata, msg = warehouse.load_model_training(training_id)
    assert pipeline is None and metadata is None
    assert isinstance(msg, str) and msg  # có thông báo lỗi, không phải exception văng ra ngoài


def test_set_production_model_missing_id_returns_graceful_error(warehouse):
    ok, msg = warehouse.set_production_model("khong-ton-tai-id")
    assert ok is False
    assert "Không tìm thấy" in msg


def test_set_production_model_corrupted_metadata_returns_graceful_error(warehouse):
    training_id, _meta = _save(warehouse, "ds1", "final_score", "RF", "v1")
    import os
    meta_path = os.path.join(warehouse.metadata_path, f"{training_id}_model.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("{ không phải JSON ][")

    ok, msg = warehouse.set_production_model(training_id)
    assert ok is False
    assert "hỏng" in msg


def test_list_models_skips_corrupted_metadata_file_without_crashing(warehouse):
    id_good, _ = _save(warehouse, "ds1", "final_score", "RF", "good")
    import os
    bad_path = os.path.join(warehouse.metadata_path, "corrupted_entry_model.json")
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("{ hỏng hoàn toàn")

    models = warehouse.list_models()
    ids = {m["training_id"] for m in models}
    assert id_good in ids
    assert "corrupted_entry" not in ids  # file hỏng bị bỏ qua, không crash toàn bộ list


def test_missing_joblib_file_reports_error_not_crash(warehouse):
    """Metadata tồn tại nhưng file .joblib thật đã bị xoá khỏi đĩa (vd. dọn ổ
    cứng thủ công) — phải báo lỗi rõ ràng, không ném exception ra ngoài."""
    training_id, _ = _save(warehouse, "ds1", "final_score", "RF", "v1")
    import os
    joblib_path = os.path.join(warehouse.models_path, f"{training_id}.joblib")
    os.remove(joblib_path)

    pipeline, metadata, msg = warehouse.load_model_training(training_id)
    assert pipeline is None
    assert "không tồn tại" in msg


# ---------------------------------------------------------------------------
# BUG ĐÃ SỬA — regression test khoá lại (KHÔNG còn xfail):
# generate_id() cũ = md5(dataset_id + model_name + datetime.now().isoformat())[:12]
# có thể trùng training_id nếu 2 lần save_model_training() cho CÙNG (dataset_id,
# model_name) hoàn tất trong CÙNG 1 tick đồng hồ hệ thống — lần lưu sau ghi đè
# ÂM THẦM file .joblib/metadata của lần trước (mất bản ghi model). Đã sửa:
# training_id giờ = f"train_{timestamp}_{uuid.uuid4().hex}" — uniqueness dựa
# HOÀN TOÀN vào uuid4 (122 bit ngẫu nhiên), không phụ thuộc đồng hồ hệ thống
# nữa; timestamp chỉ còn mục đích dễ đọc khi liệt kê file trên đĩa.
# ---------------------------------------------------------------------------
def test_same_dataset_and_model_name_saved_in_same_instant_do_not_collide(warehouse, monkeypatch):
    """2 lần lưu liên tiếp CÙNG (dataset_id, model_name), ép đồng hồ đứng yên
    (monkeypatch `datetime` trong warehouse.py — tái hiện đúng điều kiện từng
    gây collision, không phụ thuộc may rủi thời điểm chạy thật) — vẫn phải
    tạo 2 training_id khác nhau, 2 đường dẫn artifact khác nhau, cả 2 artifact
    tồn tại trên đĩa, cả 2 xuất hiện trong registry, và bản B không ghi đè bản A."""
    import os
    import dss.core.warehouse as warehouse_mod

    class _FrozenDatetime(warehouse_mod.datetime):
        @classmethod
        def now(cls, tz=None):
            return warehouse_mod.datetime(2026, 1, 1, 0, 0, 0, 0)

    monkeypatch.setattr(warehouse_mod, "datetime", _FrozenDatetime)

    id_a, meta_a = warehouse.save_model_training(
        dataset_id="ds_race", model_pipeline=_FakePipeline("first"), model_name="RF",
        feature_cols=["f1"], target_col="t", metrics={}, is_best=True,
    )
    id_b, meta_b = warehouse.save_model_training(
        dataset_id="ds_race", model_pipeline=_FakePipeline("second"), model_name="RF",
        feature_cols=["f1"], target_col="t", metrics={}, is_best=False,
    )

    # 1) training_id khác nhau dù cùng dataset_id/model_name/timestamp (đã đóng băng).
    assert id_a != id_b, "2 lần lưu cùng dataset_id+model_name trong cùng tick đồng hồ bị trùng training_id"

    # 2) Đường dẫn artifact khác nhau.
    path_a = os.path.join(warehouse.models_path, f"{id_a}.joblib")
    path_b = os.path.join(warehouse.models_path, f"{id_b}.joblib")
    assert path_a != path_b

    # 3) Cả 2 artifact đều thực sự tồn tại trên đĩa.
    assert os.path.exists(path_a), "artifact A không tồn tại — có thể đã bị artifact B ghi đè"
    assert os.path.exists(path_b), "artifact B không được ghi ra đĩa"

    # 4) Registry (list_model_versions) chứa CẢ HAI bản ghi — không mất version.
    versions = warehouse.list_model_versions("ds_race", "t")
    version_ids = {v["training_id"] for v in versions}
    assert len(versions) == 2, "1 trong 2 bản ghi đã bị ghi đè mất do trùng training_id"
    assert version_ids == {id_a, id_b}

    # 5) Artifact B không ghi đè nội dung artifact A — load lại đúng object gốc
    #    của từng bản, không phải cùng 1 object do bị trùng file.
    pipeline_a, _, _ = warehouse.load_model_training(id_a)
    pipeline_b, _, _ = warehouse.load_model_training(id_b)
    assert pipeline_a.tag == "first"
    assert pipeline_b.tag == "second"


def test_training_id_uniqueness_at_scale_same_instant(warehouse, monkeypatch):
    """Đóng băng đồng hồ, sinh >=100 training_id liên tiếp cho CÙNG (dataset_id,
    model_name) — tất cả phải khác nhau tuyệt đối (không chỉ 'khó trùng')."""
    import dss.core.warehouse as warehouse_mod

    class _FrozenDatetime(warehouse_mod.datetime):
        @classmethod
        def now(cls, tz=None):
            return warehouse_mod.datetime(2026, 1, 1, 0, 0, 0, 0)

    monkeypatch.setattr(warehouse_mod, "datetime", _FrozenDatetime)

    ids = []
    for i in range(100):
        training_id, _ = warehouse.save_model_training(
            dataset_id="ds_scale", model_pipeline=_FakePipeline(f"m{i}"), model_name="RF",
            feature_cols=["f1"], target_col="t", metrics={}, is_best=False,
        )
        ids.append(training_id)

    assert len(ids) == len(set(ids)), "phát hiện training_id trùng lặp trong 100 lần lưu cùng tick đồng hồ"
    versions = warehouse.list_model_versions("ds_scale", "t")
    assert len(versions) == 100, "1 số bản ghi bị mất do trùng training_id (ghi đè lẫn nhau)"


def test_load_model_verifies_sha256_and_rejects_tampered_artifact(warehouse):
    """Mục 28: Kiểm thử phát hiện artifact bị chỉnh sửa/hỏng qua SHA-256."""
    import os
    training_id, meta = warehouse.save_model_training(
        dataset_id="ds_sec", model_pipeline=_FakePipeline("safe"), model_name="RF",
        feature_cols=["f1"], target_col="t", metrics={}, is_best=False,
    )
    assert meta.get("model_sha256") is not None

    # Load bình thường thành công
    pipeline, _, msg = warehouse.load_model_training(training_id)
    assert pipeline is not None
    assert msg == "Thành công"

    # Giả lập tấn công hoặc file hỏng: sửa nội dung file model
    model_path = os.path.join(warehouse.models_path, f"{training_id}.joblib")
    with open(model_path, "ab") as f:
        f.write(b"MALICIOUS_TAMPERED_BYTES")

    # Load lại phải bị từ chối với lỗi bảo mật
    pipeline_bad, meta_bad, err_msg = warehouse.load_model_training(training_id)
    assert pipeline_bad is None
    assert "Mã băm SHA-256" in err_msg or "Lỗi bảo mật" in err_msg

