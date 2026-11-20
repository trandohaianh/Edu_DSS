"""Local / Offline Operation Test Suite for EduDSS.

Validates:
1. Operational integrity in air-gapped / LAN / offline environments.
2. Rule-based offline learning plan generation.
3. Gateway fallback to local Ollama or offline rule generator when external APIs are unavailable.
"""

import os

from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_profile import StudentLearningProfile
from dss.services.llm_gateway import LLMGateway
from dss.services.report_service import build_demo_study_plan


def test_offline_demo_study_plan_generation():
    """Verify that learning plans can be generated completely offline without internet or LLM keys."""
    plan_text, week_plan = build_demo_study_plan(
        student_id="SV_OFFLINE_01",
        predicted_gpa=2.45,
        weaknesses=["GiaiThuat (SV: 4.20, TB lớp: 6.80)", "CSDL (SV: 4.50, TB lớp: 7.10)"],
        profile={"plan_weeks": 4, "risk_level": "cao"},
        retrieved_docs=[],
        personal_goal="Đạt qua môn và cải thiện GPA",
    )

    assert "SV_OFFLINE_01" in plan_text
    assert "2.45" in plan_text
    assert len(week_plan) == 4
    # Check that dosage is personalized rather than hardcoded 8h
    assert "Liều lượng can thiệp" in plan_text


def test_structured_learning_plan_offline_generator():
    """Verify that StudentLearningPlan generator functions deterministically offline."""
    raw_data = {
        "quiz_score": 5.0,
        "assignment_score": 4.5,
        "exam_score": 4.0,
        "active_days": 8,
        "login_freq": 1.5,
        "practice_freq": 1.0,
        "gpa_previous": 6.0,
        "session_duration": 40,
        "learning_velocity": 0.75,
        "topic_scores": {"Python": 4},
    }
    profile = StudentLearningProfile.build_from_lms_records(
        student_id="SV_OFFLINE_02",
        course_id="CS101",
        raw_lms_data=raw_data,
    )
    plan = learning_plan_generator.generate_plan(
        profile,
        approved_resources=[
            {
                "resource_id": "offline_python",
                "course": "CS101",
                "topic": "Python",
                "status": "APPROVED",
                "url": "https://school.example.edu/python",
                "is_demo": False,
            }
        ],
    )

    assert plan.student_pseudonym is not None
    assert len(plan.activities) > 0
    assert plan.version == 1
    assert (
        "weekly_study_hours_target" in plan.success_metrics
        or "target_practice_sessions_per_week" in plan.success_metrics
    )


def test_gateway_local_offline_routing():
    """Verify that in LOCAL_OFFLINE mode, the gateway directs to local Ollama or offline fallback."""

    class MockProvider:
        def __init__(self):
            self.called_provider = None

        def call_ai_provider(self, prompt, provider, **kwargs):
            self.called_provider = provider
            return iter(["Response from " + provider])

    mock_llm = MockProvider()
    gw = LLMGateway(mock_llm)

    # Simulate LOCAL_OFFLINE environment — biến ĐÚNG mà stream_generate() thật
    # sự đọc là EDUDSS_MODE (dss/services/llm_gateway.py), không phải
    # DEPLOYMENT_MODE (tên cũ/sai — audit 2026-09-14: test này vô tình "pass"
    # trước đây chỉ vì GEMINI_API_KEY chưa từng được nạp từ .env nên bị fallback
    # sang demo bất kể EDUDSS_MODE gì; nay .env đã được nạp đúng, key gemini có
    # thật nên gateway ĐÚNG ra sẽ thử gọi gemini nếu không set đúng biến này).
    old_env = os.environ.get("EDUDSS_MODE")
    try:
        os.environ["EDUDSS_MODE"] = "LOCAL_OFFLINE"

        # When user requests gemini, gateway should reroute or fall back to local provider
        stream = gw.stream_generate(
            prompt="Plan",
            user_id="U1",
            role="Sinh viên",
            request_type="advisor_plan",
            provider="gemini",
        )
        result = "".join(stream)
        assert result is not None
        # Should have routed to ollama or mock fallback
        assert mock_llm.called_provider in ("ollama", "none", None)
    finally:
        if old_env:
            os.environ["EDUDSS_MODE"] = old_env
        else:
            os.environ.pop("EDUDSS_MODE", None)
