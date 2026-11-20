"""Portable relational models for classroom delivery and programme allocations."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class PlatformBase(DeclarativeBase):
    pass


class School(PlatformBase):
    __tablename__ = "lp_schools"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Classroom(PlatformBase):
    __tablename__ = "lp_classes"
    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_lp_class_scope"),
        UniqueConstraint("school_id", "code", "term", name="uq_lp_class_code_term"),
        CheckConstraint("status IN ('active','closed')", name="ck_lp_class_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey("lp_schools.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    course_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    term: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def class_scope_fk():
    return ForeignKeyConstraint(
        ["school_id", "class_id"], ["lp_classes.school_id", "lp_classes.id"], ondelete="CASCADE",
    )


class TeachingAssignment(PlatformBase):
    __tablename__ = "lp_teaching_assignments"
    __table_args__ = (class_scope_fk(), UniqueConstraint("school_id", "class_id", "teacher_username", name="uq_lp_teacher_assignment"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    teacher_username: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ClassEnrollment(PlatformBase):
    __tablename__ = "lp_enrollments"
    __table_args__ = (class_scope_fk(), UniqueConstraint("school_id", "class_id", "student_code", name="uq_lp_enrollment_owner"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Assessment(PlatformBase):
    __tablename__ = "lp_assessments"
    __table_args__ = (
        class_scope_fk(),
        UniqueConstraint("school_id", "class_id", "id", name="uq_lp_assessment_scope"),
        UniqueConstraint("school_id", "class_id", "family_id", "version", name="uq_lp_assessment_version"),
        CheckConstraint("version > 0 AND max_attempts > 0", name="ck_lp_assessment_limits"),
        CheckConstraint("status IN ('draft','published','closed')", name="ck_lp_assessment_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(36), default=new_id, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Attempt(PlatformBase):
    __tablename__ = "lp_attempts"
    __table_args__ = (
        class_scope_fk(),
        ForeignKeyConstraint(["school_id", "class_id", "assessment_id"],
                             ["lp_assessments.school_id", "lp_assessments.class_id", "lp_assessments.id"]),
        ForeignKeyConstraint(["school_id", "class_id", "student_code"],
                             ["lp_enrollments.school_id", "lp_enrollments.class_id", "lp_enrollments.student_code"]),
        UniqueConstraint("school_id", "class_id", "student_code", "submission_key", name="uq_lp_attempt_request"),
        UniqueConstraint("school_id", "class_id", "student_code", "id", name="uq_lp_attempt_owner"),
        CheckConstraint("score >= 0 AND score <= 10", name="ck_lp_attempt_score"),
        CheckConstraint("total_count > 0 AND correct_count >= 0 AND correct_count <= total_count", name="ck_lp_attempt_counts"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    student_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    submission_key: Mapped[str] = mapped_column(String(128), nullable=False)
    answers: Mapped[list] = mapped_column(JSON, nullable=False)
    response_times: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClassPlan(PlatformBase):
    __tablename__ = "lp_class_plans"
    __table_args__ = (
        class_scope_fk(),
        ForeignKeyConstraint(["school_id", "class_id", "student_code", "attempt_id"],
                             ["lp_attempts.school_id", "lp_attempts.class_id", "lp_attempts.student_code", "lp_attempts.id"]),
        UniqueConstraint("attempt_id", name="uq_lp_plan_attempt"),
        UniqueConstraint("school_id", "class_id", "student_code", "version", name="uq_lp_plan_version"),
        CheckConstraint("version > 0", name="ck_lp_plan_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    completion: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Intervention(PlatformBase):
    __tablename__ = "lp_interventions"
    __table_args__ = (
        class_scope_fk(),
        ForeignKeyConstraint(["school_id", "class_id", "student_code"],
                             ["lp_enrollments.school_id", "lp_enrollments.class_id", "lp_enrollments.student_code"]),
        CheckConstraint("status IN ('open','completed')", name="ck_lp_intervention_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_code: Mapped[str] = mapped_column(String(128), nullable=False)
    teacher_username: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Program(PlatformBase):
    __tablename__ = "lp_programs"
    __table_args__ = (
        CheckConstraint("seat_budget >= 0 AND ai_budget >= 0", name="ck_lp_program_budgets"),
        CheckConstraint("status IN ('active','paused','closed')", name="ck_lp_program_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    seat_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProgramMember(PlatformBase):
    __tablename__ = "lp_program_members"
    __table_args__ = (
        UniqueConstraint("program_id", "principal_school_id", "username", name="uq_lp_program_member"),
        CheckConstraint("program_role IN ('manager','analyst')", name="ck_lp_program_member_role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("lp_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_school_id: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    program_role: Mapped[str] = mapped_column(String(16), nullable=False)


class SchoolAllocation(PlatformBase):
    __tablename__ = "lp_school_allocations"
    __table_args__ = (
        UniqueConstraint("program_id", "school_id", name="uq_lp_school_allocation"),
        CheckConstraint("seats >= 0 AND ai_budget >= 0", name="ck_lp_allocation_budgets"),
        CheckConstraint("status IN ('active','suspended','revoked')", name="ck_lp_allocation_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("lp_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("lp_schools.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SchoolSummarySnapshot(PlatformBase):
    __tablename__ = "lp_school_summary_snapshots"
    __table_args__ = (
        CheckConstraint("cohort_threshold >= 5", name="ck_lp_snapshot_threshold"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("lp_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("lp_schools.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cohort_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditEvent(PlatformBase):
    __tablename__ = "lp_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    program_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


PLATFORM_TABLES = tuple(PlatformBase.metadata.sorted_tables)
