"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 12: Rule Engine tối
thiểu (prerequisite/credit limit/course registration/academic warning/
thesis eligibility/graduation eligibility) — ALLOW/DENY/WARNING/
INSUFFICIENT_DATA, tenant-scoped/versioned/effective-dated/auditable.
Test bắt buộc quan trọng nhất: "LLM says ALLOW while Rule Engine says
DENY -> final response must NOT become ALLOW"."""

from __future__ import annotations

from dss.services import rule_engine as re


def _rule(**overrides):
    defaults = dict(
        rule_id="rule_credit_limit_v1",
        regulation_id="QC-CNTT-K66",
        regulation_version=1,
        organization_id="org-1",
        rule_type=re.RULE_TYPE_CREDIT_LIMIT,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        params={"max_credits": 24},
    )
    defaults.update(overrides)
    return re.AcademicRule(**defaults)


# --- Credit limit -----------------------------------------------------------


def test_credit_limit_allow_when_within_max():
    result = re.evaluate_credit_limit(_rule(), requested_credits=20)
    assert result.status == re.STATUS_ALLOW
    assert result.rule_id == "rule_credit_limit_v1"
    assert result.regulation_id == "QC-CNTT-K66"
    assert result.regulation_version == 1
    assert result.evidence == {"max_credits": 24}
    assert result.inputs_echo == {"requested_credits": 20}


def test_credit_limit_deny_when_exceeds_max():
    result = re.evaluate_credit_limit(_rule(), requested_credits=30)
    assert result.status == re.STATUS_DENY
    assert "vượt giới hạn" in result.reason


def test_credit_limit_insufficient_data_when_missing_param():
    rule = _rule(params={})
    result = re.evaluate_credit_limit(rule, requested_credits=20)
    assert result.status == re.STATUS_INSUFFICIENT_DATA


def test_rule_not_approved_returns_insufficient_data_not_deny_or_allow():
    """Quy tắc DRAFT/PENDING/RETIRED KHÔNG được coi ngầm định là DENY hay
    ALLOW — phải rõ ràng INSUFFICIENT_DATA để phân biệt với quyết định thật."""
    rule = _rule(status="DRAFT")
    result = re.evaluate_credit_limit(rule, requested_credits=20)
    assert result.status == re.STATUS_INSUFFICIENT_DATA


def test_rule_expired_returns_insufficient_data():
    rule = _rule(effective_to="2023-12-31")
    result = re.evaluate_credit_limit(rule, requested_credits=20, at_date="2024-06-01")
    assert result.status == re.STATUS_INSUFFICIENT_DATA
    assert "hết hiệu lực" in result.reason


def test_rule_not_yet_effective_returns_insufficient_data():
    rule = _rule(effective_from="2030-01-01")
    result = re.evaluate_credit_limit(rule, requested_credits=20, at_date="2024-06-01")
    assert result.status == re.STATUS_INSUFFICIENT_DATA
    assert "chưa có hiệu lực" in result.reason


# --- Academic warning ---------------------------------------------------


def test_academic_warning_triggers_below_threshold():
    rule = _rule(rule_type=re.RULE_TYPE_ACADEMIC_WARNING, params={"warning_gpa_threshold": 2.0})
    result = re.evaluate_academic_warning(rule, gpa=1.5)
    assert result.status == re.STATUS_WARNING


def test_academic_warning_allow_above_threshold():
    rule = _rule(rule_type=re.RULE_TYPE_ACADEMIC_WARNING, params={"warning_gpa_threshold": 2.0})
    result = re.evaluate_academic_warning(rule, gpa=3.0)
    assert result.status == re.STATUS_ALLOW


# --- Thesis eligibility --------------------------------------------------


def test_thesis_eligibility_allow_when_both_conditions_met():
    rule = _rule(rule_type=re.RULE_TYPE_THESIS_ELIGIBILITY, params={"min_gpa": 2.5, "min_credits_completed": 100})
    result = re.evaluate_thesis_eligibility(rule, gpa=3.0, credits_completed=110)
    assert result.status == re.STATUS_ALLOW


