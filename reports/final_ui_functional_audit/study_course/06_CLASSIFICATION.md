# Bài 6 — Classification (Phân loại)

## 1. Mục tiêu buổi học

Hiểu 4 thuật toán phân loại EduDSS dùng, chính xác số cấu hình và số lượt fit của từng
thuật toán, và đặc biệt hiểu **vì sao XGBoost Classifier là một ngoại lệ** không dùng
GridSearchCV như 3 thuật toán còn lại.

## 2. Kiến thức cần nhớ trước

Bài 4 (tiền xử lý), Bài 5 (train/test/CV/leakage).

## 3. Giải thích từ con số 0

**Classification (phân loại)** là bài toán dự đoán một sinh viên thuộc **nhóm rời rạc**
nào — ví dụ "rủi ro cao / rủi ro trung bình / bình thường" — khác với **Regression (hồi
quy)** ở Bài 8, dự đoán một **con số liên tục** (ví dụ điểm số).

## 4. Giải thích kỹ thuật

4 thuật toán phân loại trong `dss/core/trainers.py::ClassificationTrainer`:

- **Logistic Regression (Softmax)** — mô hình tuyến tính, dùng hàm softmax để tính xác
  suất thuộc mỗi lớp. Grid: `C:[0.1,1.0,10.0] × solver:[lbfgs]` = 3 cấu hình × 5-fold CV
  = **15 lượt fit**.
- **Random Forest Classifier** — tập hợp nhiều cây quyết định (decision tree), mỗi cây
  học trên một mẫu ngẫu nhiên của dữ liệu, kết quả cuối là "bỏ phiếu" đa số. Grid:
  `n_estimators:[100,200] × max_depth:[10,20,None] × min_samples_split:[2,5] ×
  min_samples_leaf:[1,2]` = 24 cấu hình × 5-fold CV = **120 lượt fit**.
- **LightGBM Classifier** — một biến thể gradient boosting tối ưu tốc độ. Grid:
  `n_estimators:[100,200] × max_depth:[3,5] × learning_rate:[0.1,0.2]` = 8 cấu hình ×
  5-fold CV = **40 lượt fit**.
- **XGBoost Classifier** — cũng là gradient boosting, nhưng trong EduDSS **KHÔNG dùng
  GridSearchCV** — chạy với tham số cố định (`n_estimators=200, max_depth=5,
  learning_rate=0.1`) = **1 lượt fit, 0 lượt CV**.

## 5. Ví dụ cực dễ hiểu

Random Forest giống như hỏi ý kiến 100 chuyên gia độc lập rồi lấy đa số phiếu bầu.
Gradient Boosting (XGBoost/LightGBM) giống như một chuỗi chuyên gia, mỗi người sau sửa
lỗi của người trước. Logistic Regression giống như vẽ một đường ranh giới thẳng để tách
hai nhóm.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên vào tab "Huấn luyện" và chọn bài toán phân loại rủi ro (ví dụ 3 lớp: Cao/
Trung bình/Thấp), hệ thống chạy cả 4 thuật toán trên, so sánh Accuracy/Precision/Recall/
F1 (Bài 7) của từng thuật toán, rồi hiển thị bảng so sánh cho Giảng viên chọn.

## 7. Luồng xử lý thực tế trong project

```
Dữ liệu đã tiền xử lý (Bài 4-5) → với mỗi thuật toán trong 4 thuật toán:
  - Logistic Regression → GridSearchCV(3 cấu hình, cv=5) → 15 fit
  - Random Forest → GridSearchCV(24 cấu hình, cv=5) → 120 fit
  - LightGBM → GridSearchCV(8 cấu hình, cv=5) → 40 fit
  - XGBoost → fit trực tiếp với tham số cố định → 1 fit
→ so sánh Accuracy/Precision/Recall/F1 của cả 4 → lưu candidate tốt nhất vào Model Registry
```

