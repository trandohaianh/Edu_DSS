"""Audit 2026-09-15 (Issue FUNC-PLAN-001) — LearningPlanGenerator.generate_plan()
tồn tại và có test riêng (tests/adaptive_learning/test_adaptive_learning.py) từ
trước nhưng KHÔNG có điểm gọi thật nào trong dss/tabs/ai_advisor.py: `import
learning_plan_generator, StudentLearningPlan` (dòng 43) nhưng .generate_plan()
chưa từng được gọi — "Kế hoạch học tập 4 tuần" hiển thị cho người dùng luôn
dùng report_service.build_demo_study_plan() (heuristic đơn giản), kể cả khi
provider AI thật đã sẵn sàng.

Test này khoá lại 2 việc:
1. ai_advisor.py giờ THẬT SỰ gọi learning_plan_generator.generate_plan() (không
   chỉ import rồi để đó) — quét mã nguồn trực tiếp, không phụ thuộc UI render.
2. Bộ chuyển đổi `_week_plan_from_structured_plan()` cho ra đúng hình dạng
   week_plan mà checklist/lưu/xuất đã dùng, và bằng chứng (evidence/reason) là
   TÍNH TỪ ĐÚNG plan trả về — không bịa.
"""

from __future__ import annotations

import inspect

from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_profile import StudentLearningProfile
from dss.tabs import ai_advisor


def test_ai_advisor_actually_calls_generate_plan_not_just_imports_it():
    """Regression cho chính lỗi đã audit: import tồn tại nhưng không có điểm gọi.
    Quét SOURCE của module (không phải chỉ __all__/globals) để bắt đúng trường
    hợp 'imported but never called'."""
    source = inspect.getsource(ai_advisor)
    assert "learning_plan_generator.generate_plan(" in source, (
        "learning_plan_generator được import nhưng KHÔNG có điểm gọi .generate_plan() "
        "nào trong ai_advisor.py — đây chính xác là lỗi FUNC-PLAN-001 đã audit."
    )


def test_ai_advisor_no_longer_uses_demo_builder_for_the_real_provider_weekly_plan():
    """Nhánh provider AI THẬT (sau khi plan_stream đã sinh xong) không còn gọi
    lại _build_demo_study_plan() để lấy week_plan — chỉ 3 nhánh Demo tường minh
    còn dùng nó: (1) nút "Tạo kế hoạch nhanh (Demo)" riêng, (2) hộp thoại xác
    nhận khi AI chưa sẵn sàng (nút chính, nhánh demo), (3) tiếp tục hội thoại
    chat sau khi đã ở chế độ mô phỏng."""
    source = inspect.getsource(ai_advisor)
    # "(\n" (không phải "()") để chỉ đếm LỜI GỌI thật (nhiều dòng tham số), loại
    # trừ chuỗi tên hàm xuất hiện trong comment/docstring giải thích.
    demo_builder_call_count = source.count("_build_demo_study_plan(\n")
    assert demo_builder_call_count == 3, (
        f"Kỳ vọng đúng 3 điểm gọi _build_demo_study_plan còn lại (3 nhánh Demo tường minh), "
        f"tìm thấy {demo_builder_call_count} — kiểm tra lại nhánh provider AI thật có lỡ gọi lại không."
    )


def _fake_profile(pseudonym="stu_test", quiz_avg=4.0, assignment_avg=5.0, accuracy=0.5):
    from dss.services.learning_profile import AcademicEvidence, QuestionLevelEvidence

    return StudentLearningProfile(
        student_pseudonym=pseudonym,
        course_id="COURSE_X",
        academic=AcademicEvidence(quiz_average=quiz_avg, assignment_average=assignment_avg),
        question_level=QuestionLevelEvidence(accuracy_rate=accuracy),
    )


def test_week_plan_adapter_shape_matches_checklist_expectations():
    profile = _fake_profile()
    plan = learning_plan_generator.generate_plan(profile)
    week_plan = ai_advisor._week_plan_from_structured_plan(plan, weeks=4)

    assert len(week_plan) == 4
    for i, wp in enumerate(week_plan, start=1):
        assert wp["week"] == i
        assert isinstance(wp["topic"], str) and wp["topic"]
        assert isinstance(wp["action"], str) and wp["action"]
        assert wp["done"] is False


def test_week_plan_adapter_traces_back_to_real_plan_evidence_not_invented():
    """Hành động mỗi tuần phải chứa đúng `reason`/`expected_outcome` LẤY TỪ
    plan.activities thật (không phải chuỗi tự bịa) — kiểm tra bằng cách đối
    chiếu ngược lại đúng field của activity tương ứng."""
    profile = _fake_profile(quiz_avg=3.0, assignment_avg=3.5, accuracy=0.3)
    plan = learning_plan_generator.generate_plan(profile)
    week_plan = ai_advisor._week_plan_from_structured_plan(plan, weeks=len(plan.activities))

    for i, wp in enumerate(week_plan):
        act = plan.activities[i % len(plan.activities)]
        assert act.reason in wp["action"]
        assert act.expected_outcome in wp["action"]


def test_week_plan_adapter_handles_plan_with_no_activities_without_inventing_data():
    """Nếu plan (giả lập) không có activities, KHÔNG được bịa hành động —
    dùng đúng câu trung lập 'Ôn tập chủ đề: <topic>'."""
    from dss.services.learning_plan import StudentLearningPlan

    empty_plan = StudentLearningPlan(
        plan_id="p1",
        student_pseudonym="s1",
        version=1,
        created_at="",
        valid_until="",
        strengths=[],
        weaknesses=["Chủ đề A"],
        diagnoses=[],
        priority_topics=[],
        activities=[],
        assessment_plan="",
        success_metrics={},
        evidence_used=[],
        confidence=0.5,
        next_review_at="",
    )
    week_plan = ai_advisor._week_plan_from_structured_plan(empty_plan, weeks=2)
    assert all("Ôn tập chủ đề" in wp["action"] for wp in week_plan)
    assert all(wp["topic"] == "Chủ đề A" for wp in week_plan)
