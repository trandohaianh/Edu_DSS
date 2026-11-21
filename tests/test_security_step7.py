"""Hồi quy cho các lỗi bảo mật sửa ở bước 7 (21/11/2026, nhóm A).

Mỗi test ứng với một phát hiện của đợt rà soát; xem docs/security/SECURITY_CHECKLIST.md.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ chèn công thức Excel/CSV
def test_export_neutralizes_formula_cells_but_keeps_numbers():
    from dss.security.export_safety import neutralize_cell, safe_for_spreadsheet

    for bad in ("=HYPERLINK(\"http://x\",\"bấm\")", "+1+1", "-cmd", "@SUM(A1)", "\t=1"):
        assert neutralize_cell(bad).startswith("'")
    for ok in ("-5.2", "Bình thường", "", 3, None, "— không có"):
        assert neutralize_cell(ok) == ok
    df = pd.DataFrame({"=evil": ["=1+1", "an toàn"], "n": [-3, 4]})
    out = safe_for_spreadsheet(df)
    assert list(out.columns) == ["'=evil", "n"]
    assert out["'=evil"].tolist() == ["'=1+1", "an toàn"]
    assert out["n"].tolist() == [-3, 4]
    assert df.loc[0, "=evil"] == "=1+1"  # không sửa dữ liệu gốc


def test_lecturer_workbook_contains_no_formula():
    from dss.services import lecturer_reports as lr

    if lr._excel_engine() is None:
        pytest.skip("Không có xlsxwriter/openpyxl")
    data = lr.build_report_workbook({"x": pd.DataFrame({"Mã SV": ['=HYPERLINK("http://a","b")']})})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "<f>" not in sheet


# ------------------------------------------------------------------ XSS
def test_badge_and_citation_always_escape():
    from dss.tabs import ui_kit

    assert "<script>" not in ui_kit.badge_html("<script>alert(1)</script>")
    assert "&lt;img" in ui_kit.source_citation_badge('<img src=x onerror="alert(1)">', section="Bài <b>")


def test_ai_plan_keeps_only_br_tags():
    from dss.tabs.ui_kit import markdown_keep_br_only

    out = markdown_keep_br_only('| a<br>b | <img src=x onerror=alert(1)> | c<BR/>d |\n> trích dẫn & ghi chú')
    assert out.count("<br>") == 2
    assert "<img" not in out and "&lt;img" in out
    assert "> trích dẫn &amp; ghi chú" in out


def test_no_unescaped_interpolation_left_at_reported_sites():
    """Các vị trí rà soát chỉ ra (giá trị từ dữ liệu/AI chèn vào HTML) phải đi qua html.escape."""
    checks = {
        "dss/tabs/warehouse_tab.py": ["{ev.student_id}", "{ev.description}", "{item['model_name']}"],
        "dss/tabs/eda.py": ["voi {target_for_analysis}:"],
        "dss/tabs/ai_advisor.py": ['f"📄 {_src}</div>"', 'f"- {w}" for w in weaknesses_llm'],
    }
    for rel, needles in checks.items():
        src = (APP / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in src, f"{rel}: còn chèn thô {needle}"


# ------------------------------------------------------------------ phân quyền
def test_undeclared_tab_is_hidden_from_everyone():
    from dss.core.roles import ROLES, filter_tabs_for_role

    for role in [*ROLES, "Platform Admin"]:
        assert "🧪 Trang chưa khai báo" not in filter_tabs_for_role(["🧪 Trang chưa khai báo"], role)


@pytest.mark.parametrize("fn_name", ["render_risk_analysis_tab", "render_reports_tab"])
def test_lecturer_pages_refuse_students_at_function_level(as_role, fn_name):
    from dss.tabs import lecturer_pages

    as_role("Sinh viên", student_id="SV001")
    with pytest.raises(PermissionError):
        getattr(lecturer_pages, fn_name)(None, None)


def test_lecturer_history_refuses_admin(as_role):
    from dss.tabs import lecturer_pages

    as_role("Admin")
    with pytest.raises(PermissionError):
        lecturer_pages.render_consultation_history_tab(None, "admin")


# ------------------------------------------------------------------ seed demo trong production
@pytest.mark.parametrize("env", [None, "production"])
def test_demo_seed_refuses_production(monkeypatch, env):
    from dss.db import seed

    if env is None:
        monkeypatch.delenv("EDUDSS_ENV", raising=False)
    else:
        monkeypatch.setenv("EDUDSS_ENV", env)

    def _never():
        raise AssertionError("Không được mở kết nối CSDL khi seed bị từ chối")

    monkeypatch.setattr(seed, "session_scope", _never)
    with pytest.raises(SystemExit):
        seed.run_seed()


# ------------------------------------------------------------------ log
def test_usernames_are_hashed_in_logs():
    from dss.security.log_redaction import redact_text

    out = redact_text("Đăng nhập thất bại (sai mật khẩu): username=nguyenvana role=Sinh viên")
    assert "nguyenvana" not in out
    assert re.search(r"username=u#[0-9a-f]{10}", out)
    assert redact_text("username=nguyenvana") == redact_text("username=NguyenVanA")  # cùng mã băm


# ------------------------------------------------------------------ triển khai
def test_proxy_overwrites_real_ip_and_app_reads_it():
    for caddy in ("deploy/production/Caddyfile", "deploy/standalone/Caddyfile", "deploy/cloud/edudss.caddy"):
        assert "header_up X-Real-IP {remote_host}" in (APP / caddy).read_text(encoding="utf-8"), caddy
    for compose in (
        "deploy/production/docker-compose.prod.yml",
        "deploy/standalone/docker-compose.yml",
        "deploy/cloud/docker-compose.yml",
    ):
        text = (APP / compose).read_text(encoding="utf-8")
        assert "EDUDSS_CLIENT_IP_HEADER: X-Real-IP" in text, compose
        assert re.search(r"image: caddy:[0-9.]+-alpine@sha256:[0-9a-f]{64}", text), f"{compose}: Caddy chưa ghim"


# ------------------------------------------------------------------ Hướng nghiệp qua cổng AI
def test_career_chat_goes_through_quota_budget_and_output_guard():
    src = (APP / "dss/tabs/advisory.py").read_text(encoding="utf-8")
    call = src.index("llm_integration.call_ai_provider(prompt")
    assert src.rfind("check_quota_and_rate_limit(", 0, call) != -1, "phải kiểm hạn ngạch/ngân sách trước khi gọi AI"
    assert "guard_stream(" in src[call : call + 400], "câu trả lời phải qua bộ lọc lời khuyên có hại"
