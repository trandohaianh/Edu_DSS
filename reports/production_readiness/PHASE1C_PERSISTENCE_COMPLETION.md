# Phase 1C — Persistence Completion / PostgreSQL Runtime Cutover

**Base commit:** `451eb124dba05608f36b4ac52c924869ad3b0390` (accepted main HEAD after the
20k performance remediation merge)
**Branch:** `persistence/phase1c-runtime-cutover`
**Worktree:** `../edudss-persistence-phase1c`
**Candidate commit:** `72233aff0029250be257cefed9f24167c5de332e`

Mission: complete as much of the remaining Postgres runtime cutover as safely possible,
on top of the accepted Phase 1 / Phase 1B architecture — not a redesign. Every domain
below was independently audited against the CURRENT main before any code was written;
nothing was migrated "because a table exists."

---

## 1. BEFORE matrix (state at base commit `451eb12`, i.e. Phase 1B's accepted end state —
unchanged by the two intervening phases, which touched observability and performance, not
persistence)

| # | Domain | Original backend | PostgreSQL repository | Runtime wired | Fallback | Status |
|---|---|---|---|---|---|---|
| 1 | Users / authentication | `dss/services/auth_service.py` → local JSON (`users.json`), PBKDF2-HMAC-SHA256 | None — `repository_for("IDENTITY")` always raised `NotImplementedError` | No | N/A | LOCAL_ONLY |
| 2 | Students | Bulk pandas DataFrame, no per-record CRUD | `academic_repository.py::upsert_student` | No | N/A | REPOSITORY_READY |
| 3 | Lecturers | same DataFrame | `academic_repository.py::upsert_lecturer` | No | N/A | REPOSITORY_READY |
| 4 | Courses | same DataFrame | `academic_repository.py::upsert_course` | No | N/A | REPOSITORY_READY |
| 5 | Enrollments | same DataFrame | `academic_repository.py::upsert_enrollment` | No | N/A | REPOSITORY_READY |
| 6 | Academic records | same DataFrame (`diem_*` columns) | `academic_repository.py::record_academic_record` | No | N/A | REPOSITORY_READY |
| 7 | Recommendations | None — fully ephemeral (`career_ai_advisor.py`/`advisory.py`, `st.session_state` only) | `recommendation_repository.py` | No | N/A | REPOSITORY_READY |
| 8 | CMS metadata/content | `cms_lecture_repository.py` + `learning_explainer.py` → local JSON | `cms_repository.py` (own RLS) | No | N/A | REPOSITORY_READY |
| 9 | Evaluation/training history (user-facing activity feed) | `warehouse.py::log_activity`/`get_recent_activities` → local JSON | `ActivityLog` table existed (Phase 1 schema); no repository | No | N/A | SCHEMA_ONLY |
| 10 | AI token usage | `dss/services/token_tracker.py` → local JSON (`ai_token_usage.json`) | None | No | N/A | LOCAL_ONLY |
| 11 | Admin AI configuration | `dss/services/admin_ai_config.py` → local JSON (`ai_default_provider.json`) | None | No | N/A | LOCAL_ONLY |
| — | Predictions | local JSON | `prediction_repository.py` | **Yes** | Yes | POSTGRES_PRIMARY_WITH_FALLBACK |
| — | Consultations | local JSON | `consultation_repository.py` | **Yes** | Yes | POSTGRES_PRIMARY_WITH_FALLBACK |
| — | Subscriptions | local JSON | `subscription_repository.py` | **Yes** | Yes | POSTGRES_PRIMARY_WITH_FALLBACK |
| — | RAG persistence / pgvector search | local NumPy + JSON | `PgVectorStore` | **Yes** | Yes | POSTGRES_PRIMARY_WITH_FALLBACK |

(Model artifacts, dataset CSVs, technical logs, legacy embedding cache — unchanged,
carried forward as documented in `PHASE1B_RUNTIME_CUTOVER.md`; not revisited here.)

