# EduDSS — Báo cáo kiểm thử hệ thống (bước 8)

> Ngày 22/11/2026. Chạy trên **máy phát triển** (Windows 11, 8 luồng CPU, 16 GB RAM, máy dùng chung với các
> dự án khác). Trình duyệt kiểm thử và app chạy chung một máy. Đây **không phải** máy chủ thật, nên các con số hiệu
> năng chỉ dùng để so sánh và tìm điểm nghẽn, không phải cam kết.
> Liên quan: [../requirements/ACCEPTANCE_CRITERIA.md](../requirements/ACCEPTANCE_CRITERIA.md) ·
> [../security/SECURITY_CHECKLIST.md](../security/SECURITY_CHECKLIST.md) ·
> [../operations/BACKUP_RECOVERY_RUNBOOK.md](../operations/BACKUP_RECOVERY_RUNBOOK.md)

## 1. Tóm tắt

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| Bộ test tự động (không cần CSDL) | ✅ Đạt | Lỗi duy nhất còn lại: thiếu `prometheus_client` trên máy dev (đã biết) |
| Test giao diện (Playwright) | ✅ 52/52 | Chạy với các thư viện đã vá ở bước 7 |
| Test trên **PostgreSQL thật có RLS** | ✅ Đạt | Trước đây luôn bị bỏ qua vì máy chưa có CSDL. Lần này chạy trên container cô lập |
| Xuất/xoá dữ liệu sinh viên trên PostgreSQL | ✅ Đạt | `tests/test_c1_data_lifecycle.py` (4 test) |
| Đồng ý xử lý dữ liệu + giảng viên theo lớp dưới RLS | ✅ Đạt | Test mới, không lẫn dữ liệu giữa 2 trường |
| Sao lưu → kiểm tra → khôi phục sang CSDL mới | ✅ Đạt | Kể cả RLS, pgvector, đăng nhập trên bản khôi phục |
| Thời gian khôi phục cỡ thí điểm | ✅ 17 giây | CSDL 124 MB; mục tiêu tạm RTO 4 giờ |
| 50 phiên trình duyệt đồng thời — lỗi ≤ 1% | ✅ 0% lỗi | 50/50 phiên hoàn tất |
| 50 phiên — thời gian phản hồi | 🔴 Chậm | Đăng nhập p95 88–117 giây khi 50 người đăng nhập **cùng một lúc**. Xem §4 |
| Điện thoại thật | ⏳ Chưa làm | Cần chủ dự án tự thử, xem §5 |

## 2. Test trên PostgreSQL cô lập

- **Môi trường:** container `pgvector/pgvector:pg16` riêng ở cổng 55611, tạo riêng cho bước này. Không đụng container
  `edudss-postgres` của dự án khác. Mật khẩu sinh ngẫu nhiên, không ghi vào repo.
- **Migration:** `alembic upgrade head` lên `d2e3a6102601`; `ops.migration_check verify` báo `compatible: true`.
- **Kết quả:** 109 test cần PostgreSQL đạt ngay lần đầu, gồm workstream A–D, onboarding, nền tảng lớp học, chống SQL
  injection, đồng thời và lịch sử kế hoạch. 12 test RLS/vòng đời dữ liệu đạt sau 2 sửa:
  - Lần chạy đầu truyền sai biến môi trường. Lỗi ở phía người chạy test, không phải lỗi code.
  - **Lỗi thật trong test** `tests/test_db_row_level_security.py`: khi dựng lại CSDL, test bỏ sót các bảng `lp_*`
    (trang Lớp học, thêm về sau), nên lần migrate lại thất bại. Đã sửa: xoá cả các bảng đó bằng `DROP ... CASCADE`.
    Test này chưa từng chạy trên CSDL thật kể từ khi có bảng `lp_*`.
- **Test mới:** `test_consent_and_lecturer_scope_work_under_postgres_rls`, chạy bằng role ứng dụng không phải superuser:
  - Giảng viên `gv_a` được gán lớp ở 2 trường; khi đăng nhập ở trường 1 chỉ thấy sinh viên lớp của trường 1.
  - Đồng ý ở trường 1 không được tính cho trường 2.

## 3. Sao lưu và khôi phục

