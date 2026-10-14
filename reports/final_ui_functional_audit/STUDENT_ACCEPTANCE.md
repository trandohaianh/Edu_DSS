# Student Product Acceptance — Live Walkthrough Record

**Method:** live Playwright session (1440×900), real account `sv905` (real generated data, no
Production regression model trained for this dataset — the honest-empty-state path), every
destination from `STUDENT_NAV_INVENTORY.md` visited in navigation order, primary actions
exercised, before/after screenshots captured for every fix, real DOM measurements taken (not
screenshot guessing) where a visual claim needed proof.

## CRITICAL check — Student ML Hub / Clustering must not expose training controls

**Result: PASS**, verified at the code level (not assumption):
- `dss/main.py`: for `current_role == "Sinh viên"`, `tab_train_ml = None` and only
  `(tab_predict_ml,) = st.tabs(["🔮 Dự đoán"])` renders — the entire `render_training_config_ui`/
  GridSearchCV/hyperparameter block sits inside `if tab_train_ml is not None:`, which is
  structurally unreachable for this role. Confirmed live: Sinh viên's "Dự đoán ML" page never
  shows a training tab at all.
- `dss/tabs/clustering.py`: the K-Means config/fit/global-dataset block is wrapped in
  `if role != "Sinh viên":` — confirmed live: Sinh viên's "Phân cụm" page goes straight to
  "Nhóm học tập của bạn" with no k-selector, no "Chạy Phân cụm K-Means" button visible anywhere
  in their view.

## Per-page results

| # | Page | Purpose | Primary action | Data isolation | Role-appropriate | Acceptance |
|---|---|---|---|---|---|---|
| 1 | Trang chủ | Personal status dashboard | See prediction/risk/AI plan | PASS — own ID only, honest empty state when no model exists | PASS | **PASS after fix** |
| 2a | Dự đoán ML — Nhập tay | Manual what-if prediction | Fill form, get prediction | PASS | PASS after fix | **PASS after fix** |
| 2b | Dự đoán ML — Dữ liệu đã có (renamed) | View prediction for own existing row | View own prediction | PASS — locked to `current_student_id` | PASS after fix | **PASS after fix** |
| 3 | Phân cụm | Personal cluster + peer-group guidance | Understand own group + recommendations | PASS | PASS after fix | **PASS after fix** |
| 4a | Trợ lý AI — Kế hoạch học tập | Generate/view AI study plan | Ask AI / generate plan | PASS | PASS after fix | **PASS after fix** |
| 4b | Trợ lý AI — Hướng nghiệp | Career fit/readiness/roadmap | Explore career fit | PASS | PASS (verified in earlier architecture pass) | PASS |
| 4c | Trợ lý AI — Giải thích bài học | Ask AI about a real lecture | Chat with grounded citations | PASS (verified via live closed-loop test, earlier pass) | PASS | PASS (deeper dedicated pass scheduled next) |
| 5 | Lịch sử tư vấn | View own AI consultation history | Browse past plans | PASS — filtered to own student_id | PASS | PASS |

## Issues found and fixed this phase

See `ISSUE_REGISTER.csv` rows `CARD-HEIGHT-001`, `FUNC-ML-002`, `SIA-CLUSTER-002`,
`SIA-NAV-002` for full detail. Summary:

1. **CARD-HEIGHT-001 (P1)** — Home dashboard's 3-card row measured 531px / 324px / 392px
   (getBoundingClientRect, not a guess) despite an existing global equal-height CSS rule — root
   cause was a missing `stLayoutWrapper` link in the existing selector chain, specific to
   `st.container(border=True)` inside `st.columns()`. Fixed by extending the existing chain one
   level (not a new one-off rule) — this self-heals every other bordered-card row app-wide, not
   just this one. Verified after fix: all 3 cards measure exactly 531.25px.
2. **FUNC-ML-002 (P1)** — "Dự đoán — Từ file" tab has no file uploader at all (shows the
   prediction for a row already in the dataset); for Sinh viên it pointed to 2 tabs
   ("Huấn luyện mô hình", "Kho dữ liệu") that don't exist for that role, leaving an unfollowable
   dead-end instruction whenever no target was configured. Renamed to "Dự đoán — Dữ liệu đã có"
   and made both guidance messages role-aware for Sinh viên and Giảng viên/Admin.
3. **SIA-CLUSTER-002 (P2)** — literal "cosine" jargon shown to Sinh viên, a broken
   "Chạy Phân cụm K-Means" instruction reachable in an edge-case data-mismatch warning, and 4
   English-jargon parentheticals ("Cluster Profiles", "Grouped Bar Chart", "Benchmark",
   "Collaborative") plus a chart-implementation-rule note (SVG polygon-closure requirement —
   pure dev trivia, zero user value) shown unconditionally in the always-visible legend box.
   All reworded/removed; edge-case warning made role-aware.
4. **SIA-NAV-002 (P2)** — the AI Advisor page's own `section_header` (inside the page body) was
   never role-branched even though the outer sub-tab nav label was fixed earlier this session —
   still said "Tư vấn — AI (LLM)" with a raw "(RAG)" acronym for Sinh viên. Fixed to match the
   nav label ("Kế hoạch học tập của bạn").

## Regression evidence

- `tests/test_responsive_design.py` — 3/3 (new: card-height chain fix + stable-key test).
- `tests/test_student_ml_prediction_labels.py` — 4/4 (new file).
- `tests/test_student_information_architecture.py` — 14/14 (4 new tests this phase).
- Full non-e2e suite re-run after this phase (see conversation for live result).

## Not yet covered this phase (explicitly deferred to their own sequence phase)

- Learning Explainer deep-test (ingestion UX, retrieval, course isolation, version pinning,
  Socratic mode, quiz/practice) — scheduled next.
- Career Advisor deep computation trace (which inputs are real vs UI-only, Fit vs Readiness
  separation, recompute-on-change test) — scheduled after Learning Explainer.
- Multi-resolution desktop check (1920×1080, 1366×768) for Student pages beyond the phone-width
  pass already done in an earlier phase — the 1440×900 walkthrough this phase is the primary
  evidence; a dedicated responsive sweep is still queued per the execution sequence.
