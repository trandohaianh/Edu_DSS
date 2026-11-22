"""Repository for the academic domain cluster: students, lecturers, courses,
enrollments, academic_records (Phase 1B, migration order items 1-5).

AUDIT FINDING (documented honestly, not glossed over — see PHASE1B_RUNTIME_CUTOVER.md
for the full writeup): none of these 5 entities have a distinct existing runtime
service in the live app today. `dss/core/data_helpers.py::generate_data()`/
`generate_lms_data()` produce a single flat pandas DataFrame (one row per student,
columns like `diem_ky_nay`/`ty_le_diem_danh`) consumed directly and in bulk by the
ML pipeline (`dss/core/trainers.py`, `dss/tabs/eda.py`, `dss/tabs/ml_hub.py`) — there
is no per-student CRUD, no separate Lecturer/Course/Enrollment concept, and no
per-record persistence outside that one dataset file. This means there is no
existing single-record runtime call site to "wire" the way there is for
predictions/consultations/subscriptions — wiring the ML pipeline itself to read
individual rows from Postgres instead of a DataFrame would require redesigning
`dss/tabs/eda.py`/`dss/core/trainers.py`'s entire data-access pattern, which the
Phase 1B instructions explicitly flag as a caution zone (known future
security-hardening integration points) and which this pass does not attempt.

What this module DOES provide, real and tested: a genuine Postgres repository for
all 5 entities (usable by future features), and `import_dataframe()` — a real,
idempotent ETL path that takes the CURRENT in-memory dataset (whatever
`generate_data()`/`generate_lms_data()`/an uploaded CSV produced) and persists it
as real, tenant-scoped, RLS-protected relational rows. This is new capability,
not a cutover of an existing read path.
"""

from __future__ import annotations

from typing import Any, Optional

from dss.db.models import AcademicRecord, Course, Enrollment, Lecturer, Student
from dss.db.session import tenant_session_scope

# Score-like columns in generate_data()/generate_lms_data()'s DataFrame that map
# to one academic_records row each, keyed by their real column name (used as
# record_type so the source column is always traceable from the DB row).
_SCORE_COLUMNS = [
    "diem_giua_ky",
    "diem_ky_nay",
    "diem_du_an",
    "diem_ky_sau",
    "ty_le_diem_danh",
]


def upsert_student(organization_id: int, student_code: str, full_name: Optional[str] = None) -> int:
    """Idempotent by (organization_id, student_code) — matches the real unique
    constraint in the schema. Returns the row id."""
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(Student).filter_by(organization_id=organization_id, student_code=student_code).one_or_none()
        )
        if existing:
            if full_name and existing.full_name != full_name:
                existing.full_name = full_name
            return existing.id
        student = Student(
            organization_id=organization_id,
            student_code=student_code,
            full_name=full_name or student_code,
        )
        session.add(student)
        session.flush()
        return student.id


def resolve_or_create_student_id(session, organization_id: int, student_code: Optional[str]) -> Optional[int]:
    """Bước 9 (22/11/2026): id sinh viên cho dự đoán/phiên tư vấn, TẠO dòng tối thiểu (tên = mã) khi sinh viên
    chưa có trong `students` (ví dụ dữ liệu tải bằng tệp, chưa đồng bộ LMS). Trước đây trả None nên bản ghi mất mã SV
    và yêu cầu xoá dữ liệu của sinh viên đó không tìm thấy nó. Chạy trong session của nơi gọi; SAVEPOINT để hai yêu
    cầu cùng lúc cho cùng một mã không làm hỏng giao dịch chung (ràng buộc duy nhất organization_id + student_code)."""
    from sqlalchemy.exc import IntegrityError

    code = (student_code or "").strip()
    if not code or code.lower() == "unknown" or len(code) > 32:
        return None
    for _ in range(3):
        row = session.query(Student).filter_by(organization_id=organization_id, student_code=code).one_or_none()
        if row is not None:
            return row.id
        savepoint = session.begin_nested()
        try:
            row = Student(organization_id=organization_id, student_code=code, full_name=code)
            session.add(row)
            session.flush()
            savepoint.commit()
            return row.id
        except IntegrityError:
            savepoint.rollback()
    raise RuntimeError("could not resolve student row")


def upsert_lecturer(organization_id: int, lecturer_code: str, full_name: Optional[str] = None) -> int:
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(Lecturer)
            .filter_by(organization_id=organization_id, lecturer_code=lecturer_code)
            .one_or_none()
        )
        if existing:
            return existing.id
        lecturer = Lecturer(
            organization_id=organization_id,
            lecturer_code=lecturer_code,
            full_name=full_name or lecturer_code,
        )
        session.add(lecturer)
        session.flush()
        return lecturer.id


