# Xác minh và sửa lỗi độ chính xác EduDSS (ML + tầng AI dùng kết quả ML)

- Repo: `D:\KLTN\edudss-final-candidate-v2` (worktree), nhánh `fix/ml-correctness`, tạo từ `integration/final-candidate-v2` tại commit `72877d1`.
- Không push, không merge, không sửa `main`.
- Toàn bộ lệnh chạy với `LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2`, không đặt `DATABASE_URL`/`PGVECTOR_URL`, không đụng Docker/PostgreSQL của giả lập 72h. Không phát hiện dấu hiệu ảnh hưởng tới giả lập trong suốt quá trình làm việc.

## 1. Bảng xác minh — Mục 5 (đầy đủ)

Mã | Kết luận | Bằng chứng (test/lệnh, tóm tắt) | Đã sửa? | Commit
---|---|---|---|---
**S-1** | CONFIRMED | `test_ml_hub_ranking_consistency.py`: trên dữ liệu mẫu, model đứng đầu theo Accuracy (Logistic Regression) khác model đứng đầu theo F1-macro (Random Forest); trước sửa main.py không gọi hàm dùng chung nên `resolve_ranking_col` chưa tồn tại — test lỗi ImportError | ✅ | `499a7e9` |
**K-3** | CONFIRMED | `predicted_gpa_llm = student_data_llm_row.get(gpa_col_llm, 0.0)` đọc thẳng `diem_ky_sau` (target thật), không qua `pipeline.predict()` nào | ✅ | `9c854ec` |
**K-4** | CONFIRMED | Tính trên 1000 SV mẫu: công thức cũ (`diem_ky_sau − gpa_previous`, lệch thang 10/4) cho **100%** SV "đang cải thiện"; sau khi so cùng thang, tỷ lệ cải thiện/ổn định/giảm ≈ **34.2% / 17.5% / 48.3%** | ✅ | `9c854ec` |
**R-2** | CONFIRMED | `test_regression_scaler_type.py`: chọn MinMaxScaler/RobustScaler nhưng pipeline thật dùng StandardScaler (do preprocessor bị tạo lại lần 2 sau Feature Selection, thiếu `scaler_type`) | ✅ | `fee3fb0` |
**S-2** | CONFIRMED | `test_model_metadata_feature_cols.py`: metadata lưu `selected_features` (chọn thô) thay vì `hub_feats` (cột pipeline thật dùng sau lọc rò rỉ) | ✅ | `b94fcc0` |
**C-1** | CONFIRMED | Bộ từ khóa cũ chỉ khớp `final_score` (bí danh target!) và `gpa_previous` trên dữ liệu mẫu; bỏ sót toàn bộ `diem_*/ty_le_*/so_gio_*` | ✅ | `c5f4e1a` |
**A-3** | CONFIRMED | `test_rag_query_topic_hints.py`: điểm yếu định dạng thật `"**Tỷ lệ điểm danh**..."` không khớp khóa kỹ thuật `ty_le_diem_danh` trong bảng gợi ý → câu truy vấn RAG chứa nguyên nhãn `**...**`, không có từ khóa chủ đề | ✅ | `8d5ae70` |
**R-1** | CONFIRMED | `test_regression_outlier_no_test_leakage.py`: bật `outlier_method="iqr"` làm tập test co lại (lọc cả tập test, không chỉ train) | ✅ | `69cc8db` |
**R-3** | CONFIRMED | `test_regression_ensemble_selection_no_test_leakage.py`: nguồn hàm dùng `stacking_r2 > voting_r2` tính trên `X_test/y_test` để CHỌN mô hình | ✅ | `69cc8db`+`804b1cb`* |
**P-4** | CONFIRMED (thiếu tính năng) | `test_baseline_dummy_models.py`: `results` không có khóa `"__baseline__"` trước khi sửa | ✅ | `099393a` |
**P-5** | CONFIRMED (thiếu tính năng) | `test_cv_mean_std_reported.py`: `results[name]["cv_mean"]` không tồn tại dù GridSearchCV đã chạy CV | ✅ | `bddd702` |
**P-7** | CONFIRMED | `test_confidence_not_calibrated_label.py`: UI gọi `predict_proba()` là "độ tin cậy" không kèm cảnh báo chưa hiệu chuẩn | ✅ | `2c5ef43` |
**G-2** | CONFIRMED | `test_default_features_no_near_duplicates.py`: cấu hình mặc định chứa CẢ `diem_ky_nay` và `gpa_previous` (r≈0.9999) | ✅ | `8440ab1` |
**G-3** | **REFUTED** | Đã có sẵn: cảnh báo lớp <5 mẫu + mất cân bằng ≥10x (`ml_hub.py:106-118`) và per-class Precision/Recall/F1 qua `classification_report` trong `report` — không tự gộp lớp. Ngưỡng thực tế là <5 mẫu (đề bài ghi <10) nhưng cơ chế đã tồn tại và hoạt động đúng tinh thần yêu cầu | ❌ (không cần) | — |
**P-1** | CONFIRMED | `test_xgboost_gridsearch_when_safe.py`: XGBoost bỏ qua GridSearchCV **vô điều kiện** kể cả khi lớp nhỏ nhất (60 mẫu) >> số fold (3) | ✅ | `915c124` |
**P-3** | CONFIRMED | `test_smote_k_neighbors_not_overly_capped.py`: `k_neighbors` luôn ≤2 dù đủ mẫu thiểu số (60 mẫu, đáng lẽ dùng k=5) | ✅ | `915c124` |
**P-6** | CONFIRMED | `test_voting_ensemble_classifier_consistency.py`: khóa chỉ số Ensemble (`Precision/Recall/F1-Score/Train Accuracy`) lệch khỏi mô hình đơn nên `build_metrics_dataframe` không đọc được; Pipeline ensemble thiếu bước `sampler` dù model đơn có (đơn=True, ensemble=False) | ✅ | `163d05a` |
**X-1** | CONFIRMED | `test_shap_linear_model_uses_predict_proba.py`: với Logistic Regression, `predict_proba` được gọi **0 lần** — SHAP dùng `predict()` (nhãn rời rạc) làm hàm mục tiêu | ✅ | `61c6a54` |
**R-4** | CONFIRMED | Script xác minh trực tiếp: bật cờ, 26/37 feature là cột `_fe_*`; dự đoán bằng feature thô báo lỗi `ValueError: columns are missing` cho toàn bộ `_fe_*` | ✅ (tắt hẳn) | `1bad952` |
**A-4** | CONFIRMED | `test_weakness_detection_direction.py`: luật cũ gắn "điểm yếu" cho SV có `ngay_hoat_dong_gan_nhat` **thấp hơn** TB lớp (tức là **tích cực hơn**) — sai chiều | ✅ | `907d248` |
**E-1** | CONFIRMED | Dashboard/Phân cụm/Tư vấn AI không đọc `data_source_type` nên không cảnh báo dữ liệu mô phỏng (Huấn luyện đã có sẵn) | ✅ | `8819aa6` |
**E-2** | CONFIRMED | Thông báo "...chuyển sang Demo Mode **cá nhân hóa**..." trong khi `demo_text` là chuỗi cố định 100%, không đọc `student_weaknesses`/`predicted_gpa` | ✅ | `e7361af` |
**E-3** | = K-3 | (xem K-3) | ✅ | `9c854ec` |
**E-4** | CONFIRMED | `test_rag_citation_source_label.py`: `_chat_sources` chỉ lấy `title`, bỏ `source_verified`/`status` dù dữ liệu đã có sẵn trong dict trả về | ✅ | `3151481` |
**E-5** | **REFUTED** | Grep xác nhận: `confidence` (0.82/0.88...) trong `DiagnosisEngine` được lưu vào dataclass/`to_dict()` nhưng **không có nơi nào trong `dss/` render nó ra UI** như %/xác suất (`diagnosis_card` ở `ui_kit.py` thậm chí không nhận tham số `confidence`, và không được gọi ở đâu cả) | ❌ (không cần) | — |
**E-6** | CONFIRMED | `test_prediction_form_prefill_own_data.py`: form điền sẵn `df[col].mean()` cho MỌI trường hợp, kể cả sinh viên đã đăng nhập có sẵn dữ liệu của chính mình | ✅ | `ec9de20` |
**E-7** | Đã rà soát (một phần) | Xem Mục 3 bên dưới — bảng riêng | Một phần | — |
**A-1** | KHÔNG CHẠY (cần xin phép) | Cần tải `paraphrase-multilingual-MiniLM-L12-v2` qua mạng — đề bài yêu cầu hỏi trước. **Chưa hỏi/chưa chạy trong phiên này.** | — | — |
**A-2** | CONFIRMED (chỉ báo cáo) | Xem Mục 4 | — | — |
**A-6** | CONFIRMED (chỉ báo cáo) | Xem Mục 4 | — | — |
**K-2** | CONFIRMED (chỉ báo cáo) | Xem Mục 4 | — | — |
**D-1** | CONFIRMED (chỉ báo cáo) | Xem Mục 4 | — | — |

