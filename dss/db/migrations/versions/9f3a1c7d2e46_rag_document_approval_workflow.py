"""RAG document approval workflow (NHÓM F)

Thêm cột quản trị/phê duyệt vào `rag_documents` — bổ sung ADDITIVE, KHÔNG sửa
migration cũ (`4915552f6063_initial_schema.py`, nơi tạo `rag_documents` lần
đầu). Mọi cột đều nullable hoặc có server_default để không cần backfill dữ
liệu cũ; theo đúng NHÓM F mục 7: tài liệu cũ không có `status` được coi là
`PENDING_REVIEW` (không dùng được cho trích dẫn) cho tới khi được duyệt —
server_default='PENDING_REVIEW' thể hiện đúng quy tắc đó ngay ở tầng DB.

CHƯA kiểm thử migration này với PostgreSQL thật trong phiên viết code (môi
trường làm việc không có kết nối DB — xem app/reports/ml_correctness/REPORT.md
mục NHÓM F). `dss/services/vector_store.py::PgVectorStore` đã được cập nhật để
đọc/ghi các cột này (SELECT/INSERT/UPDATE) khớp đúng tên cột ở đây, nhưng
đường PgVectorStore không có test tự động chạy được trong môi trường này —
chỉ LocalVectorStore (backend thực tế đang dùng ở dev/test) có test đầy đủ.

Revision ID: 9f3a1c7d2e46
Revises: 35d62f0c6002
"""
from alembic import op
import sqlalchemy as sa

revision = "9f3a1c7d2e46"
down_revision = "35d62f0c6002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rag_documents", sa.Column("doc_type", sa.String(32), nullable=True))
    op.add_column("rag_documents", sa.Column("issuer", sa.String(255), nullable=True))
    op.add_column("rag_documents", sa.Column("official_ref", sa.String(255), nullable=True))
    op.add_column("rag_documents", sa.Column(
        "status", sa.String(32), nullable=False, server_default="PENDING_REVIEW",
    ))
    op.add_column("rag_documents", sa.Column("approved_by", sa.String(255), nullable=True))
    op.add_column("rag_documents", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rag_documents", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("rag_documents", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("rag_documents", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rag_documents", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    # Truy vấn "danh sách chờ duyệt theo namespace" (document_approval_service.
    # list_pending_documents) lọc theo (organization_id ngầm định qua RLS,
    # namespace, status) — index tổng hợp giúp truy vấn đó không full-scan khi
    # kho tích luỹ nhiều tài liệu.
    op.create_index(
        "ix_rag_documents_namespace_status", "rag_documents", ["namespace", "status"],
    )


def downgrade():
    op.drop_index("ix_rag_documents_namespace_status", table_name="rag_documents")
    op.drop_column("rag_documents", "expires_at")
    op.drop_column("rag_documents", "effective_from")
    op.drop_column("rag_documents", "content_hash")
    op.drop_column("rag_documents", "review_note")
    op.drop_column("rag_documents", "approved_at")
    op.drop_column("rag_documents", "approved_by")
    op.drop_column("rag_documents", "status")
    op.drop_column("rag_documents", "official_ref")
    op.drop_column("rag_documents", "issuer")
    op.drop_column("rag_documents", "doc_type")
