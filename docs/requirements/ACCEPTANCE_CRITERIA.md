# EduDSS — Tiêu chí chấp nhận (đo được)

> **Trạng thái: BẢN NHÁP — đã cập nhật theo quyết định của chủ dự án ngày 21/11/2026.** Còn chờ: RPO/RTO
> (§5), AC-ML-11/12 có chặn bàn giao không (§7). Soạn dựa trên commit 6e9710d.

Tài liệu này biến các biên bản nghiệm thu đã có trong `reports/` thành **tiêu chí đo được**. Mỗi tiêu chí
có mã riêng, cách kiểm, bằng chứng đang có và trạng thái. Không có con số nào được tự đặt ra: ngưỡng lấy từ
code, từ `evals/thresholds.json` hoặc từ chính các báo cáo. Chỗ chưa có ngưỡng thì để **⏳**.

Tài liệu liên quan: [PRD.md](PRD.md) · [MVP_SCOPE.md](MVP_SCOPE.md) ·
[../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) · [../database/SCHEMA.md](../database/SCHEMA.md) ·
[../ux/SCREEN_MAP.md](../ux/SCREEN_MAP.md)

---

## 1. Cách đọc

- **Mã:** `AC-SV` sinh viên · `AC-GV` giảng viên/CVHT · `AC-AD` quản trị (gồm `Platform Admin`) ·
  `AC-BM` bảo mật · `AC-HN` hiệu năng · `AC-ML` chất lượng mô hình và AI.
- **Trạng thái** chỉ có 2 mức:
  - **Đạt có bằng chứng**: có báo cáo hoặc kết quả chạy trong repo ghi rõ là đạt.
  - **Chưa có bằng chứng**: chưa có báo cáo, hoặc chỉ có test mà chưa có biên bản kết quả chạy.
- Các biên bản trong `reports/` được viết **sau khi** làm xong (PRD §8). Nhiều biên bản chạy trên nhánh
  hay commit cũ hơn 6e9710d. Trước khi bàn giao, cần **chạy lại** trên bản sẽ giao.
- Dữ liệu đi kèm là **mô phỏng**. Mô hình chưa được kiểm trên sinh viên thật của trường (`README.md:171-182`).

## 2. Sinh viên

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-SV-01 | Menu sinh viên chỉ có đúng 6 trang: Trang chủ, Lớp học và đánh giá, Dự đoán kết quả, Nhóm học tập & gợi ý, Trợ lý AI, Lịch sử tư vấn (`dss/main.py:226-232`). Không có nút huấn luyện hay cấu hình K-Means | Đăng nhập tài khoản SV, đếm mục menu, mở từng trang | `reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:9-20`, `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:132` (`test_student_primary_journey_and_nav_scope`) | Đạt có bằng chứng |
| AC-SV-02 | Sinh viên chỉ thấy dữ liệu của chính mình ở mọi trang: 0 bản ghi của mã SV khác | Đăng nhập SV A, thử xem dữ liệu SV B; chạy `tests/test_data_isolation.py`, `tests/e2e/test_data_isolation_e2e.py` | `reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:26-33`, `reports/final_ui_functional_audit/RELEASE_FREEZE.md:345-346` | Đạt có bằng chứng |
| AC-SV-03 | Có mô hình Production: Trang chủ hiện mức rủi ro, yếu tố ảnh hưởng và việc nên làm. Chưa có mô hình: hiện trạng thái trống, không hiện số giả | Mở Trang chủ ở 2 trường hợp có/không có mô hình Production | `reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:3-4`, `:26` | Đạt có bằng chứng |
| AC-SV-04 | Tạo được kế hoạch học tập khi **không** có LLM và **không** có cột GPA. Kế hoạch còn nguyên ở phiên đăng nhập mới. Đánh dấu tiến độ được lưu | Trợ lý AI → Kế hoạch học tập → "Kế hoạch và tiến độ đã lưu" (`reports/stage1_learning/ACCEPTANCE.md:27-28`) | `reports/stage1_learning/ACCEPTANCE.md:16-19`, `:49-58`; `docs/architecture/EDUDSS_MINISTRY_ROADMAP.md:55-58` | Đạt có bằng chứng |
| AC-SV-05 | Khi chưa cấu hình nhà cung cấp AI, ô hỏi nhanh báo "chưa sẵn sàng" và **không gửi** gì đi | Tắt mọi khoá AI, gửi một câu hỏi | `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:132` | Đạt có bằng chứng |
| AC-SV-06 | Lịch sử tư vấn chỉ hiện các lượt của đúng mã SV đang đăng nhập | So sánh lịch sử của 2 tài khoản SV | `reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:33` | Đạt có bằng chứng |
| AC-SV-07 | Làm bài đánh giá trong lớp: không thấy đáp án, nộp trùng không tạo 2 lượt, kế hoạch gắn theo lớp | Làm bài, bấm nộp 2 lần, xem kế hoạch | `reports/stage23/ACCEPTANCE.md:14-15`, `:55` | Đạt có bằng chứng (thí điểm kỹ thuật) |
| AC-SV-08 | Màn cảnh báo rủi ro hiện quy tắc đơn giản "G1 < 10" ngay cạnh kết quả mô hình. Eval ghi rằng ở giữa kỳ mô hình **không thắng** quy tắc này | Mở màn rủi ro, tìm dòng quy tắc | Yêu cầu nằm ở `evals/README.md:79-80` và `evals/thresholds.json:39`. Không tìm thấy chuỗi "G1 < 10" trong `dss/` | Chưa có bằng chứng |
| AC-SV-09 | Trên điện thoại (375×812 và 430×932): Trang chủ, Dự đoán, Kế hoạch học tập, Lịch sử tư vấn không tràn ngang, sidebar thu gọn không che nội dung, chuyển được cả 4 trang bằng thanh điều hướng trên cùng, nút cao ≥ 40px | `tests/e2e/test_c1_3_ui_journeys_e2e.py::test_student_pages_usable_on_phone` (2 khổ) và `::test_mobile_nav_hidden_on_desktop` | Test e2e đạt 12/12 ngày 21/11/2026 trên máy dev; kiểm tay bằng trình duyệt ở 375/430 px cả khi chưa có và đã có mô hình Production | Đạt có bằng chứng (trình duyệt giả lập; **chưa thử trên điện thoại thật**) |