---

## 2. AFTER matrix (this phase's result)

| # | Domain | Current UI-service entry point | Local store | PostgreSQL repository | Runtime wiring | Tenant scoped? | Fallback? | Migration required? | Target state |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Users / authentication | `dss/services/auth_service.py::authenticate/list_users/count_users_by_role` | `users.json` | **NEW** `dss/db/repositories/user_repository.py` | **Yes** — `EDUDSS_IDENTITY_STORE=postgres`, via `persistence_config.repository_for("IDENTITY")` | Yes (RLS, `organization_id` column) | Yes, dev/local-default | No (uses existing `users` table from Phase 1 schema) | **POSTGRES_PRIMARY_WITH_FALLBACK** |
| 2 | Students | `academic_repository.py` (unchanged) | DataFrame | `academic_repository.py::upsert_student` | No — no live single-record call site exists (see §5) | Yes | N/A | No | REPOSITORY_READY (unchanged, documented) |
| 3 | Lecturers | same | DataFrame | `academic_repository.py::upsert_lecturer` | No | Yes | N/A | No | REPOSITORY_READY (unchanged) |
| 4 | Courses | same | DataFrame | `academic_repository.py::upsert_course` | No | Yes | N/A | No | REPOSITORY_READY (unchanged) |
| 5 | Enrollments | same | DataFrame | `academic_repository.py::upsert_enrollment` | No | Yes | N/A | No | REPOSITORY_READY (unchanged) |
| 6 | Academic records | same | DataFrame | `academic_repository.py::record_academic_record` | No | Yes | N/A | No | REPOSITORY_READY (unchanged) |
| 7 | Recommendations | `career_ai_advisor.py`/`advisory.py` (unchanged) | None (ephemeral) | `recommendation_repository.py` | No | Yes | N/A | No | REPOSITORY_READY (unchanged, documented) |
| 8 | CMS metadata/content | `cms_lecture_repository.py`/`learning_explainer.py` (unchanged) | local JSON | `cms_repository.py` | No | Yes | N/A | No | REPOSITORY_READY (unchanged, documented) |
| 9 | Activity / evaluation-training history feed | `dss/core/warehouse.py::log_activity/get_recent_activities/get_merged_recent_activities` | `activity_history.json` | **NEW** `dss/db/repositories/activity_log_repository.py` | **Yes** — `EDUDSS_ACTIVITY_STORE=postgres` | Yes (RLS) | Yes, dev/local-default | No (`ActivityLog` table pre-existed) | **POSTGRES_PRIMARY_WITH_FALLBACK** |
| 10 | AI token usage | `dss/services/token_tracker.py::record_usage/_load_all_records` | `ai_token_usage.json` | **NEW** `dss/db/repositories/ai_token_usage_repository.py` | **Yes** — `EDUDSS_AI_TOKEN_USAGE_STORE=postgres` | Yes (RLS) | Yes, dev/local-default | **Yes** — new table `ai_token_usage`, migration `797f72d1c666` | **POSTGRES_PRIMARY_WITH_FALLBACK** |
| 11 | Admin AI configuration | `dss/services/admin_ai_config.py::get/set/clear_default_provider` | `ai_default_provider.json` | **NEW** `dss/db/repositories/admin_ai_config_repository.py` | **Yes** — `EDUDSS_ADMIN_AI_CONFIG_STORE=postgres` | Yes (RLS) | Yes, dev/local-default | **Yes** — new table `admin_ai_config`, same migration | **POSTGRES_PRIMARY_WITH_FALLBACK** |

Model training/evaluation *metric* history (`ModelVersion`/`ModelMetric` tables, distinct
from the user-facing activity feed above) and true model artifacts (`.joblib` binaries)
were **not** touched this phase — `ModelVersion` is used today only as an FK-resolution
helper inside `prediction_repository.py`, not a wired training-history CRUD path; building
that out was judged a separate, larger piece of work than the priority-ordered items
actually completed here, and is left **LOCAL_ONLY**, documented, not silently skipped.

