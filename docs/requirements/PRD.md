# EduDSS — Tài liệu yêu cầu sản phẩm (PRD)

> **Trạng thái: BẢN NHÁP — chờ chủ dự án duyệt** (soạn 21/11/2026, dựa trên commit 6e9710d)

Tài liệu này **gom lại** những gì repo đã có (README, code, roadmap, báo cáo nghiệm thu). Không có yêu
cầu nào mới được bịa thêm. Mỗi ý đều ghi nguồn. Chỗ nào chỉ chủ dự án quyết được thì đánh dấu
**⏳ CHỜ CHỦ DỰ ÁN CHỌN**.

Tài liệu liên quan: [MVP_SCOPE.md](MVP_SCOPE.md) · [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) ·
[../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) · [../database/SCHEMA.md](../database/SCHEMA.md) ·
[../ux/SCREEN_MAP.md](../ux/SCREEN_MAP.md)

---

## 1. Bài toán cần giải quyết

Nhà trường cần **phát hiện sớm sinh viên có nguy cơ** học kém, rồi đưa ra lời khuyên học tập và định
hướng nghề nghiệp dựa trên dữ liệu. EduDSS là hệ thống hỗ trợ ra quyết định (DSS) làm việc đó.
(Nguồn: `README.md:1-12`)

EduDSS hiện làm được:

| Năng lực | Nguồn |
|---|---|
| Phân tích dữ liệu học tập (EDA), dashboard lớp học, phân cụm sinh viên | `README.md:6`, `dss/tabs/eda.py`, `dss/tabs/dashboard.py`, `dss/tabs/clustering.py` |
| Huấn luyện và so sánh mô hình học máy (xếp loại, dự đoán điểm), giải thích bằng SHAP | `README.md:7-8`, `dss/core/training/`, `dss/services/model_explainability.py` |
| Kho mô hình có vòng đời Candidate → Production → Archived, không tự lên Production | `README.md:9`, `dss/services/model_registry.py` |
| Trợ lý AI tư vấn: định tuyến 3 tầng, RAG trên bài giảng và quy chế, ghi vết quyết định | `README.md:10`, `docs/ai/AI_ROUTING_MATRIX.md`, `dss/services/rag_service.py` |
| Kế hoạch học tập theo môn/chủ đề và lịch sử kế hoạch | `docs/architecture/EDUDSS_MINISTRY_ROADMAP.md:13-58` |
| Lớp học, bài đánh giá, chương trình và cấp phát cho trường (thí điểm) | `docs/STAGE23_PILOT_GUIDE.md`, `reports/stage23/ACCEPTANCE.md` |
| Phân quyền theo vai trò, đăng nhập Google, bút danh hoá dữ liệu cá nhân | `README.md:11`, `dss/services/auth_service.py`, `dss/services/google_signin.py`, `dss/security/pseudonymization.py` |

**Giới hạn đã ghi rõ** (`README.md:171-182`): dữ liệu đi kèm là **mô phỏng**. Mô hình chưa được kiểm
định trên sinh viên thật của trường. Tích hợp LMS/SIS/CMS thật chưa được chứng minh ngoài môi trường
mô phỏng.

## 2. Người dùng mục tiêu và vai trò

Danh sách vai trò lấy từ `dss/core/roles.py:7` (`ROLES`) và `dss/db/seed.py:28`. Mô tả lấy từ `ROLE_INFO`
trong `dss/core/roles.py`.

