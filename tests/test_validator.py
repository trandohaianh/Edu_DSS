"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 13: Validator tối
thiểu — PASS/FAIL/PARTIAL/NEEDS_HUMAN_REVIEW. Test bắt buộc quan trọng
nhất: "test that an intentionally wrong LLM answer cannot override the
Calculator result" (Phần 1h)."""

from __future__ import annotations

import pytest

from dss.services import validator as v
from dss.services.gpa_calculator import compute_required_remaining_gpa
from dss.services.regulation_resolver import RegulationResolution, RegulationVersion
from dss.services.rule_engine import RULE_TYPE_CREDIT_LIMIT, AcademicRule, evaluate_credit_limit

# --- GPA scale ---------------------------------------------------------


def test_gpa_within_scale_passes():
    result = v.validate_gpa_value(3.2, scale_min=0.0, scale_max=4.0)
    assert result.status == v.STATUS_PASS


def test_gpa_out_of_scale_fails():
    result = v.validate_gpa_value(11.0, scale_min=0.0, scale_max=10.0)
    assert result.status == v.STATUS_FAIL
    assert "ngoài thang điểm" in result.reason


def test_gpa_negative_fails():
    result = v.validate_gpa_value(-0.5)
    assert result.status == v.STATUS_FAIL


# --- Rule Engine result consistency ----------------------------------------


def test_rule_engine_deny_with_reason_passes():
    rule = AcademicRule(
        rule_id="r1",
        regulation_id="QC-1",
        regulation_version=1,
        organization_id="org-1",
        rule_type=RULE_TYPE_CREDIT_LIMIT,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        params={"max_credits": 24},
    )
    deny_result = evaluate_credit_limit(rule, requested_credits=30)
    result = v.validate_rule_engine_result(deny_result)
    assert result.status == v.STATUS_PASS


def test_rule_engine_result_with_invalid_status_fails():
    class _FakeBadResult:
        status = "MAYBE"
        reason = "..."

    result = v.validate_rule_engine_result(_FakeBadResult())
    assert result.status == v.STATUS_FAIL


def test_rule_engine_deny_without_reason_fails():
    class _FakeDenyNoReason:
        status = "DENY"
        reason = ""

    result = v.validate_rule_engine_result(_FakeDenyNoReason())
    assert result.status == v.STATUS_FAIL
    assert "không có căn cứ" in result.reason


# --- Regulation Resolver result consistency --------------------------------


def test_regulation_ok_with_regulation_object_passes():
    reg = RegulationVersion(
        regulation_id="QC-1",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
        version=1,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        approved_by="admin",
        source_document_id=None,
    )
    resolution = RegulationResolution(status="ok", regulation=reg, message="ok", candidates_considered=1)
    result = v.validate_regulation_resolution(resolution)
    assert result.status == v.STATUS_PASS


def test_regulation_ok_without_regulation_object_fails():
    """Dữ liệu KHÔNG nhất quán: status='ok' nhưng regulation=None — Validator
    phải bắt được lỗi này thay vì để tầng gọi hiển thị như thành công."""
    resolution = RegulationResolution(status="ok", regulation=None, message="ok", candidates_considered=1)
    result = v.validate_regulation_resolution(resolution)
    assert result.status == v.STATUS_FAIL


def test_regulation_not_found_passes_consistency_check():
    resolution = RegulationResolution(status="NOT_FOUND", regulation=None, message="...", candidates_considered=0)
    result = v.validate_regulation_resolution(resolution)
    assert result.status == v.STATUS_PASS


# --- CRITICAL: LLM must never override the Calculator's real number -------


def test_llm_wrong_number_vs_calculator_result_fails_and_blocks():
    """Test bắt buộc: Calculator tính ra 1 con số ĐÚNG, LLM (do ảo giác) "nói"
    ra 1 con số KHÁC — Validator PHẢI FAIL, nơi gọi PHẢI dùng Safe Fallback,
    KHÔNG được hiển thị con số sai của LLM."""
    real_result = compute_required_remaining_gpa(
        current_gpa=6.0,
        credits_done=20,
        target_gpa=7.5,
        credits_remaining=20,
    )
    assert real_result.status == "ok"
    correct_value = real_result.rounded_value  # 9.0 theo cong thuc

    llm_wrong_claim = correct_value + 2.0  # LLM co tinh "noi sai"
    result = v.validate_llm_numeric_claim(llm_wrong_claim, correct_value)
    assert result.status == v.STATUS_FAIL
    assert "CHẶN" in result.reason

    fallback_message = v.decide_safe_fallback_message(result)
    # Safe Fallback la thong diep NGHIEP VU chung, KHONG duoc chua con so SAI
    # ma LLM da neu ra (khong duoc "ro ri" ket qua da bi chan qua thong diep
    # fallback).
    assert str(llm_wrong_claim) not in fallback_message
    assert "liên hệ" in fallback_message.lower()


def test_llm_correct_number_matching_calculator_passes():
    result = v.validate_llm_numeric_claim(9.0, 9.0)
    assert result.status == v.STATUS_PASS


def test_llm_number_within_tolerance_passes():
    result = v.validate_llm_numeric_claim(9.001, 9.0, tolerance=0.01)
    assert result.status == v.STATUS_PASS


def test_llm_made_no_numeric_claim_passes_trivially():
    result = v.validate_llm_numeric_claim(None, 9.0)
    assert result.status == v.STATUS_PASS


def test_safe_fallback_message_does_not_leak_technical_details():
    result = v.ValidationResult(status=v.STATUS_FAIL, reason="Internal traceback: foo.py line 42")
    message = v.decide_safe_fallback_message(result)
    assert "traceback" not in message.lower()
    assert "foo.py" not in message


def test_safe_fallback_raises_if_called_on_pass():
    result = v.ValidationResult(status=v.STATUS_PASS, reason="ok")
    with pytest.raises(ValueError):
        v.decide_safe_fallback_message(result)


def test_needs_human_review_gets_distinct_message():
    result = v.ValidationResult(status=v.STATUS_NEEDS_HUMAN_REVIEW, reason="...")
    message = v.decide_safe_fallback_message(result)
    assert "xác nhận thủ công" in message


def test_invalid_status_raises_on_construction():
    with pytest.raises(ValueError):
        v.ValidationResult(status="MAYBE")
