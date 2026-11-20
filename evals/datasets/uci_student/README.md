# UCI Student Performance (dữ liệu học sinh THẬT, công khai)

- **Nguồn:** P. Cortez, A. Silva (2008). *Using Data Mining to Predict Secondary School Student
  Performance.* UCI Machine Learning Repository, https://doi.org/10.24432/C5TG7T
- **Giấy phép:** Creative Commons Attribution 4.0 (CC BY 4.0), được dùng và phân phối lại kèm
  ghi nguồn.
- **Tệp:**
  - `student-por.csv`: 649 học sinh, môn tiếng Bồ Đào Nha.
  - Bản môn Toán (`student-mat.csv`, 395 học sinh) đã có sẵn ở `app/dữ liệu/`, nên không lưu lại ở đây.
  - Định dạng gốc của UCI, phân cách `;`. Bản sao lấy từ github.com/avehtari/ROS-Examples (commit
    d35682d), giống hệt bản gốc (git blob 2e461960…).
- **Thang điểm:** G1, G2, G3 là điểm kỳ 1, kỳ 2 và cuối năm, thang 0–20; **< 10 là trượt**.

Bộ eval (`evals/run_evals.py`, phần `ml_real`) dùng dữ liệu này để đo trainer của EduDSS trên học
sinh thật:
- Hai thời điểm cảnh báo: **đầu kỳ** (chưa có điểm nào) và **giữa kỳ** (đã có G1). Không bao giờ
  dùng G2/G3 làm đặc trưng.
- Đo AUC, recall và precision cho nhóm có nguy cơ, độ tin cậy xác suất (Brier, ECE).
- Đo chênh lệch giữa các nhóm: giới tính, thành thị/nông thôn.
- So với quy tắc đơn giản: "đã từng trượt môn" và "G1 < 10".

Đây là dữ liệu trường phổ thông Bồ Đào Nha năm 2005–2006, không phải sinh viên Việt Nam: kết quả
cho thấy pipeline làm việc với dữ liệu thật, không phải độ chính xác cho một trường cụ thể.
