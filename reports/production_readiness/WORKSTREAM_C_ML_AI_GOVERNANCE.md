# Workstream C — ML Provenance, Data/Model Drift, and Unified AI Gateway

Status legend: **VERIFIED** (executed against real infrastructure, output
inspected), **SIMULATED** (real HTTP/HMAC/PostgreSQL machinery standing in
for a live third-party system — inherited, unrelated to this workstream),
**NOT VERIFIED**, **NOT APPLICABLE**.

## 1. Base commit

`optimization/docker-cpu-only-pytorch` @ `1254adb`.

## 2. Final candidate commit

`closure/workstream-c-ml-ai-governance` @ `5c38b46` (worktree
`D:/KLTN/edudss-closure-c`).

## 3. Files changed

New: `app/dss/db/migrations/versions/6cfe48a652ca_ml_provenance_and_drift.py`,
`app/dss/services/ml_provenance.py`,
`app/dss/db/repositories/ml_provenance_repository.py`,
`app/tests/test_ml_provenance_core.py`,
`app/tests/test_workstream_c_ml_provenance.py`,
`app/tests/test_ai_gateway_governance.py`.

Modified: `app/dss/db/models.py` (new ORM classes + `ModelVersion`
extension), `app/dss/core/warehouse.py` (additive provenance hook),
`app/dss/core/persistence_config.py` (new `ML_PROVENANCE` flag),
`app/dss/services/model_registry.py` (`get_provenance()`,
`evaluate_drift()`), `app/dss/services/learning_explainer.py` (AI Gateway
fix), `app/dss/tabs/learning_explainer_tab.py` (thread `user_id` through),
`app/dss/services/llm_service.py` (quota gate for Compare AI),
`app/dss/services/llm_gateway.py` (new
`check_quota_and_rate_limit()` method).

14 files changed, 2130 insertions(+), 9 deletions(-) (see `git diff
1254adb 5c38b46 --stat` in this worktree).

## 4. Schema/migration changes

One new migration, `6cfe48a652ca`, `down_revision = a14b15c16d17`. New
tables `dataset_provenance`, `feature_schema_provenance`,
`drift_evaluations` (all direct tenant tables — own `organization_id`,
`ENABLE`+`FORCE ROW LEVEL SECURITY`, one `tenant_isolation` policy each,
byte-identical pattern to every prior migration in this repo). Extends
`model_versions` with 9 new nullable columns: `algorithm`,
`artifact_checksum_sha256`, `dataset_provenance_id` (FK),
`feature_schema_provenance_id` (FK), `hyperparameters`, `code_commit`,
`python_version`, `library_versions`, `created_by`. No existing migration
was edited. No historical migration was rewritten.

**Alembic head: `6cfe48a652ca`** — VERIFIED zero→head (fresh ephemeral
Postgres, twice: once in the main worktree, once from a fresh detached
checkout, §21) and `a14b15c16d17`→`6cfe48a652ca` (the immediate prior
head, applied as part of the same zero→head run — no separate downgrade
round-trip was performed for this specific step since the new migration
only adds tables/nullable columns, nothing to safely round-trip test
beyond what `downgrade()` itself already demonstrates its own reversal
logic for).

## 5. Model provenance design

