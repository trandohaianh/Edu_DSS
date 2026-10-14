"""Explanation Policy Layer — kiểm chứng ĐỊNH LƯỢNG (không chỉ dựa vào chỉ thị
trong system prompt) cho AI Learning Explainer. Mục 2/3.

Nguyên tắc: LLM có thể KHÔNG tuân thủ đúng 100% chỉ thị trong prompt — lớp này
kiểm tra output MỘT CÁCH TẤT ĐỊNH (regex/rule, không gọi LLM lần 2) và có thể
TỰ SỬA (repair) một số vi phạm rõ ràng thay vì chỉ báo lỗi.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CMS_ONLY = "CMS_ONLY"
CMS_PLUS_SUPPLEMENTARY = "CMS_PLUS_SUPPLEMENTARY"

NO_CMS_CONTENT_MESSAGE = (
    "Nội dung này chưa có trong tài liệu môn học hiện tại. Tôi có thể giải thích thêm bằng kiến thức bổ "
    "sung nếu bạn muốn — chỉ cần hỏi lại và ghi rõ bạn muốn nghe giải thích ngoài bài giảng."
)

_FROM_LECTURE_HEADING_RE = re.compile(r"(từ bài giảng|nội dung từ bài giảng|theo bài giảng)", re.IGNORECASE)
_SUPPLEMENTARY_HEADING_RE = re.compile(r"kiến thức bổ sung", re.IGNORECASE)

# Cụm từ "chốt đáp án ngay" — nếu xuất hiện Ở ĐẦU câu trả lời khi đang Socratic
# và CHƯA tới bước tổng hợp cuối, coi là vi phạm "không tiết lộ đáp án ngay".
_IMMEDIATE_ANSWER_RE = re.compile(
    r"^\s*(đáp án là|kết luận là|kết luận:|câu trả lời là|tóm lại,?\s*(đáp án|kết luận))", re.IGNORECASE,
)
_GUIDING_QUESTION_MARKERS = ("?", "em nghĩ", "bạn nghĩ", "theo em", "theo bạn")


@dataclass
class PolicyViolation:
    rule: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyCheckResult:
    is_valid: bool
    violations: List[PolicyViolation] = field(default_factory=list)
    repaired_answer: Optional[str] = None  # None nếu không cần/không thể tự sửa

    def to_dict(self) -> Dict[str, Any]:
        return {"is_valid": self.is_valid, "violations": [v.to_dict() for v in self.violations], "repaired_answer": self.repaired_answer}


# ----------------------------------------------------------------------------
# RULE A + E — CMS_ONLY: mọi khẳng định kiến thức phải truy vết được về CMS;
# nếu retrieval rỗng, KHÔNG được bịa — phải đúng nguyên văn thông báo honest.
# ----------------------------------------------------------------------------
def validate_cms_only(answer: str, has_cms_content: bool, hallucinated_citations: List[Dict[str, Any]]) -> PolicyCheckResult:
    violations: List[PolicyViolation] = []
    repaired: Optional[str] = None

    if not has_cms_content:
        core_phrase = "chưa có trong tài liệu môn học hiện tại"
        if core_phrase not in answer.lower():
            violations.append(PolicyViolation(
                "E_NO_FABRICATION",
                "Không có nội dung CMS phù hợp nhưng câu trả lời không phải thông báo honest chuẩn — nghi ngờ bịa nội dung bài giảng.",
            ))
            repaired = NO_CMS_CONTENT_MESSAGE  # SỬA CỨNG — không cho phép trả lời tự bịa lọt ra ngoài

    if hallucinated_citations:
        violations.append(PolicyViolation(
            "D_CITATION_UNSUPPORTED",
            f"{len(hallucinated_citations)} trích dẫn không khớp với tài liệu CMS đã truy xuất.",
        ))

    return PolicyCheckResult(is_valid=len(violations) == 0, violations=violations, repaired_answer=repaired)


# ----------------------------------------------------------------------------
# RULE B — CMS_PLUS_SUPPLEMENTARY: khi có kiến thức bổ sung, PHẢI tách nhãn rõ.
# ----------------------------------------------------------------------------
def validate_supplementary_separation(answer: str, mode: str, supplementary_requested: bool) -> PolicyCheckResult:
    if mode != CMS_PLUS_SUPPLEMENTARY or not supplementary_requested:
        return PolicyCheckResult(is_valid=True)

    has_lecture_marker = bool(_FROM_LECTURE_HEADING_RE.search(answer))
    has_supplementary_marker = bool(_SUPPLEMENTARY_HEADING_RE.search(answer))

    if not (has_lecture_marker and has_supplementary_marker):
        return PolicyCheckResult(
            is_valid=False,
            violations=[PolicyViolation(
                "B_MUST_LABEL_SUPPLEMENTARY",
                "Chế độ CMS_PLUS_SUPPLEMENTARY nhưng câu trả lời không tách rõ 2 phần 'Từ bài giảng' / 'Kiến thức bổ sung'.",
            )],
        )
    return PolicyCheckResult(is_valid=True)


# ----------------------------------------------------------------------------
# RULE C — Socratic: không tiết lộ đáp án ngay (trừ bước tổng hợp cuối/hoặc
# học sinh chủ động bấm "Hiện đáp án đầy đủ").
# ----------------------------------------------------------------------------
def validate_socratic_no_immediate_answer(answer: str, is_final_synthesis_step: bool) -> PolicyCheckResult:
    if is_final_synthesis_step:
        return PolicyCheckResult(is_valid=True)

    if _IMMEDIATE_ANSWER_RE.match(answer.strip()):
        return PolicyCheckResult(
            is_valid=False,
            violations=[PolicyViolation("C_SOCRATIC_LEAKED_ANSWER", "Câu trả lời tiết lộ đáp án ngay dù đang ở chế độ Socratic (chưa tới bước tổng hợp cuối).")],
        )

    has_guiding_question = any(marker in answer.lower() for marker in _GUIDING_QUESTION_MARKERS)
    if not has_guiding_question:
        return PolicyCheckResult(
            is_valid=False,
            violations=[PolicyViolation("C_SOCRATIC_MISSING_QUESTION", "Chế độ Socratic yêu cầu đặt câu hỏi gợi mở, nhưng câu trả lời không có câu hỏi nào cho học sinh.")],
        )
    return PolicyCheckResult(is_valid=True)


# ----------------------------------------------------------------------------
# ĐIỂM GỌI TỔNG HỢP — chạy mọi rule liên quan tuỳ theo ngữ cảnh, trả kết quả gộp.
# ----------------------------------------------------------------------------
def validate_explanation_response(
    answer: str,
    has_cms_content: bool,
    hallucinated_citations: List[Dict[str, Any]],
    mode: str = CMS_ONLY,
    supplementary_requested: bool = False,
    socratic_mode: bool = False,
    is_final_synthesis_step: bool = False,
) -> PolicyCheckResult:
    all_violations: List[PolicyViolation] = []
    final_answer = answer

    cms_check = validate_cms_only(answer, has_cms_content, hallucinated_citations)
    all_violations.extend(cms_check.violations)
    if cms_check.repaired_answer:
        final_answer = cms_check.repaired_answer

    supp_check = validate_supplementary_separation(final_answer, mode, supplementary_requested)
    all_violations.extend(supp_check.violations)

    if socratic_mode and has_cms_content:
        socratic_check = validate_socratic_no_immediate_answer(final_answer, is_final_synthesis_step)
        all_violations.extend(socratic_check.violations)

    return PolicyCheckResult(
        is_valid=len(all_violations) == 0,
        violations=all_violations,
        repaired_answer=final_answer if final_answer != answer else None,
    )
