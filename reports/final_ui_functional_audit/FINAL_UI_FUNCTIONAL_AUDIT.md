# EduDSS — Final UI/Functional Audit Report

**Scope of this document:** consolidates the master audit's Architecture & Runtime Consistency
findings, a subsystem-by-subsystem Production Readiness assessment, and pointers to the
supporting artifacts (`ISSUE_REGISTER.csv`, `FUNCTIONAL_MATRIX.csv`,
`THESIS_DEFENSE_TRUTH_TABLE.md`). It supersedes nothing from the earlier `CHECKPOINT_REPORT.md`
in this same folder — that document remains the record of the Student/Lecturer/Admin UI pass,
Sidebar IA audit, Production Demo Policy corrections, and responsive-pass work. This document
adds the architecture-accuracy pass requested afterward: correcting several claims against
current code/runtime, closing 2 remaining reliability/cleanup issues, and finding + fixing 3
more Production Demo Policy violations that the earlier pass had not yet reached.

**Golden rule applied throughout:** current code/runtime is authoritative over any prior
handbook, summary, or even a "verified" fact supplied going into a session — every claim below
was checked by reading the actual implementation (and, for the highest-risk ones, exercising it
live), not accepted at face value.

---

## 1. Architecture & Runtime Consistency Table

| Feature | Old Handbook Claim | Current Code Truth | Runtime Verified? | UI Wired? | Production Status | Limitation | Safe Defense Claim | Must-Not-Claim | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| **PgVectorStore** | "System now has a real PostgreSQL-backed component" | Real DDL schema + real psycopg2 connection test; all 4 CRUD methods are stubs (no SQL executed) | YES — read full class body | N/A (backend) | NOT FUNCTIONAL (dormant) | Would silently lose data if activated via `PGVECTOR_URL` | "PostgreSQL backend is scaffolded (schema + connection test) but not functionally implemented" | "PostgreSQL stores RAG vectors in production" | `dss/services/vector_store.py:230-315`; `ARCH-PGVECTOR-001` |
| **File-based persistence** | (implicit default) | Dataset/model/user/org/consultation/log/subscription data all file-based (JSON/CSV/joblib) | YES | YES | PRODUCTION_READY | Not a relational DB; scale ceiling untested | "File-based storage, real and durable, appropriate to current scale" | "Enterprise-grade relational database" | `dss/core/warehouse.py`, `dss/services/auth_service.py` |
| **Knowledge Base Upload** | (assumed complete) | Real multi-format ingestion pipeline, verified live | YES (live closed-loop test) | YES | PRODUCTION_READY | — | "Real multi-format ingestion (txt/md/docx/pptx/pdf/json)" | — | `dss/tabs/knowledge_base.py:132-165` |
| **Knowledge Base Edit** | (assumed "full CRUD") | No edit UI exists anywhere | YES (read full file) | NO | NOT_IMPLEMENTED | Admin cannot correct an uploaded document | "Update not yet implemented" | "Full document CRUD" | `KB-CRUD-001` |
| **Knowledge Base Delete** | (assumed "full CRUD") | **FIXED 2026-09-16 (pre-defense hardening):** now wired end-to-end via `dss/services/knowledge_base_admin.py::delete_document_safely` — guarded by `@require_role("Admin")`, refuses to trust `PgVectorStore.delete_document()`'s stub `True` return (isinstance check), and blocks deletion if a live CMS lesson references the document | YES (14 unit + 2 E2E tests) | YES (LocalVectorStore backend; honestly "unsupported" for PgVectorStore) | PRODUCTION_READY (Delete); Update still NOT_IMPLEMENTED | Admin can now remove a document via a confirmation dialog | "Delete is real for the active backend (LocalVectorStore), Admin-only, with a confirmation step" | "Full document CRUD" (Update is still absent) | `KB-CRUD-001`; `dss/tabs/knowledge_base.py`; `tests/test_kb_delete_and_coldstart_ux.py`; `tests/e2e/test_kb_delete_and_coldstart_e2e.py` |
| **LMS** | Ambiguous / risk of overclaiming | Repository/abstraction layer real; "Real Connector" class itself delegates to demo internally; no external network integration | YES | Status display existed but was FABRICATED (fixed) | NOT REAL-INTEGRATED | No real LMS has ever been connected | "Architecture prepared for LMS integration" | "Connected to a real LMS" / "Syncs with Moodle/Canvas" | `dss/services/lms_connector.py:397-414`; `DEMO-LMS-STATUS-001` |
| **CMS** | Ambiguous | Internal lecture-content repository is real and fully working end-to-end (verified live); no external CMS connector | YES (live grounded citation test) | YES (internal repo only) | PRODUCTION_READY for internal repo; NOT REAL-INTEGRATED for external CMS | Conflated easily with "external CMS integration" — kept distinct in this report | "Internal content repository supports CMS-style flows; not connected to an external CMS" | "Connected to a real external CMS" | `dss/services/cms_lecture_repository.py` |
| **render_role_switcher** | (not tracked) | Dead code, zero callers, from pre-login-gate architecture; 2 more dead functions found in the same chain | YES (repo-wide grep) | N/A | REMOVED | — | "Removed; RBAC is via the real login gate only" | — | `ARCH-RBAC-001` |
| **MAX_CONCURRENT_REQUESTS** | (not tracked) | `=3`, config-driven constant, unchanged; limits AI calls only via a semaphore in LLMGateway | YES | YES | PRODUCTION_READY (mechanism); UNVERIFIED (capacity) | No load testing exists for this value | "Limits concurrent AI calls to 3; not load-tested" | "Optimized for scale" / any specific concurrent-user capacity | `dss/config.py:599`; `dss/services/llm_gateway.py:38` |
| **warehouse BaseException** | (not tracked) | 3 sites used `except BaseException: pass`, silently swallowing KeyboardInterrupt/SystemExit | YES | N/A (backend) | FIXED | — | "Narrowed to `except Exception`, corrupted files still skipped safely, now logged" | — | `ARCH-WH-001` |
| **Admin User Management** | (assumed CRUD) | Read-only: dataframe listing, zero action buttons | YES (read full section) | Read only | PARTIAL / READ-ONLY | No create/edit/deactivate/delete | "Admin can inspect user information" | "Admin has complete user CRUD" | `ADMIN-USER-001` |
| **Model Registry Candidate** | Possibly binary (Production/not) | Genuine 3-state lifecycle (candidate/production/archived), persisted, displayed consistently after a fix this session | YES (live screenshot, 2 pages cross-checked) | YES | PRODUCTION_READY | — | "Candidate → controlled promotion → production/archived" | "Registry is binary" | `MODELREG-001-FOLLOWUP` |
| **Model auto-promotion** | Possibly automatic | `auto_promote=True` never passed anywhere (repo-wide grep) | YES | N/A | PRODUCTION_READY (safe by default) | — | "Training never auto-promotes; only Admin-gated promotion changes Production" | "Best model is automatically promoted" | `dss/core/warehouse.py` (earlier phase) |
| **Bootstrap auto-training** | Possibly trains on login | Only reuses an existing Admin-approved Production model; explicitly does NOT call `.fit()` on login | YES (read full function body) | N/A | PRODUCTION_READY (safe by default) | — | "Login does not train models; only reuses an already-approved Production model if present" | "Login trains/updates models in the background" | `dss/core/bootstrap_service.py:169-203` |
| **RAG low-relevance fallback** | Possibly forces a weak match | `RAG_LOW_CONFIDENCE_FLOOR=0.55`, `RAG_RELATIVE_THRESHOLD=0.85`; returns `NO_RELEVANT_EVIDENCE` when below floor | YES (existing passing test) | YES | PRODUCTION_READY | Thresholds not further tuned/load-tested | "Refuses to force a weakly-related document; returns empty/no-evidence state instead" | Any different numeric threshold | `dss/config.py:582-590`; `dss/services/rag_service.py` |
| **LLM Gateway demo fallback under load** | (not tracked — found this session) | Concurrency-timeout and provider-exhaustion paths both silently emitted fabricated "Demo" content regardless of environment | YES (read + regression test) | YES | FIXED (gated behind `is_production_environment()`) | — | "REAL_LMS shows an honest overloaded/unavailable message instead of fabricated content" | "AI always returns a real personalized plan" | `DEMO-CONCURRENCY-001` |

