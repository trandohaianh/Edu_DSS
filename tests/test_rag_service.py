"""Regression suite — RAG filtering (dss.core.models.find_relevant_documents_rag
+ dss.services.rag_service).

Dùng model embedding THẬT (sentence-transformers/all-MiniLM-L6-v2) — không
mock — vì hành vi cần kiểm chứng (lọc tương đối theo top-1, không hardcode
tuyệt đối, cờ low_confidence) phụ thuộc trực tiếp vào phân phối điểm cosine
similarity THẬT của model này (xem Phase 6: model này có "sàn nhiễu" ~0.52-0.57
ngay cả với câu hỏi hoàn toàn không liên quan). Load model 1 LẦN cho cả file
(fixture scope=module) để không phải tải lại cho từng test case.
"""
from __future__ import annotations

import pytest

import dss.config as dss_config


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider
    provider = MultiAIProvider()
    # Chạm 1 lần để nạp model embedding trước khi vào các test case thật.
    provider.get_embedding("khởi động model")
    return provider


def test_relevant_query_returns_matching_document(llm_integration):
    docs = llm_integration.find_relevant_documents_rag(
        "lập trình, coding, thực hành", top_k=5, use_warehouse_data=False
    )
    assert len(docs) >= 1
    assert any("Lập trình" in d["title"] for d in docs)
    assert bool(docs[0]["low_confidence"]) is False


def test_off_topic_query_returns_no_evidence(llm_integration):
    """Mục 14: Truy vấn hoàn toàn lạc đề (thời tiết) -> Sàn tin cậy không đạt
    -> Trả về rỗng [] để LLM không bịa đặt câu trả lời từ tài liệu không liên quan."""
    docs = llm_integration.find_relevant_documents_rag(
        "thời tiết hôm nay thế nào", top_k=5, use_warehouse_data=False
    )
    assert len(docs) == 0



def test_real_lms_mode_filters_unverified_documents(llm_integration):
    """Mục 11 & 12, CẬP NHẬT theo NHÓM F (F-0b): trước đây 4/19 tài liệu mẫu
    (gồm doc_003 — Pomodoro) tự gán cứng status="APPROVED"/source_verified=True
    trong code, KHÔNG hề có người duyệt hay bản ghi duyệt thật nào — test cũ
    khẳng định hành vi đó là ĐÚNG ("doc_003 là APPROVED -> được trả về"), nhưng
    đây chính xác là lỗi F-0b đã xác minh (tự nhận đã duyệt mà không có quy
    trình duyệt thật). Đã sửa `_init_enhanced_knowledge_base` để KHÔNG còn tài
    liệu nào tự nhận "đã duyệt" — mọi tài liệu (kể cả doc_003) giờ đều
    DRAFT/source_verified=False cho tới khi có người DUYỆT THẬT (qua
    `document_approval_service`, xem `test_real_lms_mode_returns_empty_...`
    và `test_legacy_document_becomes_citable_after_real_approval` bên dưới —
    đây mới là con đường ĐÚNG để một tài liệu mẫu cũ trở nên hợp lệ)."""
    docs = llm_integration.find_relevant_documents_rag(
        "kỹ năng quản lý thời gian pomodoro", top_k=5, use_warehouse_data=False, mode="REAL_LMS"
    )
    assert docs == [], (
        "Không còn tài liệu nào trong _init_enhanced_knowledge_base tự nhận "
        "APPROVED — REAL_LMS mode phải trả về rỗng cho tới khi có người duyệt "
        "thật qua document_approval_service."
    )



def test_clear_query_gets_trimmed_by_relative_threshold(llm_integration):
    """Truy vấn có 1 tài liệu vượt trội rõ rệt -> lọc tương đối (85% điểm top-1)
    phải loại bớt các tài liệu yếu hơn nhiều, KHÔNG trả nguyên top_k mù quáng."""
    docs = llm_integration.find_relevant_documents_rag(
        "quản lý thời gian học tập hàng tuần", top_k=5, use_warehouse_data=False
    )
    assert len(docs) < 5
    assert docs[0]["title"] == "Kỹ năng quản lý thời gian"


def test_relevance_score_present_and_descending(llm_integration):
    docs = llm_integration.find_relevant_documents_rag(
        "xác suất thống kê", top_k=5, use_warehouse_data=False
    )
    scores = [d["relevance_score"] for d in docs]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(s, float) for s in scores)


def test_top_k_respected_as_ceiling(llm_integration):
    docs = llm_integration.find_relevant_documents_rag(
        "phương pháp học và ôn tập hiệu quả, kỹ năng làm bài kiểm tra",
        top_k=2, use_warehouse_data=False,
    )
    assert len(docs) <= 2


def test_default_top_k_matches_config():
    assert dss_config.RAG_TOP_K_DEFAULT == 5


# ---------------------------------------------------------------------------
# rag_service.retrieve_documents — wrapper tương thích ngược
# ---------------------------------------------------------------------------
def test_rag_service_delegates_to_provider(llm_integration):
    from dss.services import rag_service
    docs = rag_service.retrieve_documents(
        llm_integration, "lập trình, coding, thực hành", top_k=3, use_warehouse_data=False
    )
    assert len(docs) >= 1


def test_rag_service_falls_back_when_provider_lacks_runtime_documents_param():
    """MultiAIProvider cache CŨ (từ @st.cache_resource trước khi runtime_documents
    được thêm vào) không nhận tham số này — rag_service phải tự bắt TypeError và
    gọi lại KHÔNG kèm tham số đó, không được để lỗi văng ra ngoài."""
    from dss.services import rag_service

    class _OldProviderWithoutRuntimeDocsSupport:
        def find_relevant_documents_rag(self, query_text, top_k, embedding_model_name, hf_token, use_warehouse_data):
            return [{"title": "fallback-path-used", "content": "", "tags": []}]

    docs = rag_service.retrieve_documents(
        _OldProviderWithoutRuntimeDocsSupport(), "câu hỏi bất kỳ", top_k=3,
        runtime_documents=[{"id": "x"}],
    )
    assert docs == [{"title": "fallback-path-used", "content": "", "tags": []}]
