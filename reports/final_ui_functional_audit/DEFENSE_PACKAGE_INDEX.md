# EduDSS — Thesis Defense Package Index

All files below live under `reports/final_ui_functional_audit/`. This index is the single
entry point — read `RELEASE_FREEZE.md` first, then pick based on what you need.

## Release / freeze record
- **`RELEASE_FREEZE.md`** — freeze date, final test baseline, environment, storage,
  ML algorithms, Model Registry lifecycle, known limitations. Start here.
- **`TEST_RESULTS.md`** — consolidated test evidence, key test files, known transient
  failure pattern, live browser evidence highlights.
- **`VISUAL_ACCEPTANCE_MATRIX.csv`** — per-role, per-page UI acceptance record (22 rows).
- **`FINAL_SYSTEM_CAPABILITY_MATRIX.csv`** — 39-subsystem capability truth table (13
  columns: implemented/wired/verified/tested/storage/safe claim/must-not-claim/evidence).

## Architecture & technical truth
- **`FINAL_ARCHITECTURE_TRUTH.md`** — layer-by-layer (UI → Services → DSS →
  ML → AI/RAG → Repository/Storage → External Integration), each layer classified
  IMPLEMENTED/PARTIAL/ABSTRACTION ONLY/NOT IMPLEMENTED/EXTERNAL DEPENDENCY. **The most
  important single technical document in this package** — read before any deep technical
  question.
- **`THESIS_FORMULA_SHEET.md`** — every formula referenced in defense: preprocessing,
  classification/regression metrics, clustering, SHAP, RAG retrieval, token cost, exact
  ML param grids, exact synthetic target formula.

## Q&A / defense preparation
- **`THESIS_DEFENSE_QA.md`** — 100+ question bank across categories A–U, plus a
  **Top 30 Dangerous Questions** section at the end. Read this cover to cover before the
  defense.
- **`THESIS_MUST_NOT_SAY.md`** — two-column cheat sheet (dangerous phrase → safe
  replacement). Skim immediately before walking into the room.
- **`THESIS_TECHNICAL_GLOSSARY.md`** — bilingual (EN/VI) glossary of every technical term
  used across this package.

## Scripts
- **`THESIS_5_MINUTE_DEFENSE.md`** — opening statement script, ~5 minutes.
- **`THESIS_10_MINUTE_TECHNICAL_DEFENSE.md`** — deeper technical version, ~10 minutes.
- **`THESIS_LIVE_DEMO_SCRIPT.md`** — click-by-click live demo script with fallbacks for
  every step (including the known ~55–60s cold-start delay on first AI Advisor access).

## Underlying source-of-truth documents (pre-existing, referenced throughout the above —
do not recreate, always draw from these)
- `ISSUE_REGISTER.csv` — 26 tracked issues, 22 fixed / 4 open, 0 P0.
- `FUNCTIONAL_MATRIX.csv` — per-feature Create/Read/Update/Delete breakdown.
- `THESIS_DEFENSE_TRUTH_TABLE.md` — original safe/must-not-claim wording per topic.
- `FINAL_UI_FUNCTIONAL_AUDIT.md` — full architecture & runtime consistency audit, §1–§7.
- `STUDENT_ACCEPTANCE.md`, `LECTURER_ACCEPTANCE.md`, `ADMIN_ACCEPTANCE.md` — per-role
  walkthrough records.
- `LEARNING_EXPLAINER_CAREER_ADVISOR_DEEPTEST.md` — deep computation trace.
- `LMS_CMS_RAG_PRODUCT_VERIFICATION.md` — consolidated LMS/CMS/RAG verification.
- `DESIGN_SYSTEM_ADOPTION_MATRIX.md` — 16-page shared-component adoption survey.
- `RESPONSIVE_ACCESSIBILITY_REPORT.md` — responsive sweep + accessibility pass.
- `STUDENT_NAV_INVENTORY.md`, `LECTURER_NAV_INVENTORY.md`, `ADMIN_NAV_INVENTORY.md` —
  navigation inventories.

## Recommended reading order before defense day

1. `RELEASE_FREEZE.md` (5 min)
2. `FINAL_ARCHITECTURE_TRUTH.md` (10 min)
3. `THESIS_MUST_NOT_SAY.md` (5 min)
4. `THESIS_DEFENSE_QA.md` — Top 30 Dangerous Questions section (10 min)
5. `THESIS_5_MINUTE_DEFENSE.md` and `THESIS_10_MINUTE_TECHNICAL_DEFENSE.md` — read aloud
   once each (15 min)
6. `THESIS_LIVE_DEMO_SCRIPT.md` — walk through live in the actual app once (15 min)
7. `THESIS_FORMULA_SHEET.md` and `THESIS_TECHNICAL_GLOSSARY.md` — keep open as reference
   during Q&A, not required to memorize verbatim.

## Priority-of-truth rule (for resolving any apparent conflict)

1. Current verified runtime behavior (what the app actually does today)
2. Current code
3. This defense package's own documents
4. Current test suite (426/426)
5. Older project documentation (`SYSTEM_TECHNICAL_HANDBOOK.md`, prior audit-phase docs)
6. Oldest handbook/report drafts

Any older document that conflicts with this package is **STALE / SUPERSEDED** — this
package wins.
