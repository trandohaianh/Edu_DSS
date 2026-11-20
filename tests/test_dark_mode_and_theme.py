"""Unit tests for Deep Dark Mode and Theme Switcher functionality."""

from pathlib import Path

from dss.config import inject_styles


def test_main_css_contains_dark_mode_rules():
    """Kiểm tra main.css chứa đầy đủ media query prefers-color-scheme và manual dark mode."""
    css_path = Path(__file__).resolve().parent.parent / "dss" / "styles" / "main.css"
    assert css_path.is_file(), "main.css không tồn tại"
    content = css_path.read_text(encoding="utf-8")

    assert "prefers-color-scheme: dark" in content
    assert ':root[data-theme="dark"]' in content or ".dss-theme-dark" in content
    assert "#0B132B" in content or "#0F172A" in content
    assert "#1E293B" in content
    assert "#F8FAFC" in content


def test_theme_mode_session_injection(monkeypatch):
    """inject_styles nạp main.css và phát ĐÚNG 1 marker chế độ giao diện.

    C1.3: màu tối KHÔNG còn nằm trong khối CSS Python riêng — main.css giữ
    toàn bộ token (sáng + tối), Python chỉ chọn bộ token qua marker
    `.dss-theme-<mode>`. Giá trị cũ "auto" và giá trị lạ đều về "system"."""
    import streamlit as st

    markdown_calls = []

    def mock_markdown(body, unsafe_allow_html=False):
        markdown_calls.append(body)

    monkeypatch.setattr(st, "markdown", mock_markdown)

    expectations = {
        "auto": "dss-theme-system",
        "system": "dss-theme-system",
        "dark": "dss-theme-dark",
        "light": "dss-theme-light",
        "không-hợp-lệ": "dss-theme-system",
    }
    for mode, marker in expectations.items():
        markdown_calls.clear()
        st.session_state["dss_theme"] = mode
        inject_styles()
        assert any("prefers-color-scheme: dark" in c for c in markdown_calls), "main.css phải được nạp"
        markers = [c for c in markdown_calls if "dss-marker dss-theme-" in c]
        assert len(markers) == 1 and marker in markers[0], (mode, markers)


def test_dark_tokens_are_defined_for_explicit_and_system_dark():
    """Bộ token tối phải áp dụng cho cả lựa chọn "Tối" lẫn "Hệ thống" khi hệ
    điều hành đang ở chế độ tối — và đổi nền trang/bề mặt/chữ thật sự."""
    css_path = Path(__file__).resolve().parent.parent / "dss" / "styles" / "main.css"
    content = css_path.read_text(encoding="utf-8")
    explicit = content[content.index(":root:has(.dss-theme-dark) {") :]
    explicit = explicit[: explicit.index("}")]
    media = content[content.index("@media (prefers-color-scheme: dark)") :]
    system = media[media.index(":root:has(.dss-theme-system) {") :]
    system = system[: system.index("}")]
    for block in (explicit, system):
        assert "--bg-primary: #0F172A" in block
        assert "--surface: #151E2E" in block
        assert "--text-primary: #F8FAFC" in block
        assert "--dss-color-scheme: dark" in block
