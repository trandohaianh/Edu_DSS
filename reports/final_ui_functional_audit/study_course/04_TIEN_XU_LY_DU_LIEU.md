# Bài 4 — Tiền xử lý dữ liệu (Data Preprocessing)

## 1. Mục tiêu buổi học

Hiểu 4 kỹ thuật tiền xử lý chính (Imputer, Scaler, Encoder, SMOTE) — chúng làm gì, tại
sao cần, và quan trọng nhất: **thứ tự chúng chạy so với việc chia train/test**, vì đây
là nền cho Bài 5 (Data Leakage).

## 2. Kiến thức cần nhớ trước

Bài 3 (feature, target).

## 3. Giải thích từ con số 0

Dữ liệu thô (raw data) thường có 3 vấn đề: (1) thiếu giá trị (missing values) — ví dụ
một sinh viên không có dữ liệu `so_gio_hoc_tuan`; (2) các cột có thang đo khác nhau — điểm
số từ 0-10 nhưng số lần đăng nhập có thể lên tới hàng trăm; (3) lớp mất cân bằng
(imbalanced class) — ví dụ số sinh viên "rủi ro cao" ít hơn nhiều so với "bình thường".
Tiền xử lý (preprocessing) là bước "dọn dẹp" dữ liệu trước khi đưa vào mô hình.

## 4. Giải thích kỹ thuật

- **KNNImputer** (điền giá trị thiếu bằng K láng giềng gần nhất): với một giá trị bị
  thiếu, tìm k dòng dữ liệu "giống" nhất (dựa trên các cột khác đã có), lấy trung bình
  giá trị của họ để điền vào.
- **StandardScaler** (chuẩn hóa Z-score): đưa mỗi cột về cùng thang đo bằng công thức
  `z = (x - mean) / std`, giúp các thuật toán nhạy với thang đo (như Logistic Regression)
  hoạt động ổn định.
- **OneHotEncoder**: chuyển cột phân loại (categorical, ví dụ "Khoa CNTT"/"Khoa Kinh tế")
  thành các cột nhị phân 0/1 để mô hình hiểu được (mô hình chỉ hiểu số).
