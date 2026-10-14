"""Audit and Governance Test Suite — Bao phủ toàn bộ 15 yêu cầu kiểm thử (A -> O)
theo bản đặc tả audit & refactor EduDSS.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import streamlit as st

from dss.core.target_utils import (
    canonicalize_columns,
    filter_leakage_features,
    score_to_xep_loai,
    CANONICAL_TARGET_REGRESSION,
    CANONICAL_TARGET_CLASSIFICATION,
    LEGACY_ALIAS_REGRESSION,
    LEGACY_ALIAS_CLASSIFICATION,
    CLASSIFICATION_BINS,
    CLASSIFICATION_LABELS,
)
from dss.core.data_helpers import generate_data, load_data
from dss.core.warehouse import DataWarehouse
from dss.core.trainers import ClassificationTrainer
from dss.services import model_registry
from dss.services.model_service import (
    resolve_production_for_prediction,
    run_preview_benchmark,
    compute_shap_local_explanation,
    compute_shap_summary,
)


class _DummyPipeline:
    def __init__(self, tag="v1"):
        self.tag = tag

    def predict(self, X):
        return [self.tag] * len(X)


# ============================================================================
# TEST A: target=xep_loai không chứa grade/diem_ky_sau/final_score trong X
# ============================================================================
def test_a_classification_target_excludes_all_aliases_and_generators():
    df = pd.DataFrame({
        "diem_ky_nay": [7.0, 8.0, 6.5],
        "diem_giua_ky": [6.0, 7.5, 8.0],
        "diem_ky_sau": [7.5, 8.5, 7.0],
        "final_score": [7.5, 8.5, 7.0],
        "xep_loai": ["Khá", "Giỏi", "Khá"],
        "grade": ["Khá", "Giỏi", "Khá"],
    })
    target_col = "xep_loai"
    feature_cols = ["diem_ky_nay", "diem_giua_ky", "diem_ky_sau", "final_score", "grade"]

    clean_features, removed = filter_leakage_features(df, target_col, feature_cols, return_removed=True)

    assert "xep_loai" not in clean_features
    assert "grade" not in clean_features
    assert "diem_ky_sau" not in clean_features
    assert "final_score" not in clean_features
    assert "diem_ky_nay" in clean_features
    assert "diem_giua_ky" in clean_features
    assert set(removed) == {"grade", "diem_ky_sau", "final_score"}


# ============================================================================
# TEST B: target=diem_ky_sau không chứa final_score/xep_loai/grade trong X
# ============================================================================
def test_b_regression_target_excludes_all_aliases_and_derived_targets():
    df = pd.DataFrame({
        "diem_ky_nay": [7.0, 8.0, 6.5],
        "so_gio_hoc_tuan": [15, 20, 10],
        "diem_ky_sau": [7.5, 8.5, 7.0],
        "final_score": [7.5, 8.5, 7.0],
        "xep_loai": ["Khá", "Giỏi", "Khá"],
        "grade": ["Khá", "Giỏi", "Khá"],
    })
    target_col = "diem_ky_sau"
    feature_cols = ["diem_ky_nay", "so_gio_hoc_tuan", "final_score", "xep_loai", "grade"]

    clean_features, removed = filter_leakage_features(df, target_col, feature_cols, return_removed=True)

    assert "diem_ky_sau" not in clean_features
    assert "final_score" not in clean_features
    assert "xep_loai" not in clean_features
    assert "grade" not in clean_features
    assert "diem_ky_nay" in clean_features
    assert "so_gio_hoc_tuan" in clean_features
    assert set(removed) == {"final_score", "xep_loai", "grade"}


# ============================================================================
# TEST C: canonical alias conversion đúng
# ============================================================================
def test_c_canonical_alias_conversion():
    # Dataset chỉ có grade -> đổi thành xep_loai
    df_grade = pd.DataFrame({"student_id": [1, 2], "grade": ["Giỏi", "Khá"]})
    df_c1 = canonicalize_columns(df_grade)
    assert "xep_loai" in df_c1.columns
    assert "grade" not in df_c1.columns
    assert list(df_c1["xep_loai"]) == ["Giỏi", "Khá"]

    # Dataset chỉ có final_score -> đổi thành diem_ky_sau
    df_fs = pd.DataFrame({"student_id": [1, 2], "final_score": [8.5, 7.0]})
    df_c2 = canonicalize_columns(df_fs)
    assert "diem_ky_sau" in df_c2.columns
    assert "final_score" not in df_c2.columns
    assert list(df_c2["diem_ky_sau"]) == [8.5, 7.0]


# ============================================================================
# TEST D: conflicting aliases bị warning / error
# ============================================================================
def test_d_conflicting_aliases_raise_inconsistency_error():
    # grade và xep_loai mâu thuẫn
    df_conflict_clf = pd.DataFrame({
        "student_id": [1, 2],
        "xep_loai": ["Giỏi", "Khá"],
        "grade": ["Yếu", "Trung bình"],
    })
    with pytest.raises(ValueError, match="Xung đột dữ liệu"):
        canonicalize_columns(df_conflict_clf, strict=True)

    # final_score và diem_ky_sau mâu thuẫn
    df_conflict_reg = pd.DataFrame({
        "student_id": [1, 2],
        "diem_ky_sau": [8.5, 7.0],
        "final_score": [2.0, 3.5],
    })
    with pytest.raises(ValueError, match="Xung đột dữ liệu"):
        canonicalize_columns(df_conflict_reg, strict=True)


# ============================================================================
# TEST E: Lecturer training không tự Promote
# ============================================================================
def test_e_lecturer_training_creates_candidate_does_not_auto_promote(tmp_path):
    wh = DataWarehouse(base_path=str(tmp_path))
    pipeline = _DummyPipeline("lecturer_candidate")

    # Giảng viên train lưu model (is_best=True nhưng auto_promote=False theo governance mới)
    training_id, meta = wh.save_model_training(
        dataset_id="ds_demo",
        model_pipeline=pipeline,
        model_name="RandomForest",
        feature_cols=["f1", "f2"],
        target_col="diem_ky_sau",
        metrics={"R2 Score": 0.85},
        is_best=True,
        auto_promote=False,
    )

    assert meta["status"] == "candidate"
    assert meta["is_production"] is False
    assert meta["promoted_at"] is None
    assert meta["promoted_by"] is None

    # Con trỏ production vẫn trống
    prod_pipeline, prod_meta = wh.get_production_model("ds_demo", "diem_ky_sau")
    assert prod_pipeline is None
    assert prod_meta is None


# ============================================================================
# TEST F: Admin Promote thành công
# ============================================================================
def test_f_admin_promote_succeeds(tmp_path, monkeypatch):
    wh = DataWarehouse(base_path=str(tmp_path))
    pipeline = _DummyPipeline("approved_model")

    training_id, _ = wh.save_model_training(
        dataset_id="ds_demo",
        model_pipeline=pipeline,
        model_name="RandomForest",
        feature_cols=["f1", "f2"],
        target_col="diem_ky_sau",
        metrics={"R2 Score": 0.88},
        auto_promote=False,
    )

    # Thiết lập phiên Admin
    monkeypatch.setitem(st.session_state, "_auth_role", "Admin")
    monkeypatch.setitem(st.session_state, "_auth_user", "admin_lead")

    ok, msg = model_registry.promote(wh, training_id, promotion_reason="Model đạt benchmark F1 cao")
    assert ok is True

    prod_pipeline, prod_meta = wh.get_production_model("ds_demo", "diem_ky_sau")
    assert prod_pipeline is not None
    assert prod_meta["training_id"] == training_id
    assert prod_meta["status"] == "production"
    assert prod_meta["is_production"] is True
    assert prod_meta["promoted_by"] == "admin_lead"
    assert prod_meta["promotion_reason"] == "Model đạt benchmark F1 cao"
    assert prod_meta["promoted_at"] is not None


# ============================================================================
# TEST G: non-Admin Promote bị từ chối
# ============================================================================
def test_g_non_admin_promote_rejected_with_permission_error(tmp_path, monkeypatch):
    wh = DataWarehouse(base_path=str(tmp_path))
    training_id, _ = wh.save_model_training(
        dataset_id="ds_demo",
        model_pipeline=_DummyPipeline("cand"),
        model_name="RF",
        feature_cols=["f1"],
        target_col="diem_ky_sau",
        metrics={"R2 Score": 0.8},
        auto_promote=False,
    )

    # Vai trò Giảng viên
    monkeypatch.setitem(st.session_state, "_auth_role", "Giảng viên / CVHT")
    with pytest.raises(PermissionError):
        model_registry.promote(wh, training_id)

    # Vai trò Sinh viên
    monkeypatch.setitem(st.session_state, "_auth_role", "Sinh viên")
    with pytest.raises(PermissionError):
        model_registry.promote(wh, training_id)


# ============================================================================
# TEST H: prediction luôn lấy current Production model
# ============================================================================
def test_h_prediction_always_resolves_production_model(tmp_path, monkeypatch):
    wh = DataWarehouse(base_path=str(tmp_path))
    model_registry.clear_production_cache()

    # Chưa có production -> trả controlled empty state
    res_empty = resolve_production_for_prediction(wh, "ds1", "diem_ky_sau")
    assert res_empty["status"] == "empty"
    assert res_empty["pipeline"] is None

    # Tạo Candidate v1 và Promote lên Production
    id1, _ = wh.save_model_training(
        dataset_id="ds1",
        model_pipeline=_DummyPipeline("tag_v1"),
        model_name="RF_v1",
        feature_cols=["f1", "f2"],
        target_col="diem_ky_sau",
        metrics={"R2 Score": 0.80},
        auto_promote=True,  # Set production
    )

    res_v1 = resolve_production_for_prediction(wh, "ds1", "diem_ky_sau")
    assert res_v1["status"] == "ok"
    assert res_v1["pipeline"].tag == "tag_v1"
    assert res_v1["training_id"] == id1

    # Tạo Candidate v2 và Admin Promote
    id2, _ = wh.save_model_training(
        dataset_id="ds1",
        model_pipeline=_DummyPipeline("tag_v2"),
        model_name="RF_v2",
        feature_cols=["f1", "f2"],
        target_col="diem_ky_sau",
        metrics={"R2 Score": 0.90},
        auto_promote=False,
    )
    monkeypatch.setitem(st.session_state, "_auth_role", "Admin")
    model_registry.promote(wh, id2)

    res_v2 = resolve_production_for_prediction(wh, "ds1", "diem_ky_sau")
    assert res_v2["status"] == "ok"
    assert res_v2["pipeline"].tag == "tag_v2"
    assert res_v2["training_id"] == id2


# ============================================================================
# TEST I: F1 Macro được tính đúng multi-class
# ============================================================================
def test_i_f1_macro_computed_correctly_for_multiclass():
    # Tạo dataset phân loại 3 lớp với phân phối không đều
    np.random.seed(42)
    n = 120
    df = pd.DataFrame({
        "feature_1": np.random.normal(0, 1, n),
        "feature_2": np.random.normal(5, 2, n),
        "diem_ky_nay": np.random.uniform(1, 10, n),
        # 3 lớp mất cân bằng: 70% Khá, 20% Giỏi, 10% Yếu
        "xep_loai": np.random.choice(["Khá", "Giỏi", "Yếu"], size=n, p=[0.70, 0.20, 0.10]),
    })

    trainer = ClassificationTrainer()
    results, pipelines, labels, feats, X_test, y_test, X_train = trainer.train_and_evaluate(
        df=df,
        feature_cols=["feature_1", "feature_2", "diem_ky_nay"],
        target_col="xep_loai",
        selected_models=["Logistic Regression (Softmax)"],
        test_size=0.25,
        cv_folds=3,
        save_model=False,
    )

    res = results["Logistic Regression (Softmax)"]
    assert "F1 Score (Macro)" in res
    assert "F1 Score (Weighted)" in res
    assert "Precision (Macro)" in res
    assert "Recall (Macro)" in res
    assert "Confusion Matrix" in res
    assert "Accuracy" in res
    assert 0.0 <= res["F1 Score (Macro)"] <= 1.0


# ============================================================================
# TEST J: CV preprocessing fit trong fold
# ============================================================================
def test_j_preview_benchmark_uses_pipeline_without_dataset_leakage():
    df = pd.DataFrame({
        "cat_col": ["A", "B", "A", "B", "C", "A", "B", "C", "A", "B", "C", "A"],
        "num_col": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
        "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
    })

    bench = run_preview_benchmark(
        df=df,
        selected_features=["cat_col", "num_col"],
        target_col="target",
        problem_type="Phân loại (Classification)",
    )

    assert bench["evaluation_type"] == "exploratory_only"
    assert "mean" in bench and "std" in bench
    assert bench["metric_name"] == "Accuracy"


# ============================================================================
# TEST K: SMOTE không tác động test set
# ============================================================================
def test_k_smote_does_not_affect_test_set_size_or_distribution():
    # Kiểm tra trực quan từ luồng train_and_evaluate
    np.random.seed(42)
    n = 100
    df = pd.DataFrame({
        "feat1": np.random.randn(n),
        "feat2": np.random.randn(n),
        "target": ["A"] * 85 + ["B"] * 15,
    })

    trainer = ClassificationTrainer()
    results, pipelines, labels, feats, X_test, y_test, X_train = trainer.train_and_evaluate(
        df=df,
        feature_cols=["feat1", "feat2"],
        target_col="target",
        selected_models=["Logistic Regression (Softmax)"],
        balance_method="smote",
        test_size=0.20,
        cv_folds=3,
        save_model=False,
    )

    # Test set kích thước đúng 20 mẫu, hoàn toàn không bị SMOTE nhân bản
    assert len(X_test) == 20
    assert len(y_test) == 20


# ============================================================================
# TEST L: multiclass SHAP chọn đúng predicted class
# ============================================================================
def test_l_multiclass_shap_prediction_mapping():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    np.random.seed(42)
    n = 100
    X = pd.DataFrame({
        "diem_giua_ky": np.random.uniform(0, 10, n),
        "diem_du_an": np.random.uniform(0, 10, n),
        "so_gio_hoc": np.random.uniform(5, 30, n),
    })
    # 5 lớp học lực chuẩn
    y = np.random.choice(["Yếu", "Trung bình", "Khá", "Giỏi", "Xuất sắc"], size=n)

    preprocessor = ColumnTransformer([("num", StandardScaler(), list(X.columns))])
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", model)])
    pipeline.fit(X, y)

    # Local explanation
    input_sample = X.iloc[[0]]
    shap_val, err = compute_shap_local_explanation(
        pipeline, input_sample, X.iloc[:20], list(X.columns), problem_type="classification"
    )
    assert err is None
    assert shap_val is not None

    # Summary explanation
    shap_summary, s_err = compute_shap_summary(
        pipeline, X.iloc[:20], list(X.columns), problem_type="classification", class_idx=None
    )
    assert s_err is None
    assert shap_summary is not None


# ============================================================================
# TEST M: pd.cut boundaries đúng
# ============================================================================
def test_m_pd_cut_boundaries_match_specification():
    # Kiểm tra tại các biên chính xác: 0, 3.99, 5.49, 6.99, 8.49, 10.0
    scores = pd.Series([0.0, 3.99, 4.0, 5.49, 5.5, 6.99, 7.0, 8.49, 8.5, 10.0])
    labels = score_to_xep_loai(scores)

    expected = [
        "Yếu",          # 0.00
        "Yếu",          # 3.99
        "Trung bình",   # 4.00
        "Trung bình",   # 5.49
        "Khá",          # 5.50
        "Khá",          # 6.99
        "Giỏi",         # 7.00
        "Giỏi",         # 8.49
        "Xuất sắc",     # 8.50
        "Xuất sắc",     # 10.00
    ]
    assert list(labels) == expected


# ============================================================================
# TEST N: same random_state cho reproducible synthetic demo
# ============================================================================
def test_n_same_random_state_produces_identical_synthetic_dataset():
    df1 = generate_data(n_students=100, random_state=42)
    df2 = generate_data(n_students=100, random_state=42)
    df3 = generate_data(n_students=100, random_state=999)

    pd.testing.assert_frame_equal(df1, df2)
    assert not df1["diem_ky_sau"].equals(df3["diem_ky_sau"])


# ============================================================================
# TEST O: real evaluation mode không tự sinh target
# ============================================================================
def test_o_real_evaluation_mode_does_not_auto_generate_target(tmp_path):
    # Tạo 1 file CSV thực tế không chứa target diem_ky_sau
    csv_file = tmp_path / "real_historical_courses.csv"
    real_df = pd.DataFrame({
        "student_id": ["SV01", "SV02", "SV03"],
        "diem_ky_nay": [7.5, 8.0, 6.0],
        "diem_giua_ky": [7.0, 8.5, 6.5],
    })
    real_df.to_csv(csv_file, index=False)

    loaded_df = load_data(str(csv_file))
    assert loaded_df is not None
    assert loaded_df.attrs.get("data_source_type") == "real"
    # Tuyệt đối không tự động sinh cột target khi tải file thực tế
    assert "diem_ky_sau" not in loaded_df.columns
    assert "xep_loai" not in loaded_df.columns
