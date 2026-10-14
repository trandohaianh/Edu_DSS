# Bài 21 — LMS/CMS và PgVectorStore: "Có Class" ≠ "Có Kết Nối Thật"

## 1. Mục tiêu buổi học

Đây là bài giải quyết 3 hiểu lầm nguy hiểm nhất khi trình bày kiến trúc: (1) hệ thống có
kết nối LMS thật, (2) hệ thống có kết nối CMS ngoài thật, (3) hệ thống dùng PostgreSQL để
lưu vector. Cả 3 đều SAI, và bạn phải giải thích được TẠI SAO nhìn vào code dễ hiểu nhầm.

## 2. Kiến thức cần nhớ trước

Bài 2 (kiến trúc phân lớp — lớp Storage và External Integration), Bài 16 (RAG — nơi vector
store được dùng).

## 3. Giải thích từ con số 0

Trong lập trình hướng đối tượng, người ta hay dùng **mẫu thiết kế kho lưu trữ (repository
pattern)**: định nghĩa một "giao diện chung" (interface) mà nhiều cách triển khai khác
nhau có thể cắm vào. Ví dụ, một giao diện `LMSRepository` có thể có 2 lớp con:
`DemoLMSRepository` (dùng dữ liệu giả) và `RealConnectorLMSRepository` (dự định kết nối
LMS thật). **Vấn đề mấu chốt**: chỉ vì một lớp có TÊN là "RealConnector" không có nghĩa
là bên trong nó THỰC SỰ gọi ra một hệ thống bên ngoài — phải đọc code bên trong để biết
chắc.

## 4. Giải thích kỹ thuật

### LMS (Learning Management System — Hệ thống quản lý học tập)
`dss/services/lms_connector.py` có class `RealConnectorLMSRepository` — nhưng khi đọc kỹ
code bên trong, class này **NỘI BỘ GỌI LẠI** `DemoLMSRepository` — nghĩa là dù tên gọi là
"Real", nó KHÔNG hề gửi bất kỳ request mạng nào đến một hệ thống LMS thật (như Moodle,
Canvas). Đây là **ABSTRACTION ONLY** — lớp trừu tượng sẵn sàng, nhưng chưa có triển khai
thật đứng sau.

### CMS (Content Management System — Hệ thống quản lý nội dung)
`dss/services/cms_lecture_repository.py` là một kho lưu trữ NỘI BỘ cho tài liệu bài giảng
— Giảng viên tải lên, hệ thống lưu và cho phép truy xuất qua RAG (Bài 16). Đây là **THẬT
và HOẠT ĐỘNG ĐẦY ĐỦ** — nhưng nó là một kho nội bộ của chính EduDSS, KHÔNG phải kết nối
đến một nền tảng CMS bên ngoài nào (như WordPress, Moodle Content).

### PgVectorStore (PostgreSQL + pgvector)
`dss/services/vector_store.py` có class `PgVectorStore` với:
- Kết nối thật (real psycopg2 connection test) — CÓ.
- Schema/DDL thật (tạo extension pgvector, tạo HNSW index) — CÓ.
- 4 phương thức CRUD (`add_chunks`, `search`, `list_documents`, `delete_document`) — LÀ
  CÁC HÀM STUB (giả), KHÔNG thực thi câu lệnh SQL thật nào.
- Hàm `get_vector_store()` chỉ trả về `PgVectorStore` nếu biến môi trường
  `PGVECTOR_URL`/`DATABASE_URL` được thiết lập — trong triển khai hiện tại, các biến này
  KHÔNG được thiết lập, nên class này **KHÔNG BAO GIỜ được kích hoạt lúc chạy thật**.
  Vector store thực sự đang hoạt động là `LocalVectorStore` (file-based, NumPy + JSON).

## 5. Ví dụ cực dễ hiểu

Giống như một ngôi nhà mẫu (model house) của công ty bất động sản: có cửa thật, có khung
cửa sổ thật, có sơ đồ điện đầy đủ trên giấy (schema/DDL) — nhưng đường ống nước chưa được
đấu nối vào hệ thống cấp nước thành phố (CRUD là stub). Nhìn vào ngôi nhà, bạn thấy nó
"trông như" một ngôi nhà hoàn chỉnh, nhưng thử vặn vòi nước sẽ không có nước chảy ra.

## 6. Ví dụ trực tiếp trong EduDSS

Nếu một người đọc code thấy `class RealConnectorLMSRepository` hoặc `class PgVectorStore`
tồn tại, họ có thể VỘI VÀNG kết luận "vậy là có tích hợp LMS thật" hoặc "vậy là dùng
PostgreSQL" — đây CHÍNH XÁC là bẫy tư duy mà quá trình audit trước đó đã phát hiện và
sửa (qua việc đọc kỹ nội dung bên trong từng hàm, không chỉ nhìn tên class).

