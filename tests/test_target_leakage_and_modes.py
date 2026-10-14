"""Test suite kiểm chứng kiến trúc dữ liệu và ML mới của EduDSS:
1. Phân định rõ hai chế độ dữ liệu: Synthetic/Demo (data_source_type='synthetic') vs Real (data_source_type='real').
2. Target Leakage Guard: Loại bỏ hoàn toàn target alias/derived target (grade, final_score, xep_loai, diem_ky_sau).
3. Bảo toàn các biến dự báo hợp lệ (legitimate predictors: diem_ky_nay).
4. Chuẩn hóa tên cột canonical (canonicalize_columns cases 1-4).
5. Phân ngưỡng phân loại chuẩn hóa (score_to_xep_loai).
6. Chia dữ liệu theo thời gian (temporal split) và xây dựng bộ dữ liệu dọc (longitudinal dataset).
7. Lưu vết metadata kiến trúc trong Kho dữ liệu (Warehouse).
8. Khả năng phòng vệ leakage trong ClassificationTrainer và RegressionTrainer.
"""
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from dss.core.target_utils import (
    CANONICAL_TARGET_REGRESSION,
    CANONICAL_TARGET_CLASSIFICATION,
    LEGACY_ALIAS_REGRESSION,
    LEGACY_ALIAS_CLASSIFICATION,
    score_to_xep_loai,
    canonicalize_columns,
    filter_leakage_features,
    detect_temporal_column,
    prepare_longitudinal_dataset,
    temporal_train_test_split,
    get_leaky_target_columns,
    LEGITIMATE_PREDICTORS,
)
from dss.core.data_helpers import generate_data, load_data
from dss.core.trainers import RegressionTrainer, ClassificationTrainer


def test_synthetic_data_generation_metadata():
    """TEST 1: Kiểm tra metadata data_source_type và cấu trúc cột của dữ liệu tự sinh."""
    df = generate_data(n_students=50)
    assert df.attrs.get("data_source_type") == "synthetic", (
        "generate_data() phải gán df.attrs['data_source_type'] = 'synthetic'"
    )
    assert "diem_ky_sau" in df.columns, "Phải có canonical target diem_ky_sau"
    assert "diem_ky_nay" in df.columns, "Phải có legitimate predictor diem_ky_nay"
    assert "xep_loai" in df.columns, "Phải có canonical classification target xep_loai"
    assert "final_score" in df.columns, "Phải có alias final_score cho tương thích ngược"
    assert "grade" in df.columns, "Phải có alias grade cho tương thích ngược"
    
    # Kiểm tra tính nhất quán giữa điểm và xếp loại
    expected_xep_loai = score_to_xep_loai(df["diem_ky_sau"]).astype(str)
    pd.testing.assert_series_equal(
        df["xep_loai"], expected_xep_loai, check_names=False
    )
    pd.testing.assert_series_equal(
        df["grade"], df["xep_loai"], check_names=False
    )


def test_real_data_source_type(tmp_path):
    """TEST 2: Kiểm tra metadata data_source_type='real' khi nạp từ file thật."""
    sample_path = tmp_path / "sample_real.csv"
    sample_df = pd.DataFrame({
        "student_id": ["SV01", "SV02", "SV03"],
        "diem_ky_nay": [7.0, 8.0, 6.5],
        "diem_ky_sau": [7.5, 8.5, 6.0],
    })
    sample_df.to_csv(sample_path, index=False)
    
    loaded_df = load_data(str(sample_path))
    assert loaded_df is not None
    assert loaded_df.attrs.get("data_source_type") == "real", (
        "load_data() phải gán df.attrs['data_source_type'] = 'real'"
    )


def test_target_leakage_guard_regression():
    """TEST 3: Khi target là diem_ky_sau, X không được chứa final_score, xep_loai, grade,
    nhưng PHẢI giữ diem_ky_nay."""
    df = pd.DataFrame({
        "diem_ky_nay": [6.0, 7.5, 8.0],
        "so_gio_hoc_tuan": [10, 15, 20],
        "diem_giua_ky": [6.5, 7.0, 8.5],
        "final_score": [6.2, 7.8, 8.2],
        "xep_loai": ["Khá", "Giỏi", "Giỏi"],
        "grade": ["Khá", "Giỏi", "Giỏi"],
        "diem_ky_sau": [6.2, 7.8, 8.2],
    })
    candidates = ["diem_ky_nay", "so_gio_hoc_tuan", "diem_giua_ky", "final_score", "xep_loai", "grade"]
    filtered = filter_leakage_features(df, "diem_ky_sau", candidates)
    
    assert "diem_ky_nay" in filtered, "diem_ky_nay là legitimate predictor, KHÔNG được lọc bỏ"
    assert "so_gio_hoc_tuan" in filtered
    assert "diem_giua_ky" in filtered
    assert "final_score" not in filtered, "final_score là alias của target, phải bị lọc"
    assert "xep_loai" not in filtered, "xep_loai là derived target, phải bị lọc"
    assert "grade" not in filtered, "grade là alias của xep_loai, phải bị lọc"


