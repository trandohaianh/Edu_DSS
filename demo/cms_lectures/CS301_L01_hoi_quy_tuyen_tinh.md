# Bài 1 — Hồi quy tuyến tính: dự đoán điểm học kỳ sau

Môn: CS301 — Học máy ứng dụng trong giáo dục
Mục tiêu bài học: Hiểu mô hình hồi quy tuyến tính, cách mô hình học hệ số từ dữ liệu, và cách đọc kết quả khi dự đoán điểm học kỳ sau của sinh viên.

## 1. Bài toán hồi quy là gì?

Hồi quy (regression) là bài toán dự đoán một **giá trị số liên tục**. Trong EduDSS, ví dụ điển hình là dự đoán **điểm học kỳ sau** (thang 0–10) của một sinh viên từ các thông tin đã có: điểm học kỳ này, tỷ lệ điểm danh, số giờ tự học mỗi tuần, điểm giữa kỳ, điểm dự án.

Khác với phân loại (classification) — dự đoán một **nhãn** như "Giỏi", "Khá", "Trung bình" — hồi quy trả về một con số, ví dụ 7.24.

## 2. Mô hình hồi quy tuyến tính

Mô hình giả định điểm cần dự đoán là tổng có trọng số của các đặc trưng:

    ŷ = w0 + w1·x1 + w2·x2 + ... + wn·xn

Trong đó:
- ŷ (đọc là "y mũ") là giá trị dự đoán, ví dụ điểm học kỳ sau.
- x1, x2, ..., xn là các đặc trưng đầu vào, ví dụ x1 = điểm học kỳ này, x2 = tỷ lệ điểm danh.
- w1, ..., wn là các **hệ số (trọng số)**: cho biết khi đặc trưng tăng 1 đơn vị (các đặc trưng khác giữ nguyên) thì dự đoán thay đổi bao nhiêu.
- w0 là **hệ số chặn (intercept)**: giá trị dự đoán khi mọi đặc trưng bằng 0.

Ví dụ minh họa: nếu mô hình học được
    điểm kỳ sau = 0.5 + 0.8 × điểm kỳ này + 0.01 × tỷ lệ điểm danh (%)
thì một sinh viên có điểm kỳ này 7.0 và điểm danh 80% được dự đoán:
    0.5 + 0.8 × 7.0 + 0.01 × 80 = 0.5 + 5.6 + 0.8 = 6.9

Hệ số 0.8 nghĩa là: mỗi 1 điểm tăng ở học kỳ này đi kèm khoảng 0.8 điểm tăng ở học kỳ sau. Lưu ý đây là **mối liên hệ thống kê**, không phải quan hệ nhân quả.

## 3. Mô hình "học" như thế nào? — Bình phương tối thiểu

Mô hình chọn các hệ số sao cho **sai số bình phương trung bình (MSE)** trên dữ liệu huấn luyện nhỏ nhất:

    MSE = (1/m) · Σ (yi − ŷi)²

với m là số sinh viên trong tập huấn luyện, yi là điểm thật, ŷi là điểm dự đoán. Bình phương giúp sai số âm và dương không triệt tiêu nhau và phạt nặng các dự đoán lệch nhiều. Phương pháp này gọi là **bình phương tối thiểu (Ordinary Least Squares — OLS)**.

## 4. Tiền xử lý trước khi huấn luyện

- **Chuẩn hóa (StandardScaler)**: đưa các đặc trưng về cùng thang (trung bình 0, độ lệch chuẩn 1) để so sánh được độ lớn các hệ số.
- **Xử lý giá trị thiếu**: điền trung vị (median) cho cột số.
- Tiền xử lý phải được **học trên tập huấn luyện** rồi mới áp dụng cho tập kiểm tra — nếu học trên toàn bộ dữ liệu sẽ gây **rò rỉ dữ liệu (data leakage)**, làm kết quả đánh giá đẹp hơn thực tế.

## 5. Đọc kết quả

- **R² (hệ số xác định)**: tỷ lệ biến thiên của điểm thật mà mô hình giải thích được. R² = 1 là hoàn hảo, R² = 0 nghĩa là không tốt hơn việc luôn dự đoán điểm trung bình.
- **MAE**: sai số tuyệt đối trung bình, cùng đơn vị với điểm. MAE = 0.3 nghĩa là trung bình mô hình lệch 0.3 điểm.
- **RMSE**: căn bậc hai của MSE, phạt nặng các dự đoán lệch lớn — quan trọng trong cảnh báo sớm, vì dự đoán sai 3 điểm cho một sinh viên có nguy cơ nguy hiểm hơn nhiều so với sai 0.3 điểm.

## 6. Hạn chế

- Chỉ nắm bắt được quan hệ **tuyến tính**. Nếu điểm danh dưới 50% làm điểm sụt mạnh nhưng trên 80% thì gần như không ảnh hưởng, mô hình tuyến tính sẽ mô tả kém.
- Nhạy với **ngoại lai (outlier)**: vài sinh viên có điểm bất thường có thể kéo lệch hệ số.
- Các đặc trưng **tương quan mạnh với nhau** (đa cộng tuyến) làm hệ số khó diễn giải.

## 7. Tóm tắt

Hồi quy tuyến tính đơn giản, nhanh và dễ giải thích — vì vậy luôn là **mô hình mốc (baseline)** đầu tiên để so sánh. Khi dữ liệu có quan hệ phi tuyến, ta chuyển sang các mô hình dạng cây như Random Forest (Bài 2).