## 7. Luồng xử lý thực tế trong project

```
get_vector_store() được gọi
  → kiểm tra biến môi trường PGVECTOR_URL/DATABASE_URL
  → NẾU đã thiết lập: trả về PgVectorStore (hiện tại KHÔNG xảy ra trong triển khai này)
  → NẾU CHƯA thiết lập (trường hợp thực tế hiện nay): trả về LocalVectorStore
  → RAG pipeline (Bài 16) luôn thao tác qua LocalVectorStore trong thực tế

LMSRepository tương tự:
  → cấu hình chọn DemoLMSRepository hoặc RealConnectorLMSRepository
  → RealConnectorLMSRepository (nếu được chọn) vẫn nội bộ gọi lại DemoLMSRepository
```

## 8. Công thức nếu có

Không có công thức toán — đây là bài về xác minh kiến trúc thực tế bằng cách đọc code,
không phải công thức số học.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng.

## 10. Cách đọc kết quả

Khi đánh giá một thành phần kiến trúc, PHẢI đọc theo 3 câu hỏi: (1) Class/interface có
tồn tại không? (2) Bên trong hàm có thực sự thực thi hành động thật (gọi API, chạy SQL)
không? (3) Đường dẫn kích hoạt (activation path, ví dụ biến môi trường) có thực sự được
bật trong triển khai hiện tại không? Chỉ khi cả 3 câu đều "có", mới được gọi là
**IMPLEMENTED**.

## 11. Vì sao project dùng phương pháp này

Xây dựng lớp trừu tượng (abstraction) trước, để lại "chỗ trống" sẵn sàng cắm một triển
khai thật vào sau — đây là thực hành thiết kế tốt (repository pattern), giúp việc tích
hợp LMS/CMS/PostgreSQL thật trong tương lai không cần sửa đổi code ở các lớp trên (UI,
Service khác), chỉ cần thay thế đúng lớp triển khai bên trong.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm ở lớp Repository/Storage và External Integration trong kiến trúc phân lớp (Bài 2) —
là 2 trong số các lớp "yếu nhất" của toàn hệ thống, cần công khai rõ ràng.

## 13. Input là gì

Yêu cầu đọc/ghi dữ liệu LMS, tài liệu CMS, hoặc vector embedding từ các lớp trên.

## 14. Output là gì

Dữ liệu demo/nội bộ (cho LMS/CMS) hoặc dữ liệu từ file (cho vector), KHÔNG phải dữ liệu
từ một hệ thống bên ngoài thật hay từ PostgreSQL.

## 15. Output được chuyển cho module nào tiếp theo

Cho Career Advisor (Bài 20, cần dữ liệu LMS enrichment), Learning Explainer (Bài 19, cần
CMS + vector store), và RAG pipeline nói chung (Bài 16).

## 16. Ưu điểm

Kiến trúc sẵn sàng mở rộng — thêm một triển khai thật trong tương lai không phá vỡ code
hiện có ở các lớp trên.

## 17. Nhược điểm

Dễ gây hiểu lầm nếu chỉ đọc tên class mà không đọc kỹ nội dung; hiện tại chưa có giá trị
thực tế về kết nối dữ liệu bên ngoài.

## 18. Limitation thực tế của project

Đây LÀ những giới hạn quan trọng nhất của toàn bộ hệ thống cần công khai: không có kết
nối LMS thật, không có kết nối CMS ngoài thật, không có PostgreSQL vector store thật đang
hoạt động.

## 19. Hội đồng có thể hỏi gì

"Tôi thấy trong code có class tên `RealConnectorLMSRepository` và `PgVectorStore` — vậy hệ
thống đã tích hợp LMS thật và dùng PostgreSQL đúng không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không ạ, và đây là điểm quan trọng em muốn làm rõ. `RealConnectorLMSRepository` có tên
gợi ý như vậy nhưng khi đọc kỹ, nó nội bộ gọi lại `DemoLMSRepository` — không có request
mạng nào đến một LMS thật. Tương tự, `PgVectorStore` có kết nối và schema PostgreSQL thật,
nhưng 4 phương thức CRUD của nó là các hàm giả (stub), và điều kiện kích hoạt nó (biến
môi trường `PGVECTOR_URL`) chưa được thiết lập trong triển khai này — nên vector store
đang hoạt động thật sự là `LocalVectorStore`, file-based. Đây là kiến trúc trừu tượng sẵn
sàng cho tương lai, không phải kết nối thật hiện tại."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ 3 mục con ở mục 4 (LMS, CMS, PgVectorStore), và nhấn mạnh phương pháp
xác minh 3 câu hỏi ở mục 10 — đây chính là phương pháp đã dùng trong quá trình audit thực
tế để phát hiện ra những điểm này.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy công sức xây dựng PgVectorStore và RealConnectorLMSRepository có lãng phí không nếu
chúng chưa hoạt động?"

