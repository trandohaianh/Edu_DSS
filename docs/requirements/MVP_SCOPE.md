# EduDSS — Phạm vi bản đầu tiên (MVP)

> **Trạng thái: ĐÃ CHỐT PHẠM VI** — chủ dự án chọn "dùng đề xuất, sửa theo các quyết định" ngày 21/11/2026
> (soạn dựa trên commit 6e9710d). Các dòng đã đổi so với đề xuất ban đầu được đánh dấu **(đã đổi 21/11)**.

Tài liệu này liệt kê **mọi trang và tính năng con đang có trong code**, theo từng vai trò, rồi đề xuất
cái nào **Bắt buộc** cho bản đầu tiên và cái nào **Để sau**. Không có tính năng nào mới được thêm vào.
Mỗi dòng đều ghi đường dẫn code.

Tài liệu liên quan: [PRD.md](PRD.md) · [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) ·
[../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) · [../database/SCHEMA.md](../database/SCHEMA.md) ·
[../ux/SCREEN_MAP.md](../ux/SCREEN_MAP.md)

---

> ✅ **ĐÃ CHỐT (21/11/2026): dùng cột "Đề xuất" làm phạm vi MVP, có sửa theo các quyết định sau.**
> - Cách chọn: chỉ "Bắt buộc" cho những gì phục vụ trực tiếp lời hứa cốt lõi ở PRD §1, tức
>   **phát hiện sớm sinh viên có nguy cơ** và **đưa ra lời khuyên học tập** (`README.md:1-12`).
> - "Để sau" **không** có nghĩa là xoá code. Nghĩa là không đưa vào nghiệm thu bản đầu tiên và không
>   hứa với trường.
> - Quyết định của chủ dự án làm thay đổi bảng:
>   1. **Bật Trợ lý AI dùng LLM trả phí** (OpenAI/Gemini/Groq). Ngân sách hạ tầng **dưới 500.000 đ/tháng**
>      (PRD §7), nên phải đặt hạn mức chi phí AI.
>   2. **Sinh viên xem được kết quả trên điện thoại**, giống LMS. Các vai trò khác dùng máy tính.
>   3. **Làm thêm 3 trang cho giảng viên** theo mockup: Báo cáo, Lịch sử, Phân tích rủi ro. Code chưa có.
>   4. `Platform Admin` chỉ dùng nội bộ. LMS/SSO để sau. Thí điểm 1 trường, ≤ 50 người dùng đồng thời.
>   5. Stage 2/3 (lớp học – bài đánh giá) **để sau**, theo đề xuất.

## 1. Cách đọc bảng

- **Vai trò**: tên đúng như trong code (`dss/core/roles.py:7`). `Platform Admin` không nằm trong `ROLES`
  nhưng có trong `TAB_ACCESS` (`dss/core/roles.py:236`). Xem thêm PRD §2.
- **Code**: nơi trang được vẽ ra. Điều hướng chính nằm ở `dss/main.py:410-908`. Danh sách 20 trang là
  `ALL_TABS` (`dss/core/roles.py:151-172`). Quyền xem trang là `TAB_ACCESS` (`dss/core/roles.py:175-237`).
- **Tên hiển thị** có thể khác tên trong code. Ví dụ, sinh viên thấy "Dự đoán kết quả" thay cho
  "🧪 Huấn luyện — Dự đoán" (`dss/core/roles.py:42-51`).

## 2. Sinh viên (`Sinh viên`)

Menu của sinh viên: `dss/main.py:226-232`.