Per registered model version, recorded (when
`EDUDSS_ML_PROVENANCE_STORE=postgres`): `model_id` (row id),
`organization_id`, `model_key`, `dataset_id`, `target_col`, `algorithm`
(introspected from the fitted pipeline's final estimator class, e.g.
`RandomForestClassifier`), `model_version` (existing `version` field in
the warehouse JSON, unchanged), `artifact_path`,
`artifact_checksum_sha256` (the SAME SHA-256 `warehouse.py` already
computed and verifies on load — mirrored, not recomputed), `created_at`/
`trained_at`, `dataset_provenance_id` (FK), `feature_schema_provenance_id`
(FK), `hyperparameters` (best-effort `estimator.get_params(deep=False)`,
filtered to JSON-safe scalars), evaluation metrics (normalized into
`model_metrics`, one row per metric — replaces, not accumulates, on
re-evaluation), `code_commit` (best-effort: `EDUDSS_GIT_COMMIT` env var
first, since the Docker image has no `.git` directory per
`.dockerignore`; falls back to `git rev-parse HEAD` for a dev checkout;
`None` if neither is available — never fabricated), `python_version`,
`library_versions` (numpy/pandas/scipy/scikit-learn/xgboost/lightgbm/
shap/torch, via `importlib.metadata`), `status`
(`candidate`/`production`/`archived`, mirrors the existing warehouse
lifecycle exactly — no new status vocabulary invented), `created_by`.

Design decision: the joblib artifact + its JSON metadata file
(`dss/core/warehouse.py::save_model_training`) remain the **unconditional,
unchanged, primary source of truth** — this was true before this
workstream and stays true after it. Postgres provenance is an **additive,
best-effort mirror**, off by default (`ML_PROVENANCE` not in
`_IMPLEMENTED_POSTGRES_FEATURES`'s enabled set until the operator opts
in), wrapped in `try/except` at every call site so a Postgres outage never
breaks a training run. This directly satisfies "existing inference must
remain functional" (§9 of the task) and "do not store binary model
artifacts directly in PostgreSQL" (§3) — nothing binary is ever written to
Postgres; `artifact_path` is a plain string reference to the existing
on-disk `.joblib` file.

## 6. Dataset provenance design

`dss/services/ml_provenance.py::compute_dataset_fingerprint()` records,
per training dataset: row/column counts, a **schema fingerprint** (column
names + dtypes, order-sensitive) and a **content fingerprint** derived
from per-column summary statistics only — for numeric columns:
null-count, mean/std/min/max (rounded to 6 significant figures); for
categorical columns: null-count and the top-20 most frequent values with
their counts. No raw rows are ever stored or hashed row-by-row. Verified
(`test_dataset_fingerprint_does_not_store_raw_rows`) that the serialized
provenance record for a 300-row dataset is under 5KB — genuinely
"reproducibility evidence, not a second data warehouse," per the task's
own framing.

## 7. Feature-schema fingerprint

`compute_feature_schema_fingerprint()` — SHA-256 of a canonical JSON
payload built from: feature names **in the given order** (order is
semantically part of the fingerprint, not sorted away), per-feature
dtypes, per-feature numeric/categorical roles, the target definition, the
model task type, and the preprocessing-expectations dict. Verified
deterministic (same input twice → identical hash) and verified to change
under each of: reordered features, changed dtype, changed role, changed
target, changed task type, changed preprocessing — 7 dedicated tests in
`test_ml_provenance_core.py`, all passing.

## 8. Data drift methodology

**Population Stability Index (PSI)**, same binning methodology for
numeric (quantile bins derived from the baseline distribution) and
categorical (natural category bins) features — chosen over separate
KS/chi-square frameworks specifically so there is ONE consistent, bounded
score and ONE threshold system across both feature types, using the
de facto production-ML-monitoring threshold bands. For numeric features,
`scipy.stats.ks_2samp` (scipy is already a pinned dependency) is
additionally reported as a secondary, non-binning-dependent corroborating
statistic — it does not drive the status decision. This is a heuristic
distribution-shift indicator, not a hypothesis test with a p-value; no
claim of statistical certainty is made for any single evaluation
(documented explicitly in the module docstring).

## 9. Performance drift methodology

Classification: accuracy, weighted precision/recall/F1 (`scikit-learn`,
already pinned). Regression: RMSE, MAE, R². Requires **real ground truth
for both the baseline and current window** — if either is missing/empty,
returns `PERFORMANCE_DRIFT_NOT_EVALUABLE` with a `reason` field, never a
fabricated number. Verified with real (synthetic but genuine) labels for
both a detected-degradation case and a no-degradation case, for both task
types, plus the not-evaluable and insufficient-data paths.

