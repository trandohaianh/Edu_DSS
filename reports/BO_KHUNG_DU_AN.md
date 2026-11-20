# Báo cáo: bộ khung dự án EduDSS (repo Edu_DSS)

Ngày: 20/11/2026. Nguồn: thư mục `app/` của monorepo, nhánh `fullstack/edudss-production`, commit
`ffe837c`, xuất bằng `git archive HEAD:app` (chỉ tệp được theo dõi). Đích:
`https://github.com/trandohaianh/Edu_DSS`, nhánh `main`, **commit mới nối lên lịch sử cũ** (không
force-push, không viết lại lịch sử; commit cũ mới nhất trên remote là `11ba0bc`).

Đầu ra yêu cầu: *bộ khung dự án chạy được và quản lý phiên bản*. Mỗi mục dưới đây ứng với một ý
trong yêu cầu.

---

## 1. Cấu trúc thư mục rõ ràng; tách frontend, backend, database, module theo chức năng

**Hiện trạng trước:** ~15 tài liệu rời ở gốc repo (`AI_*.md`, `AGENT_FINAL_INTEGRATION.md`,
`TODO*.md`, `implementation_plan*`, `walkthrough.md`…), hai Dockerfile thử nghiệm và tệp `go`
(một dòng lệnh trỏ đường dẫn monorepo).

**Đã làm (`b07dfec`):**

| Trước | Sau |
|---|---|
| 9 tài liệu kiến trúc AI ở gốc | `docs/ai/` |
| `STREAMLIT_RECOVERY.md` | `docs/operations/` |
| `TODO*.md`, `implementation_plan*`, `walkthrough.md` | `docs/planning/` |
| `Dockerfile.c121-test`, `Dockerfile.torch210-experimental` | `docker/experimental/` (+ README) |
| `go` | xoá (không nơi nào tham chiếu) |

Mọi tham chiếu tới đường dẫn cũ trong `dss/`, `tests/`, `reports/` đã cập nhật; thêm `docs/README.md`.

Mã giữ bố cục `dss/` (180+ tệp, không di chuyển hàng loạt). Bản đồ lớp nằm trong README:

| Lớp | Thư mục |
|---|---|
| Frontend (giao diện Streamlit) | `dss/tabs/`, `dss/styles/`, `dss/assets/`, `dss/main.py` |
| Backend (nghiệp vụ) | `dss/services/` |
| Backend (lõi ML/dữ liệu) | `dss/core/`, `dss/core/training/` |
| Database | `dss/db/` (ORM, session, repositories, Alembic migrations), `dss/platform/` |
| Module khác | `dss/integrations/` (LMS/CMS), `dss/security/`, `ops/`, `tools/`, `evals/`, `simulator/` |

## 2. README

`README.md` viết lại bằng tiếng Việt (`023e0af`): ứng dụng là gì, bản đồ thư mục, chạy nhanh
(venv → `pip install -r requirements.txt -c requirements.lock.txt` → `streamlit run run_dss.py`
hoặc `run_app.bat`), Docker, triển khai độc lập có HTTPS, biến môi trường, lệnh lint/format/test,
liên kết quy ước, giới hạn (dữ liệu mô phỏng). Bỏ liên kết `../engine` không tồn tại trong repo này.

## 3. .gitignore

Đã có: `.env`, `deploy/**/*.env`, khoá (`*.pem`, `*.key`), `venv/`, `.venv/`, `data_warehouse/`,
`*.log`, backup. **Bổ sung (`aec5bde`, `4829e80`):** `.venv*/` (VD `.venv_torch210_experimental`),
`uploads/`, `models/`, `*.db`, `*.sqlite*`, `*.joblib`, `*.pkl`, `TAI-KHOAN*.md`, `*.docx`,
`*.pptx`, `~$*`, `.ruff_cache/`, `.mypy_cache/`.

Lưu ý: monorepo vẫn theo dõi 88 tệp runtime trong `data_warehouse/embeddings` và
`data_warehouse/metadata` dù `.gitignore` đã chặn thư mục đó. Chúng **không** được đưa vào repo này.

