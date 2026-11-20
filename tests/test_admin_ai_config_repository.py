"""dss/db/repositories/admin_ai_config_repository.py + admin_ai_config.py's
Postgres wiring (Phase 1C, priority item 11 — admin AI configuration).
Skipped (not faked) without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — admin AI config repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"AICFG_TEST_{uuid.uuid4().hex[:8]}", name="Admin AI Config Test Org")
        session.add(org)
        session.flush()
        return org.id


def test_get_config_returns_none_when_unset(org_id):
    from dss.db.repositories import admin_ai_config_repository as repo

    assert repo.get_config(org_id) is None


def test_set_and_get_config_round_trip(org_id):
    from dss.db.repositories import admin_ai_config_repository as repo

    repo.set_config(org_id, "gemini", "gemini-2.0-flash")
    config = repo.get_config(org_id)
    assert config == {"provider_key": "gemini", "model_name": "gemini-2.0-flash"}


def test_set_config_upserts_existing_row(org_id):
    from dss.db.repositories import admin_ai_config_repository as repo

    repo.set_config(org_id, "gemini", "gemini-2.0-flash")
    repo.set_config(org_id, "groq", "llama-3.3-70b-versatile")
    config = repo.get_config(org_id)
    assert config == {"provider_key": "groq", "model_name": "llama-3.3-70b-versatile"}


def test_clear_config(org_id):
    from dss.db.repositories import admin_ai_config_repository as repo

    repo.set_config(org_id, "gemini", "gemini-2.0-flash")
    repo.clear_config(org_id)
    assert repo.get_config(org_id) is None


def test_cross_tenant_isolation(org_id):
    from dss.db.models import Organization
    from dss.db.repositories import admin_ai_config_repository as repo
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"AICFG_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    repo.set_config(org_id, "gemini", "gemini-2.0-flash")
    assert repo.get_config(other_org_id) is None


def test_never_persists_secrets_or_api_keys(org_id):
    """Schema-level privacy check — the model must not carry any column that
    could hold an actual API key/secret value."""
    from dss.db.models import AdminAiConfig

    columns = {c.name for c in AdminAiConfig.__table__.columns}
    for forbidden in ("api_key", "secret", "token", "credential"):
        assert forbidden not in columns


def test_service_get_default_provider_reads_postgres_when_enabled(org_id, monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ADMIN_AI_CONFIG_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))

    from dss.db.repositories import admin_ai_config_repository as repo

    repo.set_config(org_id, "gemini", "gemini-2.0-flash")

    from dss.services import admin_ai_config

    assert admin_ai_config.get_default_provider() == {"provider_key": "gemini", "model_name": "gemini-2.0-flash"}


def test_service_set_default_provider_requires_admin_role_via_postgres(org_id, monkeypatch, tmp_path):
    import streamlit as st

    monkeypatch.setenv("EDUDSS_ADMIN_AI_CONFIG_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    st.session_state["_auth_role"] = "Sinh viên"

    from dss.services import admin_ai_config

    with pytest.raises(PermissionError):
        admin_ai_config.set_default_provider("gemini", "gemini-2.0-flash")

    st.session_state["_auth_role"] = "Admin"
    admin_ai_config.set_default_provider("gemini", "gemini-2.0-flash")
    assert admin_ai_config.get_default_provider() == {"provider_key": "gemini", "model_name": "gemini-2.0-flash"}
    del st.session_state["_auth_role"]


def test_service_does_not_dual_write_to_local_json(org_id, monkeypatch, tmp_path):
    import streamlit as st

    monkeypatch.setenv("EDUDSS_ADMIN_AI_CONFIG_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    st.session_state["_auth_role"] = "Admin"

    from dss.services import admin_ai_config

    admin_ai_config.set_default_provider("gemini", "gemini-2.0-flash")

    config_path = tmp_path / "ai_default_provider.json"
    assert not config_path.exists()
    del st.session_state["_auth_role"]


def test_service_local_mode_unaffected_by_default(monkeypatch, tmp_path):
    import streamlit as st

    monkeypatch.delenv("EDUDSS_ADMIN_AI_CONFIG_STORE", raising=False)
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    st.session_state["_auth_role"] = "Admin"

    from dss.services import admin_ai_config

    admin_ai_config.set_default_provider("ollama", "llama3")
    assert admin_ai_config.get_default_provider() == {"provider_key": "ollama", "model_name": "llama3"}
    del st.session_state["_auth_role"]
