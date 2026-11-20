"""Exercise the student workspace with the real Streamlit runtime."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_workspace_generates_and_reopens_without_provider_or_gpa(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "local")
    script = """
import pandas as pd
import streamlit as st
from dss.tabs.learning_plan_workspace import render_learning_plan_workspace
st.session_state["_authenticated"] = True
st.session_state["_auth_username"] = "sv1"
st.session_state["_auth_role"] = "Sinh viên"
st.session_state["_auth_student_id"] = "SV1"
render_learning_plan_workspace(pd.DataFrame([{"student_id": "SV1", "course_id": "CS101"}]))
"""
    script_path = tmp_path / "workspace_app.py"
    script_path.write_text(script, encoding="utf-8")
    app = AppTest.from_file(str(script_path)).run(timeout=30)
    assert not app.exception
    button = next(button for button in app.button if button.label == "Tạo kế hoạch từ dữ liệu hiện có")
    button.click().run(timeout=30)
    assert not app.exception
    assert any("CS101" in item.value for item in app.caption)
    assert len(app.checkbox) == 1
    app.checkbox[0].check().run(timeout=30)
    assert not app.exception
    # A new runtime session must recover completion from storage.
    reopened = AppTest.from_file(str(script_path)).run(timeout=30)
    assert not reopened.exception
    assert reopened.checkbox[0].value is True
    assert any("Chưa có quan sát" in str(item.value) for item in reopened.caption)


def test_missing_course_never_uses_first_course_or_row(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "local")
    monkeypatch.delenv("EDUDSS_COURSE_ID", raising=False)
    script = """
import pandas as pd
import streamlit as st
from dss.tabs.learning_plan_workspace import render_learning_plan_workspace
st.session_state["_authenticated"] = True
st.session_state["_auth_username"] = "sv1"
st.session_state["_auth_role"] = "Sinh viên"
st.session_state["_auth_student_id"] = "SV1"
render_learning_plan_workspace(pd.DataFrame([{"student_id": "SV2", "course_id": "OTHER"}]))
"""
    script_path = tmp_path / "workspace_app.py"
    script_path.write_text(script, encoding="utf-8")
    app = AppTest.from_file(str(script_path)).run(timeout=30)
    assert not app.exception
    assert not app.button
    assert not list(Path(tmp_path).glob("*.json"))


def test_fresh_production_session_can_read_history_without_lms_dataset(monkeypatch, tmp_path):
    from unittest.mock import Mock
    from dss.core import init_app, data_helpers
    from dss.services import auth_service, subscription_service, learning_plan_history
    import streamlit as st

    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ENV", "production")
    monkeypatch.setenv("EDUDSS_MODE", "REAL_LMS")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_LEARNING_PLANS_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_PSEUDONYM_KEY", "stage1-test-only-key-not-for-deployment-123456")
    def login():
        st.session_state["_authenticated"] = True
        st.session_state["_auth_username"] = "sv1"
        st.session_state["_auth_role"] = "Sinh viên"
        st.session_state["_auth_student_id"] = "SV1"
        return {"username": "sv1", "role": "Sinh viên", "student_id": "SV1"}

    monkeypatch.setattr(auth_service, "render_login_gate", login)
    monkeypatch.setattr(init_app, "init_trainers_and_warehouse", lambda: (None, None, None, None))
    monkeypatch.setattr(subscription_service, "render_subscription_gate", lambda role: True)
    sample = Mock(side_effect=AssertionError("Production must not create a synthetic dataset"))
    monkeypatch.setattr(data_helpers, "generate_data", sample)
    monkeypatch.setattr(learning_plan_history, "list_learning_plans", lambda sid: [{
        "schema_version": 1, "completion": {},
        "plan": {"plan_id": "saved", "course_id": "CS101", "version": 1,
                 "created_at": "2026-10-20T00:00:00+00:00", "activities": []},
    }])
    # AppTest in this Streamlit version serializes single segmented controls as characters.
    # Theme selection is outside this dataset-independent navigation check.
    monkeypatch.setattr(st, "segmented_control", lambda *args, **kwargs: None)
    main_path = Path(__file__).resolve().parents[1] / "dss" / "main.py"
    app = AppTest.from_file(str(main_path)).run(timeout=45)
    assert not app.exception
    assert any("CS101" in caption.value for caption in app.caption)
    assert any("Chưa kết nối dữ liệu LMS" in str(item.value) for item in app.info)
    sample.assert_not_called()
    # Classroom navigation must remain available before an external dataset arrives.
    from dss.services import classroom_service
    monkeypatch.setattr(classroom_service, "list_my_classes", lambda actor: [])
    next(button for button in app.button if button.label == "Mở lớp học").click().run(timeout=30)
    assert not app.exception
    assert any(header.value == "Lớp học và đánh giá" for header in app.header)
    sample.assert_not_called()
