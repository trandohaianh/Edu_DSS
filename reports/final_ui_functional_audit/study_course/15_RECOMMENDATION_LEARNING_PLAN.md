# Bài 15 — Recommendation Engine + Learning Plan Generator

## 1. Mục tiêu buổi học

Hiểu cách hệ thống biến một chẩn đoán (Bài 14) thành hành động cụ thể, và khắc sâu một
điểm dễ gây hiểu lầm nhất: **Learning Plan KHÔNG phải do AI "sáng tạo" ra — nó được xây
bằng luật/heuristic, LLM chỉ đóng vai trò diễn đạt lại bằng ngôn ngữ tự nhiên.**

## 2. Kiến thức cần nhớ trước

Bài 11-12 (K-Means), Bài 14 (Diagnosis Engine).

## 3. Giải thích từ con số 0

Sau khi biết "nguyên nhân là gì" (Diagnosis Engine, Bài 14), hệ thống cần trả lời "vậy
phải làm gì?" — đây là công việc của 2 thành phần:
- **Recommendation Engine (Bộ máy khuyến nghị)**: sinh ra gợi ý hành động dựa trên chẩn
  đoán VÀ dựa trên phân cụm (Bài 11) — ví dụ so sánh điểm mạnh/yếu của một cụm sinh viên
  với trung bình chung để đề xuất ưu tiên can thiệp.
- **Learning Plan Generator (Bộ sinh kế hoạch học tập)**: đóng gói khuyến nghị thành một
  kế hoạch có cấu trúc theo tuần, có mục tiêu ngắn hạn/dài hạn cụ thể cho từng sinh viên.

## 4. Giải thích kỹ thuật

Cả hai đều là **rule-based/heuristic** (dựa trên luật/quy tắc kinh nghiệm), KHÔNG phải
machine learning. Cụ thể:
- Recommendation dựa trên **cosine similarity** (độ tương đồng cosine) để tìm "bạn học
  tương đồng" trong CÙNG một cụm K-Means — gợi ý phương pháp học đã hiệu quả với những
  sinh viên tương tự.
- `LearningPlanGenerator` (`dss/services/learning_plan.py`) nhận đầu vào là kết quả chẩn
  đoán + hồ sơ học tập, áp dụng các quy tắc để quyết định: chủ đề ưu tiên nào, tần suất
  luyện tập bao nhiêu, thời lượng mỗi buổi học, mục tiêu ngắn/trung hạn.
- **LLM chỉ được gọi SAU KHI cấu trúc kế hoạch đã hoàn chỉnh** — vai trò của LLM là
  "diễn đạt" (narrate) kế hoạch đó bằng văn phong tự nhiên, khích lệ, dễ hiểu cho sinh
  viên — LLM không quyết định nội dung kế hoạch là gì.

## 5. Ví dụ cực dễ hiểu

Giống như một huấn luyện viên thể hình: sau khi biết bạn yếu ở phần "sức bền" (chẩn
đoán), huấn luyện viên (Recommendation Engine) lập ra một lịch tập cụ thể — "chạy bộ 20
phút, 3 buổi/tuần" (kế hoạch có cấu trúc); rồi một trợ lý viết lại thành lời động viên
"Bạn đã sẵn sàng cho 3 buổi chạy bộ tuần này chưa? Hãy bắt đầu từ 20 phút nhé!" (LLM diễn
đạt lại — không phải huấn luyện viên thật quyết định).

## 6. Ví dụ trực tiếp trong EduDSS

Khi Sinh viên có chẩn đoán `LOW_PRACTICE` (ít luyện tập), `LearningPlanGenerator` tạo kế
hoạch: chủ đề ưu tiên = môn có tỷ lệ hoàn thành bài tập thấp nhất; tần suất = tăng dần
theo tuần; mục tiêu ngắn hạn = hoàn thành 80% bài tập trong 2 tuần. Sau đó LLM được gọi
để viết đoạn văn khích lệ trình bày kế hoạch này cho sinh viên đọc trên giao diện.

## 7. Luồng xử lý thực tế trong project

