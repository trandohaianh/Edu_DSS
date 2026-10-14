"""FINAL GAP CLOSURE — Câu 48 (C-3): điểm mạnh/yếu của cụm phải xét ĐỘ PHÂN
TÁN thật của từng đặc trưng (z-score), không phải tỷ lệ ±10% cố định mù
phương sai. Test dựng 1 tình huống mà logic ratio cũ và z-score cho ra kết
luận KHÁC NHAU để chứng minh z-score thực sự thay đổi hành vi, không chỉ
thêm tham số không dùng tới."""
from __future__ import annotations

import pandas as pd

from dss.services import clustering_service


def test_high_variance_feature_not_flagged_strong_by_small_relative_gap():
    """Cột dao động MẠNH (std lớn, vd. giờ tự học 2-35): lệch +12% so với TB
    (vượt ratio 1.1 cũ) nhưng CHỈ lệch ~0.2 độ lệch chuẩn -> z-score PHẢI xem
    đây là 'typical', không phải điểm mạnh — ratio cũ sẽ sai ở đây.

    Thêm 1 cột thứ 2 CÓ z-score vượt ngưỡng thật (0.8) để logic chính (không
    phải nhánh fallback 'không cột nào vượt ngưỡng') là nhánh thực sự được
    kiểm tra — nếu chỉ có 1 cột, fallback 'không được trả rỗng' sẽ luôn chọn
    nó bất kể z-score bao nhiêu, khiến test không phản ánh đúng điều muốn
    kiểm chứng."""
    group_avg = pd.Series({"so_gio_tu_hoc": 22.4, "ty_le_diem_danh": 0.9})
    overall_avg = pd.Series({"so_gio_tu_hoc": 20.0, "ty_le_diem_danh": 0.82})
    overall_std = pd.Series({"so_gio_tu_hoc": 12.0, "ty_le_diem_danh": 0.10})
    # so_gio_tu_hoc: z=(22.4-20.0)/12.0~=0.2 (duoi nguong); ty_le_diem_danh: z=0.8 (vuot nguong)

    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(
        group_avg, overall_avg, overall_std=overall_std,
    )
    assert "ty_le_diem_danh" in strengths, "z=0.8 phai duoc coi la diem manh."
    assert "so_gio_tu_hoc" not in strengths, (
        "z-score ~0.2 (< 0.5) KHÔNG được coi là điểm mạnh dù vượt ratio ±10% cũ."
    )


def test_low_variance_feature_flagged_strong_by_small_relative_gap():
    """Cột dao động ÍT (std nhỏ, vd. tỷ lệ điểm danh 0.6-1.0): CÙNG mức lệch
    tương đối nhỏ nhưng std nhỏ -> z-score CAO -> phải được coi là điểm mạnh
    thật sự (khác biệt hiếm gặp cho cột này)."""
    group_avg = pd.Series({"ty_le_diem_danh": 0.92})
    overall_avg = pd.Series({"ty_le_diem_danh": 0.85})
    overall_std = pd.Series({"ty_le_diem_danh": 0.05})  # (0.92-0.85)/0.05 = 1.4

    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(
        group_avg, overall_avg, overall_std=overall_std,
    )
    assert "ty_le_diem_danh" in strengths, (
        "z-score 1.4 (> 0.5) PHẢI được coi là điểm mạnh thật sự."
    )


def test_zero_std_column_treated_as_typical_not_crash():
    """Cột hằng số (std=0, vd. mọi sinh viên cùng 1 giá trị) không được chia
    cho 0 gây crash — phải xử lý an toàn thành 'typical' (z=0)."""
    group_avg = pd.Series({"constant_col": 5.0, "varying_col": 8.0})
    overall_avg = pd.Series({"constant_col": 5.0, "varying_col": 6.0})
    overall_std = pd.Series({"constant_col": 0.0, "varying_col": 1.0})

    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(
        group_avg, overall_avg, overall_std=overall_std,
    )
    assert "constant_col" not in strengths and "constant_col" not in weaknesses
    assert "varying_col" in strengths


def test_backward_compatible_without_overall_std_uses_old_ratio_logic():
    """Không truyền overall_std -> PHẢI dùng lại logic ratio cũ y hệt trước
    đây (không phá vỡ lời gọi cũ chưa cập nhật)."""
    group_avg = pd.Series({"diem_tong_ket": 7.5, "gpa_ky_truoc": 7.8})
    overall_avg = pd.Series({"diem_tong_ket": 7.1, "gpa_ky_truoc": 7.15})
    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(group_avg, overall_avg)
    assert strengths[0] == "gpa_ky_truoc"
    assert weaknesses[0] == "diem_tong_ket"


def test_zscore_fallback_finds_relative_strength_when_nothing_crosses_threshold():
    """Giống hành vi fallback cũ (không được trả rỗng): khi không cột nào
    vượt |z| > 0.5, vẫn chọn cột lệch tương đối cao/thấp nhất."""
    group_avg = pd.Series({"a": 5.1, "b": 4.9})
    overall_avg = pd.Series({"a": 5.0, "b": 5.0})
    overall_std = pd.Series({"a": 1.0, "b": 1.0})  # z = +0.1 / -0.1, cả 2 đều dưới 0.5

    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(
        group_avg, overall_avg, overall_std=overall_std,
    )
    assert len(strengths) > 0 and len(weaknesses) > 0
    assert strengths[0] == "a"
    assert weaknesses[0] == "b"
