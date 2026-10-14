"""FINAL GAP CLOSURE — Câu 85 (D-1): confirm model_registry_tab() actually
calls run_on_demand_drift_check() — not just that the function exists in
isolation (source-inspection, same convention used elsewhere in this
session for Streamlit UI code hard to test via real widgets)."""
from __future__ import annotations

import inspect

from dss.tabs import warehouse_tab


def test_model_registry_tab_wires_drift_check_button():
    source = inspect.getsource(warehouse_tab.model_registry_tab)
    assert "model_registry.run_on_demand_drift_check(" in source
    assert "Chạy kiểm tra Drift" in source


def test_drift_ui_does_not_claim_continuous_monitoring():
    source = inspect.getsource(warehouse_tab.model_registry_tab)
    assert "không tuyên bố giám sát tự động liên tục" in source or "không phải giám sát tự động" in source
