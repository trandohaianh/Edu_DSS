# Bài 22 — Model Registry: Train ≠ Deploy

## 1. Mục tiêu buổi học

Hiểu vòng đời (lifecycle) 3 trạng thái của một mô hình trong Model Registry, và khắc sâu
nguyên tắc: **huấn luyện xong một mô hình KHÔNG có nghĩa là mô hình đó tự động được đưa
vào sử dụng chính thức (production).**

## 2. Kiến thức cần nhớ trước

Bài 6, 8 (Classification/Regression — nơi mô hình được huấn luyện).

## 3. Giải thích từ con số 0

Trong phát triển phần mềm nói chung, có một nguyên tắc quan trọng: **"viết code xong"
khác với "đưa code đó vào chạy thật cho người dùng."** Tương tự với machine learning:
**"huấn luyện xong một mô hình"** khác với **"đưa mô hình đó vào phục vụ người dùng thật
(production)."** Giữa hai bước này cần có một bước kiểm duyệt (review/approval) — trong
EduDSS, bước đó do CON NGƯỜI (Admin) quyết định, không phải máy tính tự động.

## 4. Giải thích kỹ thuật

Vòng đời mô hình có 3 trạng thái, quản lý bởi `dss/services/model_registry.py`:
1. **Candidate (Ứng viên)** — mô hình vừa được huấn luyện xong (Bài 6, 8), đã có các chỉ
   số đánh giá (Accuracy/R²...), nhưng CHƯA được dùng để phục vụ người dùng thật.
2. **Production (Đang triển khai)** — mô hình đã được Admin phê duyệt (`promote()`,
   được bảo vệ bởi decorator `@require_role("Admin")`), hiện đang là mô hình DUY NHẤT
   được dùng để tạo ra dự đoán hiển thị cho Sinh viên/Giảng viên.
3. **Archived (Lưu trữ)** — mô hình Production cũ, đã bị thay thế bởi một mô hình
   Production mới hơn, được giữ lại để tham khảo/rollback (quay lại phiên bản cũ) nếu
   cần.

**Xác nhận quan trọng nhất (đã kiểm chứng trực tiếp trong code)**: điểm gọi huấn luyện
THỰC SỰ trong `ml_hub.py`/`model_service.py` truyền tham số `auto_promote=False` một cách
tường minh — dù hệ thống có tính một cờ nội bộ `is_best` (mô hình này có phải tốt nhất so
với các candidate khác không), cờ đó KHÔNG được dùng để tự động promote. Việc promote
LUÔN LUÔN cần Admin bấm nút xác nhận.

## 5. Ví dụ cực dễ hiểu

Giống như một ứng viên vừa tốt nghiệp thủ khoa (candidate tốt nhất) vẫn phải qua vòng
phỏng vấn và ký hợp đồng chính thức (Admin promote) trước khi được giao việc thật — bằng
tốt nghiệp xuất sắc không tự động biến thành hợp đồng lao động.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên huấn luyện 4 thuật toán mới (Bài 6/8), cả 4 đều trở thành candidate. Admin
vào tab Model Registry, xem bảng so sánh, và TỰ TAY chọn 1 candidate để promote lên
Production. Cho đến khi Admin làm việc đó, Dashboard của Sinh viên vẫn tiếp tục dùng mô
hình Production CŨ (nếu có).

## 7. Luồng xử lý thực tế trong project

```
Giảng viên bấm "Huấn luyện" → 4 thuật toán chạy (Bài 6/8) → mỗi cái trở thành 1 candidate
  → hệ thống tính is_best (candidate nào có chỉ số tốt nhất) — CHỈ ĐỂ HIỂN THỊ GỢI Ý
  → auto_promote=False được truyền tường minh tại điểm gọi thật → KHÔNG tự động promote
  → Admin vào Model Registry, xem xét, bấm nút promote() [@require_role("Admin")]
  → candidate được chọn chuyển thành Production; Production cũ (nếu có) chuyển thành
    Archived
  → Dashboard Sinh viên/Giảng viên từ giờ dùng mô hình Production MỚI
```

