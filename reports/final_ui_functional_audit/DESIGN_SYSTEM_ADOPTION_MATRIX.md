# Design System Adoption Matrix

**Purpose:** per the earlier explicit instruction — `main.css` already has a substantial, real
design system (design tokens, `.card`/`ui_kit.kpi_row` components, typography scale, dark-mode
support). This matrix does NOT propose rebuilding it; it records which pages actually consume it
correctly, which have local ad-hoc CSS/HTML, and where that gap caused a real, evidenced defect.
Built from the screenshot evidence gathered across the entire Student/Lecturer/Admin acceptance
pass this session — not a fresh guess.

| Role | Page | Shared design usage | Local CSS/HTML | Card height consistency | Typography | Spacing | Visual hierarchy | Needs refactor? |
|---|---|---|---|---|---|---|---|---|
| Student | Trang chủ | Partial — `st.container(border=True)` cards + custom gradient banner HTML | Yes (hero banner, gauge) | **Was inconsistent (531/324/392px) — FIXED this session** (`CARD-HEIGHT-001`), now exact match | Consistent (`.page-title`-style headers) | Consistent | Strong (banner → 3-card row → clear priority) | No — fixed |
| Student | Dự đoán ML | `ui_kit.section_header`, plain widgets | Minimal | N/A (no card row) | Consistent | Consistent | Clear (form → result) | No |
| Student | Phân cụm | `ui_kit.kpi_row` (3 cards, always equal height — confirmed) + `st.container(border=True)` for config/eval/interpretation cards | Some (radar/bar chart HTML legend box) | Equal (uses the same now-fixed shared chain) | Consistent | Consistent | Good, though information-dense (multiple sections stacked) | No |
| Student | Trợ lý AI (3 sub-tabs) | `ui_kit.section_header`, `st.container(border=True)` cards | Minimal | Equal (Home-page-style 3-card row, same fix applies) | Consistent | Consistent | Good | No |
| Student | Lịch sử tư vấn | `ui_kit.empty_state`, plain layout | None | N/A | Consistent | Consistent | Simple, clear | No |
| Lecturer | Trang chủ | **Local, hand-rolled** `.dss-lect-*` CSS classes (hero, KPI cards, quick actions) — NOT the shared `ui_kit.kpi_row` | Substantial (own CSS block in `main.css`, ~100 lines) | **Was broken at phone width — FIXED this session** (`RESPONSIVE-001`) | Consistent with shared tokens (colors/weights match) despite separate class names | Consistent | Good | **Yes, lower priority** — this page duplicates a KPI-card pattern that `ui_kit.kpi_row` already provides; consolidating would have prevented `RESPONSIVE-001` from happening in the first place. Not consolidated this pass (scope: fix defects, not rearchitect working components) |
| Lecturer | Dashboard | `ui_kit.kpi_row` (colored left-border cards, confirmed equal height) | Minimal | Equal | Consistent | Consistent | Good | No |
| Lecturer | Khám phá | `ui_kit.kpi_row` + `st.container(border=True)` | Minimal | Equal (KPI row); 3-card row below appeared consistent in screenshot | Consistent | Consistent | Good | No |
| Lecturer | Huấn luyện — Dự đoán | `ui_kit.section_header`, `st.container(border=True)`, `st.expander` | Minimal | N/A (form-heavy, not a card row) | Consistent | Consistent | Good, information-dense but well-sectioned (numbered steps) | No |
| Lecturer | Phân cụm (full) | `ui_kit.kpi_row` (5 cards, equal height) + `st.container(border=True)` (3-card row) | Minimal | Equal | Consistent | Consistent | Good | No |
| Lecturer/Admin | Kho dữ liệu (all 3 sub-tabs) | `ui_kit.kpi_row`, `st.expander`, plain buttons | Minimal | Equal (2-card KPI rows) | Consistent | Consistent | Good | No |
| Admin | Model Registry | `ui_kit.kpi_row` (4 cards) + `st.dataframe` table | Minimal | Equal | Consistent | Consistent | Good | No |
| Admin | Cấu hình AI | `ui_kit.kpi_row`-style provider cards (`st.container(border=True)`) | Minimal | Equal (4 cards, confirmed in screenshot) | Consistent | Consistent | Good | No |
| Admin | Quản lý tri thức (RAG) | `st.tabs`, `st.dataframe`, `st.expander` | Minimal | N/A | Consistent | Consistent | Good | No |
| Admin | Cài đặt | `st.container(border=True)` sections | Minimal (was a fabricated-status HTML block, now honest text — `DEMO-LMS-STATUS-001`) | N/A | Consistent | Consistent | Good | No |
| Admin | Báo cáo hệ thống | `ui_kit.kpi_row` + Plotly charts | Minimal | Equal | Consistent | Consistent | Good | No |

## Summary

- **The shared design system (`ui_kit.kpi_row`, `.card`/`st.container(border=True)` + the global
  flex equal-height chain) is adopted correctly on the large majority of pages** — 15 of 16 rows
  above show "No" under Needs refactor.
- **Exactly one page had a local, hand-rolled component** (`Lecturer Trang chủ`'s `.dss-lect-*`
  KPI cards) that duplicates what `ui_kit.kpi_row` already does — and it was the **only** KPI row
  in the entire app that had a real responsive defect (`RESPONSIVE-001`). This is direct evidence
  for the general principle: local reimplementations of a shared pattern are where defects
  concentrate. Flagged as a candidate for future consolidation, not fixed this pass (the page
  works correctly now; consolidating would be a larger refactor than this pass's scope of "fix
  found defects").
- **The one systemic gap in the shared system itself** (missing `stLayoutWrapper` link in the
  equal-height CSS chain, `CARD-HEIGHT-001`) was fixed at the shared-selector level specifically
  so it self-heals every `st.container(border=True)` row app-wide — this is why every other card
  row surveyed above shows "Equal" without needing a page-specific fix.
- No emoji-clutter or excessive-decoration issues were found on any page surveyed — icon usage is
  consistent and restrained across all 3 roles.
