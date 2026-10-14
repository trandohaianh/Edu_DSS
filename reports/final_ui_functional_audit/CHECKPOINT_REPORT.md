# EduDSS — UI/Functional Audit Checkpoint

**Date:** 2026-09-15
**Scope of this checkpoint:** Production Demo Policy correction, Sidebar IA audit, full Student-role
pass (ml_hub, clustering, advisory/Career Advisor, learning_explainer, home dashboard), a first live
pass over Lecturer and Admin home/config/registry pages, and e2e test-infrastructure stabilization.

**This is a checkpoint, not the final acceptance report.** It does not re-litigate work already
verified in earlier phases of this engagement (AI provider health, the 6 architecture/runtime issues,
the baseline QA audit) — see prior conversation turns for that record. What follows is scoped strictly
to the work completed since the "Continue exactly in the planned order" instruction.

## 1. Completed this checkpoint

- **Production Demo Policy correction** applied and verified against 6 named files; one **P0 finding**
  (DEMO-CAREER-001) discovered via live screenshot, not source reading alone — see Issue Register.
- **Sidebar IA audit** against the 10 required questions, with live 1366×768 screenshot evidence
  (`sv901` login) — one grouping fix applied (SIDEBAR-IA-001).
- **Special Student Role Audit**: confirmed the backend/RBAC restriction (Student = personal
  inference only, no training/clustering config UI) was already correct from an earlier phase;
  the actual gap was presentation-layer jargon leakage — 6 findings fixed (SIA-* rows in the
  Issue Register).
- **Card alignment check** on the Student home dashboard row: captured full-content screenshots
  (not just source) and found the three cards align within ~30px — **no defect confirmed**, so no
  speculative fix was applied (this is a negative-result finding, recorded for completeness).
- **Lecturer live pass** (home, Dashboard, Career Advisor, Kho dữ liệu): no jargon or demo-policy
  violations found; the Production Demo Policy gate on the LMS-sync/sample-data buttons renders
  correctly in default (DEMO_SYNTHETIC) mode.
- **Admin live pass** (Cấu hình AI, Quản lý tri thức RAG, Model Registry, Báo cáo hệ thống, Cài đặt):
  confirmed the MODELREG-001 lifecycle badge fix (candidate/production/archived) renders correctly
  in the Model Registry table; confirmed the "Tri thức Mẫu (Demo)" page is honestly labeled and
  Admin-only; **found and fixed a follow-up MODELREG-001 inconsistency** — the Báo cáo hệ thống
  page's "Mô hình theo trạng thái" chart still used the old binary is_production check and
  disagreed with the Model Registry table on the same underlying data (see Issue Register).
- **e2e test infrastructure**: fixed one stale literal-string assertion (predates this session) and
  one load-dependent render-timing gap, both with reproduction evidence, not blind timeout bumps.

## 2. Issues found and fixed

See `ISSUE_REGISTER.csv` in this folder (10 rows, all `FIXED`). Highlights:

| ID | Severity | One-line summary |
|---|---|---|
| DEMO-CAREER-001 | **P0** | Career Advisor leaked raw "IMPLEMENTED/PARTIAL/FUTURE REAL INTEGRATION" dev-status badges to students and silently defaulted to demo LMS/CMS data regardless of environment |
| SIA-ML-001 | P1 | ML-jargon glossary + "pipeline CV" badge shown unconditionally to Sinh viên |
| SIA-CLUSTER-001 | P1 | Clustering page header/technical guide leaked to Sinh viên |
| SIA-CAREER-002 | P2 | English acronym/jargon in Career Advisor header and tab labels |
| SIA-EXPLAINER-001 | P2 | "(CMS)" leaked into Student-facing Learning Explainer header/messages |
| SIA-HOME-001 | P2 | "SHAP" leaked into the primary (non-collapsed) Student dashboard card |
| SIA-NAV-001 | P2 | AI sub-tab nav grouped by technology (LLM/CMS) instead of Student goal |
| SIDEBAR-IA-001 | P2 | "Lịch sử tư vấn" mis-grouped away from the AI assistant it is a history of |
| E2E-FLAKE-001 | P2 | Reproducible (not "flaky") render-timing gap in one e2e test under full-suite load |
| MODELREG-001-FOLLOWUP | P2 | Admin "Báo cáo hệ thống" model-status chart disagreed with the Model Registry table on the same data |

## 3. Tests run

