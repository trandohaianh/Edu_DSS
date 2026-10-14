# PHASE 0 — Codebase Audit (production-readiness engagement)

**Date:** 2026-09-17. **Method:** direct code inspection (grep/read of actual files) —
no reliance on prior documentation in `reports/final_ui_functional_audit/`, which covers a
different engagement (UI/RAG/performance) and is treated here only as a cross-check, never
as a source of truth. Every claim below cites a real file and, where non-obvious, a quoted
finding.

## Test baseline (before any change in this engagement)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | **450 / 450 PASS** (202.6s) |
| E2E (Playwright) | **39 / 39 PASS** (13m44s) |

No code has been changed yet. This is the baseline Phase 1+ must not regress.

## 1. Runtime entry point

`run_dss.py` → `dss/main.py` (single Streamlit script), launched via
`streamlit run run_dss.py`. `dss/main.py` does role-gated tab dispatch
(`selected_main_tab` against `dss/core/roles.py::TAB_ACCESS`).

| Feature | Implementation | File | Status |
|---|---|---|---|
| Runtime entry point | Single-process Streamlit app | `run_dss.py`, `dss/main.py` | **IMPLEMENTED** |

## 2. Architecture

Monolithic: UI (`dss/tabs/*.py`) calls service layer (`dss/services/*.py`) and core
(`dss/core/*.py`) **in-process**, sharing `st.session_state`. No API boundary, no separate
backend process. This is a real, coherent architecture for a single-server Streamlit app —
it is simply not the client/server split Phase 7 asks about.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Service-layer separation | UI calls `dss/services/*` directly, in-process | `dss/main.py`, `dss/tabs/*.py`, `dss/services/*.py` | **IMPLEMENTED** (as a monolith) | No API/service network boundary exists | Cannot scale UI and business logic independently; cannot be consumed by a mobile app/LMS plugin without duplicating logic | Phase 7: extract a FastAPI service layer incrementally, UI calls it over HTTP instead of importing Python modules directly |

## 3. Authentication

`dss/services/auth_service.py` (302 lines). Real PBKDF2-HMAC-SHA256 (`_PBKDF2_ITERATIONS =
200_000`) with per-user salt (`_hash_password`/`_verify_password`), rate limiting
(`is_account_locked`, `_record_failed_attempt`, `AccountLockedError`), seeded
admin/giangvien accounts, auto-provision for `SV\d{3}` usernames **only** when
`EDUDSS_MODE != REAL_LMS` (`_STUDENT_ID_PATTERN`). Session state is Streamlit's own
`st.session_state["_authenticated"]` — not a signed token, not shared across server
processes.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Password hashing | PBKDF2-HMAC-SHA256, 200k iter, per-user salt | `dss/services/auth_service.py:60-66` | **IMPLEMENTED** | none found | — | — |
| Brute-force protection | Failed-attempt counter + timed lockout | `dss/services/auth_service.py` (`is_account_locked`) | **IMPLEMENTED** | — | — | — |
| Session mechanism | `st.session_state`, in-memory, per Streamlit server process | `dss/services/auth_service.py` | **PARTIAL** | Not a portable/signed session token; lost on server restart; cannot horizontally scale across multiple app instances/load balancer without sticky sessions | Multi-instance deployment (needed for real concurrent-load scaling, Phase 10) breaks login | If Phase 7's API layer is built, move to JWT/signed session cookie |
| SSO / MFA / enterprise IdP | None | — | **NOT IMPLEMENTED** | University IT typically requires SSO (SAML/OIDC) | Real university deployment likely blocked without this | Out of scope unless explicitly requested — document as a known gap |

## 4. RBAC

Two real, independently-enforced layers, confirmed by code (not just UI hiding):
nav-level `TAB_ACCESS` dict (`dss/core/roles.py`) and function-level `@require_role(...)`
decorator (`dss/services/auth_service.py`), checked against
`st.session_state["_auth_role"]` (server-side truth, not a client-supplied parameter).

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| RBAC | Nav-level + function-level, 3 roles (Admin/Giảng viên/Sinh viên) | `dss/core/roles.py`, `dss/services/auth_service.py` | **IMPLEMENTED** | Fixed 3-role model, no fine-grained permissions/scopes beyond role name | Cannot express e.g. "department admin" vs "university admin" without new role constants | If Phase 4/5 need finer permissions, introduce a `permissions` table (see Phase 1 schema) instead of hardcoded role strings |

