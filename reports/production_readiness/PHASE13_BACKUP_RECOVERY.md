# Phase 13 PostgreSQL backup and recovery

Status: **PASS_WITH_DOCUMENTED_RECOVERY_GAPS**. This is database recovery
capability, not complete disaster recovery.

The original measurements below were produced on the pre-Phase1C schema.
Current integration decisions must use
`PHASE13_PHASE1C_REVALIDATION.md`, which re-proves the mechanism on
Alembic `797f72d1c666` and all four Phase 1C PostgreSQL domains.

## Durable-state inventory and backup matrix

| Classification / store | Current location | Durable? | Backup required? | Method / restore | Verification / limitation |
|---|---|---:|---:|---|---|
| CRITICAL_DATABASE: organizations, RBAC/users, academic records, predictions, consultations, subscriptions, CMS tables | PostgreSQL public schema | Yes | Yes | `pg_dump -Fc` / `pg_restore` | All tables/counts, FK joins, RLS, ACLs and selected records compared in dedicated restore test |
| DATABASE_METADATA: `model_versions`, `model_metrics`, `alembic_version` | PostgreSQL | Yes | Yes | Same archive | Records, relationships and revision compared; binary artifacts are separate |
| CRITICAL_DATABASE: RAG documents/chunks and 384-dimensional pgvector embeddings | PostgreSQL `rag_documents`, `rag_chunks` | Yes | Yes | Same archive, including vector extension and indexes | Real server-side vector search, dimensions, metadata, tenant ownership and ranking verified after restore |
| MODEL_ARTIFACT: trained `.joblib` plus local model JSON / production pointer | `data_warehouse/models/`, `data_warehouse/metadata/` | Yes | Yes | **Not implemented in Phase 13**; protect a separate versioned file backup and restore together | DB `artifact_path` alone cannot reconstruct binaries; verify SHA-256 and `training_id` linkage before cutover |
| OBJECT_STORAGE_CANDIDATE: dataset CSV and dataset/training metadata | `data_warehouse/datasets/`, `raw_data/`, `processed_data/`, `training_data/`, `evaluation_data/`, `metadata/` | Yes | Yes | **Not included**; separate encrypted file/object backup | Re-import may be possible for some sources, but not assumed; recovery gap |
| OBJECT_STORAGE_CANDIDATE: CMS registry / uploaded lesson source | `data_warehouse/cms/lessons_registry.json`; source content may exist only in DB RAG chunks or local files | Yes | Yes | DB CMS/RAG rows included; local registry/source files **not included** | Reconcile registry and original source files after restore; recovery gap |
| CRITICAL_DATABASE: users/auth in Phase 1C PostgreSQL mode | PostgreSQL `users`, `roles` | Yes | Yes | Same archive | Hash representation, role, organization, state and real AuthService login verified after restore |
| CRITICAL_DATABASE: user-facing activity history | PostgreSQL `activity_logs` | Yes | Yes | Same archive | Counts, records, ownership and non-superuser RLS verified |
| CRITICAL_DATABASE: AI token usage | PostgreSQL `ai_token_usage` | Yes | Yes | Same archive | Safe accounting metadata, counts, ownership and RLS verified; prompts/API keys are absent by design |
| CONFIGURATION: admin AI config | PostgreSQL `admin_ai_config` | Yes | Yes | Same archive | Provider/model names restored per tenant; no secret values stored |
| CONFIGURATION: subscriptions | PostgreSQL `subscriptions` | Yes | Yes | Same archive | Rows included and compared; legacy local fallback is outside DB backup |
| CONFIGURATION/SECRET: environment and provider API keys | Environment / external secret source | Yes | Yes, separately | Restore via approved secret/config management; **never** place in DB archive or Git | Revalidate secrets after recovery; no production secret backup implemented |
| LEGACY local fallback stores | `users.json`, `ai_token_usage.json`, activity history, `ai_default_provider.json` when explicitly configured local | Depends on deployment mode | If used | **Not included** | Current PostgreSQL-mode Phase 1C data is covered; local fallback remains a recovery gap |
| CACHE: local embeddings/vector store, semantic cache | `data_warehouse/vector_stores/`, `embeddings/`, memory | Depends on mode | If sole source | **Not included**; regenerate only where original documents and model are available | Local vector mode can be durable and is a recovery gap; pgvector mode is covered |
| LOG: technical logs | `data_warehouse/logs/` | Operational evidence | Separately | **Not included**; central retention needed | Does not block DB restore but loses incident evidence |
| REGENERABLE: temp/cache/pytest data | Process/cache directories | No | No | Recreate | Excluded intentionally |

## Mechanism, security and real proof

The portable CLI is `ops/backup_recovery.py`; the operator runbook is
`docs/operations/BACKUP_RECOVERY_RUNBOOK.md`. It emits safe JSON events for
backup start/completion, duration, archive size/checksum, verification,
restore start/completion and failure. Credentials are read from environment
only. Native mode passes the password via `PGPASSWORD` to PostgreSQL tools,
never in argv; local Docker mode uses container socket authentication without
passing a password to Docker. Errors omit tool stderr, which can contain
sensitive connection detail. Archives and manifests are Git-ignored; new
POSIX files use 0600 and a new backup directory uses 0700. On Windows,
operators must set private ACLs. Encryption, off-site replication and
scheduled execution are **not configured**.

