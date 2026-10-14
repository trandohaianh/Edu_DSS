# Bài 20 — Career Advisor: Career Fit vs Career Readiness

## 1. Mục tiêu buổi học

Hiểu rõ Career Fit và Career Readiness là hai điểm số HEURISTIC khác nhau, và khắc sâu:
**một con số phần trăm từ công thức heuristic không tự động là một xác suất thống kê.**

## 2. Kiến thức cần nhớ trước

Không cần kiến thức ML trước — đây là bài về công thức tính điểm có trọng số
(weighted scoring), khác hoàn toàn Classification/Regression.

## 3. Giải thích từ con số 0

Khi tư vấn nghề nghiệp cho một sinh viên, có hai câu hỏi khác nhau cần trả lời:
- **"Nghề này có PHÙ HỢP với bạn không?"** (Career Fit — Độ phù hợp nghề nghiệp) — dựa
  trên sở thích, kỹ năng, phong cách làm việc của sinh viên so với đặc điểm của nghề đó.
- **"Bạn đã SẴN SÀNG cho nghề này chưa?"** (Career Readiness — Độ sẵn sàng nghề nghiệp)
  — dựa trên kiến thức, kinh nghiệm, kỹ năng thực tế hiện có so với yêu cầu của nghề.

Hai câu hỏi này ĐỘC LẬP với nhau: một người có thể rất PHÙ HỢP với nghề bác sĩ (thích
giúp đỡ người khác, tỉ mỉ) nhưng CHƯA SẴN SÀNG (chưa học xong y khoa).

## 4. Giải thích kỹ thuật

Cả hai điểm số được tính bằng **công thức heuristic có trọng số (weighted heuristic
scoring)** trong `dss/services/career_scoring.py` — KHÔNG phải machine learning:
- **Career Fit** — tính từ 6 chiều: sở thích (interests), kỹ năng (skills), phong cách
  làm việc (work style), giá trị cá nhân, môi trường ưa thích, và các ràng buộc cá nhân
  (constraints).
- **Career Readiness** — tính từ 6 chiều KHÁC: kiến thức chuyên môn, kinh nghiệm thực
  tế, kỹ năng mềm, chứng chỉ/bằng cấp, mức độ chuẩn bị hồ sơ, và khoảng cách kỹ năng còn
  thiếu (skill gap).

Mỗi chiều được gán một trọng số, tổng hợp lại thành một điểm số phần trăm — nhưng đây là
**tổng có trọng số của các đánh giá chủ quan/kinh nghiệm được mã hóa thành luật**, KHÔNG
phải một xác suất được ước lượng từ dữ liệu thống kê thực tế (như xác suất trong mô hình
Logistic Regression ở Bài 6, vốn được HUẤN LUYỆN từ dữ liệu).

## 5. Ví dụ cực dễ hiểu

Giống như một bài trắc nghiệm tính cách trên tạp chí: "Trả lời 10 câu hỏi, cộng điểm theo
trọng số, ra kết quả 'Bạn hợp với nghề X 78%'" — con số 78% này là kết quả của MỘT CÔNG
THỨC CỘNG ĐIỂM, không phải "78% xác suất bạn sẽ thành công trong nghề X" theo nghĩa thống
kê nghiêm ngặt.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Sinh viên vào tab "Tư vấn hướng nghiệp" và điều chỉnh thanh trượt (slider) về sở
thích/kỹ năng, điểm Career Fit và Career Readiness thay đổi NGAY LẬP TỨC và có thể kiểm
chứng — đã được xác nhận qua truy vết tính toán sâu (deep trace) trước đó: cả 6 chiều
Fit và 6 chiều Readiness đều thực sự ảnh hưởng đến kết quả tính toán, không phải giao
diện "giả" không có tác dụng thật.

## 7. Luồng xử lý thực tế trong project

```
Sinh viên nhập/điều chỉnh: sở thích, kỹ năng, kinh nghiệm, phong cách làm việc...
  → career_scoring.py tính 6 chiều Fit (có trọng số) → tổng hợp thành điểm Career Fit
  → career_scoring.py tính 6 chiều Readiness (khác, có trọng số) → tổng hợp thành điểm
    Career Readiness
  → tính Skill Gap (khoảng cách kỹ năng còn thiếu) → gợi ý lộ trình (roadmap)
  → hỗ trợ "what-if" (giả định): sinh viên thử thay đổi input để xem điểm số thay đổi ra
    sao, hỗ trợ khám phá các lựa chọn nghề nghiệp khác nhau
```

