"""FINAL PRODUCTION GAP CLOSURE — Phần 9: Regulation Resolver. Trước khi
xây, `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (Q7-Q10) đã xác nhận
NOT_IMPLEMENTED — không có mô hình University→Program→Cohort→Regulation
Version, không có `resolve_regulation()`. Test dưới đây đúng theo yêu cầu
Phần 9: đúng trường, đúng ngành, đúng khóa, đúng thời gian, expired version,
future version, missing version, cross-tenant."""

from __future__ import annotations

from dss.services.regulation_resolver import RegulationVersion, resolve_regulation


def _reg(**overrides):
    defaults = dict(
        regulation_id="reg_default",
        organization_id="uni_a",
        program_id="cntt",
        cohort="k2022",
        version=1,
        effective_from="2022-09-01",
        effective_to=None,
        status="APPROVED",
        approved_by="admin_1",
        source_document_id="doc_001",
        rules={},
    )
    defaults.update(overrides)
    return RegulationVersion(**defaults)


def test_resolves_correct_org_program_cohort():
    """Đúng trường (org), đúng ngành (program), đúng khóa (cohort)."""
    target = _reg(regulation_id="target")
    noise = [
        _reg(regulation_id="wrong_org", organization_id="uni_b"),
        _reg(regulation_id="wrong_program", program_id="dtvt"),
        _reg(regulation_id="wrong_cohort", cohort="k2023"),
    ]
    result = resolve_regulation(
        [target] + noise,
        organization_id="uni_a",
        program_id="cntt",
        cohort="k2022",
        at_date="2023-01-01",
    )
    assert result.status == "ok"
    assert result.regulation.regulation_id == "target"


def test_resolves_correct_effective_date_window():
    """Đúng thời gian: at_date nằm giữa effective_from/effective_to."""
    reg = _reg(effective_from="2022-09-01", effective_to="2026-08-31")
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2024-06-15")
    assert result.status == "ok"
    assert result.regulation.regulation_id == "reg_default"


def test_expired_version_not_returned():
    """expired version: effective_to đã qua -> KHÔNG được trả về."""
    reg = _reg(effective_from="2018-09-01", effective_to="2022-08-31")
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2024-01-01")
    assert result.status == "EXPIRED_ONLY"
    assert result.regulation is None


def test_future_version_not_returned():
    """future version: effective_from còn ở tương lai -> KHÔNG được trả về."""
    reg = _reg(effective_from="2030-09-01", effective_to=None)
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2024-01-01")
    assert result.status == "FUTURE_ONLY"
    assert result.regulation is None


def test_missing_version_returns_not_found_not_error():
    """missing version: không có quy chế nào cho program/cohort -> NOT_FOUND,
    KHÔNG raise, KHÔNG bịa quy chế mặc định nào."""
    result = resolve_regulation([], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2024-01-01")
    assert result.status == "NOT_FOUND"
    assert result.regulation is None


def test_cross_tenant_regulation_never_leaks():
    """cross-tenant: quy chế của uni_b (dù program/cohort/thời gian khớp
    tuyệt đối) TUYỆT ĐỐI không được trả về khi resolve cho uni_a."""
    other_tenant_reg = _reg(regulation_id="uni_b_reg", organization_id="uni_b")
    result = resolve_regulation(
        [other_tenant_reg],
        organization_id="uni_a",
        program_id="cntt",
        cohort="k2022",
        at_date="2023-01-01",
    )
    assert result.status == "NOT_FOUND"
    assert result.regulation is None
    assert result.candidates_considered == 0, "Không được đếm/xét candidate của tenant khác."


def test_pending_review_regulation_not_applied():
    """Quy chế PENDING_REVIEW (chưa duyệt) KHÔNG được coi là áp dụng được,
    giống nguyên tắc document_governance.py."""
    reg = _reg(status="PENDING_REVIEW")
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2023-01-01")
    assert result.status == "PENDING_ONLY"
    assert result.regulation is None


def test_retired_regulation_not_applied():
    reg = _reg(status="RETIRED")
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2023-01-01")
    assert result.status == "PENDING_ONLY"  # nhóm chung "không có bản APPROVED nào"
    assert result.regulation is None


def test_multiple_matching_versions_picks_highest_version():
    v1 = _reg(regulation_id="v1", version=1, effective_from="2020-01-01")
    v2 = _reg(regulation_id="v2", version=2, effective_from="2020-01-01")
    result = resolve_regulation(
        [v1, v2], organization_id="uni_a", program_id="cntt", cohort="k2022", at_date="2023-01-01"
    )
    assert result.status == "ok"
    assert result.regulation.regulation_id == "v2"


def test_at_date_defaults_to_today_when_not_provided():
    reg = _reg(effective_from="2020-01-01", effective_to=None)
    result = resolve_regulation([reg], organization_id="uni_a", program_id="cntt", cohort="k2022")
    assert result.status == "ok"
