"""Career LMS-CMS Pipeline — Đường ống khép kín Closed-Loop Feedback.

Pipeline bắt buộc:
LMS + CMS
→ Student Learning Profile
→ Competency Profile
→ Career Profile
→ Career Fit
→ Career Readiness
→ Skill Gap (kèm LMS Evidence)
→ CMS Resource Matching (kèm CMS Resource Match)
→ Personalized Learning Roadmap
→ Student Learning Action
→ LMS captures new activity/result
→ Profile Update
→ Recompute Readiness
→ Career Recommendation Update

Nguyên tắc:
- Closed-loop feedback: Hành động học tập trên LMS lập tức cập nhật Skill Profile,
  tự động tính toán lại Career Readiness và làm mới khuyến nghị nghề nghiệp.
- Traceability: Mỗi khoảng cách kỹ năng (Gap) trace được LMS Evidence dẫn đến gap,
  và CMS Resource được chọn để khắc phục gap.
- LLM chỉ giải thích và trình bày; toàn bộ logic tính gap, LMS evidence và CMS matching
  đều vận hành trên structured data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dss.services.career_gap_analysis import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    STATUS_HAVE,
    STATUS_MISSING,
    STATUS_STRENGTHEN,
    GapItem,
    compute_gap_analysis,
    group_gap_by_status,
)
from dss.services.career_knowledge_base import CareerRole, get_role
from dss.services.career_profile import (
    ALL_SKILL_CATALOG,
    StudentCareerProfile,
)
from dss.services.career_roadmap import (
    _BUCKET_1M,
    _BUCKET_3M,
    _BUCKET_6M,
    _EFFORT_BY_PRIORITY,
    _PRIORITY_TO_BUCKET,
    CareerRoadmap,
    RoadmapTask,
)
from dss.services.career_scoring import (
    CareerFitResult,
    CareerReadinessResult,
    compute_career_readiness,
)
from dss.services.cms_repository import (
    BaseCMSRepository,
    CMSResourceMatch,
    get_cms_repository,
)
from dss.services.lms_connector import (
    BaseLMSRepository,
    LMSAssessmentRecord,
    LMSStudentLearningSummary,
    get_lms_repository,
)


@dataclass
class TracedGapItem(GapItem):
    """Khoảng cách kỹ năng có đầy đủ siêu dữ liệu truy vết 2 chiều: LMS Evidence & CMS Remedy."""
    lms_evidence: str = ""
    cms_match: Optional[CMSResourceMatch] = None
    cms_recommendation_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["lms_evidence"] = self.lms_evidence
        d["cms_match"] = self.cms_match.to_dict() if self.cms_match else None
        d["cms_recommendation_action"] = self.cms_recommendation_action
        return d


@dataclass
class ClosedLoopActionResult:
    """Kết quả phản hồi của vòng lặp khép kín khi sinh viên hoàn thành hành động học tập."""
    student_id: str
    target_role_id: str
    target_role_name: str
    skill_upgraded: str
    previous_level: str
    new_level: str
    previous_readiness: float
    new_readiness: float
    delta_readiness: float
    lms_record: LMSAssessmentRecord
    completed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "target_role_id": self.target_role_id,
            "target_role_name": self.target_role_name,
            "skill_upgraded": self.skill_upgraded,
            "previous_level": self.previous_level,
            "new_level": self.new_level,
            "previous_readiness": round(self.previous_readiness, 1),
            "new_readiness": round(self.new_readiness, 1),
            "delta_readiness": round(self.delta_readiness, 1),
            "lms_record": self.lms_record.to_dict(),
            "completed_at": self.completed_at,
            "message": self.message,
        }


def enrich_career_profile_with_lms_cms(
    profile: StudentCareerProfile,
    lms_repo: Optional[BaseLMSRepository] = None,
    cms_repo: Optional[BaseCMSRepository] = None,
    raw_row: Optional[Dict[str, Any]] = None,
) -> LMSStudentLearningSummary:
    """Lấy dữ liệu học tập từ LMS và ánh xạ CMS để làm giàu Career Profile với minh chứng xác thực."""
    lms = lms_repo or get_lms_repository()

    # 1. Trích xuất Student Learning Profile từ LMS
    summary = lms.get_student_learning_summary(profile.student_pseudonym, raw_row)

    # 2. Bơm các minh chứng xác thực từ LMS vào Skill Profile
    for ev in summary.evidences:
        # Nhận diện kỹ năng liên quan trong câu minh chứng
        for cat, skills in ALL_SKILL_CATALOG.items():
            for sk in skills:
                if sk.lower() in ev.lower() or (sk == "SQL" and "cơ sở dữ liệu" in ev.lower()):
                    item = profile.skills.get(sk)
                    if ev not in item.evidence:
                        item.evidence.append(ev)
                    item.confidence = "high"
                    item.source = "academic_score"

    # 3. Đảm bảo các môn thế mạnh từ LMS cập nhật vào academic profile
    for strong in summary.strong_subjects:
        if strong not in profile.academic.strengths:
            profile.academic.strengths.append(strong)

    for weak in summary.weak_subjects:
        if weak not in profile.academic.weaknesses:
            profile.academic.weaknesses.append(weak)

    return summary


def compute_traced_gap_analysis(
    profile: StudentCareerProfile,
    role: CareerRole,
    lms_repo: Optional[BaseLMSRepository] = None,
    cms_repo: Optional[BaseCMSRepository] = None,
    include_artifacts: bool = True,
) -> List[TracedGapItem]:
    """Tính toán khoảng cách kỹ năng có đầy đủ truy vết LMS Evidence và CMS Remedy."""
    lms = lms_repo or get_lms_repository()
    cms = cms_repo or get_cms_repository()

    base_gaps = compute_gap_analysis(profile, role, include_artifacts=include_artifacts)
    lms_summary = lms.get_student_learning_summary(profile.student_pseudonym)

    traced_gaps: List[TracedGapItem] = []

    for g in base_gaps:
        if g.item_type == "artifact":
            # Xử lý riêng cho tạo tác nghề nghiệp
            traced_gaps.append(TracedGapItem(
                skill_name=g.skill_name,
                is_required=g.is_required,
                weight=g.weight,
                current_level=g.current_level,
                status=g.status,
                priority=g.priority,
                item_type="artifact",
                lms_evidence="[LMS Evidence] Chưa ghi nhận liên kết đồ án môn học hoặc GitHub Portfolio trên hệ thống học tập.",
                cms_match=None,
                cms_recommendation_action=f"Xây dựng và hoàn thiện {g.skill_name} gắn link công khai trên CV.",
            ))
            continue

        # 1. Xác định LMS Evidence cho kỹ năng
        target_next_level = {"None": "Basic", "Basic": "Intermediate", "Intermediate": "Advanced"}.get(g.current_level, "Intermediate")

        # Tìm trong lịch sử bài kiểm tra của LMS xem có bài nào liên quan kỹ năng này không
        related_assessment = None
        for as_rec in lms_summary.assessment_history:
            if g.skill_name.lower() in as_rec.topic.lower() or as_rec.topic.lower() in g.skill_name.lower():
                related_assessment = as_rec
                break

        if related_assessment:
            if not related_assessment.passed or related_assessment.score < 6.5:
                lms_evidence = (
                    f"[LMS Evidence] Bài kiểm tra '{related_assessment.title}' đạt {related_assessment.score:.1f}/{related_assessment.max_score:.0f} "
                    f"(chưa đạt chuẩn tối thiểu 6.5) — Cần củng cố để nâng từ {g.current_level} lên {target_next_level}."
                )
            else:
                lms_evidence = (
                    f"[LMS Evidence] Đã hoàn thành '{related_assessment.title}' ({related_assessment.score:.1f}/{related_assessment.max_score:.0f}), "
                    f"đạt chuẩn mức {g.current_level}."
                )
        elif g.status == STATUS_HAVE:
            lms_evidence = f"[LMS Evidence] Hồ sơ học tập xác nhận đã tích lũy đủ điểm và minh chứng mức {g.current_level}."
        elif g.status == STATUS_STRENGTHEN:
            lms_evidence = (
                f"[LMS Evidence] Môn học liên quan trong LMS mới ở mức cơ bản ({g.current_level}); "
                f"chưa hoàn thành bài kiểm tra chuyên sâu hoặc đồ án ứng dụng nâng cao."
            )
        else:
            lms_evidence = (
                f"[LMS Evidence] Chưa có lịch sử ghi danh, nộp bài kiểm tra hoặc hoạt động học tập nào "
                f"cho kỹ năng '{g.skill_name}' trên hệ thống LMS."
            )

        # 2. Khớp nối tài nguyên từ CMS (CMS Resource Matching)
        remedy_matches = cms.find_resources_for_skill_gap(
            skill_name=g.skill_name,
            current_level=g.current_level,
            target_level=target_next_level,
            specific_gap_topic="Window Functions" if g.skill_name == "SQL" and g.status != STATUS_HAVE else None,
        )
        best_match = remedy_matches[0] if remedy_matches else None

        if best_match:
            rec_action = best_match.practice_action
        else:
            rec_action = f"Tham gia học phần bổ trợ và hoàn thành bài kiểm tra thực hành về {g.skill_name}."

        traced_gaps.append(TracedGapItem(
            skill_name=g.skill_name,
            is_required=g.is_required,
            weight=g.weight,
            current_level=g.current_level,
            status=g.status,
            priority=g.priority,
            item_type="skill",
            lms_evidence=lms_evidence,
            cms_match=best_match,
            cms_recommendation_action=rec_action,
        ))

    return traced_gaps


def generate_traced_roadmap(
    profile: StudentCareerProfile,
    role: CareerRole,
    readiness_score: float,
    lms_repo: Optional[BaseLMSRepository] = None,
    cms_repo: Optional[BaseCMSRepository] = None,
) -> CareerRoadmap:
    """Sinh lộ trình cá nhân hóa 1/3/6 tháng với truy vết LMS Evidence và CMS Resource Matching."""
    lms = lms_repo or get_lms_repository()
    cms = cms_repo or get_cms_repository()

    traced_gaps = [
        g for g in compute_traced_gap_analysis(profile, role, lms, cms, include_artifacts=True)
        if g.status != STATUS_HAVE
    ]

    buckets: Dict[str, List[RoadmapTask]] = {
        _BUCKET_1M: [],
        _BUCKET_3M: [],
        _BUCKET_6M: [],
    }

    completed_set = set(profile.completed_tasks)

    for gap in traced_gaps:
        bucket = _PRIORITY_TO_BUCKET.get(gap.priority, _BUCKET_3M)
        task_id = f"task_{role.role_id}_{gap.skill_name.lower().replace(' ', '_')}"
        is_completed = task_id in completed_set

        if gap.item_type == "artifact":
            task = RoadmapTask(
                task_id=task_id,
                action=gap.cms_recommendation_action,
                reason=f"{gap.lms_evidence} Nhà tuyển dụng {role.role_name} yêu cầu sản phẩm thực tế.",
                resource="EduDSS CMS & GitHub Portfolio Showcase",
                resource_url="https://github.com",
                estimated_effort="4-6 giờ / tuần",
                target_result="Có ít nhất 1 sản phẩm hoàn chỉnh gắn link công khai trên CV.",
                priority=gap.priority,
                is_completed=is_completed,
            )
        else:
            match = gap.cms_match
            res_title = match.resource_title if match else f"Học liệu chuẩn hóa {gap.skill_name}"
            res_url = match.resource_url if match else None
            effort = f"{match.estimated_hours:.0f} giờ học tập & thực hành" if match else _EFFORT_BY_PRIORITY.get(gap.priority, "4 giờ / tuần")
            target_res = match.target_outcome if match else f"Nâng bậc kỹ năng {gap.skill_name} trên hệ thống LMS."

            task = RoadmapTask(
                task_id=task_id,
                action=gap.cms_recommendation_action,
                reason=f"{gap.lms_evidence} ({'Bắt buộc' if gap.is_required else 'Nên có'}, trọng số {gap.weight:.1f}).",
                resource=res_title,
                resource_url=res_url,
                estimated_effort=effort,
                target_result=target_res,
                priority=gap.priority,
                is_completed=is_completed,
            )

        buckets[bucket].append(task)

    return CareerRoadmap(
        target_role_id=role.role_id,
        target_role_name=role.role_name,
        current_readiness=readiness_score,
        buckets=buckets,
    )


def execute_closed_loop_action(
    student_id: str,
    profile: StudentCareerProfile,
    role_id: str,
    skill_to_upgrade: str,
    new_level: str = "Intermediate",
    assessment_score: float = 8.5,
    max_score: float = 10.0,
    duration_minutes: int = 45,
    course_id: str = "CS201",
    activity_title: str = "",
    lms_repo: Optional[BaseLMSRepository] = None,
    cms_repo: Optional[BaseCMSRepository] = None,
) -> ClosedLoopActionResult:
    """Thực thi vòng lặp phản hồi khép kín (Closed-Loop Feedback):

    1. Ghi nhận bài nộp / hành động học tập mới vào LMS
    2. Nâng cấp Skill Profile với bằng chứng LMS xác thực
    3. Tự động tính toán lại Career Readiness
    4. Cập nhật khuyến nghị nghề nghiệp tức thì.
    """
    lms = lms_repo or get_lms_repository()
    role = get_role(role_id)

    # 1. Lưu readiness trước khi thực hiện
    initial_readiness = compute_career_readiness(profile, role).readiness_score

    # 2. Ghi nhận hành động mới vào LMS
    title = activity_title or f"Bài thực hành & Đánh giá năng lực {skill_to_upgrade}"
    lms_record = lms.record_learning_action(
        student_id=student_id,
        course_id=course_id,
        topic=skill_to_upgrade,
        assessment_score=assessment_score,
        max_score=max_score,
        duration_minutes=duration_minutes,
        activity_title=title,
        assessment_type="assignment" if "thực hành" in title.lower() else "quiz",
    )

    # 3. Cập nhật hồ sơ kỹ năng của sinh viên
    old_item = profile.skills.get(skill_to_upgrade)
    previous_level = old_item.skill_level

    # Nâng cấp kỹ năng
    cat = "technical"
    for c, sk_list in ALL_SKILL_CATALOG.items():
        if skill_to_upgrade in sk_list:
            cat = c
            break

    evidence_str = (
        f"[LMS Action] Đã hoàn thành '{title}' đạt {assessment_score:.1f}/{max_score:.0f} "
        f"(Học phần {course_id}, thời lượng {duration_minutes} phút) - Ngày {datetime.now().strftime('%d/%m/%Y')}"
    )
    profile.skills.add_evidence_from_experience(
        skill_name=skill_to_upgrade,
        category=cat,
        evidence_line=evidence_str,
        min_level=new_level,
    )

    # Đánh dấu task completed trong lộ trình
    task_id = f"task_{role.role_id}_{skill_to_upgrade.lower().replace(' ', '_')}"
    if task_id not in profile.completed_tasks:
        profile.completed_tasks.append(task_id)

    profile.updated_at = datetime.now().isoformat()

    # 4. Tự động tính toán lại Career Readiness (Recompute automatically)
    new_readiness_res = compute_career_readiness(profile, role)
    new_readiness = new_readiness_res.readiness_score
    delta = new_readiness - initial_readiness

    msg = (
        f"🎉 Vòng lặp phản hồi LMS thành công: Đã ghi nhận điểm {assessment_score:.1f}/{max_score:.0f} cho '{title}'. "
        f"Kỹ năng '{skill_to_upgrade}' nâng từ {previous_level} lên {new_level}. "
        f"Career Readiness cho {role.role_name} tự động tăng từ {initial_readiness:.1f}% lên {new_readiness:.1f}% (+{delta:.1f}%)."
    )

    return ClosedLoopActionResult(
        student_id=student_id,
        target_role_id=role_id,
        target_role_name=role.role_name,
        skill_upgraded=skill_to_upgrade,
        previous_level=previous_level,
        new_level=new_level,
        previous_readiness=initial_readiness,
        new_readiness=new_readiness,
        delta_readiness=delta,
        lms_record=lms_record,
        message=msg,
    )
