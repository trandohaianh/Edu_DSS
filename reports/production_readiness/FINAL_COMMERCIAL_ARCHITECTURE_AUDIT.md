# FINAL Commercial Architecture Audit — EduDSS

Phiên: "FINAL CORRECTNESS + 34-ISSUE COMMERCIAL ARCHITECTURE CLOSURE" (2026-09-25/26).
Worktree: `D:\KLTN\edudss-final-candidate-v2`. Branch: `fix/ml-correctness`. Không tạo branch mới, không merge, không push.

## 1. Starting branch/HEAD

`fix/ml-correctness` @ `167cb96f29b9534026a4542cf76d379eaa1575f8` (xác nhận khớp baseline yêu cầu trước khi sửa bất kỳ file nào — Phần 0).

## 2. Ending HEAD

`fix/ml-correctness` @ `a62264e76c0e678f275cc671e8957e0287d5041e`.

## 3. Commit list (phiên này)

```
58a170f fix(ai-gateway): H-1 CRITICAL - stream_generate() bo qua prompt that cua nguoi dung (advisor_chat/learning_explainer/home_quick_chat)
a62264e fix(rag): H-2 - loai bo truy xuat RAG hai lan doc lap cho cung 1 response ke hoach hoc tap
```

(Ngoài ra 2 file báo cáo mới — `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md`, `CANONICALIZATION_PLAN.md`, và file này — chưa commit tại thời điểm viết báo cáo này; sẽ commit cùng đợt cập nhật `REPORT.md`.)

## 4. Files changed

```
app/dss/core/models.py                                     |  21 ++-
app/dss/services/llm_gateway.py                             |  17 ++-
app/dss/tabs/ai_advisor.py                                  |  36 +++--
app/tests/test_generate_personalized_advice_prefetched_docs.py | 102 +++++++++
app/tests/test_llm_gateway_chat_routing.py                  | 154 +++++++++++
5 files changed, 318 insertions(+), 12 deletions(-)
```

## 5. H-1 result

**CONFIRMED, FIXED, TESTED.** `LLMGateway.stream_generate()` định tuyến tới `generate_personalized_advice(...)` một cách KHÔNG ĐIỀU KIỆN (`hasattr` check) bất kể `request_type`. Vì `MultiAIProvider` (llm_integration thật duy nhất) LUÔN có phương thức đó, nhánh `call_ai_provider(prompt, ...)` — nơi `prompt` thật sự được dùng — KHÔNG BAO GIỜ chạy tới trong thực tế.

**Phạm vi ảnh hưởng thật (audit toàn bộ 5 điểm gọi `stream_generate` trong `dss/`)**:
- `ai_advisor.py:1044` (`request_type="advisor_chat"`) — câu hỏi chat thật của người dùng bị bỏ qua. **BROKEN.**
- `learning_explainer.py:421` (`request_type="learning_explainer"`) — prompt giải thích bài giảng bị bỏ qua. **BROKEN.**
- `home.py:648` (`request_type="home_quick_chat"`) — câu hỏi nhanh Trang chủ bị bỏ qua. **BROKEN.**
- `ai_advisor.py:1359` (`request_type="advisor_plan"`) — ĐÚNG (đường duy nhất phải đi qua `generate_personalized_advice`).
- `advisory.py` (`career_advisor_chat`) — không qua Gateway, gọi `call_ai_provider(prompt, ...)` trực tiếp — KHÔNG bị ảnh hưởng.

Sửa: định tuyến theo `request_type in _PLANNING_REQUEST_TYPES` (`{"advisor_plan"}`) thay vì `hasattr`. Test (`test_llm_gateway_chat_routing.py`, đi qua public API, dùng fake provider ghi lại prompt thật nhận được — không mock nội bộ): 4/5 FAIL trên code gốc (Test 1 "prompt XYZ đến provider", Test 2 "2 prompt khác nhau", learning_explainer, home_quick_chat), PASS cả 5 sau khi sửa.

## 6. H-2 result

