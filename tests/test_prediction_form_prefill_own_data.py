"""E-6: form dự đoán (Nhập tay) trước đây LUÔN điền sẵn ô số bằng trung bình
lớp (df[col].mean()), kể cả cho sinh viên đã đăng nhập — nếu họ bấm gửi mà
không sửa gì, sẽ vô tình nhận "dự đoán" cho một sinh viên TRUNG BÌNH, không
phải của chính họ. Với sinh viên có dòng dữ liệu của chính mình trong dataset,
phải điền sẵn bằng dữ liệu CỦA HỌ, không phải trung bình lớp."""

from __future__ import annotations

import inspect

from dss.tabs import ml_hub


def test_student_form_prefers_own_student_data_over_class_mean():
    source = inspect.getsource(ml_hub._personal_prediction_student_form)
    assert "_own_student_row" in source, (
        "Form dự đoán chưa tra dữ liệu của chính sinh viên đã đăng nhập — vẫn "
        "chỉ điền sẵn bằng trung bình lớp cho mọi trường hợp."
    )
    assert "current_student_id" in source


def test_student_form_discloses_when_using_class_average_fallback():
    source = inspect.getsource(ml_hub._personal_prediction_student_form)
    assert "CHƯA có dữ liệu của bạn" in source, (
        "Form dự đoán không ghi rõ cho sinh viên biết khi đang dùng giá trị "
        "trung bình lớp (chưa tìm được dữ liệu của chính họ)."
    )
