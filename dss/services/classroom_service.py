"""School/class authorization and official teaching/enrollment assignments."""
from __future__ import annotations

import os

from sqlalchemy import func, select

from dss.platform.context import Actor
from dss.platform.models import (
    ClassEnrollment, Classroom, Intervention, Program, School, SchoolAllocation,
    TeachingAssignment, utcnow,
)
from dss.platform.store import audit, platform_session

ADMIN = "Admin"
TEACHER = "Giảng viên / CVHT"
STUDENT = "Sinh viên"


def _text(value, field, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field} must be nonempty and at most {maximum} characters.")
    return value.strip()


def _admin(actor):
    if actor.role != ADMIN:
        raise PermissionError("School administrator access is required.")


def require_class_access(session, actor: Actor, class_id: str, staff: bool = False) -> Classroom:
    classroom = session.get(Classroom, str(class_id))
    if classroom is None or classroom.school_id != actor.school_id:
        raise PermissionError("Class access is unavailable.")
    if actor.role == ADMIN:
        return classroom
    if actor.role == TEACHER:
        assignment = session.scalar(select(TeachingAssignment).where(
            TeachingAssignment.school_id == actor.school_id,
            TeachingAssignment.class_id == classroom.id,
            TeachingAssignment.teacher_username == actor.username,
            TeachingAssignment.active.is_(True),
        ))
        if assignment is not None:
            return classroom
    if not staff and actor.role == STUDENT and actor.student_id:
        enrolled = session.scalar(select(ClassEnrollment).where(
            ClassEnrollment.school_id == actor.school_id,
            ClassEnrollment.class_id == classroom.id,
            ClassEnrollment.student_code == actor.student_id,
            ClassEnrollment.active.is_(True),
        ))
        if enrolled is not None:
            return classroom
    raise PermissionError("Class access is unavailable.")


