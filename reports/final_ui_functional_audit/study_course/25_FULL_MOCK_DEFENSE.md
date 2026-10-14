# Bài 25 — Buổi bảo vệ giả lập đầy đủ (Full Mock Defense)

## 1. Mục tiêu buổi học

Đây là bài tổng hợp cuối cùng — mô phỏng một buổi bảo vệ hoàn chỉnh, luyện phản xạ trả
lời liên tục qua TẤT CẢ 24 chủ đề đã học, theo đúng trình tự một hội đồng thực tế thường
hỏi: mở đầu tổng quan → đi sâu kỹ thuật → hỏi khó/hỏi vặn → kết luận.

## 2. Kiến thức cần nhớ trước

Toàn bộ Bài 1–24. Nếu bạn chưa tự tin với bài nào, quay lại ôn trước khi làm bài này.

## 3. Giải thích từ con số 0

Một buổi bảo vệ thường có 3 giai đoạn: (1) bạn trình bày 5-10 phút, (2) hội đồng hỏi
xoay quanh phần trình bày, (3) hội đồng hỏi mở rộng để kiểm tra độ hiểu sâu, không chỉ
học thuộc. Bài này mô phỏng cả 3 giai đoạn bằng văn bản.

## 4. Giải thích kỹ thuật — Kịch bản mô phỏng đầy đủ

**Vòng 1 — Câu hỏi mở đầu (buộc bạn tóm tắt đúng trọng tâm):**
- "Tóm tắt EduDSS trong 2 câu." → (Bài 1) Trả lời ngắn gọn: hệ thống 3 vai trò, DSS đầy
  đủ (Prediction+Evidence+Explanation+Diagnosis+Recommendation+Action, Bài 14).
- "Vì sao gọi đây là DSS, không chỉ là công cụ dự đoán?" → (Bài 14) Đây là câu hỏi cốt
  lõi, PHẢI trả lời trôi chảy không vấp.

**Vòng 2 — Đi sâu kỹ thuật ML:**
- "Bạn chống data leakage như thế nào?" → (Bài 5) Trả lời đúng 3 lớp: filter_leakage_
  features → train_test_split trước → pipeline fit trong fold.
- "Tại sao R² hồi quy cao bất thường?" → (Bài 3, 9) Trả lời bằng công thức
  `diem_ky_sau`, không nhầm với leakage.
- "Cho biết chính xác số cấu hình/lượt fit của Random Forest ở cả 2 bài toán." → (Bài 6,
  8, 10) Classification: 24/120. Regression: 12/60. KHÔNG được nhầm lẫn 2 con số này.
- "Tại sao XGBoost Classifier không dùng GridSearchCV?" → (Bài 6) Lỗi label-contiguity
  đa lớp.

**Vòng 3 — Đi sâu DSS/Diagnosis/RAG:**
- "SHAP có chứng minh nhân quả không?" → (Bài 13) KHÔNG — chỉ đóng góp thống kê.
- "Diagnosis Engine có phải AI không?" → (Bài 14) KHÔNG — rule-based, minh bạch.
- "RAG hoạt động ra sao khi không tìm thấy tài liệu liên quan?" → (Bài 16) Trả lời trung
  thực NO_RELEVANT_EVIDENCE, không bịa.
- "Hệ thống dùng PostgreSQL đúng không?" → (Bài 21) KHÔNG — LocalVectorStore là thật
  đang chạy; PgVectorStore là stub.

**Vòng 4 — Câu hỏi "bẫy" thường gặp:**
- "K-Means dự đoán được sinh viên rớt môn không?" → (Bài 11) KHÔNG — unsupervised,
  không dự đoán.
- "Career Fit 85% là xác suất thành công đúng không?" → (Bài 20) KHÔNG — heuristic có
  trọng số.
- "Model tốt nhất tự động lên Production đúng không?" → (Bài 22) KHÔNG — Admin phải
  promote thủ công, `auto_promote=False`.
- "445 test pass nghĩa là không có bug đúng không?" → (Bài 24) KHÔNG — chỉ chứng minh
  không lỗi trong các trường hợp đã kiểm thử.

**Vòng 5 — Câu hỏi kết luận:**
- "Nếu có thêm 6 tháng, bạn sẽ làm gì tiếp theo?" → Kết nối Bài 21 (LMS/CMS thật), Bài 18
  (load test), Bài 3 (dữ liệu thật).
- "Đóng góp khoa học chính của đồ án là gì?" → Nhấn mạnh Bài 14: xây dựng đầy đủ chuỗi
  DSS (không dừng ở dự đoán), có phương pháp luận ML nghiêm túc và trung thực về giới hạn.

## 5. Ví dụ cực dễ hiểu

Giống như luyện thi vấn đáp: bạn không thể chỉ học thuộc bài giảng — bạn cần luyện phản
xạ trả lời khi bị hỏi bất ngờ, hỏi ngược, hỏi liên tiếp nhiều chủ đề khác nhau liền
mạch. Bài này chính là "buổi luyện tập" đó.

