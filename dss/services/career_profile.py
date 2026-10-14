"""Career Profile — Hồ sơ nghề nghiệp đa chiều cho Career Decision Support System.

Thay thế hoàn toàn mô hình cũ (Interest + Academic Score -> Career Recommendation) bằng
Career Profile có cấu trúc, mọi trường đều truy vết được về nguồn gốc dữ liệu
(evidence/source) — không bao giờ tự suy diễn "có kỹ năng" nếu không có bằng chứng.

Các phân hệ dữ liệu:
1. Academic Profile (GPA, subject scores, competency domains, strengths, weaknesses)
2. Skill Profile (Technical, Business, Soft, Language với level, evidence, confidence, source)
3. Experience Profile (Internship, Employment, Projects, Thesis, Certifications, Portfolio, Interview Prep)
4. Interest Profile (Mini-assessment 7 chiều theo thang 1–5)
5. Work-style Profile (7 trục đối sánh phong cách làm việc)
6. Career Constraints (Địa điểm, Ca kíp, Mức lương, Tiếng Anh, Remote, Thời gian học)
7. Career Goal (Loại mục tiêu, Nghề mục tiêu, Khung thời gian 1/3/6/12/24 tháng)
8. Feedback Loop (Lưu vết task đã hoàn thành, kỹ năng đã nâng cấp)
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from dss.core.data_helpers import TOPIC_SCORE_COLUMNS

# ============================================================================
# I. ACADEMIC PROFILE — Map Subject -> Competency Domain
# ============================================================================
# Map linh hoạt cả tên cột dataset demo (TOPIC_SCORE_COLUMNS), tên cột chuẩn hóa,
# và tên môn học tiếng Anh/tiếng Việt theo yêu cầu nghiệp vụ.
SUBJECT_TO_COMPETENCY_DOMAIN: Dict[str, str] = {
    # Dataset demo columns
    "diem_thong_ke": "Data Analysis / Quantitative Skills",
    "diem_xu_ly_du_lieu": "SQL / Data Engineering",
    "diem_truc_quan_hoa": "Data Visualization / BI",
    "diem_machine_learning": "AI / Data Science",
    "diem_lap_trinh": "Software / Web Development",
    # English names
    "Statistics": "Data Analysis / Quantitative Skills",
    "Database": "SQL / Data Engineering",
    "Machine Learning": "AI / Data Science",
    "Web Programming": "Software / Web Development",
    "Software Analysis": "Business Analysis",
    "Data Visualization": "Data Visualization / BI",
    # Common Vietnamese aliases
    "Thống kê": "Data Analysis / Quantitative Skills",
    "Cơ sở dữ liệu": "SQL / Data Engineering",
    "diem_csdl": "SQL / Data Engineering",
    "Lập trình Python": "Software / Web Development",
    "diem_web": "Software / Web Development",
    "Phân tích phần mềm": "Business Analysis",
    "diem_ptpm": "Business Analysis",
    "Trực quan hóa dữ liệu": "Data Visualization / BI",
}


@dataclass
class AcademicProfile:
    gpa: float = 0.0                                             # GPA tổng quan (0.0 - 10.0 hoặc quy đổi)
    subject_scores: Dict[str, float] = field(default_factory=dict)  # tên môn/cột -> điểm 0-10
    domain_scores: Dict[str, float] = field(default_factory=dict)   # competency domain -> điểm 0-10
    strengths: List[str] = field(default_factory=list)             # domain điểm >= 7.0
    weaknesses: List[str] = field(default_factory=list)            # domain điểm < 5.5

    @classmethod
    def build(cls, raw_row: Dict[str, Any]) -> "AcademicProfile":
        subject_scores: Dict[str, float] = {}
        domain_accum: Dict[str, List[float]] = {}

        # 1. Quét các cột điểm theo chủ đề và các môn học có trong raw_row
        for k, v in raw_row.items():
            if v is None:
                continue
            try:
                num_v = float(v)
            except (ValueError, TypeError):
                continue

            # Kiểm tra xem k có trong SUBJECT_TO_COMPETENCY_DOMAIN không
            if k in SUBJECT_TO_COMPETENCY_DOMAIN:
                subject_scores[k] = num_v
                domain = SUBJECT_TO_COMPETENCY_DOMAIN[k]
                domain_accum.setdefault(domain, []).append(num_v)

        # 2. Tính domain scores = trung bình các môn thuộc domain đó
        domain_scores: Dict[str, float] = {}
        for domain, vals in domain_accum.items():
            domain_scores[domain] = round(sum(vals) / len(vals), 2)

        # 3. Tính GPA tổng quan (ưu tiên final_score, gpa_previous, diem_gpa, hoặc TB các môn)
        gpa = 0.0
        for gpa_key in ("final_score", "gpa_previous", "diem_gpa", "gpa"):
            if gpa_key in raw_row and raw_row[gpa_key] is not None:
                try:
                    gpa = round(float(raw_row[gpa_key]), 2)
                    break
                except (ValueError, TypeError):
                    pass
        if gpa == 0.0 and subject_scores:
            gpa = round(sum(subject_scores.values()) / len(subject_scores), 2)

        strengths = [d for d, s in domain_scores.items() if s >= 7.0]
        weaknesses = [d for d, s in domain_scores.items() if s < 5.5]

        return cls(
            gpa=gpa,
            subject_scores=subject_scores,
            domain_scores=domain_scores,
            strengths=strengths,
            weaknesses=weaknesses,
        )


# ============================================================================
# II. SKILL PROFILE
# ============================================================================
SKILL_LEVELS = ["None", "Basic", "Intermediate", "Advanced"]
SKILL_LEVEL_VALUE = {"None": 0.0, "Basic": 0.33, "Intermediate": 0.66, "Advanced": 1.0}

TECHNICAL_SKILLS = [
    "Python", "SQL", "Java", "C++", "Excel", "Power BI",
    "Machine Learning", "Statistics", "Database", "Cloud",
]
BUSINESS_SKILLS = ["Requirement Analysis", "Documentation", "KPI Analysis", "Process Analysis"]
SOFT_SKILLS = ["Communication", "Presentation", "Teamwork", "Problem Solving", "Self-learning"]
LANGUAGE_SKILLS = ["English"]

ALL_SKILL_CATALOG = {
    "technical": TECHNICAL_SKILLS,
    "business": BUSINESS_SKILLS,
    "soft": SOFT_SKILLS,
    "language": LANGUAGE_SKILLS,
}

_DOMAIN_TO_SKILL_EVIDENCE = {
    "AI / Data Science": [("Machine Learning", "technical"), ("Python", "technical")],
    "SQL / Data Engineering": [("SQL", "technical"), ("Database", "technical")],
    "Data Analysis / Quantitative Skills": [("Statistics", "technical")],
    "Data Visualization / BI": [("Power BI", "technical"), ("Excel", "technical")],
    "Software / Web Development": [("Python", "technical"), ("Java", "technical")],
    "Business Analysis": [("Requirement Analysis", "business"), ("Documentation", "business")],
}


@dataclass
class SkillItem:
    skill_name: str
    category: str                                            # technical | business | soft | language
    skill_level: str = "None"                                # None | Basic | Intermediate | Advanced
    evidence: List[str] = field(default_factory=list)        # Các chuỗi chứng cứ thực tế
    confidence: str = "low"                                  # low | medium | high
    source: str = "self_assessment"                          # self_assessment | academic_score | project | experience | certificate

    @property
    def achieved_level(self) -> float:
        return SKILL_LEVEL_VALUE.get(self.skill_level, 0.0)


@dataclass
class SkillProfile:
    items: Dict[str, SkillItem] = field(default_factory=dict)

    def get(self, skill_name: str) -> SkillItem:
        if skill_name in self.items:
            return self.items[skill_name]
        # Tìm category mặc định
        category = "technical"
        for cat, skills in ALL_SKILL_CATALOG.items():
            if skill_name in skills:
                category = cat
                break
        item = SkillItem(skill_name=skill_name, category=category)
        self.items[skill_name] = item
        return item

    def upsert_self_assessment(self, skill_name: str, category: str, level: str) -> None:
        """Sinh viên tự đánh giá kỹ năng — confidence phụ thuộc vào việc đã có evidence chưa."""
        existing = self.items.get(skill_name)
        evidence = list(existing.evidence) if existing else []
        src = existing.source if (existing and existing.source != "self_assessment") else "self_assessment"
        conf = "medium" if evidence else "low"
        self.items[skill_name] = SkillItem(
            skill_name=skill_name,
            category=category,
            skill_level=level,
            evidence=evidence,
            confidence=conf,
            source=src,
        )

    def add_evidence_from_academic(self, academic: AcademicProfile) -> None:
        """Bổ sung bằng chứng kỹ năng từ kết quả học thuật khi domain đạt >= 7.0."""
        for domain, skills in _DOMAIN_TO_SKILL_EVIDENCE.items():
            domain_score = academic.domain_scores.get(domain)
            if domain_score is None or domain_score < 7.0:
                continue
            for skill_name, category in skills:
                evidence_line = f"Môn học thuộc {domain}: {domain_score:.1f}/10"
                existing = self.items.get(skill_name)
                if existing:
                    if evidence_line not in existing.evidence:
                        existing.evidence.append(evidence_line)
                    existing.confidence = "medium" if existing.confidence == "low" else existing.confidence
                    if existing.source == "self_assessment":
                        existing.source = "academic_score"
                else:
                    self.items[skill_name] = SkillItem(
                        skill_name=skill_name,
                        category=category,
                        skill_level="Basic",
                        evidence=[evidence_line],
                        confidence="medium",
                        source="academic_score",
                    )

    def add_evidence_from_experience(
        self,
        skill_name: str,
        category: str,
        evidence_line: str,
        min_level: str = "Basic",
    ) -> None:
        """Dự án/kinh nghiệm thực tế nâng confidence lên 'high' và đảm bảo skill_level tối thiểu."""
        existing = self.items.get(skill_name)
        if existing:
            if SKILL_LEVEL_VALUE.get(existing.skill_level, 0) < SKILL_LEVEL_VALUE.get(min_level, 0):
                existing.skill_level = min_level
            if evidence_line not in existing.evidence:
                existing.evidence.append(evidence_line)
            existing.confidence = "high"
            existing.source = "project" if "project" in evidence_line.lower() else "experience"
        else:
            self.items[skill_name] = SkillItem(
                skill_name=skill_name,
                category=category,
                skill_level=min_level,
                evidence=[evidence_line],
                confidence="high",
                source="project" if "project" in evidence_line.lower() else "experience",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {k: asdict(v) for k, v in self.items.items()}


# ============================================================================
# III. EXPERIENCE PROFILE
# ============================================================================
EXPERIENCE_TYPES = [
    "project",
    "internship",
    "employment",
    "thesis",
    "certification",
    "extracurricular",
    "portfolio",
]


@dataclass
class ExperienceItem:
    exp_type: str                                            # EXPERIENCE_TYPES
    title: str
    related_skills: List[str] = field(default_factory=list)  # skill_name gắn kèm
    description: str = ""
    artifact_url: str = ""                                   # GitHub, Kaggle, Certificate URL...
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExperienceProfile:
    items: List[ExperienceItem] = field(default_factory=list)
    has_portfolio_flag: bool = False
    interview_ready_flag: bool = False

    def has_portfolio(self) -> bool:
        return self.has_portfolio_flag or any(it.exp_type == "portfolio" or bool(it.artifact_url) for it in self.items)

    def is_interview_ready(self) -> bool:
        return self.interview_ready_flag or any(it.exp_type in ("internship", "employment") for it in self.items)

    def count_relevant_projects(self, related_domain_skills: List[str]) -> int:
        if not related_domain_skills:
            return 0
        related_set = set(related_domain_skills)
        return sum(
            1 for it in self.items
            if it.exp_type in ("project", "thesis", "internship", "employment", "portfolio")
            and related_set.intersection(it.related_skills)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [asdict(it) for it in self.items],
            "has_portfolio_flag": self.has_portfolio_flag,
            "interview_ready_flag": self.interview_ready_flag,
        }


# ============================================================================
# IV. INTEREST PROFILE (Mini Career Assessment - 7 Trục)
# ============================================================================
INTEREST_AXES = {
    "data": "📊 Làm việc với dữ liệu & thống kê",
    "system_building": "🏗️ Xây dựng hệ thống & kiến trúc phần mềm",
    "business_problem": "💼 Giải quyết bài toán kinh doanh & quy trình",
    "client_communication": "🗣️ Giao tiếp với khách hàng & đối tác",
    "ai_research": "🔬 Nghiên cứu thuật toán AI & Machine Learning",
    "ui_ux_design": "🎨 Thiết kế giao diện & trải nghiệm người dùng",
    "system_operations": "⚙️ Vận hành hệ thống, DevOps & hạ tầng cloud",
}

# Ánh xạ tương thích ngược từ các mã khảo sát cũ nếu có
_INTEREST_LEGACY_MAP = {
    "code": "system_building",
    "design": "ui_ux_design",
    "communication": "client_communication",
    "management": "business_problem",
    "research": "ai_research",
    "operations": "system_operations",
    "business": "business_problem",
}


@dataclass
class InterestProfile:
    scores: Dict[str, int] = field(default_factory=dict)  # axis -> 1..5

    def get_score(self, axis: str) -> int:
        if axis in self.scores:
            return self.scores[axis]
        # Fallback qua legacy map
        for old_k, new_k in _INTEREST_LEGACY_MAP.items():
            if new_k == axis and old_k in self.scores:
                return self.scores[old_k]
        return 3  # Mặc định trung tính

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.scores)


# ============================================================================
# V. WORK-STYLE PROFILE (7 Trục Đối Sánh)
# ============================================================================
WORK_STYLE_AXES = {
    "independence": ("Làm việc độc lập", "Làm việc nhóm (teamwork)"),
    "orientation": ("Thiên về kỹ thuật (technical)", "Thiên về nghiệp vụ (business)"),
    "task_type": ("Thiên về phân tích", "Thiên về giao tiếp"),
    "environment": ("Môi trường ổn định", "Môi trường thay đổi nhanh"),
    "workplace": ("Desk job (văn phòng)", "Field work (hiện trường)"),
    "hours": ("Giờ hành chính cố định", "Chấp nhận làm ca (shift)"),
    "career_track": ("Chuyên gia kỹ thuật (specialist)", "Quản lý (management)"),
}


@dataclass
class WorkStyleProfile:
    # 1 = nghiêng hẳn về lựa chọn trái, 5 = nghiêng hẳn về lựa chọn phải (3 = cân bằng)
    preferences: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.preferences)


# ============================================================================
# VI. CAREER CONSTRAINTS
# ============================================================================
ENGLISH_LEVEL_VALUE = {"Beginner": 0.25, "Intermediate": 0.55, "Advanced": 0.8, "Fluent": 1.0}


@dataclass
class CareerConstraints:
    desired_location: str = "Hồ Chí Minh"
    willing_to_relocate: bool = True
    preferred_hours: str = "office_hours"                   # office_hours | shift_ok
    shift_acceptance: bool = False                           # Có chấp nhận làm ca kíp không
    expected_salary_band: str = "10 - 15 triệu"
    english_level: str = "Intermediate"                      # Beginner | Intermediate | Advanced | Fluent
    learning_hours_per_week: float = 8.0
    preferred_industry: str = "Công nghệ thông tin"
    remote_preference: str = "flexible"                      # remote | on_site | flexible

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# VII. CAREER GOAL
# ============================================================================
@dataclass
class CareerGoal:
    goal_type: str = "Fresher job"                           # Internship | Fresher job | Junior role | Career switching | Long-term career
    target_role_id: Optional[str] = "data_analyst"
    target_timeframe_months: int = 6                         # 1 | 3 | 6 | 12 | 24 tháng

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# VIII. STUDENT CAREER PROFILE — Tổng Hợp Đa Chiều
# ============================================================================
@dataclass
class StudentCareerProfile:
    student_pseudonym: str
    data_source: str                                         # "REAL" | "DEMO"
    academic: AcademicProfile = field(default_factory=AcademicProfile)
    skills: SkillProfile = field(default_factory=SkillProfile)
    experience: ExperienceProfile = field(default_factory=ExperienceProfile)
    interest: InterestProfile = field(default_factory=InterestProfile)
    work_style: WorkStyleProfile = field(default_factory=WorkStyleProfile)
    constraints: CareerConstraints = field(default_factory=CareerConstraints)
    goal: CareerGoal = field(default_factory=CareerGoal)
    completed_tasks: List[str] = field(default_factory=list) # Danh sách task_id đã hoàn thành (Feedback loop)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def profile_completeness(self) -> Dict[str, bool]:
        """Tính mức độ đầy đủ của hồ sơ để xác định Confidence khuyến nghị."""
        return {
            "academic": bool(self.academic.domain_scores),
            "skills": any(s.achieved_level > 0 for s in self.skills.items.values()),
            "experience": bool(self.experience.items),
            "interest": any(v != 3 for v in self.interest.scores.values()) if self.interest.scores else False,
            "work_style": bool(self.work_style.preferences),
            "constraints": bool(self.constraints.desired_location or self.constraints.preferred_industry),
            "goal": bool(self.goal.target_role_id),
        }

    def clone(self) -> "StudentCareerProfile":
        """Deep copy để phục vụ What-if Analysis mà không làm thay đổi hồ sơ thật."""
        return copy.deepcopy(self)

    def mark_task_completed(self, task_id: str, skill_to_upgrade: Optional[str] = None, new_level: str = "Intermediate") -> None:
        """Feedback loop: Đánh dấu task hoàn thành và nâng cấp kỹ năng liên quan."""
        if task_id not in self.completed_tasks:
            self.completed_tasks.append(task_id)
        if skill_to_upgrade:
            category = "technical"
            for cat, skills in ALL_SKILL_CATALOG.items():
                if skill_to_upgrade in skills:
                    category = cat
                    break
            self.skills.add_evidence_from_experience(
                skill_to_upgrade,
                category,
                f"Đã hoàn thành mục tiêu trong lộ trình: {task_id}",
                min_level=new_level,
            )
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_pseudonym": self.student_pseudonym,
            "data_source": self.data_source,
            "academic": asdict(self.academic),
            "skills": self.skills.to_dict(),
            "experience": self.experience.to_dict(),
            "interest": self.interest.to_dict(),
            "work_style": self.work_style.to_dict(),
            "constraints": self.constraints.to_dict(),
            "goal": self.goal.to_dict(),
            "completed_tasks": list(self.completed_tasks),
            "updated_at": self.updated_at,
        }

    @classmethod
    def build_from_row(
        cls,
        student_id: str,
        raw_row: Dict[str, Any],
        data_source: str = "DEMO",
    ) -> "StudentCareerProfile":
        from dss.services.privacy_service import generate_pseudonym

        academic = AcademicProfile.build(raw_row)
        skills = SkillProfile()
        skills.add_evidence_from_academic(academic)

        # Khởi tạo mặc định các trục sở thích ở mức 3 (trung tính)
        interest = InterestProfile(scores={k: 3 for k in INTEREST_AXES})

        # Khởi tạo mặc định phong cách làm việc ở mức 3 (cân bằng)
        work_style = WorkStyleProfile(preferences={k: 3 for k in WORK_STYLE_AXES})

        return cls(
            student_pseudonym=generate_pseudonym(student_id),
            data_source=data_source,
            academic=academic,
            skills=skills,
            interest=interest,
            work_style=work_style,
        )
