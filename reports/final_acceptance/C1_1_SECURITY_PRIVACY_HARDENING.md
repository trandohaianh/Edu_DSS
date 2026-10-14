# C1.1: P0 data cleanup, security and privacy foundation

| | |
|---|---|
| Worktree | `D:\KLTN\edudss-final-candidate-v2` |
| Branch | `fix/ml-correctness` |
| Starting HEAD | `e2241bfd7a1e4f7363047230eddf68e68cb802e7` |
| Ending HEAD | `e2241bfd7a1e4f7363047230eddf68e68cb802e7` (no commit, merge or push; all changes are uncommitted working-tree edits) |
| Not implemented, as instructed | Redis, Kafka, Celery, Kubernetes, HNSW, new embedding models, SVM/KNN/NN, SaaS runtime tenancy |

## Status summary

| Item | Status |
|---|---|
| `PERSONAL_DATA_FILE_IN_RELEASE` | **NO**. The file and its dataset metadata were removed from the working tree; a regression guard was added. |
| `PERSONAL_DATA_IN_DOCKER_IMAGE` | **NO**. Verified in a freshly built image: `dữ liệu/` absent, 0 `*nhanvien*` files, 0 files containing the employee header. |
| `PERSONAL_DATA_IN_GIT_HISTORY` | **YES**. History was *not* rewritten (see §2). |
| `PRODUCTION_DEMO_CREDENTIALS` | **DISABLED**. Verified by test and live through the TLS proxy. |
| `PRODUCTION_AUTO_LOGIN` | **DISABLED**. Verified by test and live (`SV001/SV001123` rejected). |
| `PRODUCTION_DEMO_AI` | **DISABLED** via the canonical switch (the existing gateway and advisor gates now delegate to it). |
| `PSEUDONYMIZATION` | **KEYED HMAC-SHA256, per university, 100 bits, fail-closed in production.** |
| `EXTERNAL_AI_PII_MINIMIZATION` | **IMPLEMENTED + TESTED**. No identifier, band-only GPA, bracketed attendance, generalized subject scores, sanitized free text. |
| `DATA_EXPORT` | **IMPLEMENTED** (service level, PostgreSQL, tenant-scoped). Tested on real PostgreSQL. |
| `DATA_DELETION` | **IMPLEMENTED**: delete / anonymize / redact / retain by category. Tested on real PostgreSQL. |
| `RETENTION_POLICY` | **REPRESENTED + ENFORCEABLE** (`purge_expired`). Defaults can be overridden per deployment. |
| `POSTGRES_PRODUCTION_EXPOSURE` | **NONE**. No published port; internal network. Verified live (host:5432 unreachable). |
| `REVERSE_PROXY_CONFIG` | **CONFIGURATION_IMPLEMENTED + EXERCISED LOCALLY** (Caddy). |
| `TLS_CONFIG` | **CONFIGURATION_IMPLEMENTED**. Exercised locally with Caddy's internal CA: TLS 1.3, HTTP→HTTPS 308, HSTS, CSP and other headers present. |
| `LIVE_TLS_VERIFIED` | **NO**. No public domain or DNS here, so no public ACME certificate has been issued. |
| `SECRET_SCAN` | **PASS**. Worktree pattern scan 0 findings; `tools/security_scan.py` PASS; history and index 0 key-pattern matches. |
| `KEY_ROTATION_REQUIRED` | **YES**. The OpenAI/Gemini/Groq keys exposed earlier (in the `D:\KLTN\code` worktree) must still be rotated by the owner. |

---

## 1. Files changed

**Modified**
- `app/.dockerignore`: excludes `dữ liệu/`, `reports/`, `docs/`, the UI reference kits, office files and `deploy/`.
- `app/.gitignore`: ignores filled `deploy/**/*.env` and `data_warehouse/security/`.
- `app/Dockerfile`: creates `/app/data_warehouse` and `/app/uploads` before `chown`, so named volumes are owned by the non-root user.
- `app/docker-compose.yml`: every published dev port binds to `127.0.0.1` by default (`DB_BIND_ADDR` / `EDUDSS_BIND_ADDR` override).
- `app/dss/core/data_helpers.py`: `is_production_environment()` now delegates to the canonical switch.
- `app/dss/core/health_diagnostics.py`: new `privacy_key` readiness check, required in production.
- `app/dss/core/models.py`: the approved-documents-only knowledge filter also applies under `EDUDSS_ENV=production`.
- `app/dss/core/trainers.py`: **bug fix**. Training on the legacy target alias `final_score` crashed with `KeyError` when both alias and canonical columns existed.
- `app/dss/main.py`, `app/dss/tabs/warehouse_tab.py`: synthetic data and simulated LMS events are gated by the canonical switch.
- `app/dss/services/auth_service.py`:
  - canonical gating for demo seed, auto-provision and the demo box;
  - versioned PBKDF2 (600k) with upgrade on login;
  - persistent lockout.
