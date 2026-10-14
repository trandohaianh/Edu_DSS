"""Validator — OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE Phần 13.

"Production-quality minimum" theo đúng mô hình yêu cầu — Validator là tầng
kiểm chứng CUỐI CÙNG trước khi trả kết quả cho người dùng, đứng SAU
Calculator/Rule Engine/Regulation Resolver, KHÔNG PHẢI để tự quyết định lại
mà để XÁC NHẬN kết quả từ các tầng đó nhất quán, và — quan trọng nhất — để
PHÁT HIỆN khi LLM "nói" một con số/kết luận KHÁC với kết quả xác định đã có
(Calculator/Rule Engine) và CHẶN nó lại thay vì để lộ ra cho người dùng.

Nguyên tắc: FAIL PHẢI dẫn tới Safe Fallback (`decide_safe_fallback_message()`),
KHÔNG BAO GIỜ để câu trả lời đã FAIL kiểm chứng hiển thị như một câu trả lời
thành công/đáng tin cậy cho người dùng.

QUAN TRỌNG (trung thực về phạm vi): phiên này CHỈ build phần lõi kiểm
chứng thuần (không I/O) cho các loại dữ liệu đã có tầng nguồn thật đứng sau
(GPA/Rule Engine/Regulation Resolver) — CHƯA build kiểm chứng
authorization/tenant/course_id/citation/RAG evidence đầy đủ (cần dữ liệu
thật từ các tầng chưa tồn tại trong phiên này, xem AI_ROUTING_MATRIX.md).
Không tự nhận đã "hoàn thành toàn bộ Validator" — chỉ phần đã build thật.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_PARTIAL = "PARTIAL"
STATUS_NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"

_VALID_STATUSES = {STATUS_PASS, STATUS_FAIL, STATUS_PARTIAL, STATUS_NEEDS_HUMAN_REVIEW}

_VALID_RULE_ENGINE_STATUSES = {"ALLOW", "DENY", "WARNING", "INSUFFICIENT_DATA"}
_VALID_REGULATION_STATUSES = {"ok", "NOT_FOUND", "EXPIRED_ONLY", "FUTURE_ONLY", "PENDING_ONLY"}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationResult:
    status: str
    checks: List[CheckResult] = field(default_factory=list)
    reason: str = ""

    def __post_init__(self):
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"ValidationResult.status không hợp lệ: {self.status!r}")


def _result(status: str, checks: List[CheckResult], reason: str) -> ValidationResult:
    return ValidationResult(status=status, checks=checks, reason=reason)


def validate_gpa_value(
    value: float, *, scale_min: float = 0.0, scale_max: float = 10.0,
) -> ValidationResult:
    """Kiểm chứng 1 giá trị GPA nằm trong thang điểm hợp lệ TRƯỚC KHI hiển
    thị cho người dùng — chặn số liệu vô lý (vd. GPA âm, GPA > thang điểm
    do lỗi tính toán/parse) lọt ra ngoài như một kết quả đáng tin."""
    checks = [CheckResult(
        name="gpa_within_scale", passed=(scale_min <= value <= scale_max),
        detail=f"value={value}, scale=[{scale_min}, {scale_max}]",
    )]
    if not checks[0].passed:
        return _result(STATUS_FAIL, checks, f"GPA {value} nằm ngoài thang điểm hợp lệ [{scale_min}, {scale_max}].")
    return _result(STATUS_PASS, checks, "GPA hợp lệ.")


def validate_rule_engine_result(rule_result: Any) -> ValidationResult:
    """Kiểm chứng kết quả Rule Engine (`rule_engine.RuleEvaluationResult`)
    tự nhất quán — status hợp lệ, và DENY/WARNING phải kèm lý do + evidence
    (không được là kết luận trống không có căn cứ)."""
    status = getattr(rule_result, "status", None)
    checks = [CheckResult(
        name="rule_status_is_valid_enum", passed=(status in _VALID_RULE_ENGINE_STATUSES),
        detail=f"status={status!r}",
    )]
    if not checks[0].passed:
        return _result(STATUS_FAIL, checks, f"Rule Engine trả về status không hợp lệ: {status!r}.")

    reason = getattr(rule_result, "reason", "") or ""
    has_reason = bool(reason.strip())
    checks.append(CheckResult(name="has_non_empty_reason", passed=has_reason, detail=f"reason={reason!r}"))
    if status in ("DENY", "WARNING") and not has_reason:
        return _result(STATUS_FAIL, checks, "DENY/WARNING phải kèm lý do cụ thể — không có căn cứ.")

    return _result(STATUS_PASS, checks, "Kết quả Rule Engine nhất quán.")


def validate_regulation_resolution(resolution: Any) -> ValidationResult:
    """Kiểm chứng kết quả Regulation Resolver
    (`regulation_resolver.RegulationResolution`) tự nhất quán — status hợp
    lệ, và status="ok" PHẢI có kèm `regulation` thật (không được "ok" mà
    regulation=None, sẽ khiến tầng gọi hiển thị dữ liệu rỗng như thành
    công)."""
    status = getattr(resolution, "status", None)
    checks = [CheckResult(
        name="regulation_status_is_valid_enum", passed=(status in _VALID_REGULATION_STATUSES),
        detail=f"status={status!r}",
    )]
    if not checks[0].passed:
        return _result(STATUS_FAIL, checks, f"Regulation Resolver trả về status không hợp lệ: {status!r}.")

    regulation = getattr(resolution, "regulation", None)
    ok_has_regulation = (status != "ok") or (regulation is not None)
    checks.append(CheckResult(name="ok_status_has_regulation_object", passed=ok_has_regulation,
                              detail=f"status={status!r}, regulation={regulation!r}"))
    if not ok_has_regulation:
        return _result(STATUS_FAIL, checks, "status='ok' nhưng không có đối tượng quy chế kèm theo — dữ liệu không nhất quán.")

    return _result(STATUS_PASS, checks, "Kết quả Regulation Resolver nhất quán.")


def validate_llm_numeric_claim(
    llm_claimed_value: Optional[float], authoritative_value: float, *, tolerance: float = 0.01,
) -> ValidationResult:
    """HÀM CANH GÁC QUAN TRỌNG (Phần 1h/13): "LLM output must never override
    Calculator result". Nếu LLM tự "nói" ra 1 con số (vd. trong văn bản giải
    thích tự do) KHÁC với con số THẬT do Calculator/Rule Engine tính ra
    (`authoritative_value`) vượt quá dung sai `tolerance`, PHẢI FAIL — nơi
    gọi phải kích hoạt Safe Fallback (`decide_safe_fallback_message()`),
    TUYỆT ĐỐI không hiển thị con số sai của LLM như một kết quả đáng tin."""
    if llm_claimed_value is None:
        return _result(
            STATUS_PASS, [CheckResult(name="llm_made_no_numeric_claim", passed=True, detail="llm_claimed_value=None")],
            "LLM không tự nêu số liệu nào — không có gì để đối chiếu.",
        )

    diff = abs(llm_claimed_value - authoritative_value)
    checks = [CheckResult(
        name="llm_claim_matches_authoritative_value_within_tolerance",
        passed=(diff <= tolerance),
        detail=f"llm_claimed={llm_claimed_value}, authoritative={authoritative_value}, diff={diff}, tolerance={tolerance}",
    )]
    if not checks[0].passed:
        return _result(
            STATUS_FAIL, checks,
            f"LLM nêu số liệu {llm_claimed_value} KHÁC với kết quả xác định từ Calculator/Rule Engine "
            f"({authoritative_value}, chênh lệch {diff} > dung sai {tolerance}) — CHẶN, không hiển thị số của LLM.",
        )
    return _result(STATUS_PASS, checks, "Số liệu LLM nêu khớp với kết quả xác định.")


def decide_safe_fallback_message(validation_result: ValidationResult) -> str:
    """Thông điệp Safe Fallback khi `validation_result.status != PASS` —
    KHÔNG lộ chi tiết kỹ thuật (stack trace/nội bộ), chỉ nêu lý do nghiệp vụ
    ngắn gọn + hướng xử lý, đúng yêu cầu Phần 14 (AI Error UX)."""
    if validation_result.status == STATUS_PASS:
        raise ValueError("decide_safe_fallback_message() chỉ được gọi khi validation KHÔNG PASS.")

    if validation_result.status == STATUS_NEEDS_HUMAN_REVIEW:
        return (
            "Yêu cầu này cần được xác nhận thủ công trước khi trả lời chính xác. "
            "Vui lòng liên hệ Cố vấn học tập/Phòng Đào tạo."
        )
    return (
        "Hệ thống phát hiện kết quả chưa đủ tin cậy để hiển thị và đã CHẶN LẠI thay vì đưa ra câu trả lời "
        "có thể sai. Vui lòng thử lại hoặc liên hệ Cố vấn học tập/Phòng Đào tạo để được hỗ trợ."
    )
