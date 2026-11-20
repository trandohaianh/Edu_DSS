"""Responsive/accessibility audit (2026-09) — regression tests for defects
found via LIVE Playwright screenshots at phone width (390x844), not source
reading alone (per the audit's explicit rule: don't judge the UI only by
reading code)."""

from __future__ import annotations

from pathlib import Path

_MAIN_CSS = Path(__file__).resolve().parent.parent / "dss" / "styles" / "main.css"


def test_lecturer_kpi_row_has_phone_and_tablet_breakpoints():
    """Bug found via screenshot: .dss-lect-kpi-row (Lecturer Trang chủ, 4 thẻ
    KPI) bị ép cứng grid-template-columns: repeat(4, ...) ở MỌI kích thước màn
    hình. Ở 390px, mỗi cột chỉ còn ~70-90px sau padding/gap, khiến nhãn tiếng
    Việt dài ("Tổng sinh viên phụ trách") bị bẻ xuống dòng theo TỪNG KÝ TỰ —
    hoàn toàn không đọc được. ui_kit.kpi_row (dùng chung, vd. trang Admin Báo
    cáo) đã tự động xuống 1 cột đúng cách ở cùng kích thước màn hình — đây là
    khoảng cách "adoption" thực sự giữa 1 component riêng và design system
    dùng chung, không phải do thiếu công nghệ responsive trong toàn bộ app."""
    css = _MAIN_CSS.read_text(encoding="utf-8")
    idx_base_rule = css.find(".dss-lect-kpi-row {")
    assert idx_base_rule != -1

    idx_tablet_media = css.find("@media (max-width: 1024px)", idx_base_rule)
    idx_phone_media = css.find("@media (max-width: 480px)", idx_base_rule)
    assert idx_tablet_media != -1, "Thiếu breakpoint máy tính bảng cho .dss-lect-kpi-row"
    assert idx_phone_media != -1, "Thiếu breakpoint điện thoại cho .dss-lect-kpi-row"

    tablet_block = css[idx_tablet_media : idx_tablet_media + 200]
    phone_block = css[idx_phone_media : idx_phone_media + 200]
    assert ".dss-lect-kpi-row" in tablet_block and "repeat(2" in tablet_block
    assert ".dss-lect-kpi-row" in phone_block and "grid-template-columns: 1fr" in phone_block


def test_bordered_card_row_equal_height_chain_covers_stlayoutwrapper():
    """CARD-HEIGHT-001 (Student Product Acceptance audit, 2026-09): bug found
    via real getBoundingClientRect() measurement (not screenshot guessing) on
    the Student home dashboard's 3-card row (Điểm dự báo / Yếu tố ảnh hưởng /
    Trợ lý học tập AI) -- heights measured 531px / 324px / 392px despite the
    existing global equal-height flex rule. Root cause: the installed
    Streamlit version inserts an extra [data-testid="stLayoutWrapper"] layer
    between the already-stretched "> div" and the actual
    st.container(border=True) content block, breaking the height:100% chain
    at that missing link. This is a systemic issue for EVERY bordered-card
    row in st.columns(), not just this one page -- fixed by extending the
    existing selector chain one level deeper (not writing a new rule), so it
    self-heals every other affected row app-wide. Verified after the fix:
    all 3 cards measured exactly 531.25px (see conversation for the live
    Playwright measurement)."""
    css = _MAIN_CSS.read_text(encoding="utf-8")
    idx_base = css.find(
        '[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div > [data-testid="stVerticalBlock"]'
    )
    assert idx_base != -1, "Luật flex chung gốc (áp cho mọi hàng thẻ) không còn tồn tại"

    idx_wrapper_rule = css.find(
        '[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div > [data-testid="stLayoutWrapper"]'
    )
    assert idx_wrapper_rule != -1, (
        "Thiếu luật mở rộng qua lớp stLayoutWrapper — hàng thẻ bo viền (st.container(border=True)) sẽ không được ép chiều cao bằng nhau"
    )

    idx_wrapper_to_block = css.find(
        '[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]'
    )
    assert idx_wrapper_to_block != -1, (
        "Thiếu luật lan chiều cao 100% từ stLayoutWrapper xuống khối nội dung bo viền thật sự bên trong"
    )


def test_student_home_dashboard_cards_have_stable_keys_for_height_targeting():
    """Đảm bảo 3 thẻ Dashboard Sinh viên vẫn giữ key= ổn định (dùng để đo/kiểm
    chứng độc lập bằng Playwright ngoài bộ test này) -- nếu ai đó xoá key khi
    sửa code sau này, test này báo ngay thay vì chỉ phát hiện lại bằng mắt."""
    import inspect

    from dss.tabs import home

    source = inspect.getsource(home._render_student_home_dashboard)
    assert 'key="student_home_card_forecast"' in source
    assert 'key="student_home_card_factors"' in source
    assert 'key="student_home_card_ai"' in source