`*` R-3: do sơ suất quy trình, code sửa R-3 bị gộp chung vào commit R-1 (`69cc8db`) vì tôi sửa liên tiếp trong cùng file `trainers.py` trước khi commit. Đã xác minh RIÊNG cho R-3 bằng cách tạm revert đúng đoạn code ensemble-selection về bản cũ, chạy lại test (FAIL đúng như dự đoán), rồi khôi phục (PASS) — xem chi tiết trong message của commit `804b1cb`. Đây là sai sót quy trình duy nhất, đã ghi nhận trung thực thay vì che giấu.

## 2. Test

### 2.1 Trước khi sửa (baseline, commit `72877d1`)
```
570 passed, 158 skipped in 323.96s (0:05:23)
```
Không có test nào fail. File: `baseline_tests.txt`.

### 2.2 Sau khi sửa (toàn bộ 17 commit trên `fix/ml-correctness`)
```
634 passed, 158 skipped, 8 warnings in 183.44s (0:03:03)
```
File: `after_tests.txt`. **0 fail, 0 regressie số test skip giữ nguyên (158).**

64 test mới = đúng bằng số dòng test tăng thêm (634 − 570). Không xóa/sửa hành vi bất kỳ test cũ nào.

**Lưu ý về 1 lần fail thoáng qua:** trong lúc chạy full suite lần đầu (khi tôi vô tình sửa file `trainers.py` cho P-1 CÙNG LÚC pytest đang chạy), `tests/test_audit_and_governance.py::test_i_f1_macro_computed_correctly_for_multiclass` fail 1 lần với `KeyError`. Đã xác minh đây là **flaky do đua tiến trình** (tôi tự gây ra bằng cách sửa file khi test đang chạy), không phải lỗi thật: chạy lại riêng file đó 2 lần (cô lập, và trong file gốc) đều **PASS 100%**, và lần chạy full suite CUỐI CÙNG (không sửa file gì trong lúc chạy) cũng **PASS 100%, 0 fail**. Bài học quy trình: không sửa code khi test đang chạy nền — đã tự sửa quy trình cho các bước sau.

### 2.3 Danh sách test mới (22 file, 1089 dòng, 0 dòng xóa)
```
test_ai_advisor_prediction_source.py, test_baseline_dummy_models.py,
test_clustering_default_features.py, test_confidence_not_calibrated_label.py,
test_cv_mean_std_reported.py, test_default_features_no_near_duplicates.py,
test_feature_engineering_disabled_r4.py, test_ml_hub_ranking_consistency.py,
test_model_metadata_feature_cols.py, test_prediction_form_prefill_own_data.py,
test_rag_citation_source_label.py, test_rag_query_topic_hints.py,
test_regression_ensemble_selection_no_test_leakage.py,
test_regression_outlier_no_test_leakage.py, test_regression_scaler_type.py,
test_shap_linear_model_uses_predict_proba.py,
test_smote_k_neighbors_not_overly_capped.py, test_synthetic_data_banner.py,
test_voting_ensemble_classifier_consistency.py,
test_weakness_detection_direction.py, test_xgboost_gridsearch_when_safe.py
```
### 2.4 Test cũ bị sửa: **KHÔNG có test nào bị xóa/sửa nội dung.**
Chỉ MỘT file cũ được **bổ sung thêm 2 test mới** (không sửa test có sẵn): `test_production_demo_policy.py` (+2 test cho E-2, cùng chủ đề với các test Demo Mode đã có trong file này).

## 3. E-7 — Rà soát `demo/mẫu/giả lập/fallback/random/np.random/rng` trong code chạy thật

Vị trí | Nội dung | Đã có nhãn? | Đã sửa trong phiên này?
---|---|---|---
`llm_gateway.py` demo fallback chain | Kế hoạch 4 tuần cố định khi hết provider | Một phần (chỉ có ghi chú cuối) | ✅ E-2
`ai_advisor.py`/Dashboard/Clustering | Không cảnh báo `data_source_type=synthetic` | Không | ✅ E-1
`core/models.py` 19 tài liệu KB | Trích dẫn không phân biệt verified | Không | ✅ E-4
`ml_hub.py` form dự đoán | Điền sẵn trung bình lớp | Không | ✅ E-6
`warehouse_tab.py:127-141` (`random.uniform` cho điểm/điểm danh "giả lập") | Nút "Bắn sự kiện LMS giả lập" | **Có** — đã gắn nhãn "(Giả lập)" ở tiêu đề expander, và **đã bị chặn hoàn toàn trong REAL_LMS** (comment ghi rõ đây là audit trước đó, xem code 100-106) | Không cần — đã đúng
`vector_store.py` (PostgreSQL/pgvector fallback → LocalVectorStore) | Fallback hạ tầng kỹ thuật (DB không sẵn sàng) | Có ghi chú trong docstring, không phải nội dung hiển thị cho người dùng cuối | Không cần — không phải nội dung "bịa" cho người dùng
`admin_agent.py:75` | "fallback" trong câu cảnh báo về ngân sách AI | Câu thông báo minh bạch, không phải nội dung giả | Không cần

**Kết luận E-7:** đã rà soát các vị trí có khả năng cao nhất hiển thị nội dung/giả cho người dùng cuối; các vị trí nghiêm trọng nhất (E-1, E-2, E-4, E-6) đã sửa. Không quét được **100% tuyệt đối** mọi occurrence của `fallback`/`random` trong toàn bộ `dss/` (hàng chục file, phần lớn là fallback hạ tầng kỹ thuật hợp lệ — DB/cache/provider — không phải nội dung bịa đặt hiển thị cho người dùng); nếu cần rà soát triệt để hơn, nên làm thành hạng mục riêng.

## 4. Nhóm D — chỉ xác minh, không sửa

**A-1 (embedding model tiếng Việt):** KHÔNG chạy — cần tải `paraphrase-multilingual-MiniLM-L12-v2` qua mạng, đề bài yêu cầu hỏi trước khi tải. Chưa xin phép trong phiên này nên chưa đo Recall@5.

**A-2 (2 luồng RAG tách rời):** **CONFIRMED tách rời.** Tài liệu tải lên ở tab "Quản lý tri thức" được lưu vào `vector_store.get_vector_store(namespace=...)` (`knowledge_base.py:298-299`). Nhưng `MultiAIProvider.find_relevant_documents_rag` (được gọi từ Tư vấn AI qua `rag_service.retrieve_documents` → `_find_docs_rag_safe`) **chỉ** đọc từ: (1) 19 tài liệu hard-code trong `knowledge_base["documents"]`, (2) tham số `runtime_documents` — mà trong `ai_advisor.py`, biến `runtime_rag_documents = []` được gán **1 lần duy nhất và KHÔNG BAO GIỜ được cập nhật** (grep xác nhận không có lần gán thứ 2 nào trong toàn file), (3) lịch sử đánh giá/huấn luyện từ warehouse (chỉ namespace `admin_operations`, chỉ role Admin). Kết luận: **tài liệu do trường tải lên KHÔNG BAO GIỜ đến được Tư vấn AI thật** — `vector_store` của tab Quản lý tri thức là 1 kho hoàn toàn tách biệt, không được `find_relevant_documents_rag` truy vấn dưới bất kỳ điều kiện nào. Đây là lỗi kiến trúc nghiêm trọng nhưng theo yêu cầu đề bài, **không sửa** trong phiên này.

