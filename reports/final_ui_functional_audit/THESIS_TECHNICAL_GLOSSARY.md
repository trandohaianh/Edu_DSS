# EduDSS — Technical Glossary (Bilingual, EN/VI)

| Term | English | Tiếng Việt |
|---|---|---|
| RBAC | Role-Based Access Control — permissions gated by user role | Kiểm soát truy cập theo vai trò |
| RAG | Retrieval-Augmented Generation — grounding an LLM's answer in retrieved documents | Sinh văn bản có truy xuất tăng cường |
| Vector store | A storage system indexing document embeddings for similarity search | Kho lưu trữ vector nhúng |
| Embedding | A numeric vector representation of text capturing semantic meaning | Biểu diễn vector ngữ nghĩa của văn bản |
| Cosine similarity | A similarity metric between two vectors based on the angle between them | Độ tương đồng cosine |
| Chunking | Splitting a document into smaller retrievable segments | Phân đoạn tài liệu |
| Citation | A traceable reference from an AI answer back to its source document | Trích dẫn nguồn |
| GridSearchCV | Exhaustive hyperparameter search combined with cross-validation | Tìm kiếm siêu tham số dạng lưới kết hợp kiểm định chéo |
| Cross-validation (k-fold) | Splitting data into k parts to validate a model across multiple train/test splits | Kiểm định chéo k-phần |
| SMOTE | Synthetic Minority Over-sampling Technique — generates synthetic minority-class samples | Kỹ thuật sinh mẫu tổng hợp cho lớp thiểu số |
| Data leakage | Information from outside the training set improperly influencing the model | Rò rỉ dữ liệu |
| Random Forest | An ensemble of decision trees trained on bootstrapped samples | Rừng ngẫu nhiên |
| XGBoost / LightGBM | Gradient-boosted decision tree algorithms | Thuật toán tăng cường gradient trên cây quyết định |
| Logistic Regression | A linear model for classification via a sigmoid/softmax function | Hồi quy logistic |
| R² (R-squared) | Proportion of variance in the target explained by the model | Hệ số xác định |
| MAE / MSE / RMSE | Mean Absolute/Squared Error, Root Mean Squared Error — regression error metrics | Sai số tuyệt đối/bình phương trung bình, căn sai số bình phương trung bình |
| Precision / Recall / F1 | Classification quality metrics based on true/false positives/negatives | Độ chính xác / độ bao phủ / điểm F1 |
| K-Means | An unsupervised clustering algorithm minimizing within-cluster variance | Phân cụm K-means |
| Silhouette score | A cluster-quality metric based on intra- vs inter-cluster distance | Chỉ số silhouette |
| Elbow method | A heuristic for choosing cluster count k from an inertia curve | Phương pháp khuỷu tay |
| SHAP | SHapley Additive exPlanations — feature-contribution explanation using Shapley values | Giải thích đóng góp đặc trưng dựa trên giá trị Shapley |
| Feature contribution | The estimated effect of one input variable on a specific prediction | Đóng góp của đặc trưng |
| Causality | A cause-effect relationship (NOT what SHAP demonstrates) | Quan hệ nhân quả |
| Heuristic | A rule-of-thumb calculation, not a formally calibrated statistical model | Phương pháp suy nghiệm |
| Model Registry | A system tracking model versions and lifecycle states | Hệ thống quản lý phiên bản mô hình |
| Candidate / Production / Archived | Model lifecycle states: newly trained / actively serving / retired | Ứng viên / Đang triển khai / Lưu trữ |
| Auto-promotion | Automatically moving a model to Production without human approval (NOT implemented here) | Tự động thăng cấp mô hình |
| LMS | Learning Management System (e.g. Moodle, Canvas) — NOT connected in this project | Hệ thống quản lý học tập |
| CMS | Content Management System — here, an internal lecture-content repository, not external | Hệ thống quản lý nội dung |
| Repository pattern | An abstraction layer decoupling business logic from a concrete data source | Mẫu thiết kế kho lưu trữ (repository) |
| Pseudonymization | Replacing identifying data with a non-identifying token before processing | Ẩn danh hóa dữ liệu |
| Prompt injection | An attack attempting to override an LLM's instructions via crafted input | Tấn công chèn lệnh vào prompt |
| Token | A unit of text (roughly a word-piece) an LLM processes; cost/usage is tracked per token | Mã thông báo (đơn vị xử lý văn bản của LLM) |
| Context budget | A limit on how much text (in tokens) is sent to the LLM per request | Ngân sách ngữ cảnh |
| Semaphore (concurrency) | A concurrency primitive limiting how many operations run simultaneously | Cờ hiệu giới hạn số luồng đồng thời |
| Synthetic data | Artificially generated data, not collected from real-world observation | Dữ liệu tổng hợp |
| DSS | Decision Support System | Hệ thống hỗ trợ ra quyết định |
| Diagnosis Engine | A rule-based module identifying likely causes of academic risk | Bộ máy chẩn đoán dựa trên luật |
