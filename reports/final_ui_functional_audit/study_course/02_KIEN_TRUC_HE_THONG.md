# Bài 2 — Kiến trúc hệ thống theo lớp (Layered Architecture)

## 1. Mục tiêu buổi học

Hiểu 8 lớp kiến trúc của EduDSS (UI → Services → DSS → ML → AI/RAG → Repository/Storage
→ External Integration → Cross-cutting), và với mỗi lớp phải phân biệt được nó
**IMPLEMENTED** (đã làm thật), **PARTIAL** (làm một phần), **ABSTRACTION ONLY** (chỉ có
khung trừu tượng), hay **NOT IMPLEMENTED** (chưa làm).

## 2. Kiến thức cần nhớ trước

Bài 1 (tổng quan 3 vai trò, Streamlit, service layer).

## 3. Giải thích từ con số 0

Hãy tưởng tượng kiến trúc như một tòa nhà nhiều tầng, dữ liệu "đi thang máy" từ tầng
trên cùng (nơi người dùng bấm nút) xuống tầng dưới cùng (nơi dữ liệu được lưu trên đĩa),
rồi lại đi ngược lên để hiển thị kết quả. Mỗi tầng chỉ biết nói chuyện với tầng ngay
cạnh nó — Tab giao diện không tự đọc file JSON, nó luôn nhờ một "service" làm việc đó.
Cách tổ chức này gọi là **kiến trúc phân lớp (layered architecture)** — mỗi lớp có một
trách nhiệm rõ ràng, giúp sửa một lớp không làm hỏng lớp khác.

## 4. Giải thích kỹ thuật

8 lớp cụ thể của EduDSS (xem `FINAL_ARCHITECTURE_TRUTH.md` để đối chiếu):

1. **UI** (`dss/tabs/*.py`, `dss/main.py`) — IMPLEMENTED.
2. **Services** (`dss/services/*.py`) — IMPLEMENTED phần lớn, có ngoại lệ (lms_connector
   là ABSTRACTION ONLY).
3. **DSS Orchestration** — luồng gọi hàm tuần tự trong một lần chạy Streamlit, KHÔNG phải
   một framework điều phối pipeline riêng (không có Airflow/Prefect).
4. **ML** (`dss/core/trainers.py`, `dss/core/models.py`) — IMPLEMENTED, có một ngoại lệ
   nhỏ ở XGBoost Classifier (xem Bài 6).
5. **AI/RAG** (`llm_gateway.py`, `rag_service.py`) — IMPLEMENTED cho pipeline, nhưng phụ
   thuộc bên ngoài (EXTERNAL DEPENDENCY) cho chất lượng sinh văn bản thực tế của LLM.
6. **Repository/Storage** (`warehouse.py`, `vector_store.py`) — PARTIAL: file-based là
   thật và đang hoạt động; PostgreSQL (`PgVectorStore`) chỉ có kết nối + schema, CRUD là
   stub (giả, chưa chạy SQL thật).
7. **External Integration (LMS/CMS)** — ABSTRACTION ONLY cho LMS; PARTIAL cho CMS (CMS
   nội bộ có thật, CMS ngoài thì không).
8. **Cross-cutting** (bảo mật, riêng tư, logging, responsive UI) — IMPLEMENTED phần lớn,
   accessibility là PARTIAL.

## 5. Ví dụ cực dễ hiểu

Giống như một nhà hàng: khách gọi món (UI) → phục vụ ghi order (Service) → đầu bếp nấu
theo công thức (ML/DSS logic) → kho nguyên liệu (Storage) cung cấp thực phẩm → nếu thiếu
nguyên liệu đặc biệt phải đặt từ nhà cung cấp bên ngoài (External Integration, ví dụ nhà
cung cấp AI). Nếu kho chỉ có "kệ trống được dán nhãn sẵn" (PgVectorStore) nhưng chưa
từng nhập hàng thật, thì đầu bếp vẫn phải lấy đồ ở kho khác đang hoạt động thật (
LocalVectorStore).

