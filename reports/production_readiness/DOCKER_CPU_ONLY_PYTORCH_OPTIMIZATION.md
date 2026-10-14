# Docker CPU-Only PyTorch Optimization

Status legend: **VERIFIED** (executed against real infrastructure in this
session, output inspected), **SIMULATED** (real HTTP/HMAC/PostgreSQL
machinery, standing in for a live third-party LMS/CMS — inherited, unchanged
by this task), **NOT VERIFIED**, **NOT APPLICABLE**.

## 1. Base commit / branch / worktree

| Item | Value |
|---|---|
| Accepted base | `integration/workstream-a-b` @ `8aa90b3` |
| Branch | `optimization/docker-cpu-only-pytorch` |
| Worktree | `D:/KLTN/edudss-docker-cpu` |
| Final candidate commit | `0dbc171` — "fix: deterministic CPU-only PyTorch + drop xgboost's GPU-only nccl dep" |

## 2. Root cause of the CUDA/NVIDIA dependencies

`requirements.txt` pinned `torch==2.9.1` with no index constraint. On the
Dockerfile's `python:3.11-slim` (Debian/manylinux) base, plain
`pip install torch==2.9.1` resolves from default PyPI to the **CUDA 12.8**
build (`torch.__version__ == "2.9.1+cu128"`), because `pip show torch`
confirms `Requires: ... nvidia-cublas-cu12, nvidia-cuda-cupti-cu12,
nvidia-cuda-nvrtc-cu12, nvidia-cuda-runtime-cu12, nvidia-cudnn-cu12,
nvidia-cufft-cu12, nvidia-cufile-cu12, nvidia-curand-cu12,
nvidia-cusolver-cu12, nvidia-cusparse-cu12, nvidia-cusparselt-cu12,
nvidia-nccl-cu12, nvidia-nvjitlink-cu12, nvidia-nvshmem-cu12,
nvidia-nvtx-cu12, ..., triton` — these are **direct dependencies of the
GPU wheel itself**, not something the application code requested. This was
confirmed by dependency-tree evidence (`pip show torch`, `pip list`), not
assumed.

A second, independent root cause was found during verification:
`xgboost==3.1.2`'s own wheel metadata (`pip show xgboost` →
`Requires: numpy, nvidia-nccl-cu12, scipy`) unconditionally depends on
`nvidia-nccl-cu12` (~450MB installed) for multi-GPU distributed training —
never used by this app's CPU `tree_method="hist"` path. This is entirely
independent of the torch fix; fixing torch alone (first build) left
`nvidia-nccl-cu12` in the image.

**Application source audit** (`grep -rniE "cuda|\.to\(.?[\"']cuda|device\s*=\s*[\"']cuda"`):
only two hits, both conditional fallbacks that already handle CPU
correctly — `dss/core/models.py:1174` (`if dss_config.torch.cuda.is_available(): ... else: ... torch_dtype=float32, device_map=None`) and the same pattern in the legacy, still-tracked `5.py`. Neither is a hard CUDA requirement.

**CUDA REQUIRED BY EDUDSS APPLICATION: NO**

## 3. Root cause of the multi-hour "stalled build" appearance

The build did **not** hang. The second clean build (`--no-cache`, both
fixes applied) completed successfully in **27m38s** wall-clock, with this
stage breakdown (from the saved build log):

| Stage | Duration |
|---|---|
| `pip install -r requirements.txt && pip install --no-deps xgboost==3.1.2 && <assertion>` | 517.1s (~8.6 min) |
| `apt-get install libgomp1` | 11.1s |
| `COPY . /app` | 2.9s |
| `useradd`/`chown` | 3.0s |
| **`exporting to image`** (layer export 309.7s + **unpacking 793.9s**) | **1104.9s (~18.4 min)** |

**67% of total build time was Docker's own layer export/unpack phase**,
not dependency resolution or installation. `docker build ... | tail -100`
in the prior session buffered all output until the pipeline closed, so
nothing was visible for the ~18-minute export/unpack phase (BuildKit emits
one line at the start of that phase and one at the end, nothing in
between) — combined with the session itself being interrupted before the
completion notification was delivered, this produced the appearance of an
indefinite hang. Ground truth at the start of this recovery: `docker
images` already showed `edudss-cpu-only:8aa90b3` built and tagged, `docker
system df` showed 0 active builds, and the image ran and verified
correctly. **The build was not stuck; the notification was lost across a
session boundary.**

