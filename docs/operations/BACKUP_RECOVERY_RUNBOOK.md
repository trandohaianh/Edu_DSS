# PostgreSQL backup and recovery runbook

This procedure covers the PostgreSQL database, including pgvector columns in
`rag_chunks`, schema, indexes, constraints, RLS policies, ACLs, and Alembic
revision. It does **not** cover file-based model artifacts, datasets, CMS
uploads, JSON runtime stores, secrets, or off-site disaster recovery.

On the accepted Phase 1C architecture (Alembic `797f72d1c666`, 27 public
tables), PostgreSQL mode also covers users/authentication, user-facing
activity history, AI token usage and per-organization admin AI provider/model
configuration. API keys remain external secrets and are never DB payloads.

## Prerequisites

- PostgreSQL client utilities `pg_dump`, `pg_restore`, and `psql` compatible
  with the server, or a PostgreSQL database container containing them.
- A role allowed to dump the complete source and create schema/extension,
  policies and grants in a **separate empty** restore database.
- The application non-superuser role must already exist on the target server.
  Its grants are included in the archive, but PostgreSQL roles are cluster
  objects and are not created by a database dump.
- The pgvector extension package must be installed on the target server.
- A private backup directory on storage outside the repository, with
  restricted OS permissions, encryption at rest, and off-site replication
  arranged by operations. The script creates POSIX files with mode 0600 and
  a new directory with mode 0700; verify Windows ACLs separately.
- Set `DATABASE_URL` in the process environment. For restore also set
  `RESTORE_DATABASE_URL`. Do not put real credentials in shell history,
  command arguments, filenames, logs, or Git.

The local `--docker-container` mode runs PostgreSQL tools over the database
container's local socket. It uses the user/database components of the URLs,
not their host/port, and requires local socket authentication configured in
that container. It never passes a password to `docker exec -e`. For a remote
server, omit the flag and install client tools on the operator host.

## Backup and verify

From `app/`:

```sh
python ops/backup_recovery.py backup --dir /secure/edudss-backups
python ops/backup_recovery.py verify --manifest /secure/edudss-backups/NAME.backup.json
```

For the local Docker PostgreSQL service:

```sh
python ops/backup_recovery.py --docker-container DB_CONTAINER backup --dir backups
python ops/backup_recovery.py verify --manifest backups/NAME.backup.json
```

The backup command emits a timestamp, database identifier, elapsed time,
size and SHA-256, then creates a custom-format `.dump` and matching
`.backup.json` manifest. Both are sensitive and must travel together.
`app/backups/`, `*.dump`, and `*.backup.json` are Git-ignored. Store the
archive on encrypted, access-controlled, off-site storage; no operational
schedule or replication is configured by this phase.

## Restore into a clean, separate database

1. Declare an incident, stop writes or establish a consistent recovery
   point, and select the manifest. Keep the source database intact.
2. Create a **new empty database** with a different name. For local Docker,
   an operator can use `docker exec DB_CONTAINER createdb -U DB_OWNER NEW_DB`.
   Never run this against a database that contains business data.
3. Ensure the target server has the pgvector extension package and the
   application role. Set `RESTORE_DATABASE_URL` to the new database.
4. Run:

   ```sh
   python ops/backup_recovery.py restore --manifest /secure/edudss-backups/NAME.backup.json
   # Local database-container mode:
   python ops/backup_recovery.py --docker-container DB_CONTAINER restore --manifest backups/NAME.backup.json
   ```

   The script validates SHA-256 and size **before** connecting to the target,
   refuses matching source/target database names, refuses a target with user
   tables, and invokes `pg_restore --exit-on-error --single-transaction`.
   Failed restore returns non-zero. The script never drops or creates a DB.

5. Compare source and target tables/counts and deterministic records. Current
   Phase 1C recovery expects 27 public tables. Check
   `SELECT version_num FROM alembic_version` against the source/current
   migration head; do **not** blindly rerun migrations over the restored
   schema. Check `pg_policies`, `pg_class.relrowsecurity`, and
   `pg_class.relforcerowsecurity`.
6. Connect as the **non-superuser** application role. Set
   `SET LOCAL app.organization_id = '<tenant-id>'` inside each transaction.
   Confirm A sees only A, B sees only B, and cross-tenant UPDATE/DELETE
   affect zero rows while cross-tenant INSERT is rejected.
   Include real reads and cross-tenant write attempts for `users`,
   `activity_logs`, `ai_token_usage`, and `admin_ai_config`.
7. Query `vector_dims(embedding)` and run a real `PgVectorStore.search()`
   against known vectors. Compare ranking and document metadata with source.
8. Enable PostgreSQL identity and set the server-controlled organization ID.
   Authenticate a restored active test account through
   `auth_service.authenticate()`; verify wrong-password failure, role and
   organization. Never print the password/hash/salt.
9. Start a test application instance with `DATABASE_URL` pointing to the
   restored DB and the non-superuser role. Check HTTP 200,
   `/_stcore/health`, `readiness()` with pgvector required, and reads through
   the application repositories. Do not switch production traffic based on
   liveness alone.
10. Restore file-based artifacts and JSON/CMS/dataset state from their
   **separate** protected backups before full service cutover; this phase
   does not supply those backups. Check each model binary's SHA-256 and
   registry/version linkage; the DB only contains artifact paths/metadata.
11. If verification fails, keep traffic on the original database, preserve
    the failed target and logs for analysis, and escalate to the DB operator.
    Never overwrite the source to retry.

The real integration proof is `tests/test_backup_recovery_integration.py`.
It requires dedicated migrated source and empty target URLs via
`PHASE13_SOURCE_URL`, `PHASE13_RESTORE_URL`, `PHASE13_APP_ROLE_URL`, plus
optional `PHASE13_DOCKER_CONTAINER`. It creates only synthetic records and
does not drop databases.

## Retention and objectives

Example daily backup retention of 14 days is a **target policy**, not an
active schedule:

```sh
python ops/backup_recovery.py retention --dir /secure/edudss-backups --days 14
python ops/backup_recovery.py retention --dir /secure/edudss-backups --days 14 --execute
```

The first command is a dry-run. Execution only removes verified expired
archive/manifest pairs inside the configured real directory; symlink paths
and invalid pairs are refused/skipped. Review the selected list first.
Automation, monitoring, off-site replication, encryption/key management and
periodic restore drills must be configured and tested by operations before
claiming a service-level RPO/RTO.

Provisional target RPO: 24 hours **if** daily backups run successfully.
Provisional target RTO: 4 hours **if** database and external file restores
are operationalized. Neither is an SLA. The small synthetic DB restore timing
in the Phase 13 report is evidence for this fixture only.
