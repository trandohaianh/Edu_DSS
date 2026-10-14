"""Repository for the `recommendations` domain (Phase 1B, migration order
item 7).

AUDIT FINDING (documented, not glossed over): `dss/services/career_ai_advisor.py`
generates career-advisory answers entirely live, per chat turn
(`dss/tabs/advisory.py` builds a prompt, calls the LLM or the offline
grounded fallback, and appends the answer only to `st.session_state` — there
is no `save`/persistence function anywhere in that module or its callers).
It is a conversational Q&A stream, not a discrete "recommendation" record —
there is no existing single-record write call site to wire without changing
`advisory.py`'s live interactive chat loop, which this pass does not attempt
(same caution this engagement applied to the academic domains' ML pipeline).

Status: REPOSITORY_READY — real schema (`Recommendation`, Phase 1), real
tested repository, but not wired into the live advisory chat loop this pass.
`student_id` is a hard FK (see dss/db/models.py), so `save_recommendation`
resolves/creates the student row via academic_repository.upsert_student —
the same student-identity resolution already used by the academic domains.
"""
from __future__ import annotations

from typing import Any, Optional

from dss.db.models import Recommendation
from dss.db.repositories.academic_repository import upsert_student
from dss.db.session import tenant_session_scope


def save_recommendation(
    organization_id: int, student_code: str, recommendation_type: str, content: str,
    generated_by: Optional[str] = None,
) -> int:
    """Not idempotent by design — a recommendation is a point-in-time
    generated artifact (matches academic_records' append-only semantics);
    re-generating the same advice for the same student is a new event, not
    an update of a previous one."""
    student_id = upsert_student(organization_id, student_code)
    with tenant_session_scope(organization_id) as session:
        row = Recommendation(
            organization_id=organization_id, student_id=student_id,
            recommendation_type=recommendation_type, content=content, generated_by=generated_by,
        )
        session.add(row)
        session.flush()
        return row.id


def list_recommendations(
    organization_id: int, student_code: Optional[str] = None, limit: int = 100, offset: int = 0,
) -> list[dict[str, Any]]:
    from dss.db.models import Student

    with tenant_session_scope(organization_id) as session:
        q = (
            session.query(Recommendation, Student.student_code)
            .join(Student, Student.id == Recommendation.student_id)
            .filter(Recommendation.organization_id == organization_id)
        )
        if student_code:
            q = q.filter(Student.student_code == student_code)
        rows = q.order_by(Recommendation.created_at.desc()).limit(limit).offset(offset).all()
        return [
            {
                "id": r.id, "student_code": code, "recommendation_type": r.recommendation_type,
                "content": r.content, "generated_by": r.generated_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, code in rows
        ]
