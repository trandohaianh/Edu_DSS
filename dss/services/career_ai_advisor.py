"""Career AI Advisor — Dịch vụ cố vấn nghề nghiệp thông minh & bảo vệ chống bịa đặt (Anti-Hallucination).

Nguyên tắc bắt buộc (Mục XXII, XXIII, XXIV, XXV):
1. Context đầy đủ 100%: Hồ sơ đa chiều, điểm học thuật, kỹ năng có bằng chứng, kinh nghiệm,
   sở thích, ràng buộc, kết quả Fit/Readiness, bảng Gap Analysis và Lộ trình 1/3/6 tháng.
2. TUYỆT ĐỐI KHÔNG BỊA ĐẶT: Nếu không có bằng chứng, bắt buộc nói rõ
   "Hiện chưa có đủ dữ liệu để đánh giá kỹ năng..." thay vì đoán mò.
3. Không gắn nhãn tuyệt đối ("Bạn không phù hợp..."), dùng ngôn ngữ hỗ trợ quyết định ("Khoảng cách kỹ năng lớn hơn...").
4. Deterministic Grounded Fallback Engine: Khi LLM ngoại tuyến hoặc chưa cấu hình API,
   hệ thống tự động giải đáp 5 câu hỏi trọng tâm bằng quy tắc chuẩn hoá từ dữ liệu đã tính toán.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from dss.services.career_gap_analysis import compute_gap_analysis, group_gap_by_status, STATUS_HAVE, STATUS_MISSING, STATUS_STRENGTHEN, PRIORITY_CRITICAL, PRIORITY_HIGH
from dss.services.career_knowledge_base import CareerRole, get_role
from dss.services.career_profile import StudentCareerProfile
from dss.services.career_roadmap import generate_roadmap, _BUCKET_1M, _BUCKET_3M
from dss.services.privacy_service import sanitize_conversation_turn_for_provider
from dss.services.career_scoring import CareerFitResult, CareerReadinessResult


def _strength_band(score) -> str:
    """Nhóm năng lực chuyên đề (thang 10) — thay cho điểm chính xác trong payload AI."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "chưa rõ"
    if value >= 8.0:
        return "mạnh"
    if value >= 6.5:
        return "khá"
    return "cần cải thiện"


