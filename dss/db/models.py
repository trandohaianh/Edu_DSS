"""SQLAlchemy ORM models — PostgreSQL schema for EduDSS (Phase 1).

Scope note (read before extending): this schema is designed to eventually replace
the JSON/joblib storage in `dss/core/warehouse.py` and the JSON stores in
`dss/services/{auth_service,cms_lecture_repository,learning_explainer,
subscription_service}.py`, but this phase does NOT cut the running app over to
it yet (see PHASE1_REPORT.md for why: switching live auth/RBAC storage without
extensive parallel-run testing is exactly the kind of large, risky change the
engagement's own rules require to land backward-compatible first). Tables map
1:1 onto the JSON concepts already live in the app, not onto a redesigned data
model, specifically so the future migration is a data copy, not a re-mapping.

Multi-tenancy (Phase 5 groundwork, added now since retrofitting organization_id
onto an existing schema later is far riskier than including it from the start):
every tenant-scoped table carries a non-nullable `organization_id` foreign key.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dss.db.base import Base, TimestampMixin, utcnow

try:
    from pgvector.sqlalchemy import Vector

    _EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output size (see dss/core/models.py load_embedding_model)
    _VECTOR_AVAILABLE = True
except ImportError:  # pgvector package not installed in this environment yet
    Vector = None  # type: ignore[assignment,misc]
    _VECTOR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Organizations / RBAC / Users
# ---------------------------------------------------------------------------
class Organization(Base, TimestampMixin):
    """A university/institution — the tenant boundary for Phase 5 multi-tenancy."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Stage 2 (University Onboarding) additions:
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    # SETUP -> CONFIGURING -> READY -> ACTIVE, or DISABLED/ERROR from any state.
    deployment_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="MULTI_TENANT_SAAS")
    # MULTI_TENANT_SAAS | DEDICATED — metadata only, never auto-provisions
    # infrastructure; see dss/services/university_onboarding.py module docstring.

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="organization")


class Role(Base, TimestampMixin):
    """Role catalog. Seeded with the 3 roles already live in dss/core/roles.py
    (Admin, Giảng viên / CVHT, Sinh viên) — see seed.py. Extending beyond these
    3 (Phase 5's "department admin" etc.) means adding a row here, not code."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )


class Permission(Base, TimestampMixin):
    """Fine-grained permission catalog — Phase 0 found RBAC today is role-name-only;
    this table lets Phase 4/5 introduce finer scopes without new role constants."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    roles: Mapped[list["Role"]] = relationship(secondary="role_permissions", back_populates="permissions")


class RolePermission(Base):
    """Join table: role <-> permission (many-to-many)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class User(Base, TimestampMixin):
    """Mirrors dss/services/auth_service.py's users.json record shape (username,
    role, student_id, password hash+salt, auto_provisioned) — same fields, SQL
    storage, so a future cutover is a straight data copy."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "username", name="uq_users_org_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    student_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_provisioned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    role: Mapped["Role"] = relationship()


