"""What-if Analysis — Mục XXI: Công cụ hỗ trợ ra quyết định nghề nghiệp bằng cách giả lập
các kịch bản thay đổi hồ sơ (nâng cấp kỹ năng, thay đổi điều kiện ràng buộc, đổi mục tiêu thời gian)
và TÍNH LẠI Career Fit/Readiness tức thời — không làm thay đổi hồ sơ gốc của sinh viên.

Hỗ trợ trả lời các câu hỏi giả định cốt lõi:
1. "Nếu tôi học thêm Power BI thì sao?"
2. "Nếu SQL của tôi lên mức Khá/Giỏi thì mức độ sẵn sàng ứng tuyển DA tăng bao nhiêu %?"
3. "Nếu tôi không muốn làm ca thì nghề nào nên loại trừ?"
4. "Nếu tôi muốn xin việc trong 3 tháng thì nên ưu tiên nghề nào?"
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from dss.services.career_knowledge_base import CareerRole
from dss.services.career_profile import StudentCareerProfile
from dss.services.career_scoring import (
    compute_career_fit,
    compute_career_readiness,
)


@dataclass
class WhatIfResult:
    before_fit: float
    after_fit: float
    before_readiness: float
    after_readiness: float
    delta_fit: float
    delta_readiness: float
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def apply_skill_change(
    profile: StudentCareerProfile,
    skill_name: str,
    category: str,
    new_level: str,
) -> StudentCareerProfile:
    """Giả lập: 'Nếu tôi nâng kỹ năng X lên mức Y thì sao?'"""
    hypothetical = profile.clone()
    hypothetical.skills.upsert_self_assessment(skill_name, category, new_level)
    return hypothetical


def apply_constraint_change(
    profile: StudentCareerProfile,
    **constraint_updates,
) -> StudentCareerProfile:
    """Giả lập: 'Nếu tôi chấp nhận làm ca', 'Nếu tôi chỉ muốn remote', 'Nếu tiếng Anh đạt Advanced'."""
    hypothetical = profile.clone()
    for field_name, value in constraint_updates.items():
        if hasattr(hypothetical.constraints, field_name):
            setattr(hypothetical.constraints, field_name, value)
    return hypothetical


def compare_scenarios(
    original_profile: StudentCareerProfile,
    hypothetical_profile: StudentCareerProfile,
    role: CareerRole,
    change_description: str,
) -> WhatIfResult:
    """So sánh trước và sau kịch bản giả lập đối với 1 vai trò nghề nghiệp cụ thể."""
    before_fit_result = compute_career_fit(original_profile, role)
    after_fit_result = compute_career_fit(hypothetical_profile, role)
    before_readiness_result = compute_career_readiness(original_profile, role)
    after_readiness_result = compute_career_readiness(hypothetical_profile, role)

    delta_fit = round(after_fit_result.fit_score - before_fit_result.fit_score, 1)
    delta_readiness = round(after_readiness_result.readiness_score - before_readiness_result.readiness_score, 1)

    if delta_fit == 0.0 and delta_readiness == 0.0:
        explanation = f"{change_description} không làm thay đổi đáng kể mức độ phù hợp hay mức độ sẵn sàng đối với vai trò {role.role_name}."
    else:
        direction_fit = "tăng" if delta_fit >= 0 else "giảm"
        direction_ready = "tăng" if delta_readiness >= 0 else "giảm"
        parts = []
        if delta_fit != 0.0:
            parts.append(
                f"Career Fit {direction_fit} {abs(delta_fit):.1f}% (từ {before_fit_result.fit_score:.1f}% → {after_fit_result.fit_score:.1f}%)"
            )
        if delta_readiness != 0.0:
            parts.append(
                f"Career Readiness {direction_ready} {abs(delta_readiness):.1f}% (từ {before_readiness_result.readiness_score:.1f}% → {after_readiness_result.readiness_score:.1f}%)"
            )

        explanation = f"{change_description}: " + " và ".join(parts) + f" cho vị trí {role.role_name}."

    return WhatIfResult(
        before_fit=before_fit_result.fit_score,
        after_fit=after_fit_result.fit_score,
        before_readiness=before_readiness_result.readiness_score,
        after_readiness=after_readiness_result.readiness_score,
        delta_fit=delta_fit,
        delta_readiness=delta_readiness,
        explanation=explanation,
    )


def rank_roles_for_timeframe(
    profile: StudentCareerProfile,
    roles: List[CareerRole],
    timeframe_months: int,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Giả lập: 'Nếu tôi muốn xin việc trong 3 tháng thì nên ưu tiên nghề nào?'
    Nếu thời gian ngắn (<= 3 tháng): Ưu tiên nghề có Career Readiness cao (sẵn sàng làm ngay).
    Nếu thời gian dài (>= 6 tháng): Ưu tiên nghề có Career Fit cao (tiềm năng phát triển tốt)."""
    scored = []
    for r in roles:
        fit = compute_career_fit(profile, r)
        ready = compute_career_readiness(profile, r)
        if timeframe_months <= 3:
            # Ưu tiên Readiness (70%) hơn Fit (30%)
            hybrid_score = round(ready.readiness_score * 0.7 + fit.fit_score * 0.3, 1)
            primary_metric = "Readiness"
        else:
            # Ưu tiên Fit (70%) hơn Readiness (30%)
            hybrid_score = round(fit.fit_score * 0.7 + ready.readiness_score * 0.3, 1)
            primary_metric = "Fit"

        scored.append(
            {
                "role_id": r.role_id,
                "role_name": r.role_name,
                "fit_score": fit.fit_score,
                "readiness_score": ready.readiness_score,
                "hybrid_score": hybrid_score,
                "primary_metric": primary_metric,
            }
        )

    scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return scored[:top_k]
