# Final Architecture Truth

## 1. Product direction: ONE EDUDSS PRODUCT, ONE CODEBASE

EduDSS is one codebase, one Docker image, serving three deployment
postures via data-level configuration, never via a code fork or a
separate build:

1. **Multi-tenant SaaS** — many universities share one running
   instance, isolated by PostgreSQL Row-Level Security keyed on
   `organization_id`. Verified real (`FINAL_STAGING_SIMULATION.md`
   steps 4-16: two universities, live onboarding, live tenant
   isolation under real queries and under concurrent load).
2. **Dedicated deployment** — a university runs its own instance of the
   same image. This differs only by `Organization.deployment_mode` and
   deployment topology, not by code path. Confirmed at the schema/config
   level; not separately load-tested as its own deployment topology in
   this engagement (it exercises strictly less concurrency than the
   multi-tenant scenarios already tested, so it is not expected to
   surface new capacity findings, but this is stated as an assumption,
   not a tested fact).
3. **Future Ministry/Sector aggregation** — explicitly a **governance
   and authorization question**, not an architecture unlock. The
   multi-tenant RLS model enforces strict isolation BETWEEN tenants by
   design; any future cross-tenant aggregation feature would be a new,
   explicitly authorized capability layered on top, never a side effect
   of what exists today. See
   `docs/architecture/NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md` §9.

## 2. What is real vs. projected, in one place

| Layer | Real, verified this engagement | Projected / not done |
|---|---|---|
| Persistence | PostgreSQL 16 + pgvector, Alembic-migrated, RLS-enforced, real backup+restore | Read replicas, tenant partitioning, PgBouncer — all projected |
| Integration | Real HTTP connector against a dedicated LMS/CMS simulator; real webhook HMAC verification; real idempotent resync across restarts | A real external university LMS was never connected |
| ML/AI governance | Real SHA-256 provenance fingerprinting; real PSI/KS drift detection methodology; a real concurrency bug found and fixed via capacity testing | Drift detection is a methodology, not a guarantee of future model correctness (see `SUBMISSION_MUST_NOT_SAY.md`) |
| AI Gateway | Real multi-provider fallback cascade and quota gate, exercised live in Production Demo Policy mode | No real paid-provider SLA was tested; demo-mode responses are deliberately not the same as a production LLM answer |
| Scale | Real concurrency boundary found (SLO met at 10, violated at 25, single-machine default connection pool); real 5-minute soak (68,454 ops, 0 errors); real 20K-item batch benchmark (7,629/sec) | National/ministry-scale load was never run — explicitly a projection document, not a benchmark |
| Recovery | Real DB backup → verify → **restore-to-fresh-database**, independently queried (Stage 5, closing Workstream D's disclosed gap); real non-DB manifest build/verify | Non-DB restore ORCHESTRATION and a combined DB+non-DB restore drill were never performed — "full disaster recovery" remains PARTIAL, not YES |
| Deployment | Real Docker Compose build of the full stack (Postgres+simulator+migrate+app), CPU-only PyTorch pinned and built, two real fresh-checkout bugs found and fixed (CRLF script, unseeded roles) | No hosted/cloud CI pipeline was ever executed |

## 3. Real bugs found and fixed during this engagement (not hidden)

1. **Issue CONCUR-001** — a genuine race condition in
   `prediction_repository._resolve_or_create_model_version_id()` under
   concurrent first-use of a shared `training_id` (18% error rate at
   concurrency=10 before the fix). Fixed with a SAVEPOINT + retry
   pattern; regression test added.
2. **CRLF line-ending bug** in `postgres-init/01-app-role.sh` — silently
   broke the containerized app-role creation on a fresh Windows
   checkout. Fixed by adding `.gitattributes`.
3. **Unseeded `roles` table on a fresh database** — `seed_roles()` is a
   deployment bootstrap step, not an Alembic migration; a genuinely
   fresh database has zero role rows. Documented as a required
   deployment-runbook step, not silently patched around.

Each of these was found specifically BECAUSE this engagement performed
real, live, adversarial-to-assumptions testing (concurrency benchmarks,
a genuinely fresh worktree checkout, a full container rebuild) — not
because the original implementation was reviewed for the first time.
This is disclosed as evidence that the testing method was genuine, not
as a criticism of the underlying feature work.

## 4. What this document is not

This is not a claim that the architecture is finished or beyond
critique — see `NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md` for the
specific, named next steps (connection pooling, read replicas, object
storage, a real job queue, a real metrics backend) that a genuine
national-scale deployment would require, none of which exist yet.
