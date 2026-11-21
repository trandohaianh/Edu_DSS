"""3 trang Giảng viên (AC-GV-09..11): dữ liệu, lọc, xuất Excel, phân quyền và ghi
người thực hiện phiên tư vấn."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date

import pandas as pd
import pytest

from dss.core.roles import (
    LECTURER_HISTORY_TAB_LABEL,
    LECTURER_REPORTS_TAB_LABEL,
    LECTURER_RISK_TAB_LABEL,
    ROLES,
    TAB_ACCESS,
    nav_label,
)
from dss.services import lecturer_reports as lr

_OVERVIEW = {
    "status": "ok",
    "model_name": "Random Forest Regressor",
    "version": 2,
    "metric_name": "R2 Score",
    "metric_value": 0.91234,
    "avg_predicted": 6.8812,
    "target_col": "diem_ky_sau",
    "risk_counts": {"cao": 5, "trung bình": 3, "thấp": 12},
    "high_risk_students": [
        {"id": "SV010", "current": 5.123, "predicted": 4.2, "top_factor": "so_buoi_vang"},
        {"id": "SV002", "current": None, "predicted": 4.9, "top_factor": None},
    ],
}

_RECORDS = [
    {"student_id": "SV001", "created_at": "2026-11-01T09:00:00", "performed_by": "giangvien", "generated_plan": "A"},
    {"student_id": "SV002", "created_at": "2026-11-20T14:30:00", "performed_by": "gv2", "weaknesses": ["Toán", "Lý"]},
    {"student_id": "sv001", "created_at": "2026-11-15T08:00:00"},
    {"student_id": "SV003", "created_at": "không phải ngày"},
]


# ------------------------------------------------------------------ phân quyền
def test_three_pages_are_lecturer_only_and_have_short_labels():
    for tab in (LECTURER_RISK_TAB_LABEL, LECTURER_HISTORY_TAB_LABEL, LECTURER_REPORTS_TAB_LABEL):
        assert TAB_ACCESS[tab] == {"Giảng viên / CVHT"}
        assert set(ROLES) - TAB_ACCESS[tab] == {"Sinh viên", "Admin"}
    assert nav_label(LECTURER_RISK_TAB_LABEL, "Giảng viên / CVHT") == "Phân tích rủi ro"
    assert nav_label(LECTURER_HISTORY_TAB_LABEL, "Giảng viên / CVHT") == "Lịch sử tư vấn"
    assert nav_label(LECTURER_REPORTS_TAB_LABEL, "Giảng viên / CVHT") == "Báo cáo"


# ------------------------------------------------------------------ rủi ro
def test_risk_distribution_counts_and_percentages():
    dist = lr.risk_distribution(_OVERVIEW)
    assert dist["Mức rủi ro"].tolist() == ["Nguy cơ cao", "Nguy cơ trung bình", "Nguy cơ thấp"]
    assert dist["Số sinh viên"].tolist() == [5, 3, 12]
    assert dist["Tỉ lệ (%)"].tolist() == [25.0, 15.0, 60.0]


def test_risk_distribution_empty_without_production_model():
    assert lr.risk_distribution({"status": "empty", "message": "x"}).empty
    assert lr.risk_distribution(None).empty


def test_high_risk_table_uses_label_fn_and_handles_missing_values():
    t = lr.high_risk_table(_OVERVIEW, label_fn=lambda f: f"<{f}>")
    assert t["Mã SV"].tolist() == ["SV010", "SV002"]
    assert t.loc[0, "Điểm hiện tại"] == 5.12
    assert t.loc[0, "Yếu tố kéo điểm xuống nhiều nhất"] == "<so_buoi_vang>"
    assert pd.isna(t.loc[1, "Điểm hiện tại"])
    assert t.loc[1, "Yếu tố kéo điểm xuống nhiều nhất"] == "—"


# ------------------------------------------------------------------ lịch sử tư vấn
def test_filter_by_student_is_case_insensitive_and_newest_first():
    rows = lr.filter_consultations(_RECORDS, student_id="sv001")
    assert [r["created_at"] for r in rows] == ["2026-11-15T08:00:00", "2026-11-01T09:00:00"]


def test_filter_by_date_range_is_inclusive_and_drops_unparseable_dates():
    rows = lr.filter_consultations(_RECORDS, date_from=date(2026, 11, 15), date_to=date(2026, 11, 20))
    assert {r["student_id"] for r in rows} == {"SV002", "sv001"}
    assert len(lr.filter_consultations(_RECORDS)) == 4  # không lọc ngày → giữ cả bản ghi lỗi ngày


def test_filter_by_performer():
    rows = lr.filter_consultations(_RECORDS, performed_by="giangvien")
    assert [r["student_id"] for r in rows] == ["SV001"]


def test_consultations_frame_marks_unknown_performer():
    frame = lr.consultations_frame(lr.filter_consultations(_RECORDS))
    assert list(frame.columns) == lr.CONSULTATION_COLUMNS
    by_id = dict(zip(frame["Mã SV"], frame["Người tư vấn"], strict=False))
    assert by_id["sv001"] == lr.UNKNOWN_ACTOR
    assert by_id["SV002"] == "gv2"
    assert frame.loc[frame["Mã SV"] == "SV002", "Điểm yếu"].item() == "Toán, Lý"
    assert frame.loc[frame["Mã SV"] == "SV003", "Thời gian"].item() == "—"


# ------------------------------------------------------------------ báo cáo
def test_model_versions_frame_filters_and_sorts_by_version():
    models = [
        {"dataset_id": "d1", "target_col": "t", "version": 2, "is_production": True, "metrics": {"R2 Score": 0.9}},
        {"dataset_id": "d1", "target_col": "t", "version": 1, "status": "archived", "metrics": {"R2 Score": 0.8}},
        {"dataset_id": "d2", "target_col": "t", "version": 1, "metrics": {"R2 Score": 0.1}},
    ]
    f = lr.model_versions_frame(models, dataset_id="d1", target_col="t")
    assert f["Phiên bản"].tolist() == [1, 2]
    assert f["Trạng thái"].tolist() == ["Archived", "Production"]
    assert f["Giá trị"].tolist() == [0.8, 0.9]


def test_report_summary_has_no_numbers_without_production_model():
    s = lr.report_summary({"status": "empty"}, n_students=20, n_consultations=3)
    values = dict(zip(s["Chỉ số"], s["Giá trị"], strict=False))
    assert values["Số sinh viên trong bộ dữ liệu"] == 20
    assert values["Nguy cơ cao"] == "—"
    assert values["Mô hình đang dùng"] == "—"


def _xlsx_sheet_names(data: bytes) -> list[str]:
    """Đọc tên trang tính trực tiếp từ file .xlsx (không cần openpyxl)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return re.findall(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))


