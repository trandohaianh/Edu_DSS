# EduDSS — Thesis Defense Truth Table

**Purpose:** exact, current-code-verified claims to make (and NOT make) when defending this
system. Every row was checked against actual runtime/code behavior this session, not assumed
from imports or module docstrings. Where the current code contradicted an earlier assumption
(including one supplied as "verified" going into this pass), the code's behavior is what's
recorded here, per the standing rule: **current code/runtime is authoritative over any prior
handbook or summary statement.**

---

## 1. DATABASE / STORAGE

**Implemented?** PARTIAL / HYBRID STORAGE — by subsystem, not system-wide.

| Subsystem | Storage mechanism | Persistence | Production status |
|---|---|---|---|
| RAG vectors (active) | `LocalVectorStore` — NumPy + JSON, file-based | Real, durable | PRODUCTION_READY |
| RAG vectors (dormant) | `PgVectorStore` — PostgreSQL + pgvector | **Schema only** — see correction below | NOT FUNCTIONAL |
| Knowledge Base metadata | File-based (JSON, alongside vector store) | Real | PRODUCTION_READY |
| Student dataset | File-based (CSV + JSON metadata, `warehouse.py`) | Real | PRODUCTION_READY |
| Training dataset | File-based (same warehouse mechanism) | Real | PRODUCTION_READY |
| Models / model artifacts | File-based (`joblib`, SHA-256 verified on load) | Real | PRODUCTION_READY |
| Model Registry | File-based JSON metadata (status field: candidate/production/archived) | Real | PRODUCTION_READY |
| Users | File-based JSON (`data_warehouse/users.json`), PBKDF2-HMAC-SHA256 hashed | Real | PRODUCTION_READY (documented as a simplified mechanism appropriate to project scale, not enterprise-grade) |
| Organizations | File-based (subscription_service) | Real | PRODUCTION_READY |
| Consultation history | File-based (warehouse activity log) | Real | PRODUCTION_READY |
| LMS data | Synthetic generator (`generate_lms_data()`) in DEMO_SYNTHETIC; **no real external LMS store** | N/A (no real external source) | NOT REAL-INTEGRATED |
| CMS data | File-based (`cms_lecture_repository.py` JSON registry) for **uploaded** lecture content | Real (for uploaded content) | PRODUCTION_READY for the upload/store mechanism itself; NOT connected to any real external CMS |
| Logs | File-based (activity/audit JSON) | Real | PRODUCTION_READY |
| Subscription data | File-based | Real | PRODUCTION_READY |

### IMPORTANT CORRECTION to the "PostgreSQL exists" claim

`vector_store.py::PgVectorStore` does genuinely:
- Test a real PostgreSQL connection via `psycopg2.connect()`.
- Define a real, well-designed DDL schema (`rag_documents`/`rag_chunks` tables, `vector(384)`
  column, HNSW index with `vector_cosine_ops`).

However, its actual data methods are **stubs**, verified by reading the full class body:
- `add_chunks()` — raises if disconnected; if connected, returns `len(chunks)` **without
  executing any INSERT**.
- `search()` — raises if disconnected; if connected, **unconditionally returns `[]`**.
- `list_documents()` — **unconditionally returns `[]`**.
- `delete_document()` — returns a bare `True`/`False` with **no DELETE executed**.

It is only ever activated by `get_vector_store()` when `PGVECTOR_URL` or `DATABASE_URL` is set
in the environment — which is **not** the case in the current default configuration. The vector
store actually in use today is `LocalVectorStore`, confirmed fully functional by a real
add→search round-trip test.

**Safe:**
> "Hệ thống hiện hỗ trợ PostgreSQL thông qua PgVectorStore cho tầng lưu trữ vector của RAG —
> lớp kết nối và schema đã được thiết kế thật (kiểm tra kết nối psycopg2 thật, DDL pgvector/HNSW
> thật). Tuy nhiên các thao tác đọc/ghi dữ liệu thực tế trong lớp này hiện là khung sườn
> (scaffold), CHƯA thực thi câu lệnh SQL thật; vector store đang hoạt động thật trong phiên bản
> hiện tại là LocalVectorStore (file-based). Các thành phần dữ liệu nghiệp vụ khác như dataset,
> model và user vẫn dùng cơ chế lưu trữ file-based."

**Must NOT claim:**
> "Toàn bộ hệ thống sử dụng PostgreSQL." / "PostgreSQL là cơ sở dữ liệu trung tâm cho toàn bộ
> EduDSS." / "PgVectorStore đã lưu trữ và truy xuất vector thật qua PostgreSQL." (the last claim
> is false even when a Postgres URL is configured — the methods are stubs).

---

## 2. RAG KNOWLEDGE BASE

