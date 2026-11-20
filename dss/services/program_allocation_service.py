"""Programme reservations and school-approved aggregate snapshots.

AI budgets reserve capacity; provider usage accounting is separate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import and_, func

from dss.platform.context import Actor
from dss.platform.models import (
    Attempt,
    ClassEnrollment,
    ClassPlan,
    Classroom,
    Intervention,
    Program,
    ProgramMember,
    School,
    SchoolAllocation,
    SchoolSummarySnapshot,
)
from dss.platform.store import audit, platform_session

METRIC_VERSION = "school_activity_v1"
MIN_COHORT = 5
LEARNER_METRICS = (
    "enrolled_students",
    "assessed_students",
    "students_with_plans",
    "attempt_count",
    "open_interventions",
    "completed_interventions",
)
METRIC_KEYS = ("active_classes",) + LEARNER_METRICS
MAX_INTEGER = 2**31 - 1


def _text(value, label, limit=128):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"Invalid {label}")
    return value.strip()


def _school(value):
    value = _text(value, "school ID", 64)
    if value == "demo":
        return value
    if not value.isdecimal() or int(value) < 1:
        raise ValueError("School ID must be a positive integer")
    return str(int(value))


def _number(value, label):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _operator(actor):
    if actor.role != "Platform Admin":
        raise PermissionError("Technical platform administrator required")


def _school_admin(actor):
    if actor.role != "Admin":
        raise PermissionError("School administrator required")


def _member(session, actor, program_id, manager=False):
    member = (
        session.query(ProgramMember)
        .filter_by(program_id=program_id, principal_school_id=actor.school_id, username=actor.username)
        .one_or_none()
    )
    if member is None or (manager and member.program_role != "manager"):
        raise PermissionError("Explicit programme membership required")
    return member


def _program(session, program_id):
    program = session.get(Program, program_id)
    if program is None:
        raise ValueError("Programme not found")
    return program


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value):
    return _utc(value).isoformat() if value is not None else None


def _program_dto(program, role=None):
    return dict(
        id=program.id,
        code=program.code,
        name=program.name,
        status=program.status,
        seat_budget=program.seat_budget,
        ai_budget=program.ai_budget,
        program_role=role,
        created_at=_iso(program.created_at),
    )


def _allocation_dto(row, school=None):
    return dict(
        id=row.id,
        program_id=row.program_id,
        school_id=row.school_id,
        school_name=school.name if school else row.school_id,
        status=row.status,
        allocation_status=row.status,
        seats=row.seats,
        ai_budget=row.ai_budget,
        created_at=_iso(row.created_at),
    )


def register_school(actor: Actor, school_id: str, name: str) -> dict:
    _operator(actor)
    school_id, name = _school(school_id), _text(name, "school name", 255)
    with platform_session(write=True, actor=actor) as session:
        school = session.get(School, school_id)
        if school is None:
            school = School(id=school_id, name=name, active=True)
            session.add(school)
        else:
            school.name = name
        session.flush()
        audit(session, actor, "school.register", school_id, school_id=school_id, details={"name": name})
        return dict(id=school.id, name=school.name, active=school.active)


def set_school_status(actor: Actor, school_id: str, active: bool) -> dict:
    _operator(actor)
    school_id = _school(school_id)
    if type(active) is not bool:
        raise ValueError("active must be boolean")
    with platform_session(school_id=school_id, write=True, actor=actor) as session:
        school = session.get(School, school_id)
        if school is None:
            raise ValueError("School not found")
        school.active = active
        audit(session, actor, "school.status", school_id, school_id=school_id, details={"active": active})
        return dict(id=school.id, name=school.name, active=school.active)


def create_program(actor: Actor, code: str, name: str, seat_budget: int, ai_budget: int = 0) -> dict:
    _operator(actor)
    code, name = _text(code, "programme code"), _text(name, "programme name", 255)
    seat_budget, ai_budget = _number(seat_budget, "seat budget"), _number(ai_budget, "AI budget")
    with platform_session(write=True, actor=actor) as session:
        program = session.query(Program).filter_by(code=code).one_or_none()
        if program is not None:
            if (program.name, program.seat_budget, program.ai_budget) != (name, seat_budget, ai_budget):
                raise ValueError("Programme code already exists with different settings")
            return _program_dto(program)
        program = Program(code=code, name=name, seat_budget=seat_budget, ai_budget=ai_budget)
        session.add(program)
        session.flush()
        audit(
            session,
            actor,
            "program.create",
            program.id,
            program_id=program.id,
            details={"code": code, "seat_budget": seat_budget, "ai_budget": ai_budget},
        )
        return _program_dto(program)


def grant_program_member(
    actor: Actor, program_id: str, principal_school_id: str, username: str, program_role: str
) -> dict:
    _operator(actor)
    program_id = _text(program_id, "programme ID", 36)
    principal_school_id, username = _school(principal_school_id), _text(username, "username")
    if program_role not in ("manager", "analyst"):
        raise ValueError("Programme role must be manager or analyst")
    with platform_session(program_id=program_id, write=True, actor=actor) as session:
        _program(session, program_id)
        member = (
            session.query(ProgramMember)
            .filter_by(program_id=program_id, principal_school_id=principal_school_id, username=username)
            .one_or_none()
        )
        if member is None:
            member = ProgramMember(
                program_id=program_id,
                principal_school_id=principal_school_id,
                username=username,
                program_role=program_role,
            )
            session.add(member)
        else:
            member.program_role = program_role
        session.flush()
        audit(
            session,
            actor,
            "program.member.grant",
            member.id,
            program_id=program_id,
            details={"principal_school_id": principal_school_id, "username": username, "program_role": program_role},
        )
        return dict(
            id=member.id,
            program_id=program_id,
            principal_school_id=principal_school_id,
            username=username,
            program_role=program_role,
        )


def revoke_program_member(actor: Actor, program_id: str, principal_school_id: str, username: str):
    _operator(actor)
    program_id = _text(program_id, "programme ID", 36)
    principal_school_id, username = _school(principal_school_id), _text(username, "username")
    with platform_session(program_id=program_id, write=True, actor=actor) as session:
        _program(session, program_id)
        member = (
            session.query(ProgramMember)
            .filter_by(program_id=program_id, principal_school_id=principal_school_id, username=username)
            .one_or_none()
        )
        if member is not None:
            member_id = member.id
            session.delete(member)
            audit(
                session,
                actor,
                "program.member.revoke",
                member_id,
                program_id=program_id,
                details={"principal_school_id": principal_school_id, "username": username},
            )


def list_programs(actor: Actor) -> list[dict]:
    with platform_session(actor=actor) as session:
        memberships = (
            session.query(ProgramMember).filter_by(principal_school_id=actor.school_id, username=actor.username).all()
        )
        roles = {member.program_id: member.program_role for member in memberships}
        query = session.query(Program)
        if actor.role != "Platform Admin":
            if not roles:
                return []
            query = query.filter(Program.id.in_(roles))
        return [_program_dto(row, roles.get(row.id)) for row in query.order_by(Program.code).all()]


def list_school_directory(actor: Actor, program_id: str | None = None) -> list[dict]:
    with platform_session(program_id=program_id, actor=actor) as session:
        if actor.role != "Platform Admin":
            if program_id is None:
                raise PermissionError("Programme manager required")
            _member(session, actor, program_id, manager=True)
        return [
            dict(id=row.id, name=row.name, active=row.active) for row in session.query(School).order_by(School.id).all()
        ]


def set_program_status(actor: Actor, program_id: str, status: str) -> dict:
    if status not in ("active", "paused", "closed"):
        raise ValueError("Invalid programme status")
    with platform_session(program_id=program_id, write=True, actor=actor) as session:
        _member(session, actor, program_id, manager=True)
        program = _program(session, program_id)
        program.status = status
        audit(session, actor, "program.status", program_id, program_id=program_id, details={"status": status})
        return _program_dto(program)


def set_program_budget(actor: Actor, program_id: str, seat_budget: int, ai_budget: int) -> dict:
    _operator(actor)
    seat_budget, ai_budget = _number(seat_budget, "seat budget"), _number(ai_budget, "AI budget")
    with platform_session(program_id=program_id, write=True, actor=actor) as session:
        program = _program(session, program_id)
        seats, ai = (
            session.query(
                func.coalesce(func.sum(SchoolAllocation.seats), 0),
                func.coalesce(func.sum(SchoolAllocation.ai_budget), 0),
            )
            .filter(SchoolAllocation.program_id == program_id, SchoolAllocation.status == "active")
            .one()
        )
        if seat_budget < seats or ai_budget < ai:
            raise ValueError("Budget cannot be below active reservations")
        program.seat_budget, program.ai_budget = seat_budget, ai_budget
        audit(
            session,
            actor,
            "program.budget",
            program_id,
            program_id=program_id,
            details={"seat_budget": seat_budget, "ai_budget": ai_budget},
        )
        return _program_dto(program)


def _active_enrollments(session, school_id):
    return (
        session.query(ClassEnrollment)
        .join(
            Classroom, and_(Classroom.id == ClassEnrollment.class_id, Classroom.school_id == ClassEnrollment.school_id)
        )
        .filter(ClassEnrollment.school_id == school_id, ClassEnrollment.active.is_(True), Classroom.status == "active")
    )


def allocate_school(
    actor: Actor, program_id: str, school_id: str, seats: int, ai_budget: int = 0, status: str = "active"
) -> dict:
    program_id, school_id = _text(program_id, "programme ID", 36), _school(school_id)
    seats, ai_budget = _number(seats, "seats"), _number(ai_budget, "AI budget")
    if status not in ("active", "suspended", "revoked"):
        raise ValueError("Invalid allocation status")
    with platform_session(program_id=program_id, actor=actor) as session:
        _member(session, actor, program_id, manager=True)
    with platform_session(school_id=school_id, program_id=program_id, write=True, actor=actor) as session:
        _member(session, actor, program_id, manager=True)
        program = _program(session, program_id)
        school = session.get(School, school_id)
        if school is None:
            raise ValueError("School not found")
        if status == "active" and (program.status != "active" or not school.active):
            raise ValueError("Programme and school must be active")
        row = session.query(SchoolAllocation).filter_by(program_id=program_id, school_id=school_id).one_or_none()
        reserved_seats, reserved_ai = (
            session.query(
                func.coalesce(func.sum(SchoolAllocation.seats), 0),
                func.coalesce(func.sum(SchoolAllocation.ai_budget), 0),
            )
            .filter(
                SchoolAllocation.program_id == program_id,
                SchoolAllocation.status == "active",
                SchoolAllocation.school_id != school_id,
            )
            .one()
        )
        if status == "active" and (
            reserved_seats + seats > program.seat_budget or reserved_ai + ai_budget > program.ai_budget
        ):
            raise ValueError("Programme reservation budget exceeded")
        used = (
            _active_enrollments(session, school_id)
            .with_entities(func.count(func.distinct(ClassEnrollment.student_code)))
            .scalar()
        )
        if seats < used:
            raise ValueError("Allocation cannot be below current active learner usage")
        if row is None:
            row = SchoolAllocation(
                program_id=program_id, school_id=school_id, seats=seats, ai_budget=ai_budget, status=status
            )
            session.add(row)
        else:
            row.seats, row.ai_budget, row.status = seats, ai_budget, status
        session.flush()
        audit(
            session,
            actor,
            "program.allocate",
            row.id,
            school_id=school_id,
            program_id=program_id,
            details={"seats": seats, "ai_budget": ai_budget, "status": status},
        )
        return _allocation_dto(row, school)


def list_allocations(actor: Actor, program_id: str) -> list[dict]:
    with platform_session(program_id=program_id, actor=actor) as session:
        _member(session, actor, program_id, manager=True)
        rows = (
            session.query(SchoolAllocation, School)
            .join(School, School.id == SchoolAllocation.school_id)
            .filter(SchoolAllocation.program_id == program_id)
            .order_by(School.id)
            .all()
        )
        return [_allocation_dto(row, school) for row, school in rows]


def list_school_programs(actor: Actor) -> list[dict]:
    _school_admin(actor)
    with platform_session(school_id=actor.school_id, actor=actor) as session:
        rows = (
            session.query(SchoolAllocation, Program)
            .join(Program, Program.id == SchoolAllocation.program_id)
            .filter(SchoolAllocation.school_id == actor.school_id)
            .order_by(Program.code)
            .all()
        )
        return [
            dict(
                program_id=program.id,
                program_code=program.code,
                program_name=program.name,
                program_status=program.status,
                allocation_status=row.status,
                seats=row.seats,
                ai_budget=row.ai_budget,
            )
            for row, program in rows
        ]


def _school_metrics(session, school_id):
    cohort = (
        _active_enrollments(session, school_id)
        .with_entities(ClassEnrollment.class_id.label("class_id"), ClassEnrollment.student_code.label("student_code"))
        .subquery()
    )

    def source_query(model):
        return (
            session.query(model)
            .join(cohort, and_(model.class_id == cohort.c.class_id, model.student_code == cohort.c.student_code))
            .filter(model.school_id == school_id)
        )

    return dict(
        active_classes=session.query(func.count(Classroom.id))
        .filter(Classroom.school_id == school_id, Classroom.status == "active")
        .scalar(),
        enrolled_students=session.query(func.count(func.distinct(cohort.c.student_code))).scalar(),
        assessed_students=source_query(Attempt).with_entities(func.count(func.distinct(Attempt.student_code))).scalar(),
        students_with_plans=source_query(ClassPlan)
        .with_entities(func.count(func.distinct(ClassPlan.student_code)))
        .scalar(),
        attempt_count=source_query(Attempt).with_entities(func.count(Attempt.id)).scalar(),
        open_interventions=source_query(Intervention)
        .filter(Intervention.status == "open")
        .with_entities(func.count(Intervention.id))
        .scalar(),
        completed_interventions=source_query(Intervention)
        .filter(Intervention.status == "completed")
        .with_entities(func.count(Intervention.id))
        .scalar(),
    )


def _safe_metrics(metrics):
    if not isinstance(metrics, dict):
        metrics = {}
    return {key: value if type(value := metrics.get(key)) is int and value >= 0 else None for key in METRIC_KEYS}


def publish_school_summary(actor: Actor, program_id: str, min_cohort: int = MIN_COHORT) -> dict:
    _school_admin(actor)
    min_cohort = _number(min_cohort, "minimum cohort")
    if min_cohort < MIN_COHORT:
        raise ValueError("Minimum report cohort must be at least five")
    program_id = _text(program_id, "programme ID", 36)
    with platform_session(school_id=actor.school_id, program_id=program_id, write=True, actor=actor) as session:
        allocation = (
            session.query(SchoolAllocation)
            .filter_by(program_id=program_id, school_id=actor.school_id, status="active")
            .one_or_none()
        )
        if allocation is None:
            raise PermissionError("An active school programme allocation is required")
        program = _program(session, program_id)
        school = session.get(School, actor.school_id)
        if school is None or not school.active or program.status != "active" or allocation is None:
            raise PermissionError("An active school programme allocation is required")
        metrics = _school_metrics(session, actor.school_id)
        small_cohort = metrics["enrolled_students"] < min_cohort
        suppressed_keys = []
        for key in LEARNER_METRICS:
            if small_cohort or metrics[key] < min_cohort:
                metrics[key] = None
                suppressed_keys.append(key)
        now = datetime.now(UTC)
        snapshot = SchoolSummarySnapshot(
            program_id=program_id,
            school_id=actor.school_id,
            as_of=now,
            metric_version=METRIC_VERSION,
            metrics=metrics,
            suppressed=bool(suppressed_keys),
            cohort_threshold=min_cohort,
        )
        session.add(snapshot)
        session.flush()
        audit(
            session,
            actor,
            "program.summary.publish",
            snapshot.id,
            school_id=actor.school_id,
            program_id=program_id,
            details={
                "metric_version": METRIC_VERSION,
                "cohort_threshold": min_cohort,
                "suppressed": snapshot.suppressed,
            },
        )
        return dict(
            id=snapshot.id,
            school_id=actor.school_id,
            program_id=program_id,
            as_of=_iso(now),
            metric_version=METRIC_VERSION,
            metrics=metrics,
            suppressed=snapshot.suppressed,
            cohort_threshold=min_cohort,
            suppressed_metrics=suppressed_keys,
        )


def list_program_reports(actor: Actor, program_id: str, max_age_hours: int = 24) -> list[dict]:
    if type(max_age_hours) is not int or not 1 <= max_age_hours <= 8760:
        raise ValueError("Report freshness must be between 1 and 8760 hours")
    with platform_session(program_id=program_id, actor=actor) as session:
        _member(session, actor, program_id)
        rows = (
            session.query(SchoolAllocation, School)
            .join(School, School.id == SchoolAllocation.school_id)
            .filter(SchoolAllocation.program_id == program_id)
            .order_by(School.id)
            .all()
        )
        snapshots = (
            session.query(SchoolSummarySnapshot)
            .filter_by(program_id=program_id)
            .order_by(
                SchoolSummarySnapshot.as_of.desc(),
                SchoolSummarySnapshot.created_at.desc(),
                SchoolSummarySnapshot.id.desc(),
            )
            .all()
        )
        latest = {}
        for snapshot in snapshots:
            latest.setdefault(snapshot.school_id, snapshot)
        now = datetime.now(UTC)
        reports = []
        for allocation, school in rows:
            snapshot = latest.get(school.id)
            report = dict(
                school_id=school.id,
                school_name=school.name,
                allocation_status=allocation.status,
                report_status="not_reported",
                as_of=None,
                metric_version=None,
                metrics=None,
                cohort_threshold=None,
                suppressed=None,
                suppressed_metrics=[],
            )
            if snapshot is not None:
                metrics = _safe_metrics(snapshot.metrics)
                supported = snapshot.metric_version == METRIC_VERSION and snapshot.cohort_threshold >= MIN_COHORT
                if not supported:
                    metrics = dict.fromkeys(METRIC_KEYS)
                cohort = metrics.get("enrolled_students")
                for key in LEARNER_METRICS:
                    value = metrics.get(key)
                    if (
                        cohort is None
                        or cohort < snapshot.cohort_threshold
                        or value is None
                        or value < snapshot.cohort_threshold
                    ):
                        metrics[key] = None
                suppressed = (
                    bool(snapshot.suppressed) or not supported or any(metrics[key] is None for key in LEARNER_METRICS)
                )
                stale = (
                    not supported
                    or now - _utc(snapshot.as_of) > timedelta(hours=max_age_hours)
                    or _utc(snapshot.as_of) > now + timedelta(minutes=5)
                )
                report.update(
                    as_of=_iso(snapshot.as_of),
                    metric_version=snapshot.metric_version,
                    metrics=metrics,
                    cohort_threshold=snapshot.cohort_threshold,
                    suppressed=suppressed,
                    suppressed_metrics=[key for key in LEARNER_METRICS if metrics[key] is None],
                    report_status="stale" if stale else "suppressed" if suppressed else "current",
                )
            reports.append(report)
        return reports
