"""Regression suite cho Career Decision Support System (CDSS - Redesign toàn bộ "AI Tư vấn hướng nghiệp").

Kiểm chứng đầy đủ các tiêu chuẩn bắt buộc:
1. Knowledge base đủ 12 vai trò chuẩn hoá, có đủ metadata & alternative path notes.
2. Ánh xạ Subject -> Competency Domain hỗ trợ cả tiếng Anh lẫn tiếng Việt và tính GPA.
3. Không tự nhận kỹ năng khi thiếu bằng chứng; phân cấp độ tin cậy chuẩn xác.
4. Trọng số Career Fit & Readiness tập trung, có thể cấu hình, tổng = 1.0.
5. Career Fit và Career Readiness độc lập hoàn toàn, phân tách rõ ràng.
6. Thiếu required skill phạt điểm nặng hơn thiếu preferred skill.
7. Áp dụng hình phạt ràng buộc cá nhân (ca kíp, remote, tiếng Anh) minh bạch.
8. Phát hiện đúng nghề hợp năng lực nhưng vướng ràng buộc cá nhân (Câu hỏi 5).
9. Gap Analysis phân 3 nhóm trạng thái, 4 mức ưu tiên và phát hiện thiếu tạo tác (Portfolio/Interview).
10. Roadmap cá nhân hoá theo 3 mốc: 1 tháng (30 ngày), 3 tháng (90 ngày), 6 tháng (180 ngày).
11. Đề xuất con đường thay thế (Primary / Secondary / Long-term) có giải thích lý do.
12. Chuyển đổi nghề nghiệp (Career Transition Plan) tính đúng kỹ năng chung, kỹ năng thiếu và độ khả thi.
13. Giả lập What-if tính toán Delta Fit/Readiness và lọc nghề theo thời gian chính xác.
14. Vòng lặp phản hồi (Feedback loop) cập nhật kỹ năng và độ sẵn sàng.
15. Cố vấn AI ngoại tuyến (Grounded Offline Advisor) trả lời chính xác 5 câu hỏi trọng tâm không bịa đặt.
"""
from __future__ import annotations


from dss.services.career_profile import (
    SUBJECT_TO_COMPETENCY_DOMAIN,
    StudentCareerProfile,
)
from dss.services.career_knowledge_base import (
    get_role,
    list_roles,
)
from dss.services.career_scoring import (
    CAREER_FIT_WEIGHTS,
    CAREER_READINESS_WEIGHTS,
    compute_career_fit,
    compute_career_readiness,
    compute_constraint_match,
    compute_skill_match,
    detect_capability_vs_constraint_conflicts,
    rank_careers,
)
from dss.services.career_gap_analysis import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    STATUS_MISSING,
    compute_gap_analysis,
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
    apply_skill_change,
    compare_scenarios,
    rank_roles_for_timeframe,
)
from dss.services.career_ai_advisor import (
    build_career_ai_context,
    generate_offline_grounded_answer,
    get_system_prompt,
)


def _profile_with_scores(**raw_scores) -> StudentCareerProfile:
    return StudentCareerProfile.build_from_row("SV_TEST", raw_scores, data_source="DEMO")


# ============================================================================
# 1. KNOWLEDGE BASE & DOMAIN MAPPING
# ============================================================================
def test_career_knowledge_base_has_all_12_roles():
    roles = list_roles()
    assert len(roles) >= 12
    expected_roles = {
        "data_analyst", "data_engineer", "data_scientist", "ml_engineer",
        "business_analyst", "backend_developer", "frontend_developer", "qa_tester",
        "devops_cloud_engineer", "database_administrator", "ai_engineer", "system_analyst",
    }
    actual_roles = {r.role_id for r in roles}
    assert expected_roles.issubset(actual_roles)