## 4. .env.example không chứa khoá bí mật

- Quét mọi biến mã đọc (`os.environ`, `getenv`, các hàm `_flag`/`_env`) trong `dss/`, `ops/`,
  `simulator/`, `run_dss.py`: 46 biến chưa có trong `.env.example` được thêm dưới dạng comment, nhóm
  theo chức năng, bí mật để trống (`aec5bde`).
- Bỏ `SECRET_KEY=change-me…`: không mã nào đọc biến này, giá trị mẫu gây hiểu nhầm.
- `deploy/standalone/.env.example` mới cũng không chứa bí mật.
- Quét bí mật toàn cây: `python tools/secret_scan.py .` → `findings=0 blocking=0`. `git grep` theo
  mẫu khoá (`sk-`, `AIza`, `gsk_`, `hf_`, `ghp_`, `AKIA`, `BEGIN … PRIVATE KEY`) chỉ thấy một chuỗi
  giả trong test kiểm tra việc ẩn khoá khỏi log. `git ls-files | grep -iE '\.env$|secret|\.pem|\.key|TAI-KHOAN|\.docx'`
  chỉ ra tệp mã/test có chữ "secret" trong tên (VD `tools/secret_scan.py`), không có tệp bí mật.

## 5. Quy tắc đặt tên

`docs/CONVENTIONS.md` (`aec5bde`), rút từ mã hiện có: tệp/module, lớp (`PascalCase`), hàm/biến
(`snake_case`), hằng (`UPPER_SNAKE_CASE`, `*_AVAILABLE`), bảng CSDL số nhiều `snake_case`, khoá ngoại
`<bảng>_id`, thời điểm `*_at`, ràng buộc `uq_<bảng>_<cột>`, biến môi trường tiền tố `EDUDSS_`,
nhánh `<loại>/<mô-tả>`, commit tiếng Việt mệnh lệnh; bí mật không có giá trị mặc định trong mã.

## 6. Lint và format

- `pyproject.toml`: ruff 0.14.5, Python 3.11, dòng 120. Luật: E, W, F, I, B, UP, C4, SIM, PIE, RUF,
  S105–S107. Bỏ qua có lý do ghi ngay trong tệp (dòng dài tiếng Việt, ký tự Unicode "dễ nhầm",
  hiện đại hoá chú thích kiểu để làm một đợt riêng…). Per-file-ignores cho 11 module dùng
  `import *`, E402 có chủ đích, tests. `F401` không tự sửa (tránh xoá import được re-export/patch).
- Formatter: `quote-style = "preserve"` vì nhiều test đọc mã nguồn để kiểm chuỗi.
- `.pre-commit-config.yaml` (ruff-check --fix, ruff-format, hook cơ bản, `tools/secret_scan.py`),
  `.editorconfig`, CI `.github/workflows/lint-test.yml` (action ghim SHA): format check, ruff
  không vượt baseline, F821/E9 phải bằng 0, quét bí mật, pytest (bỏ e2e/load).
- Thứ tự commit: cấu hình trước (`4829e80`), định dạng hàng loạt riêng (`d572a55`, 391 tệp).

**Số liệu ruff:**

| Thời điểm | Cảnh báo |
|---|---|
| Trước khi cấu hình (bộ luật tạm, không bỏ qua gì) | 6.145 |
| Sau khi có cấu hình, trước autofix/format | 1.766 |
| Sau autofix an toàn + format (`d572a55`) | 506 |
| Hiện tại (sau sửa lỗi + dọn import `timezone`) | **457** = baseline trong CI |

Không còn F821 (tên chưa định nghĩa) hay lỗi cú pháp. `ruff format --check .`: 409 tệp đã đúng định dạng.
Phần còn lại chủ yếu: F401 import thừa (127, nhiều cái ở `dss/config.py` là re-export có chủ đích),
W291 khoảng trắng cuối dòng nằm trong chuỗi (144), RUF059 biến giải nén không dùng (89), B905 `zip`
không `strict` (23).

## 7. Không viết toàn bộ phần mềm trong một tệp lớn

