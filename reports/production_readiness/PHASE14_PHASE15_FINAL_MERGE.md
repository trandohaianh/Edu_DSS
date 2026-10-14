# Phase 14 + Phase 15 Final Main Merge

## Accepted history

- Pre-merge main: `7fd9c91551d245d3fdab0c4959abffe71c1ce13d`
- Rollback tag: `pre-phase14-phase15-integration` (points to the pre-merge main commit)
- Accepted integration candidate: `053a92cfea40dda899370435a88833947aac0c37`
- Integration branch: `integration/phase14-phase15`
- Merge commit: `7ea9d0b5b04516bdecf6e3bbe93469a6f70bffa3`
- Final main HEAD: the report-only commit containing this file; its hash is recorded in the final gate output.
- Merge method: history-preserving `--no-ff` merge
- Merge conflicts: none
- Merged executable tree equivalent to the accepted candidate: **YES**

## Post-merge gates

| Gate | Result |
|---|---:|
| Pytest discovery | 662 tests |
| Selected component regression | 117 passed in 45.98 s |
| PostgreSQL | 9 passed |
| RLS | 6 passed |
| pgvector | 11 passed |
| Security | 24 passed |
| Phase 12A | 14 passed |
| Phase 1C | 42 passed |
| Phase 13 deterministic/unit | 11 passed |
| Alembic head | `797f72d1c666` |
| Public schema tables | 27 |

The unchanged 20,000-row batch benchmark passed in **2.3032 seconds** at
**8,683.5 predictions/second**, satisfying both accepted thresholds (under 5
seconds and above 5,000 predictions/second). This is a batch throughput result,
not a concurrent-user load result.

## Docker smoke

The application image `edudss-phase1415-main:merged` was built from merged main.
The container ran as `uid=999(edudss) gid=999(edudss)`, became healthy, returned
HTTP 200, and reported health `ok`. PostgreSQL readiness and pgvector readiness
passed. The clean build required recovery of Docker Desktop during dependency
installation; the completed image and its runtime were then verified.

## Fresh detached checkout

Fresh worktree: `D:\KLTN\edudss-phase1415-main-fresh`

- Python imports: PASS
- Pytest discovery: 662 tests
- Alembic zero-to-head: PASS, `797f72d1c666`
- Public tables: 27
- pgvector extension: 0.8.6
- Streamlit startup: PASS
- HTTP: 200
- Health endpoint: `ok`
- Readiness: `ready`
- PostgreSQL authentication: PASS for the restored fixture user
- Runtime database role: non-superuser
- RLS: cross-tenant update affected 0 rows
- Real pgvector retrieval: PASS; top result `p13_0_near`

No application source required by the checkout was untracked.

## CI truth

`.github/workflows/edudss-release-gate.yml` is present. The CI/CD workflow is
implemented and locally validated; hosted GitHub Actions execution is pending a
push or pull request and is not claimed as passing.

## Repository safety

The pre-existing `stash@{0}` remained untouched. User-owned untracked documents,
HTML files, UI directories, diagrams, and personal scripts remained present and
were neither staged nor modified by this merge gate.

## Known limitations

- Hosted GitHub Actions was not executed.
- The 20,000-row result measures batch inference throughput, not concurrent users.
- This gate does not claim exhaustive testing of every PostgreSQL migration path.
- Full disaster-recovery RPO/RTO under production infrastructure is not proven.
- Live external LMS, SIS, and CMS integrations are not proven by local fixtures.
- Prompt-injection risk cannot be represented as absolute prevention.
- Recovery of external artifacts, datasets, uploads, and secrets still depends on
  the corresponding external backup and secret-management systems.

## Decision

**FINAL MERGE STATUS: PASS**

**MAIN READY FOR NEXT PHASE: YES**
