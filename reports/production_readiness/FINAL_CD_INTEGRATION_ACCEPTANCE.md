# Final C+D Integration Verification

## 0. Scope and base

Verifies that Workstream C (ML/AI governance) and Workstream D
(scale/recovery) genuinely coexist and compose correctly with A+B
(LMS/CMS simulation, persistence), University Onboarding, and Docker
CPU-only deployment — on **one** live stack, built from **one** fresh
Docker image, for the accepted commit chain through
`docs/phase16-release-package` @ `f7d3690` (base of this branch,
`integration/final-candidate-v2`).

Per instruction, **neither Workstream C nor Workstream D was
reimplemented.** Every capability below is exercised through its
already-accepted, real function — `ml_provenance.evaluate_data_drift`,
`model_registry.promote`, `ops.capacity_benchmark`,
`ops.backup_recovery`, `ops.non_db_recovery` — never a substitute.

## 1. Coexistence matrix

| Capability | Coexists correctly? | Evidence |
|---|---|---|
| A+B LMS/CMS simulated integration | YES | University A/B onboarded and synced live against the real simulator, this round and Stage 5's re-run both |
| PostgreSQL persistence | YES | Every write in this round went through real Postgres, no JSON-store fallback used |
| RLS multi-tenancy | YES | 83/83 RLS+security tests; live cross-tenant checks in Parts B4/F3; RLS re-confirmed on a RESTORED database |
| University Onboarding | YES | Full onboarding gate exercised for 2 fresh tenants this round (and again in Stage 5's re-run) |
| CMS -> RAG -> pgvector lifecycle | YES | Part C: index, invalidate, confirm stale content unretrievable — all against the same live Postgres the rest of the stack uses |
| ML inference | YES | Part A1-A3: real classification/regression/clustering, real predictions persisted via the CONCUR-001-fixed repository path |
| ML provenance | YES | Part A4: real `save_model_training` + `ml_provenance.record_training_provenance` mirror, confirmed present |
| Drift monitoring | YES | Part A5-A6: both a no-drift negative control and a controlled-shift positive control, both correctly classified |
| Model registry | YES | Part A4: real candidate->production promotion, Admin-gated, now genuinely audited (see defect below) |
| AI gateway | YES | Part B1: real `LLMGateway.stream_generate` call in the same process/session as the ML and CMS work above |
| Quota enforcement | YES | Part B3: real quota read-back via `quota_repository.get_usage` after live AI Gateway calls |
| Backup/recovery | YES | Part F: real backup+restore+full inventory, performed against the SAME database that all of the above wrote to |
| Docker CPU-only deployment | YES | The entire live stack above ran inside the fresh Docker build verified in section 13 |

**No coexistence conflicts were found** — no capability's real operation
broke another's when run together in one continuous session against one
live stack.

## 2. Defect found, reproduced, fixed, and regression-tested

### Issue MODELREG-002 — model promotion audit writes silently dropped under RLS

**Reproduction**: Calling `model_registry.promote()` (the real,
Admin-gated, accepted governance function) through the application's own
connection method — the non-superuser app role, exactly how the real
deployed app always connects — resulted in **zero** rows in
`audit_logs`, even though the promotion itself succeeded and `record()`
was called and returned normally.

**Root cause**: `model_registry.py::_set_production_with_audit()` called
`audit_log_repository.record(..., organization_id=None)`. The
`audit_logs` table's RLS policy is
`organization_id = current_setting('app.organization_id')` for both
`qual` and `WITH CHECK`. Under SQL NULL semantics, `NULL = NULL`
evaluates to NULL, never TRUE — so the WITH CHECK clause can **never**
be satisfied by a non-superuser role inserting a row with
`organization_id = NULL`. The resulting policy-violation exception was
silently caught by `record()`'s own intentionally-broad
`except Exception` (a deliberate design choice so a broken audit write
never blocks the actual promotion) — meaning this failure mode produced
**no error anywhere**, not in the UI, not in logs at any severity a
normal operator would notice.

**Regression test**: `tests/test_model_registry_audit_rls.py` — reproduces
the exact failure mode (DATABASE_URL set to the app role, not the
owner) and asserts a real, readable `audit_logs` row results.

**Fix**: `model_registry.py` gained
`_resolve_organization_id_best_effort()` (reads `EDUDSS_ORGANIZATION_ID`,
returns `None` on absence rather than raising — preserving the
pre-fix, correct no-op behavior for deployments that never set that
variable) and `_set_production_with_audit()` now passes its result as
`organization_id` to `audit_log_repository.record()`.

**Affected gates rerun after the fix**:
- `tests/test_model_registry_audit_rls.py` — 2/2 passed.
- Full non-E2E regression suite — 569 passed, 0 failed (no regression
  introduced).
- `tests/test_final_candidate_v2_extended.py::test_A_ml_governance_journey`
  — re-run clean end to end, including the now-successful audit
  assertion.

This is the only real defect this integration round found. No other
architecture was rewritten.

## 3. What this round did NOT change

Workstream C's drift methodology (PSI+KS), Workstream D's capacity
benchmark harness, the University Onboarding lifecycle gate, the CMS/
RAG lifecycle primitives, and the backup/restore mechanism are all
exactly as previously accepted — used, not modified, except for the one
narrowly-scoped `model_registry.py` fix above.
