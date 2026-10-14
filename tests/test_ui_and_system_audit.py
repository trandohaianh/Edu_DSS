"""Unit tests for Centralized Display Mapper and Shared UI Kit components."""
import pandas as pd
import pytest
from dss.core.display_mapper import (
    clean_display_dataframe,
    map_data_source,
    map_diagnosis_category,
    map_field_label,
    map_ml_metric,
    map_quiz_status,
    map_subscription_status,
)
from dss.tabs import ui_kit


def test_display_mapper_field_labels():
    assert map_field_label("final_score") == "Điểm tổng kết"
    assert map_field_label("gpa_previous") == "GPA kỳ trước"
    assert map_field_label("ty_le_diem_danh") == "Tỷ lệ điểm danh (%)"
    assert map_field_label("diem_machine_learning") == "Machine Learning căn bản"
    # Fallback for unknown snake_case
    assert map_field_label("unknown_special_col") == "Unknown Special Col"


def test_display_mapper_diagnosis_categories():
    assert map_diagnosis_category("MASTERY_ON_TRACK") == "Tiến độ học tập ổn định"
    assert map_diagnosis_category("LOW_ENGAGEMENT") == "Mức độ tương tác học tập thấp"
    assert map_diagnosis_category("KNOWLEDGE_GAP") == "Thiếu hụt kiến thức chuyên môn"
    assert map_diagnosis_category("PREREQUISITE_GAP") == "Chưa vững kiến thức nền tảng"
    assert map_diagnosis_category("INSUFFICIENT_DATA") == "Chưa đủ dữ liệu để đưa ra kết luận"
    assert map_diagnosis_category("") == "Tiến độ bình thường"


def test_display_mapper_quiz_and_data_source_and_sub_status():
    assert map_quiz_status("PENDING_LECTURER_APPROVAL") == "Chờ giảng viên duyệt"
    assert map_quiz_status("APPROVED") == "Đã phê duyệt"
    assert map_quiz_status("REJECTED") == "Đã từ chối"

    assert map_data_source("REAL") == "Dữ liệu LMS chính thức"
    assert map_data_source("DEMO") == "Dữ liệu mô phỏng thử nghiệm"

    assert map_subscription_status("ACTIVE") == "Đang hoạt động"
    assert map_subscription_status("EXPIRED") == "Hết hạn thuê bao"
    assert map_subscription_status("SUSPENDED") == "Tạm ngưng dịch vụ"


def test_display_mapper_ml_metrics():
    acc_info = map_ml_metric("accuracy")
    assert "Độ chính xác" in acc_info["label"]
    assert len(acc_info["desc"]) > 0

    mae_info = map_ml_metric("mae")
    assert "MAE" in mae_info["label"]

    r2_info = map_ml_metric("r2")
    assert "R²" in r2_info["label"]


def test_clean_display_dataframe():
    df = pd.DataFrame({
        "student_id": ["SV001", "SV002"],
        "final_score": [8.5, 7.0],
        "gpa_previous": [8.0, 6.8],
    })
    clean_df = clean_display_dataframe(df)
    assert "Mã sinh viên" in clean_df.columns
    assert "Điểm tổng kết" in clean_df.columns
    assert "GPA kỳ trước" in clean_df.columns
    # Ensure original df was not mutated
    assert "final_score" in df.columns


def test_ui_kit_components_rendering(monkeypatch):
    """Kiểm tra các UI helpers chạy an toàn mà không sinh ngoại lệ."""
    # Test badges and citations HTML generation
    b_html = ui_kit.badge_html("Đã duyệt", kind="success")
    assert "Đã duyệt" in b_html
    # C1.3: màu trạng thái đến từ token CSS (class ngữ nghĩa), không còn hex inline.
    assert "dss-status--success" in b_html

    cit_html = ui_kit.source_citation_badge("Bài 4 - Clustering", section="Mục 2", page="slide 12")
    assert "Bài 4 - Clustering" in cit_html
    assert "slide 12" in cit_html
