"""Token Usage Tracker — Quản lý và giám sát sử dụng token, chi phí cho LMS-scale AI (~20.000 sinh viên).

Theo dõi chi tiết:
- input_tokens, output_tokens, total_tokens
- provider, model, user_id, role, request_type, timestamp, estimated_cost
- Hạn ngạch hàng ngày theo người dùng / vai trò (Per-user daily quota)
- Ngân sách hàng ngày / hàng tháng toàn hệ thống (System budget & alerts)
- Tuyệt đối KHÔNG ghi log API key thật.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dss.core.data_root import get_data_root

_LOCK = threading.Lock()


def _usage_file() -> Path:
    """PERF-002: tính lại mỗi lần gọi, không cache mức module (xem dss/core/data_root.py)."""
    return get_data_root() / "ai_token_usage.json"


# Bảng giá định mức chi phí ($ / 1,000,000 tokens) — giá niêm yết trả theo lượt (paid tier),
# kiểm tra lại 16/11/2026. Token "suy nghĩ" (thinking) của Gemini tính theo giá OUTPUT.
# Khớp theo TÊN MODEL DÀI NHẤT trước ("gemini-2.5-flash-lite" không bị tính giá
# "gemini-2.5-flash"), rồi mới tới giá mặc định theo provider.
# Các alias "-latest" của Google trỏ sang model mới nhất nên giá có thể đổi: ghi đè không cần
# sửa code bằng EDUDSS_LLM_PRICING_JSON='{"gemini-flash-lite-latest": {"input": 0.25, "output": 1.5}}'.
PRICING_AS_OF = "2026-11-16"
MODEL_PRICING_PER_M = {
    # Google Gemini
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-3-flash": {"input": 0.50, "output": 3.00},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.1-pro": {"input": 2.00, "output": 12.00},
    "gemini-flash-lite-latest": {"input": 0.25, "output": 1.50},
    "gemini-flash-latest": {"input": 0.50, "output": 3.00},
    "gemini-pro-latest": {"input": 2.00, "output": 12.00},
    "gemini": {"input": 0.30, "output": 2.50},
    # Groq
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "groq": {"input": 0.15, "output": 0.60},
    # OpenAI
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "openai": {"input": 0.15, "output": 0.60},
    # Local models
    "ollama": {"input": 0.0, "output": 0.0},
    "huggingface": {"input": 0.0, "output": 0.0},
    "demo": {"input": 0.0, "output": 0.0},
}


def _pricing_table() -> Dict[str, Dict[str, float]]:
    table = dict(MODEL_PRICING_PER_M)
    raw = os.environ.get("EDUDSS_LLM_PRICING_JSON", "").strip()
    if raw:
        try:
            for key, price in json.loads(raw).items():
                table[str(key).lower()] = {"input": float(price["input"]), "output": float(price["output"])}
        except Exception:
            pass  # cấu hình sai -> giữ bảng mặc định, không làm hỏng lượt gọi AI
    return table


def price_for(provider: str, model: str) -> Dict[str, float]:
    table = _pricing_table()
    model_clean = (model or "").lower()
    prov_clean = (provider or "").lower()
    if prov_clean in ("demo", "ollama", "huggingface", "cache"):
        return table.get(prov_clean, {"input": 0.0, "output": 0.0})
    if model_clean in table:
        return table[model_clean]
    for key in sorted(table, key=len, reverse=True):
        if key not in ("gemini", "groq", "openai") and key in model_clean:
            return table[key]
    return table.get(prov_clean, {"input": 0.10, "output": 0.40})


DEFAULT_DAILY_QUOTA_BY_ROLE = {
    "Sinh viên": 15_000,  # 15k tokens / ngày / sinh viên (~10-15 câu hỏi)
    "Giảng viên / CVHT": 60_000,  # 60k tokens / ngày
    "Admin": 500_000,  # 500k tokens / ngày cho vận hành & test
}

SYSTEM_BUDGET_CONFIG = {
    "daily_budget_usd": 15.0,  # $15/ngày cho trường
    "monthly_budget_usd": 300.0,  # $300/tháng
    "warning_threshold_ratio": 0.80,  # Cảnh báo khi chạm 80%
}


@dataclass
class UsageRecord:
    usage_id: str
    timestamp: str
    user_id: str
    role: str
    request_type: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    # OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE (P1, tự phát hiện qua test tích
    # hợp Circuit Breaker): trường mới, mặc định False để KHÔNG phá vỡ bất kỳ
    # UsageRecord/bản ghi cũ nào đã lưu trên đĩa (đọc lại record cũ thiếu
    # trường này vẫn hợp lệ nhờ default). True nếu lượt này được phục vụ từ
    # cache (không gọi provider thật) — dùng để KHÔNG tính phí (xem cost=0.0
    # bên dưới) và để phân tích tỷ lệ cache-hit thật sau này.
    cache_hit: bool = False
    # Số token lấy từ đâu: "provider" = usage_metadata/usage do Gemini/Groq/OpenAI trả về (chính
    # xác, khớp hoá đơn); "estimated" = đếm xấp xỉ theo số ký tự khi provider không trả usage.
    usage_source: str = "estimated"
    # Token suy nghĩ (Gemini thinking / reasoning tokens) — ĐÃ nằm trong output_tokens (tính giá output).
    thinking_tokens: int = 0


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Chi phí ước tính (USD) theo bảng giá. output_tokens gồm cả token suy nghĩ (nếu có)."""
    pricing = price_for(provider, model)
    cost = (input_tokens / 1_000_000.0 * pricing["input"]) + (output_tokens / 1_000_000.0 * pricing["output"])
    return round(cost, 6)


