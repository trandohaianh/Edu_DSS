# UI/UX Audit — EduDSS

Phiên: "FINAL PRODUCTION GAP CLOSURE" (2026-09-26), Phần 18. Kiểm tra bằng đọc code (`ui_kit.section_header`/`page_header` call sites) + **screenshot thật** (Playwright, xem `UI_VISUAL_ACCEPTANCE.md` và `reports/production_readiness/ui_screenshots/`) — không chỉ đọc code suông.

**Kết luận sớm quan trọng nhất**: hệ thống UI hiện tại KHÔNG phải một giao diện chưa đầu tư — nhiều phần (Login, sidebar nav, hầu hết section header, empty state) đã trải qua NHIỀU đợt audit/tinh chỉnh trước đó (thấy rõ qua comment lịch sử: "Student Information Architecture audit 2026-09", "Lecturer/Admin Product Acceptance audit", Login "v4" khớp file tham chiếu người dùng cung cấp đo bằng Playwright). Việc redesign trong phiên này vì vậy là **tinh chỉnh có mục tiêu** (xóa icon tiêu đề, rút gọn tên kỹ thuật, tăng input height), KHÔNG PHẢI xây lại từ đầu.

## Bảng kiểm kê theo trang (route/role)

| Route (nav) | Role | Tiêu đề hiện tại | Icon tiêu đề | Vấn đề phát hiện | Đề xuất | Trạng thái |
|---|---|---|---|---|---|---|
| Trang chủ (landing, trước "Bắt đầu khám phá") | Cả 3 | "Ra quyết định học tập, bằng dữ liệu." | — | Emoji trong pill badge ("🎓 Đồ án tốt nghiệp..."), nút CTA ("🚀 Bắt đầu khám phá"), role indicator ("🧑‍🏫 Giảng viên / CVHT") — trang này dùng `st.markdown` HTML trực tiếp trong `home.py`, KHÔNG qua `ui_kit.section_header` nên fix trung tâm chưa chạm tới | Cân nhắc bỏ emoji ở CTA/badge — CHƯA sửa trong phiên này (rủi ro: đây là trang ấn tượng đầu tiên, đã được thiết kế kỹ — cần xác nhận thêm trước khi đụng) | **CHƯA SỬA** |
| Trang chủ (dashboard, sau khi vào app) | Sinh viên | "Dashboard của bạn" | ~~🎓~~ (đã xóa) | Icon 🔔 (chuông thông báo), 😊/🌙 (toggle sáng/tối), ✨ (nút "Tạo kế hoạch"), 💬 (placeholder hỏi AI), 📌/📮 nhỏ trong card — TẤT CẢ ở tầng header/toolbar CHUNG (main.py), không riêng trang này | Xem mục "Header/toolbar chung" bên dưới | **MỘT PHẦN** (tiêu đề trang đã sạch, toolbar chung chưa) |
| Dashboard lớp học | Giảng viên | "Dashboard lớp học" | ~~📊~~ (đã xóa) | KPI card có icon SVG nhỏ (người/mũ tốt nghiệp/cảnh báo/mắt) — ĐÃ là line-art SVG nhất quán (không phải emoji), nhỏ, không "icon lớn" — chấp nhận được theo Phần 28. Card header dùng dấu `(` ngoặc trang trí trước tiêu đề ("(Phân bố mức độ rủi ro hiện tại") — kiểm tra: đây là 1 chi tiết thẩm mỹ (accent bracket), không phải lỗi render | Giữ nguyên KPI icon (đã tối giản đúng mức); không cần sửa thêm | **ĐÃ ĐẠT** |
| Khám phá — Xử lý dữ liệu | Giảng viên/Admin | "Khám phá — Xử lý dữ liệu" | ~~🔍~~ (đã xóa) | Chưa chụp ảnh trang này trong phiên | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Huấn luyện — Dự đoán / "Huấn luyện mô hình" | Giảng viên/Admin | "Huấn luyện mô hình" | `icon="2️⃣"` (SỐ EMOJI — rõ ràng là tàn dư đánh số bước cũ, không phải icon có nghĩa) | Icon số 2️⃣ vô nghĩa với người dùng cuối (không phải "bước 2" nào hiển thị rõ) | Tham số `icon` đã bị vô hiệu hóa ở tầng `ui_kit.py` — KHÔNG còn render, nhưng khuyến nghị dọn tham số thừa này khỏi lời gọi (cosmetic, không gấp) | **ĐÃ ĐẠT** (không còn hiện) |
| Dự đoán — Nhập tay/Dữ liệu đã có/Hàng loạt | Sinh viên/Giảng viên | "Dự đoán kết quả học tập của bạn" | — | Tab con có icon nhỏ (👤 📂), card "Phiếu nhập thông tin" có icon 📝 — đã kiểm tra bằng screenshot thật, KHÔNG rối mắt, ở mức chấp nhận được | Không sửa — mức độ hợp lý | **ĐÃ ĐẠT** (mức chấp nhận được) |
| Phân cụm — Gợi ý | Sinh viên/Giảng viên | "Nhóm học tập của bạn" / "Phân cụm & Gợi ý" | ~~🔬~~ (đã xóa) | Chưa chụp chi tiết | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Tư vấn | Sinh viên | "Kế hoạch học tập của bạn" | ~~🤖~~ (đã xóa) | Placeholder "💬 Hỏi AI về việc học của bạn..." — icon trong placeholder input | Cân nhắc bỏ — CHƯA sửa (placeholder input là chi tiết rất nhỏ) | **MỘT PHẦN** |
| Tư vấn | Giảng viên/Admin | "Tư vấn" (đã rút gọn từ "Tư vấn — AI (LLM)") | ~~🤖~~ (đã xóa) | — | — | **ĐÃ ĐẠT** (đợt này) |
| Giải thích bài học/bài giảng | Sinh viên / Giảng viên+Admin | "Giải thích bài học" / "Giải thích bài giảng" (rút gọn từ "...(CMS)") | ~~📖~~ (đã xóa) | Chưa chụp ảnh | — | **ĐÃ SỬA TIÊU ĐỀ**, chưa kiểm thị giác |
| Hướng nghiệp / Định hướng nghề nghiệp | Sinh viên / Giảng viên+Admin | "Hướng nghiệp của bạn" / "Định hướng nghề nghiệp" (rút gọn từ "...(Career Decision Support System)") | ~~🧭~~ (đã xóa) | Chưa chụp ảnh | — | **ĐÃ SỬA TIÊU ĐỀ**, chưa kiểm thị giác |
| Kho dữ liệu | Giảng viên/Admin | "Kho dữ liệu" | ~~📦~~ (đã xóa) | Chưa chụp | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Model Registry | Admin | "Model Registry" | ~~🗄️~~ (đã xóa) | Tên tiếng Anh kỹ thuật thuần túy (Part 41) | Cân nhắc đổi tên — CHƯA sửa (đây là khái niệm kỹ thuật đặc thù cho Admin, đổi tên tiếng Việt có thể kém rõ ràng hơn — cần người dùng xác nhận thuật ngữ mong muốn) | **CHƯA SỬA** (judgment call, cần xác nhận) |
| Tài liệu (trước "Quản lý tri thức (RAG & Knowledge Base)") | Admin | "Tài liệu" | ~~📚~~ (đã xóa) | Nhãn nav cũng đã đổi "Tri thức RAG" → "Tài liệu" (đồng bộ) | — | **ĐÃ ĐẠT** |
| Duyệt tài liệu | Giảng viên | "Duyệt tài liệu môn học" | ~~📄~~ (đã xóa) | — | — | **ĐÃ ĐẠT** |
| Cấu hình AI | Admin | "Cấu hình AI" | ~~⚙️~~ (đã xóa) | Chưa chụp | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Báo cáo hệ thống | Admin | "Báo cáo hệ thống" | ~~📈~~ (đã xóa) | Chưa chụp | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Lịch sử tư vấn | Sinh viên | "Lịch sử tư vấn" | ~~📝~~ (đã xóa) | Chưa chụp | — | **CHƯA KIỂM TRA THỊ GIÁC** |
| Cài đặt (Cài đặt Hệ thống & Thuê bao SaaS) | Admin | "Cài đặt Hệ thống & Thuê bao SaaS" | ~~🔧~~ (đã xóa ở section_header) | **Đã chụp ảnh thật**: card header bên trong trang dùng emoji TRỰC TIẾP trong HTML riêng (🏛️ tên trường, 👥 "Tài khoản & Phân quyền", ⚙️ "Điều chỉnh thông tin...") — KHÔNG đi qua `ui_kit.section_header` nên fix trung tâm chưa chạm tới | Cần sửa RIÊNG file `admin_settings.py` (không sửa trong phiên này — nhiều card header tương tự, cần rà từng cái để không phá bố cục) | **PHÁT HIỆN, CHƯA SỬA** |
| Onboarding Trường Đại học | Platform Admin | "Onboarding Trường Đại học" | ~~🏛️~~ (đã xóa) | Chưa chụp | — | **CHƯA KIỂM TRA THỊ GIÁC** |

