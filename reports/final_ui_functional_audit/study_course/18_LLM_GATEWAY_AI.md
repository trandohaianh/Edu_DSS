# Bài 18 — LLM Gateway và Kiến trúc AI đa nhà cung cấp

## 1. Mục tiêu buổi học

Hiểu vì sao cần một "cổng gọi AI tập trung" (LLM Gateway) thay vì gọi trực tiếp từng nhà
cung cấp, cơ chế concurrency (đồng thời) và xử lý lỗi, và giới hạn `MAX_CONCURRENT_
REQUESTS=3` nghĩa là gì.

## 2. Kiến thức cần nhớ trước

Bài 16 (RAG — nơi LLM được gọi), Bài 2 (kiến trúc phân lớp).

## 3. Giải thích từ con số 0

EduDSS không tự xây một mô hình ngôn ngữ lớn (LLM) từ đầu — việc đó cần dữ liệu và tài
nguyên tính toán khổng lồ. Thay vào đó, hệ thống **gọi đến các nhà cung cấp AI bên ngoài**
(Google Gemini, Groq, OpenAI, hoặc Ollama chạy cục bộ) qua API. Vấn đề là: nếu để mỗi nơi
trong code tự gọi API theo cách riêng, sẽ khó quản lý lỗi, khó giới hạn số lượng request
đồng thời, khó ghi log thống nhất. Giải pháp là dùng một **"cổng" (Gateway)** duy nhất —
mọi lời gọi AI đều phải đi qua đây.

## 4. Giải thích kỹ thuật

`dss/services/llm_gateway.py` là điểm gọi tập trung duy nhất cho mọi tương tác với LLM.
Các cơ chế chính:
- **Multi-provider routing (định tuyến đa nhà cung cấp)**: hỗ trợ Gemini, Groq, OpenAI,
  Ollama (cục bộ) — có một chuỗi dự phòng (fallback cascade): nếu nhà cung cấp chính lỗi,
  thử nhà cung cấp phụ, rồi Ollama, rồi chế độ Demo (đã bị tắt trong `REAL_LMS`, xem
  Bài 24).
- **Retry (thử lại)**: dùng thư viện Tenacity, một lớp thử lại duy nhất — không thử lại
  vô hạn, không thử lại giữa chừng khi đang stream dữ liệu.
- **Concurrency control (kiểm soát đồng thời)**: dùng `threading.Semaphore
  (MAX_CONCURRENT_REQUESTS)` — một loại "vé vào cửa" giới hạn số lượng request AI được xử
  lý CÙNG LÚC. `MAX_CONCURRENT_REQUESTS = 3` nghĩa là tối đa 3 người dùng có thể có một
  request AI đang "chạy" cùng lúc; request thứ 4 phải chờ đến khi có 1 trong 3 "vé" được
  trả lại.
- **Key masking (che khóa API)**: khóa API được che (mask) khi hiển thị trên giao diện
  Admin, không bao giờ lộ toàn bộ.

## 5. Ví dụ cực dễ hiểu

Giống như một nhà hàng chỉ có 3 bàn phục vụ món đặc biệt cùng lúc (Semaphore=3) — khách
thứ 4 phải đợi. Nếu đầu bếp chính (nhà cung cấp AI chính) bị ốm, nhà hàng có đầu bếp dự
phòng (nhà cung cấp phụ) sẵn sàng thay thế (fallback cascade).

## 6. Ví dụ trực tiếp trong EduDSS

Khi 4 Sinh viên cùng lúc hỏi AI Advisor, 3 người được xử lý ngay, người thứ 4 phải chờ.
Trong chế độ `REAL_LMS`, nếu tất cả nhà cung cấp đều lỗi/hết hạn mức, hệ thống hiển thị
thông báo trung thực "dịch vụ AI hiện không khả dụng" thay vì trả lời giả (đây là kết quả
của việc sửa lỗi `DEMO-CONCURRENCY-001`).

## 7. Luồng xử lý thực tế trong project