- **SMOTE** (Synthetic Minority Over-sampling Technique — Kỹ thuật sinh mẫu tổng hợp cho
  lớp thiểu số): sinh thêm các điểm dữ liệu giả cho lớp ít dữ liệu hơn (ví dụ lớp "rủi ro
  cao"), giúp mô hình không bị thiên vị về lớp đông hơn.

## 5. Ví dụ cực dễ hiểu

Giống như trước khi nấu ăn, bạn phải rửa rau (loại bỏ giá trị thiếu), cắt tất cả nguyên
liệu về cùng kích thước (chuẩn hóa thang đo), và nếu công thức cần nhiều cà chua hơn
những gì bạn có, bạn có thể "nhân bản" thêm vài quả tương tự (SMOTE) để đủ nguyên liệu
nấu — nhưng chỉ nên làm việc này SAU KHI bạn đã tách riêng phần nguyên liệu dùng để nấu
thử (train) và phần dùng để một người khác nếm thử đánh giá (test), nếu không "người nếm
thử" đã biết trước công thức.

## 6. Ví dụ trực tiếp trong EduDSS

Trong `dss/core/trainers.py::ClassificationTrainer`, các bước KNNImputer → StandardScaler
→ OneHotEncoder → SMOTE được gói chung trong một `ImbPipeline` (pipeline hỗ trợ
imbalanced-learn), và pipeline này chỉ được "fit" (học tham số) bên trong từng fold huấn
luyện của `GridSearchCV` — không bao giờ fit trên toàn bộ dữ liệu trước khi chia.

## 7. Luồng xử lý thực tế trong project

```
Dữ liệu thô → filter_leakage_features() (loại cột tương quan target quá cao)
  → train_test_split() (CHIA TRƯỚC)
  → [chỉ trên phần train] Pipeline(KNNImputer → StandardScaler → OneHotEncoder → SMOTE)
    được fit bên trong từng fold của GridSearchCV
  → mô hình được huấn luyện trên dữ liệu đã tiền xử lý
  → đánh giá trên phần test (đã qua transform bằng tham số học từ train, không fit lại)
```

## 8. Công thức nếu có

Z-score: `z = (x - mean) / std`

SMOTE (sinh 1 điểm mới): `x_new = x_i + λ * (x_zi - x_i)`, `λ ~ Uniform(0,1)`

## 9. Giải thích từng ký hiệu trong công thức

- `x` — giá trị gốc của một feature.
- `mean`, `std` — trung bình và độ lệch chuẩn của feature đó, **chỉ tính trên tập train**.
- `x_i` — một điểm dữ liệu thuộc lớp thiểu số.
- `x_zi` — một trong k láng giềng gần nhất của `x_i` cũng thuộc lớp thiểu số.
- `λ` — một số ngẫu nhiên trong khoảng [0,1], quyết định điểm mới nằm ở đâu trên đoạn
  thẳng nối `x_i` và `x_zi`.

## 10. Cách đọc kết quả

Không có "kết quả" trực tiếp ở bước tiền xử lý — kết quả được thể hiện gián tiếp qua chỉ
số của mô hình huấn luyện sau đó (Bài 7, 9). Điều quan trọng cần "đọc" ở đây là: liệu
pipeline có tuân thủ đúng thứ tự chống rò rỉ hay không (xem Bài 5).

## 11. Vì sao project dùng phương pháp này

Đây là các kỹ thuật tiêu chuẩn trong ngành (scikit-learn, imbalanced-learn), phù hợp với
dữ liệu dạng bảng (tabular) có giá trị thiếu, thang đo khác nhau, và mất cân bằng lớp
điển hình của bài toán phân loại rủi ro học tập.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm ngay sau bước sinh/tải dữ liệu (Bài 3) và ngay trước bước huấn luyện Classification/
Regression (Bài 6, 8) trong Chuỗi 1.

## 13. Input là gì

DataFrame thô (có thể có giá trị thiếu, thang đo khác nhau, lớp mất cân bằng) sau khi đã
được chia train/test.

## 14. Output là gì

Dữ liệu đã được điền đầy đủ, chuẩn hóa, mã hóa, và cân bằng lớp (chỉ áp dụng cho tập
train).

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho `GridSearchCV`/thuật toán huấn luyện (Classification ở Bài 6, Regression ở
Bài 8).

## 16. Ưu điểm

Các kỹ thuật chuẩn, có thư viện hỗ trợ tốt, dễ tái sử dụng qua `Pipeline`, đảm bảo tính
nhất quán giữa train và test.

## 17. Nhược điểm

SMOTE sinh dữ liệu giả có thể không phản ánh đúng phân phối thực của lớp thiểu số trong
đời thực; KNNImputer có thể chậm với dữ liệu lớn.

## 18. Limitation thực tế của project

Tiền xử lý được thiết kế cho dữ liệu tổng hợp có cấu trúc sạch — chưa được kiểm chứng
với dữ liệu thật có thể có nhiều loại nhiễu phức tạp hơn (lỗi nhập liệu, định dạng không
nhất quán...).

## 19. Hội đồng có thể hỏi gì

"Tại sao phải đưa SMOTE vào trong Pipeline thay vì áp dụng trực tiếp lên toàn bộ dữ liệu
trước khi chia train/test?"

## 20. Câu trả lời ngắn 20–40 giây

"Nếu áp dụng SMOTE trước khi chia, các điểm dữ liệu giả sinh ra từ một điểm ở tập train
có thể 'na ná' một điểm rơi vào tập test — khiến tập test không còn độc lập thực sự với
tập train, dẫn đến đánh giá mô hình bị lạc quan giả (overly optimistic). Vì vậy pipeline
được thiết kế để SMOTE chỉ chạy sau khi chia, và chỉ trên phần train."

## 21. Câu trả lời chi tiết

Nhấn mạnh: thứ tự đúng là `train_test_split` → Pipeline (Imputer→Scaler→Encoder→SMOTE)
chỉ fit trong từng fold train của GridSearchCV. Đây chính là điều được xác minh trực
tiếp trong code `dss/core/trainers.py` ở phiên làm việc audit.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy nếu không dùng SMOTE, mô hình sẽ bị ảnh hưởng thế nào?"

## 23. Cách trả lời câu vặn

"Nếu không xử lý mất cân bằng lớp, mô hình có xu hướng thiên vị dự đoán về lớp đông hơn
(ví dụ luôn đoán 'không rủi ro') để đạt accuracy cao giả tạo, trong khi Recall của lớp
thiểu số (sinh viên rủi ro thật sự) lại rất thấp — đây chính là vấn đề False Negative
nguy hiểm mà em phân tích kỹ ở Bài 7."

## 24. Những câu không được nói

- "SMOTE áp dụng cho cả tập test." (Sai — chỉ áp dụng cho train.)
- "Tiền xử lý được fit trên toàn bộ dữ liệu trước khi chia." (Sai — đây chính là leakage.)

## 25. 10 câu tự kiểm tra

1. KNNImputer làm gì?
2. StandardScaler dùng công thức nào?
3. OneHotEncoder dùng để xử lý loại cột nào?
4. SMOTE giải quyết vấn đề gì?
5. Công thức sinh điểm mới của SMOTE là gì?
6. Tại sao SMOTE phải chạy sau `train_test_split`?
7. Pipeline trong EduDSS được fit ở đâu — toàn bộ dữ liệu hay chỉ trong fold train?
8. Nếu tiền xử lý fit trên toàn bộ dữ liệu trước khi chia, hậu quả là gì?
9. Feature nào cần OneHotEncoder trong dữ liệu EduDSS (ví dụ)?
10. λ trong công thức SMOTE có ý nghĩa gì?

## 26. Đáp án riêng

1. Điền giá trị thiếu bằng trung bình của k láng giềng gần nhất.
2. `z = (x - mean) / std`.
3. Cột phân loại (categorical), ví dụ tên khoa/ngành.
4. Mất cân bằng lớp — lớp thiểu số quá ít dữ liệu.
5. `x_new = x_i + λ*(x_zi - x_i)`, λ ngẫu nhiên trong [0,1].
6. Để tránh rò rỉ thông tin từ tập test vào quá trình sinh dữ liệu giả cho tập train.
7. Chỉ trong fold train, bên trong GridSearchCV.
8. Đánh giá mô hình bị lạc quan giả, không phản ánh đúng khả năng tổng quát hóa.
9. Ví dụ cột "khoa/ngành học".
10. Là số ngẫu nhiên quyết định vị trí điểm mới trên đoạn nối 2 điểm láng giềng.

## 27. 5 CÂU PHẢI THUỘC

1. "4 kỹ thuật tiền xử lý chính: KNNImputer, StandardScaler, OneHotEncoder, SMOTE."
2. "Tất cả được gói trong một Pipeline, chỉ fit bên trong fold train của GridSearchCV."
3. "SMOTE không bao giờ áp dụng lên tập test."
4. "Z-score: z = (x-mean)/std, tính trên tập train."
5. "Thứ tự đúng: chia train/test trước, tiền xử lý sau — ngược lại sẽ gây rò rỉ dữ liệu."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Imputer — Bộ điền giá trị thiếu
- Scaler — Bộ chuẩn hóa thang đo
- Encoder — Bộ mã hóa dữ liệu phân loại
- SMOTE — Kỹ thuật sinh mẫu tổng hợp cho lớp thiểu số
- Pipeline — Chuỗi xử lý tuần tự có thể fit/transform nhất quán
