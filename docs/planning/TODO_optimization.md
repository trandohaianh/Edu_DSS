# TODO: Tối ưu hóa hệ thống hỗ trợ học tập cá nhân hóa

## Mục tiêu
- Cải thiện độ chính xác mô hình, cross-validation, kỹ thuật đặc trưng, và tích hợp AI cho gợi ý
- Thêm phát hiện outlier, PCA, XGBoost, K-fold CV, Neural Collaborative Filtering

## Các bước thực hiện

### 1. Cải thiện tiền xử lý dữ liệu
- [ ] Thêm phát hiện outlier (dựa trên boxplot) trong data_generation.py
- [ ] Thêm kiểm tra tương quan trong data_generation.py
- [ ] Thêm PCA để giảm chiều đặc trưng trong model_training.py

### 2. Cải thiện huấn luyện mô hình
- [ ] Tích hợp XGBoost vào ensemble trong model_training.py
- [ ] Triển khai K-fold CV (5-fold) thay vì cv=3 trong model_training.py
- [ ] Thêm metrics đánh giá mô hình nâng cao trong model_training.py

### 3. Kỹ thuật đặc trưng nâng cao
- [ ] Sử dụng AI để tạo đặc trưng dựa trên clustering trong data_generation.py
- [ ] Thêm thành phần PCA vào feature list trong model_training.py

### 4. Nâng cao gợi ý với AI
- [ ] Triển khai Neural Collaborative Filtering trong utils.py
- [ ] Thêm reinforcement learning để điều chỉnh gợi ý dựa trên phản hồi trong utils.py

### 5. Cấu trúc module
- [ ] Tổ chức thành module: Tiền xử lý dữ liệu, Dự đoán & Phân loại, Hệ thống gợi ý, Dashboard phân tích
- [ ] Cập nhật final_personalized_learning_app.py để tích hợp modules

### 6. Dashboard phân tích
- [ ] Thêm tab phân tích với trực quan hóa (outlier, tương quan, feature importance) trong ui_components.py

## Các bước tiếp theo sau khi hoàn thành
- [ ] Test mô hình cải thiện để tăng độ chính xác
- [ ] Xác thực gợi ý với phản hồi người dùng
- [ ] Cài đặt dependencies (xgboost, tensorflow)

## Trạng thái: Đang thực hiện
