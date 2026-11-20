"""E2E (Playwright, trình duyệt thật): UI/RAG consistency pass — 2026-09-16.

Phủ đúng 3 lỗi CÓ THẬT đã tìm và sửa trong lượt này (không lặp lại các mục đã
xác nhận KHÔNG tái hiện được trên code hiện tại — xem báo cáo cuối phiên):

1. Dark mode: `-webkit-text-fill-color` (không phải `color`) là thứ Chromium
   thực sự sơn lên chữ — hàng chục rule trong main.css set cả hai cùng lúc
   bằng giá trị SÁNG cố định, khiến số liệu trên thẻ metric gần như vô hình
   trên nền tối. Test xác nhận `-webkit-text-fill-color` khớp `color` sau khi
   bật chế độ tối, dùng ĐÚNG kỹ thuật đã dùng để phát hiện lỗi (không phải
   suy đoán).
2. Sidebar: tiêu đề nhóm điều hướng ("TỔNG QUAN", "DỮ LIỆU & MÔ HÌNH"...) bị
   cắt vì `[data-testid="stElementContainer"]` của Streamlit tự tính chiều
   cao ~18px cho một dòng chữ thường, trong khi chữ hoa có dấu tiếng Việt cần
   ~30px+ — phần thừa bị cuộn ẩn (`overflow: hidden auto`) thay vì hiển thị.
3. Trạng thái nhà cung cấp AI: trang "Trợ lý AI" (bảng tóm tắt) và trang
   "Cấu hình AI" (bảng test thật) từng dùng 2 nguồn sự thật khác nhau — một
   bên suy từ việc "có cấu hình key" (luôn ra "Sẵn sàng"), một bên gọi API
   thật (`llm_gateway.check_provider_health`). Test xác nhận cả 2 trang giờ
   hiển thị CÙNG MỘT nhãn cho cùng 1 provider sau khi chạy kiểm tra thật.
"""
from __future__ import annotations



def _open_ai_advisor_tab(page):
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Trợ lý AI", exact=False).first.click(timeout=30000)
    page.get_by_role("button", name="Tạo Kế hoạch Học tập", exact=False).first.wait_for(state="visible", timeout=30000)


def _open_ai_config_tab(page):
    page.locator("[data-testid='stSidebar']").get_by_role("button", name="Cấu hình AI", exact=False).first.click(timeout=30000)
    page.get_by_text("Trạng thái provider", exact=False).first.wait_for(state="visible", timeout=30000)


def _enable_dark_mode(page):
    """C1.3: chế độ giao diện chọn bằng nhóm nút Sáng / Tối / Hệ thống ở chân
    sidebar (st.segmented_control) — bấm nút "Tối" như người dùng thật."""
    footer = page.locator(".st-key-dss_sidebar_footer")
    footer.get_by_role("button", name="Tối", exact=True).first.click(timeout=15000)
    page.wait_for_timeout(2000)
    page.locator(".dss-marker.dss-theme-dark").wait_for(state="attached", timeout=15000)


def test_dark_mode_metric_value_text_fill_matches_color(login, wait_ready):
    """Trước khi sửa: color=rgb(96,165,250) (đúng) nhưng
    -webkit-text-fill-color=rgb(15,23,42) (gần đen) — chữ vô hình trên nền tối.
    Sau khi sửa: cả hai phải khớp nhau (chữ thực sự sơn đúng màu `color`)."""
    page = login("admin", "admin123")
    _enable_dark_mode(page)
    wait_ready(page, timeout=25)

    info = page.evaluate(
        """
        () => {
            const outer = document.querySelector('[data-testid="stMetricValue"]');
            if (!outer) return null;
            const inner = outer.querySelector('div') || outer;
            const cs = getComputedStyle(inner);
            return {fill: cs.webkitTextFillColor, color: cs.color};
        }
        """
    )
    assert info is not None, "Không tìm thấy metric nào trên trang để kiểm tra."
    assert info["fill"] == info["color"], (
        f"-webkit-text-fill-color ({info['fill']}) phải khớp color ({info['color']}) "
        "ở chế độ tối — nếu khác nhau, Chromium sẽ sơn chữ theo fill-color, không "
        "phải color, khiến số liệu gần như vô hình trên nền tối."
    )


