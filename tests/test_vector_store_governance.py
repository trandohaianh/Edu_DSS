"""NHÓM F: LocalVectorStore phải hỗ trợ (1) cập nhật metadata quản trị của một
tài liệu ĐÃ lưu (để duyệt/từ chối mà không cần xóa+nạp lại — tốn embedding),
và (2) `list_documents()` phải lộ ra các trường quản trị (status/doc_type/
issuer/approved_by/uploaded_by) để trang "Chờ duyệt" đọc được — trước đây
list_documents() chỉ trả về title/course_id/source/permission_scope/
total_chunks/created_at, không có gì về trạng thái duyệt."""
from __future__ import annotations

import pytest

from dss.services import document_governance as gov
from dss.services.chunking_service import DocumentChunk
from dss.services.vector_store import LocalVectorStore


@pytest.fixture
def store(tmp_path):
    return LocalVectorStore(base_dir=str(tmp_path), namespace="student_learning")


def _make_chunk(doc_id, chunk_idx=1, **meta_overrides):
    meta = {
        "document_id": doc_id,
        "title": "Tài liệu test",
        "course_id": "CS101",
        "permission_scope": "student_learning",
        "uploaded_by": "gv_nguyen",
        "status": gov.STATUS_PENDING_REVIEW,
        "approved_by": None,
        "doc_type": "bai_giang",
        "issuer": "Khoa CNTT",
    }
    meta.update(meta_overrides)
    return DocumentChunk(
        chunk_id=f"{doc_id}#c{chunk_idx}",
        document_id=doc_id,
        course_id="CS101",
        content="Nội dung mẫu.",
        token_count=5,
        metadata=meta,
        embedding=[0.1, 0.2, 0.3],
    )


def test_list_documents_exposes_governance_fields(store):
    store.add_chunks([_make_chunk("doc_a")])
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0]["status"] == gov.STATUS_PENDING_REVIEW
    assert docs[0]["doc_type"] == "bai_giang"
    assert docs[0]["issuer"] == "Khoa CNTT"
    assert docs[0]["uploaded_by"] == "gv_nguyen"
    assert docs[0]["approved_by"] is None


def test_update_document_metadata_updates_all_chunks(store):
    store.add_chunks([_make_chunk("doc_b", 1), _make_chunk("doc_b", 2)])
    ok = store.update_document_metadata("doc_b", {
        "status": gov.STATUS_APPROVED, "approved_by": "admin_x", "approved_at": "2026-01-01T00:00:00+00:00",
    })
    assert ok is True
    docs = store.list_documents()
    assert docs[0]["status"] == gov.STATUS_APPROVED
    assert docs[0]["approved_by"] == "admin_x"


def test_update_document_metadata_persists_across_reload(tmp_path):
    store1 = LocalVectorStore(base_dir=str(tmp_path), namespace="student_learning")
    store1.add_chunks([_make_chunk("doc_c")])
    store1.update_document_metadata("doc_c", {"status": gov.STATUS_APPROVED, "approved_by": "admin_y"})

    store2 = LocalVectorStore(base_dir=str(tmp_path), namespace="student_learning")
    docs = store2.list_documents()
    assert docs[0]["status"] == gov.STATUS_APPROVED
    assert docs[0]["approved_by"] == "admin_y"


def test_update_document_metadata_returns_false_for_unknown_document(store):
    store.add_chunks([_make_chunk("doc_d")])
    assert store.update_document_metadata("doc_does_not_exist", {"status": gov.STATUS_APPROVED}) is False


def test_update_document_metadata_does_not_affect_other_documents(store):
    store.add_chunks([_make_chunk("doc_e"), _make_chunk("doc_f")])
    store.update_document_metadata("doc_e", {"status": gov.STATUS_APPROVED, "approved_by": "admin_z"})
    docs = {d["document_id"]: d for d in store.list_documents()}
    assert docs["doc_e"]["status"] == gov.STATUS_APPROVED
    assert docs["doc_f"]["status"] == gov.STATUS_PENDING_REVIEW
