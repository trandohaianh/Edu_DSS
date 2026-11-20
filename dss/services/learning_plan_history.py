"""Durable, school-scoped structured plans for the first university pilot.

Dedicated deployments resolve the school on the server. Local SQLite is for
development; production requires the explicit PostgreSQL selector and never
falls back after a database failure. This is not shared-runtime tenancy.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from dss.core.data_root import get_data_root
from dss.core.persistence_config import is_postgres_enabled
from dss.core.runtime_mode import is_production
from dss.services import auth_service
from dss.services.privacy_service import generate_pseudonym

_RECORD_TYPE = "learning_plan.v1"


def _scope(student_id: str) -> tuple[str, str]:
    user = auth_service.current_user()
    if not user:
        raise PermissionError("Authentication is required.")
    if user.get("role") == "Sinh viên":
        if not user.get("student_id") or str(user["student_id"]) != str(student_id):
            raise PermissionError("Only your own learning plans are available.")
    elif user.get("role") != "Admin":
        raise PermissionError("Learning plan history requires student or school administrator access.")
    school = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not school:
        if is_production():
            raise RuntimeError("EDUDSS_ORGANIZATION_ID is required for learning plan history.")
        school = "demo"
    elif not school.isdecimal() or int(school) <= 0:
        raise RuntimeError("EDUDSS_ORGANIZATION_ID must be a positive integer.")
    if is_production() and not is_postgres_enabled("LEARNING_PLANS"):
        raise RuntimeError("Production learning plan history requires EDUDSS_LEARNING_PLANS_STORE=postgres.")
    # The display pseudonym normalizes case. Storage must still distinguish
    # exact student codes, just like PostgreSQL's student_code uniqueness.
    exact_code = hashlib.sha256(str(student_id).encode("utf-8")).hexdigest()
    return school, generate_pseudonym(str(student_id)) + ":" + exact_code


def _encode(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _decode(content: str) -> dict:
    payload = json.loads(content)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("plan"), dict):
        raise ValueError("Unsupported learning plan history record.")
    return payload


@contextmanager
def _local_connection():
    path = get_data_root() / "learning_plans.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS pilot_learning_plans (
            school_key TEXT NOT NULL, student_key TEXT NOT NULL,
            course_id TEXT NOT NULL, plan_id TEXT NOT NULL,
            version INTEGER NOT NULL, created_at TEXT NOT NULL,
            content TEXT NOT NULL,
            PRIMARY KEY (school_key, student_key, plan_id),
            UNIQUE (school_key, student_key, course_id, version)
        )""")
        yield connection
    finally:
        connection.close()


@contextmanager
def _postgres_records(school: str, student_id: str, *, write: bool = False, create_owner: bool = False):
    from sqlalchemy import text
    from dss.db.models import Recommendation, Student
    from sqlalchemy.dialects.postgresql import insert
    from dss.db.session import tenant_session_scope

    organization_id = int(school)
    resolved_student_id = None
    with tenant_session_scope(organization_id) as session:
        if write:
            # Serialize all plan writes for this owner, including progress/retries.
            key = int.from_bytes(hashlib.blake2b(
                f"{school}:{student_id}:learning_plans".encode(), digest_size=8,
            ).digest(), "big", signed=True)
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            if create_owner:
                session.execute(insert(Student).values(
                    organization_id=organization_id, student_code=student_id, full_name=student_id,
                ).on_conflict_do_nothing(index_elements=["organization_id", "student_code"]))
                resolved_student_id = session.query(Student.id).filter_by(
                    organization_id=organization_id, student_code=student_id,
                ).scalar()
        query = (
            session.query(Recommendation)
            .join(Student, Student.id == Recommendation.student_id)
            .filter(Recommendation.organization_id == organization_id,
                    Student.organization_id == organization_id,
                    Student.student_code == student_id,
                    Recommendation.recommendation_type == _RECORD_TYPE)
            .order_by(Recommendation.id.desc())
        )
        yield session, query.all(), resolved_student_id


def _same_plan(saved: dict, candidate: dict) -> bool:
    # Versions are assigned by the store, never by the caller.
    return ({k: v for k, v in saved.items() if k != "version"}
            == {k: v for k, v in candidate.items() if k != "version"})