def build_career_ai_context(
    profile: StudentCareerProfile,
    ranked: List[Tuple[CareerFitResult, CareerReadinessResult]],
) -> str:
    """Xây dựng context phong phú, chính xác và có thể truy vết nguồn gốc cho AI Advisor."""
    lines: List[str] = [
        "=== HỒ SƠ NGHỀ NGHIỆP SINH VIÊN (DỮ LIỆU ĐÃ KHỬ ĐỊNH DANH) ===",
        # C1.1: KHÔNG gửi định danh (kể cả bí danh) ra nhà cung cấp AI.
        f"Nguồn dữ liệu: {profile.data_source} " + ("(Hồ sơ minh họa mô phỏng)" if profile.data_source == "DEMO" else "(Dữ liệu thực tế)"),
    ]

    # 1. Học thuật
    lines.append("\n[1. HỒ SƠ HỌC THUẬT]")
    # C1.1: chỉ gửi KHOẢNG/NHÓM (đủ cho định hướng nghề nghiệp), không gửi điểm chính xác.
    from dss.services.privacy_service import gpa_band
    lines.append(f"- Khoảng GPA tổng quan: {gpa_band(profile.academic.gpa)}")
    if profile.academic.domain_scores:
        dom_str = "; ".join(f"{d}: {_strength_band(s)}" for d, s in profile.academic.domain_scores.items())
        lines.append(f"- Mức năng lực theo chuyên đề: {dom_str}")
    if profile.academic.strengths:
        lines.append(f"- Thế mạnh học thuật: {', '.join(profile.academic.strengths)}")
    if profile.academic.weaknesses:
        lines.append(f"- Môn/Domain cần cải thiện: {', '.join(profile.academic.weaknesses)}")

    # 2. Kỹ năng & Bằng chứng
    lines.append("\n[2. HỒ SƠ KỸ NĂNG & MINH CHỨNG THỰC TẾ]")
    recorded_skills = [s for s in profile.skills.items.values() if s.achieved_level > 0]
    if recorded_skills:
        for s in recorded_skills:
            ev_str = "; ".join(sanitize_conversation_turn_for_provider(str(e)) for e in s.evidence) if s.evidence else "Chưa có minh chứng cụ thể"
            lines.append(f"- {s.skill_name} ({s.category}): Cấp độ {s.skill_level} | Nguồn: {s.source} | Độ tin cậy: {s.confidence} | Minh chứng: {ev_str}")
    else:
        lines.append("- Chưa có kỹ năng nào được xác thực hoặc đạt từ mức Basic trở lên.")

    # 3. Kinh nghiệm & Tạo tác
    lines.append("\n[3. KINH NGHIỆM & TẠO TÁC NGHỀ NGHIỆP]")
    lines.append(f"- Đã có Portfolio: {'Có' if profile.experience.has_portfolio() else 'Chưa có'}")
    lines.append(f"- Sẵn sàng phỏng vấn: {'Đã có kinh nghiệm' if profile.experience.is_interview_ready() else 'Chưa có kinh nghiệm'}")
    if profile.experience.items:
        for it in profile.experience.items:
            rel = f" (kỹ năng minh chứng: {', '.join(it.related_skills)})" if it.related_skills else ""
            lines.append(f"- [{it.exp_type.upper()}] {it.title}{rel}")
    else:
        lines.append("- Chưa ghi nhận dự án/hoạt động thực tập nào.")

    # 4. Sở thích & Phong cách làm việc
    lines.append("\n[4. SỞ THÍCH & PHONG CÁCH LÀM VIỆC]")
    if profile.interest.scores:
        lines.append("- Sở thích nghề nghiệp: " + "; ".join(f"{k}: {v}/5" for k, v in profile.interest.scores.items()))
    if profile.work_style.preferences:
        lines.append("- Phong cách làm việc: " + "; ".join(f"{k}: {v}/5" for k, v in profile.work_style.preferences.items()))

    # 5. Ràng buộc & Mục tiêu
    lines.append("\n[5. RÀNG BUỘC CÁ NHÂN & MỤC TIÊU]")
    c = profile.constraints
    lines.append(f"- Địa điểm mong muốn: {c.desired_location} (Sẵn sàng relocate: {'Có' if c.willing_to_relocate else 'Không'})")
    lines.append(f"- Giờ làm việc: {'Giờ hành chính' if c.preferred_hours == 'office_hours' else 'Chấp nhận làm ca'} (Làm ca đêm: {'Có' if c.shift_acceptance else 'Không'})")
    lines.append(f"- Hình thức làm việc: {c.remote_preference} | Tiếng Anh: {c.english_level} | Giờ học thêm/tuần: {c.learning_hours_per_week}h")
    g = profile.goal
    lines.append(f"- Mục tiêu: Vị trí '{g.goal_type}' cho nghề '{g.target_role_id}' trong vòng {g.target_timeframe_months} tháng")

    # 6. Xếp hạng Top nghề
    lines.append("\n[6. KẾT QUẢ PHÂN TÍCH PHÙ HỢP (FIT) & SẴN SÀNG (READINESS)]")
    for i, (fit, ready) in enumerate(ranked, start=1):
        lines.append(f"{i}. {fit.role_name} -> Career Fit: {fit.fit_score:.1f}% | Career Readiness: {ready.readiness_score:.1f}% | Độ tin cậy: {fit.confidence}")

    # 7. Khoảng cách kỹ năng nghề mục tiêu (Top 1 hoặc target role)
    target_role_id = profile.goal.target_role_id or (ranked[0][0].role_id if ranked else None)
    if target_role_id:
        target_role = get_role(target_role_id)
        if target_role:
            gaps = compute_gap_analysis(profile, target_role, include_artifacts=True)
            grouped = group_gap_by_status(gaps)
            lines.append(f"\n[7. KHOẢNG CÁCH KỸ NĂNG VỚI NGHỀ '{target_role.role_name}']")
            lines.append("- ĐÃ CÓ: " + (", ".join(g.skill_name for g in grouped[STATUS_HAVE]) if grouped[STATUS_HAVE] else "Chưa có kỹ năng nào đạt chuẩn"))
            lines.append("- CẦN CỦNG CỐ: " + (", ".join(f"{g.skill_name} [{g.priority}]" for g in grouped[STATUS_STRENGTHEN]) if grouped[STATUS_STRENGTHEN] else "Không có"))
            lines.append("- CHƯA CÓ: " + (", ".join(f"{g.skill_name} [{g.priority}]" for g in grouped[STATUS_MISSING]) if grouped[STATUS_MISSING] else "Không thiếu kỹ năng nào"))

    # 8. Tích hợp LMS & CMS (Truy vết minh chứng thực tế và học liệu cụ thể)
    try:
        from dss.services.career_lms_cms_pipeline import compute_traced_gap_analysis
        from dss.services.cms_repository import get_cms_repository
        from dss.services.lms_connector import get_lms_repository
        lms_sum = get_lms_repository().get_student_learning_summary(profile.student_pseudonym)
        lines.append("\n[8. NGUỒN DỮ LIỆU HỌC TẬP LMS & HỌC LIỆU KHUYẾN NGHỊ CMS]")
        lines.append(f"- Nguồn dữ liệu học tập: [LMS] | Chuyên cần: {lms_sum.average_attendance:.1f}% | Tiến độ: {lms_sum.average_progress:.1f}% | Tổng giờ học: {lms_sum.total_learning_hours:.1f}h | Phong độ: {lms_sum.performance_trend}")
        if target_role_id:
            role_obj = get_role(target_role_id)
            if role_obj:
                t_gaps = compute_traced_gap_analysis(profile, role_obj)
                for tg in t_gaps[:5]:
                    if tg.status != STATUS_HAVE:
                        remedy = f" -> Khắc phục [CMS]: {tg.cms_match.lesson_title} (Nhiệm vụ: {tg.cms_recommendation_action})" if tg.cms_match else ""
                        lines.append(f"- Kỹ năng '{tg.skill_name}': Căn cứ [LMS]: {tg.lms_evidence}{remedy}")
    except Exception:
        pass

    return "\n".join(lines)


