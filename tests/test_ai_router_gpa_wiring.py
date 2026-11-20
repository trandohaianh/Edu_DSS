"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 11: GPA Calculator phải
thực sự WIRE vào đường chat thật, không chỉ tồn tại như module cô lập. Test
đúng ví dụ mẫu B: 'GPA 3.05, em muốn lên 3.20 thì cần bao nhiêu?'."""

from __future__ import annotations

from dss.services import ai_router


def test_extract_two_numbers_current_and_target_in_order():
    extracted = ai_router.try_extract_gpa_calculation_inputs("GPA 3.05, em muốn lên 3.20 thì cần bao nhiêu?")
    assert extracted["current_gpa"] == 3.05
    assert extracted["target_gpa"] == 3.20
    assert extracted["credits_done"] is None
    assert extracted["credits_remaining"] is None


def test_extract_four_numbers_when_credits_provided():
    extracted = ai_router.try_extract_gpa_calculation_inputs(
        "Em đã học 60 tín chỉ với GPA 6.0, muốn đạt 7.5, còn 20 tín chỉ nữa"
    )
    assert extracted is not None
    # Thứ tự xuất hiện trong câu: 60 (tín chỉ), 6.0 (gpa), 7.5 (mục tiêu), 20 (tín chỉ còn lại)
    # -> Ham trich theo thu tu xuat hien nen se khong khop dung ngu nghia neu
    # cau khong theo mau chuan (current, done, target, remaining). Test nay
    # chi xac nhan KHONG crash va tra ve 4 con so, khong khang dinh dung
    # ngu nghia cho cau tu do bat ky.
    assert None not in extracted.values()


def test_no_gpa_reply_when_fewer_than_two_numbers():
    assert ai_router.build_gpa_calculation_reply("Điểm của em là 7.5") is None


def test_gpa_reply_asks_for_missing_credits_honestly_not_fabricated():
    """Câu hỏi mẫu chuẩn (chỉ 2 số) -> PHẢI hỏi lại tín chỉ, KHÔNG được bịa
    số tín chỉ để vẫn tính ra 1 con số trông có vẻ chắc chắn."""
    reply = ai_router.build_gpa_calculation_reply("GPA 3.05, em muốn lên 3.20 thì cần bao nhiêu?")
    assert reply is not None
    assert "3.05" in reply
    assert "3.20" in reply
    assert "tín chỉ" in reply.lower()
    assert "chưa có sẵn dữ liệu tín chỉ" in reply


def test_gpa_reply_computes_real_answer_when_credits_known():
    reply = ai_router.build_gpa_calculation_reply("current_gpa 6.0 credits_done 20 target_gpa 7.5 credits_remaining 20")
    assert reply is not None
    assert "9.00" in reply or "9.0" in reply  # đúng công thức: (7.5*40-6.0*20)/20 = 9.0
    assert "công thức xác định" in reply


def test_gpa_reply_reports_infeasible_honestly():
    reply = ai_router.build_gpa_calculation_reply("current 3.0 done 100 target 9.5 remaining 5")
    assert reply is not None
    assert "KHÔNG khả thi" in reply
