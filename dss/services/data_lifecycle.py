"""Student data lifecycle — export, erasure/anonymization, retention (C1.1 foundation).

Scope: the PostgreSQL store, which is mandatory for production. Every operation
runs inside `tenant_session_scope(organization_id)` so PostgreSQL RLS confines it
to one university. Local JSON/demo stores are out of scope and reported as such.

Not every record can be physically deleted. Categories and their treatment:

| Category            | Tables                                                    | On erasure request          | Default retention |
|---------------------|-----------------------------------------------------------|-----------------------------|-------------------|
| ACADEMIC_RECORD     | academic_records, grades, attendance, enrollments,        | RETAIN (legal/academic      | institution policy|
|                     | submissions, learning_activities                          | record); linked to the      | (not auto-purged) |
|                     |                                                           | anonymized student row      |                   |
| IDENTITY            | students (full_name, external_id), users (student account)| ANONYMIZE in place          | –                 |
| AI_CONVERSATION     | consultations (question/answer), cms_student_interactions | DELETE                      | 365 days          |
| DERIVED_ANALYTICS   | predictions, recommendations                              | DELETE                      | 365 days          |
| AUDIT               | audit_logs, activity_logs                                 | RETAIN rows, REDACT personal| 1825 days         |
|                     |                                                           | content                     |                   |
| AI_USAGE            | ai_token_usage (pseudonymous counters)                    | RETAIN (pseudonymous)       | 400 days          |

Retention values can be overridden per deployment with
EDUDSS_RETENTION_<CATEGORY>_DAYS (e.g. EDUDSS_RETENTION_AI_CONVERSATION_DAYS=180).

Important operational notes (see C1_1_SECURITY_PRIVACY_HARDENING.md):
- An erased student can be re-created by the next LMS/SIS sync unless the source
  system is updated too — erasure must be mirrored upstream.
- Backups still contain erased data until they expire under the backup retention policy.
- Pseudonymous rows created before C1.1 used the old pseudonym scheme and are not
  matched by the keyed pseudonym; they fall under time-based retention.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

ACADEMIC_RECORD = "ACADEMIC_RECORD"
IDENTITY = "IDENTITY"
AI_CONVERSATION = "AI_CONVERSATION"
DERIVED_ANALYTICS = "DERIVED_ANALYTICS"
AUDIT = "AUDIT"
AI_USAGE = "AI_USAGE"

_DEFAULT_RETENTION_DAYS: Dict[str, Optional[int]] = {
    ACADEMIC_RECORD: None,   # governed by the institution's records policy — never auto-purged here
    IDENTITY: None,
    AI_CONVERSATION: 365,
    DERIVED_ANALYTICS: 365,
    AUDIT: 1825,
    AI_USAGE: 400,
}
REDACTED = "[đã ẩn theo yêu cầu xoá dữ liệu]"


@dataclass(frozen=True)
class RetentionRule:
    category: str
    days: Optional[int]
    erasure_action: str  # RETAIN | ANONYMIZE | DELETE | REDACT


def retention_policy() -> Dict[str, RetentionRule]:
    actions = {ACADEMIC_RECORD: "RETAIN", IDENTITY: "ANONYMIZE", AI_CONVERSATION: "DELETE",
               DERIVED_ANALYTICS: "DELETE", AUDIT: "REDACT", AI_USAGE: "RETAIN"}
    policy = {}
    for category, default_days in _DEFAULT_RETENTION_DAYS.items():
        raw = os.environ.get(f"EDUDSS_RETENTION_{category}_DAYS", "").strip()
        days = default_days
        if raw:
            try:
                days = max(1, int(raw))
            except ValueError:
                pass
        policy[category] = RetentionRule(category, days, actions[category])
    return policy


class StudentNotFound(LookupError):
    pass


@dataclass
class ErasureReport:
    organization_id: int
    student_code: str
    pseudonym: str
    deleted: Dict[str, int] = field(default_factory=dict)
    anonymized: Dict[str, int] = field(default_factory=dict)
    redacted: Dict[str, int] = field(default_factory=dict)
    retained: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Counts only — never personal content (safe to log / audit)."""
        return {"organization_id": self.organization_id, "pseudonym": self.pseudonym,
                "deleted": self.deleted, "anonymized": self.anonymized,
                "redacted": self.redacted, "retained": self.retained}


def _row_dict(row, exclude=()) -> Dict[str, Any]:
    out = {}
    for column in row.__table__.columns:
        if column.name in exclude:
            continue
        value = getattr(row, column.name)
        out[column.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


def _load_student(session, models, organization_id: int, student_code: str):
    student = session.query(models.Student).filter(
        models.Student.organization_id == organization_id,
        models.Student.student_code == student_code,
    ).one_or_none()
    if student is None:
        raise StudentNotFound("No such student in this organization.")
    return student


def _student_tables(models):
    return {
        ACADEMIC_RECORD: [models.AcademicRecord, models.Grade, models.Attendance, models.Enrollment,
                          models.Submission, models.LearningActivity],
        AI_CONVERSATION: [models.Consultation],
        DERIVED_ANALYTICS: [models.Prediction, models.Recommendation],
    }


def export_student_data(organization_id: int, student_code: str) -> Dict[str, Any]:
    """Everything EduDSS holds about one student, grouped by category (JSON-serializable).
    Password hashes/salts are never exported."""
    from dss.db import models
    from dss.db.session import tenant_session_scope
    from dss.services.privacy_service import generate_pseudonym

    pseudonym = generate_pseudonym(student_code, organization_id=organization_id)
    with tenant_session_scope(organization_id) as session:
        student = _load_student(session, models, organization_id, student_code)
        export: Dict[str, Any] = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "organization_id": organization_id,
            "retention_policy": {k: {"days": r.days, "on_erasure": r.erasure_action}
                                 for k, r in retention_policy().items()},
            IDENTITY: {"student": _row_dict(student)},
        }
        if student.user_id is not None:
            user = session.get(models.User, student.user_id)
            if user is not None:
                export[IDENTITY]["account"] = _row_dict(user, exclude=("password_hash", "password_salt"))
        for category, tables in _student_tables(models).items():
            export[category] = {
                table.__tablename__: [_row_dict(r) for r in session.query(table).filter(table.student_id == student.id)]
                for table in tables
            }
        export[AI_CONVERSATION]["cms_student_interactions"] = [
            _row_dict(r) for r in session.query(models.CmsStudentInteraction).filter(
                models.CmsStudentInteraction.student_pseudonym == pseudonym)]
        export[AI_USAGE] = {"ai_token_usage": [
            _row_dict(r) for r in session.query(models.AiTokenUsage).filter(models.AiTokenUsage.user_id == pseudonym)]}
        if student.user_id is not None:
            export[AUDIT] = {"activity_logs": [
                _row_dict(r) for r in session.query(models.ActivityLog).filter(models.ActivityLog.user_id == student.user_id)]}
    return export