## 8. Công thức nếu có

```
Career Fit / Readiness = Σ (trọng số_i × điểm_thành_phần_i), i = 1..6
```

## 9. Giải thích từng ký hiệu trong công thức

- `điểm_thành_phần_i` — điểm số của một trong 6 chiều (ví dụ điểm sở thích, điểm kỹ
  năng), thường được chuẩn hóa về cùng thang đo (ví dụ 0-100).
- `trọng số_i` — mức độ quan trọng được gán cho chiều đó trong công thức tổng hợp, do
  người thiết kế hệ thống quyết định dựa trên kinh nghiệm/tài liệu tham khảo về tư vấn
  nghề nghiệp, KHÔNG học từ dữ liệu.
- Tổng `Σ` — cộng có trọng số của cả 6 chiều, cho ra điểm số cuối cùng.
- **Lưu ý quan trọng**: đây KHÔNG phải công thức Bayes hay bất kỳ công thức xác suất
  thống kê nào — nó là một phép cộng có trọng số thuần túy.

## 10. Cách đọc kết quả

Đọc điểm số Career Fit/Readiness là "một chỉ số tổng hợp phản ánh mức độ khớp theo các
tiêu chí đã định nghĩa trước" — KHÔNG đọc là "xác suất thành công trong nghề nghiệp đó."

## 11. Vì sao project dùng phương pháp này

Heuristic scoring cho phép minh bạch hoàn toàn (người dùng có thể thấy chính xác chiều
nào đóng góp bao nhiêu), dễ điều chỉnh trọng số theo phản hồi thực tế, và không cần dữ
liệu lịch sử lớn về "nghề nghiệp thành công" để huấn luyện — điều mà một mô hình ML thật
sự cần nhưng EduDSS không có.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là một nhánh riêng biệt của AI Advisor dành cho Sinh viên, dùng LLM Gateway (Bài 18) để
diễn giải kết quả bằng ngôn ngữ tự nhiên, tương tự cách Learning Plan (Bài 15) dùng LLM
chỉ để diễn đạt chứ không quyết định điểm số.

## 13. Input là gì

Thông tin sở thích, kỹ năng, kinh nghiệm, phong cách làm việc, ràng buộc cá nhân của Sinh
viên (StudentCareerProfile).

## 14. Output là gì

Điểm Career Fit, điểm Career Readiness, Skill Gap, lộ trình gợi ý (roadmap).

## 15. Output được chuyển cho module nào tiếp theo

Kết quả được LLM Gateway (Bài 18) diễn giải thành lời tư vấn, hiển thị cho Sinh viên.

## 16. Ưu điểm

Minh bạch, phản hồi tức thì (real-time recompute khi thay đổi input), không cần dữ liệu
huấn luyện lớn.

## 17. Nhược điểm

Trọng số là do con người thiết kế, mang tính chủ quan; không được kiểm định thống kê như
một mô hình được huấn luyện từ dữ liệu thực tế.

## 18. Limitation thực tế của project

Ở chế độ `REAL_LMS`, phần dữ liệu làm giàu (enrichment) từ LMS/CMS cho Career Advisor vẫn
là dữ liệu demo (chưa có kết nối LMS thật, xem Bài 21) — trong `REAL_LMS`, tính năng này
hiển thị trạng thái không khả dụng một cách trung thực thay vì dùng dữ liệu demo.

## 19. Hội đồng có thể hỏi gì

"Điểm Career Fit 85% nghĩa là sinh viên có 85% xác suất thành công trong nghề đó phải
không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. 85% ở đây là kết quả của một công thức cộng điểm có trọng số trên 6 chiều đánh
giá (sở thích, kỹ năng, phong cách làm việc...), phản ánh mức độ khớp theo các tiêu chí
đã định nghĩa — không phải một xác suất thống kê được ước lượng từ dữ liệu lịch sử về
kết quả nghề nghiệp thực tế. Em gọi đây là một chỉ số heuristic (dựa trên kinh nghiệm),
không phải một xác suất theo nghĩa thống kê."