## 3. Giảng viên / CVHT

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-GV-01 | Menu giảng viên có đúng 11 trang theo `dss/main.py:233-240`. Không có Model Registry, Cấu hình AI, Người dùng | Đăng nhập GV, đếm mục menu | `reports/final_ui_functional_audit/LECTURER_ACCEPTANCE.md:8-19`, `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:132` | Đạt có bằng chứng (biên bản chưa đi qua Lớp học, Chương trình, Duyệt tài liệu) |
| AC-GV-02 | Trang chủ hiện số SV nhóm rủi ro cao và tối đa 6 tên (`dss/tabs/home.py:151-163`). Dashboard có bảng tối đa 20 dòng, tìm được theo mã SV (`dss/tabs/dashboard.py:540-551`). Cả hai ghi rõ đây là xếp hạng tương đối, không phải xác suất (`dss/tabs/ui_kit.py:462`) | Mở Trang chủ và Dashboard với một lớp có mô hình Production | `reports/final_ui_functional_audit/LECTURER_ACCEPTANCE.md:10-11` | Đạt có bằng chứng |
| AC-GV-03 | Gõ mã SV ở ô tìm → bấm "Xem phân tích" → mở Trợ lý AI với SV đó đã được chọn sẵn | Thao tác trên giao diện (`dss/main.py:380-407`) | Không có biên bản riêng cho bước này | Chưa có bằng chứng |
| AC-GV-04 | Huấn luyện chỉ tạo bản **Candidate**. 0 trường hợp tự lên Production | Huấn luyện 1 mô hình, xem trạng thái trong Kho dữ liệu → AI Models | `dss/services/model_service.py:227-248`; `reports/final_ui_functional_audit/LECTURER_ACCEPTANCE.md:28-36` (`tests/test_model_lifecycle_badge.py`) | Đạt có bằng chứng |
| AC-GV-05 | Giảng viên **không** đổi được bản Production: nút bị ẩn và hàm bị chặn (`@require_role("Admin")`) | Đăng nhập GV, tìm nút Promote; gọi `model_registry.promote` bằng vai trò GV | `dss/tabs/warehouse_tab.py:616-619`, `dss/services/model_registry.py:253-254` | Chưa có bằng chứng (có code, chưa có biên bản chạy riêng) |
| AC-GV-06 | "Dự đoán — Hàng loạt" xuất được kết quả cho cả lớp | Chạy dự đoán hàng loạt, tải tệp kết quả | `dss/main.py:779-797`, `dss/tabs/ml_hub.py:1026`. Biên bản giảng viên không có dòng này | Chưa có bằng chứng |
| AC-GV-07 | Soạn bài MCQ, xuất bản thành phiên bản không sửa được, xem tiến độ lớp | Soạn → xuất bản → sửa thử bản đã xuất bản | `reports/stage23/ACCEPTANCE.md:12-13`, `:55` | Đạt có bằng chứng (thí điểm kỹ thuật) |
| AC-GV-08 | Duyệt tài liệu chỉ cho môn giảng viên phụ trách | Đăng nhập GV môn A, thử duyệt tài liệu môn B | `dss/tabs/knowledge_base.py:422`, chú thích `dss/core/roles.py:212-217` | Chưa có bằng chứng |
| AC-GV-09 | Trang **Báo cáo** (`dss/tabs/lecturer_pages.py::render_reports_tab`): 4 ô số (số SV, nguy cơ cao, chỉ số mô hình thật, số phiên tư vấn), biểu đồ tóm tắt rủi ro, biểu đồ chỉ số mô hình qua các phiên bản, nút xuất Excel 5 trang tính. Phạm vi = **bộ dữ liệu đang dùng** (quyết định 21/11/2026: bản Streamlit chưa lưu giảng viên phụ trách lớp nào). Chỉ Giảng viên / CVHT thấy | Mở trang; so ô "Nguy cơ cao" với Trang chủ; mở file Excel | `tests/test_lecturer_reports.py` (14 test), `tests/e2e/test_c1_3_ui_journeys_e2e.py::test_lecturer_pages_open_without_error_and_are_hidden_from_students`; kiểm tay 21/11/2026 trên dữ liệu mô phỏng 20.000 SV có mô hình Production | Đạt có bằng chứng |
| AC-GV-10 | Trang **Lịch sử tư vấn** của giảng viên: lọc theo mã SV, khoảng ngày và "chỉ phiên do tôi tư vấn"; xem đầy đủ một phiên; xuất Excel. Phiên mới ghi `performed_by` (`dss/core/warehouse.py::save_ai_consultation`); phiên cũ hiện "không rõ" | Lọc với dữ liệu có cả phiên mới và cũ | `tests/test_lecturer_reports.py` (14 test), `tests/e2e/test_c1_3_ui_journeys_e2e.py::test_lecturer_pages_open_without_error_and_are_hidden_from_students`; kiểm tay 21/11/2026 trên dữ liệu mô phỏng 20.000 SV có mô hình Production. Lưu ý: khi `EDUDSS_CONSULTATIONS_STORE=postgres`, bảng `consultations` chưa có cột người tư vấn | Đạt có bằng chứng (chế độ lưu file) |
| AC-GV-11 | Trang **Phân tích rủi ro**: số SV nguy cơ cao / trung bình / thấp và điểm dự đoán trung bình **khớp Trang chủ** (cùng hàm `compute_lecturer_dashboard_overview`); biểu đồ phân bố; yếu tố quan trọng nhất từ mô hình Production; bảng SV nguy cơ cao và nút "Xem phân tích" mở Trợ lý AI đúng SV | So số với Trang chủ trên cùng dữ liệu | `tests/test_lecturer_reports.py` (14 test), `tests/e2e/test_c1_3_ui_journeys_e2e.py::test_lecturer_pages_open_without_error_and_are_hidden_from_students`; kiểm tay 21/11/2026 trên dữ liệu mô phỏng 20.000 SV có mô hình Production: 4.998 nguy cơ cao, TB 6,89 ở cả 2 trang | Đạt có bằng chứng |

