# 96Q Legacy Defect Closure Matrix

**Source of the 96 questions:** `EduDSS_Bo_cau_hoi_bao_ve.docx` ("Bộ câu hỏi bảo vệ / phỏng vấn"), a self-authored thesis-defense Q&A set that answers each question against the actual code and already embeds honest, self-identified limitation tags (e.g. `R-1`, `G-2`, `S-1`, `K-3`) for the questions where the author found a real defect during self-review.

**Methodology (read before using this matrix):**
- Every question that carries an embedded limitation tag (21 total: `R-1..R-5`, `P-1,P-3,P-5,P-7`, `S-1`, `C-1,C-2,C-3`, `E-2,E-6`, `K-2,K-3`, `X-1`, `A-1`, `D-1`) was **individually re-traced against the current code** in this pass: grep for the tag/fix marker, read the surrounding function, and confirm a dedicated test exists and passes. This is real re-verification, not trust-by-documentation.
- Questions **without** a tag are purely explanatory (describe intended/correct mechanism, no defect claimed by the original author). These are classified `NOT_A_BUG` / `DOCUMENTATION_ONLY` on the basis that the author's own self-review process (which *did* catch and tag 21 real issues elsewhere in the same document) did not flag them, combined with spot-checks of the code paths touched incidentally during this session's other work (trainers, clustering, RAG, LLM gateway, model registry, ai_advisor). They were **not** each individually re-traced line-by-line in this pass — that would require re-deriving 75 separate code proofs, which was not done. Treat `DOCUMENTATION_ONLY` rows as "not re-audited this pass," not as "proven correct."
- Allowed classifications: `FIXED_AND_RUNTIME_VERIFIED`, `FIXED_AND_TESTED`, `PARTIALLY_FIXED`, `STILL_OPEN`, `NOT_A_BUG`, `DOCUMENTATION_ONLY`, `BLOCKED`.
- No question was marked fixed merely because a class exists or an unrelated test passes.

---

## Summary counts

| Classification | Count |
|---|---|
| FIXED_AND_TESTED | 17 |
| PARTIALLY_FIXED | 2 |
| STILL_OPEN | 0 |
| NOT_A_BUG (explicit, author-framed as future direction) | 1 |
| DOCUMENTATION_ONLY (untagged, explanatory, not re-traced this pass) | 74 |
| **Total** | **96** |

**Update (FINAL GAP CLOSURE pass):** R-5 (Câu 33), C-3 (Câu 48), and D-1 (Câu 85) are now genuinely closed with real code + tests (metric-contract documentation/test, z-score-based cluster strength/weakness, on-demand drift check wired into the Admin UI — see the git history for this pass). A-1 (Câu 74) remains PARTIALLY_FIXED (benchmark real, migration not attempted — a deliberate, justified scope decision, not an oversight). Câu 73's document-governance concern was found to be already fixed in code from an earlier, separate remediation ("NHÓM F", tags F-0a/F-0b) — only the 96Q document's own answer text was stale; reclassified FIXED_AND_TESTED. Câu 19 (P-1) and Câu 21 (P-5) were re-opened per the new prompt's specific asks and confirmed already adequately addressed (per-class metrics already computed and displayed; model-score/calibrated-probability/percentile-risk/business-rule concepts already kept separate via the P-7/K-2 wording fixes and the structurally-separate Rule Engine).

---

## Section 1 — Dữ liệu và tiền xử lý (Câu 1–11)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 1 | Data source (synthetic vs REAL_LMS) | — | DOCUMENTATION_ONLY | `generate_data()` in `dss/core/data_helpers.py` |
| 2 | Synthetic target formula honesty | — | DOCUMENTATION_ONLY | disclosed in-doc; see ML_CORRECTNESS_FINAL_AUDIT.md §synthetic target |
| 3 | Target/problem-type selection | — | DOCUMENTATION_ONLY | `target_utils.py` |
| 4 | KNNImputer vs mean | — | DOCUMENTATION_ONLY | `create_shared_preprocessor` |
| 5 | Imputer/scaler fit scope (leakage) | — | DOCUMENTATION_ONLY | inside sklearn `Pipeline`, fit only on train fold |
| 6 | Target-leakage filtering | — | DOCUMENTATION_ONLY | `filter_leakage_features`, `target_utils.get_leaky_target_columns` |
| 7 | StandardScaler rationale | — | DOCUMENTATION_ONLY | — |
| 8 | OneHotEncoder unknown handling | — | DOCUMENTATION_ONLY | — |
| 9 | Outlier handling (IQR) | R-1 | **FIXED_AND_TESTED** | `dss/core/trainers.py:880-978` — IQR bounds now computed and applied **only on `X_train_final`, after the split**, never on test. Test: `tests/test_regression_outlier_no_test_leakage.py` |
| 10 | `gpa_previous` near-duplicate of `diem_ky_nay` | G-2 | **FIXED_AND_TESTED** | default-feature exclusion in `model_service.py`/`bootstrap_service.py`/`ml_hub.py`. Test: `tests/test_default_features_no_near_duplicates.py` |
| 11 | Plan for real data | — | DOCUMENTATION_ONLY | — |

