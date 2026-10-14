"""FINAL PRODUCTION GAP CLOSURE — Phần 9: LocalRegulationStore (lưu trữ JSON
cục bộ cho RegulationVersion, cùng mẫu LocalVectorStore)."""
from __future__ import annotations

import pytest

from dss.services.regulation_resolver import RegulationVersion


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    # regulation_store.py làm `from dss.core.data_root import get_data_root`
    # (tên đã bind vào namespace riêng của module) — phải patch ĐÚNG tên đó
    # trong module tiêu thụ, patch trên dss.core.data_root không có tác dụng.
    from dss.services import regulation_store
    monkeypatch.setattr(regulation_store, "get_data_root", lambda: tmp_path)
    return tmp_path


def _reg(**overrides):
    defaults = dict(
        regulation_id="reg_001", organization_id="uni_a", program_id="cntt", cohort="k2022",
        version=1, effective_from="2022-09-01", effective_to=None, status="APPROVED",
        approved_by="admin_1", source_document_id="doc_001", rules={"min_gpa_graduation": 2.0},
    )
    defaults.update(overrides)
    return RegulationVersion(**defaults)


def test_upsert_and_list_roundtrip():
    from dss.services import regulation_store as store
    store.upsert_regulation(_reg())
    items = store.list_regulations()
    assert len(items) == 1
    assert items[0].regulation_id == "reg_001"
    assert items[0].rules == {"min_gpa_graduation": 2.0}


def test_upsert_is_idempotent_by_regulation_id():
    from dss.services import regulation_store as store
    store.upsert_regulation(_reg(version=1))
    store.upsert_regulation(_reg(version=2))  # cùng regulation_id -> thay thế, không nhân đôi
    items = store.list_regulations()
    assert len(items) == 1
    assert items[0].version == 2


def test_list_filters_by_organization_id():
    from dss.services import regulation_store as store
    store.upsert_regulation(_reg(regulation_id="a", organization_id="uni_a"))
    store.upsert_regulation(_reg(regulation_id="b", organization_id="uni_b"))
    items = store.list_regulations(organization_id="uni_a")
    assert [i.regulation_id for i in items] == ["a"]


def test_delete_regulation():
    from dss.services import regulation_store as store
    store.upsert_regulation(_reg())
    assert store.delete_regulation("reg_001") is True
    assert store.list_regulations() == []
    assert store.delete_regulation("reg_001") is False
