"""Audit 2026-09-15 (Issue MODELREG-001) — warehouse.py đã ghi đúng 3 trạng
thái ('candidate' | 'production' | 'archived') vào field `status` từ trước,
nhưng UI (dss/tabs/warehouse_tab.py) chỉ đọc field nhị phân `is_production`,
gộp 'candidate' (chưa từng duyệt) và 'archived' (từng Production, đã bị thay
thế) thành cùng 1 nhãn "Lưu trữ" — mất thông tin đã có sẵn. Test khoá lại
hành vi ĐÚNG của `_model_lifecycle_badge_text()` sau khi sửa.
"""
from __future__ import annotations

import inspect

from dss.tabs.warehouse_tab import _model_lifecycle_badge_text


def test_production_status_shows_production_badge():
    model = {"status": "production", "is_production": True}
    assert "Production" in _model_lifecycle_badge_text(model)


def test_candidate_status_distinguished_from_archived():
    candidate = {"status": "candidate", "is_production": False}
    archived = {"status": "archived", "is_production": False}
    candidate_label = _model_lifecycle_badge_text(candidate)
    archived_label = _model_lifecycle_badge_text(archived)
    assert candidate_label != archived_label
    assert "Candidate" in candidate_label or "Chờ duyệt" in candidate_label
    assert "Lưu trữ" in archived_label


def test_is_production_true_wins_even_if_status_field_disagrees():
    """is_production=True là NGUỒN SỰ THẬT cuối cùng (được set_production_model
    cập nhật đồng thời với status) — nếu 2 field lỡ lệch nhau, tin is_production."""
    model = {"status": "candidate", "is_production": True}
    assert "Production" in _model_lifecycle_badge_text(model)


def test_legacy_record_without_status_field_falls_back_safely():
    """Record cũ (trước khi field `status` tồn tại) không có key này — KHÔNG
    được suy diễn/bịa, chỉ fallback về is_production nhị phân như hành vi cũ."""
    legacy_production = {"is_production": True}
    legacy_archived = {"is_production": False}
    assert "Production" in _model_lifecycle_badge_text(legacy_production)
    assert "Lưu trữ" in _model_lifecycle_badge_text(legacy_archived)
    assert "Candidate" not in _model_lifecycle_badge_text(legacy_archived)


def test_single_shared_definition_reused_by_warehouse_tab_and_admin_reports():
    """Audit 2026-09-15 (follow-up): 'Mô hình theo trạng thái' ở admin_reports.py
    (Báo cáo hệ thống) trước đây dùng lại logic nhị phân is_production riêng,
    khiến biểu đồ đó gộp nhầm Candidate vào Lưu trữ trong khi bảng Model
    Registry (warehouse_tab.py) đã hiển thị đúng 3 trạng thái — không nhất
    quán giữa 2 trang cùng hiển thị 1 khái niệm. Cả 2 giờ phải dùng chung
    đúng 1 định nghĩa ở model_service.py."""
    from dss.services.model_service import model_lifecycle_badge_text
    from dss.tabs import warehouse_tab, admin_reports

    assert warehouse_tab._model_lifecycle_badge_text is model_lifecycle_badge_text
    source = inspect.getsource(admin_reports)
    assert "model_lifecycle_badge_text(m)" in source
    assert 'if m.get("is_production") else' not in source


def test_no_ui_text_claims_training_auto_promotes_to_production():
    """Lecturer Product Acceptance audit (2026-09): tìm thấy qua ảnh chụp
    màn hình thật (không chỉ đọc code) rằng trang 'Quan ly mo hinh' (Model
    Registry, warehouse_tab.py) tự mâu thuẫn với chính nó -- 1 dong text noi
    "Model moi huan luyen tot nhat tu dong thanh Production" trong khi dong
    khac cùng file lại nói "KHONG BAO GIO tu dong len Production". Hành vi
    THẬT (warehouse.py::save_model_training, ml_hub.py's real call site
    passing auto_promote=False explicitly) khớp với vế "khong tu dong" --
    dashboard.py và model_registry.py cũng có cùng câu sai tương tự, đã sửa
    cả 3 nơi để không còn nơi nào tuyên bố auto-promotion diễn ra."""
    import inspect
    from dss.tabs import warehouse_tab, dashboard
    from dss.services import model_registry

    for module in (warehouse_tab, dashboard, model_registry):
        source = inspect.getsource(module)
        assert "tự động thành Production" not in source, f"{module.__name__} vẫn còn câu sai"
        idx = source.find("tự động lên Production")
        assert idx == -1 or "không" in source[max(0, idx - 40):idx].lower(), (
            f"{module.__name__}: 'tự động lên Production' phải luôn đi kèm phủ định 'không' ngay trước nó"
        )
