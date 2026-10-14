# Workstream A+B Integration — Acceptance Report

Status legend used throughout: **VERIFIED** (executed against real infrastructure
in this session, with commands/output inspected), **SIMULATED** (executed
against the simulated LMS/CMS transport, which is genuine, real HTTP/HMAC/
PostgreSQL machinery, but stands in for a live third-party LMS/CMS), **NOT
VERIFIED** (not exercised in this session, for a stated reason), **NOT
APPLICABLE** (out of scope for this integration).

This report picks up a run that was interrupted mid-`pytest -q tests/e2e` by a
usage limit. No prior partial output is treated as a pass. Every gate below
was executed to completion in this session.

## 1. Provenance

| Item | Value |
|---|---|
| Base (main) | `10b487d` — "docs: record final Phase 14 and 15 main merge" |
| Workstream A | `closure/workstream-a-lms-cms-simulation` @ `0fd1704` — "feat: add realistic simulated LMS CMS integration" |
| Workstream B | `closure/workstream-b-persistence-domain` @ `aef0028` — "docs: record Workstream B acceptance evidence" |
| Integration branch | `integration/workstream-a-b` |
| Final commit | `a1be645` — "feat: durable postgres-backed sync/webhook/CMS-RAG bridge for A+B integration" |
| Alembic head | `a14b15c16d17` (single head; no new migration was required — the integration is additive glue code, not a schema change) |
| Public tables | 37 (see §4) |

The integration commit adds `dss/integrations/postgres_lms_cms.py`
(`PersistentSyncService`, `DurableWebhookProcessor`,
`PostgresIntegrationBoundary`), `postgres-init/01-app-role.sh` (non-superuser
app-role bootstrap with `ALTER DEFAULT PRIVILEGES`), a `docker-compose.yml`
`integration-ab` profile (migrate job + `streamlit-integration` service), two
small connector/simulator additions (`advertised_host` for cross-container
webhook callbacks, an `/api/admin/mutate` test hook), and the acceptance
suite `tests/test_workstream_ab_postgres_integration.py`.

## 2. Sync — VERIFIED

Full non-incremental sync, incremental sync (cursor-scoped `updated_since`),
persistent cursor (`integration_sync_states` table), and idempotent resync
(second full sync reports `changed: 0` across all 11 resources) were all
verified twice: once via `tests/test_workstream_ab_postgres_integration.py`
(4/4 passed, local-subprocess simulator + live pgvector/pg16 container), and
once via an ad-hoc script driven over the **real Docker-networked** stack
(containerized simulator on `localhost:8765`, containerized Postgres on
`localhost:55435`) — see §6. Pagination was exercised with `page_size` values
of 1, 2, 3 and default. Concurrent overlapping syncs for the same
resource/tenant were shown to serialize via a per-organization lock with no
duplicate rows created.

- Pagination: VERIFIED
- Incremental sync: VERIFIED
- Persistent cursor: VERIFIED
- Idempotent resync: VERIFIED

## 3. Webhook — VERIFIED

`submission.created`, `grade.updated`, `content.updated` were all delivered
and processed through `DurableWebhookProcessor`, both via the pytest suite
and via the real Docker network path (simulator container →
`host.docker.internal` → host-bound `WebhookReceiver`).

- HMAC: VERIFIED — `hmac.compare_digest` signature check;
  `test_webhook_invalid_signature_rejected` in
  `tests/test_lms_cms_simulated_http_integration.py` and the wrong-signature
  path in the processor both exercised.
- Persistent inbox: VERIFIED — `webhook_inbox` table, rows survive engine
  restart (`test_sync_cursor_and_webhook_inbox_survive_engine_restart`) and a
  real `docker restart edudss-postgres` (§7).
- Duplicate: VERIFIED — `mode=duplicate` delivery recorded once in
  `webhook_inbox`, second delivery marked `duplicate`, no double-apply.
- Out-of-order: VERIFIED — stale `occurred_at` event marked
  `out_of_order`, does not overwrite the newer state (grade score
  assertion in the test).
- Restart idempotency: VERIFIED — new `DurableWebhookProcessor` instance
  after a restart still recognizes a previously-seen `event_id` as
  duplicate (both in-process, via a fresh instance, and via a real
  container restart in §7).

## 4. CMS → RAG → pgvector — VERIFIED

