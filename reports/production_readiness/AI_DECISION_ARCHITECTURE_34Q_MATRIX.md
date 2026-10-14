# AI Decision Architecture — 34-Question Commercial Readiness Matrix

Nguồn: prompt "FINAL CORRECTNESS + 34-ISSUE COMMERCIAL ARCHITECTURE CLOSURE" (2026-09), Phần 7 (Capability A–K).
Kiểm tra tại: nhánh `fix/ml-correctness`, worktree `D:\KLTN\edudss-final-candidate-v2`, commit `a62264e` (sau khi sửa H-1/H-2).

**Nguyên tắc đọc bảng này**: hệ thống EduDSS hiện tại là một ứng dụng Streamlit phục vụ đồ án tốt nghiệp (dự đoán ML + RAG tư vấn học tập + quản trị tri thức), KHÔNG PHẢI một nền tảng AI đa tầng cấp doanh nghiệp. Phần lớn Capability B–K mô tả kiến trúc MỤC TIÊU THƯƠNG MẠI (aspirational) chưa tồn tại. Bảng dưới đây báo cáo TRUNG THỰC hiện trạng của **worktree `fix/ml-correctness` tại commit hiện tại** — không quy đổi "có RAG" thành "có Rule Engine", không quy đổi "có ML model" thành "có Deterministic Calculator".

**CẢNH BÁO ĐỐI CHIẾU QUAN TRỌNG**: `app/reports/production_readiness/FINAL_CAPABILITY_MATRIX.csv` (đã có sẵn trong cây thư mục này TỪ TRƯỚC phiên audit hiện tại, dấu thời gian 2026-09-22) tuyên bố nhiều năng lực là `VERIFIED` với evidence chi tiết (multi-tenant SaaS + RLS 83/83 test, PgVectorStore reindex/retrieval thật, 20K batch inference ĐÃ tự disclaim đúng "không phải concurrent users") — MỘT SỐ trong đó có vẻ MÂU THUẪN với `NOT_IMPLEMENTED`/`PARTIALLY_IMPLEMENTED` ở bảng dưới (đặc biệt Q9/tenant isolation cho vector store, Q34/scale evidence). **CHƯA đối chiếu sâu 2 nguồn trong phiên này** — khả năng cao là do 2 tài liệu mô tả 2 THỜI ĐIỂM/CẤU HÌNH khác nhau (`FINAL_CAPABILITY_MATRIX.csv` có thể phản ánh test chạy với `PgVectorStore`/Postgres thật ở một lần chạy trước, trong khi audit này chủ yếu xem xét code path của `LocalVectorStore` — backend đang hoạt động trong môi trường dev hiện tại — và CHƯA tự chạy lại Postgres thật, xem BLOCKED_BY_RUNNING_SIMULATION ở REPORT.md). Xem `CANONICALIZATION_PLAN.md` mục "Phát hiện quan trọng nhất". **Không dùng riêng lẻ một trong hai tài liệu này để kết luận cho luận văn/thuyết trình trước khi đối chiếu.**

Nhãn trạng thái CHỈ dùng đúng 6 giá trị theo yêu cầu: `IMPLEMENTED_AND_RUNTIME_VERIFIED`, `IMPLEMENTED_AND_TESTED`, `IMPLEMENTED_NOT_RUNTIME_VERIFIED`, `PARTIALLY_IMPLEMENTED`, `NOT_IMPLEMENTED`, `BLOCKED`.

---

