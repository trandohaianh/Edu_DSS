# 20,000-Student Batch Prediction — Performance Remediation

Base commit: `dbc4bb253b370be4b1253d08f5d9245948f2c471` (current accepted main).
Branch: `performance/20k-batch-remediation` (worktree: `D:/KLTN/edudss-performance`).
Candidate commit: see below (created after this report). **Not merged into `main`.**
`stash@{0}` and all other worktrees were never touched at any point in this pass.

## Original implementation

`tests/load/test_lms_scale_load.py::test_20000_students_batch_prediction_benchmark` times
exactly this block:

```python
t0 = time.perf_counter()
res = resolve_production_for_prediction(wh, dataset_id="benchmark_dataset", target_col="diem_cuoi_ky")
prod_model = res["pipeline"]
X_pred = cohort_df[features]
predictions = prod_model.predict(X_pred)
elapsed_total_sec = time.perf_counter() - t0
```

`resolve_production_for_prediction` (`dss/services/model_service.py`) calls
`model_registry.resolve_production`, which calls `_load_artifact_cached` — a function decorated
`@st.cache_resource(show_spinner="Đang tải mô hình Production...")` in
`dss/services/model_registry.py`. This is the **only** artifact-loading call in the timed
block; `prod_model.predict(X_pred)` (the actual 20,000-row inference) is a separate, tiny
operation.

## Profiler evidence

`cProfile`, run on the exact timed block with all module imports pre-warmed outside the
profiled region (matching how pytest's own module-level imports work — see methodology note
below), sorted by internal (self) time:

```
639756 function calls (633312 primitive calls) in 2.118 seconds
Ordered by: internal time

ncalls  tottime  percall  cumtime  percall  filename:lineno(function)
  7758    1.050    0.000    1.050    0.000  {built-in method nt._getfinalpathname}
     1    0.117    0.117    0.161    0.161  sqlalchemy/sql/schema.py:1(<module>)
  3627    0.054    0.000    0.054    0.000  {built-in method nt._path_exists}
    15    0.034    0.002    1.348    0.090  inspect.py:982(getmodule)
  3879    0.030    0.000    1.134    0.000  ntpath:692(realpath)
```

Call-chain trace (`pstats.Stats.print_callers`, followed link by link):

```
resolve_production_for_prediction (cumtime 1.984s of 2.118s total)
  -> streamlit.runtime.metrics_util.wrapped_func           (st.cache_resource's own wrapper)
    -> streamlit.elements.empty.empty()                    (the spinner's placeholder element)
      -> streamlit.delta_generator._enqueue
        -> streamlit.delta_generator._maybe_print_use_warning()
          -> streamlit.env_util.is_repl()
            -> inspect.stack()                              <- THE EXPENSIVE CALL
              -> inspect.getouterframes() -> getframeinfo() (x12 frames)
                -> inspect.findsource() -> inspect.getmodule()
                  -> ntpath.realpath() -> nt._getfinalpathname (x7758, Windows syscall)
```

**Ranked bottleneck table:**

| Component | Time | % of total | Evidence | Optimization candidate |
|---|---|---|---|---|
| `st.cache_resource`'s spinner (`st.empty()`) triggering Streamlit's `is_repl()` stack walk | ~1.05–1.4s (varies with call-stack depth) | ~50–65% | `cProfile` `tottime`/`cumtime` for `nt._getfinalpathname`/`inspect.stack()`, traced caller-by-caller to `_load_artifact_cached`'s decorator | **Yes — fixed** (see below) |
| Lazy `from dss.services import model_registry` import inside `resolve_production_for_prediction`, pulling in `audit_log_repository`/`db.models`/SQLAlchemy schema for the first time | ~0.16–0.3s | ~10–15% | `cProfile` shows `sqlalchemy/sql/schema.py` module-level exec inside the timed block on a cold process | Documented, not fixed this pass (see Remaining limitations) |
| Actual `.predict()` on 20,000 rows (a 6-feature `Ridge`, no pipeline preprocessing steps) | ~0.28ms | <0.02% | Directly measured in isolation (see below): `0.281 ms/call` for 20,000×6 `Ridge.predict` | Not a candidate — already negligible |
| Data generation, model training/promotion (200-row `Ridge.fit`, `DataWarehouse` metadata writes) | not measured — happens **before** `t0`, outside the timed block | 0% of measured time | Test code itself starts `t0` after these steps | N/A |

