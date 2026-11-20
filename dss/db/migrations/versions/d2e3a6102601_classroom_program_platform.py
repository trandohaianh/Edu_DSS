"""Classrooms, evidence-based plans and programme allocations with forced RLS.

Revision ID: d2e3a6102601
Revises: 9f3a1c7d2e46
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3a6102601"
down_revision = "9f3a1c7d2e46"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE lp_audit_events (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64), 
	program_id VARCHAR(36), 
	actor VARCHAR(255) NOT NULL, 
	action VARCHAR(128) NOT NULL, 
	entity_id VARCHAR(128) NOT NULL, 
	details JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE INDEX ix_lp_audit_events_program_id ON lp_audit_events (program_id)""",
    """CREATE INDEX ix_lp_audit_events_school_id ON lp_audit_events (school_id)""",
    """CREATE TABLE lp_programs (
	id VARCHAR(36) NOT NULL, 
	code VARCHAR(128) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	seat_budget INTEGER NOT NULL, 
	ai_budget INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_lp_program_budgets CHECK (seat_budget >= 0 AND ai_budget >= 0), 
	CONSTRAINT ck_lp_program_status CHECK (status IN ('active','paused','closed')), 
	UNIQUE (code)
)""",
    """CREATE TABLE lp_schools (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE TABLE lp_classes (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	code VARCHAR(128) NOT NULL, 
	course_id VARCHAR(128) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	term VARCHAR(128) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lp_class_scope UNIQUE (school_id, id), 
	CONSTRAINT uq_lp_class_code_term UNIQUE (school_id, code, term), 
	CONSTRAINT ck_lp_class_status CHECK (status IN ('active','closed')), 
	FOREIGN KEY(school_id) REFERENCES lp_schools (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lp_classes_school_id ON lp_classes (school_id)""",
    """CREATE TABLE lp_program_members (
	id VARCHAR(36) NOT NULL, 
	program_id VARCHAR(36) NOT NULL, 
	principal_school_id VARCHAR(64) NOT NULL, 
	username VARCHAR(128) NOT NULL, 
	program_role VARCHAR(16) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lp_program_member UNIQUE (program_id, principal_school_id, username), 
	CONSTRAINT ck_lp_program_member_role CHECK (program_role IN ('manager','analyst')), 
	FOREIGN KEY(program_id) REFERENCES lp_programs (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lp_program_members_program_id ON lp_program_members (program_id)""",
    """CREATE TABLE lp_school_allocations (
	id VARCHAR(36) NOT NULL, 
	program_id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	seats INTEGER NOT NULL, 
	ai_budget INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lp_school_allocation UNIQUE (program_id, school_id), 
	CONSTRAINT ck_lp_allocation_budgets CHECK (seats >= 0 AND ai_budget >= 0), 
	CONSTRAINT ck_lp_allocation_status CHECK (status IN ('active','suspended','revoked')), 
	FOREIGN KEY(program_id) REFERENCES lp_programs (id) ON DELETE CASCADE, 
	FOREIGN KEY(school_id) REFERENCES lp_schools (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lp_school_allocations_program_id ON lp_school_allocations (program_id)""",
    """CREATE INDEX ix_lp_school_allocations_school_id ON lp_school_allocations (school_id)""",
    """CREATE TABLE lp_school_summary_snapshots (
	id VARCHAR(36) NOT NULL, 
	program_id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	as_of TIMESTAMP WITH TIME ZONE NOT NULL, 
	metric_version VARCHAR(64) NOT NULL, 
	metrics JSON NOT NULL, 
	suppressed BOOLEAN NOT NULL, 
	cohort_threshold INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_lp_snapshot_threshold CHECK (cohort_threshold >= 5), 
	FOREIGN KEY(program_id) REFERENCES lp_programs (id) ON DELETE CASCADE, 
	FOREIGN KEY(school_id) REFERENCES lp_schools (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lp_school_summary_snapshots_program_id ON lp_school_summary_snapshots (program_id)""",
    """CREATE INDEX ix_lp_school_summary_snapshots_school_id ON lp_school_summary_snapshots (school_id)""",
    """CREATE TABLE lp_assessments (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	family_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	questions JSON NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_lp_assessment_scope UNIQUE (school_id, class_id, id), 
	CONSTRAINT uq_lp_assessment_version UNIQUE (school_id, class_id, family_id, version), 
	CONSTRAINT ck_lp_assessment_limits CHECK (version > 0 AND max_attempts > 0), 
	CONSTRAINT ck_lp_assessment_status CHECK (status IN ('draft','published','closed'))
)""",
    """CREATE INDEX ix_lp_assessments_class_id ON lp_assessments (class_id)""",
    """CREATE INDEX ix_lp_assessments_school_id ON lp_assessments (school_id)""",
    """CREATE TABLE lp_enrollments (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	student_code VARCHAR(128) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_lp_enrollment_owner UNIQUE (school_id, class_id, student_code)
)""",
    """CREATE INDEX ix_lp_enrollments_class_id ON lp_enrollments (class_id)""",
    """CREATE INDEX ix_lp_enrollments_school_id ON lp_enrollments (school_id)""",
    """CREATE INDEX ix_lp_enrollments_student_code ON lp_enrollments (student_code)""",
    """CREATE TABLE lp_teaching_assignments (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	teacher_username VARCHAR(128) NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_lp_teacher_assignment UNIQUE (school_id, class_id, teacher_username)
)""",
    """CREATE INDEX ix_lp_teaching_assignments_class_id ON lp_teaching_assignments (class_id)""",
    """CREATE INDEX ix_lp_teaching_assignments_school_id ON lp_teaching_assignments (school_id)""",
    """CREATE TABLE lp_attempts (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	assessment_id VARCHAR(36) NOT NULL, 
	student_code VARCHAR(128) NOT NULL, 
	submission_key VARCHAR(128) NOT NULL, 
	answers JSON NOT NULL, 
	response_times JSON, 
	score FLOAT NOT NULL, 
	correct_count INTEGER NOT NULL, 
	total_count INTEGER NOT NULL, 
	topic_scores JSON NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	FOREIGN KEY(school_id, class_id, assessment_id) REFERENCES lp_assessments (school_id, class_id, id), 
	FOREIGN KEY(school_id, class_id, student_code) REFERENCES lp_enrollments (school_id, class_id, student_code), 
	CONSTRAINT uq_lp_attempt_request UNIQUE (school_id, class_id, student_code, submission_key), 
	CONSTRAINT uq_lp_attempt_owner UNIQUE (school_id, class_id, student_code, id), 
	CONSTRAINT ck_lp_attempt_score CHECK (score >= 0 AND score <= 10), 
	CONSTRAINT ck_lp_attempt_counts CHECK (total_count > 0 AND correct_count >= 0 AND correct_count <= total_count)
)""",
    """CREATE INDEX ix_lp_attempts_class_id ON lp_attempts (class_id)""",
    """CREATE INDEX ix_lp_attempts_school_id ON lp_attempts (school_id)""",
    """CREATE INDEX ix_lp_attempts_student_code ON lp_attempts (student_code)""",
    """CREATE TABLE lp_interventions (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	student_code VARCHAR(128) NOT NULL, 
	teacher_username VARCHAR(128) NOT NULL, 
	reason TEXT NOT NULL, 
	action TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	FOREIGN KEY(school_id, class_id, student_code) REFERENCES lp_enrollments (school_id, class_id, student_code), 
	CONSTRAINT ck_lp_intervention_status CHECK (status IN ('open','completed'))
)""",
    """CREATE INDEX ix_lp_interventions_class_id ON lp_interventions (class_id)""",
    """CREATE INDEX ix_lp_interventions_school_id ON lp_interventions (school_id)""",
    """CREATE TABLE lp_class_plans (
	id VARCHAR(36) NOT NULL, 
	school_id VARCHAR(64) NOT NULL, 
	class_id VARCHAR(36) NOT NULL, 
	student_code VARCHAR(128) NOT NULL, 
	attempt_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	plan JSON NOT NULL, 
	completion JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_id, class_id) REFERENCES lp_classes (school_id, id) ON DELETE CASCADE, 
	FOREIGN KEY(school_id, class_id, student_code, attempt_id) REFERENCES lp_attempts (school_id, class_id, student_code, id), 
	CONSTRAINT uq_lp_plan_attempt UNIQUE (attempt_id), 
	CONSTRAINT uq_lp_plan_version UNIQUE (school_id, class_id, student_code, version), 
	CONSTRAINT ck_lp_plan_version CHECK (version > 0)
)""",
    """CREATE INDEX ix_lp_class_plans_class_id ON lp_class_plans (class_id)""",
    """CREATE INDEX ix_lp_class_plans_school_id ON lp_class_plans (school_id)""",
    """CREATE INDEX ix_lp_class_plans_student_code ON lp_class_plans (student_code)""",
)

