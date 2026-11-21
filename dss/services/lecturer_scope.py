"""Giảng viên chỉ xem sinh viên các lớp mình được gán (bước 7, nhóm B — 21/11/2026).

Nguồn sự thật là phân công chính thức ở trang "Lớp học" (`lp_teaching_assignments` +
`lp_enrollments`, dss/platform/models.py) — không thêm bảng mới.

Quy tắc:
- Bật mặc định khi dữ liệu là dữ liệu THẬT (`synthetic_data_allowed()` là False, tức production).
  Bản demo dữ liệu mô phỏng giữ nguyên hành vi cũ (xem toàn bộ bộ dữ liệu đang dùng).
  Ghi đè bằng EDUDSS_LECTURER_CLASS_SCOPE=1/0.
- Đóng khi lỗi (fail closed): không đọc được phân công, hoặc bộ dữ liệu không có cột mã sinh viên,
  thì giảng viên thấy 0 dòng kèm lý do — không bao giờ rơi về "xem tất cả".
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from dss.core.logging_config import get_logger

_logger = get_logger(__name__)
LECTURER_ROLE = "Giảng viên / CVHT"
_ID_CANDIDATES = ("student_id", "student_code", "ma_sv", "mssv", "Mã SV", "Mã sinh viên")


@dataclass(frozen=True)
class ScopeResult:
    df: pd.DataFrame | None
    applied: bool
    n_classes: int = 0
    n_students_total: int = 0
    n_students_visible: int = 0
    reason: str = ""


def scope_enabled() -> bool:
    raw = os.environ.get("EDUDSS_LECTURER_CLASS_SCOPE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    from dss.core.runtime_mode import synthetic_data_allowed

    return not synthetic_data_allowed()


def assigned_student_codes(username: str) -> tuple[int, set[str]]:
    """(số lớp đang dạy, tập mã SV đang ghi danh trong các lớp đó). Ném lỗi nếu không đọc được."""
    from sqlalchemy import select

    from dss.platform.context import current_actor
    from dss.platform.models import ClassEnrollment, TeachingAssignment
    from dss.platform.store import platform_session

    actor = current_actor()
    if actor.username != username or actor.role != LECTURER_ROLE:
        raise PermissionError("Phạm vi lớp chỉ tính cho chính giảng viên đang đăng nhập.")
    with platform_session(actor.school_id, actor=actor) as session:
        class_ids = set(
            session.scalars(
                select(TeachingAssignment.class_id).where(
                    TeachingAssignment.school_id == actor.school_id,
                    TeachingAssignment.teacher_username == actor.username,
                    TeachingAssignment.active.is_(True),
                )
            )
        )
        if not class_ids:
            return 0, set()
        codes = session.scalars(
            select(ClassEnrollment.student_code).where(
                ClassEnrollment.school_id == actor.school_id,
                ClassEnrollment.class_id.in_(class_ids),
                ClassEnrollment.active.is_(True),
            )
        )
        return len(class_ids), {str(c).strip().upper() for c in codes if c}


def student_id_column(df: pd.DataFrame) -> str | None:
    lowered = {str(c).strip().lower(): c for c in df.columns}
    for name in _ID_CANDIDATES:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def filter_to_codes(df: pd.DataFrame, codes: set[str]) -> pd.DataFrame | None:
    col = student_id_column(df)
    if col is None:
        return None
    mask = df[col].astype(str).str.strip().str.upper().isin(codes)
    return df.loc[mask]


def scope_for_lecturer(df, username: str, role: str) -> ScopeResult:
    """Trả bộ dữ liệu giảng viên được phép xem. Vai trò khác hoặc khi tắt phạm vi: giữ nguyên."""
    if role != LECTURER_ROLE or not isinstance(df, pd.DataFrame) or not scope_enabled():
        return ScopeResult(df=df, applied=False)
    empty = df.iloc[0:0]
    try:
        n_classes, codes = assigned_student_codes(username)
    except Exception:  # noqa: BLE001 - fail closed
        _logger.warning("Không đọc được phân công lớp của giảng viên; ẩn toàn bộ dữ liệu sinh viên.", exc_info=True)
        return ScopeResult(empty, True, n_students_total=len(df), reason="Không đọc được phân công lớp.")
    if n_classes == 0:
        return ScopeResult(empty, True, n_students_total=len(df), reason="Bạn chưa được gán lớp nào.")
    scoped = filter_to_codes(df, codes)
    if scoped is None:
        return ScopeResult(
            empty, True, n_classes, len(df), reason="Bộ dữ liệu không có cột mã sinh viên để đối chiếu với lớp."
        )
    return ScopeResult(scoped, True, n_classes, len(df), len(scoped))


def merge_scoped_edits(full_df: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    """Ghi lại các dòng giảng viên đã sửa vào bộ dữ liệu đầy đủ, không làm mất dòng của lớp khác."""
    col = student_id_column(full_df)
    if col is None or col not in edited.columns:
        raise ValueError("Không có cột mã sinh viên để ghép lại thay đổi.")
    merged = full_df.copy()
    edited_by_id = edited.set_index(col)
    key = merged[col]
    for column in edited.columns:
        if column == col or column not in merged.columns:
            continue
        updates = key.map(edited_by_id[column]) if edited_by_id.index.is_unique else None
        if updates is None:
            raise ValueError("Mã sinh viên bị trùng, không ghép được thay đổi.")
        has_update = key.isin(edited_by_id.index)
        merged.loc[has_update, column] = updates[has_update]
    return merged
