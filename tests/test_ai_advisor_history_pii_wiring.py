"""FINAL REMAINING-GAPS CLOSURE — Section 7: confirm ai_advisor.py THẬT SỰ
calls sanitize_conversation_turn_for_provider() when building conversation
history for the LLM, not just that the function exists in isolation
(source-inspection, same convention as other wiring tests this engagement)."""

from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_history_snippet_construction_calls_conversation_sanitizer():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "privacy_service.sanitize_conversation_turn_for_provider(m['content'])" in source


def test_sanitizer_call_happens_inside_history_snippet_join_not_elsewhere():
    """Đảm bảo lời gọi nằm ĐÚNG trong đoạn xây _history_snippet (trước khi
    join vào _full_student_context), không phải một chỗ không liên quan."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    idx_snippet = source.index("_history_snippet = ")
    idx_sanitizer = source.index("sanitize_conversation_turn_for_provider(m['content'])")
    idx_full_context = source.index("_full_student_context = _anon_context")
    assert idx_snippet < idx_sanitizer < idx_full_context
