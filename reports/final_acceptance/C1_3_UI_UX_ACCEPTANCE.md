# C1.3 — UI/UX Redesign Acceptance

Evidence date: 2026-09-27 · Environment: Windows 11, Python 3.12.4, Streamlit 1.52.2, Playwright Chromium, `EDUDSS_ENV=development`, `EDUDSS_MODE` unset (DEMO_SYNTHETIC), **no paid AI keys** (`app/.env` absent), isolated `EDUDSS_DATA_ROOT`.
All evidence below was produced from **this worktree only**. No screenshots, counts or acceptance results were taken from `D:\KLTN\code` or any other worktree.

## 1. Branch and HEAD

| Item | Value |
|---|---|
| Worktree | `D:\KLTN\edudss-final-candidate-v2` |
| Branch | `fix/ml-correctness` |
| HEAD | `e2241bfd7a1e4f7363047230eddf68e68cb802e7` (unchanged — nothing committed) |

## 2. Dirty-worktree acknowledgement

The worktree already contained uncommitted C1.1 (security/privacy) and C1.2 (release engineering) changes before C1.3 started. C1.3 edited on top of them and did **not** revert, stash, reset, clean, commit, merge or push anything. Several files touched by C1.3 (`dss/main.py`, `dss/services/auth_service.py`, `dss/tabs/home.py`, `dss/tabs/ui_kit.py`, `dss/tabs/dashboard.py`) already carried C1.1 edits; those edits were preserved (demo-credential gating, `build_quick_question_prompt`, pseudonymised `user_id`, `model_metric_display`, logged exceptions).

Not touched: `requirements.txt`, `requirements.lock.txt`, `Dockerfile`, release-gate logic (`tools/release_gate.py`), ML/RAG algorithms, DB schema/migrations, `runtime_mode.py`, `privacy_service.py`, pseudonymisation, data-lifecycle services.

Observed (not caused by C1.3): `requirements.txt` (modified 20:59), `requirements.lock.txt` (21:07) and `THIRD_PARTY_NOTICES.md` (19:45) were changed earlier on 2026-09-27, before C1.3 work began (~22:50). They make 2 C1.2 tests fail (see §16).

## 3. Files changed by C1.3

Application
- `app/.streamlit/config.toml` — **new**: pins Streamlit's native base theme (light) and `toolbarMode = "minimal"` (removes the developer "Deploy" menu).
- `app/dss/styles/main.css` — **rewritten** as one token-based design system (replaces ~3,100 lines of layered patches with ~1,460 lines).
- `app/dss/config.py` — theme marker injection (`light` / `dark` / `system`), Plotly figure theming through one `st.plotly_chart` wrapper, idempotent plotly patches (fixes unbounded wrapper growth per rerun), page title.
- `app/dss/main.py` — new app shell: sidebar brand, role-grouped navigation, sidebar footer (profile · theme · logout), staff-only search bar, designed empty states, new Admin routes, landing page removed.
- `app/dss/core/roles.py` — `nav_label()` role-aware labels; Admin-only tabs `👥 Người dùng`, `🔗 Tích hợp LMS/CMS`.
- `app/dss/services/auth_service.py` — login page redesign; provisioning explanation instead of registration.
- `app/dss/tabs/ui_kit.py` — token-driven component library; status presets; `report_error`, `unavailable_state`, `subsection_header`, `card_title`.
- `app/dss/tabs/home.py` — Admin / Lecturer / Student homes redesigned.
- `app/dss/tabs/admin_settings.py` — split into Users, LMS/CMS Integration, Settings pages.
- `app/dss/tabs/admin_reports.py` — Admin overview ("Cần xử lý", component status) + reports page.
- `app/dss/tabs/ai_advisor.py` — AI Configuration page redesign; plan-generation error no longer shows exception text; student wording.
- `app/dss/tabs/dashboard.py`, `loading_screen.py`, `clustering.py`, `eda.py`, `ml_hub.py`, `warehouse_tab.py`, `university_onboarding_tab.py`, `app/dss/services/subscription_service.py` — tokenised inline colours, sanitized error messages, header hierarchy, disclaimers.

Tests
- `app/tests/test_c1_3_ui_design_system.py` — **new** (25 collected tests).
- `app/tests/e2e/test_c1_3_ui_journeys_e2e.py` — **new** (9 tests).
- Updated because behaviour legitimately changed: `tests/test_dark_mode_and_theme.py` (marker instead of inline dark CSS; +1 test), `tests/test_ui_and_system_audit.py` (badge asserts semantic class instead of a hex), `tests/e2e/conftest.py` (no "Bắt đầu khám phá" landing), `tests/e2e/test_ui_dark_mode_and_provider_health_e2e.py` (theme segmented control), `tests/e2e/test_role_flows.py` (one label literal, one docstring).