| Trang/tính năng | Vai trò | Code (path) | Đề xuất | Lý do |
|---|---|---|---|---|
| Trang chủ: dự đoán, mức rủi ro, yếu tố ảnh hưởng, việc nên làm tiếp | Sinh viên | `dss/tabs/home.py:218` | **Bắt buộc** | Đúng lời hứa cốt lõi. Trang trả lời "Tôi đang học thế nào? Điều gì cần chú ý? Nên làm gì tiếp?" (`dss/tabs/home.py:219-221`) |
| Trang chủ khi chưa có dữ liệu: mở lớp học, kế hoạch đã lưu | Sinh viên | `dss/main.py:411-419` | **Bắt buộc** | Không có dữ liệu thì phải báo trung thực, không hiện số giả |
| Lớp học và đánh giá: làm bài, xem kết quả, kế hoạch theo lớp | Sinh viên | `dss/tabs/classroom_tab.py:376-385` | Để sau | Mới nghiệm thu kỹ thuật thí điểm (`reports/stage23/ACCEPTANCE.md:3-6`). Phần dự đoán rủi ro không cần trang này |
| Dự đoán kết quả — Dữ liệu đã có (dự đoán từ dữ liệu của chính mình) | Sinh viên | `dss/main.py:776`, `dss/tabs/ml_hub.py:894` | **Bắt buộc** | Là chỗ sinh viên thấy dự đoán của chính mình, đã khoá theo mã SV (`reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:28`) |
| Dự đoán kết quả — Nhập tay (thử "nếu… thì…") | Sinh viên | `dss/main.py:776`, `dss/tabs/ml_hub.py:634` | Để sau | Tính năng phụ. Trang chủ và dự đoán từ dữ liệu đã trả lời câu hỏi chính |
| Nhóm học tập & gợi ý (phân cụm) | Sinh viên | `dss/tabs/clustering.py:18` | Để sau | Số liệu chất lượng phân cụm trong luận văn chưa được kiểm lại (`reports/production_readiness/METRICS_THESIS_VS_CURRENT.md:14-16`) |
| Trợ lý AI — Kế hoạch học tập (tạo, lưu, đánh dấu tiến độ) | Sinh viên | `dss/main.py:852-853`, `dss/tabs/ai_advisor.py:457`, `dss/tabs/learning_plan_workspace.py:61` | **Bắt buộc** | Đây là phần "lời khuyên". Chạy được khi không có LLM và không có cột GPA (`reports/stage1_learning/ACCEPTANCE.md:16-17`) |
| Trợ lý AI — Hướng nghiệp (7 thẻ: hồ sơ, nghề phù hợp, so sánh, khoảng cách kỹ năng, lộ trình, giả lập, hỏi AI) | Sinh viên | `dss/tabs/advisory.py:1012`, `dss/tabs/advisory.py:1111-1121` | Để sau | Code **tự chặn** trang này ở chế độ production vì còn dùng dữ liệu LMS mẫu (`dss/tabs/advisory.py:1037-1039`, `tests/test_production_demo_policy.py:186-200`) |
| Trợ lý AI — Giải thích bài học (hỏi về bài giảng, có trích dẫn) | Sinh viên | `dss/tabs/learning_explainer_tab.py:863` | Để sau | Cần bài giảng đã duyệt trong CMS. Embedding tiếng Việt chưa có số đo (`evals/README.md:84-89`) |
| Lịch sử tư vấn | Sinh viên | `dss/tabs/consultation_history.py:14` | **Bắt buộc** | Cho sinh viên xem lại lời khuyên đã nhận. Đã lọc đúng theo mã SV (`reports/final_ui_functional_audit/STUDENT_ACCEPTANCE.md:33`) |

## 3. Giảng viên / CVHT (`Giảng viên / CVHT`)

Menu của giảng viên: `dss/main.py:233-240`.

