# Quy ước mã nguồn EduDSS

Các quy ước dưới đây mô tả cách mã **đang được viết**. Mã mới theo đúng các quy ước này; mã cũ
lệch quy ước được sửa dần khi có dịp chạm vào, không sửa hàng loạt chỉ để đổi tên.

## 1. Tệp, thư mục, module

| Đối tượng | Quy ước | Ví dụ |
|---|---|---|
| Module Python | `snake_case.py`, danh từ theo chức năng | `model_service.py`, `vector_store.py` |
| Tab giao diện Streamlit | `dss/tabs/<tên_tab>.py`, mỗi tab một hàm `render_*` | `dss/tabs/dashboard.py` |
| Logic nghiệp vụ (backend) | `dss/services/<chức_năng>_service.py` hoặc tên chức năng | `auth_service.py`, `rag_service.py` |
| Lõi ML/dữ liệu | `dss/core/` | `trainers.py`, `warehouse.py` |
| CSDL | `dss/db/` (ORM `models.py`, `session.py`, `repositories/`, `migrations/`) | |
| Tích hợp ngoài | `dss/integrations/` | `lms_cms_connector.py` |
| Bảo mật | `dss/security/` | `pseudonymization.py` |
| Script vận hành | `ops/<việc>.py`, chạy bằng `python -m ops.<việc>` | `ops/backup_recovery.py` |
| Công cụ phát triển | `tools/<việc>.py` | `tools/secret_scan.py` |
| Test | `tests/test_<chủ_đề>.py`; nhóm lớn đặt thư mục con | `tests/e2e/`, `tests/security/` |
| Tài liệu | `docs/<nhóm>/TEN_TAI_LIEU.md` (chữ hoa, gạch dưới) | `docs/ai/AI_ROUTING_MATRIX.md` |

Kích thước: một module **không nên vượt 800 dòng**. Khi vượt, tách theo chức năng thành module con và
giữ đường import cũ bằng re-export (xem `dss/core/trainers.py`).

Không dùng `from x import *` trong mã mới. Các tab cũ đang dùng được ghi ngoại lệ trong
`pyproject.toml` và sẽ được thay bằng import tường minh.

## 2. Tên trong mã Python

| Đối tượng | Quy ước | Ví dụ trong mã |
|---|---|---|
| Lớp | `PascalCase` | `ClassificationTrainer`, `LMSLiveSyncManager` |
| Hàm, phương thức, biến | `snake_case` | `resolve_ranking_col`, `predict_for_student` |
| Hàm/biến nội bộ module | tiền tố `_` | `_pr_auc_macro_scorer`, `_ENV_PATH` |
| Hằng số module | `UPPER_SNAKE_CASE` | `PR_AUC_SELECTION_THRESHOLD`, `CV_SCORE_COL` |
| Cờ thư viện tuỳ chọn | `<TÊN>_AVAILABLE` | `SHAP_AVAILABLE`, `XGBOOST_AVAILABLE` |
| Hàm trả bool | `is_`, `has_`, `can_`, `should_` | `is_production()`, `_has_complete_cv` |
| Hàm vẽ giao diện | `render_<khu_vực>` | `render_dashboard` |
| Khoá `st.session_state` | `snake_case`, có tiền tố theo tab khi dễ trùng | `current_df`, `clf_results` |

Chú thích và docstring viết tiếng Việt có dấu; tên định danh viết tiếng Anh. Tên cột dữ liệu mẫu
giữ tiếng Việt không dấu như dataset (`diem_giua_ky`, `ty_le_diem_danh`, `xep_loai`).

## 3. CSDL (PostgreSQL / SQLite qua SQLAlchemy)

