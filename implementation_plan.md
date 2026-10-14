# Kế hoạch Refactor Kiến trúc Dữ liệu & ML cho EduDSS

## Tổng quan mục tiêu
Chuyển đổi toàn diện pipeline đánh giá Machine Learning của dự án **EduDSS** từ tư duy:
```
X hiện tại ──> Công thức thủ công ──> diem_ky_sau ──> ML học lại công thức vừa tạo
```
sang:
```
Historical X_t (học kỳ t) + Observed Y_(t+1) (kết quả thực tế kỳ sau)
                           ↓
                      ML Training
                           ↓
                          fθ
                           ↓
Current X_new,t ───> Production Model (fθ) ───> Ŷ_(t+1)
```

Đồng thời giải quyết triệt để 2 vấn đề kiến trúc:
1. **Target hồi quy `diem_ky_sau`**: Tách bạch rõ giữa **Synthetic/Demo Mode** (dùng cho demo UI, testing, bootstrap) và **Real/Evaluation Mode** (bắt buộc target là kết quả thực tế quan sát được từ dữ liệu lịch sử $Y_{t+1}$, tuyệt đối không tự tính bằng công thức mô phỏng).
2. **Aliases & Target Leakage Guard**: Chuẩn hóa canonical target (`diem_ky_sau`, `xep_loai`), xử lý alias (`final_score`, `grade`), ngăn chặn duplicate columns và rò rỉ dữ liệu chéo (leakage) giữa hồi quy và phân loại, đồng thời bảo vệ biến dự báo hợp lệ đã biết tại thời điểm $t$ (`diem_ky_nay`).

---

## User Review Required

> [!IMPORTANT]
> **Xác nhận về Dữ liệu Thực tế (Longitudinal Dataset):**
> Sau khi khảo sát toàn bộ các tập dữ liệu hiện có trong project (`sample_student_data_1000.csv`, `Student_Performance.csv`, `student-mat.csv`,...):
> - Tất cả các tập dữ liệu hiện có trong project đều là dữ liệu cắt ngang (cross-sectional) hoặc dữ liệu demo với cột `final_score`/`grade` cho môn học hiện tại, **chưa có dataset thực tế nào chứa kết quả thực tế kỳ tiếp theo ($Y_{t+1}$) theo dõi sinh viên qua các học kỳ**.
> - Do đó, theo đúng nguyên tắc không tự bịa dữ liệu thực tế, báo cáo nghiệm thu sẽ tuyên bố rõ ràng:
>   *"The architecture is ready for real longitudinal evaluation, but no real observed next-semester target is currently available."*
> - Trong Real/Evaluation Mode: nếu dataset tải lên không có cột kết quả kỳ sau được quan sát, hệ thống sẽ đưa ra cảnh báo/lỗi rõ ràng và **không** tự sinh target thay thế.

> [!NOTE]
> **Dữ liệu Demo / Synthetic Mode (`generate_data`):**
> - Hàm `generate_data()` và dữ liệu mẫu khởi tạo được giữ lại để phục vụ Demo UI, integration test, và bootstrap ứng dụng mà không cần người dùng tải file trước.
> - Tuy nhiên, toàn bộ metadata đi kèm sẽ được gắn nhãn minh bạch: `data_source_type = "synthetic"`. UI và báo cáo sẽ phân định rõ ràng giữa "Chỉ số mô phỏng (Simulation/Demo)" và "Đánh giá thực tế (Real Evaluation)".

---

## Proposed Changes

### Component 1: Centralized Target & Leakage Guard (`dss/core/target_utils.py`)
Tạo module mới tập trung toàn bộ logic canonical target, alias mapping, leakage guard, phân nhóm xếp loại và hỗ trợ dữ liệu thời gian.

#### [NEW] [target_utils.py](file:///d:/KLTN/code/app/dss/core/target_utils.py)
- **Hằng số Canonical & Aliases**:
  - `CANONICAL_TARGET_REGRESSION = "diem_ky_sau"`
  - `CANONICAL_TARGET_CLASSIFICATION = "xep_loai"`
  - `COLUMN_ALIASES = {"final_score": "diem_ky_sau", "grade": "xep_loai"}`
  - `LEGITIMATE_PREDICTORS = {"diem_ky_nay", "gpa_previous", "prior_gpa", "attendance", "ty_le_diem_danh", "so_gio_hoc_tuan", "diem_giua_ky", "diem_du_an"}`
