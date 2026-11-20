"""FINAL GAP CLOSURE — Câu 15: DIRECT_DATA_LOOKUP phải THẬT SỰ trả lời từ dữ
liệu có sẵn, không rơi xuống LLM (trước đợt này: router phân loại đúng
nhưng không có reply-builder, nên hành vi thật vẫn gọi LLM — xem
docs/ai/AI_ROUTING_MATRIX.md "Gaps found")."""

from __future__ import annotations

from dss.services import ai_router


def test_attendance_question_reads_own_attendance_directly():
    student_row = {"ty_le_diem_danh": 0.87, "diem_ky_nay": 8.2}
    reply = ai_router.build_direct_data_lookup_reply("Điểm danh của em là bao nhiêu?", student_row=student_row)
    assert reply is not None
    assert "87.0%" in reply
    assert "không qua AI suy luận" in reply


def test_score_question_reads_current_term_score_not_future_target():
    """Câu hỏi 'điểm hiện tại' PHẢI dùng diem_ky_nay (hiện tại), TUYỆT ĐỐI
    KHÔNG dùng diem_ky_sau (target/nhãn tương lai — xem K-3)."""
    student_row = {"diem_ky_nay": 7.5, "diem_ky_sau": 9.9}
    reply = ai_router.build_direct_data_lookup_reply("Điểm hiện tại của em là bao nhiêu?", student_row=student_row)
    assert reply is not None
    assert "7.50" in reply
    assert "9.9" not in reply, "KHÔNG được lộ diem_ky_sau (target tương lai) trong câu trả lời 'điểm hiện tại'."


def test_no_student_row_returns_none_not_fabricated():
    assert ai_router.build_direct_data_lookup_reply("Điểm hiện tại của em là bao nhiêu?", student_row=None) is None


def test_unrecognized_field_returns_none():
    assert ai_router.build_direct_data_lookup_reply("Điểm hiện tại của em là bao nhiêu?", student_row={}) is None


def test_direct_data_lookup_is_now_wired_to_real_behavior():
    d = ai_router.classify("Điểm hiện tại của em là bao nhiêu?")
    assert d.intent == ai_router.INTENT_DIRECT_DATA_LOOKUP
    assert d.wired_to_real_behavior is True, (
        "DIRECT_DATA_LOOKUP đã có build_direct_data_lookup_reply() thật đứng sau — phải là True."
    )


def test_function_never_takes_student_id_from_question_text():
    """Đảm bảo an toàn cross-student bằng kiểm tra chữ ký hàm: không có tham
    số nào cho phép chỉ định student_id khác từ bên ngoài student_row đã
    resolve sẵn — chữ ký hàm CHỈ nhận `question` và `student_row`."""
    import inspect

    sig = inspect.signature(ai_router.build_direct_data_lookup_reply)
    assert set(sig.parameters.keys()) == {"question", "student_row"}
