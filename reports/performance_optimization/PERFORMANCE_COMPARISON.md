# PERFORMANCE_COMPARISON — Before / After (measured, browser wall-clock unless noted)

Methodology: Playwright scripts driving the real running app (`localhost:8765`), fresh
`streamlit run` process per "cold" row (server restarted, no prior session touched the
heavy import), same process reused for the paired "warm" row. Dev-only timing
instrumentation (`EDUDSS_PERF_DEBUG=1`, never on in production) cross-checked the
Python-level breakdown. Two independent real fixes are reflected below — removing 2
unnecessary eager-import call sites, and removing 741 automated-test lesson/quiz records
that had accumulated in the shared dev `data_warehouse/cms/*.json` stores (see
`PERFORMANCE_BEFORE.md` Finding #3 for why that was the dominant cost, not an ML issue).

| Metric | Before | After | Improvement |
|---|---|---|---|
| App first paint (login screen) | 6.6–12.4s | 6.6–7.1s | within measurement noise — unaffected by this pass, as expected (no ML code runs before login) |
| Login-ready (landing page) | 3.3–6.5s | 3.3–5.0s | within measurement noise — unaffected, as expected |
| Admin Dashboard open (home report page) | 6.5–8.0s (paid unconditional torch/transformers import, Finding #1) | 3.3–6.6s | eager import removed; no longer pays embedding-library cost |
| Model Registry open | 1.6–6.5s | 1.6–5.4s | unaffected (never needed embeddings) |
| AI Advisor ("Trợ lý AI") tab open | 1.6–2.7s (already warm from Admin Dashboard's eager call in the old code) | 1.6–4.8s (now genuinely never triggers the import itself, Finding #2) | eager import removed from this call site too |
| Learning Explainer cold open — Admin/Lecturer view | **60.5–96.5s** | **12.9s** | **~5–7x faster**; remaining 12.9s is plain Streamlit script-rerun overhead (confirmed via instrumentation: the tab's own render logic now completes in 0.07s), not ML-related |
| Learning Explainer warm re-open — Admin/Lecturer view | not cleanly measurable before fix (dominated by Finding #3 every time) | 5.1s | |
| Learning Explainer cold open — Student view (tab render, before first question) | not separately measured before fix; code path was already free of eager calls, so no regression risk existed | 4.0–4.2s | unchanged by design — student view never had the eager-import bug |
| First retrieval (student's first real question — torch+transformers import + embedding + LLM call, all paid here) | not isolated before fix | 24.3–25.4s | **unchanged by this pass** — this cost is inherent (first-ever local-LLM-lib import + external LLM provider response) and out of scope per Section 23 (no model replacement/quantization) |
| Second retrieval (embedding model + torch already loaded, only LLM call remains) | not isolated before fix | 5.1s | confirms warm reuse: **~4.8x faster than first retrieval**, with 0 repeat embedding-library imports (verified via instrumentation) |
| Learning Explainer warm re-open — Student view | not isolated before fix | 3.4–5.9s | |
| Embedding model initialization count (per process) | 1 (already correct — `@st.cache_resource`) | 1 (unchanged, verified via instrumentation logs across every run) | no change needed — architecture was already correct |
| Torch/transformers import — trigger sites | 2 unconditional (`admin_reports.py:199`, `ai_advisor.py:393`) + 2 legitimately lazy (`core/models.py:708,1116`) | 0 unconditional — only the 2 legitimately lazy sites remain | the 2 unnecessary triggers removed |
| Model instances (embedding model, `MultiAIProvider`) | 1 shared instance each (already correct) | 1 shared instance each (unchanged) | no change needed |
| Memory before embedding model load (process RSS) | — | ~78 MB | baseline dev-server footprint |
| Memory after embedding model load (process RSS) | — | ~622 MB | +~544 MB for torch+transformers+sentence-transformers+MiniLM in one process; single instance confirmed, not representative of per-session production capacity |

## PERF-002 follow-up (2026-09-17) — test/simulation data isolation

The CMS lesson count regrew from 2 to 54 after a single full test run, proving Finding #3's
cleanup alone was not durable — the underlying test-isolation gap was structural (every
mutable store resolved its path via a module-level constant, with no way for tests to
redirect it). Fixed via a centralized `dss/core/data_root.py::get_data_root()` resolver
(see `ISSUE_REGISTER.csv::PERF-002` for full detail) used by all ~13 stores, an autouse
pytest isolation fixture + permanent pollution guard, and E2E subprocess-level isolation
(the Streamlit subprocess spawned by `tests/e2e/conftest.py` now receives its own isolated
`EDUDSS_DATA_ROOT`, not just the pytest process).

| Metric | Before (PERF-002 fix) | After (PERF-002 fix) | Improvement |
|---|---|---|---|
| CMS lessons in real store after a full test run | grows unboundedly (2 → 54 → 743 observed across this engagement) | **0 growth** — real store snapshotted byte-for-byte identical before/after the full non-E2E suite | pollution structurally prevented, not cleaned up after the fact |
| Learning Explainer cold open — Admin/Lecturer view (post-cleanup, re-verified) | 12.9s | 13.1s | unchanged (within measurement noise) — confirms the isolation refactor added no overhead |
| Learning Explainer warm re-open — Admin/Lecturer view | 5.1s | 5.2s | unchanged |
| E2E test count | 38/38 | 39/39 (+1 new isolation-proof test) | zero regressions |
| Non-E2E test count | 444/444 | 450/450 (+6 new isolation-proof tests) | zero regressions |

## What changed vs. what didn't (honesty check against Section 14/15/16)

- No spinner was removed to fake speed — the existing `ui_kit.cold_start_aware_message()`
  spinners (Phase B) are untouched.
- No page renders before its data exists, no demo answers, no retrieval skipped, no
  source-quality checks weakened, no course isolation disabled, no student result reuse
  across students, no timing numbers fabricated (all values above are measured, several
  reported as ranges precisely because they were *not* perfectly reproducible run-to-run).
- RAG source governance (4-category classification, CMS-only retrieval, cross-course
  isolation, citation provenance) — untouched code paths, re-verified green (see test
  results in the final response).
- AI provider health single-source-of-truth (Phase C) — untouched.
- RBAC — untouched; `test_rbac.py` re-verified green.
