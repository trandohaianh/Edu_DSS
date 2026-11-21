"""Dữ liệu cho 3 trang của Giảng viên: Phân tích rủi ro, Lịch sử tư vấn, Báo cáo.

Chỉ ĐỌC và biến đổi dữ liệu thật đã có (tổng quan lớp từ
`model_service.compute_lecturer_dashboard_overview`, lịch sử tư vấn từ
`warehouse.get_history("advisor")`, danh sách mô hình từ `warehouse.list_models()`).
Không gọi Streamlit, để test được trực tiếp (tests/test_lecturer_reports.py).

Phạm vi dữ liệu = bộ dữ liệu đang dùng (quyết định chủ dự án 21/11/2026, AC-GV-09..11):
bản Streamlit chưa lưu giảng viên nào phụ trách lớp nào.
"""

from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd

from dss.security.export_safety import safe_for_spreadsheet

RISK_LEVELS = ("cao", "trung bình", "thấp")
RISK_LABELS = {"cao": "Nguy cơ cao", "trung bình": "Nguy cơ trung bình", "thấp": "Nguy cơ thấp"}
UNKNOWN_ACTOR = "không rõ"

CONSULTATION_COLUMNS = [
    "Thời gian",
    "Mã SV",
    "Điểm dự đoán",
    "Điểm yếu",
    "Người tư vấn",
    "Nguồn AI",
    "Tóm tắt kế hoạch",
]


# ------------------------------------------------------------------ rủi ro
def risk_distribution(overview: dict | None) -> pd.DataFrame:
    """Bảng [Mức rủi ro, Số sinh viên, Tỉ lệ (%)] từ `risk_counts` của tổng quan lớp.

    Trả bảng rỗng khi chưa có tổng quan hợp lệ (chưa có mô hình Production...)."""
    if not overview or overview.get("status") != "ok":
        return pd.DataFrame(columns=["Mức rủi ro", "Số sinh viên", "Tỉ lệ (%)"])
    counts = overview.get("risk_counts") or {}
    total = sum(int(counts.get(k, 0)) for k in RISK_LEVELS)
    rows = []
    for k in RISK_LEVELS:
        n = int(counts.get(k, 0))
        rows.append(
            {"Mức rủi ro": RISK_LABELS[k], "Số sinh viên": n, "Tỉ lệ (%)": round(100 * n / total, 1) if total else 0.0}
        )
    return pd.DataFrame(rows)


def high_risk_table(overview: dict | None, label_fn=None) -> pd.DataFrame:
    """Danh sách sinh viên nguy cơ cao, điểm dự đoán thấp nhất lên đầu.

    `label_fn` đổi tên cột đặc trưng sang tên dễ đọc (ví dụ `feature_label`)."""
    cols = ["Mã SV", "Điểm hiện tại", "Điểm dự đoán", "Yếu tố kéo điểm xuống nhiều nhất"]
    if not overview or overview.get("status") != "ok":
        return pd.DataFrame(columns=cols)
    rows = []
    for r in overview.get("high_risk_students") or []:
        factor = r.get("top_factor")
        rows.append(
            {
                "Mã SV": "" if r.get("id") is None else str(r.get("id")),
                "Điểm hiện tại": _round_or_none(r.get("current")),
                "Điểm dự đoán": _round_or_none(r.get("predicted")),
                "Yếu tố kéo điểm xuống nhiều nhất": (label_fn(factor) if label_fn else factor) if factor else "—",
            }
        )
    return pd.DataFrame(rows, columns=cols)


def _round_or_none(value, digits: int = 2):
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ lịch sử tư vấn
def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def filter_consultations(
    records,
    student_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    performed_by: str | None = None,
) -> list[dict]:
    """Lọc phiên tư vấn theo mã SV (không phân biệt hoa/thường, khớp một phần),
    khoảng ngày (tính cả 2 đầu) và người thực hiện. Mới nhất lên đầu.

    Phiên không đọc được thời gian vẫn giữ lại khi KHÔNG lọc theo ngày, và bị loại
    khi có lọc theo ngày (không thể biết nó có nằm trong khoảng hay không)."""
    sid = (student_id or "").strip().lower()
    out = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        if sid and sid not in str(rec.get("student_id", "")).lower():
            continue
        if performed_by and rec.get("performed_by") != performed_by:
            continue
        ts = _parse_ts(rec.get("created_at"))
        if (date_from or date_to) and ts is None:
            continue
        if date_from and ts.date() < date_from:
            continue
        if date_to and ts.date() > date_to:
            continue
        out.append(rec)
    out.sort(key=lambda r: _parse_ts(r.get("created_at")) or datetime.min, reverse=True)
    return out


