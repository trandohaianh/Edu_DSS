# Phase 15 comprehensive testing and final QA

Status: **PASS_WITH_DOCUMENTED_LIMITATIONS**.

## Scope and provenance

The QA branch `testing/phase15-final-qa` was created from accepted main
`7fd9c91551d245d3fdab0c4959abffe71c1ce13d`. Phase 14 CI/CD files were not
changed. Test discovery found **662 tests**. This phase changed only QA evidence;
no application, database migration, Docker, CI/CD, or test implementation was
modified because the new execution found no reproducible application defect.

The detailed feature inventory is in `FINAL_TEST_MATRIX.csv`. A PASS in that
matrix means the cited behavior was exercised, not merely that a test file
exists.

## Current execution evidence

| Gate | New Phase 15 result |
|---|---|
| Full non-E2E excluding the separately repeated load benchmark | **620 passed, 2 skipped** in 123.09 s |
| Full UI/E2E | **39 passed** in 877.12 s |
| Explicit component gate | **117 passed** in 34.28 s |
| PostgreSQL | **9 passed** |
| RLS | **6 passed** |
| pgvector | **11 passed** |
| Security | **24 passed** |
| Phase 12A | **14 passed** |
| Phase 1C | **42 passed** |
| Phase 13 unit | **11 passed** |
| Phase 13 real backup/restore integration | **1 passed** in 7.16 s |

The two ordinary-suite skips are conditional environment-dependent integration
tests. Phase 13's real integration test was configured separately and passed;
no skip is represented as positive evidence.

## Database and tenant evidence

Dedicated PostgreSQL databases were used. Fresh zero-to-head, a database at the
previous revision upgraded to head, a current-to-head no-op, and a safe
downgrade/re-upgrade cycle all finished at Alembic `797f72d1c666`. The fresh
schema contained **27 public tables** and pgvector **0.8.6**.

Runtime tenant proof used the genuine non-superuser `phase15_app` role. Current
RLS tests exercised cross-tenant SELECT, INSERT, UPDATE, and DELETE. Repository
tests covered the accepted PostgreSQL-backed domains. Local/default behavior,
PostgreSQL selection, and documented fallback paths passed the complete suite;
the evidence does not relabel repository-ready domains as fully migrated.

## Backup and recovery regression

The real Phase 13 test created a **129,721-byte** custom archive in **0.703 s**,
verified SHA-256
`2c7998841db6d863c0007588e58db54179085d2d66ae5b1f29aa2ef4c428577d`,
and restored an initially empty database in **1.578 s**. Source/target
verification took **0.344 s** and application/auth repository checks took
**0.688 s**. Restored authentication, non-superuser RLS, 384-dimensional real
server-side pgvector retrieval, metadata, ownership, and ranking passed.

This remains database recovery evidence. Full disaster recovery remains **NO**.

## Performance

The existing 20,000-row benchmark and both thresholds were unchanged. All three
runs passed:

| Run | Elapsed | Throughput |
|---|---:|---:|
| 1 | 2.8077 s | 7,123.3 predictions/s |
| 2 | 2.8847 s | 6,933.0 predictions/s |
| 3 | 2.7645 s | 7,234.6 predictions/s |

The benchmark proves vectorized single-process batch inference under this local
environment. It does not simulate 20,000 concurrent users.

## Security, AI, CMS, and observability

The explicit security gate covered secret redaction, RAG prompt boundaries,
upload validation, traversal and malformed input. The full suite additionally
covered empty/duplicate upload behavior, CMS metadata and linkage, provider
selection/fallback, quota boundaries, structured JSON logs, correlation IDs,
latency/error metrics, AI/RAG/ML instrumentation, and liveness/readiness
separation. Paid AI calls were not required and no API key was printed.

RAG security tests demonstrate the current untrusted-context boundary against
known malicious fixtures. They do not prove that prompt injection is impossible.

## Defect assessment

No CRITICAL, HIGH, MEDIUM, or LOW application defect was reproduced in this
execution. A first ad hoc schema-inspection command had a PowerShell quoting
syntax error after migrations had completed; direct PostgreSQL verification
confirmed the expected head, table count, and extension. This was an operator
command error, not an EduDSS defect.

Static resource review found no evidence requiring a speculative late change.
Existing guards bound upload size/shape, RAG context and top-k behavior; model
resolution and batch prediction tests cover repeated-load-sensitive paths. A
full query profiler and production-sized corpus were outside this gate.

## Claims not proven

- 20,000 concurrent users or distributed multi-node capacity;
- complete disaster recovery or a production RPO/RTO SLA;
- absolute prompt-injection prevention;
- live external LMS/SIS/CMS production integration;
- paid AI provider availability, billing reconciliation, or live-provider SLA;
- all browsers, formal accessibility conformance, or exhaustive visual QA;
- production-sized datasets, vector corpora, backup archives, or restore drills;
- encrypted off-site backup operations, secret recovery, and external artifact recovery.

## Fresh-checkout and Docker evidence

A detached checkout at candidate `ddea6d0c45ef87c3f098742ef5bdd63785fcf34a`
was clean, imported the application, authentication, vector and backup modules,
and discovered all **662 tests**. Alembic migrated a new empty database from
zero to `797f72d1c666`; it contained 27 public tables and pgvector 0.8.6.
Streamlit returned HTTP 200 and health `ok` against the restored QA database.
Readiness, restored authentication, non-superuser cross-tenant RLS and real
pgvector ranking passed from the checkout.

The current Dockerfile built successfully from that fresh committed tree. The
container ran healthy as non-root `uid=999(edudss)`, returned HTTP 200 and
health `ok`, and passed in-container PostgreSQL/pgvector readiness, restored
authentication, cross-tenant RLS and real vector retrieval. The QA container
was stopped after verification. No Dockerfile or runtime source change was
needed.
