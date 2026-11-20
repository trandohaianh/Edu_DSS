"""dss/db/repositories/cms_repository.py — real PostgreSQL integration tests
(Phase 1B, migration order item 10). Skipped (not faked) without a database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.repositories import cms_repository as repo
from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — CMS repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"CMS_TEST_{uuid.uuid4().hex[:8]}", name="CMS Test Org")
        session.add(org)
        session.flush()
        return org.id


def _sample_lesson(lesson_id="lesson_x", course_id="CS301"):
    return {
        "lesson_id": lesson_id,
        "course_id": course_id,
        "topic_id": "clustering",
        "lecturer_id": "gv001",
        "title": "K-Means",
        "learning_outcome": "Hieu K-Means",
        "difficulty": "Standard",
        "ai_enabled": True,
        "official_source": True,
        "current_document_id": "doc_1",
        "supplementary_allowed": False,
        "socratic_allowed": True,
        "quiz_allowed": True,
        "quiz_requires_approval": True,
        "excluded_document_ids": [],
        "versions": [
            {
                "document_id": "doc_1",
                "version": 1,
                "uploaded_at": "2026-01-01T00:00:00Z",
                "uploaded_by": "gv001",
                "source_file": "slide.pdf",
            }
        ],
    }


def test_upsert_lesson_is_idempotent(org_id):
    id1 = repo.upsert_lesson(org_id, _sample_lesson())
    id2 = repo.upsert_lesson(org_id, _sample_lesson())
    assert id1 == id2
    assert len(repo.list_lessons(org_id)) == 1


def test_upsert_lesson_updates_fields_on_second_call(org_id):
    repo.upsert_lesson(org_id, _sample_lesson())
    updated = _sample_lesson()
    updated["title"] = "K-Means (updated)"
    repo.upsert_lesson(org_id, updated)
    lessons = repo.list_lessons(org_id)
    assert lessons[0]["title"] == "K-Means (updated)"


def test_lesson_versions_are_synced(org_id):
    from dss.db.models import CmsLessonVersion
    from dss.db.session import session_scope

    lesson_row_id = repo.upsert_lesson(org_id, _sample_lesson())
    with session_scope() as session:
        versions = session.query(CmsLessonVersion).filter_by(lesson_id=lesson_row_id).all()
    assert len(versions) == 1
    assert versions[0].document_id == "doc_1"


def test_upsert_quiz_stores_questions_as_json(org_id):
    lesson_row_id = repo.upsert_lesson(org_id, _sample_lesson())
    quiz = {
        "queue_id": "q1",
        "course_id": "CS301",
        "status": "PENDING_LECTURER_APPROVAL",
        "blueprint": {"questions": [{"question_text": "What is K?", "options": ["A", "B"], "correct_answer_index": 0}]},
    }
    quiz_id = repo.upsert_quiz(org_id, lesson_row_id, "q1", quiz)
    assert quiz_id

    from dss.db.models import CmsQuiz
    from dss.db.session import session_scope

    with session_scope() as session:
        row = session.get(CmsQuiz, quiz_id)
        assert len(row.questions) == 1
        assert row.questions[0]["question_text"] == "What is K?"


def test_record_interaction_and_count(org_id):
    repo.record_interaction(
        org_id,
        {
            "student_pseudonym": "anon_abc",
            "course_id": "CS301",
            "lesson_id": "lesson_x",
            "topic_id": "clustering",
            "question": "What is K-Means?",
            "explanation_level": "Standard",
            "has_cms_content": True,
            "misconception_label": None,
            "quiz_correct": True,
        },
    )
    assert repo.count_interactions(org_id) == 1


def test_interactions_never_store_real_student_identity(org_id):
    """PII safety: only student_pseudonym is stored, never a raw name/email —
    matches privacy_service.py's existing pseudonymization guarantee."""
    from dss.db.models import CmsStudentInteraction

    columns = [c.name for c in CmsStudentInteraction.__table__.columns]
    assert "student_pseudonym" in columns
    assert not any(c in columns for c in ("full_name", "email", "real_name", "student_name"))


