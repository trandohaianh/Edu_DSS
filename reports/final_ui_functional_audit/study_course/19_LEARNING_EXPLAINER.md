# Bài 19 — Learning Explainer (Ứng dụng thực tế của RAG)

## 1. Mục tiêu buổi học

Hiểu Learning Explainer là "sản phẩm hoàn chỉnh" ghép nối toàn bộ Chuỗi 2 (RAG) lại với
nhau thành một tính năng người dùng thực sự sử dụng được, và hiểu rõ giới hạn cold-start
(khởi động nguội) ~55-60 giây.

## 2. Kiến thức cần nhớ trước

Bài 16, 17 (RAG, Embedding/Retrieval/Citation), Bài 18 (LLM Gateway).

## 3. Giải thích từ con số 0

Nếu Bài 16-18 dạy về "cỗ máy" đứng sau (RAG pipeline, LLM Gateway), thì Learning
Explainer là "sản phẩm cuối cùng" mà Sinh viên thực sự chạm vào: một khung chat nơi họ có
thể hỏi bất kỳ câu hỏi nào về nội dung bài giảng đã được Giảng viên tải lên, và nhận câu
trả lời có trích dẫn cụ thể.

## 4. Giải thích kỹ thuật

Learning Explainer KHÔNG phải một module riêng biệt về mặt kỹ thuật — nó là **giao diện
người dùng (UI)** gọi trực tiếp vào Chuỗi 2 đã học (RAG + LLM Gateway + Citation). Các
tính năng cụ thể được kiểm chứng riêng biệt (mỗi tính năng con có trạng thái PASS/PARTIAL
riêng, KHÔNG được gộp chung thành một "PASS" duy nhất):
- **Ingestion (nạp tài liệu)** — Giảng viên tải file lên, hệ thống phân tích và chia
  chunk — PASS.
- **Browser upload (tải qua trình duyệt)** — giao diện tải file hoạt động đúng — PASS.
- **Retrieval (truy xuất)** — tìm đúng chunk liên quan — PASS, đã kiểm chứng live.
- **Isolation (cách ly)** — mỗi lớp/tài liệu được cách ly đúng phạm vi truy cập — PASS.
- **Version pinning (ghim phiên bản)** — mỗi embedding gắn với đúng phiên bản mô hình đã
  sinh ra nó (xem Bài 17) — PASS nhưng còn thô sơ (chỉ qua tên file).
- **AI generation (sinh câu trả lời)** — LLM trả lời dựa trên ngữ cảnh — PASS.
- **Citation (trích dẫn)** — trả lời kèm trích dẫn cụ thể, đã kiểm chứng live với một
  trích dẫn thật — PASS.
- **Follow-up (câu hỏi tiếp nối)** — hỏi thêm trong cùng ngữ cảnh hội thoại — PASS.
- **Socratic (hỏi ngược kiểu Socrates)** — AI có thể đặt câu hỏi gợi mở lại cho sinh viên
  thay vì trả lời trực tiếp — cần kiểm tra riêng theo từng ngữ cảnh sử dụng cụ thể.
- **Quiz/practice (câu hỏi luyện tập)** — sinh câu hỏi luyện tập từ nội dung tài liệu —
  cần kiểm tra riêng.

## 5. Ví dụ cực dễ hiểu

Giống như một gia sư riêng đọc trước toàn bộ sách giáo khoa của bạn (ingestion), rồi khi
bạn hỏi "Kỹ thuật Pomodoro là gì?", gia sư lật đúng trang có nội dung đó (retrieval), đọc
đoạn đó (context), rồi giải thích lại bằng lời của mình (LLM generation), và chỉ rõ "tôi
lấy thông tin này từ trang 15" (citation) — không phải "nói bừa" theo trí nhớ mơ hồ.

## 6. Ví dụ trực tiếp trong EduDSS

Trong quá trình kiểm thử trước đó, đã thực hiện một bài test "closed-loop" (vòng lặp
khép kín) thực tế: tải lên một tài liệu, hỏi một câu hỏi liên quan, và nhận được một câu
trả lời có trích dẫn TRÍCH NGUYÊN VĂN một câu từ đúng file đã tải lên — chứng minh pipeline
hoạt động thật, không phải câu trả lời "đóng hộp" (canned response) giả lập.

## 7. Luồng xử lý thực tế trong project

