"""Technical logging — Phase 9 của kế hoạch refactor EduDSS (mục 13 bản yêu cầu).

Trước phase này, hệ thống KHÔNG có logging kỹ thuật nào cả (không `import
logging` ở đâu trong dss/) — thứ duy nhất được ghi lại là
`DataWarehouse.log_activity()`, vốn là NHẬT KÝ HOẠT ĐỘNG dành cho người dùng
xem lại (hiển thị trong UI, ví dụ "Huấn luyện thành công mô hình X"), không
phải log kỹ thuật cho việc vận hành/debug (không có mức độ nghiêm trọng, không
tách riêng khỏi dữ liệu hiển thị cho người dùng). Module này bổ sung ĐÚNG phần
còn thiếu đó — tách bạch 2 khái niệm:

    - `log_activity()` (dss/core/warehouse.py)  -> NGƯỜI DÙNG xem (lịch sử hoạt động)
    - `get_logger(__name__)` (module này)        -> NGƯỜI VẬN HÀNH/DEV xem (file log)

QUY TẮC BẮT BUỘC khi dùng logger từ module này: KHÔNG BAO GIỜ log mật khẩu, API
key, hoặc access token — kể cả khi log lỗi (message lỗi từ thư viện bên thứ 3
đôi khi vô tình chứa key trong URL/payload; nếu nghi ngờ, chỉ log loại lỗi,
không log message thô).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dss.core.data_root import get_data_root
from dss.core.observability import StructuredFormatter
from dss.security.log_redaction import install_log_redaction

_CONFIGURED = False


def _configure_once() -> None:
    """PERF-002: đường dẫn log tính lại từ get_data_root() ngay tại đây (không
    phải hằng số mức module) để test/E2E set EDUDSS_DATA_ROOT trước khi logger
    đầu tiên được dùng vẫn tách log kỹ thuật ra khỏi data_warehouse/logs/ thật."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_dir = get_data_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "technical.log"

    root = logging.getLogger("dss")
    level_name = os.environ.get("DSS_LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    install_log_redaction()
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
    # Không propagate lên root logger mặc định của Python (tránh in trùng ra
    # console/Streamlit log theo cấu hình của process cha ngoài ý muốn).
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Logger kỹ thuật cho module `name` (thường truyền `__name__`). Ghi vào
    `data_warehouse/logs/technical.log`, xoay vòng khi vượt ~2MB (giữ 3 bản cũ)
    — tách biệt hoàn toàn khỏi lịch sử hoạt động hiển thị cho người dùng."""
    _configure_once()
    # `__name__` bên trong package dss/ đã có dạng "dss.core.xxx"/"dss.services.xxx"
    # sẵn — chỉ thêm tiền tố "dss." nếu chưa có, tránh log tên kiểu "dss.dss.core.xxx".
    full_name = name if name == "dss" or name.startswith("dss.") else f"dss.{name}"
    return logging.getLogger(full_name)