def test_import_from_local_empty_stores_is_a_noop(org_id, monkeypatch):
    from dss.services import cms_lecture_repository, learning_explainer

    monkeypatch.setattr(cms_lecture_repository, "list_lessons", list)
    monkeypatch.setattr(learning_explainer, "_load_quiz_queue", list)
    monkeypatch.setattr(learning_explainer, "_load_interaction_log", list)

    result = repo.import_from_local(org_id)
    assert result == {"lessons_imported": 0, "quizzes_imported": 0, "interactions_imported": 0}


def test_import_from_local_is_idempotent_for_lessons(org_id, monkeypatch):
    from dss.services import cms_lecture_repository, learning_explainer

    lesson = cms_lecture_repository.CMSLesson.from_dict(_sample_lesson())
    monkeypatch.setattr(cms_lecture_repository, "list_lessons", lambda: [lesson])
    monkeypatch.setattr(learning_explainer, "_load_quiz_queue", list)
    monkeypatch.setattr(learning_explainer, "_load_interaction_log", list)

    first = repo.import_from_local(org_id)
    second = repo.import_from_local(org_id)
    assert first["lessons_imported"] == second["lessons_imported"] == 1
    assert len(repo.list_lessons(org_id)) == 1  # repeat import does not duplicate


def test_import_from_local_skips_quiz_with_no_matching_lesson(org_id, monkeypatch):
    """Invalid/orphaned record handling: a quiz referencing a lesson_id not
    present in this import batch is skipped, not guessed at or crashed on."""
    from dss.services import cms_lecture_repository, learning_explainer

    monkeypatch.setattr(cms_lecture_repository, "list_lessons", list)
    monkeypatch.setattr(
        learning_explainer,
        "_load_quiz_queue",
        lambda: [
            {
                "queue_id": "q_orphan",
                "lesson_id": "no_such_lesson",
                "course_id": "CS301",
                "status": "PENDING_LECTURER_APPROVAL",
            }
        ],
    )
    monkeypatch.setattr(learning_explainer, "_load_interaction_log", list)

    result = repo.import_from_local(org_id)
    assert result["quizzes_imported"] == 0  # orphaned quiz skipped, not crashed on


def test_import_from_local_interactions_are_append_only_on_repeat(org_id, monkeypatch):
    from dss.services import cms_lecture_repository, learning_explainer

    monkeypatch.setattr(cms_lecture_repository, "list_lessons", list)
    monkeypatch.setattr(learning_explainer, "_load_quiz_queue", list)
    monkeypatch.setattr(
        learning_explainer,
        "_load_interaction_log",
        lambda: [{"student_pseudonym": "anon_1", "course_id": "CS301", "question": "Q1"}],
    )

    repo.import_from_local(org_id)
    repo.import_from_local(org_id)
    assert repo.count_interactions(org_id) == 2  # each event-log run is a new fact, not an update


def test_import_from_local_never_cross_assigns_tenant(org_id, monkeypatch):
    from dss.db.models import Organization
    from dss.db.session import session_scope
    from dss.services import cms_lecture_repository, learning_explainer

    with session_scope() as session:
        other_org = Organization(org_code=f"CMS_IMPORT_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    lesson = cms_lecture_repository.CMSLesson.from_dict(_sample_lesson())
    monkeypatch.setattr(cms_lecture_repository, "list_lessons", lambda: [lesson])
    monkeypatch.setattr(learning_explainer, "_load_quiz_queue", list)
    monkeypatch.setattr(learning_explainer, "_load_interaction_log", list)

    repo.import_from_local(org_id)
    assert len(repo.list_lessons(org_id)) == 1
    assert len(repo.list_lessons(other_org_id)) == 0


def test_cross_tenant_isolation_for_lessons(org_id):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        other_org = Organization(org_code=f"CMS_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other_org)
        session.flush()
        other_org_id = other_org.id

    repo.upsert_lesson(org_id, _sample_lesson())
    assert len(repo.list_lessons(org_id)) == 1
    assert len(repo.list_lessons(other_org_id)) == 0
