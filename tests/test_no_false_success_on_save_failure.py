"""FINAL PRODUCTION GAP CLOSURE — Phần 3/4/46 ("'success' giả"): audit 55
silent-except phát hiện 2 vị trí (`dashboard.py`::lưu điểm chỉnh sửa,
`warehouse_tab.py`::đồng bộ LMS giả lập) LUÔN hiện
`st.session_state.show_success_message = "✅ Đã lưu..."` NGAY SAU một khối
`try: wh.save_dataset(...) except Exception: pass` — nếu save thất bại
(disk đầy, lỗi ghi file...), lỗi bị nuốt thầm lặng nhưng người dùng vẫn
thấy thông báo THÀNH CÔNG, tưởng dữ liệu đã lưu lâu dài trong khi thực ra
chỉ tồn tại tạm trong phiên (mất khi tải lại trang/khởi động lại) — đúng
loại lỗi "hệ thống tưởng đã làm việc mà thực tế chưa làm" (Phần 46).

Kiểm tra bằng source inspection (đúng quy ước dự án cho code UI Streamlit
gắn với st.button/st.session_state khó test trực tiếp): xác nhận
show_success_message CHỈ được gán trong nhánh THÀNH CÔNG của try, và có
show_error_message trung thực trong nhánh except."""

from __future__ import annotations

import inspect
from pathlib import Path

from dss.tabs import dashboard, warehouse_tab

_APP_ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_grade_save_does_not_claim_success_on_write_failure():
    source = inspect.getsource(dashboard)
    idx = source.index("Lưu thay đổi điểm vào hệ thống")
    block = source[idx : idx + 1800]
    assert "_save_ok" in block, "Phải theo dõi trạng thái lưu thành công thật (không giả định luôn thành công)."
    assert "show_error_message" in block, "Phải có nhánh báo lỗi trung thực khi lưu thất bại."
    # show_success_message phải nằm trong nhánh `if _save_ok:` — kiểm tra thô bằng
    # cách xác nhận cụm "if _save_ok:" xuất hiện TRƯỚC show_success_message trong khối này.
    assert block.index("if _save_ok:") < block.index("show_success_message")


def test_warehouse_tab_lms_sync_does_not_claim_success_on_write_failure():
    source = inspect.getsource(warehouse_tab)
    idx = source.index("Đồng bộ dữ liệu từ LMS (Giả lập)")
    block = source[idx : idx + 2200]
    assert "show_error_message" in block, "Phải có nhánh báo lỗi trung thực khi warehouse.save_dataset() thất bại."
    # show_success_message phải nằm TRONG khối try (nhánh thành công), KHÔNG phải
    # sau try/except vô điều kiện như trước khi sửa.
    try_idx = block.index("try:")
    except_idx = block.index("except Exception:")
    success_idx = block.index('show_success_message = "✅ Đã đồng bộ dữ liệu từ LMS')
    assert try_idx < success_idx < except_idx, (
        "show_success_message phải nằm TRONG nhánh try (trước except), không phải "
        "sau khối try/except như hành vi cũ (luôn hiện thành công dù save thất bại)."
    )


def test_main_py_renders_show_error_message_counterpart():
    # dss/main.py là script top-level (chạy ngay khi import) — đọc file trực
    # tiếp thay vì import, đúng quy ước dự án (xem test_session_isolation.py).
    source = (_APP_ROOT / "dss" / "main.py").read_text(encoding="utf-8")
    assert "show_error_message" in source
    assert "st.error(st.session_state.show_error_message)" in source
