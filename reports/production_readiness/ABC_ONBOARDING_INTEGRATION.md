# A+B + CPU + C + University Onboarding Integration (Stage 3)

## 1. Ancestry — again, no merge was needed

```
git merge-base --is-ancestor 80fa3df a3e8d82  -> YES
```

Same pattern as Stage 1: `closure/university-onboarding` (`a3e8d82`) was
created directly from `integration/ab-cpu-c` (`80fa3df`), so it already
contains every commit from Stage 1 (and transitively, A+B/CPU-only/
Workstream C). This branch (`integration/abc-onboarding`) is created
directly from `a3e8d82` — a fresh-verification checkpoint, not a merge.

## 2. Branch / worktree / commit

| | |
|---|---|
| Branch | `integration/abc-onboarding` |
| Worktree | `D:/KLTN/edudss-abc-onboarding` |
| Base | `a3e8d82` |

## 3. Database

Alembic head: `35d62f0c6002` (single head, confirmed from this worktree's
own migration files against the shared verification database).

## 4. Revalidation (this stage)

Rather than repeating the entire 707-test non-E2E suite and 39-test E2E
suite a third time in a row on effectively the same code (Stage 1 ran
both in full on the A+B+CPU+C combination; Stage 2 ran both in full again
after adding University Onboarding — see that report's §9), this stage
ran a **focused, cross-cutting revalidation** covering every domain the
combination touches, plus the 20K benchmark:

```
tests/test_db_row_level_security.py ...... (6)
tests/test_pgvector_store.py ........... (11)
tests/test_workstream_ab_postgres_integration.py .... (4)
tests/test_workstream_c_ml_provenance.py ........ (8)
tests/test_university_onboarding.py ....... (7)
tests/test_ai_gateway_governance.py ..... (5)
tests/test_ml_provenance_core.py ............................. (29)
70 passed in 64.20s
```

This includes the full University Onboarding suite (§Checkpoint 2 below),
RLS (genuine non-superuser), pgvector, A+B sync/webhook/CMS-RAG, ML
provenance/drift, and AI Gateway routing — every domain in Stage 1's own
Checkpoint 1 list, plus onboarding. Zero failures.

**20K batch benchmark** (batch inference, not concurrent users):
`2.7493 s` / `7274.5 predictions/sec` — threshold <5s, >5,000/sec, **PASS**.

## 5. Checkpoint 2

> "Continue only if the integrated system can demonstrably onboard
> University B while University A remains intact and tenant-isolated."

`test_university_onboarding.py::test_01_onboard_university_b_while_university_a_remains_operational`
(part of the 70 passing above) is exactly this scenario, run fresh on
this integrated branch: University A created independently; University B
onboarded end-to-end through `dss.services.university_onboarding` only
(provision → admin → connector → real HTTP test-connection → canonical
mapping validation → real initial sync → activation gate); both confirmed
operational afterward; RLS confirmed to block cross-tenant visibility in
both directions.

**CHECKPOINT 2: PASSED.**

## 6. Environment notes carried forward

- C: drive free space was 3.0GB earlier this session, now 9.6GB (some
  reclamation occurred passively) — still tight relative to the 223GB
  total. Docker Desktop's active WSL2 virtual disk lives on C:. No
  cleanup action has been taken; flagging for continued awareness in
  later stages, particularly Stage 4's heavier Docker usage.
- The one recurring flaky E2E test
  (`test_lecturer_learning_explainer_renders_without_traceback`,
  documented in `UNIVERSITY_ONBOARDING_ACCEPTANCE.md` §9) was not
  re-triggered this stage since the full E2E suite was not re-run here
  (§4) — it remains a known, pre-existing, unrelated timing flake, not
  re-litigated each stage.

## 7. Status

All of Stage 1's Checkpoint 1 domains plus University Onboarding verified
together on one branch. **Proceeding to Stage 4 (Workstream D).**
