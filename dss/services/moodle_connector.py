"""Kết nối Moodle thật qua Moodle Web Services (REST, JSON).

Cấu hình phía trường (quản trị Moodle):
1. Site administration → Advanced features → bật *Web services*; Plugins → Web services →
   Manage protocols → bật *REST*.
2. Tạo *External service* (VD "EduDSS"), thêm các hàm trong ``REQUIRED_FUNCTIONS``.
3. Tạo user dịch vụ có quyền ``webservice/rest:use``, ``moodle/grade:viewall``,
   ``moodle/course:viewparticipants``, ``report/completion:view``; cấp token cho service đó.
4. Đặt biến môi trường cho EduDSS: ``EDUDSS_MOODLE_URL`` (https://lms.truong.edu.vn) và
   ``EDUDSS_MOODLE_TOKEN``. Token chỉ gửi trong thân POST, không bao giờ nằm trong URL/log.

Ánh xạ sinh viên: mã sinh viên EduDSS khớp trường ``idnumber`` của user Moodle (khuyến nghị),
nếu trống thì khớp ``username``. Điểm quy về thang 10 theo ``grademin``/``grademax`` của từng mục.

Kiểm thử: ``tests/fixtures/fake_moodle.py`` là máy chủ giả lập trả đúng định dạng JSON của Moodle 4.x
(kể cả lỗi ``webservice_access_exception``), chạy trong CI. Chưa kiểm thử với một Moodle thật của
trường; ``check_connection()`` là bước đầu tiên khi triển khai cho khách hàng.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from dss.services.lms_connector import (
    STATUS_IMPLEMENTED,
    BaseLMSRepository,
    LMSAssessmentRecord,
    LMSEnrollment,
    LMSStudentLearningSummary,
)

MODE_MOODLE = "MOODLE"
REST_PATH = "/webservice/rest/server.php"
REQUIRED_FUNCTIONS = (
    "core_webservice_get_site_info",
    "core_user_get_users_by_field",
    "core_enrol_get_users_courses",
    "core_enrol_get_enrolled_users",
    "gradereport_user_get_grade_items",
    "core_completion_get_activities_completion_status",
    "core_course_get_courses_by_field",
)
STRONG_AT, WEAK_BELOW = 8.0, 5.0


class MoodleError(RuntimeError):
    def __init__(self, message: str, errorcode: str = "", exception: str = ""):
        super().__init__(message)
        self.errorcode, self.exception = errorcode, exception


@dataclass
class MoodleClient:
    base_url: str
    token: str
    timeout_s: float = 15.0
    retries: int = 2
    allow_insecure: bool = False          # chỉ cho máy chủ giả lập localhost trong test

    def __post_init__(self):
        parsed = urlparse(self.base_url)
        local = parsed.hostname in ("127.0.0.1", "localhost")
        if parsed.scheme != "https" and not (self.allow_insecure and local):
            raise ValueError("Moodle URL phải là https://")
        if not self.token:
            raise ValueError("thiếu token Moodle")
        self.base_url = self.base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "MoodleClient":
        return cls(os.environ.get("EDUDSS_MOODLE_URL", ""), os.environ.get("EDUDSS_MOODLE_TOKEN", ""))

    def call(self, function: str, **params: Any) -> Any:
        import requests

        data = {"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json"}
        data.update(_flatten(params))
        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                # Không theo chuyển hướng: URL đã được kiểm (https, máy chủ công khai); 30x có thể vòng vào mạng nội bộ.
                resp = requests.post(self.base_url + REST_PATH, data=data, timeout=self.timeout_s, allow_redirects=False)
                if resp.status_code >= 500:
                    raise MoodleError(f"Moodle HTTP {resp.status_code}", "http_error")
                body = resp.json()
            except (requests.RequestException, ValueError, MoodleError) as exc:
                last = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise MoodleError(f"Không gọi được Moodle ({function}): {type(exc).__name__}", "unreachable") from exc
            if isinstance(body, dict) and "exception" in body:
                # Lỗi nghiệp vụ (token sai, thiếu quyền...): không thử lại.
                raise MoodleError(body.get("message", "Moodle error"), body.get("errorcode", ""), body.get("exception", ""))
            return body
        raise MoodleError(str(last), "unreachable")  # pragma: no cover

    # ---------------------------------------------------------------- API mức cao
    def site_info(self) -> Dict[str, Any]:
        return self.call("core_webservice_get_site_info")

    def check_connection(self) -> Dict[str, Any]:
        """Kiểm tra token + các hàm cần thiết đã được thêm vào external service chưa."""
        info = self.site_info()
        available = {f.get("name") for f in info.get("functions", [])}
        missing = [f for f in REQUIRED_FUNCTIONS if f not in available]
        return {"ok": not missing, "site": info.get("sitename"), "release": info.get("release"),
                "service_user": info.get("username"), "missing_functions": missing}

    def find_user(self, student_id: str) -> Optional[Dict[str, Any]]:
        for field in ("idnumber", "username"):
            users = self.call("core_user_get_users_by_field", field=field, values=[student_id])
            if users:
                return users[0]
        return None

    def user_courses(self, user_id: int) -> List[Dict[str, Any]]:
        return self.call("core_enrol_get_users_courses", userid=user_id)

    def enrolled_users(self, course_id: int) -> List[Dict[str, Any]]:
        return self.call("core_enrol_get_enrolled_users", courseid=course_id)

    def grade_items(self, course_id: int, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"courseid": course_id}
        if user_id is not None:
            params["userid"] = user_id
        return self.call("gradereport_user_get_grade_items", **params).get("usergrades", [])

    def completion(self, course_id: int, user_id: int) -> List[Dict[str, Any]]:
        return self.call("core_completion_get_activities_completion_status",
                         courseid=course_id, userid=user_id).get("statuses", [])


def _flatten(params: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Moodle REST nhận mảng/dict dạng values[0]=..., criteria[0][key]=..."""
    out: Dict[str, Any] = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten(value, name))
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    out.update(_flatten(item, f"{name}[{i}]"))
                else:
                    out[f"{name}[{i}]"] = item
        elif isinstance(value, bool):
            out[name] = int(value)
        elif value is not None:
            out[name] = value
    return out