Evidence
- `app/reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md` (this file)
- `app/reports/final_acceptance/c1_3_screenshots/` — 44 PNG + 44 JSON capture records.

## 4. Pages audited (pre-implementation audit)

| Page | Role | Current problems (before) | Required redesign | Risk |
|---|---|---|---|---|
| Login | All | Fake preview stats ("GPA dự đoán 6.8", "Nguy cơ Thấp", "3 ưu tiên"); decorative orbs/grids; Streamlit "Deploy" toolbar | Clean 2-column login, no fabricated data, provisioning note | High (fake data) |
| Registration | — | Does not exist; no statement about how accounts are issued | Explain provisioning; no fake form | Medium |
| Post-login landing | All | Marketing page ("Đồ án tốt nghiệp", tech badges, role cards, "Bắt đầu khám phá" gate) | Remove; go straight to role home | High (student-project look) |
| Sidebar / top bar | All | Emoji nav labels; fake green "Hệ thống hoạt động" dot (no health check); bell showing activity count as "notifications"; two theme toggles; logout rendered after page content | Role nav, footer profile/theme/logout, no fake status | High |
| Theme | All | 3 contradictory CSS generations; dark mode as Python-injected patch; ui_kit hard-coded 68 light hex colours; Plotly charts always white | One token system; real dark tokens; themed charts | High |
| Admin home / Reports | Admin | "Coming soon: Quản lý tri thức" although the KB page exists (false); dense raw metrics | Operational warnings from real state; component status | Medium |
| Admin Settings | Admin | Users, LMS and subscription crammed together; subscription changes with no confirmation | Split into Users / Integration / Settings; confirm destructive-impact change | Medium |
| AI Configuration | Admin | Ollama shown "Cấu hình: Có" without any check; emoji; stars | Honest configured vs checked; never show keys | High |
| Lecturer home | Lecturer | Coloured emoji icon tiles; red risk accent even with no data | Attention-first layout | Medium |
| Lecturer Dashboard | Lecturer | Chart title "undefined" after theming; status accents on empty KPIs | Fix | Low |
| Training / prediction | Lecturer, Student | Nested page-size headers; emoji tabs; student sees "mô hình Production"; single-item tab bar for students | Header hierarchy; plain labels | Medium |
| Clustering | Lecturer, Student | No statement that clusters are segmentation, not classification | Add disclaimer | Medium (misleading ML) |
| Student home | Student | `role` undefined in quick-ask → always failed; red/yellow/green gauge zones imply absolute thresholds; summary showed model **target** column as a stat | 3-question layout; neutral gauge; honest stats | High (bug + misleading) |
| AI Advisor | All | Raw exception text in plan error; "Production" jargon for students | Sanitised error; plain wording | High |
| EDA / Warehouse / ML hub / Onboarding | Staff | ~29 places render `{e}` / `str(e)` to users; solid navy/orange/green blocks | Sanitised errors; token notices | High (info leak) |
| Knowledge base / Doc approval | Admin, Lecturer | Only global styling issues | Global tokens | Low |
| Loading / error screen | All | Decorative illustration with hard-coded colours | Minimal token card | Low |

## 5. Pages redesigned

Login · Admin: Tổng quan, Người dùng (new), Tích hợp LMS/CMS (new), Cấu hình AI, Báo cáo & giám sát, Cài đặt · Lecturer: Trang chủ · Student: Trang chủ · Loading/error screen · app shell (sidebar, nav, footer, search).
Restyled through the shared design system (no layout rewrite): Dashboard, Huấn luyện & dự đoán, Phân cụm & gợi ý, Trợ lý AI (+ Hướng nghiệp, Giải thích bài học), Kho dữ liệu, Mô hình ML, Tài liệu & quy chế, Duyệt tài liệu, Khám phá dữ liệu, Lịch sử tư vấn.

## 6. Design-system changes

