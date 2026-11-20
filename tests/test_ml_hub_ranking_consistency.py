"""S-1: Xác minh biểu đồ/bảng xếp hạng trong main.py và is_best khi lưu Kho dùng
CHUNG 1 tiêu chí "model tốt nhất" (qua model_service.resolve_ranking_col), thay
vì main.py hard-code Accuracy còn pick_best_model_name dùng F1 Score (Macro).

Trường hợp metric bất đồng dùng fixture cố định; kết quả mô hình thực tế
được kiểm tra riêng để bảo đảm bảng xếp hạng và lựa chọn mô hình thống nhất.
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer
from dss.services.model_service import (
    build_metrics_dataframe,
    pick_best_model_name,
    resolve_ranking_col,
)


def _train_classification_results():
    df = generate_data()
    feats = [
        c for c in df.columns
        if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")
    ]
    clf = ClassificationTrainer()
    results, *_ = clf.train_and_evaluate(
        df, feats, "xep_loai", list(clf.models), cv_folds=5, save_model=False
    )
    return results


def test_accuracy_and_f1_macro_rank_models_differently_on_sample_data():
    """A fixed disagreement verifies the ranking contract independently of fit results.

    A trained model can legitimately lead both metrics after model/library
    improvements; the regression needs explicit differing metrics.
    """
    results = {
        "Majority-biased": {"Accuracy": 0.95, "F1 Score (Macro)": 0.45},
        "Balanced": {"Accuracy": 0.85, "F1 Score (Macro)": 0.80},
    }
    metrics_df = build_metrics_dataframe(results, "clf")
    best_by_accuracy = metrics_df.sort_values("Accuracy", ascending=False).index[0]
    best_by_f1_macro = metrics_df.sort_values("F1 Score (Macro)", ascending=False).index[0]
    assert best_by_accuracy == "Majority-biased"
    assert best_by_f1_macro == "Balanced"
    assert pick_best_model_name(results, "clf") == best_by_f1_macro


def test_pick_best_model_name_matches_resolve_ranking_col():
    """`pick_best_model_name` (dùng để đánh dấu is_best khi lưu Kho) phải dùng
    ĐÚNG tiêu chí mà `resolve_ranking_col` trả về — đây là hàm DÙNG CHUNG mà
    main.py cũng phải gọi (thay vì hard-code "Accuracy" như trước khi sửa)."""
    results = _train_classification_results()
    metrics_df = build_metrics_dataframe(results, "clf")
    sort_col, ascending = resolve_ranking_col(metrics_df, "clf")
    expected_best = metrics_df.sort_values(sort_col, ascending=ascending).index[0]
    assert pick_best_model_name(results, "clf") == expected_best


def test_main_py_does_not_hardcode_accuracy_as_ranking_metric():
    """main.py KHÔNG ĐƯỢC tự tính tiêu chí xếp hạng "Accuracy" cứng cho phân
    loại — phải gọi resolve_ranking_col (hàm dùng chung với pick_best_model_name)
    để bảng xếp hạng UI và is_best trong Kho luôn khớp nhau."""
    main_file = Path(__file__).resolve().parents[1] / "dss" / "main.py"
    main_py = main_file.read_text(encoding="utf-8")
    assert 'resolve_ranking_col' in main_py, (
        "main.py phải gọi model_service.resolve_ranking_col thay vì hard-code "
        "tiêu chí xếp hạng \"Accuracy\"."
    )
    assert '_eval_rank_metric = "Accuracy" if _eval_hub_type == "clf"' not in main_py
    assert 'rank_metric = "Accuracy" if current_hub_type == "clf"' not in main_py
