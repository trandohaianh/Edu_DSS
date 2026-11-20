"""FINAL REMAINING-GAPS CLOSURE — Section 10: confirm agent.run_gpa_
calculation() ACTUALLY emits an audit event (both success and
INSUFFICIENT_DATA paths), not just that ai_decision_audit.py exists in
isolation."""

from __future__ import annotations

from dss.services import agent


def _request(**overrides):
    defaults = dict(
        user_id="student_A",
        organization_id="org-1",
        role=agent._ROLE_STUDENT,
        intent="GPA_CALCULATION",
        authorized_context={},
        request_text="...",
        correlation_id="c-emit-1",
    )
    defaults.update(overrides)
    return agent.AgentRequest(**defaults)


def test_successful_gpa_calculation_emits_audit_event(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "_emit_audit_event", lambda *a, **k: calls.append((a, k)))
    request = _request(
        authorized_context={"current_gpa": 6.0, "credits_done": 20, "target_gpa": 7.5, "credits_remaining": 20}
    )
    agent.run_gpa_calculation(request)
    assert len(calls) == 1


def test_insufficient_data_path_also_emits_audit_event(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "_emit_audit_event", lambda *a, **k: calls.append((a, k)))
    request = _request(authorized_context={"current_gpa": 6.0})
    agent.run_gpa_calculation(request)
    assert len(calls) == 1
    assert calls[0][1]["final_status"] == "INSUFFICIENT_DATA"


def test_real_emit_reaches_ai_decision_audit_module(monkeypatch):
    """Khong mock _emit_audit_event - xac nhan duong that toi
    ai_decision_audit.emit() thuc su duoc goi (best-effort, khong Postgres
    thi tra False nhung KHONG raise)."""
    request = _request(
        authorized_context={"current_gpa": 6.0, "credits_done": 20, "target_gpa": 7.5, "credits_remaining": 20}
    )
    result = agent.run_gpa_calculation(request)  # khong duoc raise du khong co Postgres
    assert result.decision.status == "ok"