```
Diagnosis Engine (Bài 14) → category chẩn đoán + evidence
  → Recommendation Engine: nếu có phân cụm, so sánh với cụm (Bài 11) + tìm bạn học tương
    đồng bằng cosine similarity
  → LearningPlanGenerator: áp luật để quyết định chủ đề/tần suất/mục tiêu/hoạt động cụ thể
    → tạo cấu trúc StudentLearningPlan (JSON có cấu trúc, chưa phải văn bản tự nhiên)
  → LLM Gateway (Bài 18) được gọi để "narrate" (diễn đạt) cấu trúc đó thành văn bản
    tự nhiên, khích lệ
  → hiển thị cho Sinh viên trên tab "Kế hoạch học tập"
```

## 8. Công thức nếu có

Cosine similarity (dùng để tìm bạn học tương đồng trong cùng cụm):
`cos(A,B) = (A·B) / (||A|| * ||B||)`

## 9. Giải thích từng ký hiệu trong công thức

- `A`, `B` — hai vector đặc trưng học tập của hai sinh viên (ví dụ điểm số, hành vi học
  tập được biểu diễn dưới dạng số).
- `A·B` — tích vô hướng (dot product) giữa hai vector.
- `||A||`, `||B||` — độ dài (norm) của mỗi vector.
- Kết quả — một số từ -1 đến 1, càng gần 1 nghĩa là hai sinh viên có đặc điểm học tập
  càng giống nhau (theo hướng vector, không phụ thuộc độ lớn tuyệt đối).

## 10. Cách đọc kết quả

Kết quả cuối cùng là một `StudentLearningPlan` có cấu trúc (không phải chỉ một đoạn văn)
— gồm điểm mạnh/yếu, chủ đề ưu tiên, mục tiêu, danh sách hoạt động cụ thể kèm lý do và
kết quả kỳ vọng. Đọc là "kế hoạch được XÂY DỰNG bởi luật, sau đó ĐƯỢC LLM DIỄN ĐẠT lại" —
không đọc là "AI tự nghĩ ra kế hoạch này."

## 11. Vì sao project dùng phương pháp này

Tách biệt "quyết định nội dung" (luật, minh bạch, kiểm chứng được) khỏi "cách trình bày"
(LLM, linh hoạt về ngôn ngữ) giúp đảm bảo kế hoạch học tập luôn nhất quán về logic, đồng
thời vẫn có văn phong tự nhiên, dễ tiếp cận cho sinh viên.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là bước áp chót của Chuỗi 1: `... → Diagnosis Engine → Recommendation → Learning Plan
→ Sinh viên hành động`. Nó cũng là điểm giao giữa Chuỗi 1 (ML/DSS) và LLM Gateway (Bài
18) — nơi hai phần lớn của hệ thống gặp nhau.

## 13. Input là gì

Kết quả chẩn đoán từ Diagnosis Engine, kết quả phân cụm (nếu có), Student Learning
Profile.

## 14. Output là gì

Một `StudentLearningPlan` có cấu trúc: điểm mạnh/yếu, chẩn đoán, chủ đề ưu tiên, mục
tiêu ngắn/trung hạn, danh sách hoạt động cụ thể, kế hoạch đánh giá.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho LLM Gateway (Bài 18) để diễn đạt thành văn bản tự nhiên, rồi hiển thị cho Sinh
viên.

## 16. Ưu điểm

Minh bạch, có thể kiểm chứng logic từng bước, nhất quán, không phụ thuộc vào "tâm trạng"
ngẫu nhiên của một LLM để quyết định nội dung quan trọng.

## 17. Nhược điểm

Kém linh hoạt hơn một hệ thống hoàn toàn dựa trên AI sinh tạo (generative AI) khi gặp
tình huống không lường trước trong luật.

## 18. Limitation thực tế của project

Recommendation dựa trên cosine similarity trong CÙNG một cụm, KHÔNG phải collaborative
filtering quy mô lớn (không có ma trận người dùng-sản phẩm khổng lồ như hệ thống gợi ý
thương mại điện tử thật).

## 19. Hội đồng có thể hỏi gì

"AI có tự sinh ra kế hoạch học tập này không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. Nội dung và cấu trúc của kế hoạch học tập — chủ đề ưu tiên, tần suất, mục tiêu —
được quyết định bởi một bộ luật (rule-based generator) dựa trên chẩn đoán và hồ sơ học
tập của sinh viên. Ngôn ngữ mô hình (LLM) chỉ được gọi SAU KHI cấu trúc đã hoàn chỉnh, để
diễn đạt nó thành văn bản tự nhiên, khích lệ — LLM không quyết định nội dung kế hoạch."