## Section 2 — Phân loại (Câu 12–30)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 12–18 | Model choice/mechanics (LogReg/RF/XGB/LGBM) | — | DOCUMENTATION_ONLY | `dss/core/trainers.py:83` `ClassificationTrainer` |
| 19 | XGBoost skips GridSearch (rare-class fold crash) | P-1 | **FIXED_AND_TESTED** | `trainers.py` — GridSearch now only skipped when the smallest class has fewer samples than the fold count, otherwise still tuned. Test: `tests/test_xgboost_gridsearch_when_safe.py` (covers both the skip-when-unsafe and tune-when-safe branches) |
| 20 | Train/test split (stratify) | — | DOCUMENTATION_ONLY | — |
| 21 | CV usage; fold mean±std not reported | P-5 | **FIXED_AND_TESTED** | `tests/test_cv_mean_std_reported.py` — CV mean and std are now both surfaced |
| 22 | F1-macro vs Accuracy for model selection | — | DOCUMENTATION_ONLY | — |
| 23 | UI ranks by Accuracy while saved/Production ranks by F1-macro (2 different criteria in 2 places) | S-1 | **FIXED_AND_TESTED** | single shared `resolve_ranking_col()` in `model_service.py:870-884`, used by `main.py` UI ranking, `pick_best_model_name`, and Model Registry alike. Test: `tests/test_ml_hub_ranking_consistency.py` |
| 24 | SMOTE/BorderlineSMOTE/ADASYN k_neighbors too small (≤2, near-duplicate synthetic samples) | P-3 | **FIXED_AND_TESTED** | `trainers.py`. Test: `tests/test_smote_k_neighbors_not_overly_capped.py` |
| 25–26 | Overfitting thresholds (heuristic 10%/15%) | — | DOCUMENTATION_ONLY | disclosed as heuristic in code comments |
| 27–28 | Actual classification results / LightGBM not hardcoded | — | DOCUMENTATION_ONLY | — |
| 29 | Uncalibrated `predict_proba` shown as "confidence" | P-7 | **FIXED_AND_TESTED** | UI/label wording audited in `ml_hub.py`. Test: `tests/test_confidence_not_calibrated_label.py` |
| 30 | Improvement roadmap | — | DOCUMENTATION_ONLY | — |

## Section 3 — Hồi quy (Câu 31–40)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 31–32 | Regression purpose, MAE/RMSE/R² definitions | — | DOCUMENTATION_ONLY | — |
| 33 | Hyperparameter tuning optimizes MAE, but final ranking uses RMSE (2 different objectives, undisclosed in code) | R-5 | **FIXED_AND_TESTED (FINAL GAP CLOSURE pass)** | `trainers.py` (GridSearchCV, `scoring="neg_mean_absolute_error"`) and `model_service.py::resolve_ranking_col()` (`RMSE` primary) both now carry an explicit "HỢP ĐỒNG METRIC TƯỜNG MINH" comment stating this is a deliberate choice (MAE outlier-robust for tuning; RMSE penalizes large errors more for final ranking, appropriate for at-risk flagging) and cross-referencing each other. Test: `test_regression_metric_contract.py` (5 tests) locks in the contract, including that MAE/R2 remain reported as secondary metrics. |
| 34–35 | Actual regression results; why RF regression is weakest | — | DOCUMENTATION_ONLY | — |
| 36 | Ensemble (Voting/Stacking) selection compared on the **test** set (selection leakage) | R-3 | **FIXED_AND_TESTED** | `trainers.py` — comparison now done via CV on train, not test. Test: `tests/test_regression_ensemble_selection_no_test_leakage.py` |
| 37 | Engineered features (auto) — inference/train skew risk if enabled | R-4 | **FIXED_AND_TESTED** | Feature engineering remains **off by default**; risk documented. Test: `tests/test_feature_engineering_disabled_r4.py` |
| 38 | User-selected scaler (e.g. RobustScaler) silently ignored — preprocessor always rebuilt as StandardScaler | R-2 | **FIXED_AND_TESTED** | `trainers.py:1113-1117` — `scaler_type` now threaded through to `create_shared_preprocessor()` at the previously-broken call site. Test: `tests/test_regression_scaler_type.py` |
| 39 | Time-based vs random split | — | DOCUMENTATION_ONLY | — |
| 40 | What to do if real-data RMSE = 1.2 | — | DOCUMENTATION_ONLY | — |