**A-6 (code không được gọi):**
- `SemanticCache.lookup`/`.store` (cache mờ/fuzzy theo embedding): **0 lời gọi** ngoài `semantic_cache.py`. `llm_gateway.py` chỉ dùng `layered_cache.exact_cache.get/.set` (tầng cache CHÍNH XÁC, khác tầng SemanticCache).
- `LayeredSemanticCache.get_student_plan`/`.set_student_plan`: **0 lời gọi** ngoài định nghĩa.
- `rag_service.retrieve_context` (pipeline RAG "sản xuất" có namespace + confidence floor, theo docstring): **0 lời gọi** ở bất kỳ đâu trong `dss/` — toàn bộ luồng thật dùng `retrieve_documents` (đơn giản hơn, không lọc namespace/confidence floor).
- `EnsembleTrainer` (`core/models.py:46`): **được import** vào `trainers.py` nhưng **không có lời gọi khởi tạo `EnsembleTrainer(` nào** trong toàn bộ `dss/`.
- `model_registry.evaluate_drift`: **0 lời gọi** ngoài định nghĩa (trùng D-1).

**K-2 (rủi ro tương đối):** CONFIRMED — `compute_lecturer_dashboard_overview` dùng phân vị 25%/50% của **chính lớp đang xem** (`ref_series = df[gpa_ref_col]`), không có ngưỡng tuyệt đối nào. Hệ quả: nếu cả lớp đều điểm cao, vẫn luôn có ~25% sinh viên bị gắn "rủi ro cao" một cách tương đối — dù không ai thực sự yếu. Đề xuất (không sửa): kết hợp điều kiện `predicted <= q25 AND predicted < ngưỡng_tuyệt_đối` (vd. 5.0/10) để "rủi ro cao" chỉ xuất hiện khi VỪA thấp hơn nhóm VỪA thấp hơn ngưỡng đạt tuyệt đối.

**D-1 (drift):** CONFIRMED — không tab nào gọi `evaluate_drift` (trùng phát hiện ở A-6).

## 5. Số liệu — `tools/ml_benchmark.py`

Mô hình | Baseline (gốc) | Sau khi sửa | Thay đổi
---|---|---|---
Logistic Regression — Acc / F1m | 0.9250 / 0.7149 | 0.9250 / 0.7149 | không đổi
Random Forest Clf — Acc / F1m | 0.8900 / 0.8745 | 0.8900 / 0.8745 | không đổi
XGBoost Clf — Acc / F1m | 0.9150 / 0.7008 | 0.9150 / 0.7008 | không đổi
LightGBM Clf — Acc / F1m | 0.9200 / 0.7086 | 0.9200 / 0.7086 | không đổi
Linear Regression — RMSE / R² | 0.0758 / 0.9929 | 0.0758 / 0.9929 | không đổi
Random Forest Reg — RMSE / R² | 0.1572 / 0.9695 | 0.1572 / 0.9695 | không đổi
XGBoost Reg — RMSE / R² | 0.1212 / 0.9818 | 0.1212 / 0.9818 | không đổi
LightGBM Reg — RMSE / R² | 0.1256 / 0.9805 | 0.1256 / 0.9805 | không đổi
**Mốc DummyClassifier (mới, P-4)** | — | Acc=0.46, F1m=**0.126** | mới
**Mốc DummyRegressor (mới, P-4)** | — | R²=**−0.003** | mới

**Giải thích trung thực việc số liệu KHÔNG đổi (không phải sửa "không có tác dụng"):** `ml_benchmark.py` gọi `train_and_evaluate()` **trực tiếp** với **toàn bộ tham số mặc định** của trainer (`outlier_method="none"`, `scaler_type="StandardScaler"`, `training_strategy` mặc định = so sánh (không phải "Kết hợp"), `balance_method="none"`). Phần lớn lỗi đã sửa (R-1 outlier, R-2 scaler, R-3 chọn ensemble, P-1 XGBoost GridSearch, P-3 SMOTE k, P-6 Voting Ensemble) **chỉ thay đổi hành vi khi bật các tùy chọn KHÔNG PHẢI mặc định** — không phải lỗi trong đường huấn luyện mặc định. Các lỗi còn lại (S-1, S-2, C-1, G-2, K-3, K-4, A-3, A-4, E-1, E-2, E-4, E-6) nằm ở **tầng UI/bootstrap/AI**, không nằm trong `train_and_evaluate()` nên vốn dĩ không ảnh hưởng số liệu benchmark thuần túy này. Bằng chứng số liệu **thật sự thay đổi** cho từng lỗi cụ thể nằm trong **test riêng của lỗi đó** (bảng Mục 1) — vd. R-2 test cho thấy scaler đổi từ StandardScaler → MinMaxScaler/RobustScaler đúng như chọn; R-1 test cho thấy kích thước tập test thay đổi khi bật/tắt outlier removal.

**Không có chỉ số nào giảm** trong phiên sửa lỗi này — vì các sửa đổi ảnh hưởng THUẬT TOÁN (R-1/R-2/R-3/P-1/P-3/P-6) chỉ kích hoạt khi người dùng CHỌN các tùy chọn không mặc định (outlier removal, scaler khác, ensemble, SMOTE) — với dữ liệu mẫu và cấu hình mặc định hiện tại, chưa có phép đo nào kích hoạt các nhánh đó để thấy chỉ số giảm. Nếu người dùng bật `outlier_method="iqr"` thật, R-1 dự kiến sẽ làm RMSE/MAE **tăng nhẹ** (đúng, trung thực hơn) vì SV "bất thường" không còn bị loại khỏi tập test — đây LÀ kết quả mong đợi theo đúng tinh thần đề bài ("không làm đẹp số liệu"), nhưng benchmark mặc định không đo được điều này (xem `after_metrics.txt` để có phép đo minh họa thủ công).

**Nhắc lại (Mục 6 đề bài):** đây là dữ liệu MÔ PHỎNG (`generate_data()`, công thức tuyến tính gần sạch nhiễu) — R²≈0.99 của Linear Regression **không chứng minh** hệ thống dự đoán tốt trên sinh viên thật. Không tuyên bố "độ chính xác cao" dựa trên số liệu này ở bất kỳ đâu trong report.

## 6. Việc CHƯA làm / rủi ro còn lại

1. **A-1** chưa đo (cần xin phép tải model qua mạng).
2. **A-2** đã xác nhận là lỗi kiến trúc thật sự (2 luồng RAG tách rời hoàn toàn) nhưng CHƯA sửa theo đúng yêu cầu đề bài (Nhóm D chỉ báo cáo).
3. **E-7** chưa quét 100% tuyệt đối mọi file `dss/` cho từ khóa demo/fallback/random — đã ưu tiên các vị trí rủi ro cao nhất.
4. **P-7** mới sửa phần chú thích/UI text tại `personal_prediction_tab`; CHƯA kiểm tra tương tự cho `file_prediction_tab`/`batch_prediction_tab` (có thể còn chữ "độ tin cậy" tương tự ở đó — chưa xác minh riêng).
5. Sai sót quy trình: commit R-3 bị gộp vào commit R-1 (giải thích ở Mục 1, đã verify riêng nhưng không tách được thành 2 commit sạch).
6. `K-2` chỉ đề xuất hướng sửa, chưa triển khai (đúng theo yêu cầu Nhóm D).
7. Chưa chạy `tests/e2e` (cần Playwright + trình duyệt, theo đúng chỉ dẫn "chỉ chạy nếu môi trường cho phép" — không chạy để tránh rủi ro/tốn tài nguyên không cần thiết trong lúc giả lập 72h đang chạy) và `tests/load` (cần DB thật, bị cấm theo Mục 2b).

## 8. NHÓM F — Hợp nhất 2 luồng RAG + chỉ dùng tài liệu có thẩm quyền

### 8.1 Xác minh hiện trạng (trước khi sửa)

