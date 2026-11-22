# EduDSS release process (C1.2)

This is the operating procedure for building, verifying, promoting and rolling back an EduDSS release for a dedicated single-university deployment.

What has been verified so far is listed in `reports/final_acceptance/C1_2_RELEASE_ENGINEERING.md`. A step in this document is **designed** until that report shows evidence for it.

## 1. Release identity

Every build answers "what exactly is running?" through `dss/core/release.py`. The same answer is served at `GET :8081/version` and recorded in the release manifest.

| Field | Source | Example |
|---|---|---|
| `version` | `app/VERSION` (SemVer; release candidates use `-rc.N`) | `1.0.0-rc.1` |
| `git_sha` | build arg `EDUDSS_GIT_SHA` (`git rev-parse HEAD`; `+dirty` for a local tree with changes) | 40 hex chars |
| `build_time` | build arg `EDUDSS_BUILD_TIME` (UTC, ISO 8601) | `2026-09-27T00:00:00Z` |
| `image` | build arg `EDUDSS_IMAGE_REF` | `ghcr.io/<org>/edudss:1.0.0-rc.1` |
| `alembic_head` | migration graph shipped in the image (`dss/db/schema_contract.py`) | `["9f3a1c7d2e46"]` |
| `dependency_lock` | sha256 of `requirements.lock.txt` | `sha256:…` |
| `config_schema_version` | `CONFIG_SCHEMA_VERSION` (bump it when a required env var changes) | `2` |
| `rag_config_version` | hash of the embedding model, dimension, chunking and top-k | `ragcfg-…` |
| `ml.bundled_models` | none; models are trained per deployment | — |

The runtime state (`/version` → `runtime`) holds:

- the database revision, and whether it is `at_head`;
- the model IDs promoted to production in this deployment (`_production_index.json`);
- a fingerprint of the approved current RAG documents.

Version rules:

- A git tag must be `v<VERSION>`. The CD workflow refuses a mismatch.
- `1.0.0` without a suffix is published only after the first-customer acceptance.
- Never re-use a version for different content. Bump `-rc.N` instead.

## 2. Dependencies

| File | Owner | Content |
|---|---|---|
| `requirements.txt` | humans | the direct dependencies, deliberately chosen versions or ranges, with a comment explaining why |
| `requirements.lock.txt` | machine | the complete resolved environment of the production image (every transitive package, exact versions) plus the pip version |

- **Install**: `pip install -r requirements.txt -c requirements.lock.txt`, then `pip install --no-deps xgboost==<lock>`. The xgboost wheel otherwise pulls the GPU-only NCCL.
- **Build check**: the Dockerfile compares the installed set with the lock and **fails the build on any difference**. A newer PyPI release cannot silently enter an image.
- **Upgrading a dependency**:
  1. Edit `requirements.txt`.
  2. Run `python tools/lock_dependencies.py`. It resolves inside the pinned base image, never on a developer OS.
  3. Review the lock diff.
  4. Run `python tools/license_inventory.py` inside the new image to regenerate `THIRD_PARTY_NOTICES.md`.
  5. Run the release gate.
- **Checking the lock**: `python tools/lock_dependencies.py --check` reports whether a fresh resolution would differ. Run it before a release.
- **Base image**: pinned by digest in the Dockerfile (`python:3.11.16-slim-trixie@sha256:…`). Moving to a new digest (Debian security updates) is a deliberate change, reviewed like a dependency upgrade. Keep the same Python minor version unless a separate decision is made.

## 3. Supply-chain gates and severity policy

All of these tools are free.

| Gate | Tool | Blocking rule |
|---|---|---|
| Secrets | `tools/secret_scan.py --history` (tree, archives, every reachable commit) | any finding blocks. The finding prints path and provider only, never the value |
| Python dependency vulnerabilities | `pip-audit` on the lock | any known vulnerability blocks, unless it is listed as an accepted risk (`--ignore-vuln ID`) with a justification and an expiry in the release notes |
| Container vulnerabilities | Trivy (`HIGH,CRITICAL`) | **CRITICAL/HIGH with an available fix blocks.** Unfixed CRITICAL/HIGH findings are published in the evidence table and reviewed for each release (exploitability in this deployment, compensating controls). MEDIUM is reviewed at the base-image refresh. LOW is informational |
| Licenses | `tools/license_inventory.py --check` inside the image | AGPL/GPL/SSPL/proprietary block. LGPL/MPL/EPL/unknown need review and are allowed only when used unmodified as libraries. A stale `THIRD_PARTY_NOTICES.md` blocks |

