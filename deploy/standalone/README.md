# Triển khai độc lập có HTTPS riêng

Thư mục này chạy EduDSS **một mình** trên một máy chủ: một container ứng dụng (Streamlit) và một
container Caddy riêng làm reverse proxy, tự xin chứng chỉ HTTPS. Không cần và không dùng Caddy,
mạng `edge` hay bất kỳ thành phần nào của dự án khác (FieldOps, Telecom).

```
Internet ─80/443─▶ caddy (TLS tự động, security header, WebSocket) ─▶ app:8501 (Streamlit)
                                                                 └─▶ app:8081/metrics (Bearer token)
```

Chỉ `caddy` publish cổng ra host; `app` không có `ports:`.

## Yêu cầu

- Docker Engine + Docker Compose v2.24 trở lên (dùng `env_file.required`).
- Một tên miền có bản ghi A/AAAA trỏ về IP máy chủ; cổng 80 và 443 mở ra Internet
  (Let's Encrypt cần một trong hai để xác minh).
- RAM: app giới hạn 3 GB (PyTorch + mô hình embedding).

## Chạy

```bash
cd deploy/standalone
cp .env.example .env
# Sửa .env: APP_DOMAIN, ACME_EMAIL, EDUDSS_PUBLIC_URL=https://<APP_DOMAIN>,
# sinh bí mật:  openssl rand -hex 32  (cookie),  openssl rand -hex 12  (mật khẩu admin)
docker compose up -d --build
docker compose ps                       # app phải "healthy" thì caddy mới khởi động
bash smoke.sh "https://<APP_DOMAIN>"
```

Pipeline vận hành (KPI theo giờ, chất lượng dữ liệu, backup kèm diễn tập khôi phục) là tuỳ chọn:

```bash
docker compose --profile worker up -d
```

## Thử trên máy cá nhân (chứng chỉ nội bộ)

Với `APP_DOMAIN=edudss.localhost`, Caddy tự dùng CA nội bộ (tương đương `tls internal`), không gọi
ACME. Đổi cổng nếu 80/443 đang bận:

```bash
cat > .env <<'ENV'
COMPOSE_PROJECT_NAME=edudss-standalone-test
APP_DOMAIN=edudss.localhost
ACME_EMAIL=ops@example.org
HTTP_PORT=8080
HTTPS_PORT=8443
ENV
docker compose up -d --build
curl -k --resolve edudss.localhost:8443:127.0.0.1 https://edudss.localhost:8443/_stcore/health   # -> ok
docker compose down -v
```

## Ghi chú bảo mật

- Header: HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, CSP; header `Server` bị xoá.
- WebSocket `/_stcore/stream` được Caddy chuyển tiếp tự động; `stream_close_delay 5m` giữ phiên
  người dùng khi reload cấu hình.
- `.env` bị `.gitignore` chặn (`deploy/**/*.env`, `.env`). `.env.example` không chứa bí mật.
- Đây là bản **dữ liệu mô phỏng** (`EDUDSS_PUBLIC_DEMO=1`). Bản cho một trường thật dùng
  PostgreSQL + RLS và image ký số: xem `deploy/production/`.