- `tests/test_student_information_architecture.py` — **11/11 passing** (new this checkpoint).
- `tests/test_production_demo_policy.py` — **16/16 passing** (5 new this checkpoint; 1 prior
  classification corrected — see the file's own docstring for the correction record).
- `tests/test_model_lifecycle_badge.py` — **5/5 passing** (1 new this checkpoint, for the
  MODELREG-001-FOLLOWUP consolidation).
- Full non-e2e suite (`pytest tests --ignore=tests/e2e`) — run **3 times** across this checkpoint's
  edits: 380/382 passed with 2 known **transient** Windows file-lock failures on
  `lessons_registry.tmp→.json` renames (confirmed non-regressions by isolated re-run — pass cleanly
  alone, unrelated file, not touched this session), then **383/383 clean** on the final run after
  the model_service.py refactor.
- Full e2e Playwright suite — **23/23 passing**, run **three times** across this checkpoint's three
  rounds of fixes, confirming no regression at each step and that the load-dependent timing fix
  holds consistently.

## 4. Screenshots captured (evidence, not claims)

All in this session's scratchpad (not committed to the repo — ephemeral verification artifacts):
Student sidebar (1366×768, full + sidebar-only), Student home dashboard (viewport + scrolled,
showing full 3-card row), Student Career Advisor (before and after the DEMO-CAREER-001 fix),
Student Learning Explainer chat view, Lecturer home/Dashboard/Career Advisor/Kho dữ liệu, Admin
Cấu hình AI/Quản lý tri thức RAG/Model Registry.

## 4b. LMS/CMS/RAG closed-loop — live verification

Rather than trust the already-passing service-level integration tests alone
(`test_learning_explainer_acceptance.py`, `test_lms_cms_integration.py`, `test_rag_service.py` —
confirmed by reading them: they call the real `ingest_lecture_material()` →
`retrieve_lesson_content()` → `generate_explanation()` chain, not mocks), a live browser check was
run: logged in as a real Sinh viên (`sv902`), opened "Giải thích bài học," selected the real seeded
lecture (`CS301` / "Bai 4 - K-Means Clustering"), and asked "K-Means hoạt động theo những bước
nào?" The AI's answer:

- Quoted the actual lecture file **verbatim**, including a version-specific detail
  ("bổ sung kỹ thuật K-Means++") that exists only in that document's v2 content — not generic
  LLM knowledge of K-Means.
- Cited it explicitly and traceably: *"Nguồn bài giảng đã dùng: Tài liệu: Bai 4 - K-Means
  Clustering (v2, co K-Means++) (ID: doc_727bb407b8#c1, file: bai4_kmeans_v2.txt)"*.
- Matched the student's resolved explanation level ("Tiêu chuẩn").

This confirms the CMS→RAG→Student pipeline is genuinely functional end-to-end, not merely
claimed by source code or isolated unit tests. (A separate attempt to also automate the
Lecturer-side file-upload ingest step through Playwright hit a Streamlit file-input timing issue
in the browser-automation harness itself — not a product defect — so that specific sub-step relies
on the existing integration-test coverage rather than a fresh live screenshot.)

## 4c. Responsive pass — phone width (390×844)

Live Playwright screenshots at 390×844 for Student, Lecturer, and Admin home pages, plus a
`document.documentElement.scrollWidth` vs `clientWidth` check (no horizontal overflow on any of
the 3 — confirmed `390 == 390` for all).

- **Student home**: sidebar correctly auto-collapsed, topbar reflowed vertically, hero banner and
  card row adapted cleanly. No defect.
- **Admin "Báo cáo hệ thống"**: KPI cards (using the shared `ui_kit.kpi_row` component) correctly
  stacked to a single column. No defect — direct evidence the shared design system already handles
  phone width correctly where it's actually used.
- **Lecturer home — found a real P1 defect (RESPONSIVE-001)**: the 4-card KPI row is a
  page-specific hand-rolled component (`dashboard.py::_render_lecturer_kpi_row`), built with its
  own CSS instead of the shared `ui_kit.kpi_row`. Its grid was hard-coded to 4 columns at every
  width; at 390px each column narrowed to ~70–90px, wrapping long Vietnamese labels one **character**
  per line — completely unreadable. Fixed with two new breakpoints (2 columns ≤1024px, 1 column
  ≤480px) matching this file's existing breakpoint conventions. Re-verified with a second live
  screenshot showing correct, readable single-column stacking. This is also a concrete data point
  for the Design System Adoption question raised earlier: the one Lecturer-home component that
  bypassed the shared `ui_kit.kpi_row` is exactly the one that had a responsive gap.

## 5. Explicitly NOT yet covered by this checkpoint

Per the user's original 93-section master audit, the following remain **open** and are the
next-in-sequence work, not abandoned:

- Responsive pass beyond the 3 home pages checked at 390×844 (see §4c) — the remaining Student/
  Lecturer/Admin sub-pages (ML prediction forms, clustering, Career Advisor, Model Registry table,
  RAG document table) have not yet been screenshot-verified at phone/tablet width; wide data tables
  in particular are a likely next place to find overflow issues.
- Full accessibility pass (contrast, keyboard nav, screen-reader labels) — not started.
- Repo-wide raw-label grep beyond what was found incidentally this checkpoint (final_score,
  gpa_previous, student_id, course_id, MASTERY_/PENDING_ constants) — spot-checked in clustering.py
  and learning_explainer_tab.py only; a systematic full-repo pass has not been re-run since the
  Raw Label Audit sessions earlier in this engagement.
- Full Admin pass beyond the 3 pages screenshotted here (admin_settings, admin_reports,
  knowledge_base ingestion flow, warehouse History tab).
- The remaining lower-severity jargon items noted but deliberately deferred as below the fix
  threshold this pass: `[LMS]`/`[CMS]` bracket-tag citations in the skill-gap recommendation cards
  (advisory.py), and the English phrase "LMS Realtime Live Push & Webhook Stream" inside a collapsed
  Giảng viên-only expander in warehouse_tab.py.
- Docker build verification remains **NOT VERIFIED IN RUNTIME** (unchanged from the earlier phase —
  Docker daemon unavailable in this sandbox).
- The full 31-section report structure, `FUNCTIONAL_MATRIX.csv`, `VISUAL_ACCEPTANCE_MATRIX.csv`,
  `TEST_RESULTS.md`, and `THESIS_DEFENSE_TRUTH_TABLE.md` have not been produced yet — this checkpoint
  produces only `ISSUE_REGISTER.csv` and this report.

## 6. Production-readiness note

Per the standing rule that a high readiness score cannot coexist with open P0 issues: **DEMO-CAREER-001
was a P0 and is now fixed and verified** (screenshot + regression test + full suite green). No other
P0 was found this checkpoint. The items in Section 5 are scope not yet audited, not known defects —
they should not be read as "known failing," only as "not yet checked this pass."
