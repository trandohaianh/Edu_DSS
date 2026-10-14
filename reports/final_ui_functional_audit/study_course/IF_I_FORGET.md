# NẾU BẠN ĐỨNG HÌNH GIỮA BUỔI BẢO VỆ — MỞ FILE NÀY

Chỉ đọc đúng mục bạn cần. Không đọc toàn bộ file này khi đang bảo vệ — chỉ tra đúng 1
mục, trả lời, rồi tiếp tục.

## Nếu quên toàn bộ và không biết bắt đầu từ đâu

Nói câu này, hít thở, rồi tiếp tục:
> "Để em tóm tắt lại từ đầu: EduDSS là hệ thống hỗ trợ ra quyết định học tập, xây dựng
> đầy đủ chuỗi Dự đoán, Giải thích, Chẩn đoán, Khuyến nghị — không chỉ dừng ở một mô hình
> dự đoán đơn thuần."

## Nếu quên con số ML cụ thể (bao nhiêu cấu hình/fit)

Nói câu này thay vì im lặng hoặc đoán bừa:
> "Em nhớ có 4 thuật toán cho mỗi bài toán Classification và Regression, mỗi bài toán có
> một lưới tham số riêng được tối ưu qua GridSearchCV 5-fold, ngoại trừ XGBoost
> Classifier dùng tham số cố định do một lỗi kỹ thuật đã biết với dữ liệu đa lớp. Con số
> chính xác từng cấu hình em có ghi trong tài liệu, nhưng nguyên tắc quan trọng là: số
> lượt fit luôn bằng số cấu hình nhân với số fold."

## Nếu bị hỏi về R² mà đầu óc trống rỗng

Nói chậm, từng câu một:
> "R² cao trên dữ liệu mẫu không phải vì mô hình xuất sắc. Bộ dữ liệu mẫu này có target
> được TÍNH RA từ một công thức của chính các đặc trưng đầu vào, cộng thêm rất ít nhiễu.
> Vì vậy bất kỳ mô hình đủ mạnh nào cũng học ra R² cao — đây là đặc điểm của cách sinh dữ
> liệu, không phải bằng chứng cho khả năng dự đoán thực tế."

## Nếu bị hỏi về PostgreSQL/LMS/CMS mà quên chi tiết

Nói câu "khung sườn" này rồi điền chi tiết nếu nhớ được:
> "Nguyên tắc em luôn áp dụng là: có một class tồn tại trong code không có nghĩa là nó
> đã được kết nối hay triển khai thật. Với LMS và CMS ngoài, hệ thống mới có lớp trừu
> tượng sẵn sàng, chưa có kết nối mạng thật. Với vector store, có một lớp PostgreSQL
> nhưng các hàm đọc/ghi bên trong là hàm giả (stub) — vector store thật đang chạy là một
> giải pháp file-based đơn giản hơn."

## Nếu bị hỏi vặn mà không biết trả lời

Đừng im lặng, cũng đừng chống chế. Dùng khung câu này:
> "Đây là một câu hỏi rất hay, và em xin phép trả lời theo hướng em hiểu: [nói ra điều
> bạn CHẮC CHẮN biết liên quan đến câu hỏi]. Về khía cạnh cụ thể thầy/cô hỏi, em xin ghi
> nhận đây là một điểm em cần suy nghĩ thêm / là một giới hạn của đồ án hiện tại, và
> hướng cải thiện trong tương lai có thể là [đưa ra một hướng hợp lý dựa trên logic]."

## Nếu bị hỏi "Vậy đóng góp của đồ án này là gì?"

Đây là câu hỏi kết thúc phổ biến nhất. Nói:
> "Đóng góp chính là xây dựng đầy đủ một Hệ thống Hỗ trợ Ra Quyết định thực thụ trong
> giáo dục — không dừng lại ở một mô hình dự đoán, mà có đủ tầng giải thích, chẩn đoán
> nguyên nhân bằng luật minh bạch, và khuyến nghị hành động cụ thể. Đóng góp thứ hai là
> một pipeline RAG có căn cứ thực sự, trung thực từ chối trả lời khi thiếu bằng chứng.
> Và đóng góp thứ ba, không kém quan trọng, là một quy trình tự-kiểm-tra (audit) nghiêm
> túc, minh bạch hoàn toàn về những gì hệ thống làm được và chưa làm được."

## Nếu run quá, quên sạch mọi con số và thuật ngữ

Chỉ cần nhớ ĐÚNG 3 CỤM TỪ này và nói chậm rãi, chúng sẽ tự nhắc bạn nhớ lại phần còn lại:
1. **"Prediction không phải là DSS"**
2. **"Có class không có nghĩa là có kết nối thật"**
3. **"R² cao là do cách sinh dữ liệu, không phải leakage"**

Ba cụm từ này là xương sống của gần như mọi câu trả lời trong toàn bộ buổi bảo vệ. Nhớ
được 3 cụm từ này, bạn có thể xây lại phần còn lại của câu trả lời ngay tại chỗ.

## Việc cuối cùng: đừng bịa

Nếu thực sự không nhớ câu trả lời, KHÔNG bịa ra một con số hay một tuyên bố không chắc
chắn. Nói thẳng:
> "Em xin phép không chắc chắn về con số chính xác ở đây, nhưng nguyên tắc chung mà em áp
> dụng xuyên suốt đồ án là luôn trung thực khi thiếu bằng chứng, giống như cách hệ thống
> tự nó cũng trung thực từ chối trả lời khi RAG không tìm thấy tài liệu liên quan."

Câu trả lời trung thực về việc không nhớ luôn tốt hơn một câu trả lời sai hoặc bịa đặt.
