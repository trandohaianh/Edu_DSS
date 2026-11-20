"""Independent-review finding: `LearningPlanGenerator.generate_plan()` hard-codes
`confidence=0.85` for EVERY student regardless of input data, and `ai_advisor.py`
displays it verbatim as "Độ tin cậy kế hoạch: 85%" — presenting a fixed literal
as if it were a measured/calibrated confidence score. Distinct from E-5
(`DiagnosisEngine` hypothesis confidence), which remains confirmed NON-user-facing
on re-check (grep across dss/tabs finds zero renders of hypothesis.confidence)."""

from __future__ import annotations

import inspect

from dss.services.learning_plan import LearningPlanGenerator
from dss.services.learning_profile import (
    AcademicEvidence,
    BehavioralEvidence,
    LearningTrajectory,
    QuestionLevelEvidence,
    StudentLearningProfile,
)
from dss.tabs import ai_advisor


def _make_profile(**overrides):
    defaults = dict(
        student_pseudonym="sv_test",
        course_id="CS101",
        academic=AcademicEvidence(quiz_average=8.0, assignment_average=8.0),
        behavioral=BehavioralEvidence(
            active_days_last_month=20, practice_frequency_per_week=4, average_session_duration_minutes=45
        ),
        trajectory=LearningTrajectory(score_trend="improving", learning_velocity=1.2),
        question_level=QuestionLevelEvidence(accuracy_rate=0.9),
    )
    defaults.update(overrides)
    return StudentLearningProfile(**defaults)


def test_confidence_is_identical_regardless_of_student_data():
    """Nếu `confidence` thật sự là 1 giá trị đo lường, nó phải KHÁC nhau giữa
    hồ sơ sinh viên xuất sắc và hồ sơ sinh viên rất yếu — nhưng vì đây là hằng
    số cố định, cả 2 luôn ra CÙNG 1 con số. Test này ĐẶC TẢ thực tế đó (không
    phải khẳng định đây là hành vi mong muốn) để bất kỳ ai sau này lỡ tính
    `confidence` từ dữ liệu thật sẽ thấy test này fail và biết cần cập nhật."""
    gen = LearningPlanGenerator()
    strong_profile = _make_profile(
        academic=AcademicEvidence(quiz_average=9.5, assignment_average=9.5),
        question_level=QuestionLevelEvidence(accuracy_rate=0.98),
    )
    weak_profile = _make_profile(
        academic=AcademicEvidence(quiz_average=2.0, assignment_average=2.5),
        question_level=QuestionLevelEvidence(accuracy_rate=0.15),
    )
    strong_plan = gen.generate_plan(strong_profile)
    weak_plan = gen.generate_plan(weak_profile)
    assert strong_plan.confidence == weak_plan.confidence == 0.85


def test_ai_advisor_no_longer_renders_plan_confidence_as_a_measured_percentage():
    """UI KHÔNG được hiển thị `_structured_plan.confidence` dưới dạng phần trăm
    (từng gây hiểu nhầm là chỉ số đo lường/hiệu chuẩn cho MỌI sinh viên)."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert "_structured_plan.confidence:.0%" not in source, (
        "ai_advisor.py vẫn hiển thị confidence (hằng số cố định 0.85 cho MỌI "
        "sinh viên) như một tỷ lệ phần trăm đo lường được."
    )


def test_learning_plan_module_documents_confidence_is_a_fixed_constant():
    """Mã nguồn PHẢI tự ghi rõ đây là hằng số cố định, không phải giá trị đo
    lường — để người đọc/bảo trì sau này không hiểu nhầm và không vô tình dùng
    làm căn cứ ra quyết định."""
    source = inspect.getsource(LearningPlanGenerator.generate_plan)
    lowered = source.lower()
    assert (
        "hằng số" in lowered or "khong phai" in lowered.replace("ô", "o").replace("đ", "d") or "không phải" in lowered
    )