- `app/dss/services/privacy_service.py`:
  - keyed pseudonyms;
  - minimized provider context: band-only GPA, attendance bracket, no identifier, generalized scores;
  - `build_quick_question_prompt`.
- `app/dss/services/career_ai_advisor.py`: no pseudonym, GPA band, domain strength bands, sanitized evidence.
- `app/dss/services/context_builder.py`: student-ID fields added to the Agent's forbidden set.
- `app/dss/tabs/home.py`:
  - quick-ask no longer sends the raw student ID or exact score;
  - no raw exception text;
  - metric card wording qualified.
- `app/dss/tabs/dashboard.py`, `app/dss/tabs/ui_kit.py`: R² is no longer shown as a percentage "accuracy"; the data source is stated; "risk" is labelled as a relative ranking.
- `app/dss/tabs/ml_hub.py`: uncalibrated probabilities are no longer interpreted as "khá ổn định".
- `app/reports/production_readiness/METRICS_THESIS_VS_CURRENT.md`: a dated **addendum** was appended; the historical table is unchanged.
- Tests updated to the stricter contract:
  - `app/tests/test_lms_ai_rag_gateway.py` (a pseudonym must *not* be in the provider context);
  - `app/tests/test_production_demo_policy.py` (gates checked at the canonical switch, plus a new `EDUDSS_ENV=production` check).
- `app/tests/test_ml_hub_ranking_consistency.py`: pre-existing user edit, untouched.

**Deleted (working tree only; still in git history, see §2)**
- `app/dữ liệu/nhanvien_export.csv`
- `app/data_warehouse/metadata/f0ce1f1adb6f_data.json` (dataset metadata for that file; column names only)

**Added**
- `app/dss/core/runtime_mode.py`: canonical environment contract.
- `app/dss/security/pseudonymization.py`: keyed tenant-scoped HMAC pseudonyms.
- `app/dss/security/login_throttle.py`: persistent, cross-process lockout store.
- `app/dss/services/data_lifecycle.py`: export, erasure/anonymization, retention.
- `app/deploy/production/docker-compose.prod.yml`, `Caddyfile`, `production.env.example`.
- Tests:
  - `app/tests/test_c1_release_data_hygiene.py`
  - `test_c1_ml_leakage_regression.py`
  - `test_c1_production_mode_and_auth.py`
  - `test_c1_pseudonymization_and_payload.py`
  - `test_c1_data_lifecycle.py`
  - `test_c1_production_network_config.py`
- `app/reports/final_acceptance/evidence/c1_1/c1_prod_login_via_tls_proxy.png`

---

## 2. P0: `nhanvien_export.csv`

| Question | Finding (no personal values printed anywhere) |
|---|---|
| Tracked? | Yes, since the initial commit (`8f6edf6`, 2026-08-20) |
| Records | 4 |
| Personal-data categories | full name, employee code, national ID number, age, date of birth, gender, phone, home address, department, position, salary, allowance, deduction, job satisfaction, overtime, tenure, education, commute distance |
| Referenced by | only `data_warehouse/metadata/f0ce1f1adb6f_data.json` (dataset registry entry: column names and types, no values) |
| Runtime needs it? | No. No source, test or config reads `dữ liệu/`. |
| Tests depend on it? | No. A test fixture was **not** needed; no personal content was copied anywhere. |
| Shipped in Docker image? | **Yes, before C1.1.** `.dockerignore` did not exclude `dữ liệu/`. **No after C1.1** (verified in a freshly built image). |
| Git history | The CSV is present in **193 commits** (paths `app/dữ liệu/…` and `dữ liệu/…`). A **full data copy** `data_warehouse/raw_data/f0ce1f1adb6f.csv` exists in 7 commits: `41e4622 5ad4d93 711d834 8f6edf6 e7b0ae5 ec961f4 fe3721a`. The metadata file is in 193 commits. 31 branches contain the initial commit. |