## 5. Student/Lecturer/Admin flows

Verified extensively across this whole multi-week engagement (dashboard, ML
training/prediction, clustering, AI Advisor, Learning Explainer, Knowledge Base, Model
Registry, Admin reports/settings) — each role sees a distinct, role-appropriate UI, real
data, real actions. **IMPLEMENTED.**

## 6. Storage layer

`dss/core/warehouse.py::DataWarehouse` — local JSON metadata + `.joblib` model artifacts +
flat files under `data_warehouse/` (models/datasets/raw_data/processed_data/training_data/
evaluation_data/metadata/history/embeddings/vector_stores). Path resolution centralized via
`dss/core/data_root.py::get_data_root()` (built this session for test isolation — real
users still get `data_warehouse/`, unchanged). **No relational database, no ORM, no
migration tool anywhere in the dependency tree** — confirmed via `requirements.txt`: only
`psycopg2-binary` is present, and only for `PgVectorStore`'s connection test (optional,
conditional on `PGVECTOR_URL`/`DATABASE_URL`). No `sqlalchemy`, no `alembic`, no `asyncpg`.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Local file storage | JSON + joblib, atomic writes, thread locks in newer stores | `dss/core/warehouse.py` | **IMPLEMENTED** | Single-node only; no transactions across multiple files; full-file rewrite on every write (`_atomic_json_write`) | Write contention / partial-write risk grows with data volume; not safe for multi-instance deployment | Phase 1: PostgreSQL migration behind a repository interface (see Phase 1 plan) |
| PostgreSQL persistence | None | — | **NOT IMPLEMENTED** | No ORM, no migrations, no schema | Cannot deploy multi-instance; no real concurrent-write safety; `.env.example` already documents `DB_HOST/PORT/NAME/USER/PASSWORD` as if this existed — **aspirational, not real** | Phase 1 |
| Migration tooling | None | — | **NOT IMPLEMENTED** | — | — | Alembic, per user's request |

## 7. ML pipeline

`dss/core/trainers.py` — real `ClassificationTrainer`/`RegressionTrainer` wrapping
scikit-learn/XGBoost/LightGBM with real train/test split, real metrics, K-Means clustering
with Elbow/Silhouette-assisted k selection, SHAP explainability. **IMPLEMENTED** — verified
extensively in prior phases of this engagement (not re-verified line-by-line this pass
since no red flags were raised and this isn't in the current phase's focus areas).

## 8. Model Registry

`dss/services/model_registry.py` (120 lines) + `dss/core/warehouse.py`. Real
candidate → production → archived lifecycle (`save_model_training` writes `status`,
`resolve_production`/`get_production_training_id` read a dedicated
`_production_index.json` pointer file — single source of truth, not `session_state`).
`promote()`/`rollback()` are `@require_role("Admin")`-gated and record `promoted_by`,
`promotion_reason` into the model's own metadata. Prediction persistence
(`warehouse.py::save_prediction`, line 279) records `training_id` (→ model version) and
`predicted_at` timestamp.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Candidate/Production/Archived lifecycle | Real, single-pointer-file source of truth | `dss/services/model_registry.py`, `dss/core/warehouse.py:333-546` | **IMPLEMENTED** | — | — | — |
| Model metadata (dataset, metrics, trained_at) | Present | `warehouse.py::save_model_training` params | **IMPLEMENTED** | No explicit `dataset_version` or `feature_schema` field distinct from the raw `feature_cols` list passed at train time | Cannot detect "this model was trained against a feature schema that no longer matches the current dataset" | Add explicit `feature_schema_hash`/`dataset_version` to the metadata dict |
| Model "owner" / decision threshold | Not tracked | — | **NOT IMPLEMENTED** | No accountable owner per model beyond `promoted_by` (who promoted, not who trained/owns) | — | Add `owner` field at training time |
| Prediction logging (model_version, timestamp, input schema, confidence) | Partial — `training_id` + timestamp real; input schema version and confidence are **not structured fields**, only whatever the caller happens to put in a free-form `metadata` dict | `dss/core/warehouse.py:279-300` | **PARTIAL** | Confidence/schema-version not guaranteed present or consistently named | Cannot reliably audit "what schema was this prediction made against" | Formalize the prediction record schema |
| Drift monitoring | None | — | **NOT IMPLEMENTED** | No baseline distribution capture, no statistical drift test anywhere in the codebase | Model degradation over time would go undetected | Phase 9, if prioritized — this is a substantial new subsystem, not a quick add |
| Auto-retrain / auto-promote | Explicitly disabled by design (`auto_promote` always `False` in every call site) | `dss/core/trainers.py`, `dss/tabs/ml_hub.py` | **IMPLEMENTED** (as "intentionally not automatic") | — | — | Correctly matches the user's own Phase 9 requirement — no change needed |