TABLES = ('lp_audit_events', 'lp_programs', 'lp_schools', 'lp_classes', 'lp_program_members', 'lp_school_allocations', 'lp_school_summary_snapshots', 'lp_assessments', 'lp_enrollments', 'lp_teaching_assignments', 'lp_attempts', 'lp_interventions', 'lp_class_plans')

# These expressions read transaction-local values bound by platform_session.
SCHOOL = "current_setting('app.organization_id', true)"
PRINCIPAL = "current_setting('app.principal_school_id', true)"
USERNAME = "current_setting('app.actor_username', true)"
ROLE = "current_setting('app.actor_role', true)"
OPERATOR = "current_setting('app.platform_operator', true) = 'true'"
SELF = f"m.principal_school_id = {PRINCIPAL} AND m.username = {USERNAME}"


def member(program, manager=False):
    role = " AND m.program_role = 'manager'" if manager else ""
    return f"EXISTS (SELECT 1 FROM lp_program_members m WHERE m.program_id = {program} AND {SELF}{role})"


def policy(table, name, command, using=None, check=None):
    sql = f"CREATE POLICY {name} ON {table} FOR {command}"
    if using is not None:
        sql += f" USING ({using})"
    if check is not None:
        sql += f" WITH CHECK ({check})"
    op.execute(sa.text(sql))


