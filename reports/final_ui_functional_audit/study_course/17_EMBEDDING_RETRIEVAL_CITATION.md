# Bài 17 — Đào sâu Embedding, Retrieval, Citation

## 1. Mục tiêu buổi học

Đào sâu 3 khái niệm lõi kỹ thuật của RAG (Bài 16) mà hội đồng có thể hỏi chi tiết hơn:
embedding sinh ra như thế nào, retrieval được đánh giá chất lượng ra sao, và citation
được kiểm tra chống hallucination thế nào.

## 2. Kiến thức cần nhớ trước

Bài 16 (RAG tổng quan).

## 3. Giải thích từ con số 0

Máy tính không hiểu "ý nghĩa" của từ ngữ theo cách con người hiểu — nó chỉ xử lý được số.
**Embedding** là cách "dịch" một đoạn văn bản thành một dãy số (vector) sao cho các đoạn
có ý nghĩa tương tự sẽ có vector "gần nhau" trong không gian nhiều chiều. Đây là nền tảng
để máy tính có thể "so sánh ý nghĩa" bằng phép toán hình học đơn giản (khoảng cách/góc
giữa các vector).

## 4. Giải thích kỹ thuật

- **Mô hình embedding**: EduDSS dùng `sentence-transformers` (cụ thể mô hình
  `all-MiniLM-L6-v2`, có thể thấy trong tên file `.npy` được lưu, ví dụ
  `doc_018_sentence-transformers_all-MiniLM-L6-v2.npy`) — một mô hình đã được huấn luyện
  sẵn để sinh embedding chất lượng tốt cho câu/đoạn văn bản.
- **Retrieval quality metrics (chỉ số đánh giá chất lượng truy xuất)**: trong lý thuyết
  ngành, người ta thường dùng Precision@k (trong top-k kết quả trả về, bao nhiêu phần
  trăm thực sự liên quan), Recall@k (trong tất cả tài liệu liên quan có, bao nhiêu phần
  trăm được tìm thấy trong top-k), và MRR — Mean Reciprocal Rank (đo vị trí của kết quả
  liên quan đầu tiên, càng gần đầu danh sách càng tốt).
- **Citation / Hallucination check (kiểm tra trích dẫn/ảo giác)**: sau khi LLM sinh câu
  trả lời, `citation_service.py` gắn trích dẫn trỏ về đúng chunk/tài liệu đã dùng làm
  ngữ cảnh, và có một bộ kiểm tra heuristic để phát hiện nếu câu trả lời có vẻ "trích dẫn"
  điều gì đó không thực sự có trong ngữ cảnh đã cung cấp.

## 5. Ví dụ cực dễ hiểu

Embedding giống như việc gán tọa độ GPS cho mỗi câu — hai câu có ý nghĩa gần nhau sẽ có
"tọa độ" gần nhau trên một tấm bản đồ tưởng tượng có hàng trăm chiều (không phải chỉ 2
chiều như bản đồ thật). Precision@k giống như hỏi "trong 5 kết quả tìm kiếm Google đầu
tiên, có bao nhiêu cái thực sự hữu ích?" Recall@k giống như hỏi "trong tất cả trang web
hữu ích tồn tại, Google đã hiển thị được bao nhiêu trong top 5?"

## 6. Ví dụ trực tiếp trong EduDSS

Khi một tài liệu được tải lên, mỗi chunk của nó được lưu kèm một file `.npy` chứa vector
embedding tương ứng, được đặt tên rõ ràng theo mô hình embedding đã dùng (để tránh nhầm
lẫn nếu sau này đổi mô hình embedding khác — một manifest ngầm định qua tên file).

## 7. Luồng xử lý thực tế trong project

```
Chunk văn bản → sentence-transformers (all-MiniLM-L6-v2) → vector embedding (.npy)
  → lưu vào LocalVectorStore cùng metadata (document_id, vị trí chunk, nội dung gốc)
  → câu hỏi → embedding hóa cùng mô hình → so sánh cosine similarity với mọi vector đã lưu
  → chọn top-k, lọc theo ngưỡng (Bài 16) → ghép context → gửi LLM
  → LLM trả lời → citation_service.py gắn trích dẫn + chạy kiểm tra heuristic
    chống hallucination trước khi trả về người dùng
```

## 8. Công thức nếu có