def get_system_prompt() -> str:
    """System instructions chuẩn hoá với ràng buộc chống bịa đặt nghiêm ngặt."""
    return (
        "Bạn là AI Career Advisor — chuyên gia cố vấn hướng nghiệp và hỗ trợ ra quyết định nghề nghiệp cho sinh viên thuộc hệ thống EduDSS.\n\n"
        "NGUYÊN TẮC BẮT BUỘC ĐẠO ĐỨC & ĐỘ CHÍNH XÁC:\n"
        "1. TUYỆT ĐỐI KHÔNG BỊA ĐẶT kỹ năng, kinh nghiệm hoặc bằng chứng không có trong hồ sơ sinh viên được cung cấp.\n"
        "2. Nếu người dùng hỏi về một kỹ năng mà trong hồ sơ ghi 'Chưa có dữ liệu' hoặc không có bằng chứng, BẮT BUỘC PHẢI NÓI RÕ: "
        "'Hiện chưa có đủ dữ liệu trong hồ sơ để đánh giá kỹ năng... Bạn có thể tự đánh giá hoặc thêm dự án minh chứng tại tab Hồ sơ nghề nghiệp'.\n"
        "3. KHÔNG GẮN NHÃN TUYỆT ĐỐI ('Bạn không phù hợp với nghề X...'). Luôn dùng ngôn ngữ hỗ trợ quyết định: "
        "'Vị trí X hiện tại có khoảng cách kỹ năng lớn hơn so với vị trí Y...'.\n"
        "4. PHÂN BIỆT RÕ RÀNG:\n"
        "   - Career Fit = Mức độ phù hợp với năng lực, sở thích và điều kiện cá nhân lâu dài.\n"
        "   - Career Readiness = Mức độ sẵn sàng xin việc ngay ở thời điểm hiện tại.\n"
        "5. Trả lời súc tích, cụ thể, có số liệu %, bóc tách rõ điểm mạnh, khoảng cách và hành động tiếp theo trong lộ trình 1/3/6 tháng.\n"
        "6. Khi giải thích về khoảng cách kỹ năng hoặc khuyến nghị lộ trình, BẮT BUỘC trích dẫn căn cứ thực tế từ hệ thống [LMS] "
        "(điểm số môn học, bài kiểm tra, chuyên cần) và bài học/học phần cụ thể từ kho học liệu [CMS] đã được cung cấp trong hồ sơ."
    )


