"""H-2 (đọc lập review kiến trúc thương mại, đợt 3): dù đã hợp nhất RAG về
CÙNG MỘT HÀM truy xuất (`retrieve_unified_context`), luồng "Tạo Kế hoạch Học
tập" trong `ai_advisor.py` trước đây vẫn gọi hàm đó HAI LẦN ĐỘC LẬP cho CÙNG
một response: 1 lần bên trong `generate_personalized_advice` để build prompt
gửi LLM, 1 lần nữa SAU KHI stream xong để build khung "Bằng chứng & Nguồn
tham khảo"/`verify_citations`. Có rủi ro lý thuyết 2 lần gọi trả về 2 TẬP TÀI
LIỆU KHÁC NHAU nếu trạng thái duyệt thay đổi giữa 2 lần (vd. Admin duyệt/từ
chối 1 tài liệu ngay trong lúc streaming).

Test dưới đây xác nhận `generate_personalized_advice` giờ chấp nhận
`prefetched_relevant_docs` — khi được truyền vào, hàm PHẢI dùng ĐÚNG object
đó (không tự truy xuất lại), để nơi gọi có thể truy xuất 1 lần DUY NHẤT và
tái dùng cho cả prompt lẫn citation verification."""

from __future__ import annotations

import pytest

import dss.config as dss_config


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider

    return MultiAIProvider()


def test_prefetched_relevant_docs_skips_internal_retrieval(llm_integration, monkeypatch):
    """Nếu prefetched_relevant_docs được truyền, retrieve_unified_context KHÔNG
    được gọi lại lần nữa bên trong generate_personalized_advice."""
    from dss.services import rag_service

    def _boom(*args, **kwargs):
        raise AssertionError(
            "generate_personalized_advice() KHÔNG được tự gọi retrieve_unified_context "
            "khi đã có prefetched_relevant_docs — phải dùng lại nguyên object đã truyền vào."
        )

    monkeypatch.setattr(rag_service, "retrieve_unified_context", _boom)

    sentinel_docs = [{"document_id": "doc_sentinel", "title": "T", "content": "C", "status": "APPROVED"}]
    captured = {}
    real_prepare = type(llm_integration)._prepare_personalized_advice_prompt

    def _spy(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=None):
        captured["relevant_docs"] = relevant_docs
        return real_prepare(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=student_profile)

    monkeypatch.setattr(type(llm_integration), "_prepare_personalized_advice_prompt", _spy)

    list(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
            prefetched_relevant_docs=sentinel_docs,
        )
    )

    assert captured["relevant_docs"] is sentinel_docs, (
        "relevant_docs dùng để build prompt phải là CHÍNH object prefetched_relevant_docs "
        "đã truyền vào, không phải một kết quả truy xuất mới/khác."
    )


def test_prefetched_empty_list_means_no_documents_not_fallback_to_retrieval(llm_integration, monkeypatch):
    """Truyền [] (rỗng) một cách tường minh phải được tôn trọng là 'không có
    tài liệu' — KHÔNG được coi là falsy rồi âm thầm tự truy xuất lại."""
    from dss.services import rag_service

    def _boom(*args, **kwargs):
        raise AssertionError("Không được tự truy xuất lại khi prefetched_relevant_docs=[] được truyền tường minh.")

    monkeypatch.setattr(rag_service, "retrieve_unified_context", _boom)

    list(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
            prefetched_relevant_docs=[],
        )
    )


def test_no_prefetched_docs_falls_back_to_internal_retrieval(llm_integration, monkeypatch):
    """Không truyền prefetched_relevant_docs (mặc định None) -> hành vi CŨ giữ
    nguyên: hàm tự gọi retrieve_unified_context (đường dùng bởi compare_ai)."""
    from dss.services import rag_service

    calls = []
    real_fn = rag_service.retrieve_unified_context

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(rag_service, "retrieve_unified_context", _spy)

    list(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
        )
    )

    assert len(calls) == 1
