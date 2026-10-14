# Silent Exception Audit — `except Exception: pass` (và biến thể) trong `app/dss`

Phiên: "FINAL PRODUCTION GAP CLOSURE" (2026-09-26), Phần 6. Quét bằng AST (không chỉ grep — phân tích cú pháp thật để bắt chính xác khối `except: pass` 1 dòng, gồm cả `except ImportError`/`except OSError`/`except (ValueError, TypeError)` một dòng). Tổng: **55 vị trí** trong `app/dss` (không tính `dss_old/`, `tests/`, `simulator/` — code không chạy trong hệ thống thật).

Mỗi vị trí đã được đọc trực tiếp (8-10 dòng ngữ cảnh xung quanh) — không phân loại chỉ từ tên hàm.

## Phân loại

- **P0** (security/data isolation/correctness nghiêm trọng): **0**
- **P1** (user-visible failure bị che giấu thành "thành công"/production reliability): **2** — **CẢ 2 ĐÃ SỬA trong phiên này** (commit `4cfc043`)
- **P2** (maintainability/observability — hành vi đúng nhưng thiếu log để chẩn đoán khi có sự cố thật): **2**
- **P3** (benign, có chủ đích, đã đọc kỹ và xác nhận không ảnh hưởng đúng-sai/bảo mật): **51**

## P1 — ĐÃ SỬA

| # | File:Line | Hàm | Vấn đề | Hành động |
|---|---|---|---|---|
| 1 | `dss/tabs/dashboard.py:246` | grade editor save handler | `st.session_state.show_success_message = "✅ Đã lưu..."` được gán **VÔ ĐIỀU KIỆN** ngay sau `try: wh.save_dataset(...) except Exception: pass` — nếu save thất bại thật (disk/serialize lỗi), người dùng vẫn thấy "Đã lưu" trong khi điểm chỉnh sửa chỉ tồn tại tạm trong phiên (`current_df` đã gán trước try, không phụ thuộc kết quả save) | Theo dõi `_save_ok` thật; `show_success_message` CHỈ gán khi `_save_ok`; thêm `show_error_message` trung thực + log exception khi thất bại. Commit `4cfc043` |
| 2 | `dss/tabs/warehouse_tab.py:69` | "Đồng bộ dữ liệu từ LMS (Giả lập)" button | Cùng mẫu lỗi: `show_success_message` gán sau khối try/except vô điều kiện | Chuyển `show_success_message` vào TRONG nhánh try thành công; nhánh except báo lỗi trung thực (dữ liệu vẫn dùng được trong phiên nhưng CHƯA lưu lâu dài). Commit `4cfc043` |

Thêm counterpart `show_error_message` (đối xứng với `show_success_message` có sẵn) vào `dss/main.py` để 2 fix trên có nơi hiển thị.

## P2 — Giữ nguyên hành vi, khuyến nghị thêm log (KHÔNG sửa trong phiên này — rủi ro thấp, không phải correctness bug)

| # | File:Line | Hàm | Vấn đề | Vì sao chỉ P2 (không phải P1) |
|---|---|---|---|---|
| 3 | `dss/services/model_service.py:677` | `predict_for_student` | Nếu `pipeline.predict(row_df)` raise (model corrupt, sklearn version mismatch, cột lệch kiểu...), lỗi bị nuốt và hàm rơi xuống nhánh "không có bản Production, dùng điểm hiện tại" — kết quả trả về vẫn có `source="observed"` ĐÚNG NGHĨA (không claim "model" giả), nhưng KHÔNG có log nào để phân biệt "thật sự không có Production" với "có Production nhưng bị lỗi khi predict" | Không tuyên bố sai (label `source` vẫn đúng loại), chỉ thiếu chẩn đoán — nếu muốn điều tra tại sao 1 model Production không được dùng, phải thêm log |
| 4 | `dss/core/warehouse.py:699` | `log_activity` | Ghi `activities.json` (nguồn cho "Hoạt động gần nhất") có thể lỗi thầm lặng; hàm vẫn trả về `activity_record['activity_id']` hợp lệ bất kể ghi file có thành công hay không | Không có `show_success_message` nào gắn với riêng hàm này claim "đã ghi log" — đây là audit trail phụ, không phải xác nhận hành động chính (hành động chính đã có nhánh xử lý thành công riêng ở nơi gọi) |