def test_target_leakage_guard_classification():
    """TEST 4: Khi target là xep_loai, X không được chứa grade, diem_ky_sau, final_score,
    nhưng PHẢI giữ diem_ky_nay."""
    df = pd.DataFrame({
        "diem_ky_nay": [6.0, 7.5, 8.0],
        "so_gio_hoc_tuan": [10, 15, 20],
        "diem_giua_ky": [6.5, 7.0, 8.5],
        "final_score": [6.2, 7.8, 8.2],
        "diem_ky_sau": [6.2, 7.8, 8.2],
        "grade": ["Khá", "Giỏi", "Giỏi"],
        "xep_loai": ["Khá", "Giỏi", "Giỏi"],
    })
    candidates = ["diem_ky_nay", "so_gio_hoc_tuan", "diem_giua_ky", "final_score", "diem_ky_sau", "grade"]
    filtered = filter_leakage_features(df, "xep_loai", candidates)
    
    assert "diem_ky_nay" in filtered, "diem_ky_nay là legitimate predictor, KHÔNG được lọc bỏ"
    assert "so_gio_hoc_tuan" in filtered
    assert "diem_giua_ky" in filtered
    assert "grade" not in filtered, "grade là alias của xep_loai, phải bị lọc"
    assert "diem_ky_sau" not in filtered, "diem_ky_sau là target gốc của xep_loai, phải bị lọc"
    assert "final_score" not in filtered, "final_score là alias của diem_ky_sau, phải bị lọc"


def test_filter_leakage_features_helper():
    """TEST 5: Kiểm tra trực tiếp helper filter_leakage_features."""
    dummy_df = pd.DataFrame({"a": [1, 2], "diem_ky_nay": [5.0, 6.0]})
    # Target diem_ky_sau
    res_reg = filter_leakage_features(
        dummy_df,
        "diem_ky_sau",
        ["a", "diem_ky_nay", "final_score", "xep_loai", "grade"]
    )
    assert res_reg == ["a", "diem_ky_nay"]

    # Target xep_loai
    res_clf = filter_leakage_features(
        dummy_df,
        "xep_loai",
        ["a", "diem_ky_nay", "grade", "diem_ky_sau", "final_score"]
    )
    assert res_clf == ["a", "diem_ky_nay"]


def test_canonicalize_columns_case1():
    """TEST 6: Case 1 - Chuẩn hoá dataframe chuẩn đã có diem_ky_sau và xep_loai."""
    df = pd.DataFrame({
        "diem_ky_nay": [7.0, 8.0],
        "diem_ky_sau": [7.5, 8.5],
        "xep_loai": ["Khá", "Giỏi"],
    })
    res_df = canonicalize_columns(df)
    assert "diem_ky_sau" in res_df.columns
    assert "xep_loai" in res_df.columns
    assert "final_score" not in res_df.columns
    assert "grade" not in res_df.columns


def test_canonicalize_columns_case2():
    """TEST 7: Case 2 - Dataset chỉ có final_score và grade -> đổi tên thành diem_ky_sau và xep_loai."""
    df = pd.DataFrame({
        "diem_ky_nay": [7.0, 8.0],
        "final_score": [7.5, 8.5],
        "grade": ["Khá", "Giỏi"],
    })
    res_df = canonicalize_columns(df)
    assert "diem_ky_sau" in res_df.columns
    assert "xep_loai" in res_df.columns
    assert "final_score" not in res_df.columns
    assert "grade" not in res_df.columns
    assert res_df["diem_ky_sau"].tolist() == [7.5, 8.5]
    assert res_df["xep_loai"].tolist() == ["Khá", "Giỏi"]


def test_canonicalize_columns_case3():
    """TEST 8: Case 3 - Dataset chỉ có diem_ky_sau -> tự động suy biến xep_loai theo ngưỡng chuẩn."""
    df = pd.DataFrame({
        "diem_ky_nay": [3.5, 6.0, 9.0],
        "diem_ky_sau": [3.5, 6.0, 9.0],
    })
    res_df = canonicalize_columns(df)
    assert "xep_loai" in res_df.columns
    assert res_df["xep_loai"].tolist() == ["Yếu", "Khá", "Xuất sắc"]