def _load_all_records() -> List[Dict[str, Any]]:
    """Single read choke-point used by every aggregation function below
    (daily usage / quota / budget status / usage summary) — branching here
    means none of them need their own PostgreSQL-awareness."""
    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("AI_TOKEN_USAGE"):
        from dss.core.warehouse import _current_organization_id
        from dss.db.repositories import ai_token_usage_repository

        return ai_token_usage_repository.load_all_records(_current_organization_id())

    usage_file = _usage_file()
    if not usage_file.exists():
        return []
    try:
        with open(usage_file, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _atomic_write_records(records: List[Dict[str, Any]]) -> None:
    usage_file = _usage_file()
    usage_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = usage_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, usage_file)


def record_usage(
    user_id: str,
    role: str,
    request_type: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool = False,
    usage_source: str = "estimated",
    thinking_tokens: int = 0,
) -> UsageRecord:
    """Ghi nhận lượt sử dụng token và cập nhật chi phí (Thread-safe, Atomic).

    P1 (tự phát hiện, OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE): trước đây
    hàm này KHÔNG nhận `cache_hit`, nhưng `llm_gateway.py::stream_generate()`
    (nhánh phục vụ từ cache — "MỤC 20: Kiểm tra Cache trước khi gọi
    inference") LUÔN gọi `record_usage(..., cache_hit=True)` — mọi lượt
    request được cache phục vụ đều làm hàm này raise TypeError NGAY SAU KHI
    đã yield xong câu trả lời cache cho người dùng. Nếu nơi gọi
    `stream_generate()` gom hết chunk bằng `"".join(...)` (đúng mẫu
    `ai_advisor.py` dùng cho luồng chat) TRƯỚC KHI hiển thị, exception này
    làm MẤT câu trả lời cache đã có sẵn (nhanh, đúng) và thay bằng thông báo
    lỗi chung — trong khi AI thực ra đã "trả lời" thành công. Phát hiện qua
    test tích hợp Circuit Breaker (2 test dùng cùng 1 prompt trùng nhau vô
    tình kích hoạt cache-hit)."""
    input_tokens = max(0, int(input_tokens))
    output_tokens = max(0, int(output_tokens))
    total_tokens = input_tokens + output_tokens
    # Lượt phục vụ từ cache KHÔNG gọi provider thật -> không phát sinh chi phí
    # thật, dù model/provider có trong bảng giá hay không.
    cost = 0.0 if cache_hit else estimate_cost(provider, model, input_tokens, output_tokens)

    # Ẩn danh hóa user_id nếu chứa email hoặc SĐT để bảo mật
    safe_user_id = str(user_id)
    if "@" in safe_user_id:
        safe_user_id = f"user_{safe_user_id.split('@')[0]}"

    record = UsageRecord(
        usage_id=f"use_{uuid.uuid4().hex[:12]}",
        timestamp=datetime.now(UTC).isoformat(),
        user_id=safe_user_id,
        role=role or "Sinh viên",
        request_type=request_type or "advisor_plan",
        provider=provider or "unknown",
        model=model or "unknown",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=cost,
        cache_hit=cache_hit,
        usage_source="provider" if usage_source == "provider" else "estimated",
        thinking_tokens=max(0, int(thinking_tokens or 0)),
    )
    try:
        from dss.core import metrics

        metrics.record_ai_usage(
            provider=record.provider,
            model=record.model,
            request_type=record.request_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=record.thinking_tokens,
            cost_usd=cost,
            cache_hit=cache_hit,
            source=record.usage_source,
        )
    except Exception:
        pass

    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("AI_TOKEN_USAGE"):
        from dss.core.warehouse import _current_organization_id
        from dss.db.repositories import ai_token_usage_repository

        ai_token_usage_repository.record_usage(_current_organization_id(), asdict(record))
        return record

    with _LOCK:
        records = _load_all_records()
        records.append(asdict(record))
        # Giữ tối đa 50,000 bản ghi gần nhất trong file cục bộ
        if len(records) > 50_000:
            records = records[-50_000:]
        _atomic_write_records(records)

    return record


def get_user_daily_token_usage(user_id: str, date_str: Optional[str] = None) -> int:
    """Tổng token sinh viên/người dùng đã dùng trong ngày (mặc định hôm nay theo UTC)."""
    if not date_str:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    records = _load_all_records()
    total = 0
    safe_uid = str(user_id)
    if "@" in safe_uid:
        safe_uid = f"user_{safe_uid.split('@')[0]}"

    for r in records:
        ts = r.get("timestamp", "")
        if ts.startswith(date_str) and r.get("user_id") == safe_uid:
            total += int(r.get("total_tokens", 0))
    return total