def upsert_course(
    organization_id: int,
    course_code: str,
    title: str,
    semester: Optional[str] = None,
    lecturer_id: Optional[int] = None,
) -> int:
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(Course)
            .filter_by(organization_id=organization_id, course_code=course_code, semester=semester)
            .one_or_none()
        )
        if existing:
            return existing.id
        course = Course(
            organization_id=organization_id,
            course_code=course_code,
            title=title,
            semester=semester,
            lecturer_id=lecturer_id,
        )
        session.add(course)
        session.flush()
        return course.id


def upsert_enrollment(organization_id: int, student_id: int, course_id: int) -> int:
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(Enrollment)
            .filter_by(organization_id=organization_id, student_id=student_id, course_id=course_id)
            .one_or_none()
        )
        if existing:
            return existing.id
        enrollment = Enrollment(organization_id=organization_id, student_id=student_id, course_id=course_id)
        session.add(enrollment)
        session.flush()
        return enrollment.id


def record_academic_record(
    organization_id: int,
    student_id: int,
    course_id: Optional[int],
    record_type: str,
    value: Optional[float],
    source: str = "import",
) -> int:
    """NOT idempotent by design — an academic_records row is a point-in-time
    fact (matches the LMS sync model: each sync appends new rows, it does not
    overwrite history). Callers that need idempotent re-import should dedupe
    at the DataFrame level (see import_dataframe's `replace_existing`)."""
    with tenant_session_scope(organization_id) as session:
        record = AcademicRecord(
            organization_id=organization_id,
            student_id=student_id,
            course_id=course_id,
            record_type=record_type,
            value=value,
            source=source,
        )
        session.add(record)
        session.flush()
        return record.id


def list_students(organization_id: int, limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        rows = (
            session.query(Student)
            .filter_by(organization_id=organization_id)
            .order_by(Student.student_code)
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [{"id": r.id, "student_code": r.student_code, "full_name": r.full_name} for r in rows]


def count_students(organization_id: int) -> int:
    with tenant_session_scope(organization_id) as session:
        return session.query(Student).filter_by(organization_id=organization_id).count()


def import_dataframe(
    organization_id: int,
    df,
    course_code: str,
    course_title: str,
    term: Optional[str] = None,
    student_id_column: str = "student_id",
    replace_existing: bool = False,
) -> dict[str, int]:
    """Real, idempotent (for students/enrollments — see docstring on
    record_academic_record for why academic_records rows themselves are
    append-only) ETL from an in-memory DataFrame (the exact shape
    `generate_data()`/`generate_lms_data()`/an uploaded CSV already produces)
    into Postgres. Tenant-scoped and RLS-protected throughout — every write
    goes through `tenant_session_scope(organization_id)`.

    `replace_existing=True` deletes this organization's prior academic_records
    for this course before re-importing (used by the idempotent-reimport test —
    without it, re-running an import against the same DataFrame would append a
    second full set of academic_records rows, which is correct for "a new sync
    happened" but wrong for "I ran the same import twice by accident").
    """
    if student_id_column not in df.columns:
        raise ValueError(f"DataFrame has no '{student_id_column}' column — cannot import")

    course_id = upsert_course(organization_id, course_code, course_title, semester=term)

    if replace_existing:
        with tenant_session_scope(organization_id) as session:
            session.query(AcademicRecord).filter_by(organization_id=organization_id, course_id=course_id).delete()

    students_imported = 0
    enrollments_imported = 0
    records_imported = 0
    available_score_cols = [c for c in _SCORE_COLUMNS if c in df.columns]

    for _, row in df.iterrows():
        raw_student_code = row[student_id_column]
        if raw_student_code is None or (isinstance(raw_student_code, float) and raw_student_code != raw_student_code):
            continue  # skip NaN/invalid rows rather than importing a garbage record
        student_code = str(raw_student_code)
        student_id = upsert_student(organization_id, student_code)
        students_imported += 1
        upsert_enrollment(organization_id, student_id, course_id)
        enrollments_imported += 1
        for col in available_score_cols:
            value = row[col]
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            record_academic_record(
                organization_id, student_id, course_id, record_type=col, value=value, source="import"
            )
            records_imported += 1

    return {
        "course_id": course_id,
        "students_imported": students_imported,
        "enrollments_imported": enrollments_imported,
        "academic_records_imported": records_imported,
    }