## 8. Công thức nếu có

```
should_promote = bool(auto_promote) if auto_promote is not None else bool(is_best)
```
(công thức logic trong `warehouse.py`, nhưng tại điểm gọi thật, `auto_promote=False`
luôn được truyền tường minh, nên `should_promote` luôn là `False` bất kể `is_best`.)

## 9. Giải thích từng ký hiệu trong công thức

- `auto_promote` — tham số quyết định có tự động promote hay không, được truyền vào từ
  nơi gọi hàm huấn luyện.
- `is_best` — cờ nội bộ cho biết candidate này có phải tốt nhất trong đợt huấn luyện hiện
  tại hay không (dựa trên so sánh chỉ số đánh giá).
- `should_promote` — kết quả cuối cùng quyết định có promote hay không.
- Điều quan trọng: công thức CÓ THỂ dùng `is_best` nếu `auto_promote=None`, nhưng trong
  THỰC TẾ, điểm gọi thật luôn truyền `auto_promote=False` một cách tường minh — nghĩa là
  nhánh dùng `is_best` KHÔNG BAO GIỜ được kích hoạt trong luồng chạy thực tế hiện nay.

## 10. Cách đọc kết quả

Khi thấy một candidate có chỉ số tốt nhất (is_best=True), điều đó CHỈ có nghĩa là "gợi ý
cho Admin xem xét", KHÔNG có nghĩa là "mô hình này đã hoặc sẽ tự động được dùng cho người
dùng thật."

## 11. Vì sao project dùng phương pháp này

Yêu cầu con người phê duyệt trước khi một mô hình mới ảnh hưởng đến người dùng thật là
một thực hành quản trị AI có trách nhiệm (responsible AI governance) — tránh trường hợp
một mô hình có chỉ số tốt trên tập test nhưng có vấn đề khác (ví dụ thiên lệch, hành vi
lạ) vô tình được đưa vào sử dụng mà không ai kiểm tra.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là bước quản trị nằm NGAY SAU khi Classification/Regression huấn luyện xong (Bài 6, 8) —
quyết định mô hình nào thực sự được dùng trong Chuỗi 1 (Dashboard, Diagnosis Engine...).

## 13. Input là gì

Một mô hình vừa huấn luyện xong (candidate) cùng các chỉ số đánh giá của nó.

## 14. Output là gì

Trạng thái của mô hình: `candidate`, `production`, hoặc `archived`.

## 15. Output được chuyển cho module nào tiếp theo

Mô hình ở trạng thái `production` được dùng bởi Dashboard, Diagnosis Engine, và mọi tính
năng cần dự đoán cho người dùng thật.

## 16. Ưu điểm

An toàn, có kiểm soát của con người, có thể rollback (quay lại) về mô hình cũ nếu mô hình
mới có vấn đề sau khi triển khai.

## 17. Nhược điểm

Chậm hơn một hệ thống tự động hoàn toàn (continuous deployment) — cần Admin chủ động
kiểm tra và bấm nút.

## 18. Limitation thực tế của project

Chưa có cơ chế tự động phát hiện "model drift" (mô hình Production dần kém chính xác
theo thời gian) để nhắc Admin xem xét huấn luyện lại — việc theo dõi và quyết định hoàn
toàn dựa vào Admin chủ động.

## 19. Hội đồng có thể hỏi gì

"Nếu mô hình mới huấn luyện có chỉ số tốt hơn mô hình đang Production, nó có tự động
thay thế không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. Hệ thống có tính một cờ nội bộ cho biết candidate nào có chỉ số tốt nhất, nhưng
đó chỉ là thông tin gợi ý hiển thị cho Admin. Em đã xác minh trực tiếp trong code rằng
điểm gọi huấn luyện thật sự truyền tham số `auto_promote=False` một cách tường minh — có
nghĩa là việc promote một mô hình lên Production LUÔN LUÔN cần Admin chủ động bấm xác
nhận, không bao giờ xảy ra tự động."

