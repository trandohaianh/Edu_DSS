# EduDSS — Checklist bảo mật (bước 7)

> **Trạng thái:** rà soát ngày 21/11/2026 trên commit c8ff505. Nhóm A sửa cùng ngày (`tests/test_security_step7.py`).
> Nhóm B làm phần kỹ thuật ngày 22/11/2026 (`tests/test_security_step7_group_b.py`); **nội dung pháp lý vẫn chờ luật sư**
> (xem [../legal/PRIVACY_NOTICE_DRAFT.md](../legal/PRIVACY_NOTICE_DRAFT.md)).

Tài liệu liên quan: [../requirements/PRD.md](../requirements/PRD.md) ·
[../requirements/ACCEPTANCE_CRITERIA.md](../requirements/ACCEPTANCE_CRITERIA.md) ·
[../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md)

## 1. Checklist

| # | Mục | Kết quả sau khi sửa | Bằng chứng / ghi chú |
|---|---|---|---|
| 1 | Không để khoá API, mật khẩu trong code | ✅ Đạt | `tools/secret_scan.py`: 0 phát hiện. Tài khoản demo chỉ tạo ngoài production (`dss/core/runtime_mode.py`). `python -m dss.db.seed` nay **từ chối chạy ở production** (`dss/db/seed.py`) |
| 2 | Không đưa `.env` có bí mật lên GitHub | ✅ Đạt | Chỉ có file `*.example`. `.gitignore` chặn `.env`, `*.pem`, `*.key`, `secrets.toml`. Lịch sử git sạch |
| 3 | Kiểm tra quyền ở tầng xử lý | ✅ Đạt | Menu lọc theo vai trò ở phía server. Trang **chưa khai báo quyền thì không ai thấy** (`dss/core/roles.py::filter_tabs_for_role`). 3 trang giảng viên có `@require_role`. **Giảng viên chỉ thấy sinh viên các lớp được gán** ở trang Lớp học (`dss/services/lecturer_scope.py`, lọc một chỗ trong `main.py`, lỗi thì thấy 0 dòng). Bật khi dùng dữ liệu thật; bản demo mô phỏng vẫn xem toàn bộ |
| 4 | Kiểm tra dữ liệu đầu vào | ✅ Đạt | File tải lên: dung lượng, định dạng, MIME, macro, zip bomb (`dss/security/upload_security.py`). Mọi file **xuất** (Excel/CSV) đều được trung hoà công thức (`dss/security/export_safety.py`). Văn bản đưa vào prompt được làm sạch (`prompt_security`). Webhook LMS ký HMAC |
| 5 | Chống SQL injection, XSS, CSRF | ✅ Đạt (đã sửa XSS) | SQL dùng tham số. CSRF của Streamlit đang bật. Đã thoát ký tự HTML ở ~10 chỗ chèn dữ liệu/AI vào HTML. `badge_html`, `source_citation_badge` luôn thoát. Kế hoạch AI chỉ giữ thẻ `<br>` (`ui_kit.markdown_keep_br_only`) |
| 6 | Xác thực và phiên đăng nhập | ✅ Đạt | PBKDF2-SHA256 600.000 vòng, khoá 5 lần sai / 15 phút. Sau Caddy, khoá theo **IP thật** (Caddy ghi đè `X-Real-IP`, app đọc qua `EDUDSS_CLIENT_IP_HEADER`). **Tự đăng xuất sau 30 phút không thao tác** (`EDUDSS_IDLE_TIMEOUT_MINUTES`, tối thiểu 5); khung tự làm mới của Dashboard không tính là thao tác |
| 7 | Giới hạn số lần gọi API | ✅ Đạt | Hạn mức token theo người, trần ngân sách AI 5 USD/tháng, 60 yêu cầu/phút. Trang Hướng nghiệp nay cũng đi qua các cổng này và bộ lọc lời khuyên có hại |
| 8 | Không lộ dữ liệu nhạy cảm qua log | ✅ Đạt | Che email, khoá API, mã `SV…`. **Tên đăng nhập được thay bằng mã băm** `u#…` (`dss/security/log_redaction.py`). Bộ lọc AI không ghi nội dung câu trả lời |
| 9 | Quyền tối thiểu | ✅ Đạt | App dùng role CSDL thường, RLS FORCE, container không chạy root. Caddy ghim phiên bản và digest ở cả 3 cấu hình triển khai |
| 10 | Thư viện và dịch vụ ngoài | 🟡 Một phần | 126 gói đã ghim. `pip-audit` ngày 22/11/2026: 7 gói có lỗ hổng. **Đã nâng 6 gói**: certifi 2026.10.18, filelock 4.2.1, GitPython 3.2.1, pyasn1 0.6.5, pypdf 6.21.4, tornado 6.6.1. **Còn Pillow 12.3.0** (42 lỗ hổng, bản vá 13.0.0): Streamlit 1.54 chặn `pillow<13`, phải nâng Streamlit (≥ bản cho phép `pillow<14`, mới nhất 1.67.0), chờ chủ dự án quyết. torch không quét được (bản `+cpu` không có trên PyPI) |
| 11 | Pháp lý dữ liệu cá nhân Việt Nam | 🟡 Một phần | Đã có: thông báo + đồng ý sau đăng nhập (ghi bằng chứng theo phiên bản), nút xuất/xoá dữ liệu cho Admin, danh sách chính xác dữ liệu gửi ra AI. **Chưa có: luật sư duyệt văn bản, quyết định về hồ sơ chuyển dữ liệu ra nước ngoài** |

## 2. Đã sửa ngày 21/11/2026 (nhóm A)

