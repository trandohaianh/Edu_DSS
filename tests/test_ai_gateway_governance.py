"""Workstream C (Issue AIGOV-001) regression: production AI call sites must
route through LLMGateway, not call a provider directly — see the audit and
fix summary in reports/production_readiness/WORKSTREAM_C_ML_AI_GOVERNANCE.md.

These tests use mocking deliberately (unlike test_learning_explainer.py's
real-embedding-model tests) because what's being verified here is WHICH
CODE PATH is taken — the exact call site and its arguments — not retrieval
quality or generation content.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer
from dss.services.llm_gateway import GatewayError, LLMGateway


@pytest.fixture()
def unique_course():
    suffix = uuid.uuid4().hex[:8]
    return f"TEST_COURSE_AIGOV_{suffix}"


@pytest.fixture()
def llm_integration_stub():
    """A stub with a real embedding call (so CMS retrieval works) but a
    call_ai_provider that would be an obvious, loud regression if ever
    called directly again."""
    import dss.config as dss_config

    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider

    provider = MultiAIProvider()
    provider.get_embedding("khởi động model")
    return provider


def _ingest_lesson(llm_integration, course_id):
    lesson_id, topic_id = f"L_{course_id}", f"T_{course_id}"
    cms_repository.ingest_lecture_material(
        file_bytes="Nội dung bài giảng về hồi quy tuyến tính và các giả định của nó.".encode(),
        file_name=f"{lesson_id}.txt",
        title="Hồi quy tuyến tính",
        course_id=course_id,
        lesson_id=lesson_id,
        topic_id=topic_id,
        lecturer_id="GV_TEST_AIGOV",
        llm_integration=llm_integration,
        learning_outcome="Hiểu hồi quy tuyến tính",
        difficulty="Standard",
        content_type="slide",
        page_or_section="slide 1",
    )
    return lesson_id, topic_id


def test_generate_explanation_routes_through_llm_gateway_not_direct_provider_call(
    llm_integration_stub,
    unique_course,
):
    """The core AIGOV-001 regression guard: generate_explanation() must call
    LLMGateway.stream_generate, and must NEVER call
    MultiAIProvider.call_ai_provider directly — if this test ever fails
    because call_ai_provider was called, that is exactly the bypass this
    Workstream closed."""
    lesson_id, topic_id = _ingest_lesson(llm_integration_stub, unique_course)

    fake_provider = {"provider_key": "groq", "model_name": "test-model", "api_key": "fake-key-for-test"}
    canned_answer = ["Đây ", "là ", "câu trả lời từ Gateway."]

    with (
        patch("dss.services.llm_service.resolve_auto_provider", return_value=fake_provider),
        patch.object(LLMGateway, "stream_generate", return_value=iter(canned_answer)) as mock_stream_generate,
        patch.object(type(llm_integration_stub), "call_ai_provider") as mock_direct_call,
    ):
        result = learning_explainer.generate_explanation(
            llm_integration_stub,
            "Giải thích hồi quy tuyến tính là gì?",
            unique_course,
            lesson_id,
            topic_id,
            explanation_level="Standard",
            user_id="test_student_pseudonym",
            role="Sinh viên",
        )

    assert mock_direct_call.called is False, "generate_explanation must not call call_ai_provider() directly"
    assert mock_stream_generate.called is True, "generate_explanation must route through LLMGateway.stream_generate"
    call_kwargs = mock_stream_generate.call_args.kwargs
    assert call_kwargs["provider"] == "groq"
    assert call_kwargs["user_id"] == "test_student_pseudonym"
    assert call_kwargs["role"] == "Sinh viên"
    assert call_kwargs["request_type"] == "learning_explainer"
    assert result.answer == "Đây là câu trả lời từ Gateway."
    assert result.has_cms_content is True


def test_generate_explanation_honest_failure_when_no_provider_available(llm_integration_stub, unique_course):
    """No provider configured -> honest 'AI unavailable' message, never a
    fabricated answer, and the Gateway is never even reached."""
    lesson_id, topic_id = _ingest_lesson(llm_integration_stub, unique_course)

    with (
        patch("dss.services.llm_service.resolve_auto_provider", return_value=None),
        patch.object(LLMGateway, "stream_generate") as mock_stream_generate,
    ):
        result = learning_explainer.generate_explanation(
            llm_integration_stub,
            "Giải thích hồi quy tuyến tính là gì?",
            unique_course,
            lesson_id,
            topic_id,
            explanation_level="Standard",
        )

    assert mock_stream_generate.called is False
    assert "chưa sẵn sàng" in result.answer
    assert result.has_cms_content is True


def test_advance_socratic_session_threads_user_id_to_gateway(llm_integration_stub, unique_course):
    lesson_id, topic_id = _ingest_lesson(llm_integration_stub, unique_course)
    fake_provider = {"provider_key": "groq", "model_name": "test-model", "api_key": "fake-key"}

    with (
        patch("dss.services.llm_service.resolve_auto_provider", return_value=fake_provider),
        patch.object(LLMGateway, "stream_generate", return_value=iter(["Câu hỏi gợi mở."])) as mock_stream_generate,
    ):
        session = learning_explainer.start_socratic_session(topic_id)
        _, _ = learning_explainer.advance_socratic_session(
            llm_integration_stub,
            session,
            "start",
            unique_course,
            lesson_id,
            "Standard",
            user_id="socratic_pseudonym",
        )

    assert mock_stream_generate.call_args.kwargs["user_id"] == "socratic_pseudonym"


# ---------------------------------------------------------------------------
# compare_providers() — narrower, documented exception (still must enforce
# quota/rate-limit even though it doesn't use the fallback cascade).
# ---------------------------------------------------------------------------


def test_compare_providers_enforces_quota_gate_before_dispatching():
    from dss.services import llm_service

    with patch.object(LLMGateway, "check_quota_and_rate_limit", side_effect=GatewayError("org quota exceeded")):
        results = llm_service.compare_providers(
            llm_integration=MagicMock(),
            provider_specs=[
                {"provider_key": "groq", "provider_label": "Groq", "model_name": "m1", "call_kwargs": {}},
                {"provider_key": "gemini", "provider_label": "Gemini", "model_name": "m2", "call_kwargs": {}},
            ],
            student_weaknesses=["toán"],
            predicted_gpa=2.5,
        )

    assert len(results) == 2
    assert all(r.error == "org quota exceeded" for r in results)
    assert all(r.text == "" for r in results)


def test_compare_providers_dispatches_when_quota_gate_passes():
    from dss.services import llm_service

    mock_llm_integration = MagicMock()
    mock_llm_integration.generate_personalized_advice.return_value = iter(["OK"])

    with patch.object(LLMGateway, "check_quota_and_rate_limit", return_value=None):
        results = llm_service.compare_providers(
            llm_integration=mock_llm_integration,
            provider_specs=[{"provider_key": "groq", "provider_label": "Groq", "model_name": "m1", "call_kwargs": {}}],
            student_weaknesses=["toán"],
            predicted_gpa=2.5,
        )

    assert len(results) == 1
    assert results[0].text == "OK"
    assert results[0].error is None
    assert mock_llm_integration.generate_personalized_advice.called


def test_generate_explanation_retries_once_when_model_returns_empty(llm_integration_stub, unique_course):
    """Đã gặp thật: model trả về rỗng -> giao diện hiện 1 ô trả lời trống chỉ có nhãn nguồn."""
    lesson_id, topic_id = _ingest_lesson(llm_integration_stub, unique_course)
    fake_provider = {"provider_key": "groq", "model_name": "test-model", "api_key": "fake-key-for-test"}
    with (
        patch("dss.services.llm_service.resolve_auto_provider", return_value=fake_provider),
        patch.object(
            LLMGateway, "stream_generate", side_effect=[iter(["", "  "]), iter(["Câu trả lời lần 2."])]
        ) as mock_sg,
    ):
        result = learning_explainer.generate_explanation(
            llm_integration_stub,
            "Hồi quy tuyến tính là gì?",
            unique_course,
            lesson_id,
            topic_id,
            explanation_level="Standard",
            user_id="u",
            role="Sinh viên",
        )
    assert mock_sg.call_count == 2
    assert result.answer == "Câu trả lời lần 2."


def test_generate_explanation_reports_clearly_when_model_stays_empty(llm_integration_stub, unique_course):
    lesson_id, topic_id = _ingest_lesson(llm_integration_stub, unique_course)
    fake_provider = {"provider_key": "groq", "model_name": "test-model", "api_key": "fake-key-for-test"}
    with (
        patch("dss.services.llm_service.resolve_auto_provider", return_value=fake_provider),
        patch.object(LLMGateway, "stream_generate", side_effect=[iter([""]), iter([""])]),
    ):
        result = learning_explainer.generate_explanation(
            llm_integration_stub,
            "Hồi quy tuyến tính là gì?",
            unique_course,
            lesson_id,
            topic_id,
            explanation_level="Standard",
            user_id="u",
            role="Sinh viên",
        )
    assert result.answer.strip(), "Không được trả về câu trả lời rỗng cho giao diện"
    assert "hỏi lại" in result.answer
