"""E-4: Kho 19 tài liệu viết cứng (_init_enhanced_knowledge_base) được trình bày
làm "nguồn" trong câu trả lời RAG mà không phân biệt với tài liệu do trường tải
lên/kiểm duyệt — người đọc dễ hiểu nhầm đây là tài liệu đã được thẩm định."""

from __future__ import annotations

import inspect

from dss.services.rag_service import format_document_citation
from dss.tabs import ai_advisor


def test_unverified_internal_kb_doc_labeled_not_reviewed():
    doc = {
        "title": "Kỹ năng quản lý thời gian",
        "source": "knowledge_base",
        "status": "DRAFT",
        "source_verified": False,
    }
    citation = format_document_citation(doc)
    assert "CHƯA kiểm duyệt" in citation
    assert "Kỹ năng quản lý thời gian" in citation


def test_verified_internal_kb_doc_labeled_reviewed():
    doc = {"title": "Phương pháp SQ3R", "source": "knowledge_base", "status": "APPROVED", "source_verified": True}
    citation = format_document_citation(doc)
    assert "đã kiểm duyệt" in citation
    assert "CHƯA" not in citation


def test_non_knowledge_base_doc_uses_plain_title():
    doc = {"title": "Ghi chú bài giảng tuần 3", "source": "runtime_upload"}
    assert format_document_citation(doc) == "Ghi chú bài giảng tuần 3"


def test_ai_advisor_chat_sources_use_format_document_citation():
    source = inspect.getsource(ai_advisor)
    assert 'd.get("title", "") for d in _chat_docs' not in source, (
        "ai_advisor.py vẫn hiển thị nguồn RAG chỉ bằng tiêu đề trần trụi, không "
        "phân biệt tài liệu mẫu nội bộ chưa kiểm duyệt với tài liệu đã kiểm duyệt."
    )
    assert "format_document_citation" in source
