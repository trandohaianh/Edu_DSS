# Consolidated Test Results

All figures below are real pytest/Playwright output captured during
this engagement, cited to the report or commit where each run is
recorded — none are estimated or rounded up.

## Non-E2E automated suite

| When | Result | Citation |
|---|---|---|
| After Stage 4's CONCUR-001 fix | **716 passed, 2 skipped, 0 failed** (145.18s) | `WORKSTREAM_D_SCALE_RECOVERY.md` §9 |
| Stage 5 worktree, post all fixes | **570 passed, 148 skipped (env-gated, not exercised in that particular invocation), 0 failed, 1 deselected** (99.48s) | `FINAL_STAGING_SIMULATION.md` §7 |

The skip-count difference between these two runs is fully explained:
Stage 5's quick regression check did not set every `*_OWNER_URL`/
`*_DATABASE_URL` environment variable that Stage 4's full run set, so
more env-gated integration tests were skipped rather than exercised —
this does not indicate any test was removed or any coverage was lost;
the same underlying application code passed 0-failure in both runs.

## End-to-end (Playwright) suite

39/39 passing at the last full run across Stages 1-3 (see
`ABC_INTEGRATION_ACCEPTANCE.md`, `UNIVERSITY_ONBOARDING_ACCEPTANCE.md`,
`ABC_ONBOARDING_INTEGRATION.md`). One pre-existing, unrelated test
(`test_lecturer_learning_explainer_renders_without_traceback`) is a
documented flaky Playwright timing issue, observed 3 times across 3
independent worktrees, always passing on isolated re-run, always on a
code path untouched by this engagement's changes — never silently
ignored, always investigated and attributed each time it appeared.

## Dedicated regression/capacity/soak evidence

| Test | Result | Citation |
|---|---|---|
| CONCUR-001 regression (20 concurrent threads, shared training_id) | 0 errors, 1 ModelVersion row, 20 Prediction rows | `WORKSTREAM_D_SCALE_RECOVERY.md` §2 |
| University-scale concurrency profile | SLO met at concurrency=10 (p95=207.8ms); violated at 25 (p95=595.3ms) | `WORKSTREAM_D_SCALE_RECOVERY.md` §3 |
| Multi-university concurrency profile | 4 tenants, fair distribution (100/105/103/117), zero cross-tenant visibility | `WORKSTREAM_D_SCALE_RECOVERY.md` §4 |
| Short soak (300s @ concurrency=10) | 68,454 operations, 0 errors, p95 stable ~50ms, no memory-leak trend | `WORKSTREAM_D_SCALE_RECOVERY.md` §6 |
| 20K batch inference | 2.6214s, 7,629.6 predictions/sec | `WORKSTREAM_D_SCALE_RECOVERY.md` §8 |
| Final staging narrative (Stage 5) | **34/34 steps PASS**, live Docker stack | `FINAL_STAGING_SIMULATION.md` §2, evidence: `final_staging_evidence/narrative.json` |
| Non-DB recovery manifest | 6/6 unit tests; live demo 89/89 files verified | `WORKSTREAM_D_SCALE_RECOVERY.md` §1 |
| DB backup + verify + **restore-to-fresh-database** | Real backup, checksum match, restored DB independently queried and confirmed populated | `FINAL_STAGING_SIMULATION.md` §2 step 29-30 |
| Failure injection | 10 previously-verified scenarios cited + 2 new corrupted-backup detection tests, all passing | `WORKSTREAM_D_SCALE_RECOVERY.md` §7 |

## What was never run

- No hosted/cloud CI pipeline execution (all testing was run locally by
  this engineering session).
- No load test at national/ministry scale (explicitly a projection, see
  `NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md`).
- No re-verification of the thesis's own ML experiment metrics
  (accuracy, K-Means k, Silhouette, DBI) against real data — see
  `METRICS_THESIS_VS_CURRENT.md`.
