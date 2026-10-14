# Bài 14 — DSS thật sự là gì? + Diagnosis Engine (BÀI QUAN TRỌNG NHẤT)

## 1. Mục tiêu buổi học

Đây là bài **quan trọng nhất trong toàn bộ khóa học**. Bạn phải trả lời thuyết phục được
câu hỏi cốt lõi của cả luận văn: **"Dự đoán (Prediction) không phải là Hệ thống hỗ trợ ra
quyết định (DSS)."** Nếu trả lời sai câu này, toàn bộ giá trị khoa học của đồ án bị nghi
ngờ. Bạn cũng phải hiểu rõ Diagnosis Engine — bộ máy chẩn đoán bằng luật (rule-based) chứ
không phải AI/ML.

## 2. Kiến thức cần nhớ trước

Bài 6-9 (Classification/Regression + metrics), Bài 13 (SHAP).

## 3. Giải thích từ con số 0

Hãy tưởng tượng bạn đi khám bệnh. Nếu bác sĩ chỉ nói: "Chỉ số huyết áp của bạn là
150/95" — đó là một **con số đo lường/dự đoán**. Nó có ích, nhưng KHÔNG giúp bạn biết
phải làm gì tiếp theo. Một bác sĩ giỏi phải làm thêm 4 việc:
1. **Giải thích** — "Vì sao huyết áp bạn cao? Có thể do ăn mặn, thiếu vận động, stress."
2. **Chẩn đoán** — "Dựa trên triệu chứng và tiền sử, nhiều khả năng đây là tăng huyết áp
   giai đoạn 1, nguyên nhân chính có thể do lối sống."
3. **Khuyến nghị** — "Bạn nên giảm muối, tập thể dục 30 phút/ngày, tái khám sau 1 tháng."
4. **Hỗ trợ hành động** — cung cấp một lịch trình cụ thể, dễ theo dõi.

**Một hệ thống hỗ trợ ra quyết định (Decision Support System — DSS) thực thụ PHẢI làm đủ
cả chuỗi này, không chỉ dừng ở bước 1 (dự đoán/đo lường).**

## 4. Giải thích kỹ thuật

Công thức định nghĩa DSS trong EduDSS:

```
DSS = Prediction (Dự đoán) + Evidence (Bằng chứng, từ SHAP)
    + Explanation (Giải thích) + Diagnosis (Chẩn đoán)
    + Recommendation (Khuyến nghị) + Action support (Hỗ trợ hành động)
```

Nếu chỉ có "Prediction", đó chỉ là một **công cụ dự báo (forecasting tool)**, không phải
DSS. EduDSS xây dựng đủ toàn bộ chuỗi 6 thành phần này.

**Diagnosis Engine** (`dss/services/diagnosis_engine.py`) là bộ não thực hiện bước "Chẩn
đoán". Nó **hoàn toàn là luật if/elif dựa trên ngưỡng (threshold-based rules)** — KHÔNG
phải machine learning, KHÔNG phải LLM. Nó có 12 nhóm nguyên nhân (category) được định
nghĩa sẵn: `KNOWLEDGE_GAP` (hổng kiến thức), `PREREQUISITE_GAP` (thiếu kiến thức nền),
`LOW_PRACTICE` (ít luyện tập), `LOW_RETENTION` (khó ghi nhớ lâu), `SLOW_RESPONSE` (phản
hồi chậm), `CARELESS_FAST_RESPONSE` (làm ẩu/quá nhanh), `LOW_ENGAGEMENT` (ít tương tác),
`INCONSISTENT_STUDY` (học không đều đặn), `CONTENT_SPECIFIC_GAP` (hổng theo chủ đề cụ
thể), `ASSESSMENT_ANXIETY_SIGNAL` (dấu hiệu lo âu khi kiểm tra), `INSUFFICIENT_DATA`
(không đủ dữ liệu để kết luận), `OTHER_UNCONFIRMED` (chưa xác định). Với dữ liệu hiện có
(không có dữ liệu thời gian phản hồi/mức độ chi tiết theo câu hỏi), engine trung thực trả
về `INSUFFICIENT_DATA` cho các nhóm như `SLOW_RESPONSE` thay vì đoán bừa.

