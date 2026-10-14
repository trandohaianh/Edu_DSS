# EduDSS — cảnh báo sớm sinh viên có nguy cơ

Hệ thống hỗ trợ quyết định cho trường đại học: tìm ra sinh viên có nguy cơ không
đạt **từ giữa kỳ**, khi còn kịp can thiệp, thay vì phát hiện ở điểm cuối kỳ.
Streamlit + PostgreSQL, ba vai trò (sinh viên, giảng viên, quản trị viên).

Ba quyết định thiết kế đáng chú ý nhất:

- **Chọn mô hình bằng F1-macro, không bằng accuracy.** Trong tập đánh giá 1.000
  sinh viên, lớp "Yếu" chỉ có 2 mẫu. Một mô hình đoán "Khá" cho tất cả đã có
  accuracy rất cao trong khi bỏ sót trọn vẹn nhóm cần tìm. Một `DummyClassifier`
  đoán theo lớp đa số được giữ làm mốc so sánh và không bao giờ được chọn.
- **Mô hình mới dừng ở trạng thái Candidate cho tới khi quản trị viên duyệt.**
  Đổi mô hình là đổi danh sách sinh viên bị gọi tên, nên quyết định đó không
  thuộc về người vừa bấm nút huấn luyện. Mỗi lần duyệt hoặc quay lui đều ghi
  nhật ký kiểm toán. Xem `dss/services/model_registry.py`.
- **Cách ly dữ liệu giữa các trường đặt trong cơ sở dữ liệu, không chỉ lọc trong
  mã.** 35 trên 41 bảng nghiệp vụ bật Row-Level Security. Bốn bảng không bật là
  danh mục dùng chung (`organizations`, `roles`, `permissions`,
  `role_permissions`); hai bảng còn lại (`rag_chunks`, `model_metrics`) không có
  cột `organization_id` và được cô lập qua bảng cha, vốn đã có RLS.

Mọi số liệu trong kho này đo trên **dữ liệu mô phỏng**. Chúng chứng minh pipeline
và cách thiết kế chạy đúng, không chứng minh hiệu quả trên sinh viên thật — chi
tiết trong phần giới hạn của từng báo cáo dưới `reports/`.

---

## Cài đặt để chạy thử

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
streamlit run run_dss.py
```

Local/default stores are intended for evaluation and fallback. Set
`EDUDSS_DATA_ROOT` to isolate writable data from an existing installation.

## PostgreSQL and pgvector

Create a PostgreSQL database with the pgvector extension available and set a
SQLAlchemy URL. Never commit real credentials.

```bash
export DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME'
python -m alembic upgrade head
```

The accepted migration head and the expected table list are derived from the
checkout itself by `dss/db/schema_contract.py` — do not hard-code them here, as
earlier versions of this file did (`797f72d1c666` / "27 tables" went stale the
moment a new migration landed). Production-style RLS verification also requires
`DATABASE_APP_ROLE_URL` for a separately granted, non-superuser application
role. See `.github/workflows/edudss-release-gate.yml` for a reproducible
synthetic CI setup.

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
