"""FINAL GAP CLOSURE — Section 24: Knowledge Fallback must PREVENT-BEFORE,
not just VERIFY-AFTER. Confirms ai_advisor.py blocks the LLM call entirely
for RAG_QA questions with zero retrieved evidence, rather than asking the
LLM and only flagging the answer as hallucinated afterward (source-
inspection, same convention as other wiring tests this session)."""

from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_rag_qa_with_empty_retrieval_short_circuits_before_llm_call():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert 'if _route_decision.intent == ai_router.INTENT_RAG_QA and not _chat_docs:' in source

    idx_prevent_before = source.index("if _route_decision.intent == ai_router.INTENT_RAG_QA and not _chat_docs:")
    idx_gateway_chat_call = source.index('request_type="advisor_chat"')
    assert idx_prevent_before < idx_gateway_chat_call, (
        "Chặn Knowledge Fallback PHẢI chạy TRƯỚC LLMGateway.stream_generate() — "
        "nếu không, đây vẫn chỉ là VERIFY-AFTER, không phải PREVENT-BEFORE."
    )


def test_prevent_before_block_reruns_without_calling_llm():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    idx = source.index("if _route_decision.intent == ai_router.INTENT_RAG_QA and not _chat_docs:")
    block = source[idx : idx + 1000]
    assert "st.rerun()" in block
    assert "KHÔNG" in block or "khong" in block.lower()


def test_prevent_before_check_happens_after_retrieval_not_before():
    """Chặn phải xảy ra SAU khi đã thử retrieval (_chat_docs đã tính) — nếu
    không thì không thể biết retrieval có rỗng hay không."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    idx_retrieval = source.index("_chat_docs = _find_docs_rag_safe(")
    idx_prevent_before = source.index("if _route_decision.intent == ai_router.INTENT_RAG_QA and not _chat_docs:")
    assert idx_retrieval < idx_prevent_before