## 10. Thresholds

| | Default | Configurable via |
|---|---|---|
| PSI warning | 0.10 | `warning_threshold` |
| PSI drift | 0.25 | `drift_threshold` |
| Min samples per feature | 20 | `min_samples` |
| Numeric bins | 10 | `numeric_bins` |
| Performance warning (relative drop) | 5% | `warning_relative_drop` |
| Performance drift (relative drop) | 10% | `drift_relative_drop` |

All are function parameters with explicit defaults, not hidden constants —
verified configurable in `test_thresholds_are_configurable` (same computed
PSI value classified differently under different thresholds, proving the
threshold is actually consulted).

## 11. Model lifecycle

Unchanged from the accepted lifecycle
(`TRAINED → candidate → [Admin promote] → production → [next promote]
→ archived`, in `dss/services/model_registry.py`/`dss/core/warehouse.py`).
This workstream adds a **retraining recommendation**, never an action:
`recommend_action(data_drift_status, performance_drift_status) →
NO_ACTION | REVIEW_REQUIRED | RETRAIN_RECOMMENDED`. Verified
(`test_recommend_action_never_returns_an_automatic_promotion_action`) that
no combination of inputs yields anything resembling an automatic-promotion
signal — the only three possible outputs are all advisory. Nothing in this
codebase consumes `RETRAIN_RECOMMENDED` to trigger training or promotion
automatically; `model_registry.promote()` remains `@require_role("Admin")`
and is the only path to production, unchanged.

## 12. AI call-site audit

Full production-code audit (excludes `app/tests/`, and `app/5.py` — the
pre-refactor monolith, confirmed not reachable from the production
entrypoint `run_dss.py → dss/main.py`):

| Call site | Direct or Gateway | Verdict |
|---|---|---|
| `dss/core/models.py::MultiAIProvider.call_ai_provider` (genai/Groq/openai SDK calls) | N/A — this IS the provider adapter | **Acceptable** (§11: "Direct provider SDK usage is acceptable inside the provider adapter implementation itself") |
| `dss/services/llm_gateway.py::_probe_provider_health` (admin "test connection") | Direct, deliberately | **Acceptable** — isolated diagnostic, needs real unswallowed exceptions to classify health, documented rationale in file header |
| `dss/tabs/ai_advisor.py::_run_connection_test` (admin "Kiểm tra kết nối" button) | Direct | **Acceptable** — same class as above, admin-only diagnostic, not user-facing generation |
| `dss/tabs/ai_advisor.py` HuggingFace-local branch (advice generation) | Direct | **Documented exception** — local/free model, no quota/cost/rate-limit concept applies; unchanged by this workstream |
| `dss/tabs/ai_advisor.py` main advisor flow (cloud providers) | **Through Gateway** | Correct — reference pattern |
| `dss/tabs/ai_advisor.py` chat sub-feature | **Through Gateway** | Correct |
| `dss/tabs/home.py` dashboard quick-ask | **Through Gateway** | Correct |
| `dss/services/learning_explainer.py::generate_explanation` (student-facing CMS lecture explainer) | **Was direct — FIXED** | See §13 |
| `dss/services/llm_service.py::compare_providers` (Lecturer/Admin "Compare AI") | Direct by design (N-parallel), **quota gate added** | See §13 |

## 13. Direct provider bypasses found, and how they were resolved

**Finding 1 (the real bypass): `learning_explainer.py:405`.** Student-
facing, real production feature — not a diagnostic, not an adapter. Called
`llm_integration.call_ai_provider(...)` directly: zero quota check, zero
rate limiting, zero concurrency cap, zero token/cost tracking, zero
Production Demo Policy honesty guard. The file's own docstring claimed it
went "through llm_gateway (via call_ai_provider... same as ai_advisor.py
does)" — that claim was **false**; it mirrored `ai_advisor.py`'s narrow,
justified HuggingFace-local exception pattern, not the correct
Gateway-routed pattern the same file uses for every cloud provider.