`grep -in "nvidia|nccl|cuda|triton"` against the complete build log
returned **zero matches** — confirms no GPU package was ever downloaded in
this build.

## 4. Dependency changes

**`app/requirements.txt`**: added `--extra-index-url
https://download.pytorch.org/whl/cpu` and changed `torch==2.9.1` to
`torch==2.9.1+cpu` (exact local-version-identifier pin). Removed the
`xgboost==3.1.2` line (moved to the Dockerfile, see below), with an
inline comment explaining why.

**`app/Dockerfile`**: after the main `pip install -r requirements.txt`,
added `pip install --no-deps xgboost==3.1.2` (numpy/scipy/scikit-learn/
joblib, its only actually-used dependencies, are already installed from
the line above), then a build-time Python assertion that **fails the
build** if any `nvidia-*`/`triton` package is present or torch isn't a
`+cpu` build with `cuda.is_available() is False` — so a future dependency
change that reintroduces GPU packages is caught immediately, not
discovered later.

**`.github/workflows/edudss-release-gate.yml`**: added the same
`pip install --no-deps xgboost==3.1.2` line after `pip install -r
requirements.txt` in the job that runs `pytest` directly (not the Docker
build job, which already gets it from the Dockerfile), so CI still
exercises `XGBOOST_AVAILABLE` code paths.

**`app/README.md`**: documented the same two-line install sequence for
local dev.

**Why this strategy is deterministic** (not `pip install CPU torch;
pip install -r requirements.txt` with a plain `torch==2.9.1` pin, which
the task correctly flagged as unsafe): pinning the **exact local version
identifier** `torch==2.9.1+cpu`, resolved from the official CPU wheel
index declared in the same file, means no wheel without that exact local
tag — including the default-PyPI `2.9.1+cu128` wheel — can satisfy the
requirement. This holds for every future `pip install -r requirements.txt`
run, with or without `--upgrade`, as long as the pin is unchanged; it does
not rely on pip's "skip if already satisfied" behavior at all. Verified
directly: `pip install --dry-run 'torch==2.9.1+cpu' --extra-index-url
https://download.pytorch.org/whl/cpu` resolves to `torch-2.9.1+cpu` with
no `nvidia-*` packages in the "Would install" list.

xgboost's fix uses a different mechanism (`--no-deps`) because pip has no
per-line `--no-deps` syntax inside a `requirements.txt` file — the
package had to move to its own install step, after its real dependencies
are already satisfied by the main install.

## 5. PyTorch CPU evidence

| | Before | After |
|---|---|---|
| `torch.__version__` | `2.9.1+cu128` | `2.9.1+cpu` |
| `torch.version.cuda` | `12.8` | `None` |
| `torch.cuda.is_available()` | `False` | `False` |

(Both `False` for `cuda.is_available()` — there is no GPU in this
environment either way; the difference is entirely the ~5GB of unused GPU
runtime code shipped in the image, not runtime behavior.)

## 6. XGBoost CPU evidence

