"""Regression suite — Prediction phải LUÔN lấy model từ Model Registry (bản
Production hiện tại), không được phụ thuộc vào "model nào tình cờ đang nằm
trong session_state" (Phase A của yêu cầu tái cấu trúc model lifecycle).

Kiểm tra qua `dss.services.model_registry.resolve_production` (tầng đọc con
trỏ Production + cache artifact) và `dss.services.model_service.
resolve_production_for_prediction` (tầng UI Dự đoán thật sự gọi) — dùng
warehouse THẬT (fixture `warehouse`, tmp_path), không mock.
"""

from __future__ import annotations

import streamlit as st

from dss.services import model_registry
from dss.services.model_service import resolve_production_for_prediction


class _FakePipeline:
    """Đại diện tối giản cho 1 model đã train — chỉ cần picklable + predict()."""

    def __init__(self, tag):
        self.tag = tag

    def predict(self, X):
        return [self.tag] * len(X)


def _save(warehouse, dataset_id, target_col, model_name, tag, is_best=True, metrics=None):
    training_id, meta = warehouse.save_model_training(
        dataset_id=dataset_id,
        model_pipeline=_FakePipeline(tag),
        model_name=model_name,
        feature_cols=["f1", "f2"],
        target_col=target_col,
        metrics=metrics if metrics is not None else {"R2 Score": 0.8},
        is_best=is_best,
        auto_promote=False,
    )
    if is_best:
        warehouse.set_production_model(training_id, promoted_by="admin", promotion_reason="Test setup promotion")
    return training_id, meta


def setup_function(_):
    # Cache là tối ưu tốc độ (theo warehouse_scope + training_id), không phải
    # nguồn sự thật — nhưng xoá sạch trước mỗi test để mỗi test độc lập tuyệt
    # đối, không phụ thuộc thứ tự chạy của các test khác.
    model_registry.clear_production_cache()


# ---------------------------------------------------------------------------
# 1) Prediction phải load ĐÚNG bản Production hiện tại từ Registry.
# ---------------------------------------------------------------------------
def test_prediction_resolves_current_production_model(warehouse):
    training_id, _meta = _save(warehouse, "ds1", "final_score", "RF", "prod-v1", is_best=True)

    resolved = resolve_production_for_prediction(warehouse, "ds1", "final_score")

    assert resolved["status"] == "ok"
    assert resolved["training_id"] == training_id
    assert resolved["pipeline"].tag == "prod-v1"
    assert resolved["feature_cols"] == ["f1", "f2"]
    assert resolved["hub_type"] == "reg"  # metrics chỉ có R2 Score -> hồi quy


# ---------------------------------------------------------------------------
# 2) Admin Promote model khác -> prediction TIẾP THEO phải dùng model MỚI.
# ---------------------------------------------------------------------------
def test_promote_changes_prediction_model_immediately(warehouse, as_role):
    id_a, _ = _save(warehouse, "ds1", "final_score", "RF", "model-A", is_best=True)
    id_b, _ = _save(warehouse, "ds1", "final_score", "XGB", "model-B", is_best=False)

    # Trước khi promote B: prediction vẫn phải là A.
    before = resolve_production_for_prediction(warehouse, "ds1", "final_score")
    assert before["training_id"] == id_a
    assert before["pipeline"].tag == "model-A"

    as_role("Admin")
    ok, _msg = model_registry.promote(warehouse, id_b)
    assert ok is True

    after = resolve_production_for_prediction(warehouse, "ds1", "final_score")
    assert after["training_id"] == id_b
    assert after["pipeline"].tag == "model-B", (
        "Promote B xong nhưng prediction vẫn dùng A — cache hoặc session đang "
        "'dính' bản cũ thay vì đọc lại con trỏ Production mới nhất."
    )


