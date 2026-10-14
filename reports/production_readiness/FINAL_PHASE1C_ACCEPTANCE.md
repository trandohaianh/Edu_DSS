# Final Phase 1C acceptance — persistence runtime cutover

## Merge and provenance

| Item | Result |
|---|---|
| Pre-merge main | `451eb124dba05608f36b4ac52c924869ad3b0390` |
| Rollback tag | `pre-phase1c-persistence` -> `451eb124dba05608f36b4ac52c924869ad3b0390` |
| Accepted branch | `persistence/phase1c-runtime-cutover` |
| Accepted candidate | `03add02bfea38f6aaddd0c8f3221fa8b760b8bb0` |
| Code commit | `72233aff0029250be257cefed9f24167c5de332e` |
| Merge commit | `364bb171a8360d8a506aea16197aa794af225f51` |
| Merge parents | `451eb124dba05608f36b4ac52c924869ad3b0390`, `03add02bfea38f6aaddd0c8f3221fa8b760b8bb0` |
| Merge method | `git merge --no-ff persistence/phase1c-runtime-cutover` |

This report is a separate documentation commit after the verified merge. All verification
below was re-run from the merge commit itself, not reused from the candidate branch.

## Verification from the committed merge

A fresh detached worktree at `D:\KLTN\edudss-phase1c-merge-fresh` was created from the exact
merge commit (`git rev-parse HEAD` confirmed `364bb17`). An ignored `.venv` junction supplied
the shared interpreter. All module imports (`dss.db.models`, all four new repositories,
`auth_service`, `token_tracker`, `admin_ai_config`, `warehouse`, `persistence_config`)
succeeded cleanly; 650 tests were discovered. A fresh PostgreSQL database migrated zero to
head with `alembic upgrade head` (5 migrations, ending at `797f72d1c666`), created all 27
tables including the two new Phase 1C tables, and had the `pgvector` extension present.
`streamlit run dss/main.py --server.headless true` returned HTTP 200 on `/`,
`/_stcore/health`, and `/_stcore/host-config`, with no errors in the startup log. The fresh
worktree's own non-E2E suite passed 610/1 skipped, identical to the accepted candidate.

## Migration graph

| Check | Result |
|---|---|
| Migration `797f72d1c666_ai_token_usage_and_admin_ai_config.py` present | Yes |
| `alembic heads` | Single head: `797f72d1c666` |
| Migration history | `4915552f6063` -> `cbae9b411ed5` -> `830742fd75d4` -> `f0b43f540e41` -> `797f72d1c666`, linear, no branch points |
| Existing accepted database (`edudss_pg_phase1b`) -> head | Already at head; idempotent, no drift |
| Empty database -> head | Clean, all 5 migrations applied in order, 27 tables, `pgvector` present |
| Previously accepted migrations edited | No |

## New live persistence — non-superuser application role

All flows below were run against the merged main state using `edudss_app` (a genuine
non-superuser Postgres role), never the schema-owner/superuser role, through the actual
public functions the application calls:

| Flow | Result |
|---|---|
| Users/auth: create | PASS |
| Users/auth: authenticate success | PASS |
| Users/auth: authenticate failure (wrong password rejected) | PASS |
| Users/auth: role preservation (`Giảng viên / CVHT` round-trips unchanged) | PASS |
| Users/auth: organization association (user resolvable only under its own org; cross-tenant read returns none) | PASS |
| Users/auth: restart persistence (PostgreSQL container restarted; user row, role, and grants all survived) | PASS |
| Activity history: write + read | PASS |
| AI token usage: write + read | PASS |
| Admin AI configuration: write + read | PASS |

Repeated a second time entirely inside the Docker image built from the current committed
`Dockerfile` — same nine checks, same result.

## RLS — real adversarial checks, non-superuser role

| Check (attacker session set to a different `app.organization_id`) | Result |
|---|---|
| `users` SELECT cross-tenant | Blocked (0 rows) |
| `users` UPDATE cross-tenant | Blocked (0 rows affected; victim row unchanged, verified by direct read) |
| `users` DELETE cross-tenant | Blocked (0 rows affected) |
| `activity_logs` INSERT with victim's `organization_id` | Blocked by RLS `WITH CHECK` (insert raised, no row created) |
| `activity_logs` SELECT cross-tenant | Blocked (0 rows) |
| `admin_ai_config` SELECT cross-tenant | Blocked (0 rows) |
| `ai_token_usage` SELECT cross-tenant | Blocked (0 rows) |

No schema-owner/superuser connection was used as evidence for any of the above. Re-confirmed
a second time inside the Docker container (SELECT cross-tenant blocked, pgvector present).

## Fallback policy

`POSTGRES_PRIMARY_WITH_FALLBACK` unchanged for all four domains: `EDUDSS_<FEATURE>_STORE`
gate, `local` default, `postgres` opt-in, no dual-write. Re-verified from the merged state:
the full domain-specific test suites (users, activity log, AI token usage, admin AI config,
`persistence_config`) — including each domain's "does not dual-write to local JSON" and
"local mode unaffected by default" tests — all pass (42/42). Fallback policy was not changed
during the merge.

