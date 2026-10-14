# National / Ministry-Scale Architecture Projection

**ARCHITECTURAL PROJECTION — NOT LOAD-VERIFIED.**

Nothing in this document was benchmarked at national scale. It is a
reasoned extrapolation FROM the real measurements in
`app/reports/production_readiness/WORKSTREAM_D_SCALE_RECOVERY.md` — a
single-machine, single-Postgres-instance concurrency ceiling of roughly
10-25 simultaneous database-backed operations before this specific
deployment's default connection-pool configuration becomes the binding
constraint — toward what a much larger deployment would need. No
Kubernetes, load balancer, or any of the below was implemented as part of
this work; this document exists to answer "what would be required," not
to claim it already exists.

## 1. What the measurement actually showed

The bottleneck found (§Workstream D report) was **not** CPU, not the
network, and not EduDSS's own application code — it was the **default
SQLAlchemy connection pool** (`pool_size=5, max_overflow=10` — the
library default, never explicitly tuned in `dss/db/session.py`) against
one Postgres instance on one machine also running everything else this
session's testing needed. This is a very different (and far easier)
problem than "the architecture cannot scale" — it is "the out-of-the-box
default was never tuned for concurrency beyond development use," which
is exactly the kind of thing that stops mattering once real capacity
planning happens.

## 2. Stateless application instances + load balancing

Streamlit's own execution model (one Python process per browser session,
in-memory `session_state`) means the CURRENT single-process deployment
does not horizontally scale by simply adding more Streamlit processes
behind a load balancer *unless* session affinity (sticky sessions) is
used — a user's browser must keep hitting the SAME backend instance for
the duration of their session. This is a standard, well-understood
pattern (most load balancers support cookie- or IP-based session
affinity), not a redesign; EduDSS's stateless business logic (everything
in `dss/services/`, `dss/db/repositories/`) already does not assume a
single process — the state that would need affinity is purely the
Streamlit UI layer's session_state, not the database.

## 3. PostgreSQL scaling strategy

- **Connection pooling** (PgBouncer or a tuned SQLAlchemy pool) is the
  single highest-leverage change suggested by this session's own
  measurement — before anything else, this is what the data points to.
- **Read replicas** would help specifically for read-heavy paths (the
  Lecturer Dashboard's class-wide overview, `list_predictions`,
  reporting) — write paths (sync, webhook ingestion, predictions) still
  need the primary.
- **Tenant partitioning**: the schema is already tenant-scoped via
  `organization_id` + RLS on every relevant table (verified repeatedly
  throughout this roadmap) — this is the precondition for eventually
  sharding by tenant across multiple Postgres instances if a single
  instance's write throughput becomes the ceiling, without an
  application-code rewrite (only the connection-resolution layer,
  `dss/db/session.py`, would need to route by tenant).

## 4. Caching

`dss/services/semantic_cache.py`'s layered cache (already accepted,
used by `LLMGateway.stream_generate`) is the existing caching layer for
AI responses. A national-scale deployment would extend the same
principle (cache read-heavy, rarely-changing query results — e.g.
resolved connector configs, mapping profiles) rather than introduce a
new caching philosophy.

## 5. Object storage for artifacts

Model artifacts (`.joblib` files) and CMS binaries currently live on
local disk under `data_warehouse/` (see
`ops/non_db_recovery.py`'s inventory, this workstream). At a scale where
multiple stateless application instances need to share the SAME model
artifacts, object storage (S3-compatible) would replace the local
filesystem as the artifact store — `dss/core/warehouse.py`'s own
`get_data_root()` abstraction (already resolves a configurable root path)
is the natural seam for this, not a rewrite of the training/serving code
that reads/writes through it.

## 6. Async/background jobs, queue/event processing

LMS/CMS sync (`PersistentSyncService`) and webhook processing
(`DurableWebhookProcessor`) already run as discrete, idempotent units of
work per the accepted A+B design — this is exactly the shape needed to
move them behind a real job queue (Celery, RQ, or a managed queue
service) for many-university-simultaneous-sync scenarios, without
changing what each unit of work DOES, only how it gets dispatched.

## 7. Observability at scale

`dss/core/observability.py`'s structured logging + operation counters
(already used throughout — AI Gateway, ML provenance, drift evaluation)
would need to feed a real metrics backend (Prometheus/Grafana or
equivalent) rather than process-local counters at multi-instance scale —
the instrumentation POINTS already exist; only the sink changes.

## 8. Backup/recovery implications at scale

`ops/backup_recovery.py` (DB) and `ops/non_db_recovery.py` (everything
else, this workstream) both already produce portable, checksummed
manifests independent of where the underlying storage lives — the same
manifest shape works whether the artifacts are on local disk or object
storage; only the file-access layer changes.

## 9. Governance note (not an engineering concern, stated for completeness)

A Ministry/sector-wide deployment aggregating multiple universities'
data for cross-institutional decision support is a **policy and
authorization question**, not something this architecture unlocks by
itself — the multi-tenant RLS model verified throughout this roadmap
enforces STRICT isolation BETWEEN tenants by design; any future
cross-tenant aggregation feature would be a new, explicit, separately
authorized capability, not a side effect of the existing architecture.

## 10. Honest summary

| | |
|---|---|
| Tested capacity | ~10-25 concurrent DB operations, one machine, one Postgres instance, default connection pool (see WORKSTREAM_D_SCALE_RECOVERY.md) |
| Projected national-scale requirement | Connection pooling (PgBouncer), stateless app instances + sticky-session load balancing, read replicas, tenant partitioning readiness (already schema-compatible), object storage for artifacts, a real job queue for sync/webhook processing, a real metrics backend |
| What was NOT done | No load balancer, no PgBouncer, no object storage, no job queue, no Kubernetes, no multi-instance deployment — none of this was implemented or benchmarked in this workstream |
| National-scale load verified | **NO** |