## 21. Câu trả lời chi tiết

Trình bày công thức `should_promote` ở mục 8-9, giải thích rõ nhánh `is_best` tồn tại về
mặt logic nhưng không bao giờ được kích hoạt trong luồng chạy thực tế vì `auto_promote`
luôn được truyền `False` tường minh tại điểm gọi thật.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy tại sao vẫn giữ logic `is_best` trong code nếu nó không bao giờ được dùng?"

## 23. Cách trả lời câu vặn

"Logic đó được giữ lại như một khả năng cấu hình (configurable capability) cho tương lai
— nếu sau này muốn bật chế độ tự động promote có kiểm soát (ví dụ trong môi trường CI/CD
huấn luyện tự động), chỉ cần thay đổi giá trị truyền vào tham số `auto_promote` tại điểm
gọi, mà không cần sửa lại logic cốt lõi trong `warehouse.py`. Hiện tại, quyết định thiết
kế có chủ đích là luôn giữ `auto_promote=False` để đảm bảo con người luôn kiểm soát."

## 24. Những câu không được nói

- "Mô hình tốt nhất tự động được đưa vào Production." (Sai.)
- "Huấn luyện xong nghĩa là đã triển khai cho người dùng." (Sai — cần Admin promote thủ
  công.)

## 25. 10 câu tự kiểm tra

1. 3 trạng thái trong vòng đời Model Registry là gì?
2. Ai có quyền promote một mô hình lên Production?
3. `is_best` dùng để làm gì?
4. `auto_promote` được truyền giá trị gì tại điểm gọi huấn luyện thật?
5. Công thức `should_promote` là gì?
6. Nhánh dùng `is_best` trong công thức có bao giờ được kích hoạt trong thực tế không?
7. Archived nghĩa là gì?
8. Vì sao cần con người phê duyệt trước khi promote?
9. Dashboard Sinh viên dùng mô hình ở trạng thái nào?
10. Nhược điểm của việc yêu cầu phê duyệt thủ công là gì?

## 26. Đáp án riêng

1. Candidate → Production → Archived.
2. Chỉ Admin (`@require_role("Admin")`).
3. Đánh dấu candidate nào có chỉ số đánh giá tốt nhất trong đợt huấn luyện, chỉ để gợi ý
   hiển thị.
4. `False`, truyền tường minh.
5. `should_promote = bool(auto_promote) if auto_promote is not None else bool(is_best)`.
6. Không — vì `auto_promote` luôn được truyền `False` tường minh tại điểm gọi thật.
7. Mô hình Production cũ, đã bị thay thế, được giữ lại để tham khảo/rollback.
8. Để tránh một mô hình có vấn đề tiềm ẩn (dù chỉ số tốt) vô tình ảnh hưởng đến người
   dùng thật mà không ai kiểm tra.
9. Production.
10. Chậm hơn tự động hóa hoàn toàn, cần Admin chủ động theo dõi và hành động.

## 27. 5 CÂU PHẢI THUỘC

1. "3 trạng thái: Candidate → Production → Archived."
2. "Chỉ Admin có quyền promote một mô hình lên Production — được bảo vệ bằng
   @require_role."
3. "auto_promote=False được truyền tường minh tại điểm gọi thật — training KHÔNG BAO GIỜ
   tự động promote."
4. "is_best chỉ là gợi ý hiển thị, không quyết định việc promote."
5. "Huấn luyện xong (Train) khác hoàn toàn với triển khai chính thức (Deploy) — cần con
   người ở giữa."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Model Registry — Hệ thống quản lý vòng đời mô hình
- Candidate/Production/Archived — Ứng viên/Đang triển khai/Lưu trữ
- Promote — Phê duyệt đưa lên triển khai chính thức
- Auto-promotion — Tự động thăng cấp (KHÔNG có trong EduDSS)
- Human-in-the-loop — Con người tham gia trong vòng quyết định