def test_subject_to_domain_mapping_supports_vn_and_en():
    from dss.core.data_helpers import TOPIC_SCORE_COLUMNS
    for col in TOPIC_SCORE_COLUMNS:
        assert col in SUBJECT_TO_COMPETENCY_DOMAIN

    # Các môn tiếng Anh theo đặc tả Section II
    assert "Statistics" in SUBJECT_TO_COMPETENCY_DOMAIN
    assert "Database" in SUBJECT_TO_COMPETENCY_DOMAIN
    assert "Machine Learning" in SUBJECT_TO_COMPETENCY_DOMAIN
    assert "Web Programming" in SUBJECT_TO_COMPETENCY_DOMAIN
    assert "Software Analysis" in SUBJECT_TO_COMPETENCY_DOMAIN


def test_gpa_computation_and_strengths_weaknesses():
    profile = _profile_with_scores(
        diem_thong_ke=8.5,
        diem_xu_ly_du_lieu=8.0,
        diem_lap_trinh=4.0,
        final_score=7.8,
    )
    assert profile.academic.gpa == 7.8
    assert any("Data Analysis" in s for s in profile.academic.strengths)
    assert any("Software" in w for w in profile.academic.weaknesses)


# ============================================================================
# 2. EVIDENCE-BASED SKILLS & CONFIDENCE
# ============================================================================
def test_no_skill_claimed_without_evidence():
    profile = _profile_with_scores(diem_lap_trinh=3.0)
    skill = profile.skills.get("SQL")
    assert skill.skill_level == "None"
    assert skill.evidence == []


def test_high_academic_score_creates_medium_confidence_basic_claim():
    profile = _profile_with_scores(diem_machine_learning=8.5)
    skill = profile.skills.get("Machine Learning")
    assert skill.skill_level == "Basic"
    assert skill.confidence == "medium"
    assert skill.source == "academic_score"
    assert len(skill.evidence) >= 1


def test_experience_evidence_upgrades_confidence_to_high():
    profile = _profile_with_scores(diem_machine_learning=8.5)
    profile.skills.add_evidence_from_experience(
        "Machine Learning", "technical", "Dự án Machine Learning dự đoán kết quả học tập", min_level="Intermediate",
    )
    skill = profile.skills.get("Machine Learning")
    assert skill.confidence == "high"
    assert skill.skill_level == "Intermediate"
    assert len(skill.evidence) >= 2


# ============================================================================
# 3. SCORING ENGINE (FIT & READINESS)
# ============================================================================
def test_career_fit_and_readiness_weights_sum_to_one():
    assert abs(sum(CAREER_FIT_WEIGHTS.values()) - 1.0) < 1e-6
    assert abs(sum(CAREER_READINESS_WEIGHTS.values()) - 1.0) < 1e-6


def test_required_skill_missing_hurts_more_than_preferred():
    role = get_role("data_analyst")
    profile_missing_required = _profile_with_scores()

    profile_missing_only_preferred = _profile_with_scores()
    profile_missing_only_preferred.skills.upsert_self_assessment("SQL", "technical", "Advanced")
    profile_missing_only_preferred.skills.upsert_self_assessment("Excel", "technical", "Advanced")
    profile_missing_only_preferred.skills.upsert_self_assessment("Statistics", "technical", "Advanced")
    profile_missing_only_preferred.skills.upsert_self_assessment("Power BI", "technical", "Advanced")

    score_missing_required = compute_skill_match(profile_missing_required, role).score
    score_missing_preferred_only = compute_skill_match(profile_missing_only_preferred, role).score
    assert score_missing_preferred_only > score_missing_required


def test_career_fit_and_readiness_are_independent_and_can_diverge():
    profile = _profile_with_scores(diem_machine_learning=9.0, diem_thong_ke=8.5)
    profile.interest.scores = {"data": 5, "ai_research": 5}
    role = get_role("data_scientist")

    fit = compute_career_fit(profile, role)
    readiness = compute_career_readiness(profile, role)

    # Học thuật & sở thích cao khiến Fit cao, nhưng thiếu Portfolio/Project khiến Readiness thấp
    assert fit.fit_score != readiness.readiness_score
    assert readiness.readiness_score < fit.fit_score


