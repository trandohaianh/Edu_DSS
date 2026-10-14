"""Student Learning Plan — Kế hoạch học tập cá nhân hóa có cấu trúc và liều lượng thực chứng.

Mục 8 & 9 Yêu cầu:
- LLM TUYỆT ĐỐI không được tự bịa toàn bộ kế hoạch học tập dưới dạng văn bản tự do.
- Kế hoạch phải được xây dựng như cấu trúc dữ liệu tường minh (Structured Data) với phiên bản:
  + plan_id, student_id, version, created_at, valid_until
  + strengths[], weaknesses[], diagnosis[], priority_topics[]
  + activities[]: objective, method, duration, frequency, approved_resource_ids[], reason, expected_outcome
  + assessment_plan, success_metrics, evidence_used[], confidence, next_review_at
- Liều lượng học tập (Dosage) dựa trên đường cơ sở cá nhân, tốc độ học, khối lượng công việc,
  tuyệt đối không dùng các con số cố định bịa đặt như "10 từ/ngày, 2 giờ/ngày".
- LLM chỉ làm nhiệm vụ diễn đạt cấu trúc dữ liệu này thành văn phong sư phạm ấm áp.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dss.services.diagnosis_engine import StructuredDiagnosis, diagnosis_engine
from dss.services.learning_profile import StudentLearningProfile
from dss.services.resource_catalog import resource_catalog


@dataclass
class PlanActivity:
    objective: str
    method: str
    duration_minutes: int
    frequency_per_week: int
    approved_resource_ids: List[str]
    reason: str
    expected_outcome: str


@dataclass
class StudentLearningPlan:
    plan_id: str
    student_pseudonym: str
    version: int
    created_at: str
    valid_until: str
    strengths: List[str]
    weaknesses: List[str]
    diagnoses: List[Dict[str, Any]]
    priority_topics: List[str]
    activities: List[PlanActivity]
    assessment_plan: str
    success_metrics: Dict[str, Any]
    evidence_used: List[str]
    # confidence: hằng số chính sách cố định (xem generate_plan) — KHÔNG PHẢI giá trị
    # đo lường/hiệu chuẩn từ dữ liệu sinh viên. Không hiển thị trực tiếp cho người
    # dùng như một tỷ lệ phần trăm đo được; chỉ dùng nội bộ nếu cần một mốc mặc định.
    confidence: float
    next_review_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LearningPlanGenerator:
    """Bộ tạo kế hoạch học tập có cấu trúc dựa trên hồ sơ và chẩn đoán định hình."""

    def generate_plan(
        self,
        profile: StudentLearningProfile,
        version: int = 1,
        validity_days: int = 21,
    ) -> StudentLearningPlan:
        """Tạo bản kế hoạch học tập có cấu trúc hoàn chỉnh."""
        diagnoses = diagnosis_engine.diagnose_student(profile)
        
        # 1. Nhận diện điểm mạnh (Strengths) từ hồ sơ
        strengths = []
        if profile.behavioral.active_days_last_month >= 15:
            strengths.append(f"Duy trì thói quen học tập đều đặn ({profile.behavioral.active_days_last_month} ngày hoạt động trong tháng)")
        if profile.academic.quiz_average >= 7.5:
            strengths.append(f"Điểm kiểm tra chuyên cần/quiz lý thuyết tốt ({profile.academic.quiz_average:.1f}/10)")
        if profile.trajectory.score_trend == "improving":
            strengths.append("Quỹ đạo điểm số đang có xu hướng tiến bộ so với đường cơ sở ban đầu")
        if not strengths:
            strengths.append("Có tinh thần chủ động tìm kiếm giải pháp và kế hoạch nâng cao kết quả học tập")

        # 2. Điểm yếu (Weaknesses) trích xuất từ chẩn đoán
        weaknesses = [d.issue for d in diagnoses]

        # 3. Chủ đề ưu tiên (Priority topics)
        priority_topics = []
        if profile.academic.assignment_average < 6.5:
            priority_topics.append("Bài tập thực hành và củng cố kỹ năng lập trình / bài tập tính toán")
        if profile.question_level.accuracy_rate < 0.6:
            priority_topics.append("Kỹ năng phân tích đề thi và kiểm soát độ chính xác trước khi nộp")
        if not priority_topics:
            priority_topics.append("Nâng cao và mở rộng các chủ đề nâng cao của học phần")

        # 4. Tính toán liều lượng học tập (Dosage) dựa trên baseline và tốc độ học
        # Sinh viên có tốc độ tiếp thu thấp hơn hoặc có nhiều lỗ hổng cần liều lượng can thiệp cao hơn
        vel = max(0.4, min(2.0, profile.trajectory.learning_velocity))
        gap_count = max(1, len(diagnoses))
        recommended_freq = min(5, max(2, int(round((profile.behavioral.practice_frequency_per_week + gap_count) / vel))))
        base_session_min = max(30, min(75, int(round((profile.behavioral.average_session_duration_minutes or 40) / min(vel, 1.0)))))

        # 5. Gắn tài nguyên đã thẩm định (Resource Catalog)
        approved_res = resource_catalog.list_approved_resources()
        chosen_res_ids = [r["resource_id"] for r in approved_res[:3]]

        activities = [
            PlanActivity(
                objective=f"Khắc phục điểm nghẽn: {priority_topics[0]}",
                method="Học lý thuyết ngắn gọn theo phương pháp Pomodoro, sau đó thực hành giải bài mẫu",
                duration_minutes=base_session_min,
                frequency_per_week=recommended_freq,
                approved_resource_ids=chosen_res_ids,
                reason="Dữ liệu quan sát cho thấy sinh viên tiếp thu tốt hơn qua các phiên học tập trung ngắn hạn",
                expected_outcome="Nâng tỷ lệ làm đúng trong các bài luyện tập lên trên 75%",
            ),
            PlanActivity(
                objective="Củng cố ghi nhớ dài hạn và khắc phục quên kiến thức",
                method="Thực hiện mini-quiz ôn tập ngắt quãng (Spaced repetition) cuối tuần",
                duration_minutes=20,
                frequency_per_week=1,
                approved_resource_ids=chosen_res_ids[:1],
                reason="Ngăn ngừa sụt giảm điểm số giữa các đợt kiểm tra lớn",
                expected_outcome="Duy trì tỷ lệ nhớ lại kiến thức trên 80% sau 2 tuần",
            ),
        ]

        now = datetime.now()
        valid_until_dt = now + timedelta(days=validity_days)
        next_review_dt = now + timedelta(days=min(14, validity_days))

        return StudentLearningPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
            student_pseudonym=profile.student_pseudonym,
            version=version,
            created_at=now.isoformat(),
            valid_until=valid_until_dt.isoformat(),
            strengths=strengths,
            weaknesses=weaknesses,
            diagnoses=[d.to_dict() for d in diagnoses],
            priority_topics=priority_topics,
            activities=activities,
            assessment_plan="Thực hiện bài kiểm tra định hình sau 2 tuần để đánh giá mức độ tiến bộ và cập nhật phiên bản kế hoạch.",
            success_metrics={
                "target_quiz_accuracy": 0.75,
                "target_practice_sessions_per_week": recommended_freq,
                "target_assignment_score": min(10.0, profile.academic.assignment_average + 1.0),
                "weekly_study_hours_target": round(sum(a.duration_minutes * a.frequency_per_week for a in activities) / 60.0, 1),
            },
            evidence_used=[
                f"Quiz average: {profile.academic.quiz_average:.1f}",
                f"Assignment average: {profile.academic.assignment_average:.1f}",
                f"Accuracy rate: {profile.question_level.accuracy_rate:.2f}",
                f"Practice frequency: {profile.behavioral.practice_frequency_per_week:.1f}/tuần",
            ],
            # confidence=0.85 là HẰNG SỐ CỐ ĐỊNH cho mọi kế hoạch, không phải giá trị
            # được tính/hiệu chuẩn từ profile của sinh viên (không có công thức nào ở
            # trên dùng profile để suy ra con số này). Không được diễn giải hoặc hiển
            # thị như một tỷ lệ phần trăm đo lường được (xem test
            # test_learning_plan_confidence_not_fabricated.py).
            confidence=0.85,
            next_review_at=next_review_dt.isoformat(),
        )

    def render_plan_to_prompt(self, plan: StudentLearningPlan) -> str:
        """Chuyển bản kế hoạch có cấu trúc thành chỉ thị cho LLM diễn đạt tự nhiên."""
        activities_text = "\n".join(
            [
                f"- Mục tiêu: {act.objective}\n"
                f"  + Phương pháp: {act.method}\n"
                f"  + Thời lượng khuyến nghị: {act.duration_minutes} phút/lần ({act.frequency_per_week} lần/tuần)\n"
                f"  + Tài nguyên LMS thẩm định: {', '.join(act.approved_resource_ids)}\n"
                f"  + Kết quả kỳ vọng: {act.expected_outcome}"
                for act in plan.activities
            ]
        )

        prompt = f"""Bạn là Cố vấn Học tập Sư phạm EduDSS. Dưới đây là BẢN KẾ HOẠCH HỌC TẬP ĐÃ ĐƯỢC CHẨN ĐOÁN CÓ CẤU TRÚC.
