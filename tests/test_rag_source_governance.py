"""Test Suite: RAG Source Governance (Mục B — UI/RAG consistency pass phần 2).

Không lặp lại các test đã có ở test_learning_explainer.py/
test_learning_explainer_acceptance.py (namespace isolation, citation hygiene
cơ bản...) — chỉ phủ đúng những bất biến MỚI của yêu cầu lần này: phân loại
nguồn tập trung áp dụng lên chunk CMS thật, Demo Knowledge không bao giờ trở
thành nguồn cho câu trả lời Learning Explainer, trích dẫn có ngữ cảnh môn
học, và cách ly xuyên môn ở tầng pipeline đầy đủ (generate_explanation), không
chỉ ở tầng retrieve_lesson_content thô."""
from __future__ import annotations

import uuid

import pytest

import dss.config as dss_config
from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer
from dss.services import source_classification as srcclass


@pytest.fixture(scope="module")
def llm_integration():
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider
    provider = MultiAIProvider()
    provider.get_embedding("khởi động model")
    return provider


@pytest.fixture()
def unique_course():
    suffix = uuid.uuid4().hex[:8]
    return f"GOV_COURSE_{suffix}"


def _ingest(llm_integration, course_id, lesson_id, topic_id, content: str, title: str, section: str = "slide 1"):
    return cms_repository.ingest_lecture_material(
        file_bytes=content.encode("utf-8"), file_name=f"{lesson_id}.txt", title=title,
        course_id=course_id, lesson_id=lesson_id, topic_id=topic_id, lecturer_id="GV_GOV_TEST",
        llm_integration=llm_integration, learning_outcome="Test outcome", difficulty="Standard",
        content_type="slide", page_or_section=section,
    )


# ---------------------------------------------------------------------------
# 1. Chunk CMS thật -> phân loại COURSE_MATERIAL qua bộ phân loại tập trung
# ---------------------------------------------------------------------------
def test_real_cms_chunk_metadata_classifies_as_course_material(llm_integration, unique_course):
    lesson_id = f"lesson_gov_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "governance", "Nội dung kiểm thử phân loại nguồn.", "Bài Governance")
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "kiểm thử", course_id=unique_course, lesson_id=lesson_id, top_k=3,
    )
    assert chunks, "Cần retrieve được ít nhất 1 chunk để kiểm tra phân loại."
    meta = chunks[0].get("metadata", {})
    assert srcclass.classify_document(meta) == srcclass.COURSE_MATERIAL


# ---------------------------------------------------------------------------
# 2. Demo Knowledge (19 tài liệu) không bao giờ là nguồn cho câu trả lời
#    Learning Explainer, kể cả khi không có tài liệu môn học nào khớp.
# ---------------------------------------------------------------------------
def test_generate_explanation_never_falls_back_to_demo_knowledge_base(llm_integration, unique_course):
    """Hỏi 1 câu hoàn toàn KHÔNG có tài liệu CMS nào khớp (bài học chưa từng
    tồn tại) -> phải là trạng thái insufficient-evidence trung thực, TUYỆT ĐỐI
    không lộ nội dung của 19 tài liệu demo (GEN_REF) vào câu trả lời."""
    fake_lesson_id = f"lesson_never_exists_{uuid.uuid4().hex[:8]}"
    result = learning_explainer.generate_explanation(
        llm_integration, "Làm sao để học tốt hơn?", unique_course, fake_lesson_id, None, "Standard",
    )
    assert result.has_cms_content is False
    # Không được chứa tiêu đề của bất kỳ tài liệu demo nào (vd "Hướng dẫn học
    # Toán cao cấp", "Kỹ năng quản lý thời gian"...) -- nếu có nghĩa là đã lộ
    # nội dung demo vào câu trả lời của Learning Explainer.
    demo_doc_titles = [
        "Hướng dẫn học Toán cao cấp", "Cải thiện điểm Lập trình", "Kỹ năng quản lý thời gian",
    ]
    for title in demo_doc_titles:
        assert title not in result.answer
    assert not result.citations


