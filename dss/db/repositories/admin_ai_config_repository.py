"""Repository for the `admin_ai_config` domain (Phase 1C, priority item 11 —
"admin AI configuration").

Real existing runtime being cut over: `dss/services/admin_ai_config.py`
(local JSON, `{data_root}/ai_default_provider.json`, single row: default
provider_key + model_name). One row per organization, matching the local
file's "one config for the whole deployment" semantics.

Only SAFE_DATABASE_CONFIG fields ever pass through here (`provider_key`,
`model_name` — plain non-secret strings, e.g. "gemini" / "gemini-2.0-flash").
Actual API keys/secrets are handled entirely separately via `st.secrets`/
environment variables and NEVER reach this table or this module.
"""
from __future__ import annotations

from typing import Any, Optional

from dss.db.models import AdminAiConfig
from dss.db.session import tenant_session_scope


def get_config(organization_id: int) -> Optional[dict[str, Any]]:
    with tenant_session_scope(organization_id) as session:
        row = session.query(AdminAiConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            return None
        return {"provider_key": row.provider_key, "model_name": row.model_name}


def set_config(organization_id: int, provider_key: str, model_name: str) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(AdminAiConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is None:
            row = AdminAiConfig(
                organization_id=organization_id, provider_key=provider_key, model_name=model_name,
            )
            session.add(row)
        else:
            row.provider_key = provider_key
            row.model_name = model_name


def clear_config(organization_id: int) -> None:
    with tenant_session_scope(organization_id) as session:
        row = session.query(AdminAiConfig).filter_by(organization_id=organization_id).one_or_none()
        if row is not None:
            session.delete(row)
