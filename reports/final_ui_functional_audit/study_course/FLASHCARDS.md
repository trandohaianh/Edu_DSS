# FLASHCARDS — EduDSS

Cách dùng: che phần "ĐÁP ÁN", tự trả lời trước, rồi mở ra kiểm tra. Mỗi thẻ ghi số bài
học gốc trong ngoặc để tra cứu lại nếu cần. Có 80 thẻ, chia theo 25 chủ đề.

---

**#1 (Bài 1)** — EduDSS có bao nhiêu vai trò? Kể tên.
ĐÁP ÁN: 3 — Sinh viên, Giảng viên, Admin.

**#2 (Bài 1)** — Phân quyền theo vai trò kiểm soát ở mấy lớp?
ĐÁP ÁN: 2 lớp — điều hướng (TAB_ACCESS) và hàm (@require_role).

**#3 (Bài 2)** — Kể tên 8 lớp kiến trúc của EduDSS.
ĐÁP ÁN: UI, Services, DSS Orchestration, ML, AI/RAG, Repository/Storage, External
Integration, Cross-cutting.

**#4 (Bài 2)** — Lớp nào PARTIAL vì có class nhưng CRUD là stub?
ĐÁP ÁN: Repository/Storage (PgVectorStore).

**#5 (Bài 3)** — Dữ liệu mẫu EduDSS được sinh bởi hàm nào?
ĐÁP ÁN: `generate_data()`/`generate_lms_data()` trong `dss/core/data_helpers.py`.

**#6 (Bài 3)** — Trọng số lớn nhất trong công thức `diem_ky_sau` là bao nhiêu, thuộc
feature nào?
ĐÁP ÁN: 0.60, thuộc `diem_ky_nay`.

**#7 (Bài 3)** — Độ lệch chuẩn của nhiễu trong công thức sinh dữ liệu là bao nhiêu?
ĐÁP ÁN: σ = 0.08.

**#8 (Bài 3)** — `diem_ky_sau` bị clamp trong khoảng nào quanh `diem_ky_nay`?
ĐÁP ÁN: ±1.5.

**#9 (Bài 4)** — 4 kỹ thuật tiền xử lý chính là gì?
ĐÁP ÁN: KNNImputer, StandardScaler, OneHotEncoder, SMOTE.

**#10 (Bài 4)** — Công thức Z-score là gì?
ĐÁP ÁN: `z = (x-mean)/std`.

**#11 (Bài 4)** — Công thức sinh điểm mới của SMOTE?
ĐÁP ÁN: `x_new = x_i + λ*(x_zi - x_i)`, λ ngẫu nhiên trong [0,1].

**#12 (Bài 5)** — Thứ tự đúng giữa train_test_split và tiền xử lý là gì?
ĐÁP ÁN: Chia train/test TRƯỚC, tiền xử lý SAU.

**#13 (Bài 5)** — Pipeline tiền xử lý (Imputer/Scaler/Encoder/SMOTE) được fit ở đâu?
ĐÁP ÁN: Chỉ bên trong từng fold train của GridSearchCV, không bao giờ chạm tập test.

**#14 (Bài 5)** — `filter_leakage_features()` chạy ở bước nào?
ĐÁP ÁN: Đầu tiên, trước cả train_test_split.

**#15 (Bài 6)** — Random Forest Classifier: bao nhiêu cấu hình, bao nhiêu lượt fit?
ĐÁP ÁN: 24 cấu hình, 120 lượt fit (5-fold CV).

**#16 (Bài 6)** — XGBoost Classifier có dùng GridSearchCV không? Vì sao?
ĐÁP ÁN: Không — lỗi "Invalid classes inferred" khi fold thiếu mẫu lớp hiếm ở bài toán đa
lớp; dùng tham số cố định, 1 fit.

**#17 (Bài 6)** — LightGBM Classifier: bao nhiêu cấu hình/lượt fit?
ĐÁP ÁN: 8 cấu hình / 40 lượt fit.

**#18 (Bài 6)** — Logistic Regression: bao nhiêu cấu hình/lượt fit?
ĐÁP ÁN: 3 cấu hình / 15 lượt fit.

**#19 (Bài 7)** — Công thức Precision là gì?
ĐÁP ÁN: `TP / (TP+FP)`.

**#20 (Bài 7)** — Công thức Recall là gì?
ĐÁP ÁN: `TP / (TP+FN)`.

