"""Streamlit acceptance for programme allocation and school-controlled reporting."""

import json

import pytest
from streamlit.testing.v1 import AppTest

from dss.platform.context import Actor
from dss.platform.store import reset_platform_engines
from dss.services import program_allocation_service as programs


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    reset_platform_engines()
    operator = Actor("1", "operator", "Platform Admin")
    manager = Actor("1", "manager", "Admin")
    school = Actor("2", "school-admin", "Admin")
    programs.register_school(operator, "1", "Programme office")
    programs.register_school(operator, "2", "Pilot university")
    program = programs.create_program(operator, "PILOT", "Pilot programme", 10, 0)
    programs.grant_program_member(operator, program["id"], "1", "manager", "manager")
    yield operator, manager, school, program
    reset_platform_engines()


def app_for(actor):
    script = """
import streamlit as st
from dss.tabs.programs_tab import programs_tab
st.session_state["_authenticated"] = True
st.session_state["_auth_username"] = USERNAME
st.session_state["_auth_role"] = ROLE
programs_tab()
""".replace("USERNAME", repr(actor.username)).replace("ROLE", repr(actor.role))
    return AppTest.from_string(script).run(timeout=30)


def test_manager_allocates_school_and_school_publishes(setup, monkeypatch):
    _, manager, school, program = setup
    app = app_for(manager)
    assert not app.exception and not app.error
    next(item for item in app.selectbox if item.label == "Trường nhận cấp phát").set_value(school.school_id)
    next(item for item in app.number_input if item.label == "Suất sinh viên").set_value(5)
    next(item for item in app.button if item.label == "Lưu cấp phát").click().run(timeout=30)
    assert not app.exception and not app.error
    allocations = programs.list_allocations(manager, program["id"])
    assert any(row["school_id"] == "2" and row["seats"] == 5 for row in allocations)
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "2")
    school_app = app_for(school)
    assert not school_app.exception and not school_app.error
    assert not any(item.label == "Lưu cấp phát" for item in school_app.button)
    next(item for item in school_app.button if item.label == "Gửi báo cáo tổng hợp").click().run(timeout=30)
    assert not school_app.exception and not school_app.error
    reports = programs.list_program_reports(manager, program["id"])
    assert next(row for row in reports if row["school_id"] == "2")["report_status"] == "suppressed"
    assert "student_code" not in json.dumps(reports)


def test_platform_operator_has_provisioning_but_no_default_reports(setup):
    operator, _, _, _ = setup
    app = app_for(operator)
    assert not app.exception and not app.error
    assert any(button.label == "Tạo chương trình" for button in app.button)
    assert any(button.label == "Lưu quyền chương trình" for button in app.button)
    assert not any(button.label == "Lưu cấp phát" for button in app.button)
    assert not any(button.label == "Tải báo cáo tổng hợp JSON" for button in app.button)