# ---------------------------------------------------------------------------
# 3) Admin Rollback về bản cũ -> prediction TIẾP THEO phải dùng bản cũ đó.
# ---------------------------------------------------------------------------
def test_rollback_changes_prediction_model_immediately(warehouse, as_role):
    id_a, _ = _save(warehouse, "ds1", "final_score", "RF", "model-A", is_best=True)
    id_b, _ = _save(warehouse, "ds1", "final_score", "XGB", "model-B", is_best=True)

    # Sau lần save thứ 2 (is_best=True): Production đang là B.
    mid = resolve_production_for_prediction(warehouse, "ds1", "final_score")
    assert mid["training_id"] == id_b

    as_role("Admin")
    ok, _msg = model_registry.rollback(warehouse, id_a)
    assert ok is True

    after = resolve_production_for_prediction(warehouse, "ds1", "final_score")
    assert after["training_id"] == id_a
    assert after["pipeline"].tag == "model-A", "Rollback về A xong nhưng prediction vẫn dùng B."


# ---------------------------------------------------------------------------
# 4) Model "tình cờ" đang có trong session_state (vd. vừa train/so sánh 1 batch
#    khác trong tab Huấn luyện) KHÔNG được phép override bản Production khi dự
#    đoán — resolve_production_for_prediction không hề đọc session_state.
# ---------------------------------------------------------------------------
def test_stale_session_model_cannot_override_production(warehouse):
    prod_id, _ = _save(warehouse, "ds1", "final_score", "RF", "real-production", is_best=True)

    # Giả lập session đang "dính" 1 batch train khác, hoàn toàn không liên quan
    # tới bản Production thật — đây chính là bug gốc (dùng nhầm session làm
    # nguồn sự thật) mà Phase A phải xoá bỏ.
    st.session_state["hub_pipelines"] = {"stale-model": _FakePipeline("stale-should-not-be-used")}
    st.session_state["hub_locked_model"] = "stale-model"
    st.session_state["hub_type"] = "clf"
    st.session_state["hub_feats"] = ["unrelated_feature"]
    st.session_state["hub_target_col"] = "final_score"

    resolved = resolve_production_for_prediction(warehouse, "ds1", "final_score")

    assert resolved["status"] == "ok"
    assert resolved["training_id"] == prod_id
    assert resolved["pipeline"].tag == "real-production"
    assert resolved["feature_cols"] == ["f1", "f2"], (
        "feature_cols phải đến từ metadata Registry của bản Production, "
        "không phải từ session_state['hub_feats'] còn sót lại."
    )


# ---------------------------------------------------------------------------
# 5) Sinh viên (hoặc bất kỳ role nào) không có cách nào chọn model tuỳ ý cho dự
#    đoán — resolve_production_for_prediction chỉ nhận (dataset_id, target_col),
#    không nhận tham số "model muốn dùng" nào từ phía gọi.
# ---------------------------------------------------------------------------
def test_student_session_cannot_choose_arbitrary_model(warehouse, as_role):
    prod_id, _ = _save(warehouse, "ds1", "final_score", "RF", "production-model", is_best=True)
    _other_id, _ = _save(warehouse, "ds1", "final_score", "XGB", "candidate-not-promoted", is_best=False)

    as_role("Sinh viên", student_id="SV001")
    # Sinh viên "cố" đặt 1 model khác vào session (vd. do code cũ/khác ghi
    # nhầm) — hàm resolve KHÔNG có tham số nào nhận lựa chọn này, nên không có
    # cách nào để nó lọt vào kết quả.
    st.session_state["hub_locked_model"] = "candidate-not-promoted"
    st.session_state["pers_selected_model"] = "candidate-not-promoted"

    resolved = resolve_production_for_prediction(warehouse, "ds1", "final_score")

    assert resolved["training_id"] == prod_id
    assert resolved["pipeline"].tag == "production-model"


# ---------------------------------------------------------------------------
# 6) Chưa có Production model -> trạng thái rỗng rõ ràng, KHÔNG crash, KHÔNG
#    âm thầm rơi về model ngẫu nhiên/model khác đang có trong kho.
# ---------------------------------------------------------------------------
def test_missing_production_handled_safely(warehouse):
    # Có model trong kho nhưng KHÔNG phải Production (is_best=False) — vẫn
    # phải báo "empty", không tự ý lấy bản is_best=False này thay thế.
    _save(warehouse, "ds1", "final_score", "RF", "not-production", is_best=False)

    resolved = resolve_production_for_prediction(warehouse, "ds1", "final_score")

    assert resolved["status"] == "empty"
    assert resolved["pipeline"] is None
    assert isinstance(resolved["message"], str) and resolved["message"]


