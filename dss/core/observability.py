"""Small, privacy-safe process-local diagnostics for Streamlit operations."""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import logging
import re
import threading
import time
import uuid
from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone

from dss.security.log_redaction import redact_text

_correlation_id = contextvars.ContextVar("edudss_correlation_id", default=None)
_lock = threading.Lock()
_counts = Counter()
_durations = deque(maxlen=500)
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")


def new_correlation_id() -> str:
    """Start a trace for one Streamlit rerun or explicit service operation."""
    value = uuid.uuid4().hex
    _correlation_id.set(value)
    return value


def current_correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def correlation_scope(correlation_id: str | None = None):
    value = correlation_id if correlation_id and re.fullmatch(r"[a-f0-9]{32}", correlation_id) else uuid.uuid4().hex
    token = _correlation_id.set(value)
    try:
        yield value
    finally:
        _correlation_id.reset(token)


def _label(value: object) -> str:
    value = str(value)
    return value if _SAFE_LABEL.fullmatch(value) and redact_text(value) == value else "unknown"


class StructuredFormatter(logging.Formatter):
    """JSON lines in the existing technical log, with a strict metadata allowlist."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "obs_correlation_id", None) or current_correlation_id(),
            "message": redact_text(record.getMessage()),
        }
        for key in ("event", "operation", "outcome", "provider", "model", "backend", "fallback"):
            value = getattr(record, "obs_" + key, None)
            if value is not None:
                payload[key] = _label(value)
        for key in ("duration_ms", "batch_size", "top_k", "result_count", "input_tokens", "output_tokens"):
            value = getattr(record, "obs_" + key, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def record_operation(operation: str, started: float, *, success: bool, **metadata) -> float:
    """Count and log one operation; only fixed, low-cardinality labels are emitted."""
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000)
    operation = _label(operation)
    outcome = "success" if success else "error"
    with _lock:
        _counts[(operation, outcome)] += 1
        _durations.append((operation, elapsed_ms))
    extra = {"obs_event": "operation", "obs_operation": operation, "obs_outcome": outcome,
             "obs_duration_ms": round(elapsed_ms, 3), "obs_correlation_id": current_correlation_id()}
    for key in ("provider", "model", "backend", "fallback", "batch_size", "top_k", "result_count", "input_tokens", "output_tokens"):
        if key in metadata:
            extra["obs_" + key] = metadata[key]
    # Import here to avoid a logging_config -> observability cycle.
    try:
        from dss.core.logging_config import get_logger
        get_logger(__name__).info("operation completed", extra=extra)
    except Exception:
        # Telemetry must never replace a business result or hide its exception.
        pass
    return elapsed_ms


@contextmanager
def observe(operation: str, **metadata):
    started = time.perf_counter()
    owned = current_correlation_id() is None
    with correlation_scope() if owned else _existing_scope():
        try:
            yield metadata
        except BaseException:
            record_operation(operation, started, success=False, **metadata)
            raise
        else:
            record_operation(operation, started, success=True, **metadata)


@contextmanager
def _existing_scope():
    yield


def observed(operation: str, metadata=None):
    """Decorate ordinary or streaming functions without reading payloads."""
    def decorate(func):
        def fields(args, kwargs):
            try:
                return metadata(*args, **kwargs) if metadata else {}
            except Exception:
                return {}
        if inspect.isgeneratorfunction(func):
            @functools.wraps(func)
            def generator(*args, **kwargs):
                with observe(operation, **fields(args, kwargs)):
                    yield from func(*args, **kwargs)
            return generator
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with observe(operation, **fields(args, kwargs)):
                return func(*args, **kwargs)
        return wrapper
    return decorate


def metrics_snapshot() -> dict:
    """Process-local aggregate snapshot; no prompts, documents or student rows."""
    with _lock:
        return {"counters": {f"{op}:{outcome}": count for (op, outcome), count in _counts.items()},
                "recent_durations_ms": list(_durations)}


def predict_with_metrics(pipeline, data):
    """Measure prediction without inspecting or logging feature values."""
    batch_size = len(data)
    model_name = type(pipeline).__name__
    with observe("ml.predict", model=model_name, batch_size=batch_size):
        return pipeline.predict(data)
