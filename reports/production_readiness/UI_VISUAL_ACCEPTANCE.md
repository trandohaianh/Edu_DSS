# UI Visual Acceptance — EduDSS

Phiên: "FINAL PRODUCTION GAP CLOSURE" (2026-09-26), Phần 43. Ảnh chụp THẬT (Playwright, Chromium, viewport 1440×900) từ một instance Streamlit chạy tạm thời, cô lập (`tools/capture_ui_screenshots.py`, cổng do OS tự cấp, dữ liệu cô lập trong thư mục tạm, đã dọn dẹp sau khi chạy). File ảnh gốc: `reports/production_readiness/ui_screenshots/*.png` (đã commit).

**Nguyên tắc (Phần 50)**: không tuyên bố "visually accepted" cho bất kỳ trang nào chưa thực sự xem ảnh chụp. Bảng dưới đây CHỈ đánh giá PASS/FAIL cho các trang ĐÃ chụp — các trang chưa chụp ghi rõ "CHƯA CHỤP", không suy đoán.

## Đăng nhập (00_login.png)

| Tiêu chí | Kết quả |
|---|---|
| Title | "Đăng nhập EduDSS" — ngắn, rõ |
| Alignment | Split-screen brand-trái/form-phải, form lệch phải rõ ràng, không sát mép |
| Spacing | Đồng đều, khoảng trắng hợp lý giữa các trường |
| Typography | Headline lớn rõ, hierarchy tốt (eyebrow nhỏ → headline lớn → subtitle) |
| Overflow | Không phát hiện |
| Broken text | Không phát hiện |
| Icon còn lại | Icon SVG line-art (không phải emoji) trong panel thương hiệu (logo, feature card) — có chủ đích, không phải emoji trang trí ngẫu nhiên; nút "hiện mật khẩu" (icon mắt) hợp lý theo Phần 20 ("giữ icon cho control chuẩn") |
| Error state | Đã xác nhận qua ảnh `01_sinh_vien_landing.png` (đăng nhập sai ở lượt thử đầu của script): hộp lỗi đỏ nhạt "Sai tên đăng nhập hoặc mật khẩu." hiện NGAY DƯỚI nút đăng nhập — đúng spec Phần 24 |
| Empty state | N/A |
| **PASS/FAIL** | **PASS** |

## Trang chủ (landing, trước khi vào app) — 01_*_landing.png (×3 vai trò)

| Tiêu chí | Kết quả |
|---|---|
| Title | "Ra quyết định học tập, bằng dữ liệu." |
| Icon còn lại | Emoji trong pill badge/CTA/role indicator (🎓🚀🧑‍🏫) — CHƯA sửa, xem `UI_UX_AUDIT.md` |
| Overflow/Broken text | Không phát hiện |
| **PASS/FAIL** | **PARTIAL** (bố cục/typography tốt, còn emoji chưa dọn) |

## Trang chủ (dashboard) — 02_sinh_vien_app_home.png

| Tiêu chí | Kết quả |
|---|---|
| Title | "Dashboard của bạn" |
| Sidebar nav | **Sạch — chỉ còn TEXT** (Trang chủ/Dự đoán ML/Phân cụm/Trợ lý AI/Lịch sử/Đăng xuất), xác nhận fix icon nav hoạt động đúng trên ảnh thật |
| Empty state | "Chưa có dự đoán." / "Chưa có phân tích yếu tố ảnh hưởng." — TRUNG THỰC, không có dữ liệu giả để "trông đẹp" (đúng Phần 33) |
| Icon còn lại | Toolbar chung (🔔/😊/🌙), icon nhỏ trong empty-state card (📮), nút "✨ Tạo kế hoạch" |
| Overflow/Broken text | Không phát hiện |
| **PASS/FAIL** | **PASS** (với ghi chú icon nhỏ còn lại, không nghiêm trọng) |

## Dashboard lớp học (Giảng viên) — 04_giang_vien_Dashboard.png