| Trang/tính năng | Vai trò | Code (path) | Đề xuất | Lý do |
|---|---|---|---|---|
| Trang chủ: số SV rủi ro cao, tối đa 6 SV cần chú ý | Giảng viên / CVHT | `dss/tabs/home.py:69`, `dss/tabs/home.py:108-167` | **Bắt buộc** | Đúng mục tiêu "phát hiện rủi ro sớm" (`dss/core/roles.py:102`) |
| Ô tìm sinh viên theo mã, nút "Xem phân tích" mở Trợ lý AI cho SV đó | Giảng viên / CVHT, Admin | `dss/main.py:370-407`, `dss/services/search_service.py:30` | **Bắt buộc** | Nối từ "thấy rủi ro" sang "tư vấn" |
| Dashboard — bảng "Sinh viên rủi ro cao" (tìm, xuất) | Giảng viên / CVHT | `dss/tabs/dashboard.py:324`, `dss/tabs/dashboard.py:536-560` | **Bắt buộc** | Danh sách đầy đủ SV có nguy cơ của lớp |
| Dashboard — thẻ Phân tích Điểm số / Xếp loại / Thêm thông tin | Giảng viên / CVHT | `dss/tabs/dashboard.py:630` | Để sau | Phân tích bổ sung, không cần để phát hiện rủi ro |
| Lớp học và đánh giá: tiến độ lớp, soạn bài MCQ, theo dõi hỗ trợ | Giảng viên / CVHT | `dss/tabs/classroom_tab.py:292`, `:98`, `:328` | Để sau | Thí điểm Stage 2/3 (`reports/stage23/ACCEPTANCE.md:3-6`) |
| Khám phá — Xử lý dữ liệu (EDA, tương quan, tạo đặc trưng) | Giảng viên / CVHT, Admin | `dss/tabs/eda.py:233`, `dss/tabs/eda.py:855`, `dss/tabs/eda.py:1182` | Để sau | Công cụ kỹ thuật. Huấn luyện vẫn dùng dữ liệu gốc (`dss/main.py:502`) |
| Huấn luyện — thẻ "Huấn luyện mô hình" | Giảng viên / CVHT | `dss/main.py:558-560` | **Bắt buộc** | Muốn dự đoán thì phải có mô hình. Huấn luyện chỉ tạo bản Candidate (`dss/core/warehouse.py:458`) |
| Huấn luyện — thẻ "Kết quả đánh giá mô hình" (Phân loại, Hồi quy, Phân cụm, SHAP) | Giảng viên / CVHT | `dss/tabs/evaluation_report.py:397`, `dss/tabs/evaluation_report.py:414` | **Bắt buộc** | Cần xem chất lượng trước khi Admin cho lên Production |
| Dự đoán — Hàng loạt (cả lớp) | Giảng viên / CVHT | `dss/main.py:779-797`, `dss/tabs/ml_hub.py:1026` | **Bắt buộc** | Dự đoán cho cả lớp cùng lúc là cách phát hiện sớm |
| Dự đoán — Nhập tay / Dữ liệu đã có | Giảng viên / CVHT | `dss/main.py:779-793` | Để sau | Đã có Dashboard và Hàng loạt |
| Phân cụm — Gợi ý (cấu hình K-Means, Elbow/Silhouette) | Giảng viên / CVHT | `dss/tabs/clustering.py:18` | Để sau | Như dòng phân cụm của sinh viên |
| Chương trình và cấp phát | Giảng viên / CVHT, Admin, Platform Admin | `dss/tabs/programs_tab.py:184` | Để sau | Thí điểm Stage 3. Xem PRD §2 về `Platform Admin` |
| Trợ lý AI: chọn SV, phân tích điểm yếu, tư vấn | Giảng viên / CVHT, Admin | `dss/tabs/ai_advisor.py:457` | **Bắt buộc** | Phần "lời khuyên" ở phía giảng viên/CVHT |
| Trợ lý AI — "So sánh AI" giữa nhiều nhà cung cấp | Giảng viên / CVHT, Admin | `dss/tabs/ai_advisor.py:447` | Để sau | Chỉ có ích khi đã cấu hình nhiều nhà cung cấp AI |
| Duyệt tài liệu (môn mình phụ trách) | Giảng viên / CVHT | `dss/tabs/knowledge_base.py:422` | Để sau | Đi cùng RAG bài giảng, vốn đề xuất "Để sau" |
| Kho dữ liệu — Datasets (tải dữ liệu lớp) | Giảng viên / CVHT, Admin | `dss/tabs/warehouse_tab.py:26-28`, `dss/tabs/warehouse_tab.py:196-198` | **Bắt buộc** | Không có dữ liệu thì không dự đoán được |
| Kho dữ liệu — AI Models (xem; GV không đổi được Production) | Giảng viên / CVHT, Admin | `dss/tabs/warehouse_tab.py:433-443`, `dss/tabs/warehouse_tab.py:616-619` | **Bắt buộc** | Biết mô hình nào đang phục vụ dự đoán |
| Kho dữ liệu — History (nhật ký thô) | Giảng viên / CVHT, Admin | `dss/tabs/warehouse_tab.py:26-28` | Để sau | Báo cáo ghi là "plain-text log", đủ dùng nhưng thô (`reports/final_ui_functional_audit/LECTURER_ACCEPTANCE.md:19`) |
| **Trang mới — Báo cáo** (theo mockup `ui_reference/lecturer/reports.html`) | Giảng viên / CVHT | **chưa có code** | **Bắt buộc (đã đổi 21/11)** | Chủ dự án chọn làm thêm. Nội dung chi tiết cần đặc tả trước khi lập trình (bước 6) |
| **Trang mới — Lịch sử** (theo mockup `ui_reference/lecturer/history.html`) | Giảng viên / CVHT | **chưa có code** | **Bắt buộc (đã đổi 21/11)** | Như trên. Cần phân biệt với "Kho dữ liệu — History" (nhật ký thô) và "Lịch sử tư vấn" |
| **Trang mới — Phân tích rủi ro** (theo mockup `ui_reference/lecturer/risk_analysis.html`) | Giảng viên / CVHT | **chưa có code** | **Bắt buộc (đã đổi 21/11)** | Như trên. Có thể dùng lại dữ liệu của Dashboard "Sinh viên rủi ro cao" |