Mã | Kết luận | Bằng chứng
---|---|---
**F-0a** | CONFIRMED | `MultiAIProvider.find_relevant_documents_rag` (`core/models.py:794`) chỉ đọc `self.knowledge_base["documents"]` (19 tài liệu viết cứng) + `runtime_documents` — **không bao giờ** gọi `vector_store.get_vector_store(...)`. Xác nhận lại bằng grep: 0 lời gọi `vector_store` (namespace thật) trong hàm này; `self.vector_store` trong `__init__` là **một class hoàn toàn khác** (`core/warehouse.VectorStore`, chỉ là cache embedding `.npy`, không liên quan tới kho tài liệu theo namespace).
**F-0b** | CONFIRMED | 4/19 tài liệu (`doc_003`, `doc_004`, `doc_009`, `doc_016`) tự gán cứng `"status": "APPROVED", "source_verified": True` trong code Python — không có người duyệt, không có bản ghi duyệt nào. 15 tài liệu còn lại `DRAFT`/`False`.
**F-0c** | CONFIRMED | `document_ingestion.ingest_document` (tài liệu Admin/Giảng viên tải lên qua tab "Quản lý tri thức") không có bất kỳ trường trạng thái/thẩm quyền nào — tải lên xong dùng được ngay lập tức. Test `test_document_ingestion_governance.py` xác nhận: trước sửa, `KeyError: 'content_hash'`/không có `status`.
**F-0d** | PARTIAL (mô tả ban đầu sai một phần) | `citation_service.verify_citations` **KHÔNG chỉ** dùng cho Giải thích bài giảng — cũng được gọi 2 lần trong `ai_advisor.py` (dòng ~1036, ~1364, luồng Tư vấn AI) và 1 lần trong `llm_evaluator.py`. Cơ chế xác minh trích dẫn đã tồn tại cho CẢ 2 luồng từ trước, chỉ chưa gắn cờ rõ ràng khi phát hiện ảo giác (đã sửa, xem 8.3).
**F-0e** | CONFIRMED | `rag_service.retrieve_context` có 0 lời gọi trong `app/dss` (chỉ được gọi từ 2 file test: `test_final_candidate_v2_extended.py`, `test_lms_ai_rag_gateway.py`) — đúng là code chưa dùng trong luồng thật, y như A-2/A-6 đã báo cáo trước đó.

### 8.2 Thiết kế đã triển khai

1. **Metadata thẩm quyền** (`document_governance.py`, mới): hằng số trạng thái vòng đời `DRAFT → PENDING_REVIEW → APPROVED → REJECTED/RETIRED`, loại tài liệu (`quy_che`, `de_cuong`, `giao_trinh`, `bai_giang`, `huong_dan_hoc_tap`, `faq_chinh_thuc`), và bộ lọc cứng `is_document_usable()` (status=APPROVED thật + có approved_by + chưa hết hạn + đã tới hiệu lực + content_hash khớp).
2. **`document_ingestion.ingest_document`** giờ LUÔN gắn metadata quản trị (mặc định `PENDING_REVIEW`, ép đè bất kỳ giá trị `status` nào người gọi cố truyền vào qua `**extra_metadata`) + `content_hash = SHA-256(raw_text)`.
3. **`vector_store.py`**: thêm `update_document_metadata()` (duyệt/từ chối không cần tính lại embedding) và mở rộng `list_documents()` để lộ ra đầy đủ trường quản trị. Triển khai đầy đủ + có test cho `LocalVectorStore` (backend thực tế dùng trong môi trường này); `PgVectorStore` được cập nhật SQL tương ứng nhưng **CHƯA kiểm thử với PostgreSQL thật** (không có kết nối DB trong môi trường an toàn với giả lập 72h).
4. **`document_approval_service.py`** (mới): `approve_document`/`reject_document`/`retire_document`/`list_pending_documents`. Chặn tự duyệt tài liệu của chính mình; Sinh viên không bao giờ duyệt được; Giảng viên chỉ duyệt `giao_trinh`/`bai_giang`/`de_cuong` **và** phải đứng tên dạy đúng môn đó trong CMS (`cms_lecture_repository`) — **hạn chế đã biết**: hệ thống không có bảng phân công giảng viên-môn học độc lập, chỉ kiểm tra "đã từng đứng tên dạy môn này", fail-closed (từ chối) nếu không xác minh được. Mọi quyết định đều ghi audit log qua `audit_log_repository`.
5. **`rag_service.retrieve_unified_context`** (mới) — đường ống truy xuất **DUY NHẤT** dùng để trích dẫn: đọc trực tiếp `vector_store` thật, lọc CỨNG bằng `is_document_usable` (over-fetch tối đa 300 ứng viên rồi lọc **trước** khi cắt top-k, không phải sau), kiểm tra đồng nhất `embedding_model` giữa các chunk trong 1 lượt tìm (báo lỗi rõ nếu lẫn model), và trả `NO_RELEVANT_EVIDENCE` kèm thông báo trung thực khi không có tài liệu đã duyệt phù hợp.
6. **`ai_advisor.py`** (Tư vấn AI) rewiring: `_find_docs_rag_safe` chuyển từ `rag_service.retrieve_documents` (đường cũ, chỉ đọc 19 tài liệu viết cứng) sang `rag_service.retrieve_unified_context` (kho thật, đã duyệt). Khối "Bằng chứng & Nguồn tham khảo" hiển thị thông báo trung thực khi không có tài liệu hợp lệ. Câu trả lời có trích dẫn ảo giác (`citation_service.verify_citations` phát hiện) giờ được gắn cờ `hallucinated=True` rõ ràng trong lịch sử chat, kèm cảnh báo hiển thị khi xem lại — **không xóa/chặn** câu trả lời (người dùng vẫn thấy đầy đủ, chỉ không còn bị coi ngầm là "đã xác minh").
7. **19 tài liệu viết cứng cũ**: gỡ bỏ tự nhận `"status": "APPROVED"` (giữ nguyên `"source_verified"` — xem sửa sai ở dưới), và thêm `legacy_knowledge_seed.py` — sao chép (idempotent) toàn bộ 19 tài liệu vào `vector_store` thật với `status=PENDING_REVIEW`, `issuer="Tài liệu mẫu nội bộ EduDSS"`. Test chứng minh cả 2 chiều: (a) ngay sau seed, nội dung Pomodoro (doc_003) KHÔNG được trích dẫn dù khớp truy vấn gần như tuyệt đối (điểm ~0.93); (b) sau khi Admin duyệt THẬT qua `document_approval_service`, cùng truy vấn đó MỚI trả về được, kèm `approved_by` rõ ràng.
8. **Alembic migration** `9f3a1c7d2e46` (down_revision=`35d62f0c6002`, đầu chuỗi hiện tại): thêm cột `doc_type/issuer/official_ref/status/approved_by/approved_at/review_note/content_hash/effective_from/expires_at` vào `rag_documents` (ADDITIVE, không sửa migration cũ), kèm index `(namespace, status)`. Đã xác minh `alembic heads` chỉ có 1 đầu chuỗi (không tạo nhánh), model ORM `RagDocument` import/load thành công. **CHƯA chạy `alembic upgrade` với PostgreSQL thật** (không có kết nối DB được phép dùng trong phiên này).
9. **UI "Chờ duyệt"** trong tab "Quản lý tri thức" (`tab_namespaces`, Admin-only theo `TAB_ACCESS` sẵn có) — liệt kê tài liệu `PENDING_REVIEW`, nút Duyệt/Từ chối gọi thẳng `document_approval_service` (không tự set trạng thái trong UI).

### 8.3 Sai sót đã tự phát hiện và sửa trong phiên này

Khi thêm `legacy_knowledge_seed.py`, lần đầu tôi đổi **cả** `status` lẫn `source_verified` của 4 tài liệu từ `APPROVED`/`True` xuống `DRAFT`/`False`, làm fail 1 test có sẵn (`test_rag_source_governance.py::test_classification_covers_all_19_demo_documents_exhaustively`). Điều tra cho thấy `source_verified` và `status` là **2 khái niệm khác nhau** đang bị gộp chung: `status=APPROVED` = tự nhận đã được EduDSS duyệt cấp tổ chức (đây mới là lỗi F-0b thật); `source_verified=True` = nội dung có trích dẫn nguồn thật/kiểm chứng được (kỹ thuật Pomodoro của Cirillo, kỹ thuật Feynman, Krashen Input Hypothesis — đều là nguồn có thật, độc lập với việc EduDSS có duyệt tài liệu hay không). Đã sửa lại: chỉ đổi `status`, giữ nguyên `source_verified=True` cho đúng 4 tài liệu đó (commit `4a54a0d`). Toàn bộ suite quay lại 691 passed / 0 fail.

### 8.4 Test

10 commit NHÓM F (`e1db069` → `5e93e60`) + 1 commit sửa sai sót (`4a54a0d`) = 11 commit, thêm **12 file test mới** (~100 test case), không sửa/xóa test cũ nào trừ 1 trường hợp có giải thích (`test_rag_service.py::test_real_lms_mode_filters_unverified_documents` — khẳng định đúng hành vi SAI đã xác minh ở F-0b, viết lại để khẳng định thực tế mới + thêm test đối chứng cho con đường ĐÚNG trong `test_legacy_knowledge_seed.py`). Full suite cuối cùng: **691 passed, 158 skipped, 0 failed** (từ mốc 634 passed sau NHÓM A–E).