**Direct isolated measurement of the actual prediction cost** (unrelated to the fix, included to
show the true prediction cost is not the bottleneck): 20,000×6 `Ridge.predict`, 20 iterations,
raw call: **0.281 ms/call**. This is 4 orders of magnitude smaller than the ~2–4 second total
the benchmark was measuring — confirming the benchmark was never actually measuring "prediction
throughput" in practice; it was measuring a one-time Streamlit diagnostic tax that happened to
fall inside the timed window.

## Root cause

`_load_artifact_cached` (`dss/services/model_registry.py:23`) is decorated
`@st.cache_resource(show_spinner="Đang tải mô hình Production...")`. Passing a **string** to
`show_spinner` makes Streamlit render a real UI element (a spinner via `st.empty()`) while the
cache-miss body executes. The **first** Streamlit UI element ever created in a process that has
no active `ScriptRunContext` (exactly pytest's situation, and any other headless/background
invocation) triggers `delta_generator._maybe_print_use_warning()`, which calls
`env_util.is_repl()`, which calls `inspect.stack()` to decide whether the process looks like an
interactive REPL — walking the *entire* call stack and resolving each frame's file path via
`os.path.realpath()`, which on Windows shells out to `nt._getfinalpathname()`, a comparatively
slow syscall, once per frame. With the call stack depth reached inside a real pytest run through
`model_service.py`/`model_registry.py`/`warehouse.py`, this adds up to roughly 1–2 seconds.

