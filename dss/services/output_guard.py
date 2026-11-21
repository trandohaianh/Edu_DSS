"""Chặn lời khuyên có hại trong CÂU TRẢ LỜI của Trợ lý AI trước khi tới người dùng.

Trước 21/11/2026, bộ phát hiện (`llm_evaluator.detect_harmful_or_unsupported_advice`:
từ khoá + bộ phân loại học được) chỉ chạy trong `evals/`, không đường nào trong app gọi
nó với câu trả lời thật. Module này gắn nó vào luồng trả lời:

- Sinh viên: gom TOÀN BỘ câu trả lời, kiểm tra rồi mới hiện (không để câu có hại lộ ra
  dù chỉ vài giây khi đang stream). Bị gắn cờ → thay bằng thông báo an toàn.
- Giảng viên / Admin: vẫn stream như cũ; bị gắn cờ → nối nhãn cảnh báo ở cuối để người
  tư vấn biết không chuyển nguyên văn cho sinh viên.

Kiểm tra TỪNG CÂU (bộ phân loại được huấn luyện trên câu đơn; chấm cả đoạn dài làm loãng
tín hiệu). Nhật ký sự cố không chứa nội dung câu trả lời hay mã sinh viên.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

STUDENT_ROLE = "Sinh viên"
# Câu trạng thái do chính hệ thống sinh ra (hết hạn mức, lỗi provider...) — không phải lời khuyên.
_SYSTEM_PREFIXES = ("⚠️", "🔒", "⏳", "Lỗi ", "Mã sự cố")
_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_BULLET_RE = re.compile(r"^\s*(?:[-*•+]|\d+[.)]|#+)\s*")

BLOCKED_MESSAGE = (
    "⚠️ **Câu trả lời của Trợ lý AI đã bị ẩn** vì có nội dung có thể gây hại cho sức khoẻ "
    "hoặc vi phạm quy chế học tập.\n\n"
    "Em có thể:\n"
    "- dùng **Kế hoạch học tập** (tạo theo dữ liệu của em, không cần AI);\n"
    "- đặt lại câu hỏi theo cách khác;\n"
    "- hoặc trao đổi trực tiếp với cố vấn học tập.\n\n"
    "Nếu em đang rất căng thẳng hoặc có ý nghĩ làm hại bản thân, hãy liên hệ ngay phòng tư vấn "
    "tâm lý của trường hoặc người thân."
)
STAFF_WARNING = (
    "\n\n---\n⚠️ **Cảnh báo an toàn:** bộ lọc phát hiện {n} câu có thể là lời khuyên có hại "
    "(sức khoẻ hoặc gian lận). Không chuyển nguyên văn câu trả lời này cho sinh viên."
)


@dataclass
class GuardResult:
    is_harmful: bool
    flagged_sentences: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    # Số câu bị gắn cờ MẠNH (khớp từ khoá, hoặc bộ phân loại ≥ STRONG_CLASSIFIER_SCORE). Chỉ cờ mạnh
    # mới được tính để ẩn TOÀN BỘ câu trả lời; cờ yếu chỉ làm ẩn đúng câu đó.
    strong_count: int = 0


# Bộ phân loại cho điểm 0,5–0,65 với cả một số câu an toàn lạ (câu rất ngắn, ký hiệu, chữ in hoa),
# nên cờ chỉ đến từ bộ phân loại với điểm dưới mức này là "yếu" (21/11/2026).
STRONG_CLASSIFIER_SCORE = 0.65
_SCORE_RE = re.compile(r"xác suất có hại ([0-9.]+)")


def _is_strong(issues: list[str]) -> bool:
    for issue in issues:
        m = _SCORE_RE.search(issue)
        if m is None or float(m.group(1)) >= STRONG_CLASSIFIER_SCORE:
            return True  # cờ từ khoá, hoặc bộ phân loại đủ chắc
    return False


def split_sentences(text: str) -> list[str]:
    parts = []
    for raw in _SPLIT_RE.split(text or ""):
        s = _BULLET_RE.sub("", raw).strip(" *_`>\t")
        if len(s) >= 8 and not s.startswith(_SYSTEM_PREFIXES):
            parts.append(s)
    return parts


def check_answer(text: str) -> GuardResult:
    """Kiểm tra một câu trả lời hoàn chỉnh. Lỗi của bộ phát hiện → coi như an toàn và ghi log
    (lớp chặn đầu vào và hạn mức vẫn hoạt động), không làm hỏng luồng trả lời."""
    from dss.services.llm_evaluator import detect_harmful_or_unsupported_advice

    flagged: list[str] = []
    issues: list[str] = []
    strong = 0
    try:
        for sentence in split_sentences(text):
            harmful, found = detect_harmful_or_unsupported_advice(sentence)
            if harmful:
                flagged.append(sentence)
                issues.extend(found)
                strong += int(_is_strong(found))
    except Exception:
        _logger.exception("output_guard: bộ phát hiện lời khuyên có hại lỗi — bỏ qua kiểm tra lượt này.")
        return GuardResult(False)
    return GuardResult(bool(flagged), flagged, issues, strong)


def _log_incident(role: str, request_type: str, result: GuardResult) -> None:
    # KHÔNG ghi nội dung câu hay định danh người dùng — chỉ số lượng và loại phát hiện.
    kinds = sorted({i.split(":")[0] for i in result.issues})
    _logger.warning(
        "output_guard: chặn/gắn cờ câu trả lời AI (role=%s, request_type=%s, so_cau=%d, loai=%s)",
        role,
        request_type,
        len(result.flagged_sentences),
        ",".join(kinds),
    )


# Sinh viên: ẩn TOÀN BỘ câu trả lời khi bị gắn cờ nhiều (≥ 3 câu hoặc ≥ 30% số câu); ít hơn thì
# chỉ ẩn đúng các câu bị gắn cờ, giữ phần còn lại (bộ phân loại vẫn gắn nhầm vài % câu an toàn —
# ẩn cả kế hoạch 30 câu vì 1 câu nhầm sẽ làm sinh viên mất câu trả lời hợp lệ quá thường xuyên).
BLOCK_ALL_MIN_SENTENCES = 3
BLOCK_ALL_MIN_RATIO = 0.30
REDACTED_SENTENCE = "*(Đã ẩn một câu không phù hợp.)*"
REDACTION_NOTICE = (
    "⚠️ *Đã ẩn {n} câu trong câu trả lời của Trợ lý AI vì có thể gây hại cho sức khoẻ hoặc vi phạm "
    "quy chế học tập. Phần còn lại vẫn hiển thị bên dưới.*\n\n"
)


def redact_for_student(text: str, result: GuardResult) -> str | None:
    """Ẩn đúng các câu bị gắn cờ trong văn bản gốc (giữ định dạng). Trả None nếu phải ẩn toàn bộ
    (gắn cờ nhiều, hoặc không định vị được câu trong văn bản gốc)."""
    total = max(1, len(split_sentences(text)))
    n = len(result.flagged_sentences)
    strong = result.strong_count
    if strong >= BLOCK_ALL_MIN_SENTENCES or (strong and strong / total >= BLOCK_ALL_MIN_RATIO):
        return None
    redacted = text
    for sentence in result.flagged_sentences:
        if sentence not in redacted:
            return None
        redacted = redacted.replace(sentence, REDACTED_SENTENCE)
    return REDACTION_NOTICE.format(n=n) + redacted


def guard_stream(stream: Iterable[str], role: str, request_type: str = "advisor") -> Iterator[str]:
    """Bọc một luồng trả lời của AI bằng bộ lọc lời khuyên có hại (xem docstring module)."""
    if role == STUDENT_ROLE:
        text = "".join(str(c) for c in stream)
        result = check_answer(text)
        if result.is_harmful:
            _log_incident(role, request_type, result)
            redacted = redact_for_student(text, result)
            yield BLOCKED_MESSAGE if redacted is None else redacted
            return
        if text:
            yield text
        return

    parts: list[str] = []
    for chunk in stream:
        parts.append(str(chunk))
        yield chunk
    result = check_answer("".join(parts))
    if result.is_harmful:
        _log_incident(role, request_type, result)
        yield STAFF_WARNING.format(n=len(result.flagged_sentences))
