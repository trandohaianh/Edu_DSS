"""PostgreSQL CMS metadata and stale-safe RAG lifecycle boundary."""

from __future__ import annotations

import hashlib
from typing import Any

from dss.core.observability import observed
from dss.db.repositories import domain_persistence_repository as domain_repo
from dss.services.chunking_service import DocumentChunk
from dss.services.vector_store import BaseVectorStore


def _metadata_record(organization_id: int, content: dict[str, Any], document_id: str | None) -> dict[str, Any]:
    raw = content.get("body", "").encode("utf-8")
    return {
        "organization_id": organization_id,
        "content_external_id": content["content_external_id"],
        "course_external_id": content.get("course_external_id"),
        "title": content["title"],
        "content_type": content.get("content_type", "document"),
        "source_reference": content.get("source_reference"),
        "mime_type": content.get("mime_type", "text/plain"),
        "checksum_sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "version": int(content.get("version", 1)),
        "status": content.get("status", "active"),
        "rag_document_id": document_id,
    }


@observed("kb.reindex")
def upsert_and_reindex(
    organization_id: int, content: dict[str, Any], chunks: list[DocumentChunk], vector_store: BaseVectorStore
) -> dict[str, Any]:
    """Replace a content item's vector document without leaving stale chunks searchable."""
    previous = domain_repo.get_cms_content(organization_id, content["content_external_id"])
    new_document_id = chunks[0].document_id if chunks else None
    old_document_id = previous.get("rag_document_id") if previous else None
    if not chunks or not new_document_id:
        raise ValueError("re-index requires at least one chunk")
    # Same-id replacement must delete first so removed chunks cannot survive an upsert.
    if old_document_id == new_document_id:
        vector_store.delete_document(old_document_id)
    vector_store.add_chunks(chunks)
    if old_document_id and old_document_id != new_document_id:
        vector_store.delete_document(old_document_id)
    result = domain_repo.upsert_cms_content(
        organization_id, _metadata_record(organization_id, content, new_document_id)
    )
    return {**result, "old_document_id": old_document_id, "new_document_id": new_document_id}


@observed("kb.invalidate")
def invalidate_content(organization_id: int, content_external_id: str, vector_store: BaseVectorStore) -> bool:
    current = domain_repo.get_cms_content(organization_id, content_external_id)
    if not current:
        return False
    if current.get("rag_document_id"):
        vector_store.delete_document(current["rag_document_id"])
    domain_repo.upsert_cms_content(
        organization_id,
        {
            "organization_id": organization_id,
            "content_external_id": content_external_id,
            "title": current["title"],
            "checksum_sha256": current["checksum_sha256"],
            "version": current["version"],
            "status": "invalidated",
            "rag_document_id": None,
        },
    )
    return True
