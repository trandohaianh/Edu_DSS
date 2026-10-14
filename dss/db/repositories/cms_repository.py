"""Repository for the internal CMS domain (Phase 1B, migration order item 10):
cms_lessons, cms_lesson_versions, cms_quizzes, cms_student_interactions.

Real existing runtime: `dss/services/cms_lecture_repository.py` (lessons) and
`dss/services/learning_explainer.py` (quiz queue + interaction log) — both
JSON-backed. This module provides a real, tested Postgres repository plus
`import_from_local()`, a genuine ETL path from the existing JSON stores.

Scope decision (documented, not an oversight — see PHASE1B_RUNTIME_CUTOVER.md):
this pass does NOT wire `cms_lecture_repository.py`/`learning_explainer.py`'s
own functions to read/write Postgres live (that touches many call sites across
a large, actively-used service and risks the kind of large behavioral change
this engagement's rules require extra caution for). Status is
REPOSITORY_READY: real schema, real repository, real tested import utility,
real RLS — not yet the PRIMARY runtime backend for live CMS reads/writes.
"""
from __future__ import annotations

from typing import Any, Optional

from dss.db.models import CmsLesson, CmsLessonVersion, CmsQuiz, CmsStudentInteraction
from dss.db.session import tenant_session_scope


def upsert_lesson(organization_id: int, lesson: dict[str, Any]) -> int:
    """`lesson` is the exact dict shape `CMSLesson.to_dict()` produces (see
    cms_lecture_repository.py) — idempotent by (organization_id, lesson_id)."""
    with tenant_session_scope(organization_id) as session:
        existing = (
            session.query(CmsLesson)
            .filter_by(organization_id=organization_id, lesson_id=lesson["lesson_id"])
            .one_or_none()
        )
        fields = dict(
            course_id=lesson["course_id"], topic_id=lesson.get("topic_id"),
            lecturer_id=lesson.get("lecturer_id"), title=lesson["title"],
            learning_outcome=lesson.get("learning_outcome"), difficulty=lesson.get("difficulty", "Standard"),
            ai_enabled=lesson.get("ai_enabled", True), official_source=lesson.get("official_source", True),
            current_document_id=lesson.get("current_document_id"),
            supplementary_allowed=lesson.get("supplementary_allowed", False),
            socratic_allowed=lesson.get("socratic_allowed", True),
            quiz_allowed=lesson.get("quiz_allowed", True),
            quiz_requires_approval=lesson.get("quiz_requires_approval", True),
            excluded_document_ids=lesson.get("excluded_document_ids", []),
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            lesson_row_id = existing.id
        else:
            row = CmsLesson(organization_id=organization_id, lesson_id=lesson["lesson_id"], **fields)
            session.add(row)
            session.flush()
            lesson_row_id = row.id

        # Versions: replace-all-on-import (versions are an ordered list in the
        # source JSON, not independently addressable — safe to resync fully).
        session.query(CmsLessonVersion).filter_by(lesson_id=lesson_row_id).delete()
        for v in lesson.get("versions", []):
            session.add(CmsLessonVersion(
                lesson_id=lesson_row_id, document_id=v["document_id"], version=v["version"],
                uploaded_by=v["uploaded_by"], source_file=v.get("source_file"),
            ))
        return lesson_row_id


def list_lessons(organization_id: int, course_id: Optional[str] = None) -> list[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        q = session.query(CmsLesson).filter_by(organization_id=organization_id)
        if course_id:
            q = q.filter_by(course_id=course_id)
        return [_lesson_dict(r) for r in q.all()]


def _lesson_dict(r: CmsLesson) -> dict[str, Any]:
    return {
        "lesson_id":r.lesson_id,"course_id":r.course_id,"topic_id":r.topic_id,"lecturer_id":r.lecturer_id,
        "title":r.title,"learning_outcome":r.learning_outcome or "","difficulty":r.difficulty,
        "ai_enabled":r.ai_enabled,"official_source":r.official_source,"current_document_id":r.current_document_id,
        "supplementary_allowed":r.supplementary_allowed,"socratic_allowed":r.socratic_allowed,
        "quiz_allowed":r.quiz_allowed,"quiz_requires_approval":r.quiz_requires_approval,
        "excluded_document_ids":list(r.excluded_document_ids or []),"faq":[],"explanation_notes":[],"preferred_terminology":{},
        "versions":[{"document_id":v.document_id,"version":v.version,"uploaded_at":v.uploaded_at.isoformat(),"uploaded_by":v.uploaded_by,"source_file":v.source_file} for v in r.versions],
    }


def get_lesson(organization_id: int, lesson_id: str) -> Optional[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        row=session.query(CmsLesson).filter_by(organization_id=organization_id,lesson_id=lesson_id).one_or_none()
        return _lesson_dict(row) if row else None


def upsert_quiz(organization_id: int, lesson_row_id: int, queue_id: str, quiz: dict[str, Any]) -> int:
    """`quiz` matches learning_explainer.py's quiz_review_queue.json record shape."""
    with tenant_session_scope(organization_id) as session:
        existing = session.query(CmsQuiz).filter_by(organization_id=organization_id, queue_id=queue_id).one_or_none()
        if existing:
            existing.status = quiz.get("status", existing.status)
            existing.questions = quiz.get("blueprint", {}).get("questions", existing.questions)
            return existing.id
        row = CmsQuiz(
            organization_id=organization_id, lesson_id=lesson_row_id, queue_id=queue_id,
            course_id=quiz.get("course_id"), questions=quiz.get("blueprint", {}).get("questions", []),
            status=quiz.get("status", "PENDING_LECTURER_APPROVAL"),
            reviewer_id=quiz.get("reviewer_id"), comment=quiz.get("comment"),
        )
        session.add(row)
        session.flush()
        return row.id


def record_interaction(organization_id: int, interaction: dict[str, Any]) -> int:
    """`interaction` matches interaction_log.json's record shape exactly."""
    with tenant_session_scope(organization_id) as session:
        row = CmsStudentInteraction(
            organization_id=organization_id,
            student_pseudonym=interaction["student_pseudonym"],
            course_id=interaction["course_id"], lesson_id=interaction.get("lesson_id"),
            topic_id=interaction.get("topic_id"), question=interaction.get("question"),
            explanation_level=interaction.get("explanation_level"),
            has_cms_content=interaction.get("has_cms_content"),
            misconception_label=interaction.get("misconception_label"),
            quiz_correct=interaction.get("quiz_correct"),
        )
        session.add(row)
        session.flush()
        return row.id


def count_interactions(organization_id: int) -> int:
    with tenant_session_scope(organization_id) as session:
        return session.query(CmsStudentInteraction).filter_by(organization_id=organization_id).count()


def import_from_local(organization_id: int) -> dict[str, int]:
    """Real ETL from the CURRENTLY active local JSON stores
    (cms_lecture_repository.list_lessons(), the raw quiz-queue file, the raw
    interaction-log file — read directly, not re-implemented, so there is
    exactly one source of truth for what these records look like) into
    Postgres. Idempotent for lessons/versions (upsert); interactions are
    append-only facts, like academic_records — importing twice would create
    duplicate interaction rows, matching the real system's own event-log
    semantics (each real student interaction is one point-in-time event)."""
    from dss.services import cms_lecture_repository, learning_explainer

    lessons = cms_lecture_repository.list_lessons()
    lesson_row_ids: dict[str, int] = {}
    for lesson in lessons:
        row_id = upsert_lesson(organization_id, lesson.to_dict())
        lesson_row_ids[lesson.lesson_id] = row_id

    quizzes_imported = 0
    for quiz in learning_explainer._load_quiz_queue():
        lesson_row_id = lesson_row_ids.get(quiz.get("lesson_id"))
        if lesson_row_id is None:
            continue  # orphaned quiz referencing a lesson not in this import batch — skip, don't guess
        upsert_quiz(organization_id, lesson_row_id, quiz["queue_id"], quiz)
        quizzes_imported += 1

    interactions_imported = 0
    for interaction in learning_explainer._load_interaction_log():
        record_interaction(organization_id, interaction)
        interactions_imported += 1

    return {
        "lessons_imported": len(lessons),
        "quizzes_imported": quizzes_imported,
        "interactions_imported": interactions_imported,
    }
