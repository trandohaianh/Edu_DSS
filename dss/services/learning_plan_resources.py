"""Approved current CMS material for a course, without embedding or LLM calls."""

from __future__ import annotations

from dss.services import cms_lecture_repository, document_governance, vector_store
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


def approved_plan_resources(course_id: str) -> list[dict]:
    if not course_id:
        return []
    lessons = cms_lecture_repository.list_lessons(course_id=course_id)
    if not lessons:
        return []
    store = vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    documents = {doc["document_id"]: doc for doc in store.list_documents()}
    resources = []
    for lesson in lessons:
        document_id = lesson.current_document_id
        document = documents.get(document_id)
        if (
            lesson.course_id != course_id
            or not lesson.official_source
            or not document
            or document_id in lesson.excluded_document_ids
            or document.get("course_id") != course_id
            or not document_governance.is_document_usable(document)
        ):
            continue
        resources.append(
            {
                "resource_id": f"cms:{lesson.lesson_id}:{document_id}",
                "title": lesson.title,
                "course_id": course_id,
                "topic_id": lesson.topic_id,
                "status": "APPROVED",
                "source_kind": "cms_lesson",
                "verified_cms": True,
                "lesson_id": lesson.lesson_id,
                "document_id": document_id,
            }
        )
    return resources