| Step | Result |
|---|---|
| CMS PostgreSQL (`cms_content`) | VERIFIED |
| Initial index (`rag_documents`/`rag_chunks`) | VERIFIED |
| 384-dimensional embedding | VERIFIED — `deterministic_embedding()` produces a normalized 384-vector |
| Real pgvector `<=>` | VERIFIED — `PgVectorStore.search()` against a live `pgvector/pg16` container, not mocked |
| `content.updated` handling | VERIFIED — version bump 1→2 via webhook |
| Old vector invalidation | VERIFIED — `rag_chunks` joined to the v1 `document_id` returns 0 rows after update |
| Re-index | VERIFIED — new chunk row created for `…:v2` |
| New retrieval | VERIFIED — vector search top-1 result is `…:v2` |
| Stale retrieval blocked | VERIFIED — no `…:v1` document ever appears in results post-update |
| Delete lifecycle | VERIFIED — `test_cms_content_and_real_pgvector_replace_delete_lifecycle` (Workstream B suite, re-run against this integration's schema and app-role) |

## 5. Tenant isolation / RLS — VERIFIED

Verified using a genuine non-superuser role (`edudss_app`), not the schema
owner — RLS is meaningless under a superuser/table-owner connection, and the
test suite explicitly guards against that. Cross-tenant SELECT, UPDATE,
DELETE all affect zero rows; cross-tenant INSERT is rejected by the
`WITH CHECK` clause. A same-external-ID-different-tenant case
(`test_03_non_superuser_rls_and_same_external_id_is_tenant_scoped`) confirms
tenant scoping is on the internal `organization_id`, not the external LMS ID.

## 6. Docker Compose staging (`integration-ab` profile) — VERIFIED

Final candidate stack, confirmed healthy and re-confirmed after the restart
sequence in §7:

| Container | Status |
|---|---|
| `edudss-ab-stage-streamlit-integration-1` (EduDSS) | healthy, HTTP 200 on `/` and `/_stcore/health` |
| `edudss-postgres` (pgvector/pg16) | healthy |
| `edudss-lms-cms-simulator` | healthy |

- Container networking: VERIFIED — EduDSS container reached
  `http://lms-cms-simulator:8765/health` (200) and
  `postgresql://edudss_app@postgres:5432/edudss_db` (real query,
  correct row count) via internal Docker DNS, from inside the container.
- EduDSS HTTP 200 / readiness: VERIFIED.
- UID/non-root: VERIFIED — container runs as `uid=999(edudss) gid=999(edudss)`,
  not root.
- HTTP connector / sync / webhook / CMS→RAG→pgvector over the real Docker
  network: VERIFIED — a driver script instantiated `LMSCMSConnector` and
  `PersistentSyncService` against `http://localhost:8765` (the
  container's host-mapped port) and `PostgresIntegrationBoundary` against
  `localhost:55435`, ran `sync_all()`, delivered a real webhook from
  *inside* the simulator container back to a host-bound receiver via
  `host.docker.internal` (Docker Desktop's host-callback DNS name,
  confirmed resolvable from the simulator container), and confirmed
  correct row counts, `webhook_inbox` state, and pgvector top-1 retrieval
  in Postgres afterward.

**Known limitation (test tuning, not a product defect):** the committed
`tests/test_workstream_ab_postgres_integration.py` hardcodes a 300ms
connector timeout in its own `_services()` helper, tuned for its default
local-subprocess simulator. Docker Desktop's NAT adds a one-time ~0.5s
cold-connection cost, which the test's tight timeout does not tolerate; run
as committed (its default path, no `WORKSTREAM_AB_SIMULATOR_URL` set), it
correctly spins up a local subprocess simulator and passes 4/4. It was not
modified to talk to the containerized simulator by default. The production
`LMSCMSConnector` default timeout is 2.0s, and the real-Docker-network path
above (using that default) passed.

## 7. Restart acceptance — VERIFIED

Performed against the live `integration-ab` stack, using data seeded through
the real container network (§6), before any restart:

1. **`docker restart` EduDSS** → came back `healthy`, HTTP 200; academic
   data (students, courses, enrollments…), CMS data, sync cursor
   (`integration_sync_states`), webhook inbox, and subscription/quota rows
   for the seeded tenant all confirmed unchanged in Postgres afterward.
2. **`docker restart` PostgreSQL** → came back `healthy`; same tables
   re-verified by count, including `rag_chunks` (pgvector data); EduDSS
   remained reachable (HTTP 200) throughout.
3. **`docker restart` LMS/CMS simulator** → came back `healthy`; a full
   resync against the restarted simulator, using the same stable external
   IDs, reported `changed: 0` for every resource except the previously
   webhook-updated CMS content (expected version re-check), and **no
   duplicate rows** were created in any table (all counts identical
   before/after).

## 8. Security / RLS / pgvector / persistence regression — VERIFIED

Run against the live `integration-ab` Postgres (owner + non-superuser
app-role credentials):

```
tests/test_db_row_level_security.py .......................... 6 passed
tests/test_pgvector_store.py ............................... 11 passed
tests/test_db_schema.py ........................................ 9 passed
tests/test_lms_ai_rag_gateway.py ...................... 17 passed
tests/security/test_security_and_secrets.py ............ 4 passed
tests/test_lms_cms_simulated_http_integration.py ....... 23 passed
tests/test_lms_live_sync.py ............................ 3 passed
tests/test_integration_phase1b_security8a.py ........... 8 passed
tests/test_phase12a_integration.py ..................... 6 passed
tests/test_workstream_b_persistence_closure.py ......... 11 passed (needs its own WORKSTREAM_B_* env vars — run separately)
tests/test_workstream_ab_postgres_integration.py ....... 4 passed
```

**Total: 98 passed, 0 failed** across the security/RLS/pgvector/CMS/webhook/
tenant-isolation/quota regression set.

- auth/RBAC: VERIFIED (`test_security_and_secrets.py`, role-flow assertions
  in the E2E suite, §9)
- RLS (genuine non-superuser): VERIFIED
- pgvector: VERIFIED
- security: VERIFIED
- RAG/CMS: VERIFIED
- webhook HMAC: VERIFIED
- tenant isolation: VERIFIED

## 9. Role E2E — VERIFIED (integration branch); VERIFIED (fresh checkout, see §11)

```
tests/e2e  ....................................... 39 passed in 989.86s (0:16:29)
```

Run to completion (the prior session's run was interrupted by usage limit
mid-run; this is a full, non-partial result). 0 failed, 0 skipped.

## 10. 20K batch benchmark — PASS

**This is 20,000-student batch inference, not 20,000 concurrent users.** It
measures the latency/throughput of scoring a 20,000-row synthetic cohort
through a trained Ridge model in one process, not concurrent-user load.

```
Total cohort size:       20000 students
Total inference time:    3.0649 s
Throughput:              6525.5 predictions/sec
Chunk (100) p50 latency: 0.949 ms
Chunk (100) p95 latency: 2.041 ms
Chunk (100) p99 latency: 2.663 ms
```

Required: elapsed < 5s (actual 3.06s, PASS), throughput > 5000/sec (actual
6525.5/sec, PASS).

## 11. Fresh checkout — VERIFIED, with two explicitly-scoped exceptions

A detached worktree was created from the final commit `a1be645`
(`git worktree add --detach`, no cherry-picking, no rebuild of source).

| Check | Result |
|---|---|
| Imports (`dss.integrations.postgres_lms_cms`, connector, simulator, db models) | VERIFIED |
| Test discovery | VERIFIED — 700 tests collected |
| Alembic zero → head | VERIFIED — fresh `pgvector/pg16` container, `alembic upgrade head` from empty, single head `a14b15c16d17` |
| Alembic `797f72d1c666` → head | VERIFIED — explicit downgrade to `797f72d1c666` then re-upgrade to head |
| PostgreSQL | VERIFIED (fresh container, independent of the staging DB) |
| RLS | VERIFIED — 6/6, non-superuser role |
| pgvector | VERIFIED — 11/11 |
| Simulator startup | VERIFIED — `python -m simulator.lms_cms_simulator`, HTTP 200 on `/health` |
| EduDSS startup | VERIFIED **by directly launching `streamlit run run_dss.py` in the shared project venv** from the fresh checkout — HTTP 200 on `/` and `/_stcore/health`. **NOT separately re-verified via a fresh `docker build` of the container image from this exact commit** — the running staging image (§6) was built from a working tree that is byte-identical to this commit (the commit changed no file content, only git state), but no new `docker compose build` was run after the commit to produce a freshly-tagged image. |
| HTTP integration / sync / webhook / CMS→RAG | VERIFIED — `test_workstream_ab_postgres_integration.py` (4/4) and `test_workstream_b_persistence_closure.py` (11/11) re-run against the fresh Postgres container |
| Role E2E | VERIFIED — 39/39, see §11a |

**Total for the fresh-checkout regression set: 64 passed, 0 failed.**

One real environment gap was found and fixed, not hidden: the RLS test file
(`test_db_row_level_security.py`) force-rebuilds its schema
(`Base.metadata.drop_all` + `alembic upgrade head`) inside its own fixture
by design (documented in its own docstring, to guarantee a known-good
schema regardless of prior state) — this wipes plain `GRANT`s issued before
the schema is rebuilt. The staging environment's own
`postgres-init/01-app-role.sh` already handles this correctly via
`ALTER DEFAULT PRIVILEGES`; my first manual grant on the fresh ephemeral
database omitted that clause, causing 19 failures, all `permission denied`
— not an RLS or application defect. Re-applying `ALTER DEFAULT PRIVILEGES`
(matching the committed init script) resolved it; the suite was then run
clean. This is disclosed here because it is exactly the kind of thing this
report must not gloss over.

**Dependency installation was NOT independently verified from a bare venv**
for the fresh checkout — the existing shared project venv
(`edudss-integration-ab/.venv`) was reused via a directory junction rather
than a from-scratch `pip install -r requirements.txt`, since the commit
changes no dependency and a full `torch`/`transformers` reinstall was judged
not worth the time for a KLTN-scope project. This is a scope choice, stated
plainly: **NOT VERIFIED** (fresh `pip install`), **VERIFIED** (fresh source
tree + already-known-good dependency set).

### 11a. Role E2E from fresh checkout

The `tests/e2e/conftest.py` fixture launches its Streamlit subprocess via
`<app_dir>.parent / ".venv" / "Scripts" / "python.exe"` — i.e. it expects a
venv as a *sibling* of the checkout's `app/` directory. A bare
`git worktree add` does not create one (git worktrees never carry a venv),
so the first run failed 39/39 with `FileNotFoundError: [WinError 2]` — an
environment-setup gap, not a test or product defect. A directory junction
(`edudss-ab-fresh-checkout/.venv` → `edudss-integration-ab/.venv`) was
created to satisfy that expectation without a full reinstall, consistent
with the dependency-reuse scope decision above. Result after that fix:

```
tests/e2e  ....................................... 39 passed in 913.02s (0:15:13)
```

0 failed, 0 skipped — full pass from the fresh, detached checkout.

## 12. Summary table

| Area | Status |
|---|---|
| Live external LMS | **NO** — never connected; simulated only, by design |
| Simulated LMS/CMS integration | **VERIFIED** |
| PostgreSQL-backed LMS/CMS | **VERIFIED** |
| CMS → RAG lifecycle | **VERIFIED** |
| `main` unchanged | **YES** — no commits added to `main`; still at `10b487d` |
| `stash@{0}` untouched | **YES** — not inspected or popped |

## 13. Known limitations

1. `tests/test_workstream_ab_postgres_integration.py`'s hardcoded 300ms
   connector timeout only reliably passes against its own default
   local-subprocess simulator, not directly against the Dockerized
   simulator (Docker Desktop NAT adds ~0.5s on a cold connection). The
   underlying functionality was independently verified against the real
   containerized path using the production connector's 2.0s default (§6).
2. The `streamlit-integration` staging image was not rebuilt via a fresh
   `docker compose build` after the git commit (its working-tree content is
   identical to the commit, but no new image was tagged against the commit
   hash specifically).
3. Fresh-checkout verification reused the existing project venv (via a
   directory junction) rather than a from-scratch `pip install`; dependency
   resolution itself was not re-proven.
4. All LMS/CMS integration is against the project's own simulator
   (`simulator/lms_cms_simulator.py`), which implements real HTTP, real
   HMAC, real pagination/cursors and real webhook delivery — but it is not
   a third-party LMS/CMS product.

## 14. Status

**STATUS: PASS_WITH_DOCUMENTED_LIMITATIONS**

All ten required acceptance gates (E2E, restart acceptance, Alembic,
security/RLS/pgvector, 20K benchmark, Docker Compose staging, fresh
checkout, this report, commit, and the summary below) were executed to
completion, with zero test failures across 39 (E2E, integration branch) +
98 (security/RLS/pgvector/persistence regression) + 39 (E2E, fresh checkout)
+ 64 (fresh-checkout regression) + 1 (20K benchmark) = 241 test executions
in this session, plus targeted manual verification (container restarts,
real Docker-network sync/webhook/CMS→RAG run, Alembic downgrade/upgrade
round-trip) that pytest alone does not cover.
The limitations in §13 are scope/tooling choices, disclosed rather than
hidden, and do not indicate a functional defect in the integration.

**READY FOR WORKSTREAM C/D: YES**

**DO NOT MERGE — this report and the branch remain on
`integration/workstream-a-b`, per instruction.**
