"""FINAL REMEDIATION PASS (đợt 2, đọc lập review) — Mục 2: `_run_compare_ai`
("So sánh AI") và nút chính "Tạo Kế hoạch Học tập" đều đi tới
`MultiAIProvider.generate_personalized_advice` (dss/core/models.py) để lấy
NỘI DUNG TÀI LIỆU THẬT SỰ đưa vào prompt — hàm này trước đây tự gọi
`self.find_relevant_documents_rag` (đường RAG CŨ, đọc thẳng 19 tài liệu viết
cứng trong `_init_enhanced_knowledge_base`, KHÔNG lọc theo trạng thái duyệt
khi không chạy REAL_LMS mode). Điều này RỘNG hơn những gì REPORT.md Mục 8.5
điểm 4/5 đã ghi (chỉ nêu `_run_compare_ai`) — closure `_find_docs_rag_safe`
trong ai_advisor.py (đã rewiring ở đợt NHÓM F đầu) CHỈ phục vụ khung
"Bằng chứng & Nguồn tham khảo" xem trước, KHÔNG phải nguồn tài liệu thật được
đưa vào prompt sinh kế hoạch.

Test dưới đây xác nhận sau khi sửa (models.py: generate_personalized_advice
gọi rag_service.retrieve_unified_context thay vì find_relevant_documents_rag):
1. Đường CŨ (`find_relevant_documents_rag`) KHÔNG còn được gọi.
2. Tài liệu PENDING_REVIEW/REJECTED không bao giờ lọt vào relevant_docs dù
   khớp nội dung gần tuyệt đối; tài liệu APPROVED thì có.
3. `role` truyền từ nơi gọi (Sinh viên/Giảng viên) được chuyển đúng xuống
   `retrieve_unified_context` (ảnh hưởng namespace được phép truy cập).

Dùng model embedding THẬT (giống test_rag_service.py, test_rag_retrieve_unified_context.py)."""

from __future__ import annotations

import pytest

import dss.config as dss_config
from dss.services import document_approval_service as approval
from dss.services import vector_store as vector_store_module
from dss.services.document_ingestion import ingest_document
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider

    provider = MultiAIProvider()
    provider.get_embedding("khởi động model")
    return provider


@pytest.fixture(autouse=True)
def _isolated_vector_store(tmp_path, monkeypatch):
    from dss.services.vector_store import LocalVectorStore

    def _fake_get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING, force_local=False):
        return LocalVectorStore(base_dir=str(tmp_path), namespace=namespace)

    monkeypatch.setattr(vector_store_module, "get_vector_store", _fake_get_vector_store)
    return tmp_path


def _seed_document(
    llm_integration,
    *,
    title,
    content,
    status,
    uploaded_by="gv_a",
    doc_type="bai_giang",
    namespace=NAMESPACE_STUDENT_LEARNING,
    course_id="CS101",
):
    ingested = ingest_document(
        file_bytes=content.encode("utf-8"),
        file_name=f"{title}.txt",
        title=title,
        course_id=course_id,
        permission_scope=namespace,
        uploaded_by=uploaded_by,
        doc_type=doc_type,
    )
    for c in ingested.chunks:
        c.embedding = llm_integration.get_embedding(c.content)
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    vstore.add_chunks(ingested.chunks)

    if status == "APPROVED":
        approval.approve_document(
            document_id=ingested.document_id,
            namespace=namespace,
            actor_username="admin_1",
            actor_role="Admin",
        )
    elif status == "REJECTED":
        approval.reject_document(
            document_id=ingested.document_id,
            namespace=namespace,
            actor_username="admin_1",
            actor_role="Admin",
            review_note="test",
        )
    return ingested.document_id


def _drain(gen):
    """Chạy hết generator để đảm bảo phần truy xuất RAG (trước lời gọi
    call_ai_provider) đã thực thi. KHÔNG được nuốt exception ở đây — provider
    "gemini" không có API key chỉ YIELD một chuỗi lỗi (không raise), nên nếu
    có exception thật sự xảy ra (vd. AssertionError từ spy trong test) nó PHẢI
    làm test fail, không được âm thầm biến mất."""
    return list(gen)


