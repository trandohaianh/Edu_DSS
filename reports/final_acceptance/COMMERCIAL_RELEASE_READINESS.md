# EduDSS commercial release readiness audit

| | |
|---|---|
| Date | 2026-09-26 |
| Worktree | `D:\KLTN\edudss-final-candidate-v2` |
| Branch | `fix/ml-correctness` |
| HEAD | `e2241bfd7a1e4f7363047230eddf68e68cb802e7` (unchanged by this audit) |
| Nature | Audit only: no algorithm, infrastructure or UI change, no commit, merge or push |

**Working tree at start:**
- modified: `app/tests/test_ml_hub_ranking_consistency.py`
- untracked, user-owned: 3 `.docx`, 2 `PROMPT_*.md`, `app/reports/final_acceptance/`
- index: empty

**Files added by this audit (new, untracked):**
- `app/reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md`
- `app/reports/final_acceptance/evidence/`: benchmark output, CI-equivalent logs, UI screenshots of this branch
- `app/tools/pgvector_scale_benchmark.py`

**Evidence hierarchy used:** current source code and executed commands first; existing reports are cited only where they were re-checked. Where a report disagreed with code or a re-run, the code or re-run wins (see §31).

---

## 0. Two facts that change how earlier evidence may be used

1. **The accepted UI evidence (59 screenshots, 39 Playwright tests, 23 pages, P0/P1/P2 = 0) was produced on a different codebase.** It came from `D:\KLTN\code` (`main` 10b487d plus *uncommitted* UI, AI and CI changes). Those changes are **not** in this branch: there is no `ai_provider_status.py` or `ui_kit.card`, and the hashed `.st-emotion-cache-1ne20ew` selector and the OS dark-mode media block are still present. The evidence cannot be credited to this branch. A fresh capture of **this** branch is reported in §28.
2. **The accepted CI facts (LOCAL_CI_EQUIVALENT / FRESH_CHECKOUT = VERIFIED) belong to `main`.** On this branch, `.github/workflows/edudss-release-gate.yml` hard-codes `27 tables` and head `797f72d1c666`, but this branch's head is `9f3a1c7d2e46` with 42 public tables, so the hosted workflow would **fail deterministically**. `tests/test_backup_recovery_integration.py` hard-codes the same old head. The facts are not altered for `main`; they simply do not transfer.

---

## 1. Executed evidence (this audit)

| Check | Command | Result |
|---|---|---|
| Baseline regression, local (Python 3.12.4, no PostgreSQL) | `pytest tests --ignore=tests/e2e` | **943 passed, 0 failed, 164 skipped**, 240 s |
| Fresh checkout of `e2241bf` + uncommitted overlay, Docker image, PostgreSQL 16 + pgvector (adapted local CI script) | `evidence/branch_ci_equivalent_run1.log`, `run2.log` | Alembic 0 → `9f3a1c7d2e46`, 42 tables, pgvector ✔. **Full regression 1,063 passed, 0 failed, 40 skipped** (685 s). RLS/pgvector 26 ✔, security 24 ✔, AI 56 ✔, 12A 14 ✔, 1C 42 ✔, Phase 13 deterministic 11 ✔, **Phase 13 real restore ✘** (stale head assertion fires *before* backup, so restore was **not** exercised on this schema), 20k batch ✔, container smoke ✔ (uid 999, health, `/` 200, readiness ready, no keys → `not_configured`, no `.env` in image) |
| Embedding benchmark re-run | `tools/embedding_benchmark_vi.py` | Reproduced exactly: MiniLM-L6 R@5 0.913 / MRR 0.835 / 23 ms; multilingual-MiniLM-L12 R@5 0.957 / MRR 0.957 / 42 ms. **Corpus = 19 demo docs, 23 queries.** |
| pgvector scale (new, honest proxy) | `tools/pgvector_scale_benchmark.py`, `evidence/pgvector_scale_benchmark.txt` | Exact `<=>` + tenant filter, LIMIT 50, 384-d, 8 vCPU. p95: 10k **18.5 ms**, 50k **47.8 ms**, 100k **81.5 ms**, 250k **149.6 ms**. HNSW @ 250k: p95 **35.8 ms**, build 278 s. |
| Licence inventory | `importlib.metadata` over 117 installed dists + HF model cards | No GPL/AGPL. LGPL-with-exceptions: psycopg2-binary. MPL-2.0: certifi, tqdm. Both embedding models Apache-2.0. |
| RLS coverage | SQLAlchemy metadata vs migrations | 34/34 tables with `organization_id` have RLS. `rag_chunks` and `model_metrics` have **no** `organization_id` and **no** policy. |
| UI capture of **this** branch | adapted harness, `evidence/ui_screens_branch/` | see §28 |

---

## 2. Master table

Severity: **P0** security/data-loss/legal-critical · **P1** commercial-release blocker · **P2** important hardening · **P3** polish.

