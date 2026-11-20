"""Regression suite — 429/rate-limit retry (dss.core.models) và Multi-LLM
Compare mode (dss.services.llm_service).

Không gọi API AI thật (mock provider) — chỉ kiểm chứng ĐÚNG cơ chế retry/
concurrency/error-isolation, không phụ thuộc mạng hay quota thật.
"""
from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import pytest

import dss.config as dss_config
import dss.core.models as models_mod
from dss.services import llm_service


# ---------------------------------------------------------------------------
# _is_rate_limit_error / _call_with_rate_limit_retry
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("message,expected", [
    ("Error code: 429 - Rate limit reached", True),
    ("google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED", True),
    ("Too Many Requests", True),
    ("quota exceeded for this API key", True),
    ("Invalid API key provided", False),
    ("model not found: gemini-x", False),
])
def test_is_rate_limit_error_classification(message, expected):
    assert models_mod._is_rate_limit_error(message) is expected


def test_retry_recovers_after_transient_rate_limit():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("429 Too Many Requests")
        return "ok"

    result = models_mod._call_with_rate_limit_retry(flaky, max_attempts=4)
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_raises_after_exhausting_attempts():
    def always_429():
        raise Exception("429 rate limit")

    with pytest.raises(Exception, match="429"):
        models_mod._call_with_rate_limit_retry(always_429, max_attempts=2)


def test_non_rate_limit_error_is_not_retried():
    calls = {"n": 0}

    def bad_key():
        calls["n"] += 1
        raise Exception("Invalid API key")

    with pytest.raises(Exception, match="Invalid API key"):
        models_mod._call_with_rate_limit_retry(bad_key, max_attempts=4)
    assert calls["n"] == 1  # không retry — lỗi khác 429 thì thử lại vô ích


def test_call_ai_provider_yields_friendly_message_after_rate_limit_exhausted():
    """End-to-end qua đúng generator thật `call_ai_provider('gemini', ...)` —
    không lộ '429' thô, không traceback, đúng 1 thông báo thân thiện."""
    provider = models_mod.MultiAIProvider()

    class FakeClient:
        class models:
            @staticmethod
            def generate_content_stream(*a, **kw):
                raise Exception("429 RESOURCE_EXHAUSTED: rate limit exceeded")

    with patch.object(models_mod, "GEMINI_AVAILABLE", True), \
         patch.object(models_mod, "genai") as fake_genai:
        fake_genai.Client.return_value = FakeClient()
        fake_genai.types.GenerateContentConfig = MagicMock()
        fake_genai.types.ThinkingConfig = MagicMock()
        chunks = list(provider.call_ai_provider(
            "test prompt", provider="gemini", api_key="fake-key", model_name="gemini-3.6-flash"
        ))

    assert len(chunks) == 1
    assert "Traceback" not in chunks[0]
    assert "429" not in chunks[0]
    assert "giới hạn tần suất" in chunks[0]


def test_call_ai_provider_model_not_found_still_falls_back_immediately():
    """Regression cho tương tác giữa 2 cơ chế: lỗi model-not-found (khác 429)
    PHẢI chuyển model kế tiếp ngay, không bị trì hoãn bởi logic backoff 429."""
    provider = models_mod.MultiAIProvider()
    call_log = []

    class FakeClient:
        class models:
            @staticmethod
            def generate_content_stream(model, *a, **kw):
                call_log.append(model)
                if model == models_mod.AI_MODEL_CATALOG["gemini"][0]:
                    raise Exception("404 model not found")
                return iter([MagicMock(text="phan hoi gia lap")])

    with patch.object(models_mod, "GEMINI_AVAILABLE", True), \
         patch.object(models_mod, "genai") as fake_genai:
        fake_genai.Client.return_value = FakeClient()
        fake_genai.types.GenerateContentConfig = MagicMock()
        fake_genai.types.ThinkingConfig = MagicMock()
        chunks = list(provider.call_ai_provider(
            "test prompt", provider="gemini", api_key="fake-key",
            model_name=models_mod.AI_MODEL_CATALOG["gemini"][0],
        ))

    assert call_log == models_mod.AI_MODEL_CATALOG["gemini"][:2]
    assert chunks == ["phan hoi gia lap"]