The real test used two newly created databases, one migrated source and one
empty restore target. It inserted synthetic records for two organizations:
users/students, courses/enrollments, predictions, consultations,
subscriptions, CMS lessons, model versions/metrics and four 384-dimensional
RAG chunks. Source vectors were searched with real PostgreSQL pgvector
before backup. A 117,157-byte custom archive was created and its SHA-256
verified before restore. `pg_restore` used a single transaction and did not
touch the source database. The archive included schema, rows, constraints,
indexes, RLS policies, grants and vector data.

The integration test compared **every public table name and row count**,
Alembic revision, selected student/course/enrollment joins, model metadata,
RLS flags/policies, indexes, vector row counts and dimensions. All matched.
Representative counts in both DBs: 2 predictions, 2 consultations,
2 subscriptions, 2 CMS lessons and 4 RAG chunks. The migration revision
was the same in source and target. A non-superuser application role saw only
its own tenant's students and RAG documents; cross-tenant UPDATE and DELETE
affected zero rows, and cross-tenant INSERT raised an RLS error. Real
`PgVectorStore.search()` on the restored database preserved expected
near/far ranking and metadata; no Python similarity substitute was used.

The restored DB's application role passed `readiness()` with pgvector
required and `academic_repository.list_students()` returned a restored
record. A separate test Streamlit instance pointed to the restored DB and
returned HTTP 200 and `/_stcore/health` = `ok`; a timed repeat reached
the health endpoint in 5.593 s. Both test instances were stopped.
This proves a representative application recovery path, not full user-flow
recovery across the excluded file stores.

## RPO, RTO, retention and failure behavior

| Measure | Target/assumption | Measured in this synthetic local test |
|---|---|---|
| RPO | Provisional 24 hours **if** successful daily backups are scheduled | No operational schedule; actual RPO not established |
| RTO | Provisional 4 hours **if** all DB and external file restore procedures are operational | DB restore 1.203 s; in-process readiness + repository read 0.062 s; Streamlit startup to health 5.593 s; tiny fixture, not production RTO |
| Backup | Daily assumption; no job configured | `pg_dump` 0.704 s in integration test; CLI rerun 0.375 s |
| Retention | Example 14 days | Dry-run default and verified-pair deletion unit tested; no automatic cleanup configured |

Unit tests cover missing/invalid configuration, native/Docker command
construction, credentials absent from argv, path safety, checksum mismatch,
missing manifest, non-empty target, safe retention, no stderr secret leakage
and non-zero CLI failure. Real CLI attempts with a nonexistent DB role and a
nonexistent Docker container failed non-zero without printing credentials.
The real populated target was rejected non-zero. A corrupted archive is
rejected **before** any restore command by an automated test.

## Regression and final status

The complete non-E2E suite, excluding the separate 20k load benchmark,
passed **584 passed, 2 skipped** on a dedicated regression database. The
two skips are the existing conditional skip and this phase's real restore
test when its dedicated URLs are absent; the latter was separately run and
passed against dedicated source/target databases. The explicit
PostgreSQL/RLS/pgvector/security/Phase12A/Phase13 unit gate passed
**79 passed** (PostgreSQL 9, RLS 6, pgvector 11, security 20,
Phase1B+8A 8, Phase12A 14, Phase13 unit 11). The real Phase13
backup/restore integration proof passed **1 passed**. The shared pre-existing
test DB initially produced duplicate-record/schema-state errors; no
repair/cleanup was attempted there. A first clean regression DB run failed
five RLS tests because their fixture drops/recreates tables after one-time
grants. Configuring default privileges on the **dedicated test DB only**
made subsequent full and explicit gate runs pass. No test or migration was
changed to mask this setup need.

A separate detached worktree from committed candidate
`a4533ba9859466a2f8ff7b8448637af7cb4f6449` was clean. It discovered
all 12 Phase 13 tests, passed all 11 unit tests, compiled the tooling, and
passed `git diff --check`. A **second real** backup/restore proof from that
fresh checkout used another newly created source/target DB pair and passed:
archive 117,164 bytes, SHA-256
`b5c72c5ba67c8e6163b04837db7cd770bff95925eca2bbeea3dd99c9a3e4a2d1`,
backup 0.391 s, DB restore 1.078 s, readiness + repository read 0.078 s.
This verifies the committed operational code without relying on uncommitted
source or developer-specific absolute paths. The final report-only commit
does not change executable files.

Application runtime code, migrations, RLS policies, and the application
Dockerfile are unchanged. Nevertheless, the complete E2E suite was run from
the fresh candidate checkout and passed **39 passed**. The unchanged 20k
benchmark was not triggered by this operations-only change and was not run.
PostgreSQL client tools remain outside the application image; local proof
used the existing PostgreSQL container. A cache-assisted application Docker
build from the fresh checkout passed. Its container ran as `uid=999(edudss)`,
reported healthy, returned HTTP 200 and `/_stcore/health` = `ok`, and
reported PostgreSQL plus pgvector ready while using the restored DB and
non-superuser application role. The test container was stopped.

Known recovery gaps: file-based model artifacts and metadata, datasets,
CMS source files/registry, explicitly selected legacy local fallback stores,
local vector mode, logs, secrets/config, encryption/off-site copies,
schedule/monitoring and full-scale restore drills. These prevent any claim
of complete disaster recovery or an RPO/RTO SLA.
