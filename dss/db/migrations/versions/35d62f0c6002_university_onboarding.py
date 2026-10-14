"""University onboarding (Stage 2)

Extends `organizations` with a lifecycle status and deployment-mode
metadata (both additive, nullable-safe via server defaults so existing
rows/tests need no backfill), and adds two new tenant-scoped tables:
`lms_connector_configs` (durable connector configuration — never stores a
plaintext secret, only a credential *reference*) and `lms_mapping_profiles`
(canonical-mapping validation record per organization). Same RLS pattern
as every prior migration.

Revision ID: 35d62f0c6002
Revises: 6cfe48a652ca
"""
from alembic import op
import sqlalchemy as sa

revision = "35d62f0c6002"
down_revision = "6cfe48a652ca"
branch_labels = None
depends_on = None

NEW_TENANT_TABLES = ("lms_connector_configs", "lms_mapping_profiles")


def _tenant_columns(*extra):
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        *extra,
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.add_column("organizations", sa.Column(
        "lifecycle_status", sa.String(32), nullable=False, server_default="ACTIVE",
    ))
    op.add_column("organizations", sa.Column(
        "deployment_mode", sa.String(32), nullable=False, server_default="MULTI_TENANT_SAAS",
    ))

    op.create_table(
        "lms_mapping_profiles",
        *_tenant_columns(
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("resource_mappings", sa.JSON(), nullable=False),
            sa.Column("validation_status", sa.String(32), nullable=False, server_default="UNVALIDATED"),
            sa.Column("validated_at", sa.DateTime(timezone=True)),
        ),
    )

    op.create_table(
        "lms_connector_configs",
        *_tenant_columns(
            sa.Column("connector_type", sa.String(64), nullable=False),
            sa.Column("base_url", sa.String(512)),
            sa.Column("auth_mode", sa.String(32)),
            sa.Column("credential_reference", sa.String(255)),
            sa.Column("external_organization_id", sa.String(128)),
            sa.Column("timeout_seconds", sa.Float(), server_default="2.0"),
            sa.Column("retry_policy", sa.JSON()),
            sa.Column("enabled_resources", sa.JSON()),
            sa.Column("sync_mode", sa.String(32), server_default="incremental"),
            sa.Column("mapping_profile_id", sa.Integer(), sa.ForeignKey("lms_mapping_profiles.id", ondelete="SET NULL")),
            sa.Column("last_connection_status", sa.String(32)),
            sa.Column("last_connection_at", sa.DateTime(timezone=True)),
            sa.Column("last_connection_detail", sa.Text()),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True)),
            sa.Column("configuration_status", sa.String(32), nullable=False, server_default="DRAFT"),
        ),
        sa.UniqueConstraint("organization_id", name="uq_lms_connector_configs_org"),
    )

    for table in NEW_TENANT_TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer) "
            f"WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer)"
        ))


def downgrade():
    for table in reversed(NEW_TENANT_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("lms_connector_configs")
    op.drop_table("lms_mapping_profiles")
    op.drop_column("organizations", "deployment_mode")
    op.drop_column("organizations", "lifecycle_status")