---

## 3. Per-domain detail

### 3.1 Users / authentication — HIGHEST PRIORITY (Section 4)

- **Audit finding:** `auth_service.py` was *already written* (by an earlier phase) to call
  `repository_for("IDENTITY")` and use a repository object's `get_user_by_username` /
  `list_users` / `count_users_by_role` methods — but the gate function unconditionally
  raised `NotImplementedError` for postgres mode, so this code path was structurally dead.
- **What changed:** new `dss/db/repositories/user_repository.py` (`UserRepository` class)
  implementing exactly that contract, plus `create_user`/`touch_last_login`. Wired into
  `persistence_config.repository_for("IDENTITY")`.
- **Password representation:** unchanged format — PBKDF2-HMAC-SHA256, 200,000 iterations,
  16-byte random salt, `hmac.compare_digest` verification. The repository does **not**
  reimplement hashing; it lazily imports `auth_service._hash_password` so hashes are
  byte-identical regardless of which backend created the account. No plaintext password
  is ever stored or logged; a dedicated test (`test_authenticate_never_logs_password_or_hash_via_postgres`)
  asserts the real `technical.log` file never contains the password, the wrong-password
  attempt, the hash, or the salt.
- **Role representation:** `role_id` FK to the existing `roles` table — no role value is
  ever trusted from UI input; `auth_service.py`'s role checks are unchanged.
- **Org/tenant relationship:** `UserRepository` is constructed with a single
  `organization_id`, resolved server-side only via `EDUDSS_ORGANIZATION_ID` (never from a
  UI field), matching the established single-tenant deployment pattern. RLS is proven with
  the real non-superuser app role (`test_cross_tenant_isolation_via_real_rls`).
  Unscoped/wrong-tenant access returns empty results (fail closed), never an error that
  could be mistaken for "no such feature."
- **Session identity / authorization:** unchanged — `st.session_state["_auth_role"]`
  remains the single source of truth for `require_role()`; nothing here weakens RBAC.
  Account-status/lockout logic (`AccountLockedError`, failed-attempt counter) is untouched.
- **Auto-provision UX regression avoided:** the original `authenticate()` guarded
  auto-provision-on-first-login with `if repository is None and ...` — enabling Postgres
  IDENTITY would have **silently disabled** a real, working feature. Fixed by restructuring
  the condition so both branches call through correctly
  (`test_authenticate_auto_provision_via_postgres`).
- **No credential invention:** no user passwords were reset, guessed, or fabricated. No
  data migration of the local `users.json` file into Postgres was performed this phase (see
  §4 — deliberately deferred, not silently skipped).

### 3.2 Students / Lecturers / Courses / Enrollments / Academic records (Sections 3, 6, 7)

**Unchanged from Phase 1B — REPOSITORY_READY, carried forward with the same documented
justification.** Re-audited against current main and confirmed still accurate:
`dss/core/data_helpers.py::generate_data()`/`generate_lms_data()` still produce a single
bulk pandas DataFrame consumed directly by the ML pipeline (`trainers.py`, `eda.py`,
`ml_hub.py`) — there is still no per-student/lecturer/course/enrollment CRUD call site in
the live app to wire without redesigning that data-access pattern, which both Phase 1B and
this phase's instructions explicitly flag as out of scope. `academic_repository.py` (real
schema, real RLS, real `import_dataframe()` ETL, existing test suite) remains available for
a future phase that does take on that redesign. No safe, non-redesigning cutover exists for
these five domains this phase — documented, not forced.

### 3.3 Recommendations (Section 8)

**Unchanged — REPOSITORY_READY.** Re-confirmed `career_ai_advisor.py`/`advisory.py` still
have no `save` function anywhere; recommendations remain a live conversational stream into
`st.session_state` only, with zero existing single-record write call site. Wiring this would
mean redesigning the interactive chat loop itself, which is out of this phase's scope.

