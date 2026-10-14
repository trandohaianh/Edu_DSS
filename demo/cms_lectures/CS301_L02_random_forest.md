# Bài 2 — Cây quyết định và Random Forest: xếp loại học lực

Môn: CS301 — Học máy ứng dụng trong giáo dục
Mục tiêu bài học: Hiểu cách cây quyết định đưa ra dự đoán, vì sao một cây đơn lẻ dễ quá khớp, và cách Random Forest kết hợp nhiều cây để dự đoán ổn định hơn khi xếp loại học lực sinh viên.

## 1. Cây quyết định (Decision Tree)

Cây quyết định dự đoán bằng một chuỗi câu hỏi có/không về đặc trưng. Ví dụ xếp loại học lực:

    Điểm học kỳ này ≥ 8.0?
      ├─ Có  → Tỷ lệ điểm danh ≥ 85%? → Có: "Giỏi"   | Không: "Khá"
      └─ Không → Điểm học kỳ này ≥ 6.5? → Có: "Khá" | Không: "Trung bình"

- Mỗi **nút trong** là một câu hỏi (phép tách) trên một đặc trưng.
- Mỗi **lá** là kết quả dự đoán.
- Khi huấn luyện, thuật toán chọn phép tách làm các nhóm con **thuần nhất** nhất về nhãn — đo bằng **độ tạp Gini** (Gini impurity) hoặc **entropy**.

Ưu điểm: dễ hiểu, giải thích được bằng luật "nếu… thì…", không cần chuẩn hóa dữ liệu, nắm được quan hệ phi tuyến.

## 2. Vấn đề quá khớp (overfitting)

Nếu để cây phát triển không giới hạn, nó có thể tách tới khi mỗi lá chỉ chứa 1–2 sinh viên — **học thuộc** cả nhiễu của tập huấn luyện. Khi đó độ chính xác trên tập huấn luyện gần 100% nhưng trên sinh viên mới lại thấp. Đó là **quá khớp**.

Các tham số kiểm soát độ phức tạp:
- **max_depth**: độ sâu tối đa của cây.
- **min_samples_split**: số mẫu tối thiểu để được tách tiếp một nút.
- **min_samples_leaf**: số mẫu tối thiểu ở mỗi lá.

## 3. Random Forest — "rừng" nhiều cây

Random Forest huấn luyện **nhiều cây quyết định** (ví dụ 100 hoặc 200 cây) rồi **bỏ phiếu**:
- Phân loại: lấy nhãn được nhiều cây chọn nhất.
- Hồi quy: lấy trung bình dự đoán của các cây.

Hai nguồn ngẫu nhiên làm các cây khác nhau:
1. **Bagging (bootstrap)**: mỗi cây học trên một mẫu lấy ngẫu nhiên có hoàn lại từ tập huấn luyện.
2. **Chọn ngẫu nhiên đặc trưng**: tại mỗi phép tách, cây chỉ được xét một tập con ngẫu nhiên các đặc trưng.

Vì các cây mắc lỗi **khác nhau**, khi lấy trung bình các lỗi ngẫu nhiên triệt tiêu bớt — mô hình **ổn định hơn và ít quá khớp hơn** một cây đơn lẻ.

## 4. Mất cân bằng lớp

Trong dữ liệu học tập, lớp "Yếu" thường rất ít (có thể chỉ vài chục trên hàng nghìn sinh viên). Mô hình dễ bỏ qua lớp hiếm vì đoán sai nó ít ảnh hưởng tới độ chính xác tổng. Cách xử lý:
- **class_weight="balanced"**: tăng trọng số lỗi cho lớp hiếm.
- **SMOTE**: sinh thêm mẫu tổng hợp cho lớp hiếm (chỉ trên tập huấn luyện).
- Đánh giá bằng **F1-macro** thay vì chỉ nhìn Accuracy (xem Bài 3).

## 5. Độ quan trọng đặc trưng

Random Forest cho biết **độ quan trọng (feature importance)** của từng đặc trưng: đặc trưng nào giúp giảm độ tạp nhiều nhất qua các phép tách. Ví dụ: "điểm học kỳ này" quan trọng nhất, sau đó là "tỷ lệ điểm danh". Đây là **đóng góp vào dự đoán**, không phải nguyên nhân.

## 6. Dò tham số (tuning)

Giá trị tốt nhất của n_estimators, max_depth… được chọn bằng **GridSearchCV**: thử từng tổ hợp tham số, đánh giá bằng kiểm định chéo (cross-validation) **chỉ trên tập huấn luyện**, rồi chọn tổ hợp có điểm cao nhất. Tập kiểm tra được giữ riêng để đánh giá cuối cùng.

## 7. Tóm tắt

Cây quyết định dễ hiểu nhưng dễ quá khớp. Random Forest kết hợp nhiều cây được huấn luyện ngẫu nhiên để dự đoán ổn định hơn, xử lý tốt quan hệ phi tuyến và cho biết đặc trưng nào quan trọng.
