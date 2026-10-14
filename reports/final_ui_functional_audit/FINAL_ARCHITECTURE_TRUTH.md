# EduDSS — Final Architecture Truth Map

This document is the single authoritative layer-by-layer architecture reference for
thesis defense. It supersedes any older architecture description in
`SYSTEM_TECHNICAL_HANDBOOK.md` or `Bao_cao_phan_tich_he_thong_DSS.docx` wherever they
conflict — those are prior-phase documents and are treated as **STALE / SUPERSEDED** on
any point this document contradicts them (see priority-of-truth rule in
`RELEASE_FREEZE.md`).

Classification legend used throughout:
- **IMPLEMENTED** — real code, real data flow, runtime-verified.
- **PARTIAL** — some real code path exists, but part of the feature is a stub, disabled,
  or read-only where full CRUD would be expected.
- **ABSTRACTION ONLY** — a real interface/class hierarchy exists so a real implementation
  can be plugged in later, but the current concrete implementation underneath it is not a
  real external connection.
- **NOT IMPLEMENTED** — does not exist in code; explicitly and honestly absent.
- **EXTERNAL DEPENDENCY** — correctness depends on a third-party service outside this
  codebase (an LLM provider API).

## Layer 1 — UI (Streamlit tabs, `dss/tabs/*.py`, `dss/main.py`)

**Status: IMPLEMENTED.** Single Streamlit process, single `main.py` dispatcher, `ALL_TABS`
constant confirmed 1:1 with dispatch branches (no orphaned tabs, no missing routes,
verified by prior repo-wide grep). Two-layer RBAC: nav-level (`TAB_ACCESS` filters the
sidebar) + function-level (`@require_role(...)` decorator checked against
`st.session_state["_auth_role"]`, set only by the real login gate). Shared design-system
components (`dss/ui_kit.py`) used across all 3 roles' pages, verified by
`DESIGN_SYSTEM_ADOPTION_MATRIX.md` (16-page survey).

## Layer 2 — Services (`dss/services/*.py`)

**Status: IMPLEMENTED**, with named exceptions below. Each service is a plain Python
module invoked directly from tabs — no message bus, no async task queue, no separate
process. Services covered: `auth_service`, `diagnosis_engine` (rule-based), `learning_plan`
(rule-based generator + LLM narration), `career_scoring`, `clustering_service`,
`rag_service`, `document_ingestion`, `citation_service`, `vector_store`
(`LocalVectorStore` real / `PgVectorStore` PARTIAL, see Layer 6), `llm_gateway`,
`privacy_service`, `prompt_security`, `context_budget`, `token_tracker`,
`lms_connector` (ABSTRACTION ONLY, see Layer 7), `cms_lecture_repository` (IMPLEMENTED,
internal only), `model_registry`, `subscription_service`.

## Layer 3 — DSS Orchestration (per-request business logic, not a separate service)

**Status: IMPLEMENTED as direct function calls, NOT as a formal pipeline/DAG framework.**
There is no Airflow/Prefect/state-machine library orchestrating steps — a tab handler
calls diagnosis → recommendation → learning plan generation in a straight-line sequence
within the same Streamlit script run. This is intentional simplicity appropriate to the
project's scale, not a hidden limitation, but must be described accurately: "the DSS
pipeline is a direct function-call sequence within one Streamlit run," not "a distributed
orchestration pipeline."

## Layer 4 — ML (`dss/core/trainers.py`, `dss/core/models.py`, `dss/services/model_service.py`)

**Status: IMPLEMENTED.** Real `GridSearchCV`-tuned scikit-learn/XGBoost/LightGBM models
for classification and regression (exact grids in `THESIS_FORMULA_SHEET.md`), real
`KMeans` clustering, real SHAP explanation. Anti-leakage discipline confirmed by direct
code read: `train_test_split` runs BEFORE any preprocessing; `KNNImputer` /
`StandardScaler` / `OneHotEncoder` / `SMOTE` are wrapped inside a pipeline that is fit
only inside `GridSearchCV`'s internal CV folds (training data only); a separate explicit
`filter_leakage_features()` guard removes target-correlated columns before training even
starts.