**CONFIRMED (rủi ro lý thuyết), FIXED, TESTED.** Sau khi hợp nhất RAG về `retrieve_unified_context` (đợt remediation trước), luồng "Tạo Kế hoạch Học tập" vẫn gọi hàm đó HAI LẦN ĐỘC LẬP cho cùng 1 response (1 lần build prompt, 1 lần sau khi stream xong để build khung "Bằng chứng & Nguồn tham khảo"/`verify_citations`) — rủi ro 2 tập tài liệu khác nhau nếu trạng thái duyệt đổi giữa 2 lần gọi.

Sửa: thêm `prefetched_relevant_docs` vào `generate_personalized_advice()`; `ai_advisor.py` truy xuất ĐÚNG 1 LẦN, tái dùng cho cả prompt LLM lẫn citation verification. Đường `_run_compare_ai`/`compare_providers` (chưa pre-fetch) không đổi hành vi. Test: 2/3 FAIL trên code gốc, PASS cả 3 sau sửa.

## 7. RAG call graph (sau H-1/H-2)

```
Question (chat)                    Question (plan)                  "So sánh AI"
     |                                    |                                |
     v                                    v                                v
_find_docs_rag_safe            _plan_relevant_docs =            compare_providers()
(preview/evidence panel)       _find_docs_rag_safe()             -> _run_one_provider()
     |                                    |                                |
     v                                    v                                v
retrieve_unified_context <----- (SAME call, cùng query) --------> generate_personalized_advice()
     |                                    |                        (KHÔNG pre-fetch — tự gọi
     v                                    v                         retrieve_unified_context
document_governance                prefetched_relevant_docs=       lần nữa, cùng hàm)
.is_document_usable()              _plan_relevant_docs (dùng lại,
(PENDING/REJECTED/expired/         KHÔNG gọi lại retrieve)
 tampered content_hash -> loại)             |
     |                                      v
     v                              generate_personalized_advice()
   chunks                            -> prompt LLM (CÙNG object
   (APPROVED only)                      với _docs_for_checklist)
                                              |
                                              v
                                    _docs_for_checklist = _plan_relevant_docs
                                    (KHÔNG gọi lại) -> verify_citations()
```

`_init_enhanced_knowledge_base` (19 tài liệu viết cứng) — KHÔNG còn nằm trên đường nào ở trên (production-dead, xem Mục 12). Chỉ còn dùng làm SEED SOURCE qua `legacy_knowledge_seed.py` (nạp thủ công, PENDING_REVIEW, cần Admin duyệt lại).

## 8. LLM Gateway call graph (sau H-1)

```
request_type            ->  routing decision                    ->  hàm thật sự dùng prompt
--------------------------------------------------------------------------------------------
"advisor_plan"           ->  generate_personalized_advice()      ->  tự build prompt từ
                                                                      student_weaknesses/predicted_gpa
                                                                      (BỎ QUA `prompt` truyền vào -
                                                                      ĐÚNG THIẾT KẾ, không phải bug)
"advisor_chat"            \
"learning_explainer"       >->  call_ai_provider(prompt, ...)    ->  DÙNG ĐÚNG `prompt` truyền vào
"home_quick_chat"         /                                          (sau H-1; TRƯỚC H-1: bị bỏ qua)
"career_advisor_chat"    ->  (không qua Gateway) call_ai_provider trực tiếp trong advisory.py
```

## 9. Embedding benchmark

Đã thực hiện ở đợt remediation trước (commit `4ac2541`, không lặp lại trong phiên này — không có thay đổi mã liên quan embedding). Tóm tắt: 23 truy vấn tiếng Việt, `all-MiniLM-L6-v2` (hiện tại) Recall@5=0.913/MRR=0.835 vs `paraphrase-multilingual-MiniLM-L12-v2` (ứng viên) Recall@5=0.957/MRR=0.957. Chưa đổi production. Xem `app/reports/ml_correctness/REPORT.md` Mục 10.6 và `embedding_benchmark_vi.txt`.

## 10. PostgreSQL validation

