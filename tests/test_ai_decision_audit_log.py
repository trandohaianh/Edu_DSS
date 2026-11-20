"""FINAL REMAINING-GAPS CLOSURE — Section 10: canonical AI decision audit
event contract. Written before `dss/services/ai_decision_audit.py` existed
(TDD)."""

from __future__ import annotations

from dss.services import ai_decision_audit


def test_event_has_all_required_fields():
    event = ai_decision_audit.AIDecisionAuditEvent(
        correlation_id="c1",
        tenant_id="org-1",
        actor_ref="pseudo_student_1",
        role="Sinh viên",
        intent="GPA_CALCULATION",
        tier=1,
        tools_used=["gpa_calculator.compute_required_remaining_gpa"],
        calculator_version="v1",
        rule_id=None,
        rule_version=None,
        regulation_id=None,
        regulation_version=None,
        model_id=None,
        rag_document_ids=[],
        provider=None,
        llm_used=False,
        fallback_type=None,
        validator_status="PASS",
        latency_ms=12.5,
        token_usage=None,
        final_status="ok",
    )
    assert event.correlation_id == "c1"
    assert event.final_status == "ok"


def test_emit_never_raises_when_postgres_not_configured(monkeypatch):
    """record() goc da co bao ve nay - xac nhan emit() KHONG lam mat bao ve
    do (khong tu raise them, khong swallow sai kieu loi)."""
    from dss.db.repositories import audit_log_repository

    monkeypatch.setattr(audit_log_repository, "is_database_configured", lambda: False)
    event = ai_decision_audit.AIDecisionAuditEvent(
        correlation_id="c2",
        tenant_id=None,
        actor_ref="pseudo_student_2",
        role="Sinh viên",
        intent="GPA_CALCULATION",
        tier=1,
        tools_used=[],
        calculator_version=None,
        rule_id=None,
        rule_version=None,
        regulation_id=None,
        regulation_version=None,
        model_id=None,
        rag_document_ids=[],
        provider=None,
        llm_used=False,
        fallback_type=None,
        validator_status=None,
        latency_ms=None,
        token_usage=None,
        final_status="INSUFFICIENT_DATA",
    )
    result = ai_decision_audit.emit(event)
    assert result is False  # khong ghi duoc (khong co Postgres) nhung KHONG raise


def test_emit_calls_the_shared_audit_log_repository_not_a_parallel_writer(monkeypatch):
    """Section 10 yeu cau HOP NHAT cac duong audit_log phan manh - xac nhan
    emit() dung LAI audit_log_repository.record() (da co, da test), khong
    tu viet 1 duong ghi DB song song moi."""
    calls = []

    def _fake_record(**kwargs):
        calls.append(kwargs)
        return True

    from dss.db.repositories import audit_log_repository

    monkeypatch.setattr(audit_log_repository, "record", _fake_record)

    event = ai_decision_audit.AIDecisionAuditEvent(
        correlation_id="c3",
        tenant_id="org-1",
        actor_ref="pseudo_student_3",
        role="Sinh viên",
        intent="GPA_CALCULATION",
        tier=1,
        tools_used=["gpa_calculator.compute_required_remaining_gpa"],
        calculator_version=None,
        rule_id=None,
        rule_version=None,
        regulation_id=None,
        regulation_version=None,
        model_id=None,
        rag_document_ids=[],
        provider=None,
        llm_used=False,
        fallback_type=None,
        validator_status="PASS",
        latency_ms=5.0,
        token_usage=None,
        final_status="ok",
    )
    ai_decision_audit.emit(event)
    assert len(calls) == 1
    assert calls[0]["action"] == "ai.decision"
    assert calls[0]["target_id"] == "c3"


def test_never_includes_password_secret_or_token_fields():
    """Kiem tra tinh: dataclass khong co field nao ten password/secret/token
    (tru token_usage - so luong token, khong phai chinh access token)."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(ai_decision_audit.AIDecisionAuditEvent)}
    forbidden = {"password", "secret", "access_token", "api_key"}
    assert not (field_names & forbidden)
