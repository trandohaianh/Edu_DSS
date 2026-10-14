# Bài 10 — GridSearchCV và So sánh mô hình

## 1. Mục tiêu buổi học

Hiểu cơ chế GridSearchCV hoạt động thế nào, vì sao "số cấu hình" và "số lượt fit" luôn là
hai con số khác nhau, và có thể trình bày rành mạch toàn bộ 8 con số (4 classification +
4 regression) mà không nhầm lẫn.

## 2. Kiến thức cần nhớ trước

Bài 5 (Cross-validation), Bài 6 (Classification), Bài 8 (Regression).

## 3. Giải thích từ con số 0

Một thuật toán ML thường có nhiều "núm vặn" gọi là **siêu tham số (hyperparameter)** —
ví dụ Random Forest có "số lượng cây" (`n_estimators`), "độ sâu tối đa" (`max_depth`).
Ta không biết trước tổ hợp núm vặn nào cho kết quả tốt nhất, nên **GridSearchCV** thử
**tất cả các tổ hợp có thể** trong một lưới (grid) đã định nghĩa trước, và với MỖI tổ hợp,
nó dùng cross-validation (Bài 5) để đánh giá một cách đáng tin cậy — rồi chọn ra tổ hợp
tốt nhất.

## 4. Giải thích kỹ thuật

Số lượt fit = Số cấu hình × Số fold CV. Ví dụ Random Forest Classifier: lưới có
`n_estimators:[100,200] × max_depth:[10,20,None] × min_samples_split:[2,5] ×
min_samples_leaf:[1,2]` = 2×3×2×2 = **24 tổ hợp**. Mỗi tổ hợp phải được huấn luyện và
đánh giá qua **5 fold** (5-fold CV) → 24 × 5 = **120 lượt fit** tổng cộng, chỉ để tìm ra
1 tổ hợp tham số tốt nhất.

Bảng đầy đủ 8 thuật toán (nguồn sự thật cuối cùng, đã kiểm chứng trực tiếp trong
`dss/core/trainers.py`):

| Bài toán | Thuật toán | Số cấu hình | CV | Số lượt fit |
|---|---|---|---|---|
| Classification | Random Forest | 24 | 5-fold | 120 |
| Classification | XGBoost | 1 (cố định) | không | 1 |
| Classification | LightGBM | 8 | 5-fold | 40 |
| Classification | Logistic Regression | 3 | 5-fold | 15 |
| Regression | Random Forest | 12 | 5-fold | 60 |
| Regression | XGBoost | 18 | 5-fold | 90 |
| Regression | LightGBM | 18 | 5-fold | 90 |
| Regression | Linear Regression | 0 | không | 1 |

## 5. Ví dụ cực dễ hiểu

Giống như thử món ăn với nhiều công thức khác nhau (mỗi công thức là một "cấu hình"), và
với mỗi công thức bạn nấu thử 5 lần với 5 nhóm người nếm khác nhau (5 fold) để chắc chắn
kết quả không phải do may mắn của một lần nấu — tổng số lần bạn thực sự nấu ăn (lượt fit)
lớn hơn nhiều số công thức bạn có.

## 6. Ví dụ trực tiếp trong EduDSS

Với Random Forest Classifier, hệ thống thực sự chạy 120 lần huấn luyện mô hình (đo được
bằng thời gian chạy thực tế khi Giảng viên bấm "Huấn luyện") chỉ để tìm ra 1 bộ tham số
tốt nhất trong 24 lựa chọn.

## 7. Luồng xử lý thực tế trong project

```
Xác định param_grid (cấu hình có sẵn trong code, KHÔNG đổi được từ UI)
  → GridSearchCV(estimator=Pipeline(...), param_grid=param_grid, cv=5)
  → với mỗi tổ hợp tham số: chạy đủ 5 fold, tính điểm trung bình
  → chọn tổ hợp có điểm trung bình cao nhất (hoặc lỗi thấp nhất với regression)
  → fit lại mô hình với tổ hợp tốt nhất trên toàn bộ tập train
  → đánh giá cuối cùng trên tập test
```

