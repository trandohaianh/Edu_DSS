# Phase 14 + Phase 15 integration and revalidation

Status: **PASS_WITH_DOCUMENTED_LIMITATIONS**.

## Provenance and conflicts

| Item | Commit |
|---|---|
| Accepted base | `7fd9c91551d245d3fdab0c4959abffe71c1ce13d` |
| Phase 14 candidate | `5c6390dc0e2848cf68e7b3bb669aad7cfefe5cfa` |
| Phase 15 candidate | `c38d0231e3a83d8afab4d5992dfa8d684f10ff20` |
| Two-parent integration merge | `053e947b72c9f5b5f517a1d3a2941da27b811547` |

The merge commit has the two accepted candidates as its exact parents. No
textual or semantic conflict occurred. Phase 14 owns the workflow, evaluator
README, final-submission report and claim guidance. Phase 15 owns the
comprehensive QA report and test matrix. All evidence from both candidates is
preserved without manual recreation.

The integrated diff against the accepted base adds only:

- **CI/CD:** `.github/workflows/edudss-release-gate.yml`;
- **documentation/evidence:** evaluator README and five production-readiness
  files, including this integration report;
- **tests/runtime/database/Docker/other:** no source change, no migration, no
  test implementation change and no Dockerfile change.

There are no unexpected changes.

## Workflow static validation

The GitHub Actions document parses as YAML and contains the expected
`validation` and `docker` jobs. Paths and the `app` working directory are
correct. It selects Python 3.11 and `pgvector/pgvector:pg16`, uses fixed
synthetic CI-only credentials, runs Alembic from zero to head, configures a
genuine non-superuser application role and invokes the accepted pytest gates.
No real secret, `continue-on-error`, or `|| true` suppression is present.

Hosted GitHub Actions has **not** executed because this isolated integration
branch has not been pushed or merged. Static validation and local execution of
the corresponding commands are evidence; hosted CI PASS is not claimed.

## Combined-state test evidence

Discovery found **662 tests**, unchanged from both candidates.

| Gate | Combined result |
|---|---|
| Full non-E2E excluding separately repeated load benchmark | **620 passed, 2 skipped** in 103.75 s |
| Full E2E | **39 passed** in 863.68 s |
| Explicit component gate | **117 passed** in 36.39 s |
| PostgreSQL | **9 passed** |
| Non-superuser RLS | **6 passed** |
| Real pgvector | **11 passed** |
| Security | **24 passed** |
| Phase12A | **14 passed** |
| Phase1C | **42 passed** |
| Phase13 deterministic/unit | **11 passed** |
| Phase13 real backup/restore | **1 passed** in 7.83 s |

The two ordinary-suite skips remain conditional integrations. Phase13's real
integration was configured and passed separately; no skip is represented as
positive recovery evidence.

A new database migrated from zero to Alembic `797f72d1c666`, contained 27
public tables and pgvector 0.8.6. The intended non-superuser role passed
cross-tenant SELECT, INSERT, UPDATE and DELETE enforcement. Real pgvector tests
covered 384-dimensional compatibility, metadata, tenant scope, server-side
`<=>` retrieval and ranking. Current Phase1C persistence labels remain
PostgreSQL-primary-with-fallback.

## Recovery and performance

The combined-state Phase13 proof created a **130,597-byte** archive in
**0.469 s** with SHA-256
`761b555cb3f22862338ce384c538a7fd41c5aeb9a3abfd31eb860ea5d8950ba2`.
Restore completed in **2.610 s** (2.625 s test-side), source/target verification
in **0.343 s**, and application/auth checks in **0.532 s**. Authentication,
RLS and real pgvector behavior passed after restore. Full disaster recovery is
not claimed.

The existing 20,000-record batch benchmark was unchanged and passed all three
runs:

| Run | Elapsed | Throughput |
|---|---:|---:|
| 1 | 2.3129 s | 8,647.3 predictions/s |
| 2 | 2.4023 s | 8,325.5 predictions/s |
| 3 | 2.3865 s | 8,380.6 predictions/s |

This is batch prediction evidence, not concurrent-user testing.

## Documentation truth and limitations

The integrated documentation keeps IMPLEMENTED, TESTED, SIMULATED and NOT
PROVEN distinct. It does not claim full PostgreSQL migration, full disaster
recovery, a production RPO/RTO SLA, absolute prompt-injection prevention,
live production LMS/SIS/CMS integration or full production readiness.

Live external LMS/SIS/CMS remains **NOT PROVEN**. Future simulated integration
remains **TO BE VERIFIED** and was not implemented or renamed in this task.

Other limitations include hosted CI not yet executed, external model/dataset/
CMS-upload/secret recovery gaps, no multi-node production deployment proof and
no 20,000-concurrent-user proof.

## Fresh-checkout and Docker evidence

A clean detached worktree at committed integration candidate
`87480a16600a02f159b0b9c4dfa44d27eee15d3b` imported the application,
authentication, vector and backup modules, parsed the workflow and discovered
all **662 tests**. A new evaluator database migrated from zero to
`797f72d1c666`, contained 27 public tables and pgvector 0.8.6. Streamlit
returned HTTP 200 and health `ok`. Readiness, restored authentication,
non-superuser cross-tenant RLS and real server-side vector ranking passed. No
untracked application source was required.

The current Dockerfile built from that exact committed checkout. The container
ran healthy as non-root `uid=999(edudss)`, returned HTTP 200 and health `ok`,
and passed in-container PostgreSQL/pgvector readiness, restored authentication,
RLS and real vector retrieval. It was stopped after verification.