## 4. Quản trị (Admin, Platform Admin)

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-AD-01 | Menu Admin có đúng 14 trang theo `dss/main.py:241-252` | Đăng nhập Admin, đếm mục menu | `reports/final_ui_functional_audit/ADMIN_ACCEPTANCE.md:3-19` (9 trang), `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:132` (Home → Người dùng → Tích hợp LMS/CMS → Cấu hình AI) | Đạt có bằng chứng một phần: chưa có biên bản đi qua Học liệu, Lớp học, Chương trình |
| AC-AD-02 | Tải được tệp CSV/Excel (`csv`, `xlsx`, `xls`) vào Kho dữ liệu. Tệp không hợp lệ bị từ chối | Tải 1 tệp đúng và 1 tệp sai định dạng | `dss/tabs/warehouse_tab.py:198`, `dss/security/upload_security.py`, `tests/test_security_upload.py`; `reports/final_ui_functional_audit/ADMIN_ACCEPTANCE.md:13` | Đạt có bằng chứng |
| AC-AD-03 | Mỗi cặp Dataset + Target có **đúng 1** bản Production. Promote và Rollback đổi được bản đó | Promote 1 Candidate, kiểm tra bản cũ thành Archived | `dss/tabs/warehouse_tab.py:440-443`; `reports/final_ui_functional_audit/ADMIN_ACCEPTANCE.md:14-15` | Đạt có bằng chứng |
| AC-AD-04 | Tạo được tài khoản Admin/Platform Admin đầu tiên mà không cần tài khoản demo. Tạo trùng thì bị từ chối | Chạy `ops/bootstrap_identity.py` trên CSDL trống, chạy lại lần 2 | `reports/stage23/ACCEPTANCE.md:27-28` | Đạt có bằng chứng |
| AC-AD-05 | Nhập danh sách lớp CSV theo kiểu "tất cả hoặc không": chỉ cần 1 dòng lỗi là không nhập dòng nào | Nhập tệp có 1 dòng sai (`dss/tabs/classroom_tab.py:47-49`) | `reports/stage23/ACCEPTANCE.md:10-11`, `:70` | Đạt có bằng chứng |
| AC-AD-06 | Số liệu tổng hợp công bố cho chương trình: nhóm tối thiểu 5 SV, ô nhỏ bị ẩn | Công bố một lớp có dưới 5 SV | `reports/stage23/ACCEPTANCE.md:24-26` | Đạt có bằng chứng |
| AC-AD-07 | Chỉ Admin thấy Cấu hình AI. Khoá API không được lưu trong CSDL | Đăng nhập GV/SV, tìm trang; kiểm tra bảng cấu hình | `dss/core/roles.py:219`; `docs/operations/BACKUP_RECOVERY_RUNBOOK.md:10-11`; `reports/final_ui_functional_audit/ADMIN_ACCEPTANCE.md:18` | Đạt có bằng chứng |
| AC-AD-08 | (`Platform Admin`) Nhận trường B mà trường A vẫn chạy bình thường. RLS chặn xem chéo theo cả 2 chiều | `test_university_onboarding.py::test_01_onboard_university_b_while_university_a_remains_operational` | `reports/production_readiness/ABC_ONBOARDING_INTEGRATION.md:57-69` | Đạt có bằng chứng |

