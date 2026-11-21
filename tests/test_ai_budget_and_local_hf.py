"""Ngân sách AI chặn thật (5 USD/tháng) và AI chạy tại chỗ tắt mặc định (21/11/2026).

Hồi quy cho sự cố: chưa có khoá API thì bấm "Tạo kế hoạch bằng AI" tự tải Qwen2.5-7B
(~15 GB) và chạy trên CPU; ngân sách AI chỉ cảnh báo (viết cứng 300 USD/tháng).
"""

from __future__ import annotations

import pytest

from dss import config as dss_config
from dss.services import llm_gateway, token_tracker
from dss.services.llm_gateway import LLMGateway, QuotaExceededError


# ------------------------------------------------------------------ AI tại chỗ
def test_local_hf_is_off_by_default_and_needs_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("EDUDSS_ENABLE_LOCAL_HF", raising=False)
    assert dss_config.local_hf_enabled() is False
    for value in ("1", "true", "YES", " on "):
        monkeypatch.setenv("EDUDSS_ENABLE_LOCAL_HF", value)
        assert dss_config.local_hf_enabled() is True
    monkeypatch.setenv("EDUDSS_ENABLE_LOCAL_HF", "0")
    assert dss_config.local_hf_enabled() is False


def test_huggingface_call_never_loads_model_when_disabled(monkeypatch):
    from dss.core.models import MultiAIProvider

    monkeypatch.delenv("EDUDSS_ENABLE_LOCAL_HF", raising=False)

    def _boom():
        raise AssertionError("Không được nạp transformers/tải mô hình khi AI tại chỗ đang tắt")

    monkeypatch.setattr(dss_config, "_ensure_local_llm_libs", _boom)
    provider = MultiAIProvider.__new__(MultiAIProvider)  # không cần khởi tạo đầy đủ cho nhánh chặn sớm
    out = "".join(provider.call_ai_provider("Xin chào", provider="huggingface"))
    assert out.startswith("Lỗi Hugging Face")
    assert "EDUDSS_ENABLE_LOCAL_HF" in out


def test_ready_provider_list_excludes_huggingface_without_opt_in(monkeypatch):
    from dss.tabs import ai_advisor

    class _NoKeys:
        def get_api_key_from_secrets(self, _provider):
            return None

    monkeypatch.setattr(dss_config, "HF_AVAILABLE", True)
    monkeypatch.setattr(ai_advisor, "_check_ollama_running", lambda: False)
    monkeypatch.delenv("EDUDSS_ENABLE_LOCAL_HF", raising=False)
    assert ai_advisor._list_ready_cloud_providers(_NoKeys(), {}) == []
    monkeypatch.setenv("EDUDSS_ENABLE_LOCAL_HF", "1")
    assert ai_advisor._list_ready_cloud_providers(_NoKeys(), {}) == [("huggingface", "Hugging Face (Local/Cloud)")]


# ------------------------------------------------------------------ cấu hình ngân sách
def test_budget_defaults_to_5_usd_per_month_and_a_thirtieth_per_day(monkeypatch):
    for name in ("EDUDSS_AI_MONTHLY_BUDGET_USD", "EDUDSS_AI_DAILY_BUDGET_USD", "EDUDSS_AI_BUDGET_WARNING_RATIO"):
        monkeypatch.delenv(name, raising=False)
    cfg = token_tracker.budget_config()
    assert cfg["monthly_budget_usd"] == 5.0
    assert cfg["daily_budget_usd"] == pytest.approx(5.0 / 30, abs=1e-4)
    assert cfg["warning_threshold_ratio"] == 0.8


def test_budget_reads_environment_and_ignores_bad_values(monkeypatch):
    monkeypatch.setenv("EDUDSS_AI_MONTHLY_BUDGET_USD", "10")
    monkeypatch.setenv("EDUDSS_AI_DAILY_BUDGET_USD", "abc")  # sai → mặc định tháng/30
    monkeypatch.setenv("EDUDSS_AI_BUDGET_WARNING_RATIO", "5")  # ngoài (0,1] → 0,8
    cfg = token_tracker.budget_config()
    assert cfg["monthly_budget_usd"] == 10.0
    assert cfg["daily_budget_usd"] == pytest.approx(10.0 / 30, abs=1e-4)
    assert cfg["warning_threshold_ratio"] == 0.8