## 4. Quản trị trường (`Admin`)

Menu của Admin: `dss/main.py:241-252`.

| Trang/tính năng | Vai trò | Code (path) | Đề xuất | Lý do |
|---|---|---|---|---|
| Tổng quan (dùng lại trang Báo cáo) và Báo cáo & giám sát | Admin | `dss/tabs/home.py:46-59`, `dss/tabs/admin_reports.py:84-89` | **Bắt buộc** | Admin cần biết hệ thống có dữ liệu, có mô hình Production và có việc cần xử lý |
| Người dùng: tạo/quản lý tài khoản | Admin | `dss/tabs/admin_settings.py:31` | **Bắt buộc** | Production không có tài khoản demo (`README.md:72-74`), nên phải tạo tài khoản thật |
| Kho dữ liệu — Datasets: tải CSV/Excel | Admin | `dss/tabs/warehouse_tab.py:196-198` | **Bắt buộc** | Đường nhập dữ liệu chính khi chưa nối LMS (PRD §4, đề xuất (b)) |
| Kho dữ liệu — AI Models: Promote / Rollback | Admin | `dss/tabs/warehouse_tab.py:616-622`, `dss/services/model_registry.py:253-254` | **Bắt buộc** | Chỉ Admin được cho mô hình lên Production |
| Model Registry (bảng xem toàn bộ phiên bản) | Admin | `dss/tabs/warehouse_tab.py:669-676` | Để sau | Trang chỉ để xem. Nút Promote nằm ở Kho dữ liệu (`dss/tabs/warehouse_tab.py:673-676`) |
| Lớp học: tạo lớp, nhập danh sách lớp CSV | Admin | `dss/tabs/classroom_tab.py:351-360`, `dss/tabs/classroom_tab.py:47-49` | Để sau | Thí điểm Stage 2/3 |
| Khám phá — Xử lý dữ liệu | Admin | `dss/tabs/eda.py:233` | Để sau | Như dòng của giảng viên |
| Học liệu của trường (Nạp & Quản lý, Duyệt Quiz, Dashboard phân tích) | Admin | `dss/main.py:434-435`, `dss/tabs/learning_explainer_tab.py:410` | Để sau | Đi cùng CMS/RAG |
| Quản lý tri thức (RAG): tài liệu môn học, nguồn tham khảo, không gian tri thức, tải lên | Admin | `dss/tabs/knowledge_base.py:53`, `dss/tabs/knowledge_base.py:110-115` | Để sau | Kế hoạch học tập chạy được không cần RAG. Quy chế còn lưu ở JSON cục bộ, chưa có giao diện duyệt (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:70`) |
| Cấu hình AI (nhà cung cấp, kiểm tra kết nối) | Admin | `dss/tabs/ai_advisor.py:1823` | **Bắt buộc (đã đổi 21/11)** | MVP bật LLM trả phí (§6), nên Admin cần chỗ nhập khoá API và kiểm tra kết nối |
| Trợ lý AI (Admin xem tư vấn) | Admin | `dss/tabs/ai_advisor.py:457` | Để sau | Người tư vấn chính là giảng viên/CVHT |
| Chương trình và cấp phát (công bố số liệu tổng hợp) | Admin | `dss/tabs/programs_tab.py:184-190` | Để sau | Thí điểm Stage 3 |
| Tích hợp LMS/CMS | Admin | `dss/tabs/admin_settings.py:171` | Để sau | PRD §4 đề xuất (b): chưa nối LMS thật |
| Cài đặt (gồm "Điều chỉnh thuê bao") | Admin | `dss/tabs/admin_settings.py:280`, `dss/tabs/admin_settings.py:312` | Để sau | Không phục vụ trực tiếp lời hứa cốt lõi |

## 5. Quản trị nền tảng (`Platform Admin`)

`Platform Admin` thấy trang Onboarding (`dss/core/roles.py:236`) và cả trang "Chương trình và cấp phát"
(`dss/core/roles.py:178`). Chú thích ở `dss/core/roles.py:231-235` lại ghi vai trò này chỉ thấy **một**
trang. Hai chỗ này mâu thuẫn; code (dòng 178) mới là cái có hiệu lực.

| Trang/tính năng | Vai trò | Code (path) | Đề xuất | Lý do |
|---|---|---|---|---|
| Onboarding Trường Đại học (7 bước: thông tin, tài khoản Admin, kết nối LMS/CMS, kiểm tra, ánh xạ, đồng bộ, kích hoạt) | Platform Admin | `dss/tabs/university_onboarding_tab.py:21`, `:65-151` | Để sau | PRD §2 đề xuất (b): không phải vai trò chính thức ở bản đầu |
| Chương trình — đăng ký trường, tạo chương trình, phân quyền, cấp phát | Platform Admin | `dss/tabs/programs_tab.py:30-81`, `dss/tabs/programs_tab.py:188-189` | Để sau | Như trên |

## 6. Tính năng dùng chung

| Trang/tính năng | Vai trò | Code (path) | Đề xuất | Lý do |
|---|---|---|---|---|
| Đăng nhập tên + mật khẩu (băm PBKDF2) | Tất cả | `dss/services/auth_service.py:917`, `dss/services/auth_service.py:81` | **Bắt buộc** | Không đăng nhập thì không có phân quyền |
| Khoá tài khoản 15 phút sau 5 lần sai | Tất cả | `dss/security/login_throttle.py:31-33` | **Bắt buộc** | Chống dò mật khẩu |
| Đăng nhập Google (OIDC) | Tất cả | `dss/services/google_signin.py:1-11`, `dss/services/auth_service.py:511-516` | **Bắt buộc** | Theo PRD §4 đề xuất (b): "Excel/CSV + Google OIDC". Chỉ hiện khi đã cấu hình |
| Phân quyền 2 lớp (lọc menu + chặn ở hàm) | Tất cả | `dss/core/roles.py:240-241`, `dss/services/auth_service.py:435` | **Bắt buộc** | Sinh viên không được thấy dữ liệu người khác |
| Chế độ production an toàn mặc định (không demo, không dữ liệu mô phỏng) | Tất cả | `dss/core/runtime_mode.py:6-10`, `dss/core/runtime_mode.py:66-112` | **Bắt buộc** | Tránh lộ tài khoản demo khi chạy thật |
| Tách dữ liệu giữa các trường (RLS PostgreSQL) | Tất cả | `dss/db/migrations/versions/cbae9b411ed5_row_level_security_tenant_isolation.py:39-97` | **Bắt buộc** | Bật sẵn ở production. Giữ nguyên dù chỉ có 1 trường |
| Bút danh hoá dữ liệu trước khi gửi cho AI | Tất cả | `dss/security/pseudonymization.py` | **Bắt buộc** | Bảo vệ dữ liệu cá nhân sinh viên |
| Kho mô hình: Candidate → Production → Archived, không tự lên Production | GV, Admin | `dss/services/model_registry.py`, `dss/services/model_service.py:227-248` | **Bắt buộc** | Dự đoán chỉ dùng mô hình đã duyệt |
| Giải thích dự đoán (SHAP, "yếu tố ảnh hưởng") | SV, GV | `dss/services/model_explainability.py` | **Bắt buộc** | Lời khuyên phải có lý do (`dss/core/roles.py:115`) |
| Trợ lý AI có LLM: định tuyến 3 tầng, nhà cung cấp OpenAI/Gemini/Groq/Ollama | Tất cả | `dss/services/ai_router.py`, `docs/ai/AI_ROUTING_MATRIX.md` | **Bắt buộc (đã đổi 21/11)** | Chủ dự án chọn dùng nhà cung cấp trả phí. Kế hoạch học tập theo luật vẫn phải chạy được khi AI lỗi hoặc hết hạn mức (`reports/stage1_learning/ACCEPTANCE.md:16`) |
| Hạn mức chi phí AI theo trường (đếm token, chặn khi vượt) | Admin, Vận hành | `dss/services/llm_gateway.py:382` (`check_quota_and_rate_limit`), bảng `ai_token_usage`, `quota_usage` | **Bắt buộc (đã đổi 21/11)** | Code đã có cổng kiểm tra hạn mức. Ngân sách < 500.000 đ/tháng cho cả máy chủ lẫn API, nên cần đặt mức trần cụ thể khi chọn nhà cung cấp |
| Bộ lọc an toàn AI (từ khoá + bộ phân loại) | Tất cả | `dss/services/safety_classifier.py`, `dss/services/prompt_security.py` | **Bắt buộc (đã đổi 21/11)** | ⚠️ Rủi ro lớn nhất của quyết định bật LLM. Holdout mới chặn được 65–75% lời khuyên có hại (`evals/README.md:52-53`). Phải đạt ngưỡng ở [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) trước khi cho sinh viên dùng |
| RAG trên bài giảng và quy chế | Tất cả | `dss/services/rag_service.py` | Để sau | Embedding tiếng Việt chưa đo (`evals/thresholds.json:37`) |
| Cổng AI ngoài (`engine_advisor_tab`, bật bằng `EDUDSS_ENGINE_URL`) | Tất cả | `dss/main.py:815-819`, `dss/services/engine_gateway.py:39-41` | Để sau | Chỉ chạy khi có cấu hình, thay cho Trợ lý AI thường |
| Webhook LMS ký HMAC, connector Moodle REST | Admin | `dss/services/lms_live_sync.py:44-52`, `dss/services/moodle_connector.py` | Để sau | Chưa chạy với Moodle thật (`evals/README.md:96`) |
| Nhập dữ liệu từ file CSV/Excel | GV, Admin | `dss/tabs/warehouse_tab.py:198`, `dss/security/upload_security.py` | **Bắt buộc** | Đường nhập dữ liệu chính của MVP |
| Kiểm tra sức khoẻ `/healthz`, `/readyz` | Vận hành | `dss/core/health_server.py:57-89` | **Bắt buộc** | Docker và Caddy cần biết app đã sẵn sàng (`deploy/standalone/README.md:29`) |
| Số liệu giám sát `/metrics` (Prometheus, Bearer token) | Vận hành | `dss/core/metrics_exporter.py:1-4`, `deploy/standalone/README.md:9` | Để sau | Chưa có bộ thu thập/hiển thị đi kèm (`reports/production_readiness/FINAL_PHASE12A_ACCEPTANCE.md:48`) |
| Sao lưu và khôi phục PostgreSQL | Vận hành | `ops/backup_recovery.py`, `docs/operations/BACKUP_RECOVERY_RUNBOOK.md` | **Bắt buộc** | Mất dữ liệu học tập là không chấp nhận được |
| Triển khai HTTPS độc lập (Caddy) | Vận hành | `deploy/standalone/` | **Bắt buộc** | Đăng nhập qua Internet cần HTTPS |
| Giao diện sáng/tối/theo hệ thống | Tất cả | `dss/styles/main.css:113`, `dss/styles/main.css:144-145` | Để sau | Đã có sẵn, không cần nghiệm thu thêm cho MVP |
| **Trang của sinh viên xem được trên điện thoại** (khổ 375–430 px): Trang chủ, Dự đoán từ dữ liệu của mình, Kế hoạch học tập, Lịch sử tư vấn | Sinh viên | `dss/styles/main.css` (`@media` quanh dòng 1216, 1219, 1569) | **Bắt buộc (đã đổi 21/11)** | Chủ dự án muốn dùng giống LMS. **Chưa kiểm thử** ở khổ điện thoại (xem [SCREEN_MAP.md](../ux/SCREEN_MAP.md)). Streamlit có giới hạn bố cục trên điện thoại, cần thử sớm |

> ✅ **ĐÃ CHỐT (21/11/2026): bản đầu tiên dùng LLM của nhà cung cấp trả phí** (OpenAI/Gemini/Groq).
> - Chủ dự án chọn phương án (c). Đề xuất ban đầu là (a) "không dùng LLM".
> - ⚠️ **Rủi ro đã biết, bắt buộc xử lý trước khi cho sinh viên dùng:**
>   - Bộ lọc lời khuyên có hại trên tập holdout mới đạt 65–75% (`evals/README.md:52-53`).
>   - README ghi cần một tập kiểm thử do bên thứ ba viết (`evals/README.md:61-62`).
> - Biện pháp ghi vào nghiệm thu:
>   - hạn mức chi phí theo trường;
>   - bút danh hoá trước khi gửi dữ liệu ra nước ngoài (PRD §4);
>   - tự chuyển về kế hoạch học tập theo luật khi AI lỗi hoặc hết hạn mức;
>   - ghi rõ trên giao diện rằng câu trả lời do AI tạo.
> - Gửi dữ liệu sinh viên (dù đã bút danh hoá) tới máy chủ nước ngoài cần rà soát quy định về dữ liệu cá
>   nhân tại Việt Nam. Việc này thuộc bước 7.

> ✅ **ĐÃ CHỐT (21/11/2026): vòng lớp học – bài đánh giá – kế hoạch (Stage 2/3) để sau**, theo đề xuất (b).
> - Code đã có và đã nghiệm thu kỹ thuật (`reports/stage23/ACCEPTANCE.md:8-31`), nhưng **chưa** thử
>   với trường thật (`reports/stage23/ACCEPTANCE.md:3-6`). MVP chỉ dùng dữ liệu nhập từ Kho dữ liệu.

## 7. Tóm tắt đề xuất

- **Bắt buộc (sinh viên):** Trang chủ, dự đoán từ dữ liệu của mình, kế hoạch học tập, lịch sử tư vấn.
  Cả 4 trang phải **xem được trên điện thoại**.
- **Bắt buộc (giảng viên/CVHT):** Trang chủ, Dashboard rủi ro, tìm sinh viên, huấn luyện + đánh giá mô hình,
  dự đoán hàng loạt, Trợ lý AI, Kho dữ liệu (Datasets, AI Models), và **3 trang mới**: Báo cáo, Lịch sử,
  Phân tích rủi ro (chưa có code).
- **Bắt buộc (Admin):** Tổng quan/Báo cáo, Người dùng, nhập dữ liệu, Promote/Rollback mô hình, **Cấu hình AI**.
- **Bắt buộc (dùng chung):** đăng nhập, khoá tài khoản, Google, phân quyền, chế độ production an toàn, RLS,
  bút danh hoá, kho mô hình, SHAP, nhập CSV/Excel, health check, sao lưu, HTTPS, **Trợ lý AI có LLM trả phí,
  hạn mức chi phí AI, bộ lọc an toàn AI**.
- **Việc phải làm thêm (bước 6):** 3 trang giảng viên mới, giao diện điện thoại cho sinh viên, hạn mức chi phí
  AI, nâng bộ lọc an toàn AI cho đạt ngưỡng.
- Tiêu chí nghiệm thu cho từng mục: [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).