def test_missing_production_for_unknown_dataset_target_handled_safely(warehouse):
    resolved = resolve_production_for_prediction(warehouse, "khong-ton-tai", "target")
    assert resolved["status"] == "empty"
    assert resolved["pipeline"] is None


def test_missing_dataset_or_target_col_handled_safely(warehouse):
    resolved = resolve_production_for_prediction(warehouse, None, None)
    assert resolved["status"] == "empty"
    assert resolved["pipeline"] is None


# ---------------------------------------------------------------------------
# 7) Không tự động retrain khi resolve — resolve_production chỉ ĐỌC registry,
#    không bao giờ gọi bất kỳ hàm train nào.
# ---------------------------------------------------------------------------
def test_resolve_never_triggers_training(warehouse, monkeypatch):
    from dss.services import model_service

    called = {"train": False}

    def _fail_if_called(*args, **kwargs):
        called["train"] = True
        raise AssertionError("resolve_production_for_prediction không được gọi run_training")

    monkeypatch.setattr(model_service, "run_training", _fail_if_called)

    _save(warehouse, "ds1", "final_score", "RF", "v1", is_best=True)
    resolved = resolve_production_for_prediction(warehouse, "ds1", "final_score")

    assert resolved["status"] == "ok"
    assert called["train"] is False


# ---------------------------------------------------------------------------
# 8) Model Production là clustering (không dùng để dự đoán target) -> báo lỗi
#    rõ ràng thay vì cố predict() và crash.
# ---------------------------------------------------------------------------
def test_clustering_production_model_reports_error_not_crash(warehouse):
    _save(
        warehouse,
        "ds1",
        "cluster_label",
        "KMeans",
        "kmeans-v1",
        is_best=True,
        metrics={"type": "clustering", "silhouette": 0.5},
    )

    resolved = resolve_production_for_prediction(warehouse, "ds1", "cluster_label")

    assert resolved["status"] == "error"
    assert resolved["pipeline"] is None


# ---------------------------------------------------------------------------
# resolve_model_for_prediction: Giảng viên rơi về mô hình vừa train khi CHƯA
# có Production; Sinh viên thì không bao giờ.
# ---------------------------------------------------------------------------
def _seed_session_training(target_col="final_score"):
    st.session_state.hub_pipelines = {"Linear": _FakePipeline("lin"), "RF": _FakePipeline("rf")}
    st.session_state.hub_results = {
        "Linear": {"R2 Score": 0.7, "RMSE": 1.2, "MAE": 0.9},
        "RF": {"R2 Score": 0.8, "RMSE": 0.8, "MAE": 0.6},
    }
    st.session_state.hub_type = "reg"
    st.session_state.hub_target_col = target_col
    st.session_state.hub_feats = ["f1", "f2"]


def test_lecturer_falls_back_to_best_session_model_without_production(warehouse):
    from dss.services.model_service import resolve_model_for_prediction

    _seed_session_training()
    resolved = resolve_model_for_prediction(warehouse, "ds1", "final_score", role="Giảng viên")
    assert resolved["status"] == "ok"
    assert resolved["source"] == "session"
    assert resolved["model_name"] == "RF"  # RMSE thấp nhất
    assert resolved["feature_cols"] == ["f1", "f2"]


def test_student_never_uses_session_model(warehouse):
    from dss.services.model_service import resolve_model_for_prediction

    _seed_session_training()
    resolved = resolve_model_for_prediction(warehouse, "ds1", "final_score", role="Sinh viên")
    assert resolved["status"] == "empty"
    assert resolved["pipeline"] is None


def test_production_still_wins_over_session_model_for_lecturer(warehouse):
    from dss.services.model_service import resolve_model_for_prediction

    _save(warehouse, "ds1", "final_score", "Prod", "prod")
    _seed_session_training()
    resolved = resolve_model_for_prediction(warehouse, "ds1", "final_score", role="Giảng viên")
    assert resolved["source"] == "production"
    assert resolved["pipeline"].tag == "prod"


def test_session_model_for_other_target_is_not_used(warehouse):
    from dss.services.model_service import resolve_model_for_prediction

    _seed_session_training(target_col="other_target")
    resolved = resolve_model_for_prediction(warehouse, "ds1", "final_score", role="Giảng viên")
    assert resolved["status"] == "empty"
