"""Bước 9: đủ trường để các kho tệp (dự đoán, tư vấn, token AI) chuyển hẳn sang PostgreSQL.

Chỉ THÊM cột (expand), không đổi tên hay xoá gì, nên bản app cũ vẫn chạy được trên schema mới.
Thiết kế: docs/architecture/STEP9_FILE_STORES_TO_POSTGRES.md (chủ dự án duyệt 22/11/2026).

Revision ID: 7b9e2c4f1a30
Revises: d2e3a6102601
"""

import sqlalchemy as sa
from alembic import op

revision = "7b9e2c4f1a30"
down_revision = "d2e3a6102601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_token_usage", sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "ai_token_usage", sa.Column("usage_source", sa.String(16), nullable=False, server_default="estimated")
    )
    op.add_column("ai_token_usage", sa.Column("thinking_tokens", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("predictions", sa.Column("details", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("local_prediction_id", sa.String(128), nullable=True))
    op.create_index("ix_predictions_local_prediction_id", "predictions", ["local_prediction_id"])

    op.add_column("consultations", sa.Column("performed_by", sa.String(128), nullable=True))
    op.add_column("consultations", sa.Column("performed_by_role", sa.String(64), nullable=True))
    op.add_column("consultations", sa.Column("details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("consultations", "details")
    op.drop_column("consultations", "performed_by_role")
    op.drop_column("consultations", "performed_by")
    op.drop_index("ix_predictions_local_prediction_id", table_name="predictions")
    op.drop_column("predictions", "local_prediction_id")
    op.drop_column("predictions", "details")
    op.drop_column("ai_token_usage", "thinking_tokens")
    op.drop_column("ai_token_usage", "usage_source")
    op.drop_column("ai_token_usage", "cache_hit")