def _summary(text, limit: int = 160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def consultations_frame(records) -> pd.DataFrame:
    """Bảng hiển thị/xuất Excel cho danh sách phiên tư vấn."""
    rows = []
    for rec in records or []:
        ts = _parse_ts(rec.get("created_at"))
        weaknesses = rec.get("weaknesses") or []
        if isinstance(weaknesses, (list, tuple)):
            weaknesses = ", ".join(str(w) for w in weaknesses)
        rows.append(
            {
                "Thời gian": ts.strftime("%d/%m/%Y %H:%M") if ts else "—",
                "Mã SV": str(rec.get("student_id") or "—"),
                "Điểm dự đoán": _round_or_none(rec.get("predicted_gpa")),
                "Điểm yếu": weaknesses or "—",
                "Người tư vấn": rec.get("performed_by") or UNKNOWN_ACTOR,
                "Nguồn AI": rec.get("provider") or "—",
                "Tóm tắt kế hoạch": _summary(rec.get("generated_plan")),
            }
        )
    return pd.DataFrame(rows, columns=CONSULTATION_COLUMNS)


# ------------------------------------------------------------------ báo cáo
def model_versions_frame(models, dataset_id: str | None = None, target_col: str | None = None) -> pd.DataFrame:
    """Các phiên bản mô hình của cặp dataset + target (nếu có), kèm chỉ số thật
    trong metadata. Dùng cho biểu đồ "Hiệu năng mô hình qua các phiên bản"."""
    cols = ["Phiên bản", "Mô hình", "Trạng thái", "Chỉ số", "Giá trị", "Ngày huấn luyện"]
    rows = []
    for m in models or []:
        if dataset_id and m.get("dataset_id") != dataset_id:
            continue
        if target_col and m.get("target_col") != target_col:
            continue
        metrics = m.get("metrics") or {}
        name = (
            "R2 Score"
            if "R2 Score" in metrics
            else ("F1-Score" if "F1-Score" in metrics else next(iter(metrics), None))
        )
        value = metrics.get(name) if name else None
        ts = _parse_ts(m.get("trained_at"))
        rows.append(
            {
                "Phiên bản": m.get("version"),
                "Mô hình": m.get("model_name") or "—",
                "Trạng thái": "Production" if m.get("is_production") else (m.get("status") or "candidate").capitalize(),
                "Chỉ số": name or "—",
                "Giá trị": _round_or_none(value, 4),
                "Ngày huấn luyện": ts.strftime("%d/%m/%Y %H:%M") if ts else "—",
            }
        )
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df = df.sort_values("Phiên bản", key=lambda s: pd.to_numeric(s, errors="coerce")).reset_index(drop=True)
    return df


def report_summary(overview: dict | None, n_students: int, n_consultations: int) -> pd.DataFrame:
    """Trang tính "Tổng hợp" của file Excel: mỗi dòng 1 chỉ số + ghi chú nguồn."""
    ok = bool(overview and overview.get("status") == "ok")
    counts = (overview or {}).get("risk_counts") or {}
    rows = [
        ("Ngày xuất báo cáo", datetime.now().strftime("%d/%m/%Y %H:%M"), ""),
        ("Số sinh viên trong bộ dữ liệu", n_students, "Bộ dữ liệu đang dùng"),
        ("Nguy cơ cao", counts.get("cao") if ok else None, "Tương đối trong lớp: 25% điểm dự đoán thấp nhất"),
        ("Nguy cơ trung bình", counts.get("trung bình") if ok else None, "Từ phân vị 25% đến 50%"),
        ("Nguy cơ thấp", counts.get("thấp") if ok else None, "Trên phân vị 50%"),
        ("Điểm dự đoán trung bình", _round_or_none((overview or {}).get("avg_predicted")) if ok else None, ""),
        (
            "Mô hình đang dùng",
            f"{overview.get('model_name')} v{overview.get('version')}" if ok else None,
            "Bản Production",
        ),
        (
            f"Chỉ số mô hình ({overview.get('metric_name')})"
            if ok and overview.get("metric_name")
            else "Chỉ số mô hình",
            _round_or_none((overview or {}).get("metric_value"), 4) if ok else None,
            "Đo trên tập kiểm tra của dữ liệu đang dùng",
        ),
        ("Số phiên tư vấn AI", n_consultations, "Toàn bộ phiên đã lưu"),
    ]
    return (
        pd.DataFrame(rows, columns=["Chỉ số", "Giá trị", "Ghi chú"])
        .astype({"Giá trị": "object"})
        .fillna({"Giá trị": "—"})
    )


def _excel_engine() -> str | None:
    """Ưu tiên xlsxwriter rồi openpyxl, giống `dss/core/feature_utils.py::to_excel`
    (cả 2 đều có trong requirements.txt; máy dev có thể chỉ cài 1 trong 2)."""
    import importlib.util

    for engine in ("xlsxwriter", "openpyxl"):
        if importlib.util.find_spec(engine) is not None:
            return engine
    return None


def build_report_workbook(sheets: dict[str, pd.DataFrame]) -> bytes | None:
    """Ghi nhiều bảng thành 1 file Excel (mỗi bảng 1 trang tính), trả về bytes.

    Trả None nếu máy không có thư viện ghi Excel nào. Tên trang tính bị Excel giới
    hạn 31 ký tự; độ rộng cột theo nội dung dài nhất (10–60 ký tự)."""
    engine = _excel_engine()
    if engine is None:
        return None
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine=engine) as writer:
        for name, frame in sheets.items():
            # Chống chèn công thức Excel (bước 7, 21/11/2026).
            frame = safe_for_spreadsheet(frame if frame is not None else pd.DataFrame())
            sheet = str(name)[:31]
            frame.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            for i, col in enumerate(frame.columns):
                longest = max([len(str(col))] + [len(str(v)) for v in frame[col].tolist() if v is not None])
                width = min(max(longest + 2, 10), 60)
                if engine == "xlsxwriter":
                    ws.set_column(i, i, width)
                else:
                    from openpyxl.utils import get_column_letter

                    ws.column_dimensions[get_column_letter(i + 1)].width = width
    return buf.getvalue()