def _new_payload(plan, records: list[dict]) -> dict:
    candidate = plan.to_dict()
    for record in records:
        if record["plan"]["plan_id"] == plan.plan_id:
            if not _same_plan(record["plan"], candidate):
                raise ValueError("A saved plan cannot be changed; generate a new version.")
            return record
    next_version = max(
        (int(r["plan"]["version"]) for r in records
         if r["plan"].get("course_id") == plan.course_id), default=0,
    ) + 1
    return {"schema_version": 1, "plan": replace(plan, version=next_version).to_dict(),
            "completion": {}}


def save_learning_plan(student_id: str, plan) -> dict[str, Any]:
    school, owner = _scope(student_id)
    if not plan.course_id or plan.course_id in {"LMS_COURSE", "UNKNOWN"}:
        raise ValueError("A verified course identifier is required before saving a plan.")
    if plan.student_pseudonym != generate_pseudonym(str(student_id)):
        raise PermissionError("The plan belongs to a different student.")
    if is_postgres_enabled("LEARNING_PLANS"):
        from dss.db.models import Recommendation
        with _postgres_records(school, student_id, write=True, create_owner=True) as (session, rows, student_pk):
            records = [_decode(row.content) for row in rows]
            payload = _new_payload(plan, records)
            if not any(r["plan"]["plan_id"] == plan.plan_id for r in records):
                session.add(Recommendation(
                    organization_id=int(school), student_id=student_pk,
                    recommendation_type=_RECORD_TYPE, content=_encode(payload),
                    generated_by="structured-rule-policy-v1",
                ))
            return payload
    with _local_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT content FROM pilot_learning_plans WHERE school_key=? AND student_key=?",
            (school, owner),
        ).fetchall()
        records = [_decode(row["content"]) for row in rows]
        payload = _new_payload(plan, records)
        if not any(r["plan"]["plan_id"] == plan.plan_id for r in records):
            stored = payload["plan"]
            connection.execute(
                "INSERT INTO pilot_learning_plans VALUES (?, ?, ?, ?, ?, ?, ?)",
                (school, owner, stored["course_id"], stored["plan_id"],
                 stored["version"], stored["created_at"], _encode(payload)),
            )
        connection.commit()
        return payload


def list_learning_plans(student_id: str, course_id: str | None = None, limit: int = 20) -> list[dict]:
    school, owner = _scope(student_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    if is_postgres_enabled("LEARNING_PLANS"):
        with _postgres_records(school, student_id) as (_, rows, _):
            records = [_decode(row.content) for row in rows]
        # Apply course filtering before pagination.
        return [r for r in records if course_id is None or r["plan"].get("course_id") == course_id][:limit]
    with _local_connection() as connection:
        query = "SELECT content FROM pilot_learning_plans WHERE school_key=? AND student_key=?"
        args: list = [school, owner]
        if course_id is not None:
            query += " AND course_id=?"
            args.append(course_id)
        query += " ORDER BY rowid DESC LIMIT ?"
        args.append(limit)
        return [_decode(row["content"]) for row in connection.execute(query, args)]


def set_activity_completed(student_id: str, plan_id: str, activity_index: int, completed: bool) -> dict:
    school, owner = _scope(student_id)
    if not isinstance(completed, bool):
        raise ValueError("completed must be a boolean.")

    def update(payload):
        activities = payload["plan"].get("activities", [])
        if (not isinstance(activity_index, int) or isinstance(activity_index, bool)
                or not 0 <= activity_index < len(activities)):
            raise ValueError("Unknown learning activity.")
        payload.setdefault("completion", {})[str(activity_index)] = completed
        return payload

    if is_postgres_enabled("LEARNING_PLANS"):
        with _postgres_records(school, student_id, write=True) as (_, rows, _):
            for row in rows:
                payload = _decode(row.content)
                if payload["plan"]["plan_id"] == plan_id:
                    row.content = _encode(update(payload))
                    return payload
        raise LookupError("Learning plan not found.")
    with _local_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT content FROM pilot_learning_plans WHERE school_key=? AND student_key=? AND plan_id=?",
            (school, owner, plan_id),
        ).fetchone()
        if row is None:
            raise LookupError("Learning plan not found.")
        payload = update(_decode(row["content"]))
        connection.execute(
            "UPDATE pilot_learning_plans SET content=? WHERE school_key=? AND student_key=? AND plan_id=?",
            (_encode(payload), school, owner, plan_id),
        )
        connection.commit()
        return payload