def require_school_writes(session, actor: Actor):
    """Return the current school seat cap; reads never call this eligibility gate."""
    school = session.get(School, actor.school_id)
    if school is None or not school.active:
        raise PermissionError("The school is unavailable for new learning operations.")
    allocations = session.scalars(select(SchoolAllocation).where(
        SchoolAllocation.school_id == actor.school_id,
    )).all()
    caps = []
    for allocation in allocations:
        program = session.get(Program, allocation.program_id)
        if allocation.status == "active" and program is not None and program.status == "active":
            caps.append(allocation.seats)
    managed = os.environ.get("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "").strip().lower()
    require_allocation = managed not in {"", "0", "false", "no", "off"}
    if not caps and (allocations or require_allocation):
        raise PermissionError("An active programme allocation is required for new learning operations.")
    return min(caps) if caps else None


def _active_class(classroom):
    if classroom.status != "active":
        raise PermissionError("This class is closed for new learning operations.")


def active_student_count(session, school_id):
    return session.scalar(select(func.count(func.distinct(ClassEnrollment.student_code))).join(
        Classroom,
        (ClassEnrollment.class_id == Classroom.id) & (ClassEnrollment.school_id == Classroom.school_id),
    ).where(
        ClassEnrollment.school_id == str(school_id),
        ClassEnrollment.active.is_(True), Classroom.status == "active",
    )) or 0


def _class_dict(row):
    return {
        "id": row.id, "school_id": row.school_id, "code": row.code,
        "course_id": row.course_id, "title": row.title, "term": row.term,
        "status": row.status, "created_at": row.created_at.isoformat(),
    }


def create_class(actor: Actor, code: str, course_id: str, title: str, term: str):
    _admin(actor)
    values = dict(code=_text(code, "code"), course_id=_text(course_id, "course_id"),
                  title=_text(title, "title", 255), term=_text(term, "term"))
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        school = session.get(School, actor.school_id)
        if school is None:
            # A dedicated-school administrator may establish only their own
            # school metadata. Cross-school provisioning is a separate service.
            school = School(id=actor.school_id, name=os.environ.get("EDUDSS_ORGANIZATION_NAME", "").strip() or f"School {actor.school_id}")
            session.add(school)
            session.flush()
        require_school_writes(session, actor)
        existing = session.scalar(select(Classroom).where(
            Classroom.school_id == actor.school_id, Classroom.code == values["code"], Classroom.term == values["term"],
        ))
        if existing:
            if existing.course_id != values["course_id"] or existing.title != values["title"]:
                raise ValueError("This class code/term already has different metadata.")
            return _class_dict(existing)
        row = Classroom(school_id=actor.school_id, **values)
        session.add(row)
        session.flush()
        audit(session, actor, "class.created", row.id, school_id=actor.school_id)
        return _class_dict(row)


def assign_teacher(actor: Actor, class_id: str, teacher_username: str):
    _admin(actor)
    username = _text(teacher_username, "teacher_username")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        require_school_writes(session, actor)
        _active_class(classroom)
        row = session.scalar(select(TeachingAssignment).where(
            TeachingAssignment.school_id == actor.school_id, TeachingAssignment.class_id == classroom.id,
            TeachingAssignment.teacher_username == username,
        ))
        if row is None:
            row = TeachingAssignment(school_id=actor.school_id, class_id=classroom.id, teacher_username=username)
            session.add(row)
        elif row.active:
            return {"class_id": classroom.id, "teacher_username": username, "active": True}
        row.active = True
        session.flush()
        audit(session, actor, "teacher.assigned", row.id, school_id=actor.school_id, details={"class_id": classroom.id})
        return {"class_id": classroom.id, "teacher_username": username, "active": True}


def revoke_teacher(actor: Actor, class_id: str, teacher_username: str):
    _admin(actor)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        row = session.scalar(select(TeachingAssignment).where(
            TeachingAssignment.school_id == actor.school_id, TeachingAssignment.class_id == classroom.id,
            TeachingAssignment.teacher_username == teacher_username,
        ))
        revoked = row is not None and row.active
        if revoked:
            row.active = False
            audit(session, actor, "teacher.revoked", row.id, school_id=actor.school_id, details={"class_id": classroom.id})
            session.flush()
            still = _still_teaches(session, actor.school_id, classroom.course_id, teacher_username)
        course_id = classroom.course_id
        result = {"class_id": classroom.id, "teacher_username": teacher_username, "active": False}
    if revoked and not still:
        _engine_deactivate(actor, course_id, teacher_username, "instructor")
    return result


def enroll_student(actor: Actor, class_id: str, student_code: str):
    _admin(actor)
    code = _text(student_code, "student_code")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        cap = require_school_writes(session, actor)
        _active_class(classroom)
        row = session.scalar(select(ClassEnrollment).where(
            ClassEnrollment.school_id == actor.school_id, ClassEnrollment.class_id == classroom.id,
            ClassEnrollment.student_code == code,
        ))
        if row is not None and row.active:
            return {"class_id": classroom.id, "student_code": code, "active": True}
        already_counted = session.scalar(select(ClassEnrollment.id).join(
            Classroom, (ClassEnrollment.class_id == Classroom.id) & (ClassEnrollment.school_id == Classroom.school_id),
        ).where(
            ClassEnrollment.school_id == actor.school_id, ClassEnrollment.student_code == code,
            ClassEnrollment.active.is_(True), Classroom.status == "active",
        ).limit(1))
        if cap is not None and already_counted is None and active_student_count(session, actor.school_id) >= cap:
            raise ValueError("The school's allocated student capacity has been reached.")
        if row is None:
            row = ClassEnrollment(school_id=actor.school_id, class_id=classroom.id, student_code=code)
            session.add(row)
        row.active = True
        session.flush()
        audit(session, actor, "student.enrolled", row.id, school_id=actor.school_id, details={"class_id": classroom.id})
        return {"class_id": classroom.id, "student_code": code, "active": True}


def unenroll_student(actor: Actor, class_id: str, student_code: str):
    _admin(actor)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        row = session.scalar(select(ClassEnrollment).where(
            ClassEnrollment.school_id == actor.school_id, ClassEnrollment.class_id == classroom.id,
            ClassEnrollment.student_code == student_code,
        ))
        removed = row is not None and row.active
        if removed:
            row.active = False
            audit(session, actor, "student.unenrolled", row.id, school_id=actor.school_id, details={"class_id": classroom.id})
            session.flush()
            still = _still_enrolled(session, actor.school_id, classroom.course_id, student_code)
        course_id = classroom.course_id
        result = {"class_id": classroom.id, "student_code": student_code, "active": False}
    if removed and not still:
        for username in _student_usernames(student_code):
            _engine_deactivate(actor, course_id, username, "student", student_code)
    return result


def set_class_status(actor: Actor, class_id: str, status: str):
    _admin(actor)
    if status not in {"active", "closed"}:
        raise ValueError("Class status must be active or closed.")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        if status == "active":
            cap = require_school_writes(session, actor)
            classroom.status = status
            session.flush()
            if cap is not None and active_student_count(session, actor.school_id) > cap:
                raise ValueError("Reopening this class exceeds the school allocation.")
        else:
            classroom.status = status
        audit(session, actor, "class.status_changed", classroom.id, school_id=actor.school_id, details={"status": status})
        return _class_dict(classroom)


def list_my_classes(actor: Actor):
    with platform_session(actor.school_id, actor=actor) as session:
        query = select(Classroom).where(Classroom.school_id == actor.school_id)
        if actor.role == TEACHER:
            query = query.join(TeachingAssignment, (TeachingAssignment.class_id == Classroom.id) & (TeachingAssignment.school_id == Classroom.school_id)).where(
                TeachingAssignment.teacher_username == actor.username, TeachingAssignment.active.is_(True),
            )
        elif actor.role == STUDENT and actor.student_id:
            query = query.join(ClassEnrollment, (ClassEnrollment.class_id == Classroom.id) & (ClassEnrollment.school_id == Classroom.school_id)).where(
                ClassEnrollment.student_code == actor.student_id, ClassEnrollment.active.is_(True),
            )
        elif actor.role != ADMIN:
            raise PermissionError("Classroom access is unavailable for this role.")
        return [_class_dict(row) for row in session.scalars(query.order_by(Classroom.term.desc(), Classroom.code)).all()]


def list_class_roster(actor: Actor, class_id: str, *, include_inactive: bool = False):
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id, staff=True)
        query = select(ClassEnrollment).where(ClassEnrollment.school_id == actor.school_id, ClassEnrollment.class_id == class_id)
        if not include_inactive:
            query = query.where(ClassEnrollment.active.is_(True))
        return [{"student_code": row.student_code, "active": row.active} for row in session.scalars(query.order_by(ClassEnrollment.student_code)).all()]