## Observability / privacy

Phase 12A suites (`test_observability_phase12a.py`, `test_phase12a_integration.py`) pass
14/14 on the merged state — unaffected. No password, password hash, password salt, API key,
database credential, or student/private payload appears in `technical.log` or in any of the
four new tables — verified by the existing schema-level and log-content tests
(`test_authenticate_never_logs_password_or_hash_via_postgres`,
`test_never_persists_secrets_or_api_keys` for both AI token usage and admin AI config).

## Performance

`test_20000_students_batch_prediction_benchmark` run unmodified on the merged state:
**PASSED** (elapsed < 5s, throughput > 5,000 predictions/sec — unchanged threshold, benchmark
itself untouched).

## Regression — from the merged state

| Suite | Result |
|---|---|
| Non-E2E (`pytest tests --ignore=tests/e2e`) | **611 passed, 0 skipped** |
| E2E | **39 passed** |
| PostgreSQL / RLS (`test_db_row_level_security.py`) | **6 passed** |
| pgvector | Verified via existing PostgreSQL/pgvector suite inside the 611 (pgvector-specific tests included); extension presence re-confirmed directly and inside Docker |
| Security | Included in the combined 32-test integration run below |
| Phase1B+8A + Phase12A + Security (`test_integration_phase1b_security8a.py`, `test_observability_phase12a.py`, `test_phase12a_integration.py`, `tests/security`) | **32 passed** |
| Phase1C (new domain tests: users, activity log, AI token usage, admin AI config, persistence_config gate) | **42 passed** |

None of these numbers were reused from the pre-merge candidate; all were re-run against the
merge commit `364bb17`.

## Fresh checkout

Detached worktree `D:\KLTN\edudss-phase1c-merge-fresh` from `364bb17`: imports clean, 650
tests discovered, Alembic zero-to-head clean, app startup HTTP 200 on `/`/health/host-config,
non-E2E suite 610 passed/1 skipped (matches the working checkout). No required source exists
only as an untracked file.

## Docker

Built from the current committed `Dockerfile`/`.dockerignore` (confirmed unmodified via
`git diff` against the pre-merge tag) using the fresh-checkout worktree as build context.
Verified: non-root (`uid=999(edudss)`), `HEALTHCHECK` reports `healthy`, HTTP 200 on `/` and
`/_stcore/health`, PostgreSQL connectivity from inside the container, real adversarial RLS
check via the non-superuser app role, `pgvector` extension present, and all four Phase 1C
runtime flows (create/authenticate user, activity log, admin AI config, AI token usage)
re-proven from inside the running container. No backup/recovery tooling was touched — that
remains the separate `reliability/phase13-backup-recovery` effort, confirmed untouched
(`D:/KLTN/edudss-backup-recovery` worktree unaffected by this merge).

## Remaining state (carried forward unchanged from the accepted candidate)

**Remaining REPOSITORY_READY (schema + repository exist, documented reason unchanged, not
relabeled as migrated):** Students, Lecturers, Courses, Enrollments, Academic records,
Recommendations, CMS metadata/content.

**Remaining LOCAL_ONLY:** true model training/evaluation *metric* history
(`ModelVersion`/`ModelMetric` beyond their FK-resolution role inside `prediction_repository.py`).

**Remaining file/object-storage candidates (by design, unchanged):** model artifacts
(`.joblib` — MODEL_ARTIFACT), dataset CSVs (OBJECT_STORAGE_CANDIDATE), technical logs,
legacy embedding cache (TEMPORARY_CACHE).

**Confirmed POSTGRES_PRIMARY_WITH_FALLBACK (this phase):** users/authentication, activity
history, AI token usage, admin AI configuration.

**Unchanged POSTGRES_PRIMARY_WITH_FALLBACK (Phase 1B, re-verified still passing):**
predictions, consultations, subscriptions, RAG persistence / pgvector search.

## Known limitations

- No automatic local→Postgres migration of existing `users.json` accounts; operators must
  seed Postgres accounts explicitly before enabling `EDUDSS_IDENTITY_STORE=postgres` on a
  deployment with existing local users.
- Academic-cluster domains, recommendations, and CMS remain REPOSITORY_READY — completing
  them requires redesigning `eda.py`/`trainers.py`'s bulk-DataFrame pattern,
  `advisory.py`'s live chat loop, and `cms_lecture_repository.py`/`learning_explainer.py`'s
  call sites respectively, each out of scope for this phase and the merge that followed it.
- Model training/evaluation metric history was not wired.

## Production blockers

None introduced by this merge. All four newly-wired domains default to local-mode
(pre-Phase-1C behavior) unless an operator explicitly opts in per-feature.

---

## MERGE STATUS: PASS

## MAIN READY: YES

DO NOT START ANOTHER PHASE. STOP.
