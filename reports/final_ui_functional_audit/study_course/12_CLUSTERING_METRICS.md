# Bài 12 — Đánh giá chất lượng phân cụm: Elbow, Silhouette, Davies-Bouldin

## 1. Mục tiêu buổi học

Hiểu làm sao biết được "chọn số cụm k như vậy có hợp lý không" khi không có nhãn đúng để
so sánh (khác hoàn toàn cách đánh giá Classification/Regression).

## 2. Kiến thức cần nhớ trước

Bài 11 (K-Means).

## 3. Giải thích từ con số 0

Ở Classification/Regression, ta biết "đáp án đúng" (target) nên có thể tính Accuracy hay
R² bằng cách so sánh dự đoán với đáp án thật. Nhưng phân cụm thì KHÔNG có đáp án đúng —
không ai nói trước "sinh viên A phải thuộc cụm nào." Vậy làm sao biết phân cụm "tốt" hay
"tệ", và chọn k (số cụm) bao nhiêu là hợp lý? Ta phải dùng các chỉ số đánh giá dựa trên
cấu trúc hình học của chính dữ liệu — gọi là **đánh giá nội tại (internal validation)**.

## 4. Giải thích kỹ thuật

- **Elbow method (phương pháp khuỷu tay)**: vẽ đồ thị giá trị inertia (Bài 11) theo từng
  giá trị k thử nghiệm (k=2,3,4,5...). Khi k tăng, inertia luôn giảm — nhưng đến một điểm
  nào đó, mức giảm chậm lại rõ rệt, tạo hình giống "khuỷu tay" trên đồ thị. Điểm đó là k
  hợp lý — sau nó, thêm cụm không còn giúp ích nhiều.
- **Silhouette score (điểm silhouette)**: đo cho mỗi điểm dữ liệu mức độ nó "phù hợp"
  với cụm của mình so với cụm gần nhất khác. Giá trị từ -1 đến 1, càng gần 1 càng tốt
  (điểm nằm sát cụm mình, xa cụm khác).
- **Davies-Bouldin index**: đo mức độ "chồng lấn" giữa các cụm — giá trị càng THẤP càng
  tốt (khác với Silhouette là càng cao càng tốt).

## 5. Ví dụ cực dễ hiểu

Elbow giống như đổ nước vào ly: mỗi lần thêm một cục đá (thêm 1 cụm), mực nước giảm dần
(inertia giảm) vì đá chiếm ít thể tích hơn nước lỏng đọng quanh các viên đá lớn — nhưng
đến một lúc đá đã đủ nhỏ và đủ nhiều, thêm nữa cũng không thay đổi gì đáng kể. Silhouette
giống như hỏi từng người trong một nhóm bạn: "bạn có thấy mình hợp với nhóm này hơn nhóm
bên cạnh không?" — nếu đa số trả lời "có, rất hợp", silhouette cao.

## 6. Ví dụ trực tiếp trong EduDSS

Trong tab Phân cụm, Giảng viên/Admin thấy đồ thị Elbow (trục ngang là k, trục dọc là
inertia) và một con số Silhouette hiển thị kèm theo kết quả phân cụm hiện tại, giúp đánh
giá "phân cụm này có ý nghĩa không" trước khi dùng để ra quyết định can thiệp.

## 7. Luồng xử lý thực tế trong project

```
Với mỗi giá trị k thử nghiệm (ví dụ 2 đến 8):
  → chạy K-Means → tính inertia (cho đồ thị Elbow) và Silhouette score
→ hiển thị đồ thị Elbow + bảng Silhouette cho từng k
→ Giảng viên/Admin chọn k cuối cùng (có gợi ý nhưng vẫn có thể điều chỉnh thủ công)
→ chạy K-Means chính thức với k đã chọn
```

## 8. Công thức nếu có

```
Silhouette: s(i) = (b(i) - a(i)) / max(a(i), b(i))
Davies-Bouldin: DB = (1/k) * Σ_i max_{j≠i} ((σ_i + σ_j) / d(c_i, c_j))
```

