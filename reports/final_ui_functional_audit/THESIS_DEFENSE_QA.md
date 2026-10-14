# EduDSS — Thesis Defense Q&A Bank

Every answer below is grounded in `RELEASE_FREEZE.md`, `FINAL_ARCHITECTURE_TRUTH.md`,
`FINAL_SYSTEM_CAPABILITY_MATRIX.csv`, `THESIS_FORMULA_SHEET.md`, `ISSUE_REGISTER.csv`, and
direct source-code verification performed this session. Each entry: short answer, detail,
evidence, safe claim, must-not-claim, likely follow-up.

## A. System Overview

**A1. What is EduDSS?**
Short: A Streamlit-based multi-role Decision Support System for academic risk prediction,
diagnosis, and learning-plan recommendation.
Detail: Three roles (Student, Lecturer, Admin) share one app with role-based navigation
and function-level access control; core capabilities are ML prediction (classification +
regression), K-Means clustering, a rule-based diagnosis/recommendation engine, an AI
advisor layered with RAG, and administrative model/version governance.
Evidence: `dss/main.py`, `dss/core/roles.py`.
Safe claim: "A working, tested, multi-role academic DSS prototype."
Must not claim: "A deployed, institution-scale production system."

**A2. Why Streamlit and not a full web stack (React/Django/etc.)?**
Short: Speed of development for a data-science-heavy, single-team academic project.
Detail: Streamlit lets Python own both UI and logic without a separate frontend/backend
split — appropriate for a thesis-scale prototype, not a claim of enterprise scalability.
Safe claim: "A pragmatic choice matching project scope and team size."
Must not claim: "Chosen for production scalability."

**A3. How many tests does the project have and are they all passing?**
Short: 426 total (403 non-E2E + 23 E2E), all passing at freeze.
Evidence: `RELEASE_FREEZE.md`, `TEST_RESULTS.md`.
Must not claim: 100% code coverage — test count is not coverage percentage.

**A4. What does "DEMO_SYNTHETIC" vs "REAL_LMS" mode mean?**
Short: An environment switch (`EDUDSS_MODE`) that gates synthetic/demo data paths off in
a production-like mode, replacing them with honest "unavailable" states instead of
fabricated content.
Evidence: `dss/config.py`.
Must not claim: REAL_LMS mode means a real LMS is connected — it means demo shortcuts are
disabled; there's still no live external LMS.

## B. Roles & Access Control

**B1. How is role-based access enforced?**
Short: Two independent layers — sidebar navigation filtering (`TAB_ACCESS`) and a
function-level `@require_role(...)` decorator checked against session state set only by
the real login flow.
Evidence: `dss/core/roles.py`, `dss/services/auth_service.py`.
Safe claim: "Verified by repo-wide grep: zero routes bypass the decorator."
Must not claim: Formal, externally-audited RBAC certification.