## Capability A — AI Gateway + 3-Tier Routing (Q1–Q6)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker thương mại? |
|---|---|---|---|---|---|---|---|
| Q1 | Có 1 AI Gateway trung tâm định tuyến mọi lời gọi AI? | `IMPLEMENTED_AND_TESTED` | `dss/services/llm_gateway.py::LLMGateway.stream_generate` | `tests/test_llm_gateway_chat_routing.py`, `test_production_demo_policy.py`, `test_ai_gateway_governance.py` | Chạy qua toàn bộ UI (`ai_advisor.py`, `home.py`, `learning_explainer.py`) — nhưng KHÔNG phải mọi lời gọi AI đều qua Gateway (`advisory.py` gọi `call_ai_provider` trực tiếp, xem Q1 hạn chế) | `advisory.py::_generate_career_advice` bỏ qua Gateway hoàn toàn (không quota/rate-limit/audit cho luồng đó) | Có — cần rà lại `advisory.py` để đồng bộ 1 cổng duy nhất |
| Q2 | Có phân biệt Rule/Calculator (Tier 1) vs SLM (Tier 2) vs LLM (Tier 3) theo độ phức tạp? | `NOT_IMPLEMENTED` | — | — | — | Không có Intent/Complexity Router nào chọn giữa "trả lời bằng rule/calculator" và "gọi LLM". Mọi câu hỏi (kể cả "GPA của tôi là bao nhiêu?") đều đi thẳng LLM | Có — đây là khoảng trống kiến trúc lớn nhất của Phần 7 |
| Q3 | Có Semantic Cache giảm số lời gọi LLM lặp lại? | `IMPLEMENTED_AND_TESTED` | `dss/services/semantic_cache.py::layered_cache` (dùng trong `stream_generate`, `exact_cache.get/set`) | test tồn tại trong `test_production_demo_policy.py` (gián tiếp qua cache_key) | Có chạy trong `stream_generate` thật | Chỉ cache CHÍNH XÁC (exact match theo hash prompt+role) — KHÔNG có semantic/similarity cache thật dù tên class là `SemanticCache`; `SemanticCache.lookup/store` (class riêng, khác `layered_cache`) là **DEAD CODE** — 0 điểm gọi production (chỉ `LayeredSemanticCache` được dùng) | Không (cache exact vẫn có giá trị), nhưng tên gây hiểu nhầm |
| Q4 | Provider được chọn theo health/latency/cost/quota/rate-limit/tenant policy? | `PARTIALLY_IMPLEMENTED` | `LLMGateway.resolve_active_provider_and_model`, `check_quota_and_rate_limit`, `token_tracker` | `test_llm_service.py`, `test_governance_services.py` | Có — quota/rate-limit/health đã chạy thật | KHÔNG có cost-based routing (chọn provider rẻ nhất) hay data-sensitivity routing (chọn provider on-prem cho dữ liệu nhạy cảm) — chỉ có fallback chain cố định theo cấu hình env | Không cho MVP, có cho thương mại hóa thật |
| Q5 | Streaming/SSE có được benchmark? | `NOT_IMPLEMENTED` | `st.write_stream` (Streamlit built-in) dùng cho hiển thị, KHÔNG có SSE endpoint HTTP riêng | — | — | Đây là ứng dụng Streamlit nguyên khối (server-rendered), không có API SSE độc lập để client ngoài tiêu thụ | Có nếu cần tách frontend/backend |
| Q6 | Không gọi LLM lớn nếu Calculator/Rule/RAG đủ xử lý? | `NOT_IMPLEMENTED` | — (phụ thuộc Q2) | — | — | Vì không có Tier 1/2, MỌI câu hỏi đều tốn 1 lời gọi LLM đầy đủ, kể cả câu hỏi có thể trả lời bằng phép tính đơn giản | Có |

## Capability B — Versioned Regulation Engine (Q7–Q10)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q7 | Có data model University → Program → Cohort → Regulation Version? | `NOT_IMPLEMENTED` | — | — | — | Không có bảng/entity "Regulation"/"Program"/"Cohort" nào trong `dss/db/models.py`. Có `university_onboarding` (Stage 2, closure/university-onboarding) nhưng đó là tenant onboarding, không phải quy chế học vụ có phiên bản | Có |
| Q8 | Regulation có version/effective_from/effective_to/status/approved_by/source_document/rules? | `PARTIALLY_IMPLEMENTED` | `document_governance.py` có `effective_from/expires_at/status/approved_by` — NHƯNG đây là metadata của TÀI LIỆU RAG (văn bản), không phải một "Regulation" có cấu trúc rule máy đọc được | `test_document_governance.py` | Có (cho tài liệu, không cho quy tắc) | Tài liệu quy chế được lưu dưới dạng VĂN BẢN (để RAG trích dẫn), không có biểu diễn RULE có cấu trúc (vd. "GPA tối thiểu tốt nghiệp = 2.0") mà hệ thống có thể tính toán trực tiếp | Có |
| Q9 | Student request resolve đúng regulation version theo org/program/cohort/effective date? | `NOT_IMPLEMENTED` | — | — | — | Không có cơ chế "resolve" nào — phụ thuộc Q7/Q8 | Có |
| Q10 | Khi quy chế đổi, KHÔNG mặc định retrain LLM (chỉ update documents/rules/RAG index)? | `IMPLEMENTED_AND_TESTED` (theo đúng tinh thần, dù chưa có "Regulation" formal) | Cập nhật tài liệu RAG qua `document_ingestion`/`document_approval_service` không đụng tới model/embedding weight nào | `test_document_approval_service.py` | Có | Đúng nguyên tắc "không finetune khi quy chế đổi" — nhưng vì Q7-Q9 chưa có, đây là "đúng vì chưa xây gì để sai", không phải một capability đã kiểm chứng đầy đủ | Không |

