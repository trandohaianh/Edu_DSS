# Bài 3 — Dữ liệu, Feature, Target, và Dữ liệu tổng hợp (Synthetic Data)

## 1. Mục tiêu buổi học

Hiểu rõ feature (đặc trưng) và target (biến mục tiêu) là gì, dữ liệu trong EduDSS đến từ
đâu, và — quan trọng nhất — hiểu **chính xác công thức sinh dữ liệu tổng hợp**, vì đây là
gốc rễ giải thích cho hiện tượng "R² cao bất thường" ở Bài 9.

## 2. Kiến thức cần nhớ trước

Bài 1, Bài 2.

## 3. Giải thích từ con số 0

Khi bạn muốn dạy máy tính "đoán" một điều gì đó, bạn cần hai loại thông tin:
- **Feature (đặc trưng)**: những thông tin đầu vào máy tính dùng để đoán — ví dụ điểm
  giữa kỳ, số giờ học mỗi tuần, tỷ lệ điểm danh.
- **Target (biến mục tiêu)**: cái mà máy tính phải đoán ra — ví dụ điểm kỳ sau, hoặc
  nhãn "có rủi ro / không rủi ro".

Máy học từ rất nhiều dòng dữ liệu có sẵn cả feature và target (gọi là **training data —
dữ liệu huấn luyện**) để tìm ra quy luật, rồi áp dụng quy luật đó cho dữ liệu mới.

## 4. Giải thích kỹ thuật

Dữ liệu mẫu (sample dataset) trong EduDSS được sinh ra bởi hàm
`generate_data()`/`generate_lms_data()` trong `dss/core/data_helpers.py` — đây là
**dữ liệu tổng hợp (synthetic data)**, KHÔNG phải dữ liệu thu thập từ sinh viên thật.
Các feature gồm: `diem_giua_ky`, `diem_ky_nay`, `diem_du_an`, `ty_le_diem_danh`,
`so_gio_hoc_tuan`, `so_lan_dang_nhap`, `ty_le_hoan_thanh_bai_tap`,
`ngay_hoat_dong_gan_nhat`. Target cho bài toán hồi quy là `diem_ky_sau` (điểm kỳ tiếp
theo); target cho bài toán phân loại là một nhãn rủi ro được suy ra từ ngưỡng điểm.

Điều quan trọng nhất: `diem_ky_sau` **không phải một quan sát độc lập trong thực tế** —
nó được TÍNH RA bằng công thức tuyến tính có trọng số từ chính các feature khác cùng
dòng, cộng thêm nhiễu (noise) nhỏ, rồi bị giới hạn (clamp) trong khoảng hẹp quanh
`diem_ky_nay`.

## 5. Ví dụ cực dễ hiểu

Giống như bạn tạo ra một "bài kiểm tra giả" mà đáp án được tính sẵn bằng công thức: nếu
đề bài ghi rõ "điểm cuối = 60% điểm giữa kỳ + 15% điểm dự án + ...", thì tất nhiên ai
đoán đúng công thức đó sẽ đoán trúng gần như tuyệt đối — không phải vì họ giỏi dự đoán
tương lai, mà vì đáp án vốn được sinh ra từ chính đề bài.

## 6. Ví dụ trực tiếp trong EduDSS

Công thức thật trong code (`dss/core/data_helpers.py::generate_data()`):
```
diem_ky_sau = 0.60*diem_ky_nay + 0.15*diem_giua_ky + 0.10*diem_du_an
            + 0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5)
            + noise(σ=0.08)
```
sau đó cắt về khoảng [0,10], rồi tiếp tục giới hạn (clamp) trong khoảng ±1.5 quanh
`diem_ky_nay`. Chính bản thân code này đã có docstring tự cảnh báo: không được coi đây là
bằng chứng độ chính xác dự đoán thực tế.

## 7. Luồng xử lý thực tế trong project

```
generate_data()/generate_lms_data() sinh DataFrame
  → gắn nhãn df.attrs["data_source_type"] = "synthetic"
  → ml_hub.py đọc nhãn này để hiển thị banner "dữ liệu demo" cho người dùng
  → dữ liệu này được dùng làm input cho toàn bộ chuỗi Classification/Regression (Bài 6, 8)
```

## 8. Công thức nếu có