| Rủi ro | Mức | Sửa | Test |
|---|---|---|---|
| Hướng nghiệp gọi AI thẳng, bỏ qua hạn mức, ngân sách và bộ lọc an toàn | Cao | `dss/tabs/advisory.py`: `check_quota_and_rate_limit` + `guard_stream` | `test_career_chat_goes_through_quota_budget_and_output_guard` |
| XSS ở ~10 chỗ chèn dữ liệu/câu trả lời AI vào HTML | Trung bình | `html.escape` tại chỗ gọi; `ui_kit` luôn thoát | `test_badge_and_citation_always_escape`, `test_ai_plan_keeps_only_br_tags`, `test_no_unescaped_interpolation_left_at_reported_sites` |
| Chèn công thức khi xuất Excel/CSV (đã thử thật: `=HYPERLINK(...)` thành công thức) | Trung bình | `safe_for_spreadsheet` ở 6 chỗ xuất | `test_export_neutralizes_formula_cells_but_keeps_numbers`, `test_lecturer_workbook_contains_no_formula` |
| Sau proxy mọi người chung IP → kẻ xấu khoá tài khoản người khác | Trung bình | Caddy `header_up X-Real-IP {remote_host}` + `EDUDSS_CLIENT_IP_HEADER` | `test_proxy_overwrites_real_ip_and_app_reads_it` |
| `python -m dss.db.seed` tạo `admin/admin123` trên CSDL production | Thấp | Từ chối khi không phải development/test | `test_demo_seed_refuses_production` |
| Trang chưa khai báo quyền thì mọi vai trò thấy | Thấp | Mặc định không ai thấy | `test_undeclared_tab_is_hidden_from_everyone` |
| Tên đăng nhập ghi nguyên văn vào log | Thấp | Thay bằng mã băm | `test_usernames_are_hashed_in_logs` |
| Caddy production/cloud không ghim phiên bản | Thấp | Ghim `caddy:2.10.2-alpine@sha256:…` | `test_proxy_overwrites_real_ip_and_app_reads_it` |

## 3. Nhóm B — đã làm ngày 22/11/2026

| Việc | Làm gì | Test |
|---|---|---|
| Thông báo + đồng ý | `dss/services/privacy_notice.py`: hiện ngay sau đăng nhập; từ chối thì đăng xuất; bằng chứng ghi vào `lp_audit_events` theo `NOTICE_VERSION`; không ghi được thì không cho vào | `test_consent_is_recorded_per_user_and_version`, `test_main_runs_consent_gate_right_after_login` |
| Xuất/xoá dữ liệu sinh viên | Trang Người dùng (Admin): tải JSON, xoá phải gõ lại mã + tick xác nhận; gọi `data_lifecycle` | `test_data_rights_panel_is_admin_only`, `test_data_rights_panel_calls_lifecycle_and_confirms_erasure` |
| Giảng viên chỉ xem lớp mình | `dss/services/lecturer_scope.py`; sửa điểm khi đang lọc được ghép lại vào bộ đầy đủ | `test_lecturer_sees_only_students_of_assigned_classes`, `test_lecturer_scope_fails_closed_and_skips_other_roles`, `test_scoped_grade_edits_merge_back_without_losing_other_classes` |
| Tự đăng xuất | 30 phút, chỉnh bằng env | `test_session_expires_only_after_idle_period` |
| Quét thư viện | `pip-audit`; nâng 6 gói | `test_lock_file_has_patched_versions` |
| Dữ liệu gửi ra AI | Liệt kê ở thông báo và `docs/legal/PRIVACY_NOTICE_DRAFT.md` §2 | `test_notice_lists_exactly_what_is_sent_to_ai` |

## 4. Rủi ro còn tồn tại

| Rủi ro | Mức | Đề xuất | Ai quyết |
|---|---|---|---|
| Văn bản thông báo chưa được luật sư duyệt; chưa rõ có cần hồ sơ chuyển dữ liệu ra nước ngoài (Nghị định 13/2023, Luật BVDLCN 2025) | Cao | Gửi `docs/legal/PRIVACY_NOTICE_DRAFT.md` §3 (5 câu hỏi) cho luật sư trước thí điểm | Chủ dự án + luật sư |
| Pillow 12.3.0 còn 42 lỗ hổng đã biết | Trung bình | Nâng Streamlit lên bản cho phép Pillow 13, rồi kiểm lại toàn bộ giao diện (nhiều CSS tuỳ biến) | Chủ dự án |
| Xoá dữ liệu chỉ phủ PostgreSQL; kho dạng tệp và bản sao lưu chưa được xoá theo | Trung bình | Bản sao lưu: tự hết hạn sau 14 ngày, đã ghi vào thông báo bảo mật. Dự đoán, tư vấn, hoạt động, token AI: **đã chuyển sang PostgreSQL** và được xoá/ẩn theo (bước 9, `tests/test_step9_file_stores_postgres.py`). Còn mở: 3 kho CMS (`cms/*.json`) và bộ dữ liệu tải lên dạng tệp | — |
| Giảng viên chưa được gán lớp thì thấy 0 sinh viên (cố ý) | Thấp | Admin gán lớp ở trang Lớp học trước thí điểm | Nhà trường |
| Giới hạn 60 yêu cầu/phút tính chung và trong bộ nhớ từng tiến trình | Thấp | Giới hạn theo từng người dùng | — |
| CSP cho phép `'unsafe-inline' 'unsafe-eval'` (Streamlit cần) | Thấp | Giữ; XSS đã chặn bằng thoát ký tự | — |
| Webhook LMS trong RAM không có cửa sổ thời gian chống phát lại; chưa nối vào entrypoint nào | Thấp | Xử lý khi làm tích hợp LMS (đã để sau) | — |
| "So sánh AI" (giảng viên/Admin) chưa qua bộ lọc lời khuyên có hại | Thấp | Bọc `guard_stream` khi cần | — |
