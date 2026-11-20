"""Evidence-based structured plans. Unknown schedules remain None.

Recommendations and review dates are policy, never measured outcomes.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dss.core.runtime_mode import synthetic_data_allowed
from dss.services.diagnosis_engine import (
    CATEGORY_INSUFFICIENT_DATA,
    CATEGORY_MASTERY_ON_TRACK,
    diagnosis_engine,
)
from dss.services.learning_profile import StudentLearningProfile, observed_mapping, observed_number
from dss.services.resource_catalog import resource_catalog

_LEGACY_DEMO_RESOURCE_IDS = {
    "res_math_calc_01",
    "res_prog_python_01",
    "res_time_pomodoro_01",
    "res_db_sql_01",
    "res_ml_eval_01",
}


def _key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _resource_id_for_topic(item: Any, course_id: str, topic_id: str) -> Optional[str]:
    if not isinstance(item, dict) or not _key(course_id) or not _key(topic_id):
        return None
    if item.get("status") != "APPROVED":
        return None
    if _key(item.get("course_id") or item.get("course")) != _key(course_id):
        return None
    if _key(item.get("topic_id") or item.get("topic")) != _key(topic_id):
        return None
    resource_id = item.get("resource_id")
    if not isinstance(resource_id, str) or not resource_id.strip():
        return None
    demo = (
        item.get("is_demo") is True
        or resource_id in _LEGACY_DEMO_RESOURCE_IDS
        or _key(item.get("data_source")) in {"demo", "synthetic", "seed"}
    )
    if demo and not synthetic_data_allowed():
        return None
    verified_cms = item.get("source_kind") == "cms_lesson" and item.get("verified_cms") is True
    if not verified_cms:
        try:
            parsed = urlparse(str(item.get("url") or ""))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return None
        except ValueError:
            return None
    return resource_id


def _resources_for_topic(course_id: str, topic_id: str, extra_resources=()) -> List[str]:
    """Return all eligible exact matches in stable order, never a global first N."""
    return sorted(
        {
            resource_id
            for item in [*resource_catalog.list_approved_resources(), *extra_resources]
            if (resource_id := _resource_id_for_topic(item, course_id, topic_id)) is not None
        }
    )


@dataclass
class PlanActivity:
    objective: str
    method: str
    duration_minutes: Optional[int]
    frequency_per_week: Optional[int]
    approved_resource_ids: List[str]
    reason: str
    expected_outcome: str


@dataclass
class StudentLearningPlan:
    plan_id: str
    student_pseudonym: str
    version: int
    created_at: str
    valid_until: str
    strengths: List[str]
    weaknesses: List[str]
    diagnoses: List[Dict[str, Any]]
    priority_topics: List[str]
    activities: List[PlanActivity]
    assessment_plan: str
    success_metrics: Dict[str, Any]
    evidence_used: List[str]
    confidence: float
    next_review_at: str
    course_id: str = ""
    missing_evidence: List[str] = field(default_factory=list)
    resource_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LearningPlanGenerator:
    def generate_plan(
        self,
        profile: StudentLearningProfile,
        version: int = 1,
        validity_days: int = 21,
        *,
        approved_resources: Optional[List[Dict[str, Any]]] = None,
    ) -> StudentLearningPlan:
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        if isinstance(validity_days, bool) or not isinstance(validity_days, int) or validity_days < 1:
            raise ValueError("validity_days must be a positive integer")
        diagnoses = diagnosis_engine.diagnose_student(profile)
        actionable = [
            diagnosis
            for diagnosis in diagnoses
            if any(
                hyp.category not in {CATEGORY_INSUFFICIENT_DATA, CATEGORY_MASTERY_ON_TRACK}
                for hyp in diagnosis.hypotheses
            )
        ]
        quiz = observed_number(profile.academic.quiz_average, maximum=10)
        assignment = observed_number(profile.academic.assignment_average, maximum=10)
        exam = observed_number(profile.academic.exam_score, maximum=10)
        accuracy = observed_number(profile.question_level.accuracy_rate, maximum=1)
        practice = observed_number(profile.behavioral.practice_frequency_per_week)
        session = observed_number(profile.behavioral.average_session_duration_minutes)
        velocity = observed_number(profile.trajectory.learning_velocity)
        active = observed_number(profile.behavioral.active_days_last_month, maximum=31, integer=True)
        topic_scores = observed_mapping(profile.academic.topic_scores, maximum=10)
        subskills = observed_mapping(profile.question_level.subskill_mastery, maximum=1)
        prereqs = observed_mapping(profile.academic.prerequisite_mastery, maximum=1)

        evidence = []
        for label, value, suffix in (
            ("Điểm quiz", quiz, "/10"),
            ("Điểm bài tập", assignment, "/10"),
            ("Điểm thi", exam, "/10"),
            ("Tỷ lệ trả lời đúng", accuracy, ""),
            ("Tần suất luyện tập", practice, " lần/tuần"),
            ("Thời lượng phiên học quan sát", session, " phút"),
            ("Tốc độ học được ghi nhận", velocity, ""),
            ("Ngày hoạt động trong tháng", active, ""),
        ):
            if value is not None:
                evidence.append(f"{label}: {value:g}{suffix}")
        evidence += [f"Điểm chủ đề {topic}: {value:g}/10" for topic, value in sorted(topic_scores.items())]
        evidence += [f"Thành thạo kỹ năng {topic}: {value:.1%}" for topic, value in sorted(subskills.items())]
        evidence += [f"Kiến thức nền tảng {topic}: {value:.1%}" for topic, value in sorted(prereqs.items())]

        strengths = []
        if quiz is not None and quiz >= 7.5:
            strengths.append(f"Điểm quiz được ghi nhận: {quiz:.1f}/10")
        if active is not None and active >= 15:
            strengths.append(f"Có {active} ngày hoạt động được ghi nhận trong tháng")
        strengths += [
            f"Chủ đề {topic} có điểm {value:g}/10" for topic, value in sorted(topic_scores.items()) if value >= 7.5
        ]
        weaknesses = [diagnosis.issue for diagnosis in actionable]
        missing = list(dict.fromkeys(item for diagnosis in diagnoses for item in diagnosis.missing_evidence))

        targets: Dict[str, str] = {}
        for topic, value in sorted(topic_scores.items()):
            if value < 6:
                targets[topic] = f"Điểm chủ đề {topic}: {value:g}/10"
        for topic, value in sorted(subskills.items()):
            if value < 0.6:
                targets.setdefault(topic, f"Thành thạo kỹ năng {topic}: {value:.1%}")
        for topic, value in sorted(prereqs.items()):
            if value < 0.6:
                targets.setdefault(topic, f"Kiến thức nền tảng {topic}: {value:.1%}")

        duration = frequency = None
        if session is not None and session > 0 and velocity is not None and velocity > 0 and practice is not None:
            # Policy suggestion computed from observations, not a validated dosage model.
            bounded_velocity = max(0.4, min(2.0, velocity))
            gap_count = max(1, len(actionable))
            frequency = min(5, max(2, int(round((min(practice, 5.0) + gap_count) / bounded_velocity))))
            duration = max(1, min(75, int(round(min(session, 75.0) / min(bounded_velocity, 1.0)))))
        else:
            missing.append("Thời lượng phiên học, tần suất luyện tập và tốc độ học hợp lệ để đề xuất lịch học")

        if len(targets) > 1:
            # The same weekly budget cannot be assigned independently to every
            # topic. An instructor must confirm its allocation across topics.
            duration = frequency = None
            missing.append("Lịch phân bổ thời gian giữa các chủ đề cần được giảng viên xác nhận.")

        activities: List[PlanActivity] = []
        for topic, reason in targets.items():
            resource_ids = _resources_for_topic(profile.course_id, topic, approved_resources or ())
            if not resource_ids:
                missing.append(f"Học liệu đã duyệt đúng học phần {profile.course_id} và chủ đề {topic}")
            activities.append(
                PlanActivity(
                    objective=f"Đánh giá lại và củng cố chủ đề {topic}",
                    method=(
                        "Ôn tập học liệu đã duyệt; trao đổi với giảng viên về bài đánh giá lại."
                        if resource_ids
                        else "Đề nghị giảng viên chọn học liệu và bài đánh giá phù hợp với chủ đề."
                    ),
                    duration_minutes=duration if resource_ids else None,
                    frequency_per_week=frequency if resource_ids else None,
                    approved_resource_ids=resource_ids,
                    reason=reason,
                    expected_outcome="Có kết quả đánh giá mới theo cùng chủ đề để xem xét bước học tiếp theo.",
                )
            )
        if not activities:
            missing.append("Kết quả đánh giá có gắn chủ đề hoặc chuẩn đầu ra của học phần")
            activities.append(
                PlanActivity(
                    objective=f"Thu thập bằng chứng theo chủ đề của học phần {profile.course_id}",
                    method="Đề nghị giảng viên chọn bài đánh giá đầu vào hoặc đánh giá bổ sung theo chủ đề.",
                    duration_minutes=None,
                    frequency_per_week=None,
                    approved_resource_ids=[],
                    reason=(
                        "Các quan sát hiện có chưa xác định được chủ đề cần hỗ trợ."
                        if evidence
                        else "Chưa có quan sát học tập hợp lệ để tạo hoạt động cá nhân hóa."
                    ),
                    expected_outcome="Ghi nhận kết quả theo chủ đề trước khi đề xuất học liệu và lịch học.",
                )
            )

        metrics: Dict[str, Any] = {}
        scheduled = [
            activity
            for activity in activities
            if activity.duration_minutes is not None and activity.frequency_per_week is not None
        ]
        if scheduled and len(scheduled) == len(activities):
            metrics["weekly_study_hours_target"] = round(
                sum(activity.duration_minutes * activity.frequency_per_week for activity in scheduled) / 60, 1
            )
            metrics["target_practice_sessions_per_week"] = sum(activity.frequency_per_week for activity in scheduled)
            metrics["schedule_policy"] = "observed_baseline_v1_unvalidated"
        used_resource_ids = {resource_id for activity in activities for resource_id in activity.approved_resource_ids}
        resource_details = {}
        for item in approved_resources or ():
            if not isinstance(item, dict):
                continue
            resource_id = item.get("resource_id")
            if (
                isinstance(resource_id, str)
                and resource_id in used_resource_ids
                and any(_resource_id_for_topic(item, profile.course_id, topic) == resource_id for topic in targets)
            ):
                resource_details[resource_id] = {
                    key: item[key]
                    for key in ("title", "lesson_id", "document_id")
                    if key in item and isinstance(item[key], str)
                }
        now = datetime.now(UTC)
        return StudentLearningPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
            student_pseudonym=profile.student_pseudonym,
            version=version,
            created_at=now.isoformat(),
            valid_until=(now + timedelta(days=validity_days)).isoformat(),
            strengths=strengths,
            weaknesses=weaknesses,
            diagnoses=[diagnosis.to_dict() for diagnosis in diagnoses],
            priority_topics=list(targets),
            activities=activities,
            assessment_plan="Đối chiếu kết quả đánh giá theo chủ đề; giảng viên xác nhận bước hỗ trợ tiếp theo.",
            success_metrics=metrics,
            evidence_used=evidence,
            # Hằng số legacy để tương thích; không phải độ tin cậy đo được, không hiển thị như phần trăm.
            confidence=0.85,
            next_review_at=(now + timedelta(days=min(14, validity_days))).isoformat(),
            course_id=profile.course_id,
            missing_evidence=list(dict.fromkeys(missing)),
            resource_details=resource_details,
        )

    def render_plan_to_prompt(self, plan: StudentLearningPlan) -> str:
        activities = []
        for activity in plan.activities:
            schedule = (
                f"{activity.duration_minutes} phút/lần, {activity.frequency_per_week} lần/tuần (đề xuất theo quy tắc)"
                if activity.duration_minutes is not None and activity.frequency_per_week is not None
                else "Chưa đủ dữ liệu để đề xuất thời lượng và tần suất."
            )
            activities.append(
                f"- {activity.objective}\n  Phương pháp: {activity.method}\n"
                f"  Lịch: {schedule}\n  Học liệu: {', '.join(activity.approved_resource_ids) or 'Chưa có học liệu phù hợp đã được duyệt'}\n"
                f"  Căn cứ: {activity.reason}\n  Kết quả cần ghi nhận: {activity.expected_outcome}"
            )
        return (
            "Diễn đạt kế hoạch sau bằng tiếng Việt rõ ràng. Chỉ dùng dữ liệu được cung cấp. "
            "Không biến thiếu dữ liệu thành điểm yếu, không bịa nguyên nhân, thời lượng, KPI, URL hoặc kết quả tiến bộ. "
            "Lịch học là đề xuất theo quy tắc, không phải quan sát hay cam kết hiệu quả.\n"
            f"Học phần: {plan.course_id}\nBằng chứng: {'; '.join(plan.evidence_used) or 'Chưa có'}\n"
            f"Dữ liệu cần bổ sung: {'; '.join(plan.missing_evidence) or 'Không ghi nhận'}\n" + "\n".join(activities)
        )


learning_plan_generator = LearningPlanGenerator()
