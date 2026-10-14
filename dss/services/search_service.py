"""Tìm kiếm toàn cục (thanh search trên topbar) — RBAC-aware, KHÔNG lộ dữ liệu
chưa được phép trước khi lọc quyền (Mục A2 của yêu cầu UI/RAG consistency
pass): quyết định "được tìm hay không" xảy ra TRƯỚC khi trả kết quả, không
phải lọc phía client sau khi đã trả toàn bộ dữ liệu về.

Phạm vi hiện tại (đúng những gì repository/kiến trúc thật sự hỗ trợ — không tự
suy ra "lớp học được phân công cho giảng viên", khái niệm này KHÔNG tồn tại
trong dữ liệu hiện có, Giảng viên vốn đã nhìn thấy toàn bộ dataset lớp học ở
mọi tab khác trong ứng dụng, xem `LMS_CMS_RAG_PRODUCT_VERIFICATION.md`):

- Admin: tìm kiếm sinh viên trong dataset hiện tại (toàn bộ tổ chức/dataset
  đang mở — đúng phạm vi Admin đã có ở mọi nơi khác trong app).
- Giảng viên / CVHT: tìm kiếm sinh viên trong dataset hiện tại — CÙNG phạm vi
  "toàn lớp" mà vai trò này đã thấy ở Dashboard/Kho dữ liệu/Trợ lý AI, không
  mở rộng thêm quyền nào mới.
- Sinh viên: KHÔNG được cấp quyền tìm kiếm sinh viên khác — hàm này trả về
  danh sách rỗng ngay lập tức cho vai trò Sinh viên, bất kể query là gì.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from dss.core.data_helpers import feature_label

ROLES_ALLOWED_STUDENT_SEARCH = {"Admin", "Giảng viên / CVHT"}

# Số trường chỉ số hiển thị tối đa trên 1 thẻ kết quả — đủ để hữu ích, không
# biến thẻ kết quả thành một bảng dữ liệu thô thu nhỏ.
_MAX_METRIC_FIELDS = 4
_MAX_RESULTS = 5

# Các cột KHÔNG bao giờ hiển thị trên thẻ kết quả dù có trong dataset (định
# danh kỹ thuật/nội bộ, không phải chỉ số học tập hữu ích cho người xem).
_EXCLUDED_METRIC_COLUMNS = {"id", "index", "unnamed: 0"}


@dataclass
class StudentSearchResult:
    student_id: str
    student_name: Optional[str]
    metrics: List[tuple] = field(default_factory=list)  # [(label, value), ...]


def search_students(
    df: Optional[pd.DataFrame],
    query: str,
    role: Optional[str],
) -> List[StudentSearchResult]:
    """Trả về TỐI ĐA `_MAX_RESULTS` kết quả khớp mã số sinh viên (khớp chính
    xác được ưu tiên lên đầu, sau đó khớp một phần, không phân biệt hoa
    thường). Trả về [] TRUNG THỰC nếu vai trò không được phép, chưa có
    dataset, hoặc không tìm thấy — không bao giờ dựng DataFrame rỗng."""
    if role not in ROLES_ALLOWED_STUDENT_SEARCH:
        return []
    if df is None or not query or not query.strip():
        return []

    id_col = next((c for c in df.columns if "id" in str(c).lower()), None)
    if id_col is None:
        return []

    query_norm = query.strip().lower()
    id_series = df[id_col].astype(str)

    exact_mask = id_series.str.lower() == query_norm
    partial_mask = id_series.str.lower().str.contains(query_norm, na=False, regex=False) & ~exact_mask

    matched = pd.concat([df[exact_mask], df[partial_mask]], axis=0).head(_MAX_RESULTS)

    name_col = next(
        (c for c in df.columns if "name" in str(c).lower() or "ten" in str(c).lower() or "tên" in str(c).lower()),
        None,
    )

    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if str(c).lower() not in _EXCLUDED_METRIC_COLUMNS
    ][:_MAX_METRIC_FIELDS]

    results: List[StudentSearchResult] = []
    for _, row in matched.iterrows():
        metrics = []
        for col in numeric_cols:
            val = row.get(col)
            if pd.isna(val):
                continue
            label = feature_label(col)
            if "tỷ lệ" in label.lower() or "ty le" in str(col).lower():
                display_val = f"{float(val) * 100:.0f}%" if val <= 1 else f"{val:g}"
            else:
                display_val = f"{val:g}" if isinstance(val, (int, float)) else str(val)
            metrics.append((label, display_val))

        results.append(
            StudentSearchResult(
                student_id=str(row.get(id_col)),
                student_name=(str(row.get(name_col)) if name_col and pd.notna(row.get(name_col)) else None),
                metrics=metrics,
            )
        )
    return results


def format_empty_state_message(query: str) -> str:
    return f'Không tìm thấy kết quả phù hợp với "{query}".'
