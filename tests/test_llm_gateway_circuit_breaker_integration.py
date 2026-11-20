"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 16: Circuit Breaker phải
thực sự được `LLMGateway.stream_generate()` dùng — không chỉ tồn tại như 1
module cô lập chưa ai gọi (đúng nguyên tắc đã lặp lại nhiều lần trong phiên
này: không tuyên bố 'đã xây' nếu chưa wire vào đường chạy thật)."""

from __future__ import annotations

import pytest

from dss.services import circuit_breaker as cb
from dss.services.llm_gateway import LLMGateway


@pytest.fixture(autouse=True)
def _reset_breaker():
    cb.reset_all()
    yield
    cb.reset_all()


class _AlwaysFailingIntegration:
    def __init__(self):
        self.attempts: list[str] = []

    def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
        self.attempts.append(provider)
        yield "⚠️ Hệ thống AI hiện gặp sự cố. Vui lòng thử lại sau hoặc chọn nguồn AI khác."

    def get_api_key_from_secrets(self, provider_name):
        return "fake-key"


def _patch_chain(monkeypatch, fake_integration, chain=("gemini", "groq", "groq")):
    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", "fake-key"

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", chain[0])
    monkeypatch.setenv("DSS_FALLBACK_1", chain[1])
    monkeypatch.setenv("DSS_FALLBACK_2", chain[2])
    return LLMGateway(llm_integration=fake_integration)


def test_repeated_failures_open_circuit_and_skip_provider_on_next_request(monkeypatch):
    """Sau đủ số lỗi liên tiếp (ngưỡng Circuit Breaker), CÙNG 1 provider phải
    bị bỏ qua NGAY (không thử gọi lại) ở LƯỢT REQUEST TIẾP THEO."""
    fake = _AlwaysFailingIntegration()
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))

    # Lượt 1: gemini lỗi -> failover sang groq (cũng lỗi trong fake này, nhưng
    # đủ để tích lũy lỗi liên tiếp cho gemini qua NHIỀU lượt request). Mỗi
    # lượt dùng PROMPT KHÁC NHAU — nếu không, sau lượt đầu chuỗi rơi tới
    # nhánh "demo" (thành công) và bị exact-cache lưu lại, khiến các lượt
    # sau với CÙNG prompt được phục vụ thẳng từ cache (không gọi lại
    # gemini/groq nữa) — làm sai lệch phép thử tích lũy lỗi liên tiếp này.
    for i in range(cb._FAILURE_THRESHOLD):
        fake.attempts.clear()
        list(
            gateway.stream_generate(
                prompt=f"Câu hỏi lượt {i}",
                user_id="sv_test",
                role="Sinh viên",
                request_type="advisor_chat",
            )
        )
        assert fake.attempts[0] == "gemini", "Mỗi lượt trong ngưỡng đầu vẫn phải thử gemini trước"

    assert cb.get_state("gemini") == cb.STATE_OPEN, "Sau đủ ngưỡng lỗi liên tiếp, mạch gemini phải OPEN"

    # Lượt kế tiếp: mạch gemini đang OPEN -> KHÔNG được thử gemini nữa, nhảy
    # thẳng sang groq.
    fake.attempts.clear()
    list(
        gateway.stream_generate(
            prompt="Câu hỏi khác",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert "gemini" not in fake.attempts, (
        f"Circuit Breaker phải bỏ qua provider đang OPEN — thực tế vẫn thử: {fake.attempts}"
    )


def test_success_keeps_circuit_closed_for_healthy_provider():
    """Provider khỏe mạnh (không lỗi) không bao giờ bị Circuit Breaker chặn."""
    assert cb.get_state("groq") == cb.STATE_CLOSED
    assert cb.allow_request("groq") is True


def test_one_provider_circuit_open_does_not_affect_other_provider(monkeypatch):
    """1 provider bị mở mạch KHÔNG được làm tắt AI cho provider khác — test
    tích hợp thật qua stream_generate, không chỉ unit test module thuần."""

    class _GeminiFailsGroqWorks:
        def __init__(self):
            self.attempts = []

        def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
            self.attempts.append(provider)
            if provider == "gemini":
                yield "💳 Hệ thống AI (Gemini) hiện không thể dùng do tài khoản đã hết hạn mức thanh toán/tín dụng."
                return
            yield "Câu trả lời thật từ Groq."

        def get_api_key_from_secrets(self, provider_name):
            return "fake-key"

    fake = _GeminiFailsGroqWorks()
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))

    for i in range(cb._FAILURE_THRESHOLD):
        fake.attempts.clear()
        list(
            gateway.stream_generate(
                prompt=f"Câu hỏi lượt {i}",
                user_id="sv_test",
                role="Sinh viên",
                request_type="advisor_chat",
            )
        )

    assert cb.get_state("gemini") == cb.STATE_OPEN
    assert cb.get_state("groq") == cb.STATE_CLOSED

    fake.attempts.clear()
    full_answer = "".join(
        gateway.stream_generate(
            prompt="Câu hỏi mới",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert "gemini" not in fake.attempts
    assert "Câu trả lời thật từ Groq." in full_answer