### 8.5 Việc CHƯA làm / rủi ro còn lại (NHÓM F)

1. **PgVectorStore + migration Alembic hoàn toàn CHƯA được kiểm thử với PostgreSQL thật** — chỉ viết theo đúng pattern SQL hiện có, syntax-checked, `alembic heads` xác nhận chuỗi migration hợp lệ, nhưng KHÔNG có bằng chứng chạy được thật (không được phép kết nối DB trong môi trường này). Rủi ro: có thể có lỗi SQL/kiểu dữ liệu chỉ lộ ra khi chạy thật.
2. **Không có UI riêng cho Giảng viên duyệt tài liệu môn mình phụ trách** — `document_approval_service` đã hỗ trợ đầy đủ vai trò Giảng viên (có test), nhưng tab "Quản lý tri thức" vẫn Admin-only (`TAB_ACCESS`, không đổi). Theo đúng tiền lệ dự án (quản lý tài liệu môn học nằm ở trang riêng của Giảng viên, tránh 2 nơi sửa cùng 1 thứ), cần một điểm vào UI mới ở trang đó — chưa làm.
3. **Không có bảng phân công "giảng viên X phụ trách môn Y" độc lập** — `_lecturer_owns_course` chỉ kiểm tra "đã từng đứng tên dạy môn này trong CMS" (fail-closed nếu chưa có bản ghi nào), không phải xác nhận phân công chính thức từ Phòng Đào tạo.
4. **`_run_compare_ai`/`llm_service.compare_providers`** (công cụ "So sánh AI", chỉ Giảng viên/Admin) vẫn đi qua đường RAG cũ (`retrieve_documents`) — chưa rewiring sang `retrieve_unified_context`. Đây là công cụ kỹ thuật phụ, không phải luồng tư vấn chính, nhưng vẫn là 1 đường trích dẫn từ 19 tài liệu viết cứng còn sót lại.
5. **`find_relevant_documents_rag` GIỮ NGUYÊN không đổi** (đọc 19 tài liệu viết cứng) — đây là quyết định CÓ CHỦ ĐÍCH: hàm này có 7+ test hồi quy phụ thuộc chặt vào hành vi tìm kiếm/ngưỡng tương đối của nó (`test_rag_service.py`). "Hợp nhất" được thực hiện bằng cách rewiring NƠI GỌI (ai_advisor.py) sang hàm mới, không phải xóa/sửa hàm cũ — hàm cũ trở thành code KHÔNG còn được dùng cho trích dẫn thật (nhưng vẫn tồn tại, vẫn được test, có thể gây nhầm lẫn cho người đọc code sau này nếu không đọc comment).
6. **`_run_compare_ai`, `llm_evaluator.py`** và các đường gọi LLM khác ngoài luồng chat chính của `ai_advisor.py` chưa được rà soát toàn bộ để xác nhận KHÔNG còn đường nào khác đọc `_init_enhanced_knowledge_base` cho trích dẫn thật — chỉ xác nhận `_find_docs_rag_safe` (5 điểm gọi) đã chuyển hẳn.
7. Chưa đo lại A-1 (embedding đa ngôn ngữ) trong bối cảnh kho tri thức thật (vẫn cần xin phép tải model mới qua mạng).

## 10. FINAL REMEDIATION PASS (đợt 2 — đọc lập review, 2026-09)

Nhánh/worktree **không đổi**: `fix/ml-correctness` trong `D:\KLTN\edudss-final-candidate-v2`, tạo từ `integration/final-candidate-v2`. Không tạo nhánh mới, không push, không merge, không đụng vào worktree/DB/container/cổng của giả lập 72h (`D:\KLTN\edudss-72h-simulation`) hay `edudss-closure-*`. Xác nhận bằng `docker ps` (chỉ đọc) trong Mục 10.7: 7 container đang chạy thật, không container/tiến trình nào bị dừng/sửa trong toàn bộ phiên này.

Quy ước nhãn trạng thái dùng ĐÚNG như yêu cầu: `IMPLEMENTED_AND_TESTED`, `IMPLEMENTED_NOT_RUNTIME_VERIFIED`, `EVALUATED_NO_CHANGE`, `DEFERRED`, `BLOCKED_BY_RUNNING_SIMULATION`. Không dùng "VERIFIED" cho bất kỳ thứ gì liên quan PostgreSQL thật nếu chưa thực sự chạy trên DB thật.

### 10.1 Mục 1 — `confidence=0.85` viết cứng trong kế hoạch học tập

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- Xác minh: `LearningPlanGenerator.generate_plan()` (`dss/services/learning_plan.py:154`) luôn gán `confidence=0.85` cho MỌI sinh viên, không tính từ `profile`. `ai_advisor.py:1425` (cũ) hiển thị thẳng thành `f"Độ tin cậy kế hoạch: {...:.0%}"` — trình bày hằng số cố định như số đo được, cho MỌI sinh viên giống hệt nhau.
- Sửa: **KHÔNG thay 0.85 bằng con số khác** (đúng yêu cầu chống bịa số). Bỏ hẳn dòng hiển thị phần trăm khỏi UI; thêm comment tại dataclass field + tại điểm gán giá trị, ghi rõ đây là hằng số chính sách, không phải giá trị đo lường/hiệu chuẩn.
- Rà soát toàn repo các hằng số dạng "độ tin cậy" khác:

  | Vị trí | Giá trị | Phân loại | Có hiển thị ra UI dạng số đo được không |
  |---|---|---|---|
  | `learning_plan.py:162` (`StudentLearningPlan.confidence`) | 0.85 | **HEURISTIC** (hằng số chính sách cố định) | ĐÃ SỬA — không còn hiển thị |
  | `diagnosis_engine.py:108,132,153,174,197,220` (`Hypothesis.confidence`) | 0.82/0.88/0.78/0.85/0.75/0.70 | **HEURISTIC** (do người viết luật chuyên gia đặt, ghi trong docstring module: "độ tin cậy" theo luật, không phải xác suất thống kê) | KHÔNG — grep lại `dss/tabs/*.py` xác nhận 0 kết quả render `hypothesis.confidence`/`.confidence` từ `DiagnosisEngine` (E-5, xem 10.9) |
  | `config.py:674` `RAG_RELATIVE_THRESHOLD=0.85` | 0.85 | **TECHNICAL THRESHOLD** (ngưỡng nội bộ so sánh tương đối với tài liệu tốt nhất trong retrieval, không phải "độ tin cậy" trình bày cho người dùng) | Không — dùng nội bộ trong `rag_service` |
  | `config.py:679` `RAG_LOW_CONFIDENCE_FLOOR=0.55` | 0.55 | **TECHNICAL THRESHOLD** (sàn cosine similarity tối thiểu để coi là "liên quan") | Không — dùng nội bộ, có xuất hiện trong câu thông báo kỹ thuật ("độ tương đồng chưa đạt ngưỡng") nhưng không tự nhận là "độ tin cậy dự đoán" |
  | `ml_hub.py:1082` (xác suất `predict_proba`) | tính từ mô hình | **CALIBRATED-CANDIDATE** (xác suất thật từ mô hình, nhưng CHƯA qua `CalibratedClassifierCV`) | Có — đã ghi chú "chưa hiệu chuẩn" từ đợt P-7 trước (comment tại `ml_hub.py:1178`, xem Mục 1 bảng gốc) |

  Không phát hiện thêm hằng số "confidence/độ tin cậy" nào khác bị trình bày như số đo được mà chưa có nhãn phân loại.
- Test: `test_learning_plan_confidence_not_fabricated.py` (3 test, verify-before-fix: 2/3 FAIL trên code gốc → PASS sau sửa). Không regression: `test_learning_plan_wiring.py` (5 test) + toàn bộ test `ai_advisor`/`learning_plan` (33 test) đều pass.
- Commit: `ba3b394`.

