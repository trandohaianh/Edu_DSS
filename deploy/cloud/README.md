# EduDSS — bản demo công khai miễn phí (chung VM với FieldOps và Telecom)

> **Muốn EduDSS tự có HTTPS, không dùng chung Caddy với dự án khác?** Dùng
> [`deploy/standalone/`](../standalone/README.md): app + Caddy riêng, mạng riêng, chứng chỉ tự động.
> Thư mục này giữ cách cũ (nối vào Caddy của FieldOps qua mạng `edge`).

Đây là bản **demo trên dữ liệu mô phỏng** để ai cũng mở được. Bản triển khai cho một trường thật
(PostgreSQL + RLS, image ký số, phê duyệt production) nằm ở `deploy/production/`, không thay đổi.

| Vai trò | Cách vào | Thấy gì |
|---|---|---|
| Sinh viên | **Đăng nhập với Google** → hệ thống cấp 1 sinh viên mô phỏng riêng (SVxxx) | Điểm, rủi ro, dự đoán của *chính mình*, nhóm học tập, trợ lý AI, lịch sử tư vấn |
| Giảng viên | Tài khoản do Admin tạo (mật khẩu hoặc Google nếu đã gắn email) | Tổng quan lớp, dashboard, huấn luyện & dự đoán, phân cụm, duyệt tài liệu |
| Admin | `EDUDSS_BOOTSTRAP_ADMIN_*` trong `.env` (hoặc Google với `EDUDSS_BOOTSTRAP_ADMIN_EMAIL`) | Người dùng (tạo/sửa/khoá, gắn email Google), cấu hình AI, báo cáo & giám sát, chi phí, pipeline |

Chế độ `EDUDSS_PUBLIC_DEMO=1` tắt mọi lối tắt: không có tài khoản `admin/admin123` hay
`giangvien/gv123`, không đăng nhập kiểu `SV001/SV001123`, không hộp "tài khoản dùng thử".

## Cài lên VM (~30 phút, phần lớn là build image trên ARM)

Yêu cầu: VM Oracle đã cài FieldOps theo hướng dẫn của repo FieldOps. EduDSS dùng chung Docker, mạng
`edge` và Caddy HTTPS; nếu VM chưa có FieldOps, script tự chạy một Caddy riêng.

1. **DuckDNS**: tạo thêm 1 subdomain, VD `edudss-demo`, trỏ về IP của VM.
2. **Google OAuth** (console.cloud.google.com → APIs & Services → Credentials): dùng client
   "Web application" của FieldOps hoặc tạo mới, thêm *Authorized redirect URI*
   `https://edudss-demo.duckdns.org/oauth2callback`. Ghi lại Client ID và Client secret.
3. Trên VM:
   ```bash
   git clone <repo> ~/edudss && cd ~/edudss && git checkout fullstack/edudss-production
   bash app/deploy/cloud/setup.sh      # lần 1: tạo .env, tự sinh mật khẩu admin, cookie secret, metrics token
   nano app/deploy/cloud/.env          # điền EDUDSS_DOMAIN, EDUDSS_GOOGLE_CLIENT_ID/SECRET, EDUDSS_BOOTSTRAP_ADMIN_EMAIL
   bash app/deploy/cloud/setup.sh      # lần 2: build, chạy app + worker, nối Caddy, smoke test
   ```
4. Mở `https://edudss-demo.duckdns.org`, đăng nhập Admin, vào **Người dùng** để tạo tài khoản
   giảng viên và gắn email Google cho họ.

RAM: app giới hạn 3 GB (PyTorch + mô hình embedding), worker 1,5 GB. VM free có 12 GB, đủ chạy chung
cả 3 dự án. Dữ liệu (tài khoản, kho dữ liệu, mô hình, nhật ký token, backup) nằm trong volume
`edudss_data`.

## Pipeline dữ liệu (container `worker`)

`python -m ops.pipeline --schedule` chạy:
- **Mỗi giờ:** KPI — tài khoản theo vai trò, số lượt/token/USD AI hôm nay và trong tháng, tỉ lệ token
  do provider đếm, chi phí trên mỗi người dùng AI.
- **Hằng ngày lúc `EDUDSS_PIPELINE_DAILY_AT` (UTC):**
  - Chất lượng dữ liệu: trùng mã, thiếu dữ liệu, ngoài miền giá trị, drift PSI so với dữ liệu tham chiếu.
  - Backup kèm **diễn tập khôi phục**: giải nén vào thư mục tạm và kiểm lại SHA-256 từng tệp.
  - Dọn backup cũ hơn `EDUDSS_BACKUP_KEEP_DAYS`.

Chạy tay: `docker compose exec worker python -m ops.pipeline run all`. Kết quả cũng hiện ở
**Báo cáo & giám sát → Pipeline vận hành**, nơi Admin bấm chạy ngay được.

## Monitoring (Grafana Cloud — dùng chung stack với 2 dự án kia)

- **Connections → Metrics Endpoint**: URL `https://<domain>/metrics`, xác thực Bearer bằng
  `EDUDSS_METRICS_TOKEN`. Caddy chỉ mở đường `/metrics` của cổng health, các đường khác vẫn kín.
- **Import dashboard**: `monitoring/grafana/edudss-production.json` (đăng nhập, lượt dùng theo vai trò,
  token/USD theo model, cache hit, p95 thao tác, trạng thái pipeline, backup, drift).
- **Cảnh báo**: `monitoring/alerts/edudss-rules.yml` có 12 rule. Ví dụ: app chết, provider AI lỗi,
  80% ngân sách AI, dò mật khẩu, backup trễ hoặc diễn tập khôi phục thất bại, worker ngừng, dữ liệu
  lỗi hoặc drift.

## Chi phí

- **AI:** token lấy từ `usage_metadata`/`usage` thật của Gemini, Groq, OpenAI (gồm cả token suy nghĩ),
  nhân với bảng giá trong `dss/services/token_tracker.py`. Ghi đè giá bằng `EDUDSS_LLM_PRICING_JSON`
  khi Google đổi giá các model `-latest`.
- **Hạ tầng:** Admin nhập tay theo tháng ở **Báo cáo & giám sát → Tổng chi phí tháng này**. Gói free
  ghi $0; VM chia 3 dự án thì ghi phần chia.

## Cập nhật

Workflow `edudss-demo-deploy.yml` chạy khi CI "EduDSS full-stack" xanh trên `main`, cần các secret
`DEMO_DEPLOY_HOST/USER/SSH_KEY`. Có thể chạy tay `bash app/deploy/cloud/deploy.sh`. Thứ tự:
backup → kéo code → build → chạy lại → smoke test.
