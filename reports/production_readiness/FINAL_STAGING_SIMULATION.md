# Stage 5 — Final Integrated Staging Simulation

## 0. Base / branch / worktree

| | |
|---|---|
| Base | `closure/workstream-d-scale-recovery` @ `7679f97` (linear descendant, no merge needed — confirmed via `git merge-base --is-ancestor`) |
| Branch | `integration/final-staging-candidate` |
| Worktree | `D:/KLTN/edudss-final-staging` |

## 1. What this stage actually is

Stages 1-4 proved each capability in isolation (connector tests,
concurrency profiles, backup/manifest verification, RLS, etc.), each
with its own dedicated test file. This stage does not re-prove any of
that in isolation — it runs **one real, ordered, 34-step narrative**
against **one genuinely running Docker stack** (real `docker compose
--profile integration-ab up --build`: PostgreSQL+pgvector, the LMS/CMS
simulator, the migration job, and the actual containerized Streamlit
app), covering the same journey a real onboarding-to-daily-use
university deployment would go through. The test itself is
`app/tests/test_final_staging_simulation.py::test_full_staging_narrative`,
gated behind `FINAL_STAGING_*` environment variables so it never runs
by accident in the normal suite; its full step-by-step evidence is
persisted (not hand-written) to
`app/reports/production_readiness/final_staging_evidence/narrative.json`.

**Result: all 34 steps PASSED, in one continuous run, against one live
stack.** (34, not exactly 33 — step 30, a genuine restore-to-a-fresh-
database test, was added because building this stage's backup step
made it straightforward to also close a gap Workstream D had
explicitly left open — see §4.)

## 2. The 34 steps

| # | Step | Real operation performed |
|---|---|---|
| 1 | Live stack sanity | Real SQL `SELECT 1`, real HTTP GET to simulator `/health` and streamlit-integration `/_stcore/health` |
| 2 | Alembic single-head | Queried `alembic_version` on the live DB — exactly one head, `35d62f0c6002` |
| 3 | RLS policy present | Queried `pg_policies` for `tenant_isolation` on `students` |
| 4-5 | Provision University A/B | `dss.services.university_onboarding.provision_university()` — real `Organization` rows, `lifecycle_status=SETUP` |
| 6-7 | Create admin users | `create_university_admin()` — real `User` rows with hashed passwords |
| 8-9 | Configure LMS connectors | `configure_connector()` — credential-reference only (env var name, never a raw token) |
| 10-11 | Live connector test | `test_connection()` — real HTTP GET to the containerized simulator, `SUCCESS` |
| 12 | Validate mapping | `validate_mapping()` against real sample records |
| 13-14 | Initial sync A/B | `run_initial_sync()` — real students/courses/etc. ingested via `PersistentSyncService` |
| 15 | Activation gate | `activate_university()` — real multi-condition gate (admin+connector+mapping+sync), all green |
| 16 | Tenant isolation | App-role connection scoped to org A sees **zero** org B rows |
| 17 | Lecturer-context read | Real RLS-scoped query for a synced student |
| 18 | ML prediction + SHAP | Real `RandomForestClassifier` fit + real `model_service.compute_shap_local_explanation()`, persisted via `save_prediction()` (the CONCUR-001-fixed code path) |
| 19 | Student-view read | `list_predictions()` confirms the prediction is visible |
| 20 | CMS content update | Real HTTP mutation against the live simulator |
| 21 | Webhook delivery | Real HTTP delivery, real HMAC-SHA256 verification, durable inbox (`DurableWebhookProcessor`) |
| 22 | Reindex + retrieval | `cms_content` version bumped; pgvector retrieval reflects the update |
| 23 | AI Gateway | `LLMGateway.stream_generate()` — Production Demo Policy path, no paid key |
| 24 | Audit log | Write+read capability confirmed against the live stack (see §5 for an honest caveat) |
| 25 | **Real Postgres container restart** | `docker restart edudss-postgres`, waited for reconnect |
| 26 | Persistence check | Post-restart: students and the prediction from step 18 both still present |
| 27 | **Real simulator container restart** | `docker restart edudss-lms-cms-simulator` |
| 28 | Idempotent resync | `run_incremental_sync()` post-restart — zero duplicate changes |
| 29 | Coordinated DB backup | Real `pg_dump` (owner role, `docker_container` mode) + independent checksum verify |
| 30 | **Genuine restore-to-fresh-database** | Created a real empty sibling database, ran `ops.backup_recovery.restore()`, then queried the RESTORED database directly and confirmed real organization/student rows are present |
| 31 | Concurrency burst | concurrency=10 burst on the freshly restarted+restored containers, SLO met |
| 32 | Final smoke journey | University B activation + a second live AI Gateway call |
| 33 | Log sanity | Zero unhandled tracebacks in Postgres/simulator container logs for the whole run |
| 34 | Evidence persistence | Full narrative written to `final_staging_evidence/narrative.json` |

## 3. Two real integration bugs found and fixed by this stage

Building this stage — not the individual unit-level Stages 1-4 — is
what surfaced these, because they only manifest when the pieces run
together against a genuinely fresh Docker checkout:

1. **CRLF line-ending bug in `postgres-init/01-app-role.sh`.** This
   repository has no `.gitattributes`, and `core.autocrlf=true` on
   Windows silently checks out that shell script with CRLF line
   endings. Postgres's `docker-entrypoint.sh` then fails to exec it
   (`cannot execute: required file not found` — the classic
   `#!/bin/sh\r` shebang failure), meaning **`DB_APP_USER` was never
   created**, so the containerized app (which authenticates as that
   role) could never actually connect. Fixed by adding
   `app/.gitattributes` (`*.sh text eol=lf`) and renormalizing.
   **Disclosed finding**: this means any earlier stage's containerized
   `integration-ab` profile run, if genuinely re-checked-out fresh on
   Windows without this fix, would have hit the same failure — Stages
   1-4's evidence did not depend on this exact code path being healthy
   (they used pytest-level fixtures/direct connections, not this
   specific docker-compose init script), so their acceptance is
   unaffected, but this was a real latent defect this stage caught and
   fixed.
