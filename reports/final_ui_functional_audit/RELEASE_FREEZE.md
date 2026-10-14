# EduDSS — Release Freeze Record

**Freeze date/time:** 2026-09-16→17 (per this session's clock) — **superseded five times**:
(1) a scoped pre-defense hardening pass (KB-CRUD-001 delete + COLDSTART-001 UX), (2) a
UI/RAG consistency pass part 1 (4 verified UI bugs found and fixed: dark mode, sidebar
clipping, Model Registry timestamps, provider-health consistency), (3) a UI/RAG
consistency pass part 2 (global search rebuilt with RBAC; RAG source governance/
classification added), (4) a Learning Explainer performance optimization pass (PERF-001 —
eager-import removal), (5) a test/simulation data-isolation pass (PERF-002 — see dedicated
section below). See the dedicated sections below for what changed at each step.
**Status:** ACCEPTED — the test-isolation pass is closed and re-frozen. No further product
code changes are authorized against the new baseline below except to correct a factual
documentation inconsistency, and even then only after recording it here first.

## Final test baseline (CURRENT, post test/simulation isolation pass)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | **450 / 450 PASS** (444 pre-existing + 6 new isolation tests, zero regressions) |
| E2E (Playwright) | **39 / 39 PASS** (12m44s; 38 pre-existing + 1 new isolation test, zero regressions) |
| **TOTAL** | **489 / 489 PASS** |

## PRE-ISOLATION-PASS BASELINE (preserved for history)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | 444 / 444 PASS |
| E2E (Playwright) | 38 / 38 PASS (16m34s) |
| **TOTAL** | **482 / 482 PASS** |

This was the baseline going into the test/simulation data-isolation pass (PERF-002) — this
pass added 6 new non-E2E tests (`tests/test_data_isolation.py`) and 1 new E2E test
(`tests/e2e/test_data_isolation_e2e.py`) that did not exist before, so the totals increase
honestly rather than staying flat.

## PRE-PERFORMANCE-PASS BASELINE (preserved for history)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | 444 / 444 PASS |
| E2E (Playwright) | 38 / 38 PASS (19m10s) |
| **TOTAL** | **482 / 482 PASS** |

This was the baseline going into the Learning Explainer performance optimization pass
(PERF-001) — no tests were added or removed by that pass (it was a latency fix, not a
feature change), so the non-E2E and E2E counts stayed flat at 482/482.

## PRE-HARDENING BASELINE (preserved for history — no longer the release baseline)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | 403 / 403 PASS |
| E2E (Playwright) | 23 / 23 PASS (10m18s) |
| **TOTAL** | **426 / 426 PASS** |

This was the accepted baseline from the architecture-accuracy + product-acceptance audit,
frozen earlier on 2026-09-16. It is kept here unmodified as a historical record — it is
**not** erased.

## POST-HARDENING / PRE-UI-PASS BASELINE (preserved for history)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | 417 / 417 PASS |
| E2E (Playwright) | 28 / 28 PASS (14m17s) |
| **TOTAL** | **445 / 445 PASS** |

This was the baseline after the KB-CRUD-001/COLDSTART-001 hardening pass, before the UI/RAG
consistency pass (part 1) added 3 more E2E tests (dark mode, sidebar clipping, provider
health consistency) with zero regressions.

## POST-UI-PASS-1 / PRE-UI-PASS-2 BASELINE (preserved for history)

| Suite | Result |
|---|---|
| Non-E2E (pytest) | 417 / 417 PASS |
| E2E (Playwright) | 31 / 31 PASS (16m51s) |
| **TOTAL** | **448 / 448 PASS** |

This was the baseline after UI/RAG consistency pass part 1, before part 2 (search + RAG
source governance) added 27 non-E2E tests + 7 E2E tests with zero regressions to reach the
current 482/482.

## Pre-defense hardening pass (2026-09-16, scoped to exactly 2 items)

Two items only were authorized and implemented — no other product code was touched:

1. **`KB-CRUD-001` (partial fix)** — Knowledge Base document deletion is now real and
   guarded, for the active backend only. New service
   `dss/services/knowledge_base_admin.py::delete_document_safely()`:
   - Traces the *actual* runtime vector store (`vector_store.get_vector_store()`), not an
     assumption.
   - Refuses to trust `PgVectorStore.delete_document()`'s return value — that method is
     still a stub (`return True` with no real SQL, per `ARCH-PGVECTOR-001`, confirmed again
     this pass) — and reports `"unsupported"` honestly instead of a fabricated success.
   - Blocks deletion when the document is the current version of a live CMS lesson (would
     otherwise silently break Learning Explainer citations), directing the Admin to the
     existing `cms_lecture_repository.exclude_document()` version-exclusion mechanism.
   - Is `@require_role("Admin")`-gated at the service layer (defense-in-depth on top of the
     existing nav-level restriction).
   - UI: `dss/tabs/knowledge_base.py` adds a compact "select document → Xóa tài liệu" action
     plus an `st.dialog` confirmation ("Xóa tài liệu "..."? ... không thể hoàn tác" /
     Hủy / Xóa tài liệu). Success/error/unsupported/blocked states are shown honestly —
     no fabricated success message.
   - Still **PARTIAL CRUD**: Update remains unimplemented (unchanged, out of scope).
   - Verification: 14 new unit tests + 2 new E2E tests, all passing (see
     `tests/test_kb_delete_and_coldstart_ux.py`, `tests/e2e/test_kb_delete_and_coldstart_e2e.py`).

2. **`COLDSTART-001` (PARTIAL — UX FIXED / LATENCY REMAINS)** — Root cause was *measured*,
   not assumed: the expensive step is `dss.config._ensure_local_llm_libs()` (first-time
   import of `torch`/`transformers`/`sentence-transformers` in the process, ~22s measured)
   followed by `SentenceTransformer(...)` instantiation (~5s measured), both already lazily
   deferred to the first embedding-consuming call by existing design (not this pass). Per
   explicit scope instruction, the latency itself was **not** touched:
   - No pre-warming was added at bootstrap/login (would trade Learning-Explainer-specific
     latency for whole-app startup latency affecting every role — rejected by design).
   - The existing `@st.cache_resource` on `load_embedding_model` already prevents repeat
     cost within a server process — no caching change was needed or made.
   - What changed: every spinner on the cold-start path (student chat, supplementary
     explanation, quiz generation — which previously had **no spinner at all** — lecturer
     upload, Admin Knowledge Base upload) now shows an explicit "first time may take about
     1 minute, the app is not frozen" message via a new
     `dss.tabs.ui_kit.cold_start_aware_message()` helper, shown only while the embedding
     model has not yet loaded in this process (checked via `llm_integration.embedding_model`).
   - The quiz-generation button's `retrieve_lesson_content()` call, which previously had no
     error handling, now has a try/except with a friendly error message on failure.
   - Verification: 10 new unit tests for the message helper + 2 new E2E tests confirming
     Learning Explainer still renders without a traceback for both Giảng viên and Sinh
     viên after the change. **Latency was not re-measured as improved — it is unchanged
     by design.**

Explicitly **not** touched this pass (remain documented limitations/future work):
`PgVectorStore` SQL CRUD, Admin User Management CRUD, real LMS integration, real CMS
integration, multi-tenancy, Redis rate limiting, model drift, A/B testing, observability
stack, at-rest encryption, load-test architecture changes, new ML algorithms, new AI
providers.

## UI/RAG consistency pass (2026-09-16) — 4 real bugs found and fixed, several reported items not reproducible

Requested against a large (49-point) list of UI/UX complaints. Per explicit instruction,
every item was reproduced directly in the running app with Playwright before any code was
touched — no screenshots were available from the requester for this pass. See
`FINAL_UI_FUNCTIONAL_AUDIT.md` §6.6 for full detail. Summary:

**Fixed (4 real, root-caused bugs — see `ISSUE_REGISTER.csv`: `UI-DARKMODE-001`,
`UI-SIDEBAR-CLIP-001`, `UI-AISTATUS-001`, `UI-REGISTRY-TS-001`):**
1. Dark mode text was unreadable on metric cards — root cause was
   `-webkit-text-fill-color` (which wins over `color` in Chromium) never being touched by
   the dark-mode CSS. Fixed via proper semantic-token redefinition + a `currentColor`
   failsafe, and `ui_kit.metric_card()` converted to use the token-aware CSS classes.
2. Sidebar section titles were clipped at the top in both themes — root cause was
   Streamlit's own element-wrapper computing a too-small `overflow:hidden auto` box for a
   larger custom title. Fixed with a targeted `overflow:visible` override.
3. AI provider health status was contradictory between the "Trợ lý AI" summary panel and
   the "Cấu hình AI" real test page — the summary panel inferred "Sẵn sàng" from API-key-
   configured flags instead of an actual health check. Fixed by making both panels read
   the same cached `llm_gateway.check_provider_health()` result; Hugging Face (embedding
   library) was also visually separated from the LLM provider row, since it is a different
   concern (embedding readiness ≠ LLM readiness).
4. Model Registry's "Huấn luyện lúc" column showed raw ISO timestamps — fixed with a
   `dd/mm/yyyy HH:MM` formatting helper.

**Investigated, found NOT reproducible against the current codebase** (most likely already
fixed in an earlier phase of this engagement): duplicate "EduDSS" sidebar branding block;
"Dùng dữ liệu mẫu mặc định" button "doing nothing" (live-tested end to end, works
correctly — only nuance found was a single-render-lifetime success toast); raw Python
list `repr()`/literal "Mục tiêu:" prefix in the EDA preprocessing table (code already
strips it correctly); Model Registry "no explanation of purpose" (the explanatory text and
lifecycle caption already exist verbatim); non-bold navigation button text (already
`font-weight:650` consistently).

**Not attempted this pass** (out of scope for what was verified and fixed; tracked as
future work, not silently dropped): the RAG source-priority/Knowledge-Base-reclassification
portion of the request (Sections 19–25/38–40 of the original request) and the global-search
UX/RBAC redesign portion (Sections 12–15). The existing architecture already gives Learning
Explainer exclusive priority to lecturer-uploaded CMS content over the generic Knowledge
Base (verified in an earlier phase), but no new source-classification labeling or search
redesign was added here.

**Tests:** 3 new E2E tests (`tests/e2e/test_ui_dark_mode_and_provider_health_e2e.py`) using
computed-style/live-data assertions (not screenshot diffing). Full regression: 417/417
non-E2E, 31/31 E2E (16m51s), zero regressions — new baseline at that point was 448/448.

## UI/RAG consistency pass, part 2 (2026-09-16) — global search + RAG source governance

Completed the two items explicitly left unfinished by part 1: global search RBAC/UX, and
RAG source governance. See `FINAL_UI_FUNCTIONAL_AUDIT.md` §6.8 and `ISSUE_REGISTER.csv`
(`UI-SEARCH-001`, `UI-RAGGOV-001`) for full detail.

**Part A — Search (`dss/services/search_service.py`, new):**
- RBAC enforced before any result is computed — Sinh viên never even sees the search input;
  Giảng viên now has the same search capability as Admin (matching their existing
  full-class dataset visibility elsewhere, not a new permission).
- Exact-match-first, case-insensitive partial match, capped at 5 results, humanized metric
  labels (reusing `feature_label()`), honest empty state.
- Real navigation: "Xem phân tích" pre-selects the found student in the existing Trợ lý AI
  tab's student selectbox (via `session_state["llm_student_select"]`, which Streamlit
  honors as the widget's initial value) and jumps there via the existing
  `_pending_nav_target` mechanism — verified this genuinely pre-selects the student, not
  just a page revisit. No "Xem hồ sơ"/"Xem chẩn đoán"/"Xem khuyến nghị" buttons were added
  as separate destinations, since no separate pages for them exist — fabricating those
  would have been dead buttons.
- Verified at 1920×1080, 1440×900, 1366×768 — results render full-width below the top bar,
  not overlapping theme/notifications/profile controls.

**Part B — RAG source governance (`dss/services/source_classification.py`, new):**
- Centralized classifier: `COURSE_MATERIAL` (Tài liệu môn học), `INSTITUTION_APPROVED`
  (Tài liệu được phê duyệt — defined but intentionally never populated, no real approval
  workflow exists), `SUPPLEMENTARY_REFERENCE` (Nguồn tham khảo bổ sung — the 4/19 demo
  documents with real academic references: Pomodoro/Feynman/Krashen/Cornell), `DEMO`
  (Dữ liệu demo — the other 15/19). Classification derives strictly from provenance
  metadata already present in the system, never from document text content.
- **Confirmed by re-reading, not rebuilt:** Learning Explainer's retrieval already
  exclusively uses CMS/course content filtered by course/lesson, with an honest
  insufficient-evidence response and zero citations when nothing matches — it never falls
  back to the generic 19-document Knowledge Base. This was already correct from an earlier
  phase; now covered by dedicated regression tests
  (`tests/test_rag_source_governance.py`) so it cannot silently regress.
- `dss/tabs/knowledge_base.py`: new Admin breakdown KPI row (course material /
  supplementary reference / demo counts, never merged into one total), a new read-only
  "Tài liệu môn học (CMS)" tab listing real lecturer-uploaded lessons, and the demo tab now
  shows a source-category column and replaces the old GEN_REF free text with an honest
  "Nguồn: Dữ liệu demo nội bộ" presentation for demo-classified documents.
- Citation format extended to include course context; still never exposes
  chunk_id/vector_id/namespace_id/embedding_id.
- **No external LMS or CMS connector was built or implied.** Both remain honestly
  `NOT IMPLEMENTED`.

**Tests:** 12 new unit tests (`tests/test_search_service.py`), 10 new unit tests
(`tests/test_source_classification.py`), 5 new integration tests with the real embedding
model (`tests/test_rag_source_governance.py`), 7 new E2E tests
(`tests/e2e/test_search_and_rag_governance_e2e.py`). Full regression: 444/444 non-E2E,
38/38 E2E (19m10s), zero regressions — **new baseline 482/482**.

## Learning Explainer performance optimization pass (2026-09-17)

Goal: reduce real cold/warm load time without changing product behavior — explicitly not
just "add another spinner." Full detail in `ISSUE_REGISTER.csv::PERF-001`/`PERF-002` and
`reports/performance_optimization/PERFORMANCE_BEFORE.md` /`PERFORMANCE_COMPARISON.md`.

- **Profiled first** with dev-only timing instrumentation (`dss_config.perf_mark`, gated
  by `EDUDSS_PERF_DEBUG`, never active in production) before changing any code.
- **Root cause was NOT primarily torch/transformers import**, contrary to this pass's own
  initial hypothesis: instrumentation showed the previously-reported ~60-96s Learning
  Explainer cold open (Admin/Lecturer view) was dominated by (a) two unconditional
  `dss_config._ensure_local_llm_libs()` call sites that paid the full heavy-import cost
  just to display package-installed status on pages not using embeddings
  (`admin_reports.py:199`, `ai_advisor.py:393`), and (b) an unconditional per-item
  widget-render loop over 743 accumulated automated-test lesson records + 176 test
  quiz-queue items in the shared dev `data_warehouse/cms/*.json` stores (Streamlit's
  `st.tabs()` renders every tab body on every rerun regardless of visible selection) —
  the latter was the larger of the two by far.
- **Fixes applied:** (1) both eager call sites now use the already-existing cheap
  `dss_config.HF_AVAILABLE` (`find_spec`) flag instead of forcing a real import — the real
  import remains exactly where it was already correctly gated
  (`core/models.py::load_embedding_model()`/`call_ai_provider()`'s `huggingface` branch);
  (2) the 741 test-fixture lesson/quiz records were removed from the live JSON stores
  (2 genuine CS301 demo lessons kept; full backup retained), with explicit user
  confirmation obtained before each destructive step.
- **Verified NOT already broken / no fix needed:** single shared `MultiAIProvider`
  instance (`@st.cache_resource` on `init_trainers_and_warehouse()`), single shared
  embedding-model cache (`@st.cache_resource` with `_self`-prefixed arg on
  `load_embedding_model()`) — Sections 4/6 of the optimization spec were already
  satisfied by the existing architecture; confirmed via instrumentation that
  `_ensure_local_llm_libs()` fires exactly once per process across every measured run.
- **Remaining, accepted limitation:** the first-ever embedding-consuming action in a
  fresh process (e.g. a student's first question) still pays a real torch/transformers
  import (measured 7–16s) plus external LLM provider latency — measured, not fabricated,
  and explicitly out of scope to eliminate this pass (would require model
  replacement/quantization/pre-warming, excluded by the pass's own stop condition).
  `COLDSTART-001` is updated to **PARTIAL — UX fixed and warm path optimized; first
  process cold import remains** (not marked fully FIXED).
- **No RAG governance, RBAC, or AI-provider-health regressions** — all pre-existing
  targeted tests re-verified green; no PgVectorStore work; no new AI provider; no model
  replacement.

**Tests:** no new test files (latency/data-hygiene fix, not a feature change). Full
regression: 444/444 non-E2E (unchanged), E2E re-verified (see baseline table above) —
**PRE-OPTIMIZATION baseline was 482/482**.

## Test/simulation data-isolation pass (PERF-002, 2026-09-17)

Follow-up to the performance pass above: the user pointed out that CMS lessons cleaned to
2 → full test suite run → grew back to 54, proving test isolation was fundamentally broken,
not just a one-time cleanup problem. Goal: make it structurally impossible for automated
tests to write into the live `data_warehouse/` again — isolation must prevent pollution
before it occurs, not clean it up by prefix afterward. Full detail in
`ISSUE_REGISTER.csv::PERF-002`.

- **Root cause:** every one of the app's ~13 mutable persistent stores (CMS lesson
  registry, quiz queue, interaction log, misconception records, users.json,
  ai_default_provider.json, subscription.json, ai_token_usage.json, technical logs,
  `LocalVectorStore`, `DataWarehouse`'s dataset/model/training-history directories,
  `RealConnectorLMSRepository`'s SQLite db) resolved its path via a **module-level
  constant** computed once at import time (`Path(__file__)`-relative, or a bare
  `'data_warehouse'` string relative to process CWD) — there was no way for any test to
  redirect these writes, and the 2 pre-existing opt-in fixtures
  (`isolated_users_file`/`isolated_default_provider_file`) covered only 2 of the ~13 real
  stores, and only for tests that explicitly requested them.
- **Architecture fix:** new `dss/core/data_root.py::get_data_root()` — the single
  centralized resolver (`EDUDSS_DATA_ROOT` env var if set, else the real `data_warehouse/`
  — default behavior for real users is byte-for-byte unchanged). All ~13 stores converted
  from module-level constants to functions / lazy-evaluated `__init__` defaults that call
  `get_data_root()` **at the point of use**, so setting the env var late is always honored
  — no scattered `if pytest`/`if TEST_COURSE` guards anywhere in application code.
- **pytest side:** `tests/conftest.py` gained an autouse, session-scoped fixture
  (`_isolated_data_root`) that points `EDUDSS_DATA_ROOT` at a fresh temp dir before the
  first test runs — every test is isolated automatically, no per-test opt-in needed. A
  second autouse fixture (`_pollution_guard`, Section 14's permanent regression guard)
  snapshots the REAL `data_warehouse/` (specific JSON file hashes + directory file
  listings, read via a hardcoded path independent of the env var) before the session and
  asserts byte-for-byte equality after — fails the whole suite by name of the exact store
  touched if PERF-002 ever recurs.
- **E2E side (the deeper gap):** `tests/e2e/conftest.py::base_url()` spawns a real
  Streamlit subprocess — it previously inherited the pytest process's own environment
  verbatim, so even a fully-isolated pytest process still drove a SERVER that wrote to the
  real store via the browser. Fixed: `base_url()` now creates its own separate temp dir and
  passes `EDUDSS_DATA_ROOT` via `subprocess.Popen(env=...)` specifically to that subprocess.
  Two follow-on bugs found and fixed during verification: `seeded_kb_document` and 2 test
  bodies in `test_kb_delete_and_coldstart_e2e.py` instantiated `LocalVectorStore()` directly
  in the pytest process (which now has its OWN separate isolated root from the subprocess),
  making seeded/verified documents invisible to the server — fixed by passing
  `base_dir=e2e_test_data_root` explicitly.
- **Data cleanup:** the 741 pre-existing test-fixture CMS records (regrown from 2 to 54
  since the last cleanup, exactly as the user's own observation predicted) were removed
  once more (same category: `TEST_COURSE_*`/`GOV_*`; 2 genuine CS301 lessons kept; full
  backup retained) — this time it will not regrow, since new pollution is structurally
  prevented.
- **Explicitly NOT cleaned (documented, not fixed):** `data_warehouse/{datasets,models,
  training_data,evaluation_data,metadata,history}` — hash-named files with no field
  distinguishing test-run origin from legitimate demo origin; deleting the wrong one risks
  destroying the live Model Registry's production model. See
  `ISSUE_REGISTER.csv::PERF-002-DATASETS-NOTE`.
- **Verification (Section 9/10/11 executed literally, not merely asserted):** real
  `data_warehouse/` snapshotted before/after the full non-E2E suite — compared
  byte-for-byte **IDENTICAL**. Full E2E suite (39/39) passed clean with the pollution guard
  green (verified in a run with no concurrent manual server activity). Section 11
  smoke-check: real dev server started with no `EDUDSS_DATA_ROOT` override, confirmed
  login, Admin home, Model Registry, and Learning Explainer all render normally and still
  show the genuine CS301/K-Means demo lesson. Section 12 re-measurement: Admin/Lecturer
  Learning Explainer cold open 13.1s, warm re-open 5.2s — unchanged from the PERF-001 fix,
  confirming the isolation refactor introduced no performance regression.
- **No RAG governance, RBAC, AI-provider-health, ML algorithm, or PgVectorStore changes.**

**Tests:** 6 new unit tests (`tests/test_data_isolation.py`), 1 new E2E test
(`tests/e2e/test_data_isolation_e2e.py`). Full regression: 450/450 non-E2E (444+6), 39/39
E2E (38+1) — **new baseline 489/489**. `PERF-002` marked **FIXED** (not partial) — both the
non-E2E and E2E paths were proven, not just asserted, to leave the real store untouched.

## Application entry point

- `run_dss.py` (Streamlit entry point at the project root of `app/`)
- Runtime: `streamlit run run_dss.py`

## Environment

- **Python:** 3.12.4 (project virtualenv: `d:/KLTN/code/.venv`)
- **Canonical dependency manifest:** `app/requirements.txt` (the only file kept up to date;
  `app/dss/requirements.txt` is explicitly marked as a legacy duplicate pointing back to this one)
- **Key dependency versions** (from `app/requirements.txt`):
  - `streamlit==1.52.2`
  - `scikit-learn==1.8.0`
  - `xgboost==3.1.2`
  - `lightgbm==4.6.0`
  - `imbalanced-learn==0.14.1`
  - `sentence-transformers==5.2.0`
  - `psycopg2-binary>=2.9`
- **Environment mode variable:** `EDUDSS_MODE`, read via `os.environ.get("EDUDSS_MODE",
  "DEMO_SYNTHETIC")`. Values: `DEMO_SYNTHETIC` (default — dev/test, synthetic data and internal
  demo tools allowed), `REAL_LMS` (production-like — all demo/synthetic paths gated off, honest
  unavailable states shown instead), `LOCAL_OFFLINE` (offline AI provider chain for local-only
  operation).

## Active storage mechanisms (see `THESIS_DEFENSE_TRUTH_TABLE.md` §1 and
`FINAL_ARCHITECTURE_TRUTH.md` for full detail)

| Data | Mechanism | Status |
|---|---|---|
| RAG vectors (active) | `LocalVectorStore` — file-based (NumPy + JSON) | Real, functional |
| RAG vectors (dormant) | `PgVectorStore` — PostgreSQL + pgvector | Connection + DDL schema real; CRUD methods are stubs — **not functional**, not activated in this deployment |
| Datasets, models, model registry, consultations, activity logs, users, organizations/subscription | File-based (JSON/CSV/joblib under `data_warehouse/`) | Real, functional |

## AI providers / configuration status

- Supported providers: Google Gemini, Groq, OpenAI, Ollama (local), plus an internal
  rule-based "Demo Mode" fallback (now gated out of `REAL_LMS`, see below).
- Provider routing/retry/concurrency: `dss/services/llm_gateway.py` — single retry layer
  (Tenacity, in `core/models.py`), a `threading.Semaphore(MAX_CONCURRENT_REQUESTS)` limiting
  concurrent AI calls, and a documented fallback cascade (Primary → Secondary → Ollama → Demo).
- `MAX_CONCURRENT_REQUESTS = 3` (config-driven constant, not load-tested).
- In `REAL_LMS` mode, all fabricated-content fallback paths (concurrency timeout, provider
  exhaustion) now yield an honest unavailable/overloaded message instead (`DEMO-CONCURRENCY-001`,
  fixed).

## ML algorithms currently available

- **Classification:** Logistic Regression (Softmax), Random Forest Classifier, XGBoost
  Classifier, LightGBM Classifier.
- **Regression:** Linear Regression, Random Forest Regressor, XGBoost Regressor, LightGBM
  Regressor.
- **Clustering:** K-Means (with Elbow/Silhouette-assisted k selection, PCA for visualization).
- Exact grids/fit counts are in `THESIS_FORMULA_SHEET.md` and `FINAL_SYSTEM_CAPABILITY_MATRIX.csv`.

## Model Registry lifecycle

`candidate` → (Admin-gated `promote()`) → `production` → (superseded by a later promotion) →
`archived`. Training never auto-promotes (verified: the real training call site explicitly
passes `auto_promote=False`). Bootstrap/login never auto-trains (verified: it only reuses an
existing Production model if one exists; otherwise does nothing and logs that it deliberately
skipped training).

## Known external-integration limitations

- **No real external LMS connector** — the "Real Connector" class internally delegates to the
  demo repository; only the abstraction/repository layer is real.
- **No real external CMS connector** — the internal lecture-content repository (upload → ingest
  → retrieve → cite) is real and fully working, but it is not a connector to an external CMS
  platform.

## Open/partial issues after the hardening pass (see `ISSUE_REGISTER.csv` for full detail)

| ID | Summary | Status |
|---|---|---|
| `ARCH-PGVECTOR-001` | `PgVectorStore`'s CRUD methods are stubs | OPEN — implementing real SQL operations is a feature addition, not a bug fix; explicitly out of scope this pass |
| `KB-CRUD-001` | Knowledge Base CRUD | **PARTIALLY FIXED 2026-09-16** — Delete is now real (LocalVectorStore) and guarded; Update still has no UI (needs a design decision on what "edit" means for already-embedded content) |
| `ADMIN-USER-001` | Admin User Management is read-only | OPEN — full CRUD requires prior architecture decisions (auth ownership, org isolation, audit logging) explicitly out of scope to invent |
| `COLDSTART-001` | ~55-96s cold-start delay on first embedding-consuming access / Learning Explainer open | **PARTIAL — UX FIXED AND WARM PATH OPTIMIZED; FIRST PROCESS COLD IMPORT REMAINS (2026-09-17)** — Admin/Lecturer cold open reduced 60.5-96.5s → 12.9s (root cause was eager import call sites + test-data accumulation, not primarily ML); genuinely-first embedding action (student's first question) still pays a real ~7-16s torch/transformers import by design, out of scope to eliminate this pass |
| `PERF-001` | Two eager `_ensure_local_llm_libs()` call sites on pages not using embeddings | **FIXED 2026-09-17** — see performance optimization pass section above |
| `PERF-002` | Test data isolation was fundamentally broken (all ~13 mutable stores resolved paths via module-level constants, no way to redirect) | **FIXED 2026-09-17** — centralized `get_data_root()` resolver + autouse pytest isolation + E2E subprocess isolation + permanent pollution guard; see test/simulation data-isolation pass section above |
| `PERF-002-DATASETS-NOTE` | Hash-named dataset/model/training-history files accumulated across the engagement, can't be safely classified test-vs-demo | NOT FIXED, documented limitation by design — see `ISSUE_REGISTER.csv` |

## Production-readiness limitations (summary — see `FINAL_UI_FUNCTIONAL_AUDIT.md` §7 for the full
subsystem-by-subsystem verdict)

- Concurrency capacity has never been load-tested; `3` is a configured default, not a measured
  optimum.
- No real institutional dataset has been used — all data is synthetic/seeded (see
  `THESIS_DEFENSE_TRUTH_TABLE.md` and the Data Provenance section of this defense package).
- LMS/CMS external integration is architecture-ready but not connected.
- Authentication is a simplified PBKDF2-HMAC-SHA256 username/password mechanism appropriate to
  project scale, not an enterprise identity provider.

## Explicitly excluded from this record

No API keys, secrets, tokens, passwords, or webhook credentials are recorded in this document or
any other file in this defense package.