## 8. Công thức nếu có

```
Số lượt fit = Số cấu hình (tổ hợp tham số) × Số fold CV
```

## 9. Giải thích từng ký hiệu trong công thức

- Số cấu hình — tích của số lựa chọn ở mỗi chiều siêu tham số (ví dụ 2×3×2×2=24).
- Số fold CV — số phần dữ liệu train được chia ra để kiểm định chéo (EduDSS dùng 5 cho
  mọi thuật toán có GridSearchCV).
- Trường hợp đặc biệt: nếu không dùng GridSearchCV (XGBoost Classifier, Linear
  Regression), số lượt fit luôn là 1, bất kể "số cấu hình" là 0 hay 1.

## 10. Cách đọc kết quả

Khi hội đồng hỏi "vì sao số này khác số kia", câu trả lời luôn là: **số cấu hình là số
lựa chọn tham số**, **số lượt fit là số lần mô hình THỰC SỰ được huấn luyện** — chúng
khác nhau vì cơ chế cross-validation nhân thêm hệ số fold.

## 11. Vì sao project dùng phương pháp này

GridSearchCV kết hợp cross-validation là phương pháp tiêu chuẩn, đáng tin cậy để tìm
siêu tham số tốt mà không cần đoán mò hay chỉ tin vào một lần chia dữ liệu ngẫu nhiên.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là cơ chế lõi bên trong cả Classification (Bài 6) và Regression (Bài 8) — không phải một
module riêng biệt, mà là "cách" 2 module đó huấn luyện.

## 13. Input là gì

Một lưới tham số (param grid) được định nghĩa sẵn trong code, và dữ liệu train đã tiền
xử lý.

## 14. Output là gì

Bộ tham số tốt nhất cho mỗi thuật toán, cùng mô hình đã fit lại trên toàn bộ tập train
với bộ tham số đó.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển sang bước đánh giá cuối cùng trên tập test (Bài 7, Bài 9), rồi vào Model Registry
(Bài 22).

## 16. Ưu điểm

Tìm kiếm tham số có hệ thống, đáng tin cậy hơn nhiều so với chọn tham số thủ công hay
đoán mò.

## 17. Nhược điểm

Tốn thời gian tính toán — càng nhiều cấu hình, càng nhiều fold, thời gian huấn luyện càng
lâu (120 lượt fit cho Random Forest Classifier là con số không nhỏ).

## 18. Limitation thực tế của project

Không phải mọi thuật toán đều được tuning với độ sâu như nhau — XGBoost Classifier là
ngoại lệ không dùng GridSearchCV (Bài 6) — nên so sánh giữa các thuật toán không hoàn
toàn "công bằng tuyệt đối" về độ sâu tối ưu hóa.

## 19. Hội đồng có thể hỏi gì

"Tại sao Random Forest Classifier có 120 lượt fit mà Logistic Regression chỉ có 15?"

## 20. Câu trả lời ngắn 20–40 giây

"Vì Random Forest Classifier có lưới tham số lớn hơn — 24 tổ hợp (4 chiều siêu tham số),
trong khi Logistic Regression chỉ có 3 tổ hợp (1 chiều C, 1 solver cố định). Cả hai đều
nhân với 5-fold CV, nên 24×5=120 và 3×5=15. Sự khác biệt phản ánh độ phức tạp của không
gian siêu tham số mỗi thuật toán cần khám phá, không phải một quy tắc cố định áp dụng
chung."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ bảng 8 dòng ở mục 4, nhấn mạnh công thức ở mục 8, và nếu được hỏi thêm
có thể giải thích từng chiều tham số của Random Forest (n_estimators, max_depth,
min_samples_split, min_samples_leaf) cụ thể làm gì.

## 22. Hội đồng có thể vặn tiếp thế nào

