# EduDSS — Checklist bảo mật (bước 7)

> **Trạng thái:** rà soát ngày 21/11/2026 trên commit c8ff505. Các lỗi kỹ thuật nhóm A đã sửa cùng ngày, test hồi quy ở
> `tests/test_security_step7.py`. Nhóm B (dữ liệu cá nhân, phạm vi giảng viên...) **chờ chủ dự án quyết và luật sư rà soát**.

Tài liệu liên quan: [../requirements/PRD.md](../requirements/PRD.md) ·
[../requirements/ACCEPTANCE_CRITERIA.md](../requirements/ACCEPTANCE_CRITERIA.md) ·
[../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md)

## 1. Checklist

| # | Mục | Kết quả sau khi sửa | Bằng chứng / ghi chú |
|---|---|---|---|
| 1 | Không để khoá API, mật khẩu trong code | ✅ Đạt | `tools/secret_scan.py`: 0 phát hiện. Tài khoản demo chỉ tạo ngoài production (`dss/core/runtime_mode.py`). `python -m dss.db.seed` nay **từ chối chạy ở production** (`dss/db/seed.py`) |
| 2 | Không đưa `.env` có bí mật lên GitHub | ✅ Đạt | Chỉ có file `*.example`. `.gitignore` chặn `.env`, `*.pem`, `*.key`, `secrets.toml`. Lịch sử git sạch |
| 3 | Kiểm tra quyền ở tầng xử lý | 🟡 Một phần | Menu lọc theo vai trò ở phía server. Trang **chưa khai báo quyền thì không ai thấy** (`dss/core/roles.py::filter_tabs_for_role`). 3 trang giảng viên có `@require_role`. Còn mở: giảng viên xem dữ liệu của mọi sinh viên trong bộ dữ liệu (nhóm B) |
| 4 | Kiểm tra dữ liệu đầu vào | ✅ Đạt | File tải lên: dung lượng, định dạng, MIME, macro, zip bomb (`dss/security/upload_security.py`). Mọi file **xuất** (Excel/CSV) đều được trung hoà công thức (`dss/security/export_safety.py`). Văn bản đưa vào prompt được làm sạch (`prompt_security`). Webhook LMS ký HMAC |
| 5 | Chống SQL injection, XSS, CSRF | ✅ Đạt (đã sửa XSS) | SQL dùng tham số. CSRF của Streamlit đang bật. Đã thoát ký tự HTML ở ~10 chỗ chèn dữ liệu/AI vào HTML. `badge_html`, `source_citation_badge` luôn thoát. Kế hoạch AI chỉ giữ thẻ `<br>` (`ui_kit.markdown_keep_br_only`) |
| 6 | Xác thực và phiên đăng nhập | 🟡 Một phần | PBKDF2-SHA256 600.000 vòng, khoá 5 lần sai / 15 phút. Sau Caddy, khoá theo **IP thật** (Caddy ghi đè `X-Real-IP`, app đọc qua `EDUDSS_CLIENT_IP_HEADER`). Còn mở: chưa tự đăng xuất khi không thao tác (nhóm B) |
| 7 | Giới hạn số lần gọi API | ✅ Đạt | Hạn mức token theo người, trần ngân sách AI 5 USD/tháng, 60 yêu cầu/phút. Trang Hướng nghiệp nay cũng đi qua các cổng này và bộ lọc lời khuyên có hại |
| 8 | Không lộ dữ liệu nhạy cảm qua log | ✅ Đạt | Che email, khoá API, mã `SV…`. **Tên đăng nhập được thay bằng mã băm** `u#…` (`dss/security/log_redaction.py`). Bộ lọc AI không ghi nội dung câu trả lời |
| 9 | Quyền tối thiểu | ✅ Đạt | App dùng role CSDL thường, RLS FORCE, container không chạy root. Caddy ghim phiên bản và digest ở cả 3 cấu hình triển khai |
| 10 | Thư viện và dịch vụ ngoài | 🟡 Một phần | 126 gói đã ghim (`requirements.lock.txt`). **Chưa quét lỗ hổng bằng `pip-audit`**: cần gửi danh sách gói tới dịch vụ ngoài, chờ chủ dự án đồng ý |
| 11 | Pháp lý dữ liệu cá nhân Việt Nam | 🔴 Chưa đạt | Xem §3. Cần luật sư rà soát |

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

## 3. Rủi ro còn tồn tại (nhóm B — cần chủ dự án quyết)

| Rủi ro | Mức | Đề xuất | Ai quyết |
|---|---|---|---|
| Chưa có thông báo quyền riêng tư và xin đồng ý. Hàm xuất/xoá dữ liệu của sinh viên (`dss/services/data_lifecycle.py`: `export_student_data`, `erase_student_data`) có sẵn nhưng **không có nút nào gọi** | Cao | Trang thông báo + nút đồng ý lần đầu đăng nhập; nút xuất/xoá dữ liệu cho Admin. Nội dung văn bản do chủ dự án/luật sư duyệt | Chủ dự án + luật sư |
| Dữ liệu gửi ra AI ở nước ngoài (OpenAI/Gemini/Groq): mã SV đã thay bằng bút danh nhưng vẫn có điểm dự đoán, điểm yếu, khoảng GPA và câu hỏi của sinh viên. Theo Nghị định 13/2023/NĐ-CP và Luật Bảo vệ dữ liệu cá nhân 2025 (hiệu lực 1/1/2026) có thể cần hồ sơ đánh giá tác động chuyển dữ liệu ra nước ngoài — **chưa xác minh, cần luật sư** | Cao | Liệt kê chính xác trường dữ liệu gửi đi trong thông báo; cân nhắc nhà cung cấp có máy chủ/hợp đồng phù hợp | Chủ dự án + luật sư |
| Giảng viên xem dữ liệu của mọi sinh viên trong bộ dữ liệu (chưa có phân lớp) | Trung bình | Gán giảng viên ↔ lớp và lọc theo lớp (1–2 ngày) | Chủ dự án |
| Không tự đăng xuất khi không thao tác | Thấp | Hết phiên sau N phút (đề xuất 30) | Chủ dự án |
| Chưa quét lỗ hổng thư viện | Thấp | Chạy `pip-audit` (gửi danh sách gói, không có dữ liệu cá nhân) | Chủ dự án đồng ý gửi |
| Giới hạn 60 yêu cầu/phút tính chung và trong bộ nhớ từng tiến trình | Thấp | Giới hạn theo từng người dùng | — |
| CSP cho phép `'unsafe-inline' 'unsafe-eval'` (Streamlit cần) | Thấp | Giữ; XSS đã chặn bằng thoát ký tự | — |
| Webhook LMS trong RAM không có cửa sổ thời gian chống phát lại; chưa nối vào entrypoint nào đang chạy | Thấp | Xử lý khi làm tích hợp LMS (đã để sau) | — |
| "So sánh AI" (giảng viên/Admin) chưa qua bộ lọc lời khuyên có hại | Thấp | Bọc `guard_stream` khi cần | — |