## 9. Giải thích từng ký hiệu trong công thức

- `a(i)` — khoảng cách trung bình từ điểm i đến các điểm khác TRONG CÙNG cụm với nó
  (càng nhỏ càng tốt — nghĩa là điểm i "gần gũi" với cụm của mình).
- `b(i)` — khoảng cách trung bình từ điểm i đến các điểm của cụm GẦN NHẤT khác (càng lớn
  càng tốt — nghĩa là điểm i "cách xa" cụm khác).
- `s(i)` — điểm silhouette của điểm i, từ -1 (sai cụm) đến 1 (rất đúng cụm).
- `σ_i`, `σ_j` — độ phân tán trung bình (average distance to centroid) của cụm i và cụm j.
- `d(c_i, c_j)` — khoảng cách giữa tâm cụm i và tâm cụm j.
- `DB` — trung bình của "tỷ lệ tệ nhất" giữa mỗi cụm với cụm gần nó nhất; giá trị thấp
  nghĩa là các cụm tách biệt tốt, không chồng lấn.

## 10. Cách đọc kết quả

Silhouette gần 1 → phân cụm tốt, các nhóm tách biệt rõ ràng. Silhouette gần 0 → các cụm
chồng lấn, ranh giới không rõ. Silhouette âm → nhiều điểm bị gán sai cụm. Davies-Bouldin
thấp → cụm tách biệt tốt; cao → cụm chồng lấn nhiều.

## 11. Vì sao project dùng phương pháp này

Vì không có nhãn đúng để so sánh (bản chất unsupervised — Bài 11), phải dùng đánh giá nội
tại dựa trên cấu trúc hình học dữ liệu — đây là cách tiêu chuẩn duy nhất khả thi cho bài
toán phân cụm.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là bước hỗ trợ ngay trước và sau khi chạy K-Means (Bài 11) — giúp chọn k và đánh giá chất
lượng phân cụm trước khi dùng cho Recommendation (Bài 15).

## 13. Input là gì

Kết quả phân cụm (nhãn cụm cho mỗi điểm) ứng với từng giá trị k thử nghiệm.

## 14. Output là gì

Đồ thị Elbow, điểm Silhouette, (và có thể) chỉ số Davies-Bouldin cho mỗi k.

## 15. Output được chuyển cho module nào tiếp theo

Dùng để Giảng viên/Admin chọn k cuối cùng, sau đó phân cụm chính thức chạy và chuyển kết
quả sang Recommendation (Bài 15).

## 16. Ưu điểm

Cho phép đánh giá khách quan chất lượng phân cụm ngay cả khi không có nhãn đúng.

## 17. Nhược điểm

Elbow đôi khi không có "khuỷu tay" rõ ràng (đường cong mượt dần đều), khiến việc chọn k
vẫn mang tính chủ quan; Silhouette tính toán tốn chi phí hơn với dữ liệu lớn.

## 18. Limitation thực tế của project

Việc chọn k cuối cùng vẫn có thể do Giảng viên/Admin điều chỉnh thủ công — không phải
hoàn toàn tự động hóa theo chỉ số; đây là thiết kế có chủ đích để con người vẫn có quyền
quyết định cuối cùng.

## 19. Hội đồng có thể hỏi gì

"Làm sao bạn biết số cụm k đã chọn là hợp lý, khi không có đáp án đúng để so sánh?"

## 20. Câu trả lời ngắn 20–40 giây

"Em dùng hai công cụ bổ trợ: phương pháp Elbow — nhìn vào đồ thị inertia giảm theo k để
tìm điểm 'khuỷu tay' nơi việc thêm cụm không còn giúp ích nhiều; và điểm Silhouette — đo
mức độ mỗi sinh viên phù hợp với cụm của mình so với cụm gần nhất khác, giá trị càng gần
1 càng tốt. Kết hợp cả hai giúp chọn k hợp lý mà không cần có nhãn đúng, vì bản chất phân
cụm là học không giám sát."

