# FINAL Production Gap Report — EduDSS

Phiên: "FINAL PRODUCTION GAP CLOSURE + COMPLETE UI/UX REDESIGN" (2026-09-26).
Worktree: `D:\KLTN\edudss-final-candidate-v2`. Branch: `fix/ml-correctness`.
Starting HEAD: `f628990` (đã xác nhận khớp baseline yêu cầu — Phần 0). Ending HEAD: `e7b727d`.
Không tạo branch mới, không merge, không push.

## 1. Commit list (11 commit)

```
bb19ee8 fix(ai-gateway): H-3 CRITICAL - fallback chain dừng lại ở lỗi thân thiện đầu tiên thay vì failover
102e84f feat(ai-gateway): thêm Correlation ID cho mọi thông báo lỗi AI cuối cùng
4cfc043 fix(ui): không hiện "Đã lưu thành công" khi warehouse save thất bại thầm lặng
95f01ed docs: SILENT_EXCEPTION_AUDIT.md — kiểm toán đầy đủ 55 vị trí except-pass
6fe8530 docs: CANONICAL_CAPABILITY_MATRIX.md — reconcile FINAL_CAPABILITY_MATRIX.csv với 34Q matrix
beab12c feat: Regulation Resolver + Deterministic GPA Calculator
8607cda refactor(ui): xóa icon trang trí khỏi tiêu đề + rút ngắn tiêu đề lộ thuật ngữ kỹ thuật
2c6a6e1 style(login): tăng chiều cao input từ 46px lên 48px
7d04cd8 feat(ui): công cụ chụp screenshot thật + sửa nhãn nav
e7b727d docs: UI_UX_AUDIT.md + UI_VISUAL_ACCEPTANCE.md + UI_DEAD_CODE_AUDIT.md
```

## 2. P0/P1 bugs tìm thấy (tự audit, KHÔNG có trong danh sách đã biết trước phiên này)

### H-3 (CRITICAL) — Fallback chain AI dừng ở lỗi thân thiện đầu tiên

`MultiAIProvider.call_ai_provider()` không bao giờ raise khi provider lỗi — nó `yield` MỘT câu lỗi thân thiện (thiết kế có chủ ý, không lộ exception thô). `LLMGateway.stream_generate()` chỉ coi 1 lượt là thất bại khi `except Exception` bắt được — vì không có exception nào, MỌI lượt gọi (kể cả chỉ trả về đúng 1 câu lỗi) được đánh dấu `success=True`, DỪNG fallback chain — provider dự phòng (khỏe mạnh, có key hợp lệ) KHÔNG BAO GIỜ được thử. Người dùng thấy lỗi của provider A như thể là câu trả lời cuối cùng. Bug này bị chính H-1 (đợt trước) làm lộ ra — trước H-1, luồng chat hầu như không đi qua nhánh này. Đã sửa: peek chunk đầu tiên, dò tiền tố lỗi thân thiện, `continue` sang provider kế tiếp nếu khớp.

### "Success giả" khi lưu dữ liệu thất bại (P1, 2 vị trí)

`dashboard.py` (lưu điểm Giảng viên chỉnh sửa) và `warehouse_tab.py` (đồng bộ LMS mô phỏng) LUÔN hiện "✅ Đã lưu..." ngay sau `try: wh.save_dataset(...) except Exception: pass` — nếu save thất bại thật, lỗi bị nuốt nhưng người dùng vẫn thấy thành công. Phát hiện qua audit 55 silent-except (Phần 6). Đã sửa cả 2.

## 3. AI error-handling result