**Upload:** YES — real pipeline: validation → parsing → chunking → embedding → vector store,
verified by reading `document_ingestion.ingest_document()` and its call site in
`knowledge_base.py`.

**Supported formats (verified in the file uploader's `type=` list):** `.txt`, `.md`, `.docx`,
`.pptx`, `.pdf`, `.json`.

**Retrieval:** YES — real namespace-scoped listing (`list_documents()`) and real RAG retrieval
with a relevance threshold (see §5).

**Update (Edit):** NO — no edit UI exists anywhere in `knowledge_base.py`. Unchanged by the
2026-09-16 hardening pass (out of scope — see below).

**Delete:** **YES, as of 2026-09-16 (pre-defense hardening pass), for the active backend only.**
`dss/services/knowledge_base_admin.py::delete_document_safely()` now wires a real, guarded
delete: Admin-only (`@require_role`), confirmation dialog in the UI, refuses to trust
`PgVectorStore.delete_document()`'s stub `True` (reports `"unsupported"` honestly instead),
and blocks deletion if a live CMS lesson still references the document. Verified by 14 unit
tests + 2 E2E tests, all passing.

**Safe:**
> "Knowledge Base hỗ trợ nạp tài liệu đa định dạng thật (txt/md/docx/pptx/pdf/json), truy xuất
> thật có kiểm soát ngưỡng liên quan, và (từ 2026-09-16) xóa tài liệu thật có xác nhận cho
> backend đang hoạt động (LocalVectorStore). Đây là Create + Read + Delete; Update vẫn chưa
> được triển khai ở tầng sản phẩm — vẫn là PARTIAL CRUD, không phải full CRUD."

**Must NOT claim:**
> "Knowledge Base cung cấp đầy đủ CRUD tài liệu."

**Phân loại nguồn (2026-09-16, `UI-RAGGOV-001`):** `dss/services/source_classification.py`
phân loại mọi tài liệu vào đúng 1 trong 4 nhóm — `COURSE_MATERIAL` (Tài liệu môn học, do
Giảng viên tải lên qua CMS, có `lesson_id`+`lecturer_id`), `SUPPLEMENTARY_REFERENCE`
(Nguồn tham khảo bổ sung — 4/19 tài liệu demo có nguồn học thuật thật:
Pomodoro/Feynman/Krashen/Cornell), `DEMO` (Dữ liệu demo — 15/19 tài liệu còn lại), và
`INSTITUTION_APPROVED` (Tài liệu được phê duyệt — **định nghĩa sẵn nhưng KHÔNG BAO GIỜ có
tài liệu nào thuộc nhóm này**, vì hệ thống không có quy trình phê duyệt cấp tổ chức thật).
Phân loại dựa hoàn toàn vào provenance/metadata, không đọc nội dung văn bản.

**Xác nhận quan trọng nhất (đã có từ trước, được xác minh lại bằng test hồi quy mới —
`tests/test_rag_source_governance.py`):** AI Giải thích Bài giảng (Learning Explainer)
CHỈ BAO GIỜ truy xuất từ tài liệu CMS đúng môn/bài đang học
(`cms_lecture_repository.retrieve_lesson_content`) — KHÔNG có đường dẫn code nào rơi về
19 tài liệu demo. Khi không có tài liệu môn học nào khớp, hệ thống trả lời trung thực
"chưa có trong tài liệu môn học hiện tại", không có trích dẫn nào, không bịa nguồn.

**Safe (bổ sung):**
> "Knowledge Base phân loại rõ nguồn: Tài liệu môn học / Nguồn tham khảo bổ sung / Dữ liệu
> demo — Admin thấy số lượng từng nhóm riêng biệt, không gộp thành 1 tổng gây hiểu lầm. AI
> Giải thích Bài giảng chỉ dùng Tài liệu môn học, không bao giờ dùng Dữ liệu demo để trả
> lời câu hỏi về bài giảng."

**Must NOT claim (bổ sung):**
> "Tài liệu có quy trình phê duyệt cấp tổ chức (Institution Approved) thật." (Nhóm này
> tồn tại trong code nhưng chưa từng có tài liệu nào thuộc về nó.)
> "Hệ thống có kết nối CMS ngoài thật." (Vẫn là nội bộ — xem Mục 3 bên dưới.)

---

## 3. LMS

**Real external integration:** NO.

Verified: `lms_connector.py::RealConnectorLMSRepository.get_student_learning_summary()` itself
delegates internally to `DemoLMSRepository` — even the class named "Real Connector" does not
yet talk to a real external LMS. A separate `lms_live_sync.py` module implements real HMAC
webhook-signature verification logic but has no actual network listener wired to receive
external webhooks, and its UI surface (`warehouse_tab.py`) is explicitly labeled "giả lập"
(simulated).

An `admin_settings.py` panel previously claimed **"🟢 Trực tuyến (Live Webhook & REST Connector
sẵn sàng)"** with a fabricated webhook URL and secret key — this was a genuine UI-honesty defect
(DEMO-LMS-STATUS-001), now fixed to show an honest not-connected status. This was a UI bug fix,
not an integration milestone — LMS integration status is unchanged by that fix.