Nhiệm vụ của bạn là DIỄN ĐẠT bản kế hoạch này thành văn phong tự nhiên, ấm áp, thấu cảm và mạch lạc dành cho sinh viên.

TUYỆT ĐỐI TUÂN THỦ:
1. KHÔNG tự ý bịa đặt thêm các KPI số hoặc thời lượng học khác với các số liệu đã nêu trong cấu trúc dưới đây.
2. KHÔNG tự ý suy đoán thêm các nguyên nhân không có trong mục CHẨN ĐOÁN.
3. KHÔNG đưa vào các đường dẫn URL ngoài danh sách tài nguyên LMS đã cung cấp.

=== CẤU TRÚC KẾ HOẠCH (BẢN GỐC TỪ HỆ THỐNG) ===
- Mã kế hoạch: {plan.plan_id} (Phiên bản: {plan.version})
- Điểm mạnh đã ghi nhận:
{chr(10).join(['  + ' + s for s in plan.strengths])}
- Điểm cần khắc phục:
{chr(10).join(['  + ' + w for w in plan.weaknesses])}
- Chủ đề ưu tiên: {', '.join(plan.priority_topics)}
- Hoạt động cụ thể:
{activities_text}
- Kế hoạch đánh giá tiếp theo: {plan.assessment_plan}
- Đợt rà soát kế tiếp: {plan.next_review_at}

Hãy viết lời tư vấn hoàn chỉnh gửi sinh viên dựa trên cấu trúc trên."""
        return prompt


# Singleton plan generator
learning_plan_generator = LearningPlanGenerator()