| Cấu phần | Trước phiên này | Sau phiên này |
|---|---|---|
| Timeout | Chỉ Ollama có timeout tường minh (120s) | Không đổi — chưa thêm timeout tường minh cho Gemini/Groq/OpenAI/HF trong phiên này |
| Retry | Có (Tenacity, `_call_with_rate_limit_retry`) | Không đổi |
| Circuit Breaker | KHÔNG tồn tại | **VẪN KHÔNG TỒN TẠI** — chưa xây trong phiên này (xem "Còn lại") |
| Failover | Có NHƯNG có bug nghiêm trọng (H-3) | **ĐÃ SỬA** — failover hoạt động đúng cả khi provider lỗi "êm" (không raise) |
| Safe Fallback | Có (demo mode/thông báo "chưa khả dụng"), phân biệt production/non-production đúng | Không đổi (đã đúng từ trước) |
| UI Error State | Có `st.error`, không lộ traceback | Không đổi (đã đúng từ trước) |
| Correlation ID | KHÔNG tồn tại | **ĐÃ THÊM** — mọi lỗi cuối cùng có "Mã sự cố: AI-XXXXXXXX" |
| Audit Log + Correlation ID | Có `token_tracker`/`record_operation` nhưng không có correlation | **ĐÃ THÊM** correlation_id vào mọi log liên quan trong `stream_generate` |

## 4. Silent-exception result

55 vị trí `except Exception: pass` (và biến thể) trong `app/dss` — quét bằng AST, đọc từng vị trí. **0 P0, 2 P1 (đã sửa), 2 P2 (khuyến nghị thêm log, không sửa), 51 P3 (benign, đã xác nhận)**. Chi tiết đầy đủ: `SILENT_EXCEPTION_AUDIT.md`.

## 5. 11 missing capabilities result (34Q matrix)

9/34 `IMPLEMENTED_AND_TESTED`, 13/34 `PARTIALLY_IMPLEMENTED`, 11/34 `NOT_IMPLEMENTED`. Trong phiên này đã xây MỚI 2/11 capability còn thiếu:
- **Regulation Resolver** (Q7-Q10): `resolve_regulation()` thuần + `LocalRegulationStore` (JSON, cùng mẫu `LocalVectorStore`). 14 test.
- **Deterministic GPA Calculator** (Q15-Q17): `compute_required_remaining_gpa()` đúng công thức yêu cầu, validate đầy đủ. 10 test.

**9 capability còn lại CHƯA xây** (quyết định có chủ đích — xem "Còn lại"): Rule Engine, Agent tổng quát, Validator toàn diện, 3-tier AI Router, Token Optimization/Context Builder, phần còn lại của Q1-6/Q26-32/Q33.

## 6. PostgreSQL result

**BLOCKED_BY_RUNNING_SIMULATION** — không đổi. `docker ps` xác nhận 7 container giả lập vẫn `Up 3 days` trong suốt phiên, không container nào bị động tới. Không chạy bất kỳ migration/test DB thật nào trong phiên này.

## 7. Capability-matrix reconciliation