**Fix:** `generate_explanation()` and `advance_socratic_session()` now
accept `user_id`/`role` (threaded through from `learning_explainer_tab.py`,
which already computed a real per-student pseudonym for logging —
no new PII surface introduced) and call
`LLMGateway(llm_integration).stream_generate(...)` — the exact same call
shape `ai_advisor.py`'s correct paths already use. Docstring corrected.
Verified: `test_generate_explanation_routes_through_llm_gateway_not_direct_provider_call`
asserts `LLMGateway.stream_generate` was called and
`MultiAIProvider.call_ai_provider` was **not** — a direct regression guard
against this exact bypass reappearing.

**Finding 2 (narrower, by-design exception with a real gap):
`llm_service.py::compare_providers`.** Deliberately calls N providers in
parallel (Lecturer/Admin-only "Compare AI" feature) — genuinely cannot use
`LLMGateway.stream_generate()`'s fallback cascade, because the entire
point of the feature is knowing whether each *specifically requested*
provider works, and `stream_generate(provider=X, fallback_allowed=False)`
still silently substitutes a different provider from its internal chain
when `X` has no configured API key (confirmed by reading
`llm_gateway.py:465-494` — the "no key" branch does not consult
`fallback_allowed` at all, only the exception-handling branch does).
Routing through the full cascade would have made the comparison feature
report a *different* provider's answer under the requested provider's
label — a correctness bug, not a fix. It DID, however, have a real gap:
**zero organization/user quota enforcement**, reachable by any Lecturer.

**Fix:** added `LLMGateway.check_quota_and_rate_limit(user_id, role,
prompt)` — the exact quota-check/rate-limit gate `stream_generate()`
already runs before touching any provider, extracted as its own callable.
`compare_providers()` now calls it once before dispatching the parallel
calls; on `GatewayError` it returns an honest per-provider error result
instead of silently proceeding. Verified in
`test_compare_providers_enforces_quota_gate_before_dispatching` and
`test_compare_providers_dispatches_when_quota_gate_passes`.

## 14. Remaining justified direct-SDK usage

`MultiAIProvider.call_ai_provider` (the provider adapter itself),
`_probe_provider_health`/`ai_advisor.py`'s connection-test button (admin
diagnostics), and the HuggingFace-local branch (no quota/cost concept
applies to a local model) — see §12 verdicts. None of these are arbitrary
feature code; all are either the adapter itself or a narrow, documented,
admin-or-local-only exception.

## 15. Streaming result

Audited separately per §13 of the original task. There is exactly one
real streaming implementation in this codebase
(`MultiAIProvider.call_ai_provider`, a generator); `LLMGateway.stream_generate`
wraps/iterates it. **All production streaming call sites now go through
`LLMGateway.stream_generate`** except the two documented exceptions in
§12/§14 (HuggingFace-local, and admin diagnostics, neither of which
streams a fabricated response). No case of "normal generation → gateway,
streaming → direct provider" exists — both paths converge on the same
adapter, reached the same way.

## 16. RAG regression

Full lifecycle re-verified end-to-end, real embedding, no mocks for the
core acceptance:

```
CMS content → all-MiniLM-L6-v2 (PyTorch 2.9.1 CPU) → 384-dim embedding
→ PostgreSQL pgvector → real server-side <=> retrieval → RAG context
→ LLMGateway → provider
```

`tests/test_pgvector_store.py` (11/11), `tests/test_workstream_ab_postgres_integration.py`
(4/4, includes `content.updated` → stale-vector invalidation → re-index →
new retrieval → stale-retrieval-blocked, and the delete lifecycle) — all
passed against a live `pgvector/pg16` container, both on the host and
inside the built Docker image (§22). Embedding dimension verified = 384
(carried over unchanged from the accepted CPU-only baseline; this
workstream did not touch the embedding path).

