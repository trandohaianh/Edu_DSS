"""Exact ordered resource reads without embedding inference."""
from dss.services.chunking_service import DocumentChunk
from dss.services.vector_store import LocalVectorStore


def test_plain_read_filters_course_namespace_and_preserves_order(tmp_path, monkeypatch):
    store = LocalVectorStore(str(tmp_path), namespace="student_learning")
    chunks = [
        DocumentChunk("doc#c10", "doc", "LAW101", "Later section", 2, {"chunk_index": 10}, [1.0, 0.0]),
        DocumentChunk("doc#c2", "doc", "LAW101", "Earlier section", 2, {"chunk_index": 2}, [1.0, 0.0]),
        DocumentChunk("doc#c1", "doc", "OTHER", "Other course", 2, {"chunk_index": 1}, [1.0, 0.0]),
    ]
    store.add_chunks(chunks)
    monkeypatch.setattr(store, "search", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No embedding search")))
    result = store.get_document_chunks("doc", course_id="LAW101")
    assert [item["content"] for item in result] == ["Earlier section", "Later section"]
    assert all("embedding" not in item for item in result)
    result[0]["metadata"]["chunk_index"] = 999
    assert store.get_document_chunks("doc", course_id="LAW101")[0]["metadata"]["chunk_index"] == 2
    assert store.get_document_chunks("missing", course_id="LAW101") == []
    assert LocalVectorStore(str(tmp_path), namespace="policy_admin").get_document_chunks("doc", course_id="LAW101") == []


def test_selected_postgres_failure_does_not_read_local_content(monkeypatch):
    import pytest
    from dss.services import vector_store
    monkeypatch.setenv("EDUDSS_RAG_STORE", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://isolated.invalid/test")
    class Unavailable:
        def __init__(self, *args, **kwargs):
            pass
        def is_available(self):
            return False
    monkeypatch.setattr(vector_store, "PgVectorStore", Unavailable)
    monkeypatch.setattr(vector_store, "LocalVectorStore", lambda **kwargs: pytest.fail("No local fallback"))
    with pytest.raises(RuntimeError, match="unavailable"):
        vector_store.get_vector_store()