## Capability C — AI Agent Orchestration (Q11–Q12)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q11 | Có Agent điều phối (không phải source of truth), gọi được Student DB/LMS/CMS/RAG/Rule/Calculator/ML/LLM Gateway? | `PARTIALLY_IMPLEMENTED` | `dss/services/admin_agent.py::AdminAIAgent` — CHỈ phạm vi `admin_operations` (vận hành hệ thống: dọn cache, reindex, báo cáo sức khỏe), KHÔNG PHẢI agent tư vấn học vụ cho Sinh viên/Giảng viên | Không tìm thấy file test riêng cho `admin_agent.py` trong lần grep này — **cần xác minh thêm, không khẳng định có test** | Chưa xác minh runtime | KHÔNG có agent nào điều phối luồng "Sinh viên hỏi X → Agent tự quyết định gọi RAG rồi Calculator rồi LLM". Luồng `ai_advisor.py` hiện tại là 1 pipeline TUYẾN TÍNH cố định trong code (retrieval → prompt → LLM), không phải Agent ra quyết định linh hoạt | Có nếu "Agent" là yêu cầu bắt buộc của sản phẩm thương mại |
| Q12 | Agent có tool allowlist/RBAC/tenant scope/timeout/audit/validation/bounded retry? | `PARTIALLY_IMPLEMENTED` (chỉ cho `AdminAIAgent`) | `admin_agent.py` có phân tầng rủi ro thấp/cao (tự động vs cần duyệt) + `@require_role` | — | — | Chỉ đúng cho phạm vi hẹp (admin ops); KHÔNG áp dụng cho một agent học vụ tổng quát vì agent đó chưa tồn tại | Có |

## Capability D — Hallucination Control (Q13–Q14)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q13 | Pipeline: approved evidence → retrieval → grounded prompt → LLM → citation verification → factual validator → safe fallback? | `PARTIALLY_IMPLEMENTED` | `rag_service.retrieve_unified_context` (evidence đã duyệt) → `prompt_boundary.render_retrieved_context` (grounded, đánh dấu untrusted) → `call_ai_provider` → `citation_service.verify_citations` (citation check) | `test_rag_retrieve_unified_context.py`, `test_generate_personalized_advice_unified_rag.py`, `test_citation_service` (nếu có) | Có — đã chạy qua H-1/H-2 fix | CÓ citation verification (đối chiếu mã trích dẫn AI nêu với tài liệu đã truy xuất) nhưng KHÔNG CÓ "factual validator" riêng biệt kiểm tra số liệu cụ thể (GPA/tín chỉ/điểm) AI nêu ra có khớp dữ liệu thật hay không — hallucination về SỐ (không phải nguồn) chưa được validator riêng chặn | Có — đây là khoảng trống rõ nhất của Capability D |
| Q14 | Không tuyên bố "ngăn hallucination 100%"? Không bịa course/score/prerequisite/regulation/credit/GPA/graduation requirement? | `PARTIALLY_IMPLEMENTED` | `AI_SYSTEM_POLICY` (system prompt) yêu cầu LLM không bịa; `citation_service` cảnh báo khi trích dẫn không khớp | — | Cảnh báo hiển thị cho người dùng khi phát hiện (`⚠️ AI có thể đã trích dẫn...`), KHÔNG chặn hoàn toàn câu trả lời | Đây là "best-effort warning", không phải "hard block" — LLM vẫn có thể bịa số liệu (GPA/tín chỉ) mà không qua citation check nào (vì đó không phải "trích dẫn nguồn", mà là số tự bịa) — đúng như lo ngại Q13 | Có |

