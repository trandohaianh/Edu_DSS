"""Student Learning Profile — Hồ sơ học tập cá nhân hóa đa chiều dựa trên bằng chứng LMS.

Mục 5 Yêu cầu:
- Loại bỏ hoàn toàn việc coi `student_score < 0.9 * class_average` là động cơ cá nhân hóa chính.
- Xây dựng StudentLearningProfile dựa trên bằng chứng thực tế từ LMS:
  + academic: quiz score, assignment score, exam score, topic score, prerequisite performance
  + question level: correct, response time, difficulty, attempt count, hint count, skipped, repeated error, subskill
  + behavior: login frequency, active days, session duration, material views, video completion, practice frequency, lateness
  + learning: learning velocity, time to mastery, delayed retention, repeated misconception, individual historical baseline
- TUYỆT ĐỐI không sử dụng name / email / student_id làm đặc trưng dự đoán hoặc đánh giá học lực.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AcademicEvidence:
    quiz_average: float = 0.0
    assignment_average: float = 0.0
    exam_score: float = 0.0
    topic_scores: Dict[str, float] = field(default_factory=dict)
    prerequisite_mastery: Dict[str, float] = field(default_factory=dict)


@dataclass
class QuestionLevelEvidence:
    accuracy_rate: float = 0.0
    average_response_time_seconds: float = 0.0
    attempt_count_per_question: float = 1.0
    hint_requests_count: int = 0
    skipped_questions_count: int = 0
    repeated_error_patterns: List[str] = field(default_factory=list)
    subskill_mastery: Dict[str, float] = field(default_factory=dict)


@dataclass
class BehavioralEvidence:
    active_days_last_month: int = 0
    login_frequency_per_week: float = 0.0
    average_session_duration_minutes: float = 0.0
    material_views_count: int = 0
    video_completion_rate: float = 0.0
    practice_frequency_per_week: float = 0.0
    submission_lateness_count: int = 0


@dataclass
class LearningTrajectory:
    learning_velocity: float = 1.0  # tốc độ tiếp thu so với tiêu chuẩn
    time_to_mastery_hours: float = 0.0
    delayed_retention_rate: float = 0.0  # tỷ lệ nhớ lại sau 1-2 tuần
    repeated_misconceptions: List[str] = field(default_factory=list)
    historical_baseline_score: float = 0.0  # baseline cá nhân của chính sinh viên
    score_trend: str = "stable"  # "improving" | "stable" | "declining"


@dataclass
class StudentLearningProfile:
    student_pseudonym: str
    course_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    academic: AcademicEvidence = field(default_factory=AcademicEvidence)
    question_level: QuestionLevelEvidence = field(default_factory=QuestionLevelEvidence)
    behavioral: BehavioralEvidence = field(default_factory=BehavioralEvidence)
    trajectory: LearningTrajectory = field(default_factory=LearningTrajectory)
    secondary_class_context: Dict[str, float] = field(default_factory=dict)  # Trung bình lớp chỉ làm bối cảnh thứ cấp

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def build_from_lms_records(
        cls,
        student_id: str,
        course_id: str,
        raw_lms_data: Dict[str, Any],
        class_averages: Optional[Dict[str, float]] = None,
    ) -> StudentLearningProfile:
        """Khởi tạo StudentLearningProfile từ dữ liệu thô của LMS mà không dùng PII."""
        from dss.services.privacy_service import privacy_service
        pseudonym = privacy_service.generate_pseudonym(student_id)

        # 1. Trích xuất học thuật (Academic)
        topic_scores = raw_lms_data.get("topic_scores", {})
        academic = AcademicEvidence(
            quiz_average=float(raw_lms_data.get("quiz_score", raw_lms_data.get("diem_chuyen_can", 7.0))),
            assignment_average=float(raw_lms_data.get("assignment_score", raw_lms_data.get("diem_giua_ky", 6.5))),
            exam_score=float(raw_lms_data.get("exam_score", raw_lms_data.get("diem_cuoi_ky", 6.0))),
            topic_scores=topic_scores,
            prerequisite_mastery=raw_lms_data.get("prerequisite_mastery", {}),
        )

        # 2. Chi tiết cấp câu hỏi (Question level)
        question_level = QuestionLevelEvidence(
            accuracy_rate=float(raw_lms_data.get("accuracy_rate", 0.7)),
            average_response_time_seconds=float(raw_lms_data.get("avg_response_time", 45.0)),
            attempt_count_per_question=float(raw_lms_data.get("attempt_count", 1.2)),
            hint_requests_count=int(raw_lms_data.get("hint_count", 2)),
            skipped_questions_count=int(raw_lms_data.get("skipped_count", 0)),
            repeated_error_patterns=raw_lms_data.get("repeated_errors", []),
            subskill_mastery=raw_lms_data.get("subskill_mastery", {}),
        )

        # 3. Hành vi (Behavioral)
        behavioral = BehavioralEvidence(
            active_days_last_month=int(raw_lms_data.get("active_days", 14)),
            login_frequency_per_week=float(raw_lms_data.get("login_freq", 3.5)),
            average_session_duration_minutes=float(raw_lms_data.get("session_duration", 35.0)),
            material_views_count=int(raw_lms_data.get("material_views", 18)),
            video_completion_rate=float(raw_lms_data.get("video_completion", 0.65)),
            practice_frequency_per_week=float(raw_lms_data.get("practice_freq", 2.0)),
            submission_lateness_count=int(raw_lms_data.get("lateness_count", 0)),
        )

        # 4. Quỹ đạo học tập & Baseline cá nhân (Trajectory & Personal Baseline)
        historical_baseline = float(raw_lms_data.get("gpa_previous", raw_lms_data.get("baseline_score", 6.5)))
        current_est = (academic.quiz_average * 0.2 + academic.assignment_average * 0.3 + academic.exam_score * 0.5)
        trend = "improving" if current_est > historical_baseline + 0.3 else (
            "declining" if current_est < historical_baseline - 0.3 else "stable"
        )

        trajectory = LearningTrajectory(
            learning_velocity=float(raw_lms_data.get("learning_velocity", 1.0)),
            time_to_mastery_hours=float(raw_lms_data.get("time_to_mastery", 12.0)),
            delayed_retention_rate=float(raw_lms_data.get("retention_rate", 0.72)),
            repeated_misconceptions=raw_lms_data.get("misconceptions", []),
            historical_baseline_score=historical_baseline,
            score_trend=trend,
        )

        return cls(
            student_pseudonym=pseudonym,
            course_id=course_id,
            academic=academic,
            question_level=question_level,
            behavioral=behavioral,
            trajectory=trajectory,
            secondary_class_context=class_averages or {},
        )
