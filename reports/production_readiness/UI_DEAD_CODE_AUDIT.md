# UI Dead Code Audit — EduDSS

Phiên: "FINAL PRODUCTION GAP CLOSURE" (2026-09-26), Phần 42.

## Phương pháp

1. Liệt kê toàn bộ module trong `dss/tabs/` (18 file) — xác nhận TỪNG file có được `import`/gọi từ `dss/main.py` hay không.
2. Tìm CSS trùng lặp: kiểm tra có bao nhiêu file định nghĩa `<style>`/theme riêng ngoài `dss/styles/main.css`.
3. Tìm component/logo trùng lặp không có lý do.
4. Đối chiếu với các phát hiện dead-code Ở TẦNG SERVICE đã có từ các đợt audit trước (không lặp lại chi tiết — chỉ tham chiếu).

## Kết quả

| Hạng mục | Kết quả |
|---|---|
| Module UI mồ côi (không được `dss/main.py` import/gọi) | **0/18** — TẤT CẢ 18 file trong `dss/tabs/` đều được dùng thật (chỉ `__init__.py` không cần import trực tiếp, đúng quy ước package Python) |
| CSS trùng lặp | **0** — chỉ có đúng 1 file theme trung tâm (`dss/styles/main.css`), không có `<style>` block rải rác trong các file `dss/tabs/*.py` |
| Logo/brand mark lặp lại | 4 điểm (`main.py` sidebar, `home.py` landing hero, `loading_screen.py`, `auth_service.py` login) — **KHÔNG phải trùng lặp thừa**: mỗi nơi phục vụ 1 màn hình/trạng thái khác nhau (sidebar thường trực, trang chào mừng, màn tải, màn đăng nhập) — đây là mẫu hợp lý cho brand presence xuyên suốt nhiều màn hình riêng biệt, không phải code sao chép không cần thiết |
| Theme cũ/sidebar cũ còn sót | Không tìm thấy — không có file `*_old.py`/`*_legacy.py`/`*_v1.py` nào trong `dss/tabs/` |
| Login HTML/CSS cũ | File `login.html`/`login.css` (tham chiếu thiết kế gốc do người dùng cung cấp) nằm ở `D:\KLTN\code` (thư mục làm việc CHÍNH, KHÔNG PHẢI trong worktree `fix/ml-correctness`/repo Git này) — không thuộc phạm vi audit code base, không phải "dead code" trong ứng dụng |
| Component UI dùng chung trùng lặp | Không tìm thấy — `ui_kit.py` là ĐIỂM DUY NHẤT định nghĩa `section_header`/`page_header`/`kpi_row`/`render_badge`/`empty_state`/`error_state`/`metric_card`, không có bản sao nào khác |

## Phân loại (theo yêu cầu)

Không có phát hiện nào rơi vào `PROVEN_DEAD`, `LEGACY_REPLACED`, hoặc `DUPLICATE` ở tầng UI (`dss/tabs/`, `dss/styles/`, `ui_kit.py`). **Không xóa file/code nào trong phiên audit UI này** — không có gì đủ điều kiện.

Ghi chú tham chiếu (không thuộc phạm vi UI, đã audit ở tầng khác — xem `SILENT_EXCEPTION_AUDIT.md`/`FINAL_COMMERCIAL_ARCHITECTURE_AUDIT.md` đợt trước): `rag_service.retrieve_context()`, `rag_service.retrieve_documents()`, `MultiAIProvider.find_relevant_documents()`, class `SemanticCache` (khác `LayeredSemanticCache` đang dùng thật) — đều là code CHẾT ở tầng `dss/services/`, có test phụ thuộc nên KHÔNG đủ điều kiện xóa theo tiêu chí đã nêu (0 test dependency).

## Kết luận

Tầng UI của EduDSS **sạch bất thường** so với kỳ vọng ban đầu của Phần 42 (đề bài giả định có khả năng tồn tại "duplicate CSS/component/login cũ/sidebar cũ/logo trùng") — kết quả thật là KHÔNG có. Điều này phù hợp với phát hiện ở `UI_UX_AUDIT.md`: hệ thống đã qua nhiều đợt audit/dọn dẹp UI trước đó (Student/Lecturer/Admin Information Architecture audit, Login "v4"), nên phần lớn rác kỹ thuật đã được dọn từ các phiên trước, không phải phiên này mới phát hiện lần đầu.
