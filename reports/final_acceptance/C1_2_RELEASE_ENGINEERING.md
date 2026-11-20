# C1.2 — Release Engineering Acceptance

Evidence date: 2026-09-28 · Host: Windows 11 + Docker Desktop (Server 29.8.0, containerd snapshotter, data root relocated to `E:\DockerBackup\DockerDesktopWSL`) · Worktree `D:\KLTN\edudss-final-candidate-v2`, branch `fix/ml-correctness`, HEAD `e2241bfd7a1e4f7363047230eddf68e68cb802e7` (dirty; nothing committed, merged or pushed).

## Status summary

```
C1_2_STATUS                   = BLOCKED
MANDATORY_RELEASE_GATE        = NOT RUN (final RC image not successfully produced)
REGRESSION                    = NOT RUN on final image (release gate not reached)
BACKUP_RESTORE                = NOT RUN in this session (last PASS: release-gate-20260927T151155Z, previous image)
LICENSE_GATE                  = PASS at source (notices regenerated, BLOCKED: none; 4 REVIEW incl. streamlit-shap UNKNOWN) — gate on final image NOT RUN
CONTAINER_SMOKE               = PASS on edudss:torch210-experimental (dev mode); NOT RUN on final RC image
DEPENDENCY_AUDIT              = NOT RUN (advisory)
SCOUT_CRITICAL                = 0 (edudss:torch210-experimental)
SCOUT_HIGH                    = 6 (edudss:torch210-experimental); expected 3 on final image after pip removal — NOT VERIFIED
TORCH_VERSION                 = 2.10.0+cpu (adopted)
CPU_ONLY                      = YES (verified in container + build-time lock assertion)
RAG_384D                      = YES (verified in container)
PERSONAL_DATA_IN_GIT_HISTORY  = YES
KEY_ROTATION_REQUIRED         = YES
HOSTED_CI                     = NOT_VERIFIED
LIVE_PUBLIC_TLS               = NOT_VERIFIED
SAFE_TO_PROCEED_TO_FINAL_C1_3 = NO (until the final RC image passes the mandatory gate)
```

**Exact blocker:** the final RC build (`docker build -t edudss:1.0.0-rc.1-c12final-e2241bfd7a1e-dirty .`, production Dockerfile) completed every build step — including `Dependency lock verified: 122 packages match; CPU-only torch 2.10.0+cpu` — but failed while Docker Desktop unpacked the exported image into the containerd snapshotter:
`failed to extract layer sha256:8425ff86b485…: failed to Lchown ".../snapshots/386/fs/opt/edudss-venv/lib/python3.11/site-packages/fontTools/feaLib/lexer.c" for UID 0, GID 0: no such file or directory` (build exit 1 after 14,912 s; layer export alone took 4,315 s). This is a Docker Desktop storage/snapshotter failure on the relocated data root, not a Dockerfile or dependency error. In addition, the command-safety check of the agent environment stopped returning verdicts at this point, so the image could not be inspected, rebuilt, scanned, or passed to the release gate in this session.

**Closure attempt (resumed session):** the first required step (`docker info` / `docker system df` / `docker image inspect <final tag>`) could not be executed — the agent environment's command-safety check returned no verdict for every shell/PowerShell command (4 consecutive attempts), so no Docker state was read, no rebuild was started, and no gate was run. No results below were inferred; status remains BLOCKED on the unproduced final image.

**To finish (commands, in order):**
1. `docker image inspect edudss:1.0.0-rc.1-c12final-e2241bfd7a1e-dirty` — if missing/incomplete, restart Docker Desktop and rebuild the same tag from `app/` (build cache makes the dependency stages fast; export is the slow part).
2. Verify the image (Python 3.11, torch 2.10.0+cpu, CUDA False, no nvidia/triton, no pip, uid 999, 384-d embedding, `/livez` `/readyz` `/version` = 200, no `dữ liệu/`, `.env`, `reports/`).
3. `docker scout cves <image> --only-severity critical,high` (set `TMP`/`TEMP`/`DOCKER_SCOUT_CACHE_DIR` to E: — C: has ~5–8 GB free and an earlier Scout run failed with "There is not enough space on the disk").
4. `python tools/release_gate.py --image <image>` and record each mandatory gate.