def test_canonicalize_columns_case4_consistent():
    """TEST 9: Case 4 nhất quán - Dataset có cả final_score và diem_ky_sau giống nhau -> bỏ final_score."""
    df = pd.DataFrame({
        "diem_ky_nay": [7.0, 8.0],
        "diem_ky_sau": [7.5, 8.5],
        "final_score": [7.5, 8.5],
        "xep_loai": ["Khá", "Giỏi"],
    })
    res_df = canonicalize_columns(df)
    assert "diem_ky_sau" in res_df.columns
    assert "final_score" not in res_df.columns
    assert res_df["diem_ky_sau"].tolist() == [7.5, 8.5]


def test_canonicalize_columns_case4_conflict():
    """TEST 10: Case 4 xung đột - final_score và diem_ky_sau khác nhau."""
    df = pd.DataFrame({
        "diem_ky_sau": [7.5, 8.5],
        "final_score": [5.0, 6.0],
    })
    with pytest.raises(ValueError, match="Xung đột dữ liệu"):
        canonicalize_columns(df, strict=True)
        
    # Non-strict mode giữ diem_ky_sau và drop final_score
    res_df = canonicalize_columns(df, strict=False)
    assert "diem_ky_sau" in res_df.columns
    assert "final_score" not in res_df.columns
    assert res_df["diem_ky_sau"].tolist() == [7.5, 8.5]


def test_score_to_xep_loai_thresholds():
    """TEST 11: Kiểm tra hàm phân ngưỡng score_to_xep_loai với toàn bộ các mốc biên."""
    test_scores = pd.Series([
        0.0, 3.5, 3.99,   # Yếu (< 4.0)
        4.0, 4.5, 5.49,   # Trung bình (4.0 - 5.49)
        5.5, 6.0, 6.99,   # Khá (5.5 - 6.99)
        7.0, 7.5, 8.49,   # Giỏi (7.0 - 8.49)
        8.5, 9.0, 10.0,   # Xuất sắc (8.5 - 10.0)
    ])
    labels = score_to_xep_loai(test_scores).tolist()
    expected = [
        "Yếu", "Yếu", "Yếu",
        "Trung bình", "Trung bình", "Trung bình",
        "Khá", "Khá", "Khá",
        "Giỏi", "Giỏi", "Giỏi",
        "Xuất sắc", "Xuất sắc", "Xuất sắc",
    ]
    assert labels == expected


def test_temporal_train_test_split():
    """TEST 12: Kiểm tra chia dữ liệu thời gian: train chỉ gồm học kỳ trước, test gồm học kỳ sau."""
    df = pd.DataFrame({
        "student_id": [1, 2, 3, 4, 5, 6],
        "hoc_ky": [1, 1, 2, 2, 3, 3],
        "gpa": [6.0, 7.0, 6.5, 7.2, 8.0, 7.8],
    })
    train_df, test_df = temporal_train_test_split(df, time_col="hoc_ky", test_ratio=0.33)
    
    assert not train_df.empty
    assert not test_df.empty
    assert train_df["hoc_ky"].max() < test_df["hoc_ky"].min(), (
        "Tập train không được chứa dữ liệu từ học kỳ của tập test (tránh data leakage theo thời gian)"
    )
    assert set(test_df["hoc_ky"].unique()) == {3}
    assert set(train_df["hoc_ky"].unique()) == {1, 2}


def test_prepare_longitudinal_dataset():
    """TEST 13: Kiểm tra tạo target Y_(t+1) từ dữ liệu dọc đa học kỳ."""
    df = pd.DataFrame({
        "student_id": ["SV1", "SV1", "SV1", "SV2", "SV2"],
        "hoc_ky": [1, 2, 3, 1, 2],
        "gpa": [6.0, 7.0, 8.0, 5.0, 6.5],
    })
    long_df = prepare_longitudinal_dataset(
        df,
        student_id_col="student_id",
        time_col="hoc_ky",
        target_metric_col="gpa",
        drop_na_target=True,
    )
    
    # SV1 kỳ 1 -> target 7.0 (kỳ 2)
    sv1_k1 = long_df[(long_df["student_id"] == "SV1") & (long_df["hoc_ky"] == 1)].iloc[0]
    assert sv1_k1["diem_ky_sau"] == 7.0
    assert sv1_k1["xep_loai"] == "Giỏi"
    
    # SV1 kỳ 2 -> target 8.0 (kỳ 3)
    sv1_k2 = long_df[(long_df["student_id"] == "SV1") & (long_df["hoc_ky"] == 2)].iloc[0]
    assert sv1_k2["diem_ky_sau"] == 8.0
    assert sv1_k2["xep_loai"] == "Giỏi"
    
    # SV2 kỳ 1 -> target 6.5 (kỳ 2)
    sv2_k1 = long_df[(long_df["student_id"] == "SV2") & (long_df["hoc_ky"] == 1)].iloc[0]
    assert sv2_k1["diem_ky_sau"] == 6.5
    assert sv2_k1["xep_loai"] == "Khá"
    
    # Kỳ cuối của mỗi SV không có kết quả kỳ sau nên đã bị loại khi drop_na_target=True
    assert len(long_df) == 3