## 21. Câu trả lời chi tiết

Trình bày luồng xử lý ở mục 7, nhấn mạnh ranh giới rõ ràng giữa "quyết định nội dung"
(luật) và "diễn đạt" (LLM) — đây là thiết kế có chủ đích để đảm bảo tính nhất quán và
minh bạch.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy nếu chỉ là luật, kế hoạch có thực sự cá nhân hóa (personalized) không?"

## 23. Cách trả lời câu vặn

"Có — vì luật áp dụng trên hồ sơ CỤ THỂ của từng sinh viên (điểm số, hành vi, chẩn đoán
riêng), nên kết quả đầu ra khác nhau giữa các sinh viên khác nhau. Cá nhân hóa ở đây đến
từ việc luật phản ứng với dữ liệu đầu vào riêng của từng người, không nhất thiết phải đến
từ một mô hình học máy phức tạp mới được gọi là cá nhân hóa."

## 24. Những câu không được nói

- "AI/LLM tự thiết kế kế hoạch học tập từ đầu." (Sai.)
- "Recommendation Engine dùng collaborative filtering quy mô lớn giống các nền tảng
  thương mại điện tử." (Sai — chỉ dùng cosine similarity trong cùng cụm.)

## 25. 10 câu tự kiểm tra

1. Recommendation Engine dựa trên công thức nào để tìm bạn học tương đồng?
2. Công thức cosine similarity là gì?
3. LearningPlanGenerator là rule-based hay ML-based?
4. LLM đóng vai trò gì trong việc tạo Learning Plan?
5. `StudentLearningPlan` chứa những thành phần nào?
6. Vì sao tách biệt "quyết định nội dung" và "diễn đạt bằng LLM"?
7. Recommendation Engine có dùng collaborative filtering quy mô lớn không?
8. Input của Learning Plan Generator là gì?
9. Output của Learning Plan Generator chuyển tiếp cho module nào?
10. Vì sao kế hoạch vẫn được coi là "cá nhân hóa" dù dựa trên luật?

## 26. Đáp án riêng

1. Cosine similarity, trong phạm vi cùng một cụm K-Means.
2. `cos(A,B) = (A·B)/(||A||*||B||)`.
3. Rule-based (dựa trên luật/heuristic).
4. Diễn đạt (narrate) cấu trúc kế hoạch đã có sẵn thành văn bản tự nhiên, khích lệ.
5. Điểm mạnh/yếu, chẩn đoán, chủ đề ưu tiên, mục tiêu ngắn/trung hạn, hoạt động cụ thể,
   kế hoạch đánh giá.
6. Để đảm bảo nội dung nhất quán, minh bạch, kiểm chứng được, trong khi vẫn có văn phong
   tự nhiên dễ tiếp cận.
7. Không — chỉ dùng cosine similarity trong phạm vi cùng cụm, không có ma trận
   người dùng-sản phẩm quy mô lớn.
8. Kết quả chẩn đoán, kết quả phân cụm (nếu có), Student Learning Profile.
9. LLM Gateway (Bài 18) để diễn đạt, sau đó hiển thị cho Sinh viên.
10. Vì luật áp dụng trên dữ liệu cụ thể của từng sinh viên, cho kết quả khác nhau giữa
    các cá nhân khác nhau.

## 27. 5 CÂU PHẢI THUỘC

1. "Learning Plan Generator là rule-based/heuristic — LLM chỉ diễn đạt, không quyết định
   nội dung."
2. "Recommendation Engine dùng cosine similarity để tìm bạn học tương đồng trong cùng
   cụm K-Means."
3. "StudentLearningPlan là một cấu trúc dữ liệu có tổ chức, không phải một đoạn văn AI
   tự do."
4. "Cá nhân hóa đến từ việc luật phản ứng với dữ liệu riêng của từng sinh viên."
5. "Recommendation Engine không phải collaborative filtering quy mô lớn."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Recommendation Engine — Bộ máy khuyến nghị
- Learning Plan Generator — Bộ sinh kế hoạch học tập
- Cosine similarity — Độ tương đồng cosine
- Narration (LLM) — Diễn đạt bằng ngôn ngữ tự nhiên
- Heuristic — Phương pháp dựa trên kinh nghiệm/quy tắc
