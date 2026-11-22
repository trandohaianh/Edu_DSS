"""Chuyển dữ liệu cũ từ các kho tệp trong volume appdata sang PostgreSQL (bước 9, 22/11/2026).

    python -m ops.migrate_file_stores            # chỉ ĐẾM, không ghi gì
    python -m ops.migrate_file_stores --execute  # ghi vào PostgreSQL

Chạy MỘT lần trong container app, sau khi deploy bản có các biến EDUDSS_*_STORE=postgres, và trước khi người dùng
quay lại. Lệnh:
  - chạy lại được nhiều lần, không tạo bản trùng (dò theo mã bản ghi cũ);
  - KHÔNG xoá tệp cũ: muốn quay lại thì đặt biến về `local`, dữ liệu tệp vẫn còn nguyên;
  - chỉ chuyển kho đang bật postgres; kho chưa bật thì báo "skipped".
Thiết kế: docs/architecture/STEP9_FILE_STORES_TO_POSTGRES.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _history_count(warehouse, kind: str) -> int:
    return len(warehouse.read_history_file(kind, limit=10_000_000))


def _admin_ai_config(org: int, execute: bool, root: Path, warehouse) -> dict:
    from dss.db.repositories import admin_ai_config_repository

    data = _read_json(root / "ai_default_provider.json")
    local = 1 if isinstance(data, dict) and data.get("provider_key") and data.get("model_name") else 0
    existing = admin_ai_config_repository.get_config(org)
    result = {"local_records": local, "already_in_postgres": int(existing is not None)}
    if execute and local and existing is None:
        admin_ai_config_repository.set_config(org, data["provider_key"], data["model_name"])
        result["imported"] = 1
    return result


def _subscription(org: int, execute: bool, root: Path, warehouse) -> dict:
    from dss.db.models import Subscription
    from dss.db.repositories import subscription_repository
    from dss.db.session import tenant_session_scope

    data = _read_json(root / "subscription.json")
    local = 1 if isinstance(data, dict) else 0
    with tenant_session_scope(org) as session:
        existing = session.query(Subscription).filter_by(organization_id=org).one_or_none() is not None
    result = {"local_records": local, "already_in_postgres": int(existing)}
    if execute and local and not existing:
        subscription_repository.get_or_create_subscription(org, defaults=data)
        result["imported"] = 1
    return result


def _history(kind: str, module: str) -> Callable:
    def run(org: int, execute: bool, root: Path, warehouse) -> dict:
        result = {"local_records": _history_count(warehouse, kind)}
        if execute:
            repo = __import__(f"dss.db.repositories.{module}", fromlist=["x"])
            result.update(repo.import_from_local_history(org, warehouse=warehouse))
        return result

    return run


def _ai_token_usage(org: int, execute: bool, root: Path, warehouse) -> dict:
    from dss.db.models import AiTokenUsage
    from dss.db.repositories import ai_token_usage_repository
    from dss.db.session import tenant_session_scope

    records = _read_json(root / "ai_token_usage.json")
    records = records if isinstance(records, list) else []
    result = {"local_records": len(records)}
    if not execute:
        return result
    with tenant_session_scope(org) as session:
        existing = {u for (u,) in session.query(AiTokenUsage.usage_id).filter_by(organization_id=org)}
    imported = 0
    for rec in records:
        if not isinstance(rec, dict) or not rec.get("usage_id") or rec["usage_id"] in existing:
            continue
        ai_token_usage_repository.record_usage(org, rec)
        existing.add(rec["usage_id"])
        imported += 1
    result.update(imported=imported, skipped_already_imported=len(records) - imported)
    return result


STORES: dict[str, tuple[str, Callable]] = {
    "admin_ai_config": ("ADMIN_AI_CONFIG", _admin_ai_config),
    "subscription": ("SUBSCRIPTION", _subscription),
    "activity": ("ACTIVITY", _history("activity", "activity_log_repository")),
    "predictions": ("PREDICTIONS", _history("prediction", "prediction_repository")),
    "consultations": ("CONSULTATIONS", _history("advisor", "consultation_repository")),
    "ai_token_usage": ("AI_TOKEN_USAGE", _ai_token_usage),
}


def migrate(execute: bool = False) -> dict[str, dict]:
    from dss.core.data_root import get_data_root
    from dss.core.persistence_config import is_postgres_enabled
    from dss.core.warehouse import DataWarehouse, _current_organization_id

    root = get_data_root()
    warehouse = DataWarehouse()
    org = _current_organization_id()
    report: dict[str, dict] = {}
    for name, (feature, run) in STORES.items():
        if not is_postgres_enabled(feature):
            report[name] = {"status": "skipped", "reason": f"EDUDSS_{feature}_STORE is not postgres"}
            continue
        report[name] = {"status": "imported" if execute else "dry_run", **run(org, execute, root, warehouse)}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="ghi vào PostgreSQL (mặc định chỉ đếm)")
    args = parser.parse_args(argv)
    print(json.dumps({"event": "file_stores_migration", "execute": args.execute, "stores": migrate(args.execute)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
