"""dss/db/repositories/user_repository.py + auth_service.py's Postgres wiring
(Phase 1C, priority item 1 — users/authentication). Skipped (not faked)
without a configured database.
"""

from __future__ import annotations

import uuid

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(
    not is_database_configured(),
    reason="No PostgreSQL configured — user repository tests skipped, not faked",
)


@pytest.fixture()
def org_id():
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"AUTH_TEST_{uuid.uuid4().hex[:8]}", name="Auth Test Org")
        session.add(org)
        session.flush()
        return org.id


@pytest.fixture(autouse=True)
def _ensure_roles_seeded():
    """Roles are a shared catalog (not tenant-scoped) — seed once if missing,
    matching dss/db/seed.py::seed_roles's own idempotent pattern."""
    from dss.db.models import Role
    from dss.db.session import session_scope

    with session_scope() as session:
        existing = {r.name for r in session.query(Role).all()}
        for name in ("Admin", "Giảng viên / CVHT", "Sinh viên"):
            if name not in existing:
                session.add(Role(name=name))
        session.flush()


def test_create_and_get_user_round_trip(org_id):
    from dss.db.repositories.user_repository import UserRepository

    repo = UserRepository(org_id)
    created = repo.create_user(username="admin", password="admin123", role_name="Admin")
    assert created["role"] == "Admin"
    assert created["username"] == "admin"

    fetched = repo.get_user_by_username("admin")
    assert fetched is not None
    assert fetched["role"] == "Admin"
    assert fetched["hash"] == created["hash"]
    assert fetched["salt"] == created["salt"]


def test_get_user_by_username_returns_none_when_missing(org_id):
    from dss.db.repositories.user_repository import UserRepository

    repo = UserRepository(org_id)
    assert repo.get_user_by_username("does_not_exist") is None


def test_password_verifies_through_the_shared_hasher(org_id):
    """The repository must produce hashes verifiable by auth_service's own
    _verify_password — proving the hash format is identical whether an
    account is created locally or through Postgres."""
    from dss.db.repositories.user_repository import UserRepository
    from dss.services.auth_service import _verify_password

    repo = UserRepository(org_id)
    repo.create_user(username="sv001", password="sv001123", role_name="Sinh viên", student_id="SV001")
    record = repo.get_user_by_username("sv001")
    assert _verify_password("sv001123", record["hash"], record["salt"]) is True
    assert _verify_password("wrong-password", record["hash"], record["salt"]) is False


def test_list_users_and_count_by_role(org_id):
    from dss.db.repositories.user_repository import UserRepository

    repo = UserRepository(org_id)
    repo.create_user(username="admin", password="admin123", role_name="Admin")
    repo.create_user(username="gv1", password="gv123", role_name="Giảng viên / CVHT")
    repo.create_user(username="sv001", password="sv001123", role_name="Sinh viên", student_id="SV001")
    repo.create_user(username="sv002", password="sv002123", role_name="Sinh viên", student_id="SV002")

    users = repo.list_users()
    assert set(users.keys()) == {"admin", "gv1", "sv001", "sv002"}

    counts = repo.count_users_by_role()
    assert counts == {"Admin": 1, "Giảng viên / CVHT": 1, "Sinh viên": 2}


def test_duplicate_username_in_same_org_rejected(org_id):
    from sqlalchemy.exc import IntegrityError

    from dss.db.repositories.user_repository import UserRepository

    repo = UserRepository(org_id)
    repo.create_user(username="admin", password="admin123", role_name="Admin")
    with pytest.raises(IntegrityError):
        repo.create_user(username="admin", password="different", role_name="Admin")


def test_same_username_allowed_across_different_orgs(org_id):
    from dss.db.models import Organization
    from dss.db.repositories.user_repository import UserRepository
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"AUTH_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    UserRepository(org_id).create_user(username="admin", password="pw1", role_name="Admin")
    UserRepository(other_org_id).create_user(username="admin", password="pw2", role_name="Admin")

    assert (
        UserRepository(org_id).get_user_by_username("admin")["hash"]
        != UserRepository(other_org_id).get_user_by_username("admin")["hash"]
    )


