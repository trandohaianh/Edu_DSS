"""Admin AI config — RBAC 3 cấp cho tab Tư vấn AI (mục 2/3 bản yêu cầu refactor).

Chỉ Admin được đặt provider/model MẶC ĐỊNH cho toàn hệ thống (lưu vào 1 file
JSON cục bộ) — Giảng viên và Sinh viên chỉ ĐỌC giá trị này, không sửa được.
Hàm ghi (`set_default_provider`) được chặn ở TẦNG SERVICE bằng
`auth_service.require_role("Admin")` — không chỉ ẩn nút trên UI, nên dù có cách
nào gọi thẳng hàm này (bỏ qua UI), lời gọi vẫn bị chặn nếu người gọi không phải
Admin của phiên hiện tại (kiểm tra qua `st.session_state["_auth_role"]`, không
phải tham số truyền vào — tránh trường hợp code khác lỡ truyền sai role).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypedDict

from dss.core.data_root import get_data_root
from dss.services.auth_service import require_role


def _config_path() -> Path:
    """PERF-002: tính lại mỗi lần gọi, không cache mức module (xem dss/core/data_root.py)."""
    return get_data_root() / "ai_default_provider.json"


class DefaultProviderConfig(TypedDict):
    provider_key: str
    model_name: str


def get_default_provider() -> Optional[DefaultProviderConfig]:
    """Đọc cấu hình provider/model mặc định do Admin đặt — Giảng viên/Sinh viên
    và các luồng tự động (auto-detect) đều chỉ ĐỌC qua hàm này, không có hàm ghi
    nào khác ngoài `set_default_provider`."""
    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("ADMIN_AI_CONFIG"):
        from dss.core.warehouse import _current_organization_id
        from dss.db.repositories import admin_ai_config_repository

        return admin_ai_config_repository.get_config(_current_organization_id())

    config_path = _config_path()
    if not config_path.exists():
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("provider_key") and data.get("model_name"):
            return {"provider_key": data["provider_key"], "model_name": data["model_name"]}
    except (json.JSONDecodeError, OSError):
        pass
    return None


@require_role("Admin")
def set_default_provider(provider_key: str, model_name: str) -> None:
    """Đặt provider/model mặc định cho toàn hệ thống — CHỈ Admin (chặn ở tầng
    service qua decorator, không chỉ ẩn nút UI)."""
    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("ADMIN_AI_CONFIG"):
        from dss.core.warehouse import _current_organization_id
        from dss.db.repositories import admin_ai_config_repository

        admin_ai_config_repository.set_config(_current_organization_id(), provider_key, model_name)
        return

    config_path = _config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"provider_key": provider_key, "model_name": model_name}, f, ensure_ascii=False, indent=2)


@require_role("Admin")
def clear_default_provider() -> None:
    """Xoá cấu hình mặc định (quay lại auto-detect theo thứ tự Ollama -> Gemini
    -> Groq -> OpenAI) — CHỈ Admin."""
    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("ADMIN_AI_CONFIG"):
        from dss.core.warehouse import _current_organization_id
        from dss.db.repositories import admin_ai_config_repository

        admin_ai_config_repository.clear_config(_current_organization_id())
        return

    config_path = _config_path()
    if config_path.exists():
        config_path.unlink()
