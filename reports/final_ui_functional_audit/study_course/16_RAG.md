# Bài 16 — RAG từ con số 0 (Retrieval-Augmented Generation)

## 1. Mục tiêu buổi học

Hiểu toàn bộ chuỗi RAG từ đầu đến cuối: `Document → Chunk → Embedding → Vector →
Similarity → Retrieval → Context → LLM → Citation`, và nắm được đây là **Chuỗi 2** của
hệ thống, song song với Chuỗi 1 (ML/DSS) đã học ở các bài trước.

## 2. Kiến thức cần nhớ trước

Bài 2 (kiến trúc phân lớp) — để biết RAG nằm ở lớp AI/RAG.

## 3. Giải thích từ con số 0

Một LLM (Large Language Model — mô hình ngôn ngữ lớn) như Gemini/GPT chỉ "biết" những gì
nó được huấn luyện trước đó — nó KHÔNG biết nội dung cụ thể trong bài giảng của một giảng
viên cụ thể tại một trường cụ thể. Nếu hỏi thẳng LLM về nội dung đó, nó có thể "bịa" ra
một câu trả lời nghe hợp lý nhưng sai — hiện tượng này gọi là **hallucination (ảo giác/
bịa đặt)**.

**RAG (Retrieval-Augmented Generation — Sinh văn bản có truy xuất tăng cường)** giải
quyết vấn đề này bằng cách: trước khi hỏi LLM, hệ thống **tìm (retrieve)** những đoạn văn
bản THẬT liên quan nhất từ tài liệu đã có, rồi **đưa những đoạn đó vào cùng câu hỏi** để
LLM trả lời DỰA TRÊN chúng — giống như "cho LLM mở sách để trả lời" thay vì "trả lời theo
trí nhớ."

## 4. Giải thích kỹ thuật — Chuỗi 9 bước

1. **Document (Tài liệu)** — giảng viên tải lên một file bài giảng (TXT/MD/DOCX/PPTX/
   PDF/JSON).
2. **Chunk (Phân đoạn)** — tài liệu dài được cắt thành các đoạn nhỏ hơn (chunk), vì LLM
   không thể xử lý tài liệu quá dài cùng lúc, và tìm kiếm trên đoạn nhỏ chính xác hơn.
3. **Embedding (Biểu diễn nhúng)** — mỗi đoạn văn bản được chuyển thành một vector số
   (dãy số) bằng một mô hình embedding (`sentence-transformers`), sao cho các đoạn có ý
   nghĩa gần nhau thì vector của chúng cũng "gần nhau" trong không gian số.
4. **Vector (Lưu trữ vector)** — các vector này được lưu vào kho lưu trữ vector (vector
   store).
5. **Similarity (Độ tương đồng)** — khi có câu hỏi, câu hỏi cũng được chuyển thành
   vector, rồi so sánh độ tương đồng (cosine similarity) với tất cả các vector đã lưu.
6. **Retrieval (Truy xuất)** — lấy ra các đoạn có độ tương đồng cao nhất (top-k), lọc bỏ
   những đoạn dưới ngưỡng tin cậy.
7. **Context (Ngữ cảnh)** — các đoạn được chọn được ghép lại thành "ngữ cảnh", có giới
   hạn về độ dài (context budget).
8. **LLM (Mô hình ngôn ngữ)** — câu hỏi + ngữ cảnh được gửi cho LLM để sinh câu trả lời
   DỰA TRÊN ngữ cảnh đó.
9. **Citation (Trích dẫn)** — câu trả lời kèm theo trích dẫn cụ thể trỏ về tài liệu gốc,
   để người dùng có thể kiểm chứng.

## 5. Ví dụ cực dễ hiểu

Giống như thi mở sách (open-book exam): thay vì học thuộc lòng mọi thứ, bạn được phép mở
đúng trang sách liên quan đến câu hỏi, đọc đoạn đó, rồi trả lời dựa trên nó — vừa nhanh
vừa chính xác hơn, và bạn có thể chỉ ra chính xác "tôi lấy câu trả lời từ trang nào" (
citation).

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên tải lên một tài liệu về "Kỹ thuật Pomodoro" và Sinh viên hỏi AI Advisor
"Làm sao quản lý thời gian học hiệu quả?", hệ thống tìm được đoạn văn bản nói về Pomodoro
Technique, đưa vào ngữ cảnh, LLM trả lời dựa trên đó, và câu trả lời có trích dẫn cụ thể
trỏ về tài liệu gốc — đã được kiểm chứng live (thực tế) trong quá trình audit trước đó,
với một câu trích dẫn thật trỏ về đúng file đã tải lên.

## 7. Luồng xử lý thực tế trong project