**BLOCKED_BY_RUNNING_SIMULATION** — không đổi trong phiên này. `docker ps` (chỉ đọc) xác nhận 7 container giả lập 72h/closure-C vẫn `Up 3 days`, không có container nào bị dừng/sửa/tạo mới trong phiên này. Script cô lập (`tools/validate_migration_isolated_postgres.sh`, từ đợt trước) vẫn sẵn sàng, chưa chạy. Migration mới chỉ xác minh tĩnh qua `alembic heads` — **KHÔNG dùng từ "VERIFIED" cho bất kỳ điều gì liên quan Postgres thật trong báo cáo này.**

## 11. 34Q matrix summary

Xem `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (đầy đủ). Tóm tắt: 9/34 `IMPLEMENTED_AND_TESTED`, 13/34 `PARTIALLY_IMPLEMENTED`, 11/34 `NOT_IMPLEMENTED`, 1/34 không kết luận được trong phạm vi worktree này (Q34). **Khoảng trống lớn nhất**: Deterministic Calculator (Capability E), Rule Engine (Capability F), Versioned Regulation Engine (Capability B), Agent tổng quát học vụ (Capability C, chỉ có Admin Agent hẹp) — đây là các cấu phần khiến "LLM is not the decision engine" (Capability J) chưa thực sự đúng: hiện tại LLM vẫn là nơi duy nhất tổng hợp câu trả lời cuối vì chưa có các tầng trên để nó "chỉ diễn giải".

**Phát hiện quan trọng cần đối chiếu**: `FINAL_CAPABILITY_MATRIX.csv` (có sẵn trong `production_readiness/` từ phiên trước, 2026-09-22) tuyên bố nhiều năng lực liên quan (multi-tenant RLS, PgVectorStore, 20K batch) là `VERIFIED` — có khả năng mâu thuẫn với một số kết luận `NOT_IMPLEMENTED`/`PARTIALLY_IMPLEMENTED` ở trên do khác thời điểm/cấu hình (Postgres thật vs `LocalVectorStore` dev). **Chưa đối chiếu sâu trong phiên này** — xem `CANONICALIZATION_PLAN.md`.

## 12. New issues discovered automatically (Phần 8 — system-wide audit)

| # | Phát hiện | Phân loại | Vị trí | Ghi chú |
|---|---|---|---|---|
| 1 | `LocalVectorStore` (backend dev/demo đang hoạt động trong môi trường này) KHÔNG có khái niệm `organization_id` — không lọc theo tenant | P2 (documented limitation, không phải bug mới) | `dss/services/vector_store.py` (class `LocalVectorStore`, dòng <273) | `PgVectorStore` (production) CÓ organization_id/RLS đầy đủ (dòng 273-531). `LocalVectorStore` được thiết kế RÕ RÀNG là "dev/demo fallback... không cần database ngoài" (docstring gốc) — không phải multi-tenant. KHÔNG sửa trong phiên này (rủi ro over-engineering một fallback không nhằm mục đích multi-tenant); ghi nhận rõ để không ai hiểu nhầm test chạy trên `LocalVectorStore` đã kiểm chứng cách ly tenant |
| 2 | `rag_service.retrieve_context()` — 0 điểm gọi production, chỉ 2 file test gọi trực tiếp | P3 (dead code, đã biết từ trước — trùng phát hiện A-6 cũ trong `ml_correctness/REPORT.md`) | `dss/services/rag_service.py:227` | KHÔNG đủ điều kiện xóa (có test phụ thuộc — vi phạm tiêu chí "0 test dependency") |
| 3 | `rag_service.retrieve_documents()` — 0 điểm gọi production (chỉ gọi nội bộ bởi `find_relevant_documents_rag`/test) | P3 (dead code, đã biết) | `dss/services/rag_service.py:195` | Cùng tình trạng #2 |
| 4 | `MultiAIProvider.find_relevant_documents()` (wrapper không `_rag`) — 0 điểm gọi | P3 (dead code, mới phát hiện lần audit này) | `dss/core/models.py:1617` | Wrapper gọi `find_relevant_documents_rag` — không ai gọi wrapper này trong `dss/` |
| 5 | `SemanticCache` (class riêng, khác `LayeredSemanticCache`/`layered_cache` đang dùng thật) | P3 (dead code, tên gây hiểu nhầm) | `dss/services/semantic_cache.py:97` | `stream_generate()` dùng `layered_cache.exact_cache` — CHỈ exact-match cache, KHÔNG phải semantic/similarity cache dù tên module là "semantic_cache" |
| 6 | `advisory.py` (Career Advisor chat) không đi qua `LLMGateway` | P2 | `dss/tabs/advisory.py:889` | Gọi `llm_integration.call_ai_provider(prompt, ...)` trực tiếp — bỏ qua quota/rate-limit/audit tập trung của Gateway (không bị lỗi H-1 vì không qua Gateway, nhưng cũng không có governance của Gateway) |
| 7 | 55 vị trí `except Exception: pass` (silent) trong `dss/` | P3 (đã spot-check 4/55, đa số là "best-effort secondary action", không swallow lỗi luồng chính) | Toàn `dss/` (danh sách đầy đủ trong log phiên) | KHÔNG sửa hàng loạt (rủi ro thay đổi hành vi không kiểm chứng được ở quy mô lớn trong 1 phiên) — 1 vị trí đáng chú ý nhất: `subscription_service.py:160` (parse ngày hết hạn hợp đồng lỗi -> im lặng bỏ qua thay vì fail-closed) — khuyến nghị xem lại riêng, KHÔNG sửa trong phiên này (ngoài phạm vi H-1/H-2) |
| 8 | ~50 file báo cáo "FINAL_*"/"PHASE*" có sẵn trong `production_readiness/` từ phiên trước | P2 (tài liệu, không phải code) | `app/reports/production_readiness/` | Có khả năng mâu thuẫn với audit độc lập mới — xem Mục 11 và `CANONICALIZATION_PLAN.md` |
| 9 | 50+ worktree/branch cho cùng dự án, nhiều cụm trùng lặp rõ rệt (observability ×7, phase13 ×5, phase14 ×4) | P2 (quản lý mã nguồn, không phải bug) | Toàn bộ `D:\KLTN\` | Xem `CANONICALIZATION_PLAN.md` — CHƯA đề xuất xóa gì, chỉ lập kế hoạch |

## 13. Deleted/deprecated code

**KHÔNG có file/hàm nào bị xóa trong phiên này** — đúng nguyên tắc "Muốn xóa phải chứng minh 0 test dependency"; các dead-code candidate (#2-5 ở Mục 12) đều có test phụ thuộc nên chỉ được DOCUMENT, không XÓA.

## 14. Full test results

Chạy 2 lần liên tiếp (Phần 10 yêu cầu), cùng lệnh:
```
cd D:/KLTN/edudss-final-candidate-v2/app
env -u DATABASE_URL -u PGVECTOR_URL LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2 PYTHONIOENCODING=utf-8 \
  d:/KLTN/code/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e --ignore=tests/load
