# Phase 8A: independent security hardening

## Integration-readiness verification (2026-09-17)

**Final status: PASS_WITH_INTEGRATION_DEPENDENCY.** All available tests and all 19 security cases pass. The committed Phase 1 baseline cannot execute the application because a pre-existing import target is absent. This is not a Phase 8A import regression. This status does not claim the broader 456 non-E2E / 39 E2E acceptance suite passed on this branch.

### Missing module investigation

| Item | Result |
|---|---|
| Missing module | `dss.core.logging_config` (`app/dss/core/logging_config.py`) |
| Expected by | `app/dss/core/warehouse.py:18` (`get_logger`); `run_dss.py` -> `dss/main.py` -> `data_helpers.py` -> `trainers.py` -> `models.py` -> `warehouse.py` |
| Introduced by commit | **`daf14a7`** added the import (`git log -S 'from dss.core.logging_config import get_logger' -- app/dss/core/warehouse.py`). `git log --all -- app/dss/core/logging_config.py` shows no committed version in available history. Phase 8A did not introduce the import. |
| Present in `daf14a7`? | **NO** (`git ls-tree` has no file) |
| Required before Phase 8A? | **YES**. The same startup import chain exists in `daf14a7`. |
| Location found | Original `D:\KLTN\code\app\dss\core\logging_config.py` exists only as an untracked file. It was not copied or edited. |
| Correct resolution | Commit the actual application logging module as part of its owning application work, then integrate that committed change with Phase 8A and rerun startup/regression. Do not copy uncommitted main-worktree content into this branch. |

### Regression and startup evidence

| Suite / check | Result |
|---|---|
| Unit/service (available persistence-config tests) | 6 passed, 0 failed |
| Integration (PostgreSQL schema and RLS) | 0 passed, 0 failed, 14 skipped: real `DATABASE_URL` and RLS app role unavailable |
| Complete available non-E2E (`python -m pytest . -q -rs` from `app/`) | **25 passed, 0 failed, 14 skipped**; 39 collected cases total |
| E2E | **NOT AVAILABLE in committed branch**; no E2E test file in `daf14a7` or this branch. The original worktree has untracked E2E and other test files; they were not copied. |
| Security (`pytest tests/test_security_upload.py tests/test_security_logging.py tests/test_security_prompt.py -q`) | **19 passed, 0 failed**: upload 14, logging 2, prompt/AI 3 |
| App imports | Security modules import successfully. `import run_dss` fails with `ModuleNotFoundError: dss.core.logging_config` on the pre-existing chain above. |
| Streamlit script execution | `streamlit.testing.v1.AppTest.from_file('run_dss.py').run()` records one uncaught exception, the same missing module. No claim of successful startup. |
| Docker build | **PASS** after adding `libgomp1`, required by the installed LightGBM wheel. `docker build -t edudss-security-phase8a:verify -f Dockerfile .` completed. The first build exposed `OSError: libgomp.so.1`; the rebuilt image no longer has that error. |
| Docker runtime | Container starts under `uid=999(edudss)`; `lightgbm` imports; Docker reports `running healthy` and `/_stcore/health` returns HTTP 200. AppTest **inside the container still fails** on pre-existing missing `dss.core.logging_config`. The HTTP healthcheck measures Streamlit server availability, not successful app script execution. |

The security cases cover traversal and dangerous names, invalid extension/MIME, oversized/empty/malformed/binary CSV, row/column bounds, spreadsheet magic, secret and student-ID log redaction, adversarial retrieved instructions, AI prompt and RAG query size limits, embedding size limit and masking of email/student IDs in personalized prompts. The 456 non-E2E / 39 E2E Phase 1 acceptance result refers to a larger uncommitted application tree, so it cannot establish regression status for this committed branch.

### Expected integration conflicts