**Exception:** the Classification `XGBoost` path skips `GridSearchCV` entirely (see ML
truth / formula sheet) — a single fixed-parameter fit, documented workaround for a
label-contiguity crash on rare multi-class CV folds. This is IMPLEMENTED but with reduced
tuning depth relative to the other 3 classification algorithms — must be stated plainly,
not blended into "all 4 algorithms are tuned identically."

## Layer 5 — AI / RAG (`dss/services/llm_gateway.py`, `dss/services/rag_service.py`, `dss/core/models.py`)

**Status: IMPLEMENTED** for the core pipeline (ingest → chunk → embed → retrieve →
threshold-filter → prompt → cite), **EXTERNAL DEPENDENCY** for actual generation quality
(Gemini/Groq/OpenAI/Ollama). Real per-provider health checks, real retry (Tenacity, single
layer), real `threading.Semaphore(MAX_CONCURRENT_REQUESTS=3)` concurrency limit, real
honest-failure behavior in `REAL_LMS` mode (no fabricated fallback text). RAG thresholds
are real config constants: `RAG_TOP_K_DEFAULT=5`, `RAG_RELATIVE_THRESHOLD=0.85`,
`RAG_LOW_CONFIDENCE_FLOOR=0.55`; below-floor retrieval yields an honest
NO_RELEVANT_EVIDENCE response rather than a forced weak citation.

**Update (2026-09-16, UI/RAG consistency pass, `UI-AISTATUS-001`):** the real
`llm_gateway.check_provider_health()` resolver (with its normalized
`PROVIDER_HEALTH_FRIENDLY_LABEL` mapping) was already a correct single-source-of-truth
design, but a second, uncoordinated status computation existed in the "Trợ lý AI" tab's
summary panel that inferred "Sẵn sàng" purely from API-key-configured flags — able to
show a provider as healthy while the real health-check page showed it failing (e.g.
billing exhausted). Fixed by making the summary panel consume the same cached health-check
result. This is now genuinely one resolver, read from two places, not two resolvers.

**Update (2026-09-16, RAG source governance, `UI-RAGGOV-001`):** confirmed by re-reading
(not by rebuilding) that the Learning Explainer retrieval path
(`cms_lecture_repository.retrieve_lesson_content`, called from
`learning_explainer.generate_explanation`) is architecturally separate from, and never
falls back to, the generic 19-document Knowledge Base used by the "Trợ lý AI"/"Cấu hình
AI" pages (`core/models.py::MultiAIProvider.knowledge_base` via `rag_service`). This
means Student-facing course questions are already grounded exclusively in
lecturer-uploaded CMS content, with an honest "not found in course material" response and
zero citations when none matches — this was true before this pass and is now covered by
dedicated regression tests (`tests/test_rag_source_governance.py`) so it cannot silently
regress. A new centralized classifier (`dss/services/source_classification.py`) labels
every document as `COURSE_MATERIAL` / `SUPPLEMENTARY_REFERENCE` / `DEMO` (never
`INSTITUTION_APPROVED`, since no real institutional approval workflow exists), derived
strictly from provenance metadata already present in the system, and this breakdown is now
surfaced to Admin in `dss/tabs/knowledge_base.py`.

## Layer 6 — Repository / Storage (`dss/core/warehouse.py`, `dss/services/vector_store.py`)

**Status: PARTIAL**, and this is the single most important precision point in the whole
defense package.