def _status(monthly_cost, daily_cost, monthly_budget=5.0, daily_budget=0.1667):
    return {
        "monthly_cost": monthly_cost,
        "monthly_budget": monthly_budget,
        "daily_cost": daily_cost,
        "daily_budget": daily_budget,
    }


@pytest.mark.parametrize(
    "monthly,daily,allowed,word",
    [
        (1.0, 0.05, True, ""),
        (5.0, 0.0, False, "tháng"),
        (2.0, 0.2, False, "hôm nay"),
    ],
)
def test_check_system_budget_blocks_month_and_day_independently(monkeypatch, monthly, daily, allowed, word):
    monkeypatch.setattr(token_tracker, "get_system_budget_status", lambda: _status(monthly, daily))
    ok, msg = token_tracker.check_system_budget()
    assert ok is allowed
    assert word in msg


def test_check_system_budget_does_not_block_when_ledger_unreadable(monkeypatch):
    def _broken():
        raise OSError("không đọc được")

    monkeypatch.setattr(token_tracker, "get_system_budget_status", _broken)
    assert token_tracker.check_system_budget() == (True, "")


# ------------------------------------------------------------------ cổng AI
class _RecordingProvider:
    def __init__(self):
        self.calls = []

    def call_ai_provider(self, prompt, provider, **kwargs):
        self.calls.append(provider)
        return iter([f"Trả lời từ {provider}"])


def _paid_only_chain(monkeypatch):
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setenv("DSS_FALLBACK_1", "groq")
    monkeypatch.setenv("DSS_FALLBACK_2", "openai")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")


def test_gateway_stops_before_calling_paid_providers_when_budget_spent(monkeypatch):
    _paid_only_chain(monkeypatch)
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (False, "Đã dùng hết ngân sách AI tháng này."))
    provider = _RecordingProvider()
    text = "".join(
        LLMGateway(provider).stream_generate(
            prompt="Câu hỏi ngân sách 1", user_id="U_budget_1", role="Giảng viên / CVHT", provider="gemini", api_key="k"
        )
    )
    assert provider.calls == []
    assert "Đã dùng hết ngân sách AI" in text
    assert "Kế hoạch học tập" in text


def test_gateway_keeps_free_local_provider_when_budget_spent(monkeypatch):
    _paid_only_chain(monkeypatch)
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (False, "hết ngân sách"))
    provider = _RecordingProvider()
    text = "".join(
        LLMGateway(provider).stream_generate(
            prompt="Câu hỏi ngân sách 2", user_id="U_budget_2", role="Giảng viên / CVHT", provider="ollama"
        )
    )
    assert provider.calls and set(provider.calls) <= {"ollama"}
    assert "gemini" not in provider.calls
    assert "Trả lời từ ollama" in text


def test_gateway_calls_paid_provider_when_under_budget(monkeypatch):
    _paid_only_chain(monkeypatch)
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (True, ""))
    provider = _RecordingProvider()
    "".join(
        LLMGateway(provider).stream_generate(
            prompt="Câu hỏi ngân sách 3", user_id="U_budget_3", role="Giảng viên / CVHT", provider="gemini", api_key="k"
        )
    )
    assert provider.calls[:1] == ["gemini"]


def test_quota_gate_raises_when_budget_spent(monkeypatch):
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (False, "hết ngân sách"))
    with pytest.raises(QuotaExceededError, match="hết ngân sách"):
        LLMGateway(None).check_quota_and_rate_limit("U1", "Giảng viên / CVHT", "xin chào")


def test_paid_providers_constant():
    assert set(llm_gateway.PAID_PROVIDERS) == {"gemini", "groq", "openai"}