## 5. Ví dụ cực dễ hiểu

So sánh 2 hệ thống: Hệ thống A nói "Sinh viên X có 78% khả năng rủi ro." Hệ thống B nói
"Sinh viên X có rủi ro cao (dự đoán); nguyên nhân chính có khả năng là ít luyện tập bài
tập (tỷ lệ hoàn thành 30%) và tỷ lệ điểm danh thấp (60%) — theo phân tích SHAP, đây là 2
yếu tố đóng góp nhiều nhất; khuyến nghị: tăng cường bài tập tuần 2 giờ, đặt nhắc điểm
danh." Hệ thống B là DSS thật sự — nó cho bạn BIẾT PHẢI LÀM GÌ, hệ thống A chỉ cho một
con số.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Sinh viên vào "AI Advisor → Kế hoạch học tập", hệ thống không chỉ hiển thị "rủi ro
cao" — nó hiển thị: chẩn đoán cụ thể (ví dụ "LOW_PRACTICE — ít luyện tập"), bằng chứng
(tỷ lệ hoàn thành bài tập thấp, được xác nhận qua SHAP), và một kế hoạch học tập theo
tuần (Bài 15).

## 7. Luồng xử lý thực tế trong project — CHUỖI 1 ĐẦY ĐỦ (PHẢI THUỘC)

```
Dữ liệu sinh viên (Bài 3)
  → Tiền xử lý (Bài 4)
  → Classification/Regression dự đoán rủi ro/điểm số (Bài 6, 8)
  → SHAP giải thích đóng góp feature (Bài 13) — cung cấp EVIDENCE
  → Diagnosis Engine áp luật if/elif lên profile + evidence → ra 1 hoặc nhiều category
    chẩn đoán, kèm mức độ tin cậy (confidence) và bằng chứng cụ thể
  → Recommendation Engine (Bài 15) sinh gợi ý theo category chẩn đoán
  → Learning Plan Generator (Bài 15) đóng gói thành kế hoạch học tập có cấu trúc
  → Sinh viên xem kế hoạch, hành động (làm bài tập, tăng giờ học...)
  → Hành vi mới của Sinh viên lại trở thành dữ liệu đầu vào cho vòng phân tích tiếp theo
```

## 8. Công thức nếu có

Không có công thức số học riêng — Diagnosis Engine dùng logic điều kiện (rule-based), ví
dụ dạng giả mã:
```
if ty_le_hoan_thanh_bai_tap < 0.5 and so_lan_dang_nhap thấp:
    category = LOW_PRACTICE, confidence = cao
elif dữ liệu về thời gian phản hồi không tồn tại:
    category = INSUFFICIENT_DATA  (không được đoán bừa)
```

## 9. Giải thích từng ký hiệu trong công thức

- Điều kiện `if/elif` — một ngưỡng cụ thể trên một hoặc nhiều feature (ví dụ tỷ lệ hoàn
  thành bài tập dưới 50%).
- `category` — một trong 12 nhãn chẩn đoán được định nghĩa sẵn.
- `confidence` — mức độ tin cậy của chẩn đoán đó, cũng được tính bằng luật, không phải
  xác suất thống kê.
- `INSUFFICIENT_DATA` — nhãn đặc biệt, trả về một cách trung thực khi dữ liệu hiện có
  không đủ để chẩn đoán một category cụ thể — đây là điểm thiết kế thể hiện sự trung
  thực của hệ thống, không "bịa" ra chẩn đoán khi thiếu bằng chứng.

## 10. Cách đọc kết quả

Kết quả Diagnosis Engine là MỘT HOẶC NHIỀU nhãn category kèm bằng chứng cụ thể (evidence)
— không phải một con số duy nhất. Đọc là "hệ thống nghi ngờ nguyên nhân X dựa trên bằng
chứng Y", không đọc là "hệ thống chắc chắn 100% nguyên nhân là X."

## 11. Vì sao project dùng phương pháp này