```
diem_ky_sau = 0.60*diem_ky_nay + 0.15*diem_giua_ky + 0.10*diem_du_an
            + 0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5) + noise(σ=0.08)
```

## 9. Giải thích từng ký hiệu trong công thức

- `diem_ky_nay` — điểm hiện tại của sinh viên trong kỳ này (feature đầu vào), trọng số
  0.60 — chiếm đa số ảnh hưởng.
- `diem_giua_ky` — điểm giữa kỳ, trọng số 0.15.
- `diem_du_an` — điểm dự án, trọng số 0.10.
- `ty_le_diem_danh` — tỷ lệ điểm danh (0 đến 1), nhân 10 để đưa về thang điểm 10, trọng
  số 0.10.
- `so_gio_hoc_tuan` — số giờ tự học mỗi tuần, chia cho 3.5 để chuẩn hóa về thang tương
  đương, trọng số 0.05.
- `noise(σ=0.08)` — nhiễu ngẫu nhiên có độ lệch chuẩn (standard deviation) rất nhỏ 0.08,
  mô phỏng sự biến động tự nhiên nhưng không đủ lớn để "che" đi công thức tuyến tính bên
  trên.
- Bước clip [0,10] — không cho điểm âm hoặc vượt quá thang điểm 10.
- Bước clamp ±1.5 quanh `diem_ky_nay` — buộc điểm kỳ sau không được lệch quá xa điểm kỳ
  hiện tại, càng làm tương quan giữa target và feature chính thêm chặt chẽ.

## 10. Cách đọc kết quả

Khi thấy một mô hình hồi quy đạt R² rất cao trên tập dữ liệu mẫu này, bạn phải đọc nó là:
"mô hình học đúng công thức tuyến tính đã được dùng để sinh dữ liệu" — không phải "mô
hình có khả năng dự đoán chính xác điểm số sinh viên thật ngoài đời."

## 11. Vì sao project dùng phương pháp này

Vì đồ án không có quyền truy cập dữ liệu sinh viên thật (vấn đề pháp lý và quyền riêng
tư), dữ liệu tổng hợp cho phép minh họa toàn bộ pipeline ML/DSS một cách nhất quán, có
thể tái tạo (reproducible), mà không vi phạm quyền riêng tư của ai.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là **điểm khởi đầu của Chuỗi 1**: `Dữ liệu sinh viên → Tiền xử lý → Classification/
Regression → SHAP → Diagnosis → Recommendation → Learning Plan → Hành động`.

## 13. Input là gì

Không có input từ bên ngoài — dữ liệu được sinh ra hoàn toàn bằng code Python
(`generate_data()`), có thể có tham số seed để tái lập.

## 14. Output là gì

Một DataFrame (bảng dữ liệu) gồm các cột feature và target, gắn nhãn nguồn gốc synthetic.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho bước Tiền xử lý dữ liệu (Bài 4), sau đó vào Classification/Regression (Bài 6, 8).

## 16. Ưu điểm

Không vi phạm quyền riêng tư; có thể tái tạo; đủ để minh họa toàn bộ pipeline kỹ thuật.

## 17. Nhược điểm

Không phản ánh sự phức tạp, nhiễu và các yếu tố phi tuyến tính của dữ liệu học tập thật;
không thể dùng để khẳng định hiệu năng thực tế của mô hình trên sinh viên thật.

## 18. Limitation thực tế của project

Chưa có bất kỳ dữ liệu sinh viên thật nào được sử dụng ở bất kỳ đâu trong hệ thống — đây
là giới hạn quan trọng nhất cần thừa nhận thẳng thắn trước hội đồng.

## 19. Hội đồng có thể hỏi gì

"R² của mô hình hồi quy rất cao — có phải dữ liệu bị rò rỉ (leak) không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không phải rò rỉ dữ liệu theo nghĩa kỹ thuật — pipeline có cơ chế chống rò rỉ riêng
(Bài 5). Nguyên nhân R² cao là vì target của tập dữ liệu MẪU được sinh ra bằng chính một
công thức tuyến tính từ các feature khác, cộng nhiễu rất nhỏ — đây là đặc điểm của dữ
liệu tổng hợp, không phải bằng chứng cho hiệu năng thực tế trên dữ liệu thật."

## 21. Câu trả lời chi tiết