## 6. Ví dụ trực tiếp trong EduDSS

Toàn bộ các câu hỏi/trả lời ở mục 4 đều lấy trực tiếp từ Top 30 Dangerous Questions trong
`THESIS_DEFENSE_QA.md` (thư mục cha) — không phải câu hỏi tự bịa, mà là bộ câu hỏi đã
được tổng hợp cẩn thận từ toàn bộ quá trình audit hệ thống.

## 7. Luồng xử lý thực tế trong project

Không áp dụng theo nghĩa luồng code — đây là luồng LUYỆN TẬP:
```
Đọc câu hỏi → tự trả lời trong 20-40 giây (không nhìn đáp án)
  → so sánh với đáp án ở Bài tương ứng
  → nếu sai/ấp úng: quay lại đọc kỹ Bài đó
  → lặp lại đến khi trả lời trôi chảy không cần nhìn tài liệu
```

## 8. Công thức nếu có

Không có công thức riêng — đây là bài tổng hợp toàn bộ công thức đã học ở các bài trước.
Nếu cần tra cứu nhanh mọi công thức, dùng `THESIS_FORMULA_SHEET.md` (thư mục cha) hoặc
`FLASHCARDS.md` (thư mục này).

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng — xem lại từng bài cụ thể.

## 10. Cách đọc kết quả

Nếu bạn trả lời được cả 5 vòng câu hỏi ở mục 4 mà KHÔNG cần mở tài liệu, bạn đã sẵn sàng
cho buổi bảo vệ thật. Nếu vấp ở vòng nào, quay lại đúng bài học tương ứng đã ghi chú kèm
theo.

## 11. Vì sao project dùng phương pháp này

Luyện tập theo hình thức hỏi-đáp liên tục mô phỏng đúng áp lực thời gian và tính bất ngờ
của một buổi bảo vệ thật, hiệu quả hơn nhiều so với chỉ đọc lại tài liệu một cách thụ
động.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là bài "tổng duyệt" cuối cùng, đứng sau toàn bộ 24 bài học kỹ thuật — kết nối lại
toàn bộ Chuỗi 1 và Chuỗi 2 đã học riêng lẻ trước đó thành một bức tranh thống nhất.

## 13. Input là gì

Toàn bộ kiến thức từ Bài 1–24.

## 14. Output là gì

Khả năng trả lời trôi chảy, chính xác, không mâu thuẫn giữa các câu trả lời ở các chủ đề
khác nhau.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển sang các công cụ ôn tập nhanh: `QUICK_REVIEW_1_DAY.md`, `QUICK_REVIEW_30_MINUTES.md`,
`MOCK_DEFENSE_3_ROUNDS.md`, `IF_I_FORGET.md`.

## 16. Ưu điểm

Tổng hợp toàn diện, phát hiện được lỗ hổng kiến thức còn sót giữa các bài học riêng lẻ.

## 17. Nhược điểm

Cần thời gian luyện tập nhiều lần mới đạt độ trôi chảy cần thiết, không thể "học tủ" một
lần là xong.

## 18. Limitation thực tế của project

Bài luyện tập này chỉ bao phủ những câu hỏi ĐÃ ĐƯỢC DỰ ĐOÁN trước (Top 30 Dangerous
Questions) — hội đồng thật có thể hỏi những câu hoàn toàn mới không có trong danh sách,
vì vậy việc HIỂU BẢN CHẤT (không chỉ thuộc câu trả lời mẫu) là điều quan trọng nhất.

## 19. Hội đồng có thể hỏi gì

Bất kỳ câu hỏi nào tổng hợp/kết nối nhiều chủ đề, ví dụ: "Hãy giải thích toàn bộ hành
trình dữ liệu từ lúc một sinh viên có hành vi học tập kém đến lúc họ nhận được một kế
hoạch học tập cụ thể, chỉ rõ từng bước sử dụng thuật toán/kỹ thuật nào."

## 20. Câu trả lời ngắn 20–40 giây

"Dữ liệu hành vi của sinh viên (Bài 3) được tiền xử lý (Bài 4, chống leakage ở Bài 5),
đưa vào mô hình Classification/Regression (Bài 6, 8) để dự đoán rủi ro. SHAP (Bài 13)
giải thích các feature đóng góp nhiều nhất. Diagnosis Engine (Bài 14) áp luật lên bằng
chứng đó để xác định nguyên nhân cụ thể. Recommendation Engine và Learning Plan Generator
(Bài 15) biến chẩn đoán đó thành một kế hoạch học tập có cấu trúc, và LLM Gateway (Bài
18) diễn đạt kế hoạch đó bằng ngôn ngữ tự nhiên để sinh viên đọc và hành động."

## 21. Câu trả lời chi tiết

Đọc thuộc lòng chuỗi đầy đủ ở Bài 14 mục 7, có thể mở rộng thêm chi tiết từng bước nếu
được hỏi sâu hơn về một bước cụ thể nào đó trong chuỗi.

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu tôi hỏi một câu hoàn toàn không có trong danh sách bạn đã chuẩn bị thì sao?"