**Safe:**
> "Hệ thống đã thiết kế lớp repository/abstraction (lms_connector.py) để sẵn sàng tích hợp LMS,
> đồng thời các chức năng DSS/AI có thể làm việc với dữ liệu theo cấu trúc đó. Phiên bản hiện tại
> chưa kết nối với một LMS bên ngoài thực tế."

**Must NOT claim:**
> "Hệ thống đã tích hợp LMS thực tế." / "Hệ thống đồng bộ trực tiếp với Moodle/Canvas/Google
> Classroom."

---

## 4. CMS

**Real external integration:** NO (no external CMS connector).

**What IS real:** the CMS **content repository** for lecture materials that a Lecturer directly
uploads into EduDSS (`cms_lecture_repository.py`) — this is a real, working ingestion → storage →
retrieval → AI-explanation pipeline for content the Lecturer puts in, verified end-to-end this
session with a live grounded, cited answer. It is not a connector to an external CMS platform.

**Safe:**
> "Kiến trúc/kho nội dung của hệ thống hỗ trợ luồng học liệu kiểu CMS — Giảng viên nạp tài liệu
> thật, hệ thống lưu trữ, đánh phiên bản và dùng làm nguồn duy nhất cho AI giải thích bài giảng
> (đã kiểm chứng thật, không phải giả lập). Đây là kho nội dung nội bộ của EduDSS, chưa phải kết
> nối tới một hệ thống CMS bên ngoài thực tế."

**Must NOT claim:**
> "Hệ thống đã kết nối với một CMS bên ngoài thực tế (Moodle CMS/Canvas Content/...)."

---

## 5. MODEL REGISTRY

**Candidate lifecycle:** YES — genuinely persisted, not merely a UI label. `warehouse.py`
writes a real `status` field (`candidate` | `production` | `archived`); verified live via the
Admin Model Registry screenshot showing real counts (2 Production, 2 Candidate, rest Archived)
and confirmed to match `admin_reports.py`'s chart after the MODELREG-001-FOLLOWUP consistency fix
this session.

**Auto-promotion:** NO by default — `should_promote = bool(auto_promote) if auto_promote is not
None else bool(is_best)`, and `auto_promote=True` is never passed anywhere in the app (confirmed
by a repo-wide call-site grep, earlier phase).

**Bootstrap auto-training:** NO — verified by reading `bootstrap_service.py::
_bootstrap_default_training()` in full: it only *reuses* an existing, already Admin-approved
Production model if one exists; if none exists, it explicitly logs "Tuyệt đối không tự động
chạy GridSearchCV/huấn luyện mô hình khi khởi động/đăng nhập" and does nothing. No `.fit()` call
exists on the login path.

**Safe:**
> "Model sau huấn luyện được lưu ở trạng thái Candidate. Việc huấn luyện không tự động thay thế
> model Production. Model chỉ chuyển sang Production thông qua quy trình promotion có kiểm soát
> (Admin-gated); model Production cũ sau đó chuyển sang Archived. Đăng nhập/khởi tạo phiên làm
> việc không tự động huấn luyện mô hình mới — chỉ tái sử dụng model Production đã có sẵn nếu tồn
> tại."

**Must NOT claim:**
> "Model Registry chỉ là khái niệm nhị phân (Production/không Production)." (stale — the
> 3-state lifecycle is genuinely implemented.)

---

## 6. ADMIN USER MANAGEMENT

**Read:** YES. **CRUD:** NO — verified by reading the full user-management section of
`admin_settings.py`: a single `st.dataframe()` call, zero create/edit/role-change/deactivate/
delete controls.

**Safe:**
> "Admin có thể xem danh sách tài khoản, vai trò và phương thức cấp phát hiện tại trong hệ
> thống."

**Must NOT claim:**
> "Admin có đầy đủ chức năng quản lý tài khoản (CRUD)."

This is documented as an intentional scope gap, not an oversight to patch reflexively: building
account CRUD safely requires deciding an authoritative user store, organization isolation rules,
password/auth ownership, a safe ID strategy, audit logging, and role-mutation rules first — none
of which were in scope for this pass.

---

## 7. CONCURRENCY

**Configured limit:** `MAX_CONCURRENT_REQUESTS = 3` (`dss/config.py`) — unchanged this session.

