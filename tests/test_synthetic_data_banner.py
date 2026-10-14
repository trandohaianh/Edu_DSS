"""E-1: khi dữ liệu đang dùng là MÔ PHỎNG (Synthetic/Demo, generate_data()),
Dashboard/Phân cụm/Tư vấn AI (Huấn luyện đã có sẵn ở ml_hub.py) phải hiển thị
rõ nhãn "Dữ liệu mô phỏng" — trước khi sửa, các trang này không hề đọc
df.attrs['data_source_type'] nên không hiển thị gì."""
from __future__ import annotations

import inspect

import pandas as pd

from dss.core.data_helpers import generate_data, is_synthetic_data
from dss.tabs import ai_advisor, clustering, dashboard


def test_is_synthetic_data_true_for_generate_data():
    df = generate_data()
    assert is_synthetic_data(df) is True


def test_is_synthetic_data_false_when_marked_real():
    df = pd.DataFrame({"a": [1, 2, 3]})
    df.attrs["data_source_type"] = "real_lms"
    assert is_synthetic_data(df) is False


def test_dashboard_tab_shows_synthetic_banner():
    source = inspect.getsource(dashboard.main_dashboard_tab)
    assert "render_synthetic_data_banner(df)" in source


def test_clustering_tab_shows_synthetic_banner():
    source = inspect.getsource(clustering.clustering_hybrid_tab)
    assert "render_synthetic_data_banner(df)" in source


def test_ai_advisor_tab_shows_synthetic_banner():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "render_synthetic_data_banner(df)" in source
