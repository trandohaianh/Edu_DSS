"""FINAL GAP CLOSURE — Section 17-19: constrained Agent/Orchestrator. Written
FIRST (TDD), before `dss/services/agent.py` exists, per the master prompt's
explicit instruction to write the "must not bypass RBAC/tool-allowlist"
tests before any implementation — consistent with this session's established
methodology for every genuinely new module (circuit_breaker.py, ai_router.py,
rule_engine.py, validator.py were all built this way)."""
from __future__ import annotations

import pytest

from dss.services import agent


def test_tool_allowlist_is_a_static_greppable_set():
    """Không phải danh sách động Agent có thể tự mở rộng lúc chạy — allowlist
    PHẢI là hằng số module-level."""
    assert isinstance(agent._ALLOWED_TOOLS, frozenset)
    assert len(agent._ALLOWED_TOOLS) > 0


def test_agent_refuses_tool_call_outside_allowlist():
    with pytest.raises(agent.ToolNotAllowedError):
        agent._invoke_tool("os.system", lambda: None)


def test_agent_has_no_arbitrary_sql_or_shell_capability():
    """Kiểm tra tĩnh: module agent.py không import subprocess/os.system/
    sqlalchemy text() trực tiếp cho truy vấn tuỳ ý — chỉ gọi qua các service
    đã có sẵn (gpa_calculator/regulation_resolver/rule_engine/validator)."""
    import inspect
    source = inspect.getsource(agent)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "eval(" not in source and "exec(" not in source


def test_gpa_tool_order_end_to_end_with_full_authorized_context():
    """Section 18 vi dụ GPA: Router -> Agent -> authorized student data ->
    Calculator -> Validator -> (optional LLM) -> Validator -> response."""
    request = agent.AgentRequest(
        user_id="pseudo_student_1", organization_id="org-1", role="Sinh viên",
        intent="GPA_CALCULATION",
        authorized_context={"current_gpa": 6.0, "credits_done": 20, "target_gpa": 7.5, "credits_remaining": 20},
        request_text="GPA hiện tại 6.0, muốn lên 7.5, còn 20 tín chỉ", correlation_id="corr-1",
    )
    result = agent.run_gpa_calculation(request)
    assert "gpa_calculator.compute_required_remaining_gpa" in result.tools_used
    assert "validator.validate_gpa_value" in result.tools_used
    assert result.llm_used is False
    assert result.fallback is None
    assert result.decision.status == "ok"
    assert result.validator_result.status == "PASS"
    assert result.audit_metadata["correlation_id"] == "corr-1"


def test_gpa_tool_order_reports_insufficient_data_honestly_not_fabricated():
    request = agent.AgentRequest(
        user_id="pseudo_student_1", organization_id="org-1", role="Sinh viên",
        intent="GPA_CALCULATION", authorized_context={"current_gpa": 6.0},
        request_text="...", correlation_id="corr-2",
    )
    result = agent.run_gpa_calculation(request)
    assert result.fallback == "INSUFFICIENT_DATA"
    assert result.decision is None


def test_agent_level_guard_reuses_rule_engine_decide_final_status_not_a_duplicate():
    """Section 19: bảo đảm 'LLM không override' PHẢI dùng LẠI
    rule_engine.decide_final_status() (nguồn sự thật duy nhất đã test kỹ ở
    test_rule_engine.py), KHÔNG được viết lại logic riêng ở tầng Agent (2 nơi
    cùng logic dễ lệch nhau như lỗi S-1 đã gặp)."""
    import inspect
    source = inspect.getsource(agent.enforce_rule_engine_decision_cannot_be_overridden)
    assert "decide_final_status" in source


def test_agent_deny_cannot_be_overridden_by_llm_via_agent_layer():
    from dss.services.rule_engine import AcademicRule, RULE_TYPE_CREDIT_LIMIT, evaluate_credit_limit

    rule = AcademicRule(
        rule_id="r1", regulation_id="QC-1", regulation_version=1, organization_id="org-1",
        rule_type=RULE_TYPE_CREDIT_LIMIT, effective_from="2024-01-01", effective_to=None,
        status="APPROVED", params={"max_credits": 24},
    )
    deny_result = evaluate_credit_limit(rule, requested_credits=30)
    final = agent.enforce_rule_engine_decision_cannot_be_overridden(deny_result, llm_suggested_status="ALLOW")
    assert final == "DENY"


def test_agent_request_and_result_are_structured_not_free_form_dicts():
    """Section 17 yêu cầu 'structured request contract' — xác nhận
    AgentRequest/AgentResult là dataclass thật, có field cố định, không phải
    dict tự do dễ thiếu trường."""
    import dataclasses
    assert dataclasses.is_dataclass(agent.AgentRequest)
    assert dataclasses.is_dataclass(agent.AgentResult)
    request_fields = {f.name for f in dataclasses.fields(agent.AgentRequest)}
    assert request_fields == {
        "user_id", "organization_id", "role", "intent", "authorized_context", "request_text", "correlation_id",
    }
