"""Hồi quy cho các lỗi thuật toán được rà soát xác nhận (đợt 2026-11).

B2 cột thời gian theo chuỗi con · B3 chia train/test & CV không theo nhóm sinh viên ·
B5 chọn mô hình theo điểm test · B6 Elbow luôn = k_start+1 · B7 loại nhầm cột có "id" ·
B8 SHAP bỏ qua bước chọn đặc trưng · B9 PSI báo drift giả ở cỡ mẫu nhỏ · S8 cảnh báo
khi không có cấu trúc cụm.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# B2 — detect_temporal_column
# ---------------------------------------------------------------------------


def test_b2_temporal_column_matches_whole_names_not_substrings():
    from dss.core.target_utils import detect_temporal_column

    lms = pd.DataFrame(columns=["student_id", "total_time_minutes", "diem_ky_nay", "hoc_ky"])
    assert detect_temporal_column(lms) == "hoc_ky"
    uci = pd.DataFrame(columns=["school", "age", "traveltime", "studytime", "G1", "G2", "G3"])
    assert detect_temporal_column(uci) is None
    others = pd.DataFrame(columns=["mid_term_score", "ngay_sinh", "date_of_birth", "semester_gpa"])
    assert detect_temporal_column(others) is None
    assert detect_temporal_column(pd.DataFrame(columns=["x", "semester"])) == "semester"
    assert detect_temporal_column(pd.DataFrame(columns=["x", "nam_hoc"])) == "nam_hoc"


def test_b2_temporal_column_never_returns_a_model_feature_and_prefers_datetime():
    from dss.core.target_utils import detect_temporal_column

    df = pd.DataFrame({"hoc_ky": [1, 2], "x": [0.1, 0.2]})
    assert detect_temporal_column(df, feature_cols=["hoc_ky", "x"]) is None
    df2 = pd.DataFrame({"semester": [1, 2], "submitted": pd.to_datetime(["2026-01-01", "2026-02-01"])})
    assert detect_temporal_column(df2) == "submitted"


# ---------------------------------------------------------------------------
# B3 — chia theo nhóm sinh viên
# ---------------------------------------------------------------------------


def _longitudinal_df(n_students=60, n_terms=4, seed=0):
    rng = np.random.RandomState(seed)
    rows = []
    for s in range(n_students):
        ability = rng.normal(6.5, 1.5)
        for t in range(1, n_terms + 1):
            rows.append(
                {
                    "student_id": f"SV{s:03d}",
                    "hoc_ky": t,
                    "ty_le_diem_danh": float(np.clip(0.6 + 0.05 * ability + rng.normal(0, 0.05), 0, 1)),
                    "so_gio_hoc_tuan": ability * 2 + rng.normal(0, 1),
                    "diem_ky_sau": float(np.clip(ability + rng.normal(0, 0.4), 0, 10)),
                }
            )
    df = pd.DataFrame(rows)
    df["nhom"] = pd.cut(df["diem_ky_sau"], [-1, 5.5, 7.0, 11], labels=["thap", "tb", "cao"]).astype(str)
    return df


def _capture_cv(monkeypatch):
    from dss.core import tuning

    captured = []
    real = tuning.tuned_fit

    def spy(name, pipeline, param_grid, X, y, cv, scoring, sign=1.0):
        captured.append((X.index, cv))
        return real(name, pipeline, param_grid, X, y, cv, scoring, sign)

    monkeypatch.setattr(tuning, "tuned_fit", spy)
    tuning.clear_cache()
    return captured


def _assert_no_student_leak(df, X_train, X_test, captured):
    train_ids = set(df.loc[X_train.index, "student_id"])
    test_ids = set(df.loc[X_test.index, "student_id"])
    assert train_ids and test_ids
    assert not (train_ids & test_ids), "cùng một SV nằm ở cả train và test"
    assert captured, "GridSearchCV phải được gọi"
    for X_idx, cv in captured:
        groups = df.loc[X_idx, "student_id"].to_numpy()
        splits = cv if isinstance(cv, list) else list(cv.split(np.zeros(len(X_idx)), np.zeros(len(X_idx))))
        for tr, va in splits:
            assert not (set(groups[tr]) & set(groups[va])), "cùng một SV nằm ở cả fold train và fold kiểm định"


def test_b3_regression_split_and_cv_are_grouped_by_student(monkeypatch):
    from dss.core.trainers import RegressionTrainer

    df = _longitudinal_df()
    captured = _capture_cv(monkeypatch)
    out = RegressionTrainer().train_and_evaluate(
        df,
        ["ty_le_diem_danh", "so_gio_hoc_tuan"],
        "diem_ky_sau",
        ["Random Forest Regressor"],
        cv_folds=3,
        save_model=False,
    )
    X_test, X_train_final = out[4], out[6]
    _assert_no_student_leak(df, X_train_final, X_test, captured)


def test_b3_classification_split_and_cv_are_grouped_by_student(monkeypatch):
    from dss.core.trainers import ClassificationTrainer

    df = _longitudinal_df()
    captured = _capture_cv(monkeypatch)
    out = ClassificationTrainer().train_and_evaluate(
        df,
        ["ty_le_diem_danh", "so_gio_hoc_tuan"],
        "nhom",
        ["Logistic Regression (Softmax)"],
        cv_folds=3,
        save_model=False,
    )
    X_test, X_train_final = out[4], out[6]
    _assert_no_student_leak(df, X_train_final, X_test, captured)


def test_b3_one_row_per_student_keeps_row_level_split():
    from dss.core.utils import find_repeated_group_column

    df = _longitudinal_df()
    assert find_repeated_group_column(df, exclude=["ty_le_diem_danh"]) == "student_id"
    one_row = df.drop_duplicates("student_id")
    assert find_repeated_group_column(one_row) is None


# ---------------------------------------------------------------------------
# B5 — chọn mô hình theo điểm CV, không theo điểm test
# ---------------------------------------------------------------------------


def test_b5_best_model_is_chosen_by_cv_not_test_score():
    from dss.services.model_service import pick_best_model_name

    clf = {
        "LuckyOnTest": {"Accuracy": 0.92, "F1 Score (Macro)": 0.90, "cv_mean": 0.60, "cv_std": 0.02},
        "BetterCV": {"Accuracy": 0.85, "F1 Score (Macro)": 0.80, "cv_mean": 0.78, "cv_std": 0.02},
    }
    assert pick_best_model_name(clf, "clf") == "BetterCV"
    reg = {
        "LuckyOnTest": {"RMSE": 1.0, "MAE": 0.8, "R2 Score": 0.8, "cv_mean": 1.30},
        "BetterCV": {"RMSE": 1.1, "MAE": 0.9, "R2 Score": 0.78, "cv_mean": 0.95},
    }
    assert pick_best_model_name(reg, "reg") == "BetterCV"


def test_b5_falls_back_to_test_metric_when_cv_missing():
    from dss.services.model_service import build_metrics_dataframe, pick_best_model_name, resolve_ranking_col

    clf = {
        "A": {"Accuracy": 0.92, "F1 Score (Macro)": 0.90, "cv_mean": None},
        "B": {"Accuracy": 0.85, "F1 Score (Macro)": 0.80, "cv_mean": 0.78},
    }
    assert resolve_ranking_col(build_metrics_dataframe(clf, "clf"), "clf")[0] == "F1 Score (Macro)"
    assert pick_best_model_name(clf, "clf") == "A"


# ---------------------------------------------------------------------------
# B6 / B7 / S8 — phân cụm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("true_k", [4, 5])
def test_b6_elbow_finds_knee_not_k_start_plus_one(true_k):
    from sklearn.datasets import make_blobs

    from dss.services.clustering_service import compute_elbow_silhouette

    X, _ = make_blobs(n_samples=600, centers=true_k, n_features=5, cluster_std=1.0, random_state=1)
    result = compute_elbow_silhouette(X, 2, 10)
    assert result["suggested_k_elbow"] == true_k


def test_b7_default_cluster_features_keep_columns_containing_id_substring():
    from dss.services.clustering_service import select_default_cluster_features

    rng = np.random.RandomState(0)
    df = pd.DataFrame(
        {
            "student_id": np.arange(50),
            "midterm_score": rng.rand(50) * 10,
            "diem_giua_ky": rng.rand(50) * 10,
            "ty_le_diem_danh": rng.rand(50),
        }
    )
    cols = select_default_cluster_features(df)
    assert "midterm_score" in cols
    assert "student_id" not in cols


def test_s8_weak_cluster_structure_is_flagged():
    from sklearn.datasets import make_blobs

    from dss.services.clustering_service import compute_cluster_quality_metrics, compute_elbow_silhouette

    X = np.random.RandomState(0).uniform(size=(600, 6))
    result = compute_elbow_silhouette(X, 2, 6)
    assert max(s for s in result["silhouette"] if np.isfinite(s)) < 0.25
    assert result["weak_structure"] is True
    assert "không có cấu trúc nhóm rõ ràng" in result["warning"]
    assert "không có cấu trúc nhóm rõ ràng" in result["reason"]
    labels = np.random.RandomState(1).randint(0, 3, 600)
    assert "không có cấu trúc nhóm rõ ràng" in compute_cluster_quality_metrics(X, labels)["warning"]

    Xb, _ = make_blobs(n_samples=300, centers=3, n_features=4, random_state=1)
    assert compute_elbow_silhouette(Xb, 2, 5)["warning"] is None


# ---------------------------------------------------------------------------
# B8 — SHAP chạy đủ các bước trước model
# ---------------------------------------------------------------------------


def _fs_pipeline(model, with_sampler=False):
    from sklearn.feature_selection import SelectKBest, mutual_info_classif
    from sklearn.preprocessing import StandardScaler

    rng = np.random.RandomState(0)
    X = pd.DataFrame(rng.normal(size=(120, 6)), columns=[f"f{i}" for i in range(6)])
    y = (X.f5 + 0.3 * rng.normal(size=120) > 0).astype(int)
    if with_sampler:
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import Pipeline as ImbPipeline

        p = ImbPipeline(
            [
                ("preprocessor", StandardScaler()),
                ("sampler", SMOTE(random_state=0)),
                ("feature_selection", SelectKBest(mutual_info_classif, k=2)),
                ("model", model),
            ]
        )
    else:
        from sklearn.pipeline import Pipeline

        p = Pipeline(
            [
                ("preprocessor", StandardScaler()),
                ("feature_selection", SelectKBest(mutual_info_classif, k=2)),
                ("model", model),
            ]
        )
    return p.fit(X, y), X


@pytest.mark.parametrize("kind", ["rf", "lr", "rf_smote"])
def test_b8_shap_respects_feature_selection_step(kind):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    from dss.services.model_service import compute_shap_local_explanation, compute_shap_summary

    model = LogisticRegression() if kind == "lr" else RandomForestClassifier(n_estimators=20, random_state=0)
    pipe, X = _fs_pipeline(model, with_sampler=(kind == "rf_smote"))
    selected = list(X.columns[pipe.named_steps["feature_selection"].get_support()])

    sv, err = compute_shap_local_explanation(pipe, X.iloc[[0]], X.iloc[:40], list(X.columns))
    assert err is None, err
    assert list(sv.feature_names) == selected
    summary, err2 = compute_shap_summary(pipe, X.iloc[:30], list(X.columns))
    assert err2 is None, err2
    assert list(summary.feature_names) == selected


# ---------------------------------------------------------------------------
# B9 — PSI không báo drift giả trên cùng phân bố
# ---------------------------------------------------------------------------


def test_b9_identical_distribution_does_not_flag_drift_at_n500():
    from dss.services.ml_provenance import STATUS_DRIFT_DETECTED, STATUS_WARNING, evaluate_data_drift

    rng = np.random.RandomState(0)
    statuses = []
    for _ in range(20):
        df = pd.DataFrame(rng.normal(7, 1.5, (500, 5)), columns=list("abcde"))
        idx = rng.permutation(500)
        statuses.append(evaluate_data_drift(df.iloc[idx[:400]], df.iloc[idx[400:]])["overall_status"])
    assert statuses.count(STATUS_DRIFT_DETECTED) == 0
    assert statuses.count(STATUS_WARNING) <= 2, statuses


def test_b9_small_samples_are_insufficient_and_real_shift_still_detected():
    from dss.services.ml_provenance import STATUS_DRIFT_DETECTED, STATUS_INSUFFICIENT_DATA, evaluate_data_drift

    rng = np.random.RandomState(1)
    df = pd.DataFrame(rng.normal(7, 1.5, (200, 3)), columns=list("abc"))
    assert evaluate_data_drift(df.iloc[:160], df.iloc[160:])["overall_status"] == STATUS_INSUFFICIENT_DATA

    base = pd.DataFrame({"a": rng.normal(7, 1.5, 400)})
    cur = pd.DataFrame({"a": rng.normal(8.5, 1.5, 100)})  # lệch 1 độ lệch chuẩn
    result = evaluate_data_drift(base, cur)
    assert result["overall_status"] == STATUS_DRIFT_DETECTED
    assert set(result["per_feature"]["a"]) >= {"feature_type", "drift_metric", "threshold", "status"}