| Data | Active mechanism | Status |
|---|---|---|
| Datasets, trained model artifacts, model registry metadata, consultations, activity logs, users, org/subscription records | File-based JSON/CSV/joblib under `data_warehouse/` | **IMPLEMENTED**, real, durable, SHA-256 artifact integrity checked |
| RAG vectors (the one actually used at runtime) | `LocalVectorStore` — NumPy arrays + JSON metadata files, no database server | **IMPLEMENTED** |
| RAG vectors via PostgreSQL + pgvector | `PgVectorStore` | **PARTIAL** — real psycopg2 connection test and real DDL (pgvector extension, HNSW index) exist, but all 4 CRUD methods (`add_chunks`, `search`, `list_documents`, `delete_document`) are stub implementations that do not execute real SQL. `get_vector_store()` only ever returns `PgVectorStore` if `PGVECTOR_URL`/`DATABASE_URL` env vars are set — they are not set in this deployment, so this path is dormant, not merely "partial in production," but **entirely inactive at runtime**. |

**Update (2026-09-16, pre-defense hardening pass):** a new guarded service,
`dss/services/knowledge_base_admin.py::delete_document_safely()`, now sits in front of
`delete_document()` for the Knowledge Base "delete" feature. It checks `isinstance(vstore,
PgVectorStore)` and refuses to call the stub at all if so — returning an honest
`"unsupported"` status instead of trusting the stub's `return True`. This does **not**
change PgVectorStore's own implementation (still PARTIAL, still stubbed, per
`ARCH-PGVECTOR-001`, untouched this pass) — it only ensures the one new caller built this
pass never mistakes the stub's blind `True` for a real deletion.

**The single sentence to memorize for defense:** *"There is no relational database engine
running under this application today. Every piece of persisted application data is a
file — JSON, CSV, or a joblib binary — under `data_warehouse/`. A PostgreSQL + pgvector
backend is architected and schema-ready but its data-access methods are stubs, so it is
not the storage system in use."*

## Layer 7 — External Integration (LMS / CMS)

**Status: ABSTRACTION ONLY for LMS, PARTIAL for CMS.**

- **LMS:** `dss/services/lms_connector.py` defines a repository interface with
  `DemoLMSRepository` and a `RealConnectorLMSRepository` class. The "real" class
  currently **internally delegates its calls back to the demo repository** — there is no
  network call to an actual LMS platform (Moodle, Canvas, etc.) anywhere in the codebase.
  This is architecture-ready, not integration-ready.
- **CMS:** the "CMS" in this system is an **internal** lecture-content repository
  (`cms_lecture_repository.py`) — Lecturer uploads content, it is ingested and made
  retrievable via RAG. This part is real and fully working end-to-end (verified live this
  session with an actual quoted citation). It is not a connection to an external CMS
  platform; no such external platform is contacted anywhere in the codebase.

## Layer 8 — Cross-cutting concerns

- **Privacy** — IMPLEMENTED: pseudonymization before any data reaches an LLM prompt; only
  `student_id`/`risk_level`/`progress_note` fields are used, never name/email/phone.
- **Prompt security** — IMPLEMENTED: heuristic indirect prompt-injection defenses with
  dedicated test coverage.
- **Logging** — IMPLEMENTED: flat-file JSON activity/audit log, not a centralized log
  aggregator or SIEM.
- **Responsive UI** — IMPLEMENTED: verified zero horizontal overflow at 390×844,
  1366×768, 1440×900, 1920×1080.
- **Accessibility** — PARTIAL: accessible names and basic contrast verified; no formal
  WCAG audit tooling was run.

## Layer 9 — Performance architecture (added 2026-09-17, PERF-001/PERF-002 pass)