Verified inside `edudss-cpu-only:8aa90b3`: trained an `XGBClassifier`
(`tree_method="hist"`) on a synthetic 500-row dataset, predicted,
`pickle`-serialized, reloaded, predicted again —
`np.array_equal(preds1, preds2)` and `np.allclose(proba1, proba2,
atol=1e-9)` both held (exact equivalence), with zero `nvidia-*` packages
installed at any point. `xgboost.__version__ == "3.1.2"` (version
unchanged, per the task's requirement).

## 7. NVIDIA package audit

**Before** (`edudss-ab-stage-streamlit-integration:latest`, the accepted
A+B image): `nvidia-cublas-cu12 nvidia-cuda-cupti-cu12
nvidia-cuda-nvrtc-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12
nvidia-cufft-cu12 nvidia-cufile-cu12 nvidia-curand-cu12
nvidia-cusolver-cu12 nvidia-cusparse-cu12 nvidia-cusparselt-cu12
nvidia-nccl-cu12 nvidia-nvjitlink-cu12 nvidia-nvshmem-cu12
nvidia-nvtx-cu12 triton` — 16 packages, **4,953MB** on-disk
(`du -sh` on the `nvidia/` + `triton*` site-packages directories).

**After** (`edudss-cpu-only:8aa90b3`): `pip list | grep -iE
"nvidia|cuda|cudnn|cublas|cufft|curand|cusolver|cusparse|nccl|nvjitlink|nvtx|triton"`
→ **zero matches**. Confirmed again with `importlib.metadata.distributions()`
inside the running `edudss-cpu-opt-streamlit-integration-1` container:
`bad packages in running container: []`.

Nothing was deleted after installation — both fixes work by preventing
the packages from ever being installed.

## 8. Image size

| | Value |
|---|---|
| Before (`edudss-ab-stage-streamlit-integration:latest`) | 13,794,874,748 bytes (13.79GB) |
| After (`edudss-cpu-only:8aa90b3`) | 3,650,341,514 bytes (3.65GB) |
| Absolute reduction | 10,144,533,234 bytes (~9.45GB) |
| Percentage reduction | **73.5%** |

Both measured via `docker inspect --format '{{.Size}}'`, not estimated.

## 9. Runtime dependencies vs dev/test dependencies

Audited whether `pytest`, `pyflakes`, `playwright` are needed in the final
runtime image: `grep` confirms nothing under `dss/`, `simulator/`, or
`run_dss.py` imports any of them (test-only tooling). However:

- No `requirements-dev.txt`/`requirements-test.txt` exists, and CI
  (`edudss-release-gate.yml`) installs tests from `requirements.txt`
  alone, with no second `-r` file.
- The Dockerfile never runs `playwright install`, so no browser binaries
  (the actual multi-hundred-MB cost of Playwright) ever enter the image —
  the `playwright` Python package itself is a small client/driver.
- The dominant size driver by nearly two orders of magnitude was the
  CUDA/NVIDIA stack (~5GB) and xgboost's stray NCCL dependency (~450MB),
  not these three packages.

**Decision: left unchanged, in the single `requirements.txt`.** Splitting
them would require also updating CI's install step and any docs that
assume a single-file install, for a size gain measured in tens of MB
against a torch/xgboost fix that already removed ~9.45GB. Not worth the
added reproducibility risk for this task's actual goal. Documented per
the task's own escape hatch ("if separation introduces unnecessary risk,
leave them unchanged and document that decision").

RUNTIME DEPENDENCIES: streamlit, plotly, numpy, pandas, scipy, matplotlib,
openpyxl, xlsxwriter, scikit-learn, joblib, shap, streamlit-shap,
lightgbm, imbalanced-learn, sentence-transformers, transformers,
torch (CPU), huggingface-hub, google-genai, groq, openai, requests,
python-dotenv, tenacity, pypdf, python-docx, python-pptx, reportlab,
psycopg2-binary, sqlalchemy, alembic, pgvector, xgboost (installed
separately, `--no-deps`).

DEV/TEST DEPENDENCIES (present in the same file, by the decision above):
pytest, anyio, pyflakes, playwright.

## 10. Import regression

Inside `edudss-cpu-only:8aa90b3` and, independently, inside a genuinely
fresh (non-Docker) venv built from the fresh checkout (§17): `torch`,
`sentence_transformers`, `transformers`, `numpy`, `pandas`, `scipy`,
`sklearn`, `xgboost`, `lightgbm`, `shap`, `imblearn`, `sqlalchemy`,
`psycopg2`, `pgvector` — all import cleanly. **PASS**.

## 11. SentenceTransformer / embedding regression

Loaded the real `sentence-transformers/all-MiniLM-L6-v2` model (not
mocked) inside `edudss-cpu-opt-streamlit-integration-1`, `device="cpu"`:

```
device: cpu
shape: (2, 384)
dtype: float32
finite: True
```

384-dimensional, finite values, correct batch shape for 2 input
sentences. **PASS**.

## 12. RAG / pgvector regression

Ran the real A+B integration suite
(`tests/test_workstream_ab_postgres_integration.py`, 4/4) and the
Workstream B persistence suite (`tests/test_workstream_b_persistence_closure.py`,
11/11) against a live `pgvector/pg16` container from inside the CPU-only
image, exercising the full lifecycle: CMS content → 384-d embedding →
`rag_chunks`/`rag_documents` (PostgreSQL) → real server-side `<=>`
similarity search (`PgVectorStore.search`, not a mock) → `content.updated`
webhook → old-vector invalidation (0 rows for the stale `document_id`) →
re-index (new `…:v2` chunk) → new-content retrieval (top-1 result) →
stale retrieval blocked → delete lifecycle
(`test_cms_content_and_real_pgvector_replace_delete_lifecycle`). All
passed, identical to the accepted A+B baseline's behavior — the CPU-only
torch build changes nothing here, since both the CUDA and CPU torch
builds only ever executed on CPU in this environment.

## 13. ML regression

Full application pytest suite (`tests`, excluding `e2e` and `load`) run
inside `edudss-cpu-only:8aa90b3` against the live Postgres:

```
1 failed, 635 passed, 24 skipped in 74.10s
```

The 1 failure is `tests/security/test_security_and_secrets.py::
test_zero_live_api_keys_in_env_example_and_config` — it asserts
`app/.env.example` exists inside the container. It does not, because
`.dockerignore`'s pre-existing `.env.*` glob (line 5, untouched by this
task) excludes it from every Docker build, including the original
13.8GB accepted image — **confirmed by reproducing the identical failure
inside `edudss-ab-stage-streamlit-integration:latest`** before concluding
anything. This is a pre-existing packaging gap, not a CPU/torch/xgboost
regression, and is out of this task's scope (Docker/dependency
optimization only) to fix.