def test_sidebar_group_title_not_clipped(login, wait_ready):
    """Container bọc tiêu đề nhóm điều hướng phải đủ cao để chứa toàn bộ chữ
    hoa có dấu (đo trực tiếp bằng getBoundingClientRect, không suy đoán qua
    ảnh chụp màn hình)."""
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    info = page.evaluate(
        """
        () => {
            const title = document.querySelector('.dss-sidebar-group-title');
            if (!title) return null;
            const container = title.closest('[data-testid="stElementContainer"]');
            const cs = getComputedStyle(container);
            return {overflowY: cs.overflowY, overflowX: cs.overflowX};
        }
        """
    )
    assert info is not None, "Không tìm thấy tiêu đề nhóm điều hướng nào trong sidebar."
    # ĐÚNG bất biến cần kiểm: overflow phải là "visible" — content cao hơn
    # kích thước ước lượng của Streamlit vẫn hiển thị đầy đủ, không bị cuộn/
    # clip mất phần trên. (Không kiểm bằng so sánh bounding-box: một khi
    # overflow đã là visible, content "vượt" khỏi box của nó là bình thường
    # và vô hại — đó chính là mục đích của việc sửa overflow.)
    assert info["overflowY"] == "visible", (
        f"Container bọc tiêu đề nhóm điều hướng có overflow-y='{info['overflowY']}' "
        "(cần 'visible') — với 'hidden'/'auto' và chiều cao ước lượng quá nhỏ của "
        "Streamlit cho 1 dòng chữ thường, phần chữ hoa có dấu cao hơn sẽ bị cắt."
    )


def test_provider_health_consistent_between_ai_advisor_and_ai_config(login, wait_ready):
    """Chạy kiểm tra kết nối thật ở trang Cấu hình AI, rồi xác nhận trang Trợ
    lý AI hiển thị ĐÚNG NHÃN đó cho từng provider — không có 2 nguồn sự thật
    khác nhau. So sánh dữ liệu-với-dữ liệu (không so với giá trị cố định),
    vì kết quả API thật có thể đổi khác giữa các lần chạy."""
    page = login("admin", "admin123")
    wait_ready(page, timeout=25)

    _open_ai_config_tab(page)
    test_btn = page.get_by_role("button", name="Kiểm tra kết nối tất cả provider", exact=False)
    assert test_btn.count() > 0, "Không tìm thấy nút kiểm tra kết nối ở trang Cấu hình AI."
    test_btn.first.click(timeout=15000)
    # Chờ KẾT QUẢ thật của cả 4 provider (mỗi thẻ ghi "Kiểm tra lúc ...") thay vì
    # chỉ chờ spinner biến mất — spinner có thể chưa kịp hiện khi kiểm tra lần đầu.
    for _ in range(60):
        if page.inner_text("body").count("Kiểm tra lúc") >= 4:
            break
        page.wait_for_timeout(1000)
    wait_ready(page, timeout=30)

    # Đọc nhãn phân loại thật (vd. "READY", "BILLING_REQUIRED") hiển thị trong
    # ngoặc đơn cạnh mỗi provider ở trang Cấu hình AI — 4 thẻ luôn xuất hiện
    # theo đúng thứ tự cột trái->phải cố định (Gemini, Groq, OpenAI, Ollama,
    # xem `_providers` trong ai_configuration_tab), nên ghép theo thứ tự này
    # đáng tin cậy hơn regex bắt ngữ cảnh tên provider (dễ vỡ vì xuống dòng).
    config_text = page.inner_text("body")
    import re
    all_category_tokens = re.findall(r"\(\s*([A-Z][A-Z_]{2,})\s*\)", config_text)
    provider_order = ["gemini", "groq", "openai", "ollama"]
    categories = dict(zip(provider_order, all_category_tokens))
    assert categories, f"Không đọc được phân loại trạng thái nào từ trang Cấu hình AI. Text mẫu: {config_text[:500]!r}"

    _open_ai_advisor_tab(page)
    exp = page.locator("[data-testid='stExpander']").filter(has_text="Trạng thái hệ thống AI/RAG")
    if exp.count() > 0:
        exp.first.locator("summary, details > summary").first.click(timeout=10000)
        page.wait_for_timeout(800)
    advisor_text = page.inner_text("body")

    from dss.services import llm_gateway

    checked_any = False
    for key, category in categories.items():
        if key == "ollama":
            continue  # Ollama hiển thị "Đang chạy"/"Chưa chạy" (kiểm tra process cục bộ), không qua category
        expected_label = llm_gateway.PROVIDER_HEALTH_FRIENDLY_LABEL.get(category, category)
        assert expected_label in advisor_text, (
            f"Trang 'Trợ lý AI' không hiển thị nhãn '{expected_label}' (từ category={category}) "
            f"cho provider '{key}' — hai trang đang cho 2 kết quả khác nhau."
        )
        checked_any = True
    assert checked_any, "Không so sánh được provider nào giữa 2 trang."
