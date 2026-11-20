"""LMS Live Push & Webhook Synchronization Layer — EduDSS.

Cung cấp cơ chế nhận và đồng bộ sự kiện thời gian thực từ LMS (Moodle / Canvas LTI):
- Xác thực Webhook Signature (HMAC SHA-256)
- Cập nhật trực tiếp điểm số, điểm danh vào DataFrame đang hoạt động mà không cần nạp lại file
- Giả lập bắn sự kiện Live Push từ Moodle Gradebook và Canvas Attendance
- Duy trì nhật ký sự kiện thời gian thực (Live Stream Ticker)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from dss.core.target_utils import is_id_like


@dataclass
class LMSLiveEvent:
    event_id: str
    event_type: str  # "grade_update" | "attendance_checkin" | "assignment_submitted" | "quiz_completed"
    student_id: str
    course_id: str
    field_name: str
    old_value: Any
    new_value: Any
    source: str = "Moodle Core Webhook"  # "Moodle Core Webhook" | "Canvas LTI 1.3 Event" | "Simulated Live Stream"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "processed"  # "processed" | "pending" | "failed"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LMSLiveSyncManager:
    """Quản lý tiếp nhận webhook và cập nhật dữ liệu thời gian thực."""

    _shared_history: List[LMSLiveEvent] = []

    def __init__(self, webhook_secret: Optional[str] = None):
        # Trước đây mặc định là một chuỗi cố định nằm công khai trong mã nguồn, nên ai
        # cũng tự ký được webhook hợp lệ. Nay lấy từ biến môi trường; không có thì
        # verify_webhook_signature luôn từ chối (fail closed).
        if webhook_secret is None:
            webhook_secret = os.environ.get("EDUDSS_LMS_WEBHOOK_SECRET", "")
        self.webhook_secret = webhook_secret

    @classmethod
    def get_event_history(cls, limit: int = 20) -> List[LMSLiveEvent]:
        return list(reversed(cls._shared_history[-limit:]))

    @classmethod
    def record_event(cls, event: LMSLiveEvent) -> None:
        cls._shared_history.append(event)
        if len(cls._shared_history) > 200:
            cls._shared_history = cls._shared_history[-200:]

    def verify_webhook_signature(self, payload: str, signature: str, secret: Optional[str] = None) -> bool:
        """Xác thực chữ ký số HMAC-SHA256 của Webhook LMS."""
        sec = secret or self.webhook_secret
        if not signature or not sec:
            return False
        expected = hmac.new(sec.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.lower(), signature.strip().lower())

    def apply_event_to_dataframe(
        self,
        event: LMSLiveEvent,
        df: Optional[pd.DataFrame],
    ) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Cập nhật trực tiếp bản ghi sinh viên trong DataFrame khi có sự kiện đẩy đến."""
        if df is None or df.empty:
            self.record_event(event)
            return False, df, "DataFrame trống hoặc chưa nạp."

        id_col = next((c for c in df.columns if is_id_like(c) or "ma" in str(c).lower()), None)
        if not id_col:
            self.record_event(event)
            return False, df, "Không tìm thấy cột định danh sinh viên trong dataset."

        # Tìm dòng của sinh viên
        mask = df[id_col].astype(str).str.strip().str.lower() == str(event.student_id).strip().lower()
        if not mask.any():
            event.status = "failed"
            event.description = f"Sinh viên {event.student_id} không tồn tại trong dataset hiện tại."
            self.record_event(event)
            return False, df, event.description

        # Tìm cột cần cập nhật
        target_col = None
        if event.field_name in df.columns:
            target_col = event.field_name
        else:
            # Tìm cột gần đúng (vd: 'final_score', 'diem_tong_ket', 'ty_le_diem_danh')
            for c in df.columns:
                if event.field_name.lower() in str(c).lower() or str(c).lower() in event.field_name.lower():
                    target_col = c
                    break

        if not target_col:
            event.status = "failed"
            event.description = f"Cột '{event.field_name}' không tồn tại trong dataset."
            self.record_event(event)
            return False, df, event.description

        # Ghi nhận giá trị cũ và cập nhật
        updated_df = df.copy()
        current_val = updated_df.loc[mask, target_col].iloc[0]
        event.old_value = current_val

        try:
            val_to_set = type(current_val)(event.new_value) if pd.notna(current_val) else event.new_value
            updated_df.loc[mask, target_col] = val_to_set
            event.status = "processed"
            event.description = (
                f"Đã cập nhật {target_col}: {current_val} -> {val_to_set} cho sinh viên {event.student_id}"
            )
            self.record_event(event)
            return True, updated_df, event.description
        except Exception as e:
            event.status = "failed"
            event.description = f"Lỗi chuyển đổi kiểu dữ liệu: {e}"
            self.record_event(event)
            return False, df, event.description

    def simulate_moodle_grade_push(
        self,
        student_id: str,
        new_score: float,
        df: Optional[pd.DataFrame],
        course_id: str = "CS101",
        field_name: str = "final_score",
    ) -> Tuple[LMSLiveEvent, Optional[pd.DataFrame], str]:
        """Tạo và xử lý sự kiện giả lập Moodle Webhook cập nhật điểm thi."""
        event = LMSLiveEvent(
            event_id=f"moodle_evt_{uuid.uuid4().hex[:8]}",
            event_type="grade_update",
            student_id=str(student_id),
            course_id=course_id,
            field_name=field_name,
            old_value=None,
            new_value=float(new_score),
            source="Moodle Core Webhook",
            description=f"Giảng viên chấm điểm bài thi mới trên Moodle Gradebook ({course_id}).",
        )
        success, updated_df, msg = self.apply_event_to_dataframe(event, df)
        return event, updated_df, msg

    def simulate_canvas_attendance_push(
        self,
        student_id: str,
        new_attendance: float,
        df: Optional[pd.DataFrame],
        course_id: str = "CS101",
        field_name: str = "ty_le_diem_danh",
    ) -> Tuple[LMSLiveEvent, Optional[pd.DataFrame], str]:
        """Tạo và xử lý sự kiện giả lập Canvas LTI cập nhật điểm danh."""
        event = LMSLiveEvent(
            event_id=f"canvas_evt_{uuid.uuid4().hex[:8]}",
            event_type="attendance_checkin",
            student_id=str(student_id),
            course_id=course_id,
            field_name=field_name,
            old_value=None,
            new_value=float(new_attendance),
            source="Canvas LTI 1.3 Event",
            description=f"Điểm danh tự động qua hệ thống QR Canvas ({course_id}).",
        )
        success, updated_df, msg = self.apply_event_to_dataframe(event, df)
        return event, updated_df, msg


# Instance toàn cục tiện sử dụng
lms_live_sync_manager = LMSLiveSyncManager()