- One stylesheet, `dss/styles/main.css`, all colours as tokens: `--bg-primary/secondary`, `--surface/-hover/-elevated`, `--text-primary/secondary/muted/inverse`, `--border/-strong`, `--primary/-hover/-soft`, `--success|warning|danger|info` + `-soft`, `--shadow-sm/md`, `--radius-sm/md/lg`; legacy names aliased to the same tokens.
- Theme switch: Python emits one marker (`.dss-theme-light|dark|system`); CSS selects token set via `:root:has(...)`; `system` follows `prefers-color-scheme`. Default = `system`.
- Typography scale: page 24 · section 18 · card 15 · body 14 · support 13 · caption 12 · metric 26 px; spacing 4/8/12/16/24/32.
- Components: status badge (dot + text, never colour-only), notice, empty/error/loading/unavailable states, KPI row (card), summary strip, key-value rows, list rows, citation chip.
- Buttons: primary (filled), secondary (outline), tertiary (text), danger (container key `danger_*`), consistent 40 px height, focus ring, readable disabled state.
- Charts: every `st.plotly_chart` passes through `style_figure()` — transparent background, theme text/grid colours.
- Data grid (canvas) in dark mode: whole-grid inversion filter (see Known limitations).

## 7. Login status — **IMPLEMENTED, VERIFIED**
Two-column layout (product identity + concise explanation | login card). Username/password with labels, show/hide password (native), primary button, empty-field validation, wrong-credential error, lock-out message (existing), spinner while authenticating. No fabricated numbers, no demo credentials unless explicitly enabled outside production (C1.1 gate unchanged; production test passes). Evidence: `login_light_*`, `login_error_1440x900`, `login_dark_system_1440x900`; AppTest `test_login_validation_wrong_password_and_success`, `test_login_page_has_no_fabricated_metrics_and_explains_provisioning`; E2E login tests.

## 8. Registration / provisioning status — **NOT IMPLEMENTED (by design)**
Self-registration does not exist in the data model/flow and was **not** built. The login card and the Admin "Người dùng" page state the actual flow: student accounts come from the institution's LMS, lecturer/admin accounts are issued by an administrator. A create/edit/lock UI was **not** added: `user_management_service` requires the PostgreSQL identity repository, which could not be exercised in this session (Docker/WSL unavailable — see C1.2 blocker), so it could not be verified.

## 9. Admin UI status — **IMPLEMENTED, VERIFIED (light + dark)**
Overview prioritises real operational gaps ("Cần xử lý": simulated data in use, no Production model, LMS not connected, AI not checked, AI budget alerts) and a component-status list (AI providers show "Chưa kiểm tra" until a real connection test; embedding "Đã cài, chưa nạp"). No success is shown by default. AI Configuration: configured vs connection-checked are separate; keys never rendered (AppTest with a fake key). Integration: "Chưa kết nối" + simulated-event log. Knowledge/regulation page: existing functionality, restyled; approval/version/effective-date UI was not added (not asked to invent it).

## 10. Lecturer UI status — **IMPLEMENTED, VERIFIED (light + dark)**
Home answers "what needs my attention": attention list (relative-risk wording + `RELATIVE_RISK_DISCLAIMER`), today's suggestion, quick actions. R² shown as "R² (tập kiểm tra)" with simulated-data caption (C1.1 helper). Clustering described as K-Means segmentation, not classification. SHAP shown as contribution, not causality (student home).

## 11. Student UI status — **IMPLEMENTED, VERIFIED (light + dark)**
Home: greeting · summary (current score, class average, attendance, relative risk badge) · forecast (neutral gauge, no absolute colour bands) · factors ("không phải quan hệ nhân quả") · next actions derived only from the student's own data · plan button · quick ask with honest unavailable state. No provider/model/RAG/embedding terms on the Home page. Quick-ask `role` NameError bug fixed.

## 12. Light mode — **PASS**
All captured pages render on token colours; no default Streamlit chrome (toolbar minimal, header removed).

## 13. Dark mode — **PASS (with one documented limitation)**
Explicit "Tối" and OS-driven "Hệ thống" both switch page, sidebar, cards, inputs, selects, tabs, expanders, alerts, badges, buttons, charts. Verified by screenshots (`*_dark.png`, `login_dark_system_1440x900.png`) and E2E (`test_theme_switch_changes_real_colours_both_ways`: background `rgb(15, 23, 42)` ↔ `rgb(255, 255, 255)`, input no longer white). Found-and-fixed during acceptance: expanded expander summary stayed white; bordered-card borders invisible; chart title "undefined".
Limitation: `st.dataframe` / `st.data_editor` paint on canvas with Streamlit's light base theme; dark mode inverts the grid as a whole (readable, dark, but not token-exact).