### 3.4 CMS metadata/content (Section 9)

**Unchanged — REPOSITORY_READY.** The internal CMS was **not** removed. `cms_repository.py`
(4 tables, own RLS, tested `import_from_local()`) remains available; `cms_lecture_repository.py`/
`learning_explainer.py` still own the live JSON-backed runtime. Re-wiring those call sites
touches a large, actively-used service surface and was judged out of scope for this pass,
consistent with the Phase 1B decision it inherits.

### 3.5 Activity / evaluation-training history (Section 10, priority item 9)

- **Audit finding:** the `ActivityLog` table already existed in the Phase 1 schema,
  field-for-field matching `warehouse.py::log_activity()`'s local JSON shape — a genuine
  SCHEMA_ONLY domain (schema present, nothing reading/writing it).
- **What changed:** new `dss/db/repositories/activity_log_repository.py`
  (`record_activity`, `get_recent_activities`, idempotent `import_from_local_history`).
  Wired into `warehouse.py`'s three call sites (`log_activity`, `get_recent_activities`,
  `get_merged_recent_activities`), gated by `is_postgres_enabled("ACTIVITY")`, no dual-write
  (`test_warehouse_log_activity_does_not_dual_write_to_local_json`).
- Distinct from `audit_log_repository.py` (the security/admin-action trail, already live
  since Phase 1) — this is the separate user-facing "recent activity" feed.
- True model training/evaluation *metrics* (`ModelVersion`/`ModelMetric`) were **not**
  wired this phase (see §2 note) — left LOCAL_ONLY/documented, not silently skipped.

### 3.6 AI token usage (Section 11, priority item 10)

- **Audit finding:** `token_tracker.py` has a single read choke-point,
  `_load_all_records()`, used by all four aggregation functions (daily usage, quota check,
  budget status, usage summary).
- **What changed:** new `AiTokenUsage` table (migration `797f72d1c666`) + new
  `ai_token_usage_repository.py`. Branched `_load_all_records()` and `record_usage()` on
  `is_postgres_enabled("AI_TOKEN_USAGE")` — every existing aggregation function works
  unchanged against either backend, no rewriting of aggregation logic as SQL.
- **Privacy:** the table has no column that could hold an API key, Authorization header, or
  full prompt — only `provider`, `model`, token counts, `estimated_cost`, and the
  already-pseudonymized `user_id` (email-like ids are rewritten by `token_tracker.py`
  *before* reaching the repository). Schema-level test
  (`test_never_persists_secrets_or_api_keys`) asserts this.
- **No double-counting:** this ledger is a separate accounting record from Phase 12A's
  observability metrics; nothing here changes what observability emits.

### 3.7 Admin AI configuration (Section 12, priority item 11)

- **Audit finding:** `admin_ai_config.py` persists exactly two fields — `provider_key`,
  `model_name` — both plain non-secret strings (e.g. `"gemini"` / `"gemini-2.0-flash"`).
  Classified **SAFE_DATABASE_CONFIG**. Actual API keys are resolved entirely separately via
  `st.secrets`/environment variables and never pass through this module.
- **What changed:** new `AdminAiConfig` table (same migration) + new
  `admin_ai_config_repository.py` (one row per organization, upsert semantics). Wired into
  all three service functions, gated by `is_postgres_enabled("ADMIN_AI_CONFIG")`. The
  `@require_role("Admin")` gate on write functions is untouched — RBAC enforced identically
  regardless of backend (`test_service_set_default_provider_requires_admin_role_via_postgres`).
  No secret value was ever moved into this table (schema-level test asserts no
  `api_key`/`secret`/`token`/`credential` column exists).

---

## 4. Local fallback policy (Section 13)

