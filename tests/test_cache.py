"""Regression suite — Cache Streamlit (Phase 8).

Xác nhận đúng những gì Phase 8 đã sửa: `init_trainers_and_warehouse()` là
singleton thật (không tạo lại Trainer/DataWarehouse mỗi lần rerun), và
`load_data`/`to_excel` có decorator cache thật (không chỉ ghi trong docstring
như tình trạng phát hiện lúc audit — xem PR Phase 8).
"""

from __future__ import annotations

import pandas as pd

from dss.core.data_helpers import load_data
from dss.core.feature_utils import to_excel
from dss.core.init_app import init_trainers_and_warehouse


def test_init_trainers_and_warehouse_is_a_singleton():
    """Gọi 2 lần liên tiếp (mô phỏng 2 lượt rerun Streamlit) phải trả về ĐÚNG
    cùng 1 object — không dựng lại ClassificationTrainer/RegressionTrainer/
    DataWarehouse mới mỗi lần, đúng bug đã sửa ở Phase 8."""
    clf1, reg1, llm1, wh1 = init_trainers_and_warehouse()
    clf2, reg2, llm2, wh2 = init_trainers_and_warehouse()
    assert clf1 is clf2
    assert reg1 is reg2
    assert llm1 is llm2
    assert wh1 is wh2


def test_init_trainers_and_warehouse_has_cache_resource_decorator():
    """Có `.clear()` là dấu hiệu đặc trưng của hàm được bọc `@st.cache_resource`
    (hàm thường không có phương thức này) — xác nhận decorator thật sự tồn tại,
    không phải "trông giống cache" nhờ trùng hợp identity ở test trên."""
    assert hasattr(init_trainers_and_warehouse, "clear")


def test_load_data_has_cache_data_decorator():
    """Trước Phase 8: docstring ghi 'dùng @st.cache_data' nhưng decorator thật
    không tồn tại — kiểm tra để không regress về tình trạng đó."""
    assert hasattr(load_data, "clear")


def test_to_excel_has_cache_data_decorator():
    assert hasattr(to_excel, "clear")


def test_to_excel_produces_valid_xlsx_bytes():
    """Kiểm tra hành vi thật (không chỉ decorator) — cache không được làm hỏng
    kết quả trả về."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    result = to_excel(df)
    assert isinstance(result, (bytes, bytearray))
    assert len(result) > 0
    assert result[:2] == b"PK"  # .xlsx là file zip — luôn bắt đầu bằng "PK"