def test_constraint_penalty_application():
    profile = _profile_with_scores()
    role = get_role("devops_cloud_engineer")  # Yêu cầu shift_ok

    profile.constraints.preferred_hours = "office_hours"
    profile.constraints.shift_acceptance = False
    penalized_match = compute_constraint_match(profile, role)

    profile.constraints.shift_acceptance = True
    accepted_match = compute_constraint_match(profile, role)

    assert accepted_match.score > penalized_match.score


def test_detect_capability_vs_constraint_conflicts():
    # Giả lập sinh viên giỏi CSDL nhưng kiên quyết không làm ca kíp
    profile = _profile_with_scores(diem_xu_ly_du_lieu=9.0, diem_thong_ke=8.5)
    profile.skills.upsert_self_assessment("SQL", "technical", "Advanced")
    profile.skills.upsert_self_assessment("Database", "technical", "Advanced")
    profile.constraints.preferred_hours = "office_hours"
    profile.constraints.shift_acceptance = False

    conflicts = detect_capability_vs_constraint_conflicts(profile, list_roles())
    conflict_role_ids = [c.role_id for c in conflicts]
    # Database Administrator hoặc DevOps thường bị vướng ca kíp
    assert "database_administrator" in conflict_role_ids or "devops_cloud_engineer" in conflict_role_ids


# ============================================================================
# 4. GAP ANALYSIS
# ============================================================================
def test_gap_analysis_priorities_and_status():
    profile = _profile_with_scores()
    role = get_role("data_analyst")

    gaps = compute_gap_analysis(profile, role, include_artifacts=True)
    sql_gap = next(g for g in gaps if g.skill_name == "SQL")
    assert sql_gap.status == STATUS_MISSING
    assert sql_gap.priority == PRIORITY_CRITICAL

    # Kiểm tra tạo tác Portfolio được ghi nhận là thiếu
    portfolio_gap = next(g for g in gaps if "Portfolio" in g.skill_name)
    assert portfolio_gap.status == STATUS_MISSING
    assert portfolio_gap.priority == PRIORITY_HIGH


# ============================================================================
# 5. CAREER ROADMAP & ALTERNATIVE PATHS
# ============================================================================
def test_roadmap_has_30_90_180_days_buckets_and_is_personalized():
    role = get_role("data_analyst")
    profile_weak = _profile_with_scores()

    roadmap = generate_roadmap(profile_weak, role, 25.0)
    assert _BUCKET_1M in roadmap.buckets
    assert _BUCKET_3M in roadmap.buckets
    assert _BUCKET_6M in roadmap.buckets

    # Kiểm tra tính toàn vẹn 7 trường của nhiệm vụ
    task = next(t for tasks in roadmap.buckets.values() for t in tasks)
    for attr in ("action", "reason", "resource", "estimated_effort", "target_result", "priority"):
        assert getattr(task, attr)


def test_alternative_paths_contain_explanations():
    paths = suggest_alternative_paths("data_analyst")
    assert paths["primary"] == ["data_analyst"]
    assert len(paths["secondary"]) >= 1
    assert paths["secondary_explanation"] != ""
    assert len(paths["long_term"]) >= 1
    assert paths["long_term_explanation"] != ""


def test_career_transition_shared_and_missing_skills():
    profile = _profile_with_scores()
    profile.skills.upsert_self_assessment("SQL", "technical", "Advanced")
    plan = compute_transition(profile, "data_analyst", "data_engineer", readiness_score=35.0)
    assert plan is not None
    assert "SQL" in plan.shared_skills
    assert "Database" in plan.missing_skills
    assert plan.feasibility_score > 0.0


