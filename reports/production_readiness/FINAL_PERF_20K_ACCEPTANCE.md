# Final Performance Acceptance — 20K Batch Prediction Remediation → main

Pre-merge main: `dbc4bb253b370be4b1253d08f5d9245948f2c471` (tagged `pre-perf-20k-remediation` for rollback).
Performance branch: `performance/20k-batch-remediation`.
Performance candidate: `5ad019a` (fix commit `4557370`).
Merge commit: `c412004ac24f56758ac75707a3566985ba4ae3b9` (`--no-ff`, 2 parents, history preserved, not squashed).
Final main HEAD (after this report commit): recorded below once committed.
`stash@{0}` was never touched — confirmed present and unchanged at every checkpoint of this pass.

## The fix, unchanged through the merge

```diff
-@st.cache_resource(show_spinner="Đang tải mô hình Production...")
+@st.cache_resource(show_spinner=False)
 def _load_artifact_cached(_wh, warehouse_scope: str, training_id: str):
```

Verified post-merge: `dss/services/model_registry.py` contains `show_spinner=False`;
`dss/services/model_service.py` (containing `resolve_production_for_prediction`) is
byte-identical to the pre-merge base; `tests/load/test_lms_scale_load.py` (the benchmark
itself, including both the `elapsed_total_sec < 5.0` and `throughput_rps > 5000` assertions)
is byte-identical to the pre-merge base. No additional performance changes were made during
the merge.

## Post-merge performance proof (host, 3 runs, from merged main)

| Run | Elapsed (s) | Throughput (rps) | Result |
|---|---|---|---|
| 1 | 2.6250 | 7619.1 | PASSED |
| 2 | 2.5848 | 7737.7 | PASSED |
| 3 | 2.3539 | 8496.5 | PASSED |

3/3 passed. Median throughput: 7737.7 rps (~55% above the 5,000rps threshold). Median elapsed:
2.5848s (~48% below the 5.0s threshold).

## Fresh checkout (from merge commit `c412004`)

A completely new detached worktree was created from the merge commit itself
(`git worktree add --detach ../edudss-final-perf-check c412004`).

| Check | Result |
|---|---|
| Imports | PASS |
| Test discovery | PASS — 575 tests collected |
| 20k benchmark | **PASSED** — 2.3383s elapsed, 8553.1 rps |
| Streamlit startup | PASS |
| HTTP | 200 |
| Streamlit health | `ok` |

## Regression (from the fresh checkout, not reused from any prior evidence)

| Suite | Result |
|---|---|
| Non-E2E | **574 passed, 1 skipped** (1 pre-existing, unrelated `app/.env`-dependent skip) |
| E2E | **39 passed, 0 failed** |
| Security (`test_security_upload.py` 14 + `test_security_logging.py` 3 + `test_security_prompt.py` 3) | **20/20** (security logging gained 1 test from unrelated concurrent work already present in the accepted base `dbc4bb2`, not from this performance change) |
| Phase 12A (`test_observability_phase12a.py` + `test_phase12a_integration.py`) | **8/8 unit + 6/6 integration** |

Matches the accepted candidate's numbers exactly (574/1/39/8+6), plus the security-suite count
reflects a pre-existing addition already in `dbc4bb2` before this merge, unrelated to the
performance fix.

## Docker (current committed configuration, unmodified)

`Dockerfile`/`.dockerignore` verified byte-identical to pre-merge `dbc4bb2` before building —
neither was touched by this merge. Built (cache-assisted, ~2s — dependencies unchanged) and ran
the current configuration as-is:

| Check | Result |
|---|---|
| Container healthy | PASS — Docker-native `(healthy)` status |
| Non-root | PASS — `uid=999(edudss) gid=999(edudss) groups=999(edudss)` |
| HTTP 200 | PASS |
| 20k benchmark (run via `docker exec ... pytest`, inside the container) | **PASSED** — 2.0114s elapsed, **9943.4 rps** |

Docker's benchmark number (9943.4 rps) is reported separately from the host numbers (7619.1–
8496.5 rps) — not combined into the same statistics, per instruction.

## Prediction equivalence

Established on the performance branch before this merge (`PERF_20K_REMEDIATION.md`,
byte-for-bit identical predictions on a deterministic fixture, `np.array_equal == True`, max
abs diff `0.0`) and unaffected by the merge itself, since the merge introduced no additional
code changes beyond what was already verified on the performance branch.

## Required untracked application source

None. Every file needed for imports, test discovery, application startup, and the benchmark
itself is tracked and present in the merge commit — confirmed by the fresh-checkout worktree
(a completely independent checkout with no shared state beyond the linked `.venv` for
dependencies and the external Postgres container) passing every check above.

## Remaining performance limitations

Unchanged from `PERF_20K_REMEDIATION.md`:
- A lazy `from dss.services import model_registry` import inside
  `resolve_production_for_prediction` still pays a one-time SQLAlchemy/`audit_log_repository`/
  `db.models` import cost (~0.16–0.3s measured) on a cold process. Not fixed — the achieved
  margin (all post-merge measurements 7619–9943 rps, comfortably above 5,000) does not require
  it. Flagged as a future optimization candidate only if the margin ever needs to grow further.
- The underlying Streamlit `_maybe_print_use_warning` one-time diagnostic-stack-walk cost is
  inherent to Streamlit itself (gated by a module-level flag, paid once per process) — this fix
  avoids triggering it from this specific code path, but any other code path that happens to be
  the *first* Streamlit UI element created in a fresh process would still pay it once. This is
  a Streamlit design characteristic, not something this codebase controls.
- No broader sweep was performed for other `show_spinner="..."` (string) usages elsewhere in
  the codebase — this fix was deliberately scoped to the single decorator on the 20k
  benchmark's actual code path, per the task's explicit instruction to fix only what profiling
  evidence supported for this specific blocker.

## Final acceptance

- Merge preserved history (`--no-ff`, not squashed): YES
- Exact fix (`show_spinner=False`) survived the merge unchanged: YES
- Benchmark test and thresholds unmodified: YES (byte-identical to base)
- All 3 post-merge host runs passed: YES (7619.1, 7737.7, 8496.5 rps)
- Fresh-checkout benchmark passed: YES (8553.1 rps)
- Full regression passed: YES (574/1 non-E2E, 39/39 E2E, 20/20 security, 8/8+6/6 Phase 12A)
- Docker: non-root, healthy, HTTP 200, benchmark passed inside container (9943.4 rps, reported separately)
- `stash@{0}` untouched: YES

**PERFORMANCE MERGE STATUS: PASS**

**PERFORMANCE BLOCKER CLOSED: YES**

**MAIN READY: YES**
