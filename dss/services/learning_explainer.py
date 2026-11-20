"""AI Learning Explainer — giải thích lại bài giảng của Giảng viên cho Sinh
viên, ưu tiên TUYỆT ĐỐI nội dung CMS thật (không phải chatbot kiến thức chung).

Tái sử dụng hạ tầng đã có: cms_lecture_repository (retrieval đúng phạm vi môn/bài;
KHÔNG nhầm với dss/services/cms_repository.py — module đó phục vụ Career Decision
Support System, khác miền dữ liệu hoàn toàn),
prompt_security (ranh giới chống injection), citation_service (xác minh
trích dẫn), context_budget (ước lượng token), diagnostic_assessment (sinh
quiz có căn cứ), privacy_service (định danh giả danh).

Workstream C (2026-09, Issue AIGOV-001): sinh câu trả lời trước đây gọi
THẲNG `llm_integration.call_ai_provider(...)`, bỏ qua hoàn toàn
`dss.services.llm_gateway.LLMGateway` — không có quota, không giới hạn tốc
độ/concurrency, không ghi nhận chi phí token, không có Production Demo
Policy. Đã sửa: `generate_explanation()` giờ gọi qua
`LLMGateway(llm_integration).stream_generate(...)`, cùng đường dẫn
`ai_advisor.py`'s chat/advisor flow đã dùng đúng từ trước — xem
reports/production_readiness/WORKSTREAM_C_ML_AI_GOVERNANCE.md.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dss.core.data_root import get_data_root
from dss.core.target_utils import is_id_like
from dss.services import citation_service, prompt_security
from dss.services import cms_lecture_repository as cms_repository
from dss.services import learning_explainer_policy as policy
from dss.services.learning_explainer_policy import CMS_ONLY, CMS_PLUS_SUPPLEMENTARY, NO_CMS_CONTENT_MESSAGE

_LOG_LOCK = threading.Lock()
_QUIZ_LOCK = threading.Lock()
_MISCONCEPTION_LOCK = threading.Lock()


def _interaction_log_path() -> Path:
    """PERF-002: tính lại mỗi lần gọi, không cache mức module (xem dss/core/data_root.py)."""
    return get_data_root() / "cms" / "interaction_log.json"


def _quiz_review_path() -> Path:
    return get_data_root() / "cms" / "quiz_review_queue.json"


def _misconception_store_path() -> Path:
    return get_data_root() / "cms" / "misconception_records.json"


EXPLANATION_LEVELS = ["Foundation", "Standard", "Advanced"]


# ============================================================================
# MỤC 4/5 — MỨC GIẢI THÍCH THEO NGỮ CẢNH LMS CỦA SINH VIÊN (không giải thích
# giống nhau cho mọi người)
# ============================================================================
def determine_explanation_level(topic_mastery: Optional[float]) -> str:
    """topic_mastery: 0.0-1.0 hoặc None (chưa có dữ liệu). None -> 'Standard'
    (trung lập, không giả định sinh viên yếu hay giỏi khi thiếu bằng chứng)."""
    if topic_mastery is None:
        return "Standard"
    if topic_mastery < 0.4:
        return "Foundation"
    if topic_mastery < 0.75:
        return "Standard"
    return "Advanced"


@dataclass
class ExplanationLevelResolution:
    level: str  # Foundation | Standard | Advanced
    confidence: str  # Low | Medium | High — phụ thuộc tầng bằng chứng nào khớp
    evidence: List[str]  # chi tiết KỸ THUẬT — dùng cho log/Lecturer view, KHÔNG hiện thẳng cho Sinh viên
    source: str  # "subskill_mastery" | "topic_mastery" | "quiz_history" | "course_topic_score" | "default"
    friendly_reason: str  # 1 câu tiếng Việt AN TOÀN để hiện cho Sinh viên

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_FRIENDLY_LEVEL_REASON = {
    "Foundation": "AI đang giải thích ở mức nền tảng, dựa trên tiến độ học tập gần đây của bạn.",
    "Standard": "AI đang giải thích ở mức tiêu chuẩn, phù hợp với tiến độ học tập hiện tại của bạn.",
    "Advanced": "AI đang giải thích ở mức nâng cao, dựa trên tiến độ học tập tốt gần đây của bạn.",
}


def _quiz_accuracy_from_interaction_log(student_pseudonym: str, topic_id: str) -> Optional[float]:
    """Tầng 3 — độ chính xác quiz THẬT của CHÍNH sinh viên này cho ĐÚNG topic_id,
    tính từ log tương tác của Learning Explainer (vòng phản hồi Mục 9/12).
    Trả về None trung thực nếu chưa có lượt quiz nào được ghi nhận."""
    records = [
        r
        for r in _load_interaction_log()
        if r.get("student_pseudonym") == student_pseudonym
        and r.get("topic_id") == topic_id
        and r.get("quiz_correct") is not None
    ]
    if not records:
        return None
    correct = sum(1 for r in records if r.get("quiz_correct"))
    return correct / len(records)


def resolve_explanation_level(
    student_id: str,
    course_id: str,
    lesson_id: str,
    topic_id: Optional[str],
    learning_profile: Any = None,
    df: Any = None,
) -> ExplanationLevelResolution:
    """Thứ tự ưu tiên bằng chứng BẮT BUỘC (Mục 1) — KHÔNG chỉ dựa vào so khớp
    tên topic_id với cột điểm:
    1. subskill_mastery từ StudentLearningProfile (dss/services/learning_profile.py)
    2. topic-level mastery (AcademicEvidence.topic_scores) trong CÙNG profile đó
    3. lịch sử quiz thật của chính sinh viên (vòng phản hồi nội bộ Learning Explainer)
    4. điểm chủ đề/môn liên quan trong dataset (so khớp văn bản — chỉ dùng khi
       3 tầng trên đều không có dữ liệu)
    5. mặc định Standard (trung lập, không đoán)."""
    from dss.services.privacy_service import generate_pseudonym

    pseudonym = generate_pseudonym(str(student_id)) if student_id else "guest"

    if topic_id and learning_profile is not None:
        from dss.services.learning_profile import observed_mapping

        subskill = getattr(learning_profile, "question_level", None)
        subskill_mastery = observed_mapping(getattr(subskill, "subskill_mastery", {}), maximum=1.0) if subskill else {}
        if topic_id in subskill_mastery:
            value = float(subskill_mastery[topic_id])
            return ExplanationLevelResolution(
                level=determine_explanation_level(value),
                confidence="High",
                evidence=[f"subskill_mastery[{topic_id}] = {value:.2f}"],
                source="subskill_mastery",
                friendly_reason=_FRIENDLY_LEVEL_REASON[determine_explanation_level(value)],
            )

        academic = getattr(learning_profile, "academic", None)
        topic_scores = observed_mapping(getattr(academic, "topic_scores", {}), maximum=10.0) if academic else {}
        if topic_id in topic_scores:
            raw = float(topic_scores[topic_id])
            normalized = raw / 10.0  # AcademicEvidence.topic_scores always uses the 0..10 scale.
            return ExplanationLevelResolution(
                level=determine_explanation_level(normalized),
                confidence="Medium",
                evidence=[f"topic_scores[{topic_id}] = {raw}"],
                source="topic_mastery",
                friendly_reason=_FRIENDLY_LEVEL_REASON[determine_explanation_level(normalized)],
            )

    if topic_id:
        quiz_accuracy = _quiz_accuracy_from_interaction_log(pseudonym, topic_id)
        if quiz_accuracy is not None:
            return ExplanationLevelResolution(
                level=determine_explanation_level(quiz_accuracy),
                confidence="Medium",
                evidence=[f"quiz_accuracy[{topic_id}] = {quiz_accuracy:.2f} (từ lịch sử quiz thật)"],
                source="quiz_history",
                friendly_reason=_FRIENDLY_LEVEL_REASON[determine_explanation_level(quiz_accuracy)],
            )

    if df is not None and topic_id:
        from dss.core.data_helpers import TOPIC_SCORE_COLUMNS

        id_col = next((c for c in df.columns if is_id_like(c)), None)
        matching_col = next(
            (
                c
                for c in TOPIC_SCORE_COLUMNS
                if topic_id.lower() in c.lower() or topic_id.lower() in TOPIC_SCORE_COLUMNS[c].lower()
            ),
            None,
        )
        if id_col and matching_col and matching_col in df.columns:
            rows = df[df[id_col].astype(str) == str(student_id)]
            if not rows.empty:
                try:
                    raw = float(rows.iloc[0][matching_col])
                    normalized = raw / 10.0
                    return ExplanationLevelResolution(
                        level=determine_explanation_level(normalized),
                        confidence="Low",
                        evidence=[f"{matching_col} (so khớp văn bản với topic_id) = {raw}"],
                        source="course_topic_score",
                        friendly_reason=_FRIENDLY_LEVEL_REASON[determine_explanation_level(normalized)],
                    )
                except (TypeError, ValueError):
                    pass

    return ExplanationLevelResolution(
        level="Standard",
        confidence="Low",
        evidence=["Không có bằng chứng mastery nào khớp — dùng mặc định trung lập."],
        source="default",
        friendly_reason=_FRIENDLY_LEVEL_REASON["Standard"],
    )


_LEVEL_INSTRUCTIONS = {
    "Foundation": (
        "Mức FOUNDATION: hạn chế công thức, dùng ví dụ trực quan gần gũi, giải thích TỪNG BƯỚC nhỏ, "
        "tránh thuật ngữ chuyên sâu nếu chưa giải thích trước."
    ),
    "Standard": (
        "Mức STANDARD: giải thích đầy đủ cơ chế hoạt động của khái niệm/thuật toán, có thể dùng thuật "
        "ngữ chuẩn (centroid, distance, iteration...) kèm giải nghĩa ngắn gọn."
    ),
    "Advanced": (
        "Mức ADVANCED: có thể đi sâu vào hàm mục tiêu (objective function), điều kiện hội tụ, cách khởi "
        "tạo, giới hạn/nhược điểm của phương pháp — giả định sinh viên đã nắm cơ chế cơ bản."
    ),
}

# ============================================================================
# MỤC 6 — CẤU TRÚC CÂU TRẢ LỜI BẮT BUỘC (8 phần)
# ============================================================================
_EXPLANATION_STRUCTURE_PROMPT = (
    "Cấu trúc câu trả lời BẮT BUỘC theo đúng 8 phần sau (bỏ qua phần nào không thật sự cần thiết cho câu "
    "hỏi cụ thể, nhưng KHÔNG đổi thứ tự các phần đã dùng):\n"
    "1. Ý chính (1-2 câu)\n"
    "2. Giải thích dễ hiểu\n"
    "3. Liên hệ với bài giảng (trích đúng nội dung/slide/tài liệu đã cung cấp bên dưới)\n"
    "4. Ví dụ minh hoạ\n"
    "5. Công thức (nếu có, và phù hợp với MỨC giải thích)\n"
    "6. Lỗi thường gặp\n"
    "7. Câu hỏi kiểm tra nhanh mức hiểu (1 câu ngắn)\n"
    "8. Nguồn bài giảng đã dùng"
)

# ============================================================================
# MỤC 16 — GUARDRAIL
# ============================================================================
_GUARDRAIL_PROMPT = (
    "QUY TẮC BẮT BUỘC:\n"
    "- KHÔNG được sửa đổi/diễn giải sai ý nghĩa nội dung Giảng viên đã cung cấp trong "
    "<untrusted_retrieved_evidence> — đó là nguồn CHÍNH.\n"
    "- Nếu <untrusted_retrieved_evidence> KHÔNG chứa nội dung liên quan tới câu hỏi, PHẢI trả lời đúng "
    "nguyên văn: 'Nội dung này chưa có trong tài liệu môn học hiện tại. Tôi có thể giải thích thêm bằng "
    "kiến thức bổ sung nếu bạn muốn.' — KHÔNG được tự bịa nội dung bài giảng không có thật.\n"
    "- Nếu người dùng đồng ý dùng kiến thức bổ sung, PHẦN ĐÓ phải được tách rõ dưới tiêu đề "
    "'Kiến thức bổ sung (ngoài bài giảng)' — KHÔNG trộn lẫn với phần 'Từ bài giảng'."
)

_SOCRATIC_PROMPT = (
    "CHẾ ĐỘ HỌC BẰNG CÂU HỎI GỢI MỞ (Socratic): KHÔNG đưa đáp án trực tiếp ngay. Thay vào đó, đặt 1 câu "
    "hỏi gợi mở giúp sinh viên tự suy luận ra ý chính, dựa trên đúng nội dung bài giảng đã cung cấp. Sau "
    "khi sinh viên trả lời (ở lượt hỏi tiếp theo), phản hồi ngắn gọn đúng/sai/gợi ý thêm rồi mới dẫn dắt "
    "tiếp — không giải thích trọn vẹn cho tới khi sinh viên đã thử trả lời."
)


@dataclass
class FriendlyCitation:
    label: str  # "Bài 4 – K-Means Clustering, slide 12-15"
    lesson_id: str
    course_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _format_friendly_citation(chunk: Dict[str, Any]) -> FriendlyCitation:
    """Định dạng trích dẫn thân thiện (Mục B9) — không bao giờ lộ chunk_id/
    vector_id/namespace_id/embedding_id ra ngoài, chỉ hiển thị tên tài liệu,
    bài/chương/slide, và môn học khi có metadata thật cho từng phần (không
    bịa phần nào thiếu)."""
    meta = chunk.get("metadata", {}) or {}
    title = meta.get("title") or chunk.get("title") or "Tài liệu bài giảng"
    section = meta.get("page_or_section")
    course_id = meta.get("course_id") or chunk.get("course_id")
    label = title
    if section:
        label += f", {section}"
    if course_id:
        label += f" (Tài liệu môn {course_id})"
    return FriendlyCitation(label=label, lesson_id=meta.get("lesson_id", ""), course_id=meta.get("course_id", ""))


# ============================================================================
# MỤC 11 — PHÁT HIỆN NGỘ NHẬN (MISCONCEPTION DETECTION)
# ============================================================================
# Rule-based, theo đúng ví dụ yêu cầu (K-Means bị nhầm là classification) — mở
# rộng dần khi có thêm dữ liệu quan sát thật từ log tương tác, KHÔNG suy đoán
# ngộ nhận chưa từng quan sát được.
MISCONCEPTION_PATTERNS: Dict[str, List[Dict[str, str]]] = {
    "k-means": [
        {
            "pattern": r"\b(classification|phân loại có nhãn)\b",
            "label": "Nhầm K-Means (clustering) với classification (có nhãn)",
            "hint": "K-Means là thuật toán HỌC KHÔNG GIÁM SÁT (unsupervised) — không dùng nhãn có sẵn, khác hẳn classification.",
        },
    ],
    "overfitting": [
        {
            "pattern": r"\bunderfit",
            "label": "Nhầm Overfitting với Underfitting",
            "hint": "Overfitting là mô hình HỌC QUÁ KHỚP dữ liệu train (kể cả nhiễu); Underfitting là mô hình CHƯA học đủ, cả hai đều là vấn đề nhưng ngược hướng nhau.",
        },
    ],
    "correlation": [
        {
            "pattern": r"\b(nguyên nhân|gây ra|causation)\b",
            "label": "Nhầm Tương quan (Correlation) với Nhân quả (Causation)",
            "hint": "Hai biến tương quan với nhau KHÔNG có nghĩa biến này gây ra biến kia — cần bằng chứng thực nghiệm/thiết kế thí nghiệm mới kết luận được nhân quả.",
        },
    ],
}


def detect_misconception(topic: str, student_answer_text: str) -> Optional[Dict[str, str]]:
    topic_key = topic.strip().lower()
    patterns = MISCONCEPTION_PATTERNS.get(topic_key)
    if not patterns:
        return None
    answer_lower = (student_answer_text or "").lower()
    for p in patterns:
        if re.search(p["pattern"], answer_lower):
            return {"label": p["label"], "hint": p["hint"]}
    return None


# ============================================================================
# GIẢI THÍCH THÍCH ỨNG — HÀM CHÍNH
# ============================================================================
@dataclass
class ExplanationResult:
    has_cms_content: bool
    answer: str
    explanation_level: str
    citations: List[FriendlyCitation]
    hallucinated_citations: List[Dict[str, Any]]
    used_socratic_mode: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_cms_content": self.has_cms_content,
            "answer": self.answer,
            "explanation_level": self.explanation_level,
            "citations": [c.to_dict() for c in self.citations],
            "hallucinated_citations": self.hallucinated_citations,
            "used_socratic_mode": self.used_socratic_mode,
        }


def build_system_prompt(
    explanation_level: str,
    socratic_mode: bool,
    lesson_notes: List[str],
    faq: List[Dict[str, str]],
    mode: str = CMS_ONLY,
    active_misconception: Optional[Dict[str, str]] = None,
) -> str:
    parts = [
        "Bạn là AI Learning Explainer — trợ lý giải thích lại bài giảng của Giảng viên cho sinh viên. "
        "Đây KHÔNG phải chatbot kiến thức chung — PHẢI ưu tiên tuyệt đối nội dung trong "
        "<untrusted_retrieved_evidence> (trích từ CMS bài giảng thật).",
        _LEVEL_INSTRUCTIONS[explanation_level],
        _EXPLANATION_STRUCTURE_PROMPT,
        _GUARDRAIL_PROMPT,
    ]
    if mode == CMS_PLUS_SUPPLEMENTARY:
        parts.append(
            "Sinh viên ĐÃ ĐỒNG Ý nghe thêm kiến thức bổ sung ngoài bài giảng cho câu hỏi này — được phép "
            "trả lời phần ngoài phạm vi CMS, NHƯNG BẮT BUỘC tách rõ 2 tiêu đề: 'Từ bài giảng' và 'Kiến "
            "thức bổ sung' — không được trộn lẫn không nhãn."
        )
    else:
        parts.append("Chế độ CMS_ONLY: TUYỆT ĐỐI không trả lời phần nào ngoài phạm vi tài liệu CMS đã cung cấp.")
    if socratic_mode:
        parts.append(_SOCRATIC_PROMPT)
    if active_misconception:
        parts.append(
            f"LƯU Ý SƯ PHẠM: sinh viên này TRƯỚC ĐÂY từng nhầm lẫn '{active_misconception['label']}' — hãy chủ động "
            f"phân biệt rõ khái niệm này ngay từ đầu câu trả lời trước khi đi vào phần chính, theo hướng: "
            f"{active_misconception['hint']}"
        )
    if lesson_notes:
        parts.append(
            "Ghi chú bổ sung từ Giảng viên (tham khảo khi giải thích):\n" + "\n".join(f"- {n}" for n in lesson_notes)
        )
    if faq:
        faq_text = "\n".join(f"- Hỏi: {f['question']} | Đáp: {f['answer']}" for f in faq[:5])
        parts.append(
            "Câu hỏi thường gặp Giảng viên đã trả lời sẵn (ưu tiên tham khảo nếu khớp câu hỏi hiện tại):\n" + faq_text
        )
    return "\n\n".join(parts)


def generate_explanation(
    llm_integration: Any,
    question: str,
    course_id: str,
    lesson_id: str,
    topic_id: Optional[str],
    explanation_level: str,
    socratic_mode: bool = False,
    top_k: int = 5,
    mode: str = CMS_ONLY,
    active_misconception: Optional[Dict[str, str]] = None,
    is_final_synthesis_step: bool = False,
    user_id: Optional[str] = None,
    role: str = "Sinh viên",
) -> ExplanationResult:
    """`mode`: CMS_ONLY (mặc định, Mục 3) chỉ trả lời trong phạm vi CMS;
    CMS_PLUS_SUPPLEMENTARY CHỈ được dùng sau khi người dùng đã CHỦ ĐỘNG chọn
    'Giải thích với kiến thức bổ sung' ở UI — hàm này không tự ý bật chế độ đó.
    Mọi output đều đi qua learning_explainer_policy trước khi trả về (Mục 2) —
    không chỉ dựa vào system prompt."""
    from dss.services import engine_gateway

    if engine_gateway.enabled():
        cached = engine_gateway.get_cached_explanation(course_id, lesson_id)
        return ExplanationResult(
            has_cms_content=cached.get("state") == "READY",
            answer=cached["text"],
            explanation_level=explanation_level,
            citations=[],
            hallucinated_citations=[],
            used_socratic_mode=False,
        )

    lesson = cms_repository.get_lesson(lesson_id)
    if not lesson or not lesson.ai_enabled:
        return ExplanationResult(
            has_cms_content=False,
            answer="AI giải thích bài học hiện chưa được Giảng viên bật cho bài học này.",
            explanation_level=explanation_level,
            citations=[],
            hallucinated_citations=[],
            used_socratic_mode=socratic_mode,
        )

    chunks = cms_repository.retrieve_lesson_content(
        llm_integration,
        question,
        course_id=course_id,
        lesson_id=lesson_id,
        topic_id=topic_id,
        top_k=top_k,
    )
    if not chunks:
        return ExplanationResult(
            has_cms_content=False,
            answer=NO_CMS_CONTENT_MESSAGE,
            explanation_level=explanation_level,
            citations=[],
            hallucinated_citations=[],
            used_socratic_mode=socratic_mode,
        )

    system_prompt = build_system_prompt(
        explanation_level,
        socratic_mode,
        lesson.explanation_notes,
        lesson.faq,
        mode=mode,
        active_misconception=active_misconception,
    )
    prompt = prompt_security.build_secure_rag_prompt(
        system_instructions=system_prompt,
        student_context=f"Đang học bài: {lesson.title} (môn {course_id})",
        retrieved_chunks=chunks,
        user_query=question,
    )

    from dss.services import llm_service

    chat_auto = llm_service.resolve_auto_provider(llm_integration)
    if not chat_auto:
        answer = (
            "AI trực tuyến hiện chưa sẵn sàng, chưa thể giải thích câu hỏi mở này. "
            "Bạn có thể xem lại tài liệu bài giảng gốc trong lúc chờ hệ thống AI khả dụng."
        )
        return ExplanationResult(
            has_cms_content=True,
            answer=answer,
            explanation_level=explanation_level,
            citations=[_format_friendly_citation(c) for c in chunks],
            hallucinated_citations=[],
            used_socratic_mode=socratic_mode,
        )

    kwargs = {"model_name": chat_auto["model_name"]}
    if chat_auto["provider_key"] in ("gemini", "groq", "openai"):
        kwargs["api_key"] = chat_auto["api_key"]
    elif chat_auto["provider_key"] == "ollama":
        from dss.core.models import ollama_base_url

        kwargs["base_url"] = ollama_base_url()

    from dss.core.logging_config import get_logger

    def _ask_once() -> str:
        from dss.services.llm_gateway import LLMGateway

        stream = LLMGateway(llm_integration).stream_generate(
            prompt=prompt,
            user_id=user_id or "anonymous_student",
            role=role,
            request_type="learning_explainer",
            provider=chat_auto["provider_key"],
            model=chat_auto.get("model_name") or "default",
            **kwargs,
        )
        return "".join(stream)

    try:
        answer = _ask_once()
        # Model đôi khi trả về RỖNG (đã gặp thật: giao diện hiện 1 ô trả lời trống
        # chỉ có nhãn nguồn) — hỏi lại 1 lần trước khi báo lỗi.
        if not answer.strip():
            get_logger(__name__).warning(
                "AI Learning Explainer trả về rỗng (provider=%s) — hỏi lại 1 lần", chat_auto["provider_key"]
            )
            answer = _ask_once()
        if not answer.strip():
            answer = (
                "⚠️ AI chưa tạo được câu trả lời cho câu hỏi này. Vui lòng hỏi lại hoặc diễn đạt câu hỏi theo cách khác."
            )
    except Exception:
        get_logger(__name__).exception("Lỗi khi gọi AI Learning Explainer")
        answer = "⚠️ Không thể tạo giải thích lúc này. Vui lòng thử lại sau."

    citation_check = citation_service.verify_citations(answer, chunks)
    friendly_citations = [_format_friendly_citation(c) for c in chunks]
    hallucinated = citation_check.get("hallucinated_citations", [])

    # MỤC 2 — Kiểm chứng tất định (không chỉ tin system prompt): tự sửa nếu có
    # thể (vd. rơi vào trường hợp "không có CMS content" mà LLM vẫn cố bịa),
    # ghi lại vi phạm để phục vụ giám sát chất lượng (không chặn người dùng).
    policy_check = policy.validate_explanation_response(
        answer,
        has_cms_content=True,
        hallucinated_citations=hallucinated,
        mode=mode,
        supplementary_requested=(mode == CMS_PLUS_SUPPLEMENTARY),
        socratic_mode=socratic_mode,
        is_final_synthesis_step=is_final_synthesis_step,
    )
    if policy_check.repaired_answer:
        answer = policy_check.repaired_answer
    if not policy_check.is_valid:
        from dss.core.logging_config import get_logger

        get_logger(__name__).warning(
            "Policy violation trong AI Learning Explainer: %s", [v.to_dict() for v in policy_check.violations]
        )

    return ExplanationResult(
        has_cms_content=True,
        answer=answer,
        explanation_level=explanation_level,
        citations=friendly_citations,
        hallucinated_citations=hallucinated,
        used_socratic_mode=socratic_mode,
    )


# ============================================================================
# MỤC 4 — SOCRATIC SESSION có trạng thái THẬT (không phải bật/tắt 1 cờ rồi hỏi
# đáp rời rạc): mỗi lượt tiến 1 bước qua state machine, có lịch sử, hint_count,
# misconception phát hiện giữa chừng, trạng thái hoàn thành.
# ============================================================================
@dataclass
class SocraticSession:
    topic_id: str
    current_step: int = 0
    history: List[Dict[str, Optional[str]]] = field(
        default_factory=list
    )  # [{"question":.., "learner_answer":.., "ai_response":..}]
    misconception: Optional[Dict[str, str]] = None
    hint_count: int = 0
    completion_status: str = "IN_PROGRESS"  # IN_PROGRESS | COMPLETED | GAVE_UP


def start_socratic_session(topic_id: str) -> SocraticSession:
    return SocraticSession(topic_id=topic_id)


_SOCRATIC_ACTION_INSTRUCTIONS = {
    "start": "Hãy đặt MỘT câu hỏi gợi mở đầu tiên về chủ đề này để dẫn dắt học sinh tự suy luận — CHƯA đưa ra bất kỳ kết luận/đáp án nào.",
    "hint": "Học sinh đang gặp khó khăn với câu hỏi gợi mở trước. Hãy đưa ra MỘT gợi ý (hint) nhỏ, KHÔNG tiết lộ đáp án, để giúp học sinh tự suy ra tiếp.",
    "explain_more": "Học sinh muốn được giải thích thêm một chút trước khi tiếp tục — hãy làm rõ thêm bối cảnh câu hỏi gợi mở trước (VẪN chưa tiết lộ đáp án cuối), rồi hỏi lại câu hỏi gợi mở.",
}


def advance_socratic_session(
    llm_integration: Any,
    session: SocraticSession,
    action: str,
    course_id: str,
    lesson_id: str,
    explanation_level: str,
    learner_answer: Optional[str] = None,
    top_k: int = 5,
    user_id: Optional[str] = None,
    role: str = "Sinh viên",
) -> Tuple[SocraticSession, ExplanationResult]:
    """Tiến 1 bước thật của phiên Socratic. action:
    "start" | "answer" (kèm learner_answer) | "hint" | "explain_more" |
    "give_up" | "show_full_explanation" (2 action cuối kết thúc phiên với giải
    thích ĐẦY ĐỦ, is_final_synthesis_step=True nên KHÔNG bị policy Rule C chặn)."""
    lesson = cms_repository.get_lesson(lesson_id)
    topic_for_misconception = session.topic_id or (lesson.title if lesson else "")

    if action == "answer" and learner_answer:
        misconception = detect_misconception(topic_for_misconception, learner_answer)
        if misconception:
            session.misconception = misconception
        question = (
            f"Học sinh vừa trả lời câu hỏi gợi mở trước như sau: \"{learner_answer}\". "
            "Hãy đánh giá ngắn gọn câu trả lời này (đúng hướng / còn thiếu / có ngộ nhận), KHÔNG tiết lộ đáp án "
            "cuối cùng, sau đó đặt tiếp MỘT câu hỏi gợi mở kế tiếp để dẫn học sinh tiến gần hơn tới hiểu đúng."
        )
        is_final = False
        session.current_step += 1
    elif action == "hint":
        session.hint_count += 1
        question = _SOCRATIC_ACTION_INSTRUCTIONS["hint"]
        is_final = False
    elif action == "explain_more":
        question = _SOCRATIC_ACTION_INSTRUCTIONS["explain_more"]
        is_final = False
    elif action in ("give_up", "show_full_explanation"):
        session.completion_status = "GAVE_UP" if action == "give_up" else "COMPLETED"
        question = (
            "Học sinh muốn xem giải thích đầy đủ ngay bây giờ. Hãy tổng hợp và đưa ra giải thích ĐẦY ĐỦ, rõ ràng, "
            "trực tiếp trả lời câu hỏi/chủ đề đang thảo luận."
        )
        is_final = True
    else:  # "start" hoặc giá trị không nhận diện -> coi như khởi động phiên
        question = _SOCRATIC_ACTION_INSTRUCTIONS["start"]
        is_final = False

    result = generate_explanation(
        llm_integration,
        question,
        course_id,
        lesson_id,
        session.topic_id,
        explanation_level,
        socratic_mode=not is_final,
        top_k=top_k,
        active_misconception=session.misconception,
        is_final_synthesis_step=is_final,
        user_id=user_id,
        role=role,
    )

    session.history.append({"question": question, "learner_answer": learner_answer, "ai_response": result.answer})
    if is_final and session.completion_status == "IN_PROGRESS":
        session.completion_status = "COMPLETED"
    return session, result


# ============================================================================
# MỤC 10 — SINH QUIZ TỪ CMS (tái dùng diagnostic_assessment.py, không viết lại)
# ============================================================================
def generate_lesson_quiz_from_chunks(
    lesson_id: str, chunks: List[Dict[str, Any]], num_questions: int = 3, is_high_stakes: bool = False
):
    """Sinh quiz chẩn đoán từ ĐÚNG các chunk CMS đã truy xuất được cho lesson này
    (gọi sau generate_explanation/retrieve_lesson_content để tái dùng kết quả,
    tránh truy xuất lại 2 lần)."""
    from dss.services.diagnostic_assessment import DiagnosticAssessmentService

    lesson = cms_repository.get_lesson(lesson_id)
    if not lesson:
        return None
    approved_docs = [
        {
            "id": c.get("chunk_id") or c.get("document_id"),
            "title": c.get("title", lesson.title),
            "content": c.get("content", ""),
            "status": "APPROVED" if lesson.official_source else "PENDING_REVIEW",
            "source_verified": lesson.official_source,
        }
        for c in chunks
    ]
    service = DiagnosticAssessmentService()
    return service.create_assessment_blueprint(
        topic=lesson.title,
        suspected_weakness=f"Kiểm tra hiểu bài: {lesson.title}",
        approved_docs=approved_docs,
        num_questions=num_questions,
        is_high_stakes=is_high_stakes,
    )


# ============================================================================
# MỤC 6 — QUY TRÌNH DUYỆT QUIZ: Sinh viên KHÔNG BAO GIỜ nhận quiz ở trạng thái
# PENDING_LECTURER_APPROVAL / REJECTED. Quiz do lesson.quiz_requires_approval
# quyết định có bắt buộc qua hàng đợi duyệt hay không (Mục 11).
# ============================================================================
def _load_quiz_queue() -> List[Dict[str, Any]]:
    quiz_review_path = _quiz_review_path()
    if not quiz_review_path.exists():
        return []
    try:
        with open(quiz_review_path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_quiz_queue(records: List[Dict[str, Any]]) -> None:
    quiz_review_path = _quiz_review_path()
    quiz_review_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = quiz_review_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, quiz_review_path)


def _blueprint_to_dict(blueprint) -> Dict[str, Any]:
    from dataclasses import asdict as _asdict

    return _asdict(blueprint)


def request_lesson_quiz(course_id: str, lesson_id: str, chunks: List[Dict[str, Any]], num_questions: int = 3):
    """Điểm gọi DUY NHẤT mà UI Sinh viên nên dùng để lấy quiz (thay vì gọi
    generate_lesson_quiz_from_chunks trực tiếp).

    - Nếu lesson KHÔNG yêu cầu duyệt (quiz_requires_approval=False): trả về
      blueprint sẵn sàng dùng ngay.
    - Nếu CÓ yêu cầu duyệt: kiểm tra hàng đợi trước — nếu đã có bản APPROVED
      gần nhất cho đúng lesson này thì tái dùng (đỡ phải chờ duyệt lại mỗi lần);
      nếu không, tạo 1 bản nháp mới, đẩy vào hàng đợi PENDING_LECTURER_APPROVAL
      và trả về None kèm thông báo — Sinh viên KHÔNG thấy câu hỏi ở trạng thái
      chưa duyệt."""
    lesson = cms_repository.get_lesson(lesson_id)
    if not lesson:
        return None, "Không tìm thấy bài học."

    if not lesson.quiz_allowed:
        return None, "Giảng viên chưa bật tính năng tạo quiz cho bài học này."

    if not lesson.quiz_requires_approval:
        blueprint = generate_lesson_quiz_from_chunks(
            lesson_id, chunks, num_questions=num_questions, is_high_stakes=False
        )
        return blueprint, None

    approved = get_latest_approved_quiz(lesson_id)
    if approved is not None:
        return approved, None

    if any(r["lesson_id"] == lesson_id and r["status"] == "PENDING_LECTURER_APPROVAL" for r in _load_quiz_queue()):
        return None, "Quiz cho bài học này đang chờ Giảng viên duyệt — vui lòng quay lại sau."

    blueprint = generate_lesson_quiz_from_chunks(lesson_id, chunks, num_questions=num_questions, is_high_stakes=True)
    with _QUIZ_LOCK:
        records = _load_quiz_queue()
        records.append(
            {
                "queue_id": f"quizq_{uuid.uuid4().hex[:12]}",
                "course_id": course_id,
                "lesson_id": lesson_id,
                "blueprint": _blueprint_to_dict(blueprint),
                "status": "PENDING_LECTURER_APPROVAL",
                "submitted_at": datetime.now(UTC).isoformat(),
            }
        )
        _save_quiz_queue(records)
    return None, "Quiz mới đã được tạo và gửi cho Giảng viên duyệt — vui lòng quay lại sau."


def list_pending_quizzes(course_id: Optional[str] = None) -> List[Dict[str, Any]]:
    records = [r for r in _load_quiz_queue() if r["status"] == "PENDING_LECTURER_APPROVAL"]
    if course_id:
        records = [r for r in records if r["course_id"] == course_id]
    return records


def get_latest_approved_quiz(lesson_id: str) -> Optional[Any]:
    from dss.services.diagnostic_assessment import AssessmentBlueprint, DiagnosticQuestion

    records = [r for r in _load_quiz_queue() if r["lesson_id"] == lesson_id and r["status"] == "APPROVED"]
    if not records:
        return None
    latest = max(records, key=lambda r: r["blueprint"].get("version", 1))
    bp_dict = dict(latest["blueprint"])
    bp_dict["questions"] = [DiagnosticQuestion(**q) for q in bp_dict.get("questions", [])]
    return AssessmentBlueprint(**bp_dict)


def review_quiz(
    queue_id: str,
    decision: str,
    reviewer_id: str,
    comment: str = "",
    edited_questions: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """decision: "APPROVE" | "REJECT" | "EDIT" (EDIT thay câu hỏi rồi APPROVE,
    tăng version). Ghi reviewed_by/reviewed_at/review_comment/version — trung
    thực lưu vết ai duyệt, khi nào, vì sao (Mục 6)."""
    if decision not in ("APPROVE", "REJECT", "EDIT"):
        raise ValueError(f"decision không hợp lệ: {decision}")
    with _QUIZ_LOCK:
        records = _load_quiz_queue()
        target = next((r for r in records if r["queue_id"] == queue_id), None)
        if not target:
            return False
        if decision == "EDIT" and edited_questions is not None:
            target["blueprint"]["questions"] = edited_questions
            target["blueprint"]["version"] = target["blueprint"].get("version", 1) + 1
        target["status"] = "APPROVED" if decision in ("APPROVE", "EDIT") else "REJECTED"
        target["blueprint"]["status"] = target["status"]
        target["blueprint"]["reviewed_by"] = reviewer_id
        target["blueprint"]["reviewed_at"] = datetime.now(UTC).isoformat()
        target["blueprint"]["review_comment"] = comment
        _save_quiz_queue(records)
    return True


# ============================================================================
# MỤC 8 — MisconceptionRecord có cấu trúc, tồn tại lâu dài, ảnh hưởng tới các
# giải thích SAU này (không chỉ phát hiện 1 lần rồi quên).
# ============================================================================
def _load_misconception_store() -> List[Dict[str, Any]]:
    misconception_path = _misconception_store_path()
    if not misconception_path.exists():
        return []
    try:
        with open(misconception_path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_misconception_store(records: List[Dict[str, Any]]) -> None:
    misconception_path = _misconception_store_path()
    misconception_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = misconception_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, misconception_path)


def record_misconception(
    student_pseudonym: str, course_id: str, topic_id: str, misconception_type: str, evidence: str, hint: str = ""
) -> None:
    """Cập nhật (không nhân bản) 1 MisconceptionRecord: nếu ngộ nhận CÙNG loại
    cho ĐÚNG sinh viên+topic đã tồn tại và CHƯA resolved, tăng occurrence_count
    và cập nhật last_detected_at; nếu chưa có, tạo bản ghi mới.
    `misconception_type` = nhãn ngộ nhận (label từ detect_misconception), dùng
    làm khoá định danh loại ngộ nhận theo đúng schema Mục 8."""
    with _MISCONCEPTION_LOCK:
        records = _load_misconception_store()
        now = datetime.now(UTC).isoformat()
        existing = next(
            (
                r
                for r in records
                if r["student_pseudonym"] == student_pseudonym
                and r["course_id"] == course_id
                and r["topic_id"] == topic_id
                and r["misconception_type"] == misconception_type
                and r["resolved_status"] == "UNRESOLVED"
            ),
            None,
        )
        if existing:
            existing["occurrence_count"] += 1
            existing["last_detected_at"] = now
        else:
            records.append(
                {
                    "record_id": f"misc_{uuid.uuid4().hex[:12]}",
                    "student_pseudonym": student_pseudonym,
                    "course_id": course_id,
                    "topic_id": topic_id,
                    "misconception_type": misconception_type,
                    "evidence": evidence,
                    "hint": hint,
                    "first_detected_at": now,
                    "last_detected_at": now,
                    "occurrence_count": 1,
                    "resolved_status": "UNRESOLVED",
                    "resolution_evidence": None,
                }
            )
        _save_misconception_store(records)


def resolve_misconception(
    student_pseudonym: str, course_id: str, topic_id: str, misconception_type: str, resolution_evidence: str
) -> None:
    """Đánh dấu đã khắc phục — vd sau khi Sinh viên trả lời đúng câu hỏi liên
    quan chính xác ngộ nhận đó (gọi từ vòng phản hồi quiz, Mục 9)."""
    with _MISCONCEPTION_LOCK:
        records = _load_misconception_store()
        now = datetime.now(UTC).isoformat()
        changed = False
        for r in records:
            if (
                r["student_pseudonym"] == student_pseudonym
                and r["course_id"] == course_id
                and r["topic_id"] == topic_id
                and r["misconception_type"] == misconception_type
                and r["resolved_status"] == "UNRESOLVED"
            ):
                r["resolved_status"] = "RESOLVED"
                r["resolution_evidence"] = resolution_evidence
                r["last_detected_at"] = now
                changed = True
        if changed:
            _save_misconception_store(records)


def get_active_misconception(student_pseudonym: str, course_id: str, topic_id: str) -> Optional[Dict[str, Any]]:
    """Trả về ngộ nhận CHƯA resolved gần đây nhất (nếu có) cho đúng sinh
    viên+topic — dùng làm active_misconception truyền vào build_system_prompt()
    để AI CHỦ ĐỘNG phân biệt lại khái niệm đã từng bị nhầm, theo hướng sư phạm
    (không nói kiểu 'tôi nhớ bạn đã sai' — chỉ nhắc khéo trong system prompt)."""
    records = [
        r
        for r in _load_misconception_store()
        if r["student_pseudonym"] == student_pseudonym
        and r["course_id"] == course_id
        and r["topic_id"] == topic_id
        and r["resolved_status"] == "UNRESOLVED"
    ]
    if not records:
        return None
    latest = max(records, key=lambda r: r["last_detected_at"])
    return {**latest, "label": latest["misconception_type"], "hint": latest.get("hint", "")}


# ============================================================================
# MỤC 12 — VÒNG PHẢN HỒI LMS (ghi log tương tác — nền cho Mục 13 Lecturer View)
# ============================================================================
def _load_interaction_log() -> List[Dict[str, Any]]:
    interaction_log_path = _interaction_log_path()
    if not interaction_log_path.exists():
        return []
    try:
        with open(interaction_log_path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_interaction_log(records: List[Dict[str, Any]]) -> None:
    interaction_log_path = _interaction_log_path()
    interaction_log_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = interaction_log_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, interaction_log_path)


def log_interaction(
    student_pseudonym: str,
    course_id: str,
    lesson_id: str,
    topic_id: Optional[str],
    question: str,
    explanation_level: str,
    has_cms_content: bool,
    misconception: Optional[Dict[str, str]] = None,
    quiz_correct: Optional[bool] = None,
) -> None:
    """Ghi nhận 1 lượt tương tác — KHÔNG lưu private chat nguyên văn nếu policy
    không cho phép (Mục 13): chỉ lưu CÂU HỎI (để thống kê topic hay hỏi) và các
    cờ tổng hợp, không lưu answer đầy đủ."""
    record = {
        "interaction_id": f"int_{uuid.uuid4().hex[:12]}",
        "student_pseudonym": student_pseudonym,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "topic_id": topic_id,
        "question": question[:300],
        "explanation_level": explanation_level,
        "has_cms_content": has_cms_content,
        "misconception_label": misconception["label"] if misconception else None,
        "quiz_correct": quiz_correct,
        "created_at": datetime.now(UTC).isoformat(),
    }
    with _LOG_LOCK:
        records = _load_interaction_log()
        records.append(record)
        if len(records) > 20_000:
            records = records[-20_000:]
        _save_interaction_log(records)


# ============================================================================
# MỤC 13 — LECTURER VIEW (aggregate analytics, KHÔNG hiện chat nguyên văn)
# ============================================================================
def get_lecturer_analytics(course_id: str) -> Dict[str, Any]:
    records = [r for r in _load_interaction_log() if r.get("course_id") == course_id]
    if not records:
        return {"total_questions": 0, "top_topics": [], "top_questions": [], "misconceptions": [], "no_cms_rate": 0.0}

    from collections import Counter

    topic_counter = Counter(r.get("lesson_id") for r in records if r.get("lesson_id"))
    question_counter = Counter(r.get("question", "").strip().lower() for r in records if r.get("question"))
    misconception_counter = Counter(r.get("misconception_label") for r in records if r.get("misconception_label"))
    no_cms_count = sum(1 for r in records if not r.get("has_cms_content"))

    return {
        "total_questions": len(records),
        "top_topics": topic_counter.most_common(5),
        "top_questions": question_counter.most_common(5),
        "misconceptions": misconception_counter.most_common(5),
        "no_cms_rate": round(no_cms_count / len(records), 3),
    }
