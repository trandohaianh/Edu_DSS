"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 10-11: xác nhận
ai_advisor.py THẬT SỰ gọi ai_router/gpa_calculator trong luồng chat, không
chỉ tồn tại như module cô lập chưa ai dùng tới (source inspection — đúng
quy ước dự án cho code UI Streamlit khó test trực tiếp qua widget thật)."""

from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_ai_advisor_tab_calls_router_before_llm_gateway_for_chat():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "ai_router.classify(_question)" in source
    # CẬP NHẬT (FINAL REMAINING-GAPS CLOSURE, Section 5): lời gọi này nay
    # truyền thêm user_id/role thật (để định tuyến qua agent.
    # run_gpa_calculation() với authorize() thật) — không còn khớp nguyên
    # cụm "(_question)" liền sau tên hàm, kiểm tra tên hàm xuất hiện là đủ.
    assert "ai_router.build_gpa_calculation_reply(" in source

    # Router PHẢI được gọi TRƯỚC LLM Gateway (stream_generate) trong luồng
    # chat — nếu không, Calculator sẽ không có cơ hội "chặn" trước khi tốn
    # 1 lượt gọi AI thật.
    idx_router = source.index("ai_router.classify(_question)")
    idx_gateway_chat_call = source.index('request_type="advisor_chat"')
    assert idx_router < idx_gateway_chat_call, (
        "Router phải chạy TRƯỚC lời gọi LLMGateway.stream_generate() cho luồng chat."
    )


def test_gpa_reply_short_circuits_before_rag_and_llm_call():
    """Khi router phát hiện GPA_CALCULATION và có câu trả lời xác định
    (_gpa_reply is not None -> góp vào _router_short_circuit_reply), code
    PHẢI st.rerun() ngay — không rơi tiếp xuống RAG retrieval/LLM Gateway.

    CẬP NHẬT (Phần 10): sau khi wire thêm REGULATION_LOOKUP, điều kiện chặn
    chung được đổi tên thành `_router_short_circuit_reply` (gộp cả
    `_gpa_reply` và `_regulation_reply`) — test cập nhật theo tên biến mới,
    không còn kiểm tra riêng `_gpa_reply is not None` nữa vì biến đó không
    còn là điều kiện rẽ nhánh cuối cùng trong code thật."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "_gpa_reply or _regulation_reply" in source
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