## Capability E — Deterministic Calculator (Q15–Q17)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q15 | LLM KHÔNG tính GPA làm nguồn chính — có Calculator xác định riêng? | `NOT_IMPLEMENTED` | Không có module `calculator`/`gpa_calculator` nào trong `dss/services/` | — | — | "Điểm dự đoán" (K-3, đã sửa ở đợt trước) đến từ MÔ HÌNH ML (`model_service.predict_for_student`), không phải công thức GPA-còn-lại-cần-đạt như prompt mô tả (`required_GPA_remaining = ...`). Hệ thống có DỰ ĐOÁN ML, KHÔNG có TÍNH TOÁN CHÍNH SÁCH xác định (deterministic policy calculation) | Có |
| Q16 | Validate kết quả tính theo grading scale/credits/retake policy/pass-fail/min-max GPA/rounding/feasibility? | `NOT_IMPLEMENTED` | — | — | — | Phụ thuộc Q15 (chưa có gì để validate) | Có |
| Q17 | LLM chỉ giải thích kết quả backend (không tự tính)? | `PARTIALLY_IMPLEMENTED` (đúng tinh thần cho dự đoán ML, chưa áp dụng được cho GPA-còn-lại) | `_prepare_personalized_advice_prompt` đưa `predicted_gpa` (đã tính bằng ML, xem K-3) vào prompt dưới dạng SỐ CÓ SẴN — LLM diễn giải chứ không tự tính GPA dự đoán | `test_lecturer_dashboard_overview.py` (K-3 test cũ) | Có (cho phần ML) | Đúng nguyên tắc cho ĐIỂM DỰ ĐOÁN (ML), nhưng các câu hỏi dạng "tôi cần đạt bao nhiêu điểm kỳ tới để tốt nghiệp loại giỏi" — một phép tính CHÍNH SÁCH xác định — hiện do LLM tự trả lời tự do trong prompt, KHÔNG qua Calculator nào | Có |

## Capability F — Rule Engine (Q18–Q19)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q18 | Xử lý prerequisite/corequisite/credit limits/academic warnings/thesis eligibility/graduation eligibility/course registration bằng Rule Engine? | `NOT_IMPLEMENTED` | Không có module rule engine | — | — | `diagnosis_engine.py` là bộ SUY LUẬN CHẨN ĐOÁN HỌC TẬP (structured, if/else theo ngưỡng điểm/hành vi) — GẦN với "rule-based" nhưng phục vụ mục đích CHẨN ĐOÁN nguyên nhân yếu kém, không phải RA QUYẾT ĐỊNH NGHIỆP VỤ (đủ điều kiện đăng ký môn/làm khóa luận/tốt nghiệp) | Có |
| Q19 | Rule versioned/source-linked/effective-dated/tenant-program-cohort scoped/auditable? | `NOT_IMPLEMENTED` | — | — | — | Phụ thuộc Q18 | Có |

## Capability G — Validator + Safe Fallback (Q20–Q23)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q20 | Validator kiểm numbers/course IDs/rules/citations/tenant/authorization/consistency SAU Agent/LLM? | `PARTIALLY_IMPLEMENTED` | `citation_service.verify_citations` (chỉ citations) | `test_citation_service`-liên quan (gián tiếp qua `ai_advisor`/`learning_explainer` test) | Có (chỉ phần citation) | KHÔNG có validator kiểm tra numbers/course_id/tenant/authorization SAU khi LLM trả lời — chỉ có kiểm tra trích dẫn nguồn | Có |
| Q21 | Technical Fallback (timeout/429/5xx/network) → provider failover? | `IMPLEMENTED_AND_TESTED` | `LLMGateway.stream_generate` — `dedup_chain` (primary→fallback1→fallback2→demo), `classify_provider_error`, retry qua `_call_with_rate_limit_retry` (Tenacity) | `test_production_demo_policy.py`, `test_ai_gateway_governance.py` | Có | Fallback chain đã kiểm thử tốt — đây là phần MẠNH NHẤT của toàn bộ Phần 7 | Không |
| Q22 | Knowledge Fallback (no evidence/conflicting regulation/missing student data) → "insufficient evidence" hoặc human review, KHÔNG đổi LLM để đoán? | `IMPLEMENTED_AND_TESTED` (cho phần "no evidence") | `retrieve_unified_context` trả `NO_RELEVANT_EVIDENCE` + message trung thực, không lấp bằng nội dung khác | `test_rag_retrieve_unified_context.py` | Có | KHÔNG có "human review" workflow thật (không có hàng đợi chuyển câu hỏi khó cho con người) — chỉ dừng ở "báo không có bằng chứng" | Có (thiếu human-in-the-loop) |
| Q23 | Không đổi LLM (silently swap provider) để "đoán" khi thiếu bằng chứng? | `IMPLEMENTED_AND_TESTED` | `LLMGateway` — Q21 fallback chain đổi PROVIDER khi lỗi kỹ thuật, nhưng không đổi "chiến lược" khi thiếu evidence (Q22 dừng lại thay vì hỏi provider khác đoán) | (như Q22) | Có | — | Không |