def test_thesis_eligibility_deny_when_gpa_too_low():
    rule = _rule(rule_type=re.RULE_TYPE_THESIS_ELIGIBILITY, params={"min_gpa": 2.5, "min_credits_completed": 100})
    result = re.evaluate_thesis_eligibility(rule, gpa=2.0, credits_completed=110)
    assert result.status == re.STATUS_DENY
    assert "GPA" in result.reason


def test_thesis_eligibility_deny_when_credits_too_low():
    rule = _rule(rule_type=re.RULE_TYPE_THESIS_ELIGIBILITY, params={"min_gpa": 2.5, "min_credits_completed": 100})
    result = re.evaluate_thesis_eligibility(rule, gpa=3.0, credits_completed=50)
    assert result.status == re.STATUS_DENY
    assert "tín chỉ" in result.reason


# --- Graduation eligibility -----------------------------------------------


def test_graduation_eligibility_allow_when_all_conditions_met():
    rule = _rule(rule_type=re.RULE_TYPE_GRADUATION_ELIGIBILITY, params={"min_gpa_graduation": 2.0})
    result = re.evaluate_graduation_eligibility(rule, gpa=2.5, credits_completed=140, credits_required=140)
    assert result.status == re.STATUS_ALLOW


def test_graduation_eligibility_deny_when_credits_insufficient():
    rule = _rule(rule_type=re.RULE_TYPE_GRADUATION_ELIGIBILITY, params={"min_gpa_graduation": 2.0})
    result = re.evaluate_graduation_eligibility(rule, gpa=2.5, credits_completed=100, credits_required=140)
    assert result.status == re.STATUS_DENY


def test_graduation_eligibility_deny_when_gpa_insufficient():
    rule = _rule(rule_type=re.RULE_TYPE_GRADUATION_ELIGIBILITY, params={"min_gpa_graduation": 2.0})
    result = re.evaluate_graduation_eligibility(rule, gpa=1.5, credits_completed=140, credits_required=140)
    assert result.status == re.STATUS_DENY


# --- CRITICAL: LLM must never override the Rule Engine's decision ---------


def test_llm_says_allow_but_rule_engine_says_deny_final_must_stay_deny():
    """Bài test BẮT BUỘC quan trọng nhất của Phần 12: nếu LLM (do ảo giác,
    lỗi, hoặc prompt injection) "đề xuất" ALLOW trong khi Rule Engine đã
    quyết định DENY, kết quả CUỐI CÙNG hiển thị cho người dùng TUYỆT ĐỐI
    KHÔNG được trở thành ALLOW."""
    rule = _rule(params={"max_credits": 24})
    deny_result = re.evaluate_credit_limit(rule, requested_credits=30)
    assert deny_result.status == re.STATUS_DENY

    final_status = re.decide_final_status(deny_result, llm_suggested_status=re.STATUS_ALLOW)
    assert final_status == re.STATUS_DENY, (
        "LLM 'đề xuất' ALLOW không được phép ghi đè quyết định DENY thật của Rule Engine."
    )


def test_llm_says_deny_but_rule_engine_says_allow_final_must_stay_allow():
    """Đối xứng: LLM không được ghi đè theo chiều ngược lại — Rule Engine
    LUÔN là nguồn quyết định duy nhất, không riêng gì chiều DENY->ALLOW."""
    rule = _rule(params={"max_credits": 24})
    allow_result = re.evaluate_credit_limit(rule, requested_credits=10)
    assert allow_result.status == re.STATUS_ALLOW

    final_status = re.decide_final_status(allow_result, llm_suggested_status=re.STATUS_DENY)
    assert final_status == re.STATUS_ALLOW


def test_llm_suggestion_none_still_returns_rule_engine_status():
    """Kể cả khi không có gợi ý nào từ LLM (None), kết quả vẫn phải là của
    Rule Engine — hàm không có nhánh nào phụ thuộc vào input LLM."""
    rule = _rule(params={"max_credits": 24})
    deny_result = re.evaluate_credit_limit(rule, requested_credits=30)
    assert re.decide_final_status(deny_result, llm_suggested_status=None) == re.STATUS_DENY
