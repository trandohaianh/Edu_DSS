# Bài 8 — Regression (Hồi quy)

## 1. Mục tiêu buổi học

Hiểu 4 thuật toán hồi quy EduDSS dùng để dự đoán điểm số tương lai, chính xác số cấu
hình/lượt fit của từng thuật toán (khác hoàn toàn với bộ số của Classification ở Bài 6 —
không được nhầm lẫn hai bộ số này).

## 2. Kiến thức cần nhớ trước

Bài 3 (dữ liệu, đặc biệt công thức `diem_ky_sau`), Bài 4-5 (tiền xử lý, leakage), Bài 6
(để so sánh với Classification, tránh nhầm lẫn số liệu).

## 3. Giải thích từ con số 0

**Regression (hồi quy)** dự đoán một **giá trị số liên tục** — ví dụ điểm số kỳ tới (một
số thực từ 0 đến 10) — khác với Classification dự đoán một **nhãn rời rạc** (Cao/Trung
bình/Thấp). Trong EduDSS, bài toán hồi quy cụ thể là: dự đoán `diem_ky_sau` (điểm kỳ sau)
dựa trên các feature như điểm giữa kỳ, tỷ lệ điểm danh, số giờ tự học...

## 4. Giải thích kỹ thuật

4 thuật toán hồi quy trong `dss/core/trainers.py::RegressionTrainer` — đây là **nguồn sự
thật duy nhất** (single source of truth, đã được thống nhất qua sửa lỗi `ML-REG-001`),
KHÔNG được nhầm với con số lịch sử 36 cấu hình đã bị loại bỏ:

- **Linear Regression** — mô hình tuyến tính đơn giản, không có siêu tham số cần tinh
  chỉnh. **0 cấu hình, 1 lượt fit.**
- **Random Forest Regressor** — 12 cấu hình × 5-fold CV = **60 lượt fit**.
- **XGBoost Regressor** — 18 cấu hình × 5-fold CV = **90 lượt fit**.
- **LightGBM Regressor** — 18 cấu hình × 5-fold CV = **90 lượt fit**.

Lưu ý quan trọng: **XGBoost Regressor CÓ dùng GridSearchCV đầy đủ** — chỉ có XGBoost
**Classifier** (Bài 6) mới là ngoại lệ không dùng GridSearchCV. Đừng nhầm hai cái này với
nhau.

## 5. Ví dụ cực dễ hiểu

Nếu Classification giống như hỏi "sinh viên này thuộc nhóm giỏi/khá/trung bình/yếu?" thì
Regression giống như hỏi "sinh viên này có khả năng đạt bao nhiêu điểm — chính xác đến
một chữ số thập phân?"

## 6. Ví dụ trực tiếp trong EduDSS

Trên tab "Huấn luyện" của Giảng viên, khi chọn bài toán hồi quy với target `diem_ky_sau`,
hệ thống chạy cả 4 thuật toán trên, so sánh MAE/MSE/RMSE/R² (Bài 9), và hiển thị mô hình
tốt nhất.

## 7. Luồng xử lý thực tế trong project

```
Dữ liệu đã tiền xử lý (Bài 4-5) → với mỗi thuật toán trong 4 thuật toán hồi quy:
  - Linear Regression → fit trực tiếp, không GridSearchCV → 1 fit
  - Random Forest Regressor → GridSearchCV(12 cấu hình, cv=5) → 60 fit
  - XGBoost Regressor → GridSearchCV(18 cấu hình, cv=5) → 90 fit
  - LightGBM Regressor → GridSearchCV(18 cấu hình, cv=5) → 90 fit
→ so sánh MAE/MSE/RMSE/R² → lưu candidate tốt nhất vào Model Registry
```

## 8. Công thức nếu có

Linear Regression dự đoán: `ŷ = w_0 + w_1*x_1 + w_2*x_2 + ... + w_n*x_n`

## 9. Giải thích từng ký hiệu trong công thức

- `ŷ` — giá trị dự đoán (điểm kỳ sau dự đoán).
- `w_0` — hệ số chặn (intercept/bias).
- `w_1...w_n` — các trọng số học được cho từng feature.
- `x_1...x_n` — giá trị các feature đầu vào (điểm giữa kỳ, tỷ lệ điểm danh...).

## 10. Cách đọc kết quả

Đọc số "cấu hình" là số bộ tham số được thử; đọc "lượt fit" là tổng số lần huấn luyện
thực tế (bao gồm CV fold). Linear Regression không có gì để "tìm kiếm" (search) vì không
có siêu tham số — nó chỉ fit một lần duy nhất bằng công thức đóng (closed-form) hoặc tối
ưu số học trực tiếp.

## 11. Vì sao project dùng phương pháp này

Bốn thuật toán đại diện đủ phổ: một mô hình tuyến tính đơn giản làm baseline (đường cơ
sở để so sánh), và ba mô hình phi tuyến mạnh hơn (Random Forest, XGBoost, LightGBM) để
xem có cải thiện được so với baseline hay không.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm song song với Classification trong Chuỗi 1 — cùng nhận input từ Tiền xử lý (Bài 4),
cùng chuyển output sang SHAP (Bài 13) và Diagnosis Engine (Bài 14).

## 13. Input là gì

Dữ liệu đã tiền xử lý với target là một giá trị số liên tục (`diem_ky_sau`).

## 14. Output là gì