def test_cross_tenant_isolation_read(org_id):
    from dss.db.models import Organization
    from dss.db.repositories.user_repository import UserRepository
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"AUTH_OTHER_{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    UserRepository(org_id).create_user(username="secret_admin", password="pw", role_name="Admin")

    assert UserRepository(other_org_id).get_user_by_username("secret_admin") is None
    assert len(UserRepository(other_org_id).list_users()) == 0
    assert UserRepository(other_org_id).count_users_by_role() == {}


def test_cross_tenant_isolation_via_real_rls(org_id):
    """Adversarial check using the actual non-superuser app role, not just
    the repository's own organization_id filter — proves RLS itself (not
    just application-level filtering) blocks cross-tenant reads."""
    import os

    app_role_url = os.environ.get("DATABASE_APP_ROLE_URL")
    if not app_role_url:
        pytest.skip("DATABASE_APP_ROLE_URL not configured — real RLS check skipped, not faked")

    from sqlalchemy import create_engine, text

    from dss.db.models import Organization
    from dss.db.repositories.user_repository import UserRepository
    from dss.db.session import session_scope

    with session_scope() as session:
        other = Organization(org_code=f"AUTH_RLS_{uuid.uuid4().hex[:8]}", name="RLS Other Org")
        session.add(other)
        session.flush()
        other_org_id = other.id

    UserRepository(org_id).create_user(username="rls_admin", password="pw", role_name="Admin")

    engine = create_engine(app_role_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.organization_id = :org_id"), {"org_id": str(other_org_id)})
            rows = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": "rls_admin"}).fetchall()
        assert rows == [], "RLS FAILED: org B's session could see org A's user row"
    finally:
        engine.dispose()


def test_authenticate_uses_postgres_when_enabled(org_id, monkeypatch):
    """Full integration: auth_service.authenticate() end-to-end against a
    real Postgres-backed account, through the exact same public function the
    login UI calls."""
    from dss.db.repositories.user_repository import UserRepository
    from dss.services import auth_service

    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))

    UserRepository(org_id).create_user(username="pguser", password="pgpass123", role_name="Giảng viên / CVHT")

    record = auth_service.authenticate("pguser", "pgpass123")
    assert record is not None
    assert record["role"] == "Giảng viên / CVHT"

    assert auth_service.authenticate("pguser", "wrong-password") is None


def test_authenticate_auto_provision_via_postgres(org_id, monkeypatch):
    """The existing auto-provision-on-first-login UX must keep working when
    Postgres is the identity backend, not silently break."""
    from dss.db.repositories.user_repository import UserRepository
    from dss.services import auth_service

    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.delenv("EDUDSS_MODE", raising=False)

    assert UserRepository(org_id).get_user_by_username("sv042") is None
    record = auth_service.authenticate("sv042", "sv042123")
    assert record is not None
    assert record["role"] == "Sinh viên"
    assert record["student_id"] == "SV042"
    assert record["auto_provisioned"] is True

    # Persisted for real — a second call finds the same account, doesn't re-create it.
    again = auth_service.authenticate("sv042", "sv042123")
    assert again is not None
    assert UserRepository(org_id).count_users_by_role() == {"Sinh viên": 1}


def test_authenticate_never_logs_password_or_hash_via_postgres(org_id, monkeypatch, tmp_path):
    from dss.core import logging_config
    from dss.db.repositories.user_repository import UserRepository
    from dss.services import auth_service

    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "postgres")
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(org_id))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    logging_config._CONFIGURED = False

    record = UserRepository(org_id).create_user(username="privacyuser", password="s3cr3t-p4ss", role_name="Admin")
    auth_service.authenticate("privacyuser", "s3cr3t-p4ss")
    auth_service.authenticate("privacyuser", "wrong-attempt-xyz")

    log_file = tmp_path / "logs" / "technical.log"
    content = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "s3cr3t-p4ss" not in content
    assert "wrong-attempt-xyz" not in content
    assert record["hash"] not in content
    assert record["salt"] not in content
    logging_config._CONFIGURED = False