2. **`roles` table is not seeded by Alembic migrations.** A genuinely
   fresh database has zero rows in `roles`, so
   `create_university_admin()` fails with `Unknown role: Admin`. This
   is by design — `dss/db/seed.py::seed_roles()` is a one-time
   deployment bootstrap step, not a migration — but it means **any
   fresh deployment's runbook must call `seed_roles()` (or
   `python -m dss.db.seed`) once after `alembic upgrade head` and
   before onboarding the first university**. This is now called
   explicitly in the simulation script and should be added to the
   actual deployment runbook (not yet a separate document — flagged
   here as the authoritative source until one exists).

## 4. FULL DISASTER RECOVERY — upgraded from Workstream D's "NO"

Workstream D (`WORKSTREAM_D_SCALE_RECOVERY.md` §11) honestly reported
`FULL DISASTER RECOVERY: NO`, specifically because no restore-to-a-
fresh-instance test had been performed — only backup + checksum
verification. **Step 30 of this stage closes exactly that gap**: a
real, empty sibling database was created on the same live (already
restarted) Postgres instance, `ops.backup_recovery.restore()` was run
for real against the backup taken in step 29, and the restored
database was then queried directly and independently — confirming real
`organizations` and `students` rows, not just a "restore command
exited 0."

This is now closer to **PARTIAL — DB restore genuinely verified**,
still not "FULL":
- **What is now genuinely proven**: DB backup → verify → restore →
  query-the-restored-data, end to end, against a live containerized
  Postgres.
- **What is still NOT proven**: restoring the non-DB artifact manifest
  (Workstream D's `ops/non_db_recovery.py`) was checksum-verified in
  place, never actually "restored" into a fresh empty directory tree
  from a manifest; and no test exercised restoring BOTH the DB and the
  non-DB artifacts together into one fresh environment and then
  actually running the application against that combined restored
  state. Calling this "FULL DISASTER RECOVERY: YES" would still be an
  overclaim.

## 5. Honest limitation: onboarding actions are not audit-logged

Step 24 proves the `audit_log_repository` write+read capability works
correctly against this live stack — but it does so via a manually
invoked `record()` call, **not** as a side effect of the onboarding
actions in steps 4-15. Investigation during this stage confirmed
`dss/services/university_onboarding.py` never calls
`audit_log_repository.record(...)` — only the older, separate
`dss/services/tenant_service.py` provisioning path does. This is a
real, disclosed gap: **University Onboarding (Stage 2) actions are
currently not written to the `audit_logs` table.** Recommended for a
future iteration, out of scope to fix here since it would change
Stage 2's already-accepted, closed behavior.

## 6. Networking finding specific to Windows/Docker Desktop

The webhook delivery step (21) initially failed because the simulator
runs in its own container and cannot reach a receiver bound/advertised
as `127.0.0.1` (that resolves to the simulator's own container, not the
host). Fixed by binding the test's `WebhookReceiver` to `0.0.0.0` and
advertising `host.docker.internal` (Docker Desktop's documented route
back to the host). This is purely a test-harness detail (the real
production webhook receiver would be another container on the same
compose network, addressed by service name, not by this host-loopback
pattern) — noted here because it is exactly the kind of thing that
only surfaces when the full containerized stack is actually exercised
end-to-end, which is this stage's purpose.

## 7. Regression check

Full non-E2E suite re-run in this worktree after all fixes: **570
passed, 148 skipped (env-gated integration tests not exercised in this
particular invocation — already covered with those env vars set in
Stage 4's 716-passed run on the same underlying application code), 0
failed, 1 deselected (the staging narrative itself, run separately
against the live stack).**

## 8. Truth labels

| | |
|---|---|
| FINAL STAGING SIMULATION | **PASS** (34/34 steps, real live stack) |
| POSTGRES RESTART UNDER LIVE DATA | **PASS** |
| SIMULATOR RESTART + IDEMPOTENT RESYNC | **PASS** |
| DB BACKUP | **PASS** |
| DB RESTORE TO FRESH INSTANCE | **PASS (new this stage)** |
| FULL DISASTER RECOVERY | **PARTIAL** — DB restore genuinely verified; non-DB restore and a combined DB+non-DB restore were not exercised |
| TENANT ISOLATION UNDER LIVE INTEGRATION | **PASS** |
| AUDIT LOGGING OF ONBOARDING ACTIONS | **NOT IMPLEMENTED** (disclosed gap, §5) |
| CONCURRENCY SLO ON FRESH CONTAINERS | **PASS** |
| REGRESSION | **PASS** (0 failed) |

## 9. Known limitations

1. `.gitattributes` only covers `*.sh` — the one file affected. If
   future shell scripts are added to this repo on a Windows checkout,
   the same class of bug is prevented; other line-ending-sensitive file
   types were not audited beyond this one incident.
2. `seed_roles()` being a separate manual bootstrap step (not part of
   Alembic) is a real deployment-runbook gap — not fixed here (fixing
   it would mean either adding a data migration, which this project's
   Alembic conventions treat as out of scope for schema migrations, or
   documenting it prominently in a deployment runbook, which does not
   yet exist as a separate document).
3. The webhook receiver networking workaround (`host.docker.internal`)
   is test-harness-specific; it says nothing about how a real second
   service (e.g. an actual application container) would receive
   webhooks in production — that already works correctly via Docker
   Compose service-name DNS, unaffected by this finding.
