"""Unit tests for PDF Certificate & Career Passport Generator."""
from dss.services.pdf_certificate_service import generate_career_passport_pdf


def test_generate_career_passport_pdf_basic():
    """Kiểm tra sinh file PDF hợp lệ với dữ liệu tối thiểu."""
    pdf_bytes = generate_career_passport_pdf(
        student_id="SV2025_001",
        target_role="Data Scientist",
        career_fit_score=88.5,
        career_readiness_score=82.0,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")


def test_generate_career_passport_pdf_full_data():
    """Kiểm tra sinh file PDF với đầy đủ dữ liệu kế hoạch 4 tuần và liều lượng."""
    sample_plan = [
        {"week": 1, "topic": "Ôn tập Thống kê", "action": "Hoàn thành 10 bài tập xác suất."},
        {"week": 2, "topic": "Thực hành Pandas", "action": "Xử lý dữ liệu bảng thiếu."},
        {"week": 3, "topic": "Huấn luyện Scikit-Learn", "action": "Xây dựng Random Forest."},
        {"week": 4, "topic": "Kiểm thử Model", "action": "Tính Confusion Matrix và F1."},
    ]

    pdf_bytes = generate_career_passport_pdf(
        student_id="SV2025_099",
        student_name="Trần Văn Thử Nghiệm",
        major="Khoa học Dữ liệu",
        target_role="Machine Learning Engineer",
        career_fit_score=92.0,
        career_readiness_score=89.5,
        gap_size="Nhỏ",
        key_strengths=["Toán rời rạc", "Python nâng cao"],
        key_gaps=["Kiến thức MLOps"],
        four_week_plan=sample_plan,
        dosage_hours=7.5,
        dosage_exercises=20,
        certificate_id="TEST-CERT-12345",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")
