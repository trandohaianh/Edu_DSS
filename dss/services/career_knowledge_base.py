"""Career Knowledge Base — Cấu trúc dữ liệu nghề nghiệp chuẩn hoá cho Career
Decision Support System.

Bao gồm 12 vai trò chuẩn hoá theo đặc tả yêu cầu:
1. Data Analyst
2. Data Engineer
3. Data Scientist
4. Machine Learning Engineer
5. Business Analyst
6. Backend Developer
7. Frontend Developer
8. QA / Tester
9. DevOps / Cloud Engineer
10. Database Administrator
11. AI Engineer
12. System Analyst

Mỗi vai trò có đầy đủ:
- required_skills (trọng số 0.1 - 1.0)
- preferred_skills (trọng số 0.1 - 1.0)
- academic_domains (trọng số 0.1 - 1.0, khớp SUBJECT_TO_COMPETENCY_DOMAIN)
- interest_axes (trọng số theo 7 trục mini-assessment)
- work_style (kỳ vọng 1-5 theo 7 trục phong cách làm việc)
- typical_tasks (nhiệm vụ thực tế)
- minimum_english (yêu cầu chuẩn tiếng Anh tối thiểu)
- experience_expectation (số dự án/kinh nghiệm kỳ vọng)
- preferred_hours (office_hours | shift_ok)
- remote_friendly (remote | on_site | flexible)
- adjacent_roles (vai trò liền kề)
- learning_resources (tài nguyên học uy tín có URL thực tế & gắn skill)
- alternative_path_notes (giải thích con đường thay thế và dài hạn)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LearningResource:
    title: str
    url: str
    for_skill: Optional[str] = None  # Gắn với skill cụ thể để Roadmap trích đúng nguồn


@dataclass
class CareerRole:
    role_id: str
    role_name: str
    description: str
    required_skills: Dict[str, float] = field(default_factory=dict)  # skill_name -> weight 0-1
    preferred_skills: Dict[str, float] = field(default_factory=dict)  # skill_name -> weight 0-1
    academic_domains: Dict[str, float] = field(default_factory=dict)  # domain -> weight 0-1
    interest_axes: Dict[str, float] = field(default_factory=dict)  # 7 trục interest -> weight 0-1
    work_style: Dict[str, int] = field(default_factory=dict)  # 7 trục work_style -> kỳ vọng 1-5
    typical_tasks: List[str] = field(default_factory=list)
    minimum_english: str = "Intermediate"  # Beginner | Intermediate | Advanced | Fluent
    experience_expectation: int = 1  # Số dự án kỳ vọng ở mức Fresher
    preferred_hours: str = "office_hours"  # office_hours | shift_ok
    remote_friendly: str = "flexible"  # remote | on_site | flexible
    adjacent_roles: List[str] = field(default_factory=list)  # role_id liền kề
    learning_resources: List[LearningResource] = field(default_factory=list)
    secondary_path_explanation: str = ""  # Giải thích vì sao nộp kèm được
    long_term_path_explanation: str = ""  # Giải thích định hướng dài hạn

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _res(title: str, url: str, for_skill: Optional[str] = None) -> LearningResource:
    return LearningResource(title=title, url=url, for_skill=for_skill)


CAREER_ROLES: Dict[str, CareerRole] = {}


def _register(role: CareerRole) -> None:
    CAREER_ROLES[role.role_id] = role


# ============================================================================
# 1. Data Analyst
# ============================================================================
_register(
    CareerRole(
        role_id="data_analyst",
        role_name="Data Analyst",
        description="Khai thác, làm sạch và trực quan hoá dữ liệu để tìm kiếm insight và hỗ trợ ra quyết định kinh doanh.",
        required_skills={"SQL": 1.0, "Excel": 0.8, "Statistics": 0.8, "Power BI": 0.7},
        preferred_skills={"Python": 0.5, "KPI Analysis": 0.6, "Communication": 0.5, "Problem Solving": 0.5},
        academic_domains={
            "Data Analysis / Quantitative Skills": 1.0,
            "SQL / Data Engineering": 0.7,
            "Data Visualization / BI": 0.9,
        },
        interest_axes={"data": 1.0, "business_problem": 0.8, "client_communication": 0.5},
        work_style={
            "independence": 3,
            "orientation": 3,
            "task_type": 2,
            "environment": 2,
            "workplace": 1,
            "hours": 1,
            "career_track": 2,
        },
        typical_tasks=[
            "Viết truy vấn SQL phức tạp (JOIN, Window Functions, CTE) để trích xuất dữ liệu",
            "Xây dựng và bảo trì Dashboard trên Power BI / Tableau để theo dõi KPI",
            "Phân tích dữ liệu định kỳ và thuyết trình báo cáo insight cho các phòng ban",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["business_analyst", "data_engineer"],
        secondary_path_explanation="Có thể ứng tuyển thêm Business Analyst vì cùng sử dụng kỹ năng phân tích số liệu, hiểu quy trình kinh doanh và giao tiếp báo cáo.",
        long_term_path_explanation="Phát triển dài hạn lên Data Engineer (nếu đào sâu kỹ thuật dữ liệu lớn) hoặc Senior BI / Data Analytics Lead (nếu phát triển định hướng kinh doanh).",
        learning_resources=[
            _res("Kaggle - SQL & Data Analysis Micro-Courses", "https://www.kaggle.com/learn", for_skill="SQL"),
            _res(
                "Coursera - Google Data Analytics Professional Certificate",
                "https://www.coursera.org/professional-certificates/google-data-analytics",
                for_skill="Power BI",
            ),
            _res(
                "Khan Academy - Thống kê & Xác suất ứng dụng",
                "https://www.khanacademy.org/math/statistics-probability",
                for_skill="Statistics",
            ),
            _res(
                "Microsoft Learn - Power BI Data Analyst",
                "https://learn.microsoft.com/en-us/training/paths/data-analytics-microsoft/",
                for_skill="Power BI",
            ),
        ],
    )
)

# ============================================================================
# 2. Data Engineer
# ============================================================================
_register(
    CareerRole(
        role_id="data_engineer",
        role_name="Data Engineer",
        description="Thiết kế, xây dựng và vận hành hệ thống đường ống dẫn dữ liệu (ETL/ELT), kho dữ liệu và hạ tầng dữ liệu lớn.",
        required_skills={"SQL": 1.0, "Database": 1.0, "Python": 0.8, "Cloud": 0.7},
        preferred_skills={"Java": 0.5, "Statistics": 0.3, "Documentation": 0.4, "Problem Solving": 0.6},
        academic_domains={
            "SQL / Data Engineering": 1.0,
            "Software / Web Development": 0.7,
            "Data Analysis / Quantitative Skills": 0.4,
        },
        interest_axes={"data": 0.9, "system_building": 0.9, "system_operations": 0.7},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 3,
            "workplace": 1,
            "hours": 1,
            "career_track": 1,
        },
        typical_tasks=[
            "Thiết kế cấu trúc lược đồ Data Warehouse / Data Lakehouse",
            "Xây dựng pipeline ETL tự động xử lý và làm sạch luồng dữ liệu",
            "Tối ưu hoá hiệu năng truy vấn và giám sát tài nguyên xử lý dữ liệu lớn",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["data_analyst", "devops_cloud_engineer", "database_administrator"],
        secondary_path_explanation="Có thể ứng tuyển thêm Database Administrator hoặc Backend Developer nhờ nền tảng vững chắc về SQL, thiết kế CSDL và Python/Java.",
        long_term_path_explanation="Phát triển dài hạn lên Big Data Architect hoặc Cloud Data Platform Lead phụ trách toàn bộ hạ tầng dữ liệu doanh nghiệp.",
        learning_resources=[
            _res(
                "Designing Data-Intensive Applications (Martin Kleppmann)",
                "https://dataintensive.net/",
                for_skill="Database",
            ),
            _res(
                "Data Engineering Zoomcamp",
                "https://github.com/DataTalksClub/data-engineering-zoomcamp",
                for_skill="Python",
            ),
            _res("Docker & Kubernetes Docs", "https://docs.docker.com/", for_skill="Cloud"),
        ],
    )
)

# ============================================================================
# 3. Data Scientist
# ============================================================================
_register(
    CareerRole(
        role_id="data_scientist",
        role_name="Data Scientist",
        description="Nghiên cứu, thử nghiệm và áp dụng các mô hình thống kê học và Machine Learning để giải quyết các bài toán dự đoán phức tạp.",
        required_skills={"Python": 1.0, "Machine Learning": 1.0, "Statistics": 1.0},
        preferred_skills={"SQL": 0.6, "Cloud": 0.4, "Presentation": 0.5, "Problem Solving": 0.6},
        academic_domains={
            "AI / Data Science": 1.0,
            "Data Analysis / Quantitative Skills": 0.9,
            "Data Visualization / BI": 0.5,
        },
        interest_axes={"data": 1.0, "ai_research": 1.0, "business_problem": 0.6},
        work_style={
            "independence": 2,
            "orientation": 2,
            "task_type": 1,
            "environment": 3,
            "workplace": 1,
            "hours": 1,
            "career_track": 1,
        },
        typical_tasks=[
            "Thu thập, khám phá dữ liệu (EDA) và kỹ thuật hoá đặc trưng (Feature Engineering)",
            "Thử nghiệm huấn luyện, tinh chỉnh siêu tham số và đánh giá các mô hình ML/DL",
            "Trình bày kết quả nghiên cứu và phương án triển khai mô hình cho ban lãnh đạo",
        ],
        minimum_english="Advanced",
        experience_expectation=2,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["ml_engineer", "data_analyst"],
        secondary_path_explanation="Có thể ứng tuyển vị trí Data Analyst nhờ nền tảng toán thống kê và xử lý dữ liệu sâu, hoặc Junior ML Engineer.",
        long_term_path_explanation="Phát triển dài hạn thành Principal Data Scientist, AI Research Scientist hoặc Head of Data Science.",
        learning_resources=[
            _res(
                "Coursera - Machine Learning Specialization (Andrew Ng)",
                "https://www.coursera.org/specializations/machine-learning-introduction",
                for_skill="Machine Learning",
            ),
            _res(
                "Sách: Hands-On Machine Learning with Scikit-Learn & TensorFlow",
                "https://www.oreilly.com/library/view/hands-on-machine-learning/9781098125967/",
                for_skill="Machine Learning",
            ),
            _res(
                "Khan Academy - Multivariate Calculus & Linear Algebra",
                "https://www.khanacademy.org/math",
                for_skill="Statistics",
            ),
        ],
    )
)

# ============================================================================
# 4. Machine Learning Engineer
# ============================================================================
_register(
    CareerRole(
        role_id="ml_engineer",
        role_name="Machine Learning Engineer",
        description="Đóng gói, tối ưu hoá và đưa các mô hình AI/ML vào hệ thống production vận hành thực tế ở quy mô lớn.",
        required_skills={"Python": 1.0, "Machine Learning": 1.0, "Cloud": 0.7, "Database": 0.6},
        preferred_skills={"SQL": 0.5, "C++": 0.4, "Documentation": 0.4, "Self-learning": 0.6},
        academic_domains={
            "AI / Data Science": 1.0,
            "Software / Web Development": 0.8,
            "SQL / Data Engineering": 0.5,
        },
        interest_axes={"ai_research": 0.9, "system_building": 0.9, "system_operations": 0.6},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 4,
            "workplace": 1,
            "hours": 2,
            "career_track": 1,
        },
        typical_tasks=[
            "Xây dựng pipeline MLOps: tự động hoá quy trình huấn luyện, kiểm thử và deploy model",
            "Tối ưu tốc độ suy luận (latency) và tài nguyên tính toán (GPU/CPU/RAM)",
            "Giám sát mô hình sau triển khai: phát hiện data drift và concept drift",
        ],
        minimum_english="Advanced",
        experience_expectation=2,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["data_scientist", "ai_engineer", "devops_cloud_engineer"],
        secondary_path_explanation="Có thể ứng tuyển Backend Developer hoặc Data Scientist nhờ sự kết hợp giữa kỹ năng lập trình hệ thống và thuật toán ML.",
        long_term_path_explanation="Phát triển thành MLOps Lead, AI Platform Architect hoặc Giám đốc Kỹ thuật AI (VP of AI Engineering).",
        learning_resources=[
            _res(
                "fast.ai - Practical Deep Learning for Coders", "https://course.fast.ai/", for_skill="Machine Learning"
            ),
            _res("Full Stack Deep Learning", "https://fullstackdeeplearning.com/", for_skill="Cloud"),
            _res(
                "MLOps Specialization (DeepLearning.AI)",
                "https://www.coursera.org/specializations/machine-learning-engineering-for-production-mlops",
                for_skill="Cloud",
            ),
        ],
    )
)

# ============================================================================
# 5. Business Analyst
# ============================================================================
_register(
    CareerRole(
        role_id="business_analyst",
        role_name="Business Analyst",
        description="Cầu nối giữa các phòng ban nghiệp vụ và đội ngũ phát triển kỹ thuật; phân tích yêu cầu và thiết kế giải pháp phần mềm.",
        required_skills={
            "Requirement Analysis": 1.0,
            "Documentation": 0.9,
            "Communication": 0.9,
            "Process Analysis": 0.8,
        },
        preferred_skills={"SQL": 0.5, "Excel": 0.6, "KPI Analysis": 0.6, "Presentation": 0.6},
        academic_domains={
            "Business Analysis": 1.0,
            "Data Analysis / Quantitative Skills": 0.5,
            "Software / Web Development": 0.4,
        },
        interest_axes={"business_problem": 1.0, "client_communication": 0.9, "data": 0.5},
        work_style={
            "independence": 4,
            "orientation": 4,
            "task_type": 4,
            "environment": 3,
            "workplace": 1,
            "hours": 1,
            "career_track": 2,
        },
        typical_tasks=[
            "Khảo sát, phỏng vấn các bên liên quan (stakeholders) để thu thập và làm rõ yêu cầu",
            "Viết tài liệu đặc tả yêu cầu người dùng (BRD, SRS, User Stories, Acceptance Criteria)",
            "Vẽ sơ đồ quy trình nghiệp vụ (BPMN), sơ đồ luồng dữ liệu (DFD) và wireframe mẫu",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["system_analyst", "data_analyst", "qa_tester"],
        secondary_path_explanation="Có thể ứng tuyển System Analyst (nếu có thêm hiểu biết kiến trúc hệ thống) hoặc QA/Tester nhờ khả năng phân tích ca kiểm thử kỹ lưỡng.",
        long_term_path_explanation="Phát triển lên Product Owner, Product Manager (quản lý sản phẩm) hoặc Giám đốc Nghiệp vụ / Tư vấn Chuyển đổi số.",
        learning_resources=[
            _res(
                "IIBA - Hướng dẫn BABOK chính thống",
                "https://www.iiba.org/career-resources/a-guide-to-the-business-analysis-body-of-knowledge-babok-guide/",
                for_skill="Requirement Analysis",
            ),
            _res(
                "Atlassian Agile Coach - Hướng dẫn User Story & Scrum",
                "https://www.atlassian.com/agile",
                for_skill="Documentation",
            ),
            _res(
                "Coursera - Google Project Management Certificate",
                "https://www.coursera.org/professional-certificates/google-project-management",
                for_skill="Process Analysis",
            ),
        ],
    )
)

# ============================================================================
# 6. Backend Developer
# ============================================================================
_register(
    CareerRole(
        role_id="backend_developer",
        role_name="Backend Developer",
        description="Xây dựng và tối ưu hoá hệ thống xử lý phía máy chủ (Server), cơ sở dữ liệu và các giao diện lập trình ứng dụng (API).",
        required_skills={"Java": 0.8, "Python": 0.8, "Database": 0.9, "SQL": 0.8},
        preferred_skills={"Cloud": 0.5, "Problem Solving": 0.7, "C++": 0.4, "Teamwork": 0.5},
        academic_domains={
            "Software / Web Development": 1.0,
            "SQL / Data Engineering": 0.7,
        },
        interest_axes={"system_building": 1.0, "system_operations": 0.6, "data": 0.4},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 3,
            "workplace": 1,
            "hours": 1,
            "career_track": 1,
        },
        typical_tasks=[
            "Thiết kế và xây dựng các API dịch vụ (RESTful / gRPC / GraphQL)",
            "Thiết kế schema cơ sở dữ liệu và tối ưu hoá câu truy vấn dữ liệu",
            "Xử lý xác thực người dùng (Auth), caching (Redis) và bảo mật ứng dụng",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["frontend_developer", "devops_cloud_engineer", "data_engineer"],
        secondary_path_explanation="Có thể ứng tuyển Fullstack Developer (nếu học thêm chút Frontend) hoặc DevOps/Cloud Engineer nhờ hiểu biết sâu về máy chủ và mạng.",
        long_term_path_explanation="Phát triển lên Software Architect, Technical Lead hoặc Chief Technology Officer (CTO).",
        learning_resources=[
            _res(
                "freeCodeCamp - Backend Development & APIs",
                "https://www.freecodecamp.org/learn/back-end-development-and-apis/",
                for_skill="Python",
            ),
            _res("Fullstack Open (Helsinki University)", "https://fullstackopen.com/", for_skill="Database"),
            _res("Roadmap.sh - Backend Developer Guide", "https://roadmap.sh/backend", for_skill="Java"),
        ],
    )
)

# ============================================================================
# 7. Frontend Developer
# ============================================================================
_register(
    CareerRole(
        role_id="frontend_developer",
        role_name="Frontend Developer",
        description="Phát triển giao diện web tương tác người dùng, biến bản thiết kế UI/UX thành trải nghiệm web mượt mà, chuẩn SEO và tương thích đa thiết bị.",
        required_skills={"Problem Solving": 0.8, "Python": 0.4, "Documentation": 0.5},
        preferred_skills={"Teamwork": 0.6, "Communication": 0.5, "Self-learning": 0.6},
        academic_domains={
            "Software / Web Development": 1.0,
            "Data Visualization / BI": 0.4,
        },
        interest_axes={"ui_ux_design": 1.0, "system_building": 0.8},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 4,
            "workplace": 1,
            "hours": 1,
            "career_track": 1,
        },
        typical_tasks=[
            "Chuyển đổi thiết kế Figma / UI wireframes thành giao diện web responsive",
            "Kết nối API phía Backend và quản lý trạng thái ứng dụng (State Management)",
            "Tối ưu hoá hiệu năng tải trang, trải nghiệm người dùng và kiểm thử giao diện",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["backend_developer", "qa_tester"],
        secondary_path_explanation="Có thể phát triển thành Fullstack Developer bằng cách bổ sung kỹ năng Backend API.",
        long_term_path_explanation="Phát triển thành Frontend Architect hoặc Lead Frontend Engineer chuyên trách trải nghiệm ứng dụng quy mô lớn.",
        learning_resources=[
            _res("React.js - Official Documentation", "https://react.dev/learn", for_skill="Problem Solving"),
            _res(
                "freeCodeCamp - Responsive Web Design",
                "https://www.freecodecamp.org/learn/2022/responsive-web-design/",
                for_skill="Documentation",
            ),
            _res("MDN Web Docs - HTML, CSS & JavaScript", "https://developer.mozilla.org/", for_skill="Self-learning"),
        ],
    )
)

# ============================================================================
# 8. QA / Tester
# ============================================================================
_register(
    CareerRole(
        role_id="qa_tester",
        role_name="QA / Tester",
        description="Đảm bảo chất lượng phần mềm thông qua việc lập kế hoạch kiểm thử, viết test case, thực thi kiểm thử thủ công và kiểm thử tự động.",
        required_skills={"Problem Solving": 0.9, "Documentation": 0.8, "Requirement Analysis": 0.7},
        preferred_skills={"Python": 0.5, "SQL": 0.5, "Teamwork": 0.6, "Communication": 0.6},
        academic_domains={
            "Software / Web Development": 0.7,
            "Business Analysis": 0.6,
        },
        interest_axes={"system_building": 0.6, "business_problem": 0.6, "system_operations": 0.5},
        work_style={
            "independence": 3,
            "orientation": 3,
            "task_type": 2,
            "environment": 2,
            "workplace": 1,
            "hours": 1,
            "career_track": 1,
        },
        typical_tasks=[
            "Phân tích tài liệu yêu cầu để viết kịch bản kiểm thử (Test Cases / Test Suites)",
            "Thực thi kiểm thử chức năng, giao diện, bảo mật và hiệu năng (Manual & Automation Test)",
            "Ghi nhận, mô tả và theo dõi vòng đời của lỗi (Bug Tracking trên Jira)",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["business_analyst", "backend_developer", "system_analyst"],
        secondary_path_explanation="Có thể chuyển dịch sang Business Analyst nhờ hiểu rất sâu về nghiệp vụ phần mềm và các kịch bản sử dụng thực tế.",
        long_term_path_explanation="Phát triển thành QA Lead, Automation Test Architect hoặc Giám đốc Đảm bảo Chất lượng Phần mềm.",
        learning_resources=[
            _res("ISTQB - Chuẩn kiểm thử phần mềm quốc tế", "https://www.istqb.org/", for_skill="Documentation"),
            _res(
                "freeCodeCamp - Quality Assurance Certification",
                "https://www.freecodecamp.org/learn/quality-assurance/",
                for_skill="Problem Solving",
            ),
            _res("Selenium / Cypress Documentation", "https://docs.cypress.io/", for_skill="Python"),
        ],
    )
)

# ============================================================================
# 9. DevOps / Cloud Engineer
# ============================================================================
_register(
    CareerRole(
        role_id="devops_cloud_engineer",
        role_name="DevOps / Cloud Engineer",
        description="Xây dựng đường ống tự động hoá triển khai CI/CD, quản trị hạ tầng Cloud và đảm bảo tính sẵn sàng cao của hệ thống sản phẩm.",
        required_skills={"Cloud": 1.0, "Database": 0.6, "Python": 0.7},
        preferred_skills={"SQL": 0.4, "Documentation": 0.5, "Problem Solving": 0.7, "Teamwork": 0.5},
        academic_domains={
            "Software / Web Development": 0.6,
            "SQL / Data Engineering": 0.5,
        },
        interest_axes={"system_operations": 1.0, "system_building": 0.7},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 4,
            "workplace": 1,
            "hours": 3,
            "career_track": 1,
        },
        typical_tasks=[
            "Thiết lập và bảo trì pipeline tích hợp và triển khai liên tục (CI/CD với GitHub Actions, GitLab CI)",
            "Quản lý hạ tầng dưới dạng mã (IaC với Terraform, Ansible) trên AWS / Azure / GCP",
            "Giám sát log, cảnh báo sự cố (Prometheus, Grafana) và trực sự cố hệ thống khi có lỗi phát sinh",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="shift_ok",
        remote_friendly="flexible",
        adjacent_roles=["backend_developer", "data_engineer", "database_administrator"],
        secondary_path_explanation="Có thể ứng tuyển Backend Developer hoặc Sysadmin/Cloud Operator nhờ kỹ năng hệ điều hành và hạ tầng mạng.",
        long_term_path_explanation="Phát triển thành Cloud Solutions Architect, Site Reliability Engineering (SRE) Lead hoặc VP of Infrastructure.",
        learning_resources=[
            _res("Linux Journey - Học Linux từ căn bản đến nâng cao", "https://linuxjourney.com/", for_skill="Cloud"),
            _res("Docker & Kubernetes Guides", "https://kubernetes.io/docs/tutorials/", for_skill="Cloud"),
            _res("GitLab CI/CD Fundamentals", "https://docs.gitlab.com/ee/ci/", for_skill="Python"),
        ],
    )
)

# ============================================================================
# 10. Database Administrator
# ============================================================================
_register(
    CareerRole(
        role_id="database_administrator",
        role_name="Database Administrator",
        description="Quản trị, tối ưu hoá hiệu năng, bảo mật và thiết lập phương án sao lưu dự phòng cho toàn bộ hệ thống cơ sở dữ liệu doanh nghiệp.",
        required_skills={"Database": 1.0, "SQL": 1.0, "Cloud": 0.6},
        preferred_skills={"Python": 0.4, "Documentation": 0.5, "Problem Solving": 0.7},
        academic_domains={
            "SQL / Data Engineering": 1.0,
            "Software / Web Development": 0.4,
        },
        interest_axes={"data": 0.8, "system_operations": 0.9},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 1,
            "workplace": 1,
            "hours": 3,
            "career_track": 1,
        },
        typical_tasks=[
            "Giám sát hiệu năng CSDL, phân tích explain plan và tối ưu chỉ mục (Index tuning)",
            "Thiết lập chiến lược sao lưu định kỳ và kịch bản khôi phục sau thảm hoạ (Disaster Recovery)",
            "Phân quyền truy cập, bảo mật dữ liệu và áp dụng các bản vá an toàn thông tin",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="shift_ok",
        remote_friendly="on_site",
        adjacent_roles=["data_engineer", "devops_cloud_engineer"],
        secondary_path_explanation="Có thể nộp đồng thời vị trí Data Engineer nhờ sự am hiểu sâu sắc về lưu trữ dữ liệu và câu lệnh SQL tối ưu.",
        long_term_path_explanation="Phát triển lên Head of Database Infrastructure hoặc Enterprise Data Architect.",
        learning_resources=[
            _res("PostgreSQL Official Documentation", "https://www.postgresql.org/docs/", for_skill="Database"),
            _res("Use The Index, Luke! - SQL Indexing Guide", "https://use-the-index-luke.com/", for_skill="SQL"),
            _res("Oracle Database Administration Fundamentals", "https://education.oracle.com/", for_skill="Database"),
        ],
    )
)

# ============================================================================
# 11. AI Engineer
# ============================================================================
_register(
    CareerRole(
        role_id="ai_engineer",
        role_name="AI Engineer",
        description="Ứng dụng các mô hình AI tiên tiến (LLMs, Generative AI, RAG, Computer Vision) vào các ứng dụng phần mềm thực tế nhằm nâng cao năng suất.",
        required_skills={"Python": 1.0, "Machine Learning": 0.9, "Cloud": 0.6},
        preferred_skills={"SQL": 0.4, "Database": 0.5, "Self-learning": 0.8, "Documentation": 0.4},
        academic_domains={
            "AI / Data Science": 1.0,
            "Software / Web Development": 0.8,
            "Data Analysis / Quantitative Skills": 0.5,
        },
        interest_axes={"ai_research": 0.9, "system_building": 0.9, "data": 0.7},
        work_style={
            "independence": 2,
            "orientation": 1,
            "task_type": 1,
            "environment": 5,
            "workplace": 1,
            "hours": 2,
            "career_track": 1,
        },
        typical_tasks=[
            "Tích hợp các mô hình Generative AI qua API, xây dựng hệ thống Retrieval-Augmented Generation (RAG)",
            "Tinh chỉnh (Fine-tuning) và đánh giá độ chính xác của các mô hình nguồn mở",
            "Thiết kế luồng Prompt Engineering an toàn, chống prompt injection và tối ưu chi phí token",
        ],
        minimum_english="Advanced",
        experience_expectation=2,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["ml_engineer", "data_scientist", "backend_developer"],
        secondary_path_explanation="Có thể ứng tuyển Backend Developer hoặc ML Engineer nhờ kỹ năng tích hợp hệ thống kết hợp kiến thức mô hình toán.",
        long_term_path_explanation="Phát triển thành Chief AI Architect, Generative AI Practice Lead hoặc Nhà sáng lập công ty công nghệ AI.",
        learning_resources=[
            _res(
                "DeepLearning.AI - LangChain & LLM Application Development",
                "https://www.deeplearning.ai/short-courses/",
                for_skill="Machine Learning",
            ),
            _res("Hugging Face NLP Course", "https://huggingface.co/learn/nlp-course/", for_skill="Python"),
            _res("Pinecone Vector Database Guides", "https://www.pinecone.io/learn/", for_skill="Cloud"),
        ],
    )
)

# ============================================================================
# 12. System Analyst
# ============================================================================
_register(
    CareerRole(
        role_id="system_analyst",
        role_name="System Analyst",
        description="Phân tích và thiết kế cấu trúc hệ thống thông tin, làm việc chặt chẽ với cả nghiệp vụ và kỹ sư phần mềm để tối ưu hoá kiến trúc giải pháp.",
        required_skills={"Requirement Analysis": 0.9, "Documentation": 0.8, "Database": 0.6, "Problem Solving": 0.7},
        preferred_skills={"SQL": 0.5, "Communication": 0.6, "Process Analysis": 0.6, "Teamwork": 0.5},
        academic_domains={
            "Business Analysis": 0.8,
            "Software / Web Development": 0.7,
            "SQL / Data Engineering": 0.5,
        },
        interest_axes={"system_building": 0.8, "business_problem": 0.8, "data": 0.5},
        work_style={
            "independence": 3,
            "orientation": 2,
            "task_type": 2,
            "environment": 2,
            "workplace": 1,
            "hours": 1,
            "career_track": 2,
        },
        typical_tasks=[
            "Phân tích hệ thống hiện hữu và đề xuất phương án tái cấu trúc hoặc nâng cấp kỹ thuật",
            "Vẽ thiết kế kiến trúc hệ thống tổng thể, sơ đồ cơ sở dữ liệu và sơ đồ tương tác API",
            "Đảm bảo sự nhất quán kỹ thuật giữa thiết kế phần mềm và yêu cầu nghiệp vụ",
        ],
        minimum_english="Intermediate",
        experience_expectation=1,
        preferred_hours="office_hours",
        remote_friendly="flexible",
        adjacent_roles=["business_analyst", "backend_developer", "qa_tester"],
        secondary_path_explanation="Có thể nộp cùng Business Analyst hoặc Junior Solution Architect nhờ khả năng cân bằng giữa kỹ thuật và kinh doanh.",
        long_term_path_explanation="Phát triển thành Enterprise Architect, Solutions Architect hoặc Giám đốc Công nghệ Thông tin (CIO).",
        learning_resources=[
            _res(
                "TOGAF Enterprise Architecture Overview",
                "https://www.opengroup.org/togaf",
                for_skill="Requirement Analysis",
            ),
            _res(
                "System Design Primer (GitHub)",
                "https://github.com/donnemartin/system-design-primer",
                for_skill="Database",
            ),
            _res(
                "Martin Fowler - Microservices & Architecture Guides",
                "https://martinfowler.com/",
                for_skill="Problem Solving",
            ),
        ],
    )
)


def get_role(role_id: str) -> Optional[CareerRole]:
    return CAREER_ROLES.get(role_id)


def list_roles() -> List[CareerRole]:
    return list(CAREER_ROLES.values())
