"""Resource Catalog — Quản lý danh mục tài nguyên học tập đã được thẩm định.

Mục 16 Yêu cầu:
- AI chỉ được phép gợi ý tài nguyên (LMS material, sách, video giảng viên, bài tập)
  từ ResourceCatalog đã được kiểm chứng.
- TUYỆT ĐỐI không bịa đặt (hallucinate) URL hoặc nguồn học liệu ngoài danh mục.
- Thuộc tính bắt buộc:
  resource_id, title, type, provider, url, course, topic, level, language, duration,
  verified_at, reviewed_by, status
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ResourceItem:
    resource_id: str
    title: str
    type: str  # "lms_material" | "book_chapter" | "lecture_video" | "practice_quiz" | "external_video"
    provider: str  # "LMS_Internal" | "University_Library" | "Faculty_Media" | "Coursera_Approved"
    url: str
    course: str
    topic: str
    level: str  # "Beginner" | "Intermediate" | "Advanced"
    language: str  # "vi" | "en"
    duration: str  # e.g. "15 phút", "45 phút", "1 tuần"
    verified_at: str
    reviewed_by: str
    status: str  # "APPROVED" | "PENDING_REVIEW" | "REJECTED" | "ARCHIVED"
    is_demo: bool = False


class ResourceCatalog:
    """Kho lưu trữ và truy vấn tài nguyên học tập chuẩn hóa cho EduDSS."""

    def __init__(self):
        self._resources: Dict[str, ResourceItem] = {}
        self._seed_default_approved_catalog()

    def _seed_default_approved_catalog(self) -> None:
        """Khởi tạo danh mục tài nguyên chuẩn được phê duyệt ban đầu."""
        initial_resources = [
            ResourceItem(
                resource_id="res_math_calc_01",
                title="Giáo trình Giải tích 1 - Chương 2: Đạo hàm và Vi phân",
                type="lms_material",
                provider="LMS_Internal",
                url="https://lms.university.edu.vn/courses/math101/materials/calc1_chap2.pdf",
                course="Toán cao cấp 1",
                topic="Giải tích",
                level="Beginner",
                language="vi",
                duration="2 giờ tự học",
                verified_at="2026-01-15T08:00:00",
                reviewed_by="Khoa Toán - Tin",
                status="APPROVED",
            ),
            ResourceItem(
                resource_id="res_prog_python_01",
                title="Chuỗi bài tập thực hành Python từ cơ bản đến nâng cao",
                type="practice_quiz",
                provider="LMS_Internal",
                url="https://lms.university.edu.vn/courses/cs101/assignments/lab01-python",
                course="Nhập môn lập trình",
                topic="Python Căn bản",
                level="Beginner",
                language="vi",
                duration="3 giờ thực hành",
                verified_at="2026-01-15T08:00:00",
                reviewed_by="Bộ môn Công nghệ Phần mềm",
                status="APPROVED",
            ),
            ResourceItem(
                resource_id="res_time_pomodoro_01",
                title="Kỹ thuật Pomodoro và Quản lý thời gian học đại học",
                type="lms_material",
                provider="Faculty_Media",
                url="https://lms.university.edu.vn/skills/pomodoro_guide.pdf",
                course="Kỹ năng mềm",
                topic="Quản lý thời gian",
                level="Beginner",
                language="vi",
                duration="30 phút đọc",
                verified_at="2026-02-01T09:00:00",
                reviewed_by="Phòng CTSV",
                status="APPROVED",
            ),
            ResourceItem(
                resource_id="res_db_sql_01",
                title="Hệ cơ sở dữ liệu - Bài giảng Chuẩn hóa CSDL và Truy vấn SQL",
                type="lecture_video",
                provider="Faculty_Media",
                url="https://lms.university.edu.vn/courses/db201/videos/lecture05_sql.mp4",
                course="Cơ sở dữ liệu",
                topic="SQL và Chuẩn hóa",
                level="Intermediate",
                language="vi",
                duration="45 phút",
                verified_at="2026-02-10T10:00:00",
                reviewed_by="Khoa CNTT",
                status="APPROVED",
            ),
            ResourceItem(
                resource_id="res_ml_eval_01",
                title="Đánh giá mô hình học máy: Phân biệt Overfitting và Chọn Metric",
                type="lms_material",
                provider="University_Library",
                url="https://lms.university.edu.vn/courses/ml301/readings/ml_evaluation.pdf",
                course="Machine Learning cơ bản",
                topic="Đánh giá mô hình",
                level="Intermediate",
                language="vi",
                duration="1 giờ",
                verified_at="2026-02-15T14:00:00",
                reviewed_by="Viện Trí tuệ Nhân tạo",
                status="APPROVED",
            ),
        ]
        for res in initial_resources:
            res.is_demo = True
            self._resources[res.resource_id] = res

    def get_resource(self, resource_id: str) -> Optional[ResourceItem]:
        return self._resources.get(resource_id)

    def list_approved_resources(
        self,
        course: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Chỉ trả về các tài nguyên có status=='APPROVED'."""
        results = []
        for res in self._resources.values():
            if res.status != "APPROVED":
                continue
            if course and course.lower() not in res.course.lower():
                continue
            if topic and topic.lower() not in res.topic.lower():
                continue
            results.append(asdict(res))
        return results

    def add_resource(self, resource: ResourceItem) -> None:
        self._resources[resource.resource_id] = resource

    def verify_resource_urls(self, text: str) -> bool:
        """Kiểm tra xem văn bản có chứa URL lạ không nằm trong Catalog không."""
        import re

        urls = re.findall(r"https?://[^\s)\]\"'>]+", text)
        allowed_urls = {res.url for res in self._resources.values() if res.status == "APPROVED"}
        for u in urls:
            if u not in allowed_urls:
                return False
        return True


# Singleton catalog instance
resource_catalog = ResourceCatalog()