def erase_student_data(organization_id: int, student_code: str, requested_by: str) -> ErasureReport:
    """Right-to-erasure within academic/legal limits, in ONE transaction:
    delete AI conversations and derived analytics, anonymize identity, redact the
    student's own activity-log content, retain academic records (linked to the now
    anonymous student row) and pseudonymous usage counters. Writes one audit event
    containing counts only."""
    from dss.db import models
    from dss.db.session import tenant_session_scope
    from dss.services.privacy_service import generate_pseudonym

    pseudonym = generate_pseudonym(student_code, organization_id=organization_id)
    report = ErasureReport(organization_id=organization_id, student_code="[redacted]", pseudonym=pseudonym)
    with tenant_session_scope(organization_id) as session:
        student = _load_student(session, models, organization_id, student_code)
        tables = _student_tables(models)
        for table in tables[AI_CONVERSATION] + tables[DERIVED_ANALYTICS]:
            report.deleted[table.__tablename__] = session.query(table).filter(
                table.student_id == student.id).delete(synchronize_session=False)
        report.deleted["cms_student_interactions"] = session.query(models.CmsStudentInteraction).filter(
            models.CmsStudentInteraction.student_pseudonym == pseudonym).delete(synchronize_session=False)
        for table in tables[ACADEMIC_RECORD]:
            report.retained[table.__tablename__] = session.query(table).filter(table.student_id == student.id).count()
        report.retained["ai_token_usage"] = session.query(models.AiTokenUsage).filter(
            models.AiTokenUsage.user_id == pseudonym).count()

        # "erased-" + 20 base32 chars = 27 <= 32 (students.student_code) — unique per student
        erased_label = "erased-" + pseudonym.split("_", 1)[-1]
        student.full_name = REDACTED
        student.external_id = None
        student.student_code = erased_label
        student.is_active = False
        report.anonymized["students"] = 1
        if student.user_id is not None:
            user = session.get(models.User, student.user_id)
            if user is not None:
                user.username = erased_label
                user.email = None
                user.student_id = None
                user.is_active = False
                # unusable credential: random hash that no password can match
                user.password_hash = "erased$" + secrets.token_hex(32)
                user.password_salt = secrets.token_hex(16)
                report.anonymized["users"] = 1
            activity = session.query(models.ActivityLog).filter(models.ActivityLog.user_id == student.user_id)
            report.redacted["activity_logs"] = activity.update(
                {models.ActivityLog.description: REDACTED, models.ActivityLog.details: None},
                synchronize_session=False)
            audit = session.query(models.AuditLog).filter(models.AuditLog.actor_user_id == student.user_id)
            report.redacted["audit_logs"] = audit.update(
                {models.AuditLog.actor_username: erased_label}, synchronize_session=False)

        session.add(models.AuditLog(
            organization_id=organization_id, actor_user_id=None, actor_username=str(requested_by)[:128],
            action="privacy.student_erasure", target_type="student", target_id=pseudonym,
            before=None, after=report.as_dict(),
        ))
    return report


def purge_expired(organization_id: int, now: Optional[datetime] = None) -> Dict[str, int]:
    """Time-based retention for categories with a finite retention period.
    ACADEMIC_RECORD and IDENTITY are never purged here."""
    from dss.db import models
    from dss.db.session import tenant_session_scope

    now = now or datetime.now(timezone.utc)
    policy = retention_policy()
    targets = [
        (AI_CONVERSATION, models.Consultation, models.Consultation.created_at),
        (AI_CONVERSATION, models.CmsStudentInteraction, models.CmsStudentInteraction.created_at),
        (DERIVED_ANALYTICS, models.Prediction, models.Prediction.created_at),
        (DERIVED_ANALYTICS, models.Recommendation, models.Recommendation.created_at),
        (AI_USAGE, models.AiTokenUsage, models.AiTokenUsage.timestamp),
        (AUDIT, models.ActivityLog, models.ActivityLog.created_at),
        (AUDIT, models.AuditLog, models.AuditLog.created_at),
    ]
    purged: Dict[str, int] = {}
    with tenant_session_scope(organization_id) as session:
        for category, table, column in targets:
            days = policy[category].days
            if not days:
                continue
            cutoff = now - timedelta(days=days)
            purged[table.__tablename__] = purged.get(table.__tablename__, 0) + session.query(table).filter(
                table.organization_id == organization_id, column < cutoff).delete(synchronize_session=False)
    return purged
