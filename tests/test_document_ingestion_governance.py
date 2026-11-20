"""NHÓM F (F-0c CONFIRMED): document_ingestion.ingest_document trước đây KHÔNG
gắn bất kỳ trường trạng thái/thẩm quyền nào — tài liệu tải lên dùng được ngay
lập tức, không qua duyệt. Mọi tài liệu tải lên PHẢI bắt đầu ở PENDING_REVIEW."""

from __future__ import annotations

from dss.services import document_governance as gov
from dss.services.document_ingestion import ingest_document


def _ingest(**kwargs):
    defaults = dict(
        file_bytes="Nội dung tài liệu mẫu để kiểm thử.".encode(),
        file_name="test.txt",
        title="Tài liệu kiểm thử",
        course_id="CS101",
        uploaded_by="gv_nguyen",
    )
    defaults.update(kwargs)
    return ingest_document(**defaults)


def test_ingested_chunk_starts_pending_review_by_default():
    doc = _ingest()
    assert doc.chunks, "Cần ít nhất 1 chunk để kiểm thử metadata"
    for c in doc.chunks:
        assert c.metadata["status"] == gov.STATUS_PENDING_REVIEW
        assert c.metadata["approved_by"] is None
        assert c.metadata["approved_at"] is None


def test_caller_cannot_force_status_approved_via_extra_metadata():
    """Dù người gọi có cố truyền status="APPROVED" qua **extra_metadata, hàm
    PHẢI ép về PENDING_REVIEW — không có đường nào tự duyệt lúc tải lên."""
    doc = _ingest(status="APPROVED", approved_by="ai_tu_xung")
    for c in doc.chunks:
        assert c.metadata["status"] == gov.STATUS_PENDING_REVIEW
        assert c.metadata["approved_by"] is None


def test_ingested_chunk_has_doc_type_issuer_official_ref():
    doc = _ingest(doc_type="bai_giang", issuer="Khoa CNTT", official_ref="QD-45/2026")
    for c in doc.chunks:
        assert c.metadata["doc_type"] == "bai_giang"
        assert c.metadata["issuer"] == "Khoa CNTT"
        assert c.metadata["official_ref"] == "QD-45/2026"


def test_unknown_doc_type_normalized_to_default():
    doc = _ingest(doc_type="khong_hop_le")
    assert doc.chunks[0].metadata["doc_type"] == gov.DOC_TYPE_HUONG_DAN_HOC_TAP


def test_content_hash_matches_raw_text():
    doc = _ingest()
    expected = gov.compute_content_hash(doc.raw_text)
    for c in doc.chunks:
        assert c.metadata["content_hash"] == expected


def test_content_hash_differs_for_different_content():
    doc_a = _ingest(file_bytes="Nội dung A khác nhau hoàn toàn.".encode())
    doc_b = _ingest(file_bytes="Nội dung B khác hẳn nội dung A.".encode())
    assert doc_a.chunks[0].metadata["content_hash"] != doc_b.chunks[0].metadata["content_hash"]
