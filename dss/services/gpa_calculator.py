"""Deterministic GPA Calculator — FINAL PRODUCTION GAP CLOSURE Phần 11.

Xác nhận trước khi xây: `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (Q15-Q17)
kết luận NOT_IMPLEMENTED — hệ thống có DỰ ĐOÁN ML (K-3, đã sửa đợt trước)
nhưng KHÔNG có phép TÍNH CHÍNH SÁCH xác định kiểu "cần đạt bao nhiêu điểm
kỳ tới để đủ điều kiện tốt nghiệp loại X" — câu hỏi này hiện do LLM tự do
trả lời trong prompt (không đáng tin cậy cho một phép tính số học).

Nguyên tắc: LLM KHÔNG được tự tính GPA/tín chỉ — module này là NGUỒN DUY
NHẤT tính các con số đó; LLM chỉ diễn giải kết quả CÓ CẤU TRÚC trả về từ
đây (`CalculatorResult`), không được tự suy ra số liệu khác.

Công thức (đúng yêu cầu):
    required_remaining_gpa =
        [ target_gpa * (credits_done + credits_remaining)
          - current_gpa * credits_done ]
        / credits_remaining
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CalculatorResult:
    """Kết quả CÓ CẤU TRÚC — LUÔN trả về (không raise cho lỗi input nghiệp
    vụ thông thường), để nơi gọi (Validator/UI/LLM diễn giải) có thể phân
    biệt rõ giữa "tính được" và "không khả thi"/"input không hợp lệ"."""

    status: str  # "ok" | "INFEASIBLE" | "INVALID_INPUT"
    value: Optional[float]
    rounded_value: Optional[float]
    feasible: bool
    messages: List[str] = field(default_factory=list)
    inputs_echo: dict = field(default_factory=dict)


def compute_required_remaining_gpa(
    *,
    current_gpa: float,
    credits_done: float,
    target_gpa: float,
    credits_remaining: float,
    scale_min: float = 0.0,
    scale_max: float = 10.0,
    round_digits: int = 2,
) -> CalculatorResult:
    """Tính điểm trung bình CẦN ĐẠT ở phần tín chỉ còn lại để đạt `target_gpa`
    tính trên TOÀN BỘ chương trình (đã học + còn lại).

    Validate (đúng yêu cầu): thang điểm, tín chỉ, làm tròn, GPA tối thiểu/
    tối đa, khả thi (feasibility). KHÔNG validate "retake policy" cụ thể ở
    đây (chính sách học lại khác nhau theo từng trường/quy chế — thuộc
    phạm vi Rule Engine/Regulation Resolver, không phải phép tính số học
    thuần túy này).
    """
    inputs_echo = {
        "current_gpa": current_gpa,
        "credits_done": credits_done,
        "target_gpa": target_gpa,
        "credits_remaining": credits_remaining,
        "scale_min": scale_min,
        "scale_max": scale_max,
    }
    messages: List[str] = []

    # --- Validate input (scale/credits) ---
    if scale_max <= scale_min:
        return CalculatorResult(
            "INVALID_INPUT", None, None, False, ["Thang điểm không hợp lệ (scale_max <= scale_min)."], inputs_echo
        )
    if credits_done < 0 or credits_remaining <= 0:
        return CalculatorResult(
            "INVALID_INPUT",
            None,
            None,
            False,
            ["Số tín chỉ không hợp lệ: credits_done phải >= 0, credits_remaining phải > 0."],
            inputs_echo,
        )
    if not (scale_min <= current_gpa <= scale_max):
        return CalculatorResult(
            "INVALID_INPUT",
            None,
            None,
            False,
            [f"current_gpa={current_gpa} nằm ngoài thang điểm [{scale_min}, {scale_max}]."],
            inputs_echo,
        )
    if not (scale_min <= target_gpa <= scale_max):
        return CalculatorResult(
            "INVALID_INPUT",
            None,
            None,
            False,
            [f"target_gpa={target_gpa} nằm ngoài thang điểm [{scale_min}, {scale_max}]."],
            inputs_echo,
        )

    # --- Công thức chính (đúng nguyên văn yêu cầu) ---
    total_credits = credits_done + credits_remaining
    raw_value = (target_gpa * total_credits - current_gpa * credits_done) / credits_remaining
    rounded = round(raw_value, round_digits)

    # --- Feasibility: điểm cần đạt phải nằm TRONG thang điểm hợp lệ ---
    if raw_value > scale_max:
        messages.append(
            f"KHÔNG khả thi: cần trung bình {rounded}/{scale_max} cho phần tín chỉ còn lại — "
            f"vượt quá thang điểm tối đa ({scale_max}). Mục tiêu target_gpa={target_gpa} không thể "
            f"đạt được chỉ với {credits_remaining} tín chỉ còn lại."
        )
        return CalculatorResult("INFEASIBLE", raw_value, rounded, False, messages, inputs_echo)
    if raw_value < scale_min:
        messages.append(
            f"Mục tiêu ĐÃ ĐẠT hoặc vượt: chỉ cần trung bình {rounded}/{scale_max} (thấp hơn sàn "
            f"{scale_min}) cho phần còn lại — với điểm đã học hiện tại, mục tiêu gần như chắc chắn đạt "
            f"được kể cả điểm phần còn lại ở mức tối thiểu."
        )
        # Không INFEASIBLE — đây là tin tốt (ngưỡng cần đạt thấp hơn sàn thang điểm),
        # trả "ok" với giá trị kẹp về scale_min để không hiển thị số âm/vô nghĩa.
        return CalculatorResult("ok", raw_value, max(rounded, scale_min), True, messages, inputs_echo)

    messages.append(f"Cần đạt trung bình {rounded}/{scale_max} cho {credits_remaining} tín chỉ còn lại.")
    return CalculatorResult("ok", raw_value, rounded, True, messages, inputs_echo)
