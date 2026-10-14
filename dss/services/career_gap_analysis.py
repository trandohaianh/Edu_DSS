"""Career Gap Analysis — Mục XVI & XVII: Xác định chính xác KHOẢNG CÁCH kỹ năng
và tạo tác nghề nghiệp giữa hồ sơ hiện tại và vai trò mục tiêu.

Phân loại rõ ràng:
- ĐÃ CÓ (✓): Kỹ năng đã đạt mức Intermediate hoặc Advanced.
- CẦN CỦNG CỐ (△): Kỹ năng ở mức Basic hoặc mới có chứng cứ gián tiếp từ môn học.
- CHƯA CÓ (✕): Kỹ năng ở mức None hoặc chưa từng được khai báo / đánh giá.

Xếp thứ tự ưu tiên (Priority Hierarchy):
- Critical: Kỹ năng bắt buộc (required) có trọng số cao (>= 0.8) mà sinh viên chưa có.
- High: Kỹ năng bắt buộc trọng số trung bình (>= 0.5) hoặc tạo tác quan trọng (Portfolio).
- Medium: Kỹ năng bắt buộc nền tảng, kỹ năng nên có quan trọng, hoặc chuẩn bị phỏng vấn.
- Nice-to-have: Kỹ năng phụ trợ hoặc kỹ năng đã đạt chuẩn.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from dss.services.career_knowledge_base import CareerRole
from dss.services.career_profile import StudentCareerProfile

STATUS_HAVE = "Đã có"
STATUS_STRENGTHEN = "Cần củng cố"
STATUS_MISSING = "Chưa có"

PRIORITY_CRITICAL = "Critical"
PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_NICE = "Nice-to-have"


@dataclass
class GapItem:
    skill_name: str
    is_required: bool
    weight: float
    current_level: str
    status: str                                       # STATUS_HAVE | STATUS_STRENGTHEN | STATUS_MISSING
    priority: str                                     # PRIORITY_CRITICAL | PRIORITY_HIGH | PRIORITY_MEDIUM | PRIORITY_NICE
    item_type: str = "skill"                          # skill | artifact

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _status_from_level(achieved_level: float) -> str:
    if achieved_level >= 0.66:
        return STATUS_HAVE
    if achieved_level >= 0.33:
        return STATUS_STRENGTHEN
    return STATUS_MISSING


def _priority_from_weight(is_required: bool, weight: float, status: str) -> str:
    if status == STATUS_HAVE:
        return PRIORITY_NICE
    if is_required and weight >= 0.8:
        return PRIORITY_CRITICAL
    if is_required and weight >= 0.5:
        return PRIORITY_HIGH
    if is_required:
        return PRIORITY_MEDIUM
    if weight >= 0.6:
        return PRIORITY_HIGH
    if weight >= 0.4:
        return PRIORITY_MEDIUM
    return PRIORITY_NICE


def compute_gap_analysis(
    profile: StudentCareerProfile,
    role: CareerRole,
    include_artifacts: bool = True,
) -> List[GapItem]:
    items: List[GapItem] = []

    # 1. Kỹ năng bắt buộc (Required Skills)
    for skill_name, weight in role.required_skills.items():
        skill = profile.skills.get(skill_name)
        status = _status_from_level(skill.achieved_level)
        items.append(GapItem(
            skill_name=skill_name,
            is_required=True,
            weight=weight,
            current_level=skill.skill_level,
            status=status,
            priority=_priority_from_weight(True, weight, status),
            item_type="skill",
        ))

    # 2. Kỹ năng nên có (Preferred Skills)
    for skill_name, weight in role.preferred_skills.items():
        skill = profile.skills.get(skill_name)
        status = _status_from_level(skill.achieved_level)
        items.append(GapItem(
            skill_name=skill_name,
            is_required=False,
            weight=weight,
            current_level=skill.skill_level,
            status=status,
            priority=_priority_from_weight(False, weight, status),
            item_type="skill",
        ))

    # 3. Tạo tác nghề nghiệp thực tế (Practical Artifacts Gap)
    if include_artifacts:
        # Portfolio gap
        if not profile.experience.has_portfolio():
            items.append(GapItem(
                skill_name="Portfolio dự án thực tế",
                is_required=True,
                weight=0.8,
                current_level="Chưa có",
                status=STATUS_MISSING,
                priority=PRIORITY_HIGH,
                item_type="artifact",
            ))
        else:
            items.append(GapItem(
                skill_name="Portfolio dự án thực tế",
                is_required=True,
                weight=0.8,
                current_level="Đã có",
                status=STATUS_HAVE,
                priority=PRIORITY_NICE,
                item_type="artifact",
            ))

        # Phỏng vấn kỹ thuật & CV
        if not profile.experience.is_interview_ready():
            items.append(GapItem(
                skill_name="Luyện tập phỏng vấn kỹ thuật & CV",
                is_required=True,
                weight=0.7,
                current_level="Chưa có",
                status=STATUS_MISSING,
                priority=PRIORITY_MEDIUM,
                item_type="artifact",
            ))

    priority_order = {
        PRIORITY_CRITICAL: 0,
        PRIORITY_HIGH: 1,
        PRIORITY_MEDIUM: 2,
        PRIORITY_NICE: 3,
    }
    items.sort(key=lambda it: (priority_order.get(it.priority, 4), -it.weight))
    return items


def group_gap_by_status(items: List[GapItem]) -> Dict[str, List[GapItem]]:
    grouped = {STATUS_HAVE: [], STATUS_STRENGTHEN: [], STATUS_MISSING: []}
    for it in items:
        if it.status in grouped:
            grouped[it.status].append(it)
    return grouped