## 6. Ví dụ trực tiếp trong EduDSS

Khi Sinh viên hỏi AI Advisor một câu hỏi về bài giảng: UI (tab AI Advisor) → Service
(`rag_service.py`) → tầng AI/RAG (embedding + tìm kiếm) → tầng Storage
(`LocalVectorStore` đọc file `.npy`/JSON, KHÔNG phải PostgreSQL) → LLM Gateway gọi ra
ngoài (External Dependency: Gemini/Groq/OpenAI/Ollama) → kết quả trả ngược lên UI kèm
trích dẫn.

## 7. Luồng xử lý thực tế trong project

```
UI Tab → Service function → (nếu cần ML) core/trainers.py hoặc core/models.py
       → (nếu cần lưu/đọc) warehouse.py / vector_store.py (file-based, KHÔNG phải DB thật)
       → (nếu cần AI) llm_gateway.py → nhà cung cấp AI bên ngoài
       → trả kết quả ngược lên UI
```

## 8. Công thức nếu có

Không có công thức toán ở bài kiến trúc — đây là bài về tổ chức hệ thống.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng.

## 10. Cách đọc kết quả

Khi hội đồng hỏi "lớp X có thật không", bạn trả lời theo đúng 4 nhãn: IMPLEMENTED /
PARTIAL / ABSTRACTION ONLY / NOT IMPLEMENTED — không dùng từ mơ hồ như "cơ bản là có".

## 11. Vì sao project dùng phương pháp này

Phân lớp rõ ràng giúp: (a) dễ kiểm thử từng lớp độc lập, (b) dễ thay thế một lớp (ví dụ
đổi LocalVectorStore sang PgVectorStore thật trong tương lai) mà không đụng vào lớp UI,
(c) dễ audit — chính nhờ kiến trúc phân lớp mà quá trình audit trước đó có thể xác minh
từng lớp riêng biệt.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây CHÍNH LÀ khung xương của toàn hệ thống — mọi bài học từ 03 đến 25 đều là một "lớp"
hoặc một "luồng đi qua các lớp" trong bức tranh 8 lớp này.

## 13. Input là gì

Yêu cầu (request) từ một hành động của người dùng trên UI.

## 14. Output là gì

Kết quả cuối cùng hiển thị lại trên UI, đã đi qua toàn bộ hoặc một phần của 8 lớp.

## 15. Output được chuyển cho module nào tiếp theo

Tùy tính năng — xem chuỗi cụ thể ở Bài 14 (chuỗi ML→DSS) và Bài 16 (chuỗi RAG).

## 16. Ưu điểm

Rõ ràng, dễ audit, dễ thay thế từng phần, lỗi ở một lớp không lan sang lớp khác một cách
khó kiểm soát.

## 17. Nhược điểm

Không có một framework điều phối pipeline chính thức (không DAG, không async task queue)
— với hệ thống lớn hơn sẽ cần nâng cấp.

## 18. Limitation thực tế của project

Lớp Storage là PARTIAL (PgVectorStore chưa chạy thật); lớp External Integration là
ABSTRACTION ONLY cho LMS. Đây là 2 lớp "yếu nhất" và hội đồng rất hay hỏi về chúng — xem
Bài 21.

## 19. Hội đồng có thể hỏi gì

"Hãy mô tả kiến trúc phân lớp của hệ thống và chỉ ra lớp nào chưa hoàn thiện."

## 20. Câu trả lời ngắn 20–40 giây

"Hệ thống có 8 lớp: UI, Service, DSS orchestration, ML, AI/RAG, Storage, External
Integration, và Cross-cutting concerns. Hầu hết đã implement thật và được test. Hai lớp
chưa hoàn thiện: Storage — vì PgVectorStore mới có kết nối và schema, CRUD là stub; và
External Integration — vì LMS/CMS ngoài chưa được kết nối thật, chỉ có lớp trừu tượng
sẵn sàng để cắm vào sau."