Thiết kế Diagnosis Engine bằng luật rõ ràng (không phải ML/LLM) có chủ đích: (a) minh
bạch tuyệt đối — mọi chẩn đoán đều có thể truy vết về đúng luật nào đã kích hoạt, (b) dễ
kiểm chứng đúng/sai bằng test, (c) tránh rủi ro một mô hình "hộp đen" đưa ra chẩn đoán
tâm lý/học tập nhạy cảm mà không giải thích được.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây chính là "trái tim" của Chuỗi 1 — vị trí giữa SHAP (bằng chứng) và Recommendation
(hành động). Không có Diagnosis Engine, hệ thống chỉ là công cụ dự báo, không phải DSS.

## 13. Input là gì

Kết quả dự đoán (Classification/Regression), bằng chứng SHAP, và Student Learning Profile
(hồ sơ học tập gồm các feature hành vi/học tập).

## 14. Output là gì

Một hoặc nhiều nhãn chẩn đoán (category) kèm mức độ tin cậy và bằng chứng cụ thể.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho Recommendation Engine và Learning Plan Generator (Bài 15).

## 16. Ưu điểm

Minh bạch tuyệt đối, dễ kiểm chứng, dễ giải thích cho người dùng không chuyên kỹ thuật,
trung thực khi thiếu dữ liệu (trả về INSUFFICIENT_DATA thay vì đoán bừa).

## 17. Nhược điểm

Luật cố định không tự học/cải thiện theo thời gian như một mô hình ML thật; có thể bỏ sót
các mẫu hình phức tạp mà luật thủ công không lường trước.

## 18. Limitation thực tế của project

Một số category (như `SLOW_RESPONSE`, `CARELESS_FAST_RESPONSE`) không thể chẩn đoán được
với dữ liệu hiện có (thiếu dữ liệu thời gian phản hồi theo từng câu hỏi) — engine trung
thực trả về `INSUFFICIENT_DATA` thay vì bịa ra kết luận.

## 19. Hội đồng có thể hỏi gì

"Vì sao bạn nói dự đoán ML không phải là DSS? Chẳng phải dự đoán chính xác đã là giá trị
cốt lõi rồi sao?"

## 20. Câu trả lời ngắn 20–40 giây

"Dự đoán chỉ trả lời câu hỏi 'CÁI GÌ sẽ xảy ra' — ví dụ 'sinh viên này có rủi ro cao.'
Nhưng một Hệ thống Hỗ trợ Ra Quyết định thực thụ phải trả lời thêm 'TẠI SAO' và 'PHẢI LÀM
GÌ TIẾP THEO.' EduDSS xây dựng đủ chuỗi 6 bước: Dự đoán, Bằng chứng từ SHAP, Giải thích,
Chẩn đoán nguyên nhân bằng luật rõ ràng, Khuyến nghị, và Kế hoạch hành động cụ thể — đó
mới là điều biến một mô hình ML đơn thuần thành một DSS."

## 21. Câu trả lời chi tiết

Dùng ví dụ bác sĩ ở mục 3, trình bày công thức 6 thành phần ở mục 4, và đọc thuộc chuỗi
xử lý đầy đủ ở mục 7 — đây chính là "bằng chứng sống" cho luận điểm DSS ≠ Prediction.

## 22. Hội đồng có thể vặn tiếp thế nào

"Nhưng Diagnosis Engine chỉ là if/elif đơn giản — có thể gọi đó là 'trí tuệ nhân tạo'
không?"

## 23. Cách trả lời câu vặn

"Không, và em không tuyên bố đó là AI. Diagnosis Engine là một hệ thống dựa trên luật
(rule-based system) — một nhánh cổ điển của khoa học máy tính, đôi khi được gọi là 'expert
system' trong AI truyền thống, nhưng KHÔNG phải machine learning hay LLM. Em chọn cách
tiếp cận này có chủ đích vì tính minh bạch và khả năng kiểm chứng — trong một hệ thống
đưa ra chẩn đoán ảnh hưởng đến quyết định học tập của sinh viên, tính giải thích được
quan trọng hơn việc chạy theo độ phức tạp của mô hình."

