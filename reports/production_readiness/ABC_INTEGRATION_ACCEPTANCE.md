# A+B + CPU Optimization + Workstream C Integration Acceptance (Stage 1)

Status legend: **VERIFIED** (executed against real infrastructure, output
inspected), **NOT APPLICABLE**.

## 1. Ancestry inspection — no merge was needed

Before assuming any merge/cherry-pick strategy, ancestry was inspected
directly:

```
git merge-base --is-ancestor 8aa90b3 1254adb   -> YES
git merge-base --is-ancestor 1254adb d1b17a4   -> YES
git merge-base --is-ancestor 8aa90b3 d1b17a4   -> YES
```

The three accepted branches form a **linear chain**, not divergent
history: `8aa90b3` (A+B) → `1254adb` (CPU-only optimization) →
`d1b17a4` (Workstream C). Each branch was created directly from the
previous one's tip. `d1b17a4` already contains every commit from both
`8aa90b3` and `1254adb` — there is nothing to merge, and no "ours"/
"theirs" conflict resolution is applicable, because there was never a
divergence. This was verified before creating anything, not assumed.

**Stage 1's actual work is therefore**: create the new integration
branch/worktree directly from `d1b17a4`, and independently re-verify the
combined capability set (A+B + CPU-only + Workstream C together) fresh,
on its own branch, rather than performing a needless merge operation.

## 2. Branch / worktree / commit

| | |
|---|---|
| Branch | `integration/ab-cpu-c` |
| Worktree | `D:/KLTN/edudss-integration-ab-cpu-c` |
| Base (created from) | `d1b17a4` |
| Final commit (this stage) | see §9 |

## 3. Database

Alembic head: **`6cfe48a652ca`** (single head, confirmed via `alembic
heads`). 40 public tables (confirmed via
`information_schema.tables`). No new migration was needed for this
stage (no schema change — pure re-verification).

## 4. Defects found during verification, diagnosed and fixed

Two issues surfaced during this stage's verification. Both were
diagnosed to root cause before any fix was applied — neither was a
product regression.

### 4.1 Test-isolation gap: `tests/conftest.py` (real, fixed)

**Symptom:** `test_lecturer_learning_explainer_renders_without_traceback`
and the session-scoped `_pollution_guard` teardown assertion failed on
the very first E2E run in this brand-new worktree, reporting that
`data_warehouse/logs/technical.log` (the REAL, non-isolated log file) was
created during the test session.

**Root cause:** `dss/core/logging_config.py::_configure_once()` binds its
`RotatingFileHandler` to `get_data_root()` at first use, memoized for the
whole process — by design, per its own docstring ("as long as
`EDUDSS_DATA_ROOT` is set before the first logger use"). pytest's
**collection** phase imports most of `dss/` (many modules call
`get_logger(__name__)` at module scope) **before any fixture runs**,
including the existing session-scoped `_isolated_data_root` autouse
fixture. In every worktree that had ever run anything before, this was
invisible: the pollution guard's directory comparison for the `logs`
bucket only tracks **filenames**, not content, so bytes appended to an
already-existing `technical.log` went undetected. In a genuinely fresh
worktree (no pre-existing `technical.log`), the guard correctly caught
the file's first-ever creation.

**Fix:** `os.environ.setdefault("EDUDSS_DATA_ROOT", tempfile.mkdtemp(...))`
added at the very top of the root `tests/conftest.py` module — the first
thing pytest imports, before any `dss` import happens anywhere in the
session. Verified compatible with the existing `_isolated_data_root`
fixture (which unconditionally overwrites the same env var per-session
and restores `previous` on teardown — with this fix, `previous` is now
the collection-time tmp dir instead of `None`, which is harmless).

**Verification:** deleted the worktree's own `data_warehouse/` (created
by my own test runs minutes earlier, not pre-existing/tracked content —
confirmed via `git status` before deleting) to re-create the genuinely
fresh-worktree condition, then re-ran the full E2E suite: **39/39
passed**, no pollution-guard failure.

This is a real, narrow, previously-undiscovered gap (CI never surfaces
it — `.github/workflows/edudss-release-gate.yml` excludes `tests/e2e`
entirely) — not a functional defect in the product; only test-harness log
placement was affected, never actual application behavior.

### 4.2 Self-inflicted: running too many heavy jobs in parallel (process, fixed)

Running the full non-E2E suite, the full E2E suite, and a `docker build
--no-cache` **simultaneously** produced a `psycopg2.OperationalError:
server closed the connection unexpectedly` mid-suite and a Playwright
timeout — both root-caused to resource exhaustion (the non-E2E suite,
normally ~2 minutes, took 32 minutes under that load) rather than a code
defect. Confirmed by re-running the single affected test in isolation
immediately after (8/8 passed, 43s).