| Đối tượng | Quy ước | Ví dụ |
|---|---|---|
| Bảng | `snake_case`, **số nhiều** | `students`, `model_versions`, `audit_logs` |
| Bảng nối | `<a>_<b>` số nhiều | `role_permissions` |
| Bảng theo phân hệ | tiền tố phân hệ | `cms_lessons`, `rag_chunks`, `lms_connector_configs` |
| Khoá chính | `id` | |
| Khoá ngoại | `<bảng_số_ít>_id` | `organization_id`, `role_id` |
| Thời điểm | `<sự_kiện>_at` (UTC) | `created_at`, `updated_at` |
| Cờ boolean | `is_<trạng_thái>` | `is_active`, `is_current` |
| Ràng buộc duy nhất | `uq_<bảng>_<cột>` | `uq_users_org_username` |
| Chỉ mục | `ix_<bảng>_<cột>` | |
| Migration | Alembic, `dss/db/migrations/versions/<rev>_<mô_tả>.py` | `797f72d1c666_ai_token_usage_and_admin_ai_config.py` |

Mọi bảng chứa dữ liệu của trường có `organization_id` (phân tách tenant, RLS ở PostgreSQL).
Thay đổi schema luôn đi kèm migration; không sửa migration đã phát hành.

## 4. Biến môi trường

- Tiền tố `EDUDSS_` cho cấu hình của ứng dụng: `EDUDSS_ENV`, `EDUDSS_DATA_ROOT`, `EDUDSS_PSEUDONYM_KEY`.
- `DSS_` là tiền tố cũ cho cấu hình AI/ML (`DSS_LLM_TIMEOUT`, `DSS_PRIMARY_PROVIDER`); giữ để tương thích,
  biến mới dùng `EDUDSS_`.
- Biến chuẩn của bên thứ ba giữ đúng tên gốc: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`,
  `DATABASE_URL`, `STREAMLIT_*`.
- Cờ bật/tắt nhận `1/0` (cũng chấp nhận `true/false`, `yes/no`).
- Bí mật: chỉ đặt qua môi trường hoặc `.env` (bị `.gitignore`). Không viết giá trị mặc định cho bí mật
  trong mã; thiếu bí mật thì tính năng phải **từ chối** (fail closed), không dùng khoá mặc định.
- Mọi biến mới phải được thêm vào `.env.example` (để trống nếu là bí mật).

## 5. Nhánh git

Dạng `<loại>/<mô-tả-ngắn>` bằng chữ thường, gạch nối. Các loại đang dùng trong lịch sử dự án:

| Loại | Dùng cho |
|---|---|
| `feature/` | chức năng mới |
| `fix/` | sửa lỗi (`fix/ml-correctness`) |
| `docs/` | chỉ tài liệu |
| `refactor/` | tái cấu trúc không đổi hành vi |
| `release/` | chuẩn bị phát hành |
| `chore/` | cấu hình, công cụ, phụ thuộc |

`main` luôn chạy được và qua CI. Không force-push lên `main`.

## 6. Commit

- Dòng tiêu đề ≤ 72 ký tự, tiếng Việt, câu mệnh lệnh nói **việc gì thay đổi**
  ("Sửa cân bằng lớp và bổ sung PR-AUC"). Thân commit giải thích **vì sao**, kết quả đo, cách kiểm thử.
- Một commit một mục đích. Định dạng mã hàng loạt luôn là commit riêng, không lẫn với thay đổi logic.
- Commit tại các mốc: trước thay đổi rủi ro (tách module, định dạng hàng loạt, nâng phụ thuộc)
  và sau khi test đạt.
- Không commit `.env`, khoá, dữ liệu runtime (`data_warehouse/`, `uploads/`, `models/`), tài liệu cá nhân.

## 7. Lint, format, kiểm thử

```bash
pip install ruff==0.14.5 pre-commit
pre-commit install                 # tự chạy ruff + quét bí mật trước mỗi commit
ruff format .                      # định dạng
ruff check .                       # lint (cấu hình trong pyproject.toml)
python -m pytest -q --ignore=tests/e2e --ignore=tests/load
```

CI (`.github/workflows/lint-test.yml`) chặn khi: mã chưa format, số cảnh báo ruff vượt baseline,
có tên chưa định nghĩa (F821) hoặc lỗi cú pháp, phát hiện bí mật, hoặc test hỏng.
