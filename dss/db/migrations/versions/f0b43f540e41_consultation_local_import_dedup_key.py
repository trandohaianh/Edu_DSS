"""consultation local import dedup key

Revision ID: f0b43f540e41
Revises: 830742fd75d4
Create Date: 2026-09-17 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0b43f540e41'
down_revision: Union[str, Sequence[str], None] = '830742fd75d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Additive-only: one new nullable, indexed column on `consultations` —
    lets consultation_repository.import_from_local_history() skip local
    records it has already migrated, instead of duplicating them on a
    repeat run. Does not touch the initial schema migration."""
    op.add_column('consultations', sa.Column('local_consultation_id', sa.String(length=128), nullable=True))
    op.create_index(
        op.f('ix_consultations_local_consultation_id'), 'consultations', ['local_consultation_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_consultations_local_consultation_id'), table_name='consultations')
    op.drop_column('consultations', 'local_consultation_id')
