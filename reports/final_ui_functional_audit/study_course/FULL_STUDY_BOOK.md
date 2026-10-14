# FULL STUDY BOOK — EduDSS: Toàn bộ kiến thức trong một cuốn sách

Đây là bản tổng hợp liền mạch của 25 bài học (`01_...md` đến `25_...md`), viết lại theo
dạng một chương sách kể chuyện liên tục, để bạn đọc lướt lại toàn bộ kiến thức mà không
cần mở từng file riêng. Nếu cần chi tiết đầy đủ (28 mục, câu hỏi tự kiểm tra, đáp án) của
một chủ đề cụ thể, quay lại đúng file bài học tương ứng.

---

## Chương 1 — Bức tranh tổng thể

EduDSS là một hệ thống hỗ trợ ra quyết định học tập (Decision Support System) chạy trên
Streamlit, phục vụ 3 vai trò: Sinh viên, Giảng viên, Admin, mỗi vai trò nhìn thấy dữ liệu
và chức năng khác nhau nhờ kiểm soát truy cập 2 lớp (điều hướng + hàm). Kiến trúc hệ
thống có 8 lớp: UI → Services → DSS Orchestration → ML → AI/RAG → Repository/Storage →
External Integration → Cross-cutting concerns. Bạn cần nhớ 4 nhãn phân loại mức độ hoàn
thiện của mỗi thành phần: IMPLEMENTED (đã làm thật), PARTIAL (làm một phần), ABSTRACTION
ONLY (chỉ có khung trừu tượng chờ cắm triển khai thật), NOT IMPLEMENTED (chưa làm).

## Chương 2 — Dữ liệu: Điểm khởi đầu của mọi thứ

Toàn bộ dữ liệu huấn luyện trong EduDSS là **tổng hợp (synthetic)**, sinh bởi
`generate_data()`. Feature là đầu vào (điểm giữa kỳ, tỷ lệ điểm danh...), target là cái
cần đoán (`diem_ky_sau`). Công thức sinh target: `0.60*diem_ky_nay + 0.15*diem_giua_ky +
0.10*diem_du_an + 0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5) + noise(σ=0.08)`,
sau đó clip [0,10] và clamp ±1.5 quanh `diem_ky_nay`. Đây chính là nguồn gốc của R² cao
bất thường sau này — nhớ kỹ công thức này, nó là "chìa khóa vạn năng" cho rất nhiều câu
hỏi khó.

## Chương 3 — Tiền xử lý và chống rò rỉ dữ liệu

Trước khi huấn luyện, dữ liệu qua 4 bước: KNNImputer (điền thiếu), StandardScaler
(chuẩn hóa Z-score), OneHotEncoder (mã hóa phân loại), SMOTE (cân bằng lớp bằng sinh mẫu
tổng hợp). Thứ tự BẮT BUỘC: `filter_leakage_features()` → `train_test_split` → Pipeline
(gồm cả 4 bước trên) chỉ fit BÊN TRONG từng fold train của GridSearchCV. Nếu đảo ngược
thứ tự này (tiền xử lý trước khi chia), sẽ xảy ra data leakage — kết quả đánh giá bị thổi
phồng giả tạo. Đây là câu hỏi hội đồng hỏi nhiều nhất — phải trả lời bằng đúng quy trình
code, không phải lý thuyết chung.

## Chương 4 — Classification và Regression: Hai bài toán học có giám sát

Classification dự đoán nhãn rời rạc (Cao/Trung bình/Thấp), Regression dự đoán số liên tục
(điểm số). Mỗi bài toán có 4 thuật toán và MỘT LƯỚI THAM SỐ RIÊNG — đừng nhầm lẫn:

| Bài toán | RF | XGBoost | LightGBM | Linear/Logistic |
|---|---|---|---|---|
| Classification | 24 cấu hình/120 fit | 1 cấu hình/1 fit (KHÔNG GridSearchCV) | 8/40 | 3/15 |
| Regression | 12/60 | 18/90 | 18/90 | 0/1 |

XGBoost Classifier là ngoại lệ duy nhất không dùng GridSearchCV, do lỗi "Invalid classes
inferred" khi một fold CV thiếu mẫu của một lớp hiếm trong bài toán đa lớp. Đánh giá
Classification dùng Accuracy/Precision/Recall/F1 — trong đó False Negative (bỏ sót sinh
viên rủi ro) nguy hiểm hơn False Positive (báo động giả). Đánh giá Regression dùng
MAE/MSE/RMSE/R² — và R² cao trên tập mẫu KHÔNG phải bằng chứng hiệu năng thực (xem
Chương 2).

## Chương 5 — K-Means: Đừng nhầm phân cụm với dự đoán

K-Means là học KHÔNG giám sát — không có target, chỉ nhóm sinh viên có đặc điểm giống
nhau. Thuật toán lặp 3 bước: khởi tạo tâm cụm → gán điểm vào cụm gần nhất → cập nhật lại
tâm cụm → lặp đến khi hội tụ. Đánh giá chất lượng phân cụm dùng Elbow (tìm điểm gãy trên
đồ thị inertia) và Silhouette score (càng gần 1 càng tốt). K-Means KHÔNG dự đoán tương
lai của ai cả — nó chỉ trả lời "ai giống ai ở hiện tại", phục vụ việc can thiệp theo
nhóm.

