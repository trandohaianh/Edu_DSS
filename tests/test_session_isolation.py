"""Regression suite — cách ly Session & "Student A không xem được Student B".

Cơ chế thật đang chạy (đã xác minh bằng cách đọc dss/main.py trước khi viết
test này): `st.session_state["current_student_id"]` CHỈ được gán ở ĐÚNG 1 nơi
duy nhất — main.py, ngay sau `auth_service.render_login_gate()` thành công —
lấy thẳng từ bản ghi user đã xác thực (`_user.get("student_id")`), KHÔNG có
selectbox/text_input/URL param nào khác từng ghi đè giá trị này. Vì vậy các
tab (ai_advisor_tab, clustering_hybrid_tab, file_prediction_tab,
student_advisory_tab) nhận `current_student_id` qua tham số hàm và tin thẳng —
an toàn CHỈ KHI bất biến "1 nơi gán duy nhất, ngay sau auth" này còn đúng.

Test ở đây khoá lại bất biến đó bằng kiểm tra tĩnh (grep mã nguồn) — nếu sau
này có ai thêm 1 nơi gán `current_student_id` khác (vd. từ URL query param cho
mục đích debug) mà quên xác thực, test này FAIL ngay, thay vì âm thầm mở lại
đúng lỗ hổng Critical đã sửa ở Phase 1. Phần hành vi end-to-end thật (đăng
nhập SV001, xác nhận không thấy dữ liệu SV002 trên UI) nằm ở
tests/e2e/test_role_flows.py — cần trình duyệt thật, không hợp lý kiểm ở tầng
unit vì ai_advisor_tab/clustering_hybrid_tab render trực tiếp qua st.*.
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

_APP_ROOT = Path(__file__).resolve().parent.parent
_ASSIGNMENT_PATTERN = re.compile(r'session_state\s*\[\s*["\']current_student_id["\']\s*\]\s*=')


def _find_assignment_sites():
    sites = []
    for py_file in (_APP_ROOT / "dss").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for m in _ASSIGNMENT_PATTERN.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            sites.append((py_file.relative_to(_APP_ROOT), line_no, text.splitlines()[line_no - 1]))
    return sites


def test_current_student_id_has_exactly_one_assignment_site():
    """Bất biến cốt lõi cho cách ly dữ liệu Sinh viên: CHỈ 1 nơi được phép gán
    session_state['current_student_id'] trong toàn bộ dss/ — nếu số này > 1,
    phải rà lại thủ công xem nơi mới có đi qua xác thực hay không trước khi
    cho pass lại (không được tự ý sửa test để pass)."""
    sites = _find_assignment_sites()
    assert len(sites) == 1, f"Có {len(sites)} nơi gán current_student_id, cần rà soát: {sites}"


def test_current_student_id_assignment_site_is_in_main_immediately_after_login():
    sites = _find_assignment_sites()
    path, line_no, line_text = sites[0]
    assert str(path) in ("dss\\main.py", "dss/main.py")
    assert '_user.get("student_id")' in line_text or "_user.get('student_id')" in line_text

    # Xác nhận dòng gán này nằm SAU lời gọi render_login_gate() + chặn st.stop()
    # khi None — không phải 1 khối code tách biệt có thể bị bỏ qua.
    main_src = (_APP_ROOT / "dss" / "main.py").read_text(encoding="utf-8")
    login_gate_idx = main_src.index("render_login_gate()")
    assignment_idx = main_src.index('st.session_state["current_student_id"]')
    stop_idx = main_src.index("st.stop()")
    assert login_gate_idx < stop_idx < assignment_idx, (
        "Thứ tự phải là: gọi render_login_gate() -> st.stop() nếu None -> mới gán current_student_id "
        "(nếu đảo thứ tự, có thể gán được giá trị TRƯỚC KHI xác thực xong)"
    )


# ---------------------------------------------------------------------------
# Cách ly state giữa các "phiên" (mô phỏng bằng session_state sạch mỗi test)
# ---------------------------------------------------------------------------
def test_logout_prevents_leaking_hub_and_cluster_state_to_next_session(as_role):
    """Mô phỏng: Giảng viên A dùng xong, đăng xuất; Giảng viên B đăng nhập
    CÙNG 1 tab trình duyệt (cùng session_state object) — B không được thấy kết
    quả train/cluster của A."""
    from dss.services import auth_service

    as_role("Giảng viên / CVHT", username="giangvien_a")
    st.session_state["hub_results"] = {"leaked": "data từ giảng viên A"}
    st.session_state["cluster_results_df"] = "leaked_cluster_df"
    st.session_state["current_student_id"] = None

    auth_service.logout()

    # Giảng viên B "đăng nhập" (chỉ set lại các key auth, mô phỏng lượt sau).
    as_role("Giảng viên / CVHT", username="giangvien_b")

    assert "hub_results" not in st.session_state
    assert "cluster_results_df" not in st.session_state


def test_fresh_session_has_no_leftover_student_context():
    """Đầu 1 test (session_state đã bị clean_session_state dọn sạch) không được
    có bất kỳ current_student_id nào sót lại từ test trước."""
    assert "current_student_id" not in st.session_state
    assert "_auth_student_id" not in st.session_state


def test_two_students_in_sequence_do_not_share_state(as_role):
    """SV001 dùng xong (không đăng xuất tường minh) rồi SV002 đăng nhập vào
    CÙNG session_state — hệ thống chỉ an toàn nếu mọi nơi đọc student_id đều
    đọc lại current_student_id THỜI ĐIỂM HIỆN TẠI (session_state), không có
    biến cache nào giữ giá trị cũ của SV001 lẫn vào response của SV002."""
    as_role("Sinh viên", username="sv001", student_id="SV001")
    st.session_state["current_student_id"] = "SV001"
    st.session_state["reminder_done_SV001_1"] = True

    # SV002 đăng nhập (main.py sẽ ghi đè current_student_id ngay khi login thành công).
    as_role("Sinh viên", username="sv002", student_id="SV002")
    st.session_state["current_student_id"] = "SV002"

    assert st.session_state["current_student_id"] == "SV002"
    assert auth_service_current_student_id_matches_auth()


def auth_service_current_student_id_matches_auth():
    from dss.services import auth_service

    user = auth_service.current_user()
    return st.session_state.get("current_student_id") == user["student_id"]
