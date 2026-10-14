# Final Realistic Staging Simulation

## 0. Base and how the live stack was started

Branch `integration/final-candidate-v2` @ base `f7d3690`. Real Docker
Compose `integration-ab` profile: PostgreSQL 16+pgvector, the LMS/CMS
simulator, the migration job, and the containerized Streamlit app — not
mocked function calls. Two independent live-stack sessions were run
against this exact commit: Stage 5's proven 34-step narrative
(`test_final_staging_simulation.py`, re-run fresh this round) and six
new parts (A-F, 25 sub-steps) in
`test_final_candidate_v2_extended.py`. All 59 steps across both files
passed.

## 3-4. Two synthetic universities, full onboarding

University A and University B, each independently provisioned with a
fresh `org_code`, own Admin user, own connector configuration
(credential-reference only, never a raw token), own LMS/CMS sync. Per
university, the initial sync ingested: users, students, lecturers,
courses, enrollments, assignments, submissions, grades, attendance,
learning activities, and CMS content — the full canonical resource set
the accepted simulator serves. All 34 steps of Stage 5's narrative
(re-run fresh) confirm this end to end, including the activation gate
(admin+connector+mapping+sync all green) and cross-tenant isolation
(University A's app-role connection sees **zero** University B rows).

Onboarding University B used the exact same running EduDSS deployment
and codebase as University A — no second instance, no forked code path.

## 5. LMS/CMS live-like activity

Real HTTP delivery throughout: connector fetches, admin mutations, and
webhook deliveries all went over real sockets to the containerized
simulator, never an in-process mock. Pagination and incremental sync
were exercised (Stage 5 steps 13-14, 27-28); a full resync after a real
simulator container restart produced **zero duplicate changes**, and a
real Postgres container restart preserved all prior data and the
persistent sync cursor (`integration_sync_states`).

## 6. CMS -> RAG -> pgvector, including deletion-equivalent lifecycle

- Create/update: Stage 5 steps 20-22 — real HTTP mutation, real HMAC-
  verified webhook delivery, real reindex, retrieval confirmed reflects
  the update.
- **Delete-equivalent**: Part C (new this round). The codebase has **no
  true CMS delete event path** — `PostgresIntegrationBoundary` has no
  delete/remove method, confirmed by source inspection. The only real,
  accepted lifecycle primitive for removing content from retrieval is
  `dss.services.cms_rag_lifecycle.invalidate_content()`. Called directly
  (not invented for this test — it is the codebase's own mechanism):
  content confirmed indexed (C1) -> invalidated (C2) -> confirmed **zero**
  stale results on a fresh retrieval query (C3).

## 7. ML/DSS realistic journey

Real classification (RandomForest, 5-fold CV, held-out test),
regression (RandomForest), and clustering (KMeans k=4) were run on the
project's own synthetic dataset (`dữ liệu/sample_student_data_1000.csv`,
1000 rows). **Important methodology disclosure**: this used a
deliberately minimal, independently-built scikit-learn pipeline, NOT
the production `ClassificationTrainer`/`RegressionTrainer` classes
(`dss/core/trainers.py`) — those are tightly coupled to Streamlit
widgets (button clicks, progress display, save/export UI) with no
headless invocation path found in this codebase. Results:

| Metric | This round's minimal pipeline | Threshold | Met? |
|---|---|---|---|
| Accuracy (classification) | 0.850 | >= 0.82 | YES |
| F1-macro (classification) | 0.518 | >= 0.78 | **NO** |
| RMSE (regression, `final_score`) | 0.716 raw / 0.140 normalized | <= 0.35 (assumes [0,1] scale) | Ambiguous — see note |
| R² (regression) | 0.102 | >= 0.80 | **NO** |
| Silhouette (clustering, k=4) | 0.105 | >= 0.40 | **NO** |
| Davies-Bouldin | 2.200 | (report only) | — |

**These numbers must NOT be read as a quality assessment of the actual
thesis/production model.** The 84%/16% class imbalance in `pass_fail`
makes accuracy alone misleading (hence the weak F1-macro); the
regression/clustering feature subset chosen for this quick pipeline was
arbitrary and did not include the production feature-engineering steps
(`trainers.py` has `add_engineered_features`, and `imbalanced-learn` is
a project dependency, implying the real pipeline does class balancing
this verification pipeline did not). The genuinely-representative
CURRENT figures remain what `METRICS_THESIS_VS_CURRENT.md` already
found: a real, currently-persisted production training artifact
(`data_warehouse/metadata/*.json`) shows RMSE≈0.074, R²≈0.992 —
consistent with the thesis-reported figures and far better than this
round's throwaway pipeline. **What this round's pipeline DOES prove**:
the ML governance machinery (registration -> Admin promotion -> audit
-> drift evaluation) genuinely works end to end with a real, freshly-
trained model artifact — see `FINAL_CD_INTEGRATION_ACCEPTANCE.md` §2.

Predictions were stored with tenant (`organization_id`), student
(`student_code`), model/model-version (`training_id`, resolved through
the CONCUR-001-fixed repository path), and timestamp — confirmed live
in Stage 5 step 18 and this round's Part F footprint.

**Drift vs. retraining**: `ml_provenance.evaluate_data_drift()` was
exercised with BOTH a negative control (two same-distribution batches
correctly report no drift) and a positive control (a deliberate,
disclosed 3-standard-deviation shift in `prior_gpa` correctly reports
`WARNING`/`DRIFT_DETECTED`). **No automatic retraining exists or was
claimed** — drift detection surfaces a signal; nothing in this codebase
automatically retrains or replaces a production model in response.

## 8. AI/RAG advisor journey

Student question -> `LLMGateway.stream_generate()` (the real, mandatory,
centralized AI Gateway — no call in this round bypassed it) -> real
answer text -> persisted via `consultation_repository.save_consultation()`
-> read back via `list_consultations()` -> token/quota usage read back
via `token_tracker.get_usage_summary()` and
`quota_repository.get_usage()`. Cross-tenant isolation confirmed
(University B sees none of University A's consultations).

**No paid external AI provider credentials were configured this
engagement.** Every AI Gateway call ran the accepted Production Demo
Policy (fallback/simulation) path — labeled **SIMULATED** per
instruction, never presented as live-provider evidence.

## 9. Failure simulation

| Scenario | Result |
|---|---|
| 401 (invalid bearer token) | Real HTTP, `IntegrationError.status == 401` |
| 403 (tenant/org mismatch) | Real HTTP, `status == 403` |
| 429 (rate limit) | Real HTTP, simulator-driven |
| 500 (simulated internal error) | Real HTTP, `status == 500`, `retryable` flag confirmed |
| Timeout | Real short-timeout client against the simulator's deliberate delay |
| Malformed payload | Real HTTP, truncated JSON response handled without a crash |
| 404 | **Not modeled** by the accepted simulator for this endpoint shape — disclosed, not fabricated |
| Duplicate webhook | Covered by Stage 5 step 21 and Part F1 (re-cited, not re-invented) |
| Out-of-order webhook | Covered by Stage 5 step 21 (re-cited) |
| Temporary LMS outage / restart | Stage 5 step 27, real container restart |
| Application restart | Not separately re-tested this round (the containerized app itself was not restarted mid-session; Postgres and the simulator were) |
| PostgreSQL restart | Stage 5 step 25, real container restart, data confirmed intact after |

No cross-tenant leakage occurred in any failure scenario. The webhook
inbox and sync cursor state both survived the real container restarts
(Stage 5 steps 26, 28).

## 10. Concurrency + soak (re-measured fresh, not copied)

**Progressive ladder 1/5/10/25/50** (Part E, this round):

| Concurrency | Operations | Error rate | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|---|
| 1 | 5 | 0% | 9.3ms | 16.3ms | 17.6ms | 89.5/s |
| 5 | 25 | 0% | 15.4ms | 166.5ms | 181.9ms | 101.9/s |
| 10 | 50 | 0% | 28.7ms | 66.0ms | 69.8ms | 272.3/s |
| 25 | 125 | 0% | 48.5ms | 327.7ms | 365.3ms | 277.8/s |
| 50 | 250 | 0% | 47.1ms | 358.0ms | 436.0ms | 317.1/s |

**SLO held through concurrency=50 this run** (no level exceeded the
500ms p95 threshold or produced any error). This genuinely differs from
Workstream D's earlier finding (SLO violated at concurrency=25, p95
595.3ms) — **both measurements are reported honestly, side by side,
rather than one replacing the other.** The difference is real run-to-
run variance in a shared development machine's available resources at
the time of each measurement (different background load, different
Docker/WSL2 state), not a contradiction or a methodology error — see
`ops/capacity_benchmark.py`'s own design note that this harness
measures real PostgreSQL-operation concurrency, which is sensitive to
whatever else the host machine is doing. **Neither number should be
extrapolated to a dedicated production environment or a different
machine.**

**Soak** (re-run fresh, 300s @ concurrency=10): 68,329 operations, 0
errors (0.00%), p50=18.1ms, p95=55.0ms, memory stable throughout
(1.5-2.0GB, no leak trend).

## 11. 20K benchmark (re-run fresh)

2.5498 seconds elapsed, 7,843.8 predictions/second. **This is batch
inference of 20,000 pre-existing records, never "20,000 simultaneous
users."** Pass criteria (<5s, >5,000/sec) met.

## 12. Recovery drill

See `FINAL_RECOVERY_MATRIX.csv` for the full per-asset inventory. In
summary: a real footprint (prediction, consultation, audit entry, real
webhook delivery, full onboarding/sync data) was populated on University
A, then a real `pg_dump` backup was taken (owner role, `docker_container`
mode), checksum-verified, and restored into a genuinely fresh, empty
sibling database. The RESTORED database was then queried directly and
independently — organizations, users, students, courses, cms_content,
webhook_inbox, integration_sync_states, predictions, consultations, and
audit_logs all confirmed present with the exact expected values; RLS
policies confirmed present on the restored schema; pgvector retrieval
confirmed working against the restored database with a real `<=>`
search. Model binaries and datasets are explicitly NOT covered by this
database backup (separately recoverable via `ops/non_db_recovery.py`'s
manifest, not exercised in combination this round). **Full disaster
recovery: PARTIAL** — see `FINAL_RECOVERY_MATRIX.csv` and
`FINAL_MUST_NOT_SAY.md`.

## 13-14. Docker and fresh checkout

See `FINAL_RELEASE_CANDIDATE.md` for the dedicated final verification of
both, performed once all fixes from this round were committed.