**#21 (Bài 7)** — Vì sao False Negative nguy hiểm hơn False Positive trong bài toán này?
ĐÁP ÁN: FN nghĩa là bỏ sót sinh viên rủi ro thật — không can thiệp kịp thời, hậu quả
nghiêm trọng hơn báo động giả.

**#22 (Bài 8)** — Random Forest Regressor: bao nhiêu cấu hình/lượt fit?
ĐÁP ÁN: 12 cấu hình / 60 lượt fit.

**#23 (Bài 8)** — XGBoost Regressor: bao nhiêu cấu hình/lượt fit? Có dùng GridSearchCV
không?
ĐÁP ÁN: 18 cấu hình / 90 lượt fit — CÓ dùng GridSearchCV (khác với XGBoost Classifier!).

**#24 (Bài 8)** — Con số 36 cấu hình Random Forest có còn đúng không?
ĐÁP ÁN: Không — đó là con số lịch sử đã bị loại bỏ; con số đúng hiện tại là 12/60.

**#25 (Bài 9)** — Công thức R² là gì?
ĐÁP ÁN: `1 - (Σ(y_i-ŷ_i)² / Σ(y_i-ȳ)²)`.

**#26 (Bài 9)** — Vì sao R² trên tập dữ liệu mẫu EduDSS cao bất thường?
ĐÁP ÁN: Vì target được tính trực tiếp từ công thức tuyến tính của các feature khác, cộng
nhiễu rất nhỏ, rồi bị clamp hẹp — không phải leakage.

**#27 (Bài 10)** — Công thức tính số lượt fit từ số cấu hình và fold?
ĐÁP ÁN: Số lượt fit = số cấu hình × số fold CV.

**#28 (Bài 10)** — Thuật toán nào không dùng GridSearchCV ở bài toán của nó?
ĐÁP ÁN: XGBoost Classifier (Classification) và Linear Regression (Regression).

**#29 (Bài 11)** — K-Means là học có giám sát hay không giám sát?
ĐÁP ÁN: Không giám sát (unsupervised).

**#30 (Bài 11)** — 4 bước của thuật toán K-Means?
ĐÁP ÁN: Khởi tạo tâm cụm → gán điểm vào cụm gần nhất → cập nhật tâm cụm → lặp đến khi hội
tụ.

**#31 (Bài 11)** — K-Means có dự đoán tương lai sinh viên không?
ĐÁP ÁN: Không — chỉ nhóm sinh viên giống nhau ở hiện tại.

**#32 (Bài 12)** — Silhouette score có khoảng giá trị nào, càng gần đâu càng tốt?
ĐÁP ÁN: Từ -1 đến 1, càng gần 1 càng tốt.

**#33 (Bài 12)** — Davies-Bouldin index càng cao hay càng thấp là tốt?
ĐÁP ÁN: Càng thấp càng tốt.

**#34 (Bài 13)** — SHAP là viết tắt của gì?
ĐÁP ÁN: SHapley Additive exPlanations.

**#35 (Bài 13)** — SHAP có chứng minh nhân quả không?
ĐÁP ÁN: Không — chỉ phân rã đóng góp thống kê vào dự đoán của mô hình.

**#36 (Bài 13)** — Local explanation khác global explanation ở điểm nào?
ĐÁP ÁN: Local giải thích 1 dự đoán cụ thể; global tổng hợp trên toàn bộ dữ liệu.

**#37 (Bài 14)** — Công thức 6 thành phần của DSS trong EduDSS?
ĐÁP ÁN: Prediction + Evidence + Explanation + Diagnosis + Recommendation + Action
support.

**#38 (Bài 14)** — Diagnosis Engine dựa trên cơ chế nào?
ĐÁP ÁN: Rule-based (luật if/elif theo ngưỡng), không phải ML/LLM.

**#39 (Bài 14)** — `INSUFFICIENT_DATA` được trả về khi nào?
ĐÁP ÁN: Khi dữ liệu hiện có không đủ để chẩn đoán một category cụ thể một cách trung
thực.

**#40 (Bài 15)** — Learning Plan Generator là rule-based hay ML-based?
ĐÁP ÁN: Rule-based/heuristic.

**#41 (Bài 15)** — LLM đóng vai trò gì trong Learning Plan?
ĐÁP ÁN: Chỉ diễn đạt (narrate) cấu trúc đã có sẵn, không quyết định nội dung.

**#42 (Bài 15)** — Recommendation Engine dùng công thức nào để tìm bạn học tương đồng?
ĐÁP ÁN: Cosine similarity, trong phạm vi cùng cụm K-Means.

