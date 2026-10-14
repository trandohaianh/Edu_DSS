# Kịch bản demo EduDSS (khoảng 10 phút)

Chạy app: `run_app.bat` (hoặc `streamlit run run_dss.py --server.port 8502` trong thư mục `app/`),
mở http://localhost:8502. Cần `app/.env` có ít nhất 1 key AI (Gemini hoặc Groq) — xem `.env.example`.

| Vai trò | Tài khoản | Mật khẩu |
|---|---|---|
| Giảng viên | `giangvien` | `gv123` |
| Admin | `admin` | `admin123` |
| Sinh viên | `sv901` | `sv901123` |

## 1. Giảng viên — huấn luyện và dự đoán (3 phút)

1. Đăng nhập `giangvien` → **Huấn luyện & dự đoán** → tab **Huấn luyện mô hình** → bấm **Tiến hành**
   (khoảng 30–60 giây với 20.000 sinh viên; lần huấn luyện lại cùng dữ liệu chỉ vài giây).
2. Tab **Kết quả đánh giá mô hình**: chỉ số RMSE/MAE/R², bảng so sánh, biểu đồ Thực tế vs Dự đoán.
3. Tab **Dự đoán → Dữ liệu đã có** → chọn 1 sinh viên → **Dự đoán cho Sinh viên này**.

## 2. Admin — duyệt mô hình lên Production (1 phút)

Đăng nhập `admin` → **Kho dữ liệu** → tab **AI Models** → mở mô hình vừa huấn luyện →
**Đặt làm Production**. Từ lúc này Sinh viên và Dashboard dùng mô hình này.

## 3. Giảng viên — nạp bài giảng (CMS) (1 phút)

**Trợ lý AI** → tab **Giải thích bài giảng** → bấm **Nạp 3 bài giảng mẫu**
(môn CS301: Hồi quy tuyến tính · Random Forest · Đánh giá mô hình — tệp trong `demo/cms_lectures/`).
Nút chỉ hiện ở chế độ demo khi CMS còn trống. Có thể nạp bài thật bằng form "Nạp bài giảng mới".

Dòng lệnh tương đương: `python tools/seed_demo_lectures.py --ask`

## 4. Sinh viên — dự báo, tư vấn và giải thích bài học (4 phút)

1. Đăng nhập `sv901` → **Trang chủ**: điểm dự báo, mức rủi ro, ô **Hỏi nhanh Trợ lý AI**.
2. **Trợ lý AI** → tab **Kế hoạch học tập**: hỏi tự do, ví dụ "Làm sao để em tăng điểm Machine Learning?".
3. Tab **Giải thích bài học** → chọn **Bài 3** → hỏi "F1-macro khác Accuracy như thế nào?" hoặc bấm
   **Giải thích dễ hơn / Cho ví dụ minh họa**. Câu trả lời chỉ dựa trên bài giảng đã nạp và ghi nguồn bài.
   Bật **Học bằng câu hỏi gợi mở (Socratic)** để AI hỏi dẫn dắt thay vì đưa đáp án.

## Câu hỏi hay gặp khi bảo vệ

- *AI có bịa không?* — Giải thích bài học chỉ dùng nội dung bài giảng (CMS_ONLY); câu hỏi ngoài bài
  thì AI nói rõ là chưa có trong bài giảng và chỉ giải thích thêm khi Giảng viên cho phép.
- *Vì sao Sinh viên phải chờ Admin duyệt?* — Quy trình Model Governance: mô hình mới là Candidate,
  chỉ bản Production đã duyệt mới phục vụ Sinh viên. Giảng viên dùng thử được ngay bản vừa huấn luyện.
- *Dữ liệu thật?* — Dữ liệu demo là mô phỏng (có nhãn trên mọi trang), không phải sinh viên thật.
