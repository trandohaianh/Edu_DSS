"""C1.1 — student data lifecycle: export, erasure/anonymization, retention.

Policy tests always run. PostgreSQL tests run against a real database when one is
configured and are skipped (not faked) otherwise."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from dss.db.session import is_database_configured
from dss.services import data_lifecycle as dl

requires_pg = pytest.mark.skipif(not is_database_configured(),
                                 reason="No PostgreSQL configured — lifecycle DB tests skipped, not faked")


# ---------------------------------------------------------------- policy (always)
def test_retention_policy_distinguishes_record_classes():
    policy = dl.retention_policy()
    assert policy[dl.ACADEMIC_RECORD].erasure_action == "RETAIN" and policy[dl.ACADEMIC_RECORD].days is None
    assert policy[dl.IDENTITY].erasure_action == "ANONYMIZE"
    assert policy[dl.AI_CONVERSATION].erasure_action == "DELETE" and policy[dl.AI_CONVERSATION].days == 365
    assert policy[dl.DERIVED_ANALYTICS].erasure_action == "DELETE"
    assert policy[dl.AUDIT].erasure_action == "REDACT" and policy[dl.AUDIT].days == 1825
    assert policy[dl.AI_USAGE].erasure_action == "RETAIN"


def test_retention_can_be_overridden_per_deployment(monkeypatch):
    monkeypatch.setenv("EDUDSS_RETENTION_AI_CONVERSATION_DAYS", "90")
    monkeypatch.setenv("EDUDSS_RETENTION_AUDIT_DAYS", "not-a-number")
    policy = dl.retention_policy()
    assert policy[dl.AI_CONVERSATION].days == 90
    assert policy[dl.AUDIT].days == 1825  # invalid override ignored, default kept


# ---------------------------------------------------------------- PostgreSQL
STUDENT_NAME = "Nguyễn Thị Kiểm Thử"
STUDENT_EMAIL = "kiem.thu@example.invalid"


def _seed(org_code_prefix: str):
    from dss.db import models as m
    from dss.db.session import session_scope
    from dss.services.privacy_service import generate_pseudonym

    with session_scope() as s:
        org = m.Organization(org_code=f"{org_code_prefix}_{uuid.uuid4().hex[:8]}", name="Lifecycle Test Org")
        s.add(org)
        s.flush()
        role = s.query(m.Role).filter(m.Role.name == "Sinh viên").one_or_none() or m.Role(name="Sinh viên")
        s.add(role)
        s.flush()
        code = f"SV{uuid.uuid4().hex[:6].upper()}"
        user = m.User(organization_id=org.id, username=code.lower(), password_hash="x", password_salt="y",
                      role_id=role.id, email=STUDENT_EMAIL, student_id=code)
        s.add(user)
        s.flush()
        student = m.Student(organization_id=org.id, student_code=code, full_name=STUDENT_NAME,
                            external_id=f"lms-{code}", user_id=user.id)
        course = m.Course(organization_id=org.id, course_code=f"C{uuid.uuid4().hex[:5]}", title="Thống kê")
        s.add_all([student, course])
        s.flush()
        pseudonym = generate_pseudonym(code, organization_id=org.id)
        s.add_all([
            m.AcademicRecord(organization_id=org.id, student_id=student.id, course_id=course.id,
                             record_type="final", value=7.5),
            m.Consultation(organization_id=org.id, student_id=student.id, provider="groq",
                           question=f"Em là {STUDENT_NAME}", answer="Lời khuyên"),
            m.Recommendation(organization_id=org.id, student_id=student.id, recommendation_type="plan",
                             content="Kế hoạch 4 tuần"),
            m.ActivityLog(organization_id=org.id, user_id=user.id, action_type="login",
                          description=f"{STUDENT_NAME} đăng nhập", details={"email": STUDENT_EMAIL}),
            m.CmsStudentInteraction(organization_id=org.id, student_pseudonym=pseudonym, course_id="C1",
                                    question="Câu hỏi riêng tư"),
        ])
        return org.id, code, student.id, user.id


@requires_pg
def test_export_contains_every_category_but_no_credentials():
    org_id, code, _, _ = _seed("LC_EXPORT")
    export = dl.export_student_data(org_id, code)
    text = json.dumps(export, ensure_ascii=False, default=str)
    assert export[dl.IDENTITY]["student"]["full_name"] == STUDENT_NAME
    assert "password_hash" not in text and "password_salt" not in text
    assert len(export[dl.ACADEMIC_RECORD]["academic_records"]) == 1
    assert len(export[dl.AI_CONVERSATION]["consultations"]) == 1
    assert len(export[dl.AI_CONVERSATION]["cms_student_interactions"]) == 1
    assert len(export[dl.DERIVED_ANALYTICS]["recommendations"]) == 1
    assert "retention_policy" in export


@requires_pg
def test_erasure_deletes_ai_data_anonymizes_identity_retains_academic_records():
    from dss.db import models as m
    from dss.db.session import session_scope

    org_id, code, student_pk, user_pk = _seed("LC_ERASE")
    report = dl.erase_student_data(org_id, code, requested_by="dpo@university.test")

    assert report.deleted["consultations"] == 1 and report.deleted["recommendations"] == 1
    assert report.deleted["cms_student_interactions"] == 1
    assert report.retained["academic_records"] == 1
    assert report.anonymized == {"students": 1, "users": 1}
    assert report.redacted["activity_logs"] == 1

    with session_scope() as s:
        student = s.get(m.Student, student_pk)
        user = s.get(m.User, user_pk)
        assert student.full_name == dl.REDACTED and student.external_id is None and not student.is_active
        assert student.student_code.startswith("erased-") and code not in student.student_code
        assert user.email is None and user.student_id is None and not user.is_active
        assert user.username.startswith("erased-") and user.password_hash.startswith("erased$")
        assert s.query(m.AcademicRecord).filter(m.AcademicRecord.student_id == student_pk).count() == 1
        log = s.query(m.ActivityLog).filter(m.ActivityLog.user_id == user_pk).one()
        assert STUDENT_NAME not in log.description and log.details is None
        event = s.query(m.AuditLog).filter(m.AuditLog.organization_id == org_id,
                                           m.AuditLog.action == "privacy.student_erasure").one()
        event_text = json.dumps(event.after, ensure_ascii=False)
        for personal in (STUDENT_NAME, STUDENT_EMAIL, code):
            assert personal not in event_text  # the audit trail keeps counts, not personal data

    # the erased identity can no longer authenticate or be looked up by its old code
    with pytest.raises(dl.StudentNotFound):
        dl.export_student_data(org_id, code)


@requires_pg
def test_erasure_is_confined_to_one_tenant():
    from dss.db import models as m
    from dss.db.session import session_scope

    org_a, code_a, _, _ = _seed("LC_TENANT_A")
    org_b, _, student_b, _ = _seed("LC_TENANT_B")
    with pytest.raises(dl.StudentNotFound):
        dl.erase_student_data(org_b, code_a, requested_by="attacker")   # A's student via B's tenant
    dl.erase_student_data(org_a, code_a, requested_by="dpo")
    with session_scope() as s:
        assert s.get(m.Student, student_b).full_name == STUDENT_NAME
        assert s.query(m.Consultation).filter(m.Consultation.student_id == student_b).count() == 1


@requires_pg
def test_purge_expired_respects_retention_and_never_touches_academic_records(monkeypatch):
    from dss.db import models as m
    from dss.db.session import session_scope

    org_id, _, student_pk, _ = _seed("LC_PURGE")
    future = datetime.now(timezone.utc) + timedelta(days=366)
    purged = dl.purge_expired(org_id, now=future)
    assert purged["consultations"] == 1 and purged["recommendations"] == 1
    with session_scope() as s:
        assert s.query(m.AcademicRecord).filter(m.AcademicRecord.student_id == student_pk).count() == 1
        assert s.query(m.ActivityLog).filter(m.ActivityLog.organization_id == org_id).count() == 1  # audit: 1825 days
