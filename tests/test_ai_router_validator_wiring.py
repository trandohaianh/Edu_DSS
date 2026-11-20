"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 13: xác nhận Validator
THẬT SỰ được gọi bên trong build_gpa_calculation_reply/
build_regulation_lookup_reply/build_academic_rule_check_reply — không chỉ
import mà không dùng. Ép validator FAIL (monkeypatch) để chứng minh khi
FAIL, nội dung đã tính toán KHÔNG được hiển thị, Safe Fallback được dùng
thay thế."""

from __future__ import annotations

from dss.services import ai_router, regulation_store, validator
from dss.services.regulation_resolver import RegulationVersion
from dss.services.rule_engine import (
    RULE_TYPE_CREDIT_LIMIT,
    AcademicRule,
    evaluate_credit_limit,
)


def _force_fail(*args, **kwargs):
    return validator.ValidationResult(status=validator.STATUS_FAIL, reason="forced-fail-for-test")


def test_gpa_reply_uses_safe_fallback_when_validator_fails(monkeypatch):
    monkeypatch.setattr(validator, "validate_gpa_value", _force_fail)
    reply = ai_router.build_gpa_calculation_reply("current_gpa 6.0 credits_done 20 target_gpa 7.5 credits_remaining 20")
    assert reply is not None
    assert "9.0" not in reply and "9.00" not in reply, (
        "Khi Validator FAIL, con số đã tính (9.0) KHÔNG được lọt ra trong câu trả lời."
    )
    assert "liên hệ" in reply.lower()


def test_regulation_reply_uses_safe_fallback_when_validator_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(regulation_store, "get_data_root", lambda: tmp_path)
    regulation_store.upsert_regulation(
        RegulationVersion(
            regulation_id="QC-SHOULD-NOT-APPEAR",
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
    )
    monkeypatch.setattr(validator, "validate_regulation_resolution", _force_fail)
    reply = ai_router.build_regulation_lookup_reply(
        "Quy chế nào đang áp dụng cho em?",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
    )
    assert "QC-SHOULD-NOT-APPEAR" not in reply, (
        "Khi Validator FAIL, quy chế đã resolve KHÔNG được lọt ra trong câu trả lời."
    )
    assert "liên hệ" in reply.lower()


def test_rule_check_reply_uses_safe_fallback_when_validator_fails(monkeypatch):
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
    result = evaluate_credit_limit(rule, requested_credits=20)
    monkeypatch.setattr(validator, "validate_rule_engine_result", _force_fail)
    reply = ai_router.build_academic_rule_check_reply(
        "Em có được đăng ký 20 tín chỉ không?",
        rule_evaluation_result=result,
    )
    assert "Đủ điều kiện" not in reply, (
        "Khi Validator FAIL, kết luận ALLOW đã tính KHÔNG được lọt ra trong câu trả lời."
    )
    assert "liên hệ" in reply.lower()
