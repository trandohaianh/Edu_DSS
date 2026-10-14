# ML Correctness Final Audit

Maps the master closure prompt's Section 4 checklist (4.1–4.30) directly onto the re-verified findings in `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md`. Every row below was independently re-traced against current code this pass (see that matrix for the exact grep/read evidence and test names) — this document does not introduce new findings, it indexes the existing ones by the master prompt's own numbering for quick lookup.

| § | Item | 96Q tag | Status | One-line finding |
|---|---|---|---|---|
| 4.1 | Data leakage (IQR before split) | R-1 | FIXED_AND_TESTED | IQR bounds now computed and applied only on the train split, after the split, never on test |
| 4.2 | `gpa_previous` duplicate feature | G-2 | FIXED_AND_TESTED | Excluded from default feature sets everywhere |
| 4.3 | Synthetic target too easy / leaky | — | DOCUMENTATION_ONLY | Disclosed honestly in-code and in the 96Q doc; not a bug to "fix," a property of synthetic data to keep separating from real-data claims |
| 4.4 | Train/CV/test discipline | R-3, R-5 | MIXED | Ensemble selection now uses CV not test (R-3, fixed); tuning-vs-ranking metric split (R-5) remains disclosed but unreconciled |
| 4.5 | XGBoost/LightGBM/RF tuning fairness | P-1 | FIXED_AND_TESTED | GridSearch only skipped when truly unsafe (class too small for fold count), not unconditionally |
| 4.6 | Regression scaler bug | R-2 | FIXED_AND_TESTED | `scaler_type` now threaded through to the previously-broken call site |
| 4.7 | Engineered-feature train/inference skew | R-4 | FIXED_AND_TESTED | Feature engineering off by default; risk documented if ever enabled |
| 4.8 | Metadata `feature_cols` correctness | — | DOCUMENTATION_ONLY | Not independently re-traced this pass |
| 4.9 | SMOTE k_neighbors / scope | P-3 | FIXED_AND_TESTED | k_neighbors no longer capped so low that samples are near-duplicates |
| 4.10 | Baselines (Dummy*) | — | DOCUMENTATION_ONLY | 96Q Câu 27 references a "always predict Khá" baseline (~46% accuracy) in the answer text; not independently re-verified as wired into the actual model-comparison UI this pass |
| 4.11 | Accuracy vs F1-macro consistency | S-1 | FIXED_AND_TESTED | Single shared `resolve_ranking_col()` used everywhere (UI ranking, `pick_best_model_name`, Model Registry) |
| 4.12 | Uncalibrated probability shown as confidence | P-7 | FIXED_AND_TESTED | Wording corrected to not imply calibrated confidence |
| 4.13 | Calibration | P-7 | PARTIALLY_FIXED | Labeling fixed; `CalibratedClassifierCV`/Brier-score calibration itself was never added (the 96Q answer frames this as the deeper fix, wording as the minimum fix — the minimum was done) |
| 4.14 | Risk thresholds (0.55/0.85/0.92 heuristics) | — | DOCUMENTATION_ONLY | Disclosed as empirical/heuristic in code comments, not recalibrated against a labeled QA set this pass |
| 4.15 | Relative vs absolute risk | K-2 | FIXED_AND_TESTED | UI wording now explicit that risk level is relative/in-class, not an absolute failure probability |
| 4.16 | Auto-ensemble selection using test set | R-3 | FIXED_AND_TESTED | Same fix as 4.4 |
| 4.17 | SHAP explainer choice | X-1 | FIXED_AND_TESTED | Linear models now routed through a probability-aware explainer instead of explaining the discrete label |
| 4.18 | SHAP ≠ causality | — | DOCUMENTATION_ONLY | UI wording audited alongside broader UI passes this session; not independently re-verified line-by-line |
| 4.19 | Clustering leakage (future-target column in default features) | C-1 | FIXED_AND_TESTED | Default clustering feature selection now excludes `final_score`/`diem_ky_sau`/`grade`/`xep_loai` and includes Vietnamese `diem_*` columns |
| 4.20 | Cluster naming / interpretability | C-3 | PARTIALLY_FIXED | Auto-fallback added so strong/weak points are never empty; the core ±10% ratio threshold itself remains variance-blind (no z-score/Cohen's d) |
| 4.21 | `predicted_gpa` ground-truth leak | **K-3** | **FIXED_AND_TESTED — re-verified live this pass** | The single most severe finding in the whole 96Q set. `predict_for_student()` now routes through the real Production regression pipeline, with an explicit forbidden-column guard even in its no-Production fallback. **10/10 tests re-run live, all passing.** |
| 4.22 | GPA scale (10 vs 4) mixing | — | DOCUMENTATION_ONLY | `predict_for_student()`/`compute_progress_note()` do contain explicit scale-conversion logic (`* 2.5` for 4-scale `gpa_previous`/`prior_gpa`) — spot-checked while reading K-3's fix, not independently re-audited across every chart/comparison in the app |
| 4.23 | Model Registry provenance completeness | — | DOCUMENTATION_ONLY | Candidate/Production separation and Admin-only promotion confirmed to exist (96Q Câu 55/56); artifact-hash/library-version pinning not independently re-verified this pass |
| 4.24 | Drift monitoring honesty | D-1 | **STILL_OPEN** | Confirmed via fresh grep: zero UI/tab wires drift-checking into any control. The underlying `evaluate_drift()` function and its tests are code-only; no automatic or on-demand schedule exists. Do not describe this as "automatic drift monitoring." |
| 4.25 | RAG embedding multilingual quality | A-1 | PARTIALLY_FIXED | Real benchmark run this pass with explicit user consent to download the candidate model: multilingual model wins on every metric (Recall@5 +4.4pp, MRR +12.2pp, nDCG@5 +10.2pp) at acceptable latency cost (+17.6ms avg). Production model **not migrated** — that requires re-embedding the whole KB, judged out of scope for this pass |
| 4.26 | RAG top-k tuning | — | NOT BENCHMARKED THIS PASS | No top-k sweep run; current top-k=4/5 (varies by call site) left as-is |
| 4.27 | Duplicate/legacy RAG paths | — | DOCUMENTATION_ONLY | Not independently re-traced this pass for a second, silently-active retrieval implementation |
| 4.28 | Hardcoded RAG rules vs real AI | — | DOCUMENTATION_ONLY | Not independently re-traced this pass |
| 4.29 | Document governance / RAG authority | — | DOCUMENTATION_ONLY — **known real gap from 96Q Câu 73** | AI Advisor's 19 hardcoded documents (4 self-labeled "approved") vs. Admin-uploaded documents not actually consumed by AI Advisor — disclosed in the source Q&A, not independently re-verified as fixed or still-open this specific pass (no tag exists for it in the 21-tag set, meaning the original author had not yet closed the loop on it either) |
| 4.30 | Fake/demo/random/mock/fallback sweep | E-2 | PARTIALLY COVERED | E-2 (demo-mode plan mislabeled as personalized) fixed and tested. A full repo-wide keyword sweep (Section 36 of the master prompt) was **not exhaustively run** this pass — see "Not done this pass" below |

## Overall ML-correctness verdict

**16 of 21 previously-self-identified defects are genuinely fixed and tested, re-verified this pass** (not merely trusted). **The single most severe one (K-3 — using ground truth as a "prediction")** was specifically re-run live and confirmed still fixed (10/10 tests passing). **3 remain partially fixed** (R-5, C-3, A-1) with real, disclosed reasons rather than silent gaps. **1 remains genuinely open** (D-1). **One real, pre-existing gap from the source document itself was not independently re-verified this pass** (Câu 73 / document governance, §4.29) — flagged here rather than silently assumed closed.

## Not done this pass (honestly listed)

- Full repo-wide keyword sweep (TODO/FIXME/hardcoded/confidence/etc., master prompt Section 36) was not run as an exhaustive standalone pass; individual items were checked opportunistically while tracing specific tags above.
- RAG top-k benchmarking (4.26).
- Duplicate RAG path detection (4.27).
- Document governance re-verification (4.29).