| # | Area | Current state | Evidence | Decision | Sev. | Required action | Acceptance test |
|---|---|---|---|---|---|---|---|
| 1 | Repository personal data | `app/dữ liệu/nhanvien_export.csv`: tracked since the initial import, employee-shaped (name, 9-digit ID, 10-digit phone, address, salary), 4 rows, unrelated to EduDSS, **shipped inside the Docker image** (`.dockerignore` doesn't exclude `dữ liệu/`) | §18 | REPLACE (remove) | **P0** until provenance confirmed | Confirm synthetic or real. Remove from tree and image. If real: purge history before any distribution. | secret/PII scan of image and history = 0 personal records |
| 2 | Commercial ML claims | Thesis/marketing figures (R² 0.992, RMSE 0.074, accuracy 0.875, Silhouette 0.412) come from **synthetic** data. The R² artifact also used a **leaky** feature (`xep_loai` derived from the target). | §3 | REPLACE wording | **P0 (legal/claims)** | Withdraw these figures from all commercial material. Use the §3 safe wording. | claim review sign-off; §31 table all SUPPORTED or QUALIFIED |
| 3 | Real-data validation | No real-university dataset has ever been used. The independent check on simulator data missed every target (F1 0.518, R² 0.102, Silhouette 0.105). | §3 | MISSING | **P1** | Pilot validation on the first customer's historical records (temporal split, per-cohort). Publish only those metrics. | signed validation report on customer data |
| 4 | "Risk" levels | Bottom 25% of the *current class* = "cao" (relative quantile of predicted score). Not an absolute risk, not a probability. | §4 | UPGRADE | **P1** | Label as a relative ranking, or use regulation-driven absolute thresholds (for example the academic-warning GPA from the Rule Engine), configurable per tenant | unit test: a uniformly strong class yields 0 "cao" under absolute mode |
| 5 | Probability calibration | `predict_proba` is shown as "xác suất theo mô hình" with a "CHƯA HIỆU CHUẨN" caveat, but the next line interprets ≥0.8 as "khá ổn định". There is no calibration anywhere. | §4 | UPGRADE | **P1** before selling prediction | Either calibrate (`CalibratedClassifierCV`, Brier + reliability on held-out real data) or stop showing percentages and interpreting thresholds | Brier/ECE reported; UI shows % only for calibrated models |
| 6 | ML algorithms | LR, RF, XGBoost, LightGBM (clf+reg); GridSearchCV, Stratified K-fold, Dummy baseline, leakage guard, optional SMOTE | §2 | KEEP (details §2) | P3 | Add `class_weight`/`is_unbalance` for boosting. Drop the unused `SVC/SVR/Lasso/Ridge` imports. | trainer tests |
| 7 | K-Means | K configurable 2–15 (UI default 4), Silhouette-recommended, neutral labels "Cụm N", **model lives only in Streamlit session** | §5 | KEEP algorithm / UPGRADE persistence | P2 | Persist per-tenant fit (model, K, scaler, feature set, date, approver); stable label mapping across refits; human-approved names | refit → same students keep the same named segment when data is unchanged |
| 8 | SHAP | TreeSHAP for RF/XGB/LGBM; KernelSHAP (100 background samples) for linear/other; local and global; no persistent cache | §6 | KEEP | P3 | Cache per (model version, student). Keep "đóng góp của đặc trưng" wording. | latency test p95 < 2 s for tree models |
| 9 | Embedding model | all-MiniLM-L6-v2 (English-trained), 384-d, cosine | §7 | KEEP now, **re-decide on a real corpus** | **P1** (evaluation) | Build a ≥150-query VI/EN/mixed benchmark on the customer's regulations and course docs. Multilingual-MiniLM-L12 (same 384-d, Apache-2.0) is the leading candidate. | benchmark report on customer corpus; migrate only if it wins |
| 10 | RAG governance filters | Approval, effective, expiry and single-model checks run **after** retrieval on an over-fetch of ≤300. PG `filter_scope` applied **after** `LIMIT`. | §7 | UPGRADE | P2 | Move `status='APPROVED' AND is_current AND effective/expiry` and scope into the SQL `WHERE` | test: 400 unapproved near-duplicates + 1 approved → approved returned |
| 11 | pgvector search | Exact scan, no ANN index | §8 | KEEP | P3 | Add HNSW when a tenant exceeds ~100k chunks or p95 > 100 ms | re-run `pgvector_scale_benchmark.py` at the customer's size |
| 12 | Database | PostgreSQL 16, SQLAlchemy 2, Alembic (9 revisions), RLS FORCE on 34 tables, 70 FKs, default pool (5+10), no `statement_timeout` | §9 | KEEP / UPGRADE hardening | P2 | Explicit pool sizing; `statement_timeout`; RLS for `rag_chunks` and `model_metrics`; downgrade/upgrade test | RLS test for chunks; migration round-trip in CI |
| 13 | Cache | In-process TTL dict (LLM exact cache keyed prompt+role+user), no size bound, no tenant/model/regulation version in key | §10 | KEEP (upgrade keys and bounds) | P2 | Bound size (LRU); add tenant and regulation/KB version to the key; flush on regulation/doc approval | eviction test; invalidation test |
| 14 | Background jobs | Initial sync runs **inside the Streamlit request**. **Incremental sync has no trigger at all** (only a test calls it). Training, reindex and batch run in-request. | §11 | MISSING (scheduler/worker) | **P1** (sync schedule) / P2 (worker) | CLI entrypoints (`python -m ops.sync --org N`) run by a scheduler (cron / container job). A job-status table. No Celery yet. | scheduled incremental sync runs unattended for 7 days with status visible |
| 15 | Scale | VERIFIED: 50 concurrent **DB operations** (p95 452 ms), 20k-record **batch inference** 3.03 s, 5-min soak. NOT measured: concurrent Streamlit users. | §12 | UPGRADE (test) | **P1** (first-customer sizing) | Browser-session load test at 100/250/500 sessions on the target hardware | §12 plan table filled with measured rows |
| 16 | App architecture | Streamlit stateful sessions; **single tenant per process** (`EDUDSS_ORGANIZATION_ID`); models (joblib), regulations (JSON), logs on local disk | §13 | KEEP for dedicated / UPGRADE for SaaS | P2 (dedicated) / **P1 (SaaS)** | Dedicated: shared persistent volume + sticky sessions if >1 replica. SaaS: runtime tenant context from the logged-in user. | two replicas behind LB, session survives; tenant switch test |
| 17 | LMS/SIS integration | Only `simulated_lms_cms` connector (simulator REST contract; org-a/org-b). Pagination, cursor, idempotency, HMAC webhooks and retry are real **against the simulator**. No Moodle/Canvas/SIS adapter. | §14 | MISSING (real adapter) | **P1** | First adapter matched to the first customer (Moodle Web Services, or a validated SIS CSV/Excel import into tenant tables) | contract test against the customer's staging LMS / sample export |
| 18 | Onboarding | UI: provision → admin → connector (env-var credential reference) → test → mapping check → initial sync → activate | §15 | UPGRADE | **P1** | Add program/cohort/regulation configuration; a real connector type; credential entry without server restart | end-to-end onboarding of a new tenant without shell access |
| 19 | Regulations | Resolver correct (org → program → cohort → effective window → version). **Store = local JSON; no admin upload/approval UI; only tests create regulations.** | §16 | UPGRADE (store) / MISSING (workflow) | **P1** | PostgreSQL `regulation_versions` with RLS; admin draft → approve → effective workflow with audit log | regulation update changes Tier-1 answer without restart or LLM retraining |
| 20 | AI providers | Gateway, circuit breaker, failover, audit, per-tenant default provider and token usage (DB). **API keys global (env). Budgets hard-coded** ($15/day, $300/month). | §17 | KEEP / UPGRADE | P2 (dedicated) / P1 (SaaS) | Per-tenant provider policy, budgets and (SaaS) keys in a secret store; "no external AI" tenant mode documented | tenant A policy never uses tenant B's key |
| 21 | Pseudonymization | `sha256("edudss_privacy_salt_2026:" + id)[:6]`: **public hard-coded salt, 24 bits**. Re-identifiable by enumerating student codes; identical across tenants. | §18 | UPGRADE | **P1** | HMAC-SHA256 with a per-tenant secret key from the secret store, ≥64 bits | test: pseudonym differs per tenant; no source-code constant |
| 22 | Data-subject rights / retention | No delete/export per student, no retention policy for logs, audit, consultations or backups | §18 | MISSING | **P1** | Deletion and export functions (DB + vectors + files + caches), retention schedule, backup expiry | delete-student test removes all stores |
| 23 | Auth | PBKDF2-SHA256 200k; lockout 5/15 min in process memory; demo accounts not seeded in production. **Student auto-provision (`<code>123`) gated only on `EDUDSS_MODE`, not `EDUDSS_ENV`.** Login page **shows demo credentials unconditionally.** | §19 | UPGRADE | **P1** | One `is_production()` predicate for all demo paths; hide the demo box in production; auto-provision off by default; PBKDF2 ≥600k or Argon2id; persistent lockout | test matrix env×mode: no auto-provision, no demo credentials rendered |
| 24 | TLS / network | No reverse proxy, TLS, security headers or rate limiting at the edge. Compose publishes Postgres `0.0.0.0:5432`. | §20 | MISSING | **P1** | Reference reverse proxy (TLS, HSTS, CSP compatible with Streamlit, WebSocket upgrade, body limit); DB on an internal network only | external scan: only 443 open; headers present |
| 25 | Observability | Structured JSON logs + correlation IDs, `readiness()` Python function, process-local counters. **No HTTP readiness endpoint, no metrics export, no alerting.** | §21 | UPGRADE | **P1** | `/healthz`-style readiness served by a sidecar/CLI; export key metrics; alert rules (§21) | alert fires in drill for DB down, sync failure, provider 429 |
| 26 | Backup / DR | PG backup/restore drill verified on `main` schema; **not re-verified on this branch's schema**; non-DB manifest tool separate; no combined DR drill; secrets/config not covered | §22 | UPGRADE | **P1** | Fix stale test; combined DR runbook + drill (DB + vectors + models + uploads + config); define RPO/RTO | full-environment restore to a clean host within stated RTO |
| 27 | Docker | `python:3.11-slim` **unpinned** (already drifted to Debian 13); CPU-only torch pinned; non-root; healthcheck; image carries `tests/`, `reports/`, `dữ liệu/`, UI reference kit | §23 | UPGRADE | P1 (content, due to #1) / P2 (pinning) | Digest-pinned base; exclude non-runtime dirs; pin the 6 `>=` deps via a constraints/lock file; align local Python (3.12) with the image (3.11) | reproducible build hash; image content allow-list test |
| 28 | CI | Workflow present; **stale schema/head asserts on this branch → would FAIL**; no remote → hosted NOT_VERIFIED | §24 | UPGRADE | **P1** | Derive expected head/table count from Alembic; add remote; obtain a green hosted run | hosted run URL, green |
| 29 | CD | NOT_IMPLEMENTED | §25 | MISSING | **P1** | Minimal CD (§25) | staging deploy + smoke + manual promotion + rollback drill |
| 30 | Versioning | No semver, tag, changelog, image label or `/version` | §26 | MISSING | **P1** | Release identity (§26) exposed in UI/About and logs | release manifest generated in CI |
| 31 | Licensing | No GPL/AGPL; LGPL psycopg2 (dynamic), MPL certifi/tqdm; models Apache-2.0 | §27 | KEEP | P2 | `THIRD_PARTY_NOTICES` for Python deps + models; verify TailAdmin/assets are not shipped | notices file generated in CI |
| 32 | UI | 24 pages, 61 screens captured; 4 P1 visual/security defects (dark mode broken, mixed theme, unreadable active nav, demo credentials) | §28 | UPGRADE (port fixes from `D:\KLTN\code`) | **P1** | Port, recapture, re-run Playwright on this branch | 0 P1/P2 in recapture; 39/39 E2E on this branch |
| 33 | Ops docs | Evaluator README (79 lines) + PG backup runbook only | §29 | MISSING | **P1** | Operator handbook set (§29) | a new operator installs, upgrades and restores using docs only |
| 34 | Commercial claims | See §31 | §31 | REPLACE wording | P0/P1 | Update commercial materials per §31 | review sign-off |

---

## 2. ML algorithm decision (section 2 of brief)

**Data reality:** the only data the models have ever been measured on is synthetic, simulated or public-benchmark data (§3). Evaluated with that constraint:

| Criterion | Random Forest | XGBoost | LightGBM | LR / Linear | SVM | KNN | Neural net |
|---|---|---|---|---|---|---|---|
| Tabular, mixed features, hundreds–tens of thousands of rows | strong | strong | strong | baseline | weak at scale | weak | weak without large data |
| Imbalance handling in code | `class_weight='balanced'` ✔ | none by default | none by default | none | – | – | – |
| Probabilities | yes (uncalibrated) | yes | yes | yes (usually best calibrated) | needs Platt | coarse | yes |
| TreeSHAP | ✔ | ✔ | ✔ | Kernel (slow) | Kernel | Kernel | Deep/Kernel |
| CPU training / inference | fast | fast | fastest | trivial | O(n²) training | slow inference | slowest |
| Measured macro-F1 (synthetic, 1,000 rows) | **0.875** | 0.701 | 0.709 | 0.715 | – | – | – |
| Maintenance | sklearn | extra wheel, GPU-dep workaround (`--no-deps`) | wheel | sklearn | – | – | torch already present but unused for ML |

Answers:
- **Keep LightGBM?** Yes. Fast on CPU, TreeSHAP, strong on tabular data. Give it `class_weight`/`is_unbalance` so it stops under-performing on the rare "Yếu" class (macro-F1 gap vs RF on 2-sample classes).
- **Keep XGBoost?** Yes, as an optional model. It is redundant with LightGBM, and its install needs a `--no-deps` workaround. Re-evaluate removal after the real-data benchmark (POST_RELEASE). Do not remove before evidence.
- **Keep Random Forest?** Yes. It is the most robust under imbalance in current measurements, and the natural default for small tenants.
- **Add SVM?** No. It has no native probabilities, scales poorly, and has no TreeSHAP. `SVC/SVR` are imported but unused, so remove the imports.
- **Add KNN?** No. It adds no capability, has poor inference latency and weak explanation.
- **Add neural networks?** No. There is no dataset size or benchmark that justifies them for this tabular problem, and they worsen explainability and CPU cost.
- **Regression:** Linear Regression, RF, XGB and LGBM are all KEEP. Linear Regression "winning" at R² 0.993 is a property of the synthetic generator (the target is close to a linear formula), not evidence about real students.

Governance present in code: GridSearchCV with Stratified K-fold; Dummy baseline stored as `__baseline__`; target-leakage guard (`get_leaky_target_columns('final_score')` now excludes `xep_loai`, `grade`, `diem_ky_sau`); SMOTE applied inside the CV pipeline; feature schema and provenance mirror (`ML_PROVENANCE`, off by default); model registry with candidate → Admin-promoted → production; drift table (migration `6cfe48a652ca`).

Missing for commercial prediction:
- calibration;
- decision thresholds tied to tenant policy;
- real-data temporal validation;
- automated retraining trigger (drift is recorded, nothing acts on it);
- model artifacts only on local disk (PostgreSQL holds only the optional metadata mirror).

## 3. ML data validity

| Source (in repo) | Class |
|---|---|
| `generate_data()` → dataset id `sample_data_v1` (default app dataset, `ml_benchmark.py`) | **SYNTHETIC** |
| `fake_it_student_data.csv`, `du_lieu_gia.csv`, `sample_student_data*.csv`, `test_batch_data.csv`, `50_sv_data.csv`, `student_data.csv` | **SYNTHETIC / DEMO** |
| `student-mat.csv` (395 rows, UCI Student Performance, Portuguese secondary school) | **EXTERNAL BENCHMARK** (CC BY 4.0) |
| `Student_Performance.csv`, `student_habits_performance.csv` (1,000 rows each, public Kaggle-style) | **EXTERNAL BENCHMARK / likely synthetic** (provenance not documented in repo) |
| Staging/"72h" simulator data | **SIMULATED** |
| Any real university data | **none** |

| Metric | Value | Dataset | Real/Synthetic | Valid commercial claim? | Safe wording |
|---|---|---|---|---|---|
| R² | 0.992 (thesis), 0.993 (re-run) | `sample_data_v1` (132 train rows in the thesis artifact; features include **`xep_loai`, derived from the target**) | SYNTHETIC + leaky | **No** | "On synthetic demonstration data the pipeline reproduces the generator's relationships (R² ≈ 0.99). Not a measure of real-world accuracy." |
| RMSE / MAE | 0.074 / 0.060 | same | SYNTHETIC | **No** | same as above |
| Accuracy | 0.875 (thesis) | not reproducible in repo | unknown | **No** | do not publish |
| Accuracy / F1-macro (re-run) | RF 0.890 / 0.875; LGBM 0.920 / 0.709; baseline 0.46 / 0.126 | `generate_data()` 1,000 rows | SYNTHETIC | **No** | "The models clearly beat a majority-class baseline on synthetic test data." |
| Precision / Recall | not separately published | – | – | No | – |
| Silhouette / DBI | 0.412 / 0.831 (thesis) | not reproducible | unknown | **No** | "K is chosen per dataset via Silhouette and Elbow." |
| Simulator check | F1 0.518, R² 0.102, Silhouette 0.105 | 72h-branch simulator data, minimal pipeline | SIMULATED | No (neither positive nor negative) | "Quality on real data will be established during pilot validation." |
| SHAP values | per model | any | explains the model only | Only as "đóng góp của đặc trưng vào dự đoán của mô hình" | never "nguyên nhân" |

## 4. Production ML governance

| Item | State |
|---|---|
| Leakage | Guard present and effective (verified) |
| CV / tuning | Stratified K-fold GridSearch (XGBoost skips grid when rare classes would break folds) |
| Baseline | Dummy stored, never ranked |
| Imbalance | RF `class_weight`; optional SMOTE / BorderlineSMOTE; boosting unweighted |
| **Calibration** | **absent** |
| Thresholds | risk = relative quartile; prediction confidence thresholds 0.6/0.8 hard-coded on uncalibrated scores |
| Schema / version / provenance | feature schema + provenance mirror (flag, off by default) |
| Approval / rollback | registry promote/demote (Admin) |
| Drift | recorded; no trigger/alert |
| Monitoring | none beyond logs |

Before selling predictive features:
1. Real-data temporal validation per customer.
2. Either calibrated probabilities or no percentages shown.
3. Absolute, regulation-based risk definitions.
4. Drift alert → human retraining decision.
5. Model artifacts in durable shared storage with backup.

**The UI's "70% / 85% / 92%" are uncalibrated model scores.** The caption already says so; the ≥0.8 "khá ổn định" interpretation must go.

## 5. K-Means
K is **configurable** (2–15, UI default 4) with a **Silhouette recommendation** (Elbow as a secondary hint), so it is not hard-coded. Labels are neutral ("Cụm N", with "Mạnh/Yếu" feature descriptions); the persona names "Xuất sắc / Nỗ lực / Rủi ro / Thấp động lực" do **not** appear in cluster code and are not treated as ground truth.

Commercial need:
- tenant-specific, persisted fits (today the fit is session-only and lost on logout);
- periodic, approved re-fits;
- stable cluster-to-name mapping across refits (for example by centroid matching);
- human-approved segment names.

## 6. SHAP
- Tree models use `TreeExplainer`; others use `KernelExplainer` with 100 background samples (local) or 50 (global). This covers local per-student and global explanations.
- No persistent cache.
- Wording in UI and code does not claim causality (no "nguyên nhân/cause" linked to SHAP found).
- The dashboard's "top factor" for high-risk students is deviation from the class mean, **not** SHAP. It must be labelled as such.

## 7. RAG
- Current: all-MiniLM-L6-v2, 384-d, cosine `<=>`, top-k 5, over-fetch ×10 (cap 300), chunking via `chunking_service`, namespaces, approval workflow (PENDING_REVIEW → APPROVED, approver required), effective/expiry, content hash, mixed-model detection, CMS `upsert_and_reindex` / `invalidate_content`, citations and knowledge fallback.
- **Benchmark validity:** 19 demo documents and 23 queries. There are no university regulations and no separate EN or mixed-language set, which is far too small to decide a commercial embedding.
- **Decision:** KEEP MiniLM-L6 for the codebase now. **P1:** before the first customer goes live, build a representative benchmark from the customer's regulations and course material (≥150 queries, VI/EN/mixed). Migrate to `paraphrase-multilingual-MiniLM-L12-v2` (same 384-d, Apache-2.0, +19 ms/embedding) if it wins there; the schema does not change, only a full re-embed. Top-k 5: KEEP (k=8 added nothing; k=3 is a documented precision/recall trade-off).
- **Correctness hardening (P2):** push governance predicates into SQL, and fix the post-`LIMIT` `filter_scope` filtering in `PgVectorStore.search`.

## 8. Retrieval scale
The current strategy is **exact sequential scan** (no ANN index). Measured p95 is ≈ 0.6 ms per 1,000 chunks. A typical university (a few thousand documents, ≈ 20–80k chunks) sits at ≈ 20–70 ms, so it is **not a bottleneck: KEEP**. ANN (HNSW; measured 36 ms p95 at 250k with a 278 s build) becomes justified when **one tenant exceeds ~100k chunks or retrieval p95 > 100 ms**. In shared SaaS, HNSW combined with a tenant filter needs a per-tenant partition or `iterative_scan` testing first.

## 9. Database
PostgreSQL remains the production primary: **KEEP**. There is no evidence for replacement. RLS is FORCE'd with policy `tenant_isolation` on all 34 organization-scoped tables and verified under a non-superuser role (26 tests passed in this audit).

Hardening items:
- RLS or organization column for `rag_chunks` and `model_metrics` (P2 dedicated, **P1 SaaS**);
- explicit pool size and `statement_timeout`;
- Alembic downgrade and round-trip test;
- migration run as a separate job before app start (Compose already has a `migrate` service).

## 10. Cache
**KEEP CURRENT CACHE** (in-process) for dedicated deployments. Evidence:
- The cache holds only LLM answers and embeddings. Entries are user-scoped (`user_id` in the key); the cross-user isolation test exists and passes.
- Correctness does not depend on sharing, because a miss simply recomputes.

Upgrades (P2): bounded size; tenant and KB/regulation/model version in the key; flush on approval events.

**Distributed cache (Redis) is not justified yet.** It becomes necessary only when (a) running more than one replica **and** (b) needing shared rate limits or circuit state or measurable provider-cost savings. Revisit with the load-test results.

## 11. Background jobs
Must not run inside a web request: initial and incremental LMS/CMS sync, full re-embedding or reindex, training with GridSearch, 20k+ batch prediction, reports/PDF for cohorts, backups.

Today all of them run in-request or are manual, and **incremental sync has no trigger at all**.

Minimum justified design: CLI entrypoints plus a scheduler (host cron / Compose one-shot / Kubernetes CronJob later), a `jobs` status table in PostgreSQL, and UI "start job / view status" instead of blocking. **No Celery/RQ yet.** A broker is justified only when concurrent user-triggered jobs or retries across replicas appear.

## 12. Scale claim

| Quantity | Verified? | Value |
|---|---|---|
| Registered users | not tested | – |
| Daily active users / requests per day | not tested | – |
| Concurrent **DB operations** | ✔ | 50 concurrent, p95 452 ms, 0 errors (single dev machine) |
| Soak | ✔ | 300 s, 70,887 ops, 0 errors (**not 72 h**: the "72h" branch report contains no 72-hour run) |
| **Concurrent Streamlit users** | **✘ never measured** | – |
| Batch inference | ✔ | 20,000 records in 3.03 s (6,591/s) |
| Provider latency / 429 rate | ✘ | – |

**20K = batch size, never concurrent users. 50K: nothing verified.**

Load-test plan. Browser sessions are driven by Playwright/Locust-websocket against the **target hardware**. Record RPS, p50/p95/p99, error rate, CPU, RAM per session, DB connections, queue depth, cache hit, provider latency and 429 rate.

| Stage (concurrent sessions) | Feasible on | Gate |
|---|---|---|
| 100 | 1 VM (8 vCPU/32 GB) | required before the first customer |
| 250 | 1 VM | required |
| 500 | 1–2 VMs | required if the contract promises it |
| 1,000 / 2,500 | multiple replicas + sticky LB | only with multi-replica design |
| 5,000–50,000 | not realistic for Streamlit sessions without re-architecture | do not claim |

## 13. Application architecture
Not stateless:
- Streamlit keeps a session per WebSocket (needs sticky sessions).
- The tenant is process-wide (`EDUDSS_ORGANIZATION_ID`).
- Local filesystem holds model artifacts (joblib), the regulations JSON, logs, and the local vector store if PostgreSQL is off.
- Caches, rate limiter, lockout and circuit breaker are per-process.

Target for a first customer (dedicated): HTTPS reverse proxy → **1 EduDSS container** (sized from the load test) → PostgreSQL + pgvector on a private network → persistent volume for artifacts → scheduled job container → AI Gateway (outbound only). Horizontal scaling: ≥2 replicas with sticky sessions and a shared volume or object storage. **Kubernetes is not justified.**

## 14. LMS / SIS / CMS

| Level | Status |
|---|---|
| SIMULATED | ✔ Real HTTP to the in-repo simulator: pagination, `updated_since` cursor persisted, idempotent resync (0 duplicates after restart), HMAC-SHA256 webhooks, retry on 429/500/timeout, canonical mapping validation, tenant isolation (2 synthetic tenants). |
| REAL LAB (e.g. a Moodle container) | ✘ none (UI buttons "Moodle Webhook" / "Canvas" are simulations) |
| PRODUCTION UNIVERSITY | ✘ none |

Limitations of the "72h" simulation, recorded:
- The run contains no 72-hour window: the soak was 5 min.
- 404 was not modelled.
- Cross-tenant RAG retrieval was not re-tested in that round.
- ML numbers are from a minimal pipeline.
- Live AI providers were not claimed.

First real customer requires:
1. A real adapter for their system (Moodle Web Services token auth, course/grade/attendance endpoints), **or** a validated CSV/Excel SIS import into tenant tables (fastest safe path).
2. A field-mapping profile per customer.
3. Scheduled sync (§11).
4. Contract tests against their staging.

## 15. Onboarding

| Step | State |
|---|---|
| Create tenant, university info | ✔ (`provision_university`) |
| Configure LMS/SIS/CMS | ◐ only the simulated type |
| Credentials | ◐ stored as an **env-var name** reference; adding a tenant secret needs a server env change and restart |
| Map canonical fields | ◐ validation only against the simulator's shape |
| Test connection / initial sync | ✔ simulated; sync is synchronous in the UI |
| Validate records | ◐ mapping validation; no record-level validation report |
| Regulations, program, cohort | ✘ missing |
| First admin | ✔ |
| Activate | ✔ (with `accept_without_sync` escape) |
| Monitor sync | ✘ no sync dashboard/alerts |

## 16. Regulation and decision engine
- **Authoritative:** GPA Calculator, Rule Engine (credit limit, academic warning, …) and Validator are deterministic.
- **Correct:** the resolver selects exactly one version by organization → program → cohort → effective window → highest version.
- **Missing:** a production store (JSON file today) and the admin draft/approve/publish workflow. A regulation update requires no LLM retraining by design, but there is currently no product path to enter one.

## 17. AI providers (commercial operations)
- **Accepted as-is:** 3-Tier AI, circuit breaker, failover, correlation/incident IDs, knowledge fallback, no-key operation (container verified `ai_configuration: not_configured`, app ready).
- **Needed:**
  - per-tenant provider policy (allowed providers, "no external AI" mode) — P2 dedicated / P1 SaaS;
  - per-tenant budgets instead of hard-coded constants (P2);
  - keys in a secret store, per tenant for SaaS (P1 SaaS);
  - a Data Processing Agreement with each external provider before sending any student context (P1, contractual).

Not every customer must configure every provider; the no-key mode is a supported deployment.

## 18. Privacy and data protection

Data flow:

```
University LMS/SIS/CMS ──(HTTPS, bearer token, HMAC webhooks)──▶ EduDSS
  EduDSS internal: PostgreSQL (RLS) · pgvector · local volume (models, regulations, logs) · backups
  ──▶ External AI provider (only if configured):
        pseudonym (weak today) · banded GPA *with approximate value "~7.3"* · risk level ·
        attendance/progress · sanitized weaknesses · last 5 chat turns (regex-sanitized, no NER) ·
        retrieved course/regulation chunks · the question
```

PII crossing the boundary:
- The pseudonym is re-identifiable (public salt, 24-bit).
- The approximate GPA is effectively exact.
- Free-text disclosures can slip past regex sanitization.
- Course material is sent verbatim.

Nothing else (name, email, raw student ID) is sent, per code and tests.

Required:
- per-tenant keyed HMAC pseudonyms (P1);
- drop the "~x.x" GPA or send the band only (P2);
- deletion/export and retention (P1);
- log retention;
- backup expiry;
- DPA with providers;
- mapping to Vietnam Decree 13/2023/NĐ-CP obligations (consent, purpose, cross-border transfer impact). This is a control mapping, **not** a compliance claim.

## 19. Auth / security (control mapping, no certification claimed)

| Control | State | Gap |
|---|---|---|
| Password hashing | PBKDF2-HMAC-SHA256, 200k iterations, per-user salt | raise to ≥600k (current OWASP guidance for PBKDF2-SHA256) or Argon2id (P2) |
| RBAC | 3 roles, service-level `require_role`, allow-lists | – |
| RLS | FORCE on tenant tables, non-superuser verified | chunks/metrics (see §9) |
| Session | Streamlit session state; no idle timeout found | add idle/absolute timeout (P2) |
| Brute force | 5 attempts / 15 min lockout, **in-memory per process** (reset on restart, per replica) | persist in DB (P2) |
| Demo paths in production | seeding gated (env OR mode); **auto-provision gated on mode only**; **demo credentials rendered on the login page always** | **P1** |
| CSRF | Streamlit XSRF protection (default on); no custom forms outside Streamlit | – |
| Rate limiting | in-process AI RPM; none at the edge | reverse proxy (P1 with TLS) |
| Security headers | none (Streamlit) | reverse proxy |
| Input / upload validation | `upload_security` (type/size), prompt boundary & injection tests | – |
| Secrets | env vars / `.env` (gitignored); `.env.example` blank here | secret store per deployment (P2) |
| Dependency scanning | none | add `pip-audit` / image scan in CI (P2) |
| Container | non-root uid 999, healthcheck | digest pin, content allow-list |
| Audit logs | `audit_logs` table (RLS), AI decision audit contract | retention policy |

## 20. TLS / domain / network

| Requirement | Current | Production |
|---|---|---|
| Domain + TLS + auto-renewal | none (localhost) | reverse proxy (Caddy/Nginx/Traefik) with ACME, HSTS |
| WebSocket support | direct | proxy must pass `Upgrade` for `/_stcore/stream` |
| Database exposure | Compose publishes `5432` on all interfaces | internal network only |
| Ollama | **10 hard-coded `localhost:11434` references; `OLLAMA_BASE_URL` is read nowhere**, so a containerized EduDSS can never reach a host/Compose Ollama | read endpoint from config (P1 if the customer wants local-model mode) |
| Firewall | none defined | 443 in; outbound allow-list to LMS and AI providers |

## 21. Observability
- **Present:** JSON logs with correlation IDs; AI decision audit events; `readiness()` (PostgreSQL, pgvector, AI configuration, model artifacts); process-local operation counters; the lecturer/admin "Hệ thống hoạt động" badge.
- **Missing:** HTTP readiness for external monitors (only Streamlit's `/_stcore/health` liveness is exposed), metrics export and alerting.
- **Alert requirements:** app down or readiness not ready (1 min) · DB unreachable / connections >80% · sync failed or cursor stale > N h · provider circuit open or 429 rate > 5% · AI budget 80%/100% · drift threshold crossed · RAG ingestion/reindex failure · backup job failed/missing · disk > 80%.

## 22. Backup / DR

| Asset | Evidence | Status |
|---|---|---|
| PostgreSQL logical backup + restore + RLS after restore | Phase 13 drill on the `main` schema (backup 0.34 s, restore 1.5 s, small data) | **VERIFIED on `main`; NOT_VERIFIED on this branch** (the test's stale head assertion aborts before backup) |
| Vector data | lives in PostgreSQL (`rag_*`), covered by `pg_dump` in principle | PARTIAL (not separately verified here) |
| Model artifacts, datasets, regulations JSON, uploads | `ops/non_db_recovery.py` manifest + checksum | PARTIAL (not combined with DB) |
| Config / secrets | not covered | NOT_VERIFIED |
| Combined DR (new host from backups) | none | **NOT_VERIFIED** |
| RPO/RTO | stated in runbook, not demonstrated | NOT_VERIFIED |

## 23. Docker / reproducibility
- CPU-only torch pinned (`2.9.1+cpu`); xgboost installed with `--no-deps` and a post-install assertion; non-root; healthcheck.
- **Base `python:3.11-slim` is unpinned and has already drifted to Debian 13**: pin by digest and rebuild on a schedule.
- **Six `>=` ranges** (`pypdf`, `python-pptx`, `psycopg2-binary`, `sqlalchemy`, `alembic`, `pgvector`): pin the currently-tested versions via a constraints/lock file. Don't upgrade.
- The build context includes `tests/`, `reports/`, `docs/`, `dữ liệu/` and `EduDSS_UI_Reference_Kit/`. Allow-list only runtime files.
- The developer runs Python 3.12.4 while the image uses 3.11, so align them.

## 24. CI
- Hosted GitHub Actions: **NOT_VERIFIED**. There is no remote on either worktree.
- On this branch the workflow is **stale** (asserts 27 tables and head `797f72d1c666`) and would fail.

Hosted verification requires:
1. Replace the hard-coded asserts with `alembic heads` / metadata-derived counts; fix the head assertion in `tests/test_backup_recovery_integration.py`.
2. Add a remote and push the branch.
3. Record the run URL.
4. Add `pip-audit` and an image scan.

## 25. CD (minimum design; not implemented, host-agnostic)
1. **build** (CI) → 2. **test** (CI gates) → 3. **publish** image `registry/edudss:<semver>-<sha>` + SBOM + release manifest → 4. **staging deploy** (migrate job → app → readiness) → 5. **staging smoke** (health, login, Tier-1 answer, sync dry-run) → 6. **manual approval** (protected environment) → 7. **production**: pre-deploy backup → migrate job → deploy → 8. **post-deploy health** window with alerts → 9. **rollback**: redeploy the previous image tag; DB = restore the pre-deploy backup (forward-only migrations until downgrade paths are tested).

Nothing provider-specific is written until the hosting target is known.

## 26. Release identity (missing today)
One release = `semver` (e.g. `1.0.0-rc.1`) + Git SHA + image digest + Alembic head + ML model versions per tenant (registry) + RAG index version (embedding model + KB hash) + config schema version. Emit it as `release_manifest.json` in CI; show it in Admin "Giới thiệu" and in every log line.

## 27. Licensing
No GPL/AGPL in the 117 installed Python distributions. psycopg2-binary (LGPL with exceptions, used as a dynamically linked library) and certifi/tqdm (MPL-2.0, unmodified) are compatible with proprietary distribution provided notices are kept. Both embedding models are Apache-2.0 (attribution required). The TailAdmin template carries its own LICENSE and is outside the Docker context; confirm it is not redistributed. Fonts: `Inter` is referenced by name only (no bundled files found). **Action:** generate `THIRD_PARTY_NOTICES` (P2). This is not a legal opinion.

## 28. UI on this branch
*(filled from the capture of this branch; see below)*

Captured on **this branch** with an isolated data root and no cloud keys: **61 screenshots, 24 reachable pages** (Login + Student 5 + Lecturer 8, including "Duyệt tài liệu" + Admin 10), light and dark at desktop, with tablet/mobile samples. `evidence/ui_screens_branch/audit_results.json` records **0 exceptions, 0 horizontal overflow, 0 forbidden technical strings on Student pages, logout ✔ for all roles**.

Defects confirmed on this branch (all were fixed in the `D:\KLTN\code` worktree but are **uncommitted there and absent here**):

| Sev. | Defect | Evidence |
|---|---|---|
| **P1** | **Dark mode does not work**: after enabling the sidebar toggle every page stays light (`rgb(248,250,252)`); the sidebar and top-bar toggles hold contradictory states (two widget keys fighting) | all `*_dark_desktop.png`; `lecturer_duyet_tai_lieu_dark_desktop.png` |
| **P1** | **Mixed theme**: OS dark preference + Light toggle gives a dark background with dark sidebar text (nav labels near-invisible) | `student_trang_chu_os_dark_pref_light_toggle.png`, bg `rgb(11,19,43)` |
| **P1** | **Active sidebar item unreadable** (blue text on purple) | e.g. "Duyệt tài liệu" in `lecturer_duyet_tai_lieu_dark_desktop.png` |
| **P1** | Demo credentials box ("Dev/Evaluation", `admin/admin123`, …) rendered on the login page in every mode | `auth_login_light_desktop.png`; `auth_service.py:541` |
| P2 | Empty username or password gives the generic "Sai tên đăng nhập hoặc mật khẩu." (no field validation) and counts as a failed attempt | `login_form_cases` |
| P2 | Login card clipped at the top edge (`translateY(-64px)`) | login screenshots |
| P2 | ~90 px empty band above every page (leftover `st.markdown("---")`) | every page |
| P2 | Status badge hard-coded green | `dss/main.py:366` |
| P2 | Raw exception text in UI error messages (`st.error(f"…{e}")`, 24 sites in `main`; same code here) | source |
| P3 | English strings on login ("AI-POWERED LEARNING ANALYTICS", "AI Recommendation"), "1,000" separators, dataframe canvas light in dark, no double-submit lock, fragile `.st-emotion-cache-1ne20ew` selector | source/screens |

**Commercial importance of the P3 list:** English text and number formatting become **P2** for a Vietnamese-university customer (perceived quality); the double-submit lock stays P3 (authentication is idempotent). Dark mode is not optional polish on this branch: it is broken, hence P1.

**UI gate for this branch: FAIL.** Remedy: port the already-built fixes from the `D:\KLTN\code` worktree (theme single-source, `ui_kit.card`, `show_error`, login validation and production gating, readiness badge), then recapture and re-run the 39-test Playwright suite **on this branch**.

## 29. Operations documentation
Present: evaluator setup README; PostgreSQL backup runbook.

Missing, each blocking commercial hand-off (P1):
- installation guide (production)
- upgrade guide
- rollback guide
- full restore / DR guide
- tenant onboarding guide
- LMS connector guide
- AI provider configuration and "no external AI" guide
- incident troubleshooting / runbooks per alert
- monitoring guide
- release notes / changelog
- security hardening checklist

## 30. Deployment modes (one codebase)

| Aspect | A. Multi-tenant SaaS | B. Dedicated per university |
|---|---|---|
| Fit with current code | ✘ runtime is single-tenant per process | ✔ matches `EDUDSS_ORGANIZATION_ID` design |
| Database | shared cluster, RLS (needs chunk RLS) | own DB (RLS still on) |
| Secrets | per-tenant in a secret store (LMS tokens, AI keys, HMAC secret, pseudonym key) | per-deployment env/secret store |
| Domain | `tenant.edudss…` + wildcard TLS | university subdomain / own cert |
| Providers | per-tenant policy and budgets | deployment-level policy |
| Backup | per-tenant restore needs logical export per org | whole-DB backup |
| Monitoring | multi-tenant dashboards, noisy-neighbour limits | per-deployment |
| Cost | lower per tenant, higher engineering | higher per tenant, lower engineering |
| Operations | central | per-customer runbook |

Recommendation: ship **B (dedicated)** first. The same image and code are used, and a "tenant" is a deployment. SaaS requires runtime tenant context and the P1 items marked SaaS.

## 31. Commercial claim audit

| Claim / location | Classification | Required change |
|---|---|---|
| R² 0.992, RMSE 0.074, accuracy 0.875, Silhouette 0.412, DBI 0.831 (thesis, defense docs, `METRICS_THESIS_VS_CURRENT.md`) | **UNSUPPORTED** for commercial use (synthetic; R² artifact leaky) | Remove from sales/product material; keep thesis history untouched |
| "20,000 students" (README, reports) | **SUPPORTED as batch inference only** | Always say "20.000 bản ghi dự đoán theo lô" |
| Subscription quota up to 50,000 students (Admin settings) | **NEEDS_QUALIFICATION** | Quota is a licence field, not a verified capacity |
| "72h real Moodle/CMS simulation" (branch name) | **UNSUPPORTED** | Content = simulator + 5-min soak; no Moodle, no 72-hour run |
| "Moodle Webhook / Canvas" buttons + "✅ [Moodle Webhook]" toast (warehouse tab) | **NEEDS_QUALIFICATION** | Toast must say "(giả lập)" like the expander title |
| "thời gian thực / real-time" LMS sync | **UNSUPPORTED** for real LMS | "Đồng bộ định kỳ" once scheduled sync exists |
| `PRIVACY_PROVIDER_PAYLOAD_AUDIT.md`: pseudonym "non-reversible in practice" | **UNSUPPORTED** | Fixed salt + 24-bit hash is reversible by enumeration |
| `lms_connector.py`: "Sẵn sàng kết nối Moodle Core REST API / Canvas LTI 1.3" | **UNSUPPORTED** | No such adapter exists |
| "production-ready", "high availability", "zero downtime", "99%" | **not found** in UI/README (reports use them only in negated/qualified form) | – |
| "Hệ thống hoạt động" green badge (`dss/main.py:366`) | **UNSUPPORTED**: hard-coded, shown green regardless of backend state | Drive it from `readiness()` (done on `main` worktree, not here) |

## 32. Release gates

| Gate | Status | Basis |
|---|---|---|
| 3-Tier AI | **PASS** | accepted; AI gate 56/56 on PostgreSQL fresh checkout; no-key readiness ✔ |
| UI | **FAIL** | dark mode broken, mixed theme, unreadable active nav, demo credentials in production (§28) |
| Security | **FAIL** | demo credentials rendered in production; auto-provision gating; no TLS/edge controls |
| Secrets | **PASS** (code) / PARTIAL (ops) | no keys in tree here; no secret store |
| ML validity | **FAIL** | no real-data validation; uncalibrated; relative risk; synthetic claims |
| RAG | **PARTIAL** | governance works; benchmark unrepresentative; post-filter design |
| Database | **PASS** (with P2s) | 1,063 tests on PostgreSQL; RLS verified |
| Multi-tenancy | **PARTIAL** | DB-level yes; runtime single-tenant |
| LMS integration | **FAIL** | simulator only |
| Onboarding | **PARTIAL** | no regulations, program or cohort; simulator-only connector |
| Privacy | **FAIL** | weak pseudonyms; no deletion/retention |
| Load | **NOT_VERIFIED** | user concurrency never measured |
| Observability | **PARTIAL** | logs/IDs yes; no alerting |
| Backup/DR | **PARTIAL** | DB drill not re-verified on this schema; no combined DR |
| Docker | **PARTIAL** | builds and runs; unpinned base; excess content |
| CI | **FAIL** | stale asserts on this branch; hosted never run |
| CD | **FAIL** (NOT_IMPLEMENTED) | – |
| Licensing | **PASS** | no copyleft blockers; notices file needed |
| Operations | **FAIL** | handbook set missing |

## 33. Final decision

```
COMMERCIAL_RELEASE_READY   = NO
FIRST_REAL_CUSTOMER_READY  = NO
SAAS_READY                 = NO
DEDICATED_DEPLOYMENT_READY = NO
```

- **Commercial release / first real customer:** blocked by P0 #1–2 and P1 #3–5, 9, 14, 15, 17–19, 21–30 and 33. The software core is sound (1,063 tests pass on real PostgreSQL, RLS holds, deterministic decision logic, no-key operation). The blockers are validation, integration, privacy, security configuration, operability and release engineering, not algorithm choice.
- **SaaS:** additionally blocked by the single-tenant runtime (#16), chunk RLS (#12) and per-tenant secrets and providers (#20).
- **Dedicated deployment:** the architecture fits, but it needs the same P0/P1 set minus the SaaS-only items. **A pilot (non-commercial, supervised, with explicit "không dùng để ra quyết định chính thức" wording)** is feasible sooner once #1, #2, #21, #23, #24 and #26 are closed.
- **50K concurrency is not a requirement** unless a contract states it. A realistic first customer needs a measured 100–500 concurrent-session envelope.

## 34. Next implementation phase (recommended order)

**Phase C1: dedicated-deployment first-customer hardening**
1. P0: remove `nhanvien_export.csv` (confirm provenance) and exclude non-runtime dirs from the image; withdraw synthetic metrics from commercial material.
2. Security config: one `is_production()` predicate; hide demo credentials; auto-provision off; persistent lockout; PBKDF2 ≥600k / Argon2id.
3. Privacy: keyed per-tenant HMAC pseudonyms; drop "~GPA"; delete/export + retention.
4. Release engineering: fix stale CI/test asserts; add remote; hosted green run; digest-pinned base; lock file; release manifest/semver.
5. Regulations in PostgreSQL + admin approval workflow; program/cohort in onboarding.
6. Jobs: CLI + scheduler for incremental sync, reindex, backup; job status.
7. Edge: reference reverse proxy (TLS, headers, WebSocket), internal DB network; HTTP readiness + alert rules.
8. First-customer integration: CSV/SIS import or a Moodle adapter; mapping profile; contract tests.
9. ML/RAG validation on customer data: temporal validation, calibration or no-%, absolute risk thresholds, VI regulation retrieval benchmark → embedding decision.
10. Load test at 100/250/500 sessions; combined DR drill; operator handbook set.

Deferred (post-release, evidence-gated): HNSW, Redis, job broker, Kubernetes, XGBoost removal, embedding migration beyond the benchmark decision, SaaS runtime tenancy.
