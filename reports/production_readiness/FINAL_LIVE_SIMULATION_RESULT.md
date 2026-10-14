# Final Live Simulation Result — Operational Evidence Run

**No source or test code was modified to produce this evidence.** Every
test executed below is an already-accepted, unmodified test file from
commit `06800b5`. This run exists purely to demonstrate the accepted
release candidate operating as a realistic staging environment and to
capture fresh operational evidence tied to that exact commit.

## 0. Exact release verified

| | |
|---|---|
| Git commit | `06800b5` (branch `integration/final-candidate-v2`) |
| Working tree state (this worktree) | clean at `06800b5` |
| `main` | unchanged at `10b487d` (confirmed before and after this run) |
| `stash@{0}` | untouched (confirmed before and after this run) |
| Free disk space (C:) before starting | 19GB — sufficient, no blocker |

**Docker image note**: the containers run in this simulation were built
from commit `6dd96b8` (one commit before `06800b5`). `git diff --stat
6dd96b8 06800b5` shows the only difference is the addition of
`FINAL_RELEASE_CANDIDATE.md`, a documentation file with zero effect on
application source, `Dockerfile`, or `requirements.txt` — so this image
is a functionally exact representation of `06800b5` for runtime
purposes. No rebuild was performed, per instruction to avoid an
unnecessary rebuild; this is disclosed rather than presented as a
literal `06800b5` build.

One infrastructure step was required and performed: the postgres named
volume left over from an earlier verification round (under the same
Docker Compose project name) had a different password baked into its
already-initialized data directory than this run's freshly-generated
one, causing the migration container to fail authentication on first
attempt. This is disposable staging infrastructure created by this same
verification effort (not user data) — the stale volume was removed and
the stack started clean. Not a defect in the release candidate itself.

## 1-2. Staging environment startup

PostgreSQL = **ready**. pgvector = **ready**. LMS/CMS simulator =
**healthy**. EduDSS = **healthy**, readiness = **ready**
(`{application, postgresql, pgvector: all ready}`). HTTP = **200**.
Docker runtime = **non-root** (`uid=999(edudss)`). All communication
between EduDSS and the LMS/CMS simulator used real HTTP sockets
throughout — no direct Python function-call substitution.

## 3-4. Two synthetic universities, onboarding

University A and University B, both provisioned on the same running
EduDSS instance/codebase. Each received: 1 admin, synced
lecturers/students/courses/enrollments/assignments/submissions/grades/
attendance/learning_activities/CMS content from the real simulator.
Full onboarding gate (admin+connector+mapping+sync) passed for both.
Confirmed via the 34-step narrative (steps 4-15) — **VERIFIED**.

## 5. Multi-tenancy / data isolation

Using the genuine non-superuser app role: University A's connection
sees **zero** University B rows on cross-tenant SELECT (step 16 of the
34-step narrative; Part F3 additionally re-confirms the RLS policy is
present and enforced after a real restore). **Successful unauthorized
cross-tenant operations: 0.** — **VERIFIED, no release blocker found.**

## 6. Realistic LMS activity

Student/lecturer/CMS activity flowed through the real HTTP connector
(steps 13-14, 20-22, 27-28). Pagination, incremental sync, persistent
cursor (`integration_sync_states`), and idempotent resync after a real
simulator restart all confirmed — **0 duplicate records** on repeat
sync. — **VERIFIED**.

## 7. Webhook simulation

Real HMAC-SHA256-signed webhook delivery, tenant-validated, durable
inbox (`webhook_inbox`), event_id idempotency, bounded retry — step 21
and Part F1. Duplicate and out-of-order handling verified in the
underlying accepted A+B connector suite (cited, not re-invented this
round) — **duplicate mutation = 0**, older events do not overwrite
newer valid state. — **VERIFIED**.

## 8. CMS -> RAG -> pgvector, including deletion lifecycle

Real document ingestion -> embedding -> 384-dim vector -> pgvector
storage -> server-side `<=>` retrieval, confirmed correct-tenant
retrieval (step 22). Content update via `content.updated` correctly
invalidates the old vector and re-indexes (step 20-22). **Deletion
lifecycle**: Part C — content confirmed indexed, invalidated via the
real (only-implemented) `invalidate_content()` primitive, then
confirmed **zero** stale results on a fresh retrieval query.
Cross-tenant RAG retrieval was not independently re-tested this exact
round (covered by the accepted A+B suite's tenant-scoped vector search
tests, cited) — **VERIFIED** (creation/update/invalidation, this
round's own live evidence) / **PARTIALLY_VERIFIED** (cross-tenant RAG
isolation specifically, evidence cited from the accepted suite rather
than re-run this exact session).

