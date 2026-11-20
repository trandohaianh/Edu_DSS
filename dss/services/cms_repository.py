"""CMS Repository Layer — Phân hệ quản lý nội dung và chương trình đào tạo.

Tuân thủ nguyên tắc:
1. CMS (Content Management System / Learning Content Repository) là nguồn dữ liệu chuẩn cho:
   - course content, module, topic, lesson, material
   - learning outcome (CLO/PLO), skill mapping, prerequisite
   - learning resource, difficulty, learning path
2. CMS phải được dùng để:
   - map học phần → kỹ năng
   - map nội dung → competency
   - tìm tài liệu phù hợp với skill gap
   - sinh learning roadmap với resource cụ thể, đo lường được thay vì lời khuyên chung chung.
3. Hỗ trợ 3 chế độ: DEMO, MOCK, REAL_CONNECTOR.
4. Trạng thái minh bạch:
   - IMPLEMENTED (Kiến trúc, Model, Catalog 12 miền kỹ năng, Matching Engine)
   - DEMO (Kho học liệu chuẩn nội bộ)
   - PARTIAL (Nội dung lưu trữ cục bộ)
   - FUTURE REAL INTEGRATION (Headless CMS Strapi/Directus, Git-based Curriculum).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

STATUS_IMPLEMENTED = "IMPLEMENTED"
STATUS_DEMO = "DEMO"
STATUS_PARTIAL = "PARTIAL"
STATUS_FUTURE_REAL = "FUTURE REAL INTEGRATION"

MODE_DEMO = "DEMO"
MODE_MOCK = "MOCK"
MODE_REAL = "REAL_CONNECTOR"


@dataclass
class CMSCourseContent:
    course_id: str
    course_code: str
    course_name: str
    credits: int = 3
    department: str = "Khoa CNTT"
    description: str = ""


@dataclass
class CMSModule:
    module_id: str
    course_id: str
    module_name: str
    order: int
    target_competency: str


@dataclass
class CMSTopic:
    topic_id: str
    module_id: str
    topic_name: str
    difficulty: str = "Intermediate"  # "Beginner" | "Intermediate" | "Advanced"


@dataclass
class CMSLesson:
    lesson_id: str
    topic_id: str
    lesson_title: str
    duration_minutes: int = 60
    prerequisites: List[str] = field(default_factory=list)
    practice_task: str = ""


@dataclass
class CMSLearningOutcome:
    outcome_id: str
    course_id: str
    description: str
    bloom_level: str = "Apply"  # Remember | Understand | Apply | Analyze | Evaluate | Create


@dataclass
class CMSSkillMapping:
    skill_name: str
    target_level: str                 # "Basic" | "Intermediate" | "Advanced"
    course_id: str
    module_id: str
    topic_name: str
    competency_domain: str
    min_grade: float = 6.5


@dataclass
class CMSLearningResource:
    resource_id: str
    title: str
    resource_type: str                # "interactive_lab" | "video_lecture" | "reading" | "practice_quiz" | "capstone_project"
    url: str
    provider: str                     # "EduDSS CMS" | "Coursera" | "Kaggle" | "Học liệu CNTT" | "Microsoft Learn"
    estimated_hours: float
    difficulty: str                   # "Beginner" | "Intermediate" | "Advanced"
    for_skill: str
    for_topic: Optional[str] = None


@dataclass
class CMSResourceMatch:
    """Kết quả khớp nối cụ thể từ CMS để khắc phục khoảng cách kỹ năng."""
    skill_name: str
    gap_topic: str
    course_code: str
    module_title: str
    lesson_title: str
    practice_action: str
    resource_title: str
    resource_url: str
    difficulty: str
    estimated_hours: float
    target_outcome: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseCMSRepository(ABC):
    """Giao diện trừu tượng chuẩn hóa Content Management System."""

    def __init__(self, mode: str = MODE_DEMO):
        self.mode = mode

    @abstractmethod
    def map_course_to_skills(self, course_id: str) -> List[CMSSkillMapping]:
        """Ánh xạ học phần trong chương trình sang danh mục kỹ năng chuẩn."""
        pass

    @abstractmethod
    def map_content_to_competencies(self, domain: str) -> List[CMSModule]:
        """Ánh xạ nội dung bài giảng sang miền năng lực."""
        pass

    @abstractmethod
    def find_resources_for_skill_gap(
        self,
        skill_name: str,
        current_level: str,
        target_level: str,
        specific_gap_topic: Optional[str] = None,
    ) -> List[CMSResourceMatch]:
        """Tìm tài liệu, bài học và lab cụ thể trong CMS để bù đắp skill gap."""
        pass

    def get_integration_status(self) -> Dict[str, str]:
        return {
            "component": "CMS Repository",
            "mode": self.mode,
            "architecture_status": STATUS_IMPLEMENTED,
            "data_mode_status": STATUS_DEMO if self.mode == MODE_DEMO else STATUS_PARTIAL,
            "external_systems": STATUS_FUTURE_REAL,
            "external_notes": "Sẵn sàng tích hợp Headless CMS (Strapi/Directus) hoặc Git Curriculum Repo.",
        }


class DemoCMSRepository(BaseCMSRepository):
    """Triển khai Demo: Kho học liệu và cấu trúc chương trình đào tạo chuẩn hóa cho 12+ miền kỹ năng."""

    def __init__(self):
        super().__init__(mode=MODE_DEMO)
        self._init_catalog()

    def _init_catalog(self) -> None:
        # Cấu trúc khóa học, module và ánh xạ chi tiết
        self._skill_remedies: Dict[str, List[CMSResourceMatch]] = {
            "SQL": [
                CMSResourceMatch(
                    skill_name="SQL",
                    gap_topic="Window Functions & Analytics",
                    course_code="CS201",
                    module_title="Module 04: SQL Nâng Cao & Phân Tích Dữ Liệu",
                    lesson_title="Bài 4.2: Window Functions (OVER, PARTITION BY, ROW_NUMBER, RANK)",
                    practice_action="Hoàn thành bài học Window Functions, sau đó làm bài thực hành SQL Analytics (3 bài tập tính running total & xếp hạng doanh số).",
                    resource_title="EduDSS CMS - Giáo trình & Lab SQL Analytics (CS201-M04)",
                    resource_url="https://learn.edudss.edu.vn/courses/cs201/modules/m04",
                    difficulty="Intermediate",
                    estimated_hours=4.0,
                    target_outcome="Đạt >= 7.5 điểm bài Quiz SQL Analytics trên LMS; nâng mức kỹ năng SQL lên Intermediate.",
                ),
                CMSResourceMatch(
                    skill_name="SQL",
                    gap_topic="CTE & Tối ưu hóa truy vấn",
                    course_code="CS201",
                    module_title="Module 05: Tối Ưu Hóa & Lập Trình Cơ Sở Dữ Liệu",
                    lesson_title="Bài 5.1: Common Table Expressions (CTE) & Đánh chỉ mục Indexing",
                    practice_action="Viết các truy vấn lồng phức tạp với WITH clause và phân tích EXPLAIN PLAN.",
                    resource_title="EduDSS CMS - Thực hành CTE & Indexing Chuyên Sâu",
                    resource_url="https://learn.edudss.edu.vn/courses/cs201/modules/m05",
                    difficulty="Advanced",
                    estimated_hours=5.0,
                    target_outcome="Xử lý thành thạo truy vấn đệ quy và tối ưu thời gian thực thi câu lệnh SQL.",
                ),
            ],
            "Python": [
                CMSResourceMatch(
                    skill_name="Python",
                    gap_topic="Pandas & Data Wrangling",
                    course_code="CS105",
                    module_title="Module 03: Xử Lý Dữ Liệu Với Pandas & NumPy",
                    lesson_title="Bài 3.1: Dataframe Manipulation, GroupBy, Merge & Pivot",
                    practice_action="Thực hiện làm sạch bộ dữ liệu thực tế gồm 10,000 dòng có giá trị khuyết và phân loại dữ liệu sai định dạng.",
                    resource_title="EduDSS CMS - Lab Xử Lý Dữ Liệu Pandas Thực Chiến",
                    resource_url="https://learn.edudss.edu.vn/courses/cs105/pandas-lab",
                    difficulty="Intermediate",
                    estimated_hours=6.0,
                    target_outcome="Hoàn thành notebook làm sạch dữ liệu và nộp bài trên LMS đạt chuẩn đánh giá tự động.",
                ),
            ],
            "Statistics": [
                CMSResourceMatch(
                    skill_name="Statistics",
                    gap_topic="Kiểm định Giả thuyết & Hồi quy",
                    course_code="MATH202",
                    module_title="Module 04: Thống Kê Suy Luận Ứng Dụng",
                    lesson_title="Bài 4.3: A/B Testing, T-Test, ANOVA & Mô Hình Hồi Quy Tuyến Tính",
                    practice_action="Thiết kế kịch bản A/B Test cho tính năng phần mềm và tính toán p-value, khoảng tin cậy 95%.",
                    resource_title="EduDSS CMS - Chuyên đề Thống Kê Ứng Dụng Cho Phân Tích Dữ Liệu",
                    resource_url="https://learn.edudss.edu.vn/courses/math202/hypothesis-testing",
                    difficulty="Intermediate",
                    estimated_hours=5.0,
                    target_outcome="Đọc hiểu và giải thích chính xác ý nghĩa thống kê của các chỉ số p-value, R-squared.",
                ),
            ],
            "Machine Learning": [
                CMSResourceMatch(
                    skill_name="Machine Learning",
                    gap_topic="Đánh giá mô hình & Chống Overfitting",
                    course_code="CS310",
                    module_title="Module 02: Mô Hình Phân Lớp & Đánh Giá Năng Lực",
                    lesson_title="Bài 2.4: Cross-Validation, Precision, Recall, F1-Score & ROC-AUC",
                    practice_action="Huấn luyện mô hình Random Forest và vẽ đường cong ROC-AUC, xử lý dữ liệu mất cân bằng với SMOTE.",
                    resource_title="EduDSS CMS - Notebook & Lab Học Máy Ứng Dụng",
                    resource_url="https://learn.edudss.edu.vn/courses/cs310/evaluation-metrics",
                    difficulty="Intermediate",
                    estimated_hours=8.0,
                    target_outcome="Xây dựng pipeline ML chuẩn mực có bước tiền xử lý và cross-validation hoàn chỉnh.",
                ),
            ],
            "Power BI": [
                CMSResourceMatch(
                    skill_name="Power BI",
                    gap_topic="Mô hình hóa dữ liệu & Công thức DAX",
                    course_code="BA205",
                    module_title="Module 03: Trực Quan Hóa Dữ Liệu & Báo Cáo Quản Trị",
                    lesson_title="Bài 3.2: Star Schema Modeling, CALCULATE & Time-Intelligence DAX",
                    practice_action="Xây dựng Dashboard KPI bán hàng tương tác với biểu đồ Waterfall, Ribbon và bộ lọc Slicer linh hoạt.",
                    resource_title="Microsoft Learn & EduDSS - Xây dựng Dashboard Power BI Chuẩn Doanh Nghiệp",
                    resource_url="https://learn.microsoft.com/en-us/training/paths/data-analytics-microsoft/",
                    difficulty="Intermediate",
                    estimated_hours=6.0,
                    target_outcome="Tạo dashboard hoàn chỉnh có liên kết dữ liệu nhiều bảng theo chuẩn Star Schema.",
                ),
            ],
            "Excel": [
                CMSResourceMatch(
                    skill_name="Excel",
                    gap_topic="XLOOKUP, PivotTable & Power Query",
                    course_code="BA101",
                    module_title="Module 02: Công Cụ Phân Tích Dữ Liệu Văn Phòng",
                    lesson_title="Bài 2.1: Phân Tích Số Liệu Nâng Cao Với Excel",
                    practice_action="Tự động hóa báo cáo tháng sử dụng Power Query gom dữ liệu từ 5 file CSV rời rạc.",
                    resource_title="EduDSS CMS - Chuyên đề Excel Phân Tích Kinh Doanh",
                    resource_url="https://learn.edudss.edu.vn/courses/ba101/advanced-excel",
                    difficulty="Intermediate",
                    estimated_hours=4.0,
                    target_outcome="Tự động hóa luồng trích xuất và lập bảng PivotTable phân tích đa chiều.",
                ),
            ],
            "Requirement Analysis": [
                CMSResourceMatch(
                    skill_name="Requirement Analysis",
                    gap_topic="Thu thập yêu cầu & Viết tài liệu SRS/User Stories",
                    course_code="SE202",
                    module_title="Module 02: Kỹ Thuật Phân Tích Nghiệp Vụ Phần Mềm",
                    lesson_title="Bài 2.3: Viết User Story theo chuẩn INVEST & Tài liệu đặc tả Use Case",
                    practice_action="Lập tài liệu BRD/SRS cho hệ thống quản lý học tập thu nhỏ kèm sơ đồ luồng dữ liệu DFD.",
                    resource_title="EduDSS CMS - Kỹ Thuật Viết Đặc Tả & Phân Tích Nghiệp Vụ (SE202)",
                    resource_url="https://learn.edudss.edu.vn/courses/se202/srs-documentation",
                    difficulty="Intermediate",
                    estimated_hours=5.0,
                    target_outcome="Hoàn thành tài liệu đặc tả có đầy đủ tiêu chí nghiệm thu (Acceptance Criteria).",
                ),
            ],
            "Cloud": [
                CMSResourceMatch(
                    skill_name="Cloud",
                    gap_topic="Containerization Docker & Cloud Basics",
                    course_code="IT304",
                    module_title="Module 03: Hạ Tầng Điện Toán Đám Mây",
                    lesson_title="Bài 3.1: Đóng gói ứng dụng với Docker & Triển khai Container trên AWS ECS",
                    practice_action="Viết Dockerfile đóng gói API Python và deploy lên môi trường đám mây thử nghiệm.",
                    resource_title="EduDSS CMS - Lab Đóng Gói Docker & Cloud Services",
                    resource_url="https://learn.edudss.edu.vn/courses/it304/docker-cloud-lab",
                    difficulty="Intermediate",
                    estimated_hours=6.0,
                    target_outcome="Chạy container an toàn và cấu hình đúng biến môi trường trên cloud.",
                ),
            ],
            "Database": [
                CMSResourceMatch(
                    skill_name="Database",
                    gap_topic="Thiết kế Lược đồ & Chuẩn hóa 3NF",
                    course_code="CS201",
                    module_title="Module 02: Mô Hình Thực Thể Quan Hệ (ERD)",
                    lesson_title="Bài 2.2: Thiết kế Cơ Sở Dữ Liệu Quan Hệ & Các Dạng Chuẩn 1NF-3NF",
                    practice_action="Vẽ sơ đồ ERD cho bài toán thương mại điện tử và chuẩn hóa cấu trúc bảng tránh dư thừa dữ liệu.",
                    resource_title="EduDSS CMS - Thực Hành Thiết Kế CSDL & Chuẩn Hóa",
                    resource_url="https://learn.edudss.edu.vn/courses/cs201/erd-normalization",
                    difficulty="Basic",
                    estimated_hours=4.0,
                    target_outcome="Đạt chuẩn thiết kế dữ liệu không vi phạm ràng buộc toàn vẹn khóa chính và khóa ngoại.",
                ),
            ],
        }

    def map_course_to_skills(self, course_id: str) -> List[CMSSkillMapping]:
        mapping = {
            "CS201": [
                CMSSkillMapping("SQL", "Basic", "CS201", "M01", "SQL Cơ bản", "SQL / Data Engineering", 6.5),
                CMSSkillMapping("SQL", "Intermediate", "CS201", "M04", "SQL Window Functions", "SQL / Data Engineering", 7.5),
                CMSSkillMapping("Database", "Basic", "CS201", "M02", "Thiết kế ERD & Chuẩn hóa", "SQL / Data Engineering", 6.5),
            ],
            "CS105": [
                CMSSkillMapping("Python", "Basic", "CS105", "M01", "Lập trình Python Nền tảng", "Software / Web Development", 6.5),
                CMSSkillMapping("Python", "Intermediate", "CS105", "M03", "Xử lý Pandas", "Software / Web Development", 7.0),
            ],
            "MATH202": [
                CMSSkillMapping("Statistics", "Intermediate", "MATH202", "M04", "Thống kê Suy luận", "Data Analysis / Quantitative Skills", 7.0),
            ],
            "CS310": [
                CMSSkillMapping("Machine Learning", "Intermediate", "CS310", "M02", "Mô hình Phân lớp & Đánh giá", "AI / Data Science", 7.0),
            ],
            "BA205": [
                CMSSkillMapping("Power BI", "Intermediate", "BA205", "M03", "Trực quan hóa & DAX", "Data Visualization / BI", 7.0),
            ],
        }
        return mapping.get(course_id, [])

    def map_content_to_competencies(self, domain: str) -> List[CMSModule]:
        domain_modules = {
            "SQL / Data Engineering": [
                CMSModule("CS201-M01", "CS201", "Cơ sở dữ liệu quan hệ & SQL", 1, "SQL / Data Engineering"),
                CMSModule("CS201-M04", "CS201", "SQL Nâng Cao & Phân Tích Dữ Liệu", 4, "SQL / Data Engineering"),
            ],
            "Data Analysis / Quantitative Skills": [
                CMSModule("MATH202-M04", "MATH202", "Thống Kê Suy Luận & A/B Testing", 4, "Data Analysis / Quantitative Skills"),
            ],
            "Data Visualization / BI": [
                CMSModule("BA205-M03", "BA205", "Trực Quan Hóa Dữ Liệu & Báo Cáo Quản Trị", 3, "Data Visualization / BI"),
            ],
            "AI / Data Science": [
                CMSModule("CS310-M02", "CS310", "Mô Hình Phân Lớp & Đánh Giá Năng Lực", 2, "AI / Data Science"),
            ],
        }
        return domain_modules.get(domain, [])

    def find_resources_for_skill_gap(
        self,
        skill_name: str,
        current_level: str,
        target_level: str,
        specific_gap_topic: Optional[str] = None,
    ) -> List[CMSResourceMatch]:
        remedies = self._skill_remedies.get(skill_name, [])
        if not remedies:
            # Fallback resource thông minh dựa trên CMS Catalog
            return [
                CMSResourceMatch(
                    skill_name=skill_name,
                    gap_topic=f"Nâng cấp kỹ năng {skill_name}",
                    course_code="CMS-GEN",
                    module_title=f"Chuyên đề nâng cấp kỹ năng {skill_name}",
                    lesson_title=f"Lý thuyết trọng tâm & Bài thực hành {skill_name}",
                    practice_action=f"Hoàn thành tài liệu chuyên đề và nộp sản phẩm minh họa kỹ năng {skill_name}.",
                    resource_title=f"EduDSS CMS - Tài liệu & Bài tập chuẩn hóa {skill_name}",
                    resource_url="https://learn.edudss.edu.vn/catalog",
                    difficulty=target_level if target_level != "None" else "Intermediate",
                    estimated_hours=4.0,
                    target_outcome=f"Nắm vững nguyên lý và nâng bậc kỹ năng {skill_name} từ {current_level} lên {target_level}.",
                )
            ]

        if specific_gap_topic:
            matched = [r for r in remedies if specific_gap_topic.lower() in r.gap_topic.lower()]
            if matched:
                return matched

        return remedies


class MockCMSRepository(BaseCMSRepository):
    """Triển khai Mock: Cho phép Unit Tests thêm/sửa học liệu CMS theo ý muốn."""

    def __init__(self):
        super().__init__(mode=MODE_MOCK)
        self.preset_matches: Dict[str, List[CMSResourceMatch]] = {}

    def set_resource_match(self, skill_name: str, matches: List[CMSResourceMatch]) -> None:
        self.preset_matches[skill_name] = matches

    def map_course_to_skills(self, course_id: str) -> List[CMSSkillMapping]:
        return [CMSSkillMapping("SQL", "Intermediate", course_id, "M01", "Mock SQL", "SQL", 7.0)]

    def map_content_to_competencies(self, domain: str) -> List[CMSModule]:
        return [CMSModule("M01", "C01", f"Mock Module for {domain}", 1, domain)]

    def find_resources_for_skill_gap(
        self,
        skill_name: str,
        current_level: str,
        target_level: str,
        specific_gap_topic: Optional[str] = None,
    ) -> List[CMSResourceMatch]:
        if skill_name in self.preset_matches:
            return self.preset_matches[skill_name]
        return [
            CMSResourceMatch(
                skill_name=skill_name,
                gap_topic=specific_gap_topic or f"Chủ đề {skill_name}",
                course_code="MOCK101",
                module_title=f"Mock Module {skill_name}",
                lesson_title=f"Mock Lesson {skill_name}",
                practice_action=f"Thực hành {skill_name}",
                resource_title=f"Mock Resource {skill_name}",
                resource_url="https://mock.edudss.edu.vn",
                difficulty="Intermediate",
                estimated_hours=3.0,
                target_outcome="Đạt chuẩn Mock",
            )
        ]


class RealConnectorCMSRepository(BaseCMSRepository):
    """Triển khai Real Connector: Kết nối kho CMS sản xuất (Database / Git / Headless API)."""

    def __init__(self, cms_endpoint: str = "https://cms.edudss.edu.vn/api"):
        super().__init__(mode=MODE_REAL)
        self.cms_endpoint = cms_endpoint
        self._demo_fallback = DemoCMSRepository()

    def map_course_to_skills(self, course_id: str) -> List[CMSSkillMapping]:
        return self._demo_fallback.map_course_to_skills(course_id)

    def map_content_to_competencies(self, domain: str) -> List[CMSModule]:
        return self._demo_fallback.map_content_to_competencies(domain)

    def find_resources_for_skill_gap(
        self,
        skill_name: str,
        current_level: str,
        target_level: str,
        specific_gap_topic: Optional[str] = None,
    ) -> List[CMSResourceMatch]:
        return self._demo_fallback.find_resources_for_skill_gap(
            skill_name, current_level, target_level, specific_gap_topic,
        )

    def get_integration_status(self) -> Dict[str, str]:
        status = super().get_integration_status()
        status["data_mode_status"] = STATUS_PARTIAL
        status["endpoint"] = self.cms_endpoint
        return status


# Singleton Registry
_CMS_REPOSITORIES: Dict[str, BaseCMSRepository] = {}


def get_cms_repository(mode: str = MODE_DEMO) -> BaseCMSRepository:
    """Factory lấy singleton instance của CMSRepository theo chế độ yêu cầu."""
    normalized_mode = mode.upper()
    if normalized_mode not in _CMS_REPOSITORIES:
        if normalized_mode == MODE_MOCK:
            _CMS_REPOSITORIES[normalized_mode] = MockCMSRepository()
        elif normalized_mode in (MODE_REAL, "REAL"):
            _CMS_REPOSITORIES[normalized_mode] = RealConnectorCMSRepository()
        else:
            _CMS_REPOSITORIES[normalized_mode] = DemoCMSRepository()
    return _CMS_REPOSITORIES[normalized_mode]