All four newly-wired domains use **POSTGRES_PRIMARY_WITH_FALLBACK**, matching the exact
mechanism already established in Phase 1B for predictions/consultations/subscriptions/RAG:

- Gated per-feature by `EDUDSS_<FEATURE>_STORE` (`local` default, `postgres` opt-in).
- **No dual-write, ever.** When postgres mode is active, the local JSON path is not touched
  at all (verified per-domain: `test_*_does_not_dual_write_to_local_json`). When local mode
  is active (the default), behavior is byte-for-byte the pre-Phase-1C behavior.
- Fallback/local mode is the **default** — safe for any environment that hasn't explicitly
  opted in, including production unless an operator deliberately sets the postgres env var.
- Production disables the "fallback" (i.e., commits to Postgres-only) the same way every
  other Phase 1B domain does: by setting the `EDUDSS_<FEATURE>_STORE=postgres` env var and
  leaving it set — there is no separate on/off switch beyond the one gate.

## 5. Data migration (Section 15)

No local→Postgres data import for **users** was performed this phase — `users.json`
accounts are not automatically imported into Postgres at startup, and no accounts were
invented or reset. Operators who enable `EDUDSS_IDENTITY_STORE=postgres` on a deployment
with existing local accounts must create/seed those Postgres accounts explicitly (e.g. via
`dss/db/seed.py`, which already reuses the same `_hash_password` function) — this is
intentionally **not automatic**, consistent with Section 15's "do not automatically import
arbitrary user files at application startup."

`activity_log_repository.py::import_from_local_history()` **was** built and tested
(idempotent, dedupes via `details["_local_activity_id"]`, mirrors the exact pattern used by
`prediction_repository`/`consultation_repository` in Phase 1B) — an explicit, opt-in,
re-runnable import path, not an automatic one. No legacy local data was deleted.

## 6. Migrations (Section 14)

One new Alembic migration: `797f72d1c666_ai_token_usage_and_admin_ai_config.py` (revises
`f0b43f540e41`). Adds `ai_token_usage` and `admin_ai_config` tables, both with a direct
`organization_id` FK to `organizations` (`ON DELETE CASCADE`), plus hand-added RLS
(`ENABLE`/`FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation`, direct-column
policy — no subquery needed, mirroring the pattern from `830742fd75d4`). No previously
applied migration was edited or rewritten.

Verified:
- `alembic upgrade head` from the prior head (`f0b43f540e41`) — clean.
- `alembic downgrade -1` then `alembic upgrade head` — clean re-upgrade, no errors.
- Fresh database (`CREATE DATABASE`, zero migrations applied) → `alembic upgrade head` —
  all 5 migrations apply in order (`4915552f6063` → `cbae9b411ed5` → `830742fd75d4` →
  `f0b43f540e41` → `797f72d1c666`), 27 tables created, `pgvector` extension present.
- `edudss_app` (non-superuser) grants re-applied after schema change and confirmed via
  `has_table_privilege`.

## 7. RLS / tenant isolation (Section 5)