**What it limits:** a `threading.Semaphore(3)` in `llm_gateway.py`, acquired once per
`LLMGateway.stream_generate()` call (i.e., every AI chat/plan-generation request across all
roles), with a 45-second acquire timeout. It does **not** limit non-AI requests (dataset
upload, training, RAG document listing, etc. are unaffected). On timeout, the request used to
silently fall back to fabricated "Demo" content regardless of environment — this was found and
fixed this session (DEMO-CONCURRENCY-001): in REAL_LMS mode it now returns an honest "system is
overloaded, try again" message instead.

**Load-tested capacity:** NOT VERIFIED. No load-testing evidence exists in this codebase for
this constant; `3` is a hard-coded default, not derived from measurement.

**Safe:**
> "Hệ thống hiện giới hạn tối đa 3 yêu cầu gọi AI đồng thời (semaphore ở LLM Gateway) để kiểm
> soát tải/chi phí provider; ngưỡng này chưa được tối ưu bằng kiểm thử tải, và khi vượt ngưỡng,
> hệ thống trả về thông báo trung thực thay vì nội dung giả lập (đã sửa trong đợt audit này)."

**Must NOT claim:**
> "Hệ thống đã được tối ưu/kiểm thử cho khả năng mở rộng cao." / any specific "supports N
> concurrent users" number — none has been measured.

---

## 8. RAG LOW-RELEVANCE BEHAVIOR

**Forced weak fallback:** NO. **Empty/no-evidence result allowed:** YES.

Verified concrete mechanism (`dss/config.py`):
- `RAG_LOW_CONFIDENCE_FLOOR = 0.55` — if the top-ranked document's similarity score is below
  this floor, the system returns status `NO_RELEVANT_EVIDENCE` with an empty result list rather
  than forcing any document.
- `RAG_RELATIVE_THRESHOLD = 0.85` — among documents that clear the floor, only those within 85%
  of the top score are kept, filtering out weakly-related matches even when *some* result exists.

This is exercised by an existing, passing test
(`tests/test_lms_ai_rag_gateway.py::test_10_retrieval_returns_no_relevant_evidence_on_low_confidence`)
using a mock low-confidence provider, plus cross-course isolation tests
(`test_08_rag_namespace_isolation_and_permissions`,
`test_learning_explainer_acceptance.py::test_09_cross_course_retrieval_blocked`).

**Safe:**
> "Hệ thống áp dụng ngưỡng kiểm soát chất lượng truy xuất (RAG_LOW_CONFIDENCE_FLOOR = 0.55,
> RAG_RELATIVE_THRESHOLD = 0.85, dss/config.py). Khi điểm liên quan cao nhất dưới ngưỡng, hệ
> thống trả về trạng thái NO_RELEVANT_EVIDENCE (không có nguồn phù hợp) thay vì ép dùng một tài
> liệu ít liên quan."

**Must NOT claim:** any different numeric threshold than the two above — these are the actual
configured values, not invented for the defense.

---

## 9. DEAD CODE / RBAC

`render_role_switcher()` (plus 2 more functions in the same call chain,
`set_current_role()`/`_on_role_switch()`, found during this session's investigation) were dead
code from the pre-login-gate architecture — zero real callers anywhere in the repo. Removed this
session. The live, real RBAC path is unchanged: `auth_service.render_login_gate()` →
`current_role` → `TAB_ACCESS`/`filter_tabs_for_role()`.

**Safe:** "RBAC hoạt động qua một cổng đăng nhập xác thực thật duy nhất; mã nguồn tự-chọn-vai-trò
cũ (không mật khẩu) đã được xác nhận không còn điểm gọi nào và đã được dọn dẹp."

---

## 10. Summary table for quick reference

| Claim area | Implemented? | Safe headline claim |
|---|---|---|
| Database | PARTIAL/HYBRID | "PostgreSQL used for RAG vector storage" — but note the stub caveat above when asked to elaborate |
| Knowledge Base | Create+Read+Delete (Update still absent) | "Real multi-format ingestion, retrieval, and guarded deletion — still PARTIAL CRUD (no Update)" |
| LMS | NOT integrated | "Architecture prepared for LMS integration" |
| CMS | NOT integrated (external); internal repository IS real | "Internal content repository supports CMS-style flows" |
| Model Registry | YES, real lifecycle | "Candidate → controlled promotion → production/archived" |
| Admin User Mgmt | Read-only | "Admin can inspect current user information" |
| Concurrency | Configured=3, untested | "Limits concurrent AI calls; not load-tested" |
| RAG low relevance | Refuses weak evidence | "Can return no-suitable-source instead of forcing a weak match" |
