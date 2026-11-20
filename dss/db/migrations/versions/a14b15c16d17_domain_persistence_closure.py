"""domain persistence closure

Revision ID: a14b15c16d17
Revises: 797f72d1c666
"""

import sqlalchemy as sa
from alembic import op

revision = "a14b15c16d17"
down_revision = "797f72d1c666"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "assignments",
    "submissions",
    "grades",
    "attendance",
    "learning_activities",
    "organization_configs",
    "integration_sync_states",
    "webhook_inbox",
    "cms_content",
    "quota_usage",
)


def _tenant_columns(*extra):
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
        ),
        *extra,
    ]


def upgrade():
    for table in ("students", "lecturers", "courses", "enrollments"):
        op.add_column(table, sa.Column("external_id", sa.String(128), nullable=True))
        op.create_index(f"ix_{table}_external_id", table, ["external_id"])
        op.create_unique_constraint(f"uq_{table}_org_external", table, ["organization_id", "external_id"])

    op.create_table(
        "assignments",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_assignments_org_external"),
        ),
    )
    op.create_table(
        "submissions",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column(
                "assignment_id", sa.Integer(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
            sa.Column("submitted_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_submissions_org_external"),
        ),
    )
    op.create_table(
        "grades",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="CASCADE")),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_grades_org_external"),
        ),
    )
    op.create_table(
        "attendance",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("present", sa.Boolean(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_attendance_org_external"),
        ),
    )
    op.create_table(
        "learning_activities",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("activity_type", sa.String(64), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_learning_activities_org_external"),
        ),
    )
    op.create_table(
        "organization_configs",
        *_tenant_columns(
            sa.Column("settings", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id"),
        ),
    )
    op.create_table(
        "integration_sync_states",
        *_tenant_columns(
            sa.Column("source", sa.String(128), nullable=False),
            sa.Column("resource", sa.String(64), nullable=False),
            sa.Column("cursor", sa.String(255)),
            sa.Column("last_success_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("error_code", sa.String(128)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "source", "resource", name="uq_sync_state_org_source_resource"),
        ),
    )
    op.create_table(
        "webhook_inbox",
        *_tenant_columns(
            sa.Column("source", sa.String(128), nullable=False),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column("event_type", sa.String(128), nullable=False),
            sa.Column("external_entity_id", sa.String(128)),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processing_status", sa.String(32), nullable=False, server_default="received"),
            sa.Column("processed_at", sa.DateTime(timezone=True)),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(128)),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.UniqueConstraint("organization_id", "source", "event_id", name="uq_webhook_org_source_event"),
        ),
    )
    op.create_table(
        "cms_content",
        *_tenant_columns(
            sa.Column("external_id", sa.String(128), nullable=False),
            sa.Column("course_external_id", sa.String(128)),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(64), nullable=False, server_default="document"),
            sa.Column("source_reference", sa.String(512)),
            sa.Column("mime_type", sa.String(128)),
            sa.Column("checksum_sha256", sa.String(64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("rag_document_id", sa.String(128)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "external_id", name="uq_cms_content_org_external"),
        ),
    )
    op.create_table(
        "quota_usage",
        *_tenant_columns(
            sa.Column("quota_key", sa.String(64), nullable=False),
            sa.Column("period_key", sa.String(32), nullable=False),
            sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "quota_key", "period_key", name="uq_quota_usage_org_key_period"),
        ),
    )

    for table in TENANT_TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY tenant_isolation ON {table} USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer) WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer)"
            )
        )


def downgrade():
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    for table in ("enrollments", "courses", "lecturers", "students"):
        op.drop_constraint(f"uq_{table}_org_external", table, type_="unique")
        op.drop_index(f"ix_{table}_external_id", table_name=table)
        op.drop_column(table, "external_id")