| File | Security change and reason | Cherry-pick independently? | Expected Phase 1B conflict | Merge strategy |
|---|---|---|---|---|
| `dss/main.py` | Validate sidebar upload and compare digest to prevent unsafe parsing and filename-only duplicates | With `dss/security/upload_security.py`, yes | YES if main changed routing/sidebar | Reapply validator call at current sidebar upload boundary; keep current routing |
| `dss/core/models.py` | Bound RAG/embedding/AI input, mask identifiers, separate retrieved context and remove raw provider errors | With prompt/log modules, yes | YES if AI gateway changed | Port provider-specific guards into current gateway; run all provider and RAG tests |
| `dss/tabs/eda.py` | Validate uploaded feature CSV | With upload module, yes | YES if tab changed | Reapply at current feature upload handler |
| `dss/tabs/warehouse_tab.py` | Validate warehouse CSV/Excel uploads | With upload module, yes | YES if tab changed | Reapply at current warehouse handler |
| `Dockerfile` | Non-root app user, LightGBM OpenMP runtime and healthcheck | Yes | POSSIBLE if image/dependency build changed | Preserve current build dependency strategy; retain `libgomp1` and non-root user; verify writable mounts and app script startup |

No conflicts were resolved or merged. The currently committed `main` ref remains `daf14a7`, so the expected conflicts concern later integration with uncommitted Phase 1B application work.

Base: `daf14a7` (committed Phase 1 PostgreSQL foundation). Branch: `security-hardening`; worktree: `D:\KLTN\edudss-security`. No Phase 1 database files were edited or merged.

## Findings and changes

| Finding | Severity | Existing behavior | Fix | File | Test | Remaining risk |
|---|---|---|---|---|---|---|
| Uploads entered pandas parsers without one shared size, filename, content or row policy | HIGH | Active sidebar, warehouse and EDA upload paths parsed direct input | Validate CSV/XLS/XLSX extension, MIME where provided, magic/content, filename, bytes, rows, columns and duplicate content hash before use; errors omit file contents | `dss/security/upload_security.py`, `dss/core/data_helpers.py`, `dss/main.py`, `dss/tabs/warehouse_tab.py`, `dss/tabs/eda.py` | `test_security_upload.py` (14) | MIME is client supplied; supported Excel parsers remain third party code. Legacy `5.py` has separate upload paths and should remain disabled. |
| Secret files could enter Docker build context; app container ran as root | HIGH | `.env` ignored, but Streamlit secrets and key files were not; Dockerfile used root | Ignore secrets/key files in Git and Docker context, exclude upload and runtime data, use dedicated non-root user, add OpenMP runtime and app healthcheck | `.gitignore`, `app/.dockerignore`, `app/Dockerfile` | Image build, container `id`, LightGBM import, AppTest and Python suite | Bind-mounted host directories must be writable by container user; health endpoint does not verify script execution. |
| Provider exceptions and application logs could expose credentials or student data | HIGH | Raw provider exception text returned to UI; no central redaction | Return generic provider errors, log exception class only, install application log redaction at entry point | `dss/core/models.py`, `dss/security/log_redaction.py`, `run_dss.py` | `test_security_logging.py` (2) | Free-form PII beyond known patterns and logging configured before entry point may need deployment controls. |
| RAG document content was embedded directly into a privileged-looking prompt | HIGH | Retrieved text was interpolated into prompt with no trust label | Explicit system policy, escaped and size-bounded untrusted context, remove known instruction-like patterns, retain source label | `dss/security/prompt_boundary.py`, `dss/core/models.py` | `test_security_prompt.py` (3) | Prompt injection cannot be eliminated with text filters; review new ingestion paths and provider outputs. |
| Large AI and embedding inputs consumed unbounded work | MEDIUM | Prompt, runtime document and embedding text had no central caps | Bound AI prompt, RAG query/top-k/runtime docs, embedding text and uploaded tables | `dss/security/prompt_boundary.py`, `dss/core/models.py`, `dss/security/upload_security.py` | Prompt/upload tests; full suite | No distributed rate limit or database quota; Phase 6 owns quota. |
| Dependency manifest for Docker uses lower bounds | MEDIUM | `requirements_5py.txt` mostly uses `>=`; `requirements.txt` is mostly pinned but is not installed by this Dockerfile | No blind upgrades; record reproducibility risk | `app/requirements_5py.txt`, `app/requirements.txt` (audit only) | `pip check`: no broken requirements; `pip_audit` unavailable | Run an advisory scanner and lock Docker dependencies before release. |
| Streamlit response headers depend on serving infrastructure | MEDIUM | No dedicated reverse proxy or FastAPI layer in this committed base | DEFERRED: configure CSP, HSTS, frame and content-type policy at deployment ingress after testing Streamlit compatibility | Deployment boundary (no code edit) | Not applicable | Browser header policy currently depends on hosting setup. |

