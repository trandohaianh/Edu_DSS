"""Bất biến cấu trúc: "Trang chủ" (home.py::render_lecturer_home) và
"Dashboard" (dashboard.py::main_dashboard_tab) của Giảng viên phải là 2 hàm
render ĐỘC LẬP — không route nào được là bí danh (alias) gọi thẳng hàm còn
lại. Trước bản sửa này, cả HOME_TAB_LABEL lẫn tab "Dashboard" đều gọi chung
`dashboard.main_dashboard_tab()`, khiến 2 trải nghiệm không thể phân biệt.

Kiểm tra ở tầng UNIT (đọc source code qua `inspect`), nhanh hơn nhiều so với
việc dựng trình duyệt thật chỉ để xác nhận 1 bất biến cấu trúc tĩnh — các bất
biến về NỘI DUNG hiển thị thật (hero/KPI/bảng...) đã có ở
`tests/e2e/test_role_flows.py` (test_lecturer_lands_on_home_after_login,
test_home_and_dashboard_render_distinct_content, ...).
"""

import inspect

from dss.tabs import dashboard, home


def test_render_lecturer_home_is_not_main_dashboard_tab():
    assert home.render_lecturer_home is not dashboard.main_dashboard_tab


def test_render_lecturer_home_does_not_delegate_to_main_dashboard_tab():
    # Chỉ kiểm tra LỜI GỌI thật (dấu "(" ngay sau tên hàm) — docstring của
    # hàm được PHÉP nhắc tên `main_dashboard_tab` để giải thích nó KHÔNG gọi
    # hàm đó, nên không thể chỉ tìm tên hàm xuất hiện dưới dạng chuỗi con.
    src = inspect.getsource(home.render_lecturer_home)
    assert "main_dashboard_tab(" not in src, (
        "render_lecturer_home() không được gọi main_dashboard_tab() — "
        "Trang chủ và Dashboard phải là 2 trải nghiệm render độc lập."
    )


def test_lecturer_home_dashboard_no_longer_exists():
    """Hàm cũ `_render_lecturer_home_dashboard` (bí danh gọi thẳng
    main_dashboard_tab) đã bị xoá hoàn toàn, không còn tồn tại để lỡ ai đó
    gọi nhầm lại."""
    assert not hasattr(home, "_render_lecturer_home_dashboard")


def test_dashboard_tab_label_renamed_and_distinct_from_home_label():
    from dss.core.roles import ALL_TABS, HOME_TAB_LABEL, TAB_ACCESS

    assert "📊 Dashboard" in ALL_TABS
    assert HOME_TAB_LABEL != "📊 Dashboard"
    assert TAB_ACCESS["📊 Dashboard"] == {"Giảng viên / CVHT"}