```
Lần 1: **719 passed, 158 skipped, 0 failed** (194.12s).
Lần 2: **719 passed, 158 skipped, 0 failed** (193.15s).
Kết quả nhất quán giữa 2 lần chạy — không có test không ổn định (flaky) phát hiện được.

Mốc trước phiên này (baseline `167cb96`): 711 passed, 158 skipped, 0 failed. Tăng đúng 8 test mới (5 cho H-1 + 3 cho H-2).

## 15. Skipped test classification

Không đổi so với đợt trước (không có test mới bị skip trong phiên này) — xem `app/reports/ml_correctness/REPORT.md` Mục 10.8 (6 nhóm, tất cả hợp lệ, không skip bất thường).

## 16. Runtime evidence

- H-1/H-2: test đi qua PUBLIC API (`LLMGateway.stream_generate`, `MultiAIProvider.generate_personalized_advice`) với fake provider ghi lại giá trị THẬT nhận được — không mock nội bộ, không "giả xanh".
- Verify-before-fix đầy đủ cho cả 2 bug: `git diff` lưu patch → `git checkout` revert → chạy test xác nhận FAIL trên code gốc → `git apply` khôi phục → chạy test xác nhận PASS. Log đầy đủ trong lịch sử phiên làm việc.
- Full regression 2 lần liên tiếp — xem Mục 14.
- **Không có runtime evidence nào từ PostgreSQL/pgvector thật** trong phiên này (BLOCKED_BY_RUNNING_SIMULATION) — mọi kết luận liên quan Postgres trong 34Q matrix ghi rõ `PARTIALLY_IMPLEMENTED`/không kết luận, không dùng "VERIFIED".

## 17. Remaining blockers

1. Validation Postgres thật (migration + PgVectorStore + RLS) — chờ người dùng tự chạy `tools/validate_migration_isolated_postgres.sh` khi an toàn (72h simulation kết thúc).
2. Quyết định đổi embedding model (benchmark đã có, chưa quyết định).
3. Đối chiếu `FINAL_CAPABILITY_MATRIX.csv` (cũ) với `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (mới) — khả năng mâu thuẫn chưa được giải quyết.
4. 11 câu `NOT_IMPLEMENTED` trong 34Q matrix (Calculator, Rule Engine, Regulation Engine, 3-tier routing...) — đây là công việc kiến trúc lớn, nhiều tháng, KHÔNG thực hiện trong phiên này (tránh xây dựng vội, chưa kiểm chứng, vi phạm nguyên tắc "không tối ưu để test xanh").
5. 55 vị trí `except Exception: pass` — chỉ spot-check 4, chưa rà toàn bộ.
6. `advisory.py` career chat chưa đi qua LLM Gateway (thiếu quota/audit tập trung cho riêng luồng đó).

