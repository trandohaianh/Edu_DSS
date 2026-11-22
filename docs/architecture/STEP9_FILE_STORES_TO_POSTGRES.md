# Thiết kế: đưa các kho dữ liệu dạng tệp vào PostgreSQL (bước 9, BẢN NHÁP chờ duyệt)

Ngày 22/11/2026. Trạng thái: **chờ chủ dự án duyệt, chưa viết code.**

## 1. Vì sao cần

Production hiện dùng PostgreSQL cho tài khoản, kế hoạch học tập, nền tảng, CMS và RAG. Các kho còn lại vẫn là tệp
JSON trong volume `appdata`, và gặp 3 vấn đề:

1. **Yêu cầu xoá dữ liệu không phủ hết.** `dss/services/data_lifecycle.py` (tải bản sao, xoá, hết hạn) chỉ làm việc
   với PostgreSQL. Lịch sử dự đoán, phiên tư vấn, nhật ký hoạt động và nhật ký token AI của sinh viên nằm trong tệp
   nên không bị xoá. Đây là mục "Trung bình" còn mở ở `docs/security/SECURITY_CHECKLIST.md` dòng 57.
2. **Chỉ chạy được trên một máy chủ.** Khoá tệp (`dss/core/file_lock.py`) chỉ đúng khi mọi bản app nằm trên cùng
   một máy.
3. **Sao lưu tách làm hai phần** (CSDL và tệp), nên phải khôi phục cả hai của cùng một ngày.

## 2. Hiện trạng (khảo sát code ngày 22/11/2026)

Code **đã có sẵn** bảng PostgreSQL (đều có RLS) và repository cho 8 kho. Production chưa bật kho nào trong số đó.
Bật lên thì PostgreSQL trở thành nơi lưu duy nhất (không ghi song song).

| Kho | Tệp hiện tại | Bảng PG | Bật được ngay? | Thiếu gì |
|---|---|---|---|---|
| Cấu hình AI của Admin | `ai_default_provider.json` | `admin_ai_config` | **Có** | Không thấy thiếu |
| Thuê bao | `subscription.json` | `subscriptions`, `quota_usage` | **Có, nhưng đổi hành vi** | Ở chế độ PG, hạn mức số lượt gọi AI/tháng của trường **bắt đầu được áp dụng** (`subscription_service.py:177-186`) |
| Dữ liệu học vụ (từ LMS) | không có tệp | `students`, `courses`, `grades`… | **Có** | Chỉ ghi thêm, giao diện vẫn đọc bộ dữ liệu dạng tệp. Bật lên thì bảng `students` có dữ liệu, giúp 2 kho dưới tìm được sinh viên |
| Nguồn gốc mô hình | luôn là tệp | `model_versions`, `drift_evaluations`… | **Có** | Chỉ là bản sao để tra cứu, lỗi thì bỏ qua. Tệp vẫn là bản chính |
| Nhật ký hoạt động | `history/activity_history.json` | `activity_logs` | Cần sửa nhỏ | Ghi không kèm `user_id` (`warehouse.py:754-759`), nên xoá theo sinh viên không tìm thấy dòng nào |
| Nhật ký token AI | `ai_token_usage.json` | `ai_token_usage` | Cần sửa nhỏ | (1) Mất 3 trường `cache_hit`, `usage_source`, `thinking_tokens`. (2) Mỗi lần kiểm trần chi phí đọc **toàn bộ** bảng, không giới hạn (tệp giới hạn 50.000 dòng). (3) Mã người dùng lưu dạng gốc, còn bộ xoá dữ liệu tìm theo bí danh, nên không khớp |
| Lịch sử dự đoán | `history/prediction_history.json` | `predictions` | **Chưa** | Mọi trang đọc chỉ đọc tệp (`dashboard.py:69`, `warehouse_tab.py:652`, RAG `warehouse.py:973`), bật PG thì các trang này trống. Mất tên mô hình và xác suất. Mất mã SV nếu SV chưa có trong `students` |
| Phiên tư vấn | `history/advisor_history.json` | `consultations` | **Chưa** | Thiếu cột người tư vấn (`performed_by`, `performed_by_role`), làm hỏng AC-GV-10. Mất 5 trường: GPA dự đoán, điểm yếu, tài liệu tham khảo, mô hình nhúng, metadata. 6 trang chỉ đọc tệp. Cùng lỗi mã SV |

