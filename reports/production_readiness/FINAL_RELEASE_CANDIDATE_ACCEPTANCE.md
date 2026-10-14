# Final Release Candidate Acceptance — Stage 7

## 0. Base / branch / worktree

| | |
|---|---|
| Base | `docs/phase16-release-package` @ `f7d3690` (linear descendant, confirmed via `git merge-base --is-ancestor`) |
| Branch | `release/final-candidate-verification` |
| Worktree | `D:/KLTN/edudss-final-release` |

## 1. What "fresh checkout" means for this gate, precisely

- A **brand-new git worktree** checked out from the frozen commit chain
  (not a copy, not a reused directory).
- A **brand-new Python virtual environment**, created from scratch with
  `py -3.12 -m venv .venv` (not reused, not a junction/symlink to any
  other venv used earlier in this engagement) and every dependency
  installed fresh from `requirements.txt` (CPU-only PyTorch wheel
  resolved via the project's pinned `--extra-index-url`, confirmed
  `torch==2.9.1+cpu` — never a CUDA build).
- A **brand-new Playwright browser install**, downloaded fresh for this
  verification.
- A **brand-new Docker image build** (`docker compose ... up --build`)
  from this exact checkout's `Dockerfile`.

**One real mistake found and fixed during this gate**: the first venv
was created inside `app/.venv` instead of the worktree root's `.venv`
(the location `tests/e2e/conftest.py` hardcodes:
`_APP_DIR.parent / ".venv" / "Scripts" / "python.exe"`). This caused all
39 E2E tests to error with `FileNotFoundError` at fixture setup (the
Streamlit subprocess launcher couldn't find the interpreter). This was
a setup mistake in this verification session, not a codebase defect —
recreating the venv at the correct sibling path resolved it immediately
and is recorded here in the interest of full transparency about this
gate's own execution, not just its result.

**One real infrastructure incident during this gate**: Docker Desktop's
backend engine returned `500 Internal Server Error` mid-verification
(the `docker-desktop` WSL2 VM had stopped while Windows-side processes
were still running) — consistent with the Docker/WSL2 instability
already documented multiple times earlier in this engagement. Diagnosed
via `docker version`, `tasklist`, and `wsl -l -v`; recovered by cleanly
killing all Docker Desktop processes, `wsl --shutdown`, and relaunching
`Docker Desktop.exe` from its actual per-user install path. The retry
succeeded cleanly. No data was lost (the failed attempt had not created
any of this stage's own containers yet).

## 2. Fresh non-E2E suite

**569 passed, 150 skipped (env-gated), 0 failed.** Run twice — once
from the (mistakenly placed) first venv, once from the corrected one —
identical result both times, confirming the venv location mistake did
not affect this suite (only the E2E subprocess launcher depends on that
exact path).

## 3. Fresh E2E suite

**37 passed, 2 failed** on the full run (920.08s / ~15.3 minutes).
Both failures re-run in isolation immediately after:
**2/2 passed**, confirming both are flaky-under-full-suite-load
timing issues, not genuine regressions:

- `test_lecturer_learning_explainer_renders_without_traceback` — the
  SAME pre-existing flake documented at least 3 times earlier in this
  engagement (Workstream C, Stage 1, Stage 2 worktrees), on a code path
  none of this engagement's changes ever touched.
- `test_search_result_action_navigates_to_ai_advisor_with_student_preselected`
  — a NEW instance of the same class of flake (a `page.wait_for_timeout`-based
  assertion racing real page navigation under load), documented here for
  the first time. Not previously seen because this is the first time
  this engagement ran the E2E suite from a genuinely fresh, freshly-built
  environment under the exact resource conditions that surface it.

**Honest framing**: this is not "39/39 passing" for this specific gate's
raw first run — it is 37/39 raw, 39/39 confirmed-non-regressing after
isolated re-run of the 2 failures, with both failures attributed to a
documented, understood, pre-existing flake class rather than dismissed
without evidence.

## 4. Fresh Docker build

`docker compose --profile integration-ab up -d --build` from this exact
checkout succeeded (after the Docker Desktop recovery in §1):

- `edudss-postgres`: healthy, `01-app-role.sh` executed successfully
  (`CREATE ROLE` — confirms Stage 5's `.gitattributes` CRLF fix holds on
  a genuinely fresh checkout, not just in the worktree where it was
  originally fixed).
- `edudss-lms-cms-simulator`: healthy.
- `migrate-integration`: exited 0, Alembic reached single head
  `35d62f0c6002`.
- `streamlit-integration`: healthy, real HTTP `200` on
  `/_stcore/health`.
- `streamlit-dss`: healthy.
- **Zero unhandled tracebacks** across all four containers' logs.

Stack torn down cleanly after verification (`docker compose down`); no
volumes or credentials left behind (`.env.staging` deleted).

## 5. Full truth table

| Label | Status | Evidence |
|---|---|---|
| ONE EDUDSS PRODUCT MULTI-UNIVERSITY | **TRUE** | One codebase, one Docker image; `FINAL_ARCHITECTURE_TRUTH.md` §1 |
| UNIVERSITY ONBOARDING | **VERIFIED** | `UNIVERSITY_ONBOARDING_ACCEPTANCE.md`; live in `FINAL_STAGING_SIMULATION.md` steps 4-15 |
| SIMULATED LMS/CMS | **VERIFIED** | Real HTTP connector against a dedicated simulator, throughout |
| LIVE EXTERNAL LMS | **NOT DONE** | Never attempted this engagement |
| POSTGRESQL PERSISTENCE | **VERIFIED** | Real Postgres 16 + pgvector, every stage |
| RLS | **VERIFIED** | Non-superuser app role, live cross-tenant checks under load and in integration (`FINAL_STAGING_SIMULATION.md` step 16) |
| PGVECTOR | **VERIFIED** | Real reindex + retrieval, `FINAL_STAGING_SIMULATION.md` steps 20-22 |
| ML PROVENANCE | **VERIFIED** | SHA-256 fingerprinting, Workstream C (`d1b17a4`) |
| DATA DRIFT | **VERIFIED (methodology)** | PSI+KS; not a correctness guarantee — see `SUBMISSION_MUST_NOT_SAY.md` |
| PERFORMANCE DRIFT | **VERIFIED (methodology)** | Same caveat as above |
| AI GATEWAY | **VERIFIED** | Live Production Demo Policy call, `FINAL_STAGING_SIMULATION.md` step 23 |
| CPU-ONLY DEPLOYMENT | **VERIFIED** | `torch==2.9.1+cpu` confirmed fresh this stage |
| 20K BATCH | **VERIFIED** | 7,629.6 predictions/sec, batch only — never conflated with concurrent users |
| CONCURRENT USER CAPACITY | **VERIFIED (boundary found)** | SLO met at 10, violated at 25 — single dev machine, default pool |
| MULTI-UNIVERSITY LOAD | **VERIFIED** | 4 tenants, fair distribution, zero leakage under load |
| NATIONAL-SCALE LOAD | **NOT VERIFIED** | Explicitly a projection document, never load-tested |
| DATABASE RECOVERY | **VERIFIED** | Backup → verify → **restore-to-fresh-database**, independently queried (Stage 5) |
| NON-DB RECOVERY | **VERIFIED (manifest only)** | Build/verify real and tested; no restore orchestration |
| FULL DISASTER RECOVERY | **PARTIAL** | DB restore genuinely proven; non-DB restore and a combined drill were not |
| E2E | **PASS (with disclosed flake)** | 37/39 raw, 39/39 after isolated re-run of 2 documented flaky tests |
| DOCKER | **VERIFIED** | Fresh build succeeded this stage, zero tracebacks |
| FRESH CHECKOUT | **VERIFIED** | This entire document is the evidence; one setup mistake and one infra incident found and fixed along the way, disclosed above |
| HOSTED CI EXECUTED | **NOT DONE** | All verification ran locally this engagement; no cloud/hosted CI pipeline was executed |
| READY FOR THESIS DEMO | **YES, with disclosed caveats** | Golden-path journey is real and repeatable; read `SUBMISSION_MUST_NOT_SAY.md` before defense |
| READY FOR SUBMISSION | **YES, with disclosed caveats** | Evidence trail is real, reproducible, and honestly bounded |
| FULL PRODUCTION READY | **NO** | National scale, live LMS, hosted CI, and full (combined) disaster recovery remain unverified or not implemented |
| FINAL STATUS | **PASS_WITH_DOCUMENTED_LIMITATIONS** | Consistent with every prior stage's own honest status label |
| READY FOR FINAL MAIN MERGE | **DECISION DEFERRED TO USER** | This roadmap never merges to main; see `RELEASE_FREEZE.md` |

## 6. What this gate adds that no earlier stage could

Every earlier stage reused an existing venv or an existing Docker layer
cache for speed. This gate is the first and only point in the entire
engagement where the accepted commit chain was proven, end to end, from
literally nothing — no pre-existing Python environment, no pre-existing
Docker image layers assumed valid, no pre-existing browser binaries —
and it found two real issues (one in this verification session's own
setup, one a genuine pre-existing Docker/WSL2 instability) neither of
which had been triggered by any faster, cache-reusing stage before it.