def upgrade():
    # Preserve the existing integer Course FK; CMS uses external course codes.
    op.add_column("rag_documents", sa.Column("course_code", sa.String(128), nullable=True))
    op.execute(sa.text("UPDATE rag_documents r SET course_code = c.course_code FROM courses c WHERE c.id = r.course_id AND c.organization_id = r.organization_id"))
    for sql in DDL:
        op.execute(sa.text(sql))
    for table in TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    # Raw learning records remain school scoped. Programme membership alone
    # never satisfies these policies.
    for table in (
        "lp_classes", "lp_teaching_assignments", "lp_enrollments",
        "lp_assessments", "lp_attempts", "lp_class_plans", "lp_interventions",
    ):
        scope = f"school_id = {SCHOOL}"
        policy(table, "school_scope", "ALL", scope, scope)

    # Self-only member visibility avoids recursive RLS when other tables
    # consult membership. Operators provision members explicitly.
    own_member = f"principal_school_id = {PRINCIPAL} AND username = {USERNAME}"
    policy("lp_program_members", "member_read", "SELECT", f"({own_member}) OR ({OPERATOR})")
    policy("lp_program_members", "member_insert", "INSERT", check=OPERATOR)
    policy("lp_program_members", "member_update", "UPDATE", OPERATOR, OPERATOR)
    policy("lp_program_members", "member_delete", "DELETE", OPERATOR)

    manager_directory = f"EXISTS (SELECT 1 FROM lp_program_members m WHERE {SELF} AND m.program_role = 'manager')"
    allocated_directory = f"EXISTS (SELECT 1 FROM lp_school_allocations a WHERE a.school_id = lp_schools.id AND {member('a.program_id')})"
    own_school = f"id = {SCHOOL}"
    school_write = f"({OPERATOR}) OR ({own_school} AND {ROLE} = 'Admin')"
    policy("lp_schools", "school_directory_read", "SELECT", f"({own_school}) OR ({OPERATOR}) OR ({manager_directory}) OR ({allocated_directory})")
    policy("lp_schools", "school_directory_insert", "INSERT", check=school_write)
    policy("lp_schools", "school_directory_update", "UPDATE", school_write, school_write)

    program_read = f"({OPERATOR}) OR ({member('lp_programs.id')}) OR EXISTS (SELECT 1 FROM lp_school_allocations a WHERE a.program_id = lp_programs.id AND a.school_id = {SCHOOL})"
    program_update = f"({OPERATOR}) OR ({member('lp_programs.id', manager=True)})"
    policy("lp_programs", "program_read", "SELECT", program_read)
    policy("lp_programs", "program_insert", "INSERT", check=OPERATOR)
    policy("lp_programs", "program_update", "UPDATE", program_update, program_update)

    allocation_read = f"school_id = {SCHOOL} OR ({OPERATOR}) OR ({member('lp_school_allocations.program_id')})"
    allocation_write = member("lp_school_allocations.program_id", manager=True)
    policy("lp_school_allocations", "allocation_read", "SELECT", allocation_read)
    policy("lp_school_allocations", "allocation_insert", "INSERT", check=allocation_write)
    policy("lp_school_allocations", "allocation_update", "UPDATE", allocation_write, allocation_write)

    own_snapshot = f"school_id = {SCHOOL} AND {ROLE} = 'Admin' AND {SCHOOL} = {PRINCIPAL}"
    policy("lp_school_summary_snapshots", "snapshot_read", "SELECT", f"({own_snapshot}) OR ({member('lp_school_summary_snapshots.program_id')})")
    allocation_exists = f"EXISTS (SELECT 1 FROM lp_school_allocations a WHERE a.program_id = lp_school_summary_snapshots.program_id AND a.school_id = {SCHOOL} AND a.status = 'active')"
    policy("lp_school_summary_snapshots", "snapshot_insert", "INSERT", check=f"({own_snapshot}) AND ({allocation_exists})")

    own_audit = f"school_id = {SCHOOL} AND school_id = {PRINCIPAL}"
    program_audit = f"program_id IS NOT NULL AND ({member('lp_audit_events.program_id')})"
    operator_audit = f"school_id IS NULL AND ({OPERATOR})"
    policy("lp_audit_events", "audit_read", "SELECT", f"({own_audit}) OR ({program_audit}) OR ({operator_audit})")
    policy("lp_audit_events", "audit_insert", "INSERT", check=f"school_id = {SCHOOL} OR ({program_audit}) OR ({OPERATOR})")


def downgrade():
    # Drop referencing policies before their referenced tables; keep rollback
    # limited to objects introduced here instead of using DROP ... CASCADE.
    names = {
        "lp_schools": ("school_directory_read", "school_directory_insert", "school_directory_update"),
        "lp_program_members": ("member_read", "member_insert", "member_update", "member_delete"),
        "lp_programs": ("program_read", "program_insert", "program_update"),
        "lp_school_allocations": ("allocation_read", "allocation_insert", "allocation_update"),
        "lp_school_summary_snapshots": ("snapshot_read", "snapshot_insert"),
        "lp_audit_events": ("audit_read", "audit_insert"),
    }
    for table in TABLES:
        for name in names.get(table, ("school_scope",)):
            op.execute(sa.text(f"DROP POLICY {name} ON {table}"))
    op.drop_column("rag_documents", "course_code")
    for table in reversed(TABLES):
        op.execute(sa.text(f"DROP TABLE {table}"))
