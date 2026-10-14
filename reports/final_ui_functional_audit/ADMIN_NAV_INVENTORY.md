# Admin Navigation Inventory — Live, from `dss/main.py` SIDEBAR_NAV_GROUPS["Admin"]

1. **🏡 Trang chủ** — reuses `admin_reports_tab()` (no separate Admin Dashboard exists by design).
   Screenshotted earlier this session (`admin_reports.png`, `admin_home.png`) — confirmed the
   `MODELREG-001-FOLLOWUP` fix renders correctly (3-state model chart). PASS.
2. **🔍 Khám phá — Xử lý dữ liệu** — shared with Giảng viên, already walked this session in the
   Lecturer phase (`lect_03_explore.png`). Same code path, same PASS verdict applies to Admin.
3. **📦 Kho dữ liệu** — screenshotted earlier (`lect_warehouse.png` equivalent checks); Admin sees
   the same 3 sub-tabs as Giảng viên plus full Promote/Rollback rights on Model Registry entries.
   Not yet re-walked live as Admin specifically this pass.
4. **🗄️ Model Registry** — screenshotted earlier (`admin_model_registry.png`), confirmed 3-state
   lifecycle badges render correctly with real data (2 Production, 2 Candidate, rest Archived).
5. **🤖 Tư vấn — AI (LLM)** — not yet walked live as Admin this pass (Admin sees the same 3
   sub-tabs as Giảng viên plus provider-key configuration).
6. **📚 Quản lý tri thức (RAG)** — screenshotted earlier (`admin_rag.png`), confirmed honest
   "Tri thức Mẫu (Demo)" labeling, namespace listing, real ingestion pipeline. PASS.
7. **⚙️ Cấu hình AI** — screenshotted earlier (`admin_ai_config.png`), confirmed real per-provider
   health-check UI from the original AI-provider-availability investigation phase. PASS.
8. **📈 Báo cáo hệ thống** — same underlying function as Trang chủ for Admin (by design, see
   `home.py::_render_admin_home_dashboard`'s comment) — already covered.
9. **🔧 Cài đặt** — screenshotted before AND after this session's `DEMO-LMS-STATUS-001` fix
   (`admin_settings_fixed.png`) — confirmed honest LMS/CMS status, read-only User Management
   correctly documented (not fixed, by design per explicit instruction).

This inventory is the walk order for the remaining live acceptance pass below (items 3 and 5,
the two not yet specifically re-verified as Admin, plus a final consistency spot-check on 1/4/6/7/9
now that multiple fixes have landed since they were last screenshotted).