def create_intervention(actor: Actor, class_id: str, student_code: str, reason: str, action: str):
    reason, action = _text(reason, "reason", 4000), _text(action, "action", 4000)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        require_school_writes(session, actor)
        _active_class(classroom)
        enrollment = session.scalar(select(ClassEnrollment.id).where(
            ClassEnrollment.school_id == actor.school_id, ClassEnrollment.class_id == class_id,
            ClassEnrollment.student_code == student_code, ClassEnrollment.active.is_(True),
        ))
        if enrollment is None:
            raise PermissionError("The selected learner is not enrolled in this class.")
        row = Intervention(school_id=actor.school_id, class_id=class_id, student_code=student_code,
                           teacher_username=actor.username, reason=reason, action=action)
        session.add(row)
        session.flush()
        audit(session, actor, "intervention.created", row.id, school_id=actor.school_id, details={"class_id": class_id})
        return _intervention_dict(row)


def _intervention_dict(row):
    return {"id": row.id, "class_id": row.class_id, "student_code": row.student_code,
            "teacher_username": row.teacher_username, "reason": row.reason, "action": row.action,
            "status": row.status, "created_at": row.created_at.isoformat(),
            "closed_at": row.closed_at.isoformat() if row.closed_at else None}


def list_interventions(actor: Actor, class_id: str):
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id)
        query = select(Intervention).where(Intervention.school_id == actor.school_id, Intervention.class_id == class_id)
        if actor.role == STUDENT:
            query = query.where(Intervention.student_code == actor.student_id)
        return [_intervention_dict(row) for row in session.scalars(query.order_by(Intervention.created_at.desc())).all()]


def close_intervention(actor: Actor, intervention_id: str):
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row = session.get(Intervention, intervention_id)
        if row is None or row.school_id != actor.school_id:
            raise PermissionError("Intervention access is unavailable.")
        require_class_access(session, actor, row.class_id, staff=True)
        if row.status != "completed":
            row.status, row.closed_at = "completed", utcnow()
            audit(session, actor, "intervention.completed", row.id, school_id=actor.school_id)
        return _intervention_dict(row)


