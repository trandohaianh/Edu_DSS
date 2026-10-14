"""S-1: Xác minh biểu đồ/bảng xếp hạng trong main.py và is_best khi lưu Kho dùng
CHUNG 1 tiêu chí "model tốt nhất" (qua model_service.resolve_ranking_col), thay
vì main.py hard-code Accuracy còn pick_best_model_name dùng F1 Score (Macro).

Dữ liệu mẫu generate_data() có lớp "Yếu" cực hiếm (2/1000) nên Accuracy và
F1 Score (Macro) xếp hạng model KHÁC NHAU — đúng kịch bản mô tả trong lỗi S-1.
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
    """Bằng chứng CHO THẤY lỗi có thể xảy ra: trên dữ liệu mẫu, model đứng đầu
    theo Accuracy khác model đứng đầu theo F1 Score (Macro)."""
    results = _train_classification_results()
    metrics_df = build_metrics_dataframe(results, "clf")
    best_by_accuracy = metrics_df.sort_values("Accuracy", ascending=False).index[0]
    best_by_f1_macro = metrics_df.sort_values("F1 Score (Macro)", ascending=False).index[0]
    assert best_by_accuracy != best_by_f1_macro, (
        "Dữ liệu mẫu không còn tạo ra sự khác biệt xếp hạng — cần dữ liệu khác để "
        "tái hiện S-1, nhưng bản thân sự thống nhất tiêu chí vẫn phải giữ nguyên."
    )


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