## 9. ML / DSS simulation

Real classification (RandomForest, 5-fold CV)/regression/clustering run
on the project's own synthetic dataset (1000 rows), registered through
the real model governance path (candidate -> Admin-promoted ->
production, genuinely audited). Drift evaluated in both directions
(no-drift and a controlled synthetic shift, both correctly classified).

| Metric | This run | Thesis-reported (historical) | Threshold |
|---|---|---|---|
| Accuracy | 0.850 | 0.875 | >= 0.82 (met) |
| F1-macro | 0.518 | not reported | >= 0.78 (NOT met) |
| RMSE (raw / normalized) | 0.716 / 0.140 | 0.074 | <= 0.35 (ambiguous vs. raw; see note) |
| R² | 0.102 | 0.992 | >= 0.80 (NOT met) |
| Silhouette | 0.105 | 0.412 | >= 0.40 (NOT met) |
| Davies-Bouldin | 2.200 | 0.831 | (report only) |

**These are current-simulation results from a deliberately minimal,
independently-built verification pipeline — NOT the production
`ClassificationTrainer`/`RegressionTrainer` classes** (UI-coupled, no
headless entry point exists in this codebase). They are clearly
distinct from, and must never overwrite, the historical thesis-reported
figures in the table above. The gap between this round's numbers and
the thesis figures is attributable to this verification pipeline's
simplicity (no feature engineering, no class balancing), not a
regression in the real system — see `METRICS_THESIS_VS_CURRENT.md` for
the corroborating finding that a genuinely-persisted production
training artifact's RMSE/R² (0.0738/0.9923) DOES match the thesis
figures. **What this section's real evidence proves**: the ML
governance machinery (provenance, registration, Admin-gated promotion,
audit, drift detection) genuinely works end to end — **VERIFIED**. The
raw ML quality numbers from this round's pipeline — **NOT
representative of production quality, disclosed as such**.

## 10. Student AI Advisor

Student question -> `LLMGateway.stream_generate()` (the accepted,
centralized AI Gateway — no call bypassed it) -> real answer ->
consultation record persisted and read back -> token/quota accounting
read back. No real external AI provider credentials were configured
this engagement; the accepted Production Demo Policy (simulated
fallback) path was used throughout. **Label: SIMULATED_AND_VERIFIED.**
Live Gemini/Groq/OpenAI availability is **not claimed**.

## 11. Role journeys

| Role | Journey tested | Result |
|---|---|---|
| Student | Login (auto-provision), nav correctly excludes Dashboard/Warehouse, AI advisor locked to own student ID (no picker) | **PASS** (3/3) |
| Lecturer | Login, nav includes AI Advisor tab, dashboard analytics sections render, can choose any student (unlike a student) | **PASS** (4/4) |
| Admin | Login, sees full AI provider config + connection test, sees the model-promote button for a non-production model | **PASS** (3/3) |

All 10 role-journey E2E tests passed against this exact live stack.

## 12. Failure simulation + restarts

