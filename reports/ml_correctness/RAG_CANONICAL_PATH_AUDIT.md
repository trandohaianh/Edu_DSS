# RAG Canonical Path Audit

## Finding: one canonical path, no duplicate/legacy retrieval implementation

Traced every retrieval/vector/embedding/RAG-adjacent call site in the codebase:

- **Storage layer** (`dss/services/vector_store.py`): 1 abstract base (`BaseVectorStore`) + exactly 2 concrete implementations — `LocalVectorStore` (JSON/NumPy, no Postgres needed — dev/demo default) and `PgVectorStore` (real Postgres + pgvector — production path, validated live this pass, see `POSTGRES_RUNTIME_VALIDATION.md`). No third, dead, or duplicate store class exists.
- **Retrieval entry point**: exactly one — `rag_service.py::retrieve_unified_context()`. Confirmed via grep across `dss/tabs/*.py` that **no tab directly instantiates `LocalVectorStore`/`PgVectorStore` or calls `.search()`/`.add_chunks()` directly** — every UI path goes through this single function.
- **`ai_advisor.py`'s `_find_docs_rag_safe()`** is a thin, single-purpose wrapper around `retrieve_unified_context()` (records retrieval status/message into `st.session_state`, returns `chunks`) — not a parallel implementation.
- **CMS→RAG lifecycle** (`cms_rag_lifecycle.py::upsert_and_reindex()`) calls `vector_store.add_chunks()` directly (the write side), which is correctly the same underlying store class the read side (`retrieve_unified_context`) queries — same canonical storage, not a second write path.

**Conclusion: there is no legacy or duplicate RAG path to deprecate.** The architecture is already single-path. This audit did not find the "two RAG flows" scenario the master prompt's Section 4.27 worried about — the concern was checked for and not found, which is itself the useful result (a negative finding, reported honestly rather than searched for so hard that one gets invented).

## What was found instead: a real document-governance gap (carried forward from Câu 73)

While the *retrieval mechanism* is single-path and clean, the **content source** feeding it is not fully unified — see `RAG_DOCUMENT_GOVERNANCE.md` for the specific finding (19 hardcoded documents in `ai_advisor.py`'s knowledge base vs. Admin-uploaded documents not consumed by the same path). This is a content-governance issue, not a retrieval-mechanism duplication issue — worth keeping the two concerns distinct.

## Scope note

This audit traced the *code paths* (which functions call which). It did not re-benchmark retrieval quality (see `docs/ai/AI_ROUTING_MATRIX.md`/`ML_CORRECTNESS_FINAL_AUDIT.md` for the top-k and embedding-model findings, which are quality concerns, not path-duplication concerns).
