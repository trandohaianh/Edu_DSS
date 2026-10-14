"""dss/services/vector_store.py::PgVectorStore — real PostgreSQL + pgvector
integration tests (Phase 1B, migration order items 11/12). Skipped (not
faked) without a configured database.

These tests prove the search executes server-side in PostgreSQL via
pgvector's `<=>` cosine-distance operator (result ranking follows real
distance math, not a Python-side sklearn pass over an in-memory matrix like
LocalVectorStore), and that add/search/delete/list are tenant-scoped through
the same RLS mechanism as every other Phase 1B repository.
"""
from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured
from dss.services.chunking_service import DocumentChunk

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — pgvector store tests skipped, not faked",
)


def _connection_url() -> str:
    from dss.db.session import _resolve_database_url
    return _resolve_database_url()


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"RAG_TEST_{uuid.uuid4().hex[:8]}", name="RAG Test Org")
        session.add(org)
        session.flush()
        return org.id


@pytest.fixture()
def store(org_id):
    from dss.services.vector_store import PgVectorStore
    s = PgVectorStore(_connection_url(), organization_id=org_id)
    assert s.is_available()
    return s


def _unit_vector(dim: int, hot_index: int) -> list:
    """A 384-dim vector that is 1.0 at `hot_index` and a tiny constant
    elsewhere — lets us construct vectors with known, controllable cosine
    distance from each other without needing a real embedding model."""
    v = [0.001] * dim
    v[hot_index] = 1.0
    return v


def _chunk(chunk_id, document_id, content, hot_index, dim=384, metadata=None):
    return DocumentChunk(
        chunk_id=chunk_id, document_id=document_id, course_id="CS301",
        content=content, token_count=len(content.split()),
        metadata=metadata or {"title": document_id, "source": "unit-test"},
        embedding=_unit_vector(dim, hot_index),
    )


def test_add_chunks_inserts_real_rows(store, org_id):
    from dss.db.models import RagChunk, RagDocument
    from dss.db.session import session_scope

    n = store.add_chunks([_chunk("c1", "doc_a", "Nội dung A", 0)])
    assert n == 1

    with session_scope() as session:
        doc = session.query(RagDocument).filter_by(organization_id=org_id, document_id="doc_a").one()
        chunk = session.query(RagChunk).filter_by(chunk_id="c1").one()
        assert chunk.document_id == doc.id
        assert chunk.content == "Nội dung A"
        assert chunk.embedding is not None


def test_add_chunks_upserts_on_conflict(store):
    store.add_chunks([_chunk("c1", "doc_a", "version 1", 0)])
    store.add_chunks([_chunk("c1", "doc_a", "version 2", 0)])

    from dss.db.models import RagChunk
    from dss.db.session import session_scope
    with session_scope() as session:
        rows = session.query(RagChunk).filter_by(chunk_id="c1").all()
    assert len(rows) == 1
    assert rows[0].content == "version 2"


def test_search_ranks_by_real_pgvector_distance_not_python(store):
    """Three chunks: one identical direction to the query, one orthogonal-ish,
    one opposite. If ranking is real SQL `<=>` distance (not insertion order,
    not a random default), the identical one must come back first."""
    store.add_chunks([
        _chunk("near", "doc_a", "closest", hot_index=5),
        _chunk("mid", "doc_a", "middle", hot_index=50),
        _chunk("far", "doc_a", "farthest", hot_index=383),
    ])
    query = _unit_vector(384, 5)  # identical to "near"
    results = store.search(query, top_k=3)

    assert [r["chunk_id"] for r in results] == ["near", "mid", "far"]
    assert results[0]["relevance_score"] > results[1]["relevance_score"] > results[2]["relevance_score"]
    assert results[0]["relevance_score"] > 0.99  # near-identical vector -> near-1.0 cosine similarity


def test_search_respects_document_ids_filter(store):
    store.add_chunks([_chunk("a1", "doc_a", "in scope", 5)])
    store.add_chunks([_chunk("b1", "doc_b", "out of scope", 5)])

    results = store.search(_unit_vector(384, 5), top_k=10, document_ids={"doc_a"})
    assert {r["chunk_id"] for r in results} == {"a1"}


def test_search_empty_document_ids_allowlist_returns_nothing(store):
    store.add_chunks([_chunk("a1", "doc_a", "content", 5)])
    assert store.search(_unit_vector(384, 5), top_k=10, document_ids=set()) == []


def test_delete_document_cascades_to_chunks(store, org_id):
    store.add_chunks([_chunk("c1", "doc_a", "content", 5)])
    assert store.delete_document("doc_a") is True

    from dss.db.models import RagChunk, RagDocument
    from dss.db.session import session_scope
    with session_scope() as session:
        assert session.query(RagDocument).filter_by(organization_id=org_id, document_id="doc_a").count() == 0
        assert session.query(RagChunk).filter_by(chunk_id="c1").count() == 0


def test_delete_nonexistent_document_returns_false(store):
    assert store.delete_document("does_not_exist") is False


def test_list_documents_scoped_to_namespace(store):
    store.add_chunks([_chunk("c1", "doc_a", "content", 5, metadata={"title": "Doc A"})])
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0]["document_id"] == "doc_a"
    assert docs[0]["title"] == "Doc A"


def test_cross_tenant_isolation(org_id):
    from dss.db.models import Organization
    from dss.db.session import session_scope
    from dss.services.vector_store import PgVectorStore

    with session_scope() as session:
        other = Organization(org_code=f"RAG_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    store_a = PgVectorStore(_connection_url(), organization_id=org_id)
    store_b = PgVectorStore(_connection_url(), organization_id=other_org_id)

    store_a.add_chunks([_chunk("c1", "doc_a", "org A content", 5)])

    assert len(store_a.list_documents()) == 1
    assert len(store_b.list_documents()) == 0
    assert store_b.search(_unit_vector(384, 5), top_k=10) == []
    assert store_b.delete_document("doc_a") is False


def test_search_requires_organization_id():
    from dss.services.vector_store import PgVectorStore
    store = PgVectorStore(_connection_url(), organization_id=None)
    with pytest.raises(RuntimeError):
        store.search(_unit_vector(384, 0), top_k=5)


def test_add_chunks_requires_organization_id():
    from dss.services.vector_store import PgVectorStore
    store = PgVectorStore(_connection_url(), organization_id=None)
    with pytest.raises(RuntimeError):
        store.add_chunks([_chunk("c1", "doc_a", "content", 0)])
