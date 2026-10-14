"""Unit tests for LMS Live Push & Webhook Synchronization Layer."""
import hashlib
import hmac
import pandas as pd
import pytest
from dss.services.lms_live_sync import LMSLiveEvent, LMSLiveSyncManager, lms_live_sync_manager


def test_webhook_signature_verification():
    """Kiểm tra xác thực chữ ký HMAC-SHA256 chuẩn Webhook."""
    secret = "test_webhook_secret_key"
    payload = '{"event": "grade_update", "student_id": "SV001", "score": 9.0}'
    valid_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    mgr = LMSLiveSyncManager(webhook_secret=secret)
    assert mgr.verify_webhook_signature(payload, valid_sig) is True
    assert mgr.verify_webhook_signature(payload, "invalid_sig_12345") is False
    assert mgr.verify_webhook_signature(payload, "") is False


def test_apply_event_to_dataframe_grade_update():
    """Kiểm tra áp dụng sự kiện cập nhật điểm trực tiếp vào DataFrame."""
    df = pd.DataFrame({
        "student_id": ["SV001", "SV002"],
        "final_score": [6.5, 8.0],
        "ty_le_diem_danh": [0.80, 0.95],
    })

    event = LMSLiveEvent(
        event_id="evt_001",
        event_type="grade_update",
        student_id="SV001",
        course_id="CS101",
        field_name="final_score",
        old_value=6.5,
        new_value=9.0,
    )

    mgr = LMSLiveSyncManager()
    success, updated_df, msg = mgr.apply_event_to_dataframe(event, df)

    assert success is True
    assert updated_df is not None
    assert updated_df.loc[0, "final_score"] == 9.0
    # Original student SV002 untouched
    assert updated_df.loc[1, "final_score"] == 8.0
    assert event.status == "processed"


def test_simulate_live_pushes():
    """Kiểm tra các hàm giả lập Moodle và Canvas live push."""
    df = pd.DataFrame({
        "student_id": ["SV100"],
        "final_score": [7.0],
        "ty_le_diem_danh": [0.75],
    })

    mgr = LMSLiveSyncManager()

    # 1. Simulate Moodle Grade push
    m_evt, df_m, m_msg = mgr.simulate_moodle_grade_push("SV100", 8.8, df)
    assert m_evt.status == "processed"
    assert df_m.loc[0, "final_score"] == 8.8

    # 2. Simulate Canvas Attendance push
    c_evt, df_c, c_msg = mgr.simulate_canvas_attendance_push("SV100", 0.95, df_m)
    assert c_evt.status == "processed"
    assert df_c.loc[0, "ty_le_diem_danh"] == 0.95

    # History contains both events
    history = mgr.get_event_history(limit=5)
    assert len(history) >= 2
