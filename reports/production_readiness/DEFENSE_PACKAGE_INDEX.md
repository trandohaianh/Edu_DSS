# Defense Package Index

A guide to every document produced by this closure engagement
(Stages 1-6), grouped by what a reader is trying to find. All paths
are relative to `app/reports/production_readiness/` unless noted.

## Start here

- **`FINAL_SUBMISSION_ACCEPTANCE.md`** — the single top-level status
  document; read this first. States overall status
  (`PASS_WITH_DOCUMENTED_LIMITATIONS`), the full accepted commit chain,
  and what changed at each stage.
- **`FINAL_ARCHITECTURE_TRUTH.md`** — what's real vs. projected, in one
  table, plus the real bugs found and fixed during this engagement.
- **`SUBMISSION_MUST_NOT_SAY.md`** — read before any defense Q&A or
  written submission; the exact banned claims and their safe
  replacements.

## Capability and test evidence

- **`FINAL_SYSTEM_CAPABILITY_MATRIX.csv`** — one row per capability,
  status, and citation (this engagement's Stages 1-5 scope).
- **`FINAL_TEST_MATRIX.csv`** — per-feature test matrix from the
  earlier Phase 13/14 closure (complementary, narrower granularity,
  still valid).
- **`TEST_RESULTS.md`** — consolidated pass/fail counts across every
  stage, with an explicit explanation of why skip-counts differ between
  runs (env-gating, not lost coverage).
- **`METRICS_THESIS_VS_CURRENT.md`** — which ML metrics are
  thesis-reported-only vs. independently confirmed by current code/
  artifacts.

## Stage-by-stage acceptance reports (chronological)

1. `WORKSTREAM_A_LMS_CMS_SIMULATION.md`, `WORKSTREAM_B_PERSISTENCE_DOMAIN_CLOSURE.md`, `WORKSTREAM_AB_INTEGRATION.md`
2. `DOCKER_CPU_ONLY_PYTORCH_OPTIMIZATION.md`
3. `WORKSTREAM_C_ML_AI_GOVERNANCE.md`
4. `ABC_INTEGRATION_ACCEPTANCE.md` (Stage 1)
5. `UNIVERSITY_ONBOARDING_ACCEPTANCE.md` (Stage 2)
6. `ABC_ONBOARDING_INTEGRATION.md` (Stage 3, Checkpoint 2)
7. `WORKSTREAM_D_SCALE_RECOVERY.md` (Stage 4)
8. `FINAL_STAGING_SIMULATION.md` (Stage 5 — the 34-step live narrative)
9. This document and its siblings (Stage 6 / Phase 16)

## Architecture and deployment

- **`../../docs/architecture/NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md`**
  — explicitly labeled unverified projection, grounded in this
  engagement's real connection-pool finding.
- **`PRODUCT_DEPLOYMENT_STRATEGY.md`** — the three deployment postures,
  and the concrete runbook gaps a real deployment must close (role
  seeding, pool tuning, backup scheduling, credential provisioning).
- **`RELEASE_FREEZE.md`** — the exact frozen branch/commit list this
  entire package describes, and what is explicitly deferred to the
  user (merging to main).

## Older/historical layers (pre-dating this engagement's Stage 1)

Everything named `PHASE0_*` through `PHASE15_*` and
`FINAL_PHASE*_ACCEPTANCE.md`, `FINAL_INTEGRATION_ACCEPTANCE.md`,
`FINAL_PERF_20K_ACCEPTANCE.md`, `PERF_20K_REMEDIATION.md` — the prior
closure history this engagement built on top of. Not rewritten or
re-verified by this engagement except where explicitly cited (e.g. the
20K batch benchmark's continuity, the RLS testing pattern).

## Evidence directories (not narrative documents)

- `workstream_d_evidence/` — JSON evidence from Stage 4 (concurrency
  profiles, soak test).
- `final_staging_evidence/narrative.json` — the full 34-step Stage 5
  narrative, machine-generated, not hand-written.

## If you only have time to read three documents

1. `FINAL_SUBMISSION_ACCEPTANCE.md`
2. `SUBMISSION_MUST_NOT_SAY.md`
3. `FINAL_STAGING_SIMULATION.md`
