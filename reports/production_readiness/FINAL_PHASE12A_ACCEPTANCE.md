# Final Phase 12A acceptance

## Merge and provenance

| Item | Result |
|---|---|
| Pre-merge main | `4a9d5766493050bcc0213de42d4ff200741c1295` |
| Rollback tag | `pre-observability-12a-final` -> `4a9d5766493050bcc0213de42d4ff200741c1295` |
| Revalidated integration | `b852b638e80d74343e09606c46cf290d33ab03a4` |
| Merge commit | `c857ce4aea8f78a2731a20a0d289005239bd4db5` |
| Merge parents | `4a9d5766493050bcc0213de42d4ff200741c1295`, `b852b638e80d74343e09606c46cf290d33ab03a4` |
| Merge method | `git merge --no-ff integration/observability-12a-revalidated` |

This report is a separate documentation commit after the verified merge. The final main HEAD is recorded in the final response and Git history; the tested functional tree is the merge commit above.

## Verification from the committed merge

A fresh detached worktree at `D:\KLTN\edudss-observability-merged-fresh` was created from the exact merge commit. No source or tests were copied from another worktree. An ignored `.venv` junction supplied the existing E2E fixture's hard-coded interpreter path. A temporary AppTest data directory was created only in this fresh worktree. Neither is required application source. `compileall dss tests run_dss.py`, test discovery (614 tests), and `git diff --check HEAD^ HEAD` passed. Importing the security, observability, health, RAG, and vector modules passed. Direct import of `run_dss.py` outside Streamlit raised a session-state error; the supported Streamlit entry point passed AppTest with 0 exceptions and 0 errors, and the running application returned HTTP 200 and `/_stcore/health` = `ok`.

| Gate | Post-merge result |
|---|---|
| Non-E2E, excluding separate load benchmark | **573 passed, 1 skipped, 0 failed** |
| E2E | **39 passed, 0 failed** |
| PostgreSQL schema | **9 passed** |
| RLS, including DELETE | **6 passed** |
| pgvector | **11 passed** |
| Phase 8A security | **20 passed**; includes `db_password=` and `database_password=` regression test |
| Phase 1B + 8A integration | **8 passed** |
| Phase 12A original / integration | **8 / 6 passed** |
| Combined DB/security/Observability gate | **68 passed** |

The first non-E2E attempt produced 573 passes and one skip but a teardown pollution-guard error because a concurrent *direct import* of the Streamlit entry point created `users.json` in the test worktree. The suite was rerun alone with no concurrent application invocation and passed 573/1/0. The error was in the verification procedure, not a Phase 12A regression. The direct-import result is not used as startup evidence.

The real RAG composition test passed in the six Phase 12A integration proofs. It uses a real embedding model, PostgreSQL with pgvector, tenant-scoped retrieval, correlation context, timing, a malicious retrieved chunk, and the AI prompt boundary. It asserts that tenant isolation holds, `AI_SYSTEM_POLICY` survives, malicious document instructions remain untrusted content, and logs omit raw malicious text and embedding data. RLS tests exercise a non-superuser application role. These checks do not establish complete prompt-injection protection.

## Docker and operational behavior

The image `edudss-observability-merged:final` was built from the fresh merge worktree with cached dependency layers and no Dockerfile or `.dockerignore` edits. The build preceded AppTest's temporary data directory; `.dockerignore` excludes `.venv` and `data_warehouse/`. The container `edudss_phase12a_final` ran as `uid=999(edudss)`, reported healthy, and returned HTTP 200 and `/_stcore/health` = `ok`. With pgvector required, in-container readiness reported application, PostgreSQL, and pgvector **ready** using the non-superuser application database role. AI configuration and model artifacts were optional and unavailable in this smoke environment.

Representative `technical.log` lines parsed as structured JSON. A real observed event contained correlation ID, backend, operation, outcome, and `duration_ms`. Synthetic password, `db_password`, API key, bearer, access/refresh-token, and student-email markers were absent after redaction. Security and RAG composition tests additionally check prompt/document/vector leakage. No real secret values were printed. Structured logging, correlation IDs, AI gateway metrics, RAG retrieval/index timing, ML metrics, and readiness are covered by the original eight and six integration Phase 12A tests.

## Separate 20k performance benchmark

The unchanged benchmark requires **elapsed < 5 s AND throughput > 5,000 predictions/s**. The single post-merge measurement was **4.0797 s** and **4,902.4 predictions/s**: the throughput assertion failed. Earlier revalidation of the same functional code had one pass without printed timing and measured failures at 4.4717 s / 4,472.6/s and 4.0622 s / 4,923.5/s. Classification: **KNOWN_ENVIRONMENT_SENSITIVE_PERFORMANCE_FAILURE**. No test threshold or implementation was changed for this gate.

## Limits and remaining production work

Metrics are process-local; Streamlit reruns scope correlation, and there is no Prometheus/OpenTelemetry exporter or cross-process trace propagation. Streamlit health proves liveness; PostgreSQL/pgvector readiness was verified separately. No paid AI provider call was made. Some provider functions that catch their own errors may record a completed-stream metric; the gateway's per-attempt error counter captures caught failures. The 20k throughput gate remains a visible performance blocker for production acceptance. Phase 12A functional/security merge acceptance is **PASS**, with that benchmark tracked separately.

The user's `stash@{0}` and untracked files in the original main worktree were neither applied nor deleted. No generated runtime data was committed.