```
Precision@k = (số kết quả liên quan trong top-k) / k
Recall@k    = (số kết quả liên quan trong top-k) / (tổng số kết quả liên quan có)
MRR         = (1/|Q|) * Σ (1 / rank của kết quả liên quan đầu tiên)
```

## 9. Giải thích từng ký hiệu trong công thức

- `k` — số lượng kết quả được xem xét ở đầu danh sách truy xuất (ví dụ top-5).
- `|Q|` — tổng số câu hỏi trong tập đánh giá.
- `rank` — vị trí (thứ hạng) của kết quả liên quan ĐẦU TIÊN trong danh sách trả về cho
  một câu hỏi cụ thể (rank=1 nghĩa là kết quả đúng nằm ngay đầu danh sách).
- `1/rank` — giá trị nghịch đảo của rank; càng gần đầu danh sách (rank nhỏ), giá trị này
  càng lớn — MRR thưởng cho việc kết quả đúng xuất hiện SỚM.

## 10. Cách đọc kết quả

Precision@k cao → hệ thống ít trả về kết quả "rác" không liên quan. Recall@k cao → hệ
thống ít bỏ sót thông tin liên quan quan trọng. MRR gần 1 → kết quả đúng thường xuất hiện
ngay đầu danh sách truy xuất.

## 11. Vì sao project dùng phương pháp này

`sentence-transformers` là một họ mô hình embedding phổ biến, nhẹ, chạy được cục bộ
(không cần gọi API bên ngoài để sinh embedding), phù hợp với việc EduDSS chạy trên máy
cục bộ hoặc server nhỏ, không phụ thuộc hoàn toàn vào nhà cung cấp LLM bên ngoài chỉ để
tính embedding.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là phần "lõi kỹ thuật" bên trong Chuỗi 2 (RAG, Bài 16) — cụ thể hóa các bước
Embedding, Retrieval, Citation đã giới thiệu tổng quan.

## 13. Input là gì

Văn bản đã chia chunk (cho embedding); câu hỏi và các chunk đã truy xuất (cho citation).

## 14. Output là gì

Vector embedding cho mỗi chunk; danh sách chunk được xếp hạng theo độ liên quan; câu trả
lời có trích dẫn đã qua kiểm tra heuristic.

## 15. Output được chuyển cho module nào tiếp theo

Embedding được lưu vào Vector Store; kết quả truy xuất được chuyển cho LLM Gateway
(Bài 18); câu trả lời có trích dẫn được hiển thị qua Learning Explainer (Bài 19).

## 16. Ưu điểm

Embedding cục bộ không phụ thuộc API bên ngoài cho bước này; có cơ chế kiểm tra trích
dẫn giúp tăng độ tin cậy.

## 17. Nhược điểm

Nếu đổi mô hình embedding, các vector cũ trở nên không tương thích trực tiếp (phải tính
lại toàn bộ) — đã quan sát thấy hiện tượng một số tài liệu chỉ có file `.npy` cho một
trong hai mô hình embedding đã từng dùng, cho thấy rủi ro "lệch pha" (stale embeddings)
nếu không quản lý phiên bản mô hình chặt chẽ.

## 18. Limitation thực tế của project

Không có một file manifest tường minh ánh xạ document_id → phiên bản mô hình embedding
đã dùng ngoài việc đặt tên file — đây là một điểm rủi ro vận hành thực tế đã được ghi
nhận; bộ kiểm tra hallucination là heuristic, không phải một cơ chế bảo đảm hình thức
(formal guarantee).

## 19. Hội đồng có thể hỏi gì

"Bạn dùng mô hình embedding nào? Làm sao đảm bảo embedding không bị lỗi thời khi đổi mô
hình?"

## 20. Câu trả lời ngắn 20–40 giây

"Em dùng mô hình `all-MiniLM-L6-v2` từ thư viện `sentence-transformers`. Mỗi vector
embedding được lưu kèm tên mô hình đã dùng để sinh ra nó, giúp phát hiện nếu sau này đổi
mô hình. Tuy nhiên em cũng thẳng thắn nhận ra đây là một điểm cần cải thiện — hiện chưa
có một manifest chính thức theo dõi phiên bản mô hình một cách có hệ thống, chỉ dựa vào
quy ước đặt tên file."

## 21. Câu trả lời chi tiết