## 8. Công thức nếu có

Softmax (Logistic Regression đa lớp): `P(y=k|x) = exp(z_k) / Σ_j exp(z_j)`

## 9. Giải thích từng ký hiệu trong công thức

- `z_k` — điểm số tuyến tính (linear score) mô hình tính cho lớp thứ k.
- `exp(z_k)` — hàm mũ áp lên điểm số, luôn cho giá trị dương.
- `Σ_j exp(z_j)` — tổng hàm mũ trên tất cả các lớp, dùng để chuẩn hóa (normalize) sao cho
  tổng xác suất các lớp bằng 1.
- `P(y=k|x)` — xác suất dự đoán điểm dữ liệu `x` thuộc lớp `k`.

## 10. Cách đọc kết quả

Khi thấy bảng so sánh 4 thuật toán, đọc số "cấu hình" là số bộ tham số khác nhau được thử,
đọc số "lượt fit" là tổng số lần mô hình thực sự được huấn luyện (bao gồm cả các fold CV)
— **hai con số này khác nhau vì mỗi cấu hình phải chạy qua 5 fold** (trừ XGBoost, không
qua CV nào).

## 11. Vì sao project dùng phương pháp này

4 thuật toán này đại diện cho 3 họ mô hình phổ biến trên dữ liệu dạng bảng: tuyến tính
(Logistic Regression), rừng cây độc lập (Random Forest), và gradient boosting tuần tự
(XGBoost, LightGBM) — cho phép so sánh khách quan và chọn ra mô hình phù hợp nhất với dữ
liệu cụ thể.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm trong Chuỗi 1, ngay sau Tiền xử lý (Bài 4), trước SHAP (Bài 13) và Diagnosis Engine
(Bài 14).

## 13. Input là gì

Dữ liệu đã tiền xử lý, đã chia train/test.

## 14. Output là gì

Một mô hình phân loại đã huấn luyện, cùng nhãn dự đoán (Cao/Trung bình/Thấp) và các chỉ
số đánh giá.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho SHAP để giải thích (Bài 13), và nhãn dự đoán được dùng làm input cho Diagnosis
Engine (Bài 14).

## 16. Ưu điểm

Nhiều lựa chọn thuật toán để so sánh; Random Forest/LightGBM có GridSearchCV đầy đủ giúp
tối ưu tham số nghiêm túc.

## 17. Nhược điểm

XGBoost Classifier bị giảm độ sâu tinh chỉnh so với 3 thuật toán còn lại — đây là điểm
yếu cần công khai, không được giấu.

## 18. Limitation thực tế của project

XGBoost Classifier gặp lỗi "Invalid classes inferred from unique values of y" khi một
lớp hiếm bị thiếu ở một fold CV (do fold ngẫu nhiên không đủ mẫu của lớp đó) — nên nhóm
phát triển chọn giải pháp dùng tham số cố định thay vì GridSearchCV, đây là một đánh đổi
kỹ thuật có chủ đích, không phải sai sót.

## 19. Hội đồng có thể hỏi gì

"Vì sao XGBoost Classifier không dùng GridSearchCV giống 3 thuật toán còn lại?"

## 20. Câu trả lời ngắn 20–40 giây

"Vì khi chạy GridSearchCV với XGBoost trên bài toán phân loại đa lớp, một số fold ngẫu
nhiên bị thiếu mẫu của lớp hiếm, khiến XGBoost báo lỗi 'Invalid classes inferred'. Đây là
một vấn đề kỹ thuật đã biết với dữ liệu đa lớp mất cân bằng. Giải pháp em chọn là dùng bộ
tham số cố định hợp lý (n_estimators=200, max_depth=5, learning_rate=0.1) thay vì
GridSearchCV cho riêng XGBoost Classifier — một đánh đổi có chủ đích và được ghi nhận rõ
ràng, không phải một thiếu sót bị bỏ qua."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ bảng 4 thuật toán ở mục 4, nhấn mạnh sự khác biệt giữa "số cấu hình" và
"số lượt fit" (xem Bài 10 để đào sâu thêm).

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy kết quả so sánh giữa XGBoost và 3 thuật toán còn lại có công bằng không, khi tuning
không đồng đều?"

