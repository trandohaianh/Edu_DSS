"""Document Governance — trạng thái phê duyệt & thẩm quyền cho tài liệu RAG (NHÓM F).

Nguyên tắc: một tài liệu chỉ được phép dùng làm CĂN CỨ TRÍCH DẪN cho Tư vấn AI/
Giải thích bài giảng khi nó đã đi qua một quy trình duyệt THẬT (có người duyệt,
có bản ghi audit) — KHÔNG BAO GIỜ được tự nhận "đã duyệt" chỉ bằng cách gán cứng
một trường trạng thái trong code (đây chính là lỗi F-0b đã xác minh: 4/19 tài
liệu mẫu tự gắn status="APPROVED" mà không hề có người duyệt).

Module này THUẦN (không import streamlit, không I/O) — dùng chung cho:
- `document_ingestion.ingest_document` (gắn metadata mặc định lúc tải lên)
- `document_approval_service` (kiểm tra quyền duyệt theo vai trò/loại tài liệu)
- `rag_service.retrieve_unified_context` (bộ lọc CỨNG trước khi xếp hạng/cắt top-k)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Trạng thái vòng đời tài liệu
# ---------------------------------------------------------------------------
STATUS_DRAFT = "DRAFT"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_RETIRED = "RETIRED"

ALL_STATUSES = {
    STATUS_DRAFT, STATUS_PENDING_REVIEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_RETIRED,
}

# ---------------------------------------------------------------------------
# Loại tài liệu + thẩm quyền duyệt
# ---------------------------------------------------------------------------
DOC_TYPE_QUY_CHE = "quy_che"
DOC_TYPE_DE_CUONG = "de_cuong"
DOC_TYPE_GIAO_TRINH = "giao_trinh"
DOC_TYPE_BAI_GIANG = "bai_giang"
DOC_TYPE_HUONG_DAN_HOC_TAP = "huong_dan_hoc_tap"
DOC_TYPE_FAQ_CHINH_THUC = "faq_chinh_thuc"

ALL_DOC_TYPES = {
    DOC_TYPE_QUY_CHE, DOC_TYPE_DE_CUONG, DOC_TYPE_GIAO_TRINH,
    DOC_TYPE_BAI_GIANG, DOC_TYPE_HUONG_DAN_HOC_TAP, DOC_TYPE_FAQ_CHINH_THUC,
}

# Loại tài liệu chỉ Admin mới có thẩm quyền duyệt (quy chế/FAQ chính thức cấp trường).
ADMIN_ONLY_DOC_TYPES = {DOC_TYPE_QUY_CHE, DOC_TYPE_FAQ_CHINH_THUC}
# Loại tài liệu Giảng viên phụ trách môn được phép duyệt (giáo trình/bài giảng/đề cương).
LECTURER_APPROVABLE_DOC_TYPES = {DOC_TYPE_GIAO_TRINH, DOC_TYPE_BAI_GIANG, DOC_TYPE_DE_CUONG}


def compute_content_hash(text: str) -> str:
    """SHA-256 của văn bản gốc — dùng để phát hiện tài liệu bị sửa SAU khi đã
    duyệt (nội dung đổi nhưng metadata `status=APPROVED` cũ vẫn còn) — tài liệu
    như vậy KHÔNG được coi là hợp lệ nữa cho tới khi duyệt lại."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_expired(meta: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    exp = _parse_dt(meta.get("expires_at"))
    return exp is not None and exp <= now


def is_not_yet_effective(meta: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    eff = _parse_dt(meta.get("effective_from"))
    return eff is not None and eff > now


def is_document_usable(
    meta: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    expected_content_hash: Optional[str] = None,
) -> bool:
    """CHỈ True khi tài liệu (metadata của 1 chunk) đủ điều kiện được dùng làm
    CĂN CỨ TRÍCH DẪN — đây là bộ lọc CỨNG bắt buộc, không nhờ prompt LLM tự loại.

    Điều kiện (TẤT CẢ):
    - status == APPROVED VÀ có approved_by (không chỉ dán nhãn suông — chống F-0b).
    - Đã tới hiệu lực (effective_from <= now) và chưa hết hạn (expires_at > now
      hoặc không đặt).
    - Nếu có `expected_content_hash` truyền vào (nội dung hiện tại của chunk lúc
      truy xuất): phải khớp `content_hash` đã lưu lúc duyệt — nội dung bị sửa sau
      khi duyệt sẽ bị coi là KHÔNG hợp lệ nữa.
    """
    if meta.get("status") != STATUS_APPROVED:
        return False
    if not meta.get("approved_by"):
        return False
    if is_expired(meta, now=now):
        return False
    if is_not_yet_effective(meta, now=now):
        return False
    if expected_content_hash is not None:
        stored_hash = meta.get("content_hash")
        if stored_hash and stored_hash != expected_content_hash:
            return False
    return True


def can_approve_doc_type(role: str, doc_type: str) -> bool:
    """Admin: mọi loại. Giảng viên: chỉ giáo trình/bài giảng/đề cương. Sinh viên:
    không bao giờ. Loại tài liệu lạ/chưa khai báo: chỉ Admin (an toàn hơn)."""
    if role == "Admin":
        return True
    if role == "Giảng viên / CVHT":
        return doc_type in LECTURER_APPROVABLE_DOC_TYPES
    return False


def normalize_doc_type(doc_type: Optional[str]) -> str:
    return doc_type if doc_type in ALL_DOC_TYPES else DOC_TYPE_HUONG_DAN_HOC_TAP


def default_governance_metadata(
    *,
    doc_type: Optional[str],
    issuer: str,
    official_ref: Optional[str],
    content_hash: str,
    effective_from: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Metadata quản trị MẶC ĐỊNH gắn cho MỌI tài liệu mới nạp — LUÔN bắt đầu ở
    trạng thái PENDING_REVIEW, không có đường nào để tự thành APPROVED."""
    return {
        "doc_type": normalize_doc_type(doc_type),
        "issuer": issuer or "",
        "official_ref": official_ref or "",
        "status": STATUS_PENDING_REVIEW,
        "approved_by": None,
        "approved_at": None,
        "review_note": None,
        "content_hash": content_hash,
        "effective_from": effective_from,
        "expires_at": expires_at,
    }
