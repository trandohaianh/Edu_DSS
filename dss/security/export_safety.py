"""Chống chèn công thức (CSV/Excel formula injection) khi XUẤT file cho người dùng tải về.

Ô văn bản bắt đầu bằng ``= + - @`` hoặc tab / xuống dòng có thể được Excel/LibreOffice hiểu là
công thức (ví dụ ``=HYPERLINK(...)`` gửi dữ liệu ra ngoài khi người nhận bấm vào). Dữ liệu trong
EduDSS đến từ file người dùng tải lên, tên cột, câu trả lời AI... nên không tin được.

Cách xử lý chuẩn (OWASP): thêm dấu nháy đơn ``'`` vào trước ô nguy hiểm để bảng tính coi đó là văn
bản. Số thật (kể cả số âm như ``-5.2``) giữ nguyên. Chỉ áp dụng cho file XUẤT, không áp dụng cho dữ
liệu lưu nội bộ trong kho.
"""

from __future__ import annotations

import pandas as pd

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _looks_numeric(text: str) -> bool:
    try:
        float(text.replace(",", "."))
    except ValueError:
        return False
    return True


def neutralize_cell(value):
    """Trả về giá trị an toàn cho bảng tính (chỉ đổi chuỗi bắt đầu bằng ký tự nguy hiểm)."""
    if isinstance(value, str) and value and value[0] in _DANGEROUS_PREFIXES and not _looks_numeric(value.strip()):
        return "'" + value
    return value


def safe_for_spreadsheet(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Bản sao của ``df`` với mọi ô văn bản và tên cột đã được trung hoà công thức."""
    if df is None:
        return None
    out = df.copy()
    out.columns = [neutralize_cell(c) if isinstance(c, str) else c for c in out.columns]
    for col in out.columns:
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].map(neutralize_cell)
    return out