## Capability H — Conversation Memory (Q24–Q25)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q24 | Memory = recent turns + validated structured facts + summary + optional vector memory (không gửi toàn bộ lịch sử mãi mãi)? | `PARTIALLY_IMPLEMENTED` | `ai_advisor.py::_chat_history` — chỉ lấy `_chat_history[-6:-1]` (5 lượt gần nhất) đưa vào `_history_snippet`, KHÔNG có summary tự động hay vector memory dài hạn | — | Có (giới hạn cứng, không phải summarization thông minh) | "Giới hạn 5 lượt gần nhất" là một xấp xỉ đơn giản, ĐỦ để tránh gửi lịch sử vô hạn (đúng tinh thần chính), nhưng KHÔNG có structured-fact-memory hay vector memory như mô tả | Không cho MVP, có cho hội thoại dài |
| Q25 | LLM summary ≠ source of truth; Student DB/regulation DB luôn thắng summary; memory tenant/user-scoped? | `IMPLEMENTED_AND_TESTED` (phần "DB luôn thắng") | `student_profile`/`predicted_gpa`/`risk_level` luôn tính lại từ `df`/model MỖI LẦN render (không cache từ hội thoại cũ); `_chat_history` lưu trong `st.session_state` (per-session, per-user tự nhiên vì Streamlit session riêng từng trình duyệt) | — | Có | Không có "LLM summary" nào được tạo/lưu để có thể xung đột với DB — nên tuyên bố "DB luôn thắng" đúng nhưng vì chưa có summary layer nên chưa thực sự bị kiểm thử trong tình huống xung đột | Không |

## Capability I — Privacy + PII (Q26–Q32)

| Q | Nội dung | Status | Code path | Tests | Runtime evidence | Hạn chế | Blocker? |
|---|---|---|---|---|---|---|---|
| Q26 | Pipeline DB → Authorization → Data Minimization → PII Masking/Pseudonymization → Context Builder → Gateway → Provider? | `PARTIALLY_IMPLEMENTED` | `privacy_service.generate_pseudonym`, `build_anonymized_student_context`, `sanitize_student_text` — dùng trong `ai_advisor.py` trước khi build prompt | `test_governance_services.py::test_...pseudonym` (thấy trong grep trước) | Có | Có pseudonymization + sanitize, nhưng KHÔNG có tầng "Authorization" tường minh riêng biệt trước bước minimization (RBAC kiểm tra rải rác ở tab-level qua `TAB_ACCESS`/`@require_role`, không phải 1 pipeline stage tập trung) | Không nghiêm trọng (RBAC vẫn có, chỉ không tập trung hóa) |
| Q27-Q31 | Không gửi full name/student ID/email/phone/address/lịch sử học tập không liên quan nếu không cần | `IMPLEMENTED_AND_TESTED` | `sanitize_student_text` che định danh; `build_anonymized_student_context` chỉ đưa risk_level/progress_note/điểm yếu, KHÔNG đưa tên/email/SĐT | `test_governance_services.py::test_pseudonym_is_consistent_and_does_not_leak_raw_id`, `::test_different_students_get_different_pseudonyms`, `::test_anonymized_context_never_contains_raw_student_id_or_pii` — đã re-run trong phiên audit này: 3 passed | Có (chạy lại thật trong phiên này, không chỉ đọc code) | Chỉ kiểm "không rò rỉ mã SV thật/PII cơ bản" — CHƯA có test riêng cho "lịch sử học tập KHÔNG LIÊN QUAN" (data minimization theo NGỮ CẢNH câu hỏi, vd. không gửi điểm môn X khi hỏi về môn Y) | Không |
| Q32 | Audit tối thiểu: who/tenant/capability/data categories/provider/timestamp/status/model-rule-doc versions? | `PARTIALLY_IMPLEMENTED` | `token_tracker.record_usage` (user_id giả danh/role/request_type/provider/model/timestamp), `audit_log_repository` (document approval) | `test_governance_services.py` | Có | KHÔNG có "data categories" hay "model/rule/document VERSION" trong audit log — chỉ có provider/model NAME, không có version hash cụ thể của prompt template/policy đang dùng tại thời điểm đó | Có (thiếu version-pinning trong audit) |