`PERSONAL_DATA_IN_GIT_HISTORY = YES`. History was **not** rewritten.

Owner decision required before any distribution of the repository or its history:
1. Establish whether the records are real people.
2. If they are, purge them from history (for example `git filter-repo --path "app/dữ liệu/nhanvien_export.csv" --path "dữ liệu/nhanvien_export.csv" --path-glob "*raw_data/f0ce1f1adb6f.csv" --invert-paths`) on a fresh clone, force-update every ref, rotate clones, and treat any published copies (images built before C1.1, shared archives) as exposed.

**Prevention:**
- `tests/test_c1_release_data_hygiene.py` fails if any CSV or dataset metadata in the release tree has three or more personal-data headers (it checks headers only).
- The image build context excludes `dữ liệu/`, `reports/`, `docs/`, the UI kits and office files.

---

## 3. P0: commercial ML claim safety

| Location | Classification | Action |
|---|---|---|
| `reports/production_readiness/METRICS_THESIS_VS_CURRENT.md`, `FINAL_LIVE_SIMULATION_RESULT.md`, `FINAL_REALISTIC_STAGING_SIMULATION.md` | THESIS_HISTORICAL_RESULT / INTERNAL_TEST_EVIDENCE | Not rewritten. An addendum was **appended** to `METRICS_THESIS_VS_CURRENT.md`: synthetic `sample_data_v1`, 132 training rows, leaky `xep_loai` feature, not a commercial claim, plus safe wording. |
| `reports/ml_correctness/{baseline,after}_metrics.txt`, `REPORT.md`, `COMMERCIAL_RELEASE_READINESS.md` | INTERNAL_TEST_EVIDENCE (already labelled synthetic) | unchanged |
| `ui_reference/`, `EduDSS_UI_Reference_Kit/` ("Độ chính xác mô hình 0.875" mock) | DEMO_RESULT (design mock) | excluded from the image |
| Thesis `.docx` in repo root (user-owned, untracked) | THESIS_HISTORICAL_RESULT | untouched |
| **Runtime UI**: lecturer home + Dashboard metric card | was effectively a COMMERCIAL_CLAIM: R² rendered as "99.29%" under "Độ chính xác mô hình hiện tại" | **Fixed.** Label "R² (tập kiểm tra)", value `0.993`, caption "Đo trên dữ liệu MÔ PHỎNG — không phải độ chính xác đã kiểm chứng trên sinh viên thật" (or "chưa phải kiểm định độc lập" for uploaded data). |
| Runtime UI: "Sinh viên có nguy cơ" count | implied absolute risk | Caption: "Nhóm 25% có điểm dự đoán thấp nhất lớp (xếp hạng tương đối, không phải xác suất)" |
| Runtime UI: prediction page (≥0.8 → "tín hiệu khá ổn định") | interpreted uncalibrated scores | Replaced by neutral wording |
| README / `dss/` source | no metric claims found | – |

**Leakage in current training:**
- The `get_leaky_target_columns`/`filter_leakage_features` guard was already applied in both trainers. `tests/test_c1_ml_leakage_regression.py` proves through the **real trainers** that `xep_loai`, `grade`, `diem_ky_sau` and `final_score` never reach the fitted model when offered as features (targets `diem_ky_sau`, `final_score`, `xep_loai`).
- That test **found a real bug**: training on target `final_score` crashed with `KeyError` when the dataset also had `diem_ky_sau` (the alias was canonicalized away). Fixed by resolving the target through `COLUMN_ALIASES`.
- No metric was optimized.

---

## 4–6. One production switch, demo credentials, authentication

**Environment contract** (`dss/core/runtime_mode.py`):
- `EDUDSS_ENV = development | test | production` (default development). An **unknown value fails closed** as production.
- `EDUDSS_MODE=REAL_LMS` also implies production (backward compatible). `EDUDSS_MODE` otherwise keeps its data/offline meaning.
- Development-only opt-ins, ignored in production:
  - `EDUDSS_SHOW_DEMO_CREDENTIALS=1` (default off);
  - `EDUDSS_ALLOW_STUDENT_AUTOPROVISION=0` to disable auto-provisioning in development (default on).