def list_teaching_assignments(actor: Actor, class_id: str):
    """List official assignments for the school administrator."""
    _admin(actor)
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id, staff=True)
        rows = session.scalars(select(TeachingAssignment).where(
            TeachingAssignment.school_id == actor.school_id,
            TeachingAssignment.class_id == class_id,
        ).order_by(TeachingAssignment.teacher_username)).all()
        return [{"class_id": class_id, "teacher_username": row.teacher_username,
                 "active": row.active} for row in rows]


def import_enrollments(actor: Actor, class_id: str, student_codes):
    """Import one validated roster atomically, counting distinct school learners."""
    _admin(actor)
    if isinstance(student_codes, (str, bytes)):
        raise ValueError("student_codes must be a collection of student codes.")
    try:
        codes = sorted({_text(code, "student_code") for code in student_codes})
    except TypeError as exc:
        raise ValueError("student_codes must be a collection of student codes.") from exc
    if len(codes) > 10000:
        raise ValueError("A roster import cannot exceed 10000 unique learners.")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        cap = require_school_writes(session, actor)
        _active_class(classroom)
        counted = set(session.scalars(select(ClassEnrollment.student_code).join(
            Classroom,
            (ClassEnrollment.class_id == Classroom.id) & (ClassEnrollment.school_id == Classroom.school_id),
        ).where(
            ClassEnrollment.school_id == actor.school_id,
            ClassEnrollment.active.is_(True), Classroom.status == "active",
        ).distinct()).all())
        if cap is not None and len(counted | set(codes)) > cap:
            raise ValueError("This roster exceeds the school's allocated student capacity.")
        existing = {row.student_code: row for row in session.scalars(select(ClassEnrollment).where(
            ClassEnrollment.school_id == actor.school_id,
            ClassEnrollment.class_id == classroom.id,
        )).all()}
        added = reactivated = unchanged = 0
        for code in codes:
            row = existing.get(code)
            if row is None:
                session.add(ClassEnrollment(school_id=actor.school_id, class_id=classroom.id,
                                            student_code=code, active=True))
                added += 1
            elif not row.active:
                row.active = True
                reactivated += 1
            else:
                unchanged += 1
        session.flush()
        audit(session, actor, "roster.imported", classroom.id, school_id=actor.school_id,
              details={"added": added, "reactivated": reactivated, "unchanged": unchanged})
        return {"class_id": classroom.id, "added": added, "reactivated": reactivated,
                "unchanged": unchanged, "total": len(codes)}


# ------------------------------------------------------------------ gỡ thành viên ở engine (audit 17/11/2026)
def _still_teaches(session, school_id, course_id, username) -> bool:
    """Còn dạy học phần này ở một lớp khác (cùng course_id) thì engine vẫn giữ quyền."""
    return session.scalar(select(TeachingAssignment.id).join(
        Classroom, (TeachingAssignment.class_id == Classroom.id) & (TeachingAssignment.school_id == Classroom.school_id),
    ).where(TeachingAssignment.school_id == school_id, Classroom.course_id == course_id,
            TeachingAssignment.teacher_username == username, TeachingAssignment.active.is_(True)).limit(1)) is not None


def _still_enrolled(session, school_id, course_id, student_code) -> bool:
    return session.scalar(select(ClassEnrollment.id).join(
        Classroom, (ClassEnrollment.class_id == Classroom.id) & (ClassEnrollment.school_id == Classroom.school_id),
    ).where(ClassEnrollment.school_id == school_id, Classroom.course_id == course_id,
            ClassEnrollment.student_code == student_code, ClassEnrollment.active.is_(True)).limit(1)) is not None


def _student_usernames(student_code) -> list[str]:
    try:
        from dss.services.auth_service import _load_users
        code = (student_code or "").strip().upper()
        return [u for u, r in _load_users().items() if (r.get("student_id") or "").upper() == code]
    except Exception:  # noqa: BLE001 - kho tài khoản lỗi không được chặn việc thu hồi cục bộ
        return []


def _engine_deactivate(actor, course_id, principal_id, role, student_id=None):
    """Gửi active=False sang engine sau khi đã ghi CSDL (ngoài phiên ghi). Không bao giờ làm hỏng thao tác thu hồi."""
    try:
        from dss.services import engine_gateway
        engine_gateway.deactivate_member(actor, course_id, principal_id, role, student_id)
    except Exception:  # noqa: BLE001
        pass