- **Target Leakage Matrix**:
  - Khi target là `xep_loai`: X không được chứa `{"xep_loai", "grade", "diem_ky_sau", "final_score"}`.
  - Khi target là `diem_ky_sau`: X không được chứa `{"diem_ky_sau", "final_score", "xep_loai", "grade"}`.
  - `diem_ky_nay` KHÔNG BAO GIỜ bị coi là leakage column.
- **Classification Bins & Labels chuẩn hóa**:
  - `CLASSIFICATION_BINS = [0.0, 3.99, 5.49, 6.99, 8.49, 10.0]`
  - `CLASSIFICATION_LABELS = ["Yếu", "Trung bình", "Khá", "Giỏi", "Xuất sắc"]`
  - Ghi rõ chú thích: `Prototype classification grouping / business rule`.
  - Hàm `score_to_xep_loai(series)` bọc `pd.cut(..., right=True, include_lowest=True)`.
- **Hàm `canonicalize_columns(df, strict=True)`**:
  - Case 1: Có `grade`, không có `xep_loai` -> rename `grade` -> `xep_loai`.
  - Case 2: Có `final_score`, không có `diem_ky_sau` -> rename `final_score` -> `diem_ky_sau`.
  - Case 3: Có cả `grade` và `xep_loai`: nếu khớp nhau -> giữ `xep_loai`, loại `grade`; nếu lệch nhau -> raise `ValueError` cảnh báo mâu thuẫn dữ liệu.
  - Case 4: Có cả `final_score` và `diem_ky_sau`: nếu khớp nhau -> giữ `diem_ky_sau`, loại `final_score`; nếu lệch nhau -> raise `ValueError` cảnh báo mâu thuẫn dữ liệu.
- **Hàm `filter_leakage_features(df, target_col, feature_cols)`**:
  - Lọc bỏ target, alias của target, target-derived columns, và ID columns.
  - Đảm bảo giữ nguyên các legitimate predictors như `diem_ky_nay`.
- **Hàm hỗ trợ Temporal / Longitudinal**:
  - `detect_temporal_column(df)`: phát hiện cột thời gian/học kỳ (`semester`, `hoc_ky`, `nam_hoc`, `timestamp`,...).
  - `prepare_longitudinal_dataset(df, student_id_col, time_col, outcome_col)`: shift $X_t \to Y_{t+1}$ cho dữ liệu nhiều học kỳ của cùng 1 sinh viên.
  - `temporal_train_test_split(df, time_col, test_size)`: chia quá khứ cho train, tương lai cho test.

---

### Component 2: Data Helpers & Synthetic Distinction (`dss/core/data_helpers.py`)

#### [MODIFY] [data_helpers.py](file:///d:/KLTN/code/app/dss/core/data_helpers.py)
- Refactor `generate_data()`:
  - Đổi vai trò thành DEMO / SYNTHETIC DATA ONLY.
  - Gắn nhãn rõ ràng: `df.attrs["data_source_type"] = "synthetic"`.
  - Sử dụng `score_to_xep_loai` từ `target_utils.py` để tạo `xep_loai` chuẩn hóa.
  - Ghi chú rõ: công thức weighted sum là mô phỏng phục vụ demo chức năng và kiểm thử, không phải công thức chính thức hay bằng chứng về độ chính xác dự báo thực tế.
- Refactor `load_data(uploaded_file)`:
  - Gắn nhãn `df.attrs["data_source_type"] = "real"`.
  - Tuyệt đối không gọi công thức sinh `diem_ky_sau`. Dữ liệu thật phải chứa target quan sát được.

---

### Component 3: ML Trainers (`dss/core/trainers.py`)

#### [MODIFY] [trainers.py](file:///d:/KLTN/code/app/dss/core/trainers.py)
- **`ClassificationTrainer.train_and_evaluate`**:
  - Áp dụng `canonicalize_columns` và `filter_leakage_features` ngay từ đầu.
  - Khi `target_col == 'xep_loai'`: chặn tuyệt đối `grade`, `diem_ky_sau`, `final_score` lọt vào $X$.
  - Hỗ trợ tham số `split_strategy` (`"random"` hoặc `"temporal"`).
  - Đảm bảo toàn bộ preprocessing (scaler, imputer) và feature selection (Mutual Information, RFE) chỉ fit trên tập TRAIN (đã đóng gói trong `Pipeline`/`ImbPipeline`).
  - Ghi nhận `data_source_type` và `split_strategy` để chuyển xuống lưu registry.
