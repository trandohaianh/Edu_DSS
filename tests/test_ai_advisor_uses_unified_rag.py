"""NHÓM F: Tư vấn AI (ai_advisor.py) phải trích dẫn qua
rag_service.retrieve_unified_context (kho tri thức thật, đã duyệt) — KHÔNG
còn gọi rag_service.retrieve_documents (đường cũ, chỉ đọc 19 tài liệu viết
cứng + runtime_documents, không bao giờ chạm tới vector_store thật)."""
from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_find_docs_rag_safe_calls_unified_retrieval():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "rag_service.retrieve_unified_context(" in source, (
        "_find_docs_rag_safe không còn gọi retrieve_unified_context — luồng "
        "Tư vấn AI có thể lại chỉ đọc 19 tài liệu viết cứng."
    )


def test_find_docs_rag_safe_no_longer_calls_legacy_retrieve_documents():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "rag_service.retrieve_documents(" not in source, (
        "_find_docs_rag_safe vẫn gọi rag_service.retrieve_documents (đường cũ) "
        "— 2 luồng RAG vẫn chưa thực sự hợp nhất."
    )


def test_evidence_panel_shows_honest_message_when_no_approved_docs():
    source = inspect.getsource(ai_advisor)
    assert "_last_rag_retrieval_status" in source
    assert "NO_RELEVANT_EVIDENCE" in source
