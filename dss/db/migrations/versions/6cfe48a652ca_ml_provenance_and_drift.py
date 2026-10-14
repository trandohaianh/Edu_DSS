"""ML provenance and drift (Workstream C)

Adds durable model/dataset/feature-schema provenance and drift-evaluation
history, additively — extends the existing `model_versions` table (already
created by the initial migration; see dss/db/models.py::ModelVersion) rather
than replacing it, and never touches the file-based joblib/JSON storage in
dss/core/warehouse.py, which remains the primary artifact store (this
migration only adds a nullable, best-effort metadata mirror — see
dss/core/persistence_config.py's new "ML_PROVENANCE" feature flag and
dss/core/warehouse.py::save_model_training).

Revision ID: 6cfe48a652ca
Revises: a14b15c16d17
"""
from alembic import op
import sqlalchemy as sa

revision = "6cfe48a652ca"
down_revision = "a14b15c16d17"
branch_labels = None
depends_on = None

# Direct tenant tables (own organization_id) — same RLS pattern as every
# prior migration (see cbae9b411ed5 / a14b15c16d17): ENABLE + FORCE ROW
# LEVEL SECURITY, one "tenant_isolation" policy per table, identical
# USING/WITH CHECK expression.
NEW_TENANT_TABLES = ("dataset_provenance", "feature_schema_provenance", "drift_evaluations")


def _tenant_columns(*extra):
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        *extra,
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "dataset_provenance",
        *_tenant_columns(
            sa.Column("dataset_id", sa.String(128), nullable=False),
            sa.Column("logical_name", sa.String(255)),
            sa.Column("source_type", sa.String(64), nullable=False),
            sa.Column("source_reference", sa.String(512)),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("column_count", sa.Integer(), nullable=False),
            sa.Column("schema_fingerprint", sa.String(64), nullable=False),
            sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
            sa.Column("target_column", sa.String(128)),
            sa.Column("feature_list", sa.JSON(), nullable=False),
            sa.Column("null_stats", sa.JSON()),
            sa.Column("numeric_summary", sa.JSON()),
            sa.Column("lineage_metadata", sa.JSON()),
            sa.Column("ingestion_at", sa.DateTime(timezone=True)),
        ),
        sa.UniqueConstraint(
            "organization_id", "dataset_id", "dataset_fingerprint",
            name="uq_dataset_provenance_org_dataset_fingerprint",
        ),
    )
    op.create_index("ix_dataset_provenance_dataset_id", "dataset_provenance", ["dataset_id"])

    op.create_table(
        "feature_schema_provenance",
        *_tenant_columns(
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("feature_names", sa.JSON(), nullable=False),
            sa.Column("feature_dtypes", sa.JSON(), nullable=False),
            sa.Column("feature_roles", sa.JSON(), nullable=False),
            sa.Column("target_definition", sa.String(128)),
            sa.Column("model_task_type", sa.String(32), nullable=False),
            sa.Column("preprocessing_expectations", sa.JSON()),
        ),
        sa.UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_feature_schema_provenance_org_fingerprint",
        ),
    )
    op.create_index("ix_feature_schema_provenance_fingerprint", "feature_schema_provenance", ["fingerprint"])

    op.create_table(
        "drift_evaluations",
        *_tenant_columns(
            sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("evaluation_type", sa.String(32), nullable=False),
            sa.Column("baseline_dataset_provenance_id", sa.Integer(), sa.ForeignKey("dataset_provenance.id", ondelete="SET NULL")),
            sa.Column("current_window_description", sa.JSON()),
            sa.Column("thresholds_used", sa.JSON(), nullable=False),
            sa.Column("overall_status", sa.String(40), nullable=False),
            sa.Column("recommended_action", sa.String(32), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("evaluated_by", sa.String(128)),
        ),
    )
    op.create_index("ix_drift_evaluations_model_version_id", "drift_evaluations", ["model_version_id"])

    for table in NEW_TENANT_TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer) "
            f"WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer)"
        ))

    # Extend model_versions — all nullable, no backfill required, no
    # behavior change for existing rows or the non-Postgres default path.
    op.add_column("model_versions", sa.Column("algorithm", sa.String(128)))
    op.add_column("model_versions", sa.Column("artifact_checksum_sha256", sa.String(64)))
    op.add_column("model_versions", sa.Column(
        "dataset_provenance_id", sa.Integer(),
        sa.ForeignKey("dataset_provenance.id", ondelete="SET NULL"),
    ))
    op.add_column("model_versions", sa.Column(
        "feature_schema_provenance_id", sa.Integer(),
        sa.ForeignKey("feature_schema_provenance.id", ondelete="SET NULL"),
    ))
    op.add_column("model_versions", sa.Column("hyperparameters", sa.JSON()))
    op.add_column("model_versions", sa.Column("code_commit", sa.String(64)))
    op.add_column("model_versions", sa.Column("python_version", sa.String(32)))
    op.add_column("model_versions", sa.Column("library_versions", sa.JSON()))
    op.add_column("model_versions", sa.Column("created_by", sa.String(128)))
    op.create_index("ix_model_versions_dataset_provenance_id", "model_versions", ["dataset_provenance_id"])
    op.create_index("ix_model_versions_feature_schema_provenance_id", "model_versions", ["feature_schema_provenance_id"])


def downgrade():
    op.drop_index("ix_model_versions_feature_schema_provenance_id", table_name="model_versions")
    op.drop_index("ix_model_versions_dataset_provenance_id", table_name="model_versions")
    for col in (
        "created_by", "library_versions", "python_version", "code_commit", "hyperparameters",
        "feature_schema_provenance_id", "dataset_provenance_id", "artifact_checksum_sha256", "algorithm",
    ):
        op.drop_column("model_versions", col)

    for table in reversed(NEW_TENANT_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("drift_evaluations")
    op.drop_table("feature_schema_provenance")
    op.drop_table("dataset_provenance")
