# Bài 3 — Đánh giá mô hình: chia dữ liệu, kiểm định chéo và các chỉ số

Môn: CS301 — Học máy ứng dụng trong giáo dục
Mục tiêu bài học: Biết cách chia dữ liệu và kiểm định chéo đúng để không tự lừa mình, chọn đúng chỉ số cho bài toán hồi quy và phân loại, và đọc ma trận nhầm lẫn.

## 1. Vì sao phải có tập kiểm tra?

Một mô hình có thể dự đoán rất tốt trên chính dữ liệu đã học nhưng kém trên sinh viên mới. Vì vậy ta chia dữ liệu:
- **Tập huấn luyện (train)**, thường 80%: dùng để học hệ số/tham số.
- **Tập kiểm tra (test)**, thường 20%: chỉ dùng **một lần** ở cuối để ước lượng hiệu năng trên dữ liệu chưa thấy.

Với phân loại mất cân bằng, nên chia **phân tầng (stratified)** để tỷ lệ các lớp trong train và test giống nhau.

## 2. Kiểm định chéo K-fold (cross-validation)

Để chọn tham số mà không đụng vào tập kiểm tra, ta chia tập huấn luyện thành K phần (fold):
1. Lần lượt lấy 1 phần làm tập đánh giá, K−1 phần còn lại để huấn luyện.
2. Lặp K lần, lấy **trung bình** và **độ lệch chuẩn** của điểm.

K thường là 5. Với dữ liệu rất lớn (hàng chục nghìn sinh viên), K = 3 đã đủ: mỗi fold vẫn có hàng nghìn mẫu nên ước lượng ổn định mà huấn luyện nhanh hơn.

**Rò rỉ dữ liệu (data leakage)** xảy ra khi thông tin từ tập đánh giá lọt vào lúc huấn luyện, ví dụ chuẩn hóa trên toàn bộ dữ liệu trước khi chia, hoặc dùng một đặc trưng được tính ra từ chính nhãn cần dự đoán. Kết quả khi đó đẹp nhưng sai.

## 3. Chỉ số cho hồi quy

- **MAE** = (1/m) Σ |yi − ŷi| — sai số tuyệt đối trung bình, dễ hiểu ("lệch trung bình 0.3 điểm").
- **RMSE** = √[(1/m) Σ (yi − ŷi)²] — phạt nặng sai số lớn. EduDSS dùng RMSE để **xếp hạng** mô hình hồi quy vì trong cảnh báo sớm, một dự đoán lệch lớn nguy hiểm hơn nhiều dự đoán lệch nhỏ.
- **R²** = 1 − Σ(yi − ŷi)² / Σ(yi − ȳ)² — tỷ lệ biến thiên được giải thích. R² cao trên dữ liệu mô phỏng chưa chắc phản ánh độ chính xác trên sinh viên thật.

## 4. Chỉ số cho phân loại

Cho một lớp, ví dụ "Yếu":
- **TP** (đúng dương): sinh viên thật sự Yếu, mô hình đoán Yếu.
- **FP** (dương giả): không Yếu nhưng bị đoán Yếu.
- **FN** (âm giả): thật sự Yếu nhưng mô hình bỏ sót.

- **Accuracy** = số dự đoán đúng / tổng số. Dễ gây hiểu lầm khi lớp mất cân bằng: nếu 99% sinh viên không Yếu, mô hình luôn đoán "không Yếu" vẫn đạt 99%.
- **Precision** = TP / (TP + FP): trong những em bị cảnh báo, bao nhiêu em thật sự cần hỗ trợ.
- **Recall** = TP / (TP + FN): trong những em thật sự cần hỗ trợ, mô hình phát hiện được bao nhiêu. Với cảnh báo sớm, **recall cao rất quan trọng** — bỏ sót một sinh viên có nguy cơ tốn kém hơn cảnh báo nhầm.
- **F1** = 2 · Precision · Recall / (Precision + Recall): cân bằng hai chỉ số trên.
- **F1-macro**: trung bình F1 của **tất cả các lớp, mỗi lớp trọng số như nhau** — lớp hiếm được coi trọng ngang lớp đông. EduDSS dùng F1-macro để xếp hạng mô hình phân loại.

## 5. Ma trận nhầm lẫn (confusion matrix)

Bảng có hàng là nhãn **thực tế**, cột là nhãn **dự đoán**. Đường chéo là các dự đoán đúng; các ô ngoài đường chéo cho biết mô hình hay nhầm lớp nào với lớp nào, ví dụ hay nhầm "Khá" thành "Giỏi". Đây là công cụ tốt nhất để thấy mô hình sai **ở đâu**, không chỉ sai **bao nhiêu**.

## 6. Mô hình mốc (baseline)

Luôn so sánh với một mô hình "ngây thơ": hồi quy luôn đoán điểm trung bình, phân loại luôn đoán lớp đông nhất. Nếu mô hình phức tạp không tốt hơn rõ rệt so với mốc này thì nó chưa có giá trị.

## 7. Tóm tắt

Chia train/test, chọn tham số bằng kiểm định chéo chỉ trên tập train, chọn chỉ số phù hợp (RMSE cho hồi quy cảnh báo sớm, F1-macro cho phân loại mất cân bằng), đọc ma trận nhầm lẫn, và luôn so với mô hình mốc.
