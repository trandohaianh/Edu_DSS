"""Trang "Lịch sử tư vấn" — CHỈ Sinh viên (xem `dss/core/roles.py: TAB_ACCESS`).

Dựng từ dữ liệu thật do `warehouse.save_ai_consultation()` ghi lại mỗi lần
sinh viên dùng tab Tư vấn AI (`models.py`, đã được gọi thật từ trước, không
phải logic mới thêm cho trang này). Khoá cứng theo `current_student_id` —
1 sinh viên KHÔNG thể thấy lịch sử tư vấn của sinh viên khác, giữ đúng nguyên
tắc cách ly dữ liệu đã áp dụng ở các tab khác (Tư vấn AI, Dự đoán cá nhân...).
"""

from dss.config import *  # noqa: F403
from dss.tabs import ui_kit


def consultation_history_tab(warehouse, current_student_id=None):
    ui_kit.section_header(
        "Lịch sử tư vấn",
        subtitle="Các kế hoạch học tập AI đã tạo cho bạn — chỉ hiển thị đúng dữ liệu của bạn.",
        icon="📝",
    )

    if warehouse is None:
        st.error("Lỗi: Không thể khởi tạo kho dữ liệu.")
        return

    if not current_student_id:
        ui_kit.empty_state(
            "Không xác định được mã sinh viên của bạn.",
            hint="Vui lòng đăng nhập lại hoặc liên hệ Giảng viên/Admin.",
        )
        return

    all_consultations = warehouse.get_history("advisor", limit=10000)
    my_consultations = [c for c in all_consultations if str(c.get("student_id")) == str(current_student_id)]
    my_consultations.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    if not my_consultations:
        ui_kit.empty_state(
            "Bạn chưa có lượt tư vấn AI nào.",
            icon="📝",
            hint="Bắt đầu trò chuyện với trợ lý AI để nhận kế hoạch học tập đầu tiên.",
        )
        st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
        _col_cta_l, _col_cta_mid, _col_cta_r = st.columns([1, 1, 1])
        with _col_cta_mid:
            if st.button("Bắt đầu tư vấn AI", type="primary", width="stretch", key="ch_empty_cta"):
                st.session_state["_pending_nav_target"] = "🤖 Tư vấn — AI (LLM)"
                st.rerun()
        return

    ui_kit.kpi_row([("Tổng số lượt tư vấn", len(my_consultations))])
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    for c in my_consultations:
        gpa = c.get("predicted_gpa")
        gpa_label = f"GPA dự đoán: {gpa:.2f}" if isinstance(gpa, (int, float)) else "GPA dự đoán: —"
        with st.expander(f"🗓️ {c.get('created_at', 'Không rõ thời gian')} — {gpa_label}", expanded=False):
            st.caption(f"Nguồn AI: `{c.get('provider', 'unknown')}` · Model: `{c.get('model_name', '')}`")
            weaknesses = c.get("weaknesses") or []
            if weaknesses:
                st.markdown("**Điểm cần cải thiện:** " + ", ".join(str(w) for w in weaknesses))
            plan = c.get("generated_plan")
            if plan:
                st.markdown("**Kế hoạch học tập:**")
                st.markdown(plan)
            else:
                ui_kit.empty_state("Không có nội dung kế hoạch được lưu cho lượt này.")
