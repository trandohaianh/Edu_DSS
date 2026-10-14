# FINAL Acceptance Matrix — EduDSS

Phiên: "FINAL PRODUCTION GAP CLOSURE" (2026-09-26). Nhãn CHỈ dùng: `VERIFIED`, `TESTED`, `PARTIAL`, `NOT IMPLEMENTED`, `BLOCKED`. Không gộp thành 1 PASS chung — mỗi khía cạnh báo riêng (Phần 48).

| Area | Requirement | Status | Evidence | Test | Runtime | Limitation |
|---|---|---|---|---|---|---|
| **AI CORRECTNESS** | Chat prompt thật tới đúng provider; RAG 1 nguồn duy nhất cho prompt+UI+citation | `TESTED` | H-1 (`58a170f`), H-2 (`a62264e`) | `test_llm_gateway_chat_routing.py`, `test_generate_personalized_advice_prefetched_docs.py` | Test qua public API, fake provider ghi lại giá trị thật | Chưa chạy với provider AI thật (không có API key thật trong môi trường này) |
| **AI ERROR HANDLING** | Timeout/Retry/Circuit Breaker/Failover/Safe Fallback/Correlation ID | `PARTIAL` | H-3 (`bb19ee8`), Correlation ID (`102e84f`) | `test_llm_gateway_failover_on_friendly_error.py`, `test_llm_gateway_correlation_id.py` | Test thật | Circuit Breaker CHƯA xây; timeout tường minh chỉ có ở Ollama |
| **RAG GOVERNANCE** | PENDING/REJECTED/APPROVED/tampered/tenant filtering, 1 nguồn truy xuất | `TESTED` | Đợt trước (NHÓM F) + H-2 đợt này | `test_rag_retrieve_unified_context.py` và nhiều file khác | Test thật, `LocalVectorStore` | Chưa test trên `PgVectorStore` thật |
| **ML GOVERNANCE** | Model registry, provenance, drift | `PARTIAL` | Kế thừa `FINAL_CAPABILITY_MATRIX.csv` (cũ) | Kế thừa, chưa tự re-run trong phiên này | Không | `evaluate_drift()` không có UI nào gọi (code chết đã biết từ trước) |
| **REGULATION ENGINE** | University→Program→Cohort→Regulation Version, `resolve_regulation()` | `TESTED` (thuật toán) / `NOT IMPLEMENTED` (backend Postgres) | `beab12c` | `test_regulation_resolver.py` (10 test), `test_regulation_store.py` (4 test) | Test thật, JSON store cục bộ | Chưa có bảng Postgres/migration; CHƯA wire vào UI/prompt AI |
| **RULE ENGINE** | Prerequisite/credit limit/graduation eligibility, ALLOW/DENY/WARNING | `NOT IMPLEMENTED` | — | — | — | Chưa xây trong phiên này (quyết định có chủ đích, tránh code vội chưa kiểm chứng) |
| **CALCULATOR** | GPA còn lại cần đạt, deterministic, validate đầy đủ | `TESTED` (thuật toán) | `beab12c` | `test_gpa_calculator.py` (10 test) | Test thật | CHƯA wire vào UI/prompt AI (LLM chưa dùng kết quả này thay vì tự tính) |
| **AGENT** | Orchestrate (không phải decision engine), RBAC/tenant/timeout/audit | `PARTIAL` | `dss/services/admin_agent.py` (đã có từ trước) | Chưa xác nhận có test riêng trong phiên này | Chưa xác minh | Chỉ có Admin Agent (phạm vi hẹp: vận hành hệ thống) — không có agent học vụ tổng quát |
| **VALIDATOR** | Kiểm numbers/tenant/authorization/citations sau LLM | `PARTIAL` | `citation_service.verify_citations` (đợt trước) | Test thật (đợt trước) | Test thật | Chỉ kiểm trích dẫn nguồn — KHÔNG có validator số liệu (GPA/tín chỉ AI tự nêu) |
| **PRIVACY** | Pseudonymization, data minimization, không lộ PII | `TESTED` | `privacy_service.py` (đợt trước) | `test_governance_services.py::test_pseudonym_*` — 3 test re-run trong phiên đợt trước | Test thật, re-run xác nhận | Chưa có tầng "Authorization" tập trung riêng biệt |
| **RBAC** | Phân quyền theo vai trò, fail-closed | `TESTED` | `dss/core/roles.py` (TAB_ACCESS), nhiều service `@require_role` | Nhiều test qua các đợt trước | Test thật | — |
| **RLS** | Row-Level Security tenant isolation (Postgres) | `PARTIAL` (kế thừa, chưa tự verify) | CSV cũ: "83/83 RLS+security tests" (thời điểm trước nhánh này) | Kế thừa | **KHÔNG runtime-verify trong phiên này** | `BLOCKED_BY_RUNNING_SIMULATION` — không tự chạy lại được |
| **TENANT ISOLATION** | Cross-tenant data không rò rỉ | `PARTIAL` — khác nhau theo backend | `PgVectorStore` có RLS (kế thừa); `LocalVectorStore` (đang chạy) KHÔNG có organization_id; `regulation_resolver.py` (mới) fail-closed tenant filtering có test | `test_regulation_resolver.py::test_cross_tenant_regulation_never_leaks` | Test thật cho Regulation; Postgres RLS kế thừa chưa tự verify | `LocalVectorStore` không phải multi-tenant theo thiết kế (dev-only fallback), phải dùng Postgres cho tenant isolation thật |
| **POSTGRES** | Migration additive, upgrade/downgrade, chạy được trên DB thật | `BLOCKED` | `tools/validate_migration_isolated_postgres.sh` (đợt trước, đã chuẩn bị) | — | **CHƯA CHẠY** | `BLOCKED_BY_RUNNING_SIMULATION` |
| **PGVECTOR** | Semantic retrieval thật qua Postgres | `BLOCKED` | Kế thừa CSV cũ ("Real reindex+retrieval") | Kế thừa | Chưa tự re-run | `BLOCKED_BY_RUNNING_SIMULATION` |
| **LMS/CMS** | Tích hợp LMS/CMS thật hoặc giả lập | `PARTIAL` | Chỉ có giả lập (`lms_connector.py`, simulator) | — | Giả lập 72h đang chạy (không đụng vào) | Chưa từng kết nối LMS thật ngoài (đã biết từ trước, disclosed) |
| **OBSERVABILITY** | `@observed`/`record_operation`, correlation ID | `PARTIAL` | `dss/core/observability.py` (đã có), Correlation ID mới thêm cho AI Gateway | — | Chưa tự kiểm tra dashboard/alerting thật | Correlation ID mới chỉ có trong `stream_generate`, chưa lan toàn hệ thống |
| **RECOVERY** | Backup/restore DB + non-DB | `PARTIAL` (kế thừa) | CSV cũ: "Part F: real backup, checksum verify, restore" | Kế thừa | Chưa tự re-run trong phiên này | Non-DB restore orchestration chưa có (tự CSV cũ disclaim) |
| **UI/UX** | Tối giản, không icon trang trí, tiêu đề ngắn | `PARTIAL` | `8607cda`, `UI_UX_AUDIT.md` | Test source-inspection (`test_student_information_architecture.py`) | **Screenshot thật đã chụp** (17 ảnh, Playwright) | Nhiều trang chưa chụp ảnh; icon còn ở toolbar chung/card header viết HTML riêng |
| **ACCESSIBILITY** | Contrast/keyboard/focus/labels | `NOT VERIFIED` | — | — | — | Chưa kiểm tra trong phiên này (ngoài phạm vi thời gian) |
| **PERFORMANCE** | Latency hợp lý cho thao tác thường | `NOT VERIFIED` | — | — | — | Chưa đo trong phiên này |
| **CONCURRENCY** | Giới hạn đồng thời AI Gateway | `TESTED` (mức giới hạn cơ bản) | `_GATEWAY_SEMAPHORE` (đã có từ trước) | Gián tiếp qua `test_production_demo_policy.py` | — | Chỉ giới hạn số cuộc gọi AI đồng thời, không phải toàn hệ thống |
| **20K SCALE** | Batch inference (KHÔNG phải concurrent users) | `PARTIAL` (kế thừa, đã tự disclaim đúng) | CSV cũ: "2.5498s / 7843.8 predictions/sec" | Kế thừa, chưa tự re-run | Không | CSV cũ đã tự phân biệt đúng batch vs concurrent — không mâu thuẫn với Q34 |
| **50K SCALE** | 50.000 concurrent request | `NOT IMPLEMENTED` | — | — | — | Không có kiến trúc LB/multi-instance trong `docker-compose.yml` hiện tại của worktree này |
| **<1.5s SLO** | p95 < 1.5s tại 50K concurrent | `NOT VERIFIED` | — | — | — | Phụ thuộc 50K SCALE (chưa có hạ tầng để đo) |
| **HTTPS/TLS** | Reverse-proxy/TLS termination | `NOT VERIFIED` | — | — | — | Ngoài phạm vi phiên này |
| **CI/CD** | Hosted CI pipeline | `NOT VERIFIED` trong phiên này | Có nhánh `release/phase14-cicd-final-gate` (worktree khác) | — | — | Chưa đối chiếu với worktree này |

## Ghi chú đọc bảng

- `TESTED` = có test tự động, đã tự chạy lại trong phiên này (hoặc phiên gần nhất của CHÍNH nhánh này) và pass.
- `PARTIAL` = một phần đã kiểm chứng, phần còn lại kế thừa/chưa verify/có giới hạn rõ ràng đã ghi ở cột Limitation.
- `BLOCKED` = không thể tự kiểm chứng trong phiên này do ràng buộc an toàn (72h simulation đang chạy).
- `NOT VERIFIED` = không thuộc phạm vi công việc đã làm trong phiên này (không phải "đã kiểm tra và fail").
- `NOT IMPLEMENTED` = code không tồn tại.

**Không có dòng nào dùng "VERIFIED" một mình cho bất kỳ thứ gì liên quan PostgreSQL/pgvector thật trong phiên này** — đúng yêu cầu Phần 8/50.
