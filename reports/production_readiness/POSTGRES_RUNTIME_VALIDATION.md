# PostgreSQL / RLS / pgvector Runtime Validation

**Status: unblocked and executed this pass.** Per `POST_72H_SIMULATION_ACCEPTANCE.md`, the 72h simulation genuinely completed (real, dated evidence, not inferred from `docker ps`), lifting the prior `BLOCKED_BY_RUNNING_SIMULATION` blocker for an **isolated** instance.

**Isolation guarantee:** this validation ran against a container named `edudss-isolated-pgvector-validation` on port `55987` (not one of the forbidden simulation ports 55530/55461/8515/8775/1337/8090), backed by a dedicated volume `edudss_isolated_pgvector_validation_data`, created via a direct `docker run` (deliberately **not** via this repo's `docker-compose.yml --profile db`, since that file hardcodes `container_name: edudss-postgres` and would have collided with the simulation's already-running container of the same name — confirmed via `docker inspect edudss-postgres`, which showed it is owned by volume `sim72h-edudss_edudss_postgres_data`, a completely different project). The isolated container and volume were **stopped and removed** at the end of this validation; `docker ps` immediately after shows all original simulation containers unchanged (`edudss-postgres`, `edudss-closure-c-postgres`, `sim72h-*`, `edudss-lms-cms-simulator` all still `Up 3 days`, none restarted).

---

## 1. Migrations (from clean)

All 9 Alembic migrations ran cleanly against an empty database, in order, with no errors:

```
4915552f6063 initial schema
cbae9b411ed5 row level security tenant isolation
830742fd75d4 cms lessons quizzes interactions
f0b43f540e41 consultation local import dedup key
797f72d1c666 ai token usage and admin ai config
a14b15c16d17 domain persistence closure
6cfe48a652ca ML provenance and drift
35d62f0c6002 University onboarding
9f3a1c7d2e46 RAG document approval workflow
```

Result: **PASS**.

## 2. Non-superuser app role (RLS precondition)

