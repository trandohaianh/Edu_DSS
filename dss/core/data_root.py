"""Bộ phân giải TRUNG TÂM cho thư mục dữ liệu có thể ghi của ứng dụng (PERF-002).

Trước bản vá này, gần như mọi service/repository tự tính đường dẫn của riêng
nó bằng `Path(__file__).resolve().parent.parent.parent / "data_warehouse"`
(hoặc một chuỗi tương đối `'data_warehouse'` phụ thuộc CWD tiến trình) — nghĩa
là KHÔNG có cách nào để test/E2E trỏ ứng dụng sang một thư mục dữ liệu khác,
mọi lần chạy test đều ghi thẳng vào kho dữ liệu thật của app đang chạy dev.
Đây là nguyên nhân gốc của PERF-002 (743 bản ghi bài giảng test tích lũy lại
trong data_warehouse/cms/lessons_registry.json).

Cách dùng: mọi module có trạng thái ghi-được (CMS, quiz queue, interaction
log, users.json, token usage, subscription, vector store, DataWarehouse...)
phải gọi `get_data_root()` MỖI LẦN cần đường dẫn (không lưu thành hằng số ở
mức module — hằng số mức module bị tính một lần lúc import, trước khi test
kịp set biến môi trường bên dưới), để việc set `EDUDSS_DATA_ROOT` luôn được
tôn trọng bất kể thứ tự import.

- Runtime BÌNH THƯỜNG (dev/production): không set EDUDSS_DATA_ROOT -> trả về
  <project_root>/data_warehouse, giống hệt hành vi mặc định trước đây (không
  đổi behavior cho người dùng thật).
- Runtime TEST/SIMULATION: test set EDUDSS_DATA_ROOT trỏ tới một thư mục tạm
  cô lập (vd. tempfile.mkdtemp()) TRƯỚC khi bất kỳ store nào được đọc/ghi ->
  toàn bộ dữ liệu test (CMS, dataset, model, log...) nằm gọn trong đó, không
  bao giờ chạm vào data_warehouse/ thật.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Tên biến môi trường mà test/E2E dùng để trỏ sang thư mục dữ liệu cô lập.
# Đặt TRƯỚC khi tiến trình Streamlit/pytest chạm vào bất kỳ store nào.
DATA_ROOT_ENV_VAR = "EDUDSS_DATA_ROOT"


def get_data_root() -> Path:
    """Thư mục gốc dữ liệu có thể ghi hiện tại của tiến trình. Luôn tính lại
    từ biến môi trường (không cache) để tôn trọng việc set muộn trong test."""
    override = os.environ.get(DATA_ROOT_ENV_VAR)
    if override:
        return Path(override)
    return _PROJECT_ROOT / "data_warehouse"


def is_isolated_test_environment() -> bool:
    """True khi tiến trình hiện tại đang chạy với một data root cô lập (test/
    simulation), tức KHÔNG được ghi vào data_warehouse/ thật của ứng dụng."""
    return bool(os.environ.get(DATA_ROOT_ENV_VAR))