| Scenario | Result |
|---|---|
| 401 (invalid token) | PASS — real HTTP, `status==401` |
| 403 (tenant mismatch) | PASS — real HTTP, `status==403` |
| 429 (rate limit) | PASS — real HTTP |
| 500 (simulated) | PASS — real HTTP, `retryable` flag confirmed |
| Timeout | PASS — real short-timeout client |
| Malformed payload | PASS — handled without a crash |
| Duplicate webhook | PASS (cited: accepted A+B suite + this round's Part F1) |
| Out-of-order webhook | PASS (cited: accepted A+B suite) |
| Temporary LMS outage (simulator restart) | PASS — step 27, real container restart |
| **PostgreSQL restart** | PASS — step 25, data confirmed intact after |
| **LMS/CMS Simulator restart** | PASS — step 27, idempotent resync confirmed after (0 duplicates) |
| **EduDSS application restart** (new this round) | PASS — real `docker restart` of the app container; students=48, predictions=71394, webhook_inbox=6 identical before/after; HTTP 200 and healthy again |

**Persistent-data loss across all restarts: 0.**

## 13. Security / data protection gate

Referencing the already-accepted technical control baseline
(`FINAL_COMPLIANCE_TRACEABILITY_MATRIX.csv`, `FINAL_DATA_PROTECTION_MATRIX.csv`,
produced in the prior round, not re-derived from scratch here):

- CRITICAL unresolved security defects: **0**
- HIGH unresolved security defects: **0**
- Cross-tenant leakage this run: **0**
- Privilege escalation: **0** (Admin-only `promote()` gate confirmed
  live in role journeys above)
- Plaintext password storage: **0** (PBKDF2-HMAC-SHA256 + per-user
  salt, code-reviewed, unchanged)
- Password/hash/salt/API-key in logs: **0** (spot-checked this round's
  container logs — none found)
- Secrets committed to git: **0** (`.gitignore` coverage confirmed
  unchanged)
- SQL injection resistance: **re-confirmed this run**
  (`test_sql_injection_resistance.py`, 1/1 passed, live against this
  exact stack)

This is a **technical evaluation against selected controls** from OWASP
ASVS 5.0, ISO/IEC 27001:2022, NIST authentication guidance, and Vietnam
Law 91/2025/QH15 — see `FINAL_COMPLIANCE_TRACEABILITY_MATRIX.csv` for
exactly which ones. **No certification of any kind is claimed.**

## 14. Concurrency (re-measured fresh this run)

| Concurrency | Error rate | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|
| 1 | 0% | 9.5ms | 14.8ms | 15.3ms | 89.6/s |
| 5 | 0% | 14.9ms | 45.6ms | 57.8ms | 235.5/s |
| 10 | 0% | 30.9ms | 68.6ms | 91.2ms | 254.5/s |
| 25 | 0% | 53.6ms | 261.7ms | 278.3ms | 203.6/s |
| 50 | 0% | 51.0ms | 452.4ms | 538.9ms | 308.1/s |

**SLO held through concurrency=50 this run** (p95 stayed under the
500ms threshold at every level, closer to the boundary at 50 than the
immediately-prior round's measurement). No level produced an error or
environment instability, so escalation stopped at the suggested ceiling
of 50 rather than being pushed further. **Never claim 20,000 concurrent
users** — this is the real, measured, single-development-machine
boundary.

## 15. Soak test (re-measured fresh, >= 5 minutes)

Duration: 300.9s. Operations: 70,887. Errors: 0 (0.00%). p50=17.28ms,
p95=51.45ms. Memory stable (1.19-2.00GB, no leak trend — the initial
1.19GB sample reflects the app container having just restarted for the
EduDSS-restart test immediately before this run). **Unexpected
application errors: 0. Data corruption: 0. Cross-tenant leakage: 0.**

## 16. 20K batch inference

Elapsed: **3.0343s**. Throughput: **6,591.4 predictions/sec**.
**PASS** (<5s, >5,000/sec). **This is 20,000-record batch inference —
never 20,000 concurrent users.**

## 17. Backup/restore drill

Real `pg_dump` (owner role) -> SHA-256 checksum verify -> restore into
a genuinely new, empty database -> full inventory independently queried
against the restored copy: organizations=1, users=7, students=4,
courses=2, cms_content=2, webhook_inbox=3, integration_sync_states=11,
predictions=1, consultations=1, audit_logs=1, rag_documents=2 — all
present and correct. RLS policy confirmed present on the restored
schema; pgvector `<=>` retrieval confirmed working against the restored
database.

| | |
|---|---|
| Backup duration | 0.344s |
| Backup size | 246,348 bytes |
| Restore duration | 1.516s |
| Verification (inventory query) duration | ~0.12s |

**Explicitly NOT covered by this database backup**: model artifact
`.joblib` files, training datasets, secrets/runtime configuration,
application logs — see `FINAL_RECOVERY_MATRIX.csv` (prior round,
unchanged) for the full per-asset breakdown. **Full disaster recovery
remains PARTIAL**, not YES — non-DB assets are separately recoverable
via `ops/non_db_recovery.py` but were not exercised in combination with
this drill this session.

## Summary of what changed vs. the prior verification round

Nothing in the application changed — this was a pure re-execution of
already-accepted tests against the accepted candidate to produce fresh,
independently-timestamped operational evidence. Measured figures (ML
metrics with the same fixed seed, concurrency ladder, soak, 20K, backup
size) are consistent with the prior round within expected run-to-run
variance; no new defect was found; **no code or test modification was
required or made**.
