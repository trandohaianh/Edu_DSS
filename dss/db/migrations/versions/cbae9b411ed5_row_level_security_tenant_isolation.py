"""row level security tenant isolation

Revision ID: cbae9b411ed5
Revises: 4915552f6063
Create Date: 2026-09-17 14:07:00.796627

Phase 5 groundwork, merged in from a second, independently-developed Phase 1
implementation found in the same repo (raw-SQL migrations + a psycopg2
tenant repository) after the fact — see PHASE1_REPORT.md's "Merge" section
for the full story. That implementation's core insight adopted here: relying
only on application-level `WHERE organization_id = ...` filtering (what this
migration's predecessor, 4915552f6063, provides) means ONE missed filter in
application code leaks cross-tenant data. Postgres Row Level Security makes
tenant isolation a database-engine guarantee instead — a query that forgets
the filter gets zero rows back, not another tenant's rows.

IMPORTANT — RLS only protects a connection that is NOT a superuser and NOT
the table owner unless FORCE ROW LEVEL SECURITY is also set (done below).
Superusers always bypass RLS regardless. The default role created by the
official `postgres`/`pgvector` Docker images (whatever POSTGRES_USER is) is a
superuser — production deployments MUST connect the running application as a
separate, non-superuser role for this migration's guarantee to mean anything.
See dss/db/session.py's module docstring and PHASE1_REPORT.md.
"""

from typing import Sequence, Union

import pgvector.sqlalchemy  # needed whenever a migration touches rag_chunks.embedding
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cbae9b411ed5'
down_revision: Union[str, Sequence[str], None] = '4915552f6063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tenant-scoped tables that carry `organization_id` directly.
_DIRECT_TENANT_TABLES = [
    "users",
    "subscriptions",
    "students",
    "lecturers",
    "courses",
    "enrollments",
    "academic_records",
    "model_versions",
    "predictions",
    "recommendations",
    "consultations",
    "rag_documents",
    "audit_logs",
    "activity_logs",
]

# Child tables with no organization_id column of their own — isolated via a
# subquery against their parent's organization_id instead of denormalizing
# the column (avoids a backfill step; the join cost is on writes/reads that
# already touch these tables through their parent, not a hot path change).
_SUBQUERY_TENANT_TABLES = {
    "model_metrics": ("model_version_id", "model_versions"),
    "rag_chunks": ("document_id", "rag_documents"),
}


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    for table_name in _DIRECT_TENANT_TABLES:
        conn.execute(sa.text(f'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY'))
        conn.execute(sa.text(f'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY'))
        conn.execute(
            sa.text(
                f'CREATE POLICY tenant_isolation ON {table_name} '
                f"USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer) "
                f"WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer)"
            )
        )

    for table_name, (fk_col, parent_table) in _SUBQUERY_TENANT_TABLES.items():
        conn.execute(sa.text(f'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY'))
        conn.execute(sa.text(f'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY'))
        conn.execute(
            sa.text(
                f'CREATE POLICY tenant_isolation ON {table_name} '
                f"USING ({fk_col} IN (SELECT id FROM {parent_table} "
                f"WHERE organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer)) "
                f"WITH CHECK ({fk_col} IN (SELECT id FROM {parent_table} "
                f"WHERE organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer))"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    all_tables = _DIRECT_TENANT_TABLES + list(_SUBQUERY_TENANT_TABLES.keys())
    for table_name in all_tables:
        conn.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON {table_name}'))
        conn.execute(sa.text(f'ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY'))
        conn.execute(sa.text(f'ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY'))