## 17. Security / RLS

New tables use the identical `tenant_isolation` RLS pattern
(`ENABLE`+`FORCE ROW LEVEL SECURITY`, `USING`/`WITH CHECK` on
`current_setting('app.organization_id', true)`) as every existing tenant
table. Verified with a genuine **non-superuser** role
(`edudss_app`, granted only `SELECT/INSERT/UPDATE/DELETE` via
`ALTER DEFAULT PRIVILEGES`, never a superuser/owner connection) in
`test_07_non_superuser_cross_tenant_provenance_and_drift_isolated`: a
second organization, connected as the SAME non-superuser role, gets
`None`/zero rows for the first organization's provenance and drift data —
not an error, not a data leak. `tests/test_db_row_level_security.py`
(6/6) re-passed unchanged. No API keys, passwords, or tokens are ever
written to `hyperparameters`/`library_versions`/any new column — these
carry only algorithm parameters (ints/floats/strings/bools), library
version strings, and a git commit hash. Logging (§18) never includes
prompts, secrets, or raw feature values.

## 18. Observability

Added structured log events (via the existing
`dss.core.logging_config.get_logger` convention, no new logging
framework): `model registered` (training_id, model_key, algorithm,
status), `drift evaluation started`/`drift evaluation completed`
(training_id, both statuses, recommended action), `drift detected`
(warning-level), `retraining recommended` (warning-level). `model
promoted`/`model rolled back` were already instrumented (existing
`audit_log_repository.record` calls in `model_registry.py`, untouched).
`AI gateway request`/`provider selected`/`provider failure and fallback`/
`quota rejection` were already instrumented (`llm_gateway.py`'s existing
`@observed("ai.gateway", ...)` and `record_operation("ai.provider_attempt", ...)`
calls) — not duplicated here. No prompts or secrets are logged by any new
code.

## 19. Test results

All counts below are from THIS session's actual runs, not carried over
from any prior workstream's report.

**Non-E2E/non-load suite** (host venv, real Postgres, owner + app-role
credentials both exercised across the run):

```
700 passed, 2 skipped in 128.62s
```

The 2 skips are both pre-existing and unrelated to this workstream (a
dedicated Phase 13 backup/recovery fixture requirement, and a
dev-machine-only `.env` file check) — confirmed by reading both skip
reasons directly.

**Test discovery, fresh checkout:** 742 collected (700 baseline + 42 new:
29 in `test_ml_provenance_core.py`, 8 in `test_workstream_c_ml_provenance.py`,
5 in `test_ai_gateway_governance.py`).

**Inside the built Docker image**, against the real containerized
Postgres/pgvector/simulator over internal Docker networking:

```
tests/test_workstream_ab_postgres_integration.py .... (4)
tests/test_workstream_c_ml_provenance.py ........ (8)
tests/test_ml_provenance_core.py ............................. (29)
tests/test_ai_gateway_governance.py ..... (5)
tests/test_db_row_level_security.py ...... (6)
tests/test_pgvector_store.py ........... (11)
63 passed, 1 warning in 55.88s
```

**Fresh checkout** (genuinely new venv, no junction, fresh ephemeral
Postgres): `test_db_row_level_security.py` (6), `test_workstream_c_ml_provenance.py`
(8), `test_ml_provenance_core.py` (29), `test_ai_gateway_governance.py`
(5), `test_pgvector_store.py` (11) — **59 passed**.

**E2E:** first full run hit one failure
(`test_lecturer_learning_explainer_renders_without_traceback`) under heavy
concurrent load (a Docker build plus several other running containers on
the same machine at the time). Investigated before accepting it: that
specific test only exercises the LECTURER upload/view path in
`learning_explainer_tab.py`, which this workstream never touched (all
edits were in the STUDENT-facing socratic/chat panels). Re-ran the two
affected tests in isolation — both passed. Re-ran the **entire** E2E suite
clean a second time to get a genuinely complete, non-partial result:

