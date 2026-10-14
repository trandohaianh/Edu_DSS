"""Authorized tenant user administration with immutable audit records."""
from __future__ import annotations

from typing import Any

import streamlit as st

from dss.core.observability import observed
from dss.db.repositories import audit_log_repository
from dss.db.repositories.user_repository import UserRepository
from dss.services.auth_service import require_role


def _actor() -> str:
    return str(st.session_state.get("_auth_username") or "admin")


def _audit(org: int, action: str, username: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    safe_before = {k:v for k,v in (before or {}).items() if k not in {"hash","salt"}}
    safe_after = {k:v for k,v in (after or {}).items() if k not in {"hash","salt"}}
    audit_log_repository.record(action,"user",username,_actor(),organization_id=org,before=safe_before,after=safe_after)


@require_role("Admin")
@observed("user.admin.create")
def create_user(organization_id: int, username: str, password: str, role: str, student_id: str | None = None):
    repo=UserRepository(organization_id); result=repo.create_user(username,password,role,student_id=student_id); _audit(organization_id,"user.created",username,None,result); return result


@require_role("Admin")
@observed("user.admin.update")
def update_user(organization_id: int, username: str, **changes):
    repo=UserRepository(organization_id); before=repo.get_user_by_username(username); after=repo.update_user(username,**changes); _audit(organization_id,"user.updated",username,before,after); return after


@require_role("Admin")
def set_user_active(organization_id: int, username: str, active: bool):
    repo=UserRepository(organization_id); before=repo.get_user_by_username(username); after=repo.set_active(username,active); _audit(organization_id,"user.enabled" if active else "user.disabled",username,before,after); return after


@require_role("Admin")
def reset_password(organization_id: int, username: str, new_password: str) -> None:
    UserRepository(organization_id).reset_password(username,new_password); _audit(organization_id,"user.password_reset",username,None,{"password_changed":True})


@require_role("Admin")
def change_role(organization_id: int, username: str, role: str):
    repo=UserRepository(organization_id); before=repo.get_user_by_username(username); after=repo.change_role(username,role); _audit(organization_id,"user.role_changed",username,before,after); return after
