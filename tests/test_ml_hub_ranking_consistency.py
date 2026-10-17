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
from dss.core.trainers import PR_AUC_SELECTION_THRESHOLD, ClassificationTrainer
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


def test_pr_auc_drives_selection_when_minority_class_is_tiny():
    """Lớp thiểu số quá ít mẫu thì GridSearchCV phải chọn mô hình bằng PR-AUC, không F1.

    Lịch sử của test này: trước đây nó khẳng định "trên dữ liệu mẫu, model đứng
    đầu theo Accuracy KHÁC model đứng đầu theo F1-macro" — một nhân chứng cho lỗi
    S-1. Khẳng định đó nay không còn đúng, và lý do chính là thứ test này kiểm.

    Dữ liệu mẫu có lớp "Yếu" đúng 2 mẫu trên 1.000. Ở cỡ đó, recall của lớp này
    chỉ nhận được 0 / 0,5 / 1, nên F1-macro dịch khoảng 1/số_lớp chỉ vì một mẫu
    đoán đúng hay sai — chọn mô hình bằng con số ấy là chọn theo nhiễu. Từ khi
    tiêu chí chuyển sang PR-AUC (xem PR_AUC_SELECTION_THRESHOLD), xếp hạng ổn
    định hơn và hai tiêu chí không còn mâu thuẫn trên chính bộ dữ liệu này.

    Nên ở đây kiểm ĐIỀU KIỆN KÍCH HOẠT, không kiểm triệu chứng cũ: triệu chứng
    biến mất là kết quả mong muốn, còn điều kiện kích hoạt mới là thứ phải giữ.
    """
    df = generate_data()
    min_class_count = int(df["xep_loai"].value_counts().min())
    assert min_class_count < PR_AUC_SELECTION_THRESHOLD, (
        f"Dữ liệu mẫu nay có lớp ít nhất {min_class_count} mẫu, không còn dưới "
        f"ngưỡng {PR_AUC_SELECTION_THRESHOLD} nên không kiểm được nhánh PR-AUC. "
        "Hãy chỉnh dữ liệu mẫu hoặc ngưỡng, đừng bỏ test."
    )

    results = _train_classification_results()
    metrics_df = build_metrics_dataframe(results, "clf")
    # PR-AUC phải có mặt trong báo cáo để người đọc đối chiếu được với F1.
    assert "PR-AUC (Macro)" in metrics_df.columns, (
        "Thiếu cột PR-AUC trong bảng chỉ số: tiêu chí dùng để CHỌN mô hình phải "
        "hiện ra cho người đọc, nếu không thì không ai kiểm lại được lựa chọn."
    )
    assert metrics_df["PR-AUC (Macro)"].notna().any(), (
        "Không mô hình nào tính được PR-AUC, nên tiêu chí chọn mô hình đang dựa "
        "trên giá trị rỗng."
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