def test_warehouse_metadata_persistence(warehouse):
    """TEST 14: Kiểm tra lưu vết data_source_type và split_strategy trong Kho dữ liệu (Warehouse)."""
    tid, _ = warehouse.save_model_training(
        dataset_id="test_ds",
        model_pipeline=None,
        model_name="Random Forest Regressor",
        feature_cols=["diem_ky_nay", "so_gio_hoc_tuan"],
        target_col="diem_ky_sau",
        metrics={"RMSE": 0.35, "MAE": 0.28, "R2": 0.82},
        is_best=True,
        data_source_type="synthetic",
        split_strategy="temporal",
        prediction_horizon="t+1",
    )
    warehouse.set_production_model(tid, promoted_by="admin")
    
    _, meta = warehouse.get_production_model("test_ds", "diem_ky_sau")
    assert meta is not None, "Phải đọc được production model vừa lưu"
    assert meta.get("data_source_type") == "synthetic"
    assert meta.get("split_strategy") == "temporal"
    assert meta.get("prediction_horizon") == "t+1"



def test_trainers_leakage_and_legitimate_predictors():
    """TEST 15: Kiểm tra ClassificationTrainer và RegressionTrainer tự động loại bỏ rò rỉ
    nhưng bảo vệ legitimate predictor diem_ky_nay."""
    np.random.seed(42)
    n = 60
    # Dữ liệu thử nghiệm có diem_ky_nay, diem_ky_sau, final_score, grade, xep_loai
    diem_nay = np.random.uniform(4.0, 9.5, n)
    diem_sau = np.clip(diem_nay + np.random.normal(0, 0.5, n), 0, 10)
    xep_loai_series = score_to_xep_loai(pd.Series(diem_sau))
    
    df = pd.DataFrame({
        "diem_ky_nay": diem_nay,
        "so_gio_hoc_tuan": np.random.randint(5, 30, n),
        "diem_giua_ky": np.random.uniform(4.0, 10.0, n),
        "final_score": diem_sau,             # Leaky alias
        "xep_loai": xep_loai_series.values,  # Leaky derived target for regression
        "grade": xep_loai_series.values,     # Leaky alias for classification
        "diem_ky_sau": diem_sau,             # Target regression
    })
    
    # 1. Regression Trainer
    reg_trainer = RegressionTrainer()
    reg_features = ["diem_ky_nay", "so_gio_hoc_tuan", "diem_giua_ky", "final_score", "xep_loai", "grade"]
    results, pipelines, eval_frames, trained_feats_reg, X_test, y_test, X_train = reg_trainer.train_and_evaluate(
        df,
        feature_cols=reg_features,
        target_col="diem_ky_sau",
        selected_models=["Linear Regression"],
        test_size=0.2,
        cv_folds=3,
        save_model=False,
    )
    assert "diem_ky_nay" in trained_feats_reg, "diem_ky_nay phải được giữ lại cho RegressionTrainer"
    assert "final_score" not in trained_feats_reg, "final_score phải bị loại khỏi RegressionTrainer"
    assert "xep_loai" not in trained_feats_reg, "xep_loai phải bị loại khỏi RegressionTrainer"
    assert "grade" not in trained_feats_reg, "grade phải bị loại khỏi RegressionTrainer"

    # 2. Classification Trainer
    clf_trainer = ClassificationTrainer()
    clf_features = ["diem_ky_nay", "so_gio_hoc_tuan", "diem_giua_ky", "grade", "diem_ky_sau", "final_score"]
    results, pipelines, labels, trained_feats_clf, X_test, y_test, X_train = clf_trainer.train_and_evaluate(
        df,
        feature_cols=clf_features,
        target_col="xep_loai",
        selected_models=["Random Forest Classifier"],
        test_size=0.2,
        cv_folds=3,
        save_model=False,
    )
    assert "diem_ky_nay" in trained_feats_clf, "diem_ky_nay phải được giữ lại cho ClassificationTrainer"
    assert "grade" not in trained_feats_clf, "grade phải bị loại khỏi ClassificationTrainer"
    assert "diem_ky_sau" not in trained_feats_clf, "diem_ky_sau phải bị loại khỏi ClassificationTrainer"
    assert "final_score" not in trained_feats_clf, "final_score phải bị loại khỏi ClassificationTrainer"
