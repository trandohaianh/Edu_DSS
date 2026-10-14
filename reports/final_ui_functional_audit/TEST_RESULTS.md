# Test Results — Consolidated

This file consolidates test-run evidence that was recorded inline in `FINAL_UI_FUNCTIONAL_AUDIT.md`
and the per-role acceptance records during the audit, into one place for defense reference.

## Final baseline (release-frozen)

| Suite | Count | Result |
|---|---|---|
| Non-E2E (`pytest tests --ignore=tests/e2e`) | 403 | **PASS** |
| E2E (`pytest tests/e2e`, Playwright, real browser) | 23 | **PASS (10m18s)** |
| **Total** | **426** | **PASS** |

## New test files/additions produced during this engagement (non-exhaustive list of the most
relevant ones for defense purposes — every fix in `ISSUE_REGISTER.csv` has a corresponding test)

- `tests/test_llm_service.py` — provider health/model-catalog/billing-classification (~20 tests)
- `tests/test_production_demo_policy.py` — 21 tests, REAL_LMS demo-path gating
- `tests/test_model_lifecycle_badge.py` — 6 tests, Candidate/Production/Archived lifecycle
- `tests/test_learning_plan_wiring.py` — 5 tests, real generator wired to production path
- `tests/test_regression_param_grid.py` — 7 tests, single source of truth for param grids
- `tests/test_warehouse_exception_handling.py` — 3 tests, narrowed exception handling
- `tests/test_student_information_architecture.py` — 15 tests, role-appropriate labeling
- `tests/test_student_ml_prediction_labels.py` — 4 tests, no dead-end navigation instructions
- `tests/test_responsive_design.py` — 3 tests, CSS equal-height chain + breakpoints
- `tests/test_lms_ai_rag_gateway.py` — 17 tests, RAG/LLM Gateway architecture (namespace
  isolation, vector store schema, retrieval confidence, citations, prompt security, privacy)
- `tests/test_learning_explainer_acceptance.py` — 14 tests, real ingest→retrieve→cite→quiz chain
- `tests/test_career_advisor.py` — Career Fit/Readiness/roadmap/what-if computation

## Known transient failure pattern (not a defect)

A `PermissionError: [WinError 5] Access is denied` on `*.tmp` → `.json` renames under concurrent
full-suite load was observed **3 separate times** across this engagement, always on different
specific files (`lessons_registry.json`, `quiz_review_queue.json`), always resolved cleanly on an
isolated re-run of the same test(s). This is a Windows file-lock race under heavy concurrent test
execution, not a product defect — confirmed by the discipline of never accepting "flaky" without
an isolated re-run proving it, applied consistently every time this pattern appeared.

## Live browser (E2E) evidence highlights

- Real closed-loop RAG verification: a live chat query returned a verbatim quote from an actual
  ingested lecture file with a traceable citation ID — not a canned response.
- Real card-height measurement via `getBoundingClientRect()` (not screenshot guessing) before and
  after `CARD-HEIGHT-001`'s fix: 531/324/392px → 531.25/531.25/531.25px.
- Real cold-start timing measurement (`COLDSTART-001`): 10 samples at 3s intervals confirming a
  bounded ~55-60s one-time delay, not an infinite loop.
- Zero horizontal overflow (`scrollWidth == clientWidth`) confirmed at 390×844, 1366×768,
  1440×900, and 1920×1080 for all pages checked.