## 14. Responsive status — **PASS at 1440×900, 1366×768, 1024×768**
Every capture records `page_overflow_x=false` and `main_overflow_x=false` (JSON next to each PNG); E2E `test_no_horizontal_page_overflow_on_laptop_viewports[1366/1024]`. Login stacks to one column below 900 px. Phone widths were not in scope.

## 15. Accessibility checks
WCAG contrast of token pairs (computed): light text-primary 16.1:1, text-secondary 6.05, text-muted 4.83 (4.59 on sidebar), primary button 4.51, success 5.24, warning 5.06, danger 4.92, info 4.68 (was 3.93 → token darkened); dark text-primary 17.1, secondary 11.3, muted 6.96, primary button 8.47, status 6.0–9.2. All ≥ 4.5:1.
Visible focus ring on buttons, inputs, selects and nav items; labels above every login/admin input; status never colour-only (text in every badge); error text not colour-only (title + message); disabled state uses muted text on neutral surface; `prefers-reduced-motion` respected for the spinner. Keyboard: Streamlit-native widgets; login submits with Enter. Not verified: screen-reader pass.

## 16. UI / unit tests

Command (non-E2E, whole suite):
`..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=D:/KLTN/_c13pt/full --ignore=tests/e2e tests`
First run: **1052 passed, 3 failed, 168 skipped, 341.29 s**. Final run (after all C1.3 fixes): **1053 passed, 2 failed, 168 skipped, 339.08 s**.
- `test_ui_and_system_audit::test_ui_kit_components_rendering` — C1.3 regression (asserted old hex `#047857`); test updated to assert `dss-status--success`; re-run **passed**.
- `test_c12_release_engineering::test_lock_is_fully_pinned_and_cpu_only`, `::test_third_party_notices_cover_the_lock` — **pre-existing C1.2 failures, not caused by C1.3**: `requirements.txt` starts with a UTF-8 BOM (parsed as package `\ufeff#`) and `THIRD_PARTY_NOTICES.md` does not list `annotated-doc 0.0.5`. C1.3 is forbidden to edit these files.
Targeted re-run: `tests/test_ui_and_system_audit.py tests/test_c1_3_ui_design_system.py` → **31 passed**; `tests/test_c1_3_ui_design_system.py tests/test_dark_mode_and_theme.py` → **28 passed**.
Pre-change baseline (same UI/auth subset, 18 files): 173 passed, 0 failed.

Role isolation is tested (not assumed): `test_sidebar_groups_only_reference_tabs_the_role_may_open`, `test_new_admin_pages_are_admin_only`, plus E2E nav-scope assertions per role.

## 17. Playwright / E2E results

Infrastructure: existing Playwright suite (`tests/e2e`, real Streamlit subprocess with isolated `EDUDSS_DATA_ROOT`, Chromium).

Command: `..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=D:/KLTN/_c13pt/e2e_final -rfEs tests/e2e`
Final result: **48 passed, 0 failed, 0 skipped — 1104.69 s** (2026-09-28).

New C1.3 journeys (`test_c1_3_ui_journeys_e2e.py`, all passed): login page content (provisioning help, no demo credentials, no Deploy chrome, no sidebar) · logout → login screen · theme switch dark ↔ light with real computed colours · student primary journey + nav scope · lecturer primary journey + nav scope · admin primary journey (Home → Người dùng → Tích hợp LMS/CMS → Cấu hình AI) · AI degraded state (student quick-ask with no provider shows "chưa sẵn sàng", nothing sent) · no horizontal overflow at 1366×768 and 1024×768.

First full run (before fixes) was **39 passed, 9 failed**; every failure was investigated:
- 4 search tests used the old emoji placeholder as locator → switched to the stable aria-label `Tìm sinh viên theo mã số` (this also makes the "student has no search box" test meaningful again — it had been passing vacuously).
- 2 lecturer Home/Dashboard tests: the new Home button text "Mở Dashboard lớp học" contained the Dashboard page title, making the test's page-ready wait fire early → button renamed "Mở Dashboard" (UI change).
- `test_admin_login_succeeds` expected the English role "Admin"; the footer now shows "Quản trị viên" → literal updated.
- `test_admin_primary_journey` / `test_provider_health_consistent…`: reads happened before the rerun finished → helpers now wait for the active nav item / for all four provider results; Admin Home no longer computes a class-risk overview it does not display (faster reruns). While debugging, found and fixed an honesty issue: unconfigured providers showed "Không khả dụng" (red) instead of "Chưa cấu hình".
No assertion was removed or loosened.