# ============================================================================
# DETERMINISTIC GROUNDED FALLBACK ENGINE
# ============================================================================
def generate_offline_grounded_answer(
    question: str,
    profile: StudentCareerProfile,
    ranked: List[Tuple[CareerFitResult, CareerReadinessResult]],
) -> str:
    """Bộ máy giải đáp suy luận dựa trên luật (Rule-based Decision Engine)
    khi LLM ngoại tuyến hoặc không có kết nối internet — đảm bảo 100% dựa trên dữ liệu thật."""
    if not ranked:
        return "Hiện chưa có đủ dữ liệu để xếp hạng nghề nghiệp. Vui lòng nhập điểm hoặc cập nhật kỹ năng ở Tab 1."

    q_lower = question.lower()
    top1_fit, top1_ready = ranked[0]
    top1_role = get_role(top1_fit.role_id)
    top2_fit, top2_ready = ranked[1] if len(ranked) > 1 else (None, None)
    target_role_id = profile.goal.target_role_id or top1_fit.role_id
    target_role = get_role(target_role_id) or top1_role

    gaps = compute_gap_analysis(profile, target_role, include_artifacts=True)
    grouped = group_gap_by_status(gaps)

    # CÂU HỎI 1: "Vì sao tôi hợp DA hơn DE?" hoặc so sánh 2 nghề
    if "vì sao" in q_lower or "hợp" in q_lower or "so sánh" in q_lower or ("hơn" in q_lower and top2_fit):
        role_a = top1_fit
        role_b = top2_fit if top2_fit else top1_fit
        return (
            f"### 🧭 So sánh mức độ phù hợp giữa **{role_a.role_name}** và **{role_b.role_name}**:\n\n"
            f"- **{role_a.role_name}**: Career Fit **{role_a.fit_score:.1f}%** | Career Readiness **{top1_ready.readiness_score:.1f}%**\n"
            f"- **{role_b.role_name}**: Career Fit **{role_b.fit_score:.1f}%** | Career Readiness **{top2_ready.readiness_score:.1f}%**\n\n"
            f"**Lý do bạn phù hợp với {role_a.role_name} hơn ở hiện tại:**\n"
            f"1. **Độ tương thích kỹ năng:** Điểm khớp kỹ năng của bạn với {role_a.role_name} đạt "
            f"{role_a.breakdown['skill'].score * 100:.0f}%, cao hơn so với {role_b.role_name} ({role_b.breakdown['skill'].score * 100:.0f}%).\n"
            f"2. **Minh chứng học thuật:** {'; '.join(role_a.breakdown['academic'].evidence[:2])}.\n"
            f"3. **Khoảng cách kỹ năng:** {role_b.role_name} đòi hỏi các kỹ năng chuyên sâu chưa có trong hồ sơ của bạn.\n\n"
            f"*(Lưu ý: Đây là đánh giá hỗ trợ quyết định dựa trên dữ liệu hiện tại, không phải giới hạn năng lực trong tương lai của bạn).* "
        )

    # CÂU HỎI 2: "Điểm yếu lớn nhất của tôi là gì?"
    if "điểm yếu" in q_lower or "yếu nhất" in q_lower or "thiếu gì" in q_lower or "lỗ hổng" in q_lower:
        critical_gaps = [g for g in gaps if g.priority in (PRIORITY_CRITICAL, PRIORITY_HIGH) and g.status != STATUS_HAVE]
        if not critical_gaps:
            return f"Đối với vị trí **{target_role.role_name}**, bạn đã có nền tảng kỹ năng khá vững! Điểm cần cải thiện chính là hoàn thiện thêm dự án Portfolio và chuẩn bị phỏng vấn kỹ thuật."

        items_str = "\n".join(f"- **{g.skill_name}** (Ưu tiên: `{g.priority}` - Hiện tại: `{g.current_level}`)" for g in critical_gaps)
        return (
            f"### ⚠️ Điểm yếu / Khoảng cách lớn nhất đối với vai trò **{target_role.role_name}**:\n\n"
            f"{items_str}\n\n"
            f"**Khuyến nghị:** Bạn nên tập trung giải quyết các kỹ năng mức `Critical` trước trong vòng 30 ngày tới theo đúng lộ trình phát triển."
        )

    # CÂU HỎI 5: "Nếu chỉ có 2 tháng thì nên học gì?" hoặc câu hỏi giới hạn thời gian
    if "tháng" in q_lower or "thời gian" in q_lower or "cấp tốc" in q_lower or "2 tháng" in q_lower:
        roadmap = generate_roadmap(profile, target_role, top1_ready.readiness_score)
        tasks_1m = roadmap.buckets.get(_BUCKET_1M, [])
        tasks_3m = roadmap.buckets.get(_BUCKET_3M, [])
        all_urgent = tasks_1m + tasks_3m[:2]

        tasks_summary = "\n".join(f"- **{t.action}** (Nỗ lực: {t.estimated_effort} — Kết quả: {t.target_result})" for t in all_urgent)
        return (
            f"### ⏱️ Kế hoạch hành động cấp tốc trong 2 tháng (60 ngày) cho **{target_role.role_name}**:\n\n"
            f"Với thời gian ngắn, bạn chỉ tập trung vào các kỹ năng giải quyết trực tiếp khoảng cách lớn nhất:\n\n"
            f"{tasks_summary}\n\n"
            f"Tạm gác lại các kỹ năng phụ trợ (`Nice-to-have`) để tối đa hoá điểm sẵn sàng ứng tuyển."
        )

    # CÂU HỎI 3: "Tôi nên học SQL hay Power BI trước?" hoặc "nên học kỹ năng nào trước"
    if "trước" in q_lower or "học gì" in q_lower or "ưu tiên" in q_lower or "kỹ năng nào" in q_lower:
        critical_missing = [g for g in gaps if g.status == STATUS_MISSING and g.priority == PRIORITY_CRITICAL]
        high_missing = [g for g in gaps if g.status in (STATUS_MISSING, STATUS_STRENGTHEN) and g.priority == PRIORITY_HIGH]
        priority_skills = critical_missing or high_missing or gaps

        first_skill = priority_skills[0].skill_name if priority_skills else "SQL"
        return (
            f"### 🎯 Khuyến nghị thứ tự ưu tiên học tập cho **{target_role.role_name}**:\n\n"
            f"Bạn nên ưu tiên học **{first_skill}** trước vì đây là kỹ năng có mức độ ưu tiên cao nhất (`{priority_skills[0].priority}`) "
            f"và ảnh hưởng trực tiếp nhất đến Career Readiness của bạn.\n\n"
            f"- **Mục tiêu:** Nâng kỹ năng {first_skill} lên mức Intermediate.\n"
            f"- **Thời gian phân bổ:** Khoảng 6-8 giờ / tuần trong 30 ngày đầu tiên.\n"
            f"- Sau khi đạt nền tảng {first_skill}, bạn mới nên chuyển sang các công cụ trực quan hoá hoặc nâng cao tiếp theo."
        )

    # CÂU HỎI 4: "Tôi có đủ khả năng apply Fresher chưa?"
    if "fresher" in q_lower or "apply" in q_lower or "xin việc" in q_lower or "sẵn sàng" in q_lower:
        ready_score = next(r.readiness_score for f, r in ranked if f.role_id == target_role.role_id)
        has_port = profile.experience.has_portfolio()

        if ready_score >= 70.0 and has_port:
            return (
                f"### ✅ Đánh giá mức độ sẵn sàng ứng tuyển Fresher **{target_role.role_name}**:\n\n"
                f"**Mức độ sẵn sàng: {ready_score:.1f}% (Khá cao)**\n\n"
                f"Bạn **ĐÃ ĐỦ ĐIỀU KIỆN** để bắt đầu nộp CV vào các vị trí Fresher / Junior {target_role.role_name}! "
                f"Hãy tự tin hoàn thiện CV nêu bật các dự án thực tế đã làm và chuẩn bị kỹ phần câu hỏi phỏng vấn kỹ thuật."
            )
        else:
            return (
                f"### ⏳ Đánh giá mức độ sẵn sàng ứng tuyển Fresher **{target_role.role_name}**:\n\n"
                f"**Mức độ sẵn sàng hiện tại: {ready_score:.1f}% (Cần bổ sung thêm)**\n\n"
                f"Hiện tại bạn **chưa nên apply ngay** các đợt tuyển dụng lớn vì còn thiếu một số điều kiện then chốt:\n"
                f"- Portfolio dự án thực tế: {'Đã có' if has_port else 'Chưa có (Cần ít nhất 1-2 dự án hoàn chỉnh)'}\n"
                f"- Độ bao phủ kỹ năng bắt buộc: Đạt {target_role.required_skills and len(grouped[STATUS_HAVE])} kỹ năng\n\n"
                f"**Lời khuyên:** Dành 1–3 tháng theo lộ trình tại Tab 5 để nâng Readiness lên trên 70% trước khi chính thức ứng tuyển."
            )

    # Mặc định: Phân tích tổng quan grounded
    return (
        f"### 🧭 Phân tích nghề nghiệp cho bạn:\n\n"
        f"Dựa trên hồ sơ của bạn, nghề có mức độ phù hợp cao nhất là **{top1_fit.role_name}** "
        f"(Fit: **{top1_fit.fit_score:.1f}%**, Readiness: **{top1_ready.readiness_score:.1f}%**).\n\n"
        f"**Các kỹ năng cần bổ sung ngay:** {', '.join(g.skill_name for g in grouped[STATUS_MISSING][:3]) if grouped[STATUS_MISSING] else 'Đã đáp ứng đủ kỹ năng nền tảng'}.\n"
        f"Bạn có thể chọn các câu hỏi gợi ý bên trên hoặc xem chi tiết tại tab **Nghề phù hợp**, **Khoảng cách kỹ năng** và **Lộ trình phát triển**."
    )