### 10.2 Mục 2 — Hợp nhất RAG cho `_run_compare_ai` (và phát hiện rộng hơn: luồng sinh kế hoạch chính)

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- Truy vết đầy đủ: `_run_compare_ai` → `llm_service.compare_providers` → `_run_one_provider` → `MultiAIProvider.generate_personalized_advice`. Phát hiện **RỘNG HƠN** phạm vi đề bài nêu: `generate_personalized_advice` là điểm HỘI TỤ DUY NHẤT của CẢ 2 luồng — không chỉ "So sánh AI" mà CẢ nút chính "Tạo Kế hoạch Học tập" (mọi provider: huggingface trực tiếp, và Gemini/Groq/OpenAI/Ollama qua `LLMGateway.stream_generate`) — đều gọi đúng hàm này để lấy tài liệu trích dẫn thật cho prompt. Hàm này trước đó tự gọi `self.find_relevant_documents_rag` (đường RAG CŨ) — nghĩa là closure `_find_docs_rag_safe` (đã rewiring ở NHÓM F đợt 1) chỉ phục vụ khung xem trước "Bằng chứng & Nguồn tham khảo", KHÔNG phải nguồn tài liệu thật sự đi vào nội dung kế hoạch — 2 đường có thể trích dẫn LỆCH NHAU.
- Sửa tại đúng 1 điểm gốc (`generate_personalized_advice`) thay vì vá từng nơi gọi: đổi sang `rag_service.retrieve_unified_context` (cùng hàm `_find_docs_rag_safe` dùng), thêm tham số `role` truyền tay qua chuỗi gọi (`stream_generate` tiêu thụ `role` làm tham số riêng, không lọt `**kwargs`, nên phải chuyển tay).
- Test mới (`test_generate_personalized_advice_unified_rag.py`, 4 test) — đúng yêu cầu "PENDING/REJECTED/APPROVED/top-k sau lọc quản trị":
  - `test_generate_personalized_advice_does_not_use_legacy_knowledge_base`
  - `test_generate_personalized_advice_only_cites_approved_documents` (PENDING_REVIEW bị loại dù khớp nội dung gần tuyệt đối)
  - `test_generate_personalized_advice_rejected_document_never_cited` (REJECTED → danh sách trích dẫn rỗng, không lấp bằng tài liệu khác)
  - `test_compare_ai_role_is_forwarded_to_unified_retrieval`
  - Lọc top-k-sau-governance-filter: kế thừa từ cơ chế over-fetch (×10, trần 300) → lọc `is_document_usable` → cắt top_k đã có sẵn trong `retrieve_unified_context` (test `test_rag_retrieve_unified_context.py` từ đợt NHÓM F đầu đã phủ riêng phần này; không viết lại).
  - Lọc theo tenant khác (`other_organization`): **CHƯA có test riêng cho khía cạnh multi-tenant** ở tầng `retrieve_unified_context`/`vector_store` — `organization_id` mới chỉ dùng nhất quán ở các repository Postgres (`model_registry`,...), vector_store hiện tại (LocalVectorStore) CHƯA có trường tenant riêng biệt trong metadata chunk. Ghi nhận là **rủi ro còn lại**, xem 10.9.
- Xác minh (verify-before-fix, `git diff`/`checkout`/`apply`): 4/4 test FAIL trên code gốc, PASS sau sửa. Test liên quan (`ai_advisor`, `llm_service`, `llm_gateway`, `rag_service`, `compare`, `governance`): 155 passed, 2 skipped — không regression.
- Commit: `b2722fa`.

### 10.3 Mục 3 — UI duyệt tài liệu cho Giảng viên

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- Xác minh claim "backend đã hỗ trợ Giảng viên": ĐÚNG — `document_approval_service.can_approve_document`/`approve_document`/`reject_document` đã hỗ trợ vai trò Giảng viên từ NHÓM F đợt 1 (chỉ duyệt môn mình phụ trách theo CMS, fail-closed, tự kiểm tra lại độc lập với UI). NHƯNG tab "Quản lý tri thức (RAG)" — nơi DUY NHẤT có UI duyệt — là Admin-only trong `TAB_ACCESS` → Giảng viên KHÔNG CÓ LỐI VÀO nào, dù backend sẵn sàng.
- Quyết định: XÂY UI (không DEFERRED) vì mức an toàn cao — service tự kiểm tra lại quyền độc lập (fail-closed) nên dù UI mới có lỗi hiển thị, backend vẫn từ chối hành động sai.
- Xây trang mới "📄 Duyệt tài liệu" (`Giảng viên / CVHT`-only qua `TAB_ACCESS`), CỐ TÌNH hẹp: chỉ 2 namespace liên quan giảng dạy, không có nút xóa/nạp tài liệu, chỉ gọi `document_approval_service` (không tự viết RBAC). Thêm `list_pending_documents_for_approver()` (bộ lọc hiển thị, không phải biên bảo mật).
- Test mới (7 test, `test_lecturer_document_approval_tab.py`): RBAC (không tự duyệt, không duyệt `quy_che`, không duyệt môn không phụ trách), tenant/ownership (chỉ thấy tài liệu môn mình dạy), an toàn backend độc lập UI, và source-inspection xác nhận trang không có nút xóa/nạp/đụng `admin_operations`.
- Xác minh (verify-before-fix): 6/7 test FAIL trên code gốc (AttributeError — hàm/tab chưa tồn tại), PASS sau sửa.
- Commit: `78143b0`.

### 10.4 Mục 4 — Kiểm toán 19 tài liệu cũ + bootstrap có kiểm soát

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- Kiểm toán đầy đủ 19/19 tài liệu (`_init_enhanced_knowledge_base`): **0/19 `status=APPROVED`**, **19/19 `approved_by=None`** — xác nhận ZERO tự duyệt. 4/19 (doc_003/004/009/016) giữ `source_verified=True` (trích dẫn học thuật có thật — khác khái niệm với `status` quản trị, xem F-0b Mục 8).
- Audit call site: `legacy_knowledge_seed.seed_legacy_knowledge_base_documents` — grep toàn `dss/` xác nhận **0 điểm gọi tự động** ở bất kỳ đâu (chỉ được gọi từ test và từ nút Admin mới thêm). Nghĩa là trong MỌI môi trường đang chạy hiện tại (kể cả giả lập 72h, dùng image build sẵn trước nhánh này), 19 tài liệu cũ hoàn toàn CHƯA từng được nạp vào `vector_store` thật.
- Bootstrap có kiểm soát: thêm nút "🌱 Nạp tài liệu mẫu nội bộ" (Admin-only, trong tab đã Admin-only sẵn) — gọi đúng hàm seed (idempotent, LUÔN `PENDING_REVIEW`), KHÔNG tự duyệt bất kỳ tài liệu nào — Admin vẫn phải tự xem xét từng tài liệu ở hàng đợi "Chờ duyệt" như tài liệu người dùng thật tải lên.
- Test mới: `test_knowledge_base_tab_legacy_seed_button_never_auto_approves` (source-inspection, xác nhận không có `approve_document` ngay sau khối gọi seed). Test cũ (`test_legacy_knowledge_seed.py`) đã phủ "seed luôn PENDING_REVIEW, idempotent" từ đợt trước.
- Commit: `65b73ec`.

### 10.5 Mục 5 — Nhãn "rủi ro tương đối" (K-2)

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- Xác minh: `risk_level` trong `ai_advisor.py`/`home.py` tính bằng phân vị 25%/50% của điểm dự đoán TRONG CHÍNH `df` hiện tại — hoàn toàn tương đối, không sàn tuyệt đối (đúng K-2 đã báo cáo trước). Trước đợt này, mọi badge "Mức rủi ro: CAO" hiển thị KHÔNG kèm chú thích nào.
- Sửa: hằng số dùng chung `ui_kit.RELATIVE_RISK_DISCLAIMER`, áp tại 5 điểm hiển thị chính (hồ sơ rủi ro + bối cảnh chat trong `ai_advisor.py`, banner + badge trong `home.py`, tiêu đề section trong `dashboard.py`, tooltip KPI trong `admin_reports.py`).
- Test mới (5 test, source-inspection): xác nhận hằng số tồn tại và xuất hiện đủ số lần ở mỗi module. Verify-before-fix: 5/5 FAIL trên code gốc, PASS sau sửa.
- Còn lại: một vài chỗ hiển thị rủi ro dạng bảng/dataframe riêng lẻ trong `dashboard.py` (vd. cột "Mức rủi ro" trong bảng danh sách) chưa có chú thích RIÊNG — chấp nhận được vì đã có chú thích chung ngay tiêu đề section phía trên, không lặp lại ở từng dòng.
- Commit: `b6bb1bb`.

### 10.6 Mục 6 — Benchmark embedding tiếng Việt (A-1)

