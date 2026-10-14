"""C1.1 — keyed tenant-scoped pseudonyms; external AI payload minimization."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from dss.security import pseudonymization as pz
from dss.services import privacy_service

KEY_A = "a" * 64          # 32 bytes hex — test-only values, never real keys
KEY_B = "b" * 64


@pytest.fixture
def keyed(monkeypatch):
    for name in ("EDUDSS_ENV", "EDUDSS_MODE", "EDUDSS_PSEUDONYM_KEY", "EDUDSS_PSEUDONYM_KEY_VERSION",
                 "EDUDSS_ORGANIZATION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EDUDSS_PSEUDONYM_KEY", KEY_A)
    pz.reset_cache_for_tests()
    yield monkeypatch
    pz.reset_cache_for_tests()


# ---------------------------------------------------------------- pseudonyms
def test_same_tenant_same_student_is_stable(keyed):
    assert pz.pseudonymize("SV001", organization_id=1) == pz.pseudonymize("sv001 ", organization_id=1)


def test_different_students_differ(keyed):
    assert pz.pseudonymize("SV001", organization_id=1) != pz.pseudonymize("SV002", organization_id=1)


def test_different_tenants_differ(keyed):
    assert pz.pseudonymize("SV001", organization_id=1) != pz.pseudonymize("SV001", organization_id=2)


def test_tenant_comes_from_deployment_when_not_given(keyed):
    keyed.setenv("EDUDSS_ORGANIZATION_ID", "7")
    assert pz.pseudonymize("SV001") == pz.pseudonymize("SV001", organization_id=7)


def test_different_key_or_version_changes_pseudonym(keyed):
    a = pz.pseudonymize("SV001", organization_id=1)
    keyed.setenv("EDUDSS_PSEUDONYM_KEY", KEY_B)
    assert pz.pseudonymize("SV001", organization_id=1) != a
    keyed.setenv("EDUDSS_PSEUDONYM_KEY", KEY_A)
    keyed.setenv("EDUDSS_PSEUDONYM_KEY_VERSION", "2")
    assert pz.pseudonymize("SV001", organization_id=1) != a


def test_output_length_and_alphabet(keyed):
    p = pz.pseudonymize("SV001", organization_id=1)
    assert p.startswith("Student_") and re.fullmatch(r"Student_[A-Z2-7]{20}", p)  # 100 bits


def test_no_collisions_across_a_large_cohort(keyed):
    values = {pz.pseudonymize(f"SV{i:06d}", organization_id=1) for i in range(20_000)}
    assert len(values) == 20_000


def test_cannot_be_reproduced_without_the_key(keyed):
    """The old scheme was sha256(<public salt>:id)[:6] — anyone could enumerate it."""
    import hashlib
    p = pz.pseudonymize("SV001", organization_id=1)
    legacy_like = hashlib.sha256(b"SV001").hexdigest()[:20].upper()
    assert legacy_like not in p


@pytest.mark.parametrize("prod", [{"EDUDSS_ENV": "production"}, {"EDUDSS_MODE": "REAL_LMS"}])
def test_missing_key_in_production_fails_closed(keyed, prod):
    keyed.delenv("EDUDSS_PSEUDONYM_KEY")
    for k, v in prod.items():
        keyed.setenv(k, v)
    with pytest.raises(pz.PseudonymKeyMissing):
        pz.pseudonymize("SV001", organization_id=1)
    from dss.core.health_diagnostics import readiness
    r = readiness()
    assert r["checks"]["privacy_key"] == {"status": "not_configured", "required": True}
    assert r["status"] == "not_ready"


def test_short_key_rejected(keyed):
    keyed.setenv("EDUDSS_PSEUDONYM_KEY", "too-short")
    with pytest.raises(pz.PseudonymKeyMissing):
        pz.pseudonymize("SV001", organization_id=1)


def test_development_key_is_generated_outside_source_and_stable(keyed):
    keyed.delenv("EDUDSS_PSEUDONYM_KEY")
    pz.reset_cache_for_tests()
    first = pz.pseudonymize("SV001", organization_id=1)
    pz.reset_cache_for_tests()
    assert pz.pseudonymize("SV001", organization_id=1) == first  # persisted, not per-process random
    from dss.core.data_root import get_data_root
    assert (get_data_root() / "security" / "pseudonym_dev.key").exists()


def test_no_constant_salt_left_in_source():
    root = Path(__file__).resolve().parents[1] / "dss"
    hits = [str(p) for p in root.rglob("*.py") if "edudss_privacy_salt" in p.read_text(encoding="utf-8")]
    assert hits == []


def test_key_is_never_logged(keyed, caplog):
    caplog.set_level(logging.DEBUG)
    pz.pseudonymize("SV001", organization_id=1)
    from dss.core.health_diagnostics import readiness
    output = str(readiness())
    assert KEY_A not in caplog.text and KEY_A not in output


def test_privacy_service_delegates_to_keyed_scheme(keyed):
    assert privacy_service.generate_pseudonym("SV001", organization_id=1) == pz.pseudonymize("SV001", organization_id=1)
    # the legacy `salt` argument no longer changes the output (a public salt is not a secret)
    assert privacy_service.generate_pseudonym("SV001", salt="anything", organization_id=1) == pz.pseudonymize("SV001", organization_id=1)


# ---------------------------------------------------------------- provider payload
PII_PROFILE = {
    "risk_level": "cao",
    "attendance_rate": 0.8734,
    "progress_note": "Tên em là Nguyễn Văn An, MSSV 20210045, email an.nguyen@uni.edu.vn, SĐT 0912345678",
    "full_name": "Nguyễn Văn An",
    "email": "an.nguyen@uni.edu.vn",
    "phone": "0912345678",
    "address": "12 Lê Lợi, Quận 1",
}
FORBIDDEN = ["Nguyễn Văn An", "20210045", "an.nguyen@uni.edu.vn", "0912345678", "12 Lê Lợi", "SV20210045"]


def test_student_context_leaves_no_direct_identifier(keyed):
    context, audit = privacy_service.build_anonymized_student_context(
        "SV20210045", 7.34, ["**Thống kê** (SV: **6.20**, TB lớp: **7.10**)", "Liên hệ an.nguyen@uni.edu.vn"], PII_PROFILE)
    for value in FORBIDDEN:
        assert value not in context
    pseudonym = privacy_service.generate_pseudonym("SV20210045")
    assert pseudonym not in context            # no identifier of any kind leaves the boundary
    assert audit["pseudonym"] == pseudonym     # ...it stays in the internal audit record only
    assert "7.34" not in context and "~7.3" not in context and "~" not in context  # no exact / approximate GPA
    assert "6.20" not in context and "7.10" not in context                          # no exact subject scores
    assert "Khá (7.0 <= GPA < 8.5)" in context
    assert "87" not in context and "trung bình (75-90%)" in context                  # attendance bracketed
    assert audit["has_exact_gpa"] is False and audit["has_identifier"] is False


def test_missing_prediction_is_not_reported_as_low_gpa(keyed):
    context, _ = privacy_service.build_anonymized_student_context("SV1", None, [], {})
    assert "Chưa có dự đoán" in context and "Cần cải thiện" not in context


def test_quick_question_prompt_is_minimized(keyed):
    prompt = privacy_service.build_quick_question_prompt(
        "cao", 6.87, "Thống kê", "Em là Nguyễn Văn An MSSV 20210045, email an.nguyen@uni.edu.vn, nên học gì?")
    for value in ("20210045", "an.nguyen@uni.edu.vn", "6.87"):
        assert value not in prompt
    assert "Trung bình (5.5 <= GPA < 7.0)" in prompt


def test_home_quick_ask_no_longer_embeds_raw_student_id():
    source = (Path(__file__).resolve().parents[1] / "dss" / "tabs" / "home.py").read_text(encoding="utf-8")
    assert "trợ lý học tập AI cho sinh viên {current_student_id}" not in source
    assert "build_quick_question_prompt" in source


def test_career_context_has_no_identifier_or_exact_scores(keyed):
    from dss.services.career_ai_advisor import build_career_ai_context
    from dss.services.career_knowledge_base import list_roles
    from dss.services.career_scoring import rank_careers
    import tests.test_career_advisor as career_tests
    profile = career_tests._profile_with_scores(diem_thong_ke=8.37, diem_xu_ly_du_lieu=6.12)
    context = build_career_ai_context(profile, rank_careers(profile, list_roles(), top_k=3))
    assert str(profile.student_pseudonym) not in context
    assert "8.37" not in context and "6.12" not in context
    assert f"{profile.academic.gpa:.2f}/10" not in context


def test_agent_context_builder_drops_direct_identifiers():
    from dss.services.context_builder import build_context
    result = build_context("ADVISOR_PLAN", {"authorized_academic_summary": "x", "student_id": "SV001",
                                            "student_code": "SV001", "email": "a@b.c", "name": "A"})
    assert not ({"student_id", "student_code", "email", "name"} & set(result.context))
