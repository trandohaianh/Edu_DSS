"""Test suite cho Tích Hợp LMS + CMS và Closed-Loop Feedback Pipeline trong EduDSS.

Kiểm chứng các yêu cầu bắt buộc:
1. Tầng trừu tượng LMSRepository và CMSRepository hỗ trợ 3 chế độ (DEMO, MOCK, REAL_CONNECTOR).
2. Trạng thái tích hợp minh bạch: IMPLEMENTED, DEMO, PARTIAL, FUTURE REAL INTEGRATION.
3. Dữ liệu LMS cung cấp năng lực học tập thực tế, môn mạnh/yếu, tiến độ, giờ học, chuyên cần và minh chứng.
4. CMS ánh xạ học phần -> kỹ năng, nội dung -> competency, và tìm tài nguyên cụ thể cho skill gap.
5. Mỗi Gap Item truy vết được 2 chiều: LMS Evidence (nguyên nhân) và CMS Resource (giải pháp).
6. Vòng lặp phản hồi khép kín (Closed-Loop Feedback): Hành động học tập trên LMS lập tức
   nâng cấp Skill Profile, tự động tính lại Career Readiness và cập nhật khuyến nghị.
7. Toàn bộ quá trình vận hành dựa trên structured data, không phụ thuộc vào LLM.
"""
from __future__ import annotations

import pytest

from dss.services.career_knowledge_base import get_role
from dss.services.career_lms_cms_pipeline import (
    ClosedLoopActionResult,
    TracedGapItem,
    compute_traced_gap_analysis,
    enrich_career_profile_with_lms_cms,
    execute_closed_loop_action,
    generate_traced_roadmap,
)
from dss.services.career_profile import StudentCareerProfile
from dss.services.career_scoring import compute_career_readiness
from dss.services.cms_repository import (
    STATUS_DEMO,
    STATUS_FUTURE_REAL,
    STATUS_IMPLEMENTED,
    STATUS_PARTIAL,
    DemoCMSRepository,
    MockCMSRepository,
    RealConnectorCMSRepository,
    get_cms_repository,
)
from dss.services.lms_connector import (
    DemoLMSRepository,
    LMSAssessmentRecord,
    LMSStudentLearningSummary,
    MockLMSRepository,
    RealConnectorLMSRepository,
    get_lms_repository,
)


@pytest.fixture
def base_student_profile() -> StudentCareerProfile:
    raw_scores = {
        "diem_thong_ke": 8.0,
        "diem_xu_ly_du_lieu": 6.0,  # SQL ở mức cơ bản
        "diem_truc_quan_hoa": 7.5,
        "diem_lap_trinh": 7.0,
        "final_score": 7.2,
    }
    return StudentCareerProfile.build_from_row("SV_TEST_LMS", raw_scores, data_source="DEMO")


# ============================================================================
# 1. KIỂM THỬ TẦNG TRỪU TƯỢNG VÀ TRẠNG THÁI TÍCH HỢP
# ============================================================================
def test_lms_repository_modes_and_status():
    demo_lms = DemoLMSRepository()
    mock_lms = MockLMSRepository()
    real_lms = RealConnectorLMSRepository(db_path=":memory:")

    assert demo_lms.mode == "DEMO"
    assert mock_lms.mode == "MOCK"
    assert real_lms.mode == "REAL_CONNECTOR"

    status = demo_lms.get_integration_status()
    assert status["architecture_status"] == STATUS_IMPLEMENTED
    assert status["data_mode_status"] == STATUS_DEMO
    assert status["external_systems"] == STATUS_FUTURE_REAL

    real_status = real_lms.get_integration_status()
    assert real_status["data_mode_status"] == STATUS_PARTIAL


def test_cms_repository_modes_and_status():
    demo_cms = DemoCMSRepository()
    mock_cms = MockCMSRepository()
    real_cms = RealConnectorCMSRepository()

    assert demo_cms.mode == "DEMO"
    assert mock_cms.mode == "MOCK"
    assert real_cms.mode == "REAL_CONNECTOR"

    status = demo_cms.get_integration_status()
    assert status["architecture_status"] == STATUS_IMPLEMENTED
    assert status["data_mode_status"] == STATUS_DEMO
    assert status["external_systems"] == STATUS_FUTURE_REAL


# ============================================================================
# 2. KIỂM THỬ TRÍCH XUẤT DỮ LIỆU LMS VÀ LÀM GIÀU HỒ SƠ
# ============================================================================
def test_enrich_career_profile_with_lms(base_student_profile):
    lms = DemoLMSRepository()
    cms = DemoCMSRepository()

    summary = enrich_career_profile_with_lms_cms(base_student_profile, lms, cms)

    assert isinstance(summary, LMSStudentLearningSummary)
    assert summary.gpa > 0.0
    assert summary.total_learning_hours > 0.0
    assert summary.average_attendance >= 90.0
    assert summary.average_progress > 0.0
    assert len(summary.evidences) > 0

    # Hồ sơ kỹ năng phải được bơm bằng chứng LMS xác thực
    sql_item = base_student_profile.skills.get("SQL")
    assert any("[LMS]" in ev for ev in sql_item.evidence)
    assert sql_item.confidence == "high"


