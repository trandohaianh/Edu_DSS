"""RAG Namespaces — Phân tách các không gian tri thức theo vai trò trong LMS.

Tuyệt đối KHÔNG gộp chung toàn bộ tri thức vào một kho duy nhất:
1. `student_learning`:
   - Tài liệu học tập chính quy, giáo trình, bài giảng, đề cương (syllabus)
   - Phương pháp học, kỹ năng ôn thi, tài liệu bổ trợ
   - Hỏi đáp thường gặp (FAQ) môn học
2. `lecturer_support`:
   - Tài liệu nghiệp vụ giảng dạy, sư phạm
   - Hướng dẫn can thiệp sư phạm cho sinh viên có nguy cơ rớt môn
   - Bối cảnh phân tích học tập toàn lớp (class analytics context)
3. `admin_operations`:
   - Tài liệu kỹ thuật, kiến trúc hệ thống, runbook vận hành
   - Nhật ký kiểm toán, metadata Model Registry, báo cáo drift mô hình
   - Cấu hình hạ tầng, chỉ số tài nguyên và bảo trì

NGUYÊN TẮC BẤT BIẾN:
Hồ sơ cá nhân sinh viên (điểm số, GPA, thông tin nhận dạng) TUYỆT ĐỐI KHÔNG
được lưu thành tài liệu trong RAG. Bối cảnh sinh viên được truyền riêng rẽ
dưới dạng StudentContext có cấu trúc, đã khử PII.
"""
from __future__ import annotations

from typing import List, Set

NAMESPACE_STUDENT_LEARNING = "student_learning"
NAMESPACE_LECTURER_SUPPORT = "lecturer_support"
NAMESPACE_ADMIN_OPERATIONS = "admin_operations"

ALL_NAMESPACES = [
    NAMESPACE_STUDENT_LEARNING,
    NAMESPACE_LECTURER_SUPPORT,
    NAMESPACE_ADMIN_OPERATIONS,
]

# Ánh xạ quyền truy cập Namespace theo vai trò người dùng (RBAC)
ROLE_TO_ALLOWED_NAMESPACES = {
    "Sinh viên": {NAMESPACE_STUDENT_LEARNING},
    "Giảng viên / CVHT": {NAMESPACE_STUDENT_LEARNING, NAMESPACE_LECTURER_SUPPORT},
    "Admin": {NAMESPACE_STUDENT_LEARNING, NAMESPACE_LECTURER_SUPPORT, NAMESPACE_ADMIN_OPERATIONS},
}


def get_allowed_namespaces_for_role(role: str) -> Set[str]:
    """Lấy danh sách các namespace mà vai trò hiện tại được phép truy cập."""
    return ROLE_TO_ALLOWED_NAMESPACES.get(role, {NAMESPACE_STUDENT_LEARNING})


def is_namespace_allowed(role: str, namespace: str) -> bool:
    """Kiểm tra quyền truy cập vào 1 namespace cụ thể."""
    allowed = get_allowed_namespaces_for_role(role)
    return namespace in allowed


def validate_student_profile_not_in_knowledge(doc_data: dict) -> None:
    """Bảo vệ kiến trúc: Chặn việc vô tình lưu hồ sơ sinh viên thành tài liệu tri thức."""
    title = str(doc_data.get("title", "")).lower()
    content = str(doc_data.get("content", "")).lower()
    doc_id = str(doc_data.get("id") or doc_data.get("document_id") or "").lower()

    suspicious_markers = [
        "bảng điểm sinh viên",
        "hồ sơ sinh viên",
        "danh sách lớp",
        "kết quả học tập cá nhân",
        "student_profile",
    ]

    for marker in suspicious_markers:
        if marker in title or marker in doc_id:
            raise ValueError(
                f"VI PHẠM NGUYÊN TẮC BẢO MẬT: Hồ sơ sinh viên ('{marker}') không được lưu thành "
                "tài liệu tri thức trong Vector Store. Phải truyền qua StudentContext riêng biệt."
            )
