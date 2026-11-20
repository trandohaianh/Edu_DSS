"""Real initial administrators: no demo seeds, overwrite or printed secrets."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from uuid import uuid4
import warnings

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from ops import bootstrap_identity as bootstrap
from dss.db.models import Organization, Role, User

PASSWORD = "Isolated test password 2026!"


def args(**changes):
    values = dict(org_code="TEST", org_name="Test university", username=" Owner.Admin ",
                  role="Admin", password=PASSWORD)
    return values | changes


@pytest.fixture
def database():
    engine = create_engine("sqlite:///:memory:")
    for table in (Organization.__table__, Role.__table__, User.__table__):
        table.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_IDENTITY_STORE", "local")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "17")
    return tmp_path


def create(engine, **changes):
    with Session(engine) as session, session.begin():
        return bootstrap.provision_account(session, **args(**changes))


@pytest.mark.parametrize("role", ["Admin", "Platform Admin"])
def test_only_requested_real_account_and_role_catalog(database, monkeypatch, role):
    from dss.db import seed
    from dss.services.auth_service import _verify_password
    def no_demo(*a, **kw):
        pytest.fail("No demo provisioning")
    for name in ("seed_demo_organization", "seed_demo_users", "run_seed"):
        monkeypatch.setattr(seed, name, no_demo)
    result = create(database, role=role)
    assert result["username"] == "owner.admin"
    with Session(database) as session:
        assert session.scalar(select(func.count(User.id))) == 1
        assert session.scalar(select(func.count(Organization.id))) == 1
        assert session.scalar(select(func.count(Role.id))) == 4
        user = session.scalar(select(User))
        assert session.get(Role, user.role_id).name == role
        assert user.is_active and not user.auto_provisioned and user.student_id is None
        assert _verify_password(PASSWORD, user.password_hash, user.password_salt)


def test_duplicate_preserves_password_and_hash_failure_rolls_back(database, monkeypatch):
    from dss.services import auth_service
    create(database)
    with Session(database) as session:
        old = session.scalar(select(User)).password_hash
    with pytest.raises(bootstrap.BootstrapError, match="already exists"):
        create(database, username="OWNER.ADMIN", role="Platform Admin", password="Replacement password never used!")
    with Session(database) as session:
        assert session.scalar(select(User)).password_hash == old
    def fail(*a, **kw):
        raise RuntimeError("Hasher unavailable")
    monkeypatch.setattr(auth_service, "_hash_password", fail)
    with pytest.raises(RuntimeError):
        create(database, org_code="OTHER", org_name="Other organization")
    with Session(database) as session:
        assert session.scalar(select(func.count(Organization.id))) == 1


def test_local_bootstrap_and_duplicate_preserve_bytes(local):
    from dss.services.auth_service import _verify_password
    result = bootstrap.bootstrap_local(**args(role="Platform Admin"))
    path = local / "users.json"
    before = path.read_bytes()
    users = json.loads(before)
    assert set(users) == {"owner.admin"}
    user = users["owner.admin"]
    assert _verify_password(PASSWORD, user["hash"], user["salt"])
    assert result["organization_id"] == 17
    assert PASSWORD not in before.decode()
    with pytest.raises(bootstrap.BootstrapError, match="already exists"):
        bootstrap.bootstrap_local(**args())
    assert path.read_bytes() == before


@pytest.mark.parametrize("existing", ["invalid json", "[]", '{"owner":"invalid"}'])
def test_corrupt_local_store_is_not_overwritten(local, existing):
    path = local / "users.json"
    path.write_text(existing, encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.bootstrap_local(**args())
    assert path.read_text(encoding="utf-8") == existing


def test_local_scope_and_production_refusals(local, monkeypatch):
    bootstrap.bootstrap_local(**args())
    before = (local / "users.json").read_bytes()
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "18")
    with pytest.raises(bootstrap.BootstrapError, match="another organization"):
        bootstrap.bootstrap_local(**args(username="another"))
    monkeypatch.setenv("EDUDSS_MODE", "REAL_LMS")
    with pytest.raises(bootstrap.BootstrapError, match="production"):
        bootstrap.bootstrap_local(**args(username="another"))
    assert (local / "users.json").read_bytes() == before


def test_concurrent_local_creation_cannot_overwrite(local):
    def run(index):
        try:
            return bootstrap.bootstrap_local(**args(password=PASSWORD + str(index)))
        except bootstrap.BootstrapError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(item is not None for item in executor.map(run, range(2))) == 1
    assert len(json.loads((local / "users.json").read_text(encoding="utf-8"))) == 1


@pytest.mark.parametrize("change", [
    {"password": "short"}, {"username": "bad user"}, {"role": "unknown"}, {"org_code": ""},
])
def test_invalid_input_leaves_no_store(local, change):
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.bootstrap_local(**args(**change))
    assert not (local / "users.json").exists()


def cli_args(*extra):
    return ["--org-code", "TEST", "--org-name", "Test university", "--username", "owner", "--role", "Admin", *extra]


def test_cli_hidden_password_mismatch_and_insecure_prompt(local, monkeypatch, capsys):
    responses = iter([PASSWORD, PASSWORD + "mismatch"])
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda label: next(responses))
    assert bootstrap.main(cli_args("--local")) == 2
    assert not (local / "users.json").exists()
    def insecure(label):
        warnings.warn("Echo unavailable", bootstrap.getpass.GetPassWarning)
        pytest.fail("Must not continue after insecure prompt")
    monkeypatch.setattr(bootstrap.getpass, "getpass", insecure)
    assert bootstrap.main(cli_args("--local")) == 2
    assert PASSWORD not in capsys.readouterr().err


def test_cli_success_or_driver_failure_never_prints_secrets(local, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda label: PASSWORD)
    assert bootstrap.main(cli_args("--local")) == 0
    output = capsys.readouterr()
    record = json.loads((local / "users.json").read_text(encoding="utf-8"))["owner"]
    assert PASSWORD not in output.out + output.err
    assert record["hash"] not in output.out + output.err
    assert record["salt"] not in output.out + output.err
    secret_url = "postgresql://owner:do-not-print-this@invalid/disposable"
    def fail(**kw):
        raise RuntimeError(secret_url + PASSWORD)
    monkeypatch.setattr(bootstrap, "bootstrap_postgres", fail)
    assert bootstrap.main(cli_args()) == 1
    output = capsys.readouterr()
    assert secret_url not in output.out + output.err and PASSWORD not in output.out + output.err


def test_cli_rejects_secret_in_arguments(capsys):
    with pytest.raises(SystemExit):
        bootstrap.main(cli_args("--password", PASSWORD))
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err


def test_postgres_owner_bootstrap_in_explicit_disposable_database(monkeypatch):
    owner_url = os.getenv("EDUDSS_BOOTSTRAP_TEST_OWNER_URL")
    app_url = os.getenv("EDUDSS_PLATFORM_TEST_APP_URL")
    if not owner_url or os.getenv("EDUDSS_BOOTSTRAP_TEST_ALLOW_WRITE") != "1":
        pytest.skip("Explicit isolated owner URL and write opt-in required")
    from dss.services.auth_service import _verify_password
    code = "bootstrap-" + uuid4().hex
    monkeypatch.setenv("DATABASE_URL", owner_url)
    engine = create_engine(owner_url)
    try:
        result = bootstrap.bootstrap_postgres(**args(org_code=code))
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT u.password_hash, u.password_salt FROM users u JOIN organizations o "
                "ON u.organization_id=o.id WHERE o.org_code=:code"), {"code": code}).one()
        assert _verify_password(PASSWORD, row.password_hash, row.password_salt)
        assert result["organization_id"] > 0
        with pytest.raises(bootstrap.BootstrapError, match="already exists"):
            bootstrap.bootstrap_postgres(**args(org_code=code))
        monkeypatch.setenv("DATABASE_URL", app_url)
        with pytest.raises(bootstrap.BootstrapError, match="owner"):
            bootstrap.bootstrap_postgres(**args(org_code="refused-" + uuid4().hex))
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM organizations WHERE org_code=:code"), {"code": code})
        engine.dispose()