```
Yêu cầu AI từ bất kỳ tab nào (AI Advisor, Learning Explainer, Career Advisor...)
  → llm_gateway.py: xin "vé" từ Semaphore(3)
    → nếu có vé: gọi nhà cung cấp chính → nếu lỗi: Tenacity thử lại (retry) một lần
      → nếu vẫn lỗi: chuyển sang nhà cung cấp phụ → ... → Ollama
      → nếu tất cả lỗi và ở REAL_LMS: trả về thông báo trung thực "không khả dụng"
    → nếu không có vé (đã đủ 3 request đang chạy): chờ hoặc báo quá tải
  → ghi log sử dụng (provider, model, thời gian) vào file JSON
  → trả kết quả về cho tab gọi
```

## 8. Công thức nếu có

Không có công thức toán riêng cho Gateway — đây là bài về cơ chế điều phối
(orchestration), không phải công thức số học. Công thức token/cost đã học có thể nhắc lại:
`estimated_cost = input_tokens * price_input + output_tokens * price_output`

## 9. Giải thích từng ký hiệu trong công thức

- `input_tokens` — số token (đơn vị xử lý văn bản) trong câu hỏi + ngữ cảnh gửi đến LLM.
- `output_tokens` — số token trong câu trả lời LLM sinh ra.
- `price_input`, `price_output` — đơn giá cấu hình sẵn cho mỗi loại token (KHÔNG phải
  giá thực tế lấy trực tiếp từ API billing của nhà cung cấp).

## 10. Cách đọc kết quả

Nếu thấy log ghi "provider=Groq, retry=1, thành công" — nghĩa là nhà cung cấp chính lỗi
lần đầu nhưng retry thành công. Nếu thấy "tất cả provider thất bại, trả về honest
unavailable" — đây là hành vi ĐÚNG trong `REAL_LMS`, không phải lỗi hệ thống.

## 11. Vì sao project dùng phương pháp này

Tập trung hóa việc gọi AI vào một cổng duy nhất giúp: quản lý lỗi nhất quán, dễ thêm nhà
cung cấp mới, dễ giới hạn tải, dễ ghi log sử dụng tập trung để theo dõi chi phí — thay vì
rải rác logic gọi API ở nhiều nơi trong code.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Là điểm hội tụ của cả 2 chuỗi: Chuỗi 1 (Learning Plan cần LLM diễn đạt, Bài 15) và Chuỗi
2 (RAG cần LLM sinh câu trả lời, Bài 16) đều đi qua LLM Gateway.

## 13. Input là gì

Một prompt (câu hỏi + ngữ cảnh) cần gửi đến LLM, từ bất kỳ tính năng nào cần AI.

## 14. Output là gì

Câu trả lời từ LLM, hoặc một thông báo lỗi/không khả dụng trung thực nếu tất cả nhà cung
cấp đều thất bại.

## 15. Output được chuyển cho module nào tiếp theo

Tùy tính năng gọi: Learning Plan (Bài 15) để diễn đạt, RAG/Citation (Bài 16-17) để trả
lời có trích dẫn, Career Advisor (Bài 20) để tư vấn.

## 16. Ưu điểm

Quản lý lỗi và tải tập trung, dễ mở rộng thêm nhà cung cấp, tránh lộ khóa API, có log sử
dụng để theo dõi.

## 17. Nhược điểm

Semaphore giới hạn 3 request đồng thời có thể là nút thắt cổ chai (bottleneck) khi nhiều
người dùng cùng lúc; retry chỉ có 1 lớp, không phải cơ chế phục hồi phức tạp.

## 18. Limitation thực tế của project

`MAX_CONCURRENT_REQUESTS=3` là một hằng số cấu hình, **chưa từng được kiểm thử tải
(load test)** để xác định đây có phải con số tối ưu hay không; token/cost tracking dùng
đơn giá cấu hình sẵn, không phải tích hợp API billing thời gian thực của nhà cung cấp.

## 19. Hội đồng có thể hỏi gì

"Nếu 100 sinh viên cùng lúc hỏi AI, hệ thống xử lý thế nào?"

## 20. Câu trả lời ngắn 20–40 giây