`THIRD_PARTY_NOTICES.md` is an engineering inventory, not a legal opinion. Regenerate it in the production image:

```
docker run --rm <image> python tools/license_inventory.py --out /tmp/N.md && …
```

or inside any environment installed from the lock.

## 4. The release gate (one entrypoint)

```
python tools/release_gate.py                 # all mandatory + advisory gates
python tools/release_gate.py --no-advisory   # offline
python tools/release_gate.py --image edudss:1.0.0-rc.1   # reuse a built image
```

Each run starts a **throwaway** pgvector container with tmpfs storage, a random port and random passwords, and removes it at the end. It never touches a developer or production database.

Mandatory gates, in order:

1. secret scan
2. migrations: empty database → precheck → upgrade → contract verify → head→base→head roundtrip
3. full regression, including RLS as a non-superuser and real pgvector
4. real backup and restore
5. docker build: lock drift fails the build
6. licenses
7. container smoke:
   - no AI keys;
   - `/livez`, `/readyz` and `/version`;
   - non-root user;
   - no `.env` and no personal-data export in the image;
   - production mode is not ready without the pseudonym key and ready with it
8. manifest generated from the image and verified against `/version`

The advisory gates are `pip-audit` and Trivy. They need network access. When unreachable they report `UNAVAILABLE`.

**Exit code 0 only if every mandatory gate passes.** A JSON summary is written to `reports/release_gate/`.

CI (`.github/workflows/edudss-release-gate.yml`) runs the same gates as separate jobs. Browser E2E (Playwright) is its own job.

## 5. Artifact

- **One image per release**, built once by `.github/workflows/edudss-release.yml`.
- It is tagged `:<version>` and `:sha-<12>`, and pushed to GHCR.
- It is **deployed by digest** (`…@sha256:…`). `remote_deploy.sh` refuses a mutable reference.
- Staging and production run the byte-identical image. The server never builds (`docker-compose.prod.yml` has no `build:`).
- The release manifest (`tools/release_manifest.py generate`) records:
  - the release identity read from inside the image;
  - the image ID and repo digest;
  - the OCI labels;
  - the sha256 of the evidence files.

## 6. Pipeline (CD)

```
CI gates ─▶ build once ─▶ push (semver + sha tags) ─▶ digest
   ─▶ STAGING:     pull digest ─▶ migration precheck ─▶ migrate ─▶ verify ─▶ app ─▶ /readyz ─▶ manifest verify
   ─▶ APPROVAL:    GitHub environment "production" with required reviewers
   ─▶ PRODUCTION:  pre-deploy backup (verified) ─▶ precheck ─▶ migrate ─▶ verify ─▶ SAME digest ─▶ /readyz ─▶ manifest verify
```