## Header/toolbar chung (mọi trang sau đăng nhập)

Thấy trong MỌI screenshot đã chụp — không phải lỗi riêng trang nào:
- Toggle "😊 Sáng" / chế độ tối "🌙" — icon emoji trực tiếp.
- Chuông thông báo "🔔".
- Các icon này nằm trong `dss/main.py` (thanh công cụ trên cùng, không phải `ui_kit.py`) — **CHƯA rà/sửa trong phiên này** (rủi ro: đây là thành phần TOÀN CỤC xuất hiện ở MỌI trang, cần test kỹ trước khi đổi để không phá layout header).

## Login / Register

- **Login**: đã kiểm tra kỹ (Mục riêng trong `FINAL_PRODUCTION_GAP_REPORT.md`) — thiết kế split-screen đã rất hoàn thiện từ trước (khớp file tham chiếu người dùng cung cấp, đo bằng Playwright qua nhiều vòng lặp). Chỉ sửa 1 giá trị nhỏ: input height 46px → 48px. Screenshot thật xác nhận: sạch, hiện đại, đúng tinh thần "Google-like minimal".
- **Register**: **KHÔNG TỒN TẠI** trong hệ thống — đã grep toàn bộ `dss/` xác nhận không có màn hình/luồng đăng ký tự phục vụ nào. Tài khoản được tạo qua: (1) seed mặc định (`admin`/`giangvien`, chỉ môi trường dev/demo), (2) auto-provision cho Sinh viên khi đăng nhập lần đầu bằng mã số hợp lệ (`SV0xx` + mật khẩu quy ước), (3) (suy luận, chưa xác minh) cấp phát qua Admin/LMS thật cho môi trường REAL_LMS. **KHÔNG xây mới Register trong phiên này** — đây là thay đổi MÔ HÌNH XÁC THỰC (self-service vs. cấp phát), không phải redesign thuần túy, và có hệ quả bảo mật (ai được tự tạo tài khoản, với vai trò gì) cần quyết định sản phẩm rõ ràng trước khi xây, không phải việc "vẽ lại giao diện". Đánh dấu `NOT_APPLICABLE` cho Phần 25, ghi rõ lý do thay vì bịa 1 màn hình.

## Tổng kết

- **Đã sửa trong phiên này**: icon tiêu đề trang (30+ điểm gọi `section_header`/`page_header`, sửa tập trung 1 chỗ), icon sidebar nav, 4 tiêu đề lộ thuật ngữ kỹ thuật (LLM/RAG/CMS/CDSS), input height Login, nhãn nav "Tri thức RAG"→"Tài liệu".
- **Đã phát hiện, CHƯA sửa** (ghi rõ để không tuyên bố sai): icon trong toolbar chung (chuông/theme toggle), card header dùng HTML trực tiếp với emoji (vd. `admin_settings.py`), icon trong button/tab/placeholder rải rác (mức độ nhẹ, đã xem qua screenshot, không nghiêm trọng), "Model Registry" vẫn tiếng Anh (cần xác nhận thuật ngữ thay thế), trang Landing (trước khi vào app) vẫn dùng emoji trong CTA/badge.
- **Không xây mới**: Register (không tồn tại, cần quyết định sản phẩm trước).