def check_user_quota(user_id: str, role: str, requested_tokens: int = 0) -> Tuple[bool, str]:
    """Kiểm tra xem người dùng còn đủ hạn ngạch token trong ngày không."""
    daily_quota = DEFAULT_DAILY_QUOTA_BY_ROLE.get(role, 15_000)
    current_used = get_user_daily_token_usage(user_id)

    if current_used + requested_tokens > daily_quota:
        msg = (
            f"Hạn ngạch AI hàng ngày ({daily_quota:,} tokens) của bạn đã đạt mức "
            f"({current_used:,} tokens đã dùng). Vui lòng thử lại vào ngày mai hoặc liên hệ Admin."
        )
        return False, msg

    remaining = daily_quota - current_used
    return True, f"Hạn ngạch khả dụng: {remaining:,} tokens."


def get_system_budget_status() -> Dict[str, Any]:
    """Tính toán chi phí ngày và tháng hiện tại để cảnh báo ngưỡng ngân sách."""
    now_utc = datetime.now(UTC)
    today_prefix = now_utc.strftime("%Y-%m-%d")
    month_prefix = now_utc.strftime("%Y-%m")

    records = _load_all_records()
    daily_cost = 0.0
    monthly_cost = 0.0
    daily_tokens = 0
    monthly_tokens = 0

    for r in records:
        ts = r.get("timestamp", "")
        cost = float(r.get("estimated_cost", 0.0))
        tokens = int(r.get("total_tokens", 0))

        if ts.startswith(today_prefix):
            daily_cost += cost
            daily_tokens += tokens
        if ts.startswith(month_prefix):
            monthly_cost += cost
            monthly_tokens += tokens

    daily_budget = SYSTEM_BUDGET_CONFIG["daily_budget_usd"]
    monthly_budget = SYSTEM_BUDGET_CONFIG["monthly_budget_usd"]
    warn_ratio = SYSTEM_BUDGET_CONFIG["warning_threshold_ratio"]

    status = "normal"
    alert_message = None

    if monthly_cost >= monthly_budget:
        status = "monthly_exceeded"
        alert_message = f"🚨 Ngân sách AI tháng (${monthly_budget:.2f}) đã chạm mức 100% (${monthly_cost:.2f})!"
    elif monthly_cost >= monthly_budget * warn_ratio:
        status = "monthly_warning"
        alert_message = f"⚠️ Cảnh báo: Đã dùng {(monthly_cost / monthly_budget) * 100:.1f}% ngân sách AI tháng (${monthly_cost:.2f}/${monthly_budget:.2f})."
    elif daily_cost >= daily_budget:
        status = "daily_exceeded"
        alert_message = f"🚨 Chi phí AI hôm nay (${daily_cost:.2f}) đã vượt ngân sách ngày (${daily_budget:.2f})!"
    elif daily_cost >= daily_budget * warn_ratio:
        status = "daily_warning"
        alert_message = f"⚠️ Cảnh báo: Chi phí AI hôm nay đã đạt {(daily_cost / daily_budget) * 100:.1f}% ngân sách ngày (${daily_cost:.2f}/${daily_budget:.2f})."

    return {
        "status": status,
        "alert_message": alert_message,
        "daily_cost": round(daily_cost, 4),
        "daily_budget": daily_budget,
        "monthly_cost": round(monthly_cost, 4),
        "monthly_budget": monthly_budget,
        "daily_tokens": daily_tokens,
        "monthly_tokens": monthly_tokens,
        "total_requests": len(records),
    }


def get_usage_summary(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Tổng hợp số liệu thống kê sử dụng token theo vai trò và provider."""
    records = _load_all_records()
    by_role: Dict[str, Dict[str, Any]] = {}
    by_provider: Dict[str, Dict[str, Any]] = {}
    total_tokens = 0
    total_cost = 0.0

    for r in records:
        ts = r.get("timestamp", "")
        if start_date and ts < start_date:
            continue
        if end_date and ts > end_date:
            continue

        role = r.get("role", "Khác")
        prov = r.get("provider", "Khác")
        tokens = int(r.get("total_tokens", 0))
        cost = float(r.get("estimated_cost", 0.0))

        total_tokens += tokens
        total_cost += cost

        # By role
        if role not in by_role:
            by_role[role] = {"tokens": 0, "cost": 0.0, "requests": 0}
        by_role[role]["tokens"] += tokens
        by_role[role]["cost"] += cost
        by_role[role]["requests"] += 1

        # By provider
        if prov not in by_provider:
            by_provider[prov] = {"tokens": 0, "cost": 0.0, "requests": 0}
        by_provider[prov]["tokens"] += tokens
        by_provider[prov]["cost"] += cost
        by_provider[prov]["requests"] += 1

    return {
        "total_requests": len(records),
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "by_role": by_role,
        "by_provider": by_provider,
    }


def clear_usage_records_for_tests() -> None:
    """Xóa file ghi chép — chỉ dùng cho teardown trong unit test."""
    with _LOCK:
        usage_file = _usage_file()
        if usage_file.exists():
            usage_file.unlink()
