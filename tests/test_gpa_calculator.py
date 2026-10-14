"""FINAL PRODUCTION GAP CLOSURE — Phần 11: Deterministic GPA Calculator.
Trước khi xây, 34Q matrix (Q15-17) xác nhận NOT_IMPLEMENTED. Test đúng theo
yêu cầu: scale, credits, retake policy (ngoài phạm vi, xem docstring),
rounding, min/max GPA, feasibility."""
from __future__ import annotations

import pytest

from dss.services.gpa_calculator import compute_required_remaining_gpa


def test_matches_hand_computed_example():
    # current_gpa=6.0 (20 tín chỉ đã học), muốn target=7.5 toàn chương trình
    # (tổng 40 tín chỉ, còn 20 tín chỉ) trên thang 10.
    # required = [7.5*40 - 6.0*20] / 20 = [300 - 120] / 20 = 180/20 = 9.0
    result = compute_required_remaining_gpa(
        current_gpa=6.0, credits_done=20, target_gpa=7.5, credits_remaining=20,
    )
    assert result.status == "ok"
    assert result.value == pytest.approx(9.0)
    assert result.rounded_value == pytest.approx(9.0)
    assert result.feasible is True


def test_rounding_to_configured_digits():
    result = compute_required_remaining_gpa(
        current_gpa=6.33, credits_done=17, target_gpa=7.0, credits_remaining=23, round_digits=2,
    )
    assert result.rounded_value == round(result.value, 2)


def test_infeasible_when_required_exceeds_scale_max():
    """feasibility: nếu điểm cần đạt vượt thang điểm tối đa -> INFEASIBLE,
    không trả về một con số vô nghĩa như thể đó là điều làm được."""
    result = compute_required_remaining_gpa(
        current_gpa=3.0, credits_done=100, target_gpa=9.5, credits_remaining=5,
    )
    assert result.status == "INFEASIBLE"
    assert result.feasible is False
    assert result.value > 10.0
    assert any("KHÔNG khả thi" in m for m in result.messages)


def test_goal_already_effectively_achieved_clamped_to_scale_min():
    """Nếu điểm cần đạt < sàn thang điểm (mục tiêu quá dễ so với điểm đã
    có) -> vẫn "ok", giá trị hiển thị kẹp về sàn, không phải số âm."""
    result = compute_required_remaining_gpa(
        current_gpa=9.8, credits_done=100, target_gpa=5.0, credits_remaining=10,
    )
    assert result.status == "ok"
    assert result.feasible is True
    assert result.rounded_value >= 0.0


def test_invalid_scale_rejected():
    result = compute_required_remaining_gpa(
        current_gpa=5.0, credits_done=10, target_gpa=6.0, credits_remaining=10,
        scale_min=10.0, scale_max=0.0,
    )
    assert result.status == "INVALID_INPUT"
    assert result.value is None


def test_invalid_credits_rejected():
    result = compute_required_remaining_gpa(
        current_gpa=5.0, credits_done=10, target_gpa=6.0, credits_remaining=0,
    )
    assert result.status == "INVALID_INPUT"
    assert "tín chỉ" in result.messages[0]


def test_current_gpa_outside_scale_rejected():
    result = compute_required_remaining_gpa(
        current_gpa=15.0, credits_done=10, target_gpa=6.0, credits_remaining=10,
    )
    assert result.status == "INVALID_INPUT"


def test_target_gpa_outside_scale_rejected():
    result = compute_required_remaining_gpa(
        current_gpa=5.0, credits_done=10, target_gpa=-1.0, credits_remaining=10,
    )
    assert result.status == "INVALID_INPUT"


def test_result_never_raises_for_business_edge_cases():
    """LLM/UI gọi hàm này không bao giờ được nhận exception cho các trường
    hợp nghiệp vụ (chỉ INVALID_INPUT/INFEASIBLE có cấu trúc) — chỉ raise
    thật với lỗi lập trình (vd. truyền sai kiểu dữ liệu)."""
    edge_cases = [
        dict(current_gpa=0.0, credits_done=0, target_gpa=10.0, credits_remaining=1),
        dict(current_gpa=10.0, credits_done=200, target_gpa=10.0, credits_remaining=1),
    ]
    for kwargs in edge_cases:
        result = compute_required_remaining_gpa(**kwargs)
        assert result.status in ("ok", "INFEASIBLE", "INVALID_INPUT")


def test_inputs_echoed_for_audit_traceability():
    result = compute_required_remaining_gpa(
        current_gpa=6.0, credits_done=20, target_gpa=7.5, credits_remaining=20,
    )
    assert result.inputs_echo["current_gpa"] == 6.0
    assert result.inputs_echo["credits_remaining"] == 20