## P3 — Đã đọc, xác nhận benign (51 vị trí)

Nhóm theo mẫu hành vi lặp lại (không liệt kê riêng từng dòng nếu cùng 1 mẫu — file:line đầy đủ có trong phụ lục cuối):

1. **Cấu hình/thư viện tùy chọn khi thiếu (4 vị trí)**: `config.py:40` (dotenv), `config.py:69` (scipy warning filter), `data_helpers.py:350,379` (`balance_dataset` — SMOTE thư viện tùy chọn, fallback không cân bằng dữ liệu nếu thiếu, ĐÃ có cảnh báo riêng ở nơi khác trong pipeline). Thiếu thư viện tùy chọn → tính năng đó tắt, không crash, không claim sai.
2. **Trang trí biểu đồ Plotly (5 vị trí)**: `config.py:92,639,653` (nhãn dữ liệu/text trên cột) — nếu thất bại, biểu đồ vẫn hiển thị đúng, chỉ thiếu nhãn số trang trí.
3. **Parse số/ngày với danh sách cột ứng viên, thử cột kế tiếp khi lỗi (4 vị trí)**: `lms_connector.py:213`, `career_profile.py:97`, `learning_explainer.py:172`, tương tự — pattern "thử key A, nếu parse lỗi thì thử key B" — ĐÚNG THIẾT KẾ, không phải nuốt lỗi.
4. **Best-effort ghi audit/persistence PHỤ (không phải hành động chính) (7 vị trí)**: `lms_connector.py:449` (mirror SQLite phụ sau khi bản chính đã lưu), `llm_service.py:106` (token_tracker cho compare_ai), `models.py:1612` (`save_ai_consultation` — không chặn việc trả lời chat), `warehouse.py:916` (merge activity list, bỏ qua item lỗi), `ml_provenance.py:532` (git commit hash — provenance ghi "unknown" thay vì bịa), `admin_agent.py:106` (dọn `.tmp` file, bỏ qua file đã bị xóa bởi tiến trình khác), `bootstrap_service.py:89` (logging helper tự nó lỗi — last-resort no-op).
5. **Cosmetic/optional UI decoration, không claim "thành công" (13 vị trí)**: `eda.py` ×6 (biểu đồ từng cột trong vòng lặp — 1 cột lỗi không chặn các cột khác), `ml_hub.py` ×5 (giải mã nhãn hiển thị/hiển thị xác suất — dữ liệu dự đoán CHÍNH vẫn đúng, chỉ phần hiển thị phụ bị bỏ qua), `ai_advisor.py:1526` + `advisory.py:407` (nút xuất PDF — nếu lỗi, nút không hiện, không claim đã xuất).
6. **Chuẩn hóa giá trị/kiểu dữ liệu, lỗi → giá trị an toàn có ý nghĩa rõ ràng (5 vị trí)**: `model_service.py:793` (`safe_metric_value` — lỗi → NaN, đúng tên hàm), `warehouse.py:124` (`_sanitize_for_json` thử `.item()` rồi thử cách khác), `model_service.py:370,436` (gán `feature_names` cho SHAP — cosmetic, không đổi giá trị SHAP thật), `model_service.py:1062` (`find_leaky_feature_cols` — trả kết quả từng phần nếu 1 phép tính tương quan lỗi).
7. **Config file thiếu/hỏng → coi như "chưa cấu hình" (2 vị trí)**: `admin_ai_config.py:51` (JSON provider mặc định), `llm_gateway.py:350,384` (đọc secret/API key — trả `None`, nơi gọi đã xử lý "chưa có key" đúng đắn).
8. **Cleanup lỗi phụ trong khối except đã có log ở tầng ngoài (2 vị trí)**: `warehouse.py:97` (xóa file `.tmp` khi ghi atomic thất bại — bản thân lỗi ghi ĐÃ được `_logger.error(..., exc_info=True)` và `raise` lại ở tầng ngoài, khối pass chỉ là dọn dẹp phụ), `auth_service.py:173` (tương tự — outer handler log đầy đủ + `os.replace` atomic).
9. **Fit pipeline với tham số tối ưu tùy chọn, fallback về tham số mặc định nếu model không hỗ trợ (1 vị trí)**: `trainers.py:426`.
10. **Health-probe/kiểm tra thăm dò không chặn luồng chính (1 vị trí)**: `observability.py:91` (`record_operation` — ghi observability, không được phép làm hỏng luồng nghiệp vụ chính nếu bản thân việc ghi log lỗi).
11. **`feature_utils.py` — tính năng bổ trợ phân tích (2 vị trí)**: `:851` (feature importance bổ trợ từ RandomForest tạm thời), `:1018` (gợi ý "best model" — text mô tả, không phải giá trị dùng để quyết định gì).
12. **`model_registry.py:222` `evaluate_drift`**: đã tự ghi chú "Best-effort persistence only — result above is always returned regardless" — kết quả đánh giá drift LUÔN được trả về đúng (tính toán xong trước khối try/except này), khối try/except chỉ bọc việc GHI record vào DB, không ảnh hưởng giá trị trả về.
13. **`subscription_service.py:160` `check_entitlement`**: parse ngày hết hạn hợp đồng lỗi → im lặng bỏ qua (không tự động chuyển trạng thái EXPIRED). Đây là trường hợp CẦN LƯU Ý nhất trong nhóm P3 — về lý thuyết là "fail-open" (lỗi parse ngày khiến hệ thống KHÔNG khóa truy cập thay vì khóa) — nhưng: (a) dữ liệu `expires_str` đến từ cấu hình Admin nội bộ, không phải input người dùng ngoài; (b) hành vi fail-open ở đây tương đương "không parse được ngày → coi như chưa có hạn" — hợp lý hơn fail-closed (khóa nhầm toàn bộ trường học vì 1 lỗi định dạng ngày). Xếp P3 nhưng ghi chú riêng để cân nhắc lại nếu mô hình kinh doanh yêu cầu fail-closed nghiêm ngặt hơn.

