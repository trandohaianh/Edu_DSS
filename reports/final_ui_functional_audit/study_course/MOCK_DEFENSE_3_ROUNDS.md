# Bảo vệ giả lập — 3 vòng tăng dần độ khó

Dùng file này với một người bạn/người thân đóng vai hội đồng, đọc từng câu hỏi cho bạn
trả lời trực tiếp bằng lời nói (không đọc), sau đó đối chiếu với gợi ý đáp án. Mỗi vòng
khó hơn vòng trước. Giới hạn thời gian mỗi câu: Vòng 1 = 40 giây, Vòng 2 = 60 giây, Vòng
3 = không giới hạn nhưng phải trả lời có cấu trúc.

---

## VÒNG 1 — Câu hỏi cơ bản (kiểm tra bạn có nắm vững kiến thức nền không)

1. EduDSS là gì, phục vụ những vai trò nào? *(Bài 1)*
2. Kể tên 4 thuật toán phân loại (classification) EduDSS sử dụng. *(Bài 6)*
3. Kể tên 4 thuật toán hồi quy (regression) EduDSS sử dụng. *(Bài 8)*
4. RAG là viết tắt của gì, mục đích chính là gì? *(Bài 16)*
5. K-Means dùng để làm gì trong EduDSS? *(Bài 11)*
6. SHAP dùng để làm gì? *(Bài 13)*
7. Model Registry có mấy trạng thái, kể tên? *(Bài 22)*
8. Baseline test cuối cùng của EduDSS là bao nhiêu? *(Bài 24)*
9. Career Fit và Career Readiness khác nhau ở điểm nào? *(Bài 20)*
10. Diagnosis Engine dựa trên cơ chế gì — ML hay rule-based? *(Bài 14)*

**Gợi ý chấm điểm**: Nếu bạn trả lời được cả 10 câu trong dưới 40 giây/câu mà không ấp
úng, bạn đã sẵn sàng cho Vòng 2. Nếu vấp ở câu nào, quay lại đúng bài học đó ngay.

---

## VÒNG 2 — Câu hỏi đi sâu (kiểm tra bạn hiểu CƠ CHẾ, không chỉ thuộc tên)

1. Giải thích chính xác thứ tự các bước chống data leakage trong pipeline huấn luyện.
   *(Bài 5)*
2. Tại sao XGBoost Classifier không dùng GridSearchCV, trong khi XGBoost Regressor lại
   có? *(Bài 6, 8)*
3. Giải thích công thức sinh target `diem_ky_sau`, chỉ rõ từng thành phần. *(Bài 3)*
4. Silhouette score được tính như thế nào, và đọc kết quả ra sao? *(Bài 12)*
5. Giải thích công thức Shapley value, `f(S∪{j})-f(S)` nghĩa là gì? *(Bài 13)*
6. Trình bày đầy đủ Chuỗi 2 (RAG) — 9 bước, không được bỏ sót bước nào. *(Bài 16)*
7. Tại sao LMS trong EduDSS được gọi là "abstraction only" chứ không phải "implemented"?
   *(Bài 21)*
8. `should_promote` được tính bằng công thức nào, và tại sao trong thực tế nó luôn ra
   `False`? *(Bài 22)*
9. Privacy service lọc những trường nào vào prompt AI, và tại sao lại chọn đúng những
   trường đó? *(Bài 23)*
10. Giải thích vì sao 445 test pass không tương đương với "không có bug." *(Bài 24)*

**Gợi ý chấm điểm**: Ở vòng này, câu trả lời PHẢI có cấu trúc: định nghĩa → cơ chế cụ thể
→ ví dụ/bằng chứng. Nếu bạn chỉ trả lời được "có/không" mà không giải thích được CƠ CHẾ,
quay lại đọc kỹ phần "Giải thích kỹ thuật" (mục 4) của bài học tương ứng.

---

## VÒNG 3 — Câu hỏi vặn/liên kết (mô phỏng hội đồng khó tính thực sự)

