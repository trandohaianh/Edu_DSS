"""C1.1 P0 — no personal-data exports in the release tree or Docker build context.

An unrelated employee export (name, national ID, phone, address, salary...)
was once shipped under `dữ liệu/`. These tests stop that class of file from
coming back: they look only at column HEADERS, never print row values.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", "tests"}

# Column names that identify a person directly or are sensitive HR fields.
PII_HEADER_TOKENS = {
    "name",
    "full name",
    "họ tên",
    "ho ten",
    "id card",
    "cccd",
    "cmnd",
    "national id",
    "passport",
    "phone",
    "sđt",
    "so dien thoai",
    "số điện thoại",
    "address",
    "địa chỉ",
    "dia chi",
    "dob",
    "date of birth",
    "ngày sinh",
    "salary",
    "lương",
    "luong",
    "email",
    "employee code",
}
THRESHOLD = 3  # a single "name" column in a synthetic student sample is allowed; 3+ is a person record


def _pii_columns(columns) -> set[str]:
    return {c.strip().lower() for c in columns if c and c.strip().lower() in PII_HEADER_TOKENS}


def _release_files(suffixes):
    for path in APP.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes and not (set(path.relative_to(APP).parts) & SKIP_DIRS):
            yield path


def test_no_csv_in_release_tree_has_personal_data_header():
    offenders = []
    for path in _release_files({".csv"}):
        try:
            with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
                header = next(
                    csv.reader(
                        f,
                        delimiter=";"
                        if path.read_text(encoding="utf-8-sig", errors="replace")[:500].count(";") > 3
                        else ",",
                    ),
                    [],
                )
        except (OSError, StopIteration):
            continue
        if len(_pii_columns(header)) >= THRESHOLD:
            offenders.append(str(path.relative_to(APP)))
    assert offenders == [], f"personal-data exports found (headers only checked): {offenders}"


def test_no_dataset_metadata_describes_personal_data_columns():
    offenders = []
    for path in _release_files({".json"}):
        if "metadata" not in path.parts:
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cols = meta.get("columns") if isinstance(meta, dict) else None
        if isinstance(cols, list) and len(_pii_columns(map(str, cols))) >= THRESHOLD:
            offenders.append(str(path.relative_to(APP)))
    assert offenders == [], f"dataset metadata for personal-data exports: {offenders}"


def test_removed_employee_export_is_absent():
    assert not (APP / "dữ liệu" / "nhanvien_export.csv").exists()
    assert not (APP / "data_warehouse" / "metadata" / "f0ce1f1adb6f_data.json").exists()


def test_docker_build_context_excludes_non_runtime_data():
    rules = {line.strip() for line in (APP / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    for required in ("dữ liệu/", "data_warehouse/", "reports/", ".env", ".env.*"):
        assert required in rules, f".dockerignore must exclude {required}"
