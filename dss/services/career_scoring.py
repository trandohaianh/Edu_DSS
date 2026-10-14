"""Career Scoring — Công thức tính điểm minh bạch (heuristic, KHÔNG phải xác
suất nghề nghiệp) cho Career Decision Support System.

Nguyên tắc bắt buộc:
1. Trọng số tập trung duy nhất ở CAREER_FIT_WEIGHTS và CAREER_READINESS_WEIGHTS,
   không hard-code rải rác.
2. TÁCH BIỆT HOÀN TOÀN:
   - CAREER FIT: Mức độ phù hợp với năng lực, sở thích và điều kiện cá nhân (0-100%).
   - CAREER READINESS: Mức độ sẵn sàng ứng tuyển ngay hiện tại (0-100%).
3. Mọi điểm số đều trả kèm evidence cụ thể có nguồn gốc, không số ảo.
4. Phát hiện xung đột năng lực cao vs vướng ràng buộc cá nhân (Câu hỏi 5).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dss.services.career_knowledge_base import CareerRole
from dss.services.career_profile import (
    ENGLISH_LEVEL_VALUE,
    StudentCareerProfile,
)

# ============================================================================
# TRỌNG SỐ CẤU HÌNH TẬP TRUNG (Configurable Heuristic Weights)
# ============================================================================
CAREER_FIT_WEIGHTS: Dict[str, float] = {
    "skill": 0.30,
    "academic": 0.20,
    "interest": 0.20,
    "experience": 0.10,
    "work_style": 0.10,
    "constraint": 0.10,
}

CAREER_READINESS_WEIGHTS: Dict[str, float] = {
    "required_skill_coverage": 0.35,
    "project_evidence": 0.20,
    "experience": 0.15,
    "portfolio": 0.10,
    "english": 0.10,
    "interview_prep": 0.10,
}

_REQUIRED_VS_PREFERRED_SKILL_BLEND = {"required": 0.8, "preferred": 0.2}

assert abs(sum(CAREER_FIT_WEIGHTS.values()) - 1.0) < 1e-6, "Tổng trọng số Career Fit phải bằng 1.0"
assert abs(sum(CAREER_READINESS_WEIGHTS.values()) - 1.0) < 1e-6, "Tổng trọng số Career Readiness phải bằng 1.0"


@dataclass
class ScoreResult:
    score: float                                      # 0.0 - 1.0
    evidence: List[str] = field(default_factory=list) # Danh sách minh chứng
    is_estimated: bool = False                        # True nếu thiếu dữ liệu và dùng giá trị trung tính

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _weighted_skill_coverage(
    skills_weights: Dict[str, float],
    profile: StudentCareerProfile,
) -> Tuple[float, List[str]]:
    if not skills_weights:
        return 1.0, []
    total_weight = sum(skills_weights.values()) or 1.0
    achieved = 0.0
    evidence: List[str] = []
    for skill_name, weight in skills_weights.items():
        item = profile.skills.get(skill_name)
        achieved += weight * item.achieved_level
        if item.achieved_level > 0:
            evidence.append(f"{skill_name}: {item.skill_level} (nguồn: {item.source})")
        else:
            evidence.append(f"{skill_name}: Chưa có dữ liệu")
    return achieved / total_weight, evidence


# ============================================================================
# 1. TÍNH CÁC THÀNH PHẦN CAREER FIT
# ============================================================================
def compute_skill_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """SkillMatch = 80% Required Skills + 20% Preferred Skills.
    Thiếu required skill phạt điểm nặng hơn nhiều so với preferred skill."""
    required_score, required_ev = _weighted_skill_coverage(role.required_skills, profile)
    preferred_score, preferred_ev = _weighted_skill_coverage(role.preferred_skills, profile)
    blend = _REQUIRED_VS_PREFERRED_SKILL_BLEND
    final = blend["required"] * required_score + blend["preferred"] * preferred_score
    evidence = [f"[Bắt buộc] {e}" for e in required_ev] + [f"[Nên có] {e}" for e in preferred_ev]
    return ScoreResult(score=round(final, 4), evidence=evidence)


def compute_academic_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """Khớp điểm theo domain học thuật thật (đã map subject -> domain). Không dùng GPA tổng."""
    if not role.academic_domains:
        return ScoreResult(score=0.5, evidence=["Vai trò không yêu cầu domain học thuật cụ thể"], is_estimated=True)
    total_weight = sum(role.academic_domains.values()) or 1.0
    achieved = 0.0
    evidence = []
    for domain, weight in role.academic_domains.items():
        domain_score = profile.academic.domain_scores.get(domain)
        if domain_score is None:
            evidence.append(f"{domain}: Chưa có dữ liệu điểm (mặc định trung tính)")
            achieved += weight * 0.5
            continue
        achieved += weight * (domain_score / 10.0)
        evidence.append(f"{domain}: {domain_score:.1f}/10")
    return ScoreResult(score=round(achieved / total_weight, 4), evidence=evidence)


def compute_interest_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """Khớp sở thích theo mini career assessment 7 trục (thang điểm 1-5)."""
    if not role.interest_axes or not profile.interest.scores:
        return ScoreResult(score=0.5, evidence=["Chưa có đủ dữ liệu khảo sát sở thích"], is_estimated=True)
    total_weight = sum(role.interest_axes.values()) or 1.0
    achieved = 0.0
    evidence = []
    for axis, weight in role.interest_axes.items():
        raw = profile.interest.get_score(axis)
        normalized = (raw - 1) / 4.0  # 1..5 -> 0.0..1.0
        achieved += weight * normalized
        evidence.append(f"Sở thích '{axis}': {raw}/5 (trọng số {weight:.1f})")
    return ScoreResult(score=round(achieved / total_weight, 4), evidence=evidence)


def compute_experience_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """Khớp số lượng dự án/kinh nghiệm thực tế có liên quan đến các kỹ năng của nghề."""
    related_skills = list(role.required_skills.keys()) + list(role.preferred_skills.keys())
    n_relevant = profile.experience.count_relevant_projects(related_skills)
    expected = max(1, role.experience_expectation)
    score = min(1.0, n_relevant / expected)
    if n_relevant == 0:
        return ScoreResult(score=0.0, evidence=["Chưa ghi nhận dự án/kinh nghiệm liên quan"], is_estimated=False)
    return ScoreResult(
        score=round(score, 4),
        evidence=[f"{n_relevant}/{expected} dự án/kinh nghiệm liên quan đã ghi nhận trong hồ sơ"],
    )


def compute_work_style_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """Khớp phong cách làm việc 7 trục so với kỳ vọng của vai trò."""
    if not role.work_style or not profile.work_style.preferences:
        return ScoreResult(score=0.5, evidence=["Chưa có đủ dữ liệu phong cách làm việc"], is_estimated=True)
    diffs = []
    evidence = []
    for axis, expected in role.work_style.items():
        actual = profile.work_style.preferences.get(axis, 3)
        diff = abs(expected - actual) / 4.0
        diffs.append(1.0 - diff)
        evidence.append(f"Trục '{axis}': kỳ vọng {expected}/5, bạn chọn {actual}/5")
    if not diffs:
        return ScoreResult(score=0.5, evidence=["Chưa có đủ dữ liệu phong cách làm việc"], is_estimated=True)
    return ScoreResult(score=round(sum(diffs) / len(diffs), 4), evidence=evidence)


def compute_constraint_match(profile: StudentCareerProfile, role: CareerRole) -> ScoreResult:
    """Đánh giá xung đột ràng buộc cá nhân (Giờ làm, Remote, Tiếng Anh, Chuyển chỗ ở).
    Nếu nghề yêu cầu làm ca mà sinh viên chỉ muốn giờ hành chính -> Giảm điểm nghiêm túc."""
    score = 1.0
    evidence = []
    c = profile.constraints

    # 1. Ràng buộc giờ làm việc / ca kíp
    if role.preferred_hours == "shift_ok" and c.preferred_hours == "office_hours" and not c.shift_acceptance:
        score -= 0.35
        evidence.append("Vai trò có thể yêu cầu làm ca/trực đêm, trong khi bạn chỉ muốn giờ hành chính (-0.35)")
    else:
        evidence.append("Giờ làm việc phù hợp với mong muốn của bạn (+)")

    # 2. Ràng buộc địa điểm / hình thức làm việc
    if role.remote_friendly == "on_site" and c.remote_preference == "remote":
        score -= 0.25
        evidence.append("Vai trò thường yêu cầu làm việc tại chỗ (On-site), trong khi bạn ưu tiên làm từ xa (Remote) (-0.25)")
    else:
        evidence.append("Hình thức làm việc (On-site/Remote/Flexible) tương thích (+)")

    # 3. Trình độ tiếng Anh tối thiểu
    required_eng = ENGLISH_LEVEL_VALUE.get(role.minimum_english, 0.55)
    actual_eng = ENGLISH_LEVEL_VALUE.get(c.english_level, 0.55)
    if actual_eng < required_eng:
        penalty = min(0.30, round(required_eng - actual_eng, 2))
        score -= penalty
        evidence.append(f"Tiếng Anh yêu cầu tối thiểu {role.minimum_english}, bạn tự đánh giá {c.english_level} (-{penalty:.2f})")
    else:
        evidence.append(f"Trình độ tiếng Anh ({c.english_level}) đáp ứng yêu cầu ({role.minimum_english}) (+)")

    # 4. Sẵn sàng chuyển chỗ ở
    if not c.willing_to_relocate and c.desired_location and "Hồ Chí Minh" not in c.desired_location and "Hà Nội" not in c.desired_location:
        # Nếu ở tỉnh xa và không thể relocate mà nghề công nghệ tập trung ở đô thị
        score -= 0.15
        evidence.append(f"Không sẵn sàng chuyển nơi làm việc ngoài khu vực '{c.desired_location}' (-0.15)")

    return ScoreResult(score=round(max(0.0, score), 4), evidence=evidence)


# ============================================================================
# 2. CAREER FIT RESULT & TÍNH ĐỘ TIN CẬY
# ============================================================================
@dataclass
class CareerFitResult:
    role_id: str
    role_name: str
    fit_score: float                                      # 0.0 - 100.0%
    breakdown: Dict[str, ScoreResult]
    confidence: str                                       # Low | Medium | High
    confidence_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_name": self.role_name,
            "fit_score": self.fit_score,
            "breakdown": {k: v.to_dict() for k, v in self.breakdown.items()},
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
        }


def _estimate_confidence(profile: StudentCareerProfile) -> Tuple[str, str]:
    completeness = profile.profile_completeness()
    n_filled = sum(1 for v in completeness.values() if v)
    if n_filled >= 5:
        return "High", "Hồ sơ có dữ liệu đầy đủ từ học tập, kỹ năng có chứng cứ, kinh nghiệm, sở thích và phong cách làm việc."
    if n_filled >= 3:
        return "Medium", "Hồ sơ có một số mảng dữ liệu (học tập/kỹ năng/sở thích) nhưng còn thiếu kinh nghiệm thực tế hoặc ràng buộc cá nhân."
    return "Low", "Hồ sơ hiện chủ yếu dựa trên điểm số hoặc sở thích đơn lẻ — hãy bổ sung kỹ năng và kinh nghiệm để nâng cao độ chính xác của tư vấn."


def compute_career_fit(profile: StudentCareerProfile, role: CareerRole) -> CareerFitResult:
    breakdown = {
        "skill": compute_skill_match(profile, role),
        "academic": compute_academic_match(profile, role),
        "interest": compute_interest_match(profile, role),
        "experience": compute_experience_match(profile, role),
        "work_style": compute_work_style_match(profile, role),
        "constraint": compute_constraint_match(profile, role),
    }
    total = sum(CAREER_FIT_WEIGHTS[k] * breakdown[k].score for k in CAREER_FIT_WEIGHTS)
    confidence, reason = _estimate_confidence(profile)
    return CareerFitResult(
        role_id=role.role_id,
        role_name=role.role_name,
        fit_score=round(total * 100, 1),
        breakdown=breakdown,
        confidence=confidence,
        confidence_reason=reason,
    )


# ============================================================================
# 3. CAREER READINESS RESULT
# ============================================================================
@dataclass
class CareerReadinessResult:
    role_id: str
    role_name: str
    readiness_score: float                                # 0.0 - 100.0%
    breakdown: Dict[str, ScoreResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_name": self.role_name,
            "readiness_score": self.readiness_score,
            "breakdown": {k: v.to_dict() for k, v in self.breakdown.items()},
        }


def compute_career_readiness(profile: StudentCareerProfile, role: CareerRole) -> CareerReadinessResult:
    """Career Readiness = 35% Required Skills + 20% Project Evidence + 15% Experience
                        + 10% Portfolio + 10% English + 10% Interview Preparation."""
    # 1. Required Skill Coverage
    required_coverage, req_ev = _weighted_skill_coverage(role.required_skills, profile)
    required_score = ScoreResult(score=round(required_coverage, 4), evidence=req_ev)

    # 2. Project Evidence
    project_score = compute_experience_match(profile, role)

    # 3. General Experience
    n_exp = len(profile.experience.items)
    exp_val = min(1.0, n_exp / max(1, role.experience_expectation))
    experience_score = ScoreResult(
        score=round(exp_val, 4),
        evidence=[f"{n_exp} mục hoạt động/kinh nghiệm trong hồ sơ"],
    )

    # 4. Portfolio
    has_port = profile.experience.has_portfolio()
    portfolio_score = ScoreResult(
        score=1.0 if has_port else 0.0,
        evidence=["Đã có liên kết Portfolio / Sản phẩm thực tế (+10%)"] if has_port else ["Chưa có Portfolio sản phẩm thực tế (-10%)"],
    )

    # 5. English
    eng_val = ENGLISH_LEVEL_VALUE.get(profile.constraints.english_level, 0.55)
    english_score = ScoreResult(
        score=round(eng_val, 4),
        evidence=[f"Trình độ tiếng Anh hiện tại: {profile.constraints.english_level}"],
    )

    # 6. Interview Preparation
    is_ready = profile.experience.is_interview_ready()
    interview_score = ScoreResult(
        score=0.8 if is_ready else 0.2,
        evidence=["Đã có kinh nghiệm phỏng vấn / làm việc thực tế"] if is_ready
        else ["Chưa có sự chuẩn bị hoặc kinh nghiệm phỏng vấn kỹ thuật — mức nền 20%"],
        is_estimated=not is_ready,
    )

    breakdown = {
        "required_skill_coverage": required_score,
        "project_evidence": project_score,
        "experience": experience_score,
        "portfolio": portfolio_score,
        "english": english_score,
        "interview_prep": interview_score,
    }

    total = sum(CAREER_READINESS_WEIGHTS[k] * breakdown[k].score for k in CAREER_READINESS_WEIGHTS)
    return CareerReadinessResult(
        role_id=role.role_id,
        role_name=role.role_name,
        readiness_score=round(total * 100, 1),
        breakdown=breakdown,
    )


# ============================================================================
# 4. RANKING & CONFLICT DETECTION (CÂU HỎI 5)
# ============================================================================
def rank_careers(
    profile: StudentCareerProfile,
    roles: List[CareerRole],
    top_k: int = 5,
) -> List[Tuple[CareerFitResult, CareerReadinessResult]]:
    """Xếp hạng Top K nghề nghiệp dựa trên Career Fit, đồng thời tính Readiness độc lập."""
    results = [(compute_career_fit(profile, r), compute_career_readiness(profile, r)) for r in roles]
    results.sort(key=lambda pair: pair[0].fit_score, reverse=True)
    return results[:top_k]


@dataclass
class ConstraintConflictItem:
    role_id: str
    role_name: str
    capability_score: float                               # Trung bình Academic + Skill Fit (0-100%)
    constraint_score: float                               # Điểm Constraint Match (0-100%)
    conflict_reasons: List[str]                           # Các điểm gây xung đột


def detect_capability_vs_constraint_conflicts(
    profile: StudentCareerProfile,
    roles: List[CareerRole],
) -> List[ConstraintConflictItem]:
    """Trả lời Câu hỏi 5: 'Nghề nào phù hợp với năng lực nhưng không phù hợp với điều kiện cá nhân?'
    Phát hiện các vai trò có Capability (Academic + Skill) >= 65% nhưng Constraint Match < 70%."""
    conflicts: List[ConstraintConflictItem] = []
    for role in roles:
        fit = compute_career_fit(profile, role)
        skill_score = fit.breakdown["skill"].score * 100
        academic_score = fit.breakdown["academic"].score * 100
        constraint_score = fit.breakdown["constraint"].score * 100
        capability_score = round((skill_score * 0.6 + academic_score * 0.4), 1)

        # Điều kiện: Năng lực khá tốt nhưng ràng buộc cá nhân bị trừ điểm rõ rệt
        if capability_score >= 60.0 and constraint_score < 75.0:
            negative_ev = [
                ev for ev in fit.breakdown["constraint"].evidence
                if "(-" in ev or "không" in ev.lower() or "chưa" in ev.lower()
            ]
            if negative_ev:
                conflicts.append(ConstraintConflictItem(
                    role_id=role.role_id,
                    role_name=role.role_name,
                    capability_score=capability_score,
                    constraint_score=constraint_score,
                    conflict_reasons=negative_ev,
                ))

    conflicts.sort(key=lambda x: (x.capability_score - x.constraint_score), reverse=True)
    return conflicts
