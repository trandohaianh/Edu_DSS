"""Khôi phục volume appdata từ một bản sao lưu tệp hằng ngày (bước 9, 22/11/2026).

    python -m ops.restore_appdata <thư mục files của ngày> [--replace]

Bản sao lưu do `python -m ops.pipeline run backup` tạo: `<files>/<giờ>/data_root.tar.gz` + `manifest.json`
(SHA-256 của bản nén và của từng tệp). Lệnh này:
  1. kiểm SHA-256 của bản nén trước khi đụng vào dữ liệu;
  2. từ chối ghi vào thư mục dữ liệu đang có tệp, trừ khi có --replace (khi đó xoá nội dung cũ trước);
  3. giải nén vào thư mục tạm cạnh thư mục dữ liệu, chép sang, rồi kiểm lại SHA-256 từng tệp đã khôi phục.
Exit khác 0 = khôi phục không đầy đủ; không bật lại app khi lệnh này lỗi.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ops.backup_recovery import checksum  # noqa: E402

# Thư mục/tệp do app tự tạo lại khi chạy, không có trong bản sao lưu (ops/pipeline.py: _BACKUP_EXCLUDE_DIRS).
_RUNTIME_ONLY = {"logs", "locks", "security"}


class RestoreError(RuntimeError):
    pass


def _find_backup(files_dir: Path) -> tuple[Path, dict]:
    manifests = sorted(files_dir.glob("*/manifest.json"))
    if len(manifests) != 1:
        raise RestoreError(f"cần đúng một bản sao lưu tệp trong {files_dir}, tìm thấy {len(manifests)}")
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    archive = manifests[0].parent / manifest["archive"]
    if not archive.is_file() or archive.is_symlink():
        raise RestoreError("thiếu bản nén data_root.tar.gz")
    if checksum(archive) != manifest["archive_sha256"]:
        raise RestoreError("SHA-256 của bản nén không khớp manifest — bản sao lưu hỏng")
    return archive, manifest


def _has_user_data(root: Path) -> bool:
    return any(p.name not in _RUNTIME_ONLY for p in root.iterdir()) if root.exists() else False


def restore(files_dir: Path, data_root: Path, replace: bool = False) -> dict:
    archive, manifest = _find_backup(files_dir)
    data_root.mkdir(parents=True, exist_ok=True)
    if _has_user_data(data_root):
        if not replace:
            raise RestoreError(f"{data_root} đang có dữ liệu; thêm --replace để xoá và thay bằng bản sao lưu")
        for child in data_root.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=data_root.parent) as scratch:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(scratch, filter="data")
        shutil.copytree(Path(scratch) / "data_root", data_root, dirs_exist_ok=True)
    missing, mismatched = [], []
    for name, digest in manifest["files"].items():
        path = data_root / Path(name).relative_to("data_root")
        if not path.is_file():
            missing.append(name)
        elif checksum(path) != digest:
            mismatched.append(name)
    result = {
        "event": "appdata_restored" if not missing and not mismatched else "appdata_restore_incomplete",
        "backup_id": manifest.get("backup_id"),
        "files": len(manifest["files"]),
        "missing": missing,
        "mismatches": mismatched,
    }
    if missing or mismatched:
        raise RestoreError(json.dumps(result, ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files_dir", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--data-root", type=Path, default=Path(os.environ.get("EDUDSS_DATA_ROOT", "/app/data_warehouse")))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(restore(args.files_dir, args.data_root, args.replace), ensure_ascii=False))
    except (RestoreError, OSError, KeyError, ValueError, tarfile.TarError) as exc:
        print(json.dumps({"event": "appdata_restore_failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
