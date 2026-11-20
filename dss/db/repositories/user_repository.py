"""Repository for the `users`/`roles` domain (Phase 1C, priority item 1 —
"users/authentication").

Real existing runtime being cut over: `dss/services/auth_service.py`'s local
JSON store (`data_warehouse/users.json`). `auth_service.py` was ALREADY
written (before this phase) to call a `repository_for("IDENTITY")` object
with exactly this method shape — `get_user_by_username`, `list_users`,
`count_users_by_role` — falling back to the local JSON path whenever
`repository_for("IDENTITY")` returns `None`. This module provides the first
real implementation of that object; `dss.core.persistence_config.repository_for`
is updated alongside this file to actually return an instance of it instead
of raising `NotImplementedError`.

Password hashing is intentionally NOT reimplemented here — `_hash_password`/
the PBKDF2-HMAC-SHA256 parameters live in exactly one place
(`dss/services/auth_service.py`), reused via a lazy import (see
`_hash_password_and_salt` below) purely to avoid a module import cycle
(`auth_service` imports `persistence_config`, which lazily imports THIS
module only inside `repository_for()`'s function body, never at module load
time — so there is no cycle to break, just an ordering to respect: this
module must not import `auth_service` before `auth_service` has finished
importing `persistence_config`, which a top-level import here would risk).
This guarantees the exact same hash format/iteration count is used whether
an account is created through the local JSON path or through Postgres —
a password created before a Postgres cutover verifies identically after.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any, Optional

from dss.db.models import Organization, Role, User
from dss.db.session import tenant_session_scope


def _hash_password_and_salt(password: str) -> tuple[str, str]:
    from dss.services.auth_service import _hash_password  # lazy: see module docstring

    return _hash_password(password)


def _row_to_record(row: User, role_name: str) -> dict[str, Any]:
    """Shape matches auth_service.py's local JSON `UserRecord` TypedDict
    exactly (`hash`/`salt`, not `password_hash`/`password_salt`) so
    `authenticate()`/`_verify_password()` work unmodified regardless of
    which backend is active."""
    return {
        "username": row.username,
        "role": role_name,
        "student_id": row.student_id,
        "hash": row.password_hash,
        "salt": row.password_salt,
        "auto_provisioned": row.auto_provisioned,
        "is_active": row.is_active,
        "email": row.email,
    }


class UserRepository:
    """Bound to one organization at construction time (server-resolved, never
    from user/UI input — see `dss.core.persistence_config.repository_for`)."""

    def __init__(self, organization_id: int):
        self.organization_id = organization_id

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        with tenant_session_scope(self.organization_id) as session:
            organization = session.get(Organization, self.organization_id)
            if organization is None or not organization.is_active:
                return None
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one_or_none()
            if row is None:
                return None
            role = session.get(Role, row.role_id)
            return _row_to_record(row, role.name if role else "unknown")

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Google Sign-In: the verified e-mail an Admin linked to this account (case-insensitive)."""
        from sqlalchemy import func

        with tenant_session_scope(self.organization_id) as session:
            organization = session.get(Organization, self.organization_id)
            if organization is None or not organization.is_active:
                return None
            rows = (
                session.query(User)
                .filter(User.organization_id == self.organization_id, func.lower(User.email) == email.strip().lower())
                .order_by(User.id)
                .limit(2)
                .all()
            )
            if len(rows) != 1:  # none, or ambiguous (two accounts share an e-mail): refuse
                return None
            role = session.get(Role, rows[0].role_id)
            return _row_to_record(rows[0], role.name if role else "unknown")

    def list_users(self, limit: int = 1000, offset: int = 0) -> dict[str, dict[str, Any]]:
        with tenant_session_scope(self.organization_id) as session:
            rows = (
                session.query(User)
                .filter_by(organization_id=self.organization_id)
                .order_by(User.id)
                .limit(limit)
                .offset(offset)
                .all()
            )
            result: dict[str, dict[str, Any]] = {}
            for row in rows:
                role = session.get(Role, row.role_id)
                result[row.username] = _row_to_record(row, role.name if role else "unknown")
            return result

    def count_users_by_role(self) -> dict[str, int]:
        with tenant_session_scope(self.organization_id) as session:
            rows = session.query(User).filter_by(organization_id=self.organization_id).all()
            counts: dict[str, int] = {}
            for row in rows:
                role = session.get(Role, row.role_id)
                name = role.name if role else "unknown"
                counts[name] = counts.get(name, 0) + 1
            return counts

    def create_user(
        self,
        username: str,
        password: str,
        role_name: str,
        student_id: Optional[str] = None,
        auto_provisioned: bool = False,
    ) -> dict[str, Any]:
        """Used both by admin-created accounts and by the existing
        auto-provision-on-first-login flow (see auth_service.py::authenticate).
        Idempotent-safe by the schema's own UniqueConstraint(organization_id,
        username) — a racing duplicate create raises IntegrityError rather
        than silently overwriting a different password."""
        pw_hash, salt = _hash_password_and_salt(password)
        with tenant_session_scope(self.organization_id) as session:
            role = session.query(Role).filter_by(name=role_name).one_or_none()
            if role is None:
                raise ValueError(f"Unknown role: {role_name}")
            row = User(
                organization_id=self.organization_id,
                username=username,
                password_hash=pw_hash,
                password_salt=salt,
                role_id=role.id,
                student_id=student_id,
                auto_provisioned=auto_provisioned,
            )
            session.add(row)
            session.flush()
            return _row_to_record(row, role_name)

    def touch_last_login(self, username: str) -> None:
        with tenant_session_scope(self.organization_id) as session:
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one_or_none()
            if row is not None:
                row.last_login_at = datetime.now(UTC)

    def update_user(
        self, username: str, *, email: Optional[str] = None, student_id: Optional[str] = None
    ) -> dict[str, Any]:
        with tenant_session_scope(self.organization_id) as session:
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one()
            if email is not None:
                row.email = email
            if student_id is not None:
                row.student_id = student_id
            role = session.get(Role, row.role_id)
            session.flush()
            return _row_to_record(row, role.name if role else "unknown")

    def set_active(self, username: str, active: bool) -> dict[str, Any]:
        with tenant_session_scope(self.organization_id) as session:
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one()
            row.is_active = bool(active)
            role = session.get(Role, row.role_id)
            session.flush()
            return _row_to_record(row, role.name if role else "unknown")

    def reset_password(self, username: str, new_password: str) -> None:
        password_hash, salt = _hash_password_and_salt(new_password)
        with tenant_session_scope(self.organization_id) as session:
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one()
            row.password_hash = password_hash
            row.password_salt = salt

    def change_role(self, username: str, role_name: str) -> dict[str, Any]:
        with tenant_session_scope(self.organization_id) as session:
            row = session.query(User).filter_by(organization_id=self.organization_id, username=username).one()
            role = session.query(Role).filter_by(name=role_name).one()
            row.role_id = role.id
            session.flush()
            return _row_to_record(row, role.name)