# ============================================================================
# 3. KIỂM THỬ TRUY VẾT 2 CHIỀU TRONG GAP ANALYSIS (LMS Evidence & CMS Match)
# ============================================================================
def test_traced_gap_analysis_contains_lms_and_cms_remedy(base_student_profile):
    lms = DemoLMSRepository()
    cms = DemoCMSRepository()
    role = get_role("data_analyst")

    traced_gaps = compute_traced_gap_analysis(base_student_profile, role, lms, cms)
    assert len(traced_gaps) > 0

    # Tìm gap của kỹ năng SQL
    sql_gap = next((g for g in traced_gaps if g.skill_name == "SQL"), None)
    assert sql_gap is not None
    assert isinstance(sql_gap, TracedGapItem)

    # 1. Phải có LMS Evidence rõ ràng
    assert "[LMS Evidence]" in sql_gap.lms_evidence

    # 2. Phải có CMS Match chỉ rõ khóa học/bài học/lab cụ thể
    assert sql_gap.cms_match is not None
    assert sql_gap.cms_match.course_code == "CS201"
    assert "Window Functions" in sql_gap.cms_match.lesson_title
    assert "thực hành SQL Analytics" in sql_gap.cms_recommendation_action


# ============================================================================
# 4. KIỂM THỬ LỘ TRÌNH HỌC TẬP TÍCH HỢP TÀI NGUYÊN CMS
# ============================================================================
def test_traced_roadmap_integration(base_student_profile):
    lms = DemoLMSRepository()
    cms = DemoCMSRepository()
    role = get_role("data_analyst")
    readiness = 65.0

    roadmap = generate_traced_roadmap(base_student_profile, role, readiness, lms, cms)
    assert roadmap.target_role_id == "data_analyst"

    all_tasks = [t for tasks in roadmap.buckets.values() for t in tasks]
    assert len(all_tasks) > 0

    # Mỗi task phải có lý do truy vết từ LMS và tài nguyên trích xuất từ CMS
    for t in all_tasks:
        assert "[LMS Evidence]" in t.reason
        assert t.resource is not None and len(t.resource) > 0
        assert t.estimated_effort is not None


# ============================================================================
# 5. KIỂM THỬ CLOSED-LOOP FEEDBACK: TỰ ĐỘNG TÍNH LẠI READINESS
# ============================================================================
def test_closed_loop_feedback_recomputes_readiness(base_student_profile):
    lms = DemoLMSRepository()
    cms = DemoCMSRepository()
    role = get_role("data_analyst")

    # Điểm sẵn sàng ban đầu
    initial_readiness = compute_career_readiness(base_student_profile, role).readiness_score
    initial_sql_level = base_student_profile.skills.get("SQL").skill_level
    assert initial_sql_level in ("None", "Basic")

    # Sinh viên thực hiện hành động học tập: nộp bài thực hành Window Functions đạt 8.5/10
    result = execute_closed_loop_action(
        student_id="SV_TEST_LMS",
        profile=base_student_profile,
        role_id="data_analyst",
        skill_to_upgrade="SQL",
        new_level="Intermediate",
        assessment_score=8.5,
        max_score=10.0,
        duration_minutes=60,
        course_id="CS201",
        activity_title="Bài thực hành SQL Analytics (Window Functions)",
        lms_repo=lms,
        cms_repo=cms,
    )

    assert isinstance(result, ClosedLoopActionResult)
    assert result.skill_upgraded == "SQL"
    assert result.new_level == "Intermediate"
    assert result.lms_record.score == 8.5
    assert result.lms_record.passed is True

    # 1. LMS đã ghi nhận submission vào lịch sử
    summary = lms.get_student_learning_summary("SV_TEST_LMS")
    assert any(a.title == "Bài thực hành SQL Analytics (Window Functions)" for a in summary.assessment_history)

    # 2. Skill Profile đã được nâng lên Intermediate
    updated_sql = base_student_profile.skills.get("SQL")
    assert updated_sql.skill_level == "Intermediate"
    assert any("[LMS Action]" in ev for ev in updated_sql.evidence)

    # 3. Career Readiness TỰ ĐỘNG TĂNG sau hành động học tập
    assert result.new_readiness > initial_readiness
    assert result.delta_readiness > 0.0

    # Task tương ứng trong lộ trình được ghi nhận hoàn thành
    expected_task_id = "task_data_analyst_sql"
    assert expected_task_id in base_student_profile.completed_tasks


# ============================================================================
# 6. KIỂM THỬ ĐỘ ĐỘC LẬP VÀ TINH THẦN DETERMINISTIC (KHÔNG PHỤ THUỘC LLM)
# ============================================================================
def test_pipeline_runs_without_llm_calls(base_student_profile):
    """Xác minh toàn bộ pipeline tính toán structured data hoàn toàn độc lập với LLM API."""
    mock_lms = MockLMSRepository()
    mock_cms = MockCMSRepository()
    role = get_role("backend_developer")

    # Pipeline chạy hoàn toàn trơn tru, không phát sinh bất kỳ ngoại lệ kết nối mạng hay LLM
    enrich_career_profile_with_lms_cms(base_student_profile, mock_lms, mock_cms)
    gaps = compute_traced_gap_analysis(base_student_profile, role, mock_lms, mock_cms)
    roadmap = generate_traced_roadmap(base_student_profile, role, 50.0, mock_lms, mock_cms)

    assert len(gaps) > 0
    assert len(roadmap.buckets) == 3