## 9. RAG pipeline

Two independent RAG paths exist:
- **Generic Knowledge Base** (`core/models.py::MultiAIProvider`, 19 hardcoded demo
  documents) — used by the general AI Advisor.
- **CMS-scoped Learning Explainer RAG** (`dss/services/cms_lecture_repository.py` +
  `dss/services/learning_explainer.py`) — real lecturer-uploaded content, filtered by
  course/lesson, with citation, insufficient-evidence honesty, and a 4-category source
  classifier (`dss/services/source_classification.py`).

Both are backed by `dss/services/vector_store.py`:

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| `LocalVectorStore` (active default) | Real: per-namespace NumPy array + JSON metadata, thread lock, atomic write, filter-in-`search()` (not overfetch-then-filter) | `dss/services/vector_store.py:52-227` | **IMPLEMENTED** (functionally correct) | **Loads the entire namespace's vectors into memory on init and does brute-force `cosine_similarity` over all of them on every `search()` call** (`vector_store.py`, `search()` method) — no ANN index (HNSW/IVF), no on-disk paging | Directly contradicts Phase 2's "Không load toàn bộ vector vào RAM để search khi dữ liệu lớn" at real scale (thousands of lecture chunks × many courses) | Phase 2: either implement `PgVectorStore` for real (pgvector + HNSW), or add an in-process ANN library (e.g. `faiss`/`hnswlib`) as an interim step |
| `PgVectorStore` | **Confirmed still a stub** (unchanged from earlier audit this engagement): `add_chunks()` returns `len(chunks)` with no `INSERT`; `search()`/`list_documents()` unconditionally return `[]`; `delete_document()` returns a bare bool with no `DELETE` executed. Real DDL schema (pgvector + HNSW index) exists and a real connection test runs, but no CRUD is wired | `dss/services/vector_store.py:230-315` | **STUB** | Silent data loss if anyone sets `PGVECTOR_URL` expecting it to work — `add_chunks` reports fake success | If a lecturer starts uploading real content believing it's persisted to Postgres, everything vanishes | Phase 2: implement real SQL for all 4 abstract methods |
| Chunk metadata fields (document_id, chunk_id, content, embedding, source, metadata, created_at, version) | Present for `document_id`/`chunk_id`/`content`/`embedding`/`metadata`; **no explicit `version` field on the chunk itself** (versioning exists one level up, at the CMS *lesson* level via `LessonVersion`, not the chunk/vector-store record) | `dss/services/chunking_service.py::DocumentChunk`, `dss/services/cms_lecture_repository.py::LessonVersion` | **PARTIAL** | Vector-store-level re-indexing/versioning (Phase 2's explicit ask) isn't tracked at the chunk layer | Re-embedding with a new model can't cleanly distinguish old vs. new vectors at the vector-store layer | Add a `version`/`embedding_model_version` field to `DocumentChunk` |
| Retrieval latency metrics | Not measured/logged | — | **NOT IMPLEMENTED** | No visibility into retrieval performance in production | — | Phase 12 (observability) |
| Deduplication | Not implemented in `LocalVectorStore.search()` | `dss/services/vector_store.py` | **NOT IMPLEMENTED** | Near-duplicate chunks (e.g. re-uploaded lecture versions) could both surface in top-k | Redundant/confusing citations | Add a simple content-hash or cosine-similarity dedup pass on results |

## 10. LLM Gateway

`core/models.py::MultiAIProvider.call_ai_provider()` — real multi-provider dispatch
(Gemini/Groq/OpenAI/HF-local/Ollama), `tenacity`-based retry for rate-limit (429) errors,
fallback chain logic exists in `dss/services/llm_gateway.py` (per earlier session
findings: semaphore-based concurrency gate + fallback to a clearly-labeled demo response
under REAL_LMS-gated conditions). `dss/services/token_tracker.py` (308 lines) — real
per-request `provider`/`model`/`input_tokens`/`output_tokens`/`estimated_cost`/`latency`
records, plus a pre-computed `MODEL_PRICING_PER_M` table.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Multi-provider dispatch | Real, 5 providers | `dss/core/models.py::call_ai_provider` | **IMPLEMENTED** | — | — | — |
| Retry (rate limit) | `tenacity`, provider-scoped | `dss/core/models.py` | **IMPLEMENTED** | — | — | — |
| Fallback chain | Real (semaphore-gated concurrency + fallback) | `dss/services/llm_gateway.py` | **PARTIAL** | Not verified this pass whether this is a true circuit-breaker (open/half-open/closed with automatic recovery probing) vs. a simpler semaphore+fallback — needs a dedicated re-read before claiming IMPLEMENTED | Under sustained provider outage, may not "reopen" automatically the way a real circuit breaker would | Re-audit `llm_gateway.py` in detail before Phase 11 work starts |
| Token/cost tracking | Real, per-request | `dss/services/token_tracker.py` | **IMPLEMENTED** | — | — | — |
| Timeout | Not confirmed this pass | `dss/core/models.py` | **UNVERIFIED** | — | — | Confirm explicit per-provider HTTP timeout exists before Phase 11 |

## 11. Subscription / entitlement

`dss/services/subscription_service.py` (176 lines) — single-organization subscription
record (`org_id`, `plan`, `status`, `expires_at`, `max_students`, `max_courses`,
`features_enabled`), a real `check_entitlement()`/`render_subscription_gate()` that blocks
non-Admin roles when `status` is `EXPIRED`/`SUSPENDED` or past `expires_at` (auto-flips to
EXPIRED). Confirmed via grep: `max_students` is **only displayed/editable** in
`dss/tabs/admin_settings.py` — never compared against an actual live student count
anywhere in the codebase.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Subscription status gate | Real (EXPIRED/SUSPENDED blocks access) | `dss/services/subscription_service.py:110-175` | **IMPLEMENTED** | — | — | — |
| `max_students` quota | Field exists, editable by Admin | `dss/tabs/admin_settings.py`, `subscription_service.py` | **STUB** (field only, never enforced) | No check anywhere blocks exceeding it | A university could exceed its contracted seat count with zero system awareness | Phase 6: add real usage count + enforcement at student-creation time |
| `max_ai_requests_month` | **Field does not exist** in the data model at all | — | **NOT IMPLEMENTED** | — | — | Add field + wire to `token_tracker.py`'s existing per-request records (the raw data to compute this already exists) |
| `max_storage` | **Field does not exist** | — | **NOT IMPLEMENTED** | — | — | Add field + compute from `data_warehouse/` disk usage |
| Usage tracking vs. quota | None | — | **NOT IMPLEMENTED** | — | — | Phase 6 |
| Payment gateway | None (correctly out of scope per user's own instruction) | — | **NOT IMPLEMENTED** (by design) | — | — | No action needed |

## 12. Logging / Audit

`dss/core/logging_config.py` — real rotating technical logger (ops/dev, explicitly
documents never logging passwords/API keys). `dss/core/warehouse.py::log_activity()` — real
user-facing activity history, but it is **not a security audit trail**: no
actor-vs-target distinction, no before/after diff capture. Confirmed via direct
inspection: `model_registry.py::promote()`/`rollback()` write `promoted_by`/
`promotion_reason` **only into that one model's own metadata JSON** — they never call
`log_activity()` or any other central log, so there is no queryable list of "who promoted
what, when" across the system. `dss/tabs/admin_settings.py`'s user-editing UI has zero
audit-log calls.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Technical/ops logging | Real, rotating, secret-safe | `dss/core/logging_config.py` | **IMPLEMENTED** | — | — | — |
| User-facing activity history | Real | `dss/core/warehouse.py::log_activity` | **IMPLEMENTED** (as activity history, not audit) | — | — | — |
| Security audit trail (who/action/target/timestamp/before/after) | Does not exist as a distinct concept | — | **NOT IMPLEMENTED** | Admin actions (user management, role changes, model promote/rollback) leave no centrally-queryable audit record | Cannot answer "who changed this and when" for compliance/incident response — required by Phase 4/8 | Phase 4: add a dedicated `audit_logs` store (JSON now, DB table in Phase 1) + call it from every Admin-gated mutation |

## 13. Docker / deployment

`Dockerfile` (root of `app/`, `FROM python:3.12-slim`) + `docker-compose.yml` +
`.dockerignore`. Compose defines a real healthcheck (`urllib.request.urlopen(.../
_stcore/health)`, 30s interval, 5 retries, 120s start period). No secrets baked into the
image — `.env` excluded via `.dockerignore`, keys come from host env/`.env` at runtime.
**Runs as root** (no `USER` directive). Compose bind-mounts live source
(`./dss:/app/dss`, `./data_warehouse:/app/data_warehouse`) — the built image's own copied
code is overridden at container start by the host filesystem, which is a dev/hot-reload
pattern, not a clean production deploy where the image is the immutable, self-contained
artifact.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Dockerfile | Real, builds | `Dockerfile` | **IMPLEMENTED** | Runs as root | Container breakout has full root inside the container | Add a non-root `USER` |
| Healthcheck | Real | `docker-compose.yml` | **IMPLEMENTED** | — | — | — |
| Secret handling in image | Correct (no secrets baked in) | `Dockerfile`, `.dockerignore` | **IMPLEMENTED** | — | — | — |
| Production-safe compose (no live-source bind mount) | Bind-mounts host source over the image | `docker-compose.yml` | **PARTIAL** (works, but is a dev-mode pattern) | Image content is not what actually runs; "what you tested in CI" ≠ "what runs in prod" | Deploy drift, since the running code is whatever's on the host disk, not what was built/scanned | Add a separate `docker-compose.prod.yml` without source bind mounts |

## 14. Tests

489 tests total (450 non-E2E + 39 E2E) as of the last completed engagement, all passing;
this pass's own fresh non-E2E re-run confirms 450/450 still green (202.6s). Extensive real
coverage: RBAC, RAG governance/citation/cross-course isolation, Learning Explainer,
Knowledge Base, search, data isolation (this session's own recent PERF-002 work), ML
training/prediction, Model Registry lifecycle. **IMPLEMENTED** — this is a genuine strength;
Phase 15 must not regress this.

## 15. Performance / load tests

`tests/load/test_lms_scale_load.py` — confirmed by direct inspection: **single-process,
single-threaded batch-inference benchmark**. It trains one `Ridge` model, builds a 20,000-row
synthetic `pandas.DataFrame`, calls `.predict()` once vectorized over all 20k rows, and
separately loops sequentially over 100-row chunks in the **same process** to compute
p50/p95/p99 timing and an `assert throughput_rps > 5000` threshold. **No threads, no
asyncio, no HTTP requests, no `locust`/`k6`, no simulated concurrent Streamlit sessions
anywhere in the repository.**

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Batch ML inference throughput test | Real, but narrow | `tests/load/test_lms_scale_load.py` | **IMPLEMENTED** (for what it actually is) | — | — | Rename to make its scope explicit (e.g. `test_batch_prediction_throughput.py`) so it stops being mistaken for a load test |
| Concurrent-user / RPS load test (login, dashboard, prediction, RAG, AI request under 10/50/100/250/500 simulated users) | **Does not exist** | — | **NOT IMPLEMENTED** | The project currently has zero evidence about real concurrent-session behavior | The user's own instruction is explicit: "Không được tuyên bố hệ thống support 20.000 concurrent users nếu chưa test" — this must be treated as **completely unproven** today, not "probably fine" | Phase 10: build with `locust` (recommended, Python-native) against a running `streamlit run` instance |

## 16. External integrations (SIS/LMS)

`dss/services/lms_connector.py` (474 lines) + `dss/core/lms_repository.py` (396 lines) —
`BaseLMSRepository` abstract interface, `DemoLMSRepository` (synthetic data generator),
`RealConnectorLMSRepository` which internally delegates to `SQLiteLMSRepository` (a
**local SQLite file**, not a network connection to any real external LMS/SIS such as
Moodle/Canvas/Blackboard/a university's own SIS). Confirmed via grep across both files:
**zero occurrences** of pagination, retry, exponential backoff, rate limiting, timeout, or
idempotency logic.

| Feature | Implementation | File | Status | Problem | Risk | Recommended fix |
|---|---|---|---|---|---|---|
| Connector abstraction (`BaseLMSRepository`) | Real interface | `dss/services/lms_connector.py`, `dss/core/lms_repository.py` | **IMPLEMENTED** (as an abstraction only) | — | — | Good foundation for Phase 3 |
| "Real" connector | Delegates to local SQLite, not any actual external system | `dss/services/lms_connector.py:397-405` | **STUB** (misleadingly named "Real") | Nothing in this codebase has ever talked to a real university SIS/LMS over a network | If presented as "LMS integration done," it would be a false claim | Phase 3: build one genuine reference connector (even against a mock server) with real HTTP, pagination, retry/backoff, idempotency |
| Sync robustness (pagination/retry/backoff/rate-limit/timeout/idempotency) | None found anywhere | — | **NOT IMPLEMENTED** | — | A real LMS sync without these will fail unpredictably and can silently duplicate/lose records | Phase 3, from scratch |

---

## Cross-cutting findings relevant to multiple later phases

- **Security — secret management**: sound pattern (`.env` via `python-dotenv`, real env
  vars always win, `.env` excluded from git/Docker), but plaintext-only — no vault/secrets
  manager. No hardcoded secrets found anywhere in `dss/` (verified by grep for common key
  patterns). **PARTIAL.**
- **Security — file upload validation**: `st.file_uploader(type=[...])` is a
  client-side-only extension allow-list. `dss/services/document_ingestion.py` dispatches
  purely on filename suffix, has **no size limit, no magic-byte content-type check**, and
  on a parse exception returns the **error string as if it were document content** rather
  than rejecting the file. **NOT IMPLEMENTED** as real validation — this is a genuine
  security/data-quality gap, prioritize early in Phase 8.
- **CI/CD**: confirmed, with a repo-wide search, that no `.github/workflows`,
  `.gitlab-ci.yml`, `azure-pipelines.yml`, or `Jenkinsfile` exists anywhere. **NOT
  IMPLEMENTED**, full stop.

## Summary status counts (16 requested areas)

| Status | Count | Areas |
|---|---|---|
| IMPLEMENTED | 8 | Runtime entry point, RBAC, Student/Lecturer/Admin flows, ML pipeline, Model Registry (lifecycle core), LocalVectorStore, LLM Gateway (dispatch/retry/tokens), Tests |
| PARTIAL | 5 | Architecture (monolith, no API boundary), Authentication (session portability), Storage layer (local-file only), Subscription quota (field-only), Logging (activity ≠ audit), Docker (root user + dev bind-mounts) |
| STUB | 2 | PgVectorStore, "Real" LMS connector |
| NOT IMPLEMENTED | 6 | PostgreSQL/migrations, drift monitoring, dedicated audit trail, real concurrent-load testing, CI/CD, file upload content validation |

*(Some areas appear in more than one bucket at sub-feature granularity — see the detailed
tables above for the authoritative per-feature status.)*
