"""Số token THẬT do provider trả về cho lượt gọi AI vừa xong (thay cho ước lượng theo ký tự).

`call_ai_provider()` (dss/core/models.py) đọc usage_metadata (Gemini) / usage (OpenAI, Groq) ở
chunk cuối của stream và `report()` vào đây; `LLMGateway.stream_generate()` gọi `begin()` trước
khi duyệt stream và `take()` sau khi xong để ghi token_tracker với usage_source="provider".
Lưu theo luồng (thread-local): mỗi phiên Streamlit chạy script trên một luồng riêng.
"""

from __future__ import annotations

import threading
from typing import Optional

_local = threading.local()


def begin() -> None:
    _local.usage = None


def report(provider: str, model: str, input_tokens, output_tokens, thinking_tokens=0) -> None:
    try:
        usage = {
            "provider": str(provider),
            "model": str(model),
            "input_tokens": max(0, int(input_tokens or 0)),
            "thinking_tokens": max(0, int(thinking_tokens or 0)),
        }
        # output_tokens báo cáo = token trả lời + token suy nghĩ (cả hai tính giá output).
        usage["output_tokens"] = max(0, int(output_tokens or 0)) + usage["thinking_tokens"]
        _local.usage = usage
    except (TypeError, ValueError):
        _local.usage = None


def take() -> Optional[dict]:
    usage = getattr(_local, "usage", None)
    _local.usage = None
    return usage


def _count(obj, name) -> Optional[int]:
    value = getattr(obj, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def from_gemini(provider: str, model: str, usage_metadata) -> None:
    """Gemini: candidates_token_count KHÔNG gồm thoughts_token_count (tính riêng, giá output)."""
    try:
        prompt = _count(usage_metadata, "prompt_token_count")
        output = _count(usage_metadata, "candidates_token_count")
        if prompt is None and output is None:
            return
        report(provider, model, prompt, output, _count(usage_metadata, "thoughts_token_count") or 0)
    except Exception:
        pass  # đo đếm không bao giờ được làm hỏng câu trả lời


def from_openai_compatible(provider: str, model: str, usage) -> None:
    """OpenAI/Groq: completion_tokens ĐÃ gồm reasoning tokens -> tách ra, không cộng hai lần."""
    try:
        prompt = _count(usage, "prompt_tokens")
        completion = _count(usage, "completion_tokens")
        if prompt is None and completion is None:
            return
        reasoning = _count(getattr(usage, "completion_tokens_details", None), "reasoning_tokens") or 0
        report(provider, model, prompt, max(0, (completion or 0) - reasoning), reasoning)
    except Exception:
        pass
