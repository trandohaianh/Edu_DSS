"""FINAL REMAINING-GAPS CLOSURE — Section 8: Token Budget. Written before
`dss/services/token_budget.py` existed (TDD)."""

from __future__ import annotations

from dss.services import token_budget


def test_default_budget_exists_per_known_intent():
    budget = token_budget.get_budget_for_intent("ADVISOR_PLAN")
    assert budget.max_recent_turns > 0
    assert budget.max_rag_chunks > 0


def test_unknown_intent_gets_a_conservative_fallback_budget_not_unbounded():
    budget = token_budget.get_budget_for_intent("SOME_UNKNOWN_INTENT")
    assert budget.max_recent_turns > 0
    assert budget.max_rag_chunks > 0
    assert budget.max_rag_chunks <= token_budget.get_budget_for_intent("RAG_QA").max_rag_chunks


def test_trim_history_keeps_only_max_recent_turns():
    turns = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    budget = token_budget.TokenBudget(
        max_recent_turns=3,
        max_summary_chars=0,
        max_rag_chunks=5,
        max_rag_chars=1000,
        max_structured_context_chars=2000,
        max_provider_output_tokens=512,
    )
    trimmed = token_budget.trim_conversation_history(turns, budget)
    assert len(trimmed) == 3
    assert trimmed == turns[-3:]


def test_trim_rag_chunks_keeps_only_max_chunks_highest_ranked_first():
    chunks = [{"content": f"chunk {i}", "relevance_score": 10 - i} for i in range(8)]
    budget = token_budget.TokenBudget(
        max_recent_turns=5,
        max_summary_chars=0,
        max_rag_chunks=3,
        max_rag_chars=1000,
        max_structured_context_chars=2000,
        max_provider_output_tokens=512,
    )
    trimmed = token_budget.trim_rag_chunks(chunks, budget)
    assert len(trimmed) == 3
    assert [c["content"] for c in trimmed] == ["chunk 0", "chunk 1", "chunk 2"]


def test_trim_never_touches_deterministic_facts_dict():
    """Section 8: Calculator/Rule/Regulation/Validator ket qua KHONG BAO GIO
    bi cat - ham trim chi nhan history/RAG chunks, khong co tham so nao cho
    phep truyen 'deterministic_facts' vao de bi xen vao logic cat."""
    import inspect

    sig_history = inspect.signature(token_budget.trim_conversation_history)
    sig_rag = inspect.signature(token_budget.trim_rag_chunks)
    assert set(sig_history.parameters.keys()) == {"turns", "budget"}
    assert set(sig_rag.parameters.keys()) == {"chunks", "budget"}


def test_estimate_context_size_chars_is_a_real_computation_not_a_stub():
    text = "a" * 500
    assert token_budget.estimate_context_size_chars(text) == 500


def test_context_exceeding_structured_budget_is_flagged_not_silently_truncated():
    """Section 8 noi 'KHONG duoc cat du kien xac dinh quan trong' - vi vay
    context CO CAU TRUC (structured_context, vd. ket qua Calculator) khi
    vuot ngan sach phai duoc BAO CAO (over_budget=True), KHONG duoc tu dong
    cat mat 1 phan noi dung xac dinh."""
    budget = token_budget.TokenBudget(
        max_recent_turns=5,
        max_summary_chars=0,
        max_rag_chunks=5,
        max_rag_chars=1000,
        max_structured_context_chars=10,
        max_provider_output_tokens=512,
    )
    result = token_budget.check_structured_context_budget("a" * 100, budget)
    assert result.over_budget is True
    assert result.size_chars == 100