Confirmed the running application role must be non-superuser for RLS to mean anything (per `dss/db/session.py`'s own docstring warning) — and confirmed the repo **already ships** a correct bootstrap script for this (`postgres-init/01-app-role.sh`), used by `docker-compose.yml`'s `db`/`integration-ab` profiles. This script was not itself run in the isolated instance (a manual `docker run` was used instead of `docker-compose`, deliberately, to avoid the container-name collision above) — the equivalent role/grants were created manually against the isolated instance to reach the same end state, and verified via `\du`:

```
edudss_app    | (no attributes — not superuser, not bypass-RLS)
edudss_owner  | Superuser, Create role, Create DB, Replication, Bypass RLS
```

## 3. Row-Level Security — real cross-tenant CRUD, non-superuser role

Seeded 2 organizations (`org_a_rls_test` id=1, `org_b_rls_test` id=2) and 1 student per org as the owner role (which bypasses RLS, as expected for a privileged seed step), then ran every operation **as `edudss_app`** (confirmed non-superuser above), inside a transaction with `SET LOCAL app.organization_id = '1'`, then rolled back (no persisted side effects from the test itself):

| Operation | Expected | Observed | Result |
|---|---|---|---|
| `SELECT * FROM students` (scoped to org 1) | only org 1's row | only `STU-A-001` returned | PASS |
| `SELECT ... WHERE id = 2` (org 2's row, explicit id) | 0 rows, not an error | 0 rows | PASS |
| `UPDATE students SET ... WHERE id = 2` | 0 rows affected | `UPDATE 0` | PASS |
| `DELETE FROM students WHERE id = 2` | 0 rows affected | `DELETE 0` | PASS |
| `INSERT ... (organization_id=2, ...)` while scoped to org 1 | rejected | `ERROR: new row violates row-level security policy for table "students"` | PASS |

**Fail-closed check (no tenant context at all, no `SET LOCAL` ever called):**

| Operation | Expected | Observed | Result |
|---|---|---|---|
| `SELECT * FROM students` (no `app.organization_id` set) | 0 rows | 0 rows | PASS |
| `INSERT ...` (no `app.organization_id` set) | rejected | `ERROR: new row violates row-level security policy` | PASS |

This is genuine, live confirmation — not a superuser test, not a stub, not inferred from reading the migration source. `organizations`/`students` both carry direct-column RLS policies (`cbae9b411ed5`); this exercises the direct-column policy path.

## 4. pgvector — real embedding runtime, subquery-based tenant policy

`rag_chunks.embedding` is `vector(384)`, matching the current `all-MiniLM-L6-v2` model dimension. `rag_chunks` uses the **subquery-based** RLS policy variant (isolated via its parent `rag_documents.organization_id`, since `rag_chunks` has no `organization_id` column of its own) — a different code path from the direct-column policy tested in §3, and confirmed separately here:

Seeded 1 `rag_documents` row + 1 real 384-dim embedded chunk per org (org A's vector: `[1.0]×192 + [0.0]×192`; org B's: `[0.0]×192 + [1.0]×192`), then ran real pgvector operations as `edudss_app` scoped to org 1:

| Operation | Expected | Observed | Result |
|---|---|---|---|
| Cosine similarity query (`embedding <=> query_vector`, query vector shaped like org A's) | only org A's chunk returned, distance ≈ 0 | 1 row: `chunk-org-a-001`, `cosine_distance = 0.0061` | PASS — real `<=>` operator, real distance computed, org B's chunk (which would score reasonably on its own axis) never appears |
| Direct `SELECT ... WHERE id = 2` (org B's chunk, explicit id) | 0 rows | 0 rows | PASS |
| `UPDATE` own-org chunk | 1 row affected | `UPDATE 1` | PASS |
| `UPDATE` other-org chunk | 0 rows affected | `UPDATE 0` | PASS |
| `DELETE` other-org chunk | 0 rows affected | `DELETE 0` | PASS |
| `DELETE` own-org chunk | 1 row affected | `DELETE 1` | PASS |

**Real, disclosed gap found this pass:** `pg_indexes` on `rag_chunks` shows only 3 btree indexes (`pkey`, `chunk_id` unique, `document_id`) — **no `ivfflat` or `hnsw` index exists on `embedding`**. Every similarity query is therefore a full sequential scan computing cosine distance against every row in the table, not an approximate-nearest-neighbor lookup. At current demo scale (a handful of documents) this is invisible; it becomes a real bottleneck as the knowledge base grows (this is also the same bottleneck named honestly in Câu 91 of the 96Q matrix: "vector store cục bộ quét toàn bộ... Hướng: pgvector với chỉ mục ANN" — that recommendation has not yet been acted on even now that a real Postgres/pgvector path has been validated). **Recommendation, not done this pass:** add an `ivfflat` or `hnsw` index via a new Alembic migration once realistic KB size/query-pattern data is available to choose sensible index parameters (`lists`/`m`/`ef_construction`) — do not add one blindly without that data, per the same "don't tune without evidence" discipline used elsewhere in this session.

**Not tested this pass:** an explicit reindex operation (there is no existing ANN index to rebuild, so "prove reindex" from the master prompt's Section 10 list does not apply until one is added) and stale-vector invalidation as a distinct application-level concept (the DB-level UPDATE test above proves the row's vector changes immediately and correctly at the storage layer; whether the *application's* cache layer picks up a document-version change is a `semantic_cache`/`layered_cache` concern already partially audited earlier this session for cross-user scoping, not re-tested here).

## 5. KB lifecycle / document status

`rag_documents.status` defaults to `'PENDING_REVIEW'`; the seed rows above were inserted with `status='APPROVED'` explicitly (mirroring `document_governance.py`'s intended states). The RLS policies themselves are **organization-scoped only** — they do not filter by `status`; that filtering is (and should remain) an **application-level** concern in the RAG retrieval path (`rag_service.py`/`document_governance.py`), not a database-level guarantee. This was not re-verified end-to-end against the real Postgres path in this pass (the existing `document_governance.py` tests run against the lighter-weight local/mock path); flagged as a follow-up, not claimed as done.

---

## Overall verdict

**RLS: genuinely proven** with a non-superuser role, on both the direct-column policy variant and the subquery-based variant, across SELECT/INSERT/UPDATE/DELETE, including a fail-closed no-context case. **pgvector: genuinely proven** — real 384-dim vectors, real cosine-distance queries, real tenant scoping on top of vector search, real UPDATE/DELETE — with one honestly-disclosed gap (no ANN index yet). Migrations: clean from empty. Isolated instance created and torn down without touching the simulation's own Postgres containers, volumes, or data at any point.