Đã tách hai tệp lớn nhất mà có test bao phủ, giữ nguyên đường import qua re-export:

| Tệp | Trước | Sau |
|---|---|---|
| `dss/core/trainers.py` (`ae0a305`) | 2.020 dòng | 43 dòng re-export + `dss/core/training/`: `common.py` 108, `classification.py` 858, `regression.py` 916, `preprocessing.py` 204 |
| `dss/services/model_service.py` (`0553596`) | 1.271 dòng | 851 dòng + `model_explainability.py` 239 (SHAP) + `model_metrics.py` 226 (chỉ số, chọn mô hình) |

Thân lớp/hàm giữ nguyên từng dòng; logger giữ tên `dss.core.trainers`; mô hình joblib cũ vẫn nạp
được. Commit trước khi tách: `a5aac58` (mốc ổn định); sau khi tách: test liên quan đạt.

**Chưa tách (bước tiếp theo), > 800 dòng:**

| Tệp | Dòng | Vì sao chưa tách |
|---|---|---|
| `dss/tabs/ai_advisor.py` | 1.936 | Nhiều test dùng `inspect.getsource(ai_advisor)` trên cả module; tách sẽ làm test hỏng giả |
| `dss/core/models.py` | 1.851 | Test `patch.object(models_mod, "GEMINI_AVAILABLE"/"genai")`; tab dùng `import *` từ module này |
| `dss/tabs/eda.py` | 1.634 | Tab UI, ít test đơn vị |
| `dss/tabs/ml_hub.py`, `advisory.py`, `clustering.py` | 1.150 / 1.143 / 1.119 | Tab UI dùng `import *` |
| `dss/core/warehouse.py`, `feature_utils.py` | 1.077 / 1.075 | |
| `dss/services/auth_service.py`, `learning_explainer.py` | 1.058 / 1.023 | |
| `dss/db/models.py` | 966 | ORM, tách theo phân hệ cần đổi `Base.metadata` import |
| `dss/core/training/regression.py`, `classification.py` | 916 / 858 | Có thể tách tiếp `train_and_evaluate` thành các bước |
| `dss/main.py`, `learning_explainer_tab.py`, `llm_gateway.py`, `dashboard.py`, `model_service.py`, `ml_provenance.py` | 810–908 | |

Đề xuất: trước khi tách các tab, thay `import *` bằng import tường minh và đổi các test
`getsource(module)` sang `getsource(hàm)`.

## 8. Sửa những lỗi có thể sửa

| Lỗi | Sửa | Commit |
|---|---|---|
| **Bảo mật:** `LMSLiveSyncManager` mặc định dùng khoá HMAC `"edudss_live_secret_2026"` nằm công khai trong mã → ai cũng ký được webhook hợp lệ | Đọc `EDUDSS_LMS_WEBHOOK_SECRET`; không đặt thì từ chối mọi chữ ký. Thêm 2 test | `c50d94d` |
| Toàn bộ 48 test E2E lỗi setup: conftest chạy `<app>/../.venv/Scripts/python.exe` (bố cục monorepo, chỉ Windows) | Dùng `sys.executable` | `e2e8c44` |
| `test_llm_service`, `test_c12_release_engineering` giả định thư mục tên `app/` và workflow monorepo | So với thư mục chứa gói `dss/`; phần kiểm workflow chỉ skip khi không có, phần còn lại luôn chạy | `b07dfec`, `c50d94d` |
| `except:` trần ở `dashboard.py`, `eda.py` (nuốt cả KeyboardInterrupt) | `except Exception` / `except (TypeError, ValueError)` | `04d85d6` |
| 3 test phân quyền dùng `assert False` → với `python -O` luôn đạt | `pytest.fail(...)` | `04d85d6` |
| `re.split(p, s, 1)` truyền maxsplit theo vị trí (deprecated 3.13) | `maxsplit=1` | `04d85d6` |
| 5 test đọc mã nguồn theo cửa sổ ký tự cố định, vỡ sau format | Lấy thân `if` theo thụt lề (chặt hơn) / nới cửa sổ | `a5aac58` |
| 36 import `timezone` thừa do autofix UP017 để lại | Bỏ đúng tên đó | `779c012` |
| Test `test_class_balance_and_pr_auc.py` (10 test) có trên GitHub nhưng thiếu trong monorepo | Khôi phục; mã hiện tại đạt cả 10 | `c50d94d` |

