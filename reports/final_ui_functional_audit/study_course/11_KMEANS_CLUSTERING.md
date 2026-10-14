# Bài 11 — K-Means Clustering (Phân cụm)

## 1. Mục tiêu buổi học

Hiểu thuật toán K-Means từng bước lặp một, và đạt được mục tiêu quan trọng nhất của bài
này: **không bao giờ nhầm lẫn giữa "phân cụm" (clustering) và "dự đoán" (prediction)**.

## 2. Kiến thức cần nhớ trước

Bài 3 (feature).

## 3. Giải thích từ con số 0

Ở Bài 6 và Bài 8, ta có Classification/Regression — đây là **học có giám sát
(supervised learning)**: máy học từ các cặp (feature, target) đã biết trước target là
gì. Nhưng K-Means lại khác hoàn toàn: nó là **học không giám sát (unsupervised
learning)** — KHÔNG có target nào cả! K-Means chỉ nhìn vào các feature (ví dụ điểm số,
số giờ học, tỷ lệ điểm danh) và tự tìm ra các nhóm sinh viên "giống nhau" mà không ai nói
trước nhóm nào là gì hay nhóm đó có bao nhiêu người.

**Đây là điểm mấu chốt: K-Means KHÔNG dự đoán tương lai của bất kỳ ai. Nó chỉ nhóm những
người giống nhau lại với nhau, dựa trên hiện tại.**

## 4. Giải thích kỹ thuật — Thuật toán K-Means từng bước lặp

1. **Bước khởi tạo**: chọn ngẫu nhiên `k` điểm làm tâm cụm (centroid) ban đầu.
2. **Bước gán (assignment)**: với mỗi sinh viên, tính khoảng cách đến từng tâm cụm, gán
   sinh viên đó vào cụm có tâm gần nhất.
3. **Bước cập nhật (update)**: với mỗi cụm, tính lại tâm cụm mới = trung bình cộng của
   tất cả sinh viên hiện đang thuộc cụm đó.
4. **Lặp lại bước 2 và 3** cho đến khi các tâm cụm không còn thay đổi đáng kể (hội tụ —
   convergence), hoặc đạt số vòng lặp tối đa.

## 5. Ví dụ cực dễ hiểu — mô phỏng thủ công

Giả sử có 4 sinh viên với 1 feature duy nhất là "số giờ học/tuần": A=2, B=3, C=8, D=9.
Chọn k=2, khởi tạo tâm cụm ngẫu nhiên: `tâm1=2, tâm2=9`.
- **Vòng 1 — gán**: A(2) gần tâm1 hơn → cụm 1. B(3): |3-2|=1, |3-9|=6 → gần tâm1 → cụm 1.
  C(8): |8-2|=6, |8-9|=1 → gần tâm2 → cụm 2. D(9) → cụm 2.
- **Vòng 1 — cập nhật**: tâm1 mới = trung bình(A,B) = (2+3)/2 = 2.5. tâm2 mới =
  trung bình(C,D) = (8+9)/2 = 8.5.
- **Vòng 2 — gán lại**: không ai đổi cụm (A,B vẫn gần 2.5 hơn; C,D vẫn gần 8.5 hơn) →
  **hội tụ**, dừng lại.
Kết quả: Cụm 1 = {A,B} (học ít giờ hơn), Cụm 2 = {C,D} (học nhiều giờ hơn). Đây chỉ là
việc NHÓM, không hề có "dự đoán điểm số tương lai" nào xảy ra ở đây.

## 6. Ví dụ trực tiếp trong EduDSS

Trong `dss/services/clustering_service.py`, K-Means nhóm sinh viên theo nhiều feature
hành vi/học tập cùng lúc (không chỉ 1 feature như ví dụ trên). Kết quả phân cụm được
dùng để: (a) hiển thị biểu đồ phân bố cụm (chiếu về 2D bằng PCA để vẽ được), (b) tính
"kế hoạch can thiệp" (intervention plan) theo từng cụm — so sánh điểm mạnh/yếu của một
cụm với trung bình chung.

## 7. Luồng xử lý thực tế trong project

