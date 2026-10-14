"""Diagnosis Engine — Bộ suy luận chẩn đoán học tập có cấu trúc TRƯỚC KHI gọi LLM.

Mục 6 & 7 Yêu cầu:
- LLM TUYỆT ĐỐI không được tự ý bịa đặt nguyên nhân học lực của sinh viên.
- Toàn bộ giả thuyết và căn cứ phải được suy diễn có cấu trúc dựa trên hồ sơ học tập:
  + issue: Vấn đề cần khắc phục
  + evidence[]: Các bằng chứng thực tế từ hành vi và điểm số
  + hypotheses[]: Danh sách nguyên nhân khả dĩ kèm độ tin cậy
  + missing_evidence[]: Dữ liệu còn thiếu cần kiểm chứng thêm
  + recommended_diagnostic: Bài kiểm tra định hình đề xuất để làm rõ
- Danh mục chẩn đoán chuẩn:
  KNOWLEDGE_GAP, PREREQUISITE_GAP, LOW_PRACTICE, LOW_RETENTION, SLOW_RESPONSE,
  CARELESS_FAST_RESPONSE, LOW_ENGAGEMENT, INCONSISTENT_STUDY, INSUFFICIENT_DATA
- Nguyên tắc: Không quy kết nhân quả tuyệt đối chỉ từ tương quan; dùng văn phong
  "Các bằng chứng hiện có cho thấy khả năng..."
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from dss.services.learning_profile import StudentLearningProfile


# Các danh mục chẩn đoán được chuẩn hóa
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

# Nhãn tiếng Việt thân thiện cho từng danh mục — ĐIỂM GỌI DUY NHẤT UI nên dùng
# (category_label()) khi hiển thị enum chẩn đoán cho người dùng cuối. Enum gốc
# (vd. "MASTERY_ON_TRACK") tuyệt đối KHÔNG được xuất hiện nguyên dạng trên UI.
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
    """Nhãn tiếng Việt thân thiện cho 1 mã danh mục chẩn đoán — không bao giờ
    trả về enum kỹ thuật thô cho UI, kể cả danh mục lạ/chưa khai báo."""
    if not category:
        return "Nhận định chung"
    return CATEGORY_LABELS.get(category, "Nhận định chung")


@dataclass
class HypothesisItem:
    category: str
    cause: str
    confidence: float  # 0.0 - 1.0
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
    """Động cơ suy diễn chẩn đoán học tập định hình cho EduDSS."""

    def diagnose_student(self, profile: StudentLearningProfile) -> List[StructuredDiagnosis]:
        """Phân tích hồ sơ sinh viên để sinh danh sách chẩn đoán có căn cứ dữ liệu."""
        diagnoses: List[StructuredDiagnosis] = []

        acad = profile.academic
        q_lvl = profile.question_level
        behav = profile.behavioral
        traj = profile.trajectory

        # 1. Chẩn đoán về lỗ hổng thực hành (LOW_PRACTICE)
        if behav.practice_frequency_per_week < 1.5 and acad.assignment_average < 6.5:
            diagnoses.append(
                StructuredDiagnosis(
                    issue="Điểm bài tập dưới mức kỳ vọng kèm tần suất luyện tập thấp",
                    evidence=[
                        f"Tần suất làm bài tập thực hành đạt {behav.practice_frequency_per_week:.1f} lần/tuần (dưới ngưỡng khuyến nghị 2.5 lần/tuần)",
                        f"Điểm bài tập trung bình đạt {acad.assignment_average:.1f}/10",
                    ],
                    hypotheses=[
                        HypothesisItem(
                            category=CATEGORY_LOW_PRACTICE,
                            cause="Các bằng chứng hiện có cho thấy sinh viên chưa dành đủ số giờ làm bài tập áp dụng để thuần thục kỹ năng.",
                            confidence=0.82,
                            evidence=[f"Luyện tập {behav.practice_frequency_per_week} lần/tuần", f"Hoàn thành video {behav.video_completion_rate * 100:.0f}%"],
                            needs_confirmation=False,
                        )
                    ],
                    missing_evidence=["Nhật ký làm bài tập tự luyện ngoài giờ chưa được ghi nhận."],
                    recommended_diagnostic="Giao bài quiz thực hành ngắn 5 câu để đo mức độ sẵn sàng giải quyết bài tập cơ bản.",
                )
            )

        # 2. Chẩn đoán về tốc độ phản hồi và độ cẩn trọng (SLOW_RESPONSE vs CARELESS_FAST_RESPONSE)
        if q_lvl.accuracy_rate < 0.6:
            if q_lvl.average_response_time_seconds < 20.0:
                diagnoses.append(
                    StructuredDiagnosis(
                        issue="Tỷ lệ làm đúng thấp đi kèm thời gian trả lời quá nhanh",
                        evidence=[
                            f"Tỷ lệ trả lời đúng chỉ đạt {q_lvl.accuracy_rate * 100:.1f}%",
                            f"Thời gian phản hồi trung bình chỉ đạt {q_lvl.average_response_time_seconds:.1f} giây/câu (nhanh hơn nhiều so với chuẩn bài thi)",
                        ],
                        hypotheses=[
                            HypothesisItem(
                                category=CATEGORY_CARELESS_FAST_RESPONSE,
                                cause="Dữ liệu quan sát cho thấy sinh viên có xu hướng chọn đáp án vội vã, chưa đọc kỹ câu hỏi hoặc bỏ qua bước kiểm tra lại.",
                                confidence=0.88,
                                evidence=[f"Thời gian {q_lvl.average_response_time_seconds:.1f}s/câu", f"Số lần yêu cầu gợi ý {q_lvl.hint_requests_count} lần"],
                                needs_confirmation=True,
                            )
                        ],
                        missing_evidence=["Chưa đo lường được tỷ lệ đọc lại đề bài trước khi nộp."],
                        recommended_diagnostic="Bài kiểm tra chẩn đoán 3 câu có giới hạn thời gian đọc tối thiểu 30 giây.",
                    )
                )
            elif q_lvl.average_response_time_seconds > 90.0:
                diagnoses.append(
                    StructuredDiagnosis(
                        issue="Thời gian xử lý câu hỏi kéo dài kèm tỷ lệ làm đúng thấp",
                        evidence=[
                            f"Thời gian làm bài trung bình {q_lvl.average_response_time_seconds:.1f} giây/câu",
                            f"Số lần thử lại (attempts) là {q_lvl.attempt_count_per_question:.1f} lần/câu",
                        ],
                        hypotheses=[
                            HypothesisItem(
                                category=CATEGORY_SLOW_RESPONSE,
                                cause="Dữ liệu quan sát cho thấy sinh viên gặp khó khăn trong việc gợi nhớ công thức hoặc lúng túng trong thuật toán giải quyết vấn đề.",
                                confidence=0.78,
                                evidence=[f"Số lần yêu cầu hint: {q_lvl.hint_requests_count}"],
                                needs_confirmation=True,
                            )
                        ],
                        missing_evidence=["Mức độ nắm vững các khái niệm tiên quyết."],
                        recommended_diagnostic="Thực hiện bài test chia nhỏ bước giải để xác định đoạn nghẽn tư duy.",
                    )
                )

        # 3. Chẩn đoán về lỗ hổng kiến thức tiên quyết (PREREQUISITE_GAP)
        weak_prereqs = [k for k, v in acad.prerequisite_mastery.items() if v < 0.6]
        if weak_prereqs:
            diagnoses.append(
                StructuredDiagnosis(
                    issue="Chưa thuần thục các kỹ năng/học phần tiên quyết của môn học",
                    evidence=[f"Kiến thức nền tảng '{prereq}' đạt dưới 60% mức độ thành thạo" for prereq in weak_prereqs],
                    hypotheses=[
                        HypothesisItem(
                            category=CATEGORY_PREREQUISITE_GAP,
                            cause="Các bằng chứng hiện có cho thấy khó khăn học tập xuất phát từ lỗ hổng kiến thức nền tảng ở các kỳ trước.",
                            confidence=0.85,
                            evidence=[f"Prerequisite score: {acad.prerequisite_mastery.get(weak_prereqs[0], 0):.2f}"],
                            needs_confirmation=False,
                        )
                    ],
                    missing_evidence=["Kết quả bài kiểm tra đầu khóa học."],
                    recommended_diagnostic="Bài đánh giá chẩn đoán bù đắp kiến thức nền tảng (Review Diagnostic).",
                )
            )

        # 4. Chẩn đoán về độ ghi nhớ dài hạn (LOW_RETENTION)
        if traj.delayed_retention_rate < 0.6 and acad.quiz_average >= 7.0:
            diagnoses.append(
                StructuredDiagnosis(
                    issue="Tụt giảm khả năng ghi nhớ kiến thức sau một khoảng thời gian",
                    evidence=[
                        f"Điểm quiz ban đầu đạt {acad.quiz_average:.1f}/10",
                        f"Tỷ lệ nhớ lại sau 2 tuần chỉ đạt {traj.delayed_retention_rate * 100:.1f}%",
                    ],
                    hypotheses=[
                        HypothesisItem(
                            category=CATEGORY_LOW_RETENTION,
                            cause="Dữ liệu gợi ý sinh viên học theo phương pháp học dồn trước kỳ kiểm tra, thiếu hoạt động ôn tập ngắt quãng (spaced repetition).",
                            confidence=0.75,
                            evidence=[f"Retention rate: {traj.delayed_retention_rate:.2f}"],
                            needs_confirmation=True,
                        )
                    ],
                    missing_evidence=["Nhật ký ôn tập định kỳ hàng tuần."],
                    recommended_diagnostic="Giao các mini-quiz ôn tập giãn cách 1 tuần/lần.",
                )
            )

        # 5. Nếu không có đủ dữ liệu để kết luận
        if not diagnoses:
            diagnoses.append(
                StructuredDiagnosis(
                    issue="Chưa phát hiện điểm nghẽn học tập nghiêm trọng trên dữ liệu hiện tại",
                    evidence=[
                        f"Baseline cá nhân ổn định ở mức {traj.historical_baseline_score:.2f}",
                        f"Mức độ chuyên cần và đăng nhập đạt {behav.active_days_last_month} ngày hoạt động/tháng",
                    ],
                    hypotheses=[
                        HypothesisItem(
                            category=CATEGORY_INSUFFICIENT_DATA if acad.assignment_average == 0 else CATEGORY_MASTERY_ON_TRACK,
                            cause="Dữ liệu quan sát cho thấy tiến độ học tập đang duy trì bình thường hoặc cần thêm bài tập để đánh giá sâu hơn.",
                            confidence=0.70,
                            evidence=["Chưa ghi nhận điểm trũng học tập."],
                            needs_confirmation=False,
                        )
                    ],
                    missing_evidence=["Cần thêm kết quả các bài kiểm tra chuyên sâu từng tuần."],
                    recommended_diagnostic="Tiếp tục làm bài tập tuần và theo dõi tiến độ.",
                )
            )

        return diagnoses


# Singleton diagnosis engine
diagnosis_engine = DiagnosisEngine()
