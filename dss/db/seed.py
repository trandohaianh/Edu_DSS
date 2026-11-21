"""Demo/seed data for the PostgreSQL schema (Phase 1).

Mirrors the demo data already seeded into the JSON stores (see
`dss/services/auth_service.py::_seed_default_accounts_into`,
`dss/services/subscription_service.py::DEFAULT_ORGANIZATION_SUBSCRIPTION`) so a
side-by-side comparison during migration testing is meaningful. Idempotent —
safe to run more than once (checks for existing rows by unique key first).

Usage: python -m dss.db.seed  (requires DATABASE_URL or DB_HOST/DB_NAME/DB_USER
in the environment — see dss/db/session.py).
"""

from __future__ import annotations

from datetime import date, timedelta

from dss.db.models import Organization, Role, Subscription, User
from dss.db.session import session_scope
from dss.services.auth_service import _hash_password  # reuse the real, already-audited hasher


def seed_roles(session) -> dict[str, Role]:
    # "Platform Admin" (Stage 2, University Onboarding): a cross-tenant
    # operational role, deliberately not in dss/core/roles.py's ROLES (see
    # that file's TAB_ACCESS comment) — seeded here so
    # UserRepository.create_user(role_name="Platform Admin") has a real
    # `roles` row to reference, same as every other role.
    role_names = ["Admin", "Giảng viên / CVHT", "Sinh viên", "Platform Admin"]
    existing = {r.name: r for r in session.query(Role).all()}
    for name in role_names:
        if name not in existing:
            role = Role(name=name)
            session.add(role)
            session.flush()
            existing[name] = role
    return existing


def seed_demo_organization(session) -> Organization:
    org = session.query(Organization).filter_by(org_code="DEMO_UNIV").one_or_none()
    if org is None:
        org = Organization(org_code="DEMO_UNIV", name="Trường Đại học Demo EduDSS", domain="demo.edudss.local")
        session.add(org)
        session.flush()

    if not session.query(Subscription).filter_by(organization_id=org.id).first():
        session.add(
            Subscription(
                organization_id=org.id,
                plan="ENTERPRISE",
                status="ACTIVE",
                max_students=5000,
                max_courses=150,
                max_ai_requests_month=100_000,
                max_storage_mb=51_200,
                features_enabled=["LMS_SYNC", "CMS_LECTURE_RAG", "ML_TRAINING", "STUDENT_DIAGNOSIS"],
                start_date=date.today(),
                end_date=date.today() + timedelta(days=365),
            )
        )
    return org


def seed_demo_users(session, org: Organization, roles: dict[str, Role]) -> None:
    demo_accounts = [
        ("admin", "admin123", "Admin", None),
        ("giangvien", "gv123", "Giảng viên / CVHT", None),
        ("sv001", "sv001123", "Sinh viên", "SV001"),
    ]
    for username, password, role_name, student_id in demo_accounts:
        if session.query(User).filter_by(organization_id=org.id, username=username).first():
            continue
        pw_hash, salt = _hash_password(password)
        session.add(
            User(
                organization_id=org.id,
                username=username,
                password_hash=pw_hash,
                password_salt=salt,
                role_id=roles[role_name].id,
                student_id=student_id,
                auto_provisioned=student_id is not None,
            )
        )


def run_seed() -> None:
    # Bước 7 (21/11/2026): tạo tài khoản demo có mật khẩu đã biết (admin/admin123...) — KHÔNG bao giờ
    # được chạy trên CSDL production. Dùng đúng điều kiện của auth_service (runtime_mode).
    from dss.core.runtime_mode import demo_accounts_seed_allowed

    if not demo_accounts_seed_allowed():
        raise SystemExit(
            "Từ chối seed: tài khoản demo chỉ được tạo khi EDUDSS_ENV=development/test và không bật "
            "EDUDSS_PUBLIC_DEMO. Không đặt EDUDSS_ENV thì hệ thống coi là production."
        )
    with session_scope() as session:
        roles = seed_roles(session)
        org = seed_demo_organization(session)
        seed_demo_users(session, org, roles)


if __name__ == "__main__":
    run_seed()
    print("Seed complete.")