## 23. Cách trả lời câu vặn

"Không lãng phí — đây là công việc kiến trúc nền tảng cần thiết cho việc mở rộng trong
tương lai. Việc có sẵn schema PostgreSQL với pgvector và HNSW index, hay có sẵn giao diện
Repository cho LMS, có nghĩa là khi dự án có điều kiện kết nối hệ thống thật, phần lớn
công việc thiết kế đã hoàn thành — chỉ cần triển khai đúng 4 phương thức CRUD hoặc logic
gọi API thật, mà không cần sửa đổi các lớp phía trên. Đây là đầu tư kiến trúc có chủ đích,
không phải phần thừa."

## 24. Những câu không được nói

- "Hệ thống đã tích hợp LMS thật." (Sai.)
- "Hệ thống đã tích hợp CMS ngoài thật." (Sai — CMS nội bộ có thật, CMS ngoài thì không.)
- "RAG dùng PostgreSQL để lưu vector." (Sai — dùng LocalVectorStore.)

## 25. 10 câu tự kiểm tra

1. `RealConnectorLMSRepository` có thực sự kết nối đến một LMS bên ngoài không?
2. CMS trong EduDSS là nội bộ hay kết nối đến một nền tảng CMS ngoài?
3. `PgVectorStore` có kết nối PostgreSQL thật không?
4. 4 phương thức CRUD của `PgVectorStore` có thực thi SQL thật không?
5. Điều kiện gì kích hoạt `PgVectorStore` thay vì `LocalVectorStore`?
6. Vector store thực sự đang hoạt động trong triển khai hiện tại là gì?
7. 3 câu hỏi cần đặt ra để xác minh một thành phần kiến trúc có thật sự "IMPLEMENTED"
   không?
8. Repository pattern là gì, và vì sao dùng nó ở đây?
9. Vì sao tên class "RealConnector" có thể gây hiểu lầm?
10. Công sức xây PgVectorStore/RealConnector có lãng phí không? Vì sao?

## 26. Đáp án riêng

1. Không — nó nội bộ gọi lại DemoLMSRepository.
2. Nội bộ (internal) — CMS ngoài chưa được kết nối.
3. Có — kết nối và schema/DDL là thật.
4. Không — là các hàm stub, không thực thi SQL thật.
5. Biến môi trường `PGVECTOR_URL`/`DATABASE_URL` được thiết lập — hiện tại chưa được
   thiết lập.
6. `LocalVectorStore` (file-based, NumPy + JSON).
7. (1) Class có tồn tại không? (2) Hàm bên trong có thực thi hành động thật không? (3)
   Đường dẫn kích hoạt có được bật trong triển khai hiện tại không?
8. Một mẫu thiết kế cho phép nhiều triển khai khác nhau cắm vào cùng một giao diện chung;
   dùng để chuẩn bị sẵn cho việc tích hợp thật trong tương lai.
9. Vì tên gợi ý có kết nối thật, nhưng nội dung bên trong hàm lại không thực hiện việc đó.
10. Không lãng phí — là đầu tư kiến trúc nền tảng cho khả năng mở rộng trong tương lai.

## 27. 5 CÂU PHẢI THUỘC

1. "RealConnectorLMSRepository nội bộ gọi lại DemoLMSRepository — KHÔNG có kết nối LMS
   thật."
2. "CMS nội bộ (upload-ingest-retrieve-cite) là thật; CMS ngoài chưa được kết nối."
3. "PgVectorStore: kết nối và schema THẬT, nhưng 4 CRUD là stub — KHÔNG được kích hoạt vì
   biến môi trường chưa thiết lập."
4. "Vector store thực sự đang hoạt động là LocalVectorStore (file-based)."
5. "Câu trả lời chuẩn: có Class không đồng nghĩa với có kết nối/triển khai thật — phải
   đọc nội dung hàm."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Repository pattern — Mẫu thiết kế kho lưu trữ
- Abstraction only — Chỉ có lớp trừu tượng
- Stub — Hàm giả (chưa triển khai thật)
- Activation path — Đường dẫn kích hoạt (ví dụ biến môi trường)
- Internal vs. External — Nội bộ vs. Bên ngoài