| Lần chạy | Dữ liệu | Sao lưu | Kiểm tra | Khôi phục | So sánh |
|---|---|---|---|---|---|
| `tests/test_backup_recovery_integration.py` | Dữ liệu mẫu của test | ✅ | ✅ | ✅ | RLS, pgvector, đăng nhập qua `auth_service` trên bản khôi phục |
| Cỡ thí điểm | 10.000 sinh viên, 200.000 bản ghi điểm, 50.000 lượt tư vấn (CSDL 124 MB) | 2 giây (file 4,2 MB) | 1 giây | 17 giây | Số dòng 3 bảng khớp, cùng bản migration, 50 bảng FORCE RLS ở cả hai bên |

**Chưa phủ (để bước 9):**
- 8 kho dữ liệu dạng tệp: mô hình, bộ dữ liệu, tệp CMS. `ops/non_db_recovery.py` mới có test đơn vị, chưa diễn
  tập gộp.
- Lịch sao lưu tự động, bản sao ngoài máy chủ, mã hoá.

RPO 24 giờ / RTO 4 giờ vẫn là **mức tạm**, chờ chủ dự án chốt (AC-BM-13).

## 4. Thử tải bằng trình duyệt thật (AC-HN-04)

**Kịch bản:** `tools/browser_load_test.py` (Playwright). Mỗi phiên là một context riêng, mỗi phiên một tài khoản sinh
viên khác nhau. Mỗi phiên làm 3 việc: mở trang đăng nhập → đăng nhập → chờ Trang chủ hiện "Xin chào" → bấm sang
"Trợ lý AI". **Tất cả phiên bắt đầu cùng một giây** (tình huống xấu nhất: cả lớp đăng nhập cùng lúc).
App chạy chế độ demo dữ liệu mô phỏng 20.000 sinh viên.

| Lần | Phiên | Lỗi | Đăng nhập → Trang chủ (p50 / p95) | Mở trang đăng nhập p95 | Chuyển trang p95 |
|---|---|---|---|---|---|
| Trước khi sửa, tài khoản tự tạo lần đầu | 10 | 0 | 25,6 / 29,7 s | 7,0 s | 1,7 s |
| Trước khi sửa, tài khoản tự tạo lần đầu | 25 | 0 | 118,7 / 134,9 s | 163,4 s | 16,1 s |
| Sau khi sửa, tài khoản tự tạo lần đầu | 25 | 0 | 80,9 / 94,0 s | 32,5 s | 5,2 s |
| Sau khi sửa, tài khoản có sẵn | 10 | 0 | 14,4 / 15,7 s | 7,5 s | — |
| Sau khi sửa, tài khoản có sẵn | 25 | 0 | 25,1 / 42,3 s | 68,5 s | 6,3 s |
| Sau khi sửa, tài khoản có sẵn | 50 | 0 | 57,5–77,6 / 87,9–116,7 s | 126–144 s | 4,3 s |

**Điểm nghẽn tìm được và đã sửa** (cProfile trên một phiên):
1. **Mỗi lần đăng nhập, app đọc lại file mô hình `.joblib` và băm lại SHA-256** (khoảng 1,6 giây CPU), dù đã có
   bộ nhớ đệm dùng chung ở `model_registry`. Đã chuyển `bootstrap_service` sang dùng bộ nhớ đệm đó. Mô hình vẫn được
   kiểm tra chữ ký ở lần tải đầu; khi Admin đổi bản Production thì khoá đệm đổi theo.
2. **SHAP của Trang chủ Sinh viên được tính lại ở mỗi lần trang vẽ lại** (khoảng 1 giây). Đã lưu kết quả theo
   (bản mô hình, dòng dữ liệu, dữ liệu nền).
3. Kết quả đo: lần chạy đầu của một phiên mới giảm từ 6,2 xuống 1,7 giây; mỗi lần vẽ lại giảm từ 2,2 xuống 0,3 giây.
   Test: `test_login_reuses_the_cross_session_artifact_cache`, `test_student_home_shap_is_cached_per_model_version`.

**Giới hạn còn lại (chưa sửa, cần chủ dự án quyết):**
- Sau khi sửa, một phiên vẫn tốn **3,4–4,1 giây CPU** của tiến trình app (đo bằng CPU của tiến trình, 10 và 50 phiên),
  gồm cả băm mật khẩu PBKDF2 600.000 vòng.
