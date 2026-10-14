"""Regulation Store — lưu trữ `RegulationVersion` cục bộ (JSON), CÙNG MẪU
với `LocalVectorStore` (`dss/services/vector_store.py`) — dùng cho môi
trường dev/demo không cần Postgres. Backend Postgres thật (bảng
`regulation_versions` + migration Alembic + RLS theo organization_id) LÀ
CÔNG VIỆC CHƯA LÀM trong đợt "FINAL PRODUCTION GAP CLOSURE" này — không thể
runtime-verify migration mới trên DB thật (BLOCKED_BY_RUNNING_SIMULATION),
nên KHÔNG viết migration chưa kiểm chứng được. Interface (`list_regulations`/
`upsert_regulation`) được thiết kế để dễ thay bằng 1 lớp Postgres-backed
sau này mà không đổi `regulation_resolver.py` (hàm resolve THUẦN không phụ
thuộc backend lưu trữ nào).

Không có UI (`st.*`) ở đây — hàm thuần, gọi được trực tiếp từ test."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from dss.core.data_root import get_data_root
from dss.services.regulation_resolver import RegulationVersion

_lock = threading.Lock()


def _store_path() -> Path:
    # PERF-002 (cùng quy ước LocalVectorStore): gọi get_data_root() MỖI LẦN
    # cần đường dẫn, không cache mức module — tôn trọng EDUDSS_DATA_ROOT do
    # test set trước khi store đầu tiên được dùng trong tiến trình.
    p = get_data_root() / "regulations"
    p.mkdir(parents=True, exist_ok=True)
    return p / "regulation_versions.json"


def _load_all() -> List[RegulationVersion]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [RegulationVersion(**item) for item in raw]
    except Exception:
        return []


def _save_all(items: List[RegulationVersion]) -> None:
    path = _store_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump([asdict(item) for item in items], f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def list_regulations(organization_id: Optional[str] = None) -> List[RegulationVersion]:
    """Trả về toàn bộ quy chế đã lưu — lọc theo `organization_id` nếu truyền
    vào (fail-closed: không lọc gì thì trả TẤT CẢ, nơi gọi phải tự truyền
    đúng organization_id, không dựa vào store tự lọc mặc định)."""
    with _lock:
        items = _load_all()
    if organization_id is not None:
        items = [i for i in items if i.organization_id == organization_id]
    return items


def upsert_regulation(regulation: RegulationVersion) -> None:
    """Thêm mới hoặc THAY THẾ 1 bản quy chế theo `regulation_id` (idempotent
    theo id, giống cách `legacy_knowledge_seed.py` idempotent theo
    document_id). KHÔNG có đường nào tự ý set status=APPROVED — nơi gọi
    (Admin workflow, chưa xây UI trong đợt này) phải tự truyền đúng status."""
    with _lock:
        items = _load_all()
        items = [i for i in items if i.regulation_id != regulation.regulation_id]
        items.append(regulation)
        _save_all(items)


def delete_regulation(regulation_id: str) -> bool:
    with _lock:
        items = _load_all()
        remaining = [i for i in items if i.regulation_id != regulation_id]
        if len(remaining) == len(items):
            return False
        _save_all(remaining)
        return True