| Vai trò (tên trong code) | Ai dùng | Mục tiêu (trích `ROLE_INFO`) |
|---|---|---|
| `Sinh viên` | Sinh viên | "Biết mình đang ở đâu, cần cải thiện gì": xem dự đoán của riêng mình, hiểu lý do (SHAP), nhận gợi ý, kế hoạch học tập, định hướng nghề nghiệp |
| `Giảng viên / CVHT` | Giảng viên và cố vấn học tập (dùng chung một vai trò) | "Theo dõi cả lớp, phát hiện rủi ro sớm": dashboard lớp, huấn luyện/so sánh mô hình, phân cụm, kho dữ liệu |
| `Admin` | Quản trị viên của một trường | "Quản trị dữ liệu, vận hành hệ thống": người dùng, dữ liệu, mô hình, tri thức RAG, cấu hình AI, tích hợp LMS |
| `Platform Admin` | Đơn vị quản lý chương trình nhiều trường | Đăng ký trường, tạo chương trình, giao quyền (`docs/STAGE23_PILOT_GUIDE.md:67`). Có trong `seed.py` và `TAB_ACCESS` nhưng **không** có trong danh sách `ROLES` |

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: `Platform Admin` có là vai trò chính thức của sản phẩm không?**
> - (a) **Có**: thêm vào `ROLES`, có nhóm điều hướng riêng và mockup riêng.
> - (b) **Không**: chỉ là vai trò vận hành nội bộ cho thí điểm Stage 3, ẩn khỏi tài liệu người dùng.
> - **(đề xuất) (b)** cho bản đầu tiên. Lý do: roadmap ghi Stage 3 mới là thí điểm và chưa có thỏa
>   thuận với Bộ (`docs/architecture/EDUDSS_MINISTRY_ROADMAP.md:3-8`).

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: trường đầu tiên dùng là trường nào, và bao nhiêu người dùng?**
> - Repo **chưa có** con số mục tiêu. Chỉ có tiêu đề kế hoạch "~20.000 Sinh Viên/Năm"
>   (`docs/planning/walkthrough.md:1`) và một phép đo **dự đoán theo lô** 20.000 bản ghi. Nhiều báo cáo
>   ghi rõ đó **không phải** 20.000 người dùng đồng thời (`reports/production_readiness/FINAL_MUST_NOT_SAY.md:14`).
> - Mức đồng thời đã đo được: 50 thao tác CSDL đồng thời, p95 452 ms, trên một máy dev
>   (`reports/final_acceptance/COMMERCIAL_RELEASE_READINESS.md:222`). **Chưa đo** số phiên trình duyệt đồng thời.
> - Cần chủ dự án điền: số sinh viên, số giảng viên, số người dùng đồng thời giờ cao điểm.
> - **(đề xuất)** thí điểm 1 trường với khoảng ≤ 50 người dùng đồng thời (mức đã có bằng chứng gần nhất),
>   rồi đo tải thật trước khi hứa con số lớn hơn.

## 3. Loại ứng dụng

- **Ứng dụng web** viết bằng Streamlit (Python), chạy trong trình duyệt (`README.md:3`, `run_dss.py`).
- **Không** có ứng dụng mobile riêng. Kiểm tra giao diện mới chỉ làm ở 3 độ phân giải desktop
  (`reports/final_ui_functional_audit/RESPONSIVE_ACCESSIBILITY_REPORT.md:3`).

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: có cần hỗ trợ điện thoại không?**
> - (a) Chỉ desktop/laptop (như hiện tại).
> - (b) Desktop + "xem được trên điện thoại" cho trang của sinh viên (cần kiểm thử thêm ở 375 px).
> - (c) Ứng dụng mobile riêng (ngoài phạm vi code hiện có).
> - **(đề xuất) (a)** cho MVP, ghi (b) vào danh sách "Để sau".

## 4. Đăng nhập và phân quyền