## 18. 72h simulation safety proof

`docker ps` chạy TRƯỚC (Phần 0) và trong suốt phiên xác nhận 7 container (`sim72h-edudss-streamlit-integration-1`, `edudss-postgres`, `edudss-lms-cms-simulator`, `sim72h-cms`, `sim72h-moodle`, `sim72h-moodle-db`, `edudss-closure-c-postgres`) đều `Up 3 days` liên tục, không container nào bị stop/restart/rm/build. Không lệnh `docker` nào khác ngoài `docker ps`/`docker stats`/`docker system df` (chỉ đọc) được chạy trong phiên này. Không `DATABASE_URL`/`PGVECTOR_URL` nào được set trỏ tới cổng 55530/55461 trong bất kỳ lệnh test nào (toàn bộ dùng `env -u DATABASE_URL -u PGVECTOR_URL`).

## 19. Canonicalization plan

Xem `CANONICALIZATION_PLAN.md` — kế hoạch tham khảo, CHƯA thực thi, không xóa/archive gì trong phiên này.

## 20. Explicit commercial readiness verdict (tách theo từng khía cạnh, KHÔNG gộp thành 1 chữ PASS)

| Khía cạnh | Verdict | Lý do ngắn gọn |
|---|---|---|
| **CORRECTNESS** | `PARTIALLY_VERIFIED` | H-1/H-2 (2 bug correctness nghiêm trọng nhất phát hiện được) đã sửa+test. Đợt remediation trước đã sửa ~24 lỗi khác (S-1, K-3, K-4, R-1...). Vẫn còn 11/34 capability chưa tồn tại (Calculator/Rule Engine) nên "đúng về nghiệp vụ" cho các câu hỏi tính toán chính sách phức tạp CHƯA được đảm bảo |
| **SECURITY** | `PARTIALLY_VERIFIED` | RBAC/fail-closed tốt ở tầng document governance + admin agent; PII pseudonymization có test thật (3 test re-run trong phiên này); CHƯA có validator số liệu sau LLM; CHƯA rà toàn bộ 55 silent-except |
| **TENANT ISOLATION** | `PARTIALLY_VERIFIED — KHÁC NHAU THEO BACKEND` | `PgVectorStore` (Postgres) CÓ RLS theo organization_id (chưa tự runtime-verify trong phiên này, BLOCKED_BY_RUNNING_SIMULATION); `LocalVectorStore` (backend đang chạy trong dev) KHÔNG có khái niệm tenant — chỉ chấp nhận được vì đây là fallback dev-only theo thiết kế, PHẢI ghi rõ trong tài liệu bán hàng/luận văn để không gây hiểu nhầm |
| **DATA GOVERNANCE** | `IMPLEMENTED_AND_TESTED` (cho tài liệu RAG) | `document_governance.py` đầy đủ trường yêu cầu (status/approved_by/content_hash/effective_from/expires_at...), fail-closed, đã test kỹ qua nhiều đợt |
| **ML GOVERNANCE** | `IMPLEMENTED_AND_TESTED` (theo `FINAL_CAPABILITY_MATRIX.csv` cũ, CHƯA re-verify trong phiên này) | Model registry/provenance/drift đã có theo tài liệu cũ — cần re-run để xác nhận vẫn đúng trên HEAD hiện tại trước khi trích dẫn |
| **RAG GOVERNANCE** | `IMPLEMENTED_AND_TESTED` | `retrieve_unified_context` là single retrieval authority thật (H-2 loại bỏ double-fetch), governance filter fail-closed, có test PENDING/REJECTED/APPROVED |
| **AI DECISION ARCHITECTURE** | `PARTIALLY_IMPLEMENTED` | Xem 34Q matrix Mục 11 — Gateway/fallback mạnh, nhưng thiếu Calculator/Rule Engine/Regulation Engine/Agent tổng quát/Validator số liệu |
| **OBSERVABILITY** | `NOT_INDEPENDENTLY_VERIFIED trong phiên này` | Có `dss/core/observability.py` (`@observed`, `record_operation`) dùng rộng rãi trong code đã đọc, nhưng CHƯA tự kiểm tra dashboard/alerting thật trong phiên này — có 7 worktree "observability-*" khác cần đối chiếu (xem `CANONICALIZATION_PLAN.md`) |
| **RECOVERY** | `NOT_INDEPENDENTLY_VERIFIED trong phiên này` | Có `reports/production_readiness/PHASE13_BACKUP_RECOVERY.md` (cũ) — chưa tự re-run backup/restore trong phiên này |
| **CONCURRENCY** | `NOT_IMPLEMENTED` (Tier routing) / `NOT_INDEPENDENTLY_VERIFIED` (mức khác) | `_GATEWAY_SEMAPHORE` giới hạn số cuộc gọi AI đồng thời (đã đọc code) nhưng chưa tự load-test |
| **20K SCALE** | `BLOCKED` (trong phạm vi worktree này) | Ứng dụng Streamlit đơn tiến trình đang chạy (`docker-compose.yml`: 1 container `streamlit-dss`) — không có LB/multiple instances trong cấu hình hiện hành của worktree này. `FINAL_PERF_20K_ACCEPTANCE.md` (cũ, nhánh khác) tuyên bố có batch-inference throughput test — KHÔNG kiểm chứng lại trong phiên này, và ngay cả nếu đúng, đó KHÔNG PHẢI bằng chứng 20K concurrent users (đúng cảnh báo Q34) |
| **LIVE LMS INTEGRATION** | `NOT_APPLICABLE` (theo `FINAL_CAPABILITY_MATRIX.csv` cũ, nhất quán với hiểu biết hiện tại) | Chưa từng kết nối LMS thật ngoài — chỉ có simulator |
| **HTTPS/TLS** | `NOT_VERIFIED trong phiên này` | Không kiểm tra cấu hình TLS/reverse-proxy trong phiên này — ngoài phạm vi H-1/H-2 |
| **HOSTED CI/CD** | `NOT_VERIFIED trong phiên này` | Có nhánh `release/phase14-cicd-final-gate` (khác worktree) — chưa đối chiếu trong phiên này |

**Kết luận cuối**: Hệ thống ĐÃ SẴN SÀNG cho mục đích bảo vệ đồ án tốt nghiệp với 2 bug correctness nghiêm trọng (H-1, H-2) vừa được phát hiện và sửa triệt để, có bằng chứng test rõ ràng. Hệ thống **CHƯA SẴN SÀNG** cho triển khai thương mại thật theo đúng nghĩa 34-Q matrix mô tả — khoảng cách lớn nhất là các tầng "quyết định nghiệp vụ xác định" (Calculator/Rule Engine/Regulation Engine) hoàn toàn chưa tồn tại, và scale 20K concurrent chưa có bằng chứng load-test thật trong phạm vi worktree này.

**Do NOT merge or push. Wait for review.**