```
Dữ liệu (feature hành vi + học tập) → chuẩn hóa (Z-score, giống Bài 4)
  → chọn k bằng Elbow + Silhouette (Bài 12)
  → chạy K-Means → gán mỗi sinh viên vào 1 cụm
  → PCA chiếu dữ liệu nhiều chiều về 2D để vẽ biểu đồ scatter
  → tính đặc trưng nổi bật của mỗi cụm (so với trung bình toàn lớp)
  → Giảng viên xem cụm nào cần can thiệp ưu tiên (Recommendation, Bài 15)
```

## 8. Công thức nếu có

Hàm mục tiêu K-Means tối thiểu hóa (inertia): `Σ_k Σ_{x∈C_k} ||x - μ_k||²`

## 9. Giải thích từng ký hiệu trong công thức

- `k` — chỉ số của một cụm (từ 1 đến K tổng số cụm).
- `C_k` — tập hợp tất cả các điểm dữ liệu (sinh viên) thuộc cụm thứ k.
- `x` — một điểm dữ liệu (một sinh viên, biểu diễn bằng vector feature).
- `μ_k` — tâm (centroid) của cụm k, là trung bình cộng các điểm thuộc cụm đó.
- `||x - μ_k||²` — bình phương khoảng cách Euclid từ điểm x đến tâm cụm của nó.
- Toàn bộ công thức — tổng tất cả các khoảng cách bình phương này trên mọi cụm; K-Means
  cố gắng làm cho tổng này càng nhỏ càng tốt (các điểm càng gần tâm cụm của mình).

## 10. Cách đọc kết quả

Kết quả K-Means là **một nhãn cụm** (ví dụ "Cụm 1", "Cụm 2"...) cho mỗi sinh viên — đây
KHÔNG phải một dự đoán về tương lai hay rủi ro của sinh viên đó. Phải luôn kèm theo diễn
giải: "sinh viên này giống với nhóm X về đặc điểm hành vi/học tập hiện tại."

## 11. Vì sao project dùng phương pháp này

K-Means đơn giản, chạy nhanh, dễ diễn giải (mỗi cụm có tâm cụ thể để so sánh đặc trưng),
phù hợp để nhóm sinh viên theo hành vi học tập nhằm đề xuất can thiệp theo nhóm thay vì
xử lý từng cá nhân riêng lẻ.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm song song với Classification/Regression trong Chuỗi 1 — dùng chung dữ liệu đầu vào,
nhưng đi theo một nhánh riêng: Phân cụm → Intervention Plan (Bài 15) → gợi ý theo nhóm.

## 13. Input là gì

Dữ liệu feature hành vi/học tập của toàn bộ lớp (Giảng viên) — đã chuẩn hóa.

## 14. Output là gì

Nhãn cụm cho mỗi sinh viên, tâm cụm, và các đặc trưng nổi bật của từng cụm.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho Recommendation/Intervention Plan (Bài 15) để đề xuất hành động theo từng cụm.

## 16. Ưu điểm

Đơn giản, nhanh, dễ diễn giải, hữu ích để nhóm và ưu tiên can thiệp theo nhóm lớn.

## 17. Nhược điểm

Cần chọn trước số cụm k; nhạy cảm với vị trí khởi tạo tâm cụm ban đầu; giả định các cụm
có hình dạng gần tròn (không tốt với cụm có hình dạng phức tạp).

## 18. Limitation thực tế của project

Không có centroid nào được lưu trữ lâu dài (chỉ tính lại mỗi lần chạy); k có thể được
Giảng viên/Admin điều chỉnh thủ công, không hoàn toàn tự động; cấu hình phân cụm toàn
cục chỉ dành cho Giảng viên/Admin (Sinh viên chỉ xem được diễn giải của cụm mình).

## 19. Hội đồng có thể hỏi gì

"K-Means có dự đoán được sinh viên nào sẽ trượt môn không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. K-Means là học không giám sát — nó không có khái niệm 'target' hay 'nhãn đúng'
để dự đoán. Nó chỉ nhóm các sinh viên có đặc điểm hành vi/học tập hiện tại giống nhau lại
với nhau, dựa trên khoảng cách giữa các điểm dữ liệu. Việc dự đoán rủi ro trượt môn là
công việc của Classification (Bài 6) — một mô hình học có giám sát hoàn toàn khác."