# ---------------------------------------------------------------------------
# Audit 2026-09-14 — .env loading, model catalog, thinking_level, billing
# classification, provider health, automatic-selection gating.
# ---------------------------------------------------------------------------
def test_env_path_pinned_to_app_env_not_repo_root():
    """dss.config phải nạp ĐÚNG app/.env, không phải .env ở gốc repo (2 file
    khác nhau — gốc repo chỉ có OPENAI_API_KEY, thiếu GEMINI_API_KEY/GROQ_API_KEY)."""
    from pathlib import Path

    assert dss_config._ENV_PATH.name == ".env"
    # Thư mục ứng dụng là thư mục chứa gói dss/: app/ trong monorepo, gốc repo khi
    # chạy repo Edu_DSS độc lập. Không so tên thư mục để test không phụ thuộc bố cục.
    app_root = Path(dss_config.__file__).resolve().parent.parent
    assert dss_config._ENV_PATH.parent == app_root
    assert (app_root / "dss" / "__init__.py").is_file()


def test_dotenv_override_false_lets_exported_var_win(tmp_path, monkeypatch):
    """Biến môi trường THẬT đã export trước KHÔNG bị .env ghi đè (override=False)."""
    from dotenv import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TEST_KEY=from_dotenv_file\n", encoding="utf-8")
    monkeypatch.setenv("SOME_TEST_KEY", "from_os_environment")

    load_dotenv(dotenv_path=env_file, override=False)
    assert os.environ["SOME_TEST_KEY"] == "from_os_environment"


def test_dotenv_fills_missing_var_from_env_file(tmp_path, monkeypatch):
    """Biến CHƯA có trong môi trường thì được điền từ .env."""
    from dotenv import load_dotenv

    monkeypatch.delenv("SOME_OTHER_TEST_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_OTHER_TEST_KEY=from_dotenv_file\n", encoding="utf-8")

    load_dotenv(dotenv_path=env_file, override=False)
    assert os.environ["SOME_OTHER_TEST_KEY"] == "from_dotenv_file"


@pytest.mark.skipif(not dss_config._ENV_PATH.exists(), reason="app/.env chỉ tồn tại trên máy dev cục bộ, không commit vào repo")
def test_provider_detection_after_dotenv_loading_real_env():
    """Trên máy có app/.env thật: sau khi dss.config đã nạp (import time), các
    biến môi trường AI PHẢI hiện diện trong os.environ (dotenv thật sự chạy)."""
    keys_in_env_file = dss_config._ENV_PATH.read_text(encoding="utf-8")
    for var_name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        if var_name in keys_in_env_file:
            assert os.environ.get(var_name), f"{var_name} có trong app/.env nhưng không thấy trong os.environ sau khi import dss.config"


def test_gemini_model_catalog_uses_verified_current_models():
    """Model catalog Gemini không còn model đã bị khai tử (xác nhận qua audit
    thực tế 2026-09-14: gemini-1.5-flash/gemini-2.0-flash/gemini-1.5-pro trả 404)."""
    catalog = models_mod.AI_MODEL_CATALOG["gemini"]
    for retired in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"):
        assert retired not in catalog
    assert catalog[0] == "gemini-flash-lite-latest"  # đã gọi thử thật thành công qua đúng gateway


def test_groq_model_catalog_uses_verified_current_models():
    """Model catalog Groq không còn model đã bị khai tử (xác nhận qua audit
    thực tế: llama-3.3-70b-versatile/llama-3.1-8b-instant/mixtral-8x7b-32768/
    gemma2-9b-it không còn tồn tại trong danh sách model của Groq)."""
    catalog = models_mod.AI_MODEL_CATALOG["groq"]
    for retired in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"):
        assert retired not in catalog
    assert catalog[0] == "openai/gpt-oss-20b"  # đã xác nhận thành công qua đúng MultiAIProvider.call_ai_provider


@pytest.mark.parametrize("model,expected_level", [
    ("gemini-flash-latest", "LOW"),        # xác nhận qua audit: KHÔNG hỗ trợ MINIMAL
    ("gemini-flash-lite-latest", "MINIMAL"),
    ("gemini-pro-latest", "LOW"),
    ("unknown-future-model-xyz", None),    # model lạ -> KHÔNG đoán, không gửi thinking_config
])
def test_gemini_thinking_level_explicit_per_model_not_substring_heuristic(model, expected_level):
    assert models_mod._resolve_gemini_thinking_level(model) == expected_level


@pytest.mark.parametrize("message,expected", [
    ("Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue...', 'code': 'credit_balance_exhausted'}}", True),
    ("400 INVALID_ARGUMENT: insufficient_quota", True),
    ("You exceeded your current quota, please check your plan and billing details.", True),
    ("Error code: 429 - Rate limit reached, please slow down", False),
    ("model not found: gemini-x", False),
])
def test_is_billing_required_error_classification(message, expected):
    assert models_mod._is_billing_required_error(message) is expected


