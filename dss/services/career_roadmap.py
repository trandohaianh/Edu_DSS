"""Career Roadmap — Mục XVIII, XIX, XX: Sinh lộ trình cá nhân hoá 1 tháng / 3 tháng / 6 tháng
từ ĐÚNG các khoảng cách (gap) thực tế của từng sinh viên.

Bao gồm:
1. Lộ trình cá nhân hoá:
   - 30 ngày (1 tháng): Kỹ năng Critical & High, bài thực hành nền tảng
   - 90 ngày (3 tháng): Kỹ năng Medium & Xây dựng dự án/capstone hoàn chỉnh
   - 180 ngày (6 tháng): Hoàn thiện Portfolio, chuẩn bị CV, luyện phỏng vấn và ứng tuyển Fresher
2. Con đường thay thế (Career Alternative Paths):
   - Primary Path (Nghề chính)
   - Secondary Path (Nghề nộp đồng thời kèm lý do kỹ năng tương đồng)
   - Long-term Path (Nghề phát triển dài hạn)
3. Chuyển đổi nghề nghiệp (Career Transition Plan):
   - Phân tích chuyển từ Nghề A sang Nghề B: Kỹ năng dùng chung, Kỹ năng còn thiếu, Độ khả thi & Lộ trình chuyển đổi
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from dss.services.career_gap_analysis import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_NICE,
    STATUS_HAVE,
    GapItem,
    compute_gap_analysis,
)
from dss.services.career_knowledge_base import CareerRole, get_role
from dss.services.career_profile import StudentCareerProfile

_BUCKET_1M = "30 ngày (1 tháng)"
_BUCKET_3M = "90 ngày (3 tháng)"
_BUCKET_6M = "180 ngày (6 tháng)"

_PRIORITY_TO_BUCKET = {
    PRIORITY_CRITICAL: _BUCKET_1M,
    PRIORITY_HIGH: _BUCKET_1M,
    PRIORITY_MEDIUM: _BUCKET_3M,
    PRIORITY_NICE: _BUCKET_6M,
}

_EFFORT_BY_PRIORITY = {
    PRIORITY_CRITICAL: "6-8 giờ / tuần",
    PRIORITY_HIGH: "4-6 giờ / tuần",
    PRIORITY_MEDIUM: "3-4 giờ / tuần",
    PRIORITY_NICE: "2-3 giờ / tuần",
}


@dataclass
class RoadmapTask:
    task_id: str
    action: str
    reason: str
    resource: str
    resource_url: Optional[str]
    estimated_effort: str
    target_result: str
    priority: str
    is_completed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CareerRoadmap:
    target_role_id: str
    target_role_name: str
    current_readiness: float
    buckets: Dict[str, List[RoadmapTask]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_role_id": self.target_role_id,
            "target_role_name": self.target_role_name,
            "current_readiness": self.current_readiness,
            "buckets": {k: [t.to_dict() for t in v] for k, v in self.buckets.items()},
        }


def _find_resource_for_skill(role: CareerRole, skill_name: str):
    for res in role.learning_resources:
        if res.for_skill == skill_name:
            return res
    return role.learning_resources[0] if role.learning_resources else None


def _task_from_gap(gap: GapItem, role: CareerRole, completed_tasks: List[str]) -> RoadmapTask:
    resource = _find_resource_for_skill(role, gap.skill_name)
    target_next_level = {"None": "Basic", "Basic": "Intermediate", "Intermediate": "Advanced"}.get(
        gap.current_level, "Intermediate"
    )
    task_id = f"task_{role.role_id}_{gap.skill_name.lower().replace(' ', '_')}"
    is_completed = task_id in completed_tasks

    if gap.item_type == "artifact":
        return RoadmapTask(
            task_id=task_id,
            action=f"Xây dựng và hoàn thiện {gap.skill_name}",
            reason=f"Nhà tuyển dụng {role.role_name} cần bằng chứng thực tế để đánh giá năng lực ứng tuyển.",
            resource=resource.title if resource else "GitHub / Kaggle Portfolio Showcase",
            resource_url=resource.url if resource else "https://github.com",
            estimated_effort="4-6 giờ / tuần",
            target_result="Có ít nhất 1 sản phẩm hoàn chỉnh gắn link công khai trên CV.",
            priority=gap.priority,
            is_completed=is_completed,
        )

    kind = "bắt buộc" if gap.is_required else "nên có"
    return RoadmapTask(
        task_id=task_id,
        action=f"Học và thực hành chuyên sâu kỹ năng {gap.skill_name} để nâng lên mức {target_next_level}",
        reason=f"{gap.skill_name} là kỹ năng {kind} cốt lõi của {role.role_name} (trọng số {gap.weight:.1f}), hiện tại bạn đang ở mức '{gap.current_level}'.",
        resource=resource.title if resource else f"Tài liệu và khoá học chuẩn hoá về {gap.skill_name}",
        resource_url=resource.url if resource else None,
        estimated_effort=_EFFORT_BY_PRIORITY.get(gap.priority, "3-4 giờ / tuần"),
        target_result=f"Nắm vững lý thuyết và hoàn thành ít nhất 1 bài tập thực hành/code mẫu minh hoạ kỹ năng {gap.skill_name}.",
        priority=gap.priority,
        is_completed=is_completed,
    )


def generate_roadmap(
    profile: StudentCareerProfile,
    role: CareerRole,
    readiness_score: float,
) -> CareerRoadmap:
    """Sinh lộ trình cá nhân hoá theo Gap thực tế của sinh viên qua 3 mốc: 1 tháng, 3 tháng, 6 tháng."""
    gaps = [g for g in compute_gap_analysis(profile, role, include_artifacts=True) if g.status != STATUS_HAVE]
    buckets: Dict[str, List[RoadmapTask]] = {
        _BUCKET_1M: [],
        _BUCKET_3M: [],
        _BUCKET_6M: [],
    }

    completed_set = set(profile.completed_tasks)

    for gap in gaps:
        bucket = _PRIORITY_TO_BUCKET.get(gap.priority, _BUCKET_3M)
        buckets[bucket].append(_task_from_gap(gap, role, profile.completed_tasks))

    # Nếu không còn thiếu kỹ năng nào (hoặc đã làm hết) -> Bổ sung task tối ưu & nộp hồ sơ
    if not any(buckets.values()):
        buckets[_BUCKET_1M].append(
            RoadmapTask(
                task_id=f"task_{role.role_id}_advanced_capstone",
                action=f"Xây dựng dự án Capstone đột phá thể hiện toàn bộ kỹ năng {role.role_name}",
                reason="Bạn đã đáp ứng đầy đủ kỹ năng nền tảng và chuyên sâu — bước tiếp theo là tạo sản phẩm nổi bật so với các ứng viên khác.",
                resource=role.learning_resources[0].title if role.learning_resources else "Dự án thực tế doanh nghiệp",
                resource_url=role.learning_resources[0].url if role.learning_resources else None,
                estimated_effort="6-8 giờ / tuần",
                target_result="Dự án hoàn chỉnh có tài liệu kỹ thuật, demo trực quan và mã nguồn clean code.",
                priority=PRIORITY_HIGH,
                is_completed="task_advanced_capstone" in completed_set,
            )
        )

    # Luôn đảm bảo mốc 6 tháng có nhiệm vụ chuẩn bị phỏng vấn & apply nếu chưa có
    if not buckets[_BUCKET_6M]:
        buckets[_BUCKET_6M].append(
            RoadmapTask(
                task_id=f"task_{role.role_id}_apply_jobs",
                action=f"Chuẩn bị CV chuyên nghiệp và nộp hồ sơ ứng tuyển vị trí Fresher/Junior {role.role_name}",
                reason="Tích luỹ kinh nghiệm phỏng vấn thực tế và nắm bắt cơ hội việc làm tại các công ty mục tiêu.",
                resource="LinkedIn / TopCV / VietnamWorks / ITviec",
                resource_url="https://itviec.com",
                estimated_effort="3-5 giờ / tuần",
                target_result="Gửi ít nhất 5-10 hồ sơ ứng tuyển và tham gia các buổi phỏng vấn tuyển dụng.",
                priority=PRIORITY_MEDIUM,
                is_completed=f"task_{role.role_id}_apply_jobs" in completed_set,
            )
        )

    return CareerRoadmap(
        target_role_id=role.role_id,
        target_role_name=role.role_name,
        current_readiness=readiness_score,
        buckets=buckets,
    )


# ============================================================================
# CON ĐƯỜNG THAY THẾ (ALTERNATIVE PATHS)
# ============================================================================
@dataclass
class AlternativePathsResult:
    primary_role_id: str
    primary_role_name: str
    secondary_roles: List[Dict[str, str]]  # role_id, role_name, explanation
    long_term_roles: List[Dict[str, str]]  # role_id, role_name, explanation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def suggest_alternative_paths(primary_role_id: str) -> Dict[str, Any]:
    """Mục XIX: Đề xuất Con đường Thay thế: Primary Path, Secondary Path và Long-term Path
    kèm lời giải thích nguyên nhân rõ ràng từ Knowledge Base."""
    role = get_role(primary_role_id)
    if not role:
        return {
            "primary": [primary_role_id],
            "secondary": [],
            "long_term": [],
            "secondary_explanation": "",
            "long_term_explanation": "",
        }

    secondary_list = []
    long_term_list = []

    if role.adjacent_roles:
        # Lấy vai trò đầu tiên làm secondary, vai trò thứ hai làm long-term
        secondary_list.append(role.adjacent_roles[0])
        if len(role.adjacent_roles) > 1:
            long_term_list.append(role.adjacent_roles[1])

    return {
        "primary": [role.role_id],
        "secondary": secondary_list,
        "long_term": long_term_list,
        "primary_name": role.role_name,
        "secondary_explanation": role.secondary_path_explanation,
        "long_term_explanation": role.long_term_path_explanation,
    }


# ============================================================================
# CHUYỂN ĐỔI NGHỀ NGHIỆP (CAREER TRANSITION)
# ============================================================================
@dataclass
class CareerTransitionPlan:
    from_role_id: str
    from_role_name: str
    to_role_id: str
    to_role_name: str
    shared_skills: List[str]
    missing_skills: List[str]
    feasibility_score: float  # Độ khả thi chuyển dịch 0-100%
    gap_size: str  # Nhỏ | Trung bình | Lớn
    roadmap: CareerRoadmap

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_role_id": self.from_role_id,
            "from_role_name": self.from_role_name,
            "to_role_id": self.to_role_id,
            "to_role_name": self.to_role_name,
            "shared_skills": self.shared_skills,
            "missing_skills": self.missing_skills,
            "feasibility_score": self.feasibility_score,
            "gap_size": self.gap_size,
            "roadmap": self.roadmap.to_dict(),
        }


def compute_transition(
    profile: StudentCareerProfile,
    from_role_id: str,
    to_role_id: str,
    readiness_score: float,
) -> Optional[CareerTransitionPlan]:
    """Mục XX: Pipeline Chuyển nghề:
    Current Profile + Target Career -> Shared Skills -> Missing Skills -> Transition Gap -> Transition Roadmap."""
    from_role = get_role(from_role_id)
    to_role = get_role(to_role_id)
    if not from_role or not to_role:
        return None

    from_all_skills = set(from_role.required_skills) | set(from_role.preferred_skills)
    to_required_skills = set(to_role.required_skills)
    to_all_skills = to_required_skills | set(to_role.preferred_skills)

    # Kỹ năng dùng chung
    shared = sorted(from_all_skills & to_all_skills)

    # Kỹ năng còn thiếu đối với vai trò đích
    gaps = [g for g in compute_gap_analysis(profile, to_role, include_artifacts=False) if g.status != STATUS_HAVE]
    missing = sorted({g.skill_name for g in gaps})

    # Độ khả thi chuyển dịch: Dựa trên tỷ lệ kỹ năng chung chia cho tổng kỹ năng nghề đích
    feasibility = round((len(shared) / max(1, len(to_all_skills))) * 100, 1)

    # Đánh giá độ lớn của khoảng cách
    critical_missing = sum(1 for g in gaps if g.priority in (PRIORITY_CRITICAL, PRIORITY_HIGH))
    if critical_missing == 0:
        gap_size = "Nhỏ"
    elif critical_missing <= 2:
        gap_size = "Trung bình"
    else:
        gap_size = "Lớn"

    roadmap = generate_roadmap(profile, to_role, readiness_score)

    return CareerTransitionPlan(
        from_role_id=from_role_id,
        from_role_name=from_role.role_name,
        to_role_id=to_role_id,
        to_role_name=to_role.role_name,
        shared_skills=shared,
        missing_skills=missing,
        feasibility_score=feasibility,
        gap_size=gap_size,
        roadmap=roadmap,
    )
