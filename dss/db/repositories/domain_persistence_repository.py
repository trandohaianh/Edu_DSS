"""Tenant-scoped durable boundary for academic, CMS and integration records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dss.core.observability import observed
from dss.db.models import (
    Assignment,
    Attendance,
    CmsContent,
    Course,
    Enrollment,
    Grade,
    IntegrationSyncState,
    LearningActivity,
    Lecturer,
    Organization,
    Student,
    Submission,
    WebhookInbox,
)
from dss.db.repositories.quota_repository import QuotaExceededError
from dss.db.session import tenant_session_scope


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _find(session, model, organization_id: int, external_id: str):
    return session.query(model).filter_by(organization_id=organization_id, external_id=external_id).one_or_none()


def _assert_active(session, organization_id: int) -> None:
    organization = session.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise PermissionError("organization is disabled or does not exist")


def _apply(row, values: dict[str, Any]) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(row, key) != value:
            setattr(row, key, value)
            changed = True
    return changed


@observed("academic.external_upsert", metadata=lambda organization_id, resource, record: {"resource": resource})
def upsert_external(organization_id: int, resource: str, record: dict[str, Any]) -> dict[str, Any]:
    """Idempotent `(organization_id, external_id)` upsert for Workstream A."""
    if int(record.get("organization_id", organization_id)) != organization_id:
        raise ValueError("record organization_id does not match tenant context")
    with tenant_session_scope(organization_id) as session:
        _assert_active(session, organization_id)
        if resource == "students":
            ext = record["student_external_id"]
            row = _find(session, Student, organization_id, ext)
            if row is None:
                from dss.db.models import Subscription

                sub = session.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
                count = session.query(Student).filter_by(organization_id=organization_id).count()
                if sub and sub.max_students is not None and count >= sub.max_students:
                    raise QuotaExceededError("students", sub.max_students, count, 1)
            values = {
                "student_code": record.get("student_code", ext),
                "full_name": record.get("display_name") or record.get("full_name") or ext,
                "is_active": record.get("is_active", True),
            }
            if row is None:
                row = Student(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "lecturers":
            ext = record["lecturer_external_id"]
            row = _find(session, Lecturer, organization_id, ext)
            values = {
                "lecturer_code": record.get("lecturer_code", ext),
                "full_name": record.get("display_name") or record.get("full_name") or ext,
                "department": record.get("department"),
            }
            if row is None:
                row = Lecturer(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "courses":
            ext = record["course_external_id"]
            row = _find(session, Course, organization_id, ext)
            lecturer = None
            if row is None:
                from dss.db.models import Subscription

                sub = session.query(Subscription).filter_by(organization_id=organization_id).one_or_none()
                count = session.query(Course).filter_by(organization_id=organization_id).count()
                if sub and sub.max_courses is not None and count >= sub.max_courses:
                    raise QuotaExceededError("courses", sub.max_courses, count, 1)
            if record.get("lecturer_external_id"):
                lecturer = _find(session, Lecturer, organization_id, record["lecturer_external_id"])
            values = {
                "course_code": record.get("course_code", ext),
                "title": record["title"],
                "semester": record.get("semester"),
                "lecturer_id": lecturer.id if lecturer else None,
            }
            if row is None:
                row = Course(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "enrollments":
            ext = record["enrollment_external_id"]
            student = _find(session, Student, organization_id, record["student_external_id"])
            course = _find(session, Course, organization_id, record["course_external_id"])
            if not student or not course:
                raise ValueError("enrollment references unknown tenant student/course")
            row = _find(session, Enrollment, organization_id, ext)
            values = {"student_id": student.id, "course_id": course.id, "status": record.get("status", "active")}
            if row is None:
                row = Enrollment(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "assignments":
            ext = record["assignment_external_id"]
            course = _find(session, Course, organization_id, record["course_external_id"])
            if not course:
                raise ValueError("assignment references unknown tenant course")
            row = _find(session, Assignment, organization_id, ext)
            values = {
                "course_id": course.id,
                "title": record["title"],
                "due_at": _dt(record.get("due_at")),
                "status": record.get("status", "active"),
            }
            if row is None:
                row = Assignment(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "submissions":
            ext = record["submission_external_id"]
            assignment = _find(session, Assignment, organization_id, record["assignment_external_id"])
            student = _find(session, Student, organization_id, record["student_external_id"])
            if not assignment or not student:
                raise ValueError("submission references unknown tenant entities")
            row = _find(session, Submission, organization_id, ext)
            values = {
                "assignment_id": assignment.id,
                "student_id": student.id,
                "status": record.get("status", "submitted"),
                "submitted_at": _dt(record.get("submitted_at")),
            }
            if row is None:
                row = Submission(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "grades":
            ext = record["grade_external_id"]
            student = _find(session, Student, organization_id, record["student_external_id"])
            course = _find(session, Course, organization_id, record["course_external_id"])
            submission = (
                _find(session, Submission, organization_id, record["submission_external_id"])
                if record.get("submission_external_id")
                else None
            )
            if not student or not course:
                raise ValueError("grade references unknown tenant entities")
            row = _find(session, Grade, organization_id, ext)
            values = {
                "student_id": student.id,
                "course_id": course.id,
                "submission_id": submission.id if submission else None,
                "score": float(record["score"]),
            }
            if row is None:
                row = Grade(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "attendance":
            ext = record["attendance_external_id"]
            student = _find(session, Student, organization_id, record["student_external_id"])
            course = _find(session, Course, organization_id, record["course_external_id"])
            if not student or not course:
                raise ValueError("attendance references unknown tenant entities")
            row = _find(session, Attendance, organization_id, ext)
            values = {
                "student_id": student.id,
                "course_id": course.id,
                "present": bool(record["present"]),
                "occurred_at": _dt(record["occurred_at"]),
            }
            if row is None:
                row = Attendance(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        elif resource == "activities":
            ext = record["activity_external_id"]
            student = _find(session, Student, organization_id, record["student_external_id"])
            course = _find(session, Course, organization_id, record["course_external_id"])
            if not student or not course:
                raise ValueError("activity references unknown tenant entities")
            row = _find(session, LearningActivity, organization_id, ext)
            values = {
                "student_id": student.id,
                "course_id": course.id,
                "activity_type": record["activity_type"],
                "duration_seconds": int(record.get("duration_seconds", 0)),
                "occurred_at": _dt(record["occurred_at"]),
            }
            if row is None:
                row = LearningActivity(organization_id=organization_id, external_id=ext, **values)
                session.add(row)
                created = True
            else:
                created = False
                _apply(row, values)
        else:
            raise ValueError(f"unsupported external resource: {resource}")
        session.flush()
        return {"id": row.id, "created": created, "external_id": ext}


def list_external(organization_id: int, resource: str) -> list[dict[str, Any]]:
    models = {
        "students": Student,
        "lecturers": Lecturer,
        "courses": Course,
        "enrollments": Enrollment,
        "assignments": Assignment,
        "submissions": Submission,
        "grades": Grade,
        "attendance": Attendance,
        "activities": LearningActivity,
    }
    model = models[resource]
    with tenant_session_scope(organization_id) as session:
        _assert_active(session, organization_id)
        return [
            {"id": r.id, "external_id": r.external_id, "organization_id": r.organization_id}
            for r in session.query(model).filter_by(organization_id=organization_id).all()
        ]


@observed("integration.sync_state.update")
def set_sync_state(
    organization_id: int, source: str, resource: str, *, cursor: str | None, status: str, error_code: str | None = None
) -> None:
    with tenant_session_scope(organization_id) as session:
        _assert_active(session, organization_id)
        row = (
            session.query(IntegrationSyncState)
            .filter_by(organization_id=organization_id, source=source, resource=resource)
            .one_or_none()
        )
        values = {
            "cursor": cursor,
            "status": status,
            "error_code": error_code,
            "last_success_at": datetime.now(UTC) if status == "success" else None,
        }
        if row is None:
            session.add(
                IntegrationSyncState(organization_id=organization_id, source=source, resource=resource, **values)
            )
        else:
            _apply(row, values)


def get_sync_state(organization_id: int, source: str, resource: str) -> dict[str, Any] | None:
    with tenant_session_scope(organization_id) as session:
        row = (
            session.query(IntegrationSyncState)
            .filter_by(organization_id=organization_id, source=source, resource=resource)
            .one_or_none()
        )
        return (
            None
            if row is None
            else {
                "cursor": row.cursor,
                "status": row.status,
                "error_code": row.error_code,
                "last_success_at": row.last_success_at,
            }
        )


@observed("integration.webhook.receive")
def receive_event(organization_id: int, source: str, event: dict[str, Any]) -> dict[str, Any]:
    if int(event.get("organization_id", organization_id)) != organization_id:
        raise ValueError("event organization mismatch")
    timestamp = _dt(event["source_timestamp"])
    with tenant_session_scope(organization_id) as session:
        _assert_active(session, organization_id)
        existing = (
            session.query(WebhookInbox)
            .filter_by(organization_id=organization_id, source=source, event_id=event["event_id"])
            .one_or_none()
        )
        if existing:
            return {"id": existing.id, "status": "duplicate"}
        latest = (
            session.query(WebhookInbox)
            .filter_by(
                organization_id=organization_id,
                source=source,
                event_type=event["event_type"],
                external_entity_id=event.get("external_entity_id"),
                processing_status="processed",
            )
            .order_by(WebhookInbox.source_timestamp.desc())
            .first()
        )
        status = "out_of_order" if latest and latest.source_timestamp > timestamp else "received"
        row = WebhookInbox(
            organization_id=organization_id,
            source=source,
            event_id=event["event_id"],
            event_type=event["event_type"],
            external_entity_id=event.get("external_entity_id"),
            source_timestamp=timestamp,
            processing_status=status,
            payload=event.get("payload", {}),
        )
        session.add(row)
        session.flush()
        return {"id": row.id, "status": status}


def mark_event(organization_id: int, event_id: str, *, status: str, error_code: str | None = None) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(WebhookInbox).filter_by(organization_id=organization_id, event_id=event_id).one()
        row.processing_status = status
        row.error_code = error_code
        row.processed_at = datetime.now(UTC) if status == "processed" else None
        if status == "retry":
            row.retry_count += 1


@observed("cms.content.upsert")
def upsert_cms_content(organization_id: int, record: dict[str, Any]) -> dict[str, Any]:
    if int(record.get("organization_id", organization_id)) != organization_id:
        raise ValueError("content organization mismatch")
    ext = record["content_external_id"]
    with tenant_session_scope(organization_id) as session:
        _assert_active(session, organization_id)
        row = _find(session, CmsContent, organization_id, ext)
        values = {
            "course_external_id": record.get("course_external_id"),
            "title": record["title"],
            "content_type": record.get("content_type", "document"),
            "source_reference": record.get("source_reference"),
            "mime_type": record.get("mime_type"),
            "checksum_sha256": record["checksum_sha256"],
            "size_bytes": int(record.get("size_bytes", 0)),
            "version": int(record.get("version", 1)),
            "status": record.get("status", "active"),
            "rag_document_id": record.get("rag_document_id"),
        }
        if row is None:
            row = CmsContent(organization_id=organization_id, external_id=ext, **values)
            session.add(row)
            created = True
        else:
            created = False
            _apply(row, values)
        session.flush()
        return {"id": row.id, "created": created, "rag_document_id": row.rag_document_id}


def get_cms_content(organization_id: int, external_id: str) -> dict[str, Any] | None:
    with tenant_session_scope(organization_id) as session:
        row = _find(session, CmsContent, organization_id, external_id)
        return (
            None
            if row is None
            else {
                "external_id": row.external_id,
                "title": row.title,
                "version": row.version,
                "status": row.status,
                "checksum_sha256": row.checksum_sha256,
                "rag_document_id": row.rag_document_id,
            }
        )