## Chương 6 — SHAP: Giải thích chứ không chứng minh nhân quả

SHAP dùng giá trị Shapley (từ lý thuyết trò chơi hợp tác) để phân rã đóng góp của từng
feature vào MỘT dự đoán cụ thể (local) hoặc trung bình trên toàn dữ liệu (global). Công
thức: `φ_j = Σ_{S⊆F\{j}} [trọng số] * [f(S∪{j})-f(S)]`. **SHAP không chứng minh nhân
quả** — nó chỉ nói mô hình đã "dựa vào" gì để ra quyết định, không nói điều đó có thực
sự GÂY RA kết quả trong đời thực hay không.

## Chương 7 — DSS thật sự là gì (chương quan trọng nhất)

Đây là luận điểm trung tâm của toàn bộ đồ án: **Prediction ≠ DSS**. Một hệ thống hỗ trợ ra
quyết định thực thụ phải có đủ: Prediction (dự đoán) + Evidence (bằng chứng, từ SHAP) +
Explanation (giải thích) + Diagnosis (chẩn đoán nguyên nhân) + Recommendation (khuyến
nghị) + Action support (hỗ trợ hành động). Diagnosis Engine trong EduDSS là RULE-BASED
(luật if/elif theo ngưỡng) — không phải ML, không phải LLM — với 12 category chẩn đoán,
và trung thực trả về `INSUFFICIENT_DATA` khi thiếu bằng chứng thay vì đoán bừa.

## Chương 8 — Từ chẩn đoán đến hành động

Recommendation Engine dùng cosine similarity để tìm bạn học tương đồng trong CÙNG một
cụm K-Means. Learning Plan Generator (`dss/services/learning_plan.py`) là RULE-BASED —
xây cấu trúc kế hoạch (chủ đề, tần suất, mục tiêu) bằng luật. LLM chỉ được gọi SAU CÙNG
để "diễn đạt" (narrate) kế hoạch đã có cấu trúc, KHÔNG quyết định nội dung. Đây là chuỗi
đầy đủ cần thuộc lòng: **Dữ liệu sinh viên → Tiền xử lý → Classification/Regression →
SHAP → Diagnosis Engine → Recommendation → Learning Plan → Sinh viên hành động**.

## Chương 9 — RAG: Chuỗi thứ hai của hệ thống

Song song với chuỗi ML/DSS ở trên là Chuỗi 2: **Tài liệu giảng viên → Ingestion →
Chunking → Embedding → Vector Store → Retrieval → Context Budget → LLM → Citation →
Learning Explainer**. RAG giải quyết vấn đề hallucination của LLM bằng cách ép câu trả
lời dựa trên tài liệu thật đã truy xuất. Hai ngưỡng lọc quan trọng:
`RAG_LOW_CONFIDENCE_FLOOR=0.55` (tuyệt đối) và `RAG_RELATIVE_THRESHOLD=0.85` (tương đối
so với chunk tốt nhất). Nếu không đạt ngưỡng, hệ thống trung thực trả lời "không tìm thấy
bằng chứng liên quan" — đây là hành vi ĐÚNG, không phải lỗi.

Embedding dùng `sentence-transformers` (`all-MiniLM-L6-v2`), chạy cục bộ. Citation được
gắn vào câu trả lời và qua kiểm tra heuristic chống hallucination (không phải bảo đảm
tuyệt đối). Learning Explainer là ứng dụng thực tế hoàn chỉnh của toàn bộ chuỗi này —
đã được kiểm chứng live với một trích dẫn nguyên văn từ file thật, chứng minh pipeline
hoạt động thật chứ không phải câu trả lời giả lập.

## Chương 10 — LLM Gateway: Cổng gọi AI tập trung

Mọi lời gọi AI đều đi qua `dss/services/llm_gateway.py` — một điểm tập trung duy nhất
quản lý: định tuyến đa nhà cung cấp (Gemini/Groq/OpenAI/Ollama) với chuỗi dự phòng
(fallback cascade), retry một lớp (Tenacity), và giới hạn đồng thời bằng
`threading.Semaphore(MAX_CONCURRENT_REQUESTS=3)` — con số này CHƯA được load-test. Trong
chế độ `REAL_LMS`, nếu tất cả nhà cung cấp thất bại, hệ thống trả về thông báo trung thực
"không khả dụng" thay vì bịa câu trả lời.

## Chương 11 — Career Advisor: Heuristic, không phải xác suất