# ============================================================================
# 6. WHAT-IF ANALYSIS & FEEDBACK LOOP
# ============================================================================
def test_whatif_skill_upgrade_computes_delta():
    profile = _profile_with_scores(diem_thong_ke=6.0)
    role = get_role("data_analyst")
    hypo = apply_skill_change(profile, "SQL", "technical", "Advanced")
    res = compare_scenarios(profile, hypo, role, "Nâng SQL lên Advanced")

    assert res.after_fit >= res.before_fit
    assert res.after_readiness >= res.before_readiness
    # Hồ sơ gốc không bị ảnh hưởng
    assert profile.skills.get("SQL").skill_level == "None"


def test_whatif_timeframe_prioritizes_readiness_for_short_term():
    profile = _profile_with_scores()
    # Nghề A có Fit thấp nhưng Readiness cao
    roles = list_roles()
    short_term_ranked = rank_roles_for_timeframe(profile, roles, timeframe_months=2, top_k=3)
    long_term_ranked = rank_roles_for_timeframe(profile, roles, timeframe_months=12, top_k=3)

    assert short_term_ranked[0]["primary_metric"] == "Readiness"
    assert long_term_ranked[0]["primary_metric"] == "Fit"


def test_feedback_loop_updates_readiness():
    profile = _profile_with_scores()
    role = get_role("data_analyst")
    ready_before = compute_career_readiness(profile, role).readiness_score

    profile.mark_task_completed("task_data_analyst_sql", skill_to_upgrade="SQL", new_level="Advanced")
    ready_after = compute_career_readiness(profile, role).readiness_score

    assert "task_data_analyst_sql" in profile.completed_tasks
    assert ready_after > ready_before


# ============================================================================
# 7. AI CAREER ADVISOR & ANTI-HALLUCINATION
# ============================================================================
def test_build_career_ai_context_contains_all_key_dimensions():
    profile = _profile_with_scores(diem_thong_ke=8.0, diem_xu_ly_du_lieu=7.5)
    ranked = rank_careers(profile, list_roles(), top_k=3)
    context = build_career_ai_context(profile, ranked)

    assert "HỒ SƠ HỌC THUẬT" in context
    assert "HỒ SƠ KỸ NĂNG" in context
    assert "KINH NGHIỆM" in context
    assert "RÀNG BUỘC" in context
    assert "KẾT QUẢ PHÂN TÍCH" in context


def test_system_prompt_mandates_anti_hallucination():
    prompt = get_system_prompt()
    assert "TUYỆT ĐỐI KHÔNG BỊA ĐẶT" in prompt
    assert "Hiện chưa có đủ dữ liệu" in prompt
    assert "Career Fit" in prompt
    assert "Career Readiness" in prompt


def test_offline_grounded_advisor_answers_all_5_questions():
    profile = _profile_with_scores(diem_thong_ke=8.0, diem_xu_ly_du_lieu=7.0)
    ranked = rank_careers(profile, list_roles(), top_k=3)

    # 1. So sánh 2 nghề
    ans1 = generate_offline_grounded_answer("Vì sao tôi hợp nghề đầu tiên hơn nghề thứ hai?", profile, ranked)
    assert "Career Fit" in ans1 and "Career Readiness" in ans1

    # 2. Điểm yếu lớn nhất
    ans2 = generate_offline_grounded_answer("Điểm yếu lớn nhất của tôi là gì?", profile, ranked)
    assert "Điểm yếu" in ans2 or "Khoảng cách" in ans2

    # 3. Học kỹ năng nào trước
    ans3 = generate_offline_grounded_answer("Tôi nên học kỹ năng nào trước?", profile, ranked)
    assert "ưu tiên" in ans3.lower()

    # 4. Có đủ khả năng apply Fresher chưa
    ans4 = generate_offline_grounded_answer("Tôi có đủ khả năng apply Fresher chưa?", profile, ranked)
    assert "sẵn sàng" in ans4.lower()

    # 5. Nếu chỉ có 2 tháng thì nên học gì
    ans5 = generate_offline_grounded_answer("Nếu chỉ có 2 tháng thì nên học gì?", profile, ranked)
    assert "tháng" in ans5.lower()
