"""G-2: gpa_previous = diem_ky_nay / 2.5 (tương quan ~0.99999) được giữ trong
LEGITIMATE_PREDICTORS nên KHÔNG bị coi là rò rỉ dữ liệu với TARGET — nhưng khi
tạo danh sách FEATURE MẶC ĐỊNH, cả 2 cột gần như trùng lặp này vẫn cùng lọt vào
(chúng chỉ trùng lặp VỚI NHAU, không phải với target), gây dư thừa/đa cộng
tuyến không cần thiết. Không xóa khỏi LEGITIMATE_PREDICTORS — người dùng vẫn
chọn tay được cả 2 nếu muốn."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.services.model_service import drop_near_duplicate_columns


def test_drop_near_duplicate_columns_keeps_first_drops_near_duplicate():
    df = generate_data()
    cols = ["diem_ky_nay", "gpa_previous", "diem_giua_ky"]
    kept, dropped = drop_near_duplicate_columns(df, cols)
    assert "diem_ky_nay" in kept
    assert "gpa_previous" not in kept
    assert "gpa_previous" in dropped
    assert "diem_giua_ky" in kept


def test_bootstrap_default_training_config_excludes_near_duplicate_feature():
    from dss.core.bootstrap_service import _detect_default_training_config

    df = generate_data()
    config = _detect_default_training_config(df)
    assert config is not None
    selected = config["selected_features"]
    assert not ("diem_ky_nay" in selected and "gpa_previous" in selected), (
        f"Cả diem_ky_nay và gpa_previous (gần như trùng lặp, r~0.9999) cùng lọt "
        f"vào danh sách feature mặc định: {selected}"
    )