```
39 passed in 1052.10s (0:17:32)
```

**Total across this session: 700 + 63 + 59 + 39 = 861 test executions,
zero real failures** (one transient, resource-contention-caused E2E
failure, investigated and reproduced as passing in isolation and in a
full clean rerun — not reported as a partial or hidden result).

## 20. 20K benchmark

**This is 20,000-student batch inference, not 20,000 concurrent users.**

| Run | Elapsed | Throughput |
|---|---|---|
| Host venv | 2.69s | 7,443.0/sec |
| Inside built Docker image | 2.31s | 8,653.2/sec |

Threshold: <5s, >5,000/sec — **PASS** on both. Accepted A+B reference:
3.06s / 6,525.5/sec. Both this session's numbers are somewhat faster;
attributed to normal host-load variance (this benchmark is pure
scikit-learn `Ridge` inference and does not touch anything this workstream
changed), not claimed as an effect of this work.

## 21. Docker result

Clean `docker build --no-cache` succeeded (build-time CPU-only assertion,
inherited from the prior workstream, passed: `CPU-only dependency
assertion OK: 2.9.1+cpu`). `torch.__version__ == "2.9.1+cpu"`,
`torch.version.cuda is None`, `torch.cuda.is_available() is False`,
zero `nvidia-*`/`triton` packages (`pip list` — confirmed empty match).