## 21. Câu trả lời chi tiết

Trình bày thuật toán 4 bước ở mục 4, có thể vẽ lại ví dụ số ở mục 5 lên bảng nếu được yêu
cầu minh họa cụ thể, nhấn mạnh: không có bước nào trong 4 bước đó nhắc đến "target" hay
"nhãn đúng."

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy phân cụm có ích gì nếu nó không dự đoán được gì cả?"

## 23. Cách trả lời câu vặn

"Phân cụm rất có ích cho việc RA QUYẾT ĐỊNH ở cấp độ nhóm — thay vì Giảng viên phải xem
xét từng sinh viên một cách rời rạc, phân cụm giúp nhận diện các nhóm có đặc điểm chung
(ví dụ nhóm học ít giờ, điểm danh thấp) để thiết kế can thiệp phù hợp cho cả nhóm cùng
lúc, tiết kiệm thời gian và tài nguyên. Đây là giá trị ở khâu RA QUYẾT ĐỊNH, không phải ở
khâu DỰ ĐOÁN."

## 24. Những câu không được nói

- "K-Means dự đoán sinh viên nào sẽ rủi ro trong tương lai." (Sai — đó là Classification.)
- "K-Means có target để học." (Sai — đây là bản chất của unsupervised learning.)

## 25. 10 câu tự kiểm tra

1. K-Means là học có giám sát hay không giám sát?
2. 4 bước của thuật toán K-Means là gì?
3. Centroid là gì?
4. K-Means có cần biết target/nhãn đúng trước không?
5. Công thức hàm mục tiêu (inertia) của K-Means là gì?
6. `||x - μ_k||²` nghĩa là gì?
7. K-Means dùng để làm gì trong EduDSS (mục đích thực tế)?
8. Vì sao không thể gọi K-Means là "mô hình dự đoán"?
9. Kết quả phân cụm được chuyển tiếp cho module nào?
10. Nhược điểm lớn nhất của K-Means là gì?

## 26. Đáp án riêng

1. Không giám sát (unsupervised).
2. Khởi tạo tâm cụm → gán điểm vào cụm gần nhất → cập nhật lại tâm cụm → lặp lại đến khi
   hội tụ.
3. Tâm của một cụm, là trung bình cộng của tất cả các điểm thuộc cụm đó.
4. Không — đó chính là đặc điểm của học không giám sát.
5. `Σ_k Σ_{x∈C_k} ||x - μ_k||²`.
6. Bình phương khoảng cách Euclid từ điểm x đến tâm cụm của nó.
7. Nhóm sinh viên có đặc điểm hành vi/học tập giống nhau để đề xuất can thiệp theo nhóm.
8. Vì nó không học từ target/nhãn đúng nào, chỉ nhóm dựa trên độ tương đồng hiện tại.
9. Recommendation/Intervention Plan (Bài 15).
10. Cần chọn trước k, nhạy với khởi tạo ngẫu nhiên, giả định cụm hình gần tròn.

## 27. 5 CÂU PHẢI THUỘC

1. "K-Means là học không giám sát — không có target, không dự đoán tương lai."
2. "4 bước: khởi tạo tâm cụm, gán điểm, cập nhật tâm cụm, lặp đến khi hội tụ."
3. "K-Means tối thiểu hóa tổng bình phương khoảng cách từ mỗi điểm đến tâm cụm của nó."
4. "Phân cụm giúp Giảng viên can thiệp theo nhóm, không phải dự đoán rủi ro cá nhân."
5. "Dự đoán rủi ro là việc của Classification, phân cụm là việc của K-Means — hai việc
   hoàn toàn khác nhau."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Clustering — Phân cụm
- Unsupervised learning — Học không giám sát
- Centroid — Tâm cụm
- Convergence — Sự hội tụ
- Inertia — Tổng bình phương khoảng cách nội cụm
