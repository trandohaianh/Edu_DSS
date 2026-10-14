# Ôn tập 1 ngày trước buổi bảo vệ

Dùng file này để ôn lại TOÀN BỘ kiến thức trong khoảng 1-2 giờ, một ngày trước khi bảo
vệ. Đọc từng mục, tự kiểm tra xem có thể giải thích được không mà không cần mở lại bài
học gốc. Nếu vấp ở đâu, quay lại đúng file bài học đó (số bài được ghi trong ngoặc).

## 1. Con số phải thuộc lòng tuyệt đối (Bài 6, 8, 10)

| Bài toán | Random Forest | XGBoost | LightGBM | Linear/Logistic |
|---|---|---|---|---|
| Classification | 24 cấu hình / 120 fit | 1 / 1 (KHÔNG GridSearchCV) | 8 / 40 | 3 / 15 |
| Regression | 12 / 60 | 18 / 90 | 18 / 90 | 0 / 1 |

Test baseline: **417 non-E2E + 28 E2E = 445/445 PASS (trước lượt hoàn thiện 2026-09-16: 403+23=445/445)**. Issue: 26 tracked, 22 fixed, 4
open, 0 P0.

## 2. Công thức phải thuộc (Bài 3, 4, 6, 7, 9, 11, 12, 13, 16, 20)

- Target sinh dữ liệu: `diem_ky_sau = 0.60*diem_ky_nay + 0.15*diem_giua_ky +
  0.10*diem_du_an + 0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5) + noise(σ=0.08)`,
  clip[0,10], clamp ±1.5.
- Z-score: `z=(x-mean)/std`. SMOTE: `x_new = x_i + λ*(x_zi-x_i)`.
- Accuracy/Precision/Recall/F1 (Bài 7); MAE/MSE/RMSE/R² (Bài 9).
- K-Means inertia: `Σ_k Σ_{x∈C_k} ||x-μ_k||²`. Silhouette: `s(i)=(b(i)-a(i))/max(a(i),b(i))`.
- SHAP: `φ_j = Σ_S [trọng số]*[f(S∪{j})-f(S)]`.
- Cosine similarity: `cos(A,B)=(A·B)/(||A||*||B||)`. Ngưỡng RAG: 0.55 (tuyệt đối), 0.85
  (tương đối).
- Career Fit/Readiness: `Σ(trọng số_i × điểm_i)`, 6 chiều mỗi cái, KHÔNG phải xác suất.

## 3. 5 luận điểm cốt lõi phải trả lời trôi chảy (không được vấp)

1. **DSS ≠ Prediction** (Bài 14) — DSS = Prediction + Evidence + Explanation + Diagnosis
   + Recommendation + Action support.
2. **R² cao ≠ mô hình tốt** (Bài 3, 9) — do công thức sinh dữ liệu tuyến tính, KHÔNG phải
   data leakage.
3. **"Có class" ≠ "có kết nối/triển khai thật"** (Bài 21) — LMS abstraction only, CMS
   ngoài không có, PgVectorStore CRUD là stub.
4. **SHAP ≠ chứng minh nhân quả** (Bài 13) — chỉ phân rã đóng góp thống kê.
5. **445 test ≠ chứng minh không có bug** (Bài 24) — chỉ chứng minh không lỗi trong các
   trường hợp đã kiểm thử.

## 4. Chuỗi xử lý phải đọc thuộc lòng không vấp

**Chuỗi 1**: Dữ liệu sinh viên → Tiền xử lý (chống leakage) → Classification/Regression →
SHAP → Diagnosis Engine (rule-based) → Recommendation → Learning Plan (rule-based, LLM
chỉ diễn đạt) → Sinh viên hành động.

**Chuỗi 2**: Tài liệu giảng viên → Ingestion → Chunking → Embedding (sentence-
transformers) → Vector Store (LocalVectorStore) → Retrieval (cosine similarity, ngưỡng
0.55/0.85) → Context Budget → LLM Gateway → Citation → Learning Explainer.

## 5. Bảng "Sự thật vs. Hiểu lầm nguy hiểm" (ôn nhanh bằng cách che cột phải)

| Chủ đề | Sự thật |
|---|---|
| Lưu trữ | File-based (JSON/CSV/joblib) là thật đang chạy. PostgreSQL chỉ có schema, CRUD stub. |
| LMS | Chỉ có abstraction; RealConnector nội bộ gọi Demo. |
| CMS | Nội bộ THẬT; CMS ngoài KHÔNG có. |
| Knowledge Base | Create+Read+Delete có (Delete từ 2026-09-16, chỉ LocalVectorStore); Update vẫn KHÔNG có UI — vẫn là PARTIAL CRUD. |
| Admin User Mgmt | Chỉ đọc (read-only); không CRUD đầy đủ. |
| Model Registry | Train ≠ Deploy; auto_promote=False luôn luôn. |
| K-Means | Phân cụm, KHÔNG dự đoán. |
| SHAP | Giải thích đóng góp, KHÔNG chứng minh nhân quả. |
| Career Fit/Readiness | Heuristic có trọng số, KHÔNG phải xác suất. |
| Diagnosis Engine | Rule-based (if/elif), KHÔNG phải ML/LLM. |
| Learning Plan | Rule-based, LLM chỉ diễn đạt (narrate). |
| Concurrency | MAX_CONCURRENT_REQUESTS=3, CHƯA load-test. |
| Test | 445/445 PASS ≠ không có bug tuyệt đối. |

## 6. Top 10 câu hỏi nguy hiểm nhất — tự trả lời trong đầu trước khi xem lại Bài tương ứng

1. "Hệ thống dùng PostgreSQL đúng không?" (Bài 21)
2. "SHAP chứng minh nguyên nhân đúng không?" (Bài 13)
3. "K-Means dự đoán sinh viên rớt môn đúng không?" (Bài 11)
4. "R² cao chứng tỏ mô hình chính xác đúng không?" (Bài 9)
5. "Đã kết nối LMS/CMS thật chưa?" (Bài 21)
6. "Career Fit là xác suất thành công đúng không?" (Bài 20)
7. "Knowledge Base có CRUD đầy đủ chưa?" (Bài 21, `FINAL_SYSTEM_CAPABILITY_MATRIX.csv`)
8. "Model tốt nhất tự động lên Production đúng không?" (Bài 22)
9. "AI tự thiết kế kế hoạch học tập đúng không?" (Bài 15)
10. "445 test nghĩa là không có bug đúng không?" (Bài 24)

## 7. Việc cần làm trước khi ngủ

- Đọc lại `THESIS_MUST_NOT_SAY.md` (thư mục cha) một lượt.
- Đọc lại `25_FULL_MOCK_DEFENSE.md` một lượt, tự trả lời cả 5 vòng câu hỏi.
- Thử nói to (không đọc) phần "5 luận điểm cốt lõi" ở mục 3 phía trên.
