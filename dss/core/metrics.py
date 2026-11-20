"""Prometheus metrics for EduDSS (exposed by the health server at /metrics).

Two processes share one container: Streamlit (where users act) and the health server
(which Prometheus/Grafana Cloud scrapes). prometheus_client's multiprocess mode joins them:
both processes write/read memory-mapped files under PROMETHEUS_MULTIPROC_DIR (the Dockerfile
sets it and clears it at start). Without that variable (tests, `streamlit run` locally) the
metrics live in the default in-process registry.

Labels are low-cardinality and never carry personal data: provider/model come from a fixed
catalogue (anything else becomes "other"), roles are the three product roles, pages are the
navigation keys. Every hook is best-effort: telemetry must never break a user action.
"""
from __future__ import annotations

import os
import re

try:  # optional dependency: the app must keep working without it
    from prometheus_client import Counter, Histogram

    _AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when the package is missing
    _AVAILABLE = False

_SAFE = re.compile(r"^[A-Za-z0-9_.:/-]{1,64}$")
_ROLES = {"Sinh viên": "student", "Giảng viên / CVHT": "teacher", "Admin": "admin", "Platform Admin": "platform_admin"}
_PROVIDERS = {"gemini", "groq", "openai", "ollama", "huggingface", "demo", "cache", "local"}


def _model_label(model: str | None) -> str:
    try:
        from dss.core.models import AI_MODEL_CATALOG

        known = {m for models in AI_MODEL_CATALOG.values() for m in models}
    except Exception:
        known = set()
    from dss.services.token_tracker import MODEL_PRICING_PER_M

    value = str(model or "default")
    if value in known or value in MODEL_PRICING_PER_M or value in {"default", "cache_hit", "demo"}:
        return value if _SAFE.fullmatch(value) else "other"
    return "other"


def role_label(role: str | None) -> str:
    return _ROLES.get(str(role or ""), "unknown")


def provider_label(provider: str | None) -> str:
    value = str(provider or "unknown").lower()
    return value if value in _PROVIDERS else "other"


if _AVAILABLE:
    LOGINS = Counter("edudss_logins_total", "Login attempts by method and result", ["method", "result"])
    PAGE_VIEWS = Counter("edudss_page_views_total", "Page renders by navigation key and role", ["page", "role"])
    AI_REQUESTS = Counter("edudss_ai_requests_total", "AI requests by provider and outcome",
                          ["provider", "request_type", "outcome"])
    AI_TOKENS = Counter("edudss_ai_tokens_total", "AI tokens by provider/model, kind and how they were counted",
                        ["provider", "model", "kind", "source"])
    AI_COST = Counter("edudss_ai_cost_usd_total", "Estimated AI spend in USD", ["provider", "model"])
    OPERATIONS = Counter("edudss_operations_total", "Observed service operations", ["operation", "outcome"])
    OPERATION_SECONDS = Histogram("edudss_operation_seconds", "Observed service operation duration", ["operation"],
                                  buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120))


def _safe_op(operation: str) -> str:
    value = str(operation)
    return value if _SAFE.fullmatch(value) else "other"


def record_login(method: str, result: str) -> None:
    if not _AVAILABLE:
        return
    try:
        LOGINS.labels(method=_safe_op(method), result=_safe_op(result)).inc()
    except Exception:
        pass


def page_slug(tab_label: str) -> str:
    """'🧪 Huấn luyện — Dự đoán' -> 'huan_luyen_du_doan' (fixed navigation keys -> bounded labels)."""
    import unicodedata

    text = unicodedata.normalize("NFKD", str(tab_label).replace("đ", "d").replace("Đ", "D"))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:48]
    return slug or "other"


def record_page_view(page: str, role: str | None) -> None:
    if not _AVAILABLE:
        return
    try:
        PAGE_VIEWS.labels(page=page_slug(page), role=role_label(role)).inc()
    except Exception:
        pass


def record_ai_usage(*, provider: str, model: str, request_type: str, input_tokens: int, output_tokens: int,
                    thinking_tokens: int = 0, cost_usd: float, cache_hit: bool, source: str) -> None:
    if not _AVAILABLE:
        return
    try:
        p, m = provider_label(provider), _model_label(model)
        AI_REQUESTS.labels(provider=p, request_type=_safe_op(request_type),
                           outcome="cache_hit" if cache_hit else "success").inc()
        if not cache_hit:
            src = source if source in {"provider", "estimated"} else "estimated"
            AI_TOKENS.labels(provider=p, model=m, kind="input", source=src).inc(max(0, int(input_tokens)))
            AI_TOKENS.labels(provider=p, model=m, kind="output", source=src).inc(max(0, int(output_tokens)))
            if thinking_tokens:
                AI_TOKENS.labels(provider=p, model=m, kind="thinking", source=src).inc(max(0, int(thinking_tokens)))
            AI_COST.labels(provider=p, model=m).inc(max(0.0, float(cost_usd)))
    except Exception:
        pass


def record_ai_failure(provider: str, request_type: str, outcome: str) -> None:
    if not _AVAILABLE:
        return
    try:
        AI_REQUESTS.labels(provider=provider_label(provider), request_type=_safe_op(request_type),
                           outcome=_safe_op(outcome)).inc()
    except Exception:
        pass


def record_operation(operation: str, outcome: str, seconds: float) -> None:
    if not _AVAILABLE:
        return
    try:
        op = _safe_op(operation)
        OPERATIONS.labels(operation=op, outcome=outcome).inc()
        OPERATION_SECONDS.labels(operation=op).observe(max(0.0, seconds))
    except Exception:
        pass


def multiprocess_dir() -> str | None:
    value = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    return value if value and os.path.isdir(value) else None
