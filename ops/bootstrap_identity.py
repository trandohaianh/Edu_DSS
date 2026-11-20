"""Owner-operated creation of the first real administrative account.

Use DATABASE_URL of the migration owner. Passwords use getpass, never argv.
Local mode is explicitly development-only and needs a separate data root/scope.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
ROLES = ("Admin", "Platform Admin")


class BootstrapError(ValueError):
    """An operator-safe refusal message without connection/secret data."""


def _text(value, maximum, label):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise BootstrapError(label + " is missing or invalid.")
    return value.strip()


def validate_options(org_code, org_name, username, role):
    code = _text(org_code, 64, "Organization code")
    name = _text(org_name, 255, "Organization name")
    user = _text(username, 128, "Username").lower()
    if len(user) > 128 or any(char.isspace() for char in user):
        raise BootstrapError("Username must not contain whitespace.")
    if role not in ROLES:
        raise BootstrapError("Only administrative bootstrap roles are allowed.")
    return code, name, user, role


def _validate_password(password):
    if not isinstance(password, str) or len(password) < 12 or not password.strip() or "\x00" in password:
        raise BootstrapError("Password must contain at least 12 characters.")


def _result(backend, organization_id, org_code, username, role):
    return dict(
        ok=True,
        created=True,
        backend=backend,
        organization_id=organization_id,
        org_code=org_code,
        username=username,
        role=role,
    )


def provision_account(session, *, org_code, org_name, username, role, password):
    """Create only organization/catalog/account in the caller's transaction."""
    from sqlalchemy import func, select

    from dss.db.models import Organization, User
    from dss.db.seed import seed_roles
    from dss.services.auth_service import _hash_password

    code, name, user, role = validate_options(org_code, org_name, username, role)
    _validate_password(password)
    organization = session.scalar(select(Organization).where(Organization.org_code == code))
    if organization is not None:
        if not organization.is_active:
            raise BootstrapError("The organization is inactive; no account was created.")
        if organization.name != name:
            raise BootstrapError("The organization code has a different name; use its existing name.")
        duplicate = session.scalar(
            select(User.id).where(User.organization_id == organization.id, func.lower(User.username) == user).limit(1)
        )
        if duplicate is not None:
            raise BootstrapError("That username already exists in this organization; it was not changed.")
    else:
        organization = Organization(
            org_code=code, name=name, is_active=True, lifecycle_status="ACTIVE", deployment_mode="DEDICATED"
        )
        session.add(organization)
        session.flush()
    roles = seed_roles(session)
    password_hash, salt = _hash_password(password)
    account = User(
        organization_id=organization.id,
        username=user,
        password_hash=password_hash,
        password_salt=salt,
        role_id=roles[role].id,
        student_id=None,
        is_active=True,
        auto_provisioned=False,
    )
    session.add(account)
    session.flush()
    return _result("postgres", organization.id, code, user, role)


def _require_owner(engine):
    from sqlalchemy import text

    with engine.connect() as connection:
        superuser = connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"))
        row = connection.execute(
            text(
                "SELECT count(*) AS total, bool_and(pg_has_role(current_user, c.relowner, 'USAGE')) AS owns "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname IN ('organizations','roles','users') "
                "AND c.relkind = 'r'"
            )
        ).one()
        if row.total != 3 or not (superuser or row.owns):
            raise BootstrapError("DATABASE_URL must use the migration/table owner, not the application role.")


def bootstrap_postgres(*, org_code, org_name, username, role, password):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from dss.db.schema_contract import assert_schema_matches

    validate_options(org_code, org_name, username, role)
    _validate_password(password)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise BootstrapError("DATABASE_URL is required for the PostgreSQL owner connection.")
    try:
        parsed = make_url(url)
    except Exception:
        raise BootstrapError("DATABASE_URL is invalid.") from None
    if parsed.get_backend_name() != "postgresql":
        raise BootstrapError("The owner connection must use PostgreSQL; local mode requires --local.")
    engine = create_engine(parsed, pool_pre_ping=True, echo=False, hide_parameters=True)
    try:
        try:
            assert_schema_matches(engine)
        except AssertionError:
            raise BootstrapError("Database schema is not current; apply and verify migrations first.") from None
        _require_owner(engine)
        with Session(engine, expire_on_commit=False) as session:
            with session.begin():
                session.execute(text("SET LOCAL row_security = off"))
                session.execute(text("SELECT pg_advisory_xact_lock(638416906285701)"))
                return provision_account(
                    session, org_code=org_code, org_name=org_name, username=username, role=role, password=password
                )
    finally:
        engine.dispose()