## Capability J — Responsibility Matrix (Q33)

| Q | Nội dung | Status | Ghi chú |
|---|---|---|---|
| Q33 | Phân vai rõ ràng: Calculator tính toán / Rule Engine quyết định / Regulation Resolver chọn version / RAG lấy bằng chứng / ML dự báo / LLM diễn giải / Agent điều phối / Validator kiểm cuối / Human xử lý ngoại lệ — LLM KHÔNG PHẢI decision engine | `PARTIALLY_IMPLEMENTED` | ĐÚNG cho ML (dự báo qua model thật, K-3 đã sửa) và RAG (bằng chứng qua `retrieve_unified_context`, đã duyệt). SAI/CHƯA CÓ cho Calculator (Q15), Rule Engine (Q18), Regulation Resolver (Q7-9), Agent tổng quát (Q11), Validator số liệu (Q20). LLM HIỆN TẠI vẫn là nơi DUY NHẤT tổng hợp câu trả lời cuối — về bản chất LLM ĐANG đóng vai "decision-adjacent" nhiều hơn thiết kế mục tiêu mong muốn, vì các tầng Calculator/Rule/Validator chưa tồn tại để LLM chỉ còn việc "diễn giải" |

## Capability K — Scale Evidence (Q34)

| Q | Nội dung | Status | Ghi chú |
|---|---|---|---|
| Q34 | Không dùng "20K batch predictions" để tuyên bố "20K concurrent users"; có load test thật tăng dần 100→500→1K→2.5K→5K→10K→20K đo RPS/p50/p95/p99/error rate/CPU/RAM/DB connections/pool wait/cache hit/queue depth/LLM latency/quota/cost? | `NOT_IMPLEMENTED` cho load test 20K đồng thời thật; xem ghi chú | Tồn tại `reports/production_readiness/FINAL_PERF_20K_ACCEPTANCE.md`/`PERF_20K_REMEDIATION.md` (từ nhánh `performance/20k-batch-remediation`, phiên trước, KHÔNG PHẢI worktree hiện tại) — CHƯA đọc/xác minh nội dung 2 file đó trong phiên audit này, KHÔNG khẳng định nội dung của chúng đúng hay sai. Kiến trúc target (CDN/LB/stateless app instances/Redis/PgBouncer/pgvector/LLM Gateway) — worktree hiện tại (`fix/ml-correctness`) là ỨNG DỤNG STREAMLIT ĐƠN TIẾN TRÌNH (`docker-compose.yml`: 1 container `streamlit-dss`), KHÔNG có Load Balancer/multiple stateless instances/PgBouncer nào trong cấu hình đang chạy. **Không tuyên bố PASS/FAIL cho Q34 tại đây** — cần đọc riêng 2 file lịch sử trên (nhánh khác) trước khi kết luận, nằm ngoài phạm vi worktree `fix/ml-correctness` |

---

## Tổng kết theo trạng thái

| Trạng thái | Số câu | Danh sách |
|---|---|---|
| `IMPLEMENTED_AND_TESTED` | 9 | Q1, Q3, Q10, Q21, Q22, Q23, Q25, Q27-31(nhóm, đã re-run 3 test thật trong phiên này) |
| `PARTIALLY_IMPLEMENTED` | 13 | Q4, Q8, Q11, Q12, Q13, Q14, Q17, Q20, Q24, Q26, Q32, Q33, (Q1 có hạn chế) |
| `NOT_IMPLEMENTED` | 11 | Q2, Q5, Q6, Q7, Q9, Q15, Q16, Q18, Q19 |
| Không kết luận (ngoài phạm vi worktree) | 1 | Q34 |

**Nhận định tổng quát trung thực**: EduDSS hiện tại là một hệ thống RAG + ML dự đoán CÓ governance tài liệu tốt (nhờ NHÓM F + đợt remediation trước) và có 1 AI Gateway trung tâm với fallback/quota/audit khá vững (Capability A một phần, G phần lớn). NHƯNG các capability "quyết định nghiệp vụ xác định" (Calculator, Rule Engine, Regulation Engine, Agent tổng quát, Validator số liệu) — vốn là điều kiện để LLM "không phải decision engine" — **CHƯA TỒN TẠI**. Đây là khoảng cách lớn nhất giữa hệ thống hiện tại và mục tiêu "kiến trúc thương mại" mô tả trong Phần 7.