## 21. Câu trả lời chi tiết

Trình bày công thức ở mục 8-9, phân biệt rõ 6 chiều của Fit và 6 chiều KHÁC của
Readiness, và nhấn mạnh sự khác biệt với xác suất được HUẤN LUYỆN từ dữ liệu như trong
Logistic Regression (Bài 6).

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy trọng số của từng chiều được xác định như thế nào? Có cơ sở khoa học không?"

## 23. Cách trả lời câu vặn

"Trọng số được thiết kế dựa trên các nguyên tắc phổ biến trong tài liệu tư vấn hướng
nghiệp (career counseling), không phải học từ dữ liệu thống kê thực tế của EduDSS. Đây là
một giới hạn thực tế em công khai — nếu có dữ liệu thực tế đủ lớn về kết quả nghề nghiệp
của sinh viên theo thời gian, một hướng phát triển tương lai là hiệu chỉnh (calibrate)
lại các trọng số này bằng phương pháp thống kê thay vì gán thủ công."

## 24. Những câu không được nói

- "Career Fit là xác suất thành công trong nghề nghiệp."
- "Career Fit và Career Readiness là cùng một chỉ số." (Sai — 2 bộ 6 chiều khác nhau.)

## 25. 10 câu tự kiểm tra

1. Career Fit đo cái gì?
2. Career Readiness đo cái gì?
3. Career Fit và Career Readiness có dùng chung một bộ chiều đánh giá không?
4. Công thức tổng quát để tính các điểm số này là gì?
5. Vì sao điểm số này không được gọi là xác suất?
6. Trọng số trong công thức được xác định dựa trên đâu?
7. Điều gì xảy ra với Career Advisor trong chế độ REAL_LMS?
8. Skill Gap là gì?
9. "What-if" trong Career Advisor nghĩa là gì?
10. Output của Career Advisor được chuyển tiếp qua module nào để diễn giải?

## 26. Đáp án riêng

1. Mức độ phù hợp giữa sinh viên và một nghề nghiệp cụ thể.
2. Mức độ sẵn sàng thực tế (kiến thức, kinh nghiệm) của sinh viên cho nghề đó.
3. Không — mỗi cái có 6 chiều riêng biệt, khác nhau.
4. `Σ (trọng số_i × điểm_thành_phần_i)`, i chạy từ 1 đến 6.
5. Vì đây là tổng có trọng số theo luật thiết kế sẵn, không phải xác suất ước lượng từ dữ
   liệu thống kê thực tế.
6. Các nguyên tắc phổ biến trong tài liệu tư vấn hướng nghiệp, do người thiết kế quyết
   định.
7. Hiển thị trạng thái không khả dụng trung thực vì dữ liệu làm giàu từ LMS/CMS thật
   chưa tồn tại.
8. Khoảng cách giữa kỹ năng hiện có và kỹ năng yêu cầu của nghề nghiệp mục tiêu.
9. Cho phép sinh viên thử thay đổi input để xem điểm số thay đổi ra sao, khám phá lựa
   chọn khác.
10. LLM Gateway (Bài 18), để diễn giải bằng ngôn ngữ tự nhiên.

## 27. 5 CÂU PHẢI THUỘC

1. "Career Fit và Career Readiness là hai điểm số heuristic riêng biệt, mỗi cái có 6
   chiều đánh giá khác nhau."
2. "Đây là công thức cộng điểm có trọng số, KHÔNG PHẢI xác suất thống kê."
3. "Tất cả input (6+6 chiều) đều thực sự ảnh hưởng đến kết quả, đã được xác minh qua
   truy vết tính toán."
4. "Trọng số do con người thiết kế dựa trên tài liệu tư vấn hướng nghiệp, không học từ dữ
   liệu."
5. "Trong REAL_LMS, Career Advisor hiển thị trạng thái không khả dụng trung thực thay vì
   dùng dữ liệu demo."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Career Fit — Độ phù hợp nghề nghiệp
- Career Readiness — Độ sẵn sàng nghề nghiệp
- Weighted heuristic scoring — Chấm điểm heuristic có trọng số
- Skill Gap — Khoảng cách kỹ năng
- Probability (KHÔNG áp dụng ở đây) — Xác suất thống kê
