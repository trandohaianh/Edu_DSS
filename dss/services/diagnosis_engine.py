"""Rule-based observations, with explicit missing evidence and no invented facts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from dss.services.learning_profile import StudentLearningProfile, observed_number, observed_mapping

CATEGORY_KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
CATEGORY_PREREQUISITE_GAP = "PREREQUISITE_GAP"
CATEGORY_LOW_PRACTICE = "LOW_PRACTICE"
CATEGORY_LOW_RETENTION = "LOW_RETENTION"
CATEGORY_SLOW_RESPONSE = "SLOW_RESPONSE"
CATEGORY_CARELESS_FAST_RESPONSE = "CARELESS_FAST_RESPONSE"
CATEGORY_LOW_ENGAGEMENT = "LOW_ENGAGEMENT"
CATEGORY_INCONSISTENT_STUDY = "INCONSISTENT_STUDY"
CATEGORY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
CATEGORY_MASTERY_ON_TRACK = "MASTERY_ON_TRACK"
CATEGORY_LABELS = {
    CATEGORY_KNOWLEDGE_GAP: "Thiếu hụt kiến thức",
    CATEGORY_PREREQUISITE_GAP: "Chưa vững kiến thức nền tảng",
    CATEGORY_LOW_PRACTICE: "Luyện tập chưa đủ",
    CATEGORY_LOW_RETENTION: "Khả năng ghi nhớ dài hạn thấp",
    CATEGORY_SLOW_RESPONSE: "Xử lý bài tập còn chậm",
    CATEGORY_CARELESS_FAST_RESPONSE: "Làm bài vội, thiếu cẩn trọng",
    CATEGORY_LOW_ENGAGEMENT: "Mức độ tham gia học tập thấp",
    CATEGORY_INCONSISTENT_STUDY: "Nhịp độ học tập chưa đều",
    CATEGORY_INSUFFICIENT_DATA: "Chưa đủ dữ liệu để xác định nguyên nhân",
    CATEGORY_MASTERY_ON_TRACK: "Tiến độ học tập ổn định",
}


def category_label(category: Optional[str]) -> str:
    return CATEGORY_LABELS.get(category, "Nhận định chung")


@dataclass
class HypothesisItem:
    category: str
    cause: str
    confidence: Optional[float]
    evidence: List[str]
    needs_confirmation: bool = True


@dataclass
class StructuredDiagnosis:
    issue: str
    evidence: List[str]
    hypotheses: List[HypothesisItem]
    missing_evidence: List[str]
    recommended_diagnostic: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DiagnosisEngine:
    def diagnose_student(self, profile: StudentLearningProfile) -> List[StructuredDiagnosis]:
        acad, question = profile.academic, profile.question_level
        behavior, trajectory = profile.behavioral, profile.trajectory
        quiz = observed_number(acad.quiz_average, maximum=10)
        assignment = observed_number(acad.assignment_average, maximum=10)
        exam = observed_number(acad.exam_score, maximum=10)
        accuracy = observed_number(question.accuracy_rate, maximum=1)
        response = observed_number(question.average_response_time_seconds)
        practice = observed_number(behavior.practice_frequency_per_week)
        active = observed_number(behavior.active_days_last_month, maximum=31, integer=True)
        retention = observed_number(trajectory.delayed_retention_rate, maximum=1)
        baseline = observed_number(trajectory.historical_baseline_score, maximum=10)
        core = {
            "Điểm quiz": quiz, "Điểm bài tập": assignment, "Điểm thi": exam,
            "Tỷ lệ trả lời đúng": accuracy, "Thời gian trả lời": response,
            "Tần suất luyện tập": practice, "Số ngày hoạt động": active,
            "Kết quả kiểm tra ghi nhớ": retention, "Đường cơ sở cá nhân": baseline,
        }
        missing = [label for label, value in core.items() if value is None]
        diagnoses: List[StructuredDiagnosis] = []

        def add(category, issue, evidence, cause, diagnostic, extra_missing=()):
            diagnoses.append(StructuredDiagnosis(
                issue=issue, evidence=evidence,
                hypotheses=[HypothesisItem(category, cause, None, list(evidence), True)],
                missing_evidence=list(dict.fromkeys([*missing, *extra_missing])),
                recommended_diagnostic=diagnostic,
            ))

        if practice is not None and assignment is not None and practice < 1.5 and assignment < 6.5:
            add(
                CATEGORY_LOW_PRACTICE,
                "Điểm bài tập thấp đi kèm tần suất luyện tập được ghi nhận thấp",
                [f"Luyện tập được ghi nhận: {practice:.1f} lần/tuần", f"Điểm bài tập: {assignment:.1f}/10"],
                "Cần kiểm tra thêm mối liên hệ giữa hoạt động luyện tập và kết quả; nhật ký chưa bao gồm việc tự học ngoài hệ thống.",
                "Giảng viên chọn bài thực hành ngắn theo chủ đề và đối chiếu nhật ký luyện tập.",
                ["Hoạt động tự học ngoài hệ thống"],
            )

        if accuracy is not None and accuracy < 0.6 and response is not None:
            if response < 20:
                add(
                    CATEGORY_CARELESS_FAST_RESPONSE,
                    "Tỷ lệ làm đúng thấp đi kèm thời gian trả lời ngắn",
                    [f"Tỷ lệ đúng: {accuracy:.1%}", f"Thời gian trung bình: {response:.1f} giây/câu"],
                    "Cần xem lại đáp án và độ khó câu hỏi; thời gian ngắn chưa đủ chứng minh sinh viên làm bài thiếu cẩn trọng.",
                    "Đối chiếu bước giải và cách đọc đề trên bài kiểm tra đã được giảng viên duyệt.",
                    ["Độ khó và thời gian chuẩn của câu hỏi"],
                )
            elif response > 90:
                add(
                    CATEGORY_SLOW_RESPONSE,
                    "Thời gian trả lời dài đi kèm tỷ lệ làm đúng thấp",
                    [f"Tỷ lệ đúng: {accuracy:.1%}", f"Thời gian trung bình: {response:.1f} giây/câu"],
                    "Cần kiểm tra cách giải và kiến thức liên quan trước khi xác định nguyên nhân mất nhiều thời gian.",
                    "Giảng viên dùng bài đánh giá chia nhỏ bước giải để kiểm tra chủ đề đang vướng.",
                    ["Độ khó và thời gian chuẩn của câu hỏi"],
                )

        weak_prereqs = {topic: value for topic, value in observed_mapping(acad.prerequisite_mastery, maximum=1).items() if value < 0.6}
        if weak_prereqs:
            add(
                CATEGORY_PREREQUISITE_GAP,
                "Một số kết quả đánh giá kiến thức nền tảng dưới ngưỡng rà soát",
                [f"Kiến thức nền tảng {topic}: {value:.1%}" for topic, value in sorted(weak_prereqs.items())],
                "Kết quả gợi ý cần ôn kiến thức nền tảng; chưa xác định đây là nguyên nhân của kết quả học phần.",
                "Giảng viên chọn bài đánh giá kiến thức tiên quyết tương ứng.",
            )

        if retention is not None and quiz is not None and retention < 0.6 and quiz >= 7:
            add(
                CATEGORY_LOW_RETENTION,
                "Kết quả kiểm tra ghi nhớ thấp trong khi điểm quiz đã ghi nhận khá cao",
                [f"Điểm quiz: {quiz:.1f}/10", f"Tỷ lệ ghi nhớ được ghi nhận: {retention:.1%}"],
                "Cần kiểm tra độ tương đương và khoảng cách thời gian của hai lần đánh giá trước khi kết luận về ghi nhớ dài hạn.",
                "Giảng viên chọn bài đánh giá lại cùng chuẩn đầu ra và ghi rõ thời điểm đánh giá.",
                ["Khoảng cách thời gian và độ tương đương của các lần đánh giá"],
            )

        weak_topics = {topic: value for topic, value in observed_mapping(acad.topic_scores, maximum=10).items() if value < 6}
        weak_skills = {topic: value for topic, value in observed_mapping(question.subskill_mastery, maximum=1).items() if value < 0.6}
        low_scores = [(label, value) for label, value in (("Quiz", quiz), ("Bài tập", assignment), ("Bài thi", exam)) if value is not None and value < 6]
        if weak_topics or weak_skills or low_scores:
            evidence = [f"Chủ đề {topic}: {value:.1f}/10" for topic, value in sorted(weak_topics.items())]
            evidence += [f"Kỹ năng {topic}: {value:.1%}" for topic, value in sorted(weak_skills.items())]
            evidence += [f"{label}: {value:.1f}/10" for label, value in low_scores]
            add(
                CATEGORY_KNOWLEDGE_GAP,
                "Có kết quả đánh giá dưới ngưỡng rà soát kiến thức",
                evidence,
                "Cần xác định chủ đề hoặc bước giải cần hỗ trợ bằng bài làm thực tế.",
                "Giảng viên chọn bài đánh giá theo chuẩn đầu ra tương ứng.",
            )

        if not diagnoses:
            if missing:
                available = [f"{label}: {value:g}" for label, value in core.items() if value is not None]
                add(
                    CATEGORY_INSUFFICIENT_DATA,
                    "Chưa đủ bằng chứng để nhận định tiến độ học tập",
                    available,
                    "Chỉ sử dụng các quan sát đã có; chưa suy luận mức thành thạo hoặc nguyên nhân từ dữ liệu còn thiếu.",
                    "Thu thập kết quả đánh giá theo chủ đề và nhật ký học tập còn thiếu.",
                )
            else:
                add(
                    CATEGORY_MASTERY_ON_TRACK,
                    "Các chỉ số đã ghi nhận chưa vượt ngưỡng rà soát của bộ quy tắc hiện tại",
                    [f"Điểm quiz: {quiz:.1f}/10", f"Điểm bài tập: {assignment:.1f}/10", f"Tỷ lệ đúng: {accuracy:.1%}"],
                    "Đây là kết quả rà soát theo quy tắc, chưa chứng minh đã thành thạo mọi chuẩn đầu ra.",
                    "Tiếp tục đánh giá theo chủ đề và đối chiếu các lần đo.",
                )
        return diagnoses


diagnosis_engine = DiagnosisEngine()
