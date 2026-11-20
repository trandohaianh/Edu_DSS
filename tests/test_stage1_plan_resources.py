"""Only current, reviewed material from the selected course enters a plan."""
from types import SimpleNamespace

from dss.services import learning_plan_resources as resources


def test_cms_resources_require_review_course_and_current_version(monkeypatch):
    def lesson(key, document_id, **overrides):
        values = dict(course_id="CS101", topic_id="loops", lesson_id=key, title=key,
                      current_document_id=document_id, official_source=True,
                      excluded_document_ids=[])
        values.update(overrides)
        return SimpleNamespace(**values)

    lessons = [
        lesson("current", "approved"), lesson("draft", "draft"),
        lesson("revoked", "approved", excluded_document_ids=["approved"]),
        lesson("other", "other", course_id="DB201"),
        lesson("unofficial", "approved", official_source=False),
        lesson("expired", "expired"),
    ]
    documents = [
        {"document_id": "approved", "course_id": "CS101", "status": "APPROVED", "approved_by": "teacher"},
        {"document_id": "draft", "course_id": "CS101", "status": "PENDING_REVIEW"},
        {"document_id": "other", "course_id": "DB201", "status": "APPROVED", "approved_by": "teacher"},
        {"document_id": "expired", "course_id": "CS101", "status": "APPROVED",
         "approved_by": "teacher", "expires_at": "2000-01-01T00:00:00+00:00"},
    ]
    monkeypatch.setattr(resources.cms_lecture_repository, "list_lessons", lambda **kwargs: lessons)
    monkeypatch.setattr(resources.vector_store, "get_vector_store", lambda **kwargs:
                        SimpleNamespace(list_documents=lambda: documents))
    result = resources.approved_plan_resources("CS101")
    assert len(result) == 1
    assert result[0]["resource_id"] == "cms:current:approved"
    assert result[0]["verified_cms"] is True
    assert "url" not in result[0]


def test_no_lessons_does_not_initialize_vector_store(monkeypatch):
    monkeypatch.setattr(resources.cms_lecture_repository, "list_lessons", lambda **kwargs: [])
    def forbidden(**kwargs):
        raise AssertionError("No vector store needed")
    monkeypatch.setattr(resources.vector_store, "get_vector_store", forbidden)
    assert resources.approved_plan_resources("CS101") == []