| Shortcut | Before | After (production) |
|---|---|---|
| Demo credentials on login page | always rendered | never; in development only with an explicit opt-in |
| Student `<code>/<code>123` auto-provision + login | blocked only when `EDUDSS_MODE=REAL_LMS` | blocked when `EDUDSS_ENV=production` **or** REAL_LMS |
| Demo account seeding | env OR mode | canonical |
| Synthetic sample data / simulated LMS events | literal `REAL_LMS` checks | canonical |
| Demo AI answers | `is_production_environment()` (REAL_LMS only) | same call, now canonical |
| Unapproved KB documents | filtered only in REAL_LMS | filtered in any production |

**Authentication:**
- Passwords: PBKDF2-HMAC-SHA256 at **600,000** iterations in a self-describing format (`pbkdf2_sha256$600000$…`, 85 chars, fits the column). Legacy 200k hex hashes still verify and are **re-hashed on the next successful login** (JSON and PostgreSQL identity stores).
- Lockout: 5 failures / 15 min, now stored in `<data_root>/security/login_throttle.json` under an OS file lock. It survives restarts and is shared by all processes on the host, and it stores only a SHA-256 of the username.
- **Documented limitation:** replicas on *different* hosts don't share it. Multi-host deployments need the same contract on PostgreSQL. That is out of scope for the dedicated single-host first customer, and Redis was not introduced.
- Sessions: unchanged (Streamlit per-connection session). Idle timeout is still P2.

---

## 7. Pseudonymization

```
tenant_key = HMAC-SHA256(EDUDSS_PSEUDONYM_KEY, "edudss/pseudonym/v{EDUDSS_PSEUDONYM_KEY_VERSION}/org/{organization_id}")
pseudonym  = "Student_" + base32(HMAC-SHA256(tenant_key, UPPER(TRIM(student_id))))[:20]      # 100 bits
```

- The key is never in source, never logged, and never in readiness output (tested).
- Production without a key raises `PseudonymKeyMissing`, and readiness reports `privacy_key: not_configured, required: true` → `not_ready`. The deployment Compose also refuses to start without it.
- Development uses a random key generated once under `<data_root>/security/` (git-ignored, never in source), stable across restarts.
- The pseudonym is computed **inside** EduDSS. It is no longer sent to AI providers at all, and the raw ID never was needed for it.
- **Rotation:** set a new key and increment `EDUDSS_PSEUDONYM_KEY_VERSION`. Pseudonyms change, so pseudonym-keyed rows (`ai_token_usage.user_id`, `cms_student_interactions.student_pseudonym`, learning-explainer JSON records) must be re-keyed by a one-off job computing old→new while both keys are available, or left to expire under retention. Rows created **before C1.1** used the old public-salt scheme and are not linked to new pseudonyms. This is acceptable because no customer data exists yet.

## 8. External AI data minimization

| Field | Internal | External provider payload (after C1.1) |
|---|---|---|
| Name, email, phone, address, DOB | DB / LMS | **never** |
| Student ID / code, username | DB | **never** (regex-masked if typed in free text) |
| Pseudonym | internal audit metadata | **not sent** (was sent before) |
| GPA | exact | **band only** (was "band (~7.3)") |
| Subject scores vs class | exact | **qualitative gap** ("thấp hơn TB lớp một chút / nhiều") |
| Career domain scores / GPA | exact | **strength bands** ("mạnh / khá / cần cải thiện"), GPA band |
| Attendance | exact rate | **bracket** (≥90% / 75–90% / <75%) |
| Risk level | category | category |
| Free text (progress note, chat history, weaknesses, career evidence, quick question) | raw | regex-sanitized (email, phone, student ID, self-disclosed name). No NER: an arbitrary name written mid-sentence can still pass (documented limitation). |
| Dashboard quick-ask | – | **was sending the raw student ID and exact score**; now uses `build_quick_question_prompt` |
| Agent context builder | – | forbidden set now also includes `student_id`, `student_code`, `mssv`, `id_card`, `national_id`, `username` |

Also fixed: a missing prediction used to be banded as "Cần cải thiện (GPA < 5.5)"; it is now "Chưa có dự đoán".

## 9. Data lifecycle (`dss/services/data_lifecycle.py`, PostgreSQL, tenant-scoped via RLS session)

| Category | Tables | On erasure request | Default retention |
|---|---|---|---|
| ACADEMIC_RECORD | academic_records, grades, attendance, enrollments, submissions, learning_activities | **RETAIN** (legal/academic record), linked to the anonymized student | institution policy (never auto-purged) |
| IDENTITY | students, users | **ANONYMIZE**: name → placeholder, external ID/email/student ID cleared, code/username → `erased-<pseudonym>`, account disabled, credential unusable | – |
| AI_CONVERSATION | consultations, cms_student_interactions | **DELETE** | 365 d |
| DERIVED_ANALYTICS | predictions, recommendations | **DELETE** | 365 d |
| AUDIT | audit_logs, activity_logs | **REDACT** personal content, keep rows | 1825 d |
| AI_USAGE | ai_token_usage (pseudonymous) | RETAIN | 400 d |

