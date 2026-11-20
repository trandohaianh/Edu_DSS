"""Rule Engine — OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE Phần 12.

34Q matrix + `docs/ai/AI_ROUTING_MATRIX.md` xác nhận ACADEMIC_RULE_CHECK trước đợt
này CHỈ được PHÂN LOẠI (router) chứ CHƯA có Rule Engine thật đứng sau —
"production-quality minimum" theo đúng mô hình yêu cầu, cùng kiến trúc với
`regulation_resolver.py` (Phần 9): hàm THUẦN, không I/O, nhận input đã có
sẵn (do tầng gọi cung cấp), tenant-scoped/versioned/effective-dated qua
`AcademicRule`, LUÔN trả `RuleEvaluationResult` (không raise cho trường hợp
nghiệp vụ bình thường), auditable đầy đủ (rule_id/regulation_id/version/
reason/evidence/inputs).

NGUYÊN TẮC TUYỆT ĐỐI (Phần 12, câu hỏi chấp nhận bắt buộc): Rule Engine là
NƠI DUY NHẤT quyết định ALLOW/DENY/WARNING cho các câu hỏi điều kiện học vụ
xác định (đăng ký môn/giới hạn tín chỉ/cảnh báo học vụ/đủ điều kiện khóa
luận/đủ điều kiện tốt nghiệp). LLM/Agent KHÔNG BAO GIỜ được tự quyết định
hoặc GHI ĐÈ kết quả này — nếu Rule Engine trả DENY, câu trả lời cuối cùng
hiển thị cho người dùng KHÔNG ĐƯỢC trở thành ALLOW dù LLM có "nói" ALLOW.
Xem `decide_final_status()` — hàm canh gác duy nhất cho nguyên tắc này.

Backend lưu trữ thật (bảng `academic_rules` + migration Alembic) LÀ CÔNG
VIỆC CHƯA LÀM trong đợt này (BLOCKED_BY_RUNNING_SIMULATION, cùng lý do với
regulation_store.py) — interface `AcademicRule` được thiết kế độc lập với
backend lưu trữ để dễ thay thế sau."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

STATUS_ALLOW = "ALLOW"
STATUS_DENY = "DENY"
STATUS_WARNING = "WARNING"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

RULE_TYPE_CREDIT_LIMIT = "COURSE_REGISTRATION_CREDIT_LIMIT"
RULE_TYPE_ACADEMIC_WARNING = "ACADEMIC_WARNING"
RULE_TYPE_THESIS_ELIGIBILITY = "THESIS_ELIGIBILITY"
RULE_TYPE_GRADUATION_ELIGIBILITY = "GRADUATION_ELIGIBILITY"

_REG_STATUS_APPROVED = "APPROVED"


@dataclass
class AcademicRule:
    """1 quy tắc học vụ — tenant-scoped/versioned/effective-dated, CÙNG MẪU
    `RegulationVersion` (regulation_resolver.py) — không hardcode trong UI,
    nơi gọi phải tự cung cấp rule đã resolve đúng phiên bản (thường từ
    `regulation_resolver.resolve_regulation().regulation.rules[...]`)."""

    rule_id: str
    regulation_id: str
    regulation_version: int
    organization_id: str
    rule_type: str
    effective_from: str
    effective_to: Optional[str]
    status: str  # dùng chung _REG_STATUS_* với regulation_resolver (APPROVED/DRAFT/RETIRED...)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleEvaluationResult:
    """Kết quả evaluate — LUÔN trả về (không raise cho nghiệp vụ bình
    thường), auditable đầy đủ để ghi audit log (Phần 26)."""

    status: str  # ALLOW | DENY | WARNING | INSUFFICIENT_DATA
    rule_id: Optional[str]
    regulation_id: Optional[str]
    regulation_version: Optional[int]
    reason: str
    evidence: Dict[str, Any]
    inputs_echo: Dict[str, Any]


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _rule_not_in_effect_result(rule: AcademicRule, inputs_echo: Dict[str, Any], at_date: date) -> Optional[RuleEvaluationResult]:
    """Kiểm tra chung: rule phải APPROVED và đang trong hiệu lực tại
    `at_date` — nếu không, trả INSUFFICIENT_DATA (không được coi là DENY hay
    ALLOW ngầm định) kèm lý do cụ thể."""
    if rule.status != _REG_STATUS_APPROVED:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Quy tắc '{rule.rule_id}' chưa ở trạng thái APPROVED (hiện: {rule.status}).",
            evidence={"rule_status": rule.status}, inputs_echo=inputs_echo,
        )
    ef = _parse_date(rule.effective_from)
    et = _parse_date(rule.effective_to)
    if ef is not None and at_date < ef:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Quy tắc '{rule.rule_id}' chưa có hiệu lực (từ {rule.effective_from}).",
            evidence={"effective_from": rule.effective_from}, inputs_echo=inputs_echo,
        )
    if et is not None and at_date > et:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Quy tắc '{rule.rule_id}' đã hết hiệu lực (đến {rule.effective_to}).",
            evidence={"effective_to": rule.effective_to}, inputs_echo=inputs_echo,
        )
    return None


def evaluate_credit_limit(
    rule: AcademicRule, *, requested_credits: float, at_date: Optional[str] = None,
) -> RuleEvaluationResult:
    """RULE_TYPE_CREDIT_LIMIT — `rule.params["max_credits"]`."""
    inputs_echo = {"requested_credits": requested_credits}
    resolve_date = _parse_date(at_date) or datetime.now(timezone.utc).date()
    not_in_effect = _rule_not_in_effect_result(rule, inputs_echo, resolve_date)
    if not_in_effect is not None:
        return not_in_effect

    max_credits = rule.params.get("max_credits")
    if max_credits is None:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason="Quy tắc thiếu tham số 'max_credits' — không thể đánh giá.",
            evidence={}, inputs_echo=inputs_echo,
        )
    if requested_credits > max_credits:
        return RuleEvaluationResult(
            status=STATUS_DENY, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Số tín chỉ đăng ký ({requested_credits}) vượt giới hạn tối đa ({max_credits}).",
            evidence={"max_credits": max_credits}, inputs_echo=inputs_echo,
        )
    return RuleEvaluationResult(
        status=STATUS_ALLOW, rule_id=rule.rule_id,
        regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
        reason=f"Số tín chỉ đăng ký ({requested_credits}) trong giới hạn cho phép ({max_credits}).",
        evidence={"max_credits": max_credits}, inputs_echo=inputs_echo,
    )


def evaluate_academic_warning(
    rule: AcademicRule, *, gpa: float, at_date: Optional[str] = None,
) -> RuleEvaluationResult:
    """RULE_TYPE_ACADEMIC_WARNING — `rule.params["warning_gpa_threshold"]`."""
    inputs_echo = {"gpa": gpa}
    resolve_date = _parse_date(at_date) or datetime.now(timezone.utc).date()
    not_in_effect = _rule_not_in_effect_result(rule, inputs_echo, resolve_date)
    if not_in_effect is not None:
        return not_in_effect

    threshold = rule.params.get("warning_gpa_threshold")
    if threshold is None:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason="Quy tắc thiếu tham số 'warning_gpa_threshold' — không thể đánh giá.",
            evidence={}, inputs_echo=inputs_echo,
        )
    if gpa < threshold:
        return RuleEvaluationResult(
            status=STATUS_WARNING, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"GPA hiện tại ({gpa}) dưới ngưỡng cảnh báo học vụ ({threshold}).",
            evidence={"warning_gpa_threshold": threshold}, inputs_echo=inputs_echo,
        )
    return RuleEvaluationResult(
        status=STATUS_ALLOW, rule_id=rule.rule_id,
        regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
        reason=f"GPA hiện tại ({gpa}) trên ngưỡng cảnh báo học vụ ({threshold}) — không bị cảnh báo.",
        evidence={"warning_gpa_threshold": threshold}, inputs_echo=inputs_echo,
    )


def evaluate_thesis_eligibility(
    rule: AcademicRule, *, gpa: float, credits_completed: float, at_date: Optional[str] = None,
) -> RuleEvaluationResult:
    """RULE_TYPE_THESIS_ELIGIBILITY — `rule.params["min_gpa"]` +
    `rule.params["min_credits_completed"]` (CẢ HAI đều phải đạt)."""
    inputs_echo = {"gpa": gpa, "credits_completed": credits_completed}
    resolve_date = _parse_date(at_date) or datetime.now(timezone.utc).date()
    not_in_effect = _rule_not_in_effect_result(rule, inputs_echo, resolve_date)
    if not_in_effect is not None:
        return not_in_effect

    min_gpa = rule.params.get("min_gpa")
    min_credits = rule.params.get("min_credits_completed")
    if min_gpa is None or min_credits is None:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason="Quy tắc thiếu tham số 'min_gpa'/'min_credits_completed' — không thể đánh giá.",
            evidence={}, inputs_echo=inputs_echo,
        )
    evidence = {"min_gpa": min_gpa, "min_credits_completed": min_credits}
    if gpa < min_gpa:
        return RuleEvaluationResult(
            status=STATUS_DENY, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"GPA hiện tại ({gpa}) chưa đạt tối thiểu ({min_gpa}) để làm khóa luận.",
            evidence=evidence, inputs_echo=inputs_echo,
        )
    if credits_completed < min_credits:
        return RuleEvaluationResult(
            status=STATUS_DENY, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Số tín chỉ đã hoàn thành ({credits_completed}) chưa đạt tối thiểu ({min_credits}) để làm khóa luận.",
            evidence=evidence, inputs_echo=inputs_echo,
        )
    return RuleEvaluationResult(
        status=STATUS_ALLOW, rule_id=rule.rule_id,
        regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
        reason="Đủ điều kiện GPA và số tín chỉ đã hoàn thành để làm khóa luận.",
        evidence=evidence, inputs_echo=inputs_echo,
    )


def evaluate_graduation_eligibility(
    rule: AcademicRule, *, gpa: float, credits_completed: float, credits_required: float,
    at_date: Optional[str] = None,
) -> RuleEvaluationResult:
    """RULE_TYPE_GRADUATION_ELIGIBILITY — `rule.params["min_gpa_graduation"]`
    (tối thiểu, có thể lấy từ `RegulationVersion.rules["min_gpa_graduation"]`
    như trong `test_regulation_store.py`)."""
    inputs_echo = {"gpa": gpa, "credits_completed": credits_completed, "credits_required": credits_required}
    resolve_date = _parse_date(at_date) or datetime.now(timezone.utc).date()
    not_in_effect = _rule_not_in_effect_result(rule, inputs_echo, resolve_date)
    if not_in_effect is not None:
        return not_in_effect

    min_gpa = rule.params.get("min_gpa_graduation")
    if min_gpa is None:
        return RuleEvaluationResult(
            status=STATUS_INSUFFICIENT_DATA, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason="Quy tắc thiếu tham số 'min_gpa_graduation' — không thể đánh giá.",
            evidence={}, inputs_echo=inputs_echo,
        )
    evidence = {"min_gpa_graduation": min_gpa}
    if credits_completed < credits_required:
        return RuleEvaluationResult(
            status=STATUS_DENY, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"Số tín chỉ đã hoàn thành ({credits_completed}) chưa đủ yêu cầu tốt nghiệp ({credits_required}).",
            evidence=evidence, inputs_echo=inputs_echo,
        )
    if gpa < min_gpa:
        return RuleEvaluationResult(
            status=STATUS_DENY, rule_id=rule.rule_id,
            regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
            reason=f"GPA hiện tại ({gpa}) chưa đạt tối thiểu tốt nghiệp ({min_gpa}).",
            evidence=evidence, inputs_echo=inputs_echo,
        )
    return RuleEvaluationResult(
        status=STATUS_ALLOW, rule_id=rule.rule_id,
        regulation_id=rule.regulation_id, regulation_version=rule.regulation_version,
        reason="Đủ điều kiện tốt nghiệp (đủ tín chỉ và GPA tối thiểu).",
        evidence=evidence, inputs_echo=inputs_echo,
    )


def decide_final_status(rule_result: RuleEvaluationResult, llm_suggested_status: Optional[str]) -> str:
    """HÀM CANH GÁC DUY NHẤT cho nguyên tắc "LLM IS NOT THE DECISION ENGINE"
    ở tầng Rule Engine: kết quả CUỐI CÙNG hiển thị cho người dùng LUÔN LÀ
    `rule_result.status` — bất kể `llm_suggested_status` (nếu LLM/Agent nào
    đó, do lỗi hoặc bị prompt injection, "đề xuất" một trạng thái khác) nói
    gì. Không có nhánh nào trong hàm này cho phép `llm_suggested_status`
    thắng thế — đây chính là bài test bắt buộc trong đề bài (Phần 12):
    "LLM says ALLOW while Rule Engine says DENY → final response must NOT
    become ALLOW"."""
    return rule_result.status
