"""FINAL REMAINING-GAPS CLOSURE — Section 4: the remaining 3 Agent tool
orders (B regulation/rule, C risk explanation, D personalized plan)."""

from __future__ import annotations

from dss.services import agent
from dss.services.regulation_resolver import RegulationVersion
from dss.services.rule_engine import RULE_TYPE_CREDIT_LIMIT, AcademicRule


def _request(**overrides):
    defaults = dict(
        user_id="student_A",
        organization_id="org-1",
        role=agent._ROLE_STUDENT,
        intent="ACADEMIC_RULE_CHECK",
        authorized_context={},
        request_text="...",
        correlation_id="c1",
    )
    defaults.update(overrides)
    return agent.AgentRequest(**defaults)


# --- B. Regulation / rule check ---------------------------------------


def test_regulation_check_insufficient_data_when_no_regulations_provided():
    request = _request(authorized_context={})
    result = agent.run_regulation_or_rule_check(request)
    assert result.fallback == "INSUFFICIENT_DATA"


def test_regulation_check_resolves_real_regulation_and_validates():
    reg = RegulationVersion(
        regulation_id="QC-1",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
        version=1,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        approved_by="admin",
        source_document_id=None,
    )
    request = _request(
        authorized_context={
            "regulations": [reg],
            "organization_id": "org-1",
            "program_id": "cntt",
            "cohort": "k66",
        },
    )
    result = agent.run_regulation_or_rule_check(request)
    assert "regulation_resolver.resolve_regulation" in result.tools_used
    assert "validator.validate_regulation_resolution" in result.tools_used
    assert result.decision.status == "ok"
    assert result.llm_used is False


def test_regulation_check_also_evaluates_rule_when_regulation_resolved():
    reg = RegulationVersion(
        regulation_id="QC-1",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
        version=1,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        approved_by="admin",
        source_document_id=None,
    )
    rule = AcademicRule(
        rule_id="r1",
        regulation_id="QC-1",
        regulation_version=1,
        organization_id="org-1",
        rule_type=RULE_TYPE_CREDIT_LIMIT,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        params={"max_credits": 24},
    )
    request = _request(
        authorized_context={
            "regulations": [reg],
            "organization_id": "org-1",
            "program_id": "cntt",
            "cohort": "k66",
            "rule": {"evaluate_fn_name": "evaluate_credit_limit", "rule": rule, "kwargs": {"requested_credits": 30}},
        },
    )
    result = agent.run_regulation_or_rule_check(request)
    assert "rule_engine.evaluate_credit_limit" in result.tools_used
    assert result.decision.status == "DENY"


def test_regulation_check_enforces_authorization():
    import pytest

    request = _request(
        user_id="student_A",
        authorized_context={"subject_user_id": "student_B"},
    )
    with pytest.raises(agent.AuthorizationError):
        agent.run_regulation_or_rule_check(request)


# --- C. Risk explanation ------------------------------------------------


def test_risk_explanation_returns_precomputed_evidence():
    request = _request(
        intent="LEARNING_EXPLANATION",
        authorized_context={"prediction": 7.2, "model_version": "v3", "shap_evidence": {"diem_giua_ky": 0.4}},
    )
    result = agent.run_risk_explanation(request)
    assert result.decision == 7.2
    assert result.evidence["model_version"] == "v3"
    assert result.llm_used is False


def test_risk_explanation_insufficient_data_when_missing_shap():
    request = _request(intent="LEARNING_EXPLANATION", authorized_context={"prediction": 7.2})
    result = agent.run_risk_explanation(request)
    assert result.fallback == "INSUFFICIENT_DATA"


def test_risk_explanation_enforces_authorization():
    import pytest

    request = _request(
        intent="LEARNING_EXPLANATION",
        user_id="student_A",
        authorized_context={
            "subject_user_id": "student_B",
            "prediction": 1,
            "model_version": "v1",
            "shap_evidence": {},
        },
    )
    with pytest.raises(agent.AuthorizationError):
        agent.run_risk_explanation(request)


# --- D. Personalized plan -----------------------------------------------


def test_personalized_plan_combines_gpa_and_regulation_evidence():
    reg = RegulationVersion(
        regulation_id="QC-1",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
        version=1,
        effective_from="2024-01-01",
        effective_to=None,
        status="APPROVED",
        approved_by="admin",
        source_document_id=None,
    )
    request = _request(
        intent="ADVISOR_PLAN",
        authorized_context={
            "current_gpa": 6.0,
            "credits_done": 20,
            "target_gpa": 7.5,
            "credits_remaining": 20,
            "regulations": [reg],
            "organization_id": "org-1",
            "program_id": "cntt",
            "cohort": "k66",
        },
    )
    result = agent.run_personalized_plan(request)
    assert "gpa" in result.evidence
    assert "regulation" in result.evidence
    assert result.llm_used is False


def test_personalized_plan_insufficient_data_when_nothing_available():
    request = _request(intent="ADVISOR_PLAN", authorized_context={})
    result = agent.run_personalized_plan(request)
    assert result.fallback == "INSUFFICIENT_DATA"


def test_personalized_plan_enforces_authorization():
    import pytest

    request = _request(
        intent="ADVISOR_PLAN",
        user_id="student_A",
        authorized_context={
            "subject_user_id": "student_B",
            "current_gpa": 6.0,
            "credits_done": 20,
            "target_gpa": 7.5,
            "credits_remaining": 20,
        },
    )
    with pytest.raises(agent.AuthorizationError):
        agent.run_personalized_plan(request)
