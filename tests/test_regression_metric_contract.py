"""FINAL GAP CLOSURE — Câu 33 (R-5): the regression metric contract must be
explicit, not silently inconsistent. Locks in the deliberate choice: MAE for
GridSearchCV hyperparameter tuning (outlier-robust, stable across small CV
folds), RMSE as the PRIMARY final-ranking metric (penalizes large errors
more — appropriate for an at-risk-student warning system where a large miss
matters more than several small ones), R2/MAE as SECONDARY metrics still
shown alongside. This test exists so a future change to either side of the
contract must consciously break it, not silently drift apart again."""

from __future__ import annotations

import inspect

import pandas as pd

from dss.core import trainers
from dss.services.model_service import resolve_ranking_col


def test_gridsearch_tuning_uses_mae_scoring():
    source = inspect.getsource(trainers.RegressionTrainer)
    assert 'scoring="neg_mean_absolute_error"' in source, (
        "Hợp đồng metric: GridSearchCV tuning cho hồi quy phải dùng MAE (ít nhạy ngoại lai)."
    )


def test_gridsearch_uses_single_metric_refit_no_ambiguity():
    """refit=True (đơn tiêu chí, không phải multi-metric refit callable) —
    không có nhập nhằng metric nào được refit."""
    # GridSearchCV nay nằm trong dss.core.tuning.tuned_fit (có ghi nhớ tham số).
    from dss.core import tuning

    assert "tuning.tuned_fit(" in inspect.getsource(trainers.RegressionTrainer)
    assert "refit=True" in inspect.getsource(tuning.tuned_fit)


def test_ranking_col_primary_metric_is_rmse_for_regression():
    metrics_df = pd.DataFrame({"RMSE": [1.2, 0.9], "MAE": [1.0, 0.8], "R2 Score": [0.8, 0.9]})
    sort_col, ascending = resolve_ranking_col(metrics_df, "reg")
    assert sort_col == "RMSE", "RMSE phải là PRIMARY ranking metric cho hồi quy."
    assert ascending is True, "RMSE càng thấp càng tốt -> sort ascending."


def test_ranking_col_falls_back_to_r2_when_rmse_absent():
    """Nếu vì lý do nào đó RMSE không có sẵn, R2 Score là fallback hợp lý
    (KHÔNG phải MAE — giữ nhất quán với hợp đồng: MAE chỉ dùng cho tuning,
    không dùng để xếp hạng cuối cùng)."""
    metrics_df = pd.DataFrame({"MAE": [1.0, 0.8], "R2 Score": [0.8, 0.9]})
    sort_col, ascending = resolve_ranking_col(metrics_df, "reg")
    assert sort_col == "R2 Score"
    assert ascending is False, "R2 Score càng cao càng tốt -> sort descending."


def test_mae_and_r2_still_reported_as_secondary_metrics():
    """Hợp đồng KHÔNG được ẩn MAE/R2 khỏi báo cáo chỉ vì RMSE là primary —
    cả 2 vẫn phải xuất hiện trong bảng kết quả (kiểm tra qua chính cấu trúc
    cột build_metrics_dataframe tạo ra, không lặp lại toàn bộ pipeline)."""
    from dss.services.model_service import build_metrics_dataframe

    source = inspect.getsource(build_metrics_dataframe)
    assert '"MAE"' in source or "'MAE'" in source
    assert '"R2 Score"' in source or "'R2 Score'" in source
    assert '"RMSE"' in source or "'RMSE'" in source
