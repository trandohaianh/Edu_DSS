"""FINAL REMEDIATION PASS — Mục 5 (đọc lập review 2026-09, K-2 re-audit):
mọi "Mức rủi ro"/"Sinh viên rủi ro cao" hiển thị trong hệ thống được tính
bằng PHÂN VỊ điểm dự đoán trong CHÍNH lớp/tập dữ liệu hiện tại
(`compute_lecturer_dashboard_overview`, `ai_advisor.py`, `home.py`) — KHÔNG
có ngưỡng tuyệt đối nào. Nếu cả lớp đều học giỏi, vẫn luôn có ~25% hiện
"rủi ro cao" thuần vì vị trí tương đối trong lớp, không phải vì yếu theo
chuẩn chung — trước đợt này, badge/KPI hiển thị số liệu đó KHÔNG có bất kỳ
chú thích nào giải thích tính tương đối, có thể bị đọc nhầm thành đánh giá
tuyệt đối/chính thức.

Kiểm tra bằng source inspection (đúng phong cách dự án cho UI Streamlit khó
test trực tiếp): mỗi nơi hiển thị "Mức rủi ro"/"rủi ro cao" (badge hoặc KPI)
PHẢI đi kèm `ui_kit.RELATIVE_RISK_DISCLAIMER`."""
from __future__ import annotations

import inspect

from dss.tabs import ai_advisor, dashboard, home, admin_reports, ui_kit


def test_relative_risk_disclaimer_constant_exists_and_is_non_trivial():
    assert hasattr(ui_kit, "RELATIVE_RISK_DISCLAIMER")
    assert "tương đối" in ui_kit.RELATIVE_RISK_DISCLAIMER.lower()


def test_ai_advisor_plan_risk_badge_has_relative_disclaimer():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    # 2 badge rủi ro trong ai_advisor_tab (hồ sơ rủi ro + bối cảnh chat) — cả
    # 2 phải đi kèm disclaimer ngay sau, không chỉ 1 trong 2.
    occurrences = source.count("RELATIVE_RISK_DISCLAIMER")
    assert occurrences >= 2, (
        f"Chỉ tìm thấy {occurrences} lần dùng RELATIVE_RISK_DISCLAIMER trong ai_advisor_tab "
        "— cần ít nhất 2 (hồ sơ rủi ro + bối cảnh chat)."
    )


def test_home_tab_risk_banner_and_badge_have_relative_disclaimer():
    source = inspect.getsource(home)
    occurrences = source.count("RELATIVE_RISK_DISCLAIMER")
    assert occurrences >= 2, (
        f"Chỉ tìm thấy {occurrences} lần dùng RELATIVE_RISK_DISCLAIMER trong home.py "
        "— cần ít nhất 2 (banner đầu trang + badge rủi ro thẻ Điểm dự báo)."
    )


def test_dashboard_high_risk_section_has_relative_disclaimer():
    source = inspect.getsource(dashboard)
    assert "RELATIVE_RISK_DISCLAIMER" in source


def test_admin_reports_high_risk_kpi_has_relative_disclaimer():
    source = inspect.getsource(admin_reports)
    assert "RELATIVE_RISK_DISCLAIMER" in source