Đọc thuộc công thức ở mục 8–9, nhấn mạnh trọng số 0.60 áp đảo lên `diem_ky_nay`, nhiễu
σ=0.08 rất nhỏ, và bước clamp ±1.5 càng siết chặt tương quan. Đồng thời khẳng định:
`filter_leakage_features()` (Bài 5) là một cơ chế RIÊNG BIỆT, độc lập với việc dữ liệu
mẫu này vốn dĩ tương quan cao vì cách nó được sinh ra.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy nếu dùng dữ liệu thật, em có tin R² vẫn cao như vậy không?"

## 23. Cách trả lời câu vặn

"Không — với dữ liệu thật, mối quan hệ giữa các feature và điểm số tương lai sẽ nhiễu và
phi tuyến hơn rất nhiều, có nhiều yếu tố không được thu thập (tâm lý, sức khỏe, hoàn cảnh
gia đình...). Em kỳ vọng R² sẽ thấp hơn đáng kể, và đó là lý do em không dùng con số R²
trên tập mẫu này như một tuyên bố về chất lượng mô hình trong thực tế."

## 24. Những câu không được nói

- "Mô hình đạt độ chính xác X% trên dữ liệu sinh viên thật." (Không có dữ liệu thật.)
- "R² cao chứng minh mô hình rất tốt." (Sai — nó phản ánh cách dữ liệu mẫu được sinh ra.)

## 25. 10 câu tự kiểm tra

1. Feature và target khác nhau như thế nào?
2. Dữ liệu mẫu trong EduDSS được sinh ra ở hàm nào, file nào?
3. Trọng số lớn nhất trong công thức `diem_ky_sau` thuộc về feature nào?
4. Độ lệch chuẩn của nhiễu trong công thức là bao nhiêu?
5. Sau khi tính, giá trị `diem_ky_sau` bị giới hạn (clamp) trong khoảng nào quanh
   `diem_ky_nay`?
6. Vì sao dữ liệu tổng hợp lại làm R² cao bất thường?
7. Dữ liệu tổng hợp có vi phạm quyền riêng tư không? Vì sao?
8. Nhãn `data_source_type` dùng để làm gì?
9. Dữ liệu này chảy tiếp vào bước nào sau khi được sinh ra?
10. Vì sao không nên dùng R² trên tập dữ liệu này để khẳng định chất lượng mô hình thực tế?

## 26. Đáp án riêng

1. Feature là đầu vào để đoán, target là cái cần đoán ra.
2. `generate_data()`/`generate_lms_data()` trong `dss/core/data_helpers.py`.
3. `diem_ky_nay`, trọng số 0.60.
4. σ = 0.08.
5. ±1.5 quanh `diem_ky_nay`.
6. Vì target được tính trực tiếp từ công thức tuyến tính của các feature khác, không
   phải một quan sát độc lập.
7. Không — vì hoàn toàn do máy tính sinh ra, không có dữ liệu cá nhân thật.
8. Để `ml_hub.py` hiển thị banner cảnh báo dữ liệu demo cho người dùng.
9. Bước tiền xử lý dữ liệu (Bài 4).
10. Vì R² cao phản ánh công thức sinh dữ liệu, không phản ánh khả năng dự đoán trên dữ
    liệu thật độc lập.

## 27. 5 CÂU PHẢI THUỘC

1. "Dữ liệu mẫu là 100% tổng hợp, sinh bởi `generate_data()`, không phải dữ liệu sinh
   viên thật."
2. "Target `diem_ky_sau` được tính bằng công thức tuyến tính có trọng số 0.60 lên
   `diem_ky_nay`, cộng nhiễu σ=0.08, rồi clamp ±1.5."
3. "R² cao trên tập mẫu là hệ quả của cách sinh dữ liệu, không phải bằng chứng hiệu năng
   thực tế."
4. "Chưa có dữ liệu sinh viên thật nào được dùng ở bất kỳ đâu trong hệ thống."
5. "Đây là vấn đề khác hoàn toàn với data leakage — pipeline chống rò rỉ vẫn hoạt động
   độc lập và đúng đắn (Bài 5)."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Feature — Đặc trưng (đầu vào)
- Target — Biến mục tiêu (đầu ra cần đoán)
- Synthetic data — Dữ liệu tổng hợp
- Noise (σ) — Nhiễu (độ lệch chuẩn)
- Clamp/Clip — Giới hạn giá trị trong một khoảng