# ---------------------------------------------------------------------------
# Subscriptions / entitlement (Phase 6)
# ---------------------------------------------------------------------------
class Subscription(Base, TimestampMixin):
    """Mirrors dss/services/subscription_service.py's subscription.json record,
    plus the 2 quota fields Phase 0 found missing entirely
    (max_ai_requests_month, max_storage_mb) and real usage-tracking columns."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(String(64), nullable=False, default="ENTERPRISE")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")  # ACTIVE|EXPIRED|SUSPENDED
    max_students: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    max_courses: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    max_ai_requests_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_storage_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    features_enabled: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="subscriptions")


# ---------------------------------------------------------------------------
# Academic domain
# ---------------------------------------------------------------------------
class Student(Base, TimestampMixin):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("organization_id", "student_code", name="uq_students_org_code"),
        UniqueConstraint("organization_id", "external_id", name="uq_students_org_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    student_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    enrollment_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Lecturer(Base, TimestampMixin):
    __tablename__ = "lecturers"
    __table_args__ = (
        UniqueConstraint("organization_id", "lecturer_code", name="uq_lecturers_org_code"),
        UniqueConstraint("organization_id", "external_id", name="uq_lecturers_org_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lecturer_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Course(Base, TimestampMixin):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("organization_id", "course_code", "semester", name="uq_courses_org_code_semester"),
        UniqueConstraint("organization_id", "external_id", name="uq_courses_org_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lecturer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lecturers.id", ondelete="SET NULL"), nullable=True
    )
    semester: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollments_student_course"),
        UniqueConstraint("organization_id", "external_id", name="uq_enrollments_org_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AcademicRecord(Base, TimestampMixin):
    """Grades/attendance/etc. — one row per recorded fact, not one wide row per
    student (matches the LMS sync model in Phase 3: each sync writes new rows)."""

    __tablename__ = "academic_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    record_type: Mapped[str] = mapped_column(String(64), nullable=False)  # grade|attendance|assignment|...
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")  # manual|lms_sync|import

    __table_args__ = (
        Index("ix_academic_records_student_type", "student_id", "record_type"),
    )


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_assignments_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_submissions_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Grade(Base, TimestampMixin):
    __tablename__ = "grades"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_grades_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    submission_id: Mapped[Optional[int]] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_attendance_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LearningActivity(Base, TimestampMixin):
    __tablename__ = "learning_activities"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_learning_activities_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# ML / Model Registry (Phase 9)
# ---------------------------------------------------------------------------
class ModelVersion(Base, TimestampMixin):
    """Mirrors the real candidate/production/archived lifecycle already
    implemented in dss/services/model_registry.py + dss/core/warehouse.py —
    same status values, same single-production-per-model_key invariant,
    enforced here by a partial unique index (Phase 1 migration, see below)
    instead of the JSON pointer file."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("training_id", name="uq_model_versions_training_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # dataset_id::target_col
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_col: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")  # candidate|production|archived|failed
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    promoted_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promotion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Workstream C (ML provenance/drift closure) additions — all nullable so
    # existing rows (including prediction_repository's pre-existing
    # placeholder rows, see that module's docstring) remain valid without a
    # backfill, and so warehouse.py's non-Postgres default deployment path is
    # entirely unaffected.
    algorithm: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    artifact_checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_provenance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dataset_provenance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feature_schema_provenance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("feature_schema_provenance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    hyperparameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    code_commit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    python_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    library_versions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    metrics: Mapped[list["ModelMetric"]] = relationship(back_populates="model_version")
    dataset_provenance: Mapped[Optional["DatasetProvenance"]] = relationship()
    feature_schema_provenance: Mapped[Optional["FeatureSchemaProvenance"]] = relationship()
    drift_evaluations: Mapped[list["DriftEvaluation"]] = relationship(back_populates="model_version")


class ModelMetric(Base, TimestampMixin):
    __tablename__ = "model_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)

    model_version: Mapped["ModelVersion"] = relationship(back_populates="metrics")


class DatasetProvenance(Base, TimestampMixin):
    """Reproducibility evidence for a training dataset, not a second data
    warehouse (Workstream C, §4): row/column counts and fingerprints, never
    the raw rows themselves. `dataset_fingerprint` changes when the
    underlying data materially changes (see
    dss/services/ml_provenance.py::compute_dataset_fingerprint); the same
    `dataset_id` can have multiple rows here over time as the data evolves."""

    __tablename__ = "dataset_provenance"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "dataset_id", "dataset_fingerprint",
            name="uq_dataset_provenance_org_dataset_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    logical_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    target_column: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    feature_list: Mapped[list] = mapped_column(JSON, nullable=False)
    null_stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    numeric_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    lineage_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ingestion_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FeatureSchemaProvenance(Base, TimestampMixin):
    """Deterministic model-input-contract fingerprint (Workstream C, §5) —
    the same (names, order, dtypes, roles, target, task type, preprocessing)
    always yields the same `fingerprint`; any meaningful change to the
    contract yields a different one. See
    dss/services/ml_provenance.py::compute_feature_schema_fingerprint."""

    __tablename__ = "feature_schema_provenance"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_feature_schema_provenance_org_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feature_names: Mapped[list] = mapped_column(JSON, nullable=False)
    feature_dtypes: Mapped[dict] = mapped_column(JSON, nullable=False)
    feature_roles: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_definition: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model_task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # classification|regression|clustering
    preprocessing_expectations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DriftEvaluation(Base, TimestampMixin):
    """Persisted drift-evaluation history (Workstream C, §8) — answers which
    model/baseline/window was evaluated when, with what thresholds, and what
    the result was. `details` carries the per-feature or per-metric
    breakdown (kept as JSON rather than a child table — see module docstring
    in dss/services/ml_provenance.py for why a fourth table was judged
    unnecessary complexity for this data shape)."""

    __tablename__ = "drift_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_type: Mapped[str] = mapped_column(String(32), nullable=False)  # data_drift|performance_drift
    baseline_dataset_provenance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dataset_provenance.id", ondelete="SET NULL"), nullable=True
    )
    current_window_description: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    thresholds_used: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(40), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    evaluated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    model_version: Mapped["ModelVersion"] = relationship(back_populates="drift_evaluations")