- **`RegressionTrainer.train_and_evaluate`**:
  - Áp dụng `canonicalize_columns` và `filter_leakage_features`.
  - Khi `target_col == 'diem_ky_sau'`: chặn tuyệt đối `final_score`, `xep_loai`, `grade` lọt vào $X$.
  - Bảo vệ `diem_ky_nay`: không tự động loại bỏ `diem_ky_nay` dù có tương quan cao (vì đây là biến dự báo hợp lệ đã biết tại thời điểm $t$).
  - Hỗ trợ tham số `split_strategy` (`"random"` hoặc `"temporal"`).
  - Preprocessing và feature selection chỉ fit trên TRAIN.

---

### Component 4: Model Service & Leakage Detection (`dss/services/model_service.py`)

#### [MODIFY] [model_service.py](file:///d:/KLTN/code/app/dss/services/model_service.py)
- Cập nhật `find_leaky_feature_cols`:
  - Tích hợp `get_leaky_target_columns` từ `target_utils.py`.
  - Tự động đánh dấu các alias/derived targets là leaky columns.
  - Loại trừ `diem_ky_nay` khỏi danh sách leaky columns dù tương quan cao.
- Cập nhật `run_training`:
  - Nhận diện `data_source_type` ("synthetic" vs "real") và `split_strategy` ("random" vs "temporal").
  - Chuyển tiếp các metadata này khi gọi `wh.save_model_training`.
- Cập nhật `compute_shap_local_explanation` & `compute_shap_summary`:
  - Đảm bảo danh sách feature đưa vào SHAP không chứa các cột leakage đã bị loại bỏ.
  - Hiển thị đúng các biến giải thích thực tế (`diem_ky_nay`, `ty_le_diem_danh`, `so_gio_hoc_tuan`,...).

---

### Component 5: Bootstrap Service (`dss/core/bootstrap_service.py`)

#### [MODIFY] [bootstrap_service.py](file:///d:/KLTN/code/app/dss/core/bootstrap_service.py)
- Trong `_detect_default_training_config`:
  - Ưu tiên tìm canonical targets (`diem_ky_sau`, `xep_loai`) trước legacy aliases.
  - Áp dụng `filter_leakage_features` để default features không chứa các cột rò rỉ.
  - Giữ lại `diem_ky_nay` trong danh sách features mặc định cho hồi quy.
  - Đánh dấu `data_source_type = "synthetic"` cho bootstrap ban đầu.

---

### Component 6: Warehouse & Model Registry Metadata (`dss/core/warehouse.py`)

#### [MODIFY] [warehouse.py](file:///d:/KLTN/code/app/dss/core/warehouse.py)
- Cập nhật `save_model_training`:
  - Lưu thêm các trường metadata:
    - `data_source_type`: `"synthetic"` hoặc `"real"`
    - `split_strategy`: `"random"` hoặc `"temporal"`
    - `prediction_horizon`: `"next_semester"`
  - Giữ nguyên cấu trúc hiện tại để tương thích 100% với Model Registry và các tests đã có.
- Cập nhật `save_dataset`:
  - Lưu trường `data_source_type` trong metadata dataset.

---

### Component 7: UI Tabs & Advisory Updates

#### [MODIFY] [ml_hub.py](file:///d:/KLTN/code/app/dss/tabs/ml_hub.py)
- Giao diện chọn Target & Feature:
  - Tự động loại bỏ các target-related/alias columns khỏi multiselect features.
  - Hiển thị nhãn rõ ràng: `Chế độ dữ liệu: Mô phỏng (Synthetic/Demo)` vs `Chế độ dữ liệu: Thực tế (Real)`.
  - Hiển thị huy hiệu/nhãn phân biệt kết quả đánh giá: `Metric mô phỏng (Simulation Metric)` vs `Metric thực tế (Real Evaluation Metric)`.
  - Thêm tùy chọn chiến lược chia dữ liệu: `Ngẫu nhiên (Random Split)` hoặc `Theo thời gian (Temporal Split)` khi phát hiện cột thời gian.
- Tab Dự đoán:
  - Phiếu nhập thông tin sinh viên chỉ hiển thị các features đầu vào hợp lệ tại thời điểm $t$, không cho phép nhập target hay alias của target.

