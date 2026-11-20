"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 9-10: Regulation Resolver
phải THẬT SỰ chặn LLM tự đoán quy chế trong luồng chat, không chỉ tồn tại
như module cô lập (regulation_resolver.py đã có + test từ đợt trước)."""

from __future__ import annotations

import pytest

from dss.services import ai_router, regulation_store
from dss.services.regulation_resolver import STATUS_APPROVED, RegulationVersion


@pytest.fixture()
def isolated_data_root(tmp_path, monkeypatch):
    # regulation_store.py làm `from dss.core.data_root import get_data_root`
    # (tên đã bind vào namespace riêng của module) — phải patch ĐÚNG tên đó
    # trong module tiêu thụ (cùng quy ước với test_regulation_store.py).
    monkeypatch.setattr(regulation_store, "get_data_root", lambda: tmp_path)
    yield tmp_path


def test_no_mapping_returns_honest_reply_without_fabricating_org_scope():
    """Nơi gọi thật (ai_advisor.py) hiện KHÔNG có organization_id/program_id/
    cohort cho sinh viên -> PHẢI trả lời trung thực, KHÔNG được tự bịa giá
    trị để vẫn tra cứu 'như thật'."""
    reply = ai_router.build_regulation_lookup_reply("Quy chế nào đang áp dụng cho em?")
    assert "Phòng Đào tạo" in reply
    assert "chưa được ánh xạ" in reply


def test_full_scope_but_empty_store_returns_not_found_not_silence(isolated_data_root):
    """Có đủ 3 giá trị scope nhưng store rỗng (mặc định của mọi môi trường
    demo hiện tại — chưa từng upsert quy chế nào) -> PHẢI trả lời rõ KHÔNG
    tìm thấy, không phải im lặng/crash."""
    reply = ai_router.build_regulation_lookup_reply(
        "Quy chế nào đang áp dụng cho em?",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
    )
    assert "Không xác định được quy chế" in reply
    assert "Phòng Đào tạo" in reply


def test_full_scope_with_real_approved_regulation_returns_resolver_result(isolated_data_root):
    """Khi có đủ scope THẬT và store có 1 bản APPROVED khớp -> câu trả lời
    phải phản ánh ĐÚNG kết quả từ resolve_regulation(), không phải LLM."""
    regulation_store.upsert_regulation(
        RegulationVersion(
            regulation_id="QC-CNTT-K66-V1",
            organization_id="org-1",
            program_id="cntt",
            cohort="k66",
            version=1,
            effective_from="2024-01-01",
            effective_to=None,
            status=STATUS_APPROVED,
            approved_by="admin",
            source_document_id=None,
        )
    )
    reply = ai_router.build_regulation_lookup_reply(
        "Quy chế nào đang áp dụng cho em?",
        organization_id="org-1",
        program_id="cntt",
        cohort="k66",
    )
    assert "QC-CNTT-K66-V1" in reply
    assert "version 1" in reply
    assert "không phải AI tự chọn" in reply


def test_cross_tenant_scope_never_leaks_other_org_regulation(isolated_data_root):
    """Quy chế của org-1 KHÔNG được lộ khi tra cứu cho org-2, dù program/
    cohort trùng tên — đúng nguyên tắc chống rò rỉ cross-tenant."""
    regulation_store.upsert_regulation(
        RegulationVersion(
            regulation_id="QC-ORG1",
            organization_id="org-1",
            program_id="cntt",
            cohort="k66",
            version=1,
            effective_from="2024-01-01",
            effective_to=None,
            status=STATUS_APPROVED,
            approved_by="admin",
            source_document_id=None,
        )
    )
    reply = ai_router.build_regulation_lookup_reply(
        "Quy chế nào đang áp dụng cho em?",
        organization_id="org-2",
        program_id="cntt",
        cohort="k66",
    )
    assert "QC-ORG1" not in reply
    assert "Không xác định được quy chế" in reply