## 5. Bảo mật

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-BM-01 | Sai mật khẩu **5 lần** thì khoá tài khoản **15 phút** (`dss/security/login_throttle.py:31-33`). Khoá vẫn còn sau khi khởi động lại app | Nhập sai 5 lần, thử lần 6 với mật khẩu đúng; khởi động lại rồi thử tiếp | `tests/test_c1_production_mode_and_auth.py:167-229`; `reports/final_acceptance/C1_1_SECURITY_PRIVACY_HARDENING.md:76`, `:264` | Đạt có bằng chứng (xem Mâu thuẫn số 6) |
| AC-BM-02 | Ở production: 0 tài khoản demo được tạo, trang đăng nhập không hiện mật khẩu demo, sinh viên không tự đăng nhập kiểu `<mã số>123` | Chạy với `EDUDSS_ENV` không đặt (`dss/core/runtime_mode.py:6-10`), mở trang đăng nhập, liệt kê người dùng | `tests/test_c1_production_mode_and_auth.py:88-128`; `reports/final_acceptance/C1_1_SECURITY_PRIVACY_HARDENING.md:264`; `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:132` | Đạt có bằng chứng |
| AC-BM-03 | Mật khẩu băm PBKDF2-SHA256 600.000 vòng. Băm cũ vẫn đăng nhập được và được nâng cấp | `tests/test_c1_production_mode_and_auth.py:130-140` | `reports/final_acceptance/C1_1_SECURITY_PRIVACY_HARDENING.md:264` | Đạt có bằng chứng |
| AC-BM-04 | Phân quyền 2 lớp: mở trang ngoài quyền bị chặn ở menu **và** ở hàm | `tests/test_rbac.py`; gọi hàm có `@require_role` bằng vai trò sai | `dss/core/roles.py:240-241`, `dss/services/auth_service.py:435`; `reports/performance_optimization/PERFORMANCE_COMPARISON.md:62` | Đạt có bằng chứng |
| AC-BM-05 | RLS FORCE trên mọi bảng có `organization_id`, kiểm bằng vai trò CSDL **không** phải superuser: trường A đọc/ghi 0 bản ghi của trường B | Bộ test RLS trên PostgreSQL thật | `reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:41`, `:192` (34/34 bảng, 26 test); `reports/stage23/ACCEPTANCE.md:65-68` | Đạt có bằng chứng |
| AC-BM-06 | RLS cũng áp dụng cho `rag_chunks` và `model_metrics` (2 bảng không có `organization_id`) | Truy vấn 2 bảng này bằng phiên của trường khác | Migration có chính sách qua bảng cha (`dss/db/migrations/versions/cbae9b411ed5_row_level_security_tenant_isolation.py:60-62`), nhưng báo cáo ghi "no policy" (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:41`) | Chưa có bằng chứng (xem Mâu thuẫn số 7) |
| AC-BM-07 | Dữ liệu gửi cho AI đã bút danh hoá: không có tên hay mã SV thật | `tests/test_c1_pseudonymization_and_payload.py` | `reports/final_acceptance/C1_1_SECURITY_PRIVACY_HARDENING.md:265` (21 test) | Đạt có bằng chứng |
| AC-BM-08 | Webhook LMS thiếu secret hoặc sai chữ ký thì bị từ chối (fail closed) | Gửi webhook không ký và ký sai | `dss/services/lms_live_sync.py:48-52`; `reports/production_readiness/ABC_ONBOARDING_INTEGRATION.md:45-50` | Đạt có bằng chứng |
| AC-BM-09 | Đăng nhập Google: email chưa có tài khoản EduDSS thì không tự được cấp quyền ở production. Vai trò vẫn do tài khoản EduDSS quyết định | `tests/test_fullstack_google_signin.py` | `dss/services/google_signin.py:1-11`, `dss/core/runtime_mode.py:99`. Không tìm thấy biên bản kết quả chạy | Chưa có bằng chứng |
| AC-BM-10 | HTTPS độc lập: HTTP chuyển sang HTTPS (308), có header HSTS/CSP/`X-Frame-Options`, WebSocket nâng cấp được (101), `smoke.sh` đạt 4/4 | `cd deploy/standalone && docker compose up -d --build && bash smoke.sh https://<APP_DOMAIN>` (`deploy/standalone/README.md:23-31`) | `reports/BO_KHUNG_DU_AN.md:152-172` (chạy với CA nội bộ, `edudss.localhost`) | Đạt có bằng chứng (chỉ với chứng chỉ nội bộ) |
| AC-BM-11 | Xin được chứng chỉ Let's Encrypt thật cho tên miền công khai | Chạy như AC-BM-10 với tên miền thật | `reports/BO_KHUNG_DU_AN.md:174` ghi "Chưa kiểm" | Chưa có bằng chứng |
| AC-BM-12 | Sao lưu CSDL → kiểm tra → khôi phục vào **CSDL trống riêng** → đăng nhập và RLS vẫn đúng, trên **schema hiện tại** | `docs/operations/BACKUP_RECOVERY_RUNBOOK.md` (`ops/backup_recovery.py`), `tests/test_backup_recovery_integration.py` (`:113`) | Đạt trên schema cũ (`reports/production_readiness/PHASE13_BACKUP_RECOVERY.md:102`), nhưng "NOT_VERIFIED on this branch" (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:368`) | Chưa có bằng chứng |
| AC-BM-13 | Khôi phục toàn bộ (CSDL + mô hình + tệp tải lên + cấu hình) đạt RPO/RTO đã chốt | Diễn tập khôi phục lên máy sạch | Runbook chỉ có mức **tạm**: RPO 24 giờ, RTO 4 giờ (`docs/operations/BACKUP_RECOVERY_RUNBOOK.md:136-137`). Chưa từng diễn tập gộp (`reports/production_readiness/FINAL_ARCHITECTURE_TRUTH.md:39`) | Chưa có bằng chứng |

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: RPO/RTO dùng để nghiệm thu.**
> - Runbook chỉ ghi mức tạm "nếu" sao lưu hằng ngày chạy được (`docs/operations/BACKUP_RECOVERY_RUNBOOK.md:136-137`).
> - (a) Chấp nhận RPO 24 giờ / RTO 4 giờ làm tiêu chí chính thức · (b) Chủ dự án đặt mức khác.
> - **(đề xuất) (a)** cho thí điểm, kèm điều kiện phải diễn tập AC-BM-12 trên schema hiện tại.

## 6. Hiệu năng

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-HN-01 | Dự đoán theo lô 20.000 bản ghi: **< 5 giây và > 5.000 bản ghi/giây**. Đây là dự đoán theo lô, **không phải** 20.000 người dùng đồng thời | Chạy benchmark 20K | Ngưỡng ở `reports/production_readiness/ABC_ONBOARDING_INTEGRATION.md:54`. Kết quả đo dao động giữa các lần (xem Mâu thuẫn số 4) | Đạt có bằng chứng ở phần lớn các lần đo, nhưng **không ổn định** |
| AC-HN-02 | 50 thao tác CSDL đồng thời: p95 ≤ 500 ms, lỗi ≤ 1% (SLO thử nghiệm ở `reports/production_readiness/WORKSTREAM_D_SCALE_RECOVERY.md:124-126`) | `tests/load/test_concurrency_capacity.py` | `reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:222` (50 đồng thời, p95 452 ms, 0 lỗi, 1 máy dev) | Đạt có bằng chứng (xem Mâu thuẫn số 5) |
| AC-HN-03 | Chạy liên tục 300 giây không lỗi | `tests/load/test_soak.py` | `reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:223` (70.887 thao tác, 0 lỗi; **không phải** 72 giờ) | Đạt có bằng chứng |
| AC-HN-04 | **50 phiên trình duyệt** đồng thời (mức đã chốt 21/11) chạy được, lỗi ≤ 1% (như AC-HN-02). ⏳ Ngưỡng thời gian phản hồi cho trình duyệt: repo chưa có số, cần chốt khi đo | Thử tải bằng trình duyệt thật | `reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:224` ghi "never measured" | Chưa có bằng chứng |
| AC-HN-05 | Không tràn ngang trang ở 1920×1080, 1440×900, 1366×768 và 1024×768 | Playwright so `scrollWidth` với `clientWidth`; `tests/e2e/test_c1_3_ui_journeys_e2e.py:141-142` | `reports/final_ui_functional_audit/RESPONSIVE_ACCESSIBILITY_REPORT.md:3-13`, `reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:106-107` | Đạt có bằng chứng |
| AC-HN-06 | Container khởi động "healthy"; `/healthz` và `/readyz` trả 200 khi sẵn sàng | `docker compose ps`; gọi 2 đường dẫn (`dss/core/health_server.py:57-89`) | `reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:37` (container smoke, readiness ready); `reports/BO_KHUNG_DU_AN.md:165-168` | Đạt có bằng chứng |

> ✅ **ĐÃ CHỐT (21/11/2026): AC-HN-04 dùng mức 50 phiên trình duyệt đồng thời** (thí điểm 1 trường, PRD §2).
> - Phải đo bằng phiên trình duyệt thật trên máy chủ sẽ dùng, trước khi bàn giao.

## 7. Chất lượng mô hình và AI

Nguồn số liệu **duy nhất** dùng cho bảng này: lần chạy eval ngày 16/11/2026 (`evals/README.md:22-34`),
bảng cập nhật bộ lọc an toàn (`evals/README.md:50-55`), dữ liệu học sinh thật (`evals/README.md:66-82`)
và các cổng chặn ở `evals/thresholds.json`. Kết quả dạng JSON (`reports/evals/`) **không** có trong repo.
Dữ liệu ML là cohort mô phỏng 2.000 SV (huấn luyện) và 1.000 SV độc lập (chấm) (`evals/README.md:18`).

| ID | Tiêu chí (đo được) | Cách kiểm | Bằng chứng hiện có (path) | Trạng thái |
|---|---|---|---|---|
| AC-ML-01 | Xếp loại: macro-F1 ≥ 0,80 (`evals/thresholds.json:4`) và cao hơn mốc "đoán bừa" ≥ 0,30 (`:5`) | `python evals/run_evals.py` | macro-F1 0,817; accuracy 95,7% so với dummy 48,6% (`evals/README.md:26`) | Đạt có bằng chứng |
| AC-ML-02 | Dự đoán điểm kỳ sau: R² ≥ 0,90 (`evals/thresholds.json:6`), MAE ≤ 0,30 (`:22`) | Như trên | R² 0,992, MAE 0,064 (`evals/README.md:27`). README lưu ý dữ liệu mô phỏng gần như tuyến tính nên số này chỉ cho thấy pipeline đúng (`evals/README.md:107-109`) | Đạt có bằng chứng |
| AC-ML-03 | Sàng lọc rủi ro (điểm kỳ sau < 6,0): recall ≥ 0,80 (`evals/thresholds.json:7`), precision ≥ 0,70 (`:8`) | Như trên | recall 96,5%, precision 91,8% (`evals/README.md:28`) | Đạt có bằng chứng |
| AC-ML-04 | Chặn rò rỉ nhãn: trainer tự loại cột là bản sao của nhãn (`evals/thresholds.json:33-35`) | Như trên; `tests/test_c1_ml_leakage_regression.py` | "Có" (`evals/README.md:29`) | Đạt có bằng chứng |
| AC-ML-05 | Học sinh thật (UCI, 649 em): AUC đầu kỳ ≥ 0,75, giữa kỳ ≥ 0,88; recall ≥ 0,75 cả hai (`evals/thresholds.json:12-15`); ECE ≤ 0,10 (`:25-26`) | Như trên (phần `ml_real`) | AUC 0,79 / 0,92; recall 82%; ECE 0,065 / 0,069 (`evals/README.md:72-73`) | Đạt có bằng chứng (học sinh Bồ Đào Nha, **không phải** sinh viên Việt Nam: `evals/README.md:108-109`) |
| AC-ML-06 | Chênh lệch recall giữa nam/nữ và thành thị/nông thôn ≤ 0,25 (`evals/thresholds.json:27-28`) | Như trên | Khoảng 0,11–0,20, phần lớn là nhiễu (`evals/README.md:81-82`) | Đạt có bằng chứng |
| AC-ML-07 | RAG từ khoá (TF-IDF): recall@5 ≥ 0,80 (`evals/thresholds.json:9`) | Như trên | 95,7%, MRR 0,957 (`evals/README.md:30`) | Đạt có bằng chứng |
| AC-ML-08 | RAG embedding trên câu hỏi tiếng Việt: có số đo và có ngưỡng | Chạy eval ở môi trường tải được mô hình Hugging Face | Chưa có ngưỡng (`evals/thresholds.json:37`), chưa có số đo (`evals/README.md:87-89`) | Chưa có bằng chứng |
| AC-ML-09 | Bộ golden an toàn: bắt lời khuyên có hại ≥ 0,85, gắn nhầm ≤ 0,10, chặn prompt injection ≥ 0,85, làm hỏng câu hợp lệ = 0 (`evals/thresholds.json:10-11`, `:23-24`) | Như trên | 100% / 0% / 100% / 0% (`evals/README.md:31-32`) | Đạt có bằng chứng |
| AC-ML-10 | Bộ holdout an toàn: lời khuyên có hại v1 ≥ 0,60, v2 ≥ 0,55; chặn injection v1 và v2 ≥ 0,85; gắn nhầm v2 ≤ 0,10 (`evals/thresholds.json:16-19`, `:29-31`) | Như trên | Từ khoá + bộ phân loại: 75% / 65%; 100% / 93,3%; 0% (`evals/README.md:52-55`) | Đạt có bằng chứng (xem Mâu thuẫn số 3) |
| AC-ML-11 | Tập kiểm tra an toàn do **bên thứ ba** viết, trước khi đưa số liệu cho khách hàng | Thuê/nhờ người ngoài viết tập mới | README ghi mọi tập do cùng một người viết (`evals/README.md:61-62`) | Chưa có bằng chứng |
| AC-ML-12 | Mô hình được kiểm định trên sinh viên thật của trường thí điểm | Thí điểm với dữ liệu trường | `README.md:171-182`; `docs/architecture/EDUDSS_MINISTRY_ROADMAP.md:60` | Chưa có bằng chứng |
| AC-ML-13 | Ngân sách AI **chặn thật**: trần mặc định **5 USD/tháng** (`EDUDSS_AI_MONTHLY_BUDGET_USD`), trần ngày = tháng/30. Chạm trần thì không gọi Gemini/Groq/OpenAI nữa, người dùng thấy thông báo rõ và vẫn dùng được Kế hoạch học tập; AI miễn phí tại chỗ (Ollama) vẫn chạy. Admin được cảnh báo ở 80% | `tests/test_ai_budget_and_local_hf.py` (giả lập sổ chi phí đã chạm trần) | `dss/services/token_tracker.py::check_system_budget`, `dss/services/llm_gateway.py` (2 cổng). Test 21/11/2026 đạt. **Chưa** thử với tài khoản trả phí thật | Đạt có bằng chứng (test tự động) |
| AC-ML-14 | **(mới 21/11)** Mọi câu trả lời do LLM tạo đều có nhãn "do AI tạo", và dữ liệu gửi đi đã bút danh hoá (không có tên, mã SV thật) | Bắt gói gửi tới nhà cung cấp trong môi trường thử | `dss/security/pseudonymization.py`; chưa có biên bản | Chưa có bằng chứng |
| AC-ML-15 | AI chạy tại chỗ bằng Hugging Face **tắt mặc định**: không có khoá API thì bấm "Tạo kế hoạch bằng AI" không tải mô hình nào (trước đây tự tải Qwen2.5-7B ~15 GB). Chỉ bật bằng `EDUDSS_ENABLE_LOCAL_HF=1` | Bấm nút khi chưa có khoá, theo dõi thư mục cache Hugging Face | `tests/test_ai_budget_and_local_hf.py`; kiểm tay 21/11/2026: không tải thêm byte nào, app báo "AI trực tuyến hiện chưa sẵn sàng" | Đạt có bằng chứng |

> ⚠️ Vì MVP **bật LLM trả phí** (quyết định 21/11), AC-ML-09, AC-ML-10, AC-ML-13 và AC-ML-14 là điều kiện
> **bắt buộc** trước khi cho sinh viên dùng Trợ lý AI.

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: AC-ML-11 và AC-ML-12 có là điều kiện bắt buộc để bàn giao thí điểm không?**
> - (a) Có: chưa đạt thì chưa bàn giao.
> - (b) Không: bàn giao thí điểm, ghi rõ "chưa kiểm định trên dữ liệu thật" trên giao diện và trong hợp đồng.
> - **(đề xuất) (b)**. Lý do: AC-ML-12 chỉ làm được khi đã có dữ liệu của trường. Báo cáo cũng đã gợi ý câu
>   chữ an toàn (`reports/production_readiness/METRICS_THESIS_VS_CURRENT.md:48-50`).

## 8. Mâu thuẫn số liệu

Các chỗ dưới đây có **nhiều con số khác nhau** cho cùng một việc. Tài liệu này **không tự chọn** một số.
Bảng trên chỉ dùng ngưỡng ghi trong `evals/thresholds.json` và các báo cáo nghiệm thu, rồi ghi rõ nguồn.

1. **Số liệu ML trong luận văn.** Accuracy 0,875, Silhouette 0,412, DBI 0,831 "THESIS-REPORTED ONLY"
   (`reports/production_readiness/METRICS_THESIS_VS_CURRENT.md:11-16`). RMSE 0,074 / R² 0,992 đến từ
   dữ liệu mô phỏng 132 dòng có rò rỉ nhãn `xep_loai` (`reports/production_readiness/METRICS_THESIS_VS_CURRENT.md:41-50`).
   → **Không dùng** cho tiêu chí nào.
2. **`reports/ml_correctness/after_metrics.txt`.** Ghi Random Forest macro-F1 0,8745, Logistic Regression
   accuracy 0,925, Linear Regression R² 0,9929, mốc dummy accuracy 0,46 (`reports/ml_correctness/after_metrics.txt:6-12`).
   Eval hiện tại ghi macro-F1 0,817, dummy 48,6% (`evals/README.md:26`). Hai lần chạy dùng dữ liệu và cách
   chấm khác nhau. → Dùng số của eval hiện tại, vì eval có cổng chặn.
3. **Bộ holdout an toàn.** Bảng ngày 16/11/2026 ghi lời khuyên có hại 12,5% và chặn injection 50%
   (`evals/README.md:33-34`). Hai số này **dưới** cổng 0,60 và 0,85. Bảng cập nhật (không ghi ngày) ghi
   75% và 100% khi thêm bộ phân loại (`evals/README.md:52-54`), và tự ghi rằng số injection là "lạc quan"
   (`evals/README.md:57-60`). → AC-ML-10 dựa trên bảng cập nhật. Cần chạy lại để có kết quả kèm ngày.
4. **Tốc độ dự đoán lô 20K.** Các lần đo: 9.314,6/giây (`reports/production_readiness/DOCKER_CPU_ONLY_PYTORCH_OPTIMIZATION.md:363`),
   7.843,8/giây (`reports/production_readiness/FINAL_RELEASE_CANDIDATE.md:30`), 7.629,6/giây
   (`reports/production_readiness/TEST_RESULTS.md:40`), 7.274,5/giây (`reports/production_readiness/ABC_ONBOARDING_INTEGRATION.md:54`),
   6.591/giây (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:225`), và **4.841,4/giây — không đạt**
   (`reports/production_readiness/FINAL_INTEGRATION_ACCEPTANCE.md:58-60`). Một báo cáo khác ghi 2 lần đo
   không đạt (`reports/production_readiness/PHASE12A_MAIN_DRIFT_REVALIDATION.md:78`). → AC-HN-01 dùng
   **ngưỡng** "< 5 s, > 5.000/giây", không dùng một số đo nào.
5. **Số thao tác đồng thời.** Một báo cáo ghi 50 đồng thời, p95 452 ms, 0 lỗi
   (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:222`). Báo cáo trước đó ghi SLO p95 ≤ 500 ms
   chỉ đạt đến **10** đồng thời và vượt ở **25** (`reports/production_readiness/WORKSTREAM_D_SCALE_RECOVERY.md:135-136`).
   → AC-HN-02 ghi theo báo cáo mới hơn. Cần chạy lại trên máy chủ thật.
6. **Khoá đăng nhập.** Báo cáo thương mại ghi khoá chỉ nằm trong bộ nhớ, mất khi khởi động lại
   (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:74`, `:338`). Báo cáo sau đó ghi đã chuyển sang
   lưu bền, dùng chung giữa các tiến trình (`reports/final_acceptance/C1_1_SECURITY_PRIVACY_HARDENING.md:76`),
   và có test "survives restart" (`tests/test_c1_production_mode_and_auth.py:167`). Báo cáo thương mại cũng
   ghi PBKDF2 200k, nhưng test hiện tại kiểm 600k (`tests/test_c1_production_mode_and_auth.py:130`).
   → Dùng theo code và test hiện tại.
7. **RLS cho `rag_chunks` và `model_metrics`.** Báo cáo ghi "no policy"
   (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:41`), nhưng migration có khai báo chính sách
   qua bảng cha (`dss/db/migrations/versions/cbae9b411ed5_row_level_security_tenant_isolation.py:60-62`).
   → AC-BM-06 để "Chưa có bằng chứng" cho tới khi kiểm trực tiếp trên PostgreSQL.
8. **HTTPS.** Báo cáo thương mại ghi "No reverse proxy, TLS" (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:75`).
   Sau đó `deploy/standalone/` đã được thêm và chạy thử (`reports/BO_KHUNG_DU_AN.md:152-174`).
   → Báo cáo cũ đã lỗi thời ở điểm này.
9. **Điện thoại.** Một báo cáo nói đã có lượt kiểm ở 390×844 (`reports/final_ui_functional_audit/RESPONSIVE_ACCESSIBILITY_REPORT.md:26-29`).
   Báo cáo C1.3 mới hơn ghi "Phone widths were not in scope" (`reports/final_acceptance/C1_3_UI_UX_ACCEPTANCE.md:107`).
   → Coi như **chưa** có bằng chứng cho điện thoại. Xem [SCREEN_MAP.md](../ux/SCREEN_MAP.md) §6.