Every newly-wired domain has a real cross-tenant isolation test, and users additionally has
an **adversarial** test using the actual non-superuser `edudss_app` role (not just the
repository's own `organization_id` filter):

- `test_user_repository.py::test_cross_tenant_isolation_via_real_rls` — opens a raw
  connection as `edudss_app`, sets `SET LOCAL app.organization_id` to org B, proves org A's
  user row is invisible.
- `test_activity_log_repository.py::test_cross_tenant_isolation`,
  `test_ai_token_usage_repository.py::test_cross_tenant_isolation`,
  `test_admin_ai_config_repository.py::test_cross_tenant_isolation` — application-level
  isolation for the other three domains.
- Real-runtime proof (§9 below) repeats the adversarial app-role RLS check inside the
  running Docker container.
- No runtime code path connects as a superuser/schema-owner role; `edudss_app` has exactly
  the grants `GRANT ALL ON ALL TABLES/SEQUENCES IN SCHEMA public` (same as every other
  Phase 1B domain) — no elevated bypass.

## 8. Observability / privacy (Section 16)

No changes to Phase 12A's observability wiring. New persistence paths do not add any new
telemetry themselves (out of scope for this pass — no new metric points were required by
the priority list), but do not remove or bypass any existing correlation-ID/redaction
behavior in `logging_config.py`. Privacy assertions verified directly:
- Passwords, password hashes, and password salts never appear in `technical.log`
  (`test_authenticate_never_logs_password_or_hash_via_postgres`).
- No API key, Authorization header, or full prompt column exists in `ai_token_usage` or
  `admin_ai_config` (`test_never_persists_secrets_or_api_keys`, both domains).

## 9. Real runtime proof (Section 19)

Using the real non-superuser app role (`edudss_app`), against a live PostgreSQL 15 +
pgvector instance (`edudss_pg_phase1b`), the following flows were exercised end-to-end
through the actual public functions the app calls (not test-only shortcuts):

1. Create user (`UserRepository.create_user`) — **PASS**
2. Authenticate user (`auth_service.authenticate`, correct and incorrect password) — **PASS**
3. Activity log write + read (`activity_log_repository`) — **PASS**
4. Admin AI config set + read (`admin_ai_config_repository`) — **PASS**
5. AI token usage record + read (`ai_token_usage_repository`) — **PASS**

Only flows actually implemented this phase are claimed above. Students/lecturers/courses/
enrollments/academic records/recommendations/CMS flows were **not** exercised as "runtime
proof" because they are not wired to a live single-record runtime path this phase (§3.2–3.4).

Repeated a second time fully inside the built Docker image (`edudss-phase1c-candidate:verify`,
container `edudss_phase1c_check`, non-root `uid=999`), against `host.docker.internal:55433` —
same five flows, same result, plus a direct adversarial RLS check from inside the container
(cross-tenant `SELECT` under a different `app.organization_id` returned zero rows) and a
pgvector-extension presence check.

## 10. Restart persistence (not disaster recovery)

`docker restart edudss_pg_phase1b` was performed twice during this phase, each time
followed by direct `psql` verification that the records written by the real-runtime-proof
flow (users, activity_logs, admin_ai_config, ai_token_usage rows) were still present and
unchanged after the restart, and that `edudss_app`'s grants survived. The application
container (`edudss_phase1c_check`) was also restarted and returned to `healthy` / HTTP 200
without any code changes. This is ordinary process-restart persistence, not a disaster
recovery drill (that remains a separate, explicitly out-of-scope effort per the prompt).

## 11. Performance (Section 17)

`test_20000_students_batch_prediction_benchmark` run unmodified: **PASSED**. No change was
made to this test or to the code paths it exercises.

## 12. Full test suite results (Section 18)

| Suite | Result |
|---|---|
| Non-E2E (`pytest tests --ignore=tests/e2e`, `DATABASE_URL` + `DATABASE_APP_ROLE_URL` set) | 610 passed, 1 skipped (pre-existing, unrelated `.env`-dependent LLM test) |
| E2E (`pytest tests/e2e`) | 39 passed |
| Real RLS (`test_db_row_level_security.py`, real app role) | 6 passed |
| Phase1B+8A integration + Phase12A + security suites | 26 passed |
| 20k performance benchmark | 1 passed, unmodified |
| New Phase 1C tests (users, activity log, AI token usage, admin AI config) | 42 passed (11 + 7 + 7 + 17), all real-Postgres, none faked |

One pre-existing Phase-1B-era test (`test_persistence_config.py::test_postgres_mode_fails_loudly_not_silently`)
asserted `IDENTITY` always raises `NotImplementedError` — now genuinely false since IDENTITY
is wired. Replaced with two tests reflecting the new, correct behavior (returns a real
`UserRepository`; still fails loudly with a clear `RuntimeError` if `EDUDSS_ORGANIZATION_ID`
is unset). `SUBSCRIPTION`'s equivalent test is untouched (still correctly unwired via this
gate).