## 21. Câu trả lời chi tiết

Trình bày công thức Silhouette ở mục 8-9, giải thích a(i) và b(i) cụ thể, và nhấn mạnh sự
khác biệt Silhouette (càng cao càng tốt) với Davies-Bouldin (càng thấp càng tốt) nếu được
hỏi cả hai.

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu Elbow và Silhouette đưa ra hai gợi ý k khác nhau thì sao?"

## 23. Cách trả lời câu vặn

"Trong trường hợp đó, em ưu tiên xem xét thêm ý nghĩa thực tiễn của các cụm — ví dụ liệu
các cụm có tạo ra nhóm can thiệp có ý nghĩa cho Giảng viên hay không — chứ không chỉ dựa
thuần túy vào con số toán học. Đây là lý do thiết kế cho phép Giảng viên/Admin điều chỉnh
k thủ công thay vì tự động hóa hoàn toàn theo một chỉ số duy nhất."

## 24. Những câu không được nói

- "Silhouette cao tuyệt đối chứng minh phân cụm này phản ánh đúng nhóm rủi ro thực tế."
  (Sai — Silhouette chỉ đo chất lượng hình học, không liên quan đến rủi ro học tập.)

## 25. 10 câu tự kiểm tra

1. Vì sao không thể dùng Accuracy để đánh giá phân cụm?
2. Elbow method dựa trên chỉ số nào?
3. Silhouette score có khoảng giá trị nào?
4. Công thức Silhouette là gì?
5. a(i) và b(i) trong công thức Silhouette nghĩa là gì?
6. Davies-Bouldin càng cao hay càng thấp là tốt?
7. Nếu Silhouette gần 0 nghĩa là gì?
8. Ai là người quyết định k cuối cùng trong EduDSS?
9. Elbow method có luôn cho ra điểm khuỷu tay rõ ràng không?
10. Kết quả đánh giá phân cụm được dùng để làm gì tiếp theo?

## 26. Đáp án riêng

1. Vì phân cụm không có nhãn đúng (target) để so sánh — đây là bài toán không giám sát.
2. Inertia (tổng bình phương khoảng cách nội cụm) theo từng giá trị k.
3. Từ -1 đến 1.
4. `s(i) = (b(i)-a(i)) / max(a(i),b(i))`.
5. a(i) là khoảng cách trung bình đến các điểm cùng cụm; b(i) là khoảng cách trung bình
   đến cụm gần nhất khác.
6. Càng thấp càng tốt.
7. Các cụm chồng lấn, ranh giới không rõ ràng.
8. Giảng viên/Admin, dựa trên gợi ý từ Elbow/Silhouette.
9. Không — đôi khi đường cong mượt, không có khuỷu tay rõ.
10. Dùng để chọn k phân cụm chính thức, sau đó chuyển sang Recommendation/Intervention
    Plan (Bài 15).

## 27. 5 CÂU PHẢI THUỘC

1. "Phân cụm không có nhãn đúng nên phải dùng đánh giá nội tại: Elbow và Silhouette."
2. "Silhouette càng gần 1 càng tốt; Davies-Bouldin càng thấp càng tốt."
3. "a(i) đo độ gần với cụm mình, b(i) đo độ xa với cụm gần nhất khác."
4. "Chọn k cuối cùng vẫn có thể do con người (Giảng viên/Admin) điều chỉnh, không hoàn
   toàn tự động."
5. "Silhouette đo chất lượng hình học của phân cụm, không đo mức độ rủi ro học tập thực
   tế."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Internal validation — Đánh giá nội tại
- Elbow method — Phương pháp khuỷu tay
- Silhouette score — Điểm silhouette
- Davies-Bouldin index — Chỉ số Davies-Bouldin
- Cluster separation — Độ tách biệt giữa các cụm
