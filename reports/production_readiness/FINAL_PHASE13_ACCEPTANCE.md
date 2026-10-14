# Final Phase 13 backup and recovery acceptance

Status: **PASS_WITH_DOCUMENTED_RECOVERY_GAPS**.

## Merge provenance

| Item | Commit |
|---|---|
| Pre-merge main / rollback tag | `48f40ec691d437cbaf184b30fce8d8a0357a4413` / `pre-phase13-backup-recovery` |
| Accepted candidate | `8fcb13c1529596a135a4472d0871bb7c0e12147f` |
| No-ff merge | `3cf42c3d0124d05924be47a920fdd881bf9a5f83` |

The merge has two parents: the accepted Phase 1C main and the revalidated
Phase 13 lineage. No Phase 1C source or migration was reverted. PostgreSQL
client tooling remains operational tooling and was not added to the
application image.

## What the database backup protects

The PostgreSQL custom-format archive protects the current 27-table schema,
constraints, indexes, ACLs, RLS policies, Alembic revision, relational rows,
model registry metadata and pgvector data. Phase 1C PostgreSQL-mode
users/auth, activity history, AI token usage and safe admin AI configuration
are covered and were restored. Predictions, consultations, subscriptions,
RAG chunks and model metadata were also represented by deterministic
synthetic fixtures.

It does **not** protect external model `.joblib` binaries, dataset files,
external CMS uploads, explicitly selected local fallback stores, external
secrets/configuration, logs, encrypted off-site copies or operational
scheduling.

## New post-merge database proof

A new migrated source and new empty restore target were created after merge.
The fixture used two synthetic organizations and no real credentials,
prompts, API keys or private records.

| Measurement | Result |
|---|---|
| Backup | PASS; 127,123 bytes; 0.343 s |
| SHA-256 | `d0aaf8579511220d1a794cb5d6dc510d93790f986e023b45854755d307c1615e` |
| Restore | PASS; 1.641 s |
| Source/restored verification | 0.344 s |
| Application/auth/repository check | 0.531 s |

Source and target matched for revision `797f72d1c666`, 27 tables,
constraints, indexes, policies, RLS flags, relationships, safe deterministic
Phase 1C fields, vector dimensions and model metadata. The restore test used
the real non-superuser role. Cross-tenant SELECT returned no foreign rows,
UPDATE/DELETE affected zero rows and INSERT was rejected across users,
activity, AI token usage and admin AI configuration.

`auth_service.authenticate()` accepted the restored valid synthetic
account, rejected the invalid password, and preserved role, organization and
account-state representation. Real server-side pgvector `<=>` search
preserved 384 dimensions, row count, metadata, tenant ownership and ranking.

## Regression and performance

Post-merge full non-E2E: **621 passed, 1 skipped**. The conditional real
restore test is the skip in the ordinary environment and separately passed
above. Existing component baselines represented in the combined gate remain:
PostgreSQL 9, RLS 6, pgvector 11, security 20, Phase12A 14, Phase1C 42,
Phase13 11 unit tests plus the real integration proof. The explicit
post-merge component gate passed **113 tests**. Full E2E passed
**39 tests** in 808.00 s.

The unchanged 20k benchmark passed: **2.2891 s**, **8,737.1
predictions/second**, against the required elapsed <5 s and throughput
>5,000/s. Final fresh-checkout and Docker evidence are reported from the
evidence-complete final main commit.

## Recovery objectives and remaining work

Target RPO remains a provisional 24 hours **if** successful daily backups
are later scheduled. No operational RPO is measured because no schedule is
configured. Target RTO remains a provisional four hours **if** database and
external file recovery are operationalized. Small synthetic timings are
engineering evidence, not a production RTO or SLA.

Database backup/restore is verified. Full disaster recovery is not complete.
Production work remains for external file backups, secret/config recovery,
encryption and off-site replication, scheduling/monitoring, retention
operations and full-scale recovery drills.
