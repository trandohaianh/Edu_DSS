# Product Deployment Strategy

## One product, one codebase, two deployment postures today

EduDSS ships as a single Docker image and a single codebase. What
differs between deployment postures is configuration and data, never
source code:

### 1. Multi-tenant SaaS (verified)

One running instance serves many universities. Isolation is enforced at
the database layer via PostgreSQL Row-Level Security keyed on
`organization_id` — not by any application-level filtering that could
be bypassed by a code path someone forgot to update. Verified live in
`FINAL_STAGING_SIMULATION.md` (two universities onboarded, activated,
and load-tested concurrently in one running stack, with zero
cross-tenant data visibility confirmed by direct query, not just by
absence of an error).

**Onboarding path**: `dss/services/university_onboarding.py`'s staged
gate — provision → create admin → configure connector → validate
mapping → test connection → initial sync → activate — each step
independently checkable, with `activate_university()` refusing to flip
a university live until every precondition is genuinely green.

### 2. Dedicated deployment (schema/config-level, not separately load-tested)

The same image, pointed at its own database, for a university that
wants isolation at the infrastructure level rather than only the RLS
level. `Organization.deployment_mode` records this as data, not as a
build flag — there is no separate "dedicated" Docker image or code
branch to maintain. This posture is expected to face strictly less
concurrency than the multi-tenant scenarios already load-tested (single
tenant, not several sharing one pool), so no new capacity finding is
expected — but this is an inference from the existing measurements, not
a separately executed load test, and is stated as such.

### 3. Future Ministry/Sector aggregation (explicitly not built)

A future capability where an authorized ministry-level actor could view
aggregated, cross-university data. This is **not** an architecture
change waiting to be flipped on — the RLS model deliberately makes
cross-tenant access impossible by default, which is the correct default
for a system holding student data. Building this capability later means
building a new, explicitly-scoped, separately-authorized feature (e.g.
a dedicated aggregation role with its own RLS bypass function, audited
and rate-limited), not "raising a flag" on existing code. See
`docs/architecture/NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md` §9 for
the governance framing.

## What a real deployment needs that this engagement did not automate

These are genuine, disclosed gaps a deployment runbook must cover —
listed here rather than glossed over:

1. **Seed reference roles once, post-migration.** A fresh database has
   no `roles` rows (`Admin`, `Giảng viên / CVHT`, `Sinh viên`,
   `Platform Admin`) until `python -m dss.db.seed` (or the equivalent
   `seed_roles()` call) is run. Discovered as a real blocker while
   building Stage 5's live simulation. Must be step 2 of any deployment
   runbook, immediately after `alembic upgrade head`.
2. **Connection pool tuning.** The default SQLAlchemy pool
   (`pool_size=5, max_overflow=10`) is the concrete bottleneck found at
   concurrency=25 in `WORKSTREAM_D_SCALE_RECOVERY.md` §3. A production
   deployment expecting more than roughly a dozen concurrent
   DB-backed operations should tune this before going live, not
   discover it under real load.
3. **Line-ending discipline for shell scripts.** `.gitattributes`
   (`*.sh text eol=lf`) is now in the repo specifically because a
   Windows checkout previously produced a silently broken
   `postgres-init/01-app-role.sh`. Any new shell script added to this
   repository should be checked against this rule.
4. **A real backup schedule and off-site copy.** `ops/backup_recovery.py`
   and `ops/non_db_recovery.py` are the manual/scriptable tools; neither
   this engagement nor the codebase itself schedules or ships backups
   automatically (no cron/systemd-timer/managed-backup-service
   integration exists).
5. **Credential provisioning for real LMS connectors.**
   `configure_connector()` deliberately only accepts an environment
   variable NAME as `credential_reference`, never a raw secret — a real
   deployment must have its own secret-management process to populate
   that environment variable with a genuine token before a live LMS
   connector (as opposed to the accepted simulator) could ever be used.

## What this document is not

This is not a claim that EduDSS has been deployed to any real
production environment — it has not. This is the deployment strategy
and runbook-relevant findings this engineering engagement is handing
off, grounded in what was actually built and tested, not a marketing
description of a finished product.
