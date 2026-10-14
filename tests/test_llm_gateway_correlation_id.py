"""FINAL PRODUCTION GAP CLOSURE — Phần 3/4: mỗi thông báo lỗi CUỐI CÙNG
(terminal — không còn provider dự phòng nào để thử) hiển thị cho người dùng
phải kèm 1 "Mã sự cố" (correlation ID) ngắn, để Admin/hỗ trợ tra được đúng
log kỹ thuật của lượt gọi đó — mà KHÔNG lộ bất kỳ chi tiết kỹ thuật nào
(exception message, API key, path) ra UI."""
from __future__ import annotations

import re

from dss.services.llm_gateway import LLMGateway


def test_no_configured_provider_error_includes_correlation_id(monkeypatch):
    """Hết toàn bộ chuỗi fallback (không có provider nào cấu hình được key) ->
    thông báo cuối cùng phải kèm 'Mã sự cố: AI-XXXXXXXX'."""
    from dss.core import data_helpers

    monkeypatch.setattr(data_helpers, "is_production_environment", lambda: True)
    monkeypatch.setattr("dss.services.llm_gateway.is_production_environment", lambda: True)

    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", None  # không có api_key

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setenv("DSS_FALLBACK_1", "groq")
    monkeypatch.setenv("DSS_FALLBACK_2", "openai")

    gateway = LLMGateway(llm_integration=None)
    full_answer = "".join(gateway.stream_generate(
        prompt="Câu hỏi bất kỳ", user_id="sv_test", role="Sinh viên", request_type="advisor_chat",
    ))

    assert "Mã sự cố: AI-" in full_answer
    correlation_id = re.search(r"Mã sự cố: AI-([0-9a-f]{8})", full_answer)
    assert correlation_id is not None, f"Không tìm thấy mã sự cố hợp lệ trong: {full_answer!r}"


def test_correlation_id_error_message_leaks_no_technical_detail(monkeypatch):
    """Thông báo lỗi cuối cùng KHÔNG được chứa stack trace/exception
    class/path/API key — chỉ câu thân thiện + mã sự cố."""
    from dss.core import data_helpers
    monkeypatch.setattr("dss.services.llm_gateway.is_production_environment", lambda: True)

    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", None

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setenv("DSS_FALLBACK_1", "groq")
    monkeypatch.setenv("DSS_FALLBACK_2", "openai")

    gateway = LLMGateway(llm_integration=None)
    full_answer = "".join(gateway.stream_generate(
        prompt="Câu hỏi bất kỳ", user_id="sv_test", role="Sinh viên", request_type="advisor_chat",
    ))

    lowered = full_answer.lower()
    for leak in ("traceback", "site-packages", "d:\\klt", "api_key=", "secret", ".py\", line"):
        assert leak not in lowered, f"Thông báo lỗi rò rỉ chi tiết kỹ thuật: chứa '{leak}'"
