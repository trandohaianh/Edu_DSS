"""Phân loại nguồn tri thức tập trung (Mục B1 — UI/RAG consistency pass phần
2). MỘT điểm gọi duy nhất quyết định một tài liệu/chunk thuộc nhóm nào — dựa
trên PROVENANCE/METADATA THẬT đã có sẵn trong hệ thống, KHÔNG suy đoán từ nội
dung văn bản "có vẻ học thuật" (Mục B1: "Do not classify a document as
COURSE_MATERIAL merely because it contains academic-looking text").

4 nhóm, đúng theo yêu cầu:

- COURSE_MATERIAL ("Tài liệu môn học") — tài liệu Giảng viên thật sự tải lên
  qua CMS (`cms_lecture_repository.ingest_lecture_material`), luôn có
  `lesson_id` + `lecturer_id` gắn kèm mọi chunk. Đây là nguồn CHÍNH cho Learning
  Explainer.
- INSTITUTION_APPROVED ("Tài liệu được phê duyệt") — dành cho tài liệu đã qua
  một quy trình phê duyệt cấp tổ chức THẬT SỰ tồn tại. Hệ thống hiện KHÔNG có
  quy trình phê duyệt cấp tổ chức nào (không có bảng "institution approval"),
  nên nhóm này CHƯA có tài liệu nào thật sự thuộc về nó — cố tình để trống
  thay vì gán bừa, tránh tạo thẩm quyền giả (Mục B1: "No fake academic
  authority").
- SUPPLEMENTARY_REFERENCE ("Nguồn tham khảo bổ sung") — 4/19 tài liệu demo có
  `source_verified=True` (gắn với tác giả/nghiên cứu thật: Pomodoro/Cirillo,
  Feynman, Krashen, Cornell/Ebbinghaus) — có căn cứ học thuật thật, nhưng
  KHÔNG gắn với môn học/giảng viên cụ thể nào của hệ thống này, nên không thể
  gọi là "tài liệu môn học" hay "được phê duyệt".
- DEMO ("Dữ liệu demo") — 15/19 tài liệu demo còn lại (`source_verified=False`,
  GEN_REF chung chung, không gắn tác giả/nghiên cứu cụ thể) VÀ bất kỳ tài liệu
  nào không khớp 3 nhóm trên.
"""

from __future__ import annotations

from typing import Any, Dict

COURSE_MATERIAL = "COURSE_MATERIAL"
INSTITUTION_APPROVED = "INSTITUTION_APPROVED"
SUPPLEMENTARY_REFERENCE = "SUPPLEMENTARY_REFERENCE"
DEMO = "DEMO"

SOURCE_LABEL_VI = {
    COURSE_MATERIAL: "Tài liệu môn học",
    INSTITUTION_APPROVED: "Tài liệu được phê duyệt",
    SUPPLEMENTARY_REFERENCE: "Nguồn tham khảo bổ sung",
    DEMO: "Dữ liệu demo",
}

# Thứ tự ưu tiên retrieval khi nhiều nguồn cùng khớp truy vấn (Mục B2) — số
# càng NHỎ càng được ưu tiên trước. Learning Explainer hiện chỉ truy xuất
# trong đúng 1 nguồn (CMS của đúng course_id/lesson_id) nên bảng này chủ yếu
# phục vụ hiển thị/tài liệu, không phải một bộ lọc runtime đa nguồn thật.
SOURCE_PRIORITY_ORDER = [COURSE_MATERIAL, INSTITUTION_APPROVED, SUPPLEMENTARY_REFERENCE, DEMO]


def classify_document(doc: Dict[str, Any]) -> str:
    """`doc`: dict metadata của 1 tài liệu/chunk — chấp nhận cả 2 dạng đang có
    trong hệ thống: (a) tài liệu demo tĩnh trong `core/models.py` (có khóa
    `status`/`source_verified`), (b) chunk metadata từ pipeline ingest thật
    (có khóa `lesson_id`/`lecturer_id` nếu đến từ CMS)."""
    if doc.get("lesson_id") and doc.get("lecturer_id"):
        return COURSE_MATERIAL
    if doc.get("institution_approved") is True:
        return INSTITUTION_APPROVED
    if doc.get("source_verified") is True:
        return SUPPLEMENTARY_REFERENCE
    return DEMO


def classification_badge_kind(category: str) -> str:
    """Map sang `kind` của `ui_kit.render_badge`/`badge_html` đã có sẵn."""
    return {
        COURSE_MATERIAL: "success",
        INSTITUTION_APPROVED: "info",
        SUPPLEMENTARY_REFERENCE: "warning",
        DEMO: "neutral",
    }.get(category, "neutral")