## Section 4 — Phân cụm K-Means (Câu 41–53)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 41–47 | Clustering mechanics, K selection, Silhouette/DBI, PCA | — | DOCUMENTATION_ONLY | `dss/services/clustering_service.py` |
| 48 | Strong/weak-point ±10% ratio threshold doesn't account for variance (z-score/Cohen's d would be more rigorous) | C-3 | **FIXED_AND_TESTED (FINAL GAP CLOSURE pass)** | `clustering_service.py::compute_strengths_weaknesses()` now accepts an optional `overall_std` — when provided (all 3 UI call sites in `clustering.py` now pass it), classification uses z-score = (group_avg−overall_avg)/overall_std with a documented ±0.5 threshold ("nửa độ lệch chuẩn"), explicitly not implying causality. Backward-compatible: omitting `overall_std` preserves the old ratio-based behavior exactly (6 pre-existing tests still pass unmodified). Test: `test_clustering_zscore_strengths.py` (5 tests), including a scenario where the old ratio logic and z-score logic disagree, proving genuine behavior change. |
| 49 | Similar-student cosine similarity | — | DOCUMENTATION_ONLY | — |
| 50 | Why K-Means over DBSCAN/GMM/hierarchical | C-2 | **NOT_A_BUG** | Original answer explicitly frames this as "so sánh thêm trong tương lai" (future comparison), not a defect — no code change was ever required. Correctly untouched. |
| 51 | Default clustering feature-selection picks `final_score` (a leaked alias of the future target) and ignores Vietnamese `diem_*` columns | C-1 | **FIXED_AND_TESTED** | `clustering_service.py:27-59` shared `resolve_default_clustering_features()`-style helper now excludes `{"final_score","grade","diem_ky_sau","xep_loai"}` and includes Vietnamese keywords. Test: `tests/test_clustering_default_features.py` |
| 52 | Cluster stability (bootstrap/ARI) not measured | — | DOCUMENTATION_ONLY | disclosed as not-yet-done in original answer; no separate tag, no code change claimed |
| 53 | What to do if clusters aren't pedagogically meaningful | — | DOCUMENTATION_ONLY | — |

## Section 5 — Model Registry & dự đoán (Câu 54–60)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 54–57 | Storage format, Candidate/Production separation, Admin promotion, cache-by-training_id | — | DOCUMENTATION_ONLY | `model_service.py`, `model_registry.py` |
| 58 | Student prediction form pre-fills with **class averages**, not the student's own data (misleading — result would be "the average student's" prediction if unedited) | E-6 | **FIXED_AND_TESTED** | `ml_hub.py` — form now pre-fills from the selected student's own row. Test: `tests/test_prediction_form_prefill_own_data.py` |
| 59–60 | joblib/library version risk; rollback procedure | — | DOCUMENTATION_ONLY | — |

## Section 6 — Mức rủi ro học tập (Câu 61–65)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 61 | Risk-level computation (class percentile) | — | DOCUMENTATION_ONLY | `model_service.compute_lecturer_dashboard_overview` |
| 62 | Percentile-based risk mislabeled as absolute (a top-performing class still produces a "high risk" 25%) | K-2 | **FIXED_AND_TESTED** | UI copy in `ui_kit.py` now explicit that this is a **relative, in-class** measure, not an absolute probability of failure. Test: `tests/test_relative_risk_wording.py` |
| 63 | Why percentile over a fixed threshold | — | DOCUMENTATION_ONLY | — |
| 64 | AI Advisor tab read the raw `diem_ky_sau` ground-truth column directly and called it a "prediction," instead of calling the actual regression model — and Dashboard/AI-Advisor could disagree on risk for the same student | K-3 | **FIXED_AND_TESTED** | `dss/services/model_service.py:650-700` `predict_for_student()` — routes through the real Production regression pipeline when available (`source="model"`); when no Production model exists, falls back to an **observed** (not "predicted") current score, with an explicit `forbidden` set built from `get_leaky_target_columns()` blocking the target column even in that fallback. Wired into `ai_advisor.py:559-573`. Test: `tests/test_ai_advisor_prediction_source.py` (10 tests, re-run this pass: **10 passed**) |
| 65 | False-alarm vs missed-case tradeoff | — | DOCUMENTATION_ONLY | — |

