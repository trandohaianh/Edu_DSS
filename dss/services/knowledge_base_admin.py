"""Admin service for safely deleting a Knowledge Base document.

Both LocalVectorStore and PgVectorStore implement real deletion. Before deleting,
this service protects the CMS relationship described below so a live lesson cannot
silently lose its retrieval source.

A ``document_id``
trong Knowledge Base có thể ĐỒNG THỜI là ``current_document_id`` của một bài
giảng CMS (``dss/services/cms_lecture_repository.py``, dùng bởi Learning
Explainer). Nếu xóa thẳng tài liệu đó khỏi vector store, bài giảng sẽ âm thầm
mất khả năng trích dẫn (retrieval trả về rỗng) trong khi registry bài giảng
(``lessons_registry.json``) vẫn còn trỏ tới ``document_id`` đã biến mất — một
kho dữ liệu THỨ HAI cần giữ nhất quán ngoài vector store. Hàm ở đây CHẶN việc
xóa trong trường hợp đó và hướng người dùng tới cơ chế loại-bỏ-phiên-bản
(``cms_lecture_repository.exclude_document``) đã có sẵn cho đúng tình huống
này, thay vì mở rộng phạm vi thay đổi sang registry bài giảng trong tác vụ
này (ngoài phạm vi được cho phép — "KB delete" đơn thuần).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from dss.services import cms_lecture_repository
from dss.services import vector_store as vector_store_module
from dss.services.auth_service import require_role
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

STATUS_SUCCESS = "success"
STATUS_NOT_FOUND = "not_found"
STATUS_ERROR = "error"
STATUS_BLOCKED_REFERENCED = "blocked_referenced"


def _find_lesson_using_document(document_id: str) -> Optional[Any]:
    """Trả về CMSLesson đang dùng `document_id` này làm phiên bản current,
    hoặc None nếu không bài giảng nào tham chiếu tới nó. Lỗi đọc registry
    được coi là "không tìm thấy tham chiếu" (không chặn xóa vì lý do đọc
    thất bại — registry rỗng/hỏng không phải bằng chứng có tham chiếu)."""
    try:
        lessons = cms_lecture_repository.list_lessons()
    except Exception:
        return None
    for lesson in lessons:
        if getattr(lesson, "current_document_id", None) == document_id:
            return lesson
    return None


@require_role("Admin")
def delete_document_safely(document_id: str, namespace: str = NAMESPACE_STUDENT_LEARNING) -> Dict[str, Any]:
    """Xóa 1 tài liệu khỏi Knowledge Base — CHỈ báo `status="success"` khi
    backend đang hoạt động THẬT SỰ đã xóa dữ liệu. Không bao giờ trả về
    thành công giả (fabricated success)."""
    vstore = vector_store_module.get_vector_store(namespace=namespace)

    referencing_lesson = _find_lesson_using_document(document_id)
    if referencing_lesson is not None:
        return {
            "status": STATUS_BLOCKED_REFERENCED,
            "message": (
                f"Tài liệu này đang là phiên bản hiện hành của bài giảng "
                f"\"{referencing_lesson.title}\" "
                f"({referencing_lesson.course_id}/{referencing_lesson.lesson_id}) "
                "trong AI Giải thích Bài giảng. Vui lòng dùng chức năng "
                "\"Loại 1 phiên bản khỏi retrieval\" trong trang Quản lý bài "
                "giảng thay vì xóa trực tiếp tại đây, để tránh bài giảng bị "
                "mất nội dung trích dẫn một cách âm thầm."
            ),
        }

    try:
        deleted = vstore.delete_document(document_id)
    except Exception as exc:  # backend lỗi thật — KHÔNG được hiển thị như thành công
        return {
            "status": STATUS_ERROR,
            "message": f"Lỗi khi xóa tài liệu khỏi Knowledge Base: {exc}",
        }

    if not deleted:
        return {
            "status": STATUS_NOT_FOUND,
            "message": ("Không tìm thấy tài liệu này trong Knowledge Base (có thể đã bị xóa trước đó)."),
        }

    return {"status": STATUS_SUCCESS, "message": "Đã xóa tài liệu khỏi Knowledge Base."}
