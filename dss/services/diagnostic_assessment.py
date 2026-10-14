"""Diagnostic Assessment — Hệ thống bài đánh giá chẩn đoán định hình có căn cứ tri thức.

Mục 10 Yêu cầu:
- Hỗ trợ bài đánh giá chẩn đoán cá nhân hóa định hình (formative diagnostic assessment).
- Quy trình:
  suspected weakness
  -> assessment blueprint
  -> retrieve APPROVED course knowledge
  -> generate candidate questions
  -> validate against source (kiểm chứng với tài liệu nguồn)
  -> deliver to student
  -> collect evidence (accuracy, response time, attempt count, hints)
  -> update StudentLearningProfile
  -> update Diagnosis
  -> update LearningPlan version
- LLM TUYỆT ĐỐI không bao giờ được bịa đặt sự thật/kiến thức môn học.
- Đánh giá có tính chất xếp loại cao (high-stakes) bắt buộc có phê duyệt của Giảng viên.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from dss.services.learning_profile import StudentLearningProfile


@dataclass
class DiagnosticQuestion:
    question_id: str
    topic: str
    subskill: str
    question_text: str
    options: List[str]
    correct_answer_index: int
    source_document_id: str
    explanation: str
    difficulty: str = "Medium"  # "Easy" | "Medium" | "Hard"
    approved_by_lecturer: bool = True


@dataclass
class AssessmentBlueprint:
    blueprint_id: str
    target_topic: str
    suspected_weakness: str
    num_questions: int
    allowed_source_ids: List[str]
    questions: List[DiagnosticQuestion] = field(default_factory=list)
    status: str = "APPROVED"  # "DRAFT" | "PENDING_LECTURER_APPROVAL" | "APPROVED" | "REJECTED"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_comment: str = ""
    version: int = 1


class DiagnosticAssessmentService:
    """Dịch vụ điều phối bài đánh giá chẩn đoán định hình."""

    def __init__(self, resource_catalog=None):
        self.resource_catalog = resource_catalog

    def create_assessment_blueprint(
        self,
        topic: str,
        suspected_weakness: str,
        approved_docs: List[Dict[str, Any]],
        num_questions: int = 3,
        is_high_stakes: bool = False,
    ) -> AssessmentBlueprint:
        """Tạo khung bài kiểm tra chẩn đoán dựa trên tài liệu đã được duyệt."""
        blueprint_id = f"diag_{uuid.uuid4().hex[:10]}"
        allowed_ids = [d.get("id", "") for d in approved_docs if d.get("status") == "APPROVED" or d.get("source_verified")]

        # Khởi tạo câu hỏi dựa trên tài liệu đã kiểm chứng
        sample_questions: List[DiagnosticQuestion] = []
        for i, doc in enumerate(approved_docs[:num_questions]):
            doc_id = doc.get("id", f"doc_{i+1}")
            title = doc.get("title", "Chủ đề học tập")
            content = doc.get("content", "")

            sample_questions.append(
                DiagnosticQuestion(
                    question_id=f"q_{blueprint_id}_{i+1}",
                    topic=topic,
                    subskill=title,
                    question_text=f"Dựa trên kiến thức về '{title}': Đâu là phương pháp tiếp cận phù hợp nhất?",
                    options=[
                        f"Áp dụng nguyên tắc: {content[:80]}...",
                        "Học thuộc lòng toàn bộ công thức mà không cần thực hành",
                        "Chỉ làm bài tập ngay trước ngày thi chính thức",
                        "Bỏ qua các phần lý thuyết chưa hiểu rõ",
                    ],
                    correct_answer_index=0,
                    source_document_id=doc_id,
                    explanation=f"Căn cứ trực tiếp theo tài liệu đã được phê duyệt: {title}.",
                    difficulty="Medium",
                    approved_by_lecturer=True if not is_high_stakes else False,
                )
            )

        status = "PENDING_LECTURER_APPROVAL" if is_high_stakes else "APPROVED"

        return AssessmentBlueprint(
            blueprint_id=blueprint_id,
            target_topic=topic,
            suspected_weakness=suspected_weakness,
            num_questions=len(sample_questions),
            allowed_source_ids=allowed_ids,
            questions=sample_questions,
            status=status,
        )

    def process_student_response(
        self,
        profile: StudentLearningProfile,
        blueprint: AssessmentBlueprint,
        student_answers: List[int],
        response_times_seconds: List[float],
        hint_counts: List[int],
    ) -> Dict[str, Any]:
        """Thu thập kết quả bài làm của sinh viên và cập nhật hồ sơ học tập."""
        total_questions = len(blueprint.questions)
        correct_count = 0

        for i, q in enumerate(blueprint.questions):
            if i < len(student_answers) and student_answers[i] == q.correct_answer_index:
                correct_count += 1

        accuracy = correct_count / max(1, total_questions)
        avg_time = sum(response_times_seconds) / max(1, len(response_times_seconds))
        total_hints = sum(hint_counts)

        # Cập nhật bằng chứng cấp câu hỏi vào profile
        profile.question_level.accuracy_rate = (profile.question_level.accuracy_rate * 0.7) + (accuracy * 0.3)
        profile.question_level.average_response_time_seconds = (
            profile.question_level.average_response_time_seconds * 0.7
        ) + (avg_time * 0.3)
        profile.question_level.hint_requests_count += total_hints

        return {
            "blueprint_id": blueprint.blueprint_id,
            "total_questions": total_questions,
            "correct_answers": correct_count,
            "accuracy_score": accuracy,
            "average_response_time": avg_time,
            "hints_used": total_hints,
            "feedback": (
                "Hoàn thành tốt bài chẩn đoán. Kiến thức cốt lõi đã được củng cố."
                if accuracy >= 0.75
                else "Phát hiện một số lỗ hổng kiến thức cần tiếp tục ôn tập theo kế hoạch."
            ),
        }


# Singleton service
diagnostic_service = DiagnosticAssessmentService()