def to_ten(raw: Any, gmin: Any, gmax: Any) -> Optional[float]:
    try:
        raw, gmin, gmax = float(raw), float(gmin or 0), float(gmax)
    except (TypeError, ValueError):
        return None
    if gmax <= gmin:
        return None
    return round(max(0.0, min(10.0, 10.0 * (raw - gmin) / (gmax - gmin))), 2)


def _assessment_type(item: Dict[str, Any]) -> str:
    name = (item.get("itemname") or "").lower()
    if "giữa kỳ" in name or "midterm" in name:
        return "midterm"
    if "cuối kỳ" in name or "final" in name:
        return "final"
    return {"quiz": "quiz", "assign": "assignment"}.get(item.get("itemmodule") or "", "assignment")


def _iso(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


class MoodleLMSRepository(BaseLMSRepository):
    """Nguồn dữ liệu học tập lấy trực tiếp từ Moodle của trường (chỉ đọc)."""

    def __init__(self, client: Optional[MoodleClient] = None):
        super().__init__(mode=MODE_MOODLE)
        self.client = client or MoodleClient.from_env()

    def course_snapshot(self, user_id: int, course: Dict[str, Any]) -> tuple[Optional[float], List[LMSAssessmentRecord], LMSEnrollment]:
        cid = int(course["id"])
        grades = self.client.grade_items(cid, user_id)
        total, records = None, []
        for usergrade in grades:
            for item in usergrade.get("gradeitems", []):
                score = to_ten(item.get("graderaw"), item.get("grademin"), item.get("grademax"))
                if item.get("itemtype") == "course":
                    total = score
                elif item.get("itemtype") == "mod" and score is not None:
                    records.append(LMSAssessmentRecord(
                        assessment_id=f"moodle-{cid}-{item.get('id')}", course_id=str(course.get("shortname") or cid),
                        title=item.get("itemname") or "", assessment_type=_assessment_type(item),
                        topic=item.get("itemname") or "", score=score, max_score=10.0,
                        weight=float(item.get("weightraw") or 1.0), passed=score >= WEAK_BELOW,
                        submitted_at=_iso(item.get("gradedatesubmitted") or item.get("gradedategraded"))))
        statuses = self.client.completion(cid, user_id)
        tracked = [s for s in statuses if s.get("tracking", 1) != 0]
        done = sum(1 for s in tracked if int(s.get("state", 0)) in (1, 2))
        progress = round(100.0 * done / len(tracked), 1) if tracked else float(course.get("progress") or 0.0)
        enrollment = LMSEnrollment(enrollment_id=f"moodle-{cid}-{user_id}", course_id=str(course.get("shortname") or cid),
                                   course_name=course.get("fullname") or "", semester=str(course.get("startdate") or ""),
                                   progress_percent=progress, attendance_rate=0.0,
                                   status="completed" if course.get("completed") else "enrolled")
        if total is None and records:
            total = round(sum(r.score * r.weight for r in records) / max(1e-9, sum(r.weight for r in records)), 2)
        return total, records, enrollment

    def get_student_learning_summary(self, student_id: str, raw_row: Optional[Dict[str, Any]] = None) -> LMSStudentLearningSummary:
        user = self.client.find_user(student_id)
        if not user:
            raise LookupError(f"Không tìm thấy sinh viên {student_id} trên Moodle (idnumber/username)")
        uid = int(user["id"])
        grades: Dict[str, float] = {}
        history: List[LMSAssessmentRecord] = []
        progress: List[float] = []
        for course in self.client.user_courses(uid):
            total, records, enrollment = self.course_snapshot(uid, course)
            name = course.get("fullname") or str(course["id"])
            if total is not None:
                grades[name] = total
            history += records
            progress.append(enrollment.progress_percent)
        gpa = round(sum(grades.values()) / len(grades), 2) if grades else 0.0
        history.sort(key=lambda r: r.submitted_at)
        trend = _trend([r.score for r in history])
        return LMSStudentLearningSummary(
            student_id=student_id, pseudonym=f"moodle:{uid}", gpa=gpa, course_grades=grades,
            strong_subjects=sorted(c for c, g in grades.items() if g >= STRONG_AT),
            weak_subjects=sorted(c for c, g in grades.items() if g < WEAK_BELOW),
            average_progress=round(sum(progress) / len(progress), 1) if progress else 0.0,
            average_attendance=0.0, total_learning_hours=0.0, performance_trend=trend,
            assessment_history=history,
            evidences=[f"Moodle: {len(grades)} khoá có điểm tổng, {len(history)} bài đánh giá"])

    def course_roster_grades(self, course_id: int) -> List[Dict[str, Any]]:
        """Một dòng/sinh viên cho cả khoá — dùng để nạp vào kho dữ liệu và huấn luyện mô hình."""
        students = [u for u in self.client.enrolled_users(course_id)
                    if any(r.get("shortname") == "student" for r in u.get("roles", []))]
        by_user = {g["userid"]: g for g in self.client.grade_items(course_id)}
        rows = []
        for u in students:
            row: Dict[str, Any] = {"student_id": u.get("idnumber") or u.get("username"), "moodle_user_id": u["id"]}
            for item in by_user.get(u["id"], {}).get("gradeitems", []):
                score = to_ten(item.get("graderaw"), item.get("grademin"), item.get("grademax"))
                key = "course_total" if item.get("itemtype") == "course" else (item.get("itemname") or f"item_{item.get('id')}")
                row[key] = score
            rows.append(row)
        return rows

    def record_learning_action(self, student_id: str, course_id: str, topic: str, assessment_score: float,
                               max_score: float = 10.0, duration_minutes: int = 45, activity_title: str = "",
                               assessment_type: str = "quiz") -> LMSAssessmentRecord:
        # Moodle là nguồn điểm chính thức: EduDSS không ghi đè điểm lên Moodle.
        raise PermissionError("Nguồn Moodle chỉ đọc: điểm được nhập trên Moodle, EduDSS đồng bộ về.")

    def get_integration_status(self) -> Dict[str, str]:
        status = super().get_integration_status()
        status.update({"data_mode_status": STATUS_IMPLEMENTED, "connector": "Moodle Web Services REST",
                       "moodle_url": self.client.base_url})
        return status


def _trend(scores: Iterable[float]) -> str:
    scores = list(scores)
    if len(scores) < 4:
        return "Ổn định"
    half = len(scores) // 2
    delta = sum(scores[half:]) / (len(scores) - half) - sum(scores[:half]) / half
    return "Tăng tiến" if delta >= 0.5 else ("Cần lưu ý" if delta <= -0.5 else "Ổn định")