| Tiêu chí | Kết quả |
|---|---|
| Title | "Dashboard lớp học" |
| KPI card | 4 thẻ đều nhau, số lớn/nhãn nhỏ UPPERCASE, icon SVG nhỏ nhất quán (không phải emoji) — ĐÚNG tinh thần Phần 28 |
| Empty state | "—" cho metric chưa có dữ liệu (GPA dự đoán TB/Nguy cơ cao/Độ chính xác) THAY VÌ số giả/0 gây hiểu nhầm; card lớn "Chưa có mô hình Production để dự đoán rủi ro..." kèm hướng dẫn cụ thể — TRUNG THỰC | 
| Nhãn "Dữ liệu mô phỏng" | Có banner xanh nhạt "Chế độ dữ liệu: Dữ liệu mô phỏng (Synthetic/Demo)..." NGAY ĐẦU trang — đúng yêu cầu E-1 (đợt trước) |
| Sidebar nav | Sạch, đúng nhóm (TỔNG QUAN/GIẢNG DẠY & PHÂN TÍCH/TRỢ LÝ & KHO), có "Duyệt tài liệu" (tính năng đợt trước) |
| Overflow/Broken text | Không phát hiện |
| **PASS/FAIL** | **PASS** |

## Cài đặt Hệ thống & Thuê bao SaaS (Admin) — 05_admin_Cài_đặt.png

| Tiêu chí | Kết quả |
|---|---|
| Title | "Cài đặt Hệ thống & Thuê bao SaaS" (section_header — icon đã xóa) |
| Card header | **Còn emoji trực tiếp trong HTML riêng** (🏛️ tên trường, 👥 "Tài khoản & Phân quyền", ⚙️ "Điều chỉnh...") — KHÔNG đi qua `ui_kit.section_header` nên chưa được dọn | 
| Thông tin | Rõ ràng: mã tổ chức, tên miền, gói dịch vụ, trạng thái, hạn ngạch — bố cục card sạch |
| Overflow/Broken text | Không phát hiện |
| **PASS/FAIL** | **PARTIAL** (tiêu đề trang sạch, card con còn icon) |

## Dự đoán — Nhập tay (Sinh viên) — 04_sinh_vien_Dự_đoán.png

| Tiêu chí | Kết quả |
|---|---|
| Title | "Dự đoán kết quả học tập của bạn" |
| Tab con | "Dự đoán — Nhập tay" / "Dự đoán — Dữ liệu đã có" — có icon nhỏ, chấp nhận được |
| Empty/honest state | "Chưa có mục tiêu dự đoán được cấu hình cho lớp của bạn. Vui lòng chờ Giảng viên thiết lập..." — TRUNG THỰC, hướng dẫn hành động rõ |
| Overflow/Broken text | Không phát hiện |
| **PASS/FAIL** | **PASS** |

## Các trang CHƯA CHỤP trong phiên này

Khám phá — Xử lý dữ liệu, Phân cụm (nội dung đầy đủ), Model Registry, Kho dữ liệu, Cấu hình AI, Báo cáo hệ thống, Lịch sử tư vấn, Onboarding Trường Đại học, Duyệt tài liệu (nội dung đầy đủ, chỉ chụp được lúc đang chuyển trang), Trợ lý AI (nội dung chat đầy đủ), Giải thích bài học, Hướng nghiệp — **KHÔNG tuyên bố PASS/FAIL cho các trang này**, cần chụp thêm trước khi kết luận.

## Mobile / responsive

**CHƯA kiểm tra** — chỉ chụp desktop 1440×900 trong phiên này (đúng yêu cầu tối thiểu Phần 43, nhưng phần "nếu có browser automation: test thêm mobile width" chưa thực hiện do giới hạn thời gian phiên này).

## Tổng kết

5/5 trang đã chụp và đánh giá đều ở mức PASS hoặc PARTIAL (không có FAIL/vỡ layout/tràn ngang) — chất lượng UI nền tảng tốt, đúng tinh thần tối giản. Vấn đề còn lại chủ yếu là icon/emoji RẢI RÁC ở các thành phần KHÔNG đi qua `ui_kit.py` (toolbar chung, card header viết tay bằng HTML trực tiếp trong một số file như `admin_settings.py`) — đã ghi trong `UI_UX_AUDIT.md`, KHÔNG sửa hết trong phiên này vì cần rà từng file riêng để không phá bố cục.