def test_generate_personalized_advice_does_not_use_legacy_knowledge_base(llm_integration, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError(
            "generate_personalized_advice() KHÔNG được gọi find_relevant_documents_rag "
            "(đường RAG cũ, đọc 19 tài liệu viết cứng không qua lọc quản trị) nữa."
        )

    monkeypatch.setattr(type(llm_integration), "find_relevant_documents_rag", _boom)
    _drain(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
        )
    )


def test_generate_personalized_advice_only_cites_approved_documents(llm_integration, monkeypatch):
    captured = {}
    real_prepare = type(llm_integration)._prepare_personalized_advice_prompt

    def _spy(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=None):
        captured["relevant_docs"] = relevant_docs
        return real_prepare(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=student_profile)

    monkeypatch.setattr(type(llm_integration), "_prepare_personalized_advice_prompt", _spy)

    _seed_document(
        llm_integration,
        title="Quản lý thời gian (CHƯA duyệt)",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả, chia nhỏ thời gian ôn tập.",
        status="PENDING_REVIEW",
    )
    approved_id = _seed_document(
        llm_integration,
        title="Quản lý thời gian (đã duyệt)",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả, chia nhỏ thời gian ôn tập.",
        status="APPROVED",
    )

    _drain(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
        )
    )

    docs = captured.get("relevant_docs") or []
    assert docs, "Phải có ít nhất 1 tài liệu ĐÃ DUYỆT được trích dẫn cho truy vấn khớp nội dung."
    assert all(d.get("status") == "APPROVED" for d in docs), (
        "relevant_docs đưa vào prompt lẫn tài liệu chưa duyệt (PENDING_REVIEW)."
    )
    assert any(d.get("document_id") == approved_id for d in docs)


def test_generate_personalized_advice_rejected_document_never_cited(llm_integration, monkeypatch):
    captured = {}
    real_prepare = type(llm_integration)._prepare_personalized_advice_prompt

    def _spy(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=None):
        captured["relevant_docs"] = relevant_docs
        return real_prepare(self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=student_profile)

    monkeypatch.setattr(type(llm_integration), "_prepare_personalized_advice_prompt", _spy)

    _seed_document(
        llm_integration,
        title="Quản lý thời gian (đã từ chối)",
        content="Phương pháp Pomodoro giúp quản lý thời gian học tập hiệu quả, chia nhỏ thời gian ôn tập.",
        status="REJECTED",
    )

    _drain(
        llm_integration.generate_personalized_advice(
            student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
            predicted_gpa=5.0,
            provider="gemini",
            use_rag=True,
            student_profile={},
            role="Sinh viên",
        )
    )

    docs = captured.get("relevant_docs") or []
    assert docs == [], "Tài liệu REJECTED không bao giờ được trích dẫn, kể cả khi không có tài liệu nào khác."


def test_compare_ai_role_is_forwarded_to_unified_retrieval(llm_integration, monkeypatch):
    """`_run_compare_ai` (ai_advisor.py) -> llm_service.compare_providers ->
    _run_one_provider -> generate_personalized_advice: `role` phải được
    chuyển tay xuống tới đây (không âm thầm rơi về mặc định "Sinh viên"),
    quyết định namespace nào retrieve_unified_context được phép truy cập."""
    from dss.services import llm_service

    seen_roles = []
    real_gpa = type(llm_integration).generate_personalized_advice

    def _spy_gpa(self, *args, **kwargs):
        seen_roles.append(kwargs.get("role"))
        return real_gpa(self, *args, **kwargs)

    monkeypatch.setattr(type(llm_integration), "generate_personalized_advice", _spy_gpa)

    results = llm_service.compare_providers(
        llm_integration,
        [{"provider_key": "gemini", "provider_label": "Google Gemini", "model_name": "x", "call_kwargs": {}}],
        student_weaknesses=["Quản lý thời gian (SV: 3, TB lớp: 7)"],
        predicted_gpa=5.0,
        student_profile={},
        role="Giảng viên / CVHT",
    )
    assert len(results) == 1
    assert seen_roles == ["Giảng viên / CVHT"], (
        f"role không được chuyển đúng xuống generate_personalized_advice: {seen_roles}"
    )
