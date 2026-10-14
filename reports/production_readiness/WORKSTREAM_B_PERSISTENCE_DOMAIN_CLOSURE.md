# Workstream B — PostgreSQL, RAG and Domain Persistence Closure

**Base:** `10b487dd2e187febc645373ce77e6a1cbb0039d8`  
**Branch:** `closure/workstream-b-persistence-domain`  
**Status:** `PASS_WITH_DOCUMENTED_LIMITATIONS`

## Scope and storage matrix

| Domain | Before | After | Database/runtime | Fallback | RLS | Restart persistence | Evidence / limitations |
|---|---|---|---|---|---|---|---|
| Students, lecturers, courses, enrollments | PostgreSQL tables existed; simulator/DataFrame ingestion did not use an external-ID contract | Tenant-scoped idempotent upsert and DataFrame cutover | PostgreSQL when `EDUDSS_ACADEMIC_STORE=postgres` | Existing local path remains explicit | Yes | Yes | First/repeat/update/wrong-tenant integration tests |
| Academic records and recommendations | Phase 1C PostgreSQL runtime | Preserved | PostgreSQL primary with explicit fallback | Yes | Yes | Yes | Existing Phase 1C regression suite |
| Assignments, submissions, grades, attendance, activities | No durable application-side model | New repository-backed domain tables and upserts | PostgreSQL | None claimed | Yes | Yes | Real PostgreSQL Workstream B test |
| CMS lessons/content | JSON lesson registry was the active path | CMS lesson repository switches to PostgreSQL; durable source metadata and version/checksum lifecycle | PostgreSQL when `EDUDSS_CMS_STORE=postgres` | Existing JSON path remains explicit | Yes | Yes | Create/read/update and engine-restart checks |
| Knowledge Base / RAG | Real pgvector CRUD existed; CMS replacement/invalidation orchestration was incomplete | CMS-to-RAG service performs create/read/update/delete/invalidate/re-index and removes replaced chunks | PostgreSQL + pgvector `<=>` | Existing local vector store remains explicit | Yes | Yes | Real vector lifecycle test verifies old and invalidated chunks are not retrievable |
| Sync state | Process-side state only | Durable cursor, source/resource, status, error and last-success state | PostgreSQL | None | Yes | Yes | Engine restart test |
| Webhook inbox | No durable receiving-side state | Durable event inbox with duplicate and out-of-order decisions, retry/error fields | PostgreSQL | None | Yes | Yes | Duplicate/out-of-order behavior survives engine restart |
| Users | PostgreSQL identity supported create/read | Authorized update, enable/disable, admin password reset and role change | PostgreSQL when identity store selects it | Existing JSON identity remains explicit | Yes | Yes | Password hashing, disabled login, RBAC and audit tests |
| Organizations | RLS boundary existed | Provision, configure, enable and disable lifecycle | PostgreSQL | None claimed | Config is RLS protected | Yes | Disabled organizations block new identity operations; data is retained |
| Subscription/quota | Subscription values existed; request quota was not atomically enforced | Row-locked counters and deterministic quota error; student/course and AI request limits enforced | PostgreSQL when subscription store selects it | Existing local subscription remains explicit | Yes | Yes | Below/at/over/reset tests |

## Migration acceptance

- Old accepted head: `797f72d1c666`.
- New single head: `a14b15c16d17`.
- New migration: `a14b15c16d17_domain_persistence_closure.py`.
- Adds tenant-scoped external IDs to four academic entities and creates ten durable domain tables.
- Enables and forces tenant RLS on every new tenant-owned table.
- Zero to head: passed on a clean PostgreSQL database.
- `797f72d1c666` to head: passed.
- Head downgrade to `797f72d1c666` and re-upgrade: passed.
- Public tables at head: **37**. pgvector extension: **0.8.6**.

## Current test evidence

- Workstream B: **11 passed** against PostgreSQL and pgvector, including application-engine restart and concurrent first-use quota checks.
- PostgreSQL schema/RLS/pgvector component run: **26 passed** with a genuine non-superuser application role.
- Full non-E2E: **632 passed, 2 skipped** in 94.43 seconds. The two skips are environment-conditional tests; no failures.
- Full E2E: **39 passed** in 844.82 seconds with a real Streamlit subprocess and Playwright.
- Focused security run: **32 passed**.
- Current Phase 1C repository run: **35 passed**.
- Python compile: passed for `dss` and the Workstream B test module.
- 20k batch benchmark, unchanged: one loaded-machine run missed the throughput threshold at 4.2797 s / 4673.2 predictions/s; immediate repeat passed at **2.6237 s / 7622.8 predictions/s**. The full non-E2E run, which includes the same benchmark, also passed. This is batch inference and is not described as concurrent-user load.

## Security and operational behavior

- All new domain rows include `organization_id`; unique external IDs are scoped to the tenant.
- New tables use forced PostgreSQL RLS. Cross-tenant SELECT/UPDATE/DELETE affect zero rows and cross-tenant INSERT is rejected through a non-superuser role.
- User administration requires the Admin role. Password reset stores the existing salted hash format; plaintext passwords and hash/salt values are excluded from audit payloads.
- Quota increments lock the counter row and reject over-limit requests without incrementing usage.
- Instrumentation uses the existing Phase 12A observation functions; no second logging pipeline was introduced.

## Documented limitations

- Workstream B supplies receiving-side persistence contracts. It does not contain the Workstream A simulator, HTTP connector, delivery mechanism or role journeys.
- Organization assignment is made when an administrator creates a user in a tenant. Cross-tenant user transfer is intentionally absent because the application role is RLS scoped and there is no separate privileged control-plane credential contract. Consequently no `organization.changed` event is claimed.
- PostgreSQL cutover is configuration gated. Existing local implementations remain as explicit compatibility paths; database write failures do not silently report successful PostgreSQL persistence.
- CMS large binaries remain outside PostgreSQL. The database stores truthful content metadata, checksum, reference, version and RAG document identity.
- AI request count enforcement is new. Existing Phase 1C AI token accounting remains the token ledger; no payment, invoice or billing-provider behavior is implemented.
- The performance assertion is sensitive to host load, as shown by the recorded miss and immediate passing repeat.

## Integration contract for Workstream A

The durable boundary preserves `organization_id`, all requested `*_external_id` identifiers, `content_external_id`, and `event_id`. Workstream A can call the repository/service boundary after validation and mapping without importing a simulator into the application persistence layer.

## Fresh candidate and Docker acceptance

- Candidate `b7a33b09265983ea4a756d54f599b166cd69c64c` was checked out as a detached worktree with no required untracked application source.
- Fresh discovery found **673 tests**. A new database migrated from zero to `a14b15c16d17`, then all **11** Workstream B tests passed from the detached checkout.
- Fresh Streamlit startup returned HTTP **200** and `/_stcore/health` returned `ok`.
- Docker image `edudss-workstream-b:b7a33b0` built from that exact checkout in 641.1 seconds. The configured image user is `edudss`; runtime UID is **999**.
- The running container returned HTTP **200**, Streamlit health `ok`, and reached Docker health status `healthy`.
- Container readiness reported the required application and PostgreSQL checks as `ready`. The 11 Workstream B tests also passed inside the container against the migrated PostgreSQL database, exercising real pgvector lifecycle operations even though the optional readiness gate reported pgvector as `not_required` under the container's selected feature flags.
- PostgreSQL container restart preserved academic/CMS/sync/webhook/quota records. A dedicated 384-dimensional vector named `restart-proof-chunk` was retrieved before and after database restart through a new `PgVectorStore` connection.