Residual-finding classification prepared from the experimental image's actual Scout output:

| Finding | Package | Class | Final-image expectation |
|---|---|---|---|
| GHSA-6v7p-g79w-8964, CVE-2026-57585 | msgpack 1.1.2 (pip vendored, `pip/_vendor/bom.cdx.json`) | VENDORED_BUILD_TOOL | removed with pip (to be verified) |
| CVE-2025-47273 | setuptools 70.3.0 (pip vendored SBOM entry) | VENDORED_BUILD_TOOL | removed with pip (to be verified) |
| CVE-2026-4538 | torch 2.10.0+cpu | RUNTIME_UNFIXED | remains; no upstream fix |
| CVE-2026-85091 | zlib (Debian trixie) | BASE_IMAGE_UNFIXED | remains; "not fixed" in Debian |
| CVE-2026-82560 | perl-base (Debian trixie) | BASE_IMAGE_UNFIXED | remains; "not fixed" in Debian |

## 1. Torch 2.10 container experiment

Image `edudss:torch210-experimental` (`sha256:7018705f6732…`, 3.71 GB), built from `docker/experimental/Dockerfile.torch210-experimental` (current multi-stage structure; only torch overridden to `2.10.0+cpu` from the PyTorch CPU index). Verified **inside the container**:

| Check | Result |
|---|---|
| Python | 3.11.16 |
| torch | 2.10.0+cpu |
| `torch.cuda.is_available()` | False |
| `torch.version.cuda` | None |
| nvidia-* / triton distributions | none |
| transformers / sentence-transformers | 5.10.4 / 5.3.0 |
| all-MiniLM-L6-v2 load + encode | PASS, embedding shape (1, 384) |
| user | `edudss` (uid 999) |
| `/livez` `/readyz` `/version` | 200 / 200 / 200 (dev mode, no DB: PostgreSQL/pgvector/AI `not_configured`, not required) |
| installed set vs `requirements.lock.txt` | identical except `torch` (2.9.1+cpu → 2.10.0+cpu) |

Docker Scout (`docker scout cves … --only-severity critical,high`, actual results, not inferred):

| Image | CRITICAL | HIGH | HIGH findings |
|---|---|---|---|
| `edudss:c121-multistage-test` (baseline, torch 2.9.1+cpu) | 0 | 7 | msgpack 1.1.2 ×2 (GHSA-6v7p-g79w-8964, CVE-2026-57585), torch 2.9.1+cpu ×2 (CVE-2026-24747, CVE-2026-4538), setuptools 70.3.0 (CVE-2025-47273), zlib (CVE-2026-85091), perl (CVE-2026-82560) |
| `edudss:torch210-experimental` | 0 | 6 | same as baseline **minus CVE-2026-24747**; no new HIGH/CRITICAL |

