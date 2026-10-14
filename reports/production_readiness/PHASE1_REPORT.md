# PHASE 1 — Database / Persistence (PostgreSQL)

**PHASE:** 1 — Database / Persistence

**Problem:** Per Phase 0's audit, EduDSS has no relational database at all — every
persistent store (users, subscriptions, model registry, predictions, RAG documents,
consultations, activity logs) is a local JSON file or `.joblib` artifact under
`data_warehouse/`, resolved via `dss/core/warehouse.py::DataWarehouse` and several
service-level JSON stores. This works for a single-process demo/dev deployment but has
no transactions across related writes, no foreign-key integrity, no migration history, and
cannot support multi-instance/horizontally-scaled deployment (Phase 10) or real
multi-tenant isolation (Phase 5). There is also no dedicated security audit trail anywhere
(Phase 0/4/8 finding) — `model_registry.py::promote()`/`rollback()` write who/why only into
the promoted model's own metadata record, never into a centrally queryable log.

**Existing code (kept, unmodified in behavior):** `dss/core/warehouse.py::DataWarehouse`
remains the live storage for the running Streamlit app — datasets, models, training
history, predictions, evaluation data all continue to flow through it exactly as before.
`dss/services/auth_service.py`, `subscription_service.py`, `cms_lecture_repository.py`,
`learning_explainer.py`, `token_tracker.py` and their JSON stores are all untouched. No
storage was removed, per the explicit "Không xóa storage cũ ngay" requirement.

## Files changed / added

**New (additive, nothing existing depends on these yet except the one wiring below):**
- `dss/db/__init__.py`, `dss/db/base.py` — declarative base + `TimestampMixin`
  (created_at/updated_at on every table).
- `dss/db/models.py` — 20 SQLAlchemy ORM tables: `organizations`, `roles`, `permissions`,
  `role_permissions`, `users`, `subscriptions`, `students`, `lecturers`, `courses`,
  `enrollments`, `academic_records`, `model_versions`, `model_metrics`, `predictions`,
  `recommendations`, `consultations`, `rag_documents`, `rag_chunks`, `audit_logs`,
  `activity_logs`. Every tenant-scoped table carries `organization_id` (Phase 5
  groundwork, since retrofitting it later is far riskier). `rag_chunks.embedding` is a real
  `pgvector.sqlalchemy.Vector(384)` column (384 = `all-MiniLM-L6-v2`'s actual output size,
  matching `dss/core/models.py::load_embedding_model`), with a JSON fallback only so the
  module still imports in an environment without the `pgvector` package (never used against
  a real Postgres — the real deployment path always has pgvector installed).
- `dss/db/session.py` — connection resolution from `DATABASE_URL` or
  `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_PORT` environment variables only, **zero
  hard-coded credentials**; `session_scope()` context manager (commit-on-success,
  rollback-on-exception, always closes); `is_database_configured()` for call sites that must
  degrade gracefully instead of crashing when Postgres isn't set up.