## Phụ lục — danh sách đầy đủ 55 vị trí (file:line)

```
dss/config.py:40, 69, 92, 639, 653
dss/core/bootstrap_service.py:89
dss/core/data_helpers.py:350, 379
dss/core/feature_utils.py:851, 1018
dss/core/models.py:695, 1612
dss/core/observability.py:91
dss/core/trainers.py:426
dss/core/warehouse.py:97, 124, 699, 916
dss/services/admin_agent.py:106
dss/services/admin_ai_config.py:51
dss/services/auth_service.py:173
dss/services/career_ai_advisor.py:115
dss/services/career_profile.py:97
dss/services/learning_explainer.py:172
dss/services/llm_gateway.py:350, 384
dss/services/llm_service.py:106
dss/services/lms_connector.py:213, 449
dss/services/ml_provenance.py:532
dss/services/model_registry.py:222
dss/services/model_service.py:370, 436, 677 (P2), 793, 1062
dss/services/subscription_service.py:160
dss/tabs/admin_reports.py:30
dss/tabs/advisory.py:407
dss/tabs/ai_advisor.py:1526
dss/tabs/dashboard.py:246 (P1 — ĐÃ SỬA)
dss/tabs/eda.py:91, 108, 129, 151, 177, 225
dss/tabs/ml_hub.py:867, 1139, 1443, 1484, 1844
dss/tabs/warehouse_tab.py:69 (P1 — ĐÃ SỬA), 85
```

## Kết luận

Không có `except Exception: pass` nào trên đường CHÍNH của AI (H-1/H-2/H-3 đã xử lý riêng, không nằm trong danh sách này — `call_ai_provider`/`stream_generate` dùng try/except CÓ log + yield thông báo, không phải silent-pass), RAG (governance filtering fail-closed, không dùng try/except im lặng), hay RBAC/tenant isolation. 2/55 vị trí (P1) đúng là lỗi correctness ("success giả") và đã sửa. Phần còn lại là các mẫu phòng thủ hợp lý cho tính năng phụ/cosmetic/tùy chọn — không cần sửa hàng loạt (đúng cảnh báo trong đề bài: "Không sửa hàng loạt mù quáng").