Kho **chưa có** bản PostgreSQL mà chứa dữ liệu sinh viên:
- `cms/interaction_log.json`, `cms/quiz_review_queue.json`, `cms/misconception_records.json`: tương tác học bài, gắn
  bí danh sinh viên.
- Bộ dữ liệu tải lên (`raw_data/`, `processed_data/`, `training_data/`…): bảng điểm, chuyên cần.

## 3. Đề xuất: 3 đợt, mỗi đợt tự kiểm được

### Đợt A: bật 4 kho sẵn sàng (khoảng nửa ngày)
- Bật `ADMIN_AI_CONFIG`, `SUBSCRIPTION`, `ACADEMIC`, `ML_PROVENANCE` trong `docker-compose.prod.yml`.
- Lệnh chuyển dữ liệu cũ (`ops/migrate_file_stores.py`), dùng lại các hàm `import_from_local_history` sẵn có:
  - mặc định chỉ đếm, không ghi;
  - có cờ `--execute` mới ghi;
  - không xoá tệp cũ.
- **Quyết định cần bạn:** bật thuê bao thì hạn mức lượt gọi AI/tháng bắt đầu có hiệu lực. Mức mặc định đặt bao
  nhiêu? Đề xuất: lấy theo trần chi phí 5 USD/tháng đã chốt.

### Đợt B: sửa 2 kho cần sửa nhỏ (khoảng nửa ngày)
- Hoạt động: ghi kèm người thực hiện.
- Token AI:
  - thêm 3 cột (migration chỉ thêm cột, không xoá gì);
  - kiểm trần chi phí bằng câu lệnh tính tổng theo ngày/tháng, không đọc cả bảng;
  - lưu bí danh để bộ xoá dữ liệu tìm được.
- Test mới chạy trên PostgreSQL thật (container tạm như bước 8).

### Đợt C: dự đoán + tư vấn (khoảng 1 ngày)
- Migration thêm cột cho `consultations` (người tư vấn, vai trò, các trường đang mất) và `predictions` (tên mô hình,
  xác suất). Giữ mã SV dạng chữ khi SV chưa có trong `students`.
- Thêm hàm đọc từ PG cho `get_history("prediction")` và `get_history("advisor")`, để 8 trang đang đọc tệp chuyển sang
  PG mà không phải sửa từng trang.
- Bộ xoá dữ liệu phủ thêm 2 kho này. Test AC-GV-10 chạy lại ở chế độ PG.

### Chưa làm trong lần này (đề xuất để sau)
- 3 kho CMS chưa có bảng PG, và bộ dữ liệu tải lên. Cần thiết kế bảng mới, nên tách thành một việc riêng.

## 4. Rủi ro và cách quay lại
- Mỗi đợt là một biến môi trường. Muốn quay lại thì đặt lại `local`, tệp cũ vẫn còn vì lệnh chuyển không xoá tệp.
- Migration chỉ **thêm** cột hoặc bảng (kiểu expand/contract, `RELEASE_PROCESS.md` §7). Không đổi tên, không xoá.
- Trước khi triển khai mỗi đợt: sao lưu và diễn tập khôi phục (`scheduled_backup.sh`, `restore_daily.sh`).

## 5. Cách nghiệm thu
- Bộ test hiện có đạt.
- Test mới chạy trên PostgreSQL thật.
- Diễn tập "xoá dữ liệu một sinh viên" tìm thấy và xoá được dòng ở mọi kho đã chuyển.
- Các trang Lịch sử tư vấn, Dashboard, Báo cáo hiện đủ dữ liệu như trước.

## 6. Câu hỏi cho chủ dự án
1. Duyệt cả 3 đợt, hay chỉ đợt A + B trước?
2. Hạn mức lượt gọi AI/tháng mặc định cho một trường khi bật thuê bao?
3. Bản Streamlit là portfolio công khai, còn bản đem bán là SaaS (FastAPI + Next.js). Có muốn dồn công sức "production
   thật" sang bản SaaS thay vì bản này không?