def test_billing_required_error_is_excluded_from_rate_limit_classification():
    """Lỗi hết hạn mức thanh toán KHÔNG được coi là rate-limit tạm thời (2 loại
    lỗi này cùng có mã 429 nhưng cách xử lý đúng khác hẳn nhau — retry vô ích
    với billing, hữu ích với rate-limit thật)."""
    billing_msg = "Error code: 429 - insufficient_quota: credit_balance_exhausted"
    assert models_mod._is_billing_required_error(billing_msg) is True
    assert models_mod._is_rate_limit_error(billing_msg) is False


def test_call_ai_provider_openai_billing_required_yields_friendly_message_without_wasted_retries():
    """Regression cho lỗi thật đã audit (OpenAI insufficient_quota) — PHẢI báo
    đúng thông báo 'hết hạn mức thanh toán', KHÔNG lặp lại 4 lần backoff vô ích
    (khác hẳn rate-limit thật), và KHÔNG lộ traceback/JSON lỗi thô."""
    provider = models_mod.MultiAIProvider()
    call_log = []

    class FakeOpenAIClient:
        class chat:
            class completions:
                @staticmethod
                def create(*a, **kw):
                    call_log.append(1)
                    raise Exception(
                        "Error code: 429 - {'error': {'message': 'You have no credits remaining.', "
                        "'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}"
                    )

    with patch.object(models_mod, "OPENAI_AVAILABLE", True), \
         patch.object(models_mod, "openai") as fake_openai_module:
        fake_openai_module.OpenAI.return_value = FakeOpenAIClient()
        chunks = list(provider.call_ai_provider(
            "test prompt", provider="openai", api_key="fake-key", model_name="gpt-4o-mini",
        ))

    assert len(call_log) == 1  # KHÔNG retry billing error nhiều lần (khác rate-limit thật)
    assert len(chunks) == 1
    assert "hết hạn mức thanh toán" in chunks[0]
    assert "credit_balance_exhausted" not in chunks[0]
    assert "insufficient_quota" not in chunks[0]
    assert "Traceback" not in chunks[0]


# ---------------------------------------------------------------------------
# Structured provider health (dss.services.llm_gateway) — Mục 7/8/9 audit
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=False)
def _clear_health_cache():
    from dss.services import llm_gateway
    llm_gateway._HEALTH_CACHE.clear()
    yield
    llm_gateway._HEALTH_CACHE.clear()


@pytest.mark.parametrize("message,expected_category", [
    ("Error code: 429 - insufficient_quota: credit_balance_exhausted", "BILLING_REQUIRED"),
    ("404 NOT_FOUND: models/gemini-1.5-flash is not found", "MODEL_NOT_FOUND"),
    ("401 Unauthorized: invalid credentials", "AUTH_ERROR"),
    ("400 INVALID_ARGUMENT: api key not valid", "INVALID_KEY"),
    ("Connection timeout while reaching api.groq.com", "NETWORK_ERROR"),
])
def test_classify_provider_error_categories(message, expected_category):
    from dss.services import llm_gateway
    assert llm_gateway.classify_provider_error(Exception(message)) == expected_category


def test_provider_health_to_dict_schema_has_no_key_material_field():
    """to_dict() không có field nào CHỨA GIÁ TRỊ key thật theo thiết kế — chỉ
    có field boolean 'key_detected' (có/không), không có field nào giữ chính
    key. Kiểm tra CẤU TRÚC schema để không ai vô tình thêm field kiểu
    'api_key'/'raw_key'/'secret_value' vào sau này mà không bị test bắt lỗi."""
    from dss.services import llm_gateway
    health = llm_gateway.ProviderHealth("gemini", True, True, model="gemini-flash-latest", category="READY", detail="")
    result = health.to_dict()
    allowed_fields = {"provider", "configured", "key_detected", "model", "category", "friendly_label", "detail"}
    assert set(result.keys()) == allowed_fields
    forbidden_field_names = {"api_key", "raw_key", "secret", "secret_value", "token", "token_value", "traceback", "stack", "stacktrace"}
    assert not (set(result.keys()) & forbidden_field_names)


def test_is_known_unhealthy_true_only_after_real_negative_test(_clear_health_cache):
    from dss.services import llm_gateway
    # Chưa từng kiểm tra -> không bị chặn oan.
    assert llm_gateway.is_known_unhealthy("openai") is False
    llm_gateway.record_provider_health("openai", llm_gateway.ProviderHealth("openai", True, True, category=llm_gateway.HEALTH_BILLING_REQUIRED))
    assert llm_gateway.is_known_unhealthy("openai") is True
    # Provider READY không bị coi là unhealthy.
    llm_gateway.record_provider_health("groq", llm_gateway.ProviderHealth("groq", True, True, category=llm_gateway.HEALTH_READY))
    assert llm_gateway.is_known_unhealthy("groq") is False