**#43 (Bài 16)** — RAG là viết tắt của gì?
ĐÁP ÁN: Retrieval-Augmented Generation.

**#44 (Bài 16)** — Kể đủ 9 bước chuỗi RAG.
ĐÁP ÁN: Document → Chunk → Embedding → Vector → Similarity → Retrieval → Context → LLM →
Citation.

**#45 (Bài 16)** — Hai ngưỡng lọc RAG là gì, giá trị bao nhiêu?
ĐÁP ÁN: `RAG_LOW_CONFIDENCE_FLOOR=0.55` (tuyệt đối), `RAG_RELATIVE_THRESHOLD=0.85` (tương
đối).

**#46 (Bài 16)** — Nếu không chunk nào đạt ngưỡng, hệ thống làm gì?
ĐÁP ÁN: Trả về thông báo trung thực "không tìm thấy bằng chứng liên quan", không bịa.

**#47 (Bài 17)** — Mô hình embedding EduDSS dùng là gì?
ĐÁP ÁN: `sentence-transformers`, mô hình `all-MiniLM-L6-v2`.

**#48 (Bài 17)** — MRR đo cái gì?
ĐÁP ÁN: Vị trí trung bình của kết quả liên quan đầu tiên trong danh sách truy xuất.

**#49 (Bài 18)** — LLM Gateway nằm ở file nào?
ĐÁP ÁN: `dss/services/llm_gateway.py`.

**#50 (Bài 18)** — `MAX_CONCURRENT_REQUESTS` bằng bao nhiêu?
ĐÁP ÁN: 3.

**#51 (Bài 18)** — Cơ chế nào giới hạn số request AI đồng thời?
ĐÁP ÁN: `threading.Semaphore`.

**#52 (Bài 18)** — MAX_CONCURRENT_REQUESTS=3 đã được load-test chưa?
ĐÁP ÁN: Chưa.

**#53 (Bài 19)** — Learning Explainer có phải module kỹ thuật riêng không?
ĐÁP ÁN: Không — là UI gọi vào Chuỗi 2 (RAG + LLM Gateway + Citation).

**#54 (Bài 19)** — COLDSTART-001 là vấn đề gì, và trạng thái hiện tại là gì?
ĐÁP ÁN: Độ trễ khởi động ~27-60 giây lần đầu truy cập (import torch/transformers/
sentence-transformers + tải mô hình). Từ 2026-09-16: PARTIAL — UX ĐÃ SỬA (mọi spinner
trên đường cold-start giờ có thông báo rõ ràng "lần đầu có thể mất ~1 phút"), nhưng ĐỘ
TRỄ THẬT SỰ KHÔNG ĐỔI (có chủ đích — không pre-warm ở bootstrap để tránh làm chậm khởi
động cho mọi vai trò).

**#55 (Bài 20)** — Career Fit và Career Readiness có dùng chung bộ chiều đánh giá không?
ĐÁP ÁN: Không — mỗi cái có 6 chiều riêng biệt.

**#56 (Bài 20)** — Career Fit % có phải xác suất không?
ĐÁP ÁN: Không — là kết quả công thức cộng điểm có trọng số (heuristic).

**#57 (Bài 21)** — `RealConnectorLMSRepository` có kết nối LMS thật không?
ĐÁP ÁN: Không — nội bộ gọi lại `DemoLMSRepository`.

**#58 (Bài 21)** — CMS trong EduDSS là nội bộ hay kết nối CMS ngoài?
ĐÁP ÁN: Nội bộ (internal) — CMS ngoài chưa được kết nối.

**#59 (Bài 21)** — PgVectorStore có kết nối PostgreSQL thật không? CRUD có thật không?
ĐÁP ÁN: Kết nối và schema thật; CRUD là stub, không thực thi SQL thật.

**#60 (Bài 21)** — Vector store thực sự đang hoạt động là gì?
ĐÁP ÁN: `LocalVectorStore` (file-based, NumPy + JSON).

**#61 (Bài 21)** — 3 câu hỏi xác minh một thành phần kiến trúc có IMPLEMENTED thật không?
ĐÁP ÁN: (1) Class tồn tại? (2) Hàm thực thi hành động thật? (3) Điều kiện kích hoạt được
bật trong triển khai hiện tại?

**#62 (Bài 22)** — 3 trạng thái vòng đời Model Registry?
ĐÁP ÁN: Candidate → Production → Archived.

**#63 (Bài 22)** — Ai có quyền promote một mô hình lên Production?
ĐÁP ÁN: Chỉ Admin (`@require_role("Admin")`).