**Image-size measurement note:** `docker inspect --format '{{.Size}}'`
reported an inconsistent, unreliable value for this build (845MB) —
starkly different from the CPU-only baseline's own `docker inspect`
figure (3.65GB) despite both images containing the same dependency set.
Investigated rather than reported blindly: a direct `du -sh /` inside a
running container of **both** images gives **2.6GB (CPU-only baseline)**
and **2.7GB (this workstream's image)** — nearly identical, consistent
with this workstream adding no new pip dependencies (only a small Python
module, a migration file, and test files). `docker inspect .Size` is
unreliable on this machine's Docker Desktop/containerd setup for
comparing separately-built images and should not be used for this
comparison; the `du`-based measurement is the trustworthy number reported
here.

Runtime acceptance (standalone container and an isolated
`docker compose --profile integration-ab` stack, distinct ports/container
names from every other running stack — nothing else was touched or
stopped): container starts, non-root **UID 999**, HTTP 200 (`/` and
`/_stcore/health`), PostgreSQL healthy, pgvector working, LMS/CMS
simulator healthy, container-to-container HTTP confirmed, ML inference
(20K benchmark, §20) and RAG (§16) both confirmed inside the container, AI
Gateway behavior confirmed via the full 63-test in-container run (§19) —
no paid provider call was required for any of this; the Compare-AI quota
gate and `generate_explanation`'s Gateway routing are both verified via
mocked-provider tests, not real API calls.

## 22. Fresh-checkout result

Closed the same reproducibility gap the prior two workstreams' reports
disclosed and closed for themselves: a **genuinely fresh venv** (`python
-m venv .venv` from scratch, no junction/symlink to any existing venv)
plus an **independent `docker build --no-cache`**, both from a
`git worktree add --detach` of the exact final commit `5c38b46`.

- Dependency installation: VERIFIED (`pip install -r requirements.txt`
  then `pip install --no-deps xgboost==3.1.2`, per README.md)
- `torch == 2.9.1+cpu`, `torch.version.cuda is None`,
  `torch.cuda.is_available() is False`: VERIFIED
- Zero NVIDIA packages: VERIFIED
- Imports: VERIFIED (all new/changed modules)
- Test discovery: VERIFIED (742 tests)
- Alembic zero→head (fresh ephemeral Postgres): VERIFIED, single head
  `6cfe48a652ca`
- RLS, pgvector, ML provenance, drift, AI gateway tests: VERIFIED (59/59,
  §19)
- Docker build (independent, from the fresh checkout): VERIFIED — same
  CPU-only assertion passed, zero NVIDIA packages, `du -sh /` = 2.6GB
  (matches the main worktree's build to within measurement noise)
- Application startup: VERIFIED (standalone container, UID 999, HTTP 200)

## 23. Known limitations

1. `learning_explainer.py`'s HuggingFace-local advice-generation branch
   still bypasses the Gateway — a pre-existing, documented, deliberate
   exception (local/free model, no quota/cost concept applies), unchanged
   by this workstream.
2. `compare_providers()` still does not route through the Gateway's
   fallback cascade or its global concurrency semaphore — by design (see
   §13, Finding 2); it now shares the quota/rate-limit gate but has its
   own separate `ThreadPoolExecutor` concurrency cap
   (`dss.config.MAX_CONCURRENT_REQUESTS`), not integrated with the
   Gateway's global semaphore. This is a narrower, disclosed gap, not
   silently left unaddressed.
3. ML provenance to Postgres is off by default
   (`EDUDSS_ML_PROVENANCE_STORE` unset = local-only, matching every other
   persistence flag in this codebase) — an operator must explicitly opt
   in for the governance data described in this report to actually be
   recorded in a given deployment.
4. `docker inspect --format '{{.Size}}'` was found unreliable for
   cross-build image-size comparison in this environment (§21) — anyone
   extending this report's methodology should use `du -sh /` inside a
   running container instead.
5. The E2E suite showed one transient failure under heavy concurrent
   background load in this session (§19), fully investigated and
   reproduced as passing both in isolation and in a full clean rerun —
   noted here for transparency, not hidden.
6. This workstream does not implement Workstream D, university onboarding,
   national-scale load testing, FastAPI, or Kubernetes — out of scope by
   the task's own instruction.

## 24. Must-not-say claims — explicitly disclaimed

This report does **not** claim: that drift detection guarantees model
correctness; that any detected drift automatically means retraining is
required (only ever a recommendation, §11); that model performance can be
measured without ground truth (§9 — returns
`PERFORMANCE_DRIFT_NOT_EVALUABLE` instead); that all AI providers are
production-SLA verified; that prompt injection is completely prevented;
that the 20K batch benchmark means 20,000 concurrent users (§20, stated
explicitly); that the simulated LMS/CMS integration is a live university
integration; that national-scale capacity has been verified; or that the
system has reached full production readiness.

## 25. Truth labels

| | |
|---|---|
| MODEL PROVENANCE | **FULLY_WIRED_AND_TESTED** |
| DATASET PROVENANCE | **FULLY_WIRED_AND_TESTED** |
| FEATURE SCHEMA PROVENANCE | **FULLY_WIRED_AND_TESTED** |
| DATA DRIFT | **FULLY_WIRED_AND_TESTED** |
| PERFORMANCE DRIFT | **FULLY_WIRED_AND_TESTED** |
| ALL PRODUCTION AI CALLS THROUGH LLMGATEWAY | **NO** — two narrow, documented exceptions remain (HuggingFace-local, admin diagnostics); the one real bypass found (`learning_explainer.py`) was fixed, and the one by-design exception (`compare_providers`) now shares the Gateway's quota/rate-limit gate |
| RAG REGRESSION | **PASS** |
| CPU-ONLY DEPLOYMENT PRESERVED | **YES** |
| TENANT/RLS | **PASS** |
| 20K BATCH | **PASS** |
| DOCKER | **PASS** |
| FRESH CHECKOUT | **PASS** |

**FINAL STATUS: PASS_WITH_DOCUMENTED_LIMITATIONS**

**READY FOR NEXT INTEGRATION: YES**

**DO NOT MERGE — remains on `closure/workstream-c-ml-ai-governance`.**
