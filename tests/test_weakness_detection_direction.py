"""A-4: luật phát hiện "điểm yếu" cũ ("col_val < avg_val * 0.9") áp dụng cho
MỌI cột số, kể cả cột mà giá trị THẤP mới là TỐT (vd. ngay_hoat_dong_gan_nhat —
số ngày từ lần hoạt động gần nhất, càng thấp càng tốt) và bí danh/target
(final_score). Sinh viên hoạt động TÍCH CỰC hơn trung bình lớp (ít ngày hơn) bị
gắn nhầm thành "điểm yếu"."""
from __future__ import annotations

import inspect

from dss.core.data_helpers import is_weakness
from dss.tabs import ai_advisor


def test_lower_is_better_column_flags_high_value_not_low_value():
    # Sinh viên hoạt động TÍCH CỰC hơn TB lớp (2 ngày < TB 5 ngày) -> KHÔNG PHẢI điểm yếu.
    assert is_weakness("ngay_hoat_dong_gan_nhat", col_val=2.0, avg_val=5.0) is False
    # Sinh viên LÂU không hoạt động hơn TB lớp (10 ngày > TB 5 ngày, +100%) -> ĐÚNG là điểm yếu.
    assert is_weakness("ngay_hoat_dong_gan_nhat", col_val=10.0, avg_val=5.0) is True


def test_higher_is_better_column_unchanged_from_old_threshold():
    assert is_weakness("diem_giua_ky", col_val=5.0, avg_val=7.0) is True  # ~29% dưới TB
    assert is_weakness("diem_giua_ky", col_val=6.8, avg_val=7.0) is False  # trong ngưỡng


def test_undeclared_column_never_flagged_as_weakness():
    # Bí danh/target (final_score) hoặc cột chưa khai báo chiều -> không được dùng
    # làm căn cứ điểm yếu, dù giá trị lệch xa trung bình.
    assert is_weakness("final_score", col_val=2.0, avg_val=9.0) is False
    assert is_weakness("some_unknown_column", col_val=2.0, avg_val=9.0) is False


def test_ai_advisor_uses_is_weakness_not_raw_threshold():
    source = inspect.getsource(ai_advisor)
    assert "if col_val < avg_val * 0.9:" not in source, (
        "ai_advisor.py vẫn dùng luật cũ áp cho MỌI cột số, không phân biệt "
        "chiều tốt/xấu hay bí danh/target."
    )
    assert "is_weakness(col, col_val, avg_val)" in source
