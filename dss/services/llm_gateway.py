"""Centralized LLM Gateway — Cổng giao tiếp AI tập trung cho hệ sinh thái EduDSS LMS.

Chịu trách nhiệm toàn bộ các cuộc gọi AI:
1. Định tuyến Provider (Gemini / Groq / OpenAI / Hugging Face / Ollama / Demo)
2. Phân giải API Key an toàn (từ Admin Default Config, Environment, Streamlit Secrets;
   tuyệt đối KHÔNG để Sinh viên thấy hoặc phải cấu hình API key)
3. Định tuyến tới lớp Thử lại DUY NHẤT (Retry with Exponential Backoff) — thực
   thi thật trong core/models.py::_call_with_rate_limit_retry (Tenacity), qua
   MultiAIProvider.call_ai_provider(). LLMGateway KHÔNG tự cài đặt retry riêng
   (audit 2026-09-15, Issue ARCH-AI-001: execute_with_retry() cũ là code chết,
   0 điểm gọi, tham chiếu ProviderError chưa từng được định nghĩa — đã gỡ bỏ
   để chỉ còn ĐÚNG 1 tầng retry, tránh 2 hệ thống retry cạnh tranh nhau).
4. Giới hạn Tần suất (Rate Limiting) & Giới hạn Đồng thời (Concurrency Semaphore)
5. Chuyển tầng Dự phòng (Fallback Cascade): Primary -> Secondary -> Ollama -> Demo Mode
6. Đo lường & Ghi nhận Token, Chi phí (Token Usage & Cost Tracking)
7. Nhật ký Kiểm toán (Audit Logging, không bao giờ ghi API key thô)
8. Quản lý Thời gian chờ (Timeout)
9. Chuẩn hóa Lỗi (Error Normalization)
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import uuid
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import streamlit as st

import dss.config as dss_config
from dss.core.data_helpers import is_production_environment
from dss.services import admin_ai_config, circuit_breaker, token_tracker
from dss.services.context_budget import approximate_token_count
from dss.core.observability import observed, record_operation

_logger = logging.getLogger(__name__)

# H-1 (CRITICAL, đợt audit kiến trúc thương mại 2026-09): request_type nào
# thực sự cần đường "sinh kế hoạch cá nhân hóa" (MultiAIProvider.
# generate_personalized_advice — tự xây prompt riêng từ student_weaknesses/
# predicted_gpa, KHÔNG dùng `prompt` truyền vào stream_generate()). MỌI
# request_type khác PHẢI đi qua call_ai_provider(prompt, ...) — dùng ĐÚNG
# prompt người gọi đã xây (câu hỏi chat, giải thích bài giảng, hỏi nhanh...).
# Trước đây routing dựa vào `hasattr(llm_integration, "generate_personalized_advice")`
# — vì MultiAIProvider (llm_integration DUY NHẤT trong hệ thống) LUÔN có
# phương thức này, nhánh call_ai_provider không bao giờ chạy tới trong thực
# tế: prompt thật của người dùng (advisor_chat/learning_explainer/
# home_quick_chat) bị ÂM THẦM BỎ QUA, AI trả lời cho một "kế hoạch học tập"
# chung (student_weaknesses=[], predicted_gpa=0.0) thay vì câu hỏi họ vừa gõ.
# Xem tests/test_llm_gateway_chat_routing.py (Test 1-3, verify-before-fix).
_PLANNING_REQUEST_TYPES = frozenset({"advisor_plan"})

# H-3 (phát hiện đợt "FINAL PRODUCTION GAP CLOSURE", lộ ra sau khi sửa H-1):
# MultiAIProvider.call_ai_provider() KHÔNG BAO GIỜ raise — nó bắt lỗi nội bộ
# và yield 1 câu THÂN THIỆN duy nhất (không lộ exception thô, đúng thiết kế).
# Nhưng vì không raise, khối `except Exception` của fallback chain không bao
# giờ bắt được các lỗi này — PHẢI tự dò bằng tiền tố câu chữ để biết 1 lượt
# gọi provider thực ra đã THẤT BẠI (và cần thử provider dự phòng tiếp theo)
# thay vì coi là thành công và dừng fallback chain tại đó. Danh sách tiền tố
# này PHẢI khớp CHÍNH XÁC với mọi câu `yield "..."` lỗi trong
# core/models.py::call_ai_provider (xem comment tại _detect_friendly_provider_error).
_PROVIDER_FRIENDLY_ERROR_PREFIXES = ("Lỗi", "⏳", "⚠️", "💳", "🔒")


def _is_friendly_provider_error(text: str) -> bool:
    """True nếu `text` là 1 trong các câu lỗi THÂN THIỆN mà
    `call_ai_provider()` tự yield khi provider thất bại (KHÔNG raise) — xem
    `_PROVIDER_FRIENDLY_ERROR_PREFIXES`. Dùng để quyết định fallback chain có
    nên thử provider kế tiếp hay không, thay vì coi mọi stream không rỗng là
    thành công."""
    return isinstance(text, str) and text.startswith(_PROVIDER_FRIENDLY_ERROR_PREFIXES)

# Giới hạn số cuộc gọi AI đồng thời toàn hệ thống
_GATEWAY_SEMAPHORE = threading.Semaphore(dss_config.MAX_CONCURRENT_REQUESTS)

# Trượt thời gian đếm số request mỗi phút (Rate limiting in-memory)
_REQUEST_TIMESTAMPS: List[float] = []
_RATE_LIMIT_LOCK = threading.Lock()
_MAX_RPM = 60  # Tối đa 60 requests/phút


class GatewayError(Exception):
    """Lớp ngoại lệ chuẩn hóa của LLM Gateway."""
    def __init__(self, message: str, provider: str = "unknown", error_code: str = "GATEWAY_ERROR"):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.error_code = error_code


class RateLimitError(GatewayError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, provider=provider, error_code="RATE_LIMIT_EXCEEDED")


class QuotaExceededError(GatewayError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, provider=provider, error_code="QUOTA_EXCEEDED")


class ModelUnavailableError(GatewayError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, provider=provider, error_code="MODEL_UNAVAILABLE")


class TimeoutError(GatewayError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, provider=provider, error_code="TIMEOUT")


class AuthenticationError(GatewayError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, provider=provider, error_code="AUTH_ERROR")


# ============================================================================
# Mục 7/8 (audit 2026-09-14) — Phân loại sức khoẻ provider CÓ CẤU TRÚC, dùng
# cho trang Cấu hình AI của Admin (Mục 8) và lựa chọn provider tự động (Mục 9).
# Đây là một lượt "kiểm tra thăm dò" (health probe) THẬT, ĐỘC LẬP với luồng
# chat thật (MultiAIProvider.call_ai_provider ở core/models.py) — không đổi
# hành vi/luồng dự phòng đang chạy cho Sinh viên/Giảng viên, chỉ thêm một công
# cụ chẩn đoán riêng cho Admin, có quyền truy cập exception THẬT để phân loại
# chính xác (call_ai_provider vốn đã swallow exception thành text thân thiện
# nên không đủ chi tiết để phân biệt AUTH_ERROR/NETWORK_ERROR/SDK_ERROR...).
# ============================================================================
HEALTH_READY = "READY"
HEALTH_NOT_CONFIGURED = "NOT_CONFIGURED"
HEALTH_INVALID_KEY = "INVALID_KEY"
HEALTH_AUTH_ERROR = "AUTH_ERROR"
HEALTH_MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
HEALTH_BILLING_REQUIRED = "BILLING_REQUIRED"
HEALTH_QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
HEALTH_NETWORK_ERROR = "NETWORK_ERROR"
HEALTH_SDK_ERROR = "SDK_ERROR"
HEALTH_CONFIG_ERROR = "CONFIG_ERROR"
HEALTH_UNKNOWN_ERROR = "UNKNOWN_ERROR"

PROVIDER_HEALTH_FRIENDLY_LABEL = {
    HEALTH_READY: "Kết nối thành công",
    HEALTH_NOT_CONFIGURED: "Chưa cấu hình",
    HEALTH_INVALID_KEY: "Key không hợp lệ",
    HEALTH_AUTH_ERROR: "Lỗi xác thực",
    HEALTH_MODEL_NOT_FOUND: "Model không khả dụng",
    HEALTH_BILLING_REQUIRED: "Cần thanh toán/hết hạn mức",
    HEALTH_QUOTA_EXCEEDED: "Vượt hạn mức tần suất",
    HEALTH_NETWORK_ERROR: "Lỗi mạng",
    HEALTH_SDK_ERROR: "Lỗi SDK",
    HEALTH_CONFIG_ERROR: "Lỗi cấu hình",
    HEALTH_UNKNOWN_ERROR: "Lỗi không xác định",
}


def classify_provider_error(exc: BaseException) -> str:
    """Phân loại 1 exception THẬT (chưa qua swallow) thành 1 health category
    chuẩn hoá. CHỈ dựa vào type/message của exception để xếp loại — KHÔNG bao
    giờ trả về hay log lại message thô chứa key (điểm gọi phải tự cắt/ẩn nếu
    muốn hiển thị chi tiết kỹ thuật cho Admin)."""
    msg = str(exc).lower()
    type_name = type(exc).__name__

    if any(k in msg for k in ("insufficient_quota", "credit_balance_exhausted", "no credits remaining", "add credits")):
        return HEALTH_BILLING_REQUIRED
    if any(k in msg for k in ("api_key_invalid", "invalid api key", "api key not valid", "invalid_api_key")):
        return HEALTH_INVALID_KEY
    if any(k in msg for k in ("401", "unauthorized")):
        return HEALTH_AUTH_ERROR
    if any(k in msg for k in ("403", "permission", "blocked", "consumer")):
        return HEALTH_AUTH_ERROR
    if any(k in msg for k in ("429", "quota exceeded", "resource_exhausted", "resource exhausted", "rate limit", "too many requests")):
        return HEALTH_QUOTA_EXCEEDED
    if any(k in msg for k in ("404", "not found", "does not exist", "decommissioned", "deprecated")):
        return HEALTH_MODEL_NOT_FOUND
    if any(k in msg for k in ("connection", "timeout", "network", "resolve", "unreachable")):
        return HEALTH_NETWORK_ERROR
    if any(k in msg for k in ("invalid_argument", "invalid argument", "config")):
        return HEALTH_CONFIG_ERROR
    if type_name in ("ImportError", "ModuleNotFoundError", "AttributeError", "TypeError"):
        return HEALTH_SDK_ERROR
    return HEALTH_UNKNOWN_ERROR


class ProviderHealth:
    """Kết quả kiểm tra sức khoẻ 1 provider — dùng cho Admin UI (Mục 8) và
    lựa chọn provider tự động (Mục 9). to_dict() KHÔNG BAO GIỜ chứa key thật,
    prefix key, suffix key hay traceback — chỉ category + 1 câu mô tả an toàn."""

    def __init__(self, provider_key, configured, key_detected, model=None, category=HEALTH_NOT_CONFIGURED, detail=""):
        self.provider_key = provider_key
        self.configured = configured
        self.key_detected = key_detected
        self.model = model
        self.category = category
        self.detail = detail

    @property
    def is_ready(self) -> bool:
        return self.category == HEALTH_READY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_key,
            "configured": self.configured,
            "key_detected": self.key_detected,
            "model": self.model,
            "category": self.category,
            "friendly_label": PROVIDER_HEALTH_FRIENDLY_LABEL.get(self.category, self.category),
            "detail": self.detail,
        }


def check_provider_health(provider_key: str, model_name: Optional[str] = None, gateway: Optional["LLMGateway"] = None) -> ProviderHealth:
    """Thăm dò sức khoẻ THẬT của 1 provider và GHI LẠI kết quả vào cache TTL
    (dùng cho is_known_unhealthy() ở lựa chọn tự động, Mục 9)."""
    result = _probe_provider_health(provider_key, model_name, gateway)
    record_provider_health(provider_key, result)
    return result


def _probe_provider_health(provider_key: str, model_name: Optional[str] = None, gateway: Optional["LLMGateway"] = None) -> ProviderHealth:
    """Thăm dò sức khoẻ THẬT của 1 provider bằng 1 lệnh gọi tối thiểu qua đúng
    SDK thật (KHÔNG qua call_ai_provider — hàm đó vốn đã swallow exception
    thành text thân thiện nên không đủ chi tiết để phân loại chính xác).
    KHÔNG BAO GIỜ trả về giá trị key thật trong ProviderHealth."""
    gw = gateway or LLMGateway()
    key = gw.resolve_api_key(provider_key)

    if provider_key == "ollama":
        from dss.core.models import _check_ollama_running, list_ollama_models, ollama_base_url, resolve_ollama_model
        base_url = ollama_base_url()
        ready = _check_ollama_running(base_url)
        if ready and not list_ollama_models(base_url):
            return ProviderHealth(provider_key, True, True, model="", category=HEALTH_CONFIG_ERROR,
                                   detail="Ollama đang chạy nhưng chưa có model nào — chạy `ollama pull qwen2.5:7b`.")
        return ProviderHealth(provider_key, True, True, model=resolve_ollama_model(model_name, base_url) if ready else "ollama_local",
                               category=HEALTH_READY if ready else HEALTH_NETWORK_ERROR,
                               detail="" if ready else f"Ollama không phản hồi tại {base_url}.")

    if not key:
        return ProviderHealth(provider_key, False, False, model=model_name, category=HEALTH_NOT_CONFIGURED,
                               detail="Chưa tìm thấy API key qua secrets/env.")

    from dss.core.models import AI_MODEL_CATALOG
    resolved_model = model_name or (AI_MODEL_CATALOG.get(provider_key, [""])[0] if provider_key in AI_MODEL_CATALOG else "")

    try:
        if provider_key == "gemini":
            import google.genai as genai
            from dss.core.models import _resolve_gemini_thinking_level
            client = genai.Client(api_key=key, http_options=genai.types.HttpOptions(timeout=20000))
            gen_kwargs = {"max_output_tokens": 10}
            thinking_level = _resolve_gemini_thinking_level(resolved_model)
            if thinking_level:
                gen_kwargs["thinking_config"] = genai.types.ThinkingConfig(thinking_level=thinking_level)
            client.models.generate_content(model=resolved_model, contents="Say OK", config=genai.types.GenerateContentConfig(**gen_kwargs))
        elif provider_key == "groq":
            from groq import Groq
            Groq(api_key=key, timeout=20, max_retries=0).chat.completions.create(model=resolved_model, messages=[{"role": "user", "content": "Say OK"}], max_tokens=5)
        elif provider_key == "openai":
            import openai
            openai.OpenAI(api_key=key, timeout=20, max_retries=0).chat.completions.create(model=resolved_model, messages=[{"role": "user", "content": "Say OK"}], max_tokens=5)
        else:
            return ProviderHealth(provider_key, True, True, model=resolved_model, category=HEALTH_CONFIG_ERROR,
                                   detail=f"Chưa hỗ trợ kiểm tra sức khoẻ cho provider '{provider_key}'.")
        return ProviderHealth(provider_key, True, True, model=resolved_model, category=HEALTH_READY, detail="")
    except Exception as e:
        category = classify_provider_error(e)
        _logger.exception("check_provider_health: %s that bai (model=%s, category=%s)", provider_key, resolved_model, category)
        return ProviderHealth(provider_key, True, True, model=resolved_model, category=category,
                               detail=PROVIDER_HEALTH_FRIENDLY_LABEL.get(category, "Lỗi không xác định"))


# Mục 9 (audit 2026-09-14) — bộ nhớ đệm TTL cho kết quả health-check, dùng để
# lựa chọn provider TỰ ĐỘNG không gọi request thật mỗi lần (sẽ quá tốn kém/chậm
# cho mỗi tin nhắn của Sinh viên). Provider CHƯA từng được kiểm tra vẫn được
# coi là "có thể thử" (không chặn oan) — chỉ provider đã XÁC NHẬN không khoẻ
# (vd. BILLING_REQUIRED) trong TTL gần nhất mới bị loại khỏi lựa chọn tự động.
_HEALTH_CACHE: Dict[str, Tuple[float, "ProviderHealth"]] = {}
_HEALTH_CACHE_TTL_SECONDS = 300
_HEALTH_CACHE_LOCK = threading.Lock()


def get_cached_provider_health(provider_key: str) -> Optional["ProviderHealth"]:
    """Trả về ProviderHealth gần nhất còn trong hạn TTL, hoặc None nếu chưa
    từng kiểm tra/đã hết hạn — KHÔNG tự động gọi request thật ở đây."""
    with _HEALTH_CACHE_LOCK:
        entry = _HEALTH_CACHE.get(provider_key)
    if not entry:
        return None
    ts, health = entry
    if time.time() - ts > _HEALTH_CACHE_TTL_SECONDS:
        return None
    return health


def record_provider_health(provider_key: str, health: "ProviderHealth") -> None:
    """Ghi lại 1 kết quả health-check thật vào cache (Admin bấm 'Kiểm tra kết
    nối', hoặc 1 lượt gọi thật trong luồng chat vừa thất bại) để lựa chọn tự
    động sau đó tránh lặp lại provider đã biết là không dùng được."""
    with _HEALTH_CACHE_LOCK:
        _HEALTH_CACHE[provider_key] = (time.time(), health)


def is_known_unhealthy(provider_key: str) -> bool:
    """True CHỈ KHI đã có kết quả kiểm tra thật gần đây (trong TTL) và kết quả
    đó KHÔNG PHẢI READY — dùng để loại provider khỏi danh sách tự động chọn mà
    không cần gọi request thật ngay lúc chọn. Provider chưa từng kiểm tra
    (cache rỗng) trả về False — không chặn oan chỉ vì chưa có dữ liệu."""
    health = get_cached_provider_health(provider_key)
    return health is not None and health.category != HEALTH_READY


class LLMGateway:
    """Cổng tập trung thực thi mọi yêu cầu sinh văn bản qua LLM."""

    def __init__(self, llm_integration=None):
        self.llm_integration = llm_integration

    def check_quota_and_rate_limit(self, user_id: str, role: str, prompt: str = "") -> None:
        """Workstream C (Issue AIGOV-001): the shared quota/rate-limit GATE
        `stream_generate()` applies before it ever touches a provider,
        extracted as its own callable so call sites that genuinely cannot
        use the fallback-cascade part of `stream_generate()` (today: exactly
        one — dss/services/llm_service.py::compare_providers(), which by
        design must know whether a SPECIFIC requested provider succeeded or
        failed, not receive a silently-substituted fallback provider's
        answer under that provider's label) can still enforce the same
        organization quota, per-user token quota, and RPM rate limit that
        every other production AI call path goes through, instead of
        bypassing the gateway's controls entirely. Raises a `GatewayError`
        subclass on any check failure; callers should catch and surface an
        honest message (never fabricate a response on this path either).
        """
        from dss.db.repositories.quota_repository import QuotaExceededError as SubscriptionQuotaExceededError
        from dss.services.subscription_service import consume_ai_request_quota

        try:
            consume_ai_request_quota()
        except SubscriptionQuotaExceededError as exc:
            raise QuotaExceededError(f"Hạn ngạch AI theo tháng của tổ chức đã đạt giới hạn ({exc.limit}).") from exc

        input_tokens = approximate_token_count(prompt)
        ok, quota_msg = token_tracker.check_user_quota(user_id, role, requested_tokens=input_tokens)
        if not ok:
            raise QuotaExceededError(quota_msg)

        self._check_rate_limit()

    def _safe_get_secret(self, key_name: str) -> Optional[str]:
        try:
            if hasattr(st, "secrets") and key_name in st.secrets:
                return str(st.secrets[key_name])
        except Exception:
            pass
        return None

    def resolve_api_key(self, provider_key: str) -> Optional[str]:
        """Phân giải API Key an toàn theo thứ tự ưu tiên:

        1. Cấu hình secrets của Streamlit (nếu có)
        2. Biến môi trường hệ thống
        3. Hàm hỗ trợ của llm_integration
        """
        prov = (provider_key or "").lower()
        key = None

        if prov == "gemini":
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not key:
                key = self._safe_get_secret("GEMINI_API_KEY") or self._safe_get_secret("GOOGLE_API_KEY")
        elif prov == "groq":
            key = os.environ.get("GROQ_API_KEY")
            if not key:
                key = self._safe_get_secret("GROQ_API_KEY")
        elif prov == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                key = self._safe_get_secret("OPENAI_API_KEY")
        elif prov == "huggingface":
            key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
            if not key:
                key = self._safe_get_secret("HF_TOKEN") or self._safe_get_secret("HUGGINGFACE_TOKEN")

        if not key and self.llm_integration and hasattr(self.llm_integration, "get_api_key_from_secrets"):
            try:
                key = self.llm_integration.get_api_key_from_secrets(prov)
            except Exception:
                pass

        return key or None

    def resolve_active_provider_and_model(
        self,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        role: str = "Sinh viên",
        explicit_api_key: Optional[str] = None,
    ) -> Tuple[str, str, Optional[str]]:
        """Xác định provider và model thực sự được gọi.

        Sinh viên không bao giờ thấy hoặc tự chọn provider mà đi qua cấu hình do Admin đặt,
        hoặc tự động phát hiện provider khả dụng tốt nhất.
        """
        # 1. Nếu Admin có đặt Provider mặc định toàn hệ sinh thái — nhưng KHÔNG
        # tự ý dùng nếu lần kiểm tra sức khoẻ gần nhất đã XÁC NHẬN provider đó
        # không dùng được (vd. BILLING_REQUIRED), rơi xuống auto-detect (Mục 9).
        default_cfg = admin_ai_config.get_default_provider()
        if default_cfg and (role == "Sinh viên" or not requested_provider) and not is_known_unhealthy(default_cfg["provider_key"]):
            p_key = default_cfg["provider_key"]
            m_name = default_cfg["model_name"]
            api_k = explicit_api_key or self.resolve_api_key(p_key)
            if p_key in ("ollama", "huggingface") or api_k:
                return p_key, m_name, api_k

        # 2. Nếu Giảng viên / Admin tự chọn trên panel — đây là lựa chọn THỦ CÔNG,
        # tôn trọng nguyên vẹn kể cả khi provider đó đang không khoẻ (người chọn
        # đã thấy trạng thái sức khoẻ trên UI Cấu hình AI trước khi chọn).
        if requested_provider:
            from dss.core.models import AI_MODEL_CATALOG
            p_key = requested_provider
            m_name = requested_model or os.environ.get(f"{p_key.upper()}_MODEL") or (AI_MODEL_CATALOG.get(p_key, [""])[0] if p_key in AI_MODEL_CATALOG else "")
            api_k = explicit_api_key or self.resolve_api_key(p_key)
            return p_key, m_name, api_k

        # 3. Tự động phát hiện (Auto-detect): Groq -> Gemini -> OpenAI -> Ollama -> Demo
        # — bỏ qua candidate đã biết KHÔNG khoẻ (Mục 9), không chặn candidate
        # chưa từng kiểm tra.
        for cand in ["groq", "gemini", "openai"]:
            if is_known_unhealthy(cand):
                continue
            cand_key = explicit_api_key or self.resolve_api_key(cand)
            if cand_key:
                from dss.core.models import AI_MODEL_CATALOG
                cand_model = os.environ.get(f"{cand.upper()}_MODEL") or (AI_MODEL_CATALOG.get(cand, [""])[0] if cand in AI_MODEL_CATALOG else "")
                return cand, cand_model, cand_key

        return "demo", "rule_based_fallback", None

    def _check_rate_limit(self) -> None:
        """Kiểm tra giới hạn tần suất gọi API (Requests per minute)."""
        now = time.monotonic()
        with _RATE_LIMIT_LOCK:
            global _REQUEST_TIMESTAMPS
            # Giữ lại các timestamp trong 60 giây gần nhất
            _REQUEST_TIMESTAMPS = [t for t in _REQUEST_TIMESTAMPS if now - t < 60.0]
            if len(_REQUEST_TIMESTAMPS) >= _MAX_RPM:
                raise RateLimitError("Hệ sinh thái AI đang xử lý lượng yêu cầu tối đa (RPM). Vui lòng thử lại sau ít giây.")
            _REQUEST_TIMESTAMPS.append(now)

    @observed("ai.gateway", metadata=lambda *args, **kwargs: {
        "provider": kwargs.get("provider") or "auto", "model": kwargs.get("model") or "auto",
        "input_tokens": approximate_token_count(args[1] if len(args) > 1 else kwargs.get("prompt", ""))})
    def stream_generate(
        self,
        prompt: str,
        user_id: str = "anonymous_student",
        role: str = "Sinh viên",
        request_type: str = "advisor_plan",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        fallback_allowed: bool = True,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Phương thức chính trả về luồng streaming của câu trả lời từ LLM."""
        from dss.services.semantic_cache import layered_cache, CACHE_CLASS_GLOBAL
        from dss.services.subscription_service import consume_ai_request_quota
        from dss.db.repositories.quota_repository import QuotaExceededError

        # FINAL PRODUCTION GAP CLOSURE (Phần 3/4): Correlation ID — mã ngắn gắn
        # với ĐÚNG 1 lượt gọi stream_generate() này, đưa vào MỌI log kỹ thuật
        # (_logger.*) và vào các thông báo lỗi CUỐI CÙNG hiển thị cho người
        # dùng (không phải mọi log — chỉ log và lỗi liên quan trực tiếp lượt
        # gọi này) để hỗ trợ/Admin tra cứu đúng request khi người dùng báo lỗi,
        # mà KHÔNG cần lộ bất kỳ chi tiết kỹ thuật nào (exception/API key/path)
        # ra UI — chỉ 1 mã ngắn vô hại.
        correlation_id = uuid.uuid4().hex[:8]

        try:
            consume_ai_request_quota()
        except QuotaExceededError as exc:
            yield f"⚠️ Hạn ngạch AI theo tháng của tổ chức đã đạt giới hạn ({exc.limit})."
            return

        # MỤC 20: Kiểm tra Cache trước khi gọi inference
        # P0 SECURITY FIX (OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE, Phần 7,
        # tự phát hiện): khóa cache PHẢI gồm user_id, không chỉ prompt+role —
        # nếu không, 2 sinh viên KHÁC NHAU gửi prompt trùng CHUỖI KÝ TỰ (hoàn
        # toàn có thể xảy ra với dataset mô phỏng ít giá trị phân loại) sẽ bị
        # phục vụ CHÉO câu trả lời cá nhân hóa của nhau (điểm số, cảnh báo học
        # vụ...). Xem test_llm_gateway_cache_cross_user_isolation.py.
        cache_key = f"llm_exact::{hashlib.sha256((prompt + role + user_id).encode('utf-8')).hexdigest()[:16]}"
        cached_response = layered_cache.exact_cache.get(cache_key)
        if cached_response:
            yield cached_response
            # Ghi nhận lượt dùng cache
            token_tracker.record_usage(
                user_id=user_id, role=role, request_type=request_type,
                provider=provider or "cache", model=model or "cache_hit",
                input_tokens=approximate_token_count(prompt),
                output_tokens=approximate_token_count(cached_response),
                cache_hit=True,
            )
            return

        # 1. Kiểm tra hạn ngạch người dùng (Quota check)
        input_tokens = approximate_token_count(prompt)
        ok, quota_msg = token_tracker.check_user_quota(user_id, role, requested_tokens=input_tokens)
        if not ok:
            yield f"⚠️ {quota_msg}"
            return

        # 2. Kiểm tra Rate Limiting & Concurrency
        self._check_rate_limit()

        # MỤC 18 & 23: Xây dựng chuỗi Fallback Chain (PRIMARY -> FALLBACK_1 -> FALLBACK_2)
        edudss_mode = os.environ.get("EDUDSS_MODE", "DEMO_SYNTHETIC")
        if edudss_mode == "LOCAL_OFFLINE":
            # MỤC 23: Ở chế độ ngoại tuyến LOCAL_OFFLINE, chỉ dùng Ollama hoặc Local Models
            provider_chain = ["ollama", "demo"]
        else:
            primary = os.environ.get("DSS_PRIMARY_PROVIDER", "local_ollama").replace("local_", "")
            fb1 = os.environ.get("DSS_FALLBACK_1", "groq")
            fb2 = os.environ.get("DSS_FALLBACK_2", "gemini")
            provider_chain = [provider or primary, fb1, fb2, "demo"]

        # Loại bỏ provider trùng lặp nhưng giữ thứ tự
        dedup_chain = []
        for p in provider_chain:
            if p and p not in dedup_chain:
                dedup_chain.append(p)

        acquired = _GATEWAY_SEMAPHORE.acquire(timeout=45.0)
        if not acquired:
            # Production Demo Policy (audit 2026-09): trước đây luôn "Đang chuyển
            # sang Demo Mode" khi hết chỗ trong hàng đợi — dù có ghi rõ "Demo",
            # đây vẫn là nội dung tư vấn BỊA ĐẶT thay cho phản hồi thật, không
            # được phép lộ ra trong REAL_LMS dù có gắn nhãn (yêu cầu đã chỉnh sửa
            # rõ: "explicitly labeled Demo" KHÔNG đủ cho production).
            if is_production_environment():
                _logger.warning("LLMGateway [%s]: semaphore day (qua tai dong thoi), tu choi request.", correlation_id)
                yield f"⏳ Hệ thống AI hiện đang quá tải (vượt số lượt xử lý đồng thời). Vui lòng thử lại sau ít phút.\n\nMã sự cố: AI-{correlation_id}"
                return
            # E-2: bỏ chữ "cá nhân hóa" — demo_text bên dưới là 1 mẫu CỐ ĐỊNH,
            # không hề phụ thuộc student_weaknesses/predicted_gpa, nên gọi là
            # "cá nhân hóa" là không đúng bản chất, dù có gắn nhãn "Demo Mode".
            yield "⏳ Hệ thống AI đang phục vụ tối đa tải sinh viên đồng thời. Đang chuyển sang Demo Mode (mẫu chung, không cá nhân hóa)..."
            dedup_chain = ["demo"]

        final_answer = ""

        try:
            for p_candidate in dedup_chain:
                explicit_k = kwargs.get("api_key") if p_candidate == provider else None
                # Model do nơi gọi chỉ định (vd. advisor_chat truyền model_name từ
                # resolve_auto_provider) — trước đây bị bỏ qua nên luôn rơi về model
                # đầu danh sách. Chỉ áp cho đúng provider được yêu cầu.
                requested_m = (model or kwargs.get("model_name")) if p_candidate == provider else None
                p_key, p_model, p_api_key = self.resolve_active_provider_and_model(
                    requested_provider=p_candidate, requested_model=requested_m, role=role, explicit_api_key=explicit_k,
                )

                # Circuit Breaker (Phần 16, hoàn thiện chuỗi resilience sau H-3):
                # provider vừa lỗi liên tiếp đủ ngưỡng -> mạch đang OPEN -> bỏ
                # qua NGAY, không tốn 1 lượt gọi/chờ timeout thật cho 1 provider
                # gần như chắc chắn vẫn đang hỏng (vd. hết hạn mức thanh toán).
                # KHÔNG áp dụng cho "demo" (luôn là fallback cuối cùng trong
                # dedup_chain, không phải provider thật — không được phép bị
                # chặn bởi mạch, nếu không toàn bộ chain có thể chạy hết mà
                # không có gì để yield). "demo" luôn là phần tử cuối của
                # dedup_chain nên vòng lặp vẫn tới được nhánh thông báo trung
                # thực bên dưới sau khi bỏ qua các provider thật đang mở mạch.
                if p_key != "demo" and not circuit_breaker.allow_request(p_key):
                    _logger.warning(
                        "LLMGateway [%s]: mach Circuit Breaker dang OPEN cho provider '%s' "
                        "- bo qua, thu provider ke tiep.", correlation_id, p_key,
                    )
                    record_operation("ai.provider_attempt", time.perf_counter(), success=False,
                                     provider=p_key, model=p_model or "default", fallback="circuit_open")
                    continue

                if p_key == "demo" or (not p_api_key and p_key in ("gemini", "groq", "openai")):
                    if p_candidate == "demo" or p_candidate == dedup_chain[-1]:
                        # Production Demo Policy (audit 2026-09): toàn bộ chuỗi
                        # fallback provider đã cạn (không còn provider thật nào
                        # cấu hình được key) — trong REAL_LMS, KHÔNG được bịa nội
                        # dung tư vấn thay thế dù có gắn nhãn "Demo". Trả về trạng
                        # thái trung thực để Sinh viên/Giảng viên biết cần liên hệ
                        # Admin, thay vì nhận một kế hoạch học tập không có thật.
                        if is_production_environment():
                            _logger.warning("LLMGateway [%s]: het chuoi fallback, khong con provider nao cau hinh hop le.", correlation_id)
                            yield f"🔒 Trợ lý AI hiện chưa khả dụng (chưa có provider AI nào được cấu hình hợp lệ). Vui lòng liên hệ quản trị viên.\n\nMã sự cố: AI-{correlation_id}"
                            return
                        # E-2: ghi rõ NGAY ĐẦU câu trả lời rằng đây KHÔNG phải nội dung
                        # cá nhân hóa — trước đây chỉ có 1 ghi chú mơ hồ ở cuối, không đủ
                        # rõ để người đọc hiểu đây là mẫu chung, không tạo riêng cho họ.
                        demo_text = (
                            "*⚠️ Không có mô hình AI khả dụng — đây là mẫu chung, "
                            "KHÔNG được tạo cho riêng bạn.*\n\n"
                            "### 📘 Kế hoạch học tập khuyến nghị (Chế độ Cố vấn Sư phạm Demo)\n"
                            "- **Tuần 1-2**: Ôn tập củng cố các lỗ hổng kiến thức căn bản, làm lại các bài tập tuần.\n"
                            "- **Tuần 3**: Luyện đề tự đánh giá, tham gia nhóm học tập và thảo luận cùng trợ giảng.\n"
                            "- **Tuần 4**: Hoàn thiện bài tập lớn và tổng kết phương pháp làm bài thi.\n\n"
                            "*Ghi chú: Phản hồi được tạo tự động bởi hệ thống gợi ý quy tắc nội bộ EduDSS.*"
                        )
                        yield demo_text
                        final_answer = demo_text
                        break
                    else:
                        continue  # Không có key -> thử candidate tiếp theo trong chain

                provider_started = time.perf_counter()
                try:
                    # Thực thi gọi provider
                    stream = None
                    is_raw_provider_call = False
                    if self.llm_integration:
                        rest_kwargs = dict(kwargs)
                        rest_kwargs.pop("api_key", None)
                        rest_kwargs.pop("provider", None)
                        rest_kwargs.pop("model_name", None)
                        if request_type in _PLANNING_REQUEST_TYPES and hasattr(self.llm_integration, "generate_personalized_advice"):
                            student_weaknesses = rest_kwargs.pop("student_weaknesses", [])
                            predicted_gpa = rest_kwargs.pop("predicted_gpa", 0.0)
                            stream = self.llm_integration.generate_personalized_advice(
                                student_weaknesses=student_weaknesses,
                                predicted_gpa=predicted_gpa,
                                provider=p_key,
                                model_name=p_model,
                                api_key=p_api_key,
                                # `role` được stream_generate() tiêu thụ như tham số
                                # riêng ở trên (không lọt vào **kwargs/rest_kwargs) —
                                # phải chuyển tay xuống đây để retrieve_unified_context
                                # trong generate_personalized_advice() lọc namespace
                                # đúng theo vai trò thật của người gọi, không rơi về
                                # mặc định "Sinh viên" (NHÓM F remediation đợt 2).
                                role=role,
                                **rest_kwargs,
                            )
                        elif hasattr(self.llm_integration, "call_ai_provider"):
                            is_raw_provider_call = True
                            stream = self.llm_integration.call_ai_provider(
                                prompt,
                                provider=p_key,
                                model_name=p_model,
                                api_key=p_api_key,
                                **rest_kwargs,
                            )
                    if stream:
                        chunk_list = []
                        from dss.services import llm_usage
                        llm_usage.begin()
                        stream_iter = iter(stream)
                        if is_raw_provider_call:
                            # H-3: call_ai_provider() không raise khi lỗi — nó yield ĐÚNG
                            # 1 câu lỗi thân thiện rồi return (xem _PROVIDER_FRIENDLY_ERROR_PREFIXES).
                            # "Peek" chunk đầu tiên TRƯỚC KHI yield ra ngoài: nếu đó là câu
                            # lỗi, KHÔNG hiển thị cho người dùng như câu trả lời cuối cùng —
                            # coi lượt này là THẤT BẠI và thử provider kế tiếp trong chain.
                            try:
                                first_chunk = next(stream_iter)
                            except StopIteration:
                                first_chunk = None
                            if first_chunk is not None and _is_friendly_provider_error(first_chunk):
                                _logger.warning(
                                    "LLMGateway [%s]: provider '%s' tra ve loi than thien (khong raise) "
                                    "- chuyen sang provider ke tiep trong fallback chain.", correlation_id, p_key,
                                )
                                if p_key != "demo":
                                    circuit_breaker.record_failure(p_key)
                                record_operation("ai.provider_attempt", provider_started, success=False,
                                                 provider=p_key, model=p_model or "default",
                                                 fallback="next_friendly_error" if fallback_allowed else "blocked")
                                if not fallback_allowed:
                                    yield first_chunk
                                    return
                                continue  # thử candidate kế tiếp trong dedup_chain
                            if first_chunk is not None:
                                yield first_chunk
                                chunk_list.append(first_chunk)
                        for chunk in stream_iter:
                            yield chunk
                            chunk_list.append(chunk)
                        final_answer = "".join(chunk_list)
                        if p_key != "demo":
                            circuit_breaker.record_success(p_key)
                        # Token THẬT do provider trả về (usage_metadata/usage) nếu có — khớp hoá
                        # đơn, gồm cả token suy nghĩ; nếu không có mới dùng ước lượng theo ký tự.
                        provider_usage = llm_usage.take()
                        if provider_usage:
                            used_model = provider_usage["model"] or p_model or "default"
                            used_in, used_out = provider_usage["input_tokens"], provider_usage["output_tokens"]
                            used_thinking, usage_source = provider_usage["thinking_tokens"], "provider"
                        else:
                            used_model = p_model or "default"
                            used_in, used_out = input_tokens, approximate_token_count(final_answer)
                            used_thinking, usage_source = 0, "estimated"
                        record_operation("ai.provider_attempt", provider_started, success=True,
                                         provider=p_key, model=used_model,
                                         input_tokens=used_in, output_tokens=used_out)
                        # Ghi nhận token thành công
                        token_tracker.record_usage(
                            user_id=user_id, role=role, request_type=request_type,
                            provider=p_key, model=used_model,
                            input_tokens=used_in, output_tokens=used_out,
                            usage_source=usage_source, thinking_tokens=used_thinking,
                        )
                        # Lưu vào đệm — dimensions PHẢI gồm "student_pseudonym" (=user_id):
                        # trước fix này, dimensions chỉ có {"role": role} nên
                        # layered_cache.invalidate_student(pseudonym) (lọc theo dimension
                        # "student_pseudonym") KHÔNG BAO GIỜ khớp được entry nào tạo từ
                        # đường này — cache cá nhân hóa không bao giờ bị hủy khi điểm/dữ
                        # liệu sinh viên thay đổi, chỉ hết hạn theo TTL (tới 1 giờ).
                        layered_cache.exact_cache.set(
                            cache_key, final_answer, CACHE_CLASS_GLOBAL,
                            {"role": role, "student_pseudonym": user_id, "request_type": request_type},
                        )
                        break
                except Exception as call_err:
                    err_lower = str(call_err).lower()
                    # MỤC 18: TUYỆT ĐỐI KHÔNG fallback khi lỗi là Authorization (401/403) hoặc Vi phạm PII/Bảo mật
                    is_auth = any(t in err_lower for t in ["401", "403", "unauthorized", "permission", "forbidden", "invalid api key"])
                    is_security = any(t in err_lower for t in ["pii", "injection", "security policy", "blocked prompt"])
                    if p_key != "demo":
                        circuit_breaker.record_failure(p_key)
                    record_operation("ai.provider_attempt", provider_started, success=False,
                                     provider=p_key, model=p_model or "default",
                                     fallback="blocked" if is_auth or is_security else "next")
                    if is_auth or is_security:
                        _logger.error("LLMGateway [%s]: Chặn failover do vi phạm xác thực/bảo mật (provider=%s): error_type=%s", correlation_id, p_key, type(call_err).__name__)
                        yield f"\n⚠️ Lỗi bảo mật/ủy quyền ({p_key}): Yêu cầu bị từ chối và không được phép chuyển tiếp.\n\nMã sự cố: AI-{correlation_id}"
                        return

                    _logger.warning("LLMGateway [%s]: Provider %s thất bại (error_type=%s), thử fallback tiếp theo...", correlation_id, p_key, type(call_err).__name__)
                    if not fallback_allowed:
                        yield f"\n⚠️ Lỗi từ provider {p_key}: không thể hoàn tất yêu cầu.\n\nMã sự cố: AI-{correlation_id}"
                        return
                    continue
        finally:
            if acquired:
                _GATEWAY_SEMAPHORE.release()