```
Giảng viên tải tài liệu → document_ingestion.py phân tích + chia chunk
  → sentence-transformers sinh embedding cho từng chunk
  → LocalVectorStore lưu embedding + metadata (KHÔNG phải PostgreSQL, xem Bài 21)
  → Sinh viên đặt câu hỏi → embedding hóa câu hỏi
  → rag_service.py tính cosine similarity giữa câu hỏi và mọi chunk đã lưu
  → lọc theo ngưỡng (RAG_LOW_CONFIDENCE_FLOOR=0.55, RAG_RELATIVE_THRESHOLD=0.85)
  → nếu có chunk đạt ngưỡng: ghép context, gửi cho LLM Gateway (Bài 18)
  → nếu KHÔNG có chunk đạt ngưỡng: trả về "không tìm thấy bằng chứng liên quan" (trung
    thực, không bịa câu trả lời)
  → citation_service.py gắn trích dẫn vào câu trả lời cuối cùng
  → hiển thị cho người dùng qua Learning Explainer (Bài 19)
```

## 8. Công thức nếu có

Cosine similarity: `cos(A,B) = (A·B) / (||A|| * ||B||)`

Ngưỡng lọc: `RAG_TOP_K_DEFAULT=5`, `RAG_RELATIVE_THRESHOLD=0.85`,
`RAG_LOW_CONFIDENCE_FLOOR=0.55`

## 9. Giải thích từng ký hiệu trong công thức

- `A` — vector embedding của câu hỏi.
- `B` — vector embedding của một chunk tài liệu.
- Kết quả `cos(A,B)` — một số từ -1 đến 1 (thực tế với embedding văn bản thường dương, từ
  0 đến 1), càng gần 1 nghĩa là câu hỏi và chunk đó càng liên quan về ý nghĩa.
- `RAG_TOP_K_DEFAULT=5` — chỉ lấy tối đa 5 chunk có điểm cao nhất để xem xét.
- `RAG_RELATIVE_THRESHOLD=0.85` — một chunk phải đạt ít nhất 85% điểm số của chunk cao
  nhất mới được giữ lại (loại bỏ chunk yếu hơn đáng kể so với chunk tốt nhất).
- `RAG_LOW_CONFIDENCE_FLOOR=0.55` — ngưỡng tuyệt đối tối thiểu; nếu không chunk nào đạt
  mức này, hệ thống từ chối trả lời thay vì ép trả lời với bằng chứng yếu.

## 10. Cách đọc kết quả

Nếu câu trả lời có trích dẫn cụ thể — đó là bằng chứng RAG hoạt động đúng (grounded —
"có căn cứ"). Nếu hệ thống trả về "không tìm thấy bằng chứng liên quan" — đây KHÔNG phải
lỗi, mà là hành vi ĐÚNG ĐẮN khi không có tài liệu nào đủ liên quan.

## 11. Vì sao project dùng phương pháp này

RAG giúp giảm hallucination, cho phép LLM trả lời dựa trên tài liệu THẬT và cụ thể của
từng giảng viên/môn học, thay vì chỉ dựa vào kiến thức chung chung đã huấn luyện sẵn của
mô hình — đặc biệt quan trọng trong giáo dục, nơi độ chính xác của thông tin rất quan
trọng.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là **toàn bộ Chuỗi 2**: `Tài liệu giảng viên → Ingestion → Chunking → Embedding →
Vector Store → Retrieval → Context → LLM → Citation → Learning Explainer hiển thị cho
sinh viên`.

## 13. Input là gì

Tài liệu do Giảng viên/Admin tải lên, và câu hỏi của người dùng.

## 14. Output là gì

