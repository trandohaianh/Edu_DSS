"""Student Product Acceptance audit (2026-09) — FUNC-ML-002: the "Dự đoán —
Từ file" prediction sub-tab has no file uploader at all (it shows the
prediction for a row already in the loaded dataset); worse, for Sinh viên it
pointed to 2 tabs ("Huấn luyện mô hình", "Kho dữ liệu") that do not exist for
that role at all (main.py sets tab_train_ml=None for Sinh viên, and Sinh
viên has no "Kho dữ liệu" sidebar entry), leaving the student with an
unfollowable instruction whenever no target/model was configured yet."""

from __future__ import annotations

import inspect


def test_main_py_no_longer_uses_misleading_tu_file_label():
    from pathlib import Path

    main_py = Path(__file__).resolve().parent.parent / "dss" / "main.py"
    source = main_py.read_text(encoding="utf-8")
    assert "Dự đoán — Từ file" not in source
    assert "Dự đoán — Dữ liệu đã có" in source


def test_file_prediction_tab_role_branches_target_missing_message_for_student():
    from dss.tabs import ml_hub

    source = inspect.getsource(ml_hub.file_prediction_tab)
    assert 'role == "Sinh viên"' in source
    idx_role_check = source.find('role == "Sinh viên"')
    # Nhánh Sinh viên (trước else) không được nhắc tới 2 tab Sinh viên
    # không thể vào được.
    idx_else = source.find("else:", idx_role_check)
    student_branch = source[idx_role_check:idx_else]
    assert "Huấn luyện mô hình" not in student_branch
    assert "Kho dữ liệu" not in student_branch


def test_file_prediction_tab_header_no_longer_implies_file_upload():
    from dss.tabs import ml_hub

    source = inspect.getsource(ml_hub.file_prediction_tab)
    assert '"Dự đoán — Từ file"' not in source
    assert "Dự đoán — Dữ liệu đã có" in source


def test_personal_prediction_student_form_no_target_message_is_role_aware():
    """Cùng lớp lỗi ở form nhập tay (_personal_prediction_student_form) —
    thông báo 'chưa có Target' trước đây cũng chỉ Sinh viên tới tab không
    tồn tại."""
    from dss.tabs import ml_hub

    source = inspect.getsource(ml_hub._personal_prediction_student_form)
    idx_target_check = source.find("if not target_col:")
    assert idx_target_check != -1
    window = source[idx_target_check : idx_target_check + 600]
    assert 'role == "Sinh viên"' in window