1. "Nếu SHAP cho thấy 'tỷ lệ điểm danh' đóng góp nhiều nhất vào dự đoán rủi ro, tại sao
   bạn không thể kết luận rằng cải thiện điểm danh sẽ giảm rủi ro?" *(Bài 13, liên kết
   Bài 14)*
2. "Bạn nói Diagnosis Engine minh bạch hơn ML vì là rule-based — nhưng luật đó có được
   kiểm chứng bằng dữ liệu thực tế không, hay chỉ là ý kiến chủ quan của người thiết kế?"
   *(Bài 14)*
3. "R² cao vì công thức sinh dữ liệu tuyến tính — nhưng nếu vậy, việc dùng 3 thuật toán
   phi tuyến phức tạp (Random Forest, XGBoost, LightGBM) có còn ý nghĩa gì không trên bộ
   dữ liệu này?" *(Bài 3, 8)*
4. "Nếu PgVectorStore chưa hoạt động, và LocalVectorStore là file-based — điều gì xảy ra
   nếu 10,000 sinh viên dùng RAG cùng lúc? Hệ thống có sập không?" *(Bài 21, liên kết Bài
   18)*
5. "Bạn nói Career Fit không phải xác suất — vậy tại sao lại hiển thị nó dưới dạng phần
   trăm (%) trên giao diện, dễ gây hiểu lầm cho sinh viên?" *(Bài 20)*
6. "Nếu Learning Plan Generator là rule-based và LLM chỉ diễn đạt — vậy nếu LLM diễn đạt
   sai lệch ý nghĩa của kế hoạch gốc, ai chịu trách nhiệm, và hệ thống có cơ chế kiểm tra
   không?" *(Bài 15, liên kết Bài 18, 23)*
7. "So sánh 4 thuật toán classification có công bằng không khi XGBoost không được tuning
   bằng GridSearchCV như 3 thuật toán kia?" *(Bài 6, 10)*
8. "Bạn xác nhận `auto_promote=False` luôn được truyền — vậy tại sao code vẫn giữ logic
   `is_best`? Đây có phải code thừa (dead code) không?" *(Bài 22)*
9. "Cơ chế chống prompt injection là heuristic — vậy nếu một giảng viên vô tình tải lên
   tài liệu chứa một đoạn văn bản trông giống lệnh hệ thống, điều gì sẽ xảy ra?" *(Bài
   17, 23)*
10. "Toàn bộ đồ án dựa trên dữ liệu tổng hợp — vậy giá trị khoa học thực sự của đồ án nằm
    ở đâu, nếu không chứng minh được điều gì về sinh viên thật?" *(Bài 3, liên kết Bài 24
    — đây là câu hỏi tổng kết, xem Bài 25 mục 23)*

**Gợi ý chấm điểm**: Đây là những câu hỏi KHÔNG có đáp án "đúng tuyệt đối" trong tài liệu
— chúng kiểm tra khả năng bạn TỰ SUY LUẬN dựa trên các nguyên tắc đã học (DSS≠Prediction,
class≠triển khai thật, SHAP≠nhân quả, luôn trung thực về giới hạn). Cách trả lời tốt: (1)
thừa nhận đây là giới hạn/câu hỏi hợp lý, (2) áp dụng đúng nguyên tắc đã học để lý giải,
(3) đề xuất hướng cải thiện trong tương lai nếu phù hợp — KHÔNG cố "chống chế" hay phủ
nhận vấn đề.

---

## Sau khi hoàn thành cả 3 vòng

- Nếu bạn trả lời trôi chảy Vòng 1 và Vòng 2, bạn đã sẵn sàng cho phần lớn buổi bảo vệ
  thực tế.
- Nếu Vòng 3 khiến bạn bối rối ở một vài câu, đó là BÌNH THƯỜNG — hãy đọc lại
  `IF_I_FORGET.md` để có chiến lược ứng phó khi gặp câu hỏi không có sẵn đáp án học
  thuộc.
- Lặp lại cả 3 vòng ít nhất 2 lần trước ngày bảo vệ, lý tưởng là với người khác hỏi bạn
  (không tự đọc một mình), để luyện phản xạ nói thành lời thực sự.
