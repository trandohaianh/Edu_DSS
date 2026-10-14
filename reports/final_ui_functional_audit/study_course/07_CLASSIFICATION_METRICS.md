# Bài 7 — Đọc hiểu chỉ số phân loại: Accuracy, Precision, Recall, F1

## 1. Mục tiêu buổi học

Hiểu TP/TN/FP/FN là gì, 4 chỉ số đánh giá phân loại, và đặc biệt hiểu sâu **vì sao False
Negative nguy hiểm hơn False Positive trong bài toán phát hiện sinh viên rủi ro**.

## 2. Kiến thức cần nhớ trước

Bài 6 (Classification).

## 3. Giải thích từ con số 0

Khi mô hình dự đoán một sinh viên "có rủi ro" hay "không có rủi ro", có 4 khả năng xảy ra
so với thực tế:
- **True Positive (TP)** — dự đoán "có rủi ro", thực tế đúng là "có rủi ro". Dự đoán ĐÚNG.
- **True Negative (TN)** — dự đoán "không rủi ro", thực tế đúng là "không rủi ro". Dự
  đoán ĐÚNG.
- **False Positive (FP)** — dự đoán "có rủi ro", nhưng thực tế "không rủi ro". Dự đoán
  SAI (báo động giả).
- **False Negative (FN)** — dự đoán "không rủi ro", nhưng thực tế "có rủi ro". Dự đoán
  SAI (**BỎ SÓT** — nguy hiểm nhất trong bài toán này).

## 4. Giải thích kỹ thuật

- **Accuracy (độ chính xác tổng thể)**: tỷ lệ dự đoán đúng trên tổng số dự đoán.
- **Precision (độ chuẩn xác)**: trong số các trường hợp mô hình dự đoán "có rủi ro", bao
  nhiêu phần trăm đúng thực sự.
- **Recall (độ bao phủ / độ nhạy)**: trong số các trường hợp thực sự "có rủi ro", mô hình
  phát hiện được bao nhiêu phần trăm.
- **F1**: trung bình điều hòa (harmonic mean) giữa Precision và Recall, cân bằng cả hai.

## 5. Ví dụ cực dễ hiểu

Giống như hệ thống báo cháy: nếu hệ thống **bỏ sót** một đám cháy thật (False Negative) —
hậu quả có thể là thảm họa. Nếu hệ thống **báo động giả** (False Positive) khi không có
cháy — phiền phức nhưng không nguy hiểm bằng. Với sinh viên rủi ro cũng vậy: bỏ sót một
sinh viên đang thực sự gặp khó khăn (không can thiệp kịp thời) nguy hiểm hơn nhiều so với
việc "báo động nhầm" một sinh viên bình thường (họ chỉ nhận thêm hỗ trợ không cần thiết).

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên xem bảng so sánh 4 thuật toán phân loại rủi ro (Bài 6), hệ thống hiển thị
cả 4 chỉ số cho từng thuật toán. Vì bài toán là phát hiện rủi ro, **Recall của lớp "rủi ro
cao" quan trọng ngang hoặc hơn Accuracy tổng thể** — một mô hình có Accuracy cao nhưng
Recall lớp rủi ro thấp có nghĩa là nó đang bỏ sót nhiều sinh viên cần giúp đỡ nhất.

## 7. Luồng xử lý thực tế trong project

```
Mô hình dự đoán trên tập test → so sánh với nhãn thật
  → tính ma trận nhầm lẫn (confusion matrix): TP, TN, FP, FN cho từng lớp
  → tính Accuracy, Precision, Recall, F1 (trung bình weighted/macro tùy cấu hình)
  → hiển thị bảng so sánh 4 thuật toán cho Giảng viên
```

## 8. Công thức nếu có

```
Accuracy  = (TP + TN) / (TP + TN + FP + FN)
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * (Precision * Recall) / (Precision + Recall)
```

## 9. Giải thích từng ký hiệu trong công thức

- `TP` — số dự đoán đúng "có rủi ro".
- `TN` — số dự đoán đúng "không rủi ro".
- `FP` — số báo động giả (dự đoán "có rủi ro" nhưng thực tế không).
- `FN` — số bỏ sót (dự đoán "không rủi ro" nhưng thực tế có) — **con số cần theo dõi sát
  nhất trong bài toán này**.
- Mẫu số của Precision (`TP+FP`) — tổng số lần mô hình "báo có rủi ro".
- Mẫu số của Recall (`TP+FN`) — tổng số trường hợp "có rủi ro" thực sự tồn tại.

## 10. Cách đọc kết quả

Nếu Accuracy cao nhưng Recall của lớp rủi ro thấp — đây là dấu hiệu **cảnh báo**, không
phải kết quả tốt, vì mô hình "lười" đoán an toàn về phía đa số (lớp không rủi ro) để đạt
Accuracy cao giả tạo. Luôn ưu tiên nhìn Recall của lớp thiểu số/rủi ro trước Accuracy
tổng.

## 11. Vì sao project dùng phương pháp này

Đây là bộ 4 chỉ số tiêu chuẩn trong ngành cho bài toán phân loại, đủ để đánh giá toàn
diện cả độ chính xác tổng thể lẫn khả năng phát hiện đúng lớp quan trọng (rủi ro).

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là bước đánh giá ngay sau khi huấn luyện Classification (Bài 6), quyết định mô hình nào
được chọn làm candidate tốt nhất để đưa vào Model Registry (Bài 22).

## 13. Input là gì

Nhãn dự đoán của mô hình trên tập test, và nhãn thật tương ứng.

## 14. Output là gì

