# Phase 13 revalidation on Phase 1C main

Status: **PASS_WITH_DOCUMENTED_RECOVERY_GAPS** (pending final regression
totals recorded below). This report supersedes old-schema acceptance evidence
for integration decisions; it does not rewrite or invalidate the frozen
original Phase 13 history.

## Provenance and reconciliation

| Item | Value |
|---|---|
| New accepted base | `48f40ec691d437cbaf184b30fce8d8a0357a4413` |
| Original Phase 13 base | `451eb124dba05608f36b4ac52c924869ad3b0390` |
| Original Phase 13 candidate | `afa6c02ac78e3730cdbf61c2a0fd2a373000862f` |
| Revalidation branch | `integration/phase13-revalidated-on-phase1c` |
| Port method | Cherry-picked implementation `a4533ba` and report-only `afa6c02`, then manually reconciled current persistence semantics |

Phase 13 changed only `.gitignore`, its new operations tool, two tests,
runbook and report. Phase 1C changed persistence configuration, warehouse,
models/migration, four repository/service domains and their tests/reports.
There were **no textual conflicts**. A clean cherry-pick did not establish
semantic compatibility: the old inventory and restore fixture treated
users/auth, activity history, AI usage and admin AI config as local gaps.
Manual reconciliation extended the real fixture, source/target snapshot,
RLS mutation tests, repository reads and AuthService proof for those current
PostgreSQL domains. No Phase 1C source, migration or history was modified.

## Current schema and database recovery evidence

A newly created database migrated from zero to Alembic
`797f72d1c666`, contained exactly **27 public tables**, and had pgvector
extension 0.8.6. A separate migrated source and initially empty restore
target were used for the real proof.

The synthetic two-organization fixture contains:

- users with real PBKDF2 hash representation, roles, organization ownership,
  active/inactive state and no real credential;
- tenant activity rows;
- AI accounting rows with provider/model and input/output/total tokens, no
  prompt or API key;
- per-tenant safe AI provider/model configuration, no secret;
- students, courses, enrollments, predictions, consultations, subscriptions,
  CMS rows, model metadata and four 384-dimensional pgvector chunks.

The PostgreSQL custom archive was **126,829 bytes**. Backup took **0.375 s**.
SHA-256 was
`a5a08264cde5e92f91604fcec43c397c582410c1022d56052d8599ead192b284`
and was verified before restore. Restore completed in **2.422 s** (2.438 s
including test-side timing). Application readiness plus repository/auth
verification took **0.593 s**.

Source and target snapshots matched for all table names/counts, Alembic
revision, indexes, RLS flags/policies, student-course-enrollment joins,
model metadata, vector dimensions and all four Phase 1C domains. The
comparison uses only hash/salt lengths, never values. Representative
Phase 1C row counts were two users, two activity rows, two token usage rows
and two AI config rows.

## Runtime security and application proof

The restored application role is a real non-superuser. For each of
`users`, `activity_logs`, `ai_token_usage`, and `admin_ai_config`,
an Org A session saw one A row and no B row; cross-tenant UPDATE and DELETE
affected zero rows; a cross-tenant INSERT was rejected by RLS. Existing
student/RAG isolation remained intact.

`auth_service.authenticate()` against the restored DB accepted the valid
synthetic active user, rejected an invalid password and returned the
preserved role. The server-controlled organization ID selected the correct
tenant. Repositories returned the restored activity, 15-token accounting
record and safe AI config. Real `PgVectorStore.search()` used PostgreSQL's
`<=>` operator and preserved vector count, 384 dimensions, metadata,
ownership and near/far ranking.

After restarting the PostgreSQL container, authentication and all three
other Phase 1C repository reads still passed. Two separate Streamlit starts
against the restored database reached health in **2.842 s** and **2.310 s**;
the processes were stopped. This is restart persistence, not full disaster
recovery.

No real API key, Authorization header or real credential was inserted.
Passwords, hashes, salts, raw vectors and private document content are not
emitted by backup metadata/events. Existing Phase 12A redaction and security
tests are part of the regression gate.

## Coverage boundary and objectives

PostgreSQL backup now covers Phase 1C PostgreSQL-mode identity, activity,
token usage and safe admin AI config as well as prior database domains.
It still does not protect external `.joblib` model binaries, dataset CSVs,
CMS source uploads/registry, explicitly selected local fallback stores,
local vector files, logs, external secrets, encrypted off-site copies or
an operational scheduler.

- Target RPO: provisional 24 hours if daily backup automation is deployed.
- Operational/measured RPO: not established; no schedule or SLA.
- Target RTO: provisional 4 hours if database and external file recovery are
  operationalized; not an SLA.
- Measured current-schema DB restore: 2.422 s on this small synthetic fixture.
- Measured application restart to health: 2.842 s and 2.310 s.

The 11 Phase 13 unit tests revalidated missing configuration, password-free
command construction, invalid path, checksum corruption, non-empty target,
safe failures and directory-constrained retention with dry-run default.
Scheduling and destructive automatic retention remain unconfigured.

## Final regression and fresh-checkout evidence

On a dedicated current-schema regression database:

- full non-E2E excluding the separate load benchmark: **620 passed,
  2 skipped, 0 failed**;
- explicit combined gate: **121 passed**;
- PostgreSQL schema 9, RLS 6, pgvector 11, security 20, Phase1B+8A 8,
  Phase12A 14, Phase1C 42;
- Phase13: 11 unit tests passed in the ordinary suite and the conditional
  real restore proof passed separately;
- full E2E: **39 passed** in 847.02 s;
- unchanged 20k benchmark: **PASS**, 2.2926 s and 8,723.5 predictions/s
  (threshold: elapsed <5 s and throughput >5,000/s).

The detached fresh checkout at code/revalidation commit `92f3b65` was
clean, imported the backup and Phase 1C modules, and discovered **662 tests**.
Alembic migrated two new databases from zero to `797f72d1c666`; the
independent schema database had 27 public tables and pgvector 0.8.6.

The fresh-checkout real proof used another new empty target:

- backup: PASS, **127,113 bytes**, **0.329 s**;
- SHA-256:
  `c0aa51ee7468c9510815ef12b7cd4796e075a6ebbfd8c413211abcbd0c934148`;
- restore: PASS, PostgreSQL event **1.203 s**, test-side **1.218 s**;
- source/restored verification: **0.375 s**;
- readiness, repositories and AuthService: **0.532 s**;
- Streamlit HTTP 200 and health `ok`: **2.728 s**;
- Phase 13 unit/failure/retention tests: **11 passed**;
- security + Phase12A redaction/privacy + auth-secret logging:
  **35 passed**.

The fresh archive again restored all four Phase 1C domain comparisons,
AuthService valid/invalid-password behavior, role/organization/state,
non-superuser cross-tenant SELECT/UPDATE/DELETE/INSERT enforcement and real
server-side pgvector ranking. No password/hash/salt or real secret was
printed. A cache-assisted Docker build completed from the committed tree;
final clean-checkout runtime evidence is recorded in the final response.