## 24. Những câu không được nói

- "Diagnosis Engine dùng machine learning để chẩn đoán." (Sai — hoàn toàn rule-based.)
- "Dự đoán ML chính là DSS." (Sai — đây là hiểu lầm cốt lõi cần tránh tuyệt đối.)
- "Hệ thống luôn chẩn đoán được chính xác nguyên nhân." (Sai — có category
  INSUFFICIENT_DATA khi thiếu bằng chứng.)

## 25. 10 câu tự kiểm tra

1. Công thức 6 thành phần của DSS trong EduDSS là gì?
2. Vì sao "chỉ có Prediction" không đủ để gọi là DSS?
3. Diagnosis Engine dựa trên cơ chế nào — ML, LLM, hay rule-based?
4. Kể tên ít nhất 4 trong 12 category chẩn đoán.
5. `INSUFFICIENT_DATA` được trả về khi nào?
6. Diagnosis Engine nhận input từ những module nào?
7. Output của Diagnosis Engine được chuyển cho module nào?
8. Vì sao chọn rule-based thay vì ML cho Diagnosis Engine?
9. Category nào không thể chẩn đoán được với dữ liệu hiện có? Vì sao?
10. Đọc thuộc lòng chuỗi xử lý đầy đủ Chuỗi 1 (8 bước).

## 26. Đáp án riêng

1. Prediction + Evidence (SHAP) + Explanation + Diagnosis + Recommendation + Action
   support.
2. Vì Prediction chỉ trả lời "cái gì" chứ không trả lời "tại sao" và "phải làm gì tiếp
   theo".
3. Rule-based (luật if/elif dựa trên ngưỡng).
4. Ví dụ: KNOWLEDGE_GAP, LOW_PRACTICE, LOW_ENGAGEMENT, INCONSISTENT_STUDY (hoặc bất kỳ 4
   trong 12 category liệt kê ở mục 4).
5. Khi dữ liệu hiện có không đủ để chẩn đoán một category cụ thể một cách trung thực.
6. Kết quả dự đoán (Classification/Regression), bằng chứng SHAP, Student Learning
   Profile.
7. Recommendation Engine và Learning Plan Generator.
8. Để đảm bảo tính minh bạch, khả năng kiểm chứng, và tránh chẩn đoán "hộp đen" cho vấn
   đề nhạy cảm.
9. `SLOW_RESPONSE`/`CARELESS_FAST_RESPONSE` — vì thiếu dữ liệu thời gian phản hồi theo
   từng câu hỏi.
10. Dữ liệu sinh viên → Tiền xử lý → Classification/Regression → SHAP → Diagnosis Engine
    → Recommendation → Learning Plan → Sinh viên hành động → dữ liệu mới quay lại hệ
    thống.

## 27. 5 CÂU PHẢI THUỘC

1. "DSS = Prediction + Evidence + Explanation + Diagnosis + Recommendation + Action
   support — không chỉ là dự đoán."
2. "Diagnosis Engine là rule-based (if/elif theo ngưỡng), hoàn toàn minh bạch, KHÔNG phải
   machine learning hay LLM."
3. "Khi thiếu dữ liệu, Diagnosis Engine trả về INSUFFICIENT_DATA thay vì đoán bừa — đây
   là thiết kế trung thực có chủ đích."
4. "Prediction chỉ trả lời 'cái gì sẽ xảy ra'; DSS phải trả lời thêm 'tại sao' và 'phải
   làm gì'."
5. "Chuỗi xử lý đầy đủ: Dữ liệu → Tiền xử lý → Prediction → SHAP → Diagnosis → Khuyến
   nghị → Kế hoạch học tập → Hành động."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Decision Support System (DSS) — Hệ thống hỗ trợ ra quyết định
- Diagnosis Engine — Bộ máy chẩn đoán
- Rule-based system — Hệ thống dựa trên luật
- Evidence — Bằng chứng
- Actionable recommendation — Khuyến nghị có thể hành động được