- `export_student_data`: all categories as JSON, with the retention policy. Password hash and salt are excluded.
- `erase_student_data`: one transaction. It writes an audit event holding **counts only**, with no name, email or code (tested).
- `purge_expired`: time-based retention; overrides via `EDUDSS_RETENTION_<CATEGORY>_DAYS`.
- Uploaded course documents are not student personal data and are governed by the existing document approval and retirement workflow.

Known limits:
- The next LMS/SIS sync can re-create an erased student unless the erasure is mirrored upstream.
- Backups keep erased data until they expire.
- Local JSON/demo stores are out of scope.
- There is no UI yet (service level only). An admin UI belongs to a later phase.

## 10–11. Network boundary, reverse proxy, TLS

**Development** (`docker-compose.yml`): published ports bind to `127.0.0.1` unless `DB_BIND_ADDR`/`EDUDSS_BIND_ADDR` are set explicitly.

**Production** (`deploy/production/`):

```
Internet ─443/80─▶ proxy (Caddy) ──edge──▶ app (EDUDSS_ENV=production, no published port)
                                              └─backend (internal: true)─▶ postgres (no published port)
migrate (owner role, one-shot) ─backend─▶ postgres        app connects as non-superuser → RLS enforced
```

Live local exercise (`EDUDSS_DOMAIN=localhost`, Caddy internal CA, throwaway secrets generated and deleted):

| Check | Result |
|---|---|
| `docker compose config` | only proxy publishes 80/443; postgres, app and migrate publish none; `backend` internal |
| host → 127.0.0.1:5432 | **not reachable** |
| migrate job | completed; app role `edudss_app` is non-superuser (`rolsuper = f`) |
| app readiness (inside) | `ready`; PostgreSQL ready; pgvector ready; `privacy_key: ready, required: true`; production = true; demo credentials visible = false; auto-provision = false |
| HTTP | `308 → https://localhost/` |
| HTTPS | TLS 1.3; `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` present; `Server` header removed |
| Browser via proxy | WebSocket `wss://localhost/_stcore/stream` works under CSP; **0 CSP violations** after disabling Streamlit usage stats; no developer toolbar; **no demo credentials rendered**; **`SV001/SV001123` rejected**. Screenshot in `evidence/c1_1/`. |

**Defects found by the live exercise and fixed:**
1. An empty `email {$ACME_EMAIL}` made Caddy crash-loop.
2. `trusted_proxies private_ranges` would have trusted spoofed `X-Forwarded-*` from any campus-LAN client. Removed: Caddy is the edge.
3. Streamlit usage telemetry to `data.streamlit.io` and the developer toolbar were enabled. Both are now disabled in the production environment.

Observation (P2): after a container is **created**, the first page render on this Windows/Docker Desktop host took 60–240+ s, versus 12 s after a restart and 3 s warm, even though the healthcheck was already green. Re-measure on the target Linux host and add a warm-up/readiness probe that performs a first render.

`LIVE_TLS_VERIFIED = NO` until a real domain points at a real host and Caddy obtains a public certificate. Acceptance test for that: `curl -I https://<domain>` without `-k` succeeds, SSL Labs grade ≥ A, auto-renewal is visible in Caddy logs.

## 12. Secrets
- Worktree pattern scan (tracked, untracked, ignored, zip members): **0 findings**.
- `tools/security_scan.py`: **PASS**.
- Git history + index key-pattern scan: **0 matches**.
- No secret was printed during this phase. The production env file used for the live test was generated in the scratchpad, never displayed, and deleted with the stack (`down -v`).
- `KEY_ROTATION_REQUIRED = YES`: the OpenAI/Gemini/Groq keys exposed in the other worktree still need rotation by the owner.

---

## 13. Tests

**New targeted tests (all pass):**