---

## 2. Production Readiness — by subsystem (not a single score)

Per the standing rule that a high readiness score cannot coexist with open P0 issues: **all P0s
found across this entire engagement (DEMO-CAREER-001 in the earlier pass, DEMO-CONCURRENCY-001
and DEMO-LMS-STATUS-001 in this pass) are FIXED and verified** (regression tests + live
screenshots/behavioral tests, full suites green). No P0 remains open as of this document.

| Subsystem | Status | Rationale |
|---|---|---|
| Student core (dashboard, prediction, clustering, learning plan) | **READY** | Live-verified, role-appropriate, no known defects |
| AI Learning Explainer (CMS-grounded Q&A) | **READY** | Live closed-loop verified with real grounded citation |
| Career Advisor | **READY in DEMO_SYNTHETIC; HONEST_UNAVAILABLE in REAL_LMS** | Underlying LMS/CMS connector is not real yet — correctly disclosed now rather than faked |
| Lecturer core (dashboard, training, warehouse) | **READY** | Responsive bug found and fixed this session; otherwise clean |
| Admin core (registry, AI config, RAG knowledge base, reports, settings) | **READY**, with 2 documented functional gaps | User Management is read-only by design decision (not a bug); Knowledge Base is Create+Read only |
| LMS integration | **NOT READY (by design, honestly disclosed)** | No real external LMS connector exists; UI no longer claims otherwise |
| CMS integration (external) | **NOT READY (by design, honestly disclosed)** | No real external CMS connector exists; internal content repository is separately READY |
| RAG / Vector Store | **READY (active LocalVectorStore)**; **NOT READY (dormant PgVectorStore)** | Do not enable `PGVECTOR_URL` in production without first implementing PgVectorStore's real SQL operations |
| Concurrency / scale | **UNVERIFIED** | Mechanism is safe (documented default, no silent overload behavior after this session's fix); actual capacity has never been load-tested |
| Test infrastructure | **STABLE** | Full non-e2e suite (392 tests) and full e2e suite (23 tests) green; 1 load-dependent timing issue found and fixed with evidence, not a blind timeout bump |

---

## 3. What changed in this pass (architecture-accuracy audit)

1. Corrected the PostgreSQL/PgVectorStore claim — documented the schema-vs-stub distinction
   (`ARCH-PGVECTOR-001`).
2. Corrected the Knowledge Base "CRUD" claim — Create+Read only (`KB-CRUD-001`).
3. Corrected the LMS/CMS integration claim and **fixed a genuine P0** — `admin_settings.py` was
   fabricating a live LMS connection with a fake webhook/secret (`DEMO-LMS-STATUS-001`).
4. Found and fixed a second, related P2 — the honestly-labeled but session-data-mutating "LMS
   Live Push" simulation panel is now hidden in REAL_LMS mode (`DEMO-LMS-LIVEPUSH-001`).
5. Found and fixed a **P0 the user's own supplied facts did not flag** — `LLMGateway
   .stream_generate()` had two more production-reachable fabricated-content fallback paths
   triggered by concurrency pressure or provider exhaustion (`DEMO-CONCURRENCY-001`).
6. Removed confirmed dead code: `render_role_switcher()` plus 2 more functions in the same call
   chain found during investigation (`ARCH-RBAC-001`).
7. Narrowed `except BaseException` to `except Exception` at 3 sites in `warehouse.py`, with
   logging added (`ARCH-WH-001`).
8. **Corrected an inaccurate supplied fact** — bootstrap auto-training was reported as
   already-fixed; verification confirmed this is TRUE (the code explicitly avoids `.fit()` on
   login), so no code change was needed here, only documentation.
9. Fixed a real cross-page inconsistency found while verifying Model Registry claims —
   `admin_reports.py`'s status chart disagreed with the Model Registry table on identical data
   (`MODELREG-001-FOLLOWUP`).
10. Documented Admin User Management as read-only without inventing unsafe CRUD
    (`ADMIN-USER-001`).

See `ISSUE_REGISTER.csv` for full details on every item above (Root Cause / Fix / Verification
columns), `FUNCTIONAL_MATRIX.csv` for the complete Create/Read/Update/Delete breakdown per
feature, and `THESIS_DEFENSE_TRUTH_TABLE.md` for exact safe/must-not-claim wording per topic.

---

## 4. Explicitly still open (not fixed this pass, by deliberate scope decision)

- `ARCH-PGVECTOR-001` — implementing real PgVectorStore SQL operations is a feature addition,
  not a quick fix; out of scope for this pass.
- `KB-CRUD-001` — **PARTIALLY FIXED 2026-09-16 (pre-defense hardening).** Delete is now real for
  the active LocalVectorStore backend (hard delete of chunks+embeddings, atomic disk write,
  Admin-only, confirmation dialog, blocked when a live CMS lesson still references the document).
  Update remains NOT_IMPLEMENTED — still needs a design decision on what "edit" means for
  already-embedded/chunked content, out of scope for this hardening pass. Overall still **PARTIAL
  CRUD**, not "full CRUD".
- `ADMIN-USER-001` — full user CRUD requires prior architecture decisions (auth ownership, org
  isolation, audit logging, role-mutation rules) that were explicitly out of scope to invent.
- Everything listed as "Explicitly NOT yet covered" in `CHECKPOINT_REPORT.md` (full responsive
  sweep beyond the home pages, full accessibility pass, LMS/CMS/RAG items beyond what this pass
  re-verified).

## 5. Regression evidence for the architecture-accuracy pass

- `tests/test_warehouse_exception_handling.py` — 3/3 passing (new).
- `tests/test_production_demo_policy.py` — 21/21 passing (5 new this pass, on top of the 16 from
  the earlier pass).
- `tests/test_model_lifecycle_badge.py` — 5/5 passing.
- Full non-e2e suite: 392/392 passing.
- Full e2e Playwright suite: 23/23 passing.

---

## 6. Product Acceptance pass (Student → Lecturer → Admin → LMS/CMS/RAG → Design System →
Responsive/Accessibility)

This section consolidates the live product-acceptance continuation that followed the
architecture-accuracy pass above — every Student, Lecturer, and Admin destination was opened
live in a real browser (not judged from source alone), primary actions exercised, and genuine
defects fixed with before/after evidence. Full detail lives in the companion documents in this
folder; this section is the roll-up.

### 6.1 What was walked, and where the full record is

| Phase | Record | Destinations covered |
|---|---|---|
| Student | `STUDENT_ACCEPTANCE.md` | All 5 sidebar destinations + every sub-tab (9 screens total) |
| Learning Explainer / Career Advisor deep-test | `LEARNING_EXPLAINER_CAREER_ADVISOR_DEEPTEST.md` | Retrieval, course isolation, version pinning, citation grounding, active vector-store determination, Career Fit/Readiness computation trace |
| Lecturer | `LECTURER_ACCEPTANCE.md` | All 7 sidebar destinations + sub-tabs (10 screens total) |
| Admin | `ADMIN_ACCEPTANCE.md` | All 9 sidebar destinations |
| LMS/CMS/RAG | `LMS_CMS_RAG_PRODUCT_VERIFICATION.md` | Consolidated cross-role verification with evidence pointers |
| Design system | `DESIGN_SYSTEM_ADOPTION_MATRIX.md` | 16 pages surveyed for shared-component adoption |
| Responsive/Accessibility | `RESPONSIVE_ACCESSIBILITY_REPORT.md` | 1920×1080/1440×900/1366×768/390×844 + a pragmatic a11y spot-check |

### 6.2 New issues found and fixed during this pass (in addition to the architecture-accuracy
pass's issues in §1 above) — full detail in `ISSUE_REGISTER.csv`

| ID | Severity | One-line summary |
|---|---|---|
| `CARD-HEIGHT-001` | P1 | Student home 3-card row measured 531/324/392px despite an existing equal-height rule; root-caused to a missing `stLayoutWrapper` link and fixed at the shared-selector level (self-heals every bordered-card row app-wide) |
| `FUNC-ML-002` | P1 | "Dự đoán — Từ file" tab had no file uploader and pointed Sinh viên to 2 inaccessible tabs on a dead-end message |
| `SIA-CLUSTER-002` | P2 | Literal "cosine" jargon, a broken K-Means button reference, 4 English-jargon parentheticals, and dev-trivia chart documentation shown to Sinh viên |
| `SIA-NAV-002` | P2 | AI Advisor's own page header wasn't role-branched even though the outer nav label was |
| `RESPONSIVE-001` | P1 | Lecturer home's hand-rolled KPI row broke at phone width (labels wrapped one character per line) |
| `SIA-CLUSTER-002-FOLLOWUP` | P2 | Cluster Interpretation card leaked raw column names instead of `feature_label()` |
| `MODELREG-TEXT-001` | P1 | Model Registry page text claimed training auto-promotes to Production, contradicting both the actual code and another sentence in the same file — corrected in 3 files |
| `COLDSTART-001` | P2 (PARTIAL — UX FIXED / LATENCY REMAINS, 2026-09-16) | Root cause measured directly: first-time `torch`/`transformers`/`sentence-transformers` import (~22s) + `SentenceTransformer(...)` instantiation (~5s), lazily triggered by the first embedding-consuming action in the process. Latency itself is unchanged by design (no bootstrap pre-warming, per explicit scope decision — see below); every spinner on the cold-start path now shows an explicit "may take about 1 minute, the app is not frozen" message via `ui_kit.cold_start_aware_message()` |

**Total across the whole engagement (architecture-accuracy + product-acceptance passes, plus the
2026-09-16 pre-defense hardening pass): 26 rows in `ISSUE_REGISTER.csv`, of which 22 are FIXED, 2
are PARTIALLY FIXED this hardening pass (`KB-CRUD-001` — Delete done, Update still open;
`COLDSTART-001` — UX fixed, latency unchanged by design), and 2 remain deliberately OPEN by
documented scope decision** (`ARCH-PGVECTOR-001`, `ADMIN-USER-001` — neither is a correctness bug;
each is either future-scope feature work or a deliberate architecture-decision gap the instructions
explicitly forbade inventing unsafe CRUD to close, or a documented UX-polish
opportunity).

### 6.3 Critical product checks (explicit requirement) — both PASS

- **Student ML Hub does not expose training controls**: verified at the code level
  (`tab_train_ml = None` for Sinh viên, the entire training UI block is structurally unreachable)
  and confirmed live (no training tab ever renders for this role).
- **Student Clustering does not expose global K-Means config**: verified at the code level
  (`if role != "Sinh viên":` wraps the entire config/fit block) and confirmed live.

### 6.4 Regression evidence for the full product-acceptance pass

- New test files/additions this pass: `tests/test_responsive_design.py` (+2 tests),
  `tests/test_student_ml_prediction_labels.py` (new, 4 tests),
  `tests/test_student_information_architecture.py` (+3 tests),
  `tests/test_model_lifecycle_badge.py` (+1 test).
- Full non-e2e suite: **403/403 passing** (final confirmation run).
- Full e2e Playwright suite: **23/23 passing** (final run, 10m18s) — this is the authoritative
  "after ALL final changes" run per the standing test strategy (not re-run after every small
  change; run once, fully, at the very end). **This was the final green baseline for the
  architecture-accuracy + product-acceptance engagement: 403 non-e2e + 23 e2e = 426 tests
  passing — see `RELEASE_FREEZE.md` for this preserved as the PRE-HARDENING BASELINE.**
- Two isolated transient-failure incidents during this pass (both on `*.tmp`→`.json` renames under
  concurrent load) were confirmed, per the established discipline, to be the same pre-existing
  Windows file-lock race documented earlier in this engagement — not regressions, verified by
  clean isolated re-runs both times.

### 6.5 Regression evidence for the 2026-09-16 pre-defense hardening pass (KB-CRUD-001 delete + COLDSTART-001 UX)

- New test files: `tests/test_kb_delete_and_coldstart_ux.py` (14 tests) and
  `tests/e2e/test_kb_delete_and_coldstart_e2e.py` (5 E2E tests).
- Full non-e2e suite: **417/417 passing** (403 pre-existing + 14 new, zero regressions).
- Full e2e Playwright suite: **28/28 passing** (23 pre-existing + 5 new, 14m17s), zero
  regressions.
- **New final baseline for the whole engagement: 417 non-e2e + 28 e2e = 445 tests passing.**
  The prior 426/426 result is preserved unmodified as the PRE-HARDENING BASELINE (see
  `RELEASE_FREEZE.md`) — history is not erased, only superseded.
- No product-code changes were made outside the two authorized items (KB-CRUD-001 delete,
  COLDSTART-001 loading UX); `PgVectorStore` CRUD, Admin User Management CRUD, and real
  LMS/CMS integration were explicitly NOT touched, per the hardening pass's scope lock.

### 6.6 UI/RAG consistency pass (2026-09-16) — root-caused and fixed 4 real bugs, verified live

This pass was requested against a large (49-point) list of reported UI/UX problems. Every
item was reproduced (or attempted to be reproduced) directly in the running application with
Playwright before any code was touched, per the explicit instruction not to "merely change
text and declare success." Four items were **confirmed as real bugs with a precise root
cause** and fixed; several other reported items were **investigated and found NOT
reproducible against the current codebase** (most likely already fixed in an earlier phase
of this engagement) — these are reported honestly as not reproducible rather than
re-described as fixed.

**Real bugs found and fixed:**

1. **Dark mode text contrast (confirmed root cause via live `getComputedStyle()`, not
   guessed).** Metric card values/labels were nearly invisible in dark mode. The actual
   cause: Chromium paints text using `-webkit-text-fill-color` when present, which wins
   over `color` — dozens of rules in `main.css` set both together with light-mode values
   (`#0F172A` etc.), and the dark-mode CSS block in `dss/config.py::inject_styles()` only
   overrode `color`, never `-webkit-text-fill-color`. Fixed by (a) redefining the actual
   semantic tokens (`--text-main`, `--text-muted`, `--bg-app`, `--bg-surface`, `--border`,
   etc.) inside the dark-mode block so the ~40 rules that already read `var(--text-main)`
   automatically become correct, and (b) a single `-webkit-text-fill-color: currentColor
   !important` failsafe scoped to the app + sidebar to neutralize the remaining hardcoded
   literals. Also converted `ui_kit.metric_card()` from ad-hoc inline-styled HTML to the
   existing `.metric-card`/`.metric-card-label`/`.metric-card-value` CSS classes so it
   participates in the token system instead of being permanently theme-blind.
2. **Sidebar section titles ("TỔNG QUAN", "DỮ LIỆU & MÔ HÌNH"...) clipped at the top, in
   both themes.** Root cause (confirmed via live `getBoundingClientRect()`): Streamlit's
   own `[data-testid="stElementContainer"]` wrapper around the `st.markdown()` title call
   computes `overflow: hidden auto` with a single-line-text height estimate (~18px), but
   the app's larger font-size/line-height/letter-spacing uppercase title needs ~30px+ —
   the difference was silently scroll-clipped. Fixed with a targeted
   `:has(.dss-sidebar-group-title)` override forcing that specific wrapper to
   `overflow: visible; height: auto`.
3. **AI provider health status was contradictory between two Admin pages** (the "Cấu hình
   AI" page's real per-provider test vs. the "Trợ lý AI" tab's summary expander). Root
   cause: the summary expander computed "Sẵn sàng" purely from `*_AVAILABLE` flags (API
   key **configured**), never from an actual health check, while the config page's
   "Kiểm tra kết nối" button calls the real `llm_gateway.check_provider_health()`. Fixed
   by making the summary expander read the same cached health-check result
   (`session_state["_admin_ai_health_{provider}"]`) the config page already writes,
   falling back to an honest "Chưa kiểm tra" (not "Sẵn sàng") when no test has run yet.
   Also separated the Hugging Face **embedding** indicator (a different role — turns text
   into vectors for retrieval, does not generate answers) out of the LLM provider row,
   with an explicit caption that its readiness is unrelated to LLM readiness.
4. **Model Registry table showed raw ISO timestamps** (e.g. `2026-09-09T22:36:00.587897`)
   in the "Huấn luyện lúc" column. This did not surface in text-based checks because
   `st.dataframe` renders large tables via canvas (glide-data-grid) — cell text is not
   part of the accessible DOM and only visible via screenshot. Fixed with a
   `_humanize_trained_at()` helper formatting to `dd/mm/yyyy HH:MM`.

All four fixes were verified two ways: (a) new dedicated E2E tests
(`tests/e2e/test_ui_dark_mode_and_provider_health_e2e.py`, 3 tests, computed-style/live-data
assertions, not screenshot diffing) and (b) manual before/after Playwright screenshots.

**Reported items investigated and found NOT reproducible against the current codebase**
(no screenshots were available from the requester for this pass — investigation proceeded
directly against the running app instead):
- Duplicate "EduDSS" branding block in the sidebar — `dss/main.py` contains exactly one
  branding block; a fresh server restart showed only one instance.
- "Dùng dữ liệu mẫu mặc định" button doing nothing — live-tested end to end (click →
  dataset activates → name/row-count/`DỮ LIỆU MẪU / SYNTHETIC` label shown → carries over
  to the Khám phá tab); works correctly. The one real nuance found: the one-time success
  toast is consumed after a single rerun and can be missed if not looking at the right
  moment — a minor, pre-existing Streamlit pattern limitation, not "the button does
  nothing."
- Raw Python list `repr()` / literal "Mục tiêu:" prefix in the EDA preprocessing detail
  table — `dss/tabs/eda.py` already applies `.removeprefix('Mục tiêu: ')` on both the
  dataframe column and the expander bullet list; verified no raw prefix or list-repr text
  appears anywhere in the rendered page.
- Model Registry "no explanation of purpose" / misleading action buttons — the page
  already opens with the exact explanatory sentence and Chờ duyệt→Đang sử dụng→Lưu trữ
  lifecycle caption requested, and already states plainly that the page is view-only with
  actions elsewhere; no fake action buttons found.
- Bold navigation/button text — `.stButton button p, .stButton button span,
  [data-testid="stTabs"] button p { font-weight: 650 !important; }` already exists and
  applies consistently.

**Not attempted this pass** (explicitly out of the verified-fix list below — the RAG
source-priority/Knowledge-Base-reclassification and global-search-UX/RBAC portions of the
original request were not implemented; see `ISSUE_REGISTER.csv` for tracking). The existing
architecture already gives Learning Explainer exclusive priority to lecturer-uploaded CMS
content over the generic Knowledge Base (verified in an earlier phase of this engagement),
but no new source-classification labeling or search redesign was added in this pass.

### 6.7 Regression evidence for the 2026-09-16 UI/RAG consistency pass

- New test file: `tests/e2e/test_ui_dark_mode_and_provider_health_e2e.py` (3 E2E tests —
  computed-style/live-data assertions, not screenshot diffing).
- Full non-e2e suite: **417/417 passing** (unchanged from the prior hardening pass — this
  pass touched no non-E2E-tested logic, only UI/CSS and one AI-status display path).
- Full e2e Playwright suite: **31/31 passing** (28 pre-existing + 3 new, 16m51s), zero
  regressions.
- **New final baseline for the whole engagement: 417 non-e2e + 31 e2e = 448 tests passing.**
  Both prior baselines (426/426 and 445/445) are preserved unmodified in `RELEASE_FREEZE.md`
  as historical record.

### 6.8 Search + RAG Source Governance pass (2026-09-16, part 2 of the UI/RAG consistency work)

Completed the two items left unfinished by §6.6/§6.7 above: global search UX/RBAC, and RAG
source governance (course-material priority over generic Knowledge Base content).

**Part A — Global search, rebuilt on a new `dss/services/search_service.py`:**
- RBAC enforced *before* any result is computed: `search_students(df, query, role)` returns
  `[]` immediately for any role other than Admin/Giảng viên — the search input itself is
  no longer even rendered for Sinh viên (not just result-filtered after the fact).
  Giảng viên's scope matches the same full-class dataset visibility they already have
  everywhere else in the app (Dashboard, Kho dữ liệu, Trợ lý AI) — no new permission was
  invented, and no "assigned classes" concept was fabricated since the data model has none.
- Exact-ID matches rank before partial matches; matching is case-insensitive; results are
  capped at 5 with humanized metric labels (via the existing `feature_label()` helper) —
  never raw column names, never a raw dataframe as the primary experience.
- Honest empty state: `Không tìm thấy kết quả phù hợp với "...".` plus a hint line — never
  an empty dataframe/`[]`/`None`.
- Real navigation, not a dead button: "Xem phân tích" pre-selects the found student in the
  Trợ lý AI tab's existing `llm_student_select` widget (via session_state, which Streamlit
  honors as the widget's initial value) and jumps there via the existing
  `_pending_nav_target` mechanism. This is the one destination that could be wired safely
  and honestly with current architecture (it already surfaces weakness analysis, risk
  profile, and prediction for the selected student) — "Xem hồ sơ"/"Xem chẩn đoán"/"Xem
  khuyến nghị" as *separate* destinations were not fabricated since no separate pages for
  them currently exist.
- Verified at 1920×1080, 1440×900, and 1366×768 — results render in a full-width container
  below the top bar row, not overlapping the theme toggle/notifications/profile controls.

**Part B — RAG source governance, on a new `dss/services/source_classification.py`:**
- Centralized 4-category classifier (`COURSE_MATERIAL`, `INSTITUTION_APPROVED`,
  `SUPPLEMENTARY_REFERENCE`, `DEMO`) derived strictly from existing provenance metadata
  (`lesson_id`+`lecturer_id` for CMS uploads; `source_verified` for the 4/19 demo documents
  with real academic references; everything else defaults to `DEMO`) — never from
  "academic-looking" text content. `INSTITUTION_APPROVED` requires an explicit
  `institution_approved=True` flag that nothing in the system currently sets, so it is
  intentionally never populated rather than fabricating institutional authority.
- **Confirmed by re-reading, not re-built:** Learning Explainer's retrieval
  (`cms_lecture_repository.retrieve_lesson_content`) already only ever queries the
  CMS/course-material path filtered by `course_id`/`lesson_id`/`document_id` — it has no
  code path that falls back to the generic 19-document Knowledge Base. `generate_explanation()`
  already returns an honest "not found in course material" message
  (`NO_CMS_CONTENT_MESSAGE`) with zero citations when no course content matches, rather than
  substituting demo content. This was true before this pass; it is now covered by dedicated
  regression tests so it cannot silently regress.
- `dss/tabs/knowledge_base.py` reorganized: a new top-of-page KPI breakdown
  (Tài liệu môn học / Nguồn tham khảo bổ sung / Dữ liệu demo counts, never merged into one
  misleading total) and a new read-only "🎓 Tài liệu môn học (CMS)" tab listing real
  lecturer-uploaded lessons (course, lecturer, official-source flag, version count, AI-enabled
  state) — sourced from `cms_lecture_repository.list_lessons()`, no fake CMS connector, no
  fake sync status, no fake external CMS ID. The former "Demo Knowledge" tab (now "📖 Nguồn
  tham khảo & Demo") shows a `Phân loại nguồn` column per document, and for `DEMO`-classified
  documents replaces the old free-text GEN_REF sentence with an explicit
  "Nguồn: Dữ liệu demo nội bộ · Mục đích: Minh họa chức năng truy xuất RAG." instead of
  presenting it as a real citation.
- Citation format (`learning_explainer._format_friendly_citation`) extended to include the
  course context (`"{title}, {section} (Tài liệu môn {course_id})"`) — still never exposes
  chunk_id/vector_id/namespace_id/embedding_id.
- No external LMS or CMS connector was built or implied anywhere in this work — both remain
  honestly `NOT IMPLEMENTED`, per explicit instruction.

**Tests:** 12 new unit tests (`tests/test_search_service.py`), 10 new unit tests
(`tests/test_source_classification.py`), 5 new integration tests using the real embedding
model (`tests/test_rag_source_governance.py` — course-material classification of real CMS
chunks, demo-fallback exclusion at the full `generate_explanation()` pipeline level,
citation course-context, cross-course isolation at the pipeline level, exhaustive
classification of all 19 real demo documents), and 7 new E2E tests
(`tests/e2e/test_search_and_rag_governance_e2e.py` — search exact/empty-state/RBAC/lecturer
access/real navigation, Knowledge Base breakdown display, honest demo labeling).

### 6.9 Regression evidence for the search + RAG governance pass

- Full non-e2e suite: **444/444 passing** (417 pre-existing + 27 new [12 search_service +
  10 source_classification + 5 rag_source_governance], zero regressions).
- Full e2e Playwright suite: **38/38 passing** (31 pre-existing + 7 new, 19m10s), zero
  regressions.
- **New final baseline for the whole engagement: 444 non-e2e + 38 e2e = 482 tests passing.**
  All three prior baselines (426/426, 445/445, 448/448) are preserved unmodified in
  `RELEASE_FREEZE.md` as historical record.

### 6.10 Learning Explainer performance optimization pass (2026-09-17)

Profiled first with dev-only timing instrumentation (never active in production), then
fixed only what the measurements actually showed. Two real, distinct root causes were
found and fixed — full detail in `ISSUE_REGISTER.csv::PERF-001`/`PERF-002` and
`reports/performance_optimization/PERFORMANCE_BEFORE.md`/`PERFORMANCE_COMPARISON.md`:

1. **PERF-001** — `admin_reports.py` and `ai_advisor.py` each unconditionally imported
   `torch`/`transformers`/`sentence-transformers` (several seconds) merely to display an
   installed/not-installed badge, on pages that do not use embeddings on that render.
   Fixed by using the already-existing cheap `find_spec`-based flag for display, leaving
   the real import exactly where it was already correctly lazy (only when an
   embedding-consuming action is actually invoked).
2. **PERF-002** — the dominant real cost (not an ML issue at all): the shared dev
   `data_warehouse/cms/*.json` stores had accumulated 743 lesson records + 176 quiz-queue
   items from this session's own automated tests, never cleaned up. Streamlit renders
   every `st.tabs()` body on every rerun regardless of visible selection, so opening the
   Learning Explainer as Admin/Lecturer rendered full management UI for all 743 lessons
   and a full review-queue UI for all 176 items every time. Cleaned up with explicit user
   confirmation (741 test-fixture records removed; 2 genuine demo lessons kept; full
   backup retained).

### 6.11 Test/simulation data-isolation pass (PERF-002 follow-up, 2026-09-17)

PERF-002's cleanup alone was proven insufficient: the user observed CMS lessons cleaned to
2, then regrown to 54 after a single full test run — conclusive proof the isolation gap was
structural, not a one-time cleanup problem. Root cause: **every** mutable store in the app
(not just CMS) resolved its writable path via a module-level constant computed once at
import time, with no way for any test to redirect it. Fix — full detail in
`ISSUE_REGISTER.csv::PERF-002` and `dss/core/data_root.py`:

- New centralized `get_data_root()` resolver: real `data_warehouse/` unless
  `EDUDSS_DATA_ROOT` is set, checked **at the point of use** in all ~13 stores (CMS
  lesson/quiz/interaction/misconception, users.json, AI config, subscription, token usage,
  logs, vector store, dataset/model/training-history directories, LMS SQLite db) — no
  scattered `if pytest`/`if TEST_COURSE` guards in application code.
- `tests/conftest.py`: autouse session-scoped fixture sets the isolated root automatically
  for every test, plus a permanent pollution-guard fixture (snapshots the real store before
  the session, asserts byte-for-byte equality after — names the exact store if this ever
  regresses).
- `tests/e2e/conftest.py`: the spawned Streamlit **subprocess** now receives its own
  isolated `EDUDSS_DATA_ROOT` via `subprocess.Popen(env=...)` — previously it inherited the
  parent's environment with no override at all, meaning a fully-isolated pytest process
  still drove a real server writing to the real store via the browser. Two follow-on bugs
  (direct `LocalVectorStore()` calls in `test_kb_delete_and_coldstart_e2e.py` pointing at
  the wrong one of the two now-separate isolated roots) found and fixed during verification.
- Verified, not just asserted: real `data_warehouse/` snapshotted before/after the full
  non-E2E suite (450/450) came back byte-for-byte identical; full E2E suite (39/39,
  including a new dedicated isolation-proof test) passed with the pollution guard green in
  a run with no concurrent interference; a post-fix smoke-check (real dev server, no
  isolation override) confirmed login/Admin home/Model Registry/Learning Explainer all
  render normally and still show the genuine CS301/K-Means demo lesson; a re-measurement
  confirmed Learning Explainer cold/warm timing unchanged from the PERF-001 fix (13.1s /
  5.2s) — the isolation refactor introduced no performance regression.
- **Explicitly not cleaned** (documented, not fixed): `data_warehouse/{datasets,models,
  training_data,evaluation_data,metadata,history}` — hash-named files with no field
  distinguishing test-run origin from legitimate demo origin; see
  `ISSUE_REGISTER.csv::PERF-002-DATASETS-NOTE`.

`PERF-002` is now marked **FIXED** (not partial) — the test-isolation gap itself is closed,
not merely its symptom cleaned up once more.

Measured result: Admin/Lecturer Learning Explainer cold open **60.5–96.5s → 12.9s**;
warm re-open 5.1s. Student first retrieval (genuinely-first embedding+LLM call, unchanged
by design) 24.3–25.4s; second retrieval (model already warm) 5.1s — confirms 0 repeat
embedding-library imports. Single shared embedding-model instance and single shared
`MultiAIProvider` instance were verified already correct (no fix needed). No RAG
governance/RBAC/AI-provider-health regression. Full regression: 444/444 non-E2E
(unchanged); E2E re-verified (see `RELEASE_FREEZE.md` for the exact confirmed count).
`COLDSTART-001` updated from "UX fixed / latency remains" to **"UX fixed and warm path
optimized; first process cold import remains"** — not marked fully FIXED, per the pass's
own honesty requirement, since the genuinely-first-ever import in a process is unchanged
by design.

---

## 7. Final Production-Readiness Verdict

Per the standing rule that a high readiness score cannot coexist with open P0 issues:
**every P0 found across the ENTIRE engagement is FIXED and verified** — `DEMO-CAREER-001`,
`DEMO-CONCURRENCY-001`, and `DEMO-LMS-STATUS-001`. No P0 remains open.

| Subsystem | Verdict |
|---|---|
| Student experience (all destinations) | **READY** |
| Lecturer experience (all destinations) | **READY** |
| Admin experience (all destinations) | **READY**, 1 documented-by-design gap (User Management read-only) |
| AI Learning Explainer | **READY** (1 documented perf gap, `COLDSTART-001` — PARTIAL: UX fixed + warm path optimized 2026-09-17 [cold open 60.5–96.5s → 12.9s]; first process cold import remains by design) |
| Career Advisor | **READY in DEMO_SYNTHETIC; honestly UNAVAILABLE in REAL_LMS** (correct target state — no real LMS/CMS connector exists yet) |
| RAG / Knowledge Base | **READY** for Create+Read+Delete (fixed 2026-09-16, `KB-CRUD-001` partial); documented gap: still no Update/Edit UI |
| LMS integration | **NOT READY, honestly disclosed** (correct target state per explicit instruction — architecture prepared, no fabricated claims) |
| Vector storage | **READY** (active `LocalVectorStore`); **dormant, non-functional** (`PgVectorStore` stub, documented, do not enable via `PGVECTOR_URL` without implementing it first) |
| Design system | **READY**, correctly adopted on 15/16 surveyed pages; 1 local component flagged for future consolidation |
| Responsive (390/1366/1440/1920) | **READY** — zero overflow at any checked resolution, 1 sub-threshold cosmetic wrap noted |
| Accessibility | **PARTIALLY VERIFIED** — accessible names and keyboard-focusability confirmed; focus-visible styling and screen-reader landmarks not yet audited (no tooling wired up) |
| Test infrastructure | **STABLE** — 450 non-e2e + 39 e2e = 489/489, both green at the final run (see §6.11); test data isolation fixed (PERF-002) — automated tests can no longer write into the live `data_warehouse/` |

**This audit is complete for the scope requested.** Remaining open items are documented,
intentional scope boundaries (feature work deferred, not defects hidden) — see §4 and §6.2 above
for the exhaustive list with reasoning for each.
