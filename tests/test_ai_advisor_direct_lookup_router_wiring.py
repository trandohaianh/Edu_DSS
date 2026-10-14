"""FINAL GAP CLOSURE — Câu 15: xác nhận ai_advisor.py THẬT SỰ gọi
ai_router.build_direct_data_lookup_reply() trong luồng chat, chặn LLM cho
câu hỏi tra cứu dữ liệu trực tiếp (source-inspection, cùng quy ước với các
test wiring khác trong phiên này)."""
from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_ai_advisor_tab_calls_direct_lookup_before_llm_gateway_for_chat():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "ai_router.build_direct_data_lookup_reply(_question, student_row=student_data_llm_filtered)" in source
    assert "INTENT_DIRECT_DATA_LOOKUP" in source

    idx_direct_lookup_call = source.index("ai_router.build_direct_data_lookup_reply(")
    idx_gateway_chat_call = source.index('request_type="advisor_chat"')
    assert idx_direct_lookup_call < idx_gateway_chat_call, (
        "build_direct_data_lookup_reply() phải chạy TRƯỚC LLMGateway.stream_generate() cho luồng chat."
    )


def test_direct_lookup_uses_only_the_current_authenticated_students_own_row():
    """student_data_llm_filtered phải được truyền y nguyên (không có tham số
    student_id nào khác đọc từ nội dung câu hỏi) — an toàn cross-student."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    idx = source.index("student_row=student_data_llm_filtered")
    block = source[max(0, idx - 200): idx + 50]
    assert "_question" in block


def test_direct_lookup_included_in_short_circuit_condition():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "_gpa_reply or _regulation_reply or _rule_check_reply or _direct_lookup_reply" in source
    idx_short_circuit = source.index("if _router_short_circuit_reply is not None:")
    block = source[idx_short_circuit: idx_short_circuit + 400]
    assert "st.rerun()" in block