"Có thể tăng số cấu hình lên nhiều hơn để tìm tham số tốt hơn không?"

## 23. Cách trả lời câu vặn

"Có thể, nhưng đánh đổi là thời gian huấn luyện tăng tuyến tính theo số cấu hình. Lưới
hiện tại được chọn ở mức đủ để khám phá không gian tham số hợp lý trong thời gian huấn
luyện chấp nhận được cho một ứng dụng tương tác (Giảng viên bấm nút và chờ kết quả), phù
hợp quy mô đồ án chứ không phải một hệ thống huấn luyện offline quy mô lớn."

## 24. Những câu không được nói

- "Tất cả 8 thuật toán (4 classification + 4 regression) đều dùng cùng một lưới tham
  số." (Sai — mỗi bài toán, mỗi thuật toán có lưới riêng.)
- "Số cấu hình và số lượt fit là một." (Sai — luôn khác nhau khi có CV.)

## 25. 10 câu tự kiểm tra

1. GridSearchCV làm gì?
2. Công thức tính số lượt fit từ số cấu hình và số fold?
3. Random Forest Classifier có bao nhiêu cấu hình? Bao nhiêu lượt fit?
4. XGBoost Regressor có bao nhiêu cấu hình? Bao nhiêu lượt fit?
5. Thuật toán nào không dùng GridSearchCV ở cả 2 bài toán (Classification/Regression)?
6. 5-fold CV nghĩa là gì trong ngữ cảnh GridSearchCV?
7. Vì sao Random Forest Classifier (24 cấu hình) và Random Forest Regressor (12 cấu
   hình) có số cấu hình khác nhau?
8. Sau khi GridSearchCV chọn được tham số tốt nhất, bước tiếp theo là gì?
9. Nhược điểm lớn nhất của GridSearchCV là gì?
10. Vì sao không thể nói "tất cả các thuật toán được so sánh công bằng tuyệt đối"?

## 26. Đáp án riêng

1. Thử tất cả tổ hợp siêu tham số trong một lưới định trước, dùng CV để đánh giá từng
   tổ hợp, chọn tổ hợp tốt nhất.
2. Số lượt fit = số cấu hình × số fold.
3. 24 cấu hình, 120 lượt fit.
4. 18 cấu hình, 90 lượt fit.
5. XGBoost Classifier (Linear Regression cũng không dùng GridSearchCV nhưng chỉ ở bài
   toán Regression).
6. Chia tập train thành 5 phần, lần lượt dùng 4 phần học 1 phần kiểm tra, lặp 5 lần.
7. Vì lưới tham số được thiết kế độc lập cho từng bài toán trong code, không dùng chung.
8. Fit lại mô hình với tham số tốt nhất trên toàn bộ tập train, rồi đánh giá trên tập
   test.
9. Tốn thời gian tính toán, tăng tuyến tính theo số cấu hình và số fold.
10. Vì XGBoost Classifier không được tuning bằng GridSearchCV như 3 thuật toán còn lại
    trong bài toán phân loại.

## 27. 5 CÂU PHẢI THUỘC

1. "Số lượt fit = số cấu hình × số fold CV."
2. "Random Forest Classifier: 24 cấu hình/120 fit. Random Forest Regressor: 12 cấu
   hình/60 fit — hai lưới độc lập, đừng nhầm."
3. "XGBoost Classifier và Linear Regression là hai ngoại lệ không dùng GridSearchCV."
4. "Tất cả các thuật toán có GridSearchCV đều dùng 5-fold CV."
5. "So sánh giữa các thuật toán không hoàn toàn công bằng tuyệt đối về độ sâu tuning —
   đây là điều cần công khai."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- GridSearchCV — Tìm kiếm siêu tham số dạng lưới kết hợp CV
- Hyperparameter — Siêu tham số
- Param grid — Lưới tham số
- Fold — Phần dữ liệu con trong CV
- Best estimator — Mô hình với tham số tốt nhất được chọn
