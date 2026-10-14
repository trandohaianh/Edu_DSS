# Ôn tập 30 phút trước khi vào phòng bảo vệ

Chỉ đọc file này. Không mở file nào khác. Mục tiêu: nạp lại đúng những gì dễ quên nhất
ngay trước giờ G.

## 5 câu nói mở đầu nếu được hỏi tổng quan

1. "EduDSS là hệ thống hỗ trợ ra quyết định học tập 3 vai trò — không chỉ là công cụ dự
   đoán, mà có đủ chuỗi Prediction + Evidence + Explanation + Diagnosis + Recommendation
   + Action support."
2. "Toàn bộ dữ liệu là tổng hợp — em minh bạch điều này ngay từ đầu."
3. "Có 4 thuật toán phân loại và 4 thuật toán hồi quy, mỗi bài toán có lưới tham số riêng."
4. "Có một pipeline RAG thật, đã kiểm chứng live với trích dẫn thật."
5. "445/445 test pass, 0 lỗi P0 còn tồn đọng, và em công khai đầy đủ các giới hạn còn
   lại."

## 4 con số không được nhầm (đọc to 2 lần)

- Random Forest **Classification**: 24 cấu hình / 120 fit.
- Random Forest **Regression**: 12 cấu hình / 60 fit.
- XGBoost **Classification**: KHÔNG GridSearchCV, 1 fit.
- XGBoost **Regression**: CÓ GridSearchCV, 18 cấu hình / 90 fit.

## 3 câu "cứu mạng" nếu bị hỏi bất ngờ về R²

"R² cao trên tập mẫu là vì target được TÍNH TRỰC TIẾP từ công thức tuyến tính của các
feature khác (0.60×điểm hiện tại + các trọng số khác + nhiễu rất nhỏ), cộng thêm bị
giới hạn (clamp) trong khoảng hẹp. Đây là đặc điểm của DỮ LIỆU TỔNG HỢP, KHÔNG PHẢI data
leakage — cơ chế chống leakage (split trước, tiền xử lý sau) vẫn đúng và độc lập với vấn
đề này."

## 3 câu "cứu mạng" nếu bị hỏi về LMS/CMS/PostgreSQL

"Không có kết nối LMS/CMS ngoài thật — chỉ có lớp trừu tượng (abstraction) sẵn sàng.
Không dùng PostgreSQL làm vector store thật — PgVectorStore có kết nối và schema thật
nhưng CRUD là stub; vector store đang hoạt động thật là LocalVectorStore, file-based.
Toàn bộ dữ liệu ứng dụng khác cũng là file-based (JSON/CSV/joblib), không có RDBMS đứng
sau."

## 3 câu "cứu mạng" nếu bị hỏi về SHAP/K-Means/Career Fit

"SHAP giải thích đóng góp của feature vào dự đoán của MÔ HÌNH, không chứng minh nhân quả
trong thực tế. K-Means là học không giám sát, chỉ nhóm sinh viên giống nhau, không dự
đoán tương lai ai cả. Career Fit và Career Readiness là điểm số heuristic có trọng số
trên 6 chiều, không phải xác suất thống kê."

## 3 câu "cứu mạng" nếu bị hỏi về giới hạn/test

"445/445 test pass (baseline mới nhất sau lượt hoàn thiện trước bảo vệ, trước đó là
426/426) chứng minh không có lỗi hồi quy trong các trường hợp đã được thiết kế, không
phải bằng chứng toán học rằng hệ thống hoàn toàn không có lỗi. Em công khai các giới hạn
còn mở: PgVectorStore là stub, Admin User Management thiếu Update/Delete UI, Knowledge
Base vẫn thiếu Update (Delete đã hoàn thiện), và concurrency chưa được load-test — không
có lỗi nào trong số này ở mức nghiêm trọng (P0)."

## Nếu quên hết mọi thứ, chỉ cần nhớ ĐÚNG 1 CÂU DUY NHẤT NÀY

**"EduDSS xây dựng đầy đủ một Hệ thống Hỗ trợ Ra Quyết định thực thụ — không dừng ở dự
đoán — với phương pháp luận ML nghiêm túc và chống rò rỉ dữ liệu đúng chuẩn, một pipeline
RAG có căn cứ và trung thực khi thiếu bằng chứng, và một quy trình tự-audit minh bạch về
mọi giới hạn còn tồn tại."**

Hít thở sâu. Bạn đã học đủ. Vào phòng thôi.