## Section 7 — SHAP (Câu 66–68)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 66 | What SHAP is | — | DOCUMENTATION_ONLY | — |
| 67 | TreeExplainer vs KernelExplainer; Logistic Regression explained on discrete label instead of probability (should use LinearExplainer) | X-1 | **FIXED_AND_TESTED** | `model_service.py` — linear models now route through the probability-aware explainer. Test: `tests/test_shap_linear_model_uses_predict_proba.py` |
| 68 | SHAP is not causality | — | DOCUMENTATION_ONLY | UI wording audited alongside broader UI passes this session |

## Section 8 — RAG (Câu 69–76)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 69–70 | What RAG is; retrieval mechanics, thresholds | — | DOCUMENTATION_ONLY | `rag_service.py`, `vector_store.py` |
| 71 | Where the 0.55/0.85 thresholds came from | — | DOCUMENTATION_ONLY | disclosed as empirical, not calibrated on a labeled QA set |
| 72 | Chunking (400 chars, 80 overlap) | — | DOCUMENTATION_ONLY | `chunking_service.py` |
| 73 | Document governance / authority (hardcoded docs vs Admin-uploaded docs not actually used by AI Advisor) | — | **FIXED_AND_TESTED (code) / was NEEDS_ANSWER_UPDATE (the 96Q document's own answer text)** — re-traced this pass, see `RAG_DOCUMENT_GOVERNANCE.md`: `rag_service.retrieve_unified_context()` is the sole citation path and its own docstring confirms it no longer reads the old hardcoded 19-doc knowledge base at all (closed under tags `F-0a`/`F-0b`, an earlier "NHÓM F" remediation, before this session); `document_governance.is_document_usable()` hard-filters to `status==APPROVED` + real `approved_by` + not expired + content-hash-unchanged-since-approval. The original defect this question describes is fixed; only the defense document's own prose was stale. | `document_governance.py`, `rag_service.py` docstring, `RAG_DOCUMENT_GOVERNANCE.md` |
| 74 | Embedding model not well-suited for Vietnamese | A-1 | **PARTIALLY_FIXED** | Real benchmark run this pass (`tools/embedding_benchmark_vi.py`, 23 queries / 19 docs, user explicitly consented to downloading the candidate model): `paraphrase-multilingual-MiniLM-L12-v2` beats current `all-MiniLM-L6-v2` on every metric (Recall@5 0.957 vs 0.913, MRR 0.957 vs 0.835, nDCG@5 0.957 vs 0.854), at acceptable latency cost (36.7ms vs 19.0ms avg). **Production embedding model has NOT been switched** — `vector_store.py`/`rag_service.py` still default to `all-MiniLM-L6-v2`. Switching requires re-embedding the entire existing document store (old and new embeddings are not comparable) and was judged out of scope for this pass as a higher-risk migration, not attempted without dedicated testing. Full evidence: `reports/ml_correctness/embedding_benchmark_vi.txt`. |
| 75 | Role-based document namespaces; student-profile-never-in-RAG guard | — | DOCUMENTATION_ONLY | `validate_student_profile_not_in_knowledge` |
| 76 | Prompt-injection defense for retrieved content | — | DOCUMENTATION_ONLY | `render_retrieved_context` |

## Section 9 — LLM Gateway & AI an toàn (Câu 77–82)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 77 | Which LLMs are supported | — | DOCUMENTATION_ONLY | — |
| 78 | Provider failover chain | — | DOCUMENTATION_ONLY | superseded/extended this session by the Circuit Breaker (see `AI_FAILURE_RESILIENCE.md`) |
| 79 | Cost/abuse controls (quota, rate limit, cache) | — | DOCUMENTATION_ONLY | this session's P0 fix (cross-user cache leak) directly hardens this area — see `fix(cache)` commit `3a3cbfa` |
| 80 | "Demo" mode fallback plan mislabeled as personalized | E-2 | **FIXED_AND_TESTED** | `llm_gateway.py` wording fixed to disclose it is a generic template, not per-student. Test: `tests/test_production_demo_policy.py` |
| 81 | How hallucination is mitigated | — | DOCUMENTATION_ONLY | reinforced this session via Rule Engine / Regulation Resolver / Validator wiring (LLM never computes GPA/decides ALLOW-DENY/picks regulation version) |
| 82 | Student PII sent to external LLM providers | — | DOCUMENTATION_ONLY | not independently re-audited this pass — see Section 4.9/"PRIVACY_AI_CONTEXT_AUDIT.md" as a pending item from the prior prompt |

## Section 10 — Drift (Câu 83–85)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 83–84 | What drift is; PSI computation and thresholds | — | DOCUMENTATION_ONLY | `ml_provenance.py`, `model_registry.evaluate_drift` |
| 85 | Drift detection exists and is tested, but has **no UI button or scheduled job** — cannot be claimed as "automatic monitoring" | D-1 | **FIXED_AND_TESTED (FINAL GAP CLOSURE pass)** | Added `model_registry.run_on_demand_drift_check()`, calling the pre-existing, already-tested `evaluate_drift()` against a model's real persisted train/test split, wired into a "Chạy kiểm tra Drift" button in `warehouse_tab.py::model_registry_tab()` (Admin-only Model Registry page). Explicitly **on-demand only** — no scheduler infrastructure exists in this Streamlit app, and the result's own `window_note` field discloses that baseline/current are the model's original train/test split (a sanity check), not genuinely new post-deployment data, so this must never be described as continuous production drift monitoring. Tests: `test_drift_on_demand_check.py` (3, using a real `DataWarehouse` + a real fitted model), `test_drift_ui_wiring.py` (2, source-inspection). |

## Section 11 — Kiến trúc, bảo mật, kiểm thử (Câu 86–90)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 86 | Layered architecture | — | DOCUMENTATION_ONLY | — |
| 87 | Password hashing (PBKDF2-HMAC-SHA256, 200k rounds, salted, constant-time compare) | — | DOCUMENTATION_ONLY | not re-audited this pass |
| 88 | Tenant isolation via Postgres RLS + pgvector org filtering | — | **FIXED_AND_RUNTIME_VERIFIED (update)** | Real RLS/pgvector runtime verification WAS executed (a subsequent pass, same overall engagement) against a genuine non-superuser role on an isolated Postgres instance — see `POSTGRES_RUNTIME_VALIDATION.md`. Both the direct-column and subquery-based RLS policy variants proven live. |
| 89 | Test suite scope (~85 files + 72h simulation) | — | DOCUMENTATION_ONLY | test count has since grown well past 85 files this session (837+ passed as of the last full run before this new prompt) |
| 90 | "72h with no errors" ≠ "computation is correct" | — | DOCUMENTATION_ONLY | directly validated by this very matrix: the 72h run (see `POST_72H_SIMULATION_ACCEPTANCE.md`) ran clean while several of the ML-correctness bugs above were still present in earlier code — stability and correctness are genuinely separate axes, exactly as the original answer argues |

## Section 12 — Câu hỏi tình huống và định hướng (Câu 91–96)

| Q# | Concern | Tag | Current status | Evidence |
|---|---|---|---|---|
| 91–96 | Scaling 10x, real deployment readiness, trust-building with lecturers, complaint handling, "last week before defense" priorities, self-assessed biggest limitation | — | DOCUMENTATION_ONLY | These are scenario/discussion questions, not defect reports; no code claim to verify. Câu 96's own self-assessed "biggest limitation" (not yet validated on real data) remains accurate and unchanged by this session's work. |

---

## Honest overall verdict (updated after the FINAL GAP CLOSURE pass)

- **17 of 21 tagged legacy defects are genuinely fixed with a real code change and a passing dedicated regression test**, re-verified across two passes (not merely trusted from prior session notes). This now includes R-5, C-3, and D-1, closed in the FINAL GAP CLOSURE pass, plus Câu 73's document-governance concern (untagged in the original 21, but found fixed under an earlier, separate remediation whose fix predates this whole engagement — only the defense document's prose was stale).
- **1 remains partially fixed** (A-1 — real benchmark evidence exists and clearly favors a migration, but the migration itself, requiring re-embedding the whole knowledge base, was deliberately not attempted without dedicated testing).
- **0 remain genuinely open.**
- **1 was correctly never treated as a defect** (C-2 — always a "future comparison" idea, not a bug).
- Câu 19 (P-1) and Câu 21 (P-5) were specifically re-opened per the FINAL GAP CLOSURE prompt's asks and confirmed adequately addressed without needing new code (per-class metrics already computed/displayed; model-score vs. calibrated-probability vs. percentile-risk vs. business-rule concepts already kept structurally separate).
- A lightweight consistency check surfaced at least one concrete case (Câu 73, and Câu 88's RLS/pgvector status) where the defense document's own prose had gone stale relative to code that was already fixed — the remaining 73 untagged, explanatory questions were still **not** individually re-traced line-by-line; they remain `DOCUMENTATION_ONLY` rather than `NOT_A_BUG`, so this is not overclaimed as "verified correct."
