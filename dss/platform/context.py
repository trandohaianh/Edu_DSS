"""Authenticated server-resolved context for dedicated-school deployments."""
from __future__ import annotations

from dataclasses import dataclass
import os

from dss.core.runtime_mode import is_production


@dataclass(frozen=True)
class Actor:
    school_id: str
    username: str
    role: str
    student_id: str | None = None

    def __post_init__(self):
        school = str(self.school_id).strip()
        if not school or (school != "demo" and (not school.isdecimal() or int(school) <= 0)):
            raise ValueError("A valid server school scope is required.")
        if is_production() and school == "demo":
            raise ValueError("Demonstration school scope is unavailable in production.")
        if not isinstance(self.username, str) or not self.username.strip():
            raise ValueError("An authenticated principal is required.")
        object.__setattr__(self, "school_id", str(int(school)) if school != "demo" else school)
        object.__setattr__(self, "username", self.username.strip())


def current_actor() -> Actor:
    from dss.services.auth_service import current_user
    user = current_user()
    if not user:
        raise PermissionError("Authentication is required.")
    school_id = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not school_id:
        if is_production():
            raise RuntimeError("EDUDSS_ORGANIZATION_ID is required.")
        school_id = "demo"
    return Actor(
        school_id=school_id, username=str(user.get("username") or ""),
        role=str(user.get("role") or ""),
        student_id=str(user["student_id"]) if user.get("student_id") is not None else None,
    )