**Trạng thái: `IMPLEMENTED_AND_TESTED`** (đã hỏi và được người dùng đồng ý tải model qua mạng trước khi chạy)

- Mở rộng `rag_evaluator.STANDARD_RAG_BENCHMARK_SET` từ 8 → 23 truy vấn (phủ đủ 19/19 tài liệu + 4 truy vấn "diễn đạt khác" không trùng từ khóa tiêu đề, để đo đúng khả năng hiểu ngữ nghĩa).
- Chạy thật (`tools/embedding_benchmark_vi.py`), kết quả đầy đủ ở `reports/ml_correctness/embedding_benchmark_vi.txt`:

  | Model | Recall@5 | Precision@5 | MRR | nDCG@5 | Latency TB (ms) |
  |---|---|---|---|---|---|
  | `all-MiniLM-L6-v2` (hiện tại) | 0.9130 | 0.1826 | 0.8348 | 0.8543 | 19.04 |
  | `paraphrase-multilingual-MiniLM-L12-v2` (ứng viên) | 0.9565 | 0.1913 | **0.9565** | **0.9565** | 36.65 |

- **Kết luận: KHÔNG phải `EVALUATED_NO_CHANGE`** — model đa ngôn ngữ xếp hạng tốt hơn RÕ RỆT, đặc biệt trên các truy vấn "diễn đạt khác" (kịch bản người dùng thật gõ, không lặp từ khóa tài liệu): MRR/nDCG tăng từ ~0.83-0.85 lên 0.957. Chi phí: độ trễ tính embedding tăng ~2x (19ms→37ms/tài liệu) — không đáng kể so với thời gian sinh câu trả lời LLM (giây). Cả 2 model đều MISS 1/23 truy vấn (paraphrase cực đoan, không còn từ khóa chung nào) — hạn chế chung, không phải lỗi riêng của model nào.
- **KHÔNG tự đổi model production trong phiên này** — đây là quyết định kiến trúc lớn hơn phạm vi "remediation pass" (ảnh hưởng embedding đã lưu trong `vector_store` thật + cơ chế phát hiện "lẫn model" trong `retrieve_unified_context` sẽ kích hoạt nếu tài liệu cũ/mới dùng model khác nhau — cần kế hoạch re-embed toàn bộ kho khi đổi). **Khuyến nghị**: cân nhắc đổi mặc định sang `paraphrase-multilingual-MiniLM-L12-v2` cho nội dung tiếng Việt, nhưng cần quyết định rõ ràng của người dùng + kế hoạch re-embed trước khi thực hiện.
- Commit: `4ac2541`.

### 10.7 Mục 7 — Validation Postgres cô lập (migration + PgVectorStore)

**Trạng thái: `BLOCKED_BY_RUNNING_SIMULATION`** (theo yêu cầu tường minh của người dùng, không phải do thiếu tài nguyên kỹ thuật)

- Kiểm tra an toàn (chỉ đọc, không sửa gì): `docker ps` xác nhận 7 container đang chạy thật (giả lập 72h + closure-C), chiếm đúng các cổng đã liệt kê trong quy tắc an toàn gốc (8515, 55530, 8775, 1337, 8090, 55461). `docker-compose.yml` của repo dùng `container_name: edudss-postgres` — **TRÙNG TÊN THẬT** với container giả lập 72h đang chạy → xác nhận KHÔNG được dùng `docker compose --profile db up` từ nhánh này cho validation, bắt buộc phải dùng container hoàn toàn độc lập (tên/cổng/volume riêng).
- `docker stats`/`docker system df` (chỉ đọc): CPU gần như rảnh (0-3%), RAM còn nhiều — về mặt tài nguyên có thể an toàn, nhưng đây vẫn là hành động Docker thật (tạo container mới).
- Đã hỏi người dùng trước khi thực thi (đúng tinh thần "chuẩn bị nhưng không tự chạy trừ khi an toàn") — người dùng chọn **CHỈ chuẩn bị, KHÔNG chạy**.
- Sản phẩm đã chuẩn bị: `tools/validate_migration_isolated_postgres.sh` — container tên `edudss-remediation-validation-postgres`, cổng `55599` (khác hoàn toàn mọi cổng đang dùng), volume riêng, tự dọn dẹp (`trap cleanup EXIT`) kể cả khi lỗi giữa chừng. Khi được chạy: bật extension `vector`, `alembic upgrade head` (áp đủ 9 migration gồm migration mới `9f3a1c7d2e46`), xác nhận cột mới trên `rag_documents`, chạy bộ test đang SKIP vì thiếu `DATABASE_URL` (xem Mục 10.8).
- **CHƯA CHẠY — không có kết quả thật nào để báo cáo**. Migration mới CHỈ được xác minh qua `alembic heads` (không cần kết nối DB) — xem Mục 8.2 — KHÔNG BAO GIỜ dùng chữ "VERIFIED" cho việc này cho tới khi script trên thực sự chạy.
- Commit: `6dbe38d`.

### 10.8 Mục 8 — Kiểm kê 158 test bị skip

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

Chạy `pytest tests -q --ignore=tests/e2e --ignore=tests/load -rs` (full run, không DB thật) → **711 passed, 158 skipped, 0 failed**. Phân loại toàn bộ 158 skip theo lý do (tổng khớp đúng 158):

| Nhóm | Số lượng | Lý do skip | Đánh giá |
|---|---|---|---|
| DB_REQUIRED_REPOSITORY | 60 | "No PostgreSQL configured — X repository tests skipped, not faked" (CMS 12, user 11, admin AI config 10, academic 9, activity log 7, AI token usage 7, recommendation 4) | Hợp lệ — tự khai báo rõ "not faked" |
| DB_REQUIRED_INTEGRATION | 49 | "No PostgreSQL configured — prediction/consultation 11, pgvector store 11, combined Phase 1B+8A 8, Phase 12A real-embedding/RAG 6, subscription 4, Phase 1 9" | Hợp lệ |
| WORKSTREAM_POSTGRES_URLS | 24 | "Workstream B/C/D PostgreSQL URLs are required" (B 11, C 8, D 1), "A+B PostgreSQL URLs required" (4) | Hợp lệ |
| LIVE_STACK_URLS | 15 | "University onboarding PostgreSQL URLs required" (7), "Final candidate v2 live stack URLs required (FCV2_*)" (6), "Stage 5 live staging stack URLs required (FINAL_STAGING_*)" (1), "Dedicated Phase 13..." (1) | Hợp lệ |
| RLS_DUAL_ROLE | 9 | Cần cả `DATABASE_URL` (owner) VÀ `DATABASE_APP_ROLE_URL` (role không phải superuser) để test RLS thật | Hợp lệ |
| LOCAL_DEV_ONLY | 1 | "app/.env chỉ tồn tại trên máy dev cục bộ, không commit vào repo" | Hợp lệ |

- **Không phát hiện skip "bất thường"**: grep toàn `tests/*.py` xác nhận **0 kết quả** cho `pytest.mark.skip(` không điều kiện và **0 kết quả** cho `pytest.mark.xfail` — mọi skip đều là `skipif` có điều kiện rõ ràng (thiếu biến môi trường DB/live-stack), tự ghi lý do trong message, đúng nguyên tắc "not faked" nhất quán trong toàn bộ test suite.
- Tất cả 158 skip đều thuộc nhóm cần PostgreSQL thật/stack live thật — nhất quán với việc môi trường làm việc này CHỦ ĐỘNG không kết nối DB thật (Mục 2b quy tắc an toàn gốc).

### 10.9 Mục 9 — Tái xác minh độc lập F-0d, G-3, E-5

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