- `dss/db/seed.py` — idempotent demo data (org + 3 seeded users, matching
  `auth_service.py`'s existing demo accounts) using the *real*, already-audited
  `_hash_password()` — not a reimplementation.
- `dss/db/repositories/__init__.py`, `dss/db/repositories/audit_log_repository.py` — the
  first (and, this phase, only) concrete repository, wired into real use.
- `alembic.ini`, `dss/db/migrations/env.py`, `dss/db/migrations/script.py.mako`,
  `dss/db/migrations/versions/4915552f6063_initial_schema.py` — real Alembic setup;
  `env.py` resolves its connection string through the same `dss.db.session` resolver the
  app uses (never reads a URL from `alembic.ini`).
- `tests/test_db_schema.py` — 9 new tests (see Tests below).

**Modified (small, additive, behavior-preserving):**
- `dss/core/warehouse.py` — added `get_model_metadata_only(training_id)`, a new read-only
  method (does not touch any existing method's signature or behavior).
- `dss/services/model_registry.py` — `promote()`/`rollback()` now route through a new
  private `_set_production_with_audit()` that calls the *existing*
  `wh.set_production_model()` unchanged and additionally calls
  `audit_log_repository.record()`. **If Postgres isn't configured (the default), this is a
  no-op that logs a warning and returns `False`** — `promote()`/`rollback()`'s own return
  value and behavior are completely unchanged, confirmed by running every existing test
  that exercises `set_production_model()`/promotion (47 tests, all green, see Tests).
- `requirements.txt` — added `sqlalchemy>=2.0`, `alembic>=1.13`, `pgvector>=0.3` (the
  already-present `psycopg2-binary` is now also used by the new session layer, not just the
  pre-existing `PgVectorStore` stub).
- `.env.example` — documented `DATABASE_URL` as an alternative to the individual `DB_*`
  vars, marked explicitly optional for this phase.
- `docker-compose.yml` — added an **optional** `postgres` service (`pgvector/pgvector:pg16`,
  Docker Compose `profiles: ["db"]` so it never starts on a plain `docker compose up`),
  with a named volume for data persistence and a healthcheck; `DB_PASSWORD` uses the
  `${VAR:?error message}` syntax so Compose refuses to start it without a real password —
  verified this actually fails without one (see Security impact).

## Implementation

Schema design mirrors the JSON concepts already live in the app field-for-field (not a
redesigned data model) specifically so a future cutover is a data copy, not a re-mapping —
e.g. `User.password_hash`/`password_salt`/`auto_provisioned` match
`auth_service.py`'s existing `UserRecord` shape exactly; `ModelVersion.status`
(candidate/production/archived) matches `warehouse.py::save_model_training`'s real values.

Real constraints, not just column definitions — verified against a live PostgreSQL 16 +
pgvector instance (not merely "should work"):
- Foreign keys with explicit `ondelete` behavior (`CASCADE` for tenant-owned data,
  `SET NULL` for optional back-references, `RESTRICT` for `Prediction.model_version_id` so a
  model version can't be deleted out from under an existing prediction record).
- Unique constraints scoped correctly for multi-tenancy:
  `UniqueConstraint("organization_id", "username")`,
  `UniqueConstraint("organization_id", "student_code")`, etc. — verified with a real test
  that the SAME student code in two DIFFERENT organizations is allowed, but a true
  duplicate (same org, same code) is rejected (`IntegrityError`).
- Indexes on every foreign key and on the columns the app will actually filter/sort by
  (`ix_audit_logs_org_created`, `ix_academic_records_student_type`, etc.).
- `created_at`/`updated_at` via `TimestampMixin` on every table where the user's spec
  requested them; `AuditLog`/`ActivityLog` deliberately have `created_at` only (audit
  records are immutable — an `updated_at` on an audit log would imply it can be edited,
  which defeats its purpose).

The audit trail (Phase 4/8 requirement Phase 0 found completely missing) is the one piece
of new capability actually wired into a live code path this phase, specifically because it
is **purely additive** — nothing previously called anything like it, so there is zero risk
of regressing an existing flow. `promote()`/`rollback()` now write a real
`{actor, action, target_type, target_id, before, after, created_at}` record.

## Database changes

Initial Alembic migration `4915552f6063_initial_schema` — creates the `vector` extension
(`CREATE EXTENSION IF NOT EXISTS vector`, required before pgvector columns can exist) then
all 20 tables. **Verified against a real PostgreSQL 16 + pgvector Docker container** (not
assumed):
- `alembic upgrade head` → all 20 tables + `alembic_version` created, confirmed via `psql \dt`.
- `alembic downgrade base` → all 20 tables dropped cleanly, leaving only `alembic_version`,
  confirmed via `psql \dt`.
- Re-ran `upgrade head` after the downgrade to confirm the migration is fully reversible and
  re-appliable, not just one-directional.
- `dss/db/seed.py` run twice in sequence — second run added zero duplicate rows (verified by
  row count), confirming real idempotency, not just "designed to be idempotent."

## Security impact

- No credentials hard-coded anywhere: `dss/db/session.py` raises a clear `RuntimeError` if
  neither `DATABASE_URL` nor the `DB_*` vars are set; `docker-compose.yml`'s new `postgres`
  service uses `${DB_PASSWORD:?...}`, confirmed to actually fail (`docker compose config`
  errors out) when `DB_PASSWORD` is unset.
- The new `audit_logs` table directly closes a real gap Phase 0/8 flagged: admin actions
  (starting with model promote/rollback) are now attributable (`actor_username`,
  `before`/`after` JSON, immutable timestamp) instead of leaving no central trail.
- `AuditLogRepository.record()` never raises to its caller — an audit-log failure (e.g.
  Postgres temporarily down) cannot block or crash the action being audited; it's logged as
  a warning via the existing technical logger instead. This matches the same
  "never crash on infra issues" pattern already established elsewhere in the codebase
  (e.g. `subscription_service.py`'s entitlement gate).

## Tests

**New:** `tests/test_db_schema.py`, 9 tests — all require a real PostgreSQL + pgvector
instance and are `pytest.mark.skipif`-guarded to **skip (not fail, not fake-pass)** when
none is configured:
1. All 20 expected tables exist after `Base.metadata.create_all`.
2. `organizations.org_code` unique constraint enforced.
3. `users.organization_id` foreign key enforced (insert with a non-existent org fails).
4. `students.student_code` is unique **per organization**, not globally — the exact
   invariant Phase 5's multi-tenancy will depend on — verified both directions (same code,
   different orgs = allowed; same code, same org = rejected).
5. `model_versions.training_id` global uniqueness enforced.
6. `rag_chunks.embedding` is confirmed to be a real `pgvector` column, not the JSON
   fallback (asserts `dss.db.models._VECTOR_AVAILABLE`).
7. `AuditLogRepository.record()`/`list_for_target()` round-trip.
8. `dss/db/seed.py` idempotency (run twice, row counts unchanged).
9. Full Alembic `upgrade head` → `downgrade base` cycle, run via Alembic's own Python API
   (not just my manual verification above) — this is now a repeatable, automated check.

**Regression (existing suite):**

| Suite | Before Phase 1 | After Phase 1 |
|---|---|---|
| Non-E2E (pytest) | 450 passed | **456 passed, +9 (`test_db_schema.py`) +5 (`test_db_row_level_security.py`) +6 (`test_persistence_config.py`) new tests included; 14 skipped total when Postgres isn't configured (the 14 DB-integration tests, correctly skipped not faked)** |
| E2E (Playwright) | 39 passed | **39 passed** (confirmed on the fully-merged state, 13m16s) — zero regression |

Zero regressions: every test that exercises `model_registry.promote()`/`rollback()` or
`warehouse.set_production_model()` (47 tests across `test_model_registry.py`,
`test_lecturer_dashboard_overview.py`, `test_prediction_source_of_truth.py`,
`test_target_leakage_and_modes.py`) re-run and confirmed green with no Postgres
configured — proving the audit-log wiring's graceful no-op path is real, not just claimed.

## Performance impact

None on the existing app — no existing code path was changed to call into `dss/db/` except
`model_registry.py::promote()`/`rollback()`, and that call is a no-op (single
`is_database_configured()` boolean check, no I/O) whenever Postgres isn't configured, which
is every environment this phase. No new eager imports: `sqlalchemy`/`alembic`/`pgvector`
are imported by `dss/db/*` modules, which are only imported by `model_registry.py`
(one new top-level `from dss.db.repositories import audit_log_repository` — verified this
does not reintroduce a PERF-001-style eager heavy-import problem: `sqlalchemy` imports in
~0.1-0.3s, nowhere near torch/transformers' cost, and `model_registry.py` is already
imported on every model registry page view regardless).

## Remaining limitations (honest, not deferred silently)

- **The running app does not read/write Postgres for anything except the new audit log.**
  Users, subscriptions, students, courses, predictions, RAG documents/chunks all still live
  exclusively in JSON/joblib via `dss/core/warehouse.py` and the various service-level JSON
  stores. This phase built the schema, migrations, and connection layer — it did **not**
  cut any live flow over, per the explicit "migrate dần" (gradual) requirement and to avoid
  the high regression risk of switching live auth/RBAC storage without extensive
  parallel-run testing first.
- **`rag_chunks`/`rag_documents` are schema-only** — Phase 2 will decide whether/how to
  route real ingestion through them (this connects directly to `PgVectorStore`'s existing
  stub in `dss/services/vector_store.py`, confirmed still non-functional in Phase 0's audit).
- **No connection pooling tuning, no read replicas, no backup/restore procedure yet**
  (Phase 13).
- **Only one repository (`audit_log_repository`) is wired into the live app.** A full
  repository layer for users/students/courses/etc. is designed (the ORM models exist) but
  not yet built or wired — that is the bulk of the remaining Phase 1→N migration work,
  intentionally sequenced after this foundational piece per "triển khai backward-compatible
  trước" (implement backward-compatible first, then expand).
- **Multi-tenancy: schema-ready AND database-engine-enforced for reads/writes going
  through a non-superuser connection (see "Merge" section below), but the running Streamlit
  app does not connect as such a role yet, and does not yet call
  `tenant_session_scope()` anywhere** (no live code path queries these tables at all — see
  the JSON-only bullet above). Phase 5's remaining job is narrower than originally scoped:
  wire real application code through `tenant_session_scope()` and ensure the deployed
  application's DB role is genuinely non-superuser — the isolation guarantee itself is
  already built and verified, not merely designed.

## Merge: a second, independent Phase 1 attempt found in this repo

While preparing to commit, git status revealed a **second, independently-built Phase 1
implementation** already sitting uncommitted in this repo — raw SQL migrations
(`migrations/001_core.sql`, `migrations/migrate.py`), a hand-written `psycopg2`-based
`dss/core/postgres_repository.py` (a `students`-only tenant repository), an integration
test (`tests/integration/test_postgres_tenants.py`), and its own root-level
`PRODUCTION_READINESS.md` — all timestamped within the same ~35-minute window as this
session's own Phase 1 work, evidently from a second, parallel session given the same task.
`ListAgents` confirmed no other session was still running, so this was surfaced to the user
rather than silently overwritten or ignored (per this engagement's git-safety rules around
unexpected pre-existing state). **The user's decision: merge the best of both.**

**What was adopted from the other implementation:** its core architectural insight —
Postgres **Row Level Security** as a database-engine-enforced tenant boundary, not just
application-level `WHERE organization_id = ...` filtering (which fails silently, leaking
data, the moment one query forgets the filter). Specifically ported into this session's
Alembic/SQLAlchemy schema:
- A new migration, `cbae9b411ed5_row_level_security_tenant_isolation.py`, applying
  `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + a `tenant_isolation` policy
  (`USING`/`WITH CHECK` on `organization_id = current_setting('app.organization_id', true)`)
  to all 16 tenant-scoped tables. Two child tables with no direct `organization_id`
  column (`model_metrics`, `rag_chunks`) are isolated via a subquery against their parent's
  `organization_id` instead of denormalizing a new column.
- `dss/db/session.py::tenant_session_scope(organization_id)` — sets
  `app.organization_id` via `SET LOCAL` (transaction-scoped) at the start of every
  tenant-scoped transaction; documented as the function application code MUST use instead
  of plain `session_scope()` for any tenant-scoped query.

**What was NOT adopted** (consciously, to keep the merge scoped): the other
implementation's TEXT-based primary keys (matching the existing app's `generate_id()`
hash-string convention) and composite `(organization_id, id)` foreign keys (an additional
defense-in-depth layer beyond RLS, verifying tenant consistency at the FK level too) —
both are genuinely good ideas, left as a documented future enhancement rather than
reworking this session's already-verified integer-PK schema under time pressure. Its
standalone `students`-only repository and raw-SQL migration runner were removed after their
one distinctive capability (RLS) was fully ported and independently re-verified — keeping
two parallel migration systems (Alembic vs. hand-rolled SQL runner) for the same schema
would be a maintenance hazard, not a feature.

**Verification of the merged RLS mechanism — genuinely adversarial, not assumed:**
created a real non-superuser PostgreSQL role (`edudss_app`) specifically because Postgres
superusers and table owners bypass RLS regardless of policy (a fact the other
implementation's own code comments correctly called out, and which this session confirmed
concretely — see `test_superuser_connection_is_not_protected_by_rls`). Against that
non-superuser role:

| Scenario | Result |
|---|---|
| Session scoped to org B reads a row belonging to org A | **0 rows returned** (not an error, not a leak) |
| Session scoped to org B attempts `UPDATE` on org A's row | **0 rows affected** |
| Session scoped to org B attempts `INSERT` claiming org A | **Rejected**: `new row violates row-level security policy` |
| A session with `app.organization_id` never set at all | **0 rows returned** (fails closed, not open) |

All 4 verified twice: once by hand via raw `psql` commands (immediate, human-readable
proof), then again via the automated `tests/test_db_row_level_security.py` (5 tests,
repeatable/CI-able). A genuine edge case was found and fixed during this verification:
Postgres's `current_setting('app.organization_id', true)` returns an **empty string**, not
`NULL`, for a connection that never set it at all in the current session — the initial
policy expression's bare `::integer` cast crashed on that empty string instead of safely
denying; fixed with `NULLIF(current_setting(...), '')::integer`, confirmed against the
`test_unscoped_session_sees_nothing` test.

**A second wave from the same parallel session, discovered mid-merge:** while verifying
the RLS merge above, the other session (confirmed by the user to be their own second
Claude Code session, since paused) kept working and added
`dss/core/persistence_config.py::repository_for(feature)` — a minimal, explicit,
env-var-gated selector (`EDUDSS_IDENTITY_STORE`/`EDUDSS_SUBSCRIPTION_STORE`, defaulting to
`"local"`) for incrementally cutting individual subsystems over to Postgres — and wired it
into `dss/services/auth_service.py`'s `_load_users()`/`count_users_by_role()`/`_save_users()`.
This is a reasonable, complementary pattern to this session's own `dss/db/` ORM layer (a
lightweight per-feature flag vs. a full schema), so it was kept rather than reverted. Two
real problems found and fixed during reconciliation:
1. **The app was completely broken** for a few minutes: `persistence_config.py` imports
   `dss/core/postgres_repository.py`, which this session had already deleted as part of the
   RLS merge above (its one distinctive capability, RLS, had already been ported and
   independently re-verified). Fixed by restoring `postgres_repository.py`.
2. **A latent crash-on-activation bug**: `auth_service.py`'s new code calls
   `repository.list_users()` / `.count_users_by_role()` / `.get_user_by_username()`, but
   `PostgresTenantRepository` only ever implemented `get_student`/`upsert_student`/
   `list_students` — flipping `EDUDSS_IDENTITY_STORE=postgres` before this gap was noticed
   would have raised a confusing `AttributeError`. First fixed by adding those 3 methods as
   explicit `NotImplementedError` stubs; **the other session then independently simplified
   `persistence_config.py` further** (observed mid-verification, ~15 minutes after the user
   said they'd paused it — likely an in-flight edit landing late, not a contradiction) to
   remove the `PostgresTenantRepository` dependency entirely and raise `NotImplementedError`
   immediately inside `repository_for()` itself when `mode == "postgres"`, without ever
   constructing a half-working repository object. This is a strictly better fix than the
   stub-methods approach — fewer moving parts, fails at the exact call site instead of one
   level removed — so it was kept, `dss/core/postgres_repository.py` was removed entirely
   (now genuinely unreferenced by anything, confirmed via repo-wide grep), and
   `tests/test_persistence_config.py` was updated to match the new, simpler contract.

Both fixes verified: full non-E2E suite green (456/456 passed — the final count including
all 3 new Phase 1 test files — 14 skipped when Postgres isn't configured) and the full E2E
suite (39/39, confirmed on the final state) after each round of changes. The other
session's own `PHASE_CHANGELOG.md` (a parallel, differently-formatted phase report) was
folded into this document and removed to avoid two competing sources of truth for the same
phase.

**A real, disclosed testing limitation:** `tests/test_db_schema.py` and
`tests/test_db_row_level_security.py`, run together in one `pytest` invocation against a
Postgres container that has been through many manual schema drop/recreate cycles in the
same long-lived container process, were observed to occasionally interfere with each other
via `dss/db/session.py`'s global engine singleton (root-caused twice during this session:
once a genuine bug — `dss/db/models.py` was never imported before `Base.metadata.create_all`,
silently creating zero tables — now fixed; once accumulated container-side state after
repeated `DROP SCHEMA CASCADE` cycles from this session's own manual debugging, which
disappeared entirely on a fresh container and has not recurred since). Both files are
individually 100% reliable, repeatedly confirmed, and pass together reliably on a
freshly-provisioned container (confirmed twice in a row). Recommendation for CI: run these
two DB-integration files against a freshly-provisioned container per pipeline run (already
true for any real CI setup, which does not reuse a long-lived hand-debugged container the
way this session's local verification did).