| File | Tests | Notes |
|---|---|---|
| `test_c1_release_data_hygiene.py` | 4 | headers only |
| `test_c1_ml_leakage_regression.py` | 4 | real trainers |
| `test_c1_production_mode_and_auth.py` | 22 | includes Streamlit `AppTest` renders of the login page in production vs development |
| `test_c1_pseudonymization_and_payload.py` | 21 | |
| `test_c1_production_network_config.py` | 6 | |
| `test_c1_data_lifecycle.py` | 6 | 4 run on **real PostgreSQL 16 + pgvector** (Alembic head `9f3a1c7d2e46`) |

**Full regression:** run on real PostgreSQL 16 + pgvector (throwaway container, Alembic `9f3a1c7d2e46`) with a non-superuser app role for the RLS suite, `EDUDSS_SKIP_DOTENV=1`, E2E excluded.

**1,125 passed, 0 failed, 46 skipped**, 356.32 s.

Skip reasons, enumerated with `-rs`:

| Count | Reason |
|---|---|
| 34 | Workstream B/C/D, onboarding and A+B suites that need their own dedicated PostgreSQL URL sets (not provided in this run) |
| 7 | live staging / final-candidate stack URLs |
| 3 | xgboost not installed in the local venv (it is installed in the image) |
| 1 | Phase 13 dedicated restore URLs |
| 1 | local `app/.env` test |

The first full run (before updating the tests to the new contract) had 4 failures. All four were tests pinned to the *old* behaviour: a pseudonym expected in the provider context, and three source-order checks for the literal `REAL_LMS` gate. They were updated to the stricter canonical contract, and one extra test was added for `EDUDSS_ENV=production`. Baseline before C1.1 on the same branch: 943 passed locally without PostgreSQL; 1,063 passed on PostgreSQL in the audit.

## 14. Remaining issues

**P0**
- Personal data in git history (193 commits + 7 commits with a raw copy). Needs an owner decision; history was not rewritten.
- Images built before C1.1 contained the file; treat them as exposed.
- `KEY_ROTATION_REQUIRED = YES` (external).

**P1** (unchanged from the commercial audit unless noted)
- Real-data ML validation; calibration or no percentages; absolute (regulation-based) risk thresholds.
- Real LMS/SIS connector; scheduled incremental sync.
- Regulation store in PostgreSQL + approval workflow.
- **CI:** stale schema/head asserts in the workflow and the backup test; no hosted run; no CD; no release versioning.
- Alerting / HTTP readiness endpoint; combined DR drill; operator documentation.
- UI P1s on this branch (dark mode, mixed theme, unreadable active nav). The demo-credentials P1 is **closed** by C1.1.
- Data-subject operations have no admin UI yet (service level only). Erasure must be mirrored upstream.
- Live TLS with a real domain not yet verified.

**P2**
- Multi-host lockout store (PostgreSQL) if more than one host is used.
- Session idle timeout.
- Rehash-on-login leaves unused accounts on legacy hashes until they log in.
- Old-scheme pseudonymous rows are unlinked.
- NER-grade free-text PII detection.
- Cold-start first render after container creation (60–240 s on this host).
- RAG governance filters in SQL.
- `rag_chunks`/`model_metrics` RLS.
- Cache bounds and keys.
- Image still ships `tests/`, `models/` and root-level design docs.
- Base image digest pinning; lock file for the six `>=` ranges.
- CSP still needs `'unsafe-inline' 'unsafe-eval'` for Streamlit.

**P3**
- English strings on login.
- Number formatting in narrative text.
- Pre-existing pyflakes warnings in `career_ai_advisor.py` and `context_builder.py` (unused imports, not introduced here).

## 15. Result

Stop conditions:

| Condition | Met? |
|---|---|
| Known P0 personal-data release issue removed | ✅ working tree + image; history is an owner decision (reported, not rewritten) |
| Commercial ML claims safely qualified | ✅ runtime UI qualified; historical reports addended, not rewritten; leakage proven absent in current training |
| Production demo shortcuts disabled | ✅ tested + live |
| Pseudonymization production-safe | ✅ |
| Provider payload minimization tested | ✅ |
| Data lifecycle foundation exists | ✅ service level, tested on PostgreSQL |
| Production DB exposure safe | ✅ config + live |
| Secret scan passes | ✅ |

```
C1_1_STATUS = COMPLETE
SAFE_TO_PROCEED_TO_C1_2_RELEASE_ENGINEERING = YES
```

Carried into C1.2 and beyond:
- the git-history personal data decision (owner);
- external key rotation (owner);
- live TLS on a real domain;
- the stale CI/backup-test asserts (the first C1.2 item);
- an admin UI for data-subject operations.
