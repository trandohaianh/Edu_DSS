# Phase 12A main drift audit and revalidation

## Main drift

| Item | Evidence |
|---|---|
| Old accepted main | `d8d3b29` |
| Current main at audit | `4a9d5766493050bcc0213de42d4ff200741c1295` |
| Ancestry | `git merge-base --is-ancestor d8d3b29 4a9d576` succeeded |
| Added commit | `4a9d576` by `trandohaianh <anhhaduc7777@gmail.com>`: `docs: final integration acceptance report for Phase 1B+8A merge to main` |
| Drift file | Added `app/reports/production_readiness/FINAL_INTEGRATION_ACCEPTANCE.md` (150 lines); no source, test, configuration, runtime, generated, Docker, security, RLS or persistence file changed |
| Reason main moved | Git proves only that the final Phase 1B+8A acceptance report was committed after `d8d3b29`; it does not prove any further intent |

### Main drift table

| Commit | Purpose shown by Git | Files | Touches Observability integration point? | Risk |
|---|---|---|---|---|
| `4a9d576` | Add final Phase 1B+8A acceptance report | `app/reports/production_readiness/FINAL_INTEGRATION_ACCEPTANCE.md` | NO | LOW, documentation-only drift |

No drift overlap with `run_dss.py`, `dss/core/models.py`, `dss/services/llm_gateway.py`, `dss/services/vector_store.py`, `dss/tabs/ml_hub.py`, `logging_config.py`, `log_redaction.py`, Observability/readiness modules, Dockerfile, `.dockerignore`, requirements, database/RLS or pgvector code.

## Reconciliation

New branch/worktree: `integration/observability-12a-revalidated` / `D:\KLTN\edudss-observability-revalidated`, created at exactly `4a9d576`. Cherry-picked accepted source/test commits `9fdd991` -> `a4cf76a` and `f949325` -> `f7079c9`. The old `51aca74` commit was a report-only commit and was not blindly cherry-picked. A new revalidation report records this gate.

Functional revalidation commit: `62263448fd9c223f52ac3bbf38d8c0f2764e2ad5` (includes the minimal DB-password redaction fix and its test). The branch tip may include a later report-only commit containing the final Docker evidence; the functional tree remains the one tested here.

The initial tree comparison against old accepted candidate `51aca74` had only two documentation differences: the new main acceptance report is present, and the old Phase 12A integration report is absent. Every original source/test integration point was byte-identical to the previously accepted candidate. Classification for each named integration point was **SAFE**; no textual or semantic reconciliation was needed for main drift. This was established by `git diff --name-status 51aca74..f7079c9`, not by assuming that a clean cherry-pick proves semantic safety.

A separate privacy gate on the new candidate found a pre-existing redaction gap: `db_password=` and `database_password=` were not matched by the Phase 8A regex. This is **MANUAL_RECONCILIATION_REQUIRED** for the logging/redaction pipeline, discovered during this gate rather than caused by the documentation-only main drift. The minimum fix extends the label allowlist in `dss/security/log_redaction.py`; a new test checks both labels. No real credential was printed. This change is explicitly additional to the two accepted Observability commits and requires its own full verification below.

## Verification

