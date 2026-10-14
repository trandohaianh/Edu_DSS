# Bài 1 — Tổng quan EduDSS

## 1. Mục tiêu buổi học

Sau bài này, bạn phải tự vẽ được trong đầu "bức tranh một trang" của toàn bộ hệ thống:
nó là gì, phục vụ ai, giải quyết vấn đề gì, và các mảnh lớn (ML, RAG, DSS, quản trị)
ghép với nhau ra sao. Đây là nền tảng để mọi bài sau có chỗ "cắm vào".

## 2. Kiến thức cần nhớ trước

Không cần kiến thức trước — đây là bài mở đầu. Chỉ cần bạn nhớ: đây là một ứng dụng
web viết bằng Streamlit (một framework Python để dựng giao diện nhanh), chạy tại
`run_dss.py`.

## 3. Giải thích từ con số 0

Hãy tưởng tượng một trường đại học có hàng nghìn sinh viên. Nếu chỉ nhìn vào bảng điểm,
giảng viên khó biết sinh viên nào đang gặp khó khăn *trước khi* họ trượt môn. EduDSS
(Education Decision Support System — Hệ thống hỗ trợ ra quyết định trong giáo dục) được
xây để giải quyết đúng vấn đề đó: dự đoán sớm rủi ro học tập, giải thích vì sao rủi ro đó
xuất hiện, và đề xuất một kế hoạch học tập cụ thể — chứ không chỉ đưa ra một con số dự
đoán trơ trọi.

Hệ thống có **3 vai trò (role)** dùng chung một ứng dụng nhưng nhìn thấy giao diện và dữ
liệu khác nhau:
- **Sinh viên (Student)** — chỉ xem dữ liệu của chính mình, nhận kế hoạch học tập, hỏi
  AI về bài giảng, xem gợi ý định hướng nghề nghiệp.
- **Giảng viên (Lecturer)** — xem toàn bộ lớp, huấn luyện mô hình, phân cụm sinh viên,
  quản lý tài liệu bài giảng (CMS nội bộ).
- **Quản trị viên (Admin)** — quản lý mô hình (Model Registry), cấu hình nhà cung cấp AI,
  quản lý Knowledge Base, xem báo cáo toàn hệ thống.

## 4. Giải thích kỹ thuật

Về mặt kỹ thuật, EduDSS là **một tiến trình Streamlit duy nhất** (không phải kiến trúc
microservices nhiều server), với các "tab" tương ứng các trang chức năng, được điều
hướng (route) qua `dss/main.py`. Quyền truy cập theo vai trò được kiểm soát ở **hai lớp**:
lớp điều hướng (ẩn/hiện tab trên sidebar) và lớp hàm (decorator `@require_role(...)`
chặn ngay tại hàm xử lý, không chỉ ẩn nút bấm). Bên dưới UI là các "services" (dịch vụ)
python thuần — mỗi dịch vụ làm một việc: huấn luyện mô hình, chẩn đoán, sinh kế hoạch học
tập, truy xuất tài liệu RAG, gọi LLM, v.v.

## 5. Ví dụ cực dễ hiểu

Giống như một phòng khám: **Sinh viên** đến khám (xem dashboard của mình), **Bác sĩ**
(Giảng viên) xem hồ sơ toàn bộ bệnh nhân trong khoa và ra y lệnh, **Quản lý bệnh viện**
(Admin) quyết định thiết bị nào (mô hình AI nào) được đưa vào sử dụng chính thức.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Sinh viên đăng nhập và vào "Trang chủ", hệ thống lấy dòng dữ liệu của riêng sinh viên
đó từ tập dữ liệu đã tải, chạy qua mô hình đang ở trạng thái Production (xem Bài 22), rồi
hiển thị mức rủi ro và một thẻ (card) gợi ý xem kế hoạch học tập AI.

## 7. Luồng xử lý thực tế trong project

```
Đăng nhập (auth_service) → roles.py xác định vai trò → main.py điều hướng đến tab đúng
  → tab gọi service tương ứng → service đọc/ghi dữ liệu qua warehouse.py (lưu trữ file)
```

## 8. Công thức nếu có

Không có công thức ở bài tổng quan.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng.

## 10. Cách đọc kết quả

Không áp dụng — bài này là bức tranh tổng thể, không có "kết quả" để đọc.

## 11. Vì sao project dùng phương pháp này

Streamlit + kiến trúc service-layer đơn giản phù hợp quy mô đồ án tốt nghiệp: một người
phát triển, thời gian giới hạn, cần một hệ thống chạy được và kiểm chứng được, không cần
hạ tầng phân tán phức tạp.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây chính là "cái khung" chứa tất cả — mọi bài học sau (ML, RAG, DSS...) đều là các module
bên trong bức tranh này.

## 13. Input là gì

Người dùng (Sinh viên/Giảng viên/Admin) tương tác qua trình duyệt web.

## 14. Output là gì

Giao diện web hiển thị dự đoán, chẩn đoán, kế hoạch học tập, câu trả lời AI, báo cáo.

## 15. Output được chuyển cho module nào tiếp theo

Không áp dụng ở mức tổng quan — hãy xem Bài 2 (Kiến trúc) để thấy luồng dữ liệu chi tiết
giữa các lớp.