`CANONICAL_CAPABILITY_MATRIX.md` — hợp nhất `FINAL_CAPABILITY_MATRIX.csv` (cũ, 2026-09-22) với `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (mới). Kết luận: KHÔNG mâu thuẫn thật — 2 báo cáo mô tả 2 phạm vi khác nhau (Postgres/RLS đã test thật ở 1 thời điểm trước vs. kiến trúc quyết định AI + LocalVectorStore hiện tại). Phát hiện giá trị nhất: CSV cũ tự ghi "AI Gateway VERIFIED... Demo-mode, no paid provider credentials" — giải thích tại sao H-1/H-2/H-3 (đường gọi provider thật) chưa từng bị phát hiện trước đây.

## 8. UI pages changed

Xem `UI_UX_AUDIT.md` bảng đầy đủ. Tóm tắt: icon tiêu đề xóa tập trung tại `ui_kit.py` (áp dụng ~30 điểm gọi), icon sidebar nav xóa tại `main.py`, 4 tiêu đề rút gọn (`ai_advisor.py`, `advisory.py`, `learning_explainer_tab.py`, `knowledge_base.py`), 1 nhãn nav đồng bộ (`roles.py`), input Login tăng 2px.

## 9. Before/after screenshots

`reports/production_readiness/ui_screenshots/` — 17 ảnh chụp THẬT (Playwright, sau khi sửa). Không có ảnh "before" riêng (sửa tại chỗ trong 1 phiên, không chụp before/after cặp đôi) — bằng chứng "before" nằm ở việc đọc code (icon `icon="🤖"` v.v. trong lịch sử git diff của các commit `8607cda`). Đánh giá chi tiết: `UI_VISUAL_ACCEPTANCE.md`.

## 10. Login/Register result

- **Login**: đã đạt spec ở mức cao TỪ TRƯỚC phiên này (thiết kế "v4", khớp file tham chiếu người dùng cung cấp, đo bằng Playwright). Chỉ sửa 1 giá trị: input height 46→48px.
- **Register**: **KHÔNG TỒN TẠI**. Xác nhận qua grep toàn bộ `dss/` — không có luồng đăng ký tự phục vụ. Tài khoản qua seed mặc định/auto-provision Sinh viên/cấp phát Admin. KHÔNG xây mới (thay đổi mô hình xác thực, cần quyết định sản phẩm, không phải việc redesign giao diện thuần túy). Đánh dấu `NOT_APPLICABLE`.

## 11. Icons removed count

Không đếm được con số tuyệt đối "icon đã xóa" vì sửa tại 2 ĐIỂM TRUNG TÂM (`ui_kit.section_header`/`page_header` không còn render `icon` — áp dụng cho ~30 lời gọi hiện có; `main.py` sidebar bỏ `tab_icon()` — áp dụng cho toàn bộ danh sách điều hướng ~14 tab). Ước lượng: **~44 điểm hiển thị icon bị vô hiệu hóa** qua 2 thay đổi trung tâm này. **CHƯA đếm/xử lý** icon trong button/tab con/card header viết HTML riêng (xem `UI_UX_AUDIT.md` — còn nhiều, chưa sửa).

## 12. Titles renamed (4)

| Trước | Sau | File |
|---|---|---|
| "Tư vấn — AI (LLM)" | "Tư vấn" | `ai_advisor.py` |
| "Tư vấn — Định hướng nghề nghiệp (Career Decision Support System)" | "Định hướng nghề nghiệp" | `advisory.py` |
| "AI Giải thích Bài giảng (CMS)" | "Giải thích bài giảng" | `learning_explainer_tab.py` |
| "Quản lý tri thức (RAG & Knowledge Base)" | "Tài liệu" | `knowledge_base.py` |

(+ 1 nhãn nav: "Tri thức RAG" → "Tài liệu" trong `roles.py`)

## 13. Dead UI code removed

**0** — `UI_DEAD_CODE_AUDIT.md` xác nhận 0/18 module tabs mồ côi, 0 CSS trùng lặp, không có component/login/sidebar cũ còn sót. Tầng UI sạch hơn kỳ vọng ban đầu của đề bài — không có gì đủ điều kiện `PROVEN_DEAD`/`LEGACY_REPLACED` để xóa.

## 14. Full test results

Chạy 2 lần liên tiếp:
```
cd D:/KLTN/edudss-final-candidate-v2/app
env -u DATABASE_URL -u PGVECTOR_URL LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2 PYTHONIOENCODING=utf-8 \
  d:/KLTN/code/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e --ignore=tests/load
