# LỘ TRÌNH HỌC — EduDSS Study Course

Đây là cuốn "giáo trình cá nhân" chuyển hóa toàn bộ gói bảo vệ luận văn
(`reports/final_ui_functional_audit/*`) thành bài giảng dễ hiểu, để bạn **hiểu bản chất**
chứ không chỉ thuộc bảng. Nguồn sự thật (source of truth) là các file đã được đóng băng
(freeze) ở thư mục cha: `RELEASE_FREEZE.md`, `FINAL_ARCHITECTURE_TRUTH.md`,
`THESIS_FORMULA_SHEET.md`, `THESIS_DEFENSE_QA.md`, `THESIS_MUST_NOT_SAY.md`,
`FINAL_SYSTEM_CAPABILITY_MATRIX.csv`. Khóa học này **không thay đổi** sự thật đó — chỉ
dạy lại nó theo cách một người thầy sẽ giảng cho bạn.

## Cách dùng khóa học này

1. Học theo đúng thứ tự 01 → 25. Mỗi bài xây trên kiến thức bài trước — đừng nhảy cóc.
2. Mỗi bài có 28 mục cố định (mục tiêu, giải thích từ số 0, ví dụ, công thức, câu hỏi
   hội đồng, câu trả lời, câu tự kiểm tra...). Đọc hết, đừng chỉ đọc phần công thức.
3. Sau khi học xong 25 bài, dùng `FULL_STUDY_BOOK.md` để ôn tổng hợp.
4. Trước ngày bảo vệ 1 hôm: dùng `QUICK_REVIEW_1_DAY.md`.
5. Trước khi vào phòng bảo vệ 30 phút: dùng `QUICK_REVIEW_30_MINUTES.md`.
6. Dùng `FLASHCARDS.md` để tự kiểm tra nhanh bất cứ lúc nào (che đáp án, tự trả lời).
7. Diễn tập phản xạ bằng `MOCK_DEFENSE_3_ROUNDS.md` — có người hỏi dồn dập bạn.
8. Nếu đứng hình giữa buổi bảo vệ — mở `IF_I_FORGET.md`, nó chỉ có các câu "cứu nguy".

## Bản đồ 25 bài học

