"""NHÓM F: document_governance — trạng thái phê duyệt & thẩm quyền tài liệu RAG.

Kiểm tra bộ lọc CỨNG is_document_usable (chỉ tài liệu APPROVED thật, có người
duyệt, chưa hết hạn, đã tới hiệu lực, nội dung không bị sửa sau khi duyệt mới
được dùng làm căn cứ trích dẫn) và quy tắc thẩm quyền duyệt theo vai trò/loại
tài liệu."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dss.services import document_governance as gov


def _approved_meta(**overrides):
    meta = {
        "status": gov.STATUS_APPROVED,
        "approved_by": "admin_user",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "content_hash": "abc123",
    }
    meta.update(overrides)
    return meta


def test_pending_review_document_not_usable():
    meta = {"status": gov.STATUS_PENDING_REVIEW, "approved_by": None}
    assert gov.is_document_usable(meta) is False


def test_rejected_document_not_usable():
    meta = {"status": gov.STATUS_REJECTED, "approved_by": "admin"}
    assert gov.is_document_usable(meta) is False


def test_retired_document_not_usable():
    meta = {"status": gov.STATUS_RETIRED, "approved_by": "admin"}
    assert gov.is_document_usable(meta) is False


def test_approved_but_missing_approved_by_not_usable():
    """Phòng trường hợp status="APPROVED" bị gán tay/lỗi mà không qua quy trình
    duyệt thật (đúng lỗi F-0b) — PHẢI có approved_by mới được coi là hợp lệ."""
    meta = {"status": gov.STATUS_APPROVED, "approved_by": None}
    assert gov.is_document_usable(meta) is False


def test_approved_with_approver_is_usable():
    assert gov.is_document_usable(_approved_meta()) is True


def test_expired_document_not_usable():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    meta = _approved_meta(expires_at=past)
    assert gov.is_document_usable(meta) is False


def test_not_yet_effective_document_not_usable():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    meta = _approved_meta(effective_from=future)
    assert gov.is_document_usable(meta) is False


def test_document_within_effective_window_is_usable():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    meta = _approved_meta(effective_from=past, expires_at=future)
    assert gov.is_document_usable(meta) is True


def test_content_hash_mismatch_not_usable():
    """Tài liệu bị sửa nội dung SAU khi duyệt (content_hash không khớp nữa) —
    không còn hợp lệ cho tới khi duyệt lại."""
    meta = _approved_meta(content_hash="hash-at-approval-time")
    assert gov.is_document_usable(meta, expected_content_hash="hash-after-edit") is False


def test_content_hash_match_still_usable():
    meta = _approved_meta(content_hash="same-hash")
    assert gov.is_document_usable(meta, expected_content_hash="same-hash") is True


def test_admin_can_approve_any_doc_type():
    for dt in gov.ALL_DOC_TYPES:
        assert gov.can_approve_doc_type("Admin", dt) is True


def test_lecturer_can_only_approve_course_material_types():
    assert gov.can_approve_doc_type("Giảng viên / CVHT", gov.DOC_TYPE_BAI_GIANG) is True
    assert gov.can_approve_doc_type("Giảng viên / CVHT", gov.DOC_TYPE_GIAO_TRINH) is True
    assert gov.can_approve_doc_type("Giảng viên / CVHT", gov.DOC_TYPE_DE_CUONG) is True
    assert gov.can_approve_doc_type("Giảng viên / CVHT", gov.DOC_TYPE_QUY_CHE) is False
    assert gov.can_approve_doc_type("Giảng viên / CVHT", gov.DOC_TYPE_FAQ_CHINH_THUC) is False


def test_student_can_never_approve():
    for dt in gov.ALL_DOC_TYPES:
        assert gov.can_approve_doc_type("Sinh viên", dt) is False


def test_default_governance_metadata_always_starts_pending_review():
    meta = gov.default_governance_metadata(
        doc_type="bai_giang", issuer="Khoa CNTT", official_ref="QD-123",
        content_hash="h1",
    )
    assert meta["status"] == gov.STATUS_PENDING_REVIEW
    assert meta["approved_by"] is None
    assert meta["approved_at"] is None


def test_default_governance_metadata_normalizes_unknown_doc_type():
    meta = gov.default_governance_metadata(
        doc_type="loai_khong_ton_tai", issuer="", official_ref=None, content_hash="h1",
    )
    assert meta["doc_type"] == gov.DOC_TYPE_HUONG_DAN_HOC_TAP


def test_compute_content_hash_deterministic_and_sensitive_to_content():
    h1 = gov.compute_content_hash("nội dung A")
    h2 = gov.compute_content_hash("nội dung A")
    h3 = gov.compute_content_hash("nội dung B")
    assert h1 == h2
    assert h1 != h3
