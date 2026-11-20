# EduDSS — Hệ thống hỗ trợ ra quyết định cho giáo dục

EduDSS là ứng dụng web (Streamlit) giúp giảng viên, cố vấn học tập và nhà trường **phát hiện sớm
sinh viên có nguy cơ** và tư vấn học tập/nghề nghiệp:

- Phân tích dữ liệu học tập (EDA), dashboard lớp học, phân cụm sinh viên.
- Huấn luyện và so sánh mô hình học máy (phân loại xếp loại, hồi quy điểm), giải thích bằng SHAP,
  chọn mô hình bằng F1 hoặc PR-AUC khi lớp thiểu số quá ít mẫu.
- Kho mô hình có vòng đời Candidate → Production → Archived, không tự động lên Production.
- Trợ lý AI tư vấn có định tuyến 3 tầng, RAG trên tài liệu bài giảng/quy chế, ghi vết quyết định.
- Phân quyền Admin / Giảng viên / Sinh viên, đăng nhập Google, bút danh hoá dữ liệu cá nhân.

Phiên bản: xem tệp `VERSION`.

> **Giới hạn quan trọng:** dữ liệu đi kèm repo là **dữ liệu mô phỏng**. Kết quả mô hình trên dữ liệu
> này không phản ánh sinh viên thật. Tích hợp LMS/SIS/CMS thật của một trường chưa được chứng minh
> ngoài môi trường mô phỏng (xem [Giới hạn](#giới-hạn)).

---

## Mục lục

1. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
2. [Chạy nhanh trên máy](#chạy-nhanh-trên-máy)
3. [Docker](#docker)
4. [Triển khai độc lập có HTTPS](#triển-khai-độc-lập-có-https)
5. [Biến môi trường](#biến-môi-trường)
6. [Lint, format, kiểm thử](#lint-format-kiểm-thử)
7. [Quy ước](#quy-ước)
8. [Giới hạn](#giới-hạn)

---

## Cấu trúc thư mục

```
.
├── run_dss.py              # Điểm vào: streamlit run run_dss.py
├── dss/                    # Mã ứng dụng
│   ├── main.py             #   Khung ứng dụng: đăng nhập, điều hướng, gọi các tab
│   ├── tabs/               #   FRONTEND  – mỗi trang giao diện Streamlit một module
│   ├── styles/ assets/     #   FRONTEND  – CSS, ảnh, tài nguyên giao diện
│   ├── services/           #   BACKEND   – nghiệp vụ: xác thực, AI/RAG, mô hình, báo cáo, LMS
│   ├── core/               #   BACKEND   – lõi ML & dữ liệu: huấn luyện, kho dữ liệu, health, metrics
│   │   └── training/       #               bộ huấn luyện tách theo chức năng (phân loại, hồi quy, tiền xử lý)
│   ├── db/                 #   DATABASE  – ORM SQLAlchemy, session, repositories, migrations (Alembic)
│   ├── platform/           #   DATABASE  – lớp học/chương trình (store riêng)
│   ├── integrations/       #   Kết nối LMS/CMS
│   ├── security/           #   Bút danh hoá, chặn dò mật khẩu, kiểm tra tệp tải lên, ẩn bí mật trong log
│   ├── resources/          #   Danh mục nghề nghiệp, quy chế, dữ liệu tĩnh
│   └── config.py           #   Nạp .env, cờ thư viện tuỳ chọn
├── tests/                  # ~190 tệp pytest (unit, integration, security, e2e Playwright, load)
├── ops/                    # Script vận hành: backup/khôi phục, migration check, pipeline KPI
├── tools/                  # Công cụ phát triển: quét bí mật, khoá phụ thuộc, benchmark, release gate
├── evals/                  # Bộ đánh giá có ngưỡng chặn (ML, RAG, AI)
├── simulator/              # Máy chủ LMS/CMS mô phỏng cho kiểm thử tích hợp
├── monitoring/             # Dashboard Grafana và luật cảnh báo
├── postgres-init/          # Script khởi tạo role PostgreSQL
├── deploy/
│   ├── standalone/         #   Triển khai độc lập: app + Caddy riêng, HTTPS tự động
│   ├── cloud/              #   Demo trên VM dùng chung Caddy với dự án khác (cách cũ)
│   └── production/         #   Bản cho một trường: PostgreSQL + RLS, image bất biến
├── docker/experimental/    # Dockerfile thử nghiệm (không dùng phát hành)
├── docs/                   # Tài liệu: ai/, architecture/, operations/, planning/, CONVENTIONS.md
├── reports/                # Báo cáo kiểm thử/nghiệm thu (bản chụp theo thời điểm)
├── Dockerfile              # Image phát hành (multi-stage, phụ thuộc khoá phiên bản)
├── docker-compose.yml      # Môi trường phát triển: PostgreSQL, simulator (theo profile)
├── requirements.txt        # Phụ thuộc trực tiếp; requirements.lock.txt là bản khoá đầy đủ
└── pyproject.toml          # Cấu hình ruff (lint + format)
```

Ranh giới phụ thuộc: `tabs/` (giao diện) → `services/` (nghiệp vụ) → `core/`, `db/` (lõi, dữ liệu).
`core/` và `services/` không import ngược `tabs/`.

## Chạy nhanh trên máy

Yêu cầu: Python 3.11 (image phát hành dùng 3.11.16), khoảng 6 GB đĩa cho PyTorch CPU và mô hình.

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c requirements.lock.txt
# xgboost cài riêng, không kèm NCCL (chỉ dùng cho GPU), giống Dockerfile:
python -m pip install --no-deps xgboost==3.1.2

cp .env.example .env                      # Windows: copy .env.example .env
# .env mặc định có EDUDSS_ENV=development: có tài khoản demo và dữ liệu mô phỏng
streamlit run run_dss.py                  # hoặc: python -m streamlit run run_dss.py
```

Mở <http://localhost:8501>. Trên Windows có thể bấm `run_app.bat` (cổng 8502).

Không đặt `EDUDSS_ENV` thì ứng dụng coi là **production** và fail closed: không tài khoản demo
`admin/admin123`, `giangvien/gv123`, không tự tạo tài khoản sinh viên, không dữ liệu mô phỏng.

PostgreSQL + pgvector là tuỳ chọn. Khi dùng:

```bash
docker compose --profile db up -d         # cần DB_PASSWORD, DB_APP_PASSWORD trong .env
export DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@localhost:5432/edudss_db'
python -m alembic upgrade head
python -m ops.migration_check verify
```

## Docker

```bash
docker build -t edudss:local .
docker run --rm -p 8501:8501 -e EDUDSS_ENV=development edudss:local
```

Image không chứa `.env`, bí mật hay dữ liệu runtime (xem `.dockerignore`). Health:
`http://localhost:8081/livez` (bên trong container), `/_stcore/health` (Streamlit).

## Triển khai độc lập có HTTPS

`deploy/standalone/` chạy EduDSS **một mình** với Caddy riêng làm reverse proxy, tự xin chứng chỉ
Let's Encrypt cho tên miền của bạn. Không phụ thuộc Caddy hay mạng Docker của dự án khác.

```bash
cd deploy/standalone
cp .env.example .env      # điền APP_DOMAIN, ACME_EMAIL và các bí mật
docker compose up -d --build
bash smoke.sh "https://<APP_DOMAIN>"
```

Có sẵn: security header (HSTS, CSP, X-Frame-Options…), chuyển tiếp WebSocket của Streamlit,
chỉ Caddy mở cổng 80/443, chứng chỉ nội bộ khi thử với `*.localhost`. Chi tiết:
[deploy/standalone/README.md](deploy/standalone/README.md). Bản cho một trường thật (PostgreSQL +
RLS, image ký số): [docs/operations/RELEASE_PROCESS.md](docs/operations/RELEASE_PROCESS.md) và
`deploy/production/`.

## Biến môi trường

Danh sách đầy đủ, có chú thích: [`.env.example`](.env.example). `.env` bị `.gitignore` chặn;
tệp mẫu không chứa bí mật. Các biến quan trọng:

| Biến | Ý nghĩa |
|---|---|
| `EDUDSS_ENV` | `development` / `test` / `production` (mặc định production) |
| `EDUDSS_MODE` | `DEMO_SYNTHETIC`, `REAL_LMS`, `LOCAL_OFFLINE` |
| `EDUDSS_DATA_ROOT` | Thư mục dữ liệu runtime (mặc định `data_warehouse/`) |
| `DATABASE_URL` hoặc `DB_*` | Kết nối PostgreSQL (tuỳ chọn khi chạy thử) |
| `EDUDSS_PSEUDONYM_KEY` | Khoá bút danh hoá, **bắt buộc ở production** (≥ 32 byte) |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_BASE_URL` | AI (tuỳ chọn) |
| `EDUDSS_LMS_WEBHOOK_SECRET` | Khoá HMAC webhook LMS; trống thì mọi webhook bị từ chối |
| `APP_DOMAIN`, `ACME_EMAIL` | Chỉ cho `deploy/standalone` (tên miền và email chứng chỉ) |

## Lint, format, kiểm thử

```bash
pip install ruff==0.14.5 pre-commit
pre-commit install            # tự chạy ruff + quét bí mật trước mỗi commit

ruff format .                 # định dạng
ruff check .                  # lint; cấu hình ở pyproject.toml
python tools/secret_scan.py . # quét khoá bí mật

python -m pytest tests --ignore=tests/e2e --ignore=tests/load -q   # như CI
python -m pytest -q                                                  # toàn bộ (~10–30 phút)
python -m playwright install chromium                                # trước khi chạy tests/e2e
```

CI: `.github/workflows/lint-test.yml` (format, lint không vượt baseline, F821/E9 = 0, quét bí mật,
pytest). Một số test cần PostgreSQL thật hoặc thư viện tuỳ chọn sẽ tự `skip` khi thiếu.

## Quy ước

Đặt tên tệp, lớp, hàm, hằng số, bảng/cột CSDL, biến môi trường, nhánh và commit:
[docs/CONVENTIONS.md](docs/CONVENTIONS.md). Mục lục tài liệu: [docs/README.md](docs/README.md).

## Giới hạn

- **Dữ liệu mô phỏng.** Dataset mẫu và simulator LMS/CMS là giả lập. Lớp "Yếu" chỉ có vài mẫu
  trên 1.000, nên chỉ số trên lớp đó dao động mạnh; mô hình chưa được kiểm định trên dữ liệu thật.
- Tích hợp LMS/SIS/CMS thật của trường chưa được chứng minh. Webhook LMS chỉ chạy khi đặt khoá.
- Tài khoản demo (`admin/admin123`…) chỉ tồn tại ngoài production và bị tắt khi
  `EDUDSS_PUBLIC_DEMO=1`. Đổi mật khẩu hoặc tắt trước khi mở ra Internet.
- Backup/khôi phục CSDL đã kiểm; khôi phục toàn bộ hạ tầng (mô hình, tệp CMS, bí mật) là việc riêng.
- Test 20.000 sinh viên đo dự đoán theo lô, không phải tải đồng thời nhiều người dùng.
- Một số module lớn (> 800 dòng) chưa tách hết; danh sách ở `reports/BO_KHUNG_DU_AN.md`.
