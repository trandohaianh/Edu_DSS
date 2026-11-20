"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 9-10: xác nhận
ai_advisor.py THẬT SỰ gọi ai_router.build_regulation_lookup_reply() trong
luồng chat để chặn LLM tự đoán quy chế, không chỉ tồn tại như module cô lập
(source inspection — đúng quy ước dự án cho code UI Streamlit khó test trực
tiếp qua widget thật, cùng mẫu test_ai_advisor_gpa_router_wiring.py)."""

from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_ai_advisor_tab_calls_regulation_lookup_before_llm_gateway_for_chat():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "ai_router.build_regulation_lookup_reply(_question)" in source
    assert "INTENT_REGULATION_LOOKUP" in source

    idx_regulation_call = source.index("ai_router.build_regulation_lookup_reply(_question)")
    idx_gateway_chat_call = source.index('request_type="advisor_chat"')
    assert idx_regulation_call < idx_gateway_chat_call, (
        "build_regulation_lookup_reply() phải chạy TRƯỚC LLMGateway.stream_generate() "
        "cho luồng chat — nếu không, LLM vẫn có cơ hội tự đoán quy chế trước khi bị chặn."
    )


def test_regulation_reply_short_circuits_before_rag_and_llm_call():
    """Khi router phát hiện REGULATION_LOOKUP và có câu trả lời xác định
    (_regulation_reply is not None -> góp vào _router_short_circuit_reply),
    code PHẢI st.rerun() ngay — không rơi tiếp xuống RAG retrieval/LLM
    Gateway (nơi LLM có thể tự đoán quy chế)."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
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