- Streamlit phục vụ mọi người bằng **một tiến trình Python**. Phần lớn công việc tranh nhau một khoá chung (GIL), nên
  tiến trình chỉ dùng được khoảng 1,25 nhân. 50 phiên tốn 207 giây CPU, nên 50 người đăng nhập cùng một giây sẽ mất
  khoảng 3 phút mới phục vụ xong. **Máy mạnh hơn không giải quyết được**, vì giới hạn nằm ở số tiến trình.
- Một phần độ trễ đo được là do chính máy kiểm thử quá tải: 50 trình duyệt chiếm khoảng 4–6 GB RAM, CPU 93–100%. Vì vậy
  "mở trang đăng nhập 126 giây" bị đẩy cao hơn thực tế.
- Tài khoản tự tạo lần đầu (chỉ có ở bản demo) chậm hơn, vì băm mật khẩu trong khoá file `users.json`. Production tắt
  chức năng tự tạo nên không bị ảnh hưởng.

**Đề xuất (cần chủ dự án duyệt, vì đổi cách triển khai):**
- (a) **Chạy 3–4 tiến trình Streamlit sau Caddy, giữ phiên cố định (sticky session)**, trên máy chủ 4 nhân.
  Ước tính nâng sức chứa lên gấp 3–4 lần. Phải đo lại ở bước 9.
  → **Đã duyệt và làm ở bước 9 (22/11/2026):** `docs/operations/SCALING.md`.
- (b) Chỉ tính SHAP khi sinh viên mở phần "Yếu tố ảnh hưởng", để giảm thêm khoảng 1 giây ở lần đầu.
- (c) Chốt ngưỡng AC-HN-04. Đề xuất: **khi 50 người dùng đồng thời thao tác bình thường** (không phải cùng đăng
  nhập một giây), p95 chuyển trang ≤ 3 giây và đăng nhập ≤ 10 giây.

## 5. Việc chủ dự án cần tự làm: thử trên điện thoại thật

Máy kiểm thử chỉ giả lập được màn hình điện thoại (test e2e ở bề ngang 360–414 px đã đạt ở bước 6). Cần một lần thử
trên máy thật:

1. Mở app trên Android (Chrome) và iPhone (Safari) qua mạng của trường.
2. Đăng nhập bằng tài khoản sinh viên → màn hình đồng ý hiện đủ chữ, bấm được nút.
3. Xem Trang chủ, kết quả dự đoán, Trợ lý AI; xoay ngang và dọc; không có thanh cuộn ngang.
4. Để yên 30 phút → thao tác lại → phải bị đăng xuất.
5. Ghi lại: máy, trình duyệt, lỗi nếu có, kèm ảnh chụp màn hình.

## 6. Cách chạy lại

```sh
# PostgreSQL cô lập (mật khẩu tự sinh, đặt qua biến môi trường)
docker run -d --name edudss-step8-pg -p 127.0.0.1:55611:5432 \
  -v edudss_step8_pgdata:/var/lib/postgresql/data -v $PWD/postgres-init:/docker-entrypoint-initdb.d:ro \
  -e POSTGRES_DB=edudss_step8 -e POSTGRES_USER=edu_owner -e POSTGRES_PASSWORD=... \
  -e POSTGRES_APP_USER=edu_app -e POSTGRES_APP_PASSWORD=... pgvector/pgvector:pg16
DATABASE_URL=<owner-url> python -m alembic upgrade head
DATABASE_URL=<owner-url> DATABASE_APP_ROLE_URL=<app-url> pytest tests/test_db_row_level_security.py tests/test_c1_data_lifecycle.py
EDUDSS_PLATFORM_TEST_APP_URL=<app-url> EDUDSS_PLATFORM_TEST_OWNER_URL=<owner-url> pytest tests/test_security_step7_group_b.py tests/test_stage23_platform_postgres.py
PHASE13_SOURCE_URL=<owner-url nguồn sạch> PHASE13_RESTORE_URL=<owner-url CSDL rỗng> PHASE13_APP_ROLE_URL=<app-url nguồn> \
  PHASE13_DOCKER_CONTAINER=edudss-step8-pg pytest tests/test_backup_recovery_integration.py
```

Thử tải: chạy app rồi `python tools/browser_load_test.py http://localhost:8599 50 1500`. Chạy một lần với chỉ số bắt đầu mới để tạo tài khoản, sau đó chạy lại cùng chỉ số để đo với tài khoản có sẵn.