| # | File | Chủ đề | Vì sao nằm ở vị trí này |
|---|---|---|---|
| 1 | `01_TONG_QUAN_EDUDSS.md` | Bức tranh toàn cảnh hệ thống | Phải hiểu "cái gì đang được xây" trước khi vào chi tiết |
| 2 | `02_KIEN_TRUC_HE_THONG.md` | Kiến trúc phân lớp | Biết dữ liệu chảy qua những lớp nào |
| 3 | `03_DU_LIEU_FEATURE_TARGET.md` | Dữ liệu, feature, target, dữ liệu tổng hợp | Không hiểu dữ liệu thì không hiểu được vì sao model có R² cao |
| 4 | `04_TIEN_XU_LY_DU_LIEU.md` | Tiền xử lý (Scaler, Imputer, Encoder, SMOTE) | Bước bắt buộc trước khi train bất kỳ model nào |
| 5 | `05_TRAIN_TEST_CV_DATA_LEAKAGE.md` | Train/test split, Cross-validation, Data leakage | Đây là câu hỏi hội đồng hỏi nhiều nhất |
| 6 | `06_CLASSIFICATION.md` | 4 thuật toán phân loại | Ứng dụng đầu tiên của ML trong EduDSS |
| 7 | `07_CLASSIFICATION_METRICS.md` | Accuracy/Precision/Recall/F1 | Đọc hiểu kết quả phân loại |
| 8 | `08_REGRESSION.md` | 4 thuật toán hồi quy | Ứng dụng thứ hai của ML |
| 9 | `09_REGRESSION_METRICS.md` | MAE/MSE/RMSE/R² | Đọc hiểu kết quả hồi quy, đặc biệt R² cao bất thường |
| 10 | `10_GRIDSEARCH_MODEL_COMPARISON.md` | GridSearchCV, so sánh mô hình | Vì sao số lượng cấu hình khác số lượt fit |
| 11 | `11_KMEANS_CLUSTERING.md` | K-Means | Phân biệt "phân cụm" với "dự đoán" |
| 12 | `12_CLUSTERING_METRICS.md` | Silhouette, Davies-Bouldin, Elbow | Đọc hiểu chất lượng phân cụm |
| 13 | `13_SHAP.md` | Giải thích mô hình bằng SHAP | Không phải bằng chứng nhân quả |
| 14 | `14_DSS_DIAGNOSIS_ENGINE.md` | DSS thật sự là gì + Diagnosis Engine | Bài quan trọng nhất — Prediction ≠ DSS |
| 15 | `15_RECOMMENDATION_LEARNING_PLAN.md` | Recommendation + Learning Plan | Từ chẩn đoán ra hành động cụ thể |
| 16 | `16_RAG.md` | RAG từ số 0 | Chuỗi Document→Chunk→Embedding→Retrieval→LLM→Citation |
| 17 | `17_EMBEDDING_RETRIEVAL_CITATION.md` | Chi tiết embedding, retrieval, trích dẫn | Đào sâu phần lõi kỹ thuật của RAG |
| 18 | `18_LLM_GATEWAY_AI.md` | LLM Gateway, nhiều nhà cung cấp AI | Kiến trúc gọi AI, concurrency, lỗi |
| 19 | `19_LEARNING_EXPLAINER.md` | Tính năng hỏi-đáp bài giảng | Ứng dụng thực tế của RAG |
| 20 | `20_CAREER_ADVISOR.md` | Career Fit vs Career Readiness | Không phải xác suất |
| 21 | `21_LMS_CMS_STORAGE.md` | LMS/CMS + PgVectorStore | Phân biệt "có class" với "có kết nối thật" |
| 22 | `22_MODEL_REGISTRY.md` | Candidate → Production → Archived | Train ≠ Deploy |
| 23 | `23_SECURITY_RBAC_PRIVACY.md` | Bảo mật, RBAC, quyền riêng tư | Vai trò, dữ liệu cá nhân, prompt injection |
| 24 | `24_TESTING_LIMITATIONS.md` | Kiểm thử và giới hạn hệ thống | 445 test nghĩa là gì, KHÔNG nghĩa là gì |
| 25 | `25_FULL_MOCK_DEFENSE.md` | Buổi bảo vệ giả lập đầy đủ | Tổng hợp toàn bộ, luyện phản xạ |

## Chuỗi liên kết bắt buộc phải hiểu xuyên suốt (không học rời rạc từng khái niệm)

**Chuỗi 1 — Dữ liệu học sinh đến hành động:**
`Dữ liệu sinh viên → Tiền xử lý → Classification/Regression → SHAP → Diagnosis Engine →
Recommendation → Learning Plan → Sinh viên hành động → Phản hồi quay lại hệ thống`

**Chuỗi 2 — Tài liệu giảng viên đến câu trả lời AI:**
`Tài liệu giảng viên → Ingestion → Chunking → Embedding → Vector Store → Retrieval →
Context Budget → LLM → Citation → Learning Explainer hiển thị cho sinh viên`

Mỗi bài học từ 01–25 đều sẽ chỉ rõ **bài đó nằm ở đâu trong 2 chuỗi này** (mục 12 và mục
15 của khung 28 mục). Đây là điều hội đồng thường kiểm tra: "Vậy cái này nối vào đâu?" —
nếu bạn chỉ học từng khối riêng lẻ mà không biết nó nối tiếp gì, bạn sẽ bị hỏi bí.

## Nguyên tắc không được vi phạm khi trả lời hội đồng

Xem đầy đủ ở `THESIS_MUST_NOT_SAY.md` (thư mục cha) — nhưng ghi nhớ 5 điều cốt lõi:
1. Không nói "toàn bộ hệ thống dùng PostgreSQL" — hệ thống chủ yếu dùng file JSON/CSV/joblib.
2. Không nói "SHAP chứng minh nhân quả" — SHAP chỉ giải thích đóng góp đặc trưng.
3. Không nói "K-Means dự đoán" — K-Means là phân cụm không giám sát.
4. Không nói "Career Fit là xác suất" — đó là điểm số heuristic có trọng số.
5. Không nói "hệ thống đã tích hợp LMS/CMS thật" — mới chỉ có lớp trừu tượng (abstraction).

Bắt đầu với `01_TONG_QUAN_EDUDSS.md`.