## 13. Fresh checkout (Section 20)

Detached worktree `../edudss-phase1c-freshcheck` created from commit `72233af` (verified via
`git rev-parse HEAD`). From that worktree alone (`.venv` junction-linked, no untracked files
from the working worktree carried over):
- All new/changed modules import cleanly.
- `pytest --collect-only`: 650 tests discovered.
- Fresh database, zero to head: `alembic upgrade head` — clean, 27 tables, pgvector present.
- `streamlit run dss/main.py --server.headless true` — HTTP 200 on `/`, `/_stcore/health`,
  `/_stcore/host-config`; no errors/tracebacks in the startup log.
- Full non-E2E suite from this worktree: 610 passed, 1 skipped — identical to the working
  worktree.

## 14. Docker (Section 21)

Dockerfile and `.dockerignore` were **not modified** (confirmed via `git diff` — no changes
this phase). Built `edudss-phase1c-candidate:verify` from the fresh-checkout worktree
(cache-assisted, dependency layers reused). Verified:
- Container runs as non-root (`uid=999(edudss)`).
- `HEALTHCHECK` reports `healthy`.
- HTTP 200 on `/` and `/_stcore/health`.
- PostgreSQL connectivity from inside the container (`host.docker.internal:55433`).
- All five newly-wired runtime flows (§9) re-verified from inside the container.
- Real adversarial RLS check from inside the container using the non-superuser app role.
- pgvector extension present.
- Survived a PostgreSQL container restart (§10) without code changes.

No backup/recovery tooling was implemented — that is explicitly reserved for a separate,
parallel effort per the prompt's own instruction, and was not touched here.

---

## 15. Remaining state (explicit, not glossed over)

**Still LOCAL_ONLY:** true model training/evaluation *metric* history
(`ModelVersion`/`ModelMetric` beyond their FK-resolution use in `prediction_repository.py`),
model artifacts (`.joblib`, by design — MODEL_ARTIFACT), dataset CSVs (OBJECT_STORAGE_CANDIDATE,
by design), technical logs, legacy embedding cache (TEMPORARY_CACHE).

**Still REPOSITORY_READY (schema + repository exist, not live-wired, documented reason
unchanged from Phase 1B):** Students, Lecturers, Courses, Enrollments, Academic records,
Recommendations, CMS metadata/content.

**Still POSTGRES_PRIMARY_WITH_FALLBACK (unchanged, Phase 1B):** Predictions, Consultations,
Subscriptions, RAG persistence, pgvector search.

**Newly POSTGRES_PRIMARY_WITH_FALLBACK (this phase):** Users/authentication, Activity log,
AI token usage, Admin AI configuration.

## 16. Known limitations

- No automatic local→Postgres data migration for existing `users.json` accounts; operators
  must seed Postgres accounts explicitly before flipping `EDUDSS_IDENTITY_STORE=postgres`
  on a deployment with existing local users.
- The academic-cluster domains (students/lecturers/courses/enrollments/academic records),
  recommendations, and CMS remain REPOSITORY_READY, not wired — completing them requires a
  larger redesign of `eda.py`/`trainers.py`'s bulk-DataFrame pattern, `advisory.py`'s live
  chat loop, and `cms_lecture_repository.py`/`learning_explainer.py`'s call sites
  respectively, each explicitly out of scope for this pass.
- Model training/evaluation metric history was not wired this phase.

## 17. Production blockers

None introduced by this phase. All four newly-wired domains default to local-mode
(unchanged behavior) unless an operator explicitly opts in per-feature.

---

## PHASE STATUS: PASS_WITH_DOCUMENTED_REMAINING_MIGRATION

## READY FOR LATER INTEGRATION: YES

DO NOT MERGE INTO MAIN. STOP.
