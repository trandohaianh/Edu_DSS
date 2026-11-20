"""Regression test — `model_service.compute_lecturer_dashboard_overview`, dùng
để dựng Lecturer Dashboard (KPI + rủi ro theo lớp) từ ĐÚNG bản Production hiện
tại trong Model Registry, không phải một pipeline tính riêng cho dashboard."""

from __future__ import annotations

import pandas as pd

from dss.services.model_service import compute_lecturer_dashboard_overview


class _LinearPipeline:
    """Trả về chính giá trị cột 'score' làm dự đoán — đủ để kiểm tra phân loại
    rủi ro theo phân vị mà không cần model sklearn thật."""

    def predict(self, X):
        return X["score"].to_numpy()


class _OffsetPipeline:
    """Dự đoán = score - 100 — dùng để tạo 1 bản Production KHÁC HẲN bản A,
    chứng minh Promote đổi ngay kết quả dashboard. Định nghĩa ở module-level
    (không phải trong hàm test) vì joblib.dump cần pickle được class."""

    def predict(self, X):
        return (X["score"] - 100).to_numpy()


def _save_reg_model(warehouse, dataset_id="ds1", target_col="score", metrics=None):
    tid, meta = warehouse.save_model_training(
        dataset_id=dataset_id,
        model_pipeline=_LinearPipeline(),
        model_name="LinearPassthrough",
        feature_cols=["score"],
        target_col=target_col,
        metrics=metrics if metrics is not None else {"R2 Score": 0.75},
        is_best=True,
    )
    warehouse.set_production_model(tid, promoted_by="admin")
    return tid, meta


def _class_df():
    # 10 sinh viên, điểm trải đều 1..10 -> phân vị 25%/50% chia rõ 3 nhóm.
    return pd.DataFrame({"student_id": [f"SV{i:03d}" for i in range(1, 11)], "score": list(range(1, 11))})


def test_overview_uses_production_model_and_classifies_risk(warehouse):
    _save_reg_model(warehouse)
    df = _class_df()

    result = compute_lecturer_dashboard_overview(df, warehouse, "ds1", "score")

    assert result["status"] == "ok"
    assert result["model_name"] == "LinearPassthrough"
    assert result["avg_predicted"] == sum(range(1, 11)) / 10
    # Tổng số sinh viên phân loại phải khớp đúng tổng số dòng.
    assert sum(result["risk_counts"].values()) == 10
    assert result["risk_counts"]["cao"] > 0
    # Sinh viên rủi ro cao phải có điểm dự đoán THẤP nhất trong danh sách.
    predicted_values = [s["predicted"] for s in result["high_risk_students"]]
    assert predicted_values == sorted(predicted_values)
    assert max(predicted_values) <= df["score"].quantile(0.25)


def test_overview_reports_metric_from_registry(warehouse):
    _save_reg_model(warehouse, metrics={"R2 Score": 0.912, "RMSE": 0.4})
    df = _class_df()

    result = compute_lecturer_dashboard_overview(df, warehouse, "ds1", "score")

    assert result["metric_name"] == "R2 Score"
    assert result["metric_value"] == 0.912


def test_overview_missing_production_handled_safely(warehouse):
    df = _class_df()
    result = compute_lecturer_dashboard_overview(df, warehouse, "khong-ton-tai", "score")
    assert result["status"] == "empty"


def test_overview_rejects_classification_production_model(warehouse):
    warehouse.save_model_training(
        dataset_id="ds1",
        model_pipeline=_LinearPipeline(),
        model_name="ClfModel",
        feature_cols=["score"],
        target_col="score",
        metrics={"Accuracy": 0.9, "F1 Score": 0.88},
        is_best=True,
    )
    df = _class_df()
    result = compute_lecturer_dashboard_overview(df, warehouse, "ds1", "score")
    assert result["status"] == "error"


def test_overview_promote_changes_dashboard_immediately(warehouse, as_role):
    from dss.services import model_registry

    id_a, _ = _save_reg_model(warehouse, metrics={"R2 Score": 0.5})
    df = _class_df()
    df_b = df.copy()
    df_b["score"] = df_b["score"] + 100  # bản B dự đoán khác hẳn bản A

    id_b, _ = warehouse.save_model_training(
        dataset_id="ds1",
        model_pipeline=_OffsetPipeline(),
        model_name="OffsetModel",
        feature_cols=["score"],
        target_col="score",
        metrics={"R2 Score": 0.9},
        is_best=False,
    )

    as_role("Admin")
    model_registry.promote(warehouse, id_b)

    result = compute_lecturer_dashboard_overview(df_b, warehouse, "ds1", "score")
    assert result["status"] == "ok"
    assert result["model_name"] == "OffsetModel"