Một mô hình hồi quy đã huấn luyện, dự đoán ra một con số điểm cụ thể, cùng các chỉ số
MAE/MSE/RMSE/R² (Bài 9).

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho SHAP (Bài 13) để giải thích, và giá trị dự đoán được dùng trong Dashboard của
Sinh viên/Giảng viên.

## 16. Ưu điểm

Linear Regression đơn giản, dễ giải thích; Random Forest/XGBoost/LightGBM có thể bắt được
quan hệ phi tuyến phức tạp hơn.

## 17. Nhược điểm

Random Forest/XGBoost/LightGBM khó giải thích trực tiếp bằng hệ số như Linear Regression
(cần dùng SHAP — Bài 13); tốn tài nguyên tính toán hơn do GridSearchCV.

## 18. Limitation thực tế của project

R² đo trên tập dữ liệu mẫu (tổng hợp) rất cao vì bản chất công thức sinh dữ liệu (Bài 3,
Bài 9) — không thể coi đây là minh chứng hiệu năng thực tế.

## 19. Hội đồng có thể hỏi gì

"Vì sao Random Forest Regressor chỉ có 12 cấu hình trong khi Random Forest Classifier có
tới 24?"

## 20. Câu trả lời ngắn 20–40 giây

"Vì đây là hai bài toán khác nhau với hai lưới siêu tham số (param grid) được thiết kế
riêng biệt trong code, không dùng chung. Classification cần khám phá thêm chiều
`min_samples_leaf` nên có nhiều tổ hợp hơn (24), còn Regression được thiết kế với lưới
gọn hơn (12) — đây là quyết định thiết kế độc lập cho từng bài toán, không phải một quy
tắc chung áp dụng cho cả hai."

## 21. Câu trả lời chi tiết

Liệt kê chính xác bảng 4 thuật toán regression (mục 4) và nếu cần, đối chiếu với bảng
classification (Bài 6) để cho thấy sự khác biệt rõ ràng, có chủ đích, không phải nhầm
lẫn.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy con số 36 cấu hình Random Forest mà tài liệu cũ có đề cập là gì?"

## 23. Cách trả lời câu vặn

"Đó là một con số lịch sử từ một phiên bản tài liệu trước, chưa từng thực sự được thực
thi trong code. Sau khi rà soát lại (fix `ML-REG-001`), nguồn sự thật duy nhất hiện tại
được xác nhận trực tiếp trong `dss/core/trainers.py` là 12 cấu hình / 60 lượt fit cho
Random Forest Regressor. Em xin đính chính và không sử dụng con số cũ đó nữa."

## 24. Những câu không được nói

- "Random Forest Regressor có 36 cấu hình." (Sai — con số lịch sử đã bị loại bỏ.)
- "Regression và Classification dùng chung một lưới tham số." (Sai — hai lưới hoàn toàn
  độc lập.)

## 25. 10 câu tự kiểm tra

1. Kể tên 4 thuật toán hồi quy trong EduDSS.
2. Linear Regression có bao nhiêu cấu hình, bao nhiêu lượt fit?
3. Random Forest Regressor có bao nhiêu cấu hình, bao nhiêu lượt fit?
4. XGBoost Regressor có bao nhiêu cấu hình, bao nhiêu lượt fit?
5. LightGBM Regressor có bao nhiêu cấu hình, bao nhiêu lượt fit?
6. XGBoost Regressor có dùng GridSearchCV không? (So với XGBoost Classifier ở Bài 6?)
7. Target của bài toán hồi quy trong EduDSS là gì?
8. Vì sao Random Forest Regressor và Random Forest Classifier có số cấu hình khác nhau?
9. Con số 36 cấu hình Random Forest có còn đúng không?
10. Regression khác Classification ở điểm cốt lõi nào?

## 26. Đáp án riêng

1. Linear Regression, Random Forest, XGBoost, LightGBM.
2. 0 cấu hình, 1 lượt fit.
3. 12 cấu hình, 60 lượt fit.
4. 18 cấu hình, 90 lượt fit.
5. 18 cấu hình, 90 lượt fit.
6. Có — khác với XGBoost Classifier (không dùng GridSearchCV).
7. `diem_ky_sau` (điểm kỳ sau).
8. Vì lưới tham số được thiết kế riêng biệt cho từng bài toán trong code.
9. Không — đó là con số lịch sử đã bị loại bỏ; con số đúng hiện tại là 12/60.
10. Regression dự đoán số liên tục, Classification dự đoán nhãn rời rạc.

## 27. 5 CÂU PHẢI THUỘC

1. "Linear Regression: 0 cấu hình, 1 fit. Random Forest: 12 cấu hình, 60 fit. XGBoost:
   18 cấu hình, 90 fit. LightGBM: 18 cấu hình, 90 fit."
2. "XGBoost Regressor CÓ dùng GridSearchCV đầy đủ — khác với XGBoost Classifier."
3. "Con số 36 cấu hình Random Forest là lịch sử, đã bị loại bỏ — không dùng lại."
4. "Target của bài toán hồi quy là `diem_ky_sau`, một giá trị số liên tục."
5. "Lưới tham số của Classification và Regression là hai lưới hoàn toàn độc lập."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Regression — Hồi quy
- Continuous value — Giá trị liên tục
- Baseline model — Mô hình cơ sở (Linear Regression)
- Param grid — Lưới siêu tham số
- Single source of truth — Nguồn sự thật duy nhất