class Prediction(Base, TimestampMixin):
    """Formalizes the fields Phase 0 found only loosely present in
    warehouse.py::save_prediction's free-form metadata dict."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    input_schema_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    prediction_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # rule-based|model_version_id|...


class Consultation(Base, TimestampMixin):
    """Mirrors dss/core/warehouse.py::save_ai_consultation."""

    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Phase 1B (migration order item 8): tracks the source local
    # consultation_id when a record was migrated from the legacy JSON
    # history via consultation_repository.import_from_local_history — lets
    # a repeat import skip records already migrated instead of duplicating.
    local_consultation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)


# ---------------------------------------------------------------------------
# RAG (Phase 2)
# ---------------------------------------------------------------------------
class RagDocument(Base, TimestampMixin):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "document_id", name="uq_rag_documents_org_docid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    course_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)  # COURSE_MATERIAL|DEMO|... (see source_classification.py)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="student_learning")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # NHÓM F (migration 9f3a1c7d2e46) — quy trình phê duyệt tài liệu. status
    # mặc định "PENDING_REVIEW" (server_default trong migration) — tài liệu cũ
    # không có gì trong các cột này vẫn KHÔNG được coi là đã duyệt (đúng nguyên
    # tắc "chưa duyệt thì không trích dẫn được", xem document_governance.py).
    doc_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    issuer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    official_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["RagChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class RagChunk(Base, TimestampMixin):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_rag_chunks_chunk_id"),
        Index("ix_rag_chunks_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # pgvector column — only usable against real PostgreSQL + the pgvector extension.
    # Falls back to a plain JSON list column when the pgvector package/extension
    # is unavailable (e.g. schema inspection against SQLite in tests), so the
    # model still imports and the migration can be reasoned about everywhere;
    # actual similarity search always requires the real Postgres+pgvector path.
    embedding = mapped_column(Vector(_EMBEDDING_DIM) if _VECTOR_AVAILABLE else JSON, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    document: Mapped["RagDocument"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Audit / activity (Phase 4 / Phase 8)
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """The security audit trail Phase 0 found does NOT exist anywhere today —
    records who/action/target/timestamp/before/after for every sensitive
    mutation (user management, role changes, model promote/rollback)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str] = mapped_column(String(128), nullable=False)  # denormalized: survives user deletion
    action: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "user.role_changed", "model.promoted"
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "user", "model_version"
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ActivityLog(Base):
    """Mirrors dss/core/warehouse.py::log_activity — user-facing activity
    history (distinct from AuditLog, which is the security trail)."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# CMS — internal lecture repository (Phase 1B, migration order item 10).
# Mirrors dss/services/cms_lecture_repository.py's CMSLesson/LessonVersion
# dataclasses and dss/services/learning_explainer.py's quiz-queue/interaction-
# log JSON record shapes field-for-field. Added via a NEW migration
# (e9f4bec0ef79) rather than editing the already-verified initial migration
# (4915552f6063), per explicit instruction. `questions` on CmsQuiz is a JSON
# column (a list of question dicts), matching the app's OWN current
# unnormalized in-memory/JSON shape (`blueprint.questions`) — a deliberate
# scope decision documented in PHASE1B_RUNTIME_CUTOVER.md, not an oversight.
# ---------------------------------------------------------------------------
class CmsLesson(Base, TimestampMixin):
    __tablename__ = "cms_lessons"
    __table_args__ = (
        UniqueConstraint("organization_id", "lesson_id", name="uq_cms_lessons_org_lesson_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # app's own string id
    course_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    topic_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lecturer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    learning_outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="Standard")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    official_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_document_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    supplementary_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    socratic_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiz_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiz_requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    excluded_document_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    versions: Mapped[list["CmsLessonVersion"]] = relationship(back_populates="lesson", cascade="all, delete-orphan")


class CmsLessonVersion(Base):
    __tablename__ = "cms_lesson_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("cms_lessons.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    lesson: Mapped["CmsLesson"] = relationship(back_populates="versions")


class CmsQuiz(Base, TimestampMixin):
    """One row per submitted quiz blueprint (matches
    learning_explainer.py's quiz_review_queue.json record shape) —
    `questions` embeds the full question list as JSON, matching the app's own
    current unnormalized shape rather than inventing a separate
    quiz_questions table the real app doesn't have."""

    __tablename__ = "cms_quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[int] = mapped_column(ForeignKey("cms_lessons.id", ondelete="CASCADE"), nullable=False)
    queue_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # app's own string id
    course_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_LECTURER_APPROVAL")
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CmsStudentInteraction(Base):
    """Mirrors learning_explainer.py's interaction_log.json record shape
    exactly (student_pseudonym — never a real name/ID, see privacy_service.py
    — course_id, lesson_id, topic_id, question, explanation_level,
    has_cms_content, misconception_label, quiz_correct)."""

    __tablename__ = "cms_student_interactions"
    __table_args__ = (
        Index("ix_cms_interactions_org_created", "organization_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    student_pseudonym: Mapped[str] = mapped_column(String(128), nullable=False)
    course_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lesson_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    topic_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    has_cms_content: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    misconception_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quiz_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# AI token usage ledger + admin AI config (Phase 1C, priority items 10-11).
# Mirrors dss/services/token_tracker.py::UsageRecord and
# dss/services/admin_ai_config.py::DefaultProviderConfig field-for-field.
# Added via a NEW migration, not editing the initial schema.
# ---------------------------------------------------------------------------
class AiTokenUsage(Base):
    """Append-only accounting ledger — NEVER stores API keys/Authorization
    headers/full prompts (see token_tracker.py's own docstring: "Tuyệt đối
    KHÔNG ghi log API key thật"). `user_id` here is already the pseudonymized
    value token_tracker.record_usage() produces (email-shaped ids are
    rewritten to `user_<local-part>` before this repository ever sees them)."""

    __tablename__ = "ai_token_usage"
    __table_args__ = (
        Index("ix_ai_token_usage_org_timestamp", "organization_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    usage_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False)


class AdminAiConfig(Base, TimestampMixin):
    """One row per organization — SAFE_DATABASE_CONFIG only (provider key
    NAME and model NAME, e.g. "gemini"/"gemini-flash-latest"). NEVER holds
    the actual API key/secret value — those remain in st.secrets/environment
    variables via the existing secure configuration mechanism, untouched by
    this table by design (see PHASE1C_PERSISTENCE_COMPLETION.md, Section 12,
    for the SAFE_DATABASE_CONFIG / SECRET / RUNTIME_ENVIRONMENT_CONFIG
    classification this table's fields were audited against)."""

    __tablename__ = "admin_ai_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)


# ---------------------------------------------------------------------------
# University onboarding (Stage 2)
# ---------------------------------------------------------------------------
class LmsMappingProfile(Base, TimestampMixin):
    """Canonical-mapping validation record — proves (or disproves) that an
    organization's configured LMS/CMS source can supply every required
    canonical field for its enabled resources. `resource_mappings` shape:
    {resource_name: {"required_fields": [...], "present_fields": [...],
    "status": "valid"|"invalid", "missing_fields": [...]}}."""

    __tablename__ = "lms_mapping_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_mappings: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNVALIDATED")
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    connector_configs: Mapped[list["LmsConnectorConfig"]] = relationship(back_populates="mapping_profile")


class LmsConnectorConfig(Base, TimestampMixin):
    """Durable per-organization LMS/CMS connector configuration. Designed so
    a future Moodle/Canvas/custom-SIS adapter can be added by introducing a
    new `connector_type` value and its own adapter implementation, without
    changing this table or any onboarding/activation code that reads it —
    see dss/services/university_onboarding.py module docstring.

    `credential_reference` is NEVER a plaintext secret — it names where the
    real credential lives (an env var name, or a secrets-manager key),
    consistent with dss/services/llm_gateway.py::resolve_api_key's existing
    env/secrets-reference pattern. No connector credential is ever stored
    in this table or logged anywhere in this module."""

    __tablename__ = "lms_connector_configs"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_lms_connector_configs_org"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    auth_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    credential_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_organization_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=2.0)
    retry_policy: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    enabled_resources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sync_mode: Mapped[str] = mapped_column(String(32), default="incremental")
    mapping_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lms_mapping_profiles.id", ondelete="SET NULL"), nullable=True
    )
    last_connection_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_connection_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connection_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_successful_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    configuration_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    # DRAFT -> (test connection + mapping valid) -> VALID, or INVALID on failure.

    mapping_profile: Mapped[Optional["LmsMappingProfile"]] = relationship(back_populates="connector_configs")


# ---------------------------------------------------------------------------
# Capability-closure integration, tenant configuration and quota state.
# ---------------------------------------------------------------------------
class OrganizationConfig(Base, TimestampMixin):
    __tablename__ = "organization_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntegrationSyncState(Base, TimestampMixin):
    __tablename__ = "integration_sync_states"
    __table_args__ = (UniqueConstraint("organization_id", "source", "resource", name="uq_sync_state_org_source_resource"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"
    __table_args__ = (
        UniqueConstraint("organization_id", "source", "event_id", name="uq_webhook_org_source_event"),
        Index("ix_webhook_org_status", "organization_id", "processing_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    external_entity_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CmsContent(Base, TimestampMixin):
    __tablename__ = "cms_content"
    __table_args__ = (UniqueConstraint("organization_id", "external_id", name="uq_cms_content_org_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    course_external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="document")
    source_reference: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rag_document_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class QuotaUsage(Base, TimestampMixin):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("organization_id", "quota_key", "period_key", name="uq_quota_usage_org_key_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    quota_key: Mapped[str] = mapped_column(String(64), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
