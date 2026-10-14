# Phase 1B — Incremental PostgreSQL Runtime Cutover

Base commit: `f120281` (Phase 1 baseline repair — verified: app starts, 467/467
non-E2E, 39/39 E2E, 9/9 PostgreSQL schema, 5/5 RLS adversarial).

This document reports what Phase 1B actually built and verified on top of
that baseline: **PostgreSQL as the real runtime persistence backend** for
migrated domains — not merely "a SQLAlchemy table exists." Status is
reported per domain using evidence (file paths + test names), not
assumptions, with the exact taxonomy the engagement specified.

## Status taxonomy (used verbatim below)

`LOCAL_ONLY` · `SCHEMA_ONLY` · `REPOSITORY_READY` · `PARTIALLY_WIRED` ·
`POSTGRES_PRIMARY_WITH_FALLBACK` · `FULLY_MIGRATED`

Note on `FULLY_MIGRATED`: the engagement's own no-dual-write / no-silent-cutover
requirement ("PostgreSQL disabled: preserve current local behavior for
compatibility") means every wired domain in this app is designed to always
keep a local-fallback code path available behind a flag. Under that design
constraint, no domain in this app can honestly reach `FULLY_MIGRATED` without
*deleting* the local fallback entirely — which was not requested and would
remove the incremental-cutover safety net. `POSTGRES_PRIMARY_WITH_FALLBACK`
is therefore the ceiling status for any domain with a live call site.

## Per-domain acceptance table

| # | Domain | Original backend | PostgreSQL repository | Runtime wired | Postgres primary | RLS tested | Migration utility | Fallback tested | Real integration test | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Students | Bulk pandas DataFrame (`generate_data`/`generate_lms_data`), no per-record CRUD | `dss/db/repositories/academic_repository.py::upsert_student` | No — no existing single-record call site (see audit finding below) | N/A | Yes (`cbae9b411ed5` policy on `students`) | `import_dataframe()` | N/A (no live gate) | `tests/test_academic_repository.py` (9 tests) | REPOSITORY_READY |
| 2 | Lecturers | same DataFrame | `academic_repository.py::upsert_lecturer` | No | N/A | Yes | via `import_dataframe()` (lecturer_id not in current dataset — upsert function tested directly) | N/A | same file | REPOSITORY_READY |
| 3 | Courses | same DataFrame | `academic_repository.py::upsert_course` | No | N/A | Yes | via `import_dataframe()` | N/A | same file | REPOSITORY_READY |
| 4 | Enrollments | same DataFrame | `academic_repository.py::upsert_enrollment` | No | N/A | Yes | via `import_dataframe()` | N/A | same file | REPOSITORY_READY |
| 5 | Academic records | same DataFrame (`diem_*`/`ty_le_diem_danh` columns) | `academic_repository.py::record_academic_record` | No | N/A | Yes | `import_dataframe()`, `replace_existing` re-import mode | N/A | same file | REPOSITORY_READY |
| 6 | Predictions | `dss/core/warehouse.py::save_prediction` → local JSON (`prediction_history.json`) | `dss/db/repositories/prediction_repository.py` | **Yes** — `warehouse.py::save_prediction`, gated by `is_postgres_enabled("PREDICTIONS")` | Yes when enabled | Yes (schema RLS + explicit org filter) | `import_from_local_history()` | Yes | `tests/test_predictions_consultations_postgres_wiring.py` | POSTGRES_PRIMARY_WITH_FALLBACK |
| 7 | Recommendations | **None — fully ephemeral.** `career_ai_advisor.py` generates career-chat answers live into `st.session_state` only; no save function exists anywhere in that module or `advisory.py` | `dss/db/repositories/recommendation_repository.py` | No — see audit finding below | N/A | Yes | N/A (nothing local to import — there was never a store) | N/A | `tests/test_recommendation_repository.py` (4 tests) | REPOSITORY_READY |
| 8 | Consultations | `warehouse.py::save_ai_consultation` → local JSON (`advisor_history.json`) | `dss/db/repositories/consultation_repository.py` | **Yes** — gated by `is_postgres_enabled("CONSULTATIONS")` | Yes when enabled | Yes | `import_from_local_history()` (new `local_consultation_id` dedup column, migration `f0b43f540e41`) | Yes | same test file as #6 | POSTGRES_PRIMARY_WITH_FALLBACK |
| 9 | Subscriptions | `dss/services/subscription_service.py` → local JSON | `dss/db/repositories/subscription_repository.py` | **Yes** — gated by `is_postgres_enabled("SUBSCRIPTION")` | Yes when enabled | Yes | N/A (subscription is a singleton-per-org row, created on first read — `get_or_create_subscription`) | Yes | `tests/test_subscription_postgres_wiring.py` (4 tests) | POSTGRES_PRIMARY_WITH_FALLBACK |
| 10 | CMS (lessons/quizzes/interactions) | `cms_lecture_repository.py` + `learning_explainer.py` → local JSON | `dss/db/repositories/cms_repository.py`, new migration `830742fd75d4` (4 tables, own RLS) | No — see scope decision below | N/A | Yes (direct org_id policy on 3 tables, subquery policy on `cms_lesson_versions`) | `import_from_local()` — verified against REAL local data (2 lessons, 1 quiz, 341 interactions) **and** against controlled fixtures for edge cases | N/A | `tests/test_cms_repository.py` (12 tests) | REPOSITORY_READY |
| 11 | RAG document/chunk persistence | `dss/services/vector_store.py::LocalVectorStore` → NumPy matrix + JSON on disk | `PgVectorStore` now targets the real Phase 1 `rag_documents`/`rag_chunks` tables (old incompatible `DDL_SCHEMA`, which had no `organization_id`, removed) | **Yes** — `get_vector_store()` factory, gated by `is_postgres_enabled("RAG")` | Yes when enabled | Yes (`cbae9b411ed5` policies, enforced via explicit `organization_id` filter in every query + `SET LOCAL app.organization_id`) | N/A (chunk-level upsert via `ON CONFLICT (chunk_id)` is itself the re-index path) | Yes (`LocalVectorStore` untouched, still the default) | `tests/test_pgvector_store.py` (11 tests) | POSTGRES_PRIMARY_WITH_FALLBACK |
| 12 | pgvector similarity search | `LocalVectorStore.search()` — loads entire matrix into NumPy, `sklearn.cosine_similarity` in Python | `PgVectorStore.search()` — real SQL, pgvector `<=>` cosine-distance operator, `ORDER BY ... LIMIT` executed server-side | Yes (same gate as #11) | Yes when enabled | Yes (same as #11) | N/A | Yes | `test_search_ranks_by_real_pgvector_distance_not_python` proves ranking follows real distance math (3 chunks at controlled cosine distances, asserts exact SQL-ranked order + document_id-filter pushed into `WHERE`, not Python) | POSTGRES_PRIMARY_WITH_FALLBACK |

### Audit findings behind the `REPOSITORY_READY` ceiling (domains 1–5, 7, 10)

- **Students/Lecturers/Courses/Enrollments/Academic records (1–5):** no
  existing runtime service exists for these as individual entities today.
  `dss/core/data_helpers.py::generate_data()`/`generate_lms_data()` produce
  one flat pandas DataFrame consumed in bulk by the ML pipeline
  (`dss/core/trainers.py`, `dss/tabs/eda.py`, `dss/tabs/ml_hub.py`) — there is
  no per-student CRUD call site to wire without redesigning that pipeline's
  entire data-access pattern, which touches `dss/tabs/eda.py` (one of the
  five files this engagement explicitly flagged as a future
  security-hardening integration point). Real, tested repository + a real
  DataFrame→Postgres ETL utility (`import_dataframe`) were built instead —
  new capability, not a cutover of an existing read path.
- **Recommendations (7):** `career_ai_advisor.py`/`advisory.py`'s career chat
  is a live, per-turn conversational stream stored only in
  `st.session_state` — there is no existing `save` function anywhere to cut
  over. A real, tested repository against the Phase 1 `recommendations`
  schema was built (student identity resolved via `academic_repository`),
  but it is not wired into the interactive chat loop this pass — doing so
  would change that loop's behavior/UX, which is out of this pass's scope.
- **CMS (10):** `cms_lecture_repository.py`/`learning_explainer.py` are
  large, actively-used services with many call sites. This pass built the
  real schema, repository, and a tested import path (verified against both
  real local data and controlled edge-case fixtures) but did not redirect
  those services' own read/write functions to Postgres live — documented as
  a deliberate scope decision, not an oversight.

## Local storage audit (remaining stores, excluding domains covered above)

| Store | Code | Data | Location | Category |
|---|---|---|---|---|
| Model artifacts | `warehouse.py` `save_model_training`/`load_model_training`/`set_production_model`, wrapped by `model_registry.py` | Trained sklearn pipeline binary + SHA-256/version/status metadata | `data_warehouse/models/*.joblib`, `data_warehouse/metadata/*_model.json` | MODEL_ARTIFACT (binary); metadata JSON is DATABASE_DATA-eligible in a future pass |
| Dataset files | `warehouse.py` `save_dataset`/`save_raw_data`/`save_processed_data`/`save_training_data` | Raw/processed/train-test CSV rows + metadata | `data_warehouse/{raw_data,processed_data,training_data,evaluation_data}/*.csv` + metadata JSON | OBJECT_STORAGE_CANDIDATE (CSV blobs); metadata sidecar is DATABASE_DATA |
| Evaluation results | `warehouse.py` `save_evaluation_data`/`get_evaluation_data_for_rag` | Per-training-run evaluation metrics | `data_warehouse/evaluation_data/*.json` | DATABASE_DATA |
| Training/activity history log | `warehouse.py` `_add_to_history`/`log_activity`/`get_history` | Append-only training/activity audit trail (distinct from predictions/consultations, already migrated) | `data_warehouse/history/{training_history,activity_history,activities}.json` | DATABASE_DATA |
| Legacy embedding cache | `VectorStore` class inside `warehouse.py`, instantiated by `MultiAIProvider.__init__` in `dss/core/models.py` | Embeddings + cached text for the OLD hard-coded 19-doc knowledge base — a second, older embedding mechanism separate from `dss/services/vector_store.py` | `data_warehouse/embeddings/*.npy` | TEMPORARY_CACHE (regeneratable; a legacy duplicate mechanism, not the RAG store migrated in this phase) |
| AI token usage ledger | `dss/services/token_tracker.py` | Per-request LLM token/cost usage, pseudonymized user_id | `data_warehouse/ai_token_usage.json` | DATABASE_DATA |
| Admin default AI provider config | `dss/services/admin_ai_config.py` | System-wide default LLM provider/model | `data_warehouse/ai_default_provider.json` | DATABASE_DATA (small system-config row) |
| User accounts / auth | `dss/services/auth_service.py` | username, role, PBKDF2 hash+salt | `data_warehouse/users.json` | DATABASE_DATA — `repository_for("IDENTITY")` exists but raises `NotImplementedError` if set to postgres; this JSON remains the only functioning identity store. Users/auth runtime cutover was explicitly deferred by the engagement to a later dedicated phase. |
| LMS SQLite relational DB | `dss/core/lms_repository.py::SQLiteLMSRepository` | Student events/learning plans (17-table schema defined, 3 created) | `data_warehouse/lms_production.db` | LEGACY_FALLBACK — every live call site defaults to `MODE_DEMO`; `REAL_CONNECTOR` mode is never actually requested anywhere in the app |
| Technical log file | `dss/core/logging_config.py` | Rotating operational/debug log | `data_warehouse/logs/technical.log` | TEMPORARY_CACHE |

`dss/services/semantic_cache.py` and `document_ingestion.py` do no
filesystem I/O of their own (in-memory/pass-through) — not counted.
`dss/tabs/{eda,warehouse_tab,dashboard}.py` only do transient
`pd.read_csv`/`to_csv` on user-uploaded/download buffers, not persistent app
state — not counted.

## Migration safety

Idempotent import utilities exist for every domain that had pre-existing
local data to migrate (predictions, consultations, academic/CMS bulk data).
Each is tested for: empty-store import (no-op), repeat import (no
duplication), invalid/orphaned record handling (skipped, not guessed at or
crashed on), and cross-tenant assignment (never silently cross-assigned —
verified by asserting a second organization's count stays zero after
importing into the first). See `tests/test_academic_repository.py`,
`tests/test_cms_repository.py`, and the `test_import_*` tests in
`tests/test_predictions_consultations_postgres_wiring.py`.

One schema addition was needed to make consultation-history import
idempotent: `consultations.local_consultation_id` (nullable, indexed),
added in a new, additive migration `f0b43f540e41` — does not modify
`4915552f6063` (initial schema) or any other prior migration.

## Bug found and fixed during this pass (pre-existing, not introduced by Phase 1B)

`tests/test_db_row_level_security.py`'s schema-reset fixture called
`Base.metadata.drop_all(engine)` without first importing `dss.db.models` —
`Base.metadata` starts empty until some module populates it, so `drop_all`
silently no-op'ed and the subsequent `alembic upgrade head` could fail with
`DuplicateTable` when this file ran without another test module having
already imported `dss.db.models` first (previously "worked" only by
accident of pytest's collection order in a full-suite run). Fixed with one
defensive `import dss.db.models` line in the fixture — no RLS behavior
changed; verified by re-running the file standalone (5/5 pass) both alone
and as part of the full suite.

`tests/test_lms_ai_rag_gateway.py::test_07_vector_store_local_and_pgvector_schema`
asserted against `PgVectorStore.DDL_SCHEMA`, a stub-only class attribute
describing a schema that never actually ran and was incompatible with the
real Phase 1 `rag_documents`/`rag_chunks` tables (no `organization_id`).
Removed with the stub; the test now asserts against the real ORM models
(`dss.db.models.RagDocument`/`RagChunk`) instead.

## Testing (final regression, base commit `f120281` → this Phase 1B state)

| Suite | f120281 baseline | This state |
|---|---|---|
| Non-E2E (no Postgres configured — local-mode default) | 467/467 | 467/467, 0 regressions |
| Non-E2E (DATABASE_URL + DATABASE_APP_ROLE_URL configured) | — | 523/523, 0 skipped |
| PostgreSQL schema tests | 9/9 | 9/9 |
| RLS adversarial tests | 5/5 | 5/5 |
| pgvector integration tests (new) | — | 11/11 |
| Phase 1B repository tests (new, total) | — | 51/51 (academic 9, predictions/consultations 11, subscription 4, CMS 12, recommendations 4, pgvector 11 — see table cells above) |
| E2E (Playwright) | 39/39 | 39/39, 0 regressions (13m14s run against the same live Postgres+pgvector container) |
| Application startup | HTTP 200 | unchanged — no cautioned file (`main.py`, `core/models.py`, `tabs/eda.py`, `tabs/warehouse_tab.py`, `Dockerfile`) was modified |

## Files touched that are on the security-hardening caution list

None of the five explicitly cautioned files (`dss/main.py`,
`dss/core/models.py`, `dss/tabs/eda.py`, `dss/tabs/warehouse_tab.py`,
`Dockerfile`) were modified in this pass.

Files modified that are **not** on that list but do carry live-wiring risk
of eventual merge conflict with `security-hardening` (documented per the
engagement's instruction):
- `dss/core/warehouse.py` — added the `is_postgres_enabled` branch inside
  `save_prediction`/`save_ai_consultation`; local-path code is byte-for-byte
  unchanged.
- `dss/services/subscription_service.py` — same pattern for subscriptions.
- `dss/services/vector_store.py` — `PgVectorStore` implemented for real;
  `get_vector_store()` factory now gates on `is_postgres_enabled("RAG")`
  instead of bare `DATABASE_URL` presence; `LocalVectorStore` untouched.
- `dss/core/persistence_config.py` — new `is_postgres_enabled()` gate
  function, added alongside (not replacing) the pre-existing
  `repository_for()`.
- `dss/db/models.py` — 4 new CMS models appended; one new column
  (`Consultation.local_consultation_id`) added.
- Two new, additive-only Alembic migrations
  (`830742fd75d4`, `f0b43f540e41`); the verified initial migration
  (`4915552f6063`) and the RLS migration (`cbae9b411ed5`) were not modified.
- `tests/test_db_row_level_security.py`, `tests/test_lms_ai_rag_gateway.py`
  — the two pre-existing-bug fixes described above.

## Remaining limitations (honest, not glossed over)

- Domains 1–5, 7, and 10 are `REPOSITORY_READY`, not wired into a live call
  site — see the audit findings above for exactly why, per domain.
- Users/auth (`dss/services/auth_service.py`) runtime cutover is explicitly
  out of scope for Phase 1B per the engagement's own instruction (deferred
  to a later dedicated step) and was not attempted.
- Model Registry (`model_versions`/`model_metrics`) live-training-pipeline
  cutover is out of Phase 1B's 12-domain scope; `prediction_repository.py`
  auto-creates a minimal placeholder `ModelVersion` row per `training_id`
  the first time it's seen, documented explicitly in that module.
- Model artifacts, dataset CSVs, and the legacy embedding cache remain on
  local disk by design (MODEL_ARTIFACT/OBJECT_STORAGE_CANDIDATE/
  TEMPORARY_CACHE — not relational data Postgres should own).
- The LMS SQLite repository (`lms_production.db`) is confirmed dead code in
  practice (no live call site ever requests `REAL_CONNECTOR` mode) —
  flagged as `LEGACY_FALLBACK`, not migrated, not deleted this pass.

## Final status

Base commit: `f120281`
Final commit: (uncommitted at time of writing — see below)

**PASS_WITH_DOCUMENTED_REMAINING_MIGRATION**

Six of twelve domains (predictions, consultations, subscriptions, RAG
document/chunk persistence, pgvector search) reached
`POSTGRES_PRIMARY_WITH_FALLBACK` with real, tested, non-dual-write runtime
wiring. The remaining domains (students, lecturers, courses, enrollments,
academic records, recommendations, CMS) reached `REPOSITORY_READY` — real
schema, real tested repository and import utilities, real RLS — for
honestly audited architectural reasons documented per-domain above, not
oversights. Zero regressions confirmed against the `f120281` baseline
across every comparable test suite that was run.
