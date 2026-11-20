"""Test Suite: source_classification.py (Mục B1 — phân loại nguồn tri thức
tập trung, UI/RAG consistency pass phần 2).

Nguyên tắc kiểm thử cốt lõi: phân loại phải dựa trên PROVENANCE THẬT (lesson_id
+ lecturer_id cho CMS, source_verified cho tài liệu demo đã kiểm chứng), không
được suy đoán từ nội dung văn bản, và một tài liệu chưa từng qua quy trình phê
duyệt cấp tổ chức thật KHÔNG BAO GIỜ được gán INSTITUTION_APPROVED."""

from __future__ import annotations

from dss.services import source_classification as sc


def test_cms_uploaded_document_is_course_material():
    doc = {"lesson_id": "L01", "lecturer_id": "gv001", "title": "Bài 4 - K-Means"}
    assert sc.classify_document(doc) == sc.COURSE_MATERIAL


def test_verified_academic_reference_is_supplementary_not_course_material():
    """4/19 tài liệu demo (Pomodoro/Feynman/Krashen/Cornell) có nguồn thật
    nhưng KHÔNG gắn với môn học/giảng viên cụ thể nào -> supplementary,
    không phải course material."""
    doc = {
        "id": "doc_003",
        "source_verified": True,
        "reference": "Kỹ thuật Pomodoro — Francesco Cirillo...",
    }
    assert sc.classify_document(doc) == sc.SUPPLEMENTARY_REFERENCE


def test_unverified_generic_demo_document_is_demo():
    doc = {"id": "doc_001", "source_verified": False, "status": "DRAFT"}
    assert sc.classify_document(doc) == sc.DEMO


def test_document_with_no_metadata_at_all_defaults_to_demo_not_authoritative():
    """Không có metadata gì -> phải mặc định về nhóm THẤP NHẤT (DEMO), không
    được mặc định lên một nhóm có vẻ uy tín hơn khi thiếu bằng chứng."""
    assert sc.classify_document({}) == sc.DEMO


def test_institution_approved_requires_explicit_real_flag():
    """Không được suy luận INSTITUTION_APPROVED từ bất kỳ trường nào khác --
    hệ thống hiện không có quy trình phê duyệt cấp tổ chức thật, nên chỉ một
    cờ `institution_approved=True` tường minh mới được xếp vào nhóm này."""
    assert sc.classify_document({"official_source": True}) != sc.INSTITUTION_APPROVED
    assert sc.classify_document({"status": "APPROVED"}) != sc.INSTITUTION_APPROVED
    assert sc.classify_document({"institution_approved": True}) == sc.INSTITUTION_APPROVED


def test_cms_document_takes_priority_over_source_verified_flag():
    """Nếu (giả định) một tài liệu CMS nào đó cũng vô tình có source_verified,
    CMS/course-material vẫn phải thắng -- đây là tín hiệu xác thực mạnh nhất
    (Giảng viên thật đã tải lên cho đúng lớp/bài học)."""
    doc = {"lesson_id": "L02", "lecturer_id": "gv002", "source_verified": True}
    assert sc.classify_document(doc) == sc.COURSE_MATERIAL


def test_academic_looking_text_alone_does_not_grant_course_material():
    """Mục B1: không được phân loại COURSE_MATERIAL chỉ vì nội dung 'trông có
    vẻ học thuật' -- hàm không hề đọc nội dung `content`/`title`, chỉ đọc
    provenance, nên 1 tài liệu demo với tiêu đề học thuật vẫn phải là DEMO."""
    doc = {
        "title": "Giáo trình chính thức Toán cao cấp - Đại học Bách Khoa",
        "content": "Chương 1: Đạo hàm và tích phân...",
    }
    assert sc.classify_document(doc) == sc.DEMO


def test_all_four_categories_have_vietnamese_labels():
    for category in (sc.COURSE_MATERIAL, sc.INSTITUTION_APPROVED, sc.SUPPLEMENTARY_REFERENCE, sc.DEMO):
        assert category in sc.SOURCE_LABEL_VI
        assert sc.SOURCE_LABEL_VI[category]


def test_priority_order_puts_course_material_first_and_demo_last():
    assert sc.SOURCE_PRIORITY_ORDER[0] == sc.COURSE_MATERIAL
    assert sc.SOURCE_PRIORITY_ORDER[-1] == sc.DEMO


def test_badge_kind_mapping_uses_valid_ui_kit_kinds():
    valid_kinds = {"success", "warning", "danger", "info", "neutral", "violet"}
    for category in (sc.COURSE_MATERIAL, sc.INSTITUTION_APPROVED, sc.SUPPLEMENTARY_REFERENCE, sc.DEMO):
        assert sc.classification_badge_kind(category) in valid_kinds