def test_workbook_has_one_sheet_per_table():
    if lr._excel_engine() is None:
        pytest.skip("Không có xlsxwriter/openpyxl")
    data = lr.build_report_workbook(
        {
            "Tổng hợp": lr.report_summary(_OVERVIEW, 20, 4),
            "Phân bố rủi ro": lr.risk_distribution(_OVERVIEW),
            "Một tên trang tính rất dài vượt quá ba mươi mốt ký tự": pd.DataFrame({"a": [1]}),
        }
    )
    names = _xlsx_sheet_names(data)
    assert names[:2] == ["Tổng hợp", "Phân bố rủi ro"]
    assert len(names[2]) == 31
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheet2 = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "<v>5</v>" in sheet2 and "<v>12</v>" in sheet2  # số SV từng mức rủi ro


def test_workbook_returns_none_without_excel_library(monkeypatch):
    monkeypatch.setattr(lr, "_excel_engine", lambda: None)
    assert lr.build_report_workbook({"x": pd.DataFrame({"a": [1]})}) is None


# ------------------------------------------------------------------ ghi người tư vấn
def test_consultation_records_who_performed_it(tmp_path, monkeypatch):
    from dss.core import warehouse as wh_mod

    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("EDUDSS_CONSULTATIONS_STORE", raising=False)
    monkeypatch.setattr(wh_mod, "_current_actor", lambda: {"username": "giangvien", "role": "Giảng viên / CVHT"})
    wh = wh_mod.DataWarehouse(base_path=str(tmp_path))
    wh.save_ai_consultation({"student_id": "SV001", "provider": "rule", "generated_plan": "x"})
    rec = wh.get_history("advisor", limit=10)[-1]
    assert rec["performed_by"] == "giangvien"
    assert rec["performed_by_role"] == "Giảng viên / CVHT"


def test_consultation_without_session_still_saves(tmp_path, monkeypatch):
    from dss.core import warehouse as wh_mod

    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("EDUDSS_CONSULTATIONS_STORE", raising=False)
    monkeypatch.setattr(wh_mod, "_current_actor", dict)
    wh = wh_mod.DataWarehouse(base_path=str(tmp_path))
    wh.save_ai_consultation({"student_id": "SV002", "provider": "rule"})
    rec = wh.get_history("advisor", limit=10)[-1]
    assert rec["student_id"] == "SV002"
    assert rec["performed_by"] is None
