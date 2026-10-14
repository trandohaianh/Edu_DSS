# Bài 9 — Đọc hiểu chỉ số hồi quy: MAE, MSE, RMSE, R²

## 1. Mục tiêu buổi học

Hiểu 4 chỉ số đánh giá hồi quy, và làm chủ hoàn toàn lời giải thích cho câu hỏi khó nhất
trong toàn bộ buổi bảo vệ: **"Vì sao R² cao bất thường trên tập dữ liệu mẫu?"**

## 2. Kiến thức cần nhớ trước

Bài 3 (công thức sinh `diem_ky_sau`), Bài 5 (chống leakage), Bài 8 (Regression).

## 3. Giải thích từ con số 0

Với bài toán hồi quy, ta không thể dùng "đúng/sai" như phân loại — vì dự đoán là một số
thực, gần như không bao giờ trùng khớp tuyệt đối với giá trị thật. Thay vào đó, ta đo
**mức độ sai lệch (error)** giữa giá trị dự đoán và giá trị thật, và đo **mức độ mô hình
giải thích được sự biến thiên (variance)** của dữ liệu.

## 4. Giải thích kỹ thuật

- **MAE (Mean Absolute Error — sai số tuyệt đối trung bình)**: trung bình của trị tuyệt
  đối sai lệch giữa dự đoán và thật, đơn vị giống với target (ví dụ "sai trung bình 0.5
  điểm").
- **MSE (Mean Squared Error — sai số bình phương trung bình)**: giống MAE nhưng bình
  phương sai lệch trước khi lấy trung bình — phạt nặng hơn các sai lệch lớn.
- **RMSE (Root Mean Squared Error — căn bậc hai của MSE)**: đưa đơn vị MSE về lại đơn vị
  gốc (vì MSE bị bình phương nên đơn vị bị "bình phương" theo).
- **R² (hệ số xác định)**: tỷ lệ phương sai của target được mô hình giải thích, giá trị
  từ 0 đến 1 (càng gần 1 càng tốt, về mặt lý thuyết).

## 5. Ví dụ cực dễ hiểu

Nếu bạn ném phi tiêu vào bia, MAE giống như đo khoảng cách trung bình từ mỗi lần ném đến
tâm bia. MSE giống như vậy nhưng "phạt nặng" những lần ném trật xa hơn nhiều (bình
phương làm sai số lớn "phình to" nhanh hơn). R² giống như trả lời câu hỏi: "Kỹ năng ném
của bạn giải thích được bao nhiêu phần trăm lý do các mũi tiêu rơi gần tâm, so với nếu
bạn ném ngẫu nhiên hoàn toàn?"

## 6. Ví dụ trực tiếp trong EduDSS

Khi huấn luyện Random Forest Regressor trên tập dữ liệu mẫu để dự đoán `diem_ky_sau`, R²
đo được thường **rất cao** (gần 1). Đây CHÍNH LÀ điểm hội đồng sẽ hỏi kỹ nhất — và câu trả
lời không nằm ở thuật toán, mà nằm ở cách dữ liệu mẫu được sinh ra (xem mục 20 dưới đây).

## 7. Luồng xử lý thực tế trong project

```
Mô hình dự đoán trên tập test → so sánh dự đoán với `diem_ky_sau` thật
  → tính MAE, MSE, RMSE, R² → hiển thị bảng so sánh 4 thuật toán cho Giảng viên
  → nếu R² cao, banner "dữ liệu demo/tổng hợp" phải được hiển thị kèm theo (data_source_type)
```

## 8. Công thức nếu có

```
MAE  = (1/n) * Σ|y_i - ŷ_i|
MSE  = (1/n) * Σ(y_i - ŷ_i)²
RMSE = sqrt(MSE)
R²   = 1 - (Σ(y_i - ŷ_i)² / Σ(y_i - ȳ)²)
```

## 9. Giải thích từng ký hiệu trong công thức

- `n` — số lượng điểm dữ liệu trong tập test.
- `y_i` — giá trị thật của điểm dữ liệu thứ i.
- `ŷ_i` — giá trị mô hình dự đoán cho điểm dữ liệu thứ i.
- `ȳ` — giá trị trung bình của tất cả `y_i` thật (baseline "đoán mù" tốt nhất nếu không
  có mô hình gì).
- Tử số của R² (`Σ(y_i-ŷ_i)²`) — tổng sai số bình phương của MÔ HÌNH.
- Mẫu số của R² (`Σ(y_i-ȳ)²`) — tổng sai số bình phương nếu chỉ dùng trung bình để đoán
  (không có mô hình).
- Nếu mô hình dự đoán hoàn hảo, tử số = 0 → R² = 1. Nếu mô hình tệ như đoán mù bằng trung
  bình, R² ≈ 0. R² có thể âm nếu mô hình tệ hơn cả đoán mù.

## 10. Cách đọc kết quả

MAE/MSE/RMSE càng nhỏ càng tốt (đơn vị cùng thang với target — ví dụ điểm số 0-10). R²
càng gần 1 càng tốt về mặt toán học — **nhưng R² cao trên dữ liệu tổng hợp phải được diễn
giải cẩn trọng**, không được đọc thẳng là "mô hình dự đoán chính xác điểm số sinh viên
thật."

## 11. Vì sao project dùng phương pháp này

Đây là bộ 4 chỉ số tiêu chuẩn công nghiệp cho bài toán hồi quy, cho phép nhìn cả về "sai
số tuyệt đối" (MAE/RMSE, dễ diễn giải theo đơn vị gốc) và "mức độ giải thích phương sai"
(R², dễ so sánh giữa các mô hình khác nhau).

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là bước đánh giá ngay sau huấn luyện Regression (Bài 8), quyết định mô hình candidate tốt
nhất cho Model Registry (Bài 22).

## 13. Input là gì

Giá trị dự đoán của mô hình và giá trị thật trên tập test.

## 14. Output là gì

4 con số MAE, MSE, RMSE, R² cho mỗi thuật toán.

## 15. Output được chuyển cho module nào tiếp theo

Dùng để chọn candidate tốt nhất (Bài 10, Bài 22); giá trị dự đoán hiển thị trên Dashboard.

## 16. Ưu điểm

Bộ 4 chỉ số bổ trợ cho nhau: MAE dễ hiểu theo đơn vị gốc, RMSE nhạy với sai số lớn, R²
dễ so sánh tương đối giữa các mô hình.

## 17. Nhược điểm

R² có thể gây hiểu lầm nếu người đọc không hiểu bản chất dữ liệu đứng sau nó (chính là
vấn đề trọng tâm của bài này).

## 18. Limitation thực tế của project

**Đây là limitation quan trọng nhất của toàn bộ phần ML**: R² đo trên tập dữ liệu mẫu
tổng hợp cao không phải vì mô hình "giỏi dự đoán tương lai," mà vì target `diem_ky_sau`
được TÍNH TRỰC TIẾP từ công thức tuyến tính của chính các feature đầu vào (xem Bài 3).

## 19. Hội đồng có thể hỏi gì

"R² của mô hình hồi quy rất cao, gần như hoàn hảo — bạn giải thích thế nào?"

## 20. Câu trả lời ngắn 20–40 giây

"R² cao vì bản chất tập dữ liệu mẫu: target `diem_ky_sau` được tính bằng công thức
`0.60*diem_ky_nay + 0.15*diem_giua_ky + 0.10*diem_du_an + 0.10*(ty_le_diem_danh*10) +
0.05*(so_gio_hoc_tuan/3.5)` cộng một nhiễu rất nhỏ (σ=0.08), sau đó bị giới hạn trong
khoảng ±1.5 quanh điểm hiện tại. Vì target gần như là một hàm tuyến tính của chính các
feature đầu vào, bất kỳ mô hình hồi quy nào đủ mạnh cũng sẽ học ra R² rất cao. Đây là đặc
điểm của dữ liệu tổng hợp, không phải bằng chứng cho khả năng dự đoán chính xác điểm số
sinh viên thật ngoài đời."

## 21. Câu trả lời chi tiết

Đọc đầy đủ công thức và trọng số ở Bài 3, nhấn mạnh: (a) trọng số 0.60 áp đảo lên
`diem_ky_nay`, (b) nhiễu rất nhỏ σ=0.08 không đủ để "che" quan hệ tuyến tính, (c) bước
clamp ±1.5 càng siết chặt tương quan thêm. Khẳng định đây là vấn đề tách biệt hoàn toàn
với data leakage trong quy trình huấn luyện (đã kiểm chứng đúng ở Bài 5).

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu biết trước R² sẽ cao vì cách sinh dữ liệu, tại sao vẫn dùng bộ dữ liệu này để demo?"

## 23. Cách trả lời câu vặn

"Vì mục tiêu của bộ dữ liệu mẫu là minh họa toàn bộ pipeline kỹ thuật — tiền xử lý, chống
leakage, GridSearchCV, so sánh 4 thuật toán — một cách nhất quán và có thể tái lập, khi
không có quyền truy cập dữ liệu sinh viên thật. Em không dùng con số R² này để khẳng định
chất lượng dự đoán trong thực tế, và đã ghi rõ điều này trong tài liệu bảo vệ cũng như
banner cảnh báo 'dữ liệu demo' hiển thị ngay trên giao diện khi người dùng xem kết quả."

## 24. Những câu không được nói

- "R² gần 1 chứng minh mô hình có thể dự đoán chính xác điểm số sinh viên thật."
- "R² cao là do data leakage." (Sai — đây là vấn đề khác, xem Bài 5 và Bài 3.)

## 25. 10 câu tự kiểm tra

1. MAE đo cái gì?
2. MSE khác MAE ở điểm nào?
3. RMSE tại sao phải lấy căn bậc hai của MSE?
4. Công thức R² là gì?
5. R² = 1 nghĩa là gì? R² = 0 nghĩa là gì?
6. R² có thể âm không? Khi nào?
7. Vì sao R² trên tập dữ liệu mẫu EduDSS lại cao bất thường?
8. Đây có phải là data leakage không? Vì sao?
9. `ȳ` trong công thức R² là gì?
10. Nếu dùng dữ liệu sinh viên thật, R² có còn cao như vậy không? Vì sao?

## 26. Đáp án riêng

1. Trung bình trị tuyệt đối sai lệch giữa dự đoán và giá trị thật.
2. MSE bình phương sai lệch trước khi lấy trung bình, phạt nặng sai số lớn hơn.
3. Để đưa đơn vị về lại thang gốc (vì MSE đã bị bình phương đơn vị).
4. `1 - (Σ(y_i-ŷ_i)² / Σ(y_i-ȳ)²)`.
5. R²=1 là dự đoán hoàn hảo; R²=0 là mô hình tệ ngang với đoán bằng giá trị trung bình.
6. Có — khi mô hình dự đoán tệ hơn cả việc đoán mù bằng trung bình.
7. Vì target được tính trực tiếp từ công thức tuyến tính của các feature đầu vào, cộng
   nhiễu rất nhỏ, rồi bị clamp hẹp.
8. Không — data leakage là vấn đề về quy trình huấn luyện (đã được chống đúng ở Bài 5);
   đây là vấn đề về bản chất cách sinh dữ liệu mẫu.
9. Giá trị trung bình của toàn bộ target thật trong tập test.
10. Không — dữ liệu thật sẽ có nhiều nhiễu và yếu tố phi tuyến không được thu thập, nên
    R² dự kiến sẽ thấp hơn đáng kể.

## 27. 5 CÂU PHẢI THUỘC

1. "MAE/MSE/RMSE càng nhỏ càng tốt, R² càng gần 1 càng tốt về mặt toán học."
2. "R² cao trên dữ liệu mẫu là do công thức sinh target tuyến tính, không phải do mô
   hình xuất sắc."
3. "Đây KHÔNG phải data leakage — leakage là vấn đề quy trình, đây là vấn đề bản chất dữ
   liệu tổng hợp."
4. "Công thức R²: 1 trừ (tổng sai số bình phương của mô hình chia tổng sai số bình
   phương nếu chỉ đoán bằng trung bình)."
5. "R² cao trên tập mẫu không được dùng làm bằng chứng cho hiệu năng thực tế trên dữ liệu
   sinh viên thật."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- MAE — Sai số tuyệt đối trung bình
- MSE/RMSE — Sai số bình phương trung bình / căn bậc hai của nó
- R² (R-squared) — Hệ số xác định
- Variance explained — Phương sai được giải thích
- Synthetic-data artifact — Hiện tượng do bản chất dữ liệu tổng hợp gây ra