## Upload boundary

Defaults: `EDUDSS_MAX_UPLOAD_MB=10`, `EDUDSS_MAX_UPLOAD_ROWS=20000`, `EDUDSS_MAX_UPLOAD_COLUMNS=200`. Accepted extensions: CSV, XLSX, XLS. Names with separators, control characters, drive separators or dot prefixes are rejected; names are never used as filesystem paths. CSV requires UTF-8, consistent columns and nonempty records. XLSX archive members and expansion are bounded; macros and external links are rejected. Uploaded contents are not executed or logged. SHA-256 identifies duplicate sidebar uploads instead of filename alone.

`app/5.py` is a tracked legacy monolith with unguarded upload paths. The configured runtime is `run_dss.py` -> `dss/main.py`; legacy direct launch remains an unsafe path. Remove or quarantine it in a separate cleanup after confirming deployments do not use it.

## Secret and AI data policy

Tracked secret-file audit found only the `.env.example` template; no tracked `.env`, `secrets.toml`, PEM or key file. A broad credential-assignment pattern yielded many variable/placeholder matches and is not evidence of a real credential. No secret values are reproduced here. Git and Docker ignore rules now cover `.env*` (except the tracked template in Git), `secrets.toml`, PEM and key files.

Necessary AI context: learning weaknesses, coarse risk level, predicted GPA, relevant source excerpts. Optional: bounded progress note and local curriculum evidence. Prohibited in cloud prompts: passwords, API tokens, authorization/session tokens, direct email or student ID when avoidable, raw uploaded datasets and full student records. Known identifiers are masked before constructing personalized advice; unknown free-text identifiers remain a residual risk. Ollama receives the same bounded policy locally.

## Test evidence

- Baseline in this worktree: **6 passed, 0 failed, 14 skipped** (`python -m pytest tests -q -rs`).
- Final non-E2E suite: **25 passed, 0 failed, 14 skipped** (`python -m pytest tests -q -rs`).
- New security tests: **19** (upload 14, log 2, prompt 3).
- All 14 skips require a configured real PostgreSQL database or app role; no database behavior was simulated.
- `pip check`: no broken requirements. `pip_audit` is not installed. Docker image builds and starts as non-root after installing `libgomp1`; in-container AppTest still fails at the baseline's missing `dss.core.logging_config`. The prompt unit test uses an import stub solely for isolation.

## DEFERRED_TO_PHASE1_OR_PHASE8B

| Problem | Affected file/area | Recommended fix | Severity |
|---|---|---|---|
| Demo/default credentials and authentication lifecycle need a dedicated review | `dss/services/auth_service.py` | Remove production defaults; enforce secret sourcing and credential rotation without changing Phase 1 interfaces | HIGH |
| Database audit logging, RLS and tenant-policy verification require the real app role and database | `dss/db/**`, migrations, PostgreSQL repositories and policies | Execute Phase 1 integration/RLS tests against provisioned PostgreSQL and audit cross-tenant cases | HIGH |
| Persistent request quota/rate controls are outside this independent pass | Subscription/quota persistence | Implement in Phase 6 with tenant-aware storage | MEDIUM |

## Merge impact

This branch only adds app/security changes and does not modify Phase 1 persistence. Likely textual conflicts are concentrated in active UI/provider files if main advanced those paths after `daf14a7`; preserve the Phase 1 versions and reapply the validation/prompt call sites during merge. New security modules/tests/report should merge cleanly. Do not merge until reviewed against the current main branch.