Each environment needs these secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` and `DEPLOY_PATH`.

On the host, `DEPLOY_PATH` contains `deploy/production/` and a filled `production.env` with `chmod 600`.

Status: **NOT_VERIFIED.** No staging or production hosts exist yet.

### Khi nào được triển khai (bước 9, 22/11/2026)

Production chạy nhiều bản app sau Caddy (`docs/operations/SCALING.md`). Phiên Streamlit nằm trong bộ nhớ của một bản,
nên khi một bản khởi động lại, **người dùng trên bản đó phải đăng nhập lại** và mất phần đang nhập dở.

- Triển khai và khôi phục **ngoài giờ học**: sau 22:00 hoặc cuối tuần, theo lịch của trường. Không triển khai trong tuần thi.
- Không triển khai trong khoảng 02:00–03:30, vì sao lưu hằng ngày chạy lúc 02:30 (`edudss-backup.timer`).
- Báo trước cho giảng viên và CVHT ít nhất 1 ngày nếu bản mới có migration, vì nếu phải quay lại thì dữ liệu từ lúc
  sao lưu trước khi triển khai sẽ mất.
- Sửa lỗi bảo mật nghiêm trọng được triển khai ngay, kèm thông báo ngắn trên trang đăng nhập.

## 7. Migration safety

Tool: `python -m ops.migration_check status | precheck | verify | roundtrip`. It uses `DATABASE_URL` with the owner role.

- **precheck**:
  - OK when the database is empty or at an ancestor of the release head;
  - **refuses** when the database revision is unknown to the code (the database is ahead, or from another branch);
  - refuses when there are several heads in the database.
- **verify**: exact Alembic head, every metadata table present, and no unexpected tables.
- **readiness**: `/readyz` is 503 while the schema is not at the code's head. A new app on an old schema, or an old app on a new schema, never receives traffic.
- **roundtrip**: head → base → head. Allowed only on a disposable database (`--confirm-disposable-database`) and refused in production.
- **Downgrade assessment** (from `pending_revisions` / `_destructive_downgrade`):
  - every migration has a `downgrade()`;
  - all except the RLS-policy migration drop tables or columns, so **a downgrade destroys data**.
  - Production schema rollback is therefore **restore the pre-deploy backup** or a **forward fix**, never `alembic downgrade`.
- **Writing migrations for zero-surprise upgrades (expand/contract)**:
  - add nullable columns or new tables first;
  - deploy code that handles both shapes;
  - backfill;
  - drop old structures only in a later release.
  - Never rename or drop in the same release that stops using a structure.

## 8. Rollback design

| Layer | Rollback | Data loss | Precondition |
|---|---|---|---|
| **App** | re-run `remote_deploy.sh <previous digest>` (the previous digest is in `.release-history`) | none | the previous image is compatible with the current schema. It is compatible when the release had no migration. Otherwise also roll back the DB |
| **DB** | stop the app, then restore the verified pre-deploy backup into a new empty database with `python -m ops.backup_recovery restore --manifest …` (`RESTORE_DATABASE_URL`), then point `DB_NAME` at it or swap the names, then deploy the previous digest | writes since the backup are lost. Export them first if needed | the pre-deploy backup taken by `remote_backup.sh` with a verified checksum |
| **Config** | `production.env` is outside the image. Keep a dated copy before each change (`production.env.<date>`, chmod 600) and restore it, then `docker compose up -d app` | none | `config_schema_version` must match the image being run |
| **ML models** | models are trained per deployment. Re-promote the previous `training_id` in the model registry (`_production_index.json`, admin UI) | none | model artifacts are kept in the `appdata` volume, so back up that volume with the DB |
| **RAG index** | knowledge documents are versioned (`is_current`, approval workflow): revert to the previous document version, or re-index | none | when `rag_config_version` changes between releases (a new embedding model, dimension or chunking), a re-index is required. The index cannot be mixed across configurations |

**ROLLBACK status: NOT_VERIFIED.** No rollback drill has been executed on a deployed stack. The drill to run on staging before the first customer:

1. Deploy N.
2. Deploy N+1 with a migration.
3. Restore the pre-deploy backup and deploy N.
4. Confirm `/readyz` = 200 and the manifest of N verifies.

## 9. Staging contract

- **Production-like**:
  - the same `docker-compose.prod.yml`, Caddy, internal backend network and non-superuser app role;
  - `EDUDSS_ENV=production`;
  - the same image digest as the one to be promoted.
- **Synthetic data only**: never a copy of production data. Personal data must not leave production.
- **Non-production credentials**:
  - its own database passwords;
  - its own `EDUDSS_PSEUDONYM_KEY`;
  - its own SSH key and GitHub environment secrets;
  - AI providers are either absent or separate test keys with spending limits.
- **Separate host or VM**: never share a Docker daemon or database with production.
- **Reset**: staging data can be destroyed at any time. The migration roundtrip runs only here or in CI.

## 10. Backups

- The pre-deploy backup is mandatory before any production migration (`remote_backup.sh`).
- The manifest format is identical to `ops/backup_recovery.py`, so `verify` and `restore` work on it.
- Routine backups, retention and restore drills: see `BACKUP_RECOVERY_RUNBOOK.md`.
- **DB_BACKUP** and **DB_RESTORE** are verified (C1.2 report).
- **Volume restore** (DB + `appdata` from a daily backup, one command `deploy/production/restore_daily.sh`) is verified
  on the dev machine with the production image (22/11/2026, see `BACKUP_RECOVERY_RUNBOOK.md`).
- **FULL_DR** (rebuilding a new host, off-site copy, TLS, DNS) is **not verified**: no pilot host yet, and backups
  are not copied off the host (owner decision 22/11/2026).

## 11. Cold start

Measured on Windows 11 with Docker Desktop (WSL2) only. Linux hosts are not measured. See the C1.2 report for the numbers.

- The first container created from a freshly built multi-GB image can take minutes before the Python process runs. Docker Desktop unpacks and snapshots the layers, which is outside the application's control.
- The first UI session additionally pays for the heavy imports and the first model or embedding load.
- `/livez` becomes 200 when Streamlit serves. `/readyz` reflects the dependencies, not the model warm-up.
- The compose `start_period` (120 s) covers a normal start. Operators must wait for `/readyz`, not for a fixed sleep.