```
Giảng viên/Admin tải tài liệu qua giao diện trình duyệt
  → document_ingestion.py xử lý (Bài 16-17)
  → Sinh viên mở tab Learning Explainer, đặt câu hỏi
  → (LẦN ĐẦU TIÊN trong phiên: có độ trễ cold-start ~55-60 giây do phải khởi tạo mô hình
    embedding/kết nối lần đầu)
  → RAG pipeline chạy đầy đủ (Bài 16) → LLM Gateway (Bài 18) → Citation
  → hiển thị câu trả lời + trích dẫn trên giao diện chat
  → Sinh viên có thể hỏi tiếp (follow-up), giữ nguyên ngữ cảnh hội thoại
```

## 8. Công thức nếu có

Không có công thức riêng — xem lại Bài 16 (cosine similarity, ngưỡng lọc) áp dụng trực
tiếp ở đây.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng — xem Bài 16-17.

## 10. Cách đọc kết quả

Khi đánh giá Learning Explainer, KHÔNG được nói "tính năng này PASS" một cách chung
chung — phải chỉ rõ TỪNG tính năng con (ingestion, retrieval, citation, follow-up...) ở
trạng thái nào, vì đây là một tính năng phức hợp gồm nhiều bước nhỏ có thể có mức độ
hoàn thiện khác nhau.

## 11. Vì sao project dùng phương pháp này

Ghép RAG pipeline vào một giao diện chat trực quan giúp Sinh viên tiếp cận nội dung bài
giảng theo cách tự nhiên (hỏi-đáp) thay vì phải tự tìm kiếm trong tài liệu dài.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là **điểm cuối cùng của Chuỗi 2**: `Tài liệu giảng viên → Ingestion → Chunking →
Embedding → Retrieval → Context → LLM → Citation → Learning Explainer hiển thị cho sinh
viên`.

## 13. Input là gì

Câu hỏi của Sinh viên, và tài liệu đã được Giảng viên/Admin tải lên trước đó.

## 14. Output là gì

Câu trả lời có trích dẫn cụ thể, hiển thị trong giao diện chat.

## 15. Output được chuyển cho module nào tiếp theo

Đây là điểm cuối của Chuỗi 2 — không chuyển tiếp sang module xử lý nào khác, kết quả hiển
thị trực tiếp cho người dùng.

## 16. Ưu điểm

Trải nghiệm hỏi-đáp tự nhiên, có căn cứ (grounded), có trích dẫn kiểm chứng được, đã được
kiểm chứng live với bằng chứng cụ thể.

## 17. Nhược điểm

Có độ trễ khởi động lần đầu đáng kể (~27-60 giây, đo trực tiếp: import
torch/transformers/sentence-transformers ~22s + tải mô hình ~5s); phụ thuộc chất lượng
tài liệu đã tải lên.

## 18. Limitation thực tế của project

`COLDSTART-001` — **PARTIAL kể từ 2026-09-16**: UX đã được sửa (mọi spinner trên đường
cold-start — chat, quiz, giải thích bổ sung, nạp bài giảng — giờ hiện thông báo rõ ràng
"lần đầu có thể mất khoảng 1 phút, hệ thống không bị treo"), nhưng ĐỘ TRỄ THẬT SỰ KHÔNG
ĐỔI — đây là quyết định thiết kế có chủ đích (xem Bài 18/mục 23 bên dưới), không phải
thiếu sót.

## 19. Hội đồng có thể hỏi gì

"Bạn có thể chứng minh Learning Explainer thực sự hoạt động, không phải câu trả lời giả
lập không?"

## 20. Câu trả lời ngắn 20–40 giây

"Có. Trong quá trình kiểm thử, em đã thực hiện một bài kiểm tra vòng lặp khép kín: tải
lên một tài liệu cụ thể, đặt một câu hỏi liên quan đến nội dung đó, và hệ thống trả về
một trích dẫn NGUYÊN VĂN từ đúng file đã tải lên, kèm ID trích dẫn có thể truy vết. Đây
là bằng chứng cho thấy pipeline RAG hoạt động thật — không phải một câu trả lời đóng hộp
được lập trình sẵn."

## 21. Câu trả lời chi tiết

Trình bày rõ 10 tính năng con và trạng thái của từng cái ở mục 4, nhấn mạnh nguyên tắc
không được gộp chung thành một "PASS" duy nhất — đây thể hiện sự trung thực và chi tiết
trong đánh giá.

## 22. Hội đồng có thể vặn tiếp thế nào

"Độ trễ 27-60 giây đó có chấp nhận được cho một sản phẩm thực tế không, và tại sao chỉ
sửa UX mà không sửa độ trễ?"

## 23. Cách trả lời câu vặn