def test_automatic_selection_skips_known_unhealthy_provider(_clear_health_cache):
    """Mục 9 — Groq/Gemini READY, OpenAI BILLING_REQUIRED -> tự động chọn
    KHÔNG BAO GIỜ là OpenAI, dù OpenAI đứng cuối danh sách ưu tiên vẫn được bỏ qua
    hoàn toàn (không rơi về OpenAI dù Groq/Gemini giả lập KHÔNG có key)."""
    from dss.services import llm_gateway
    from dss.services import admin_ai_config

    with patch.object(admin_ai_config, "get_default_provider", return_value=None):
        llm_gateway.record_provider_health("openai", llm_gateway.ProviderHealth("openai", True, True, category=llm_gateway.HEALTH_BILLING_REQUIRED))

        fake_llm = MagicMock()
        fake_llm.get_api_key_from_secrets.side_effect = lambda p: "fake-groq-key" if p == "groq" else ("fake-openai-key" if p == "openai" else "")

        result = llm_service.resolve_auto_provider(fake_llm)
        assert result is not None
        assert result["provider_key"] != "openai"
        assert result["provider_key"] == "groq"


# ---------------------------------------------------------------------------
# Multi-LLM Compare mode — llm_service.compare_providers
# ---------------------------------------------------------------------------
class _FakeLLMForCompare:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        import threading
        self._lock = threading.Lock()

    def generate_personalized_advice(self, provider, model_name, **kwargs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.2)
            if provider == "broken":
                raise RuntimeError("simulated crash")
            if provider == "errors_out":
                yield "Lỗi Gemini: simulated API error"
                return
            yield f"ket qua tu {provider} ({model_name})"
        finally:
            with self._lock:
                self.active -= 1


def _spec(key, label, model="m1"):
    return {"provider_key": key, "provider_label": label, "model_name": model, "call_kwargs": {}}


def test_compare_providers_runs_concurrently_within_cap():
    fake = _FakeLLMForCompare()
    specs = [_spec(k, k) for k in ["gemini", "groq", "openai", "hf1", "hf2"]]

    t0 = time.time()
    results = llm_service.compare_providers(fake, specs, student_weaknesses=[], predicted_gpa=5.0)
    elapsed = time.time() - t0

    assert elapsed < 1.4, "phải chạy song song, không tuần tự (5 * 0.2s = 1.0s tối thiểu nếu tuần tự)"
    assert fake.max_active <= dss_config.MAX_CONCURRENT_REQUESTS
    assert [r.provider_label for r in results] == ["gemini", "groq", "openai", "hf1", "hf2"]


def test_compare_providers_isolates_per_provider_errors():
    fake = _FakeLLMForCompare()
    specs = [_spec("gemini", "Gemini"), _spec("broken", "Broken"), _spec("errors_out", "ErrorsOut")]

    results = llm_service.compare_providers(fake, specs, student_weaknesses=[], predicted_gpa=5.0)
    by_label = {r.provider_label: r for r in results}

    assert by_label["Gemini"].error is None
    assert "ket qua tu gemini" in by_label["Gemini"].text

    assert by_label["Broken"].error is not None
    assert "simulated crash" in by_label["Broken"].error

    assert by_label["ErrorsOut"].error == "Lỗi Gemini: simulated API error"
    assert by_label["ErrorsOut"].text == ""


def test_compare_providers_empty_spec_list_returns_empty():
    fake = _FakeLLMForCompare()
    assert llm_service.compare_providers(fake, [], student_weaknesses=[], predicted_gpa=5.0) == []


def test_max_concurrent_requests_is_a_config_value_not_hardcoded():
    """MAX_CONCURRENT_REQUESTS phải nằm trong config, không hard-code trong
    llm_service.py — kiểm tra bằng cách patch giá trị config và xác nhận
    compare_providers thực sự tôn trọng giá trị mới."""
    fake = _FakeLLMForCompare()
    specs = [_spec(str(i), str(i)) for i in range(5)]
    with patch.object(dss_config, "MAX_CONCURRENT_REQUESTS", 1):
        llm_service.compare_providers(fake, specs, student_weaknesses=[], predicted_gpa=5.0)
    assert fake.max_active == 1