| Nội dung | Hiện trạng trong code | Nguồn |
|---|---|---|
| Đăng nhập bằng tên đăng nhập + mật khẩu | Mật khẩu băm PBKDF2-HMAC-SHA256 | `dss/services/auth_service.py:76-95` |
| Khoá khi nhập sai nhiều lần | Khoá 15 phút sau 5 lần sai | `dss/security/login_throttle.py:31-32` |
| Đăng nhập bằng Google | OIDC qua `st.login`. Chỉ hiện khi đã cấu hình. Google chứng minh email, vai trò vẫn do tài khoản EduDSS quyết định | `dss/services/google_signin.py:1-11` |
| Phân quyền 2 lớp | Lọc menu theo vai trò (`TAB_ACCESS`) + chặn ở hàm (`@require_role`) | `dss/core/roles.py:175-196`, `auth_service.py:430` |
| Tách dữ liệu giữa các trường | PostgreSQL Row Level Security theo `app.organization_id` | `dss/db/migrations/versions/cbae9b411ed5_*.py` |
| Chế độ production "an toàn mặc định" | Không đặt `EDUDSS_ENV` thì coi là production: không tài khoản demo, không dữ liệu mô phỏng | `README.md:72-74` |

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: có kết nối HLU và SSO của trường trong phạm vi không?**
> - Repo ghi: "Kết nối HLU, mua sắm và triển khai diện rộng chưa được nghiệm thu" (`docs/STAGE23_PILOT_GUIDE.md:4`, mục 124+).
>   Có connector Moodle REST (`dss/services/moodle_connector.py`) và webhook LMS ký HMAC, nhưng chưa
>   chạy với LMS thật của trường nào.
> - (a) Trong phạm vi MVP · (b) Để sau, MVP chỉ nhập dữ liệu bằng file Excel/CSV + Google OIDC.
> - **(đề xuất) (b).**

## 5. Lưu trữ dữ liệu (tóm tắt)

Có 2 chế độ (chi tiết ở [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) và [SCHEMA.md](../database/SCHEMA.md)):

- **Phát triển / chạy thử:** tệp JSON, CSV, joblib và SQLite trong `data_warehouse/` (`README.md:76-83`,
  `dss/platform/store.py:38`, `dss/services/learning_plan_history.py:64`).
- **Production:** PostgreSQL 16 + pgvector, có RLS. Bật theo từng phân hệ bằng biến `EDUDSS_<PHÂN_HỆ>_STORE=postgres`
  (`dss/core/persistence_config.py`, `deploy/production/docker-compose.prod.yml:63-73`).

## 6. Phạm vi tính năng

Danh sách đầy đủ theo trang và vai trò, kèm cột Bắt buộc/Để sau (đề xuất): [MVP_SCOPE.md](MVP_SCOPE.md).

## 7. Ngân sách và tiến độ

> ⏳ **CHỜ CHỦ DỰ ÁN CHỌN: ngân sách và mốc thời gian.**
> - Repo **không có** số liệu ngân sách hay lịch biểu. Chỉ có ghi chú "chưa có thỏa thuận mua sắm
>   hay tài trợ của Bộ" (`docs/architecture/EDUDSS_MINISTRY_ROADMAP.md:7-8`). Phiên bản hiện tại là
>   `1.0.0-rc.1` (`VERSION`).
> - Cần điền: chi phí hạ tầng/tháng (máy chủ, tên miền, khoá API AI), ngày bảo vệ/bàn giao, ngày thí điểm.
> - Gợi ý mục cần dự trù, rút từ code: máy chủ chạy Docker (~6 GB đĩa cho PyTorch CPU, `README.md:66`),
>   PostgreSQL, tên miền HTTPS (`deploy/standalone/`), khoá AI tuỳ chọn (OpenAI/Gemini/Groq). Ollama
>   chạy cục bộ thì không tốn phí API.
> - **(đề xuất)** không có số mặc định. Chủ dự án phải tự điền.

## 8. Tiêu chí chấp nhận

Xem [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md). Lưu ý: các biên bản nghiệm thu trong `reports/`
được viết **sau khi** làm xong. Tài liệu kia chuyển chúng thành tiêu chí đo được.

## 9. Ngoài phạm vi (theo chính repo)

- Tải đồng thời 20.000 người dùng, chạy nhiều node (`reports/production_readiness/FINAL_SUBMISSION_ACCEPTANCE.md:232`).
- Tổng hợp cấp Bộ ở quy mô quốc gia (`reports/production_readiness/PRODUCT_DEPLOYMENT_STRATEGY.md:38`).
- Object storage, hàng đợi, cân bằng tải: mới là phác thảo
  (`docs/architecture/NATIONAL_SCALE_ARCHITECTURE_PROJECTION.md`).
- Gửi email: không tìm thấy chức năng gửi email nào trong `dss/`.