"Hệ thống giới hạn tối đa 3 request AI được xử lý đồng thời, thông qua một cơ chế gọi là
Semaphore. Với 100 yêu cầu cùng lúc, 3 yêu cầu đầu được xử lý ngay, các yêu cầu còn lại
phải xếp hàng chờ. Đây là một con số cấu hình mặc định, và em thẳng thắn thừa nhận nó
chưa được kiểm thử tải để xác định đây có phải giá trị tối ưu cho quy mô thực tế hay
không — đó là một hạng mục công việc tương lai."

## 21. Câu trả lời chi tiết

Trình bày luồng xử lý ở mục 7, giải thích Semaphore bằng ví dụ nhà hàng ở mục 5, và nêu
rõ hành vi honest-failure trong `REAL_LMS` khi tất cả nhà cung cấp đều lỗi.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy tại sao chọn con số 3 mà không phải một con số khác?"

## 23. Cách trả lời câu vặn

"Con số 3 được chọn như một giá trị mặc định hợp lý cho quy mô thử nghiệm/demo của đồ
án, không dựa trên một phép đo tải thực tế. Đây là một điểm hạn chế em ghi nhận rõ ràng —
việc xác định con số tối ưu cho một triển khai thực tế sẽ cần load testing với số lượng
người dùng đồng thời mô phỏng thực tế, điều nằm ngoài phạm vi thời gian của đồ án này."

## 24. Những câu không được nói

- "Hệ thống đã được kiểm thử với tải thực tế lớn." (Sai — chưa load-test.)
- "Chi phí AI được tính chính xác theo giá billing thực tế của nhà cung cấp." (Sai — chỉ
  là ước tính dựa trên đơn giá cấu hình sẵn.)

## 25. 10 câu tự kiểm tra

1. LLM Gateway nằm ở file nào?
2. Kể tên các nhà cung cấp AI được hỗ trợ.
3. `MAX_CONCURRENT_REQUESTS` bằng bao nhiêu?
4. Semaphore dùng để làm gì?
5. Fallback cascade là gì?
6. Điều gì xảy ra khi tất cả nhà cung cấp đều lỗi trong chế độ REAL_LMS?
7. Retry trong LLM Gateway dùng thư viện nào?
8. Vì sao khóa API cần được che (mask) trên giao diện?
9. Token/cost tracking trong EduDSS có chính xác theo billing thực tế không?
10. MAX_CONCURRENT_REQUESTS=3 đã được load-test chưa?

## 26. Đáp án riêng

1. `dss/services/llm_gateway.py`.
2. Google Gemini, Groq, OpenAI, Ollama (cục bộ).
3. 3.
4. Giới hạn số lượng request AI được xử lý đồng thời.
5. Chuỗi dự phòng: nếu nhà cung cấp chính lỗi, tự động thử nhà cung cấp phụ, rồi Ollama.
6. Trả về thông báo trung thực "không khả dụng", không bịa câu trả lời.
7. Tenacity.
8. Để tránh lộ thông tin nhạy cảm cho người xem giao diện Admin hoặc ảnh chụp màn hình.
9. Không — chỉ là ước tính dựa trên đơn giá cấu hình sẵn, không tích hợp API billing
   thời gian thực.
10. Chưa — đây là một hằng số cấu hình mặc định, chưa qua kiểm thử tải.

## 27. 5 CÂU PHẢI THUỘC

1. "LLM Gateway là điểm gọi AI tập trung duy nhất, hỗ trợ Gemini/Groq/OpenAI/Ollama."
2. "MAX_CONCURRENT_REQUESTS=3, dùng Semaphore, CHƯA được load-test."
3. "Trong REAL_LMS, khi tất cả nhà cung cấp lỗi, hệ thống trả về thông báo trung thực,
   không bịa câu trả lời."
4. "Retry dùng Tenacity, một lớp duy nhất, không thử lại giữa chừng khi đang stream."
5. "Token/cost tracking là ước tính dựa trên đơn giá cấu hình, không phải billing thời
   gian thực."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- LLM Gateway — Cổng gọi mô hình ngôn ngữ tập trung
- Semaphore — Cơ chế giới hạn truy cập đồng thời
- Fallback cascade — Chuỗi dự phòng
- Retry — Thử lại
- Honest failure — Thất bại trung thực (không bịa kết quả)