Trình bày công thức Precision@k/Recall@k/MRR ở mục 8-9 nếu được hỏi về cách đánh giá
chất lượng retrieval một cách học thuật, kể cả khi EduDSS không tự động tính các chỉ số
này theo quy trình đánh giá chính thức (đây là kiến thức nền tảng cần biết, không nhất
thiết là con số đã đo được trong hệ thống).

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy nếu bộ kiểm tra hallucination là heuristic, làm sao đảm bảo trích dẫn luôn đúng?"

## 23. Cách trả lời câu vặn

"Không có đảm bảo tuyệt đối. Bộ kiểm tra heuristic giúp phát hiện các trường hợp rõ ràng
bất thường, nhưng em không tuyên bố zero-hallucination. Đây là một giới hạn thực tế được
ghi nhận rõ ràng trong tài liệu bảo vệ — cơ chế grounding (ép trả lời dựa trên ngữ cảnh
truy xuất) làm giảm đáng kể rủi ro so với hỏi thẳng LLM, nhưng không loại bỏ hoàn toàn."

## 24. Những câu không được nói

- "Hệ thống đảm bảo 100% trích dẫn chính xác, không bao giờ hallucination."
- "Retrieval được đánh giá bằng Precision@k/Recall@k/MRR một cách tự động trong hệ
  thống." (Đây là kiến thức nền cần biết, nhưng không tuyên bố đã đo đạc chính thức nếu
  chưa có bằng chứng cụ thể trong code.)

## 25. 10 câu tự kiểm tra

1. Mô hình embedding EduDSS sử dụng là gì?
2. Vì sao vector embedding được lưu kèm tên mô hình đã dùng?
3. Precision@k đo cái gì?
4. Recall@k đo cái gì?
5. MRR đo cái gì, công thức ra sao?
6. Rank trong công thức MRR nghĩa là gì?
7. Citation service làm gì sau khi LLM sinh câu trả lời?
8. Bộ kiểm tra hallucination trong EduDSS là loại cơ chế gì — heuristic hay bảo đảm hình
   thức?
9. Rủi ro gì xảy ra nếu đổi mô hình embedding mà không tính lại toàn bộ vector cũ?
10. Vì sao dùng sentence-transformers chạy cục bộ thay vì gọi API bên ngoài để tính
    embedding?

## 26. Đáp án riêng

1. `sentence-transformers`, mô hình `all-MiniLM-L6-v2`.
2. Để phát hiện và quản lý nếu sau này đổi sang mô hình embedding khác.
3. Tỷ lệ kết quả liên quan trong top-k kết quả trả về.
4. Tỷ lệ kết quả liên quan được tìm thấy trong top-k so với tổng số kết quả liên quan có.
5. Đo vị trí kết quả liên quan đầu tiên; `MRR = (1/|Q|) * Σ(1/rank)`.
6. Thứ hạng của kết quả liên quan đầu tiên trong danh sách trả về cho một câu hỏi.
7. Gắn trích dẫn trỏ về tài liệu gốc, chạy kiểm tra heuristic chống hallucination.
8. Heuristic — không phải một bảo đảm hình thức tuyệt đối.
9. Vector cũ và mới không tương thích trực tiếp, có thể gây kết quả truy xuất sai lệch
   (stale embeddings).
10. Để không phụ thuộc hoàn toàn vào nhà cung cấp AI bên ngoài chỉ để tính embedding,
    giảm chi phí và độ trễ.

## 27. 5 CÂU PHẢI THUỘC

1. "Embedding dùng sentence-transformers (all-MiniLM-L6-v2), chạy cục bộ."
2. "Precision@k đo độ 'sạch' của kết quả; Recall@k đo độ 'đầy đủ'; MRR đo vị trí kết quả
   đúng đầu tiên."
3. "Citation service gắn trích dẫn và chạy kiểm tra heuristic — không phải bảo đảm hình
   thức tuyệt đối."
4. "Rủi ro lệch pha embedding tồn tại nếu đổi mô hình mà không tính lại toàn bộ vector."
5. "Không tuyên bố zero-hallucination — chỉ giảm rủi ro đáng kể so với hỏi thẳng LLM."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Sentence embedding — Biểu diễn nhúng câu
- Precision@k / Recall@k — Độ chính xác/độ bao phủ tại top-k
- MRR (Mean Reciprocal Rank) — Hạng nghịch đảo trung bình
- Hallucination check — Kiểm tra ảo giác/bịa đặt
- Stale embedding — Embedding lỗi thời (do đổi mô hình)