4 con số (Accuracy, Precision, Recall, F1) cho mỗi thuật toán, mỗi lớp.

## 15. Output được chuyển cho module nào tiếp theo

Dùng để so sánh và chọn mô hình candidate tốt nhất (Bài 10, Bài 22).

## 16. Ưu điểm

Dễ tính, dễ hiểu, là chuẩn công nghiệp, cho phép so sánh khách quan giữa các thuật toán.

## 17. Nhược điểm

Accuracy có thể gây hiểu lầm khi lớp mất cân bằng (một mô hình "ngu" luôn đoán lớp đông
vẫn có Accuracy cao); cần luôn xem cùng với Precision/Recall/F1 theo từng lớp.

## 18. Limitation thực tế của project

Các chỉ số này được tính trên tập test của dữ liệu TỔNG HỢP (Bài 3) — chưa được kiểm
chứng độ tin cậy trên dữ liệu sinh viên thật.

## 19. Hội đồng có thể hỏi gì

"Vì sao False Negative lại nguy hiểm hơn False Positive trong bài toán này?"

## 20. Câu trả lời ngắn 20–40 giây

"Vì False Negative nghĩa là hệ thống bỏ sót một sinh viên đang thực sự gặp rủi ro học
tập — sinh viên đó sẽ không được can thiệp kịp thời, có thể dẫn đến hậu quả nghiêm trọng
như trượt môn hoặc bỏ học. Trong khi đó False Positive chỉ khiến một sinh viên bình
thường nhận thêm sự quan tâm không cần thiết — tốn nguồn lực nhưng không gây hại. Vì vậy
trong bài toán phát hiện rủi ro, em ưu tiên theo dõi Recall của lớp rủi ro hơn là chỉ
nhìn Accuracy tổng."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ 4 công thức ở mục 8-9, đưa ví dụ báo cháy ở mục 5, và nhấn mạnh cách đọc
kết quả ở mục 10 (Accuracy cao + Recall thấp là dấu hiệu xấu).

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy tại sao không tối ưu hoàn toàn theo Recall, chấp nhận Precision thấp?"

## 23. Cách trả lời câu vặn

"Nếu chỉ tối ưu Recall tuyệt đối, mô hình có thể đoán 'mọi sinh viên đều rủi ro' để không
bỏ sót ai — Recall sẽ là 100% nhưng Precision cực thấp, gây quá tải cho hệ thống can
thiệp thực tế (giảng viên phải xử lý quá nhiều cảnh báo giả). Vì vậy F1 — cân bằng cả hai
— là chỉ số tổng hợp quan trọng, nhưng trong ngữ cảnh cụ thể của rủi ro học tập, em vẫn
ưu tiên xem xét Recall trước khi tối ưu F1 tổng thể, đặc biệt với lớp rủi ro cao."

## 24. Những câu không được nói

- "Accuracy là chỉ số quan trọng nhất." (Sai trong ngữ cảnh mất cân bằng lớp.)
- "Recall 100% là mục tiêu tối ưu duy nhất." (Sai — sẽ làm Precision sụp đổ.)

## 25. 10 câu tự kiểm tra

1. TP, TN, FP, FN là viết tắt của gì?
2. False Negative trong bài toán này có nghĩa là gì?
3. Công thức tính Accuracy?
4. Công thức tính Precision?
5. Công thức tính Recall?
6. Công thức tính F1?
7. Vì sao Accuracy có thể gây hiểu lầm với dữ liệu mất cân bằng?
8. Vì sao False Negative nguy hiểm hơn False Positive trong bài toán phát hiện rủi ro?
9. F1 cân bằng giữa hai chỉ số nào?
10. Nếu Accuracy cao nhưng Recall lớp rủi ro thấp, nên kết luận gì?

## 26. Đáp án riêng

1. True Positive, True Negative, False Positive, False Negative.
2. Mô hình dự đoán "không rủi ro" nhưng thực tế sinh viên đó có rủi ro — bị bỏ sót.
3. `(TP+TN)/(TP+TN+FP+FN)`.
4. `TP/(TP+FP)`.
5. `TP/(TP+FN)`.
6. `2*(Precision*Recall)/(Precision+Recall)`.
7. Vì mô hình có thể đạt Accuracy cao chỉ bằng cách luôn đoán lớp đông, bỏ qua lớp thiểu
   số.
8. Vì bỏ sót một sinh viên rủi ro thật có thể dẫn đến hậu quả nghiêm trọng không được can
   thiệp kịp thời.
9. Precision và Recall.
10. Mô hình đang bỏ sót nhiều sinh viên rủi ro thật — đây là dấu hiệu xấu, cần cải thiện.

## 27. 5 CÂU PHẢI THUỘC

1. "TP/TN đúng, FP là báo động giả, FN là bỏ sót — FN nguy hiểm nhất trong bài toán rủi
   ro học tập."
2. "Accuracy = (TP+TN)/tổng; Precision = TP/(TP+FP); Recall = TP/(TP+FN); F1 = trung bình
   điều hòa của Precision và Recall."
3. "Accuracy cao không đủ khi dữ liệu mất cân bằng — phải xem Recall của lớp rủi ro."
4. "Luôn ưu tiên theo dõi False Negative trong bài toán phát hiện rủi ro học tập."
5. "F1 cân bằng Precision và Recall, tránh việc tối ưu một chiều."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- True/False Positive/Negative — Dương/Âm tính thật/giả
- Accuracy — Độ chính xác tổng thể
- Precision — Độ chuẩn xác
- Recall — Độ bao phủ/độ nhạy
- F1-score — Điểm F1 (trung bình điều hòa)
