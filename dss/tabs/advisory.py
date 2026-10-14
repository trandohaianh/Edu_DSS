"""Tư vấn — Định hướng nghề nghiệp (Career Decision Support System - EduDSS).

REDESIGN TOÀN DIỆN:
Biến module hướng nghiệp thành một Career Decision Support System (CDSS) hoàn chỉnh,
trả lời trọn vẹn 9 câu hỏi cốt lõi của người học:
1. Tôi phù hợp nghề nào? (Top 3-5 roles với Career Fit độc lập)
2. Vì sao tôi phù hợp? (Bóc tách minh chứng từ học thuật, kỹ năng, dự án, sở thích)
3. Tôi đang sẵn sàng đến mức nào? (Chỉ số Career Readiness 0-100%)
4. Tôi còn thiếu kỹ năng gì? (Gap Analysis: Đã có / Cần củng cố / Chưa có; Phân cấp Critical -> Nice)
5. Nghề nào phù hợp năng lực nhưng không phù hợp điều kiện cá nhân? (Capability vs Constraint conflict)
6. Nếu muốn theo nghề đó thì phải học gì? (Task cụ thể có tài nguyên, nỗ lực và kết quả đo lường)
7. Tôi cần làm gì trong 1 tháng / 3 tháng / 6 tháng? (Lộ trình cá nhân hoá theo 30/90/180 ngày)
8. Tôi có thể chuyển từ nghề A sang nghề B như thế nào? (Transition: Shared & Missing skills, Feasibility)
9. Nếu mục tiêu hoặc điều kiện thay đổi thì khuyến nghị thay đổi ra sao? (What-if simulation & Feedback loop)
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dss.config import *  # noqa: F403
from dss.core.data_helpers import is_production_environment as _is_production_environment
from dss.tabs import ui_kit

from dss.services.career_profile import (
    ALL_SKILL_CATALOG,
    EXPERIENCE_TYPES,
    INTEREST_AXES,
    SKILL_LEVELS,
    WORK_STYLE_AXES,
    ExperienceItem,
    StudentCareerProfile,
)
from dss.services.career_knowledge_base import CareerRole, get_role, list_roles
from dss.services.career_scoring import (
    compute_career_fit,
    compute_career_readiness,
    detect_capability_vs_constraint_conflicts,
    rank_careers,
)
from dss.services.career_gap_analysis import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_NICE,
    STATUS_HAVE,
    STATUS_MISSING,
    STATUS_STRENGTHEN,
    compute_gap_analysis,
    group_gap_by_status,
)
from dss.services.career_roadmap import (
    _BUCKET_1M,
    _BUCKET_3M,
    _BUCKET_6M,
    compute_transition,
    generate_roadmap,
    suggest_alternative_paths,
)
from dss.services.career_whatif import (
    apply_constraint_change,
    apply_skill_change,
    compare_scenarios,
    filter_roles_by_constraint,
    rank_roles_for_timeframe,
)
from dss.services.career_ai_advisor import (
    build_career_ai_context,
    generate_offline_grounded_answer,
    get_system_prompt,
)
from dss.services.lms_connector import (
    BaseLMSRepository,
    STATUS_DEMO,
    STATUS_FUTURE_REAL,
    STATUS_IMPLEMENTED,
    STATUS_PARTIAL,
    get_lms_repository,
)
from dss.services.cms_repository import (
    BaseCMSRepository,
    get_cms_repository,
)
from dss.services.career_lms_cms_pipeline import (
    ClosedLoopActionResult,
    TracedGapItem,
    compute_traced_gap_analysis,
    enrich_career_profile_with_lms_cms,
    execute_closed_loop_action,
    generate_traced_roadmap,
)

_STATUS_ICON = {STATUS_HAVE: "✅", STATUS_STRENGTHEN: "🔶", STATUS_MISSING: "✕"}
_PRIORITY_BADGE_KIND = {
    PRIORITY_CRITICAL: "danger",
    PRIORITY_HIGH: "warning",
    PRIORITY_MEDIUM: "neutral",
    PRIORITY_NICE: "success",
}


def _gap_size_label(gaps) -> str:
    critical_or_high = sum(1 for g in gaps if g.priority in (PRIORITY_CRITICAL, PRIORITY_HIGH) and g.status != STATUS_HAVE)
    if critical_or_high == 0:
        return "Nhỏ"
    if critical_or_high <= 2:
        return "Trung bình"
    return "Lớn"


def _profile_state_key(selected_id) -> str:
    return f"career_profile_{selected_id}"


def _get_or_build_profile(selected_id, raw_row: dict, data_source: str) -> StudentCareerProfile:
    key = _profile_state_key(selected_id)
    if key not in st.session_state:
        st.session_state[key] = StudentCareerProfile.build_from_row(str(selected_id), raw_row, data_source=data_source)
    return st.session_state[key]


# ============================================================================
# TAB 1 — HỒ SƠ NGHỀ NGHIỆP CỦA BẠN
# ============================================================================
def _render_profile_section(profile: StudentCareerProfile) -> None:
    # 1. Header & Data Source Status
    c_status, c_comp = st.columns([1, 2])
    with c_status:
        if profile.data_source == "DEMO":
            ui_kit.render_badge("Hồ sơ minh họa (dữ liệu mô phỏng)", kind="warning")
            st.caption("Dữ liệu được mô phỏng cho mục đích tham quan hệ thống.")
        else:
            ui_kit.render_badge("Dữ liệu học tập thực tế", kind="success")
            st.caption("Dữ liệu trích xuất từ hệ thống quản lý học tập (LMS).")

    with c_comp:
        completeness = profile.profile_completeness()
        n_filled = sum(1 for v in completeness.values() if v)
        st.progress(n_filled / len(completeness), text=f"Mức độ hoàn thiện hồ sơ: {n_filled}/{len(completeness)} mảng dữ liệu")

    # 1.1 Dữ liệu gắn kết & Năng lực thực tế từ LMS
    lms = get_lms_repository()
    lms_summary = lms.get_student_learning_summary(profile.student_pseudonym)
    st.markdown("#### 🏫 Năng lực & Gắn kết học tập thực tế")
    lm1, lm2, lm3, lm4 = st.columns(4)
    with lm1:
        st.metric("Tỷ lệ chuyên cần", f"{lms_summary.average_attendance:.1f}%")
    with lm2:
        st.metric("Tiến độ hoàn thành", f"{lms_summary.average_progress:.1f}%")
    with lm3:
        st.metric("Tổng giờ học tích lũy", f"{lms_summary.total_learning_hours:.1f} giờ")
    with lm4:
        st.metric("Xu hướng phong độ", lms_summary.performance_trend)

    with st.expander(f"📋 Bằng chứng học tập xác thực từ LMS ({len(lms_summary.evidences)} sự kiện ghi nhận)", expanded=False):
        for ev in lms_summary.evidences:
            st.markdown(f"- `{ev}`")

    st.markdown("---")

    # 2. Hồ sơ học thuật
    st.markdown("#### 1. Hồ sơ học thuật (Tự động từ điểm chuyên đề)")
    st.caption("Điểm số được ánh xạ sang các miền năng lực (Competency Domains) — không dùng GPA tổng một cách máy móc.")
    if profile.academic.domain_scores:
        cols = st.columns(len(profile.academic.domain_scores) + 1)
        with cols[0]:
            st.metric("GPA Tổng quan", f"{profile.academic.gpa:.2f}/10")
        for col, (domain, score) in zip(cols[1:], profile.academic.domain_scores.items()):
            with col:
                st.metric(domain, f"{score:.1f}/10")

        c_str, c_weak = st.columns(2)
        with c_str:
            if profile.academic.strengths:
                st.info(f"🌟 **Thế mạnh học thuật (>= 7.0):** {', '.join(profile.academic.strengths)}")
            else:
                st.caption("Chưa có môn học nào đạt trên 7.0 để xem là thế mạnh.")
        with c_weak:
            if profile.academic.weaknesses:
                st.warning(f"⚠️ **Môn cần củng cố (< 5.5):** {', '.join(profile.academic.weaknesses)}")
            else:
                st.success("Không có miền năng lực nào bị điểm yếu dưới 5.5.")
    else:
        ui_kit.empty_state("Chưa có dữ liệu điểm chuyên đề để suy ra năng lực học thuật.", icon="📭")

    st.markdown("---")

    # 3. Hồ sơ kỹ năng
    st.markdown("#### 2. Kỹ năng cá nhân & Bằng chứng thực tế")
    st.caption(
        "Hệ thống KHÔNG tự khẳng định bạn có kỹ năng nếu không có minh chứng. "
        "Điểm học thuật cao chỉ cấp chứng cứ mức gián tiếp (Basic). Hãy tự đánh giá thêm:"
    )

    for category, skills in ALL_SKILL_CATALOG.items():
        with st.expander(f"{category.upper()} SKILLS ({len(skills)} kỹ năng)", expanded=(category == "technical")):
            cols = st.columns(3)
            for i, skill_name in enumerate(skills):
                with cols[i % 3]:
                    current = profile.skills.get(skill_name)
                    idx = SKILL_LEVELS.index(current.skill_level) if current.skill_level in SKILL_LEVELS else 0
                    new_level = st.select_slider(
                        skill_name,
                        options=SKILL_LEVELS,
                        value=SKILL_LEVELS[idx],
                        key=f"skill_slider_{skill_name}",
                    )
                    if current.evidence:
                        st.caption(f"📎 Minh chứng: {current.evidence[-1]}")
                    if current.confidence != "low":
                        st.caption(f"Độ tin cậy: **{current.confidence.upper()}** (Nguồn: {current.source})")
                    if new_level != current.skill_level:
                        profile.skills.upsert_self_assessment(skill_name, category, new_level)

    st.markdown("---")

    # 4. Kinh nghiệm & Tạo tác nghề nghiệp
    st.markdown("#### 3. Kinh nghiệm thực tế & Dự án Portfolio")
    st.caption("Dự án, khoá luận, chứng chỉ hoặc kỳ thực tập là bằng chứng mạnh mẽ nhất nâng độ tin cậy của kỹ năng.")

    c_flags1, c_flags2 = st.columns(2)
    with c_flags1:
        has_portfolio = st.checkbox(
            "📂 Đã có liên kết Portfolio / Sản phẩm thực tế công khai (GitHub / Kaggle)",
            value=profile.experience.has_portfolio(),
            key="chk_profile_portfolio",
        )
        profile.experience.has_portfolio_flag = has_portfolio
    with c_flags2:
        is_interview_ready = st.checkbox(
            "💼 Đã có kinh nghiệm phỏng vấn tuyển dụng / đi làm thực tế",
            value=profile.experience.is_interview_ready(),
            key="chk_profile_interview",
        )
        profile.experience.interview_ready_flag = is_interview_ready

    with st.form("career_experience_form_redesign", clear_on_submit=True):
        st.markdown("##### ➕ Thêm mục kinh nghiệm / dự án mới:")
        c1, c2 = st.columns(2)
        with c1:
            exp_type = st.selectbox("Loại hình", EXPERIENCE_TYPES, key="exp_type_input")
            exp_title = st.text_input("Tên hoạt động (vd: 'Dự án ML dự đoán điểm')", key="exp_title_input")
            artifact_url = st.text_input("Đường dẫn chứng chỉ/GitHub (tuỳ chọn)", key="exp_url_input")
        with c2:
            related_skills = st.multiselect(
                "Kỹ năng được minh chứng qua hoạt động này",
                [s for skills in ALL_SKILL_CATALOG.values() for s in skills],
                key="exp_skills_input",
            )
            exp_desc = st.text_area("Mô tả ngắn gọn kết quả / công nghệ sử dụng", key="exp_desc_input")

        if st.form_submit_button("Lưu hoạt động vào hồ sơ") and exp_title:
            profile.experience.items.append(ExperienceItem(
                exp_type=exp_type,
                title=exp_title,
                related_skills=related_skills,
                description=exp_desc,
                artifact_url=artifact_url,
            ))
            for skill_name in related_skills:
                cat = next((c for c, sk in ALL_SKILL_CATALOG.items() if skill_name in sk), "technical")
                profile.skills.add_evidence_from_experience(
                    skill_name, cat, f"{exp_type.capitalize()}: {exp_title}", min_level="Basic",
                )
            st.success(f"Đã cập nhật '{exp_title}' và nâng độ tin cậy cho các kỹ năng liên quan!")
            st.rerun()

    if profile.experience.items:
        st.markdown("###### Các hoạt động đã ghi nhận:")
        for idx, it in enumerate(profile.experience.items):
            url_part = f" — 🔗 [Xem liên kết]({it.artifact_url})" if it.artifact_url else ""
            st.caption(f"• **[{it.exp_type.upper()}]** {it.title}{url_part} (Kỹ năng: {', '.join(it.related_skills) if it.related_skills else 'Không gắn'})")
    else:
        st.caption("Chưa có mục kinh nghiệm nào trong hồ sơ.")

    st.markdown("---")

    # 5. Khảo sát sở thích (7 trục)
    st.markdown("#### 4. Khảo sát sở thích nghề nghiệp (Mini Career Assessment)")
    st.caption("Đánh giá mức độ hứng thú từ 1 (Rất không thích) đến 5 (Rất thích):")
    cols_int = st.columns(4)
    for i, (axis_key, axis_label) in enumerate(INTEREST_AXES.items()):
        with cols_int[i % 4]:
            val = profile.interest.get_score(axis_key)
            profile.interest.scores[axis_key] = st.slider(axis_label, 1, 5, val, key=f"interest_sl_{axis_key}")

    st.markdown("---")

    # 6. Phong cách làm việc
    st.markdown("#### 5. Phong cách làm việc mong muốn")
    st.caption("Chọn điểm cân bằng giữa hai thái cực (1 = Nghiêng hẳn bên trái, 5 = Nghiêng hẳn bên phải):")
    cols_ws = st.columns(2)
    for i, (axis_key, (left_l, right_l)) in enumerate(WORK_STYLE_AXES.items()):
        with cols_ws[i % 2]:
            cur_ws = profile.work_style.preferences.get(axis_key, 3)
            profile.work_style.preferences[axis_key] = st.slider(
                f"{left_l}  ↔  {right_l}", 1, 5, cur_ws, key=f"ws_sl_{axis_key}",
            )

    st.markdown("---")

    # 7. Ràng buộc cá nhân & Mục tiêu
    st.markdown("#### 6. Ràng buộc cá nhân & Mục tiêu nghề nghiệp")
    c1, c2, c3 = st.columns(3)
    with c1:
        profile.constraints.desired_location = st.text_input("Địa điểm làm việc mong muốn", value=profile.constraints.desired_location, key="con_loc")
        profile.constraints.willing_to_relocate = st.checkbox("Sẵn sàng chuyển nơi sinh sống nếu có cơ hội tốt", value=profile.constraints.willing_to_relocate, key="con_reloc")
        profile.constraints.preferred_hours = st.radio(
            "Giờ làm việc ưu tiên",
            ["office_hours", "shift_ok"],
            index=0 if profile.constraints.preferred_hours == "office_hours" else 1,
            format_func=lambda x: "Giờ hành chính cố định" if x == "office_hours" else "Linh hoạt ca kíp",
            key="con_hours",
        )
        profile.constraints.shift_acceptance = st.checkbox("Chấp nhận làm ca kíp / trực đêm", value=profile.constraints.shift_acceptance, key="con_shift")
    with c2:
        profile.constraints.remote_preference = st.selectbox(
            "Hình thức làm việc mong muốn",
            ["flexible", "remote", "on_site"],
            index=["flexible", "remote", "on_site"].index(profile.constraints.remote_preference),
            format_func=lambda x: {"flexible": "Linh hoạt (Hybrid)", "remote": "Từ xa hoàn toàn (Remote)", "on_site": "Tại văn phòng (On-site)"}[x],
            key="con_remote",
        )
        profile.constraints.english_level = st.selectbox(
            "Trình độ tiếng Anh hiện tại",
            ["Beginner", "Intermediate", "Advanced", "Fluent"],
            index=["Beginner", "Intermediate", "Advanced", "Fluent"].index(profile.constraints.english_level),
            key="con_eng",
        )
        profile.constraints.expected_salary_band = st.text_input("Mức lương kỳ vọng", value=profile.constraints.expected_salary_band, key="con_salary")
    with c3:
        profile.constraints.learning_hours_per_week = st.number_input(
            "Thời gian học thêm mỗi tuần (giờ)", min_value=0.0, max_value=50.0, value=float(profile.constraints.learning_hours_per_week), key="con_learn_h",
        )
        profile.goal.goal_type = st.selectbox(
            "Loại mục tiêu ứng tuyển",
            ["Internship", "Fresher job", "Junior role", "Career switching", "Long-term career"],
            index=["Internship", "Fresher job", "Junior role", "Career switching", "Long-term career"].index(profile.goal.goal_type),
            key="goal_type_sel",
        )
        profile.goal.target_timeframe_months = st.slider("Thời gian mong muốn đạt mục tiêu (tháng)", 1, 24, profile.goal.target_timeframe_months, key="goal_time_sl")


# ============================================================================
# TAB 2 — NGHỀ PHÙ HỢP & KHUYẾN NGHỊ
# ============================================================================
def _render_matching_section(profile: StudentCareerProfile, ranked) -> None:
    if not ranked:
        ui_kit.empty_state("Chưa có đủ dữ liệu để xếp hạng nghề nghiệp.", icon="📭")
        return

    fit0, _ = ranked[0]
    conf_kind = {"High": "success", "Medium": "warning", "Low": "danger"}.get(fit0.confidence, "neutral")

    c_conf, c_disc = st.columns([1, 2])
    with c_conf:
        st.markdown("**Độ tin cậy của khuyến nghị:**")
        ui_kit.render_badge(fit0.confidence, kind=conf_kind)
        st.caption(fit0.confidence_reason)
    with c_disc:
        st.info(
            "💡 **Lưu ý nguyên tắc:** Đây là điểm số heuristic hỗ trợ ra quyết định (quy tắc tính minh bạch, có thể truy vết nguồn gốc), "
            "KHÔNG phải xác suất nghề nghiệp tuyệt đối. Career Fit phản ánh độ phù hợp tổng thể; Career Readiness phản ánh mức sẵn sàng xin việc ngay bây giờ."
        )

    st.markdown("---")

    # Cảnh báo xung đột Năng lực cao vs Vướng ràng buộc (Câu hỏi 5)
    conflicts = detect_capability_vs_constraint_conflicts(profile, list_roles())
    if conflicts:
        with st.expander("⚠️ Nghề phù hợp năng lực nhưng vướng ràng buộc cá nhân (Câu hỏi 5)", expanded=True):
            st.markdown("Các nghề sau đây bạn có **năng lực học thuật & kỹ năng tốt** (>= 60%), nhưng đang bị vướng các điều kiện cá nhân (ca kíp / địa điểm / tiếng Anh):")
            for c_item in conflicts:
                st.markdown(f"- **{c_item.role_name}**: Năng lực **{c_item.capability_score:.1f}%**, nhưng Ràng buộc chỉ đạt **{c_item.constraint_score:.1f}%**")
                for r_reason in c_item.conflict_reasons:
                    st.caption(f"  • {r_reason}")

    col_t5_head, col_t5_dl = st.columns([3, 2], vertical_alignment="center")
    with col_t5_head:
        st.markdown("#### Top 5 nghề nghiệp phù hợp nhất với bạn:")
    with col_t5_dl:
        if ranked:
            top_fit, top_readiness = ranked[0]
            _top_strengths = []
            for dim_k, dim_res in top_fit.breakdown.items():
                if dim_res.score >= 0.6:
                    _top_strengths.extend(dim_res.evidence[:2])
            try:
                from dss.services.pdf_certificate_service import generate_career_passport_pdf
                _gaps_top = compute_gap_analysis(profile, get_role(top_fit.role_id))
                pdf_data = generate_career_passport_pdf(
                    student_id=str(profile.student_pseudonym or "SV2025"),
                    target_role=top_fit.role_name,
                    career_fit_score=float(top_fit.fit_score),
                    career_readiness_score=float(top_readiness.readiness_score),
                    gap_size=_gap_size_label(_gaps_top),
                    key_strengths=_top_strengths[:3] if _top_strengths else None,
                )
                st.download_button(
                    label="📜 Xuất Bằng Chứng Nhận (PDF)",
                    data=pdf_data,
                    file_name=f"Career_Passport_{profile.student_pseudonym}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_career_passport_btn",
                )
            except Exception:
                pass

    for rank_idx, (fit, readiness) in enumerate(ranked, start=1):
        role = get_role(fit.role_id)
        gaps = compute_gap_analysis(profile, role)
        gap_size = _gap_size_label(gaps)

        with st.container(border=True):
            r_head1, r_head2 = st.columns([3, 1])
            with r_head1:
                st.markdown(f"### {rank_idx}. {fit.role_name}")
                st.caption(role.description)
            with r_head2:
                ui_kit.render_badge(f"Khoảng cách kỹ năng: {gap_size}", kind="neutral" if gap_size == "Nhỏ" else "warning")

            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Career Fit",
                f"{fit.fit_score:.1f}%",
                help="Mức độ phù hợp với năng lực học tập, kỹ năng, sở thích và điều kiện của bạn.",
            )
            m2.metric(
                "Career Readiness",
                f"{readiness.readiness_score:.1f}%",
                help="Mức độ SẴN SÀNG ứng tuyển vị trí này NGAY BÂY GIỜ dựa trên kỹ năng thực tế, dự án và portfolio.",
            )
            gap_badge_color = {"Nhỏ": "✅ Nhỏ", "Trung bình": "🔶 Trung bình", "Lớn": "✕ Lớn"}.get(gap_size, gap_size)
            m3.metric("Mức độ chênh lệch", gap_badge_color)

            with st.expander(f"🔍 Vì sao nghề {fit.role_name} phù hợp với bạn? (Bóc tách chi tiết)"):
                c_str_box, c_weak_box = st.columns(2)
                with c_str_box:
                    st.markdown("**🌟 Điểm mạnh & Minh chứng thực tế:**")
                    any_strong = False
                    for dim_key, dim_result in fit.breakdown.items():
                        if dim_result.score >= 0.6:
                            any_strong = True
                            for ev in dim_result.evidence[:3]:
                                st.caption(f"✓ [{dim_key.upper()}] {ev}")
                    if not any_strong:
                        st.caption("Chưa có mảng nào nổi trội rõ rệt.")

                with c_weak_box:
                    st.markdown("**⚠️ Thách thức & Điểm chưa tương thích:**")
                    any_weak = False
                    for dim_key, dim_result in fit.breakdown.items():
                        if dim_result.score < 0.5:
                            any_weak = True
                            for ev in dim_result.evidence[:3]:
                                st.caption(f"✕ [{dim_key.upper()}] {ev}")
                    if not any_weak:
                        st.caption("Không có xung đột nào đáng kể giữa bạn và nghề này!")


# ============================================================================
# TAB 3 — SO SÁNH NGHỀ
# ============================================================================
def _render_comparison_section(profile: StudentCareerProfile, ranked) -> None:
    if not ranked:
        ui_kit.empty_state("Chưa có dữ liệu để so sánh.", icon="📭")
        return

    role_names = [fit.role_name for fit, _ in ranked]
    chosen = st.multiselect(
        "Chọn tối đa 3 nghề nghiệp để so sánh đối đầu:",
        role_names,
        default=role_names[:min(3, len(role_names))],
        max_selections=3,
        key="career_compare_pick_v2",
    )
    if not chosen:
        st.info("Vui lòng chọn ít nhất 1 nghề để xem bảng so sánh.")
        return

    chosen_pairs = [(fit, ready) for fit, ready in ranked if fit.role_name in chosen]
    all_req_skills = set()
    role_objs = {}
    for fit, _ in chosen_pairs:
        role = get_role(fit.role_id)
        role_objs[fit.role_name] = role
        all_req_skills.update(role.required_skills.keys())

    header = ["Chỉ số / Tiêu chí"] + [fit.role_name for fit, _ in chosen_pairs]
    rows = []
    rows.append(["Career Fit (Phù hợp)"] + [f"{fit.fit_score:.1f}%" for fit, _ in chosen_pairs])
    rows.append(["Career Readiness (Sẵn sàng)"] + [f"{ready.readiness_score:.1f}%" for _, ready in chosen_pairs])
    rows.append(["Khoảng cách kỹ năng"] + [_gap_size_label(compute_gap_analysis(profile, role_objs[fit.role_name])) for fit, _ in chosen_pairs])
    rows.append(["Yêu cầu tiếng Anh"] + [role_objs[fit.role_name].minimum_english for fit, _ in chosen_pairs])
    rows.append(["Giờ làm việc"] + [("Giờ hành chính" if role_objs[fit.role_name].preferred_hours == "office_hours" else "Làm ca/trực") for fit, _ in chosen_pairs])
    rows.append(["Hình thức làm việc"] + [role_objs[fit.role_name].remote_friendly for fit, _ in chosen_pairs])

    # Kỹ năng yêu cầu chi tiết
    for sk in sorted(all_req_skills):
        row = [f"Kỹ năng: {sk}"]
        for fit, _ in chosen_pairs:
            role = role_objs[fit.role_name]
            if sk in role.required_skills:
                w = role.required_skills[sk]
                achieved = profile.skills.get(sk).skill_level
                row.append(f"{achieved} (Cần: {w:.1f})")
            else:
                row.append("—")
        rows.append(row)

    df_compare = pd.DataFrame(rows, columns=header).set_index("Chỉ số / Tiêu chí")
    st.dataframe(df_compare, width="stretch")


# ============================================================================
# TAB 4 — KHOẢNG CÁCH KỸ NĂNG (GAP ANALYSIS)
# ============================================================================
def _render_gap_section(profile: StudentCareerProfile, ranked, lms_repo: Optional[BaseLMSRepository] = None, cms_repo: Optional[BaseCMSRepository] = None) -> str | None:
    if not ranked:
        ui_kit.empty_state("Chưa có dữ liệu để phân tích khoảng cách kỹ năng.", icon="📭")
        return None

    lms = lms_repo or get_lms_repository()
    cms = cms_repo or get_cms_repository()

    role_options = {fit.role_name: fit.role_id for fit, _ in ranked}
    chosen_name = st.selectbox("Chọn nghề mục tiêu để soi chi tiết khoảng cách kỹ năng:", list(role_options.keys()), key="gap_role_pick_v2")
    role_id = role_options[chosen_name]
    role = get_role(role_id)
    gaps = compute_traced_gap_analysis(profile, role, lms_repo=lms, cms_repo=cms, include_artifacts=True)
    grouped = group_gap_by_status(gaps)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### ✅ ĐÃ CÓ")
        st.caption("Đã đạt mức Intermediate trở lên hoặc có minh chứng rõ ràng:")
        if grouped[STATUS_HAVE]:
            for g in grouped[STATUS_HAVE]:
                with st.container(border=True):
                    st.markdown(f"**✓ {g.skill_name}**")
                    st.caption(f"Hiện tại: `{g.current_level}` ({'Bắt buộc' if g.is_required else 'Nên có'})")
                    if isinstance(g, TracedGapItem) and g.lms_evidence:
                        st.info(f"🔍 **LMS:** {g.lms_evidence}")
        else:
            st.caption("Chưa có kỹ năng nào đạt yêu cầu độc lập.")

    with c2:
        st.markdown("### 🔶 CẦN CỦNG CỐ")
        st.caption("Mới ở mức Basic hoặc chỉ có bằng chứng gián tiếp từ môn học:")
        if grouped[STATUS_STRENGTHEN]:
            for g in grouped[STATUS_STRENGTHEN]:
                with st.container(border=True):
                    ui_kit.render_badge(g.priority, kind=_PRIORITY_BADGE_KIND.get(g.priority, "neutral"))
                    st.markdown(f"**△ {g.skill_name}**")
                    st.caption(f"Cần nâng từ `{g.current_level}` lên `Intermediate` (Trọng số: {g.weight:.1f})")
                    if isinstance(g, TracedGapItem):
                        if g.lms_evidence:
                            st.warning(f"🔍 {g.lms_evidence}")
                        if g.cms_match:
                            st.success(
                                f"📦 **[CMS]** `{g.cms_match.course_code}` — {g.cms_match.module_title}\n\n"
                                f"📖 **Bài học:** {g.cms_match.lesson_title}  |  ⏱️ **Nỗ lực:** {g.cms_match.estimated_hours:.0f}h\n\n"
                                f"🎯 **Hành động đề xuất:** *\"{g.cms_recommendation_action}\"*"
                            )
        else:
            st.caption("Không có kỹ năng nào ở mức trung gian.")

    with c3:
        st.markdown("### ✕ CHƯA CÓ")
        st.caption("Chưa từng học hoặc chưa có bằng chứng thực tế trong hồ sơ:")
        if grouped[STATUS_MISSING]:
            for g in grouped[STATUS_MISSING]:
                with st.container(border=True):
                    ui_kit.render_badge(g.priority, kind=_PRIORITY_BADGE_KIND.get(g.priority, "neutral"))
                    st.markdown(f"**✕ {g.skill_name}**")
                    st.caption(f"Mức độ ưu tiên: `{g.priority}` ({'Bắt buộc' if g.is_required else 'Nên có'})")
                    if isinstance(g, TracedGapItem):
                        if g.lms_evidence:
                            st.error(f"🔍 {g.lms_evidence}")
                        if g.cms_match:
                            st.success(
                                f"📦 **[CMS]** `{g.cms_match.course_code}` — {g.cms_match.module_title}\n\n"
                                f"📖 **Bài học:** {g.cms_match.lesson_title}  |  ⏱️ **Nỗ lực:** {g.cms_match.estimated_hours:.0f}h\n\n"
                                f"🎯 **Hành động đề xuất:** *\"{g.cms_recommendation_action}\"*"
                            )
        else:
            st.success("Tuyệt vời! Bạn không thiếu kỹ năng cơ bản nào.")

    return role_id


# ============================================================================
# TAB 5 — LỘ TRÌNH PHÁT TRIỂN & CHUYỂN NGHỀ
# ============================================================================
def _render_roadmap_section(
    profile: StudentCareerProfile,
    ranked,
    default_role_id: str | None,
    lms_repo: Optional[BaseLMSRepository] = None,
    cms_repo: Optional[BaseCMSRepository] = None,
    selected_id: str = "",
) -> None:
    if not ranked:
        ui_kit.empty_state("Chưa có dữ liệu để lập lộ trình học tập.", icon="📭")
        return

    lms = lms_repo or get_lms_repository()
    cms = cms_repo or get_cms_repository()

    role_options = {fit.role_name: fit.role_id for fit, _ in ranked}
    default_name = next((n for n, rid in role_options.items() if rid == default_role_id), list(role_options.keys())[0])
    chosen_name = st.selectbox(
        "Lộ trình phát triển cho nghề mục tiêu:",
        list(role_options.keys()),
        index=list(role_options.keys()).index(default_name),
        key="roadmap_role_pick_v2",
    )
    role_id = role_options[chosen_name]
    role = get_role(role_id)
    readiness = next(r.readiness_score for f, r in ranked if f.role_id == role_id)

    st.markdown(f"🎯 **TARGET ROLE:** `{role.role_name}`  |  📊 **CURRENT READINESS:** `{readiness:.1f}%`")
    roadmap = generate_traced_roadmap(profile, role, readiness, lms_repo=lms, cms_repo=cms)

    # 3 Cột mốc: 1 tháng / 3 tháng / 6 tháng
    for bucket_name in (_BUCKET_1M, _BUCKET_3M, _BUCKET_6M):
        tasks = roadmap.buckets.get(bucket_name, [])
        if not tasks:
            continue
        st.markdown(f"#### 📅 {bucket_name.upper()}")
        for t in tasks:
            with st.container(border=True):
                pc1, pc2 = st.columns([5, 1])
                with pc1:
                    st.markdown(f"**{t.action}**")
                with pc2:
                    ui_kit.render_badge(t.priority, kind=_PRIORITY_BADGE_KIND.get(t.priority, "neutral"))
                st.caption(f"🔍 **Căn cứ LMS:** {t.reason}")
                st.caption(f"⏱️ **Nỗ lực:** {t.estimated_effort}  |  🏁 **Kết quả mong đợi:** {t.target_result}")
                if t.resource_url and t.resource_url != "#":
                    st.markdown(f"📦 **Học liệu CMS:** [{t.resource}]({t.resource_url})")
                else:
                    st.caption(f"📦 **Học liệu CMS:** {t.resource}")

                # Feedback loop check
                done = t.task_id in profile.completed_tasks
                if st.checkbox("Đã hoàn thành nhiệm vụ này", value=done, key=f"task_chk_{t.task_id}"):
                    if not done:
                        profile.mark_task_completed(t.task_id)
                        st.success("Đã ghi nhận tiến độ vào hồ sơ!")
                        st.rerun()

    # Closed-Loop Feedback Simulator
    st.markdown("---")
    st.markdown("### 🔄 Mô Phỏng Hành Động Học Tập LMS (Closed-Loop Feedback Simulator)")
    st.caption(
        "Thực hiện vòng lặp phản hồi khép kín: Sinh viên làm bài học/kiểm tra trên LMS → "
        "LMS ghi nhận kết quả → Cập nhật Skill Profile → Tự động tính lại Career Readiness → Làm mới khuyến nghị nghề nghiệp."
    )

    non_have_gaps = [
        g for g in compute_traced_gap_analysis(profile, role, lms_repo=lms, cms_repo=cms)
        if g.status != STATUS_HAVE and g.item_type == "skill"
    ]
    if non_have_gaps:
        gap_map = {g.skill_name: g for g in non_have_gaps}
        selected_skill = st.selectbox(
            "Chọn kỹ năng / bài thực hành trên LMS để mô phỏng hoàn thành:",
            list(gap_map.keys()),
            key=f"sim_skill_sel_{role_id}",
        )
        matched_gap = gap_map[selected_skill]
        if matched_gap.cms_match:
            st.info(
                f"📚 **Học phần CMS:** `{matched_gap.cms_match.course_code}` — {matched_gap.cms_match.module_title}\n\n"
                f"📖 **Bài học:** {matched_gap.cms_match.lesson_title}\n\n"
                f"🎯 **Nhiệm vụ:** {matched_gap.cms_match.practice_action}"
            )

        col_s1, col_s2, col_btn = st.columns([2, 2, 2])
        with col_s1:
            score_val = st.slider("Điểm bài kiểm tra LMS (thang 10):", min_value=5.0, max_value=10.0, value=8.5, step=0.5, key=f"sim_score_{role_id}")
        with col_s2:
            duration_val = st.number_input("Thời lượng học tập (phút):", min_value=15, max_value=240, value=45, step=15, key=f"sim_dur_{role_id}")
        with col_btn:
            st.write("")
            st.write("")
            if st.button("🚀 Gửi kết quả lên LMS & Cập nhật", type="primary", key=f"btn_sim_lms_{role_id}"):
                next_lvl = "Intermediate" if score_val >= 6.5 else "Basic"
                act_title = matched_gap.cms_match.lesson_title if matched_gap.cms_match else f"Bài thực hành {selected_skill}"
                course_code = matched_gap.cms_match.course_code if matched_gap.cms_match else "CS201"
                action_res = execute_closed_loop_action(
                    student_id=str(selected_id),
                    profile=profile,
                    role_id=role_id,
                    skill_to_upgrade=selected_skill,
                    new_level=next_lvl,
                    assessment_score=score_val,
                    duration_minutes=duration_val,
                    course_id=course_code,
                    activity_title=act_title,
                    lms_repo=lms,
                    cms_repo=cms,
                )
                st.session_state["last_closed_loop_msg"] = action_res.message
                st.rerun()

        if "last_closed_loop_msg" in st.session_state:
            st.success(st.session_state.pop("last_closed_loop_msg"))
    else:
        st.success("🎉 Xuất sắc! Tất cả kỹ năng yêu cầu cho vị trí này đã đạt chuẩn Intermediate trở lên.")

    st.markdown("---")

    # Alternative Paths
    st.markdown("#### 🔀 Con đường thay thế (Alternative Career Paths)")
    paths = suggest_alternative_paths(role_id)
    c_p1, c_p2, c_p3 = st.columns(3)
    with c_p1:
        st.metric("Nghề mục tiêu chính", role.role_name)
    with c_p2:
        sec_role = get_role(paths["secondary"][0]) if paths["secondary"] else None
        st.metric("Nghề có thể nộp kèm", sec_role.role_name if sec_role else "—")
        if paths.get("secondary_explanation"):
            st.caption(f"💡 {paths['secondary_explanation']}")
    with c_p3:
        lt_role = get_role(paths["long_term"][0]) if paths["long_term"] else None
        st.metric("Mục tiêu dài hạn", lt_role.role_name if lt_role else "—")
        if paths.get("long_term_explanation"):
            st.caption(f"🚀 {paths['long_term_explanation']}")

    st.markdown("---")

    # Career Transition
    st.markdown("#### 🔄 Chuyển đổi nghề nghiệp (Career Transition Explorer)")
    other_roles = [r for r in list_roles() if r.role_id != role_id]
    target_transition_name = st.selectbox(
        f"Từ {role.role_name}, bạn muốn chuyển sang nghề nào?",
        [r.role_name for r in other_roles],
        key="transition_target_pick_v2",
    )
    target_role_id = next(r.role_id for r in other_roles if r.role_name == target_transition_name)

    if st.button(f"Phân tích chuyển đổi: {role.role_name} → {target_transition_name}", key="btn_run_trans"):
        plan = compute_transition(profile, role_id, target_role_id, readiness)
        if plan:
            t_m1, t_m2 = st.columns(2)
            t_m1.metric("Độ khả thi chuyển nghề", f"{plan.feasibility_score:.1f}%")
            t_m2.metric("Khoảng cách chuyển dịch", plan.gap_size)

            st.info(f"🤝 **Kỹ năng dùng chung:** {', '.join(plan.shared_skills) if plan.shared_skills else 'Không có'}")
            st.warning(f"🎯 **Kỹ năng cần học mới:** {', '.join(plan.missing_skills) if plan.missing_skills else 'Không có'}")


# ============================================================================
# TAB 6 — GIẢ LẬP WHAT-IF & PHẢN HỒI (DECISION SUPPORT SYSTEM)
# ============================================================================
def _render_whatif_section(profile: StudentCareerProfile, ranked) -> None:
    st.markdown("### 🧪 Giả lập tình huống & Hỗ trợ Ra Quyết định")
    st.caption("Thử nghiệm các kịch bản thay đổi điều kiện hoặc nâng kỹ năng để xem biến thiên của Career Fit và Readiness:")

    w_tab1, w_tab2, w_tab3 = st.tabs([
        "1. Nâng cấp Kỹ năng",
        "2. Đổi Ràng buộc Cá nhân",
        "3. Lọc Nghề theo Thời gian",
    ])

    role_options = {fit.role_name: fit.role_id for fit, _ in ranked}

    # Kịch bản 1: Nâng kỹ năng
    with w_tab1:
        st.markdown("##### Kịch bản: 'Nếu tôi nâng kỹ năng X lên mức Y thì điểm thay đổi thế nào?'")
        wc1, wc2, wc3 = st.columns(3)
        with wc1:
            test_role_name = st.selectbox("Chọn nghề cần kiểm tra:", list(role_options.keys()), key="wi_role_sk")
            target_r = get_role(role_options[test_role_name])
        with wc2:
            test_skill = st.selectbox("Chọn kỹ năng cần nâng:", [s for skills in ALL_SKILL_CATALOG.values() for s in skills], key="wi_skill_pick")
        with wc3:
            test_level = st.selectbox("Mức độ giả định:", ["Basic", "Intermediate", "Advanced"], index=1, key="wi_level_pick")

        if st.button("Chạy giả lập nâng kỹ năng", key="btn_run_wi_sk"):
            hypo = apply_skill_change(profile, test_skill, "technical", test_level)
            res = compare_scenarios(profile, hypo, target_r, f"Nếu nâng {test_skill} lên {test_level}")

            m_c1, m_c2 = st.columns(2)
            m_c1.metric("Career Fit mới", f"{res.after_fit:.1f}%", delta=f"{res.delta_fit:+.1f}%")
            m_c2.metric("Career Readiness mới", f"{res.after_readiness:.1f}%", delta=f"{res.delta_readiness:+.1f}%")
            st.success(res.explanation)

    # Kịch bản 2: Đổi ràng buộc
    with w_tab2:
        st.markdown("##### Kịch bản: 'Nếu tôi chấp nhận làm ca kíp hoặc thay đổi hình thức remote?'")
        rc1, rc2 = st.columns(2)
        with rc1:
            toggle_shift = st.checkbox("Giả sử: Tôi chấp nhận làm ca kíp / trực đêm", value=True, key="wi_shift_chk")
        with rc2:
            toggle_remote = st.selectbox("Giả sử: Hình thức làm việc", ["flexible", "remote", "on_site"], key="wi_remote_sel")

        if st.button("Chạy giả lập ràng buộc", key="btn_run_wi_con"):
            hypo_con = apply_constraint_change(profile, shift_acceptance=toggle_shift, remote_preference=toggle_remote)
            st.markdown("##### Thay đổi xếp hạng nghề nghiệp sau khi nới lỏng ràng buộc:")
            new_ranked = rank_careers(hypo_con, list_roles(), top_k=5)
            for r_idx, (f, r) in enumerate(new_ranked, start=1):
                st.caption(f"{r_idx}. **{f.role_name}**: Fit = {f.fit_score:.1f}% | Readiness = {r.readiness_score:.1f}%")

    # Kịch bản 3: Lọc theo thời gian
    with w_tab3:
        st.markdown("##### Kịch bản: 'Nếu tôi muốn xin việc trong 3 tháng thì nghề nào nên ưu tiên?'")
        st.caption("Nếu thời gian ngắn (<= 3 tháng), hệ thống sẽ ưu tiên Career Readiness. Nếu dài hạn, ưu tiên Career Fit.")
        tf = st.select_slider("Khung thời gian mục tiêu (tháng):", options=[1, 3, 6, 12, 24], value=3, key="wi_tf_slider")
        timeframe_results = rank_roles_for_timeframe(profile, list_roles(), tf, top_k=5)

        tf_df = pd.DataFrame(timeframe_results)[["role_name", "fit_score", "readiness_score", "hybrid_score", "primary_metric"]]
        tf_df.columns = ["Nghề nghiệp", "Career Fit (%)", "Readiness (%)", "Điểm ưu tiên tổng hợp", "Trọng số ưu tiên"]
        st.dataframe(tf_df.set_index("Nghề nghiệp"), width="stretch")


# ============================================================================
# TAB 7 — AI CAREER ADVISOR (CHAT TƯ VẤN)
# ============================================================================
def _render_ai_chat_section(profile: StudentCareerProfile, ranked, role, student_id_llm) -> None:
    from dss.services import llm_service, prompt_security, token_tracker
    from dss.core.logging_config import get_logger

    _logger = get_logger(__name__)
    st.caption("Hỏi AI hướng nghiệp — Tư vấn dựa trên 100% dữ liệu hồ sơ thực tế của bạn, tuyệt đối không bịa đặt khi thiếu bằng chứng.")

    quick_prompts = [
        "Vì sao tôi hợp nghề đầu tiên hơn nghề thứ hai?",
        "Điểm yếu lớn nhất của tôi là gì?",
        "Tôi nên học kỹ năng nào trước?",
        "Tôi có đủ khả năng apply Fresher chưa?",
        "Nếu chỉ có 2 tháng thì nên học gì?",
    ]

    chat_key = f"career_chat_{profile.student_pseudonym}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
    chat_history = st.session_state[chat_key]

    pending_q = None
    st.markdown("###### Câu hỏi thường gặp (bấm để hỏi ngay):")
    qcols = st.columns(len(quick_prompts))
    for i, q in enumerate(quick_prompts):
        with qcols[i]:
            if st.button(q, key=f"career_quick_q_{i}", width="stretch"):
                pending_q = q

    chat_box = st.container(height=450)
    with chat_box:
        if not chat_history:
            st.caption("Chưa có tin nhắn nào. Hãy chọn câu hỏi gợi ý phía trên hoặc nhập câu hỏi bên dưới.")
        for msg in chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    typed_q = st.chat_input("Nhập câu hỏi về định hướng nghề nghiệp, kỹ năng hoặc lộ trình học của bạn...", key="career_chat_input_v2")
    question = pending_q or typed_q

    if question:
        chat_history.append({"role": "user", "content": question})
        context_text = build_career_ai_context(profile, ranked)
        system_instructions = get_system_prompt()

        prompt = prompt_security.build_secure_rag_prompt(
            system_instructions=system_instructions,
            student_context=context_text,
            retrieved_chunks=[],
            user_query=question,
        )

        try:
            from dss.core.init_app import get_llm_integration
            llm_integration = get_llm_integration()
        except Exception:
            llm_integration = None

        chat_auto = llm_service.resolve_auto_provider(llm_integration) if llm_integration else None
        if chat_auto:
            try:
                with st.spinner("AI đang phân tích hồ sơ hướng nghiệp..."):
                    kwargs = {"model_name": chat_auto["model_name"]}
                    if chat_auto["provider_key"] in ("gemini", "groq", "openai"):
                        kwargs["api_key"] = chat_auto["api_key"]
                    elif chat_auto["provider_key"] == "ollama":
                        from dss.core.models import ollama_base_url
                        kwargs["base_url"] = ollama_base_url()
                    stream = llm_integration.call_ai_provider(prompt, provider=chat_auto["provider_key"], **kwargs)
                    answer = "".join(stream)

                token_tracker.record_usage(
                    user_id=profile.student_pseudonym,
                    role=role or "Sinh viên",
                    request_type="career_advisor_chat",
                    provider=chat_auto["provider_key"],
                    model=chat_auto.get("model_name") or "default",
                    input_tokens=len(prompt) // 4,
                    output_tokens=len(answer) // 4,
                )
            except Exception:
                _logger.exception("Lỗi kết nối AI Provider — chuyển sang Deterministic Grounded Advisor")
                answer = generate_offline_grounded_answer(question, profile, ranked)
        else:
            # Deterministic Grounded Engine (Không bao giờ để sinh viên gặp ngõ cụt)
            answer = generate_offline_grounded_answer(question, profile, ranked)

        chat_history.append({"role": "assistant", "content": answer})
        st.rerun()


# ============================================================================
# ENTRY POINT
# ============================================================================
def student_advisory_tab(df, role=None, current_student_id=None):
    """Career Decision Support System (CDSS) — Điểm vào chính."""
    # Student Information Architecture (audit 2026-09): bỏ tên hệ thống/thuật
    # ngữ viết tắt tiếng Anh (CDSS, What-if) khỏi tiêu đề Sinh viên nhìn thấy —
    # chỉ Giảng viên/Admin cần biết đây là module CDSS.
    if role == "Sinh viên":
        ui_kit.section_header(
            "Hướng nghiệp của bạn",
            subtitle="Nghề phù hợp, mức sẵn sàng, khoảng cách kỹ năng cần bổ sung và lộ trình 1/3/6 tháng.",
        )
    else:
        # FINAL PRODUCTION GAP CLOSURE (Phần 21/41): bỏ tên hệ thống tiếng Anh
        # viết tắt "(Career Decision Support System)" khỏi tiêu đề Giảng
        # viên/Admin — không cần thiết, chỉ gây dài dòng.
        ui_kit.section_header(
            "Định hướng nghề nghiệp",
            subtitle="Nghề phù hợp, mức sẵn sàng, khoảng cách kỹ năng, lộ trình 1/3/6 tháng và giả lập tình huống.",
        )

    # Production Demo Policy (audit 2026-09): profile ở tab này được làm giàu
    # qua get_lms_repository()/get_cms_repository() — RealConnectorLMSRepository
    # (lms_connector.py) HIỆN TẠI vẫn tự uỷ quyền sang DemoLMSRepository bên
    # trong get_student_learning_summary() (chưa có kết nối LMS thật nào —
    # đúng hiện trạng kiến trúc đã ghi nhận: "No real LMS integration exists
    # today"). Hiển thị dữ liệu mô phỏng này như thể là Hướng nghiệp thật trong
    # môi trường REAL_LMS vi phạm trực tiếp yêu cầu "NO demo Career Advisor" —
    # nên phải chặn tại đây bằng thông báo trung thực thay vì âm thầm dùng demo.
    if _is_production_environment():
        st.warning(
            "🔒 Hướng nghiệp hiện chưa khả dụng ở môi trường production: hệ thống chưa được kết nối với "
            "dữ liệu LMS/CMS thật. Vui lòng liên hệ Quản trị viên để hoàn tất tích hợp trước khi sử dụng tính năng này."
        )
        return

    id_col = next((c for c in df.columns if "id" in c.lower()), df.columns[0] if not df.empty else None)
    if not id_col:
        st.error("Không tìm thấy cột định danh ID trong tập dữ liệu.")
        return

    data_source = "REAL" if getattr(df, "attrs", {}).get("data_source_type") == "real" else "DEMO"

    if role == "Sinh viên":
        selected_id = current_student_id
        student_rows = df[df[id_col] == selected_id]
        if student_rows.empty:
            ui_kit.empty_state(
                "Chưa có đủ dữ liệu học tập để phân tích định hướng nghề nghiệp.",
                icon="📭",
                hint="Hệ thống cần dữ liệu điểm số chuyên đề trước khi gợi ý — vui lòng liên hệ Giảng viên/Admin.",
            )
            return
        raw_row = student_rows.iloc[0].to_dict()
        st.info(f"👤 Đang phân tích định hướng nghề nghiệp cho sinh viên: **{selected_id}**")
    else:
        student_ids = df[id_col].unique()
        selected_id = st.selectbox("Chọn sinh viên để tư vấn định hướng:", student_ids, key="career_student_sel_v2")
        if not selected_id:
            return
        raw_row = df[df[id_col] == selected_id].iloc[0].to_dict()

    profile = _get_or_build_profile(selected_id, raw_row, data_source)

    # BỔ SUNG BẮT BUỘC: Khởi tạo và liên kết LMS + CMS Repositories
    lms_repo = get_lms_repository()
    cms_repo = get_cms_repository()
    enrich_career_profile_with_lms_cms(profile, lms_repo, cms_repo, raw_row)

    # Student Information Architecture + Production Demo Policy (audit 2026-09):
    # khối này TRƯỚC ĐÂY hiển thị các nhãn trạng thái triển khai phần mềm dạng
    # tiếng Anh viết hoa (vd. mức độ hoàn thành tích hợp kết nối/kho học liệu)
    # thẳng cho MỌI vai trò kể cả Sinh viên — đây là ghi chú tiến độ phát triển
    # (dev/thesis), không phải thông tin có ích cho người dùng cuối. Sinh viên
    # không cần thấy khối này. Giảng viên/Admin vẫn thấy nguồn gốc dữ liệu
    # (đúng nguyên tắc data-provenance) nhưng bằng câu chữ trung thực, dễ hiểu —
    # không phải nhãn trạng thái triển khai phần mềm.
    if role != "Sinh viên":
        with st.container(border=True):
            c_lms, c_cms = st.columns(2)
            with c_lms:
                st.markdown("##### 🏫 Nguồn dữ liệu học tập")
                ui_kit.render_badge(
                    f"Nguồn dữ liệu: {'Mô phỏng (Demo)' if lms_repo.mode == 'DEMO' else lms_repo.mode}",
                    kind="warning" if lms_repo.mode == "DEMO" else "success",
                )
                st.caption("Nguồn dữ liệu chính xác định: năng lực học tập thực tế, môn mạnh/yếu, tiến độ, giờ học, chuyên cần và minh chứng.")
            with c_cms:
                st.markdown("##### 📚 Nguồn nội dung khuyến nghị")
                ui_kit.render_badge(
                    f"Nguồn nội dung: {'Mô phỏng (Demo)' if cms_repo.mode == 'DEMO' else cms_repo.mode}",
                    kind="warning" if cms_repo.mode == "DEMO" else "success",
                )
                st.caption("Khớp nối học phần, module, bài học, lab thực hành chuẩn hóa theo từng khoảng cách kỹ năng thay vì khuyến nghị chung chung.")

    ranked = rank_careers(profile, list_roles(), top_k=5)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "1️⃣ Hồ sơ nghề nghiệp",
        "2️⃣ Nghề phù hợp",
        "3️⃣ So sánh nghề",
        "4️⃣ Khoảng cách kỹ năng",
        "5️⃣ Lộ trình phát triển",
        "6️⃣ Giả lập tình huống",
        "7️⃣ Hỏi AI hướng nghiệp",
    ])

    with tab1:
        _render_profile_section(profile)
    with tab2:
        _render_matching_section(profile, ranked)
    with tab3:
        _render_comparison_section(profile, ranked)
    with tab4:
        default_role_id = _render_gap_section(profile, ranked, lms_repo=lms_repo, cms_repo=cms_repo)
    with tab5:
        _render_roadmap_section(
            profile,
            ranked,
            default_role_id if "default_role_id" in dir() else None,
            lms_repo=lms_repo,
            cms_repo=cms_repo,
            selected_id=str(selected_id),
        )
    with tab6:
        _render_whatif_section(profile, ranked)
    with tab7:
        _render_ai_chat_section(profile, ranked, role, selected_id)