"Với một sản phẩm thực tế phục vụ số lượng lớn người dùng, độ trễ này vẫn là một điểm cần
cải thiện — đây là lý do em phân loại COLDSTART-001 là PARTIAL, không phải FIXED. Em đã
cân nhắc pre-warming ở bootstrap nhưng quyết định KHÔNG làm vậy, vì điều đó sẽ chuyển độ
trễ từ 'chỉ ảnh hưởng người dùng Learning Explainer' thành 'ảnh hưởng thời gian khởi động
của TOÀN BỘ ứng dụng cho MỌI vai trò', kể cả những người không bao giờ dùng tính năng này
— một đánh đổi tệ hơn. Việc em làm là đảm bảo người dùng LUÔN biết hệ thống đang xử lý,
không bị treo, trong khi để việc tối ưu độ trễ thật sự (vd. mô hình embedding nhẹ hơn,
dịch vụ embedding riêng luôn 'ấm') làm hạng mục cải tiến tương lai."

## 24. Những câu không được nói

- "Toàn bộ Learning Explainer đã PASS hoàn toàn không có bất kỳ giới hạn nào."
- "Không có độ trễ nào khi sử dụng lần đầu." (Sai — vẫn có, chỉ là UX đã rõ ràng hơn.)
- "COLDSTART-001 đã được sửa hoàn toàn (FIXED)." (Sai — đúng trạng thái là PARTIAL: UX
  FIXED / LATENCY REMAINS.)

## 25. 10 câu tự kiểm tra

1. Learning Explainer có phải một module kỹ thuật riêng biệt không, hay là UI gọi vào
   Chuỗi 2?
2. Kể tên ít nhất 5 tính năng con của Learning Explainer.
3. Bằng chứng nào chứng minh RAG hoạt động thật, không phải giả lập?
4. COLDSTART-001 là vấn đề gì?
5. Vì sao COLDSTART-001 không được coi là lỗi đúng/sai (correctness defect)?
6. Follow-up trong Learning Explainer nghĩa là gì?
7. Vì sao không được nói "Learning Explainer PASS" một cách chung chung?
8. Version pinning trong ngữ cảnh Learning Explainer nghĩa là gì?
9. Isolation (cách ly) trong Learning Explainer đảm bảo điều gì?
10. Đầu ra cuối cùng của Learning Explainer là gì?

## 26. Đáp án riêng

1. Là UI gọi trực tiếp vào Chuỗi 2 (RAG + LLM Gateway + Citation), không phải module kỹ
   thuật riêng biệt.
2. Ingestion, Retrieval, Citation, Follow-up, Isolation (hoặc bất kỳ 5 trong 10 tính
   năng đã liệt kê).
3. Bài kiểm tra vòng lặp khép kín: trích dẫn nguyên văn từ file thật đã tải lên.
4. Độ trễ khởi động ~27-60 giây lần đầu truy cập; từ 2026-09-16 đã có thông báo tiến
   trình rõ ràng (PARTIAL — UX FIXED / LATENCY REMAINS).
5. Vì hệ thống vẫn hoạt động đúng logic, chỉ là chậm ở lần đầu — thuộc vấn đề trải
   nghiệm người dùng, không phải sai kết quả.
6. Khả năng hỏi tiếp trong cùng ngữ cảnh hội thoại đã có từ trước.
7. Vì đây là tính năng phức hợp gồm nhiều bước nhỏ có mức độ hoàn thiện khác nhau, gộp
   chung sẽ che giấu chi tiết quan trọng.
8. Đảm bảo mỗi vector embedding gắn đúng với phiên bản mô hình đã sinh ra nó.
9. Mỗi lớp/tài liệu chỉ được truy xuất trong đúng phạm vi được phép.
10. Câu trả lời có trích dẫn cụ thể hiển thị cho người dùng trong giao diện chat.

## 27. 5 CÂU PHẢI THUỘC

1. "Learning Explainer là ứng dụng thực tế của Chuỗi 2 (RAG), không phải module riêng."
2. "Đã kiểm chứng live: trích dẫn nguyên văn từ file thật, chứng minh pipeline hoạt động
   thật."
3. "10 tính năng con có trạng thái riêng biệt — không được gộp thành một 'PASS' chung."
4. "COLDSTART-001: PARTIAL — UX đã sửa (thông báo tiến trình rõ ràng), độ trễ ~27-60
   giây vẫn còn nguyên, có chủ đích, không phải lỗi logic."
5. "Learning Explainer là điểm cuối của Chuỗi 2: Tài liệu → Ingestion → ... → Citation →
   hiển thị cho sinh viên."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Learning Explainer — Tính năng giải thích bài học
- Closed-loop test — Kiểm tra vòng lặp khép kín
- Cold-start — Độ trễ khởi động lần đầu
- Follow-up question — Câu hỏi tiếp nối
- Feature-level status — Trạng thái theo từng tính năng con