Không sửa (ghi nhận): tài khoản demo `admin/admin123`, `giangvien/gv123` trong `dss/db/seed.py`,
`auth_service.py` — chỉ tồn tại ngoài production, bị tắt khi `EDUDSS_PUBLIC_DEMO=1`; đây là thiết kế
có chủ đích cho chạy thử, README đã cảnh báo. B023 trong `evals/run_evals.py` là báo nhầm (lambda
dùng ngay trong cùng vòng lặp). Hai F811 trong `tests/test_ollama_provider.py` là báo nhầm (tên
tham số `json`).

## 9. Mỗi dự án tự có HTTPS

`deploy/standalone/` (`5a26f71`, `023e0af`): `docker-compose.yml` (app + `caddy:2.10.2-alpine` ghim
digest `sha256:4c6e91c6…`, mạng riêng của dự án, chỉ Caddy publish 80/443/443-udp, app không có
`ports:`), `Caddyfile` (HTTPS tự động theo `APP_DOMAIN` + `ACME_EMAIL`, CA nội bộ cho `*.localhost`,
HSTS/CSP/X-Frame-Options/Referrer-Policy/Permissions-Policy, xoá header `Server`, WebSocket Streamlit,
`stream_close_delay`, `/metrics` qua Bearer token), `.env.example`, `smoke.sh`, `README.md`. Không
dùng mạng `edge` hay Caddy của FieldOps; `deploy/cloud/README.md` trỏ sang đây.

**Kiểm tra:**
- `docker compose --env-file <env tạm> config -q` → hợp lệ; thiếu `APP_DOMAIN`/`ACME_EMAIL` thì báo lỗi rõ.
- `caddy validate` trong image `caddy:2.10.2-alpine` → `Valid configuration` với `edudss.localhost`
  và với tên miền công khai.
- Chạy thật với env tạm (`COMPOSE_PROJECT_NAME=edudss-standalone-smoke`, `APP_DOMAIN=edudss.localhost`,
  cổng 18080/18443): `docker compose up -d --build` build image từ `Dockerfile` (khoá phụ thuộc đạt),
  app `healthy`, rồi Caddy khởi động. Qua Caddy:
  - `GET https://edudss.localhost:18443/_stcore/health` → `ok` (chứng chỉ nội bộ của Caddy)
  - header có HSTS, CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Alt-Svc: h3`; không có `Server`
  - `http://…:18080/` → `308` sang HTTPS
  - nâng cấp WebSocket `/_stcore/stream` → `101 Switching Protocols`
  - `INSECURE=1 bash smoke.sh https://edudss.localhost:18443` → cả 4 mục OK
  - Sau đó `docker compose down -v` và xoá image tạm; không đụng container hay project khác.
- Chưa kiểm: xin chứng chỉ Let's Encrypt thật (cần tên miền công khai trỏ về máy chủ).

## 10. Commit tại các mốc ổn định

| Commit | Mục đích |
|---|---|
| `093ce58` | Mốc 1: đồng bộ bản Streamlit từ monorepo (thay cây làm việc bằng `app/`) |
| `b07dfec` | Cấu trúc: gom tài liệu rời vào `docs/`, Dockerfile thử nghiệm vào `docker/experimental/` |
| `5a26f71` | HTTPS riêng: `deploy/standalone/` với Caddy |
| `c50d94d` | Sửa lỗi khoá webhook cố định; test không phụ thuộc bố cục monorepo; khôi phục test PR-AUC |
| `4829e80` | Cấu hình lint/format/pre-commit/CI — **trước** thay đổi rủi ro (format hàng loạt) |
| `d572a55` | Áp dụng ruff format + autofix an toàn (391 tệp), riêng một commit |
| `aec5bde` | Quy ước đặt tên, `.env.example`, `.gitignore` |
| `a5aac58` | Sửa 5 test vỡ do format — mốc ổn định **trước** khi tách module |
| `ae0a305` | Tách `trainers.py` thành `dss/core/training/` (sau khi test liên quan đạt) |
| `0553596` | Tách `model_service.py` (sau khi test liên quan đạt) |
| `04d85d6` | Sửa lỗi thật do ruff phát hiện |
| `779c012` | Dọn import `timezone` thừa; chốt baseline ruff 457 |
| `e2e8c44` | Sửa E2E dùng `sys.executable` |
| `023e0af` | README tiếng Việt; ghim digest Caddy |
| `01ee3ca` | Sửa E2E chập chờn: chờ xác thực xong |
| (commit chứa báo cáo này) | Báo cáo bộ khung dự án |