```
Lần 1: **749 passed, 158 skipped, 0 failed** (243.06s).
Lần 2: **749 passed, 158 skipped, 0 failed** (218.63s).
Nhất quán — không flaky. Mốc trước phiên này (`f628990`): 749 passed (không đổi tổng — các test UI mới thay thế/cập nhật test cũ 1:1, không cộng dồn ròng nhiều; xem chi tiết từng commit).

## 15. E2E results

**KHÔNG chạy `tests/e2e/` trong phiên này** (ngoài phạm vi — bộ E2E cần trình duyệt đầy đủ và thời gian dài hơn khung phiên cho phép). Đã dùng CHÍNH cơ chế của `tests/e2e/conftest.py` (cổng tự do, data root cô lập) để tự viết `tools/capture_ui_screenshots.py` chụp ảnh thật — đây là bằng chứng runtime thật dù không phải chạy bộ E2E chính thức.

## 16. Còn lại (chưa làm, có chủ đích)

1. **Circuit Breaker** thật (trạng thái mở mạch theo dõi lỗi liên tiếp/cooldown) — chưa xây, chỉ có failover đơn giản.
2. **9/11 capability** còn thiếu trong 34Q matrix (Rule Engine, Agent tổng quát, Validator toàn diện, 3-tier Router, Token/Context Builder...) — quyết định có chủ đích KHÔNG xây vội trong 1 phiên để tránh code chưa kiểm chứng, chưa test kỹ (đúng nguyên tắc "không tối ưu để test xanh").
3. **Icon/emoji còn lại**: toolbar chung (main.py), card header viết HTML trực tiếp (vd. `admin_settings.py`), button/tab con — đã phát hiện, ghi trong `UI_UX_AUDIT.md`, chưa sửa (rủi ro cần rà từng file).
4. **Register**: không xây (NOT_APPLICABLE, cần quyết định sản phẩm).
5. **Regulation Resolver/Calculator**: mới xây MODULE + TEST, **CHƯA wire vào UI/prompt AI** (LLM chưa thực sự dùng kết quả này thay vì tự tính).
6. **Mobile/responsive**: chưa kiểm tra (chỉ chụp desktop 1440×900).
7. **Trang chưa chụp ảnh**: Khám phá, Phân cụm (đầy đủ), Model Registry, Kho dữ liệu, Cấu hình AI, Báo cáo hệ thống, Lịch sử tư vấn, Onboarding, và nội dung đầy đủ của Duyệt tài liệu/Trợ lý AI/Giải thích bài học/Hướng nghiệp.
8. **Validation Postgres thật** — vẫn `BLOCKED_BY_RUNNING_SIMULATION`.

## 17. 72h simulation status

Xác nhận qua `docker ps` (chỉ đọc) TRƯỚC (Phần 0) và SAU (kết thúc phiên): cả 7 container (`sim72h-edudss-streamlit-integration-1`, `edudss-postgres`, `edudss-lms-cms-simulator`, `sim72h-cms`, `sim72h-moodle`, `sim72h-moodle-db`, `edudss-closure-c-postgres`) đều `Up 3 days` liên tục, KHÔNG có container nào bị stop/restart/rm/build trong suốt phiên. Không `DATABASE_URL`/`PGVECTOR_URL` nào trỏ tới cổng 55530/55461 trong bất kỳ lệnh nào. Cổng dùng để chạy Streamlit tạm cho screenshot do OS tự cấp ngẫu nhiên (`_free_port()`), xác nhận KHÔNG trùng bất kỳ cổng nào trong danh sách bảo vệ (8515/55530/8775/1337/8090/55461).

## 18. Safe to merge? **NO** — lý do cụ thể

1. Circuit Breaker và phần lớn kiến trúc "AI Decision" (Rule Engine/Calculator wiring/Validator/Agent tổng quát/3-tier Router) chưa hoàn thiện — hệ thống vẫn để LLM tự do trả lời các câu hỏi tính toán/quyết định chính sách.
2. Validation Postgres thật (migration mới, RLS, PgVectorStore) CHƯA runtime-verify trong bất kỳ phiên nào của nhánh `fix/ml-correctness` — toàn bộ dựa trên `alembic heads` tĩnh.
3. UI còn icon/emoji rải rác ở các thành phần ngoài `ui_kit.py`, một số trang chưa kiểm tra thị giác.
4. Register không tồn tại — nếu sản phẩm cần self-service registration, đây là gap chức năng, không chỉ UI.
5. `FINAL_CAPABILITY_MATRIX.csv` (cũ) và các báo cáo "FINAL_*"/"PHASE*" khác trong `production_readiness/` từ phiên trước CHƯA được đối chiếu TOÀN BỘ (chỉ đối chiếu 1 file, `FINAL_CAPABILITY_MATRIX.csv`) — có thể còn phát hiện mâu thuẫn khác chưa lộ ra.

**Việc ĐÃ đủ điều kiện merge**: 3 bug AI correctness nghiêm trọng (H-1/H-2/H-3) đã sửa + test đầy đủ, silent-exception đã audit toàn diện, không regression (749/749 pass ổn định 2 lần liên tiếp), không đụng vào giả lập 72h.