Later in this same stage, Docker Desktop's own engine crashed entirely
(WSL2 `docker-desktop` distro stopped, zero Docker processes running) —
root-caused to cumulative memory pressure from 5 simultaneous full
`docker-compose` stacks left running from every prior workstream's
verification (A+B, CPU-only, Workstream C) plus this stage's own
concurrent heavy jobs, compounded by this development machine's limited
total RAM (~16GB) shared with the user's own already-substantial
application footprint (multiple editor windows, browsers). Diagnosed via
`docker version`, `tasklist`, and `wsl -l -v` (confirmed
`docker-desktop` WSL distro state = `Stopped`). Resolved by: locating the
per-user Docker Desktop install (`%APPDATA%\...\Docker Desktop.lnk` →
`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` — not under
`C:\Program Files`, which is why a naive search first failed), restarting
it, confirming full engine recovery (`docker version`, `docker ps`
against the auto-resumed compose containers), and restarting the one
manually-`docker run` container that lacked a restart policy.

**Corrective action taken for the remainder of this run:** stopped and
removed the fully-completed, already-committed earlier stages' leftover
`docker-compose` stacks (A+B's, CPU-only's — their evidence is already
recorded in their own committed reports, so their containers were not
needed anymore), pruned ~7GB of accumulated build cache, and paced all
subsequent heavy jobs (builds, full test suites) to run **one at a time**
rather than in parallel. This is disclosed honestly here because it
materially affects how Stage 4's capacity/load testing (later in this
run) must be scoped and reported — see that stage's own report for the
resource ceiling this specific machine actually has.

## 5. Test results (this stage, current run)

**Non-E2E suite** (host venv, real Postgres, run alone after the
resource-contention fix): `700 passed, 2 skipped in 631.65s`. The 2
skips are the same pre-existing, unrelated ones already documented in
prior reports (a dedicated Phase 13 fixture requirement, a dev-machine-
only `.env` check).

**E2E suite** (run alone, after the conftest.py fix): `39 passed in
941.26s (0:15:41)`.

**Focused in-container cross-check** (real Docker image, real
containerized Postgres/pgvector/simulator, via the already-built
`edudss-closure-c-opt-streamlit-integration-1` container — content-
identical to this branch's commit since the only diff is the test-only
`conftest.py` fix): `tests/test_workstream_ab_postgres_integration.py`,
`tests/test_workstream_c_ml_provenance.py`, `tests/test_db_row_level_security.py`,
`tests/test_ai_gateway_governance.py`, `tests/test_pgvector_store.py` —
**28 passed, 6 skipped** (skips are env-var-scoped tests not relevant to
this specific invocation, e.g. Workstream B's own separate credential
set), 0 failed.

## 6. 20K batch benchmark

**This is 20,000-student batch inference, not 20,000 concurrent users.**

```
Total inference time:    2.7017 s
Throughput:              7402.8 predictions/sec
```

Threshold: <5s, >5,000/sec — **PASS**.

## 7. Docker

Clean `docker build --no-cache` of `edudss-integration-abc:d1b17a4`
succeeded (after the Docker Desktop crash/recovery in §4.2, run alone).

```
torch.__version__ = 2.9.1+cpu
torch.version.cuda = None
torch.cuda.is_available() = False
```

`pip list | grep -iE "nvidia|triton|cuda"` → no matches. Standalone
container run: `uid=999(edudss) gid=999(edudss)`, HTTP 200 on
`/_stcore/health`.

## 8. Known limitation found (not acted on, out of scope for this stage)

While investigating §4.1, `app/data_warehouse/embeddings/` and
`app/data_warehouse/metadata/` were found to contain files that are
**still tracked in git** despite `data_warehouse/` being covered by
`.gitignore` (confirmed via `git check-ignore -v`) — almost certainly
committed before a later phase's `.gitignore` fix was applied, with the
already-tracked files never subsequently removed via `git rm --cached`.
This surfaced only because deleting the directory to test a fresh-
worktree scenario showed up as tracked-file deletions in `git status`;
those deletions were immediately reverted (`git checkout --
app/data_warehouse/`) since modifying/removing this pre-existing tracked
content was never this stage's intent and is out of this stage's scope.
Flagged here for visibility; not fixed in this commit.

## 9. Checkpoint 1

| Criterion | Result |
|---|---|
| A+B regression | **PASS** |
| CPU optimization | **PASS** |
| Workstream C regression | **PASS** |
| Migrations | **PASS** (single head, zero→head previously verified in Workstream C's own report; unchanged here) |
| RLS | **PASS** |
| RAG | **PASS** |
| AI Gateway | **PASS** |

**CHECKPOINT 1: PASSED — proceeding to Stage 2.**