- **F-0d** (REFUTED một phần từ trước — `verify_citations` đã dùng cho cả Tư vấn AI, không chỉ Giải thích bài giảng): **re-verify — REFUTED, và nay CÀNG VỮNG HƠN**. Trước Mục 10.2, `_docs_for_checklist` (dùng để `verify_citations`) và `relevant_docs` (dùng để build prompt/nội dung kế hoạch thật) lấy từ 2 đường KHÁC NHAU (unified vs. legacy) — có nguy cơ lệch tập tài liệu. Sau Mục 10.2, CẢ HAI đều đi qua `retrieve_unified_context` — nhất quán hơn, giảm rủi ro citation-check kiểm tra "nhầm" tập tài liệu so với tài liệu thật sự được trích trong kế hoạch.
- **G-3** (REFUTED từ trước — cơ chế cảnh báo lớp hiếm đã tồn tại, `ml_hub.py:106-118`): **re-verify — REFUTED, không đổi**. Không file nào trong phiên này (`trainers.py`, `ml_hub.py`) bị chỉnh sửa; đọc lại trực tiếp `ml_hub.py:106-118` xác nhận cơ chế cảnh báo `< 5 mẫu`/mất cân bằng `≥10x` + `classification_report` per-class vẫn nguyên vẹn.
- **E-5** (REFUTED từ trước — `DiagnosisEngine.confidence` không hiển thị UI): **re-verify — REFUTED, không đổi, và phân biệt rõ với phát hiện MỚI ở Mục 10.1**. Grep lại `dss/tabs/*.py`, `dss/services/report_service.py`, `dss/core/models.py` xác nhận **0 kết quả** render `hypothesis.confidence`/`diagnosis.*confidence` ra UI. Đây là phát hiện HOÀN TOÀN KHÁC `learning_plan.py`'s `confidence=0.85` (Mục 10.1) — 2 module riêng biệt (`diagnosis_engine.py` vs. `learning_plan.py`), lỗi hiển thị chỉ tồn tại ở module sau.

### 10.10 Mục 10 — Hồi quy đầy đủ

**Trạng thái: `IMPLEMENTED_AND_TESTED`**

```
cd D:/KLTN/edudss-final-candidate-v2/app
env -u DATABASE_URL -u PGVECTOR_URL LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2 PYTHONIOENCODING=utf-8 \
  d:/KLTN/code/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e --ignore=tests/load -rs
```
Kết quả: **711 passed, 158 skipped, 0 failed** (220.41s). Mốc trước đợt remediation này: 691 passed, 158 skipped, 0 failed (sau NHÓM F đợt 1) — tăng đúng 20 test mới (3 Mục 1 + 4 Mục 2 + 7 Mục 3 + 1 Mục 4 + 5 Mục 5 = 20). Không test nào bị sửa nội dung trong đợt này (chỉ thêm mới); không test nào chuyển từ pass sang fail/skip.

### 10.11 Việc CHƯA làm / rủi ro còn lại (đợt 2)

1. Lọc theo tenant/tổ chức khác (`organization_id`) ở tầng `retrieve_unified_context`/`vector_store` — CHƯA có test riêng, `LocalVectorStore` hiện chưa có trường tenant tách biệt trong metadata chunk (xem 10.2).
2. Validation Postgres thật (migration + PgVectorStore + RLS) — **BLOCKED_BY_RUNNING_SIMULATION**, script đã sẵn sàng (10.7), CHƯA chạy.
3. Khuyến nghị đổi embedding model (10.6) CHƯA được quyết định/thực hiện — cần xác nhận riêng của người dùng + kế hoạch re-embed kho thật trước khi đổi mặc định production.
4. `_run_one_provider`'s nhánh `except TypeError` (tương thích chữ ký cũ) không truyền `role` — mặc định rơi về `"Sinh viên"` (an toàn hơn vì namespace hạn chế hơn, không phải lỗ hổng) nhưng chưa có test riêng cho nhánh fallback này.
5. Bảng/dataframe hiển thị rủi ro riêng lẻ trong `dashboard.py` (ngoài tiêu đề section) chưa có chú thích tương đối riêng từng dòng (10.5) — chấp nhận được, không coi là lỗi.

## 11. Trả lời ngắn gọn (cập nhật sau đợt remediation thứ 2)

- **Lỗi SAI (REFUTED, đã tái xác minh độc lập ở đợt 2):** G-3, E-5 (phân biệt rõ với lỗi MỚI ở `learning_plan.py`, xem 10.1/10.9), F-0d (nay càng vững hơn sau khi hợp nhất RAG ở 10.2).
- **Đã sửa thêm ở đợt remediation thứ 2 (5 hạng mục, 7 commit mới: `ba3b394`, `b2722fa`, `78143b0`, `65b73ec`, `b6bb1bb`, `4ac2541`, `6dbe38d`):** confidence kế hoạch học tập bịa số (Mục 10.1), hợp nhất RAG cho CẢ luồng sinh kế hoạch chính lẫn So sánh AI — phát hiện rộng hơn yêu cầu gốc (10.2), UI duyệt tài liệu cho Giảng viên (10.3), kiểm toán + bootstrap có kiểm soát cho 19 tài liệu cũ (10.4), nhãn "rủi ro tương đối" (10.5), benchmark embedding tiếng Việt với kết luận rõ ràng (10.6, không phải "không đổi gì").
- **Còn lại sau đợt 2 (xem 10.11 để biết đầy đủ):** validation Postgres thật (BLOCKED_BY_RUNNING_SIMULATION, chờ người dùng tự chạy khi an toàn), quyết định đổi embedding model (chờ xác nhận người dùng), lọc tenant ở vector_store (chưa có test/trường riêng).
- **Tuyên bố hệ thống hiện CHƯA đúng với code (đã biết, còn lại sau đợt 2):** `PgVectorStore`/migration Alembic mới hoàn toàn chưa được xác minh chạy thật trên DB thật (chỉ `alembic heads` tĩnh); model embedding mặc định vẫn là `all-MiniLM-L6-v2` dù benchmark cho thấy model đa ngôn ngữ tốt hơn rõ rệt cho tiếng Việt (chưa đổi, đang chờ quyết định).

## 12. FINAL CORRECTNESS + COMMERCIAL ARCHITECTURE CLOSURE (đợt 3, 2026-09-26)

Đợt review kiến trúc thương mại phát hiện **2 lỗi correctness mức P0 MỚI** (H-1, H-2), cả hai đã sửa + test đầy đủ (verify-before-fix). Chi tiết đầy đủ nằm ở `app/reports/production_readiness/FINAL_COMMERCIAL_ARCHITECTURE_AUDIT.md` (báo cáo audit kiến trúc thương mại 34 câu hỏi) — mục này chỉ tóm tắt phần liên quan trực tiếp tới correctness ML/AI.

- **H-1 (CRITICAL, đã sửa, commit `58a170f`):** `LLMGateway.stream_generate()` định tuyến theo `hasattr(llm_integration, "generate_personalized_advice")` thay vì theo `request_type` — vì `MultiAIProvider` LUÔN có phương thức đó, `prompt` thật của người dùng (chat hỏi tiếp AI Advisor, câu hỏi giải thích bài giảng, hỏi nhanh Trang chủ) bị ÂM THẦM BỎ QUA, thay bằng một "kế hoạch học tập" chung cho `predicted_gpa=0.0`. Ảnh hưởng 3/5 luồng chat thật trong toàn hệ thống. Sửa: định tuyến theo `request_type in {"advisor_plan"}`. Test: 4/5 FAIL trên code gốc (đi qua public API, fake provider ghi lại prompt thật), PASS sau sửa.
- **H-2 (đã sửa, commit `a62264e`):** luồng "Tạo Kế hoạch Học tập" gọi `retrieve_unified_context` HAI LẦN độc lập cho cùng 1 response (prompt LLM + citation-check sau đó) — rủi ro 2 tập tài liệu lệch nhau nếu trạng thái duyệt đổi giữa 2 lần gọi. Sửa: truy xuất 1 lần, tái dùng qua `prefetched_relevant_docs`. Test: 2/3 FAIL trên code gốc, PASS sau sửa.
- **Hồi quy:** 719 passed, 158 skipped, 0 failed — chạy 2 lần liên tiếp, kết quả nhất quán (tăng 8 test so với mốc 711 cuối đợt 2).
- **34Q matrix kiến trúc thương mại** (`AI_DECISION_ARCHITECTURE_34Q_MATRIX.md`): 9/34 IMPLEMENTED_AND_TESTED, 13/34 PARTIALLY_IMPLEMENTED, 11/34 NOT_IMPLEMENTED (chủ yếu: Deterministic Calculator, Rule Engine, Versioned Regulation Engine, Agent tổng quát học vụ — các cấu phần enterprise chưa từng được xây trong đồ án này).
- **Kế hoạch canonical hóa** (`CANONICALIZATION_PLAN.md`): kiểm kê 50+ worktree/branch, đề xuất tham khảo (KHÔNG thực thi) — phát hiện đáng chú ý: `production_readiness/FINAL_CAPABILITY_MATRIX.csv` (có sẵn từ phiên trước) có thể mâu thuẫn với audit độc lập mới, cần đối chiếu trước khi dùng cho luận văn.
