"""C-1: Phân cụm mặc định chọn nhầm cột — bộ từ khóa cũ (['score','gpa','hours',
'point','mark','grade'], chỉ tiếng Anh) trên dữ liệu mẫu CHỈ khớp 'final_score'
(chính là bí danh của target diem_ky_sau!) và 'gpa_previous', bỏ sót toàn bộ
diem_*/ty_le_*/so_gio_* — vừa rò rỉ target vào phân cụm, vừa bỏ sót phần lớn
đặc trưng có ý nghĩa."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dss.core.data_helpers import generate_data
from dss.core.target_utils import get_leaky_target_columns
from dss.services.clustering_service import select_default_cluster_features


def _forbidden_target_alias_cols():
    forbidden = {"final_score", "grade", "diem_ky_sau", "xep_loai"}
    for target in ("diem_ky_sau", "xep_loai"):
        forbidden.update(c.lower() for c in get_leaky_target_columns(target))
    return forbidden


def test_default_cluster_features_exclude_target_aliases():
    df = generate_data()
    cols = select_default_cluster_features(df)
    forbidden = _forbidden_target_alias_cols()
    leaked = [c for c in cols if c.lower() in forbidden]
    assert not leaked, f"Cột bí danh/target lọt vào phân cụm mặc định: {leaked}"


def test_default_cluster_features_include_vietnamese_named_columns():
    df = generate_data()
    cols = select_default_cluster_features(df)
    assert any(c.startswith("ty_le_diem_danh") for c in cols), cols
    assert any(c.startswith("so_gio_hoc_tuan") for c in cols), cols
    assert any(c.startswith("diem_") for c in cols), cols


def test_default_cluster_features_drop_near_duplicate_columns():
    df = generate_data()
    cols = select_default_cluster_features(df)
    # gpa_previous = diem_ky_nay / 2.5 -> tương quan gần như tuyệt đối, KHÔNG
    # được giữ cả 2 nếu diem_ky_nay đã được chọn.
    assert not ("diem_ky_nay" in cols and "gpa_previous" in cols), cols
