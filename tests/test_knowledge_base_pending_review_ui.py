"""NHÓM F: tab "Quản lý tri thức" phải có hàng đợi "Chờ duyệt" gọi đúng
document_approval_service — trước đây không có UI nào để duyệt tài liệu
(document_ingestion không có khái niệm trạng thái, mọi tài liệu tải lên dùng
được ngay). Kiểm tra bằng source inspection (đúng phong cách dự án cho code UI
Streamlit khó test trực tiếp)."""
from __future__ import annotations

import inspect

from dss.tabs import knowledge_base


def test_knowledge_base_tab_shows_pending_review_queue():
    source = inspect.getsource(knowledge_base.knowledge_base_tab)
    assert "STATUS_PENDING_REVIEW" in source
    assert "Chờ duyệt" in source


def test_knowledge_base_tab_calls_approval_service_not_direct_status_write():
    """Không được tự set status="APPROVED" trực tiếp trong UI — PHẢI đi qua
    document_approval_service (có kiểm tra thẩm quyền + audit log)."""
    source = inspect.getsource(knowledge_base.knowledge_base_tab)
    assert "document_approval_service.approve_document(" in source
    assert "document_approval_service.reject_document(" in source
    assert '"status": "APPROVED"' not in source
    assert '"status": gov.STATUS_APPROVED' not in source


def test_knowledge_base_tab_legacy_seed_button_never_auto_approves():
    """FINAL REMEDIATION PASS Mục 4: nút "Nạp tài liệu mẫu nội bộ" (bootstrap
    có kiểm soát cho 19 tài liệu cũ) phải gọi ĐÚNG
    legacy_knowledge_seed.seed_legacy_knowledge_base_documents (luôn
    PENDING_REVIEW, xem test_legacy_knowledge_seed.py) và KHÔNG được tự động
    gọi approve_document/duyệt bất kỳ tài liệu nào trong cùng thao tác — nạp
    xong tài liệu vẫn phải nằm ở hàng đợi Chờ duyệt, chờ Admin tự xem xét."""
    source = inspect.getsource(knowledge_base.knowledge_base_tab)
    assert "seed_legacy_knowledge_base_documents" in source
    # Đoạn code seed không được đi kèm bất kỳ lời gọi approve_document nào
    # ngay sau đó trong cùng hàm (kiểm tra thô bằng cách đếm số lần xuất hiện:
    # approve_document CHỈ nên xuất hiện ở khối hàng đợi Chờ duyệt, không phải
    # ngay trong/ngay sau khối nút "Nạp tài liệu mẫu").
    seed_idx = source.index("seed_legacy_knowledge_base_documents")
    seed_block = source[seed_idx: seed_idx + 400]
    assert "approve_document" not in seed_block