Streamlit guards this check with a **module-level global flag**
(`_use_warning_has_been_displayed`), so the expensive path runs **exactly once per process** —
completely invisible in a long-running real Streamlit app (paid once at first UI render, most
likely during the app's own startup, and never again). It only becomes a problem precisely
because this pytest benchmark is normally the *first* Streamlit element ever created in its
process, landing the one-time tax squarely inside a 5-second budget test — and explains the
flakiness observed across this whole engagement's prior phases: when the benchmark ran as part
of a large full-suite run (where some earlier test had already triggered a Streamlit element),
it sometimes passed; run in isolation, it reliably paid the tax and hovered right at the
threshold.

## Optimization

```diff
-@st.cache_resource(show_spinner="Đang tải mô hình Production...")
+@st.cache_resource(show_spinner=False)
 def _load_artifact_cached(_wh, warehouse_scope: str, training_id: str):
```

One line. `show_spinner=False` tells `st.cache_resource` not to create any UI element for this
cache's miss path at all — it never calls `st.empty()`, so it never triggers the expensive
first-element diagnostic check via this call site.

## Why this optimization is safe

- **Prediction semantics**: unaffected — `_load_artifact_cached`'s body (`_wh.load_model_training(training_id)`) is untouched.
- **Model version**: unaffected — the cache key (`warehouse_scope`, `training_id`) is untouched; `training_id` still changes on every Promote/Rollback exactly as before.
- **Feature ordering**: unaffected — `resolve_production_for_prediction` builds `feature_cols` from the same metadata, untouched.
- **Input validation**: unaffected — no validation logic lives in this decorator or function.
- **Security / tenant isolation**: unaffected — this function has no database/tenant-scoped logic; it loads a joblib artifact from the local warehouse path.
- **Observability**: unaffected and verified (Section below) — `model_registry.py`/`model_service.py` contain no `@observed`/`observe()` calls at all; `ml_hub.py`'s `predict_with_metrics` call sites (the actual observability integration point for predictions) are untouched and still invoked exactly once per UI operation, never per-row.
- **Public API**: unaffected — `resolve_production_for_prediction`'s signature, return dict shape, and `_load_artifact_cached`'s signature are all untouched. Only a keyword argument's *value* on an internal decorator changed.
- **Correctness**: proven bit-for-bit identical (see below) — this change cannot alter computed values because it doesn't touch computation at all, only a UI side-effect.
- **User-visible effect (production only)**: the "Đang tải mô hình Production..." spinner text
  no longer appears during a real cache-miss model load in the Streamlit UI. Given a real
  cache-miss load from local disk (warm OS file cache, no `nt._getfinalpathname` diagnostic
  tax in a real running session past its very first UI render) typically completes in well
  under a second, this is judged an acceptable, minor UX trade-off against removing a
  multi-second tax that was landing in an automated performance gate. It is not a functional
  regression.

## Correctness proof

A deterministic fixture (fixed `RandomState` seeds for both model training data and the
prediction cohort, 5,000 rows) was run against the **unmodified** code, then again against the
**fixed** code, saving raw prediction arrays and metadata for direct comparison:

| Check | Result |
|---|---|
| Row count | 5,000 == 5,000 |
| Row ordering (`student_id` sequence) | Identical |
| Feature ordering (`feature_cols` from `resolve_production_for_prediction`) | Identical |
| Model name / training id resolution | Identical |
| `np.array_equal(before, after)` (exact bitwise equality) | **True** |
| Max absolute difference | **0.0** |
| `np.allclose(rtol=1e-9, atol=1e-12)` | True (trivially, given exact equality) |

No floating-point tolerance was actually needed — the two prediction arrays are bit-for-bit
identical, as expected for a change that touches zero computation.

## Before measurements (unmodified code, 5 runs)

| Run | Elapsed (s) | Throughput (rps) | Pass/Fail |
|---|---|---|---|
| 1 | 4.6912 | 4263.3 | FAILED |
| 2 | 4.1235 | 4850.3 | FAILED |
| 3 | 3.8993 | 5129.2 | PASSED |
| 4 | 3.8963 | 5133.1 | PASSED |
| 5 | 4.0434 | 4946.4 | FAILED |

Elapsed: min 3.8963, max 4.6912, median 4.0434, mean 4.1307.
Throughput: min 4263.3, max 5133.1, median 4946.4, mean 4864.5.
**3 of 5 baseline runs failed** — confirms this is the same environment-sensitive,
borderline-threshold condition documented in every prior phase's reports.

Environment for all baseline and after runs: Python 3.12.4; Intel Core i7-6700HQ @ 2.60GHz
(4 physical cores / 8 logical threads, a 2015-era mobile quad-core, not a server CPU); shared
development machine with VS Code, browser, and Docker Desktop processes concurrently present
(not idle, but no deliberate competing load was started during measurement); model: `Ridge`
(scikit-learn, 6 features, no pipeline preprocessing steps); rows: 20,000; prediction code
path: `resolve_production_for_prediction()` -> `model_registry.resolve_production()` ->
`_load_artifact_cached()` (`st.cache_resource`) -> `pipeline.predict()`.

## After measurements (fixed code, 5 runs)

| Run | Elapsed (s) | Throughput (rps) | Pass/Fail |
|---|---|---|---|
| 1 | 2.3668 | 8450.4 | PASSED |
| 2 | 2.3436 | 8534.0 | PASSED |
| 3 | 2.3180 | 8628.1 | PASSED |
| 4 | 2.3709 | 8435.6 | PASSED |
| 5 | 2.2939 | 8718.9 | PASSED |

Elapsed: min 2.2939, max 2.3709, median 2.3436, mean 2.3386.
Throughput: min 8435.6, max 8718.9, median 8534.0, mean 8553.4.
**5 of 5 runs passed**, with throughput consistently 69–74% above the 5,000rps threshold and
elapsed time consistently 53% below the 5.0s threshold — a stable, comfortable margin, not a
single lucky pass.

## Regression

All run from this branch, not reused from any prior phase's numbers:

| Suite | Result |
|---|---|
| Non-E2E (including the 20k benchmark itself, `DATABASE_URL`+`DATABASE_APP_ROLE_URL` configured) | **574 passed, 1 skipped** (1 pre-existing, unrelated `.env`-dependent skip) |
| E2E | **39 passed, 0 failed** |
| ML-specific / Phase 12A observability (`test_observability_phase12a.py`, `test_phase12a_integration.py`) | 8 passed + 6 (need DB, run as part of the full suite above) — all pass |
| Security (`test_security_upload.py`+`test_security_logging.py`+`test_security_prompt.py`) | 19/19 (part of the full suite above) |

Zero regressions anywhere. The 20k benchmark itself is now consistently passing as part of the
full suite too (was previously a known flaky/failing member of that same run).

## Fresh checkout

Candidate commit `4557370`. A completely new detached worktree was created from that exact
commit (`git worktree add --detach ../edudss-perf-fresh-check 4557370`) — nothing carried over
from the working worktree.

| Check | Result |
|---|---|
| Imports (`model_registry`, `model_service`, `observability`) | PASS |
| 20k benchmark | **PASSED** — 2.4374s elapsed, **8205.6 rps** (consistent with the 5 "after" runs above) |
| Streamlit startup | PASS |
| HTTP | 200 |
| Streamlit health | `ok` |

## Docker

Per instruction: no Docker/dependency change was required for this fix (a single Python
keyword-argument value change), so **Dockerfile/.dockerignore were not touched** — verified
byte-identical to the base commit (`dbc4bb2`) before building. Built and ran the current
accepted Docker configuration as-is (cache-assisted build, ~2s — dependencies unchanged):

| Check | Result |
|---|---|
| Non-root | PASS — `uid=999(edudss) gid=999(edudss) groups=999(edudss)` |
| Healthy | PASS — Docker-native `(healthy)`, HTTP 200, `/_stcore/health` → `ok` |
| 20k benchmark (run via `docker exec ... pytest`, inside the container) | **PASSED** — 2.4105s elapsed, **8297.2 rps** |

Container number (8297.2 rps) is reported separately from the host numbers (8435.6–8718.9 rps)
per instruction — not mixed into the same statistics — but is consistent with them, confirming
the fix holds inside Docker's CPU scheduling too.

## Known limitations

- The lazy `from dss.services import model_registry` import inside
  `resolve_production_for_prediction` (`dss/services/model_service.py`) still pays a one-time
  SQLAlchemy/`audit_log_repository`/`db.models` import cost (~0.16–0.3s measured) the first
  time it's called in a fresh process — this remains inside the timed block on a cold run. It
  was not fixed in this pass because the already-achieved margin (69–74% above the throughput
  threshold, 53% below the elapsed threshold, 5/5 stable) does not require it, and moving a
  lazy import to module level is a real (if very safe) code change that the task's "prefer
  minimal, evidence-backed changes" framing argues against making without necessity. Flagged
  here as a legitimate future optimization candidate if the margin ever needs to grow further.
- This fix only addresses the *test/pytest* manifestation of the underlying Streamlit
  diagnostic cost. Any other code path that is the *first* Streamlit UI element created in a
  fresh process (a cold Streamlit worker, a background job, a CLI script that imports the app)
  would still pay the same one-time tax once — this is inherent to Streamlit's own
  `_maybe_print_use_warning` design, not something this codebase controls. It is invisible in
  the normal running web app because the app's own UI naturally creates its first element very
  early during startup, long before any user-perceptible interaction.
- The `show_spinner="..."` string pattern may exist on other `@st.cache_resource`/
  `@st.cache_data` decorators elsewhere in the codebase; this pass deliberately scoped its
  change to the single decorator on the 20k benchmark's actual code path, per the task's
  explicit instruction to fix only what profiling evidence supports for this specific
  blocker — a broader sweep was not performed and would be a separate, explicitly-scoped task.

## Final acceptance

- Benchmark test itself: **unmodified** (`tests/load/test_lms_scale_load.py`, byte-identical to base commit).
- Threshold: **unmodified** (`elapsed < 5.0s AND throughput > 5000 rps`).
- Both acceptance conditions pass: **YES**, 5/5 host runs and both fresh-checkout/Docker runs.
- Repeated measurements demonstrate the improvement: **YES** — 5/5 after vs. 3/5-failing before, non-overlapping distributions (before max 5133.1 rps vs. after min 8435.6 rps).
- Prediction correctness preserved: **YES** — bit-for-bit identical on a deterministic fixture.
- Regression suites pass: **YES** — 574/575 non-E2E (1 pre-existing unrelated skip), 39/39 E2E.
- Fresh-checkout benchmark passes: **YES** — 8205.6 rps.

**PERFORMANCE STATUS: PASS**