| Gate | New candidate result |
|---|---|
| Fast precheck | `compileall dss tests` PASS; `git diff --check` PASS; initially 613 tests discovered; original Phase 12A + Phase 8A security **27 passed** |
| Full non-E2E excluding separate 20k benchmark, initial candidate | **572 passed, 1 skipped, 0 failed** against configured PostgreSQL and non-superuser app role |
| Full non-E2E after redaction fix | **573 passed, 1 skipped, 0 failed** against the same real PostgreSQL setup |
| E2E, initial candidate | **39 passed, 0 failed** after supplying an ignored `.venv` junction for the test fixture |
| E2E after redaction fix | **39 passed, 0 failed** from a new server/session |
| PostgreSQL schema | **9 passed**, real PostgreSQL container |
| RLS adversarial | **6 passed**, including DELETE; application role `edudss_app` verified `rolsuper=false` |
| pgvector | **11 passed**, extension `vector` present |
| Phase1B+8A integration | **8 passed** |
| Phase 12A | **8 passed** original plus **6 passed** integration proofs |
| Phase 8A security | **19 passed** initially; **20 passed** with the added DB-password test |
| All separate DB/security/Observability gate files combined | **67 passed, 0 failed** initially; **68 passed, 0 failed** after the added test |
| Real RAG composition | `test_phase12a_integration.py` **6 passed**: real embedding/model load, pgvector retrieval, malicious chunk boundary, correlation, safe logs and failure behavior |
| Fresh detached checkout | Final functional commit `6226344`: imports PASS, **614 tests discovered**, Streamlit AppTest 0 exceptions/errors; prior committed checkout also returned HTTP 200 and `/_stcore/health` `ok` |
| Docker | Rebuilt cache-assisted from fresh detached `6226344`: `uid=999(edudss)`, healthy, HTTP 200, PostgreSQL/pgvector readiness ready, AppTest 0 exceptions/errors, structured log/redaction PASS including DB password labels |
| 20k benchmark | **KNOWN_ENVIRONMENT_SENSITIVE_PERFORMANCE_FAILURE**: one pass and two measured failures; see below |

The first E2E attempt had 39 fixture errors because the test hardcodes `.venv/Scripts/python.exe` adjacent to its worktree. A local ignored junction to the shared Python environment was created **only in this revalidation worktree**; it is dependency setup, not committed application source. E2E was rerun and all 39 passed. No test assertion, benchmark threshold, source file or Docker file was modified to address this fixture path.

Fresh checkout validation used separate detached worktrees from committed `5d2418b` and then committed `6226344`, with the shared Python dependency environment but no source from the developer worktree. Docker was built from each detached committed checkout; dependency and apt layers were cached, so these are **not** claimed as no-cache builds. The final container's `readiness()` reported PostgreSQL and pgvector ready using the real non-superuser `edudss_app` role; `PgVectorStore` connected and listed documents. Streamlit returned HTTP 200 and `/_stcore/health` `ok`. The on-disk `technical.log` contained parseable JSON with correlation ID, backend and duration. Synthetic markers for password, `db_password`, API key, Authorization bearer, access/refresh/session tokens, prompt, student ID and email were absent after redaction; no real secret values were printed. Real RAG composition tests separately asserted no raw malicious document or vector in logs.

### Unchanged 20k benchmark

Threshold: elapsed **< 5 seconds** AND throughput **> 5,000 predictions/second**. The benchmark directly calls `prod_model.predict(X_pred)` and does not call `predict_with_metrics`; the Observability instrumentation is outside this timed path.

| Run | Elapsed | Throughput | Result |
|---|---:|---:|---|
| 1 (`-q`) | Telemetry captured by pytest, not printed | Telemetry captured by pytest, not printed | PASS |
| 2 (`-q -s`) | 4.4717 s | 4,472.6/s | FAIL throughput |
| 3 (`-q -s`) | 4.0622 s | 4,923.5/s | FAIL throughput |

The two printed measurements both meet latency but miss throughput; the first run passed. This variation on the same committed code supports **KNOWN_ENVIRONMENT_SENSITIVE_PERFORMANCE_FAILURE**, tracked separately from functional acceptance. No threshold or implementation was changed to make it pass.

## Privacy and user state

`stash@{0}` was only listed to confirm its existence; it was not applied, popped, dropped, rewritten or inspected. Original main untracked files were not changed. No merge into main was attempted.

## Known limitations and remaining blockers

- Process-local metrics and Streamlit rerun-scoped correlation remain architectural limitations documented in `PHASE12A_OBSERVABILITY.md`; no Prometheus/OpenTelemetry exporter or cross-process trace propagation is claimed.
- The HTTP Streamlit health endpoint proves server liveness. Readiness was checked separately with real PostgreSQL and pgvector; no paid AI provider calls were made.
- Direct provider functions that catch their own errors may emit a completed-stream metric; the gateway's per-attempt error counter captures caught provider failures.
- The unchanged 20k benchmark is environment-sensitive and failed two measured throughput runs despite one passing run. It remains a separate performance concern, not a functional/security regression caused by this port.
- Final Docker verification is complete on the committed functional candidate `6226344`; a later report-only commit does not change runtime source. No merge into main is authorized by this report.