This run includes `test_clustering_fixes.py`, `test_model_registry.py`,
`test_regression_param_grid.py`, `test_target_leakage_and_modes.py`,
`test_audit_and_governance.py` (all of which exercise
`dss.core.trainers`, i.e. the real classification/regression/clustering/
XGBoost/LightGBM/SHAP paths) — all passed, no tolerances loosened.

No numeric output comparison against the accepted baseline was performed
beyond "all these tests, which assert exact/tolerant values, still pass
unchanged" — because scikit-learn, numpy, pandas, scipy, and lightgbm are
byte-identical versions to the accepted baseline (untouched by this
task), and xgboost is the identical `3.1.2` wheel installed via
`--no-deps` (which only skips its *dependency* resolution, not anything
about xgboost's own code) — so no numeric drift was expected, and none
was observed.

## 14. A+B integration regression

Re-ran against a live, correctly-networked Docker Compose stack built
from the CPU-only image (`edudss-cpu-opt` project, isolated from the
accepted branch's running containers — distinct ports/container names,
nothing shared was touched):

```
tests/test_db_row_level_security.py ...... 6 passed
tests/test_workstream_ab_postgres_integration.py .... 4 passed
tests/test_workstream_b_persistence_closure.py ........... 11 passed
tests/test_lms_cms_simulated_http_integration.py ....................... 23 passed
tests/test_lms_ai_rag_gateway.py ................. 17 passed
tests/test_lms_live_sync.py ... 3 passed
tests/test_integration_phase1b_security8a.py ........ 8 passed
tests/test_phase12a_integration.py ...... 6 passed
```

**78/78 passed** — pagination, full sync, incremental sync, persistent
cursor, idempotent resync, webhook HMAC, persistent inbox, duplicate and
out-of-order handling, `submission.created`/`grade.updated`/
`content.updated`, non-superuser RLS, tenant isolation, restart-safe sync
state, all unchanged from the accepted A+B behavior.

One re-run was needed: the webhook sub-test initially returned `599`
(connection failure) because the test's `WebhookReceiver` defaults to
binding `127.0.0.1`, which inside a container is *that container's own*
loopback — unreachable from the separate simulator container. Setting
`WORKSTREAM_AB_WEBHOOK_ADVERTISED_HOST=streamlit-integration` (the
compose service's internal DNS name) fixed it. This is the exact same,
already-documented limitation from the accepted A+B report (§6 there) —
not a new regression, not something introduced by this task.

This remains **SIMULATED LMS/CMS INTEGRATION = VERIFIED**, not a live
external LMS. No relabeling.

## 15. Docker runtime acceptance

Isolated `docker compose -p edudss-cpu-opt --profile integration-ab up`
(distinct ports/container names from the accepted branch's running
stack — nothing there was touched or stopped):

| Check | Result |
|---|---|
| EduDSS container starts | VERIFIED |
| PostgreSQL starts, healthy | VERIFIED |
| pgvector works | VERIFIED (§12) |
| LMS/CMS simulator starts, healthy | VERIFIED |
| Container-to-container HTTP | VERIFIED (A+B suite uses `postgres:5432`, `lms-cms-simulator:8765`, `streamlit-integration` internal DNS names throughout) |
| HTTP 200 | VERIFIED (`/`, `/_stcore/health`) |
| Liveness/readiness | VERIFIED |
| Non-root UID | VERIFIED — `uid=999(edudss) gid=999(edudss)`, unchanged |
| LMS/CMS sync | VERIFIED (§14) |
| Webhook | VERIFIED (§14) |
| CMS → RAG → pgvector | VERIFIED (§12) |

One pre-existing, out-of-scope issue surfaced and worked around (not
fixed, per this task's scope): `app/postgres-init/01-app-role.sh` is
committed with git mode `100644` (not executable), so PostgreSQL's
`docker-entrypoint-initdb.d` silently skips it (`cannot execute: required
file not found`) and the `edudss_app` role is never auto-created on a
fresh volume. This is inherited from the accepted A+B branch (confirmed:
`git ls-files -s` shows `100644` there too) — worked around here by
manually running the same `CREATE ROLE`/`GRANT`/`ALTER DEFAULT
PRIVILEGES` statements the script contains, exactly as was necessary
during the original A+B acceptance. Flagged in Known Limitations; not
fixed, since it is unrelated to CPU/torch/xgboost and this task's scope
is dependency/Docker optimization only.

## 16. 20K batch benchmark

**This is 20,000-student batch inference, not 20,000 concurrent users.**

Run inside `edudss-cpu-opt-streamlit-integration-1`:

```
Total cohort size:       20000 students
Total inference time:    2.1472 s
Throughput:              9314.6 predictions/sec
```

Threshold: elapsed < 5s (2.15s, PASS), throughput > 5000/sec (9314.6/sec,
PASS). Faster than the accepted A+B reference (3.06s / 6525.5/sec) — this
benchmark is pure scikit-learn `Ridge` inference and does not touch torch
at all, so the difference reflects normal host-load variance between
runs, not an optimization effect. Reported honestly rather than claimed
as caused by this change.

## 17. Fresh-checkout reproducibility

A detached worktree was created from the final commit `0dbc171`
(`git worktree add --detach`, at `D:/KLTN/edudss-cpu-fresh-checkout`).
**No venv junction/symlink was used this time** — a brand-new venv was
created from scratch (`python -m venv .venv`), and the documented
install procedure from `README.md` was followed exactly:

```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-deps xgboost==3.1.2
```

Result:

```
torch.__version__ = 2.9.1+cpu
torch.version.cuda = None
torch.cuda.is_available() = False
```

`pip list | grep -iE "nvidia|triton|cuda"` → no matches. `xgboost`
imports and predicts correctly. Imports of the full dependency set
(`dss.integrations.*`, `simulator.*`, torch, sentence_transformers,
transformers, numpy, pandas, scipy, sklearn, xgboost, lightgbm, shap,
imblearn, sqlalchemy, psycopg2, pgvector) all succeed. Test discovery:
**700 tests collected**.

A second, independent `docker build --no-cache --progress=plain` was
also run from this same fresh detached checkout (not reusing any
previously-built layer, tagged `edudss-cpu-fresh:0dbc171`), to close the
Docker-build side of the reproducibility gap the same way.

### 17a. Fresh Docker build result

Completed in 26m25s. Build-time assertion (Dockerfile step, §4) passed
during the build itself: `CPU-only dependency assertion OK: 2.9.1+cpu`.
Post-build verification:

```
torch.__version__ = 2.9.1+cpu
torch.version.cuda = None
torch.cuda.is_available() = False
```

`pip list | grep -iE "nvidia|triton|cuda"` → no matches. Image size:
**3,650,337,678 bytes (3.65GB)** — within 4KB of the first build
(`edudss-cpu-only:8aa90b3`, 3,650,341,514 bytes), i.e. reproducibly the
same result from an independent, from-scratch checkout and build. This
closes the reproducibility gap the accepted A+B report explicitly
disclosed (it had reused the project venv via a directory junction); this
task instead used a genuinely fresh venv (§17) **and** a genuinely fresh
Docker build, neither reusing anything from a prior environment.

## 18. CI consistency

The CI workflow (`edudss-release-gate.yml`) installs from the same
`requirements.txt` (now CPU-only by construction, no separate CI-only
index configuration needed) plus the same `pip install --no-deps
xgboost==3.1.2` line the Dockerfile and README use — there is no scenario
where Docker resolves CPU-only while CI or a fresh local install resolves
CUDA. The `--extra-index-url` in `requirements.txt` applies identically
regardless of caller (`pip install -r requirements.txt` from Dockerfile,
CI, or a developer's shell).

Note: this same CI workflow's later steps (table-count and Alembic-head
assertions) were found to be pre-existing-stale (27 tables /
`797f72d1c666`, vs. the current schema's 37 tables / `a14b15c16d17`) —
inherited from before the A+B integration, unrelated to this task, and
explicitly out of scope to fix here (this task is dependency/Docker
optimization only).

## 19. Known limitations

1. `app/postgres-init/01-app-role.sh` lacks the executable git mode
   (`100644` instead of `100755`), inherited from the accepted A+B
   branch — PostgreSQL's init hook silently skips it on a fresh volume.
   Worked around manually for this task's verification; not fixed here
   (out of scope).
2. `.dockerignore`'s pre-existing `.env.*` pattern excludes
   `app/.env.example` from every Docker image (confirmed present in the
   original 13.8GB image too), causing one pre-existing test failure
   inside any container. Not a regression from this task; not fixed here
   (out of scope).
3. The CI workflow's later Alembic/table-count assertions are stale
   relative to the current schema (pre-existing, unrelated to this task).
4. `pytest`/`pyflakes`/`playwright` remain in the single
   `requirements.txt` (runtime image includes them) — a deliberate,
   documented low-risk choice (§9), not an oversight.
5. This task never claims GPU deployment is supported, GPU performance
   was tested, or that GPU acceleration is unnecessary for every future
   deployment. **CUDA is not required for the currently accepted EduDSS
   deployment target.** A future GPU deployment would use a separate
   GPU image/profile (e.g. a second Dockerfile stage or `requirements-gpu.txt`
   pinning the CUDA wheel index instead) — not attempted here, out of
   scope.

## 20. Git safety evidence

```
main HEAD:              unchanged (10b487d, not touched by this task)
integration/workstream-a-b: unchanged (still at 8aa90b3 going into this
                             task; this task's own final commit 0dbc171
                             is on the NEW optimization branch, not on
                             workstream-a-b)
stash@{0}:               untouched
```

No `git add -A` / `git add .` was used — only the four intended files
were staged explicitly (`.github/workflows/edudss-release-gate.yml`,
`app/Dockerfile`, `app/README.md`, `app/requirements.txt`). No user
untracked files were read, modified, or deleted.

## 21. Final truth labels

| | |
|---|---|
| CUDA REQUIRED FOR CURRENT DEPLOYMENT TARGET | **NO** |
| PYTORCH STILL REQUIRED | **YES** (sentence-transformers/RAG embeddings depend on it) |
| CPU-ONLY PYTORCH VERIFIED | **YES** |
| UNNECESSARY NVIDIA RUNTIME REMOVED | **YES** |
| XGBOOST CPU VERIFIED | **YES** |
| 384-D EMBEDDING VERIFIED | **YES** |
| A+B REGRESSION | **PASS** (78/78) |
| DOCKER RUNTIME | **PASS** |
| FRESH CLEAN INSTALL | **PASS** (fresh venv and fresh Docker build both reproduced `torch==2.9.1+cpu`, zero NVIDIA packages — §17, §17a) |

**FINAL STATUS: PASS_WITH_DOCUMENTED_LIMITATIONS**

**READY AS BASE FOR WORKSTREAM C/D: YES**

**DO NOT MERGE — remains on `optimization/docker-cpu-only-pytorch`.**