Career Fit (độ phù hợp) và Career Readiness (độ sẵn sàng) là hai điểm số HEURISTIC độc
lập, mỗi cái tổng hợp từ 6 chiều khác nhau bằng công thức cộng có trọng số:
`Σ(trọng số_i × điểm_i)`. Đây KHÔNG phải xác suất thống kê được huấn luyện từ dữ liệu —
trọng số do con người thiết kế dựa trên tài liệu tư vấn hướng nghiệp. Tất cả 12 chiều
input (6 Fit + 6 Readiness) đã được xác minh thực sự ảnh hưởng đến kết quả tính toán.

## Chương 12 — Những thứ "trông có thật nhưng chưa hoạt động"

Ba cái bẫy tư duy quan trọng nhất cần nhớ:
1. `RealConnectorLMSRepository` — tên gợi ý kết nối LMS thật, nhưng NỘI BỘ gọi lại
   `DemoLMSRepository`. Chưa có kết nối mạng thật đến LMS nào.
2. CMS trong EduDSS là kho nội bộ THẬT (upload-ingest-retrieve-cite hoạt động đầy đủ),
   nhưng KHÔNG kết nối đến một nền tảng CMS ngoài nào.
3. `PgVectorStore` — có kết nối PostgreSQL thật và schema/DDL thật (pgvector extension,
   HNSW index), nhưng 4 phương thức CRUD là STUB (giả). Điều kiện kích hoạt
   (`PGVECTOR_URL`/`DATABASE_URL`) chưa được thiết lập, nên vector store thực sự đang
   hoạt động là `LocalVectorStore` (file-based).

Nguyên tắc kiểm chứng: (1) Class có tồn tại không? (2) Hàm bên trong có thực thi hành
động thật không? (3) Điều kiện kích hoạt có được bật trong triển khai hiện tại không? Cả
3 câu phải "có" mới được gọi là IMPLEMENTED thật sự.

## Chương 13 — Model Registry: Train ≠ Deploy

Vòng đời mô hình: Candidate (vừa huấn luyện) → Production (đã được Admin phê duyệt qua
`promote()`, được bảo vệ bởi `@require_role("Admin")`) → Archived (bị thay thế). Điểm gọi
huấn luyện thật truyền `auto_promote=False` một cách tường minh — dù hệ thống có tính cờ
`is_best`, cờ đó KHÔNG được dùng để tự động promote. Huấn luyện xong một mô hình tốt
KHÔNG có nghĩa là nó tự động được đưa vào phục vụ người dùng thật.

## Chương 14 — Bảo mật, RBAC, Riêng tư

4 lớp bảo vệ: Authentication (PBKDF2-HMAC-SHA256, đơn giản nhưng thật), RBAC (2 lớp:
điều hướng + hàm), Privacy (chỉ `student_id`/`risk_level`/`progress_note` vào prompt AI —
KHÔNG BAO GIỜ có tên/email/số điện thoại), Prompt injection defense (heuristic, chống
lệnh độc hại ẩn trong tài liệu được truy xuất).

## Chương 15 — Testing: 445 test chứng minh gì, không chứng minh gì

Baseline: 417 non-E2E + 28 E2E = 445 (trước đó: 403+23=426) test PASS. Test chứng minh: các trường hợp ĐÃ ĐƯỢC
THIẾT KẾ hoạt động đúng, không có lỗi hồi quy. Test KHÔNG chứng minh: không có bug tuyệt
đối, không tương đương 100% coverage, không chứng minh hiệu năng dưới tải thực hoặc trên
dữ liệu thật.

## Chương 16 — Tổng kết: 10 giới hạn cần nhớ

1. Dữ liệu hoàn toàn tổng hợp, chưa có dữ liệu sinh viên thật.
2. Chưa có kết nối LMS/CMS ngoài thật.
3. PgVectorStore là stub.
4. Knowledge Base và Admin User Management thiếu Update/Delete UI.
5. Concurrency (3 request đồng thời) chưa load-test.
6. Accessibility mới spot-check, chưa audit WCAG chính thức.
7. XGBoost Classifier không GridSearchCV như 3 thuật toán còn lại.
8. R² cao trên dữ liệu mẫu là hiện tượng dữ liệu tổng hợp, không phải bằng chứng thực tế.
9. Career Fit/Readiness là heuristic, không phải xác suất.
10. Chống hallucination/prompt injection là heuristic, không phải bảo đảm tuyệt đối.

---

## Kết luận

Giá trị khoa học của EduDSS không nằm ở việc tuyên bố một hệ thống hoàn hảo, mà nằm ở:
(1) xây dựng đầy đủ chuỗi DSS thực thụ (không dừng ở dự đoán), (2) áp dụng phương pháp
luận ML nghiêm túc (chống leakage có hệ thống, GridSearchCV, so sánh đa thuật toán), (3)
xây dựng một pipeline RAG có căn cứ, trung thực khi không tìm thấy bằng chứng, và (4) một
quy trình tự-audit minh bạch, công khai rõ ràng chính xác những gì còn hạn chế.

Để ôn nhanh hơn nữa, dùng `QUICK_REVIEW_1_DAY.md` (ôn 1 ngày trước) hoặc
`QUICK_REVIEW_30_MINUTES.md` (ôn ngay trước giờ bảo vệ).