@contextmanager
def _local_lock(path):
    lock = path.with_suffix(".bootstrap.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise BootstrapError("Another local bootstrap holds the account-store lock.") from None
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def bootstrap_local(*, org_code, org_name, username, role, password):
    from dss.core.runtime_mode import is_production

    if is_production():
        raise BootstrapError("Local identity bootstrap is unavailable in production.")
    if os.environ.get("EDUDSS_IDENTITY_STORE", "local").strip().lower() != "local":
        raise BootstrapError("Local bootstrap requires EDUDSS_IDENTITY_STORE=local.")
    code, name, user, role = validate_options(org_code, org_name, username, role)
    _validate_password(password)
    data_root = os.environ.get("EDUDSS_DATA_ROOT", "").strip()
    scope = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not data_root or not scope.isdecimal() or int(scope) <= 0:
        raise BootstrapError(
            "Local bootstrap requires explicit EDUDSS_DATA_ROOT and a positive EDUDSS_ORGANIZATION_ID."
        )
    organization_id = int(scope)
    path = Path(data_root).expanduser().resolve() / "users.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _local_lock(path):
        try:
            users = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (ValueError, UnicodeError):
            raise BootstrapError("The existing account store is unreadable; it was not changed.") from None
        if not isinstance(users, dict) or any(
            not isinstance(key, str) or not isinstance(value, dict) for key, value in users.items()
        ):
            raise BootstrapError("The existing account store has an invalid structure; it was not changed.")
        if any(key.strip().lower() == user for key in users):
            raise BootstrapError("That username already exists; it was not changed.")
        for record in users.values():
            if record.get("organization_id") not in (None, organization_id, str(organization_id)) or record.get(
                "organization_code"
            ) not in (None, code):
                raise BootstrapError("This data root is already bound to another organization.")
        from dss.services.auth_service import _hash_password

        password_hash, salt = _hash_password(password)
        users[user] = dict(
            username=user,
            role=role,
            student_id=None,
            hash=password_hash,
            salt=salt,
            is_active=True,
            auto_provisioned=False,
            organization_id=organization_id,
            organization_code=code,
            organization_name=name,
        )
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".users-bootstrap-", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(users, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return _result("local", organization_id, code, user, role)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid command arguments. Use --help.\n")


def main(argv=None):
    parser = _Parser(description="Create one real administrative account without demo seeding.")
    parser.add_argument("--org-code", required=True)
    parser.add_argument("--org-name", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--local", action="store_true", help="Explicit local development account store.")
    args = parser.parse_args(argv)
    try:
        validate_options(args.org_code, args.org_name, args.username, args.role)
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("New password (at least 12 characters): ")
            confirmation = getpass.getpass("Confirm new password: ")
        _validate_password(password)
        if password != confirmation:
            raise BootstrapError("Password confirmation does not match.")
        operation = bootstrap_local if args.local else bootstrap_postgres
        result = operation(
            org_code=args.org_code, org_name=args.org_name, username=args.username, role=args.role, password=password
        )
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except BootstrapError as error:
        print("Bootstrap refused: " + str(error), file=sys.stderr)
        return 2
    except getpass.GetPassWarning:
        print("Bootstrap refused: secure password input is unavailable; use an interactive terminal.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Bootstrap cancelled.", file=sys.stderr)
        return 130
    except Exception:
        print(
            "Bootstrap failed. Check database availability, migrations, owner permissions or local-store access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