**B2. Can a Student see another student's data?**
Short: No — every Student-facing query is filtered to the logged-in student's own ID.
Evidence: `VISUAL_ACCEPTANCE_MATRIX.csv` (Data Isolation column, all Student rows = "Own
ID only").
Must not claim: Formally proven via static analysis — verified via targeted functional
tests and code read, not an automated isolation proof.

**B3. What can Admin do that Lecturer cannot?**
Short: Model Registry promotion/rollback, AI provider key configuration, org-wide reports,
user visibility (read-only), Knowledge Base document upload.
Evidence: `dss/core/roles.py` TAB_ACCESS table.

## C. Machine Learning — Classification

**C1. Which classification algorithms are implemented?**
Short: Logistic Regression (Softmax), Random Forest, XGBoost, LightGBM.
Evidence: `dss/core/trainers.py::ClassificationTrainer`.

**C2. What hyperparameters are tuned for each?**
Short: RF = 24 combos (120 fits w/ 5-fold CV); LightGBM = 8 combos (40 fits); Logistic
Regression = 3 combos (15 fits); XGBoost = fixed params, no GridSearchCV, 1 fit.
Evidence: `THESIS_FORMULA_SHEET.md` §8.
Must not claim: All 4 algorithms are tuned with equal depth — XGBoost classifier is a
documented exception.

**C3. Why does XGBoost Classifier skip GridSearchCV?**
Short: A documented workaround for a crash ("Invalid classes inferred from unique values
of y") that occurs when rare multi-class CV folds become label-non-contiguous.
Evidence: `dss/core/trainers.py` comment at the XGBoost classifier branch.
Safe claim: "A real, disclosed engineering tradeoff, not an oversight."

**C4. How is class imbalance handled?**
Short: SMOTE inside a pipeline, fit only on training folds.
Evidence: `dss/core/trainers.py`, `THESIS_FORMULA_SHEET.md` §1.

## D. Machine Learning — Regression

**D1. Which regression algorithms are implemented and with what grids?**
Short: Linear Regression (0 hyperparams), Random Forest (12 combos/60 fits), XGBoost (18
combos/90 fits), LightGBM (18 combos/90 fits).
Evidence: `THESIS_FORMULA_SHEET.md` §9, `dss/core/trainers.py::RegressionTrainer`.
Must not claim: A historical 36-combination RF grid — never executed; single current
source of truth is 12/60.

**D2. Why is regression R² so high on the sample dataset?**
Short: The sample dataset's target is a synthetic deterministic linear formula of the
input features plus small noise — not an independently measured real-world value.
Detail: `diem_ky_sau = 0.60*diem_ky_nay + 0.15*diem_giua_ky + 0.10*diem_du_an +
0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5) + noise(σ=0.08)`, clipped and then
clamped to within ±1.5 of `diem_ky_nay`.
Evidence: `dss/core/data_helpers.py::generate_data()`; `THESIS_FORMULA_SHEET.md` §10.
Safe claim: "High R² on the bundled sample data is expected and is a synthetic-data
construction artifact, not evidence of real-world predictive power."
Must not claim: "The model achieves this accuracy on real institutional data" — no real
institutional dataset has been used.

**D3. How do you prevent data leakage?**
Short: `train_test_split` happens before any preprocessing; imputation/scaling/encoding/
SMOTE are wrapped in a pipeline fit only inside GridSearchCV's training folds; a separate
`filter_leakage_features()` guard removes target-correlated columns before training starts.
Evidence: `dss/core/trainers.py` (direct code read this session).
Safe claim: "Leakage-guard discipline is real and independent of the synthetic-data R²
question above — they are two separate topics."

## E. Clustering

**E1. What does the clustering feature do?**
Short: K-Means groups students by similarity; Elbow/Silhouette assist `k` selection; PCA
projects to 2D for visualization.
Evidence: `dss/services/clustering_service.py`.
Must not claim: "K-Means predicts a student's future outcome" — it is unsupervised
grouping, not prediction.

**E2. How is `k` chosen?**
Short: Elbow method (inertia curve) plus Silhouette score, both computed and shown, final
choice can be Lecturer/Admin-adjusted.
Evidence: `THESIS_FORMULA_SHEET.md` §4.

## F. SHAP / Explainability

**F1. What does SHAP tell you?**
Short: Per-feature contribution to a specific prediction relative to a baseline, via
Shapley values from cooperative game theory.
Evidence: `THESIS_FORMULA_SHEET.md` §5.
Must not claim: "SHAP proves feature X causes outcome Y" — it decomposes what the trained
model used, not real-world causality.

## G. Diagnosis Engine / Learning Plan

**G1. Is the Diagnosis Engine machine learning?**
Short: No — it is rule-based (explicit if/elif threshold checks) against the student's
profile fields.
Evidence: `dss/services/diagnosis_engine.py` (direct code read this session).
Safe claim: "A transparent, rule-based diagnostic layer, not a black-box classifier."

**G2. Is the Learning Plan AI-generated?**
Short: The plan's structure and content come from a rule-based/heuristic generator; the
LLM is used only to phrase (narrate) the already-structured plan in natural language.
Evidence: `dss/services/learning_plan.py` (direct code read this session).
Must not claim: "The AI designs the learning plan from scratch."

## H. Career Advisor

**H1. Is Career Fit a probability of success?**
Short: No — it is a weighted heuristic score across 6 real, independently-varying
dimensions (and Readiness uses a different set of 6 dimensions).
Evidence: `dss/services/career_scoring.py`.
Must not claim: "X% probability of career success" — the number is a heuristic index, not
a calibrated statistical probability.

**H2. Do all the sliders/inputs actually affect the score?**
Short: Yes — traced this session; all 6 Fit and all 6 Readiness input dimensions genuinely
change the computed score live.
Evidence: prior-phase `LEARNING_EXPLAINER_CAREER_ADVISOR_DEEPTEST.md` deep trace.

## I. RAG / AI Advisor

**I1. How does the RAG pipeline work end-to-end?**
Short: Question → prompt-security/context check → embedding → vector similarity search →
threshold filter → context budget trim → LLM call → citation attachment → response.
Evidence: `dss/services/rag_service.py`, `FINAL_ARCHITECTURE_TRUTH.md` Layer 5.

**I2. What happens if no relevant document is found?**
Short: The system returns an honest "no relevant evidence found" response rather than
forcing a low-confidence citation.
Evidence: `RAG_LOW_CONFIDENCE_FLOOR=0.55` in `dss/config.py`.

**I3. Are citations verified against hallucination?**
Short: A heuristic hallucinated-citation check exists; citations are traceable to real
document IDs, verified live this session with an actual quoted source.
Must not claim: Zero-hallucination guarantee.

## J. Vector Storage

**J1. Where are document embeddings stored?**
Short: `LocalVectorStore` — NumPy arrays + JSON metadata files on disk. No database
server is involved in the active path.
Evidence: `dss/services/vector_store.py`.

**J2. What about the PostgreSQL/pgvector code that exists in the repo?**
Short: Real connection test and real DDL schema exist, but all 4 CRUD methods are stubs
with no actual SQL execution — this backend is dormant and not activated (its trigger env
vars are unset).
Evidence: `ARCH-PGVECTOR-001` in `ISSUE_REGISTER.csv`.
Must not claim: "The system uses PostgreSQL for vector storage" or "the whole system uses
PostgreSQL" — no relational database engine is running under this application at all.

## K. Knowledge Base

**K1. Can Admin fully manage Knowledge Base documents?**
Short: Create and Read are implemented; Update and Delete have no UI (the service-layer
delete method exists but has zero UI callers).
Evidence: `KB-CRUD-001` in `ISSUE_REGISTER.csv`.
Must not claim: "Complete document CRUD."

**K2. What document formats are supported?**
Short: TXT, MD, DOCX, PPTX, PDF, JSON.
Evidence: `dss/services/document_ingestion.py`.

## L. Model Registry

**L1. Does training auto-promote a model to Production?**
Short: No — verified this session: the actual training call site explicitly passes
`auto_promote=False`, even though an internal `is_best` flag is computed.
Evidence: `dss/core/warehouse.py`, `dss/services/model_service.py` / `ml_hub.py` call site
(direct code read this session).
Must not claim: "The best model is automatically promoted."

**L2. Does the app auto-train a model on bootstrap or login?**
Short: No — bootstrap only reuses an existing Production model if one exists; otherwise it
deliberately does nothing and logs that it skipped training.
Evidence: `dss/core/init_app.py` / bootstrap service.

## M. LMS / CMS Integration

**M1. Is there a real LMS integration?**
Short: No — an abstraction/repository interface exists, but the "Real Connector"
implementation internally delegates to the demo repository; no network call reaches an
actual LMS platform.
Evidence: `dss/services/lms_connector.py`; `FINAL_ARCHITECTURE_TRUTH.md` Layer 7.
Must not claim: "Fully integrated with an LMS" or naming a specific real platform as
connected.

**M2. Is the CMS real?**
Short: The internal lecture-content repository (upload → ingest → retrieve → cite) is
real and fully functional end-to-end, but it is not a connection to an external CMS
platform.
Evidence: `dss/services/cms_lecture_repository.py`; live citation test this session.

## N. Concurrency / Reliability

**N1. How many concurrent AI requests are supported?**
Short: `MAX_CONCURRENT_REQUESTS = 3`, enforced by a `threading.Semaphore`.
Evidence: `dss/config.py`, `dss/services/llm_gateway.py`.
Must not claim: This number is load-tested or is a measured optimum — it is a configured
default.

**N2. What happens under provider failure/exhaustion?**
Short: In REAL_LMS mode, all fabricated-fallback paths were removed; the user sees an
honest unavailable/overloaded message instead.
Evidence: `DEMO-CONCURRENCY-001` fix in `ISSUE_REGISTER.csv`.

## O. Data Provenance

**O1. Is the 1,000-student dataset real institutional data?**
Short: No — it is fully synthetic, generated by `generate_data()`/`generate_lms_data()`.
Evidence: `dss/core/data_helpers.py` (direct code read this session).
Must not claim: "Trained/validated on real student data."

**O2. Is the Knowledge Base content real?**
Short: A mix — 4 of the 19 seeded documents cite real, verifiable sources (Pomodoro
Technique, Feynman Technique, Krashen's Input Hypothesis, Cornell note-taking/spaced
repetition); the remaining 15 are generic unattributed study-advice text.
Evidence: prior-phase RAG document audit (retained from the audit phase's findings).

## P. Security / Privacy

**P1. What personal data reaches the LLM prompt?**
Short: Only `student_id`, `risk_level`, `progress_note` — never name/email/phone.
Evidence: `dss/services/privacy_service.py`.

**P2. Is the system protected against prompt injection?**
Short: A heuristic indirect-injection defense exists with dedicated test coverage.
Evidence: `dss/services/prompt_security.py`; `test_12_prompt_security_indirect_injection_protection`.
Must not claim: Immunity to all possible prompt injection techniques.

**P3. How are passwords stored?**
Short: PBKDF2-HMAC-SHA256, a real cryptographic hashing scheme appropriate to project
scale.
Must not claim: Enterprise identity-provider-grade authentication (SSO, MFA, etc. — none
of these exist).

## Q. Testing & Verification

**Q1. What testing methodology was used?**
Short: pytest for unit/integration (403 tests), Playwright for real-browser E2E (23
tests), plus a manual per-role acceptance walkthrough with live screenshots and DOM
measurements.
Evidence: `TEST_RESULTS.md`, `VISUAL_ACCEPTANCE_MATRIX.csv`.

**Q2. Were there any flaky tests?**
Short: One known transient Windows file-lock rename race (`.tmp`→`.json`) observed 3
times, always resolved on isolated re-run — documented as a non-defect race condition
under heavy concurrent test load, not a product bug.
Evidence: `TEST_RESULTS.md`.

## R. Limitations (see also THESIS_MUST_NOT_SAY.md)

**R1. What are the biggest limitations of this system?**
Short: (1) No real institutional dataset used anywhere; (2) no real external LMS/CMS
connection; (3) PgVectorStore is a non-functional stub; (4) Knowledge Base and Admin User
Management are read-mostly (no Update/Delete UI); (5) concurrency capacity is unverified
under real load; (6) accessibility was spot-checked, not formally audited.
Evidence: `ISSUE_REGISTER.csv` (4 open issues), `RELEASE_FREEZE.md` production-readiness
section.

## S. Future Work

**S1. What would you build next?**
Short: Real LMS/CMS connectors; PgVectorStore real CRUD implementation for horizontal
scale; full Knowledge Base and User Management CRUD; question-level data collection to
support IRT/BKT-based mastery modeling in the Diagnosis Engine; load testing to justify
(or raise) `MAX_CONCURRENT_REQUESTS`; formal WCAG accessibility audit.

## T. Comparisons / Algorithm Choice

**T1. Why these 3 tree/boosting algorithms (RF, XGBoost, LightGBM) instead of deep learning?**
Short: Tabular educational data with moderate row counts favors gradient-boosted trees
and random forests, which are typically stronger and more interpretable than deep nets on
this data shape; SHAP explainability is also more mature/standard for tree ensembles.
Safe claim: "A deliberate, defensible choice for tabular data at this scale, not an
oversight."
Must not claim: Deep learning was benchmarked and lost — no such comparison was run.

**T2. Why 5-fold cross-validation specifically?**
Short: A standard, moderate-cost bias/variance tradeoff for the dataset size used;
consistent across every algorithm's `GridSearchCV` call.

## U. Miscellaneous

**U1. What database engine powers this application?**
Short: None — every persisted artifact is a file (JSON/CSV/joblib) under
`data_warehouse/`. PostgreSQL exists only as a dormant, stub-CRUD vector-store option.
Evidence: `FINAL_ARCHITECTURE_TRUTH.md` Layer 6.

**U2. How many total P0 (blocking) issues remain?**
Short: Zero. 26 issues were tracked across the audit; 22 fixed, 4 intentionally left open
(none rated P0).
Evidence: `ISSUE_REGISTER.csv`.

---

## TOP 30 DANGEROUS QUESTIONS (most likely to trip up an unprepared defense)

1. "So the whole system runs on PostgreSQL?" → No. See U1 — file-based storage; Postgres
   is a dormant stub.
2. "Does SHAP prove that feature X causes the outcome?" → No. See F1 — contribution
   decomposition, not causality.
3. "Is K-Means predicting which students will fail?" → No. See E1 — unsupervised
   grouping, prediction is a separate supervised model.
4. "Your R² is suspiciously high — did you leak the target?" → See D2/D3: leakage guards
   are real and separate from the fact that the *sample dataset's target itself* is a
   synthetic linear formula of the inputs — that's why R² is high, not because training
   leaked test data.
5. "Is this connected to a real LMS like Moodle or Canvas?" → No. See M1 — abstraction
   layer only, "Real Connector" delegates to the demo repository.
6. "Is the Career Fit score a probability?" → No. See H1 — heuristic weighted index.
7. "Can I edit or delete a Knowledge Base document from the UI?" → Delete: no UI (K1).
   Update: no UI. Both intentionally open (`KB-CRUD-001`).
8. "Can Admin deactivate a user account?" → No CRUD UI beyond read-only visibility
   (`ADMIN-USER-001`).
9. "Does every classification algorithm get the same hyperparameter tuning depth?" → No.
   XGBoost Classifier is a fixed-params exception (C3) — do not imply uniform tuning.
10. "Was the Random Forest grid ever 36 combinations?" → No, that number is historical and
    was never actually executed; current truth is 12 combos / 60 fits (D1).
11. "Does training automatically promote the best model to Production?" → No (L1) —
    `auto_promote=False` at the real call site, verified by code read.
12. "Does the app retrain a model every time someone logs in?" → No (L2).
13. "Is the 1,000-row dataset real student data from a university?" → No (O1) — fully
    synthetic.
14. "How do you know the AI won't leak student PII to the LLM provider?" → Verified field
    allowlist: only student_id/risk_level/progress_note (P1).
15. "What happens when all your AI providers are down?" → Honest unavailable message in
    REAL_LMS mode, not a fabricated answer (N2).
16. "Have you load-tested concurrency?" → No — `MAX_CONCURRENT_REQUESTS=3` is configured,
    not measured (N1).
17. "Is your app WCAG accessibility certified?" → No — spot-checked only (R1).
18. "Is the CMS a real content management platform like a real LMS's content module?" →
    No — it's an internal lecture repository (M2), real but not external.
19. "Does the vector store scale to millions of documents?" → The active LocalVectorStore
    is file-based (NumPy+JSON); no such scale test was performed.
20. "If I ask the AI something outside the Knowledge Base, does it make something up?" →
    No — below `RAG_LOW_CONFIDENCE_FLOOR=0.55` it returns an honest no-evidence response
    (I2).
21. "Can citations be hallucinated?" → A heuristic detector exists, but there is no
    formal zero-hallucination guarantee (I3).
22. "Is the password hashing enterprise-grade (bcrypt/Argon2/SSO)?" → It's PBKDF2-HMAC-
    SHA256, real but simplified; no SSO/MFA (P3).
23. "Does the Diagnosis Engine use machine learning?" → No, it's rule-based/threshold
    logic (G1).
24. "Does the AI generate the learning plan from scratch?" → No — a rule-based generator
    builds it; the LLM only phrases it (G2).
25. "How many of the 26 tracked issues are still open, and are any severe?" → 4 open, 0
    rated P0 (U2).
26. "What's the actual test pass count, and is it current?" → 426/426 at freeze
    (`RELEASE_FREEZE.md`) — cite this number, not any earlier partial count.
27. "Why not use a real relational database like PostgreSQL for everything?" → It's an
    architecture choice for project scope; a Postgres path is scaffolded (schema, DDL)
    for the vector store specifically, not activated project-wide.
28. "Is Career Readiness the same computation as Career Fit?" → No — 6 different weighted
    dimensions for each (H1).
29. "Did you compare against deep learning models?" → No such comparison was run (T1) —
    don't claim benchmarking that didn't happen.
30. "Is this production-ready for a real university deployment today?" → No — see
    `RELEASE_FREEZE.md` production-readiness limitations: no real LMS/CMS, no load testing,
    synthetic data only, several read-only admin/KB gaps.
