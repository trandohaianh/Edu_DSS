# LMS / CMS / RAG — Consolidated Product Verification

This phase consolidates everything verified about these 3 subsystems across the whole engagement
(architecture-accuracy pass + this Student/Lecturer/Admin acceptance pass) rather than re-doing
work already done with real evidence. Pointers to where each claim was established are included
so nothing here is asserted without a traceable source.

## RAG (Retrieval-Augmented Generation)

| Claim | Status | Evidence |
|---|---|---|
| Real multi-format document ingestion (txt/md/docx/pptx/pdf/json) | VERIFIED | Code trace: `knowledge_base.py` → `document_ingestion.ingest_document()` → `vector_store.add_chunks()`; `ARCH-PGVECTOR-001` investigation |
| Real retrieval with relevance thresholds | VERIFIED | `dss/config.py`: `RAG_LOW_CONFIDENCE_FLOOR=0.55`, `RAG_RELATIVE_THRESHOLD=0.85`; exercised by `test_10_retrieval_returns_no_relevant_evidence_on_low_confidence` |
| Refuses to force a weak match | VERIFIED | Same as above — `NO_RELEVANT_EVIDENCE` status, not a forced fallback document |
| Namespace isolation (student_learning / lecturer_support / admin_operations) | VERIFIED | `test_08_rag_namespace_isolation_and_permissions`; live confirmed via `admin_rag.png` |
| Active vector store is `LocalVectorStore`, not `PgVectorStore` | VERIFIED | `get_vector_store()` only activates Pg when `PGVECTOR_URL`/`DATABASE_URL` is set — neither is set; `PgVectorStore`'s CRUD methods are stubs anyway (`ARCH-PGVECTOR-001`) |
| Create + Read only (no Edit/Delete in the product) | VERIFIED (documented gap, not a bug) | `KB-CRUD-001` — `delete_document()` exists on the vector store classes but has zero UI callers anywhere |
| No chunk/embedding internals leaked to Admin UI | VERIFIED | `list_documents()` returns only `document_id/title/course_id/source/permission_scope/total_chunks/created_at` — no raw chunk IDs or vectors |

## CMS (Course/Lecture Content Management — internal to EduDSS)

| Claim | Status | Evidence |
|---|---|---|
| Real Lecturer upload → real ingestion → real retrieval → real AI citation | VERIFIED, live | A real `sv902` chat asking about K-Means returned a verbatim quote from the actual ingested `bai4_kmeans_v2.txt` with a traceable citation (`doc_727bb407b8#c1`) |
| Course isolation | VERIFIED | `test_09_cross_course_retrieval_blocked` |
| Version pinning (superseded versions not retrievable) | VERIFIED | `test_08_retrieval_uses_current_version_only` (this file's own test numbering, distinct from the RAG config's `test_10` above) |
| Socratic mode doesn't leak answers | VERIFIED | `test_04_socratic_does_not_leak_answer_immediately` |
| Quiz generation/approval workflow (Lecturer approves → Student receives; rejected never reaches Student) | VERIFIED by real tests; **not yet visually screenshot-verified live** | `test_06_lecturer_approves_quiz_then_student_receives`, `test_07_rejected_quiz_never_reaches_student` — the "Duyệt Quiz" and "Dashboard phân tích" CMS sub-tabs were not visually walked live this pass (only the default "Nạp & Quản lý" sub-tab was) |
| No "CMS" jargon leaked to Sinh viên | FIXED this session | `SIA-EXPLAINER-001` |
| Cold-start delay on first access (~55-60s, no loading indicator) | DOCUMENTED, not fixed | `COLDSTART-001` |

## LMS (External Learning Management System integration)

| Claim | Status | Evidence |
|---|---|---|
| No real external LMS connector exists | VERIFIED | `lms_connector.py::RealConnectorLMSRepository.get_student_learning_summary()` itself delegates to `DemoLMSRepository` internally |
| Architecture/abstraction layer exists and is ready for a real connector | VERIFIED (honestly disclosed now) | `dashboard.py`/`advisory.py`/`admin_settings.py` all now state this accurately after `DEMO-CAREER-001` and `DEMO-LMS-STATUS-001` fixes |
| No fabricated "Live" connection status anywhere | FIXED this session | `DEMO-LMS-STATUS-001` (P0) — was claiming "🟢 Trực tuyến (Live Webhook & REST Connector sẵn sàng)" with a fake secret; now shows an honest not-connected badge, confirmed live in `admin_settings_fixed.png` |
| Simulated LMS event injection cannot corrupt real data in production | FIXED this session | `DEMO-LMS-LIVEPUSH-001` — the "LMS Realtime Live Push" panel (which mutates the currently-open dataset with random values) is now hidden in REAL_LMS mode |
| Demo/synthetic LMS sync data cannot silently appear as real in production | FIXED earlier this session | `main.py`'s synthetic auto-bootstrap gate (`if EDUDSS_MODE == REAL_LMS: st.stop()` instead of silently generating data) |

## Cross-cutting: privacy / isolation

| Claim | Status | Evidence |
|---|---|---|
| Student profile data cannot be stored as retrievable knowledge | VERIFIED | `test_09_student_profile_cannot_be_stored_as_knowledge` (raises `ValueError` on attempt) |
| Private chat text never leaks into aggregated Lecturer analytics | VERIFIED | `test_13_private_chat_text_not_exposed_in_aggregated_analytics` |
| Cross-student profile leakage prevented | VERIFIED | `test_14_cross_student_profile_leakage_prevented` |

## Explicitly still open

- Live visual walkthrough of the "Duyệt Quiz" (quiz review queue) and "Dashboard phân tích"
  (CMS analytics) sub-tabs — functionally verified by real tests, not yet screenshot-verified.
- `COLDSTART-001` and `KB-CRUD-001` remain documented-not-fixed by deliberate scope decision (see
  their entries in `ISSUE_REGISTER.csv` for the reasoning).
- `ARCH-PGVECTOR-001` (PgVectorStore is a non-functional stub) remains documented-not-fixed —
  implementing real PostgreSQL SQL operations is a feature addition outside this pass's scope.

## Verdict

**RAG: PASS.** **CMS: PASS** (1 documented UX gap, `COLDSTART-001`). **LMS: HONEST_NOT_INTEGRATED**
— this is the correct target state per explicit instruction (architecture ready, no real external
connector, no fabricated claims of one existing). No new fixes required this phase beyond what was
already applied in the architecture-accuracy pass and the Student/Lecturer phases.