## 16. Ưu điểm

Đơn giản, dễ bảo trì, một codebase duy nhất, nhanh để phát triển tính năng mới, dễ kiểm
thử tự động (test được toàn bộ luồng UI bằng Playwright).

## 17. Nhược điểm

Không phải kiến trúc phân tán nên khó mở rộng theo chiều ngang (horizontal scaling) như
một hệ thống microservices thật; một tiến trình Streamlit phục vụ tất cả người dùng.

## 18. Limitation thực tế của project

Chưa từng được kiểm thử với tải thực (load test) ở quy mô lớn; dữ liệu vẫn là dữ liệu
tổng hợp/demo (xem Bài 3); chưa kết nối LMS/CMS thật (xem Bài 21).

## 19. Hội đồng có thể hỏi gì

"EduDSS khác gì một hệ thống dự đoán điểm số thông thường?"

## 20. Câu trả lời ngắn 20–40 giây

"EduDSS không dừng ở việc dự đoán điểm số. Nó là một hệ thống hỗ trợ ra quyết định đầy
đủ: dự đoán rủi ro, giải thích vì sao (SHAP), chẩn đoán nguyên nhân bằng luật rõ ràng,
rồi sinh ra một kế hoạch học tập cụ thể cho từng sinh viên — đồng thời có lớp AI hỏi-đáp
dựa trên tài liệu thật của giảng viên, và lớp quản trị mô hình cho Admin."

## 21. Câu trả lời chi tiết

Nhấn mạnh 3 vai trò khác nhau nhìn thấy hệ thống khác nhau (không phải một giao diện
chung cho tất cả), và chuỗi xử lý đầy đủ Dữ liệu→Dự đoán→Giải thích→Chẩn đoán→Khuyến
nghị→Kế hoạch→Hành động (xem Bài 14 để hiểu sâu vì sao đây mới thực sự là DSS).

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy nếu chỉ có phần dự đoán ML thôi thì có gọi là DSS được không?"

## 23. Cách trả lời câu vặn

"Không. Một mô hình dự đoán đơn thuần đưa ra một con số nhưng không nói AI PHẢI LÀM GÌ
TIẾP THEO. DSS đòi hỏi phải có thêm chẩn đoán nguyên nhân và khuyến nghị hành động cụ
thể — đó là điều em xây thêm ở Diagnosis Engine và Learning Plan (Bài 14–15)."

## 24. Những câu không được nói

- "Đây là hệ thống production sẵn sàng triển khai cho trường đại học thật." (Sai — xem
  Bài 24, còn nhiều giới hạn.)
- "Tất cả 3 vai trò dùng chung một giao diện." (Sai — có phân quyền 2 lớp.)

## 25. 10 câu tự kiểm tra

1. EduDSS có bao nhiêu vai trò người dùng? Kể tên.
2. EduDSS chạy trên framework nào?
3. File nào là điểm vào (entry point) của ứng dụng?
4. Phân quyền theo vai trò được kiểm soát ở mấy lớp?
5. Vì sao chọn Streamlit thay vì kiến trúc web đầy đủ (React/Django)?
6. EduDSS có phải kiến trúc microservices không?
7. Sinh viên có thể xem dữ liệu của sinh viên khác không?
8. Admin có quyền gì mà Giảng viên không có?
9. Vấn đề cốt lõi mà EduDSS giải quyết là gì?
10. "DSS" trong EduDSS viết tắt của gì?

## 26. Đáp án riêng

1. 3 vai trò: Sinh viên, Giảng viên, Admin.
2. Streamlit.
3. `run_dss.py`.
4. 2 lớp: điều hướng (nav-level) và hàm (`@require_role`).
5. Phù hợp quy mô đồ án, phát triển nhanh, một người một codebase Python.
6. Không — một tiến trình duy nhất.
7. Không — luôn lọc theo ID của chính sinh viên đó.
8. Quản lý Model Registry, cấu hình AI, xem báo cáo toàn hệ thống, quản lý Knowledge Base.
9. Phát hiện sớm rủi ro học tập và hỗ trợ hành động cụ thể, không chỉ báo cáo điểm số.
10. Decision Support System — Hệ thống hỗ trợ ra quyết định.

## 27. 5 CÂU PHẢI THUỘC

1. "EduDSS là hệ thống hỗ trợ ra quyết định học tập ba vai trò: Sinh viên, Giảng viên, Admin."
2. "Phân quyền được thực hiện ở hai lớp: điều hướng và hàm xử lý."
3. "EduDSS không chỉ dự đoán — nó chẩn đoán nguyên nhân và đề xuất hành động cụ thể."
4. "Toàn bộ hệ thống là một tiến trình Streamlit duy nhất, không phải microservices."
5. "445 test đã pass ở baseline đóng băng (freeze), không có lỗi P0 nào còn tồn đọng."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Role-Based Access Control (RBAC) — Kiểm soát truy cập theo vai trò
- Service layer — Lớp dịch vụ
- Decision Support System (DSS) — Hệ thống hỗ trợ ra quyết định
- Entry point — Điểm vào ứng dụng
- Two-layer authorization — Phân quyền hai lớp