**#64 (Bài 22)** — `auto_promote` được truyền giá trị gì tại điểm gọi thật?
ĐÁP ÁN: `False`, tường minh.

**#65 (Bài 22)** — Model tốt nhất (`is_best`) có tự động lên Production không?
ĐÁP ÁN: Không.

**#66 (Bài 23)** — Mật khẩu được băm bằng thuật toán nào?
ĐÁP ÁN: PBKDF2-HMAC-SHA256.

**#67 (Bài 23)** — Những trường nào được phép vào prompt AI?
ĐÁP ÁN: `student_id`, `risk_level`, `progress_note`.

**#68 (Bài 23)** — Trường nào KHÔNG BAO GIỜ vào prompt AI?
ĐÁP ÁN: Tên thật, email, số điện thoại.

**#69 (Bài 23)** — Prompt injection gián tiếp (indirect) là gì?
ĐÁP ÁN: Lệnh độc hại ẩn trong TÀI LIỆU được truy xuất, không phải trong câu hỏi trực tiếp
của người dùng.

**#70 (Bài 24)** — Baseline test cuối cùng của EduDSS?
ĐÁP ÁN: 417 non-E2E + 28 E2E = 445/445 PASS (trước lượt hoàn thiện 2026-09-16: 403+23=445/445).

**#71 (Bài 24)** — 445 test có chứng minh không có bug tuyệt đối không?
ĐÁP ÁN: Không — chỉ chứng minh không có lỗi trong các trường hợp đã thiết kế.

**#72 (Bài 24)** — 445 test có tương đương 100% code coverage không?
ĐÁP ÁN: Không.

**#73 (Tổng hợp)** — Đọc thuộc Chuỗi 1 (8 bước).
ĐÁP ÁN: Dữ liệu sinh viên → Tiền xử lý → Classification/Regression → SHAP → Diagnosis
Engine → Recommendation → Learning Plan → Sinh viên hành động.

**#74 (Tổng hợp)** — Đọc thuộc Chuỗi 2 (9 bước).
ĐÁP ÁN: Document → Chunk → Embedding → Vector → Similarity → Retrieval → Context → LLM →
Citation.

**#75 (Tổng hợp)** — 5 điều tuyệt đối không được nói (chọn 5 trong THESIS_MUST_NOT_SAY).
ĐÁP ÁN: "Toàn bộ hệ thống dùng PostgreSQL", "SHAP chứng minh nhân quả", "K-Means dự
đoán", "Career Fit là xác suất", "Đã tích hợp LMS/CMS thật".

**#76 (Tổng hợp)** — Issue Register: bao nhiêu issue tổng, bao nhiêu đã sửa hoàn toàn, bao
nhiêu sửa một phần, bao nhiêu còn mở, bao nhiêu P0?
ĐÁP ÁN: 26 tổng, 22 đã sửa hoàn toàn, 2 sửa một phần (KB-CRUD-001: Delete xong nhưng
Update vẫn chưa; COLDSTART-001: UX xong nhưng độ trễ vẫn còn), 2 còn mở hoàn toàn
(ARCH-PGVECTOR-001, ADMIN-USER-001), 0 P0.

**#77 (Tổng hợp)** — Kể tên 2 issue còn mở hoàn toàn và 2 issue chỉ mới sửa một phần.
ĐÁP ÁN: Còn mở hoàn toàn: ARCH-PGVECTOR-001, ADMIN-USER-001. Sửa một phần (2026-09-16):
KB-CRUD-001 (Delete xong, Update chưa), COLDSTART-001 (UX xong, độ trễ chưa đổi).

**#78 (Tổng hợp)** — EduDSS chạy trên framework/entry point nào?
ĐÁP ÁN: Streamlit, entry point `run_dss.py`.

**#79 (Tổng hợp)** — EDUDSS_MODE có những giá trị nào?
ĐÁP ÁN: `DEMO_SYNTHETIC` (mặc định), `REAL_LMS`, `LOCAL_OFFLINE`.

**#80 (Tổng hợp)** — Câu nói "cứu mạng" duy nhất nếu chỉ nhớ được 1 câu?
ĐÁP ÁN: "EduDSS xây dựng đầy đủ một Hệ thống Hỗ trợ Ra Quyết định thực thụ — không dừng ở
dự đoán — với phương pháp luận ML nghiêm túc, một pipeline RAG có căn cứ, và một quy
trình tự-audit trung thực về giới hạn."