- **Heavy-import boundary:** `torch`/`transformers`/`sentence-transformers` are never
  imported at module load time anywhere in the codebase (verified by repo-wide grep for
  top-level `import torch`/`from torch`/etc. outside `dss/config.py`). The real import is
  gated behind `dss_config._ensure_local_llm_libs()`, a one-time-per-process function
  guarded by a module-level boolean. As of this pass, its only call sites are the two
  places that actually need the embedding model at the moment of the call:
  `core/models.py::load_embedding_model()` (called from `get_embedding()`, itself only
  called when a real embedding is needed) and `core/models.py::call_ai_provider()`'s
  `huggingface`-branch (only when that specific provider is invoked). Two previously
  eager, unnecessary call sites (`admin_reports.py`, `ai_advisor.py` — see
  `ISSUE_REGISTER.csv::PERF-001`) were removed; they now use the cheap
  `find_spec`-based `dss_config.HF_AVAILABLE` flag for display purposes only.
- **Embedding model ownership:** exactly one shared instance per process. The
  `MultiAIProvider` singleton (`llm_integration`) comes from
  `init_app.py::init_trainers_and_warehouse()`, `@st.cache_resource`-decorated — not
  recreated on Streamlit reruns. `load_embedding_model()` is itself
  `@st.cache_resource`-decorated with a `_self`-prefixed first argument (excluded from
  Streamlit's cache key), so the cache is genuinely global (keyed only on model name),
  not per-instance. Verified via dev-only timing instrumentation across every measured
  run: `_ensure_local_llm_libs()` fires exactly once per process, never repeats on
  subsequent reruns or subsequent retrievals.
- **Known, accepted remaining cost:** the first-ever embedding-consuming action in a
  freshly started process (e.g. a student's first question to the Learning Explainer)
  still pays the real torch/transformers import cost (measured 7–16s, machine/disk-cache
  dependent) plus the external LLM provider's own response latency. This is inherent to
  using a local PyTorch-based embedding model and an external LLM API; eliminating it
  would require model replacement/quantization/ONNX conversion or pre-warming at
  bootstrap, all explicitly out of scope for the PERF-001 pass. See
  `reports/performance_optimization/PERFORMANCE_BEFORE.md` and
  `PERFORMANCE_COMPARISON.md` for full measured detail.
- **Test/simulation data isolation (PERF-002, fixed 2026-09-17):** every mutable
  persistent store in the app (CMS lesson registry, quiz queue, interaction log,
  misconception records, users.json, ai_default_provider.json, subscription.json,
  ai_token_usage.json, technical logs, `LocalVectorStore`, `DataWarehouse`'s
  dataset/model/training-history directories, `RealConnectorLMSRepository`'s SQLite db)
  now resolves its writable path through one centralized function,
  `dss/core/data_root.py::get_data_root()` — returns the real `data_warehouse/` unless
  `EDUDSS_DATA_ROOT` is set (test/CI only), in which case every store transparently
  redirects there instead. Every store calls this function **at the point of use** (not a
  module-level constant computed once at import time), so the override is always honored
  regardless of import order. `tests/conftest.py` sets this env var automatically for every
  pytest run (autouse fixture) and asserts via a permanent pollution-guard fixture that the
  real store is byte-for-byte unchanged after the full suite. `tests/e2e/conftest.py`
  additionally passes this env var into the spawned Streamlit subprocess's own environment
  (`subprocess.Popen(env=...)`) — the deeper of the two original gaps, since a real browser
  session driving a real server needed server-level isolation, not just test-runner-level.
  This was proven, not merely asserted: real `data_warehouse/` snapshotted before/after the
  full non-E2E suite came back byte-for-byte identical, and the full E2E suite (39/39,
  including a dedicated isolation-proof test) passed with the pollution guard green.

## Summary sentence for defense

*"The application is a single-process Streamlit app with a clean service-layer
separation. Every subsystem that is claimed as 'real' — authentication, RBAC, the 4 ML
algorithms per task type, K-Means clustering, SHAP, the rule-based diagnosis and learning
plan engines, the RAG retrieval-and-citation pipeline, and the internal CMS lecture
repository — is genuinely implemented and was runtime-verified this session. The two
things that are NOT real are: (1) a live external LMS/CMS network integration, and (2) the
PostgreSQL vector-store backend, both of which exist only as ready-to-fill architecture."*