# ---------------------------------------------------------------------------
# 3. Trích dẫn có ngữ cảnh môn học (Mục B9) khi có course_id
# ---------------------------------------------------------------------------
def test_citation_includes_course_context(llm_integration, unique_course):
    lesson_id = f"lesson_cite_ctx_{uuid.uuid4().hex[:8]}"
    _ingest(llm_integration, unique_course, lesson_id, "citation", "Nội dung kiểm thử trích dẫn có ngữ cảnh môn.", "Bài Citation Context", section="slide 5-7")
    chunks = cms_repository.retrieve_lesson_content(
        llm_integration, "kiểm thử", course_id=unique_course, lesson_id=lesson_id, top_k=3,
    )
    citation = learning_explainer._format_friendly_citation(chunks[0])
    assert "slide 5-7" in citation.label
    assert unique_course in citation.label
    assert "chunk_" not in citation.label
    assert "vector" not in citation.label.lower()


# ---------------------------------------------------------------------------
# 4. Cách ly xuyên môn ở tầng pipeline ĐẦY ĐỦ (generate_explanation), không
#    chỉ ở tầng retrieve_lesson_content thô (Mục B13).
# ---------------------------------------------------------------------------
def test_cross_course_isolation_at_full_pipeline_level(llm_integration):
    course_a = f"GOV_ML_{uuid.uuid4().hex[:8]}"
    course_b = f"GOV_HIST_{uuid.uuid4().hex[:8]}"
    lesson_a = f"lesson_a_{uuid.uuid4().hex[:8]}"
    lesson_b = f"lesson_b_{uuid.uuid4().hex[:8]}"

    _ingest(llm_integration, course_a, lesson_a, "ml", "K-Means là thuật toán phân cụm không giám sát, dùng khoảng cách Euclid.", "Bài 4 - K-Means")
    _ingest(llm_integration, course_b, lesson_b, "history", "Chiến tranh thế giới thứ hai kết thúc năm 1945.", "Bài 4 - Lịch sử Thế chiến 2")

    result = learning_explainer.generate_explanation(
        llm_integration, "K-Means là gì?", course_a, lesson_a, "ml", "Standard",
    )
    assert result.has_cms_content is True
    for citation in result.citations:
        assert course_b not in citation.label
        assert "Lịch sử Thế chiến" not in citation.label
    assert "1945" not in result.answer
    assert "Chiến tranh thế giới" not in result.answer


# ---------------------------------------------------------------------------
# 5. Bộ phân loại nguồn áp dụng đúng cho toàn bộ 19 tài liệu demo thật (không
#    phải dữ liệu giả lập trong test) -- tổng 2 nhóm phải khớp đúng 19.
# ---------------------------------------------------------------------------
def test_classification_covers_all_19_demo_documents_exhaustively():
    from dss.core.models import MultiAIProvider
    provider = MultiAIProvider()
    documents = provider.knowledge_base.get("documents", [])
    assert len(documents) == 19

    counts = {srcclass.SUPPLEMENTARY_REFERENCE: 0, srcclass.DEMO: 0}
    for doc in documents:
        category = srcclass.classify_document(doc)
        assert category in (srcclass.SUPPLEMENTARY_REFERENCE, srcclass.DEMO), (
            f"Tài liệu demo {doc.get('id')} không nên tự nhận COURSE_MATERIAL/"
            "INSTITUTION_APPROVED -- các tài liệu tĩnh trong core/models.py không "
            "có provenance CMS hay phê duyệt cấp tổ chức thật."
        )
        counts[category] += 1

    # Xác nhận đúng 4/19 tài liệu có nguồn thật đã xác minh (Pomodoro/Feynman/
    # Krashen/Cornell) -- con số này đã được xác nhận trong audit trước đó.
    assert counts[srcclass.SUPPLEMENTARY_REFERENCE] == 4
    assert counts[srcclass.DEMO] == 15
