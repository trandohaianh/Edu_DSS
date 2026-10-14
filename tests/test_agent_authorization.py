"""FINAL REMAINING-GAPS CLOSURE — Section 3: real Agent authorization,
tested with exactly the scenarios the master prompt names: Student A → own
data (allowed), Student A → Student B (denied), Org A → Org B (denied),
Student → Admin-only tool (denied), missing identity (fail-closed)."""
from __future__ import annotations

import pytest

from dss.services import agent


def _request(**overrides):
    defaults = dict(
        user_id="student_A", organization_id="org-1", role=agent._ROLE_STUDENT,
        intent="GPA_CALCULATION", authorized_context={}, request_text="...", correlation_id="c1",
    )
    defaults.update(overrides)
    return agent.AgentRequest(**defaults)


def test_student_accessing_own_data_is_allowed():
    request = _request(authorized_context={"subject_user_id": "student_A"})
    agent.authorize(request)  # does not raise


def test_student_accessing_another_students_data_is_denied():
    request = _request(user_id="student_A", authorized_context={"subject_user_id": "student_B"})
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_org_a_accessing_org_b_data_is_denied():
    request = _request(organization_id="org-A", authorized_context={"organization_id": "org-B"})
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_org_a_accessing_org_a_data_is_allowed():
    request = _request(organization_id="org-A", authorized_context={"organization_id": "org-A"})
    agent.authorize(request)  # does not raise


def test_student_calling_admin_only_intent_is_denied():
    request = _request(role=agent._ROLE_STUDENT, intent="ADMIN_REGULATION_MANAGEMENT")
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_admin_calling_admin_only_intent_is_allowed():
    request = _request(role=agent._ROLE_ADMIN, intent="ADMIN_REGULATION_MANAGEMENT")
    agent.authorize(request)  # does not raise


def test_lecturer_allowed_lecturer_scope_not_admin_only():
    request = _request(role=agent._ROLE_LECTURER, intent="GPA_CALCULATION")
    agent.authorize(request)  # does not raise
    request_admin_only = _request(role=agent._ROLE_LECTURER, intent="ADMIN_AI_PROVIDER_CONFIG")
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request_admin_only)


def test_missing_user_id_fails_closed():
    request = _request(user_id="")
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_missing_role_fails_closed():
    request = _request(role="")
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_invalid_role_string_fails_closed():
    """Khong tin bat ky chuoi role nao - chi 3 vai tro da biet duoc chap
    nhan, khong suy doan cho gia tri la."""
    request = _request(role="SomeRandomRoleString")
    with pytest.raises(agent.AuthorizationError):
        agent.authorize(request)


def test_identity_is_never_read_from_request_text():
    """Dam bao authorize() KHONG doc request_text de suy ra danh tinh - danh
    tinh CHI den tu cac truong cau truc (user_id/role/organization_id)."""
    import inspect
    source = inspect.getsource(agent.authorize)
    assert "request.request_text" not in source, (
        "authorize() KHONG duoc doc request_text de xac dinh danh tinh/quyen truy cap."
    )


def test_run_gpa_calculation_enforces_authorization_before_any_tool_call():
    """Xac nhan run_gpa_calculation() THAT SU goi authorize() - khong chi ton
    tai ham rieng khong ai dung (giong bai hoc tu Circuit Breaker/Rule Engine
    - phai wire that, khong chi dinh nghia roi khong goi)."""
    request = _request(
        user_id="student_A", role=agent._ROLE_STUDENT,
        authorized_context={"subject_user_id": "student_B", "current_gpa": 6.0, "credits_done": 20, "target_gpa": 7.5, "credits_remaining": 20},
    )
    with pytest.raises(agent.AuthorizationError):
        agent.run_gpa_calculation(request)
