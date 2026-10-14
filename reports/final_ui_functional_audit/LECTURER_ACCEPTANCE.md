# Lecturer Product Acceptance — Live Walkthrough Record

**Method:** live Playwright session (1440×900), real account `giangvien`, every destination from
`LECTURER_NAV_INVENTORY.md` visited, primary actions inspected, issues fixed with live re-check.

## Per-page results

| Page | Purpose | Data scope | Role-appropriate | Acceptance |
|---|---|---|---|---|
| Trang chủ | Class overview landing | Full class (correct for this role) | PASS | PASS (fixed earlier: `RESPONSIVE-001`) |
| Dashboard | Deep class analytics | Full class | PASS | PASS (fixed earlier: `MODELREG-001-FOLLOWUP`); **new fix this phase**: stale auto-promotion hint text |
| Khám phá — Xử lý dữ liệu | Data quality/exploration | Full class dataset, raw column names shown (correct — technical audience actually configuring data) | PASS | **PASS** |
| Huấn luyện — Dự đoán (Huấn luyện mô hình) | Train/compare models | Full class dataset | PASS — training gate correctly Lecturer/Admin-only, confirmed unreachable for Sinh viên at the code level | **PASS** |
| Phân cụm — Gợi ý (full config) | K-Means config, Elbow/Silhouette, cluster interpretation | Full class dataset | PASS except one finding | **PASS after fix** — see `SIA-CLUSTER-002-FOLLOWUP` below |
| Trợ lý AI (chat sub-tab) | Provider config / compare AI / chat | N/A | PASS | PASS |
| Giải thích Bài giảng (CMS management) | Upload/manage lecture content, review quiz queue | Own uploaded content | PASS | PASS (see `COLDSTART-001` — cold-start UX gap, documented not fixed) |
| Kho dữ liệu — Datasets | Upload/manage datasets | Full class | PASS | PASS (fixed earlier: `DEMO-LMS-LIVEPUSH-001`, confirmed live this phase) |
| Kho dữ liệu — AI Models | View Model Registry | Full class model history | PASS except one finding | **PASS after fix** — see below |
| Kho dữ liệu — History | Raw activity/training log | Full class | PASS (functional), minor polish opportunity | PASS — plain-text log is utilitarian but correct; could be upgraded to a table view in a future pass, not fixed this pass (low priority, no correctness/policy issue) |

## Issues found and fixed this phase

1. **`SIA-CLUSTER-002-FOLLOWUP` (P2)** — the "Diễn giải cụm" (Cluster Interpretation) card in the
   full Lecturer clustering view displayed raw column names directly ("Mạnh: final_score,
   gpa_previous") instead of friendly labels via the established `feature_label()` mapper used
   everywhere else in this file. Found via live screenshot, not source-reading alone. Fixed by
   wrapping both the strengths and weaknesses lists in `feature_label()`.
2. **`MODELREG-TEXT-001` (P1, new)** — found via live screenshot of the Model Registry page: its
   own subtitle claimed *"Model mới huấn luyện tốt nhất tự động thành Production"* (auto-promotes),
   directly contradicting (a) the actual verified code behavior (`ml_hub.py`'s real training
   call site explicitly passes `auto_promote=False`, and `warehouse.py::save_model_training`'s own
   docstring states training only ever creates Candidates) and (b) **another sentence in the same
   file** ("KHÔNG BAO GIỜ tự động lên Production"). Two more instances of the identical stale claim
   were found by repo-wide grep: `dashboard.py`'s empty-state hint, and
   `model_registry.py::resolve_production_for_prediction`'s "no production model" message. All 3
   fixed to state the correct lifecycle: best model → Candidate → Admin-gated Promote → Production.
   This is exactly the kind of internally-contradictory, misleading-for-a-thesis-defense text the
   whole engagement has been hunting for — found only because a real screenshot was inspected, not
   because the code was re-read in isolation.

## Regression evidence

- `tests/test_student_information_architecture.py` — 15/15 (1 new test this phase: cluster
  interpretation panel label fix).
- `tests/test_model_lifecycle_badge.py` — 6/6 (1 new test this phase: no UI text claims
  auto-promotion, checked across all 3 affected files).
- Full non-e2e suite re-run after this phase (see conversation for live result); 3 tests failed
  once in the first full run with the well-established transient Windows file-lock
  `.tmp`→`.json` rename race (unrelated files, not touched this session) — confirmed non-regressions
  by isolated re-run (3/3 pass cleanly alone).

## Not yet covered this phase

- Multi-resolution desktop sweep (1920×1080, 1366×768) for Lecturer pages.
- Deep interaction testing of "Duyệt Quiz" (quiz review queue) and "Dashboard phân tích" sub-tabs
  within the CMS management view — only the default "Nạp & Quản lý" sub-tab was inspected live
  this phase (the other 2 sub-tabs are covered by the existing real acceptance tests
  `test_06_lecturer_approves_quiz_then_student_receives` / `test_07_rejected_quiz_never_reaches_student`,
  but not visually screenshot-verified live).
- "Dự đoán" sub-tab under Huấn luyện — Dự đoán was not captured live this phase due to a locator
  script bug (not an app issue) — the underlying `personal_prediction_tab`/`file_prediction_tab`
  functions were already read in full during the Student phase and confirmed correctly
  role-branched.