## 11. Kiểm thử

Python: `D:/KLTN/edudss-final-candidate-v2/.venv/Scripts/python.exe` (venv của dự án). Lệnh:
`python -m pytest -q -p no:cacheprovider --basetemp=<tạm>` chạy trong một git worktree riêng tại
đúng commit cần đo.

| Lần chạy | Commit | Kết quả |
|---|---|---|
| Sau mốc 1 (đồng bộ), + test PR-AUC khôi phục | `093ce58` | 1.355 passed, 178 skipped, 3 failed, 48 errors — 9 phút 29 giây |
| Bộ đầy đủ cuối cùng | `e2e8c44` | **1.405 passed, 179 skipped, 2 failed, 0 errors** — 25 phút 41 giây |
| Chạy riêng sau sửa E2E chờ xác thực | `01ee3ca` | 2 test đăng nhập sai: 2 passed |

Giải thích lần đầu: 48 errors là toàn bộ E2E (đường dẫn venv cố định, đã sửa ở `e2e8c44`); 3 failed
là 2 test giả định bố cục monorepo (đã sửa) và `test_metrics_endpoint_content_and_auth`.

Hai failed của lần cuối:
- `tests/test_fullstack_costs_metrics_pipeline.py::test_metrics_endpoint_content_and_auth`: venv cục
  bộ thiếu `prometheus_client` (lỗi môi trường đã biết, không phải hồi quy).
- `tests/e2e/test_role_flows.py::test_unknown_username_rejected`: đọc trang khi còn "Đang xác thực…".
  Tái hiện được cả trên monorepo gốc. Đã sửa ở `01ee3ca` và chạy lại đạt. Bộ E2E đầy đủ **chưa** chạy
  lại sau sửa này (chỉ nhánh `expect_success=False` của fixture thay đổi).

Test chạy riêng giữa các mốc: sau tách `trainers.py` 22 tệp liên quan: 119 passed, 9 skipped; sau tách
`model_service.py` 22 tệp: 140 passed, 1 skipped; sau sửa lỗi lint 63 passed, 1 skipped.

## 12. Cách chạy

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt -c requirements.lock.txt
pip install --no-deps xgboost==3.1.2
copy .env.example .env
streamlit run run_dss.py
```

HTTPS độc lập: `cd deploy/standalone && cp .env.example .env && docker compose up -d --build`.
Lint: `ruff format --check . && ruff check .`. Test: `python -m pytest tests --ignore=tests/e2e --ignore=tests/load -q`.

## 13. Việc còn lại

1. Tách tiếp các tệp > 800 dòng ở mục 7, bắt đầu bằng việc bỏ `import *` trong các tab.
2. Giảm baseline ruff: xoá import thừa có kiểm chứng, thêm `strict=` cho `zip`, rồi đợt hiện đại
   hoá chú thích kiểu (UP006/UP045, ~1.200 chỗ) thành commit riêng.
3. `prometheus_client` có trong `requirements.lock.txt` nhưng thiếu trong venv cục bộ: cài lại venv
   từ lock để test `/metrics` chạy được.
4. Workflow CI mới chưa chạy trên GitHub tới khi push; cần xem lần chạy đầu (thời gian cài torch CPU).
5. Đổi hoặc tắt tài khoản demo trước khi mở bản `development` ra Internet; dùng `EDUDSS_PUBLIC_DEMO=1`.
