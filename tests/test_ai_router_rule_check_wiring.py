"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 12: Rule Engine phải
THẬT SỰ chặn LLM tự quyết định ALLOW/DENY trong luồng chat, không chỉ tồn
tại như module cô lập (rule_engine.py đã có + test đầy đủ, xem
test_rule_engine.py)."""
from __future__ import annotations

from dss.services import ai_router
from dss.services.rule_engine import AcademicRule, RULE_TYPE_CREDIT_LIMIT, evaluate_credit_limit


def test_no_evaluation_result_returns_honest_reply_without_fabricating_input():
    """Nơi gọi thật (ai_advisor.py) hiện KHÔNG có đủ dữ liệu (organization_id/
    program_id/cohort + tín chỉ đã hoàn thành) -> PHẢI trả lời trung thực,
    KHÔNG được tự bịa input để gọi rule_engine 'như thật'."""
    reply = ai_router.build_academic_rule_check_reply("Em có được đăng ký môn B không?")
    assert "Cố vấn học tập" in reply
    assert "Phòng Đào tạo" in reply


def test_allow_result_reflects_rule_engine_not_llm():
    rule = AcademicRule(
        rule_id="r1", regulation_id="QC-1", regulation_version=1, organization_id="org-1",
        rule_type=RULE_TYPE_CREDIT_LIMIT, effective_from="2024-01-01", effective_to=None,
        status="APPROVED", params={"max_credits": 24},
    )
    result = evaluate_credit_limit(rule, requested_credits=20)
    reply = ai_router.build_academic_rule_check_reply("Em có được đăng ký 20 tín chỉ không?", rule_evaluation_result=result)
    assert "Đủ điều kiện" in reply
    assert "không phải AI tự quyết định" in reply


def test_deny_result_reflects_rule_engine_not_llm():
    rule = AcademicRule(
        rule_id="r1", regulation_id="QC-1", regulation_version=1, organization_id="org-1",
        rule_type=RULE_TYPE_CREDIT_LIMIT, effective_from="2024-01-01", effective_to=None,
        status="APPROVED", params={"max_credits": 24},
    )
    result = evaluate_credit_limit(rule, requested_credits=30)
    reply = ai_router.build_academic_rule_check_reply("Em có được đăng ký 30 tín chỉ không?", rule_evaluation_result=result)
    assert "Không đủ điều kiện" in reply
    assert "vượt giới hạn" in reply
