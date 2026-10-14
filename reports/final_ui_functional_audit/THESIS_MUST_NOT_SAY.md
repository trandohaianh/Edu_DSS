# EduDSS — Must-Not-Say Cheat Sheet

Two-column quick reference. Left = dangerous/overclaiming phrase. Right = safe, accurate
replacement. Memorize this table before defense.

| ❌ Do NOT say | ✅ Say instead |
|---|---|
| "The whole system uses PostgreSQL" | "All persisted data is file-based (JSON/CSV/joblib); PostgreSQL exists only as a dormant, stub vector-store option" |
| "RAG stores vectors in PostgreSQL" | "RAG uses LocalVectorStore, a file-based NumPy+JSON store; PgVectorStore's CRUD methods are stubs and it is never activated" |
| "SHAP proves feature X causes outcome Y" | "SHAP shows feature X's contribution to this specific model's prediction — a decomposition, not a causal proof" |
| "K-Means predicts student outcomes" | "K-Means groups similar students (unsupervised); outcome prediction is a separate supervised classification/regression model" |
| "Career Fit is a X% probability of success" | "Career Fit is a heuristic weighted score across 6 dimensions, not a calibrated statistical probability" |
| "Knowledge Base has complete CRUD" | "Knowledge Base supports Create, Read, and (since 2026-09-16) guarded Delete; Update still has no UI (KB-CRUD-001, partially fixed)" |
| "Admin has full user management" | "Admin can view registered users (read-only); create/edit/deactivate/delete are not implemented (ADMIN-USER-001)" |
| "Fully integrated with an LMS (Moodle/Canvas/etc.)" | "An LMS repository abstraction exists; the current 'real connector' implementation delegates to demo data — no live LMS is connected" |
| "Fully integrated with an external CMS" | "The CMS is an internal lecture-content repository — real and functional, but not a connection to an external CMS platform" |
| "AI guarantees accurate/safe answers" | "The AI is grounded by RAG with a confidence floor and returns an honest 'no evidence' response when below threshold; it is not error-free" |
| "Trained/validated on real student data" | "Trained and demonstrated on a synthetic sample dataset; no real institutional dataset has been used" |
| "Zero hallucination" | "A heuristic hallucination/citation check exists; there is no formal zero-hallucination guarantee" |
| "All 4 classification algorithms are tuned equally" | "3 of 4 use full GridSearchCV; XGBoost Classifier uses fixed parameters due to a documented multi-class CV crash workaround" |
| "The Random Forest regression grid has 36 combinations" | "The current, single source of truth is 12 combinations / 60 fits (ML-REG-001)" |
| "Training automatically promotes the best model" | "Promotion to Production is Admin-gated; the training call site explicitly passes auto_promote=False" |
| "The app auto-trains models on login/bootstrap" | "Bootstrap only reuses an existing Production model if present; otherwise it does nothing and logs that it skipped training" |
| "The Diagnosis Engine uses machine learning / AI" | "The Diagnosis Engine is rule-based (explicit threshold logic), not ML or LLM-based" |
| "The AI generates the learning plan" | "A rule-based generator builds the plan's structure and content; the LLM only narrates/phrases the already-built plan" |
| "Enterprise-grade authentication" | "A real but simplified PBKDF2-HMAC-SHA256 username/password mechanism; no SSO/MFA" |
| "Load-tested for concurrency" | "MAX_CONCURRENT_REQUESTS=3 is a configured default; it has not been load-tested" |
| "WCAG accessibility certified" | "Accessible names and contrast were spot-checked; no formal WCAG audit was performed" |
| "100% code coverage" | "445/445 tests passing (current baseline, up from 426/426 pre-hardening); test count is not the same as coverage percentage" |
| "Production-ready for real university deployment" | "A tested prototype with a documented, honest list of production-readiness gaps (see RELEASE_FREEZE.md)" |
| "Benchmarked against deep learning and won" | "No deep-learning comparison was run; tree/boosting algorithms were chosen as a defensible fit for tabular data at this scale" |
| "Real-time streaming dashboard" | "Dashboards compute from the current Production model and dataset on each page load, not a live streaming feed" |
| "The cold-start delay is fixed" | "Only the UX is fixed (a clear 'first time may take ~1 minute' loading message everywhere on the cold path); the ~27-60s underlying latency itself is unchanged by design (COLDSTART-001: PARTIAL — UX FIXED / LATENCY REMAINS)" |
