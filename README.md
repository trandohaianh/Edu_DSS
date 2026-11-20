# EduDSS evaluator setup

> **Bản full-stack (16/11/2026)**
> - Đăng nhập Google (OIDC native của Streamlit) gắn với tài khoản theo email.
> - Admin quản lý tài khoản ngay trong app.
> - Chế độ demo công khai (`EDUDSS_PUBLIC_DEMO`) không có tài khoản mặc định.
> - Chi phí AI tính theo token thật do provider trả về; chi phí hạ tầng nhập tay.
> - `/metrics` cho Grafana Cloud, kèm dashboard và 12 cảnh báo.
> - Pipeline vận hành: KPI, chất lượng dữ liệu/drift, backup có diễn tập khôi phục.
> - Bộ eval có cổng chặn: [evals/README.md](evals/README.md).
> - Deploy miễn phí chung VM: [deploy/cloud/README.md](deploy/cloud/README.md).


## Prerequisites

- Python 3.11 or 3.12
- PostgreSQL 16 with pgvector, or Docker
- A virtual environment is recommended

## Python setup and local mode

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# xgboost is deliberately not in requirements.txt (its wheel unconditionally
# pulls in the GPU-only nvidia-nccl-cu12, unused on CPU) — install it the
# same way the Dockerfile does, with --no-deps, after the line above:
python -m pip install --no-deps xgboost==3.1.2
export EDUDSS_ENV=development    # Windows PowerShell: $env:EDUDSS_ENV="development" (hoặc đặt trong app/.env)
streamlit run run_dss.py
```

`EDUDSS_ENV` không đặt thì ứng dụng chạy như **production** (fail closed): không có tài khoản demo
`admin/admin123`, `giangvien/gv123`, không tự tạo tài khoản sinh viên và không có dữ liệu mô phỏng.

Local/default stores are intended for evaluation and fallback. Set
`EDUDSS_DATA_ROOT` to isolate writable data from an existing installation.

## PostgreSQL and pgvector

Create a PostgreSQL database with the pgvector extension available and set a
SQLAlchemy URL. Never commit real credentials.

```bash
export DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME'
python -m alembic upgrade head
```

The classroom/programme release migration head is `d2e3a6102601`.
Use `python -m alembic heads` and `python -m ops.migration_check verify`
to check the shipped graph and the deployed schema. Production-style RLS
verification uses a separately granted, non-superuser application role.
The isolated test runner below creates its own disposable PostgreSQL and
never uses the development database.

See [the classroom/programme pilot guide](docs/STAGE23_PILOT_GUIDE.md) for
roles, school allocations, CSV enrollment and the HLU integration boundary.

```bash
python tools/run_stage23_acceptance.py
```

Current users/auth, activity history, AI token usage and admin AI configuration
are PostgreSQL-primary-with-fallback. This wording does not imply that every
domain has completed runtime migration.

## Tests

```bash
python -m pytest --collect-only -q
python -m pytest tests --ignore=tests/e2e --ignore=tests/load -q
python -m pytest tests/e2e -q
python -m pytest tests/load/test_lms_scale_load.py::test_20000_students_batch_prediction_benchmark -q -s
```

The 20,000-record test measures batch prediction. It is not a concurrent-user
load test. E2E tests require Playwright Chromium:

```bash
python -m playwright install chromium
```

## Docker

```bash
docker build -t edudss:local .
docker run --rm -p 8501:8501 edudss:local
```

For PostgreSQL mode, pass the documented environment variables at runtime. Do
not bake `.env`, secrets, database dumps or private datasets into the image.
The provided Compose file can start PostgreSQL with `--profile db` after a
private `DB_PASSWORD` is supplied.

## Demonstration boundary

The internal demo exercises the accepted local and PostgreSQL-backed flows.
External production LMS/SIS/CMS integration is not proven. Database
backup/restore is verified, while external model artifacts, datasets, CMS
uploads, secret recovery and full disaster recovery remain separate work.

## Optional queued learning engine

The [learning engine guide](../engine/README.md) covers time-aware ML validation,
local TF-IDF/Surprise SVD recommendations, Redis lecture cache and Celery advice.
Set EDUDSS_ENGINE_URL and the shared server signing key to enable its AI tab.
Dataset school/course/student identities must match the application's verified
classes. The [architecture and measured limits](../engine/docs/VALIDATION.md)
include synthetic accuracy, quota checks and cache-versus-HTTP timings.