## 23. Cách trả lời câu vặn

"Đây là một giới hạn thực sự mà em công khai thừa nhận — so sánh không hoàn toàn công
bằng về độ sâu tuning. Tuy nhiên bộ tham số cố định của XGBoost được chọn dựa trên các
giá trị phổ biến, hợp lý trong thực hành (không phải giá trị mặc định ngẫu nhiên), nên
kết quả vẫn có giá trị tham khảo, chỉ là không thể khẳng định đó là so sánh 'tối ưu hóa
ngang hàng tuyệt đối' giữa 4 thuật toán."

## 24. Những câu không được nói

- "Cả 4 thuật toán đều được tối ưu hóa với độ sâu như nhau." (Sai.)
- "Random Forest có 36 cấu hình." (Sai — đây là con số lịch sử đã bị loại bỏ, con số
  đúng hiện tại là 24 cấu hình cho classification.)

## 25. 10 câu tự kiểm tra

1. Kể tên 4 thuật toán phân loại trong EduDSS.
2. Random Forest Classifier có bao nhiêu cấu hình và bao nhiêu lượt fit?
3. LightGBM Classifier có bao nhiêu cấu hình và bao nhiêu lượt fit?
4. Logistic Regression có bao nhiêu cấu hình và bao nhiêu lượt fit?
5. XGBoost Classifier có dùng GridSearchCV không? Vì sao?
6. Vì sao số "cấu hình" và số "lượt fit" khác nhau?
7. Softmax dùng để làm gì trong Logistic Regression?
8. Vấn đề gì khiến XGBoost Classifier gặp lỗi khi chạy GridSearchCV đa lớp?
9. Classification khác Regression ở điểm nào?
10. Output của Classification được chuyển tiếp cho những module nào?

## 26. Đáp án riêng

1. Logistic Regression (Softmax), Random Forest, XGBoost, LightGBM.
2. 24 cấu hình, 120 lượt fit.
3. 8 cấu hình, 40 lượt fit.
4. 3 cấu hình, 15 lượt fit.
5. Không — dùng tham số cố định, 1 lượt fit, do lỗi "Invalid classes inferred" ở CV
   đa lớp mất cân bằng.
6. Vì mỗi cấu hình phải chạy qua 5 fold CV (trừ XGBoost không qua fold nào).
7. Chuyển điểm số tuyến tính thành xác suất chuẩn hóa cho từng lớp.
8. Một fold CV ngẫu nhiên có thể thiếu mẫu của một lớp hiếm.
9. Classification dự đoán nhóm rời rạc, Regression dự đoán số liên tục.
10. SHAP (giải thích) và Diagnosis Engine (chẩn đoán nguyên nhân).

## 27. 5 CÂU PHẢI THUỘC

1. "Random Forest Classifier: 24 cấu hình, 120 lượt fit (5-fold CV)."
2. "LightGBM Classifier: 8 cấu hình, 40 lượt fit."
3. "Logistic Regression: 3 cấu hình, 15 lượt fit."
4. "XGBoost Classifier: KHÔNG dùng GridSearchCV — tham số cố định, 1 lượt fit, do lỗi
   đa lớp mất cân bằng."
5. "4 thuật toán KHÔNG được tuning với độ sâu như nhau — đây là điểm cần công khai."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Classification — Phân loại
- Random Forest — Rừng ngẫu nhiên
- Gradient Boosting — Tăng cường gradient
- Softmax — Hàm chuẩn hóa xác suất đa lớp
- Configuration vs. Fit — Cấu hình tham số vs. lượt huấn luyện thực tế
