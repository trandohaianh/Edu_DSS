"""Bounded validation for Streamlit CSV and spreadsheet uploads."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

import pandas as pd


class UploadValidationError(ValueError):
    """A safe, user-facing reason for rejecting an upload."""


@dataclass(frozen=True)
class ParsedUpload:
    name: str
    sha256: str
    frame: pd.DataFrame


MIME_BY_EXTENSION = {
    ".csv": {"text/csv", "text/plain", "application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel"},
}
XLS_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def _limit(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _safe_name(name: object) -> tuple[str, str]:
    if not isinstance(name, str) or not name or len(name) > 128:
        raise UploadValidationError("Tên tệp không hợp lệ hoặc quá dài.")
    if name in {".", ".."} or "/" in name or "\\" in name or re.search(r"[\x00-\x1f\x7f]", name):
        raise UploadValidationError("Tên tệp chứa đường dẫn hoặc ký tự không hợp lệ.")
    if name.startswith(".") or name.endswith((".", " ")) or ":" in name:
        raise UploadValidationError("Tên tệp không an toàn.")
    suffix = PurePath(name).suffix.lower()
    if suffix not in MIME_BY_EXTENSION:
        raise UploadValidationError("Chỉ chấp nhận tệp CSV, XLSX hoặc XLS.")
    return name, suffix


def _validate_csv(data: bytes, max_rows: int, max_columns: int) -> pd.DataFrame:
    if b"\x00" in data:
        raise UploadValidationError("Tệp CSV chứa dữ liệu nhị phân không hợp lệ.")
    try:
        decoded = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        header = next(reader)
        if not header or len(header) > max_columns or any(not col.strip() for col in header):
            raise UploadValidationError("Tệp CSV cần có tên cột hợp lệ.")
        if len(set(header)) != len(header):
            raise UploadValidationError("Tệp CSV có tên cột trùng lặp.")
        row_count = 0
        for row in reader:
            row_count += 1
            if len(row) != len(header):
                raise UploadValidationError("Tệp CSV có số cột không nhất quán.")
            if row_count > max_rows:
                raise UploadValidationError("Tệp CSV vượt quá giới hạn số dòng.")
        if row_count == 0:
            raise UploadValidationError("Tệp CSV không có dòng dữ liệu.")
        frame = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", on_bad_lines="error")
    except (UnicodeError, csv.Error, StopIteration, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise UploadValidationError("Tệp CSV không hợp lệ hoặc không dùng UTF-8.") from exc
    return frame


def _validate_excel(data: bytes, suffix: str, max_bytes: int, max_rows: int) -> pd.DataFrame:
    if suffix == ".xlsx":
        if not data.startswith(b"PK\x03\x04"):
            raise UploadValidationError("Nội dung XLSX không hợp lệ.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                if len(members) > 1000 or not any(item.filename == "xl/workbook.xml" for item in members):
                    raise UploadValidationError("Cấu trúc XLSX không hợp lệ.")
                if sum(item.file_size for item in members) > min(max_bytes * 20, 100 * 1024 * 1024):
                    raise UploadValidationError("Tệp XLSX giải nén vượt giới hạn.")
                if any("externalLinks/" in item.filename or "vbaProject" in item.filename for item in members):
                    raise UploadValidationError("XLSX chứa liên kết ngoài hoặc macro không được chấp nhận.")
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise UploadValidationError("Nội dung XLSX không hợp lệ.") from exc
    elif not data.startswith(XLS_MAGIC):
        raise UploadValidationError("Nội dung XLS không hợp lệ.")
    try:
        return pd.read_excel(io.BytesIO(data), nrows=max_rows + 1)
    except Exception as exc:
        raise UploadValidationError("Không thể đọc bảng tính hợp lệ.") from exc


def safe_document_name(name: object, *, allowed_extensions: set[str]) -> tuple[str, str]:
    """Phase 1B addition — same path-traversal/dangerous-name checks as
    `_safe_name`, generalized to non-tabular document extensions (CMS lesson
    uploads: txt/md/docx/pptx/pdf/json) that `parse_tabular_upload` does not
    cover. Kept separate from `_safe_name` rather than changing its
    signature, so Phase 8A's original tabular validator/tests stay
    untouched."""
    if not isinstance(name, str) or not name or len(name) > 128:
        raise UploadValidationError("Tên tệp không hợp lệ hoặc quá dài.")
    if name in {".", ".."} or "/" in name or "\\" in name or re.search(r"[\x00-\x1f\x7f]", name):
        raise UploadValidationError("Tên tệp chứa đường dẫn hoặc ký tự không hợp lệ.")
    if name.startswith(".") or name.endswith((".", " ")) or ":" in name:
        raise UploadValidationError("Tên tệp không an toàn.")
    suffix = PurePath(name).suffix.lower()
    if suffix not in allowed_extensions:
        raise UploadValidationError("Định dạng tệp không được chấp nhận ở đây.")
    return name, suffix


def read_upload_within_size_limit(uploaded_file: object) -> bytes:
    """Phase 1B addition — enforce the same EDUDSS_MAX_UPLOAD_MB bound as
    `parse_tabular_upload` for non-tabular uploads (CMS documents) before
    handing bytes to a downstream parser."""
    max_bytes = _limit("EDUDSS_MAX_UPLOAD_MB", 10, 1, 100) * 1024 * 1024
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > max_bytes:
        raise UploadValidationError("Tệp vượt quá giới hạn dung lượng.")
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read(max_bytes + 1)
    if not isinstance(data, bytes) or not data:
        raise UploadValidationError("Tệp rỗng hoặc không hợp lệ.")
    if len(data) > max_bytes:
        raise UploadValidationError("Tệp vượt quá giới hạn dung lượng.")
    return data


def parse_tabular_upload(uploaded_file: object, *, allowed_extensions: set[str] | None = None) -> ParsedUpload:
    """Validate before parsing; never use the supplied filename as a path."""
    name, suffix = _safe_name(getattr(uploaded_file, "name", None))
    if allowed_extensions is not None and suffix not in allowed_extensions:
        raise UploadValidationError("Định dạng tệp không được chấp nhận ở đây.")
    mime = (getattr(uploaded_file, "type", "") or "").lower()
    if mime and mime != "application/octet-stream" and mime not in MIME_BY_EXTENSION[suffix]:
        raise UploadValidationError("Loại nội dung không khớp với phần mở rộng tệp.")
    max_bytes = _limit("EDUDSS_MAX_UPLOAD_MB", 10, 1, 100) * 1024 * 1024
    max_rows = _limit("EDUDSS_MAX_UPLOAD_ROWS", 20000, 1, 100000)
    max_columns = _limit("EDUDSS_MAX_UPLOAD_COLUMNS", 200, 1, 1000)
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > max_bytes:
        raise UploadValidationError("Tệp vượt quá giới hạn dung lượng.")
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read(max_bytes + 1)
    if not isinstance(data, bytes) or not data:
        raise UploadValidationError("Tệp rỗng hoặc không hợp lệ.")
    if len(data) > max_bytes:
        raise UploadValidationError("Tệp vượt quá giới hạn dung lượng.")
    frame = _validate_csv(data, max_rows, max_columns) if suffix == ".csv" else _validate_excel(data, suffix, max_bytes, max_rows)
    if frame.empty or len(frame) > max_rows or len(frame.columns) > max_columns:
        raise UploadValidationError("Tệp không có dữ liệu hoặc vượt giới hạn bảng.")
    return ParsedUpload(name=name, sha256=hashlib.sha256(data).hexdigest(), frame=frame)