## 21. Câu trả lời chi tiết

Đi từng lớp theo đúng thứ tự trong mục 4, nhấn mạnh: KHÔNG có framework điều phối pipeline
chính thức (là lựa chọn thiết kế phù hợp quy mô, không phải thiếu sót); Storage thật đang
dùng là file-based, không phải PostgreSQL.

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu không có DB thật, làm sao hệ thống đảm bảo tính toàn vẹn dữ liệu (data integrity)?"

## 23. Cách trả lời câu vặn

"Warehouse layer có cơ chế kiểm tra toàn vẹn bằng SHA-256 checksum cho các artifact (mô
hình đã huấn luyện), và log hoạt động ghi vào file JSON riêng biệt cho từng loại dữ liệu.
Đây không tương đương với ràng buộc toàn vẹn (constraint) của một RDBMS thật, và em xin
ghi nhận đó là một giới hạn thực tế của kiến trúc file-based ở quy mô đồ án này."

## 24. Những câu không được nói

- "Tất cả các lớp đều hoàn thiện 100%."
- "Có một pipeline orchestration framework thật (Airflow/Prefect) đứng sau." (Không có.)

## 25. 10 câu tự kiểm tra

1. Kể tên 8 lớp kiến trúc theo đúng thứ tự.
2. Lớp nào là PARTIAL vì có class tồn tại nhưng CRUD là stub?
3. Lớp nào là ABSTRACTION ONLY?
4. DSS Orchestration có dùng framework điều phối riêng không?
5. Cross-cutting concerns gồm những gì?
6. Vì sao kiến trúc phân lớp giúp việc audit dễ hơn?
7. Storage thật sự đang hoạt động là gì?
8. Lớp AI/RAG vì sao được gọi là EXTERNAL DEPENDENCY một phần?
9. Ưu điểm lớn nhất của kiến trúc phân lớp là gì?
10. Nhược điểm lớn nhất là gì?

## 26. Đáp án riêng

1. UI → Services → DSS Orchestration → ML → AI/RAG → Repository/Storage → External
   Integration → Cross-cutting.
2. Repository/Storage (vì PgVectorStore).
3. External Integration (LMS).
4. Không — là luồng gọi hàm tuần tự trong một lần chạy Streamlit.
5. Bảo mật, riêng tư, logging, responsive UI, accessibility.
6. Vì mỗi lớp có ranh giới rõ, kiểm tra được độc lập bằng test/code read riêng từng lớp.
7. `LocalVectorStore` (file-based: NumPy + JSON) và file JSON/CSV/joblib cho phần còn lại.
8. Vì chất lượng câu trả lời phụ thuộc vào nhà cung cấp LLM bên ngoài (Gemini/Groq/...).
9. Dễ audit, dễ thay thế từng phần.
10. Không có framework điều phối pipeline chính thức cho quy mô lớn hơn.

## 27. 5 CÂU PHẢI THUỘC

1. "Hệ thống có 8 lớp kiến trúc, phân tách rõ trách nhiệm."
2. "Storage thật đang hoạt động là file-based; PostgreSQL chỉ là schema sẵn sàng, CRUD là stub."
3. "DSS Orchestration là luồng gọi hàm tuần tự, không phải framework điều phối riêng."
4. "External Integration với LMS là abstraction only — chưa có kết nối mạng thật."
5. "Kiến trúc phân lớp giúp từng lớp được kiểm thử và audit độc lập."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Layered architecture — Kiến trúc phân lớp
- Repository pattern — Mẫu thiết kế kho lưu trữ
- Stub — Hàm giả (chưa triển khai thật)
- Cross-cutting concern — Mối quan tâm xuyên suốt (bảo mật, logging...)
- External dependency — Phụ thuộc bên ngoài