## 23. Cách trả lời câu vặn

"Em đã cố gắng hiểu bản chất từng thành phần thay vì chỉ học thuộc câu trả lời mẫu — nếu
câu hỏi mới, em sẽ áp dụng đúng nguyên tắc đã học: phân biệt rõ Prediction với DSS đầy
đủ, phân biệt 'có class tồn tại' với 'có triển khai/kết nối thật', và luôn trung thực về
những gì hệ thống làm được và chưa làm được, thay vì cố gắng trả lời cho có."

## 24. Những câu không được nói

Xem lại `THESIS_MUST_NOT_SAY.md` (thư mục cha) — đây là bảng tổng hợp đầy đủ mọi câu
không được nói trong suốt 24 bài học đã đi qua. Không lặp lại ở đây để tránh trùng lặp —
hãy đọc trực tiếp file đó trước ngày bảo vệ.

## 25. 10 câu tự kiểm tra — ĐÂY LÀ BÀI KIỂM TRA TỔNG HỢP CUỐI CÙNG

1. Đọc thuộc lòng chuỗi 8 bước từ dữ liệu sinh viên đến hành động (Chuỗi 1).
2. Đọc thuộc lòng chuỗi 9 bước từ tài liệu giảng viên đến câu trả lời AI (Chuỗi 2).
3. Kể ra 5 con số quan trọng nhất về ML (classification + regression) mà không nhầm lẫn.
4. Giải thích trong 30 giây vì sao Prediction ≠ DSS.
5. Giải thích trong 30 giây vì sao R² cao không phải bằng chứng tốt.
6. Kể tên 3 thứ "trông như có thật nhưng thực ra chưa" trong hệ thống.
7. Giải thích 445 test chứng minh gì và không chứng minh gì.
8. Kể tên 5 câu tuyệt đối không được nói trong buổi bảo vệ.
9. Nếu bị hỏi một câu hoàn toàn mới, nguyên tắc ứng xử là gì?
10. Đóng góp khoa học chính của đồ án là gì?

## 26. Đáp án riêng

1. Xem Bài 14 mục 7 — Dữ liệu → Tiền xử lý → Prediction → SHAP → Diagnosis → Recommendation
   → Learning Plan → Hành động.
2. Xem Bài 16 mục 4 — Document→Chunk→Embedding→Vector→Similarity→Retrieval→Context→LLM→
   Citation.
3. RF Classification 24/120, XGBoost Classification 1/0CV, RF Regression 12/60, XGBoost
   Regression 18/90, LightGBM (cả hai) 8/40 và 18/90.
4. Xem Bài 14 mục 20.
5. Xem Bài 9 mục 20.
6. RealConnectorLMSRepository (LMS), PgVectorStore (Postgres), Career Fit % (không phải
   xác suất).
7. Xem Bài 24 mục 4.
8. Xem `THESIS_MUST_NOT_SAY.md`.
9. Áp dụng nguyên tắc cốt lõi đã học (DSS≠Prediction, class≠triển khai thật, luôn trung
   thực), không cố trả lời cho có.
10. Xây dựng đầy đủ một DSS thực thụ (không chỉ dừng ở dự đoán), với phương pháp luận ML
    nghiêm túc và một quy trình tự-audit trung thực về giới hạn.

## 27. 5 CÂU PHẢI THUỘC (tổng hợp năm câu quan trọng nhất toàn khóa học)

1. "DSS = Prediction + Evidence + Explanation + Diagnosis + Recommendation + Action
   support — đây là luận điểm cốt lõi của toàn bộ đồ án."
2. "R² cao trên dữ liệu mẫu là do công thức sinh dữ liệu tuyến tính, không phải bằng
   chứng hiệu năng thực tế — và đây KHÔNG phải data leakage."
3. "Có class/tên gọi 'Real' không đồng nghĩa với có kết nối/triển khai thật — luôn kiểm
   tra nội dung hàm và điều kiện kích hoạt."
4. "SHAP giải thích đóng góp thống kê vào dự đoán của mô hình — KHÔNG chứng minh nhân
   quả trong thực tế."
5. "445 test pass chứng minh không có lỗi hồi quy trong các trường hợp đã kiểm thử — KHÔNG
   chứng minh hệ thống hoàn hảo tuyệt đối."

## 28. 5 TỪ KHÓA PHẢI NHỚ (tổng hợp)

- Decision Support System (DSS) — Hệ thống hỗ trợ ra quyết định
- Data leakage vs. Synthetic-data artifact — Rò rỉ dữ liệu vs. Hiện tượng do dữ liệu tổng hợp
- Abstraction only vs. Implemented — Chỉ có khung trừu tượng vs. Đã triển khai thật
- SHAP ≠ Causality — SHAP không chứng minh nhân quả
- Honest limitation disclosure — Công khai trung thực giới hạn hệ thống