Scout SARIF locations: msgpack and setuptools 70.3.0 are reported from `/opt/edudss-venv/lib/python3.11/site-packages/pip/_vendor/bom.cdx.json` (pip's vendored-component SBOM — not application packages; `import msgpack` fails in the image); torch from `torch-2.10.0+cpu.dist-info/METADATA`; zlib/perl from dpkg status (Debian base).

## 2. Torch decision — **ADOPT torch 2.10.0+cpu**

All adoption criteria met: container compatibility PASS, CPU-only PASS, RAG embedding 384-d PASS, probes PASS, CVE-2026-24747 removed, no regression / no new HIGH. Not upgraded beyond 2.10.0 (no evidence-based reason).
Residual: **CVE-2026-4538** affects torch ≤ 2.10.0 and has no upstream fix → documented risk (RUNTIME_UNFIXED).

## 3. Dependencies

- `requirements.txt`: UTF-8 BOM removed and a UTF-8→cp1252 double-encoding (“—” rendered as `â€”` in 16 places) repaired losslessly; `torch==2.10.0+cpu` with rationale comment. Other version bumps in that file were already present from the earlier C1.2.1 remediation and are unchanged.
- `requirements.lock.txt`: only `torch==2.9.1+cpu → 2.10.0+cpu`. The lock was **not** re-resolved from scratch because `tools/lock_dependencies.py` re-resolves `requirements.txt` without constraints (transitive versions would float); instead the change was proven by the production `Dockerfile`'s own lock-drift assertion: build log `Dependency lock verified: 122 packages match; CPU-only torch 2.10.0+cpu`.
- CPU-only preserved (no nvidia-*/triton anywhere in the lock or the image); xgboost still installed `--no-deps`.
- msgpack / jaraco-context were **not** added as application dependencies.
- Multi-stage build kept (builder resolves + verifies, runtime copies only `/opt/edudss-venv`).
- **Runtime hardening:** `pip` is removed from the runtime stage (venv and base interpreter). Nothing in the application invokes pip at runtime (only user-facing hint strings mention `pip install`); pip's vendored components were the source of 3 of the 6 HIGH findings. This is removal of an unused build tool from an immutable image, not a scanner suppression.
- `.dockerignore`: added `.venv*`, `venv*/`, `tmp_license/`. Finding: the experimental virtualenv `app/.venv_torch210_experimental` was **not** excluded (only `.venv` was); verified afterwards that `/app` in the built image is 15 MB with no venv. (Docker Desktop still walks the excluded 1.8 GB directory on the Windows filesystem during context transfer, which makes builds slow; image content is unaffected.)

## 4. Third-party notices

Regenerated with `tools/license_inventory.py` **inside** `edudss:torch210-experimental` (installed distributions == final lock) with the final lock mounted: 122 packages, **BLOCKED: none**. REVIEW (weak copyleft / unknown metadata, used unmodified as libraries): certifi (MPL-2.0), psycopg2-binary (LGPL with exceptions), tqdm (MPL-2.0 AND MIT), **streamlit-shap (license metadata UNKNOWN — needs manual legal review)**. Lock coverage verified by `test_third_party_notices_cover_the_lock`.

## 5. Targeted C1.2 validation

`python -m pytest -q -p no:cacheprovider tests/test_c12_release_engineering.py` → **26 passed, 0 failed** (527.97 s). The two previous failures were fixed at the source (BOM, stale notices). The only test edit is the torch version pin in `test_lock_is_fully_pinned_and_cpu_only` (`2.9.1+cpu` → `2.10.0+cpu`); the CPU-only / no-nvidia / exact-pin / lock-coverage assertions are unchanged.

## 6. Final RC image — NOT PRODUCED (see Status summary for the exact blocker)

## 7. Release gate — NOT RUN (prerequisite image missing). Prior history, for context only: `release-gate-20260927T124847Z.json` / `…130544Z.json` passed all mandatory gates on the older `edudss:1.0.0-rc.1-e2241bfd7a1e-dirty` (torch 2.9.1+cpu, stale notices at that time); `…151155Z.json` on `edudss:c121-dependency-test` failed `regression` and `licenses` — the two causes fixed in this session.

## Not claimed

- FULL_DR: not verified (only database backup/restore is exercised by the gate).
- HOSTED_CI: NOT_VERIFIED (no hosted CI run exists for this state).
- LIVE_PUBLIC_TLS: NOT_VERIFIED (no real domain was tested).
- PERSONAL_DATA_IN_GIT_HISTORY = YES (history not rewritten; see `docs/operations/PERSONAL_DATA_HISTORY_REMEDIATION_PLAN.md`).
- KEY_ROTATION_REQUIRED = YES (no user confirmation of external key revocation).
