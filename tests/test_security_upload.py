import io

import pytest

from dss.security.upload_security import UploadValidationError, parse_tabular_upload


class Upload(io.BytesIO):
    def __init__(self, name: str, data: bytes, mime: str = "text/csv"):
        super().__init__(data)
        self.name = name
        self.type = mime
        self.size = len(data)


def test_valid_csv_returns_digest_and_data():
    parsed = parse_tabular_upload(Upload("grades.csv", b"student,score\nSV001,8\n"))
    assert parsed.name == "grades.csv"
    assert parsed.frame.shape == (1, 2)
    assert len(parsed.sha256) == 64


@pytest.mark.parametrize("name", ["../../grades.csv", "..\\grades.csv", "C:\\grades.csv", ".hidden.csv"])
def test_path_traversal_and_dangerous_names_rejected(name):
    with pytest.raises(UploadValidationError):
        parse_tabular_upload(Upload(name, b"a\n1\n"))


def test_invalid_extension_and_mime_rejected():
    with pytest.raises(UploadValidationError):
        parse_tabular_upload(Upload("payload.py", b"a\n1\n"))
    with pytest.raises(UploadValidationError):
        parse_tabular_upload(Upload("grades.csv", b"a\n1\n", "application/pdf"))


def test_size_limit_applies_before_parser(monkeypatch):
    monkeypatch.setenv("EDUDSS_MAX_UPLOAD_MB", "1")
    with pytest.raises(UploadValidationError, match="dung lượng"):
        parse_tabular_upload(Upload("large.csv", b"a\n" + b"1" * (1024 * 1024)))


@pytest.mark.parametrize("data", [b"", b"a,b\n1\n", b"a,b\n1,2,3\n", b"a,b\n1,\x00\n", b"\xff\xfe"])
def test_empty_malformed_or_binary_csv_rejected(data):
    with pytest.raises(UploadValidationError):
        parse_tabular_upload(Upload("bad.csv", data))


def test_row_limit_and_duplicate_columns_rejected(monkeypatch):
    monkeypatch.setenv("EDUDSS_MAX_UPLOAD_ROWS", "1")
    with pytest.raises(UploadValidationError, match="số dòng"):
        parse_tabular_upload(Upload("many.csv", b"a\n1\n2\n"))
    with pytest.raises(UploadValidationError, match="trùng lặp"):
        parse_tabular_upload(Upload("duplicate.csv", b"a,a\n1,2\n"))


def test_unexpected_spreadsheet_bytes_rejected():
    with pytest.raises(UploadValidationError):
        parse_tabular_upload(Upload("fake.xlsx", b"not a workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