## 18. Screenshot inventory
`app/reports/final_acceptance/c1_3_screenshots/` (fresh, this worktree, 1440×900 unless stated; each has a `.json` record with overflow, theme marker, background and traceback checks — all `traceback=false`, no overflow):
- Login: `login_light_1440x900`, `login_light_1366x768`, `login_light_1024x768`, `login_error_1440x900`, `login_dark_system_1440x900`
- Admin light: `admin_home_light`, `admin_users_light`, `admin_data_light`, `admin_knowledge_light`, `admin_ai_config_light`, `admin_integration_light`, `admin_reports_light`, `admin_models_light`, `admin_settings_light`, `admin_eda_light`
- Admin dark: `admin_home_dark`, `admin_ai_config_dark`, `admin_users_dark`, `admin_data_dark`
- Lecturer light: `lecturer_home_light`, `lecturer_dashboard_light`, `lecturer_training_light`, `lecturer_clustering_light`, `lecturer_ai_advisor_light`, `lecturer_doc_review_light`, `lecturer_eda_light`
- Lecturer dark: `lecturer_home_dark`, `lecturer_dashboard_dark`, `lecturer_clustering_dark`, `lecturer_training_dark`
- Student light: `student_home_light`, `student_prediction_light`, `student_groups_light`, `student_ai_advisor_light`, `student_history_light`
- Student dark: `student_home_dark`, `student_ai_advisor_dark`, `student_groups_dark`
- Responsive: `lecturer_home_light_1366x768`, `lecturer_dashboard_light_1366x768`, `student_home_light_1366x768`, `lecturer_home_light_1024x768`, `lecturer_dashboard_light_1024x768`, `student_home_light_1024x768`

Defects found by inspecting screenshots and fixed before the final capture: login intro column hidden by marker rule; Deploy toolbar visible; sidebar group titles clipped; KPI cards lost styling; theme switch labels truncated; card borders invisible in dark; tooltip icons invisible in dark; chart title "undefined"; expander summary white in dark; duplicate "Tổng quan" nav title; red risk accent with no data; student summary showing model target column; duplicate page-level headers inside tabs; student single-item tab bar; "Production" jargon for students.

Screenshots show the no-Production-model state (fresh isolated data root); pages with a trained Production model (forecast gauge, factor bars, attention list) are covered by code paths and E2E, not by these captures.

## 19. Known limitations
- Data grid dark mode is an inversion filter (canvas; Streamlit has no per-session native theme API).
- No user create/edit/lock UI (PostgreSQL identity service not verifiable in this session).
- Regulation approval / version / effective-date UI not present (not invented).
- Deep staff pages (EDA, ML hub, warehouse, knowledge base) keep some emoji in section/tab labels and mixed English/Vietnamese labels ("Datasets (Dữ liệu)", "AI Models").
- Student group table shows some raw column names (e.g. `cluster`).
- Risk level can differ between Student Home ("Chưa xác định" — requires a Production prediction) and AI Advisor (percentile of current score). The ML logic was out of scope.
- Hosted/containerised verification not done (Docker blocked, see C1.2); all runs are local Windows.

## 20. Remaining defects by severity
- **P0**: none known.
- **P1**: none known.
- **P2**: risk-level inconsistency between Student Home and AI Advisor; data-grid dark mode is inversion-based; no user-management CRUD UI.
- **P3**: residual emoji and mixed-language labels on deep staff pages; raw column names in student cluster table; "Chọn sinh viên" heading shown to students on AI Advisor.

## Final labels

```
C1_3_UI_IMPLEMENTATION   = PARTIAL
VISUAL_ACCEPTANCE        = PASS
ROLE_UI_ACCEPTANCE       = PASS
DARK_MODE_ACCEPTANCE     = PASS
REGISTRATION_ACCEPTANCE  = NOT IMPLEMENTED
E2E_UI_ACCEPTANCE        = PASS
SAFE_TO_PROCEED          = YES
```

Label rationale: implementation is **PARTIAL** because the shell, design system, login, all three role homes and the Admin pages were redesigned, but deep staff pages (EDA, ML hub, warehouse, knowledge base) were restyled through the shared design system rather than redesigned, and user-management CRUD was not built. VISUAL / DARK / ROLE / E2E are PASS on rendered evidence from this worktree. SAFE_TO_PROCEED = YES for the C1.3 changes (no P0/P1 open, C1.1 controls intact — C1.1 tests pass); this does **not** clear the separate C1.2 blockers (Docker/WSL, lock-file BOM and notices mismatch).