Câu trả lời của LLM kèm trích dẫn cụ thể trỏ về tài liệu gốc (hoặc thông báo "không tìm
thấy bằng chứng liên quan" nếu không đạt ngưỡng).

## 15. Output được chuyển cho module nào tiếp theo

Hiển thị trực tiếp cho người dùng qua Learning Explainer (Bài 19) hoặc AI Advisor.

## 16. Ưu điểm

Giảm hallucination, câu trả lời có căn cứ và có thể kiểm chứng, cập nhật được kiến thức
mới chỉ bằng cách tải thêm tài liệu (không cần huấn luyện lại mô hình).

## 17. Nhược điểm

Chất lượng câu trả lời phụ thuộc vào chất lượng tài liệu đã tải lên; nếu tài liệu không
đầy đủ, hệ thống sẽ trung thực từ chối trả lời thay vì "đoán" — điều này tốt về độ tin
cậy nhưng có thể khiến người dùng cảm thấy hệ thống "không biết gì" với câu hỏi ngoài
phạm vi tài liệu.

## 18. Limitation thực tế của project

Kho lưu trữ vector đang dùng thực tế là `LocalVectorStore` (file-based) — KHÔNG phải
PostgreSQL dù có class `PgVectorStore` tồn tại trong code (xem Bài 21, đây là điểm hay bị
hỏi nhầm); có độ trễ khởi động (cold-start) ~55-60 giây lần đầu truy cập.

## 19. Hội đồng có thể hỏi gì

"RAG khác gì so với việc hỏi thẳng LLM (như ChatGPT) một câu hỏi?"

## 20. Câu trả lời ngắn 20–40 giây

"Nếu hỏi thẳng LLM, nó chỉ có thể trả lời dựa trên kiến thức chung nó đã học trước đó,
không biết cụ thể nội dung bài giảng của giảng viên, và có thể bịa ra thông tin sai
(hallucination). RAG giải quyết bằng cách trước tiên TÌM những đoạn văn bản thật liên
quan nhất trong tài liệu đã tải lên, rồi đưa các đoạn đó vào cùng câu hỏi để LLM trả lời
DỰA TRÊN chúng, kèm trích dẫn cụ thể để người dùng kiểm chứng được nguồn."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ chuỗi 9 bước ở mục 4, và có thể minh họa bằng ví dụ live đã kiểm chứng ở
mục 6 (câu hỏi về Pomodoro Technique).

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu tài liệu không đủ liên quan, hệ thống sẽ làm gì? Có bịa câu trả lời không?"

## 23. Cách trả lời câu vặn

"Không. Hệ thống có 2 ngưỡng lọc: một ngưỡng tuyệt đối tối thiểu (0.55) và một ngưỡng
tương đối so với chunk tốt nhất (85%). Nếu không có chunk nào vượt qua cả hai ngưỡng này,
hệ thống trả về một thông báo trung thực rằng không tìm thấy bằng chứng liên quan, thay
vì ép LLM trả lời dựa trên bằng chứng yếu hoặc không có — đây là thiết kế có chủ đích để
tránh hallucination."

## 24. Những câu không được nói

- "RAG lưu trữ vector trên PostgreSQL." (Sai — xem Bài 21, đây là LocalVectorStore.)
- "RAG không bao giờ trả lời sai." (Sai — chỉ giảm hallucination, không loại bỏ hoàn
  toàn; có cơ chế kiểm tra trích dẫn heuristic, không phải bảo đảm tuyệt đối.)

## 25. 10 câu tự kiểm tra

1. RAG là viết tắt của gì?
2. Kể tên đầy đủ 9 bước của chuỗi RAG.
3. Hallucination là gì?
4. Vì sao tài liệu phải được chia thành chunk?
5. Embedding là gì?
6. Công thức tính độ tương đồng giữa câu hỏi và một chunk là gì?
7. Hai ngưỡng lọc trong RAG của EduDSS là gì, giá trị bao nhiêu?
8. Nếu không chunk nào đạt ngưỡng, hệ thống làm gì?
9. Kho lưu trữ vector thực tế đang dùng là gì?
10. Vì sao RAG giúp giảm hallucination so với hỏi thẳng LLM?

## 26. Đáp án riêng

1. Retrieval-Augmented Generation — Sinh văn bản có truy xuất tăng cường.
2. Document → Chunk → Embedding → Vector → Similarity → Retrieval → Context → LLM →
   Citation.
3. Hiện tượng LLM bịa ra thông tin nghe hợp lý nhưng sai, không có căn cứ thật.
4. Vì LLM có giới hạn độ dài xử lý, và tìm kiếm trên đoạn nhỏ chính xác hơn tìm trên toàn
   bộ tài liệu dài.
5. Biểu diễn một đoạn văn bản dưới dạng vector số, sao cho ý nghĩa gần nhau thì vector
   gần nhau.
6. `cos(A,B) = (A·B)/(||A||*||B||)`.
7. `RAG_LOW_CONFIDENCE_FLOOR=0.55` (tuyệt đối) và `RAG_RELATIVE_THRESHOLD=0.85` (tương
   đối so với chunk tốt nhất).
8. Trả về thông báo trung thực "không tìm thấy bằng chứng liên quan", không bịa câu trả
   lời.
9. `LocalVectorStore` — file-based (NumPy + JSON), không phải PostgreSQL.
10. Vì câu trả lời được ép phải dựa trên tài liệu thật đã truy xuất, thay vì chỉ dựa vào
    trí nhớ nội tại của mô hình.

## 27. 5 CÂU PHẢI THUỘC

1. "RAG gồm 9 bước: Document→Chunk→Embedding→Vector→Similarity→Retrieval→Context→LLM→
   Citation."
2. "Hai ngưỡng lọc: tuyệt đối 0.55, tương đối 85% so với chunk tốt nhất."
3. "Nếu không đạt ngưỡng, hệ thống trung thực từ chối trả lời, không bịa thông tin."
4. "Kho lưu trữ vector thực tế đang hoạt động là LocalVectorStore (file-based), KHÔNG
   phải PostgreSQL."
5. "RAG giảm hallucination bằng cách ép câu trả lời dựa trên tài liệu thật đã truy xuất."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Retrieval-Augmented Generation (RAG) — Sinh văn bản có truy xuất tăng cường
- Chunk — Đoạn văn bản
- Embedding — Biểu diễn nhúng
- Hallucination — Ảo giác/bịa đặt của LLM
- Citation — Trích dẫn nguồn