#### [MODIFY] [advisory.py](file:///d:/KLTN/code/app/dss/tabs/advisory.py)
- Sửa cấu hình định hướng `ORIENTATIONS`:
  - Đổi `'diem_ky_sau'` trong `key_features` thành `'diem_ky_nay'` (kết quả học kỳ hiện tại đã biết của sinh viên).

#### [MODIFY] [home.py](file:///d:/KLTN/code/app/dss/tabs/home.py) & [dashboard.py](file:///d:/KLTN/code/app/dss/tabs/dashboard.py)
- Cập nhật thứ tự ưu tiên tìm cột điểm số và xếp loại: ưu tiên `diem_ky_sau` và `xep_loai` lên hàng đầu trước `final_score` và `grade`.

---

### Component 8: Test Suite Mới

#### [NEW] [test_target_leakage_and_modes.py](file:///d:/KLTN/code/app/tests/test_target_leakage_and_modes.py)
Triển khai toàn bộ 15 tests bắt buộc theo yêu cầu:
- **TEST 1**: Classification leakage (target = `xep_loai` -> `grade`, `diem_ky_sau`, `final_score` không có trong X).
- **TEST 2**: Regression leakage (target = `diem_ky_sau` -> `final_score`, `xep_loai`, `grade` không có trong X).
- **TEST 3**: Legitimate predictor (target = `diem_ky_sau` -> `diem_ky_nay` nằm trong X).
- **TEST 4**: Legacy classification dataset (input `grade` không có `xep_loai` -> canonicalize thành `xep_loai`).
- **TEST 5**: Legacy regression dataset (input `final_score` không có `diem_ky_sau` -> canonicalize thành `diem_ky_sau`).
- **TEST 6**: Duplicate aliases (`grade` & `xep_loai` giống nhau -> chỉ canonical được dùng trong ML).
- **TEST 7**: Classification alias conflict (`grade != xep_loai` -> warning/error rõ ràng).
- **TEST 8**: Regression alias conflict (`final_score != diem_ky_sau` -> warning/error rõ ràng).
- **TEST 9**: Real evaluation target (chế độ real: đọc từ dataset, không gọi synthetic formula).
- **TEST 10**: Missing future target (dataset real thiếu `diem_ky_sau` -> validation error, không tự sinh).
- **TEST 11**: Synthetic mode (chế độ demo/synthetic hoạt động bình thường, metadata đánh dấu `synthetic`).
- **TEST 12**: Classification boundaries (kiểm tra các mốc ranh giới của `score_to_xep_loai` / `pd.cut`).
- **TEST 13**: Preprocessing leakage (scaler/imputer/feature selector fit duy nhất trên training data).
- **TEST 14**: Registry metadata (lưu đúng `data_source_type`, `split_strategy`, `prediction_horizon`, `feature_cols`).
- **TEST 15**: Production prediction (dự đoán luôn resolve từ Model Registry, không lấy session state tùy tiện).

---

## Verification Plan

### Automated Tests
1. Chạy toàn bộ 15 tests mới:
   ```powershell
   D:\KLTN\code\.venv\Scripts\pytest.exe tests/test_target_leakage_and_modes.py -v
   ```
2. Chạy lại toàn bộ test suite hiện có để đảm bảo 100% backward compatibility:
   ```powershell
   D:\KLTN\code\.venv\Scripts\pytest.exe tests/test_auth_service.py tests/test_cache.py tests/test_lecturer_dashboard_overview.py tests/test_lecturer_home_dashboard_separation.py tests/test_llm_service.py tests/test_model_registry.py tests/test_prediction_source_of_truth.py tests/test_rag_service.py tests/test_rbac.py tests/test_session_isolation.py -v
   ```

### Manual / Integration Verification
1. Kiểm tra luồng Synthetic/Demo: Khởi chạy app hoặc gọi bootstrap, kiểm tra metadata `data_source_type == "synthetic"` và bảng chỉ số được dán nhãn Demo/Simulation.
2. Kiểm tra luồng Real/Evaluation: Thử tải dataset không có target kỳ sau -> hệ thống cảnh báo rõ ràng; thử tải dataset có observed target -> pipeline train trên $X_t$ để dự đoán $Y_{t+1}$ mà không có leakage.
3. Kiểm tra giải thích SHAP: Xác nhận biểu đồ SHAP chỉ giải thích các feature hợp lệ (`diem_ky_nay`, `ty_le_diem_danh`,...), hoàn toàn sạch bóng các cột leakage.
