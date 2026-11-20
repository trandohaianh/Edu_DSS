"""Document Approval Service — quy trình duyệt tài liệu RAG (NHÓM F).

Tài liệu tải lên (`document_ingestion.ingest_document`) LUÔN bắt đầu ở
PENDING_REVIEW (xem `document_governance`). Module này là NƠI DUY NHẤT được
phép chuyển trạng thái đó sang APPROVED/REJECTED/RETIRED — có kiểm tra thẩm
quyền theo vai trò/loại tài liệu, chặn tự duyệt tài liệu của chính mình, và
ghi audit log cho mọi quyết định.

Không có UI (`st.*`) ở đây — hàm thuần, gọi được trực tiếp từ test và từ
`dss/tabs/knowledge_base.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from dss.core.logging_config import get_logger
from dss.services import document_governance as gov
from dss.services import vector_store as vector_store_module
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

_logger = get_logger(__name__)


def _resolve_organization_id_best_effort() -> Optional[int]:
    """Cùng cách 'best effort' các service khác đã dùng (vd. model_registry) —
    không chặn hành động nếu chưa cấu hình tenant."""
    try:
        import os

        raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _lecturer_owns_course(actor_username: str, course_id: Optional[str]) -> bool:
    """Kiểm tra BEST-EFFORT: giảng viên `actor_username` có đứng tên
    `lecturer_id` ở ÍT NHẤT 1 bài giảng thuộc `course_id` trong CMS hay không.

    HẠN CHẾ ĐÃ BIẾT (ghi rõ, không giấu): hệ thống hiện KHÔNG có một bảng phân
    công "giảng viên X phụ trách môn Y" độc lập — `lecturer_id` chỉ được ghi
    nhận theo TỪNG bài giảng tại thời điểm giảng viên đó tự tải bài giảng lên
    (`cms_lecture_repository.CMSLesson.lecturer_id`). Vì vậy đây là kiểm tra
    "đã từng đứng tên dạy môn này trong CMS", không phải xác nhận phân công
    chính thức từ Phòng Đào tạo. Nếu course_id trống hoặc CMS không có bài
    giảng nào của môn đó, trả False (an toàn hơn — từ chối thay vì đoán bừa).
    """
    if not course_id:
        return False
    try:
        from dss.services import cms_lecture_repository

        lessons = cms_lecture_repository.list_lessons(course_id=course_id)
        return any(lesson.lecturer_id == actor_username for lesson in lessons)
    except Exception:
        _logger.warning(
            "Không thể xác minh giảng viên '%s' có phụ trách môn '%s' qua CMS — từ chối an toàn.",
            actor_username,
            course_id,
        )
        return False


def _get_document_meta(namespace: str, document_id: str) -> Optional[Dict[str, Any]]:
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    for doc in vstore.list_documents():
        if doc.get("document_id") == document_id:
            return doc
    return None


def list_pending_documents(namespace: str = NAMESPACE_STUDENT_LEARNING) -> List[Dict[str, Any]]:
    """Danh sách tài liệu đang chờ duyệt (status == PENDING_REVIEW) trong 1
    namespace — dùng cho hàng đợi "Chờ duyệt" ở tab Quản lý tri thức."""
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    return [d for d in vstore.list_documents() if d.get("status") == gov.STATUS_PENDING_REVIEW]


def list_pending_documents_for_approver(
    namespace: str,
    *,
    actor_username: str,
    actor_role: str,
) -> List[Dict[str, Any]]:
    """Như `list_pending_documents`, nhưng lọc thêm CHỈ những tài liệu
    `actor` thực sự có thẩm quyền duyệt (dùng cho hàng đợi hẹp của Giảng
    viên — mỗi Giảng viên chỉ nên thấy tài liệu môn mình phụ trách, không
    phải toàn bộ hàng đợi hệ thống).

    LƯU Ý AN TOÀN: đây CHỈ là bộ lọc hiển thị (giảm nhiễu UI) — KHÔNG phải
    biên bảo mật. `approve_document`/`reject_document` tự kiểm tra lại
    `can_approve_document` một cách độc lập, nên dù bộ lọc này có sai/bị bỏ
    qua, backend vẫn từ chối hành động không được phép (fail-closed)."""
    pending = list_pending_documents(namespace)
    return [
        d
        for d in pending
        if can_approve_document(
            actor_username=actor_username,
            actor_role=actor_role,
            doc_type=d.get("doc_type"),
            course_id=d.get("course_id"),
            uploaded_by=d.get("uploaded_by"),
        )[0]
    ]


def can_approve_document(
    *,
    actor_username: str,
    actor_role: str,
    doc_type: Optional[str],
    course_id: Optional[str],
    uploaded_by: Optional[str],
) -> Tuple[bool, str]:
    """Kiểm tra thuần (không I/O ghi) xem `actor` có được phép duyệt tài liệu
    này không. Trả (được_phép, lý_do_nếu_từ_chối)."""
    if uploaded_by and actor_username == uploaded_by:
        return False, "Không được tự duyệt tài liệu do chính mình tải lên."
    normalized_type = gov.normalize_doc_type(doc_type)
    if not gov.can_approve_doc_type(actor_role, normalized_type):
        return False, f"Vai trò '{actor_role}' không có thẩm quyền duyệt loại tài liệu '{normalized_type}'."
    if actor_role == "Giảng viên / CVHT" and not _lecturer_owns_course(actor_username, course_id):
        return False, "Chưa xác định được bạn phụ trách môn học này trong CMS — liên hệ Admin để duyệt."
    return True, ""


def approve_document(
    *,
    document_id: str,
    namespace: str,
    actor_username: str,
    actor_role: str,
    review_note: Optional[str] = None,
) -> Tuple[bool, str]:
    """Duyệt 1 tài liệu — chuyển status PENDING_REVIEW -> APPROVED, ghi
    approved_by/approved_at, và ghi 1 bản audit log. Trả (thành_công, thông_báo)."""
    doc_meta = _get_document_meta(namespace, document_id)
    if doc_meta is None:
        return False, f"Không tìm thấy tài liệu '{document_id}' trong không gian '{namespace}'."

    allowed, reason = can_approve_document(
        actor_username=actor_username,
        actor_role=actor_role,
        doc_type=doc_meta.get("doc_type"),
        course_id=doc_meta.get("course_id"),
        uploaded_by=doc_meta.get("uploaded_by"),
    )
    if not allowed:
        return False, reason

    now_iso = datetime.now(UTC).isoformat()
    vstore = vector_store_module.get_vector_store(namespace=namespace)
    updated = vstore.update_document_metadata(
        document_id,
        {
            "status": gov.STATUS_APPROVED,
            "approved_by": actor_username,
            "approved_at": now_iso,
            "review_note": review_note,
        },
    )
    if not updated:
        return False, "Cập nhật trạng thái thất bại (tài liệu có thể đã bị xóa)."

    _record_audit(
        action="document.approved",
        document_id=document_id,
        actor_username=actor_username,
        before={"status": doc_meta.get("status")},
        after={"status": gov.STATUS_APPROVED, "review_note": review_note},
    )
    return True, f"Đã duyệt tài liệu '{document_id}'."


def reject_document(
    *,
    document_id: str,
    namespace: str,
    actor_username: str,
    actor_role: str,
    review_note: str,
) -> Tuple[bool, str]:
    """Từ chối 1 tài liệu — chuyển status sang REJECTED. `review_note` là BẮT
    BUỘC (lý do từ chối), khác `approve_document` (ghi chú là tuỳ chọn)."""
    if not review_note or not review_note.strip():
        return False, "Phải ghi rõ lý do từ chối."

    doc_meta = _get_document_meta(namespace, document_id)
    if doc_meta is None:
        return False, f"Không tìm thấy tài liệu '{document_id}' trong không gian '{namespace}'."

    allowed, reason = can_approve_document(
        actor_username=actor_username,
        actor_role=actor_role,
        doc_type=doc_meta.get("doc_type"),
        course_id=doc_meta.get("course_id"),
        uploaded_by=doc_meta.get("uploaded_by"),
    )
    if not allowed:
        return False, reason

    vstore = vector_store_module.get_vector_store(namespace=namespace)
    updated = vstore.update_document_metadata(
        document_id,
        {
            "status": gov.STATUS_REJECTED,
            "approved_by": None,
            "approved_at": None,
            "review_note": review_note,
        },
    )
    if not updated:
        return False, "Cập nhật trạng thái thất bại (tài liệu có thể đã bị xóa)."

    _record_audit(
        action="document.rejected",
        document_id=document_id,
        actor_username=actor_username,
        before={"status": doc_meta.get("status")},
        after={"status": gov.STATUS_REJECTED, "review_note": review_note},
    )
    return True, f"Đã từ chối tài liệu '{document_id}'."


def retire_document(
    *,
    document_id: str,
    namespace: str,
    actor_username: str,
    actor_role: str,
    review_note: Optional[str] = None,
) -> Tuple[bool, str]:
    """Rút một tài liệu ĐÃ DUYỆT khỏi lưu hành (vd. hết hiệu lực, bị thay thế) —
    chuyển status sang RETIRED. Chỉ Admin hoặc chính giảng viên phụ trách được
    rút; không cần kiểm tra "tự duyệt" vì đây là hành động RÚT, không phải
    duyệt mới."""
    doc_meta = _get_document_meta(namespace, document_id)
    if doc_meta is None:
        return False, f"Không tìm thấy tài liệu '{document_id}' trong không gian '{namespace}'."

    normalized_type = gov.normalize_doc_type(doc_meta.get("doc_type"))
    if not gov.can_approve_doc_type(actor_role, normalized_type):
        return False, f"Vai trò '{actor_role}' không có thẩm quyền rút loại tài liệu '{normalized_type}'."

    vstore = vector_store_module.get_vector_store(namespace=namespace)
    updated = vstore.update_document_metadata(
        document_id,
        {
            "status": gov.STATUS_RETIRED,
            "review_note": review_note,
        },
    )
    if not updated:
        return False, "Cập nhật trạng thái thất bại (tài liệu có thể đã bị xóa)."

    _record_audit(
        action="document.retired",
        document_id=document_id,
        actor_username=actor_username,
        before={"status": doc_meta.get("status")},
        after={"status": gov.STATUS_RETIRED, "review_note": review_note},
    )
    return True, f"Đã rút tài liệu '{document_id}' khỏi lưu hành."


def _record_audit(*, action: str, document_id: str, actor_username: str, before: dict, after: dict) -> None:
    """Ghi audit log — KHÔNG BAO GIỜ chặn hành động duyệt/từ chối nếu ghi audit
    thất bại (giống mọi service khác đang dùng audit_log_repository)."""
    try:
        from dss.db.repositories import audit_log_repository

        audit_log_repository.record(
            action=action,
            target_type="document",
            target_id=document_id,
            actor_username=actor_username,
            organization_id=_resolve_organization_id_best_effort(),
            before=before,
            after=after,
        )
    except Exception:
        _logger.warning("Không ghi được audit log cho hành động '%s' trên tài liệu '%s'.", action, document_id)
