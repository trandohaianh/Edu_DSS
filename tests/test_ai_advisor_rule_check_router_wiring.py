"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 12: xác nhận
ai_advisor.py THẬT SỰ gọi ai_router.build_academic_rule_check_reply() trong
luồng chat để chặn LLM tự quyết định ALLOW/DENY (source inspection — đúng
quy ước dự án, cùng mẫu test_ai_advisor_regulation_router_wiring.py)."""

from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_ai_advisor_tab_calls_rule_check_before_llm_gateway_for_chat():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "ai_router.build_academic_rule_check_reply(_question)" in source
    assert "INTENT_ACADEMIC_RULE_CHECK" in source

    idx_rule_check_call = source.index("ai_router.build_academic_rule_check_reply(_question)")
    idx_gateway_chat_call = source.index('request_type="advisor_chat"')
    assert idx_rule_check_call < idx_gateway_chat_call, (
        "build_academic_rule_check_reply() phải chạy TRƯỚC LLMGateway.stream_generate() "
        "cho luồng chat — nếu không, LLM vẫn có cơ hội tự quyết định ALLOW/DENY trước khi bị chặn."
    )


def test_rule_check_reply_included_in_short_circuit_condition():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "_gpa_reply or _regulation_reply or _rule_check_reply" in source
    idx_short_circuit = source.index("if _router_short_circuit_reply is not None:")
    block = _if_body(source, idx_short_circuit)
    assert "st.rerun()" in block


def _if_body(source: str, idx: int) -> str:
    """Thân của câu lệnh `if` bắt đầu tại idx: các dòng thụt sâu hơn dòng `if`.
    Dựa vào thụt lề thay vì số ký tự cố định, nên không vỡ khi mã được format lại."""
    lines = source[idx:].splitlines()
    head = source[:idx].rsplit("\n", 1)[-1] + lines[0]
    indent = len(head) - len(head.lstrip())
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return "\n".join(body)
