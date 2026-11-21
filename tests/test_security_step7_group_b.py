"""Bước 7, nhóm B (21/11/2026): tự đăng xuất, thông báo + đồng ý, giảng viên chỉ xem lớp mình,
nút xuất/xoá dữ liệu cho Admin. Xem docs/security/SECURITY_CHECKLIST.md."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

from dss.platform import store
from dss.platform.context import Actor
from dss.services import classroom_service as classes

APP = Path(__file__).resolve().parents[1]
ADMIN = Actor("1", "admin", "Admin")
LECTURER = "Giảng viên / CVHT"


@pytest.fixture
def platform(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    store.reset_platform_engines()
    yield
    store.reset_platform_engines()


# ------------------------------------------------------------------ tự đăng xuất
def test_idle_timeout_defaults_to_30_minutes_and_has_a_floor(monkeypatch):
    from dss.services import auth_service

    monkeypatch.delenv("EDUDSS_IDLE_TIMEOUT_MINUTES", raising=False)
    assert auth_service.idle_timeout_seconds() == 30 * 60
    monkeypatch.setenv("EDUDSS_IDLE_TIMEOUT_MINUTES", "1")
    assert auth_service.idle_timeout_seconds() == 5 * 60
    monkeypatch.setenv("EDUDSS_IDLE_TIMEOUT_MINUTES", "abc")
    assert auth_service.idle_timeout_seconds() == 30 * 60


def test_session_expires_only_after_idle_period(monkeypatch):
    from dss.services import auth_service

    monkeypatch.delenv("EDUDSS_IDLE_TIMEOUT_MINUTES", raising=False)
    st.session_state["_auth_last_activity_at"] = 1_000.0
    assert auth_service.session_idle_expired(now=1_000.0 + 29 * 60) is False  # thao tác: làm mới mốc
    assert auth_service.session_idle_expired(now=1_000.0 + 29 * 60 + 31 * 60) is True
    st.session_state.pop("_auth_last_activity_at", None)


def test_login_gate_checks_idle_before_returning_identity():
    src = (APP / "dss/services/auth_service.py").read_text(encoding="utf-8")
    gate = src[src.index("def render_login_gate") :]
    assert gate.index("session_idle_expired()") < gate.index("return existing")


# ------------------------------------------------------------------ thông báo + đồng ý
def test_notice_lists_exactly_what_is_sent_to_ai():
    from dss.services import privacy_notice

    text = privacy_notice.notice_markdown("Sinh viên")
    for item in privacy_notice.DATA_SENT_TO_AI:
        assert item in text
    for item in ("Họ tên", "Mã sinh viên", "Email"):
        assert item in text  # liệt kê ở mục "không gửi"
    assert privacy_notice.NOTICE_VERSION in text


def test_consent_required_follows_real_data_and_env(monkeypatch):
    from dss.services import privacy_notice

    monkeypatch.setenv("EDUDSS_PRIVACY_CONSENT_REQUIRED", "1")
    assert privacy_notice.consent_required() is True
    monkeypatch.setenv("EDUDSS_PRIVACY_CONSENT_REQUIRED", "0")
    assert privacy_notice.consent_required() is False


def test_consent_is_recorded_per_user_and_version(platform, as_role):
    from dss.services import privacy_notice

    as_role("Sinh viên", username="sv001", student_id="SV001")
    assert privacy_notice.has_accepted("sv001") is False
    privacy_notice.record_acceptance("sv001")
    assert privacy_notice.has_accepted("sv001") is True
    with pytest.raises(PermissionError):
        privacy_notice.record_acceptance("sv002")  # không đồng ý thay người khác
    as_role("Sinh viên", username="sv002", student_id="SV002")
    assert privacy_notice.has_accepted("sv002") is False


def test_main_runs_consent_gate_right_after_login():
    src = (APP / "dss/main.py").read_text(encoding="utf-8")
    assert src.index("render_login_gate()") < src.index("render_consent_gate(_user)") < src.index("current_df")


# ------------------------------------------------------------------ giảng viên chỉ xem lớp mình
def _df():
    return pd.DataFrame({"student_id": ["SV001", "SV002", "SV003", "SV004"], "gpa": [6.0, 7.0, 8.0, 5.0]})


def test_lecturer_sees_only_students_of_assigned_classes(platform, as_role, monkeypatch):
    from dss.services import lecturer_scope

    monkeypatch.setenv("EDUDSS_LECTURER_CLASS_SCOPE", "1")
    mine = classes.create_class(ADMIN, "A1", "C1", "Lớp A1", "2026")
    other = classes.create_class(ADMIN, "B1", "C1", "Lớp B1", "2026")
    classes.import_enrollments(ADMIN, mine["id"], ["sv001", "SV003"])
    classes.import_enrollments(ADMIN, other["id"], ["SV002"])
    classes.assign_teacher(ADMIN, mine["id"], "gv_a")

    as_role(LECTURER, username="gv_a")
    res = lecturer_scope.scope_for_lecturer(_df(), "gv_a", LECTURER)
    assert res.applied and res.n_classes == 1
    assert sorted(res.df["student_id"]) == ["SV001", "SV003"]

    as_role(LECTURER, username="gv_b")
    res = lecturer_scope.scope_for_lecturer(_df(), "gv_b", LECTURER)
    assert res.applied and res.df.empty and res.reason  # chưa được gán lớp: thấy 0 dòng


def test_lecturer_scope_fails_closed_and_skips_other_roles(platform, as_role, monkeypatch):
    from dss.services import lecturer_scope

    monkeypatch.setenv("EDUDSS_LECTURER_CLASS_SCOPE", "1")
    as_role(LECTURER, username="gv_a")

    def _boom(_u):
        raise RuntimeError("CSDL lỗi")

    monkeypatch.setattr(lecturer_scope, "assigned_student_codes", _boom)
    assert lecturer_scope.scope_for_lecturer(_df(), "gv_a", LECTURER).df.empty
    monkeypatch.setattr(lecturer_scope, "assigned_student_codes", lambda _u: (1, {"SV001"}))
    no_id = pd.DataFrame({"gpa": [1.0]})
    assert lecturer_scope.scope_for_lecturer(no_id, "gv_a", LECTURER).df.empty
    assert lecturer_scope.scope_for_lecturer(_df(), "admin", "Admin").applied is False


def test_scoped_grade_edits_merge_back_without_losing_other_classes():
    from dss.services.lecturer_scope import merge_scoped_edits

    full = _df()
    edited = full[full["student_id"].isin(["SV001"])].copy()
    edited.loc[:, "gpa"] = 9.5
    merged = merge_scoped_edits(full, edited)
    assert len(merged) == 4
    assert merged.set_index("student_id")["gpa"].to_dict() == {"SV001": 9.5, "SV002": 7.0, "SV003": 8.0, "SV004": 5.0}


def test_main_filters_df_once_for_lecturers():
    src = (APP / "dss/main.py").read_text(encoding="utf-8")
    assert "scope_for_lecturer(df, _user[\"username\"], current_role)" in src


# ------------------------------------------------------------------ xuất/xoá dữ liệu cho Admin
def test_data_rights_panel_is_admin_only(as_role):
    from dss.tabs import admin_settings

    as_role(LECTURER, username="gv_a")
    with pytest.raises(PermissionError):
        admin_settings._student_data_rights_panel()


def test_data_rights_panel_calls_lifecycle_and_confirms_erasure():
    src = (APP / "dss/tabs/admin_settings.py").read_text(encoding="utf-8")
    panel = src[src.index("def _student_data_rights_panel") :]
    assert "data_lifecycle.export_student_data(" in panel
    assert "data_lifecycle.erase_student_data(" in panel
    assert "confirm == code and sure" in panel  # phải gõ lại mã + tick xác nhận


# ------------------------------------------------------------------ thư viện đã vá
def test_lock_file_has_patched_versions():
    lock = (APP / "requirements.lock.txt").read_text(encoding="utf-8").splitlines()
    pins = dict(line.split("==", 1) for line in lock if "==" in line and not line.startswith("#"))
    pins = {k.lower(): v.strip() for k, v in pins.items()}
    for name, minimum in {"tornado": "6.6.1", "pypdf": "6.21.4", "pyasn1": "0.6.5", "gitpython": "3.2.1"}.items():
        assert tuple(map(int, pins[name].split("."))) >= tuple(map(int, minimum.split("."))), name
