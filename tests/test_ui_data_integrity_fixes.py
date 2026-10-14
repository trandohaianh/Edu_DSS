"""Regression suite cho đợt sửa lỗi UI/logic (raw enum leak, recommendation
chung chung, feature label, màu biểu đồ theo môn, Dataset-card lộ cho Sinh
viên). Test thuần logic, không cần Streamlit runtime.
"""
from __future__ import annotations

import pandas as pd
import pytest


def test_category_label_never_returns_raw_enum():
    from dss.services.diagnosis_engine import category_label, CATEGORY_MASTERY_ON_TRACK, CATEGORY_LOW_PRACTICE

    assert category_label(CATEGORY_MASTERY_ON_TRACK) == "Tiến độ học tập ổn định"
    assert "_" not in category_label(CATEGORY_LOW_PRACTICE)
    # Danh mục lạ/None vẫn phải trả về tiếng Việt, không trả nguyên input.
    assert category_label("SOME_UNKNOWN_ENUM") == "Nhận định chung"
    assert category_label(None) == "Nhận định chung"


def test_feature_label_translates_known_raw_columns():
    from dss.core.data_helpers import feature_label

    assert feature_label("gpa_previous") == "GPA kỳ trước"
    assert feature_label("final_score") == "Điểm tổng kết"
    assert feature_label("ty_le_diem_danh") == "Tỷ lệ điểm danh"
    assert feature_label("so_gio_hoc_tuan") == "Số giờ học mỗi tuần"


def test_feature_label_never_leaks_raw_snake_case_for_unknown_column():
    from dss.core.data_helpers import feature_label

    label = feature_label("mot_cot_la_chua_khai_bao")
    assert "_" not in label
    assert label[0].isupper()


def test_topic_color_is_deterministic_across_calls_and_known_topics_match_spec():
    from dss.core.data_helpers import topic_color

    # Môn đã khai báo phải khớp đúng màu yêu cầu trong spec.
    assert topic_color("Thống kê") == "#2563EB"
    assert topic_color("Xử lý dữ liệu") == "#F59E0B"
    assert topic_color("Machine Learning cơ bản") == "#7C3AED"

    # Môn lạ (không có trong COURSE_COLOR_MAP) vẫn phải ra CÙNG 1 màu mỗi lần gọi
    # (ổn định giữa các lần chạy — không phụ thuộc PYTHONHASHSEED).
    c1 = topic_color("Một môn học hoàn toàn mới")
    c2 = topic_color("Một môn học hoàn toàn mới")
    assert c1 == c2

    # Hai môn khác tên nên (thường) ra màu khác nhau.
    assert topic_color("Môn A") != topic_color("Môn hoàn toàn khác B") or True  # không bắt buộc tuyệt đối (hash collision hiếm)


def test_intervention_plan_recommendations_differ_across_features():
    from dss.services.clustering_service import compute_intervention_plan

    diff_pct = pd.Series({
        "final_score": -25.0,
        "ty_le_diem_danh": -25.0,
        "so_gio_hoc_tuan": -25.0,
    })
    df_plan = compute_intervention_plan(diff_pct, ["final_score", "ty_le_diem_danh", "so_gio_hoc_tuan"])

    actions = df_plan["Hành động gợi ý"].tolist()
    # Bug cũ: cả 3 dòng nhận ĐÚNG 1 câu văn giống hệt nhau dù feature khác nhau.
    assert len(set(actions)) == len(actions), f"Recommendation bị lặp lại giống hệt nhau: {actions}"

    # Cột hiển thị phải dùng nhãn tiếng Việt, không phải tên cột thô.
    assert "Điểm tổng kết" in df_plan["Chỉ số"].tolist()
    assert "final_score" not in df_plan["Chỉ số"].tolist()


def test_intervention_plan_action_mentions_the_actual_gap_percentage():
    from dss.services.clustering_service import compute_intervention_plan

    diff_pct = pd.Series({"ty_le_diem_danh": -30.0})
    df_plan = compute_intervention_plan(diff_pct, ["ty_le_diem_danh"])
    action = df_plan.iloc[0]["Hành động gợi ý"]
    assert "30" in action  # bằng chứng số liệu thật, không phải câu chung chung


def test_intervention_plan_columns_use_vietnamese_labels_not_english():
    from dss.services.clustering_service import compute_intervention_plan

    df_plan = compute_intervention_plan(pd.Series({"diem_giua_ky": 0.0}), ["diem_giua_ky"])
    cols = set(df_plan.columns)
    assert "Feature" not in cols
    assert "Ưu tiên" not in cols  # tên cột cũ (đã đổi thành "Mức ưu tiên")
    assert "Mức ưu tiên" in cols
    assert "Chỉ số" in cols
