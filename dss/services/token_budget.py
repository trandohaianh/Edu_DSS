"""Token Budget — FINAL REMAINING-GAPS CLOSURE, Section 8.

Chính sách ngân sách context/token theo bounded, per-intent. Ưu tiên cắt an
toàn: hội thoại cũ trước, RAG chunk xếp hạng thấp sau — TUYỆT ĐỐI KHÔNG cắt
kết quả Calculator/Rule Engine/Regulation Resolver/Validator (những hàm
dưới đây không nhận tham số nào cho phép truyền các giá trị đó vào để bị
cắt nhầm — xem `test_trim_never_touches_deterministic_facts_dict`).

QUAN TRỌNG (trung thực về phạm vi): các con số ngân sách dưới đây là giá
trị KHỞI ĐIỂM hợp lý (không phải đo thực nghiệm từ traffic thật — chưa có
traffic thật để đo). Xem `docs/ai/CONTEXT_BUILDER_AND_TOKEN_BUDGET.md` để biết lý
do và khuyến nghị điều chỉnh khi có dữ liệu thật."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class TokenBudget:
    max_recent_turns: int
    max_summary_chars: int
    max_rag_chunks: int
    max_rag_chars: int
    max_structured_context_chars: int
    max_provider_output_tokens: int


@dataclass
class BudgetCheckResult:
    over_budget: bool
    size_chars: int
    limit_chars: int


_DEFAULT_BUDGET = TokenBudget(
    max_recent_turns=5, max_summary_chars=500, max_rag_chunks=4, max_rag_chars=2000,
    max_structured_context_chars=4000, max_provider_output_tokens=1024,
)

_INTENT_BUDGETS: Dict[str, TokenBudget] = {
    "GPA_CALCULATION": TokenBudget(0, 0, 0, 0, 500, 256),  # deterministic — no RAG/history needed at all
    "ACADEMIC_RULE_CHECK": TokenBudget(0, 0, 0, 0, 500, 256),
    "REGULATION_LOOKUP": TokenBudget(0, 0, 2, 1000, 500, 256),
    "DIRECT_DATA_LOOKUP": TokenBudget(0, 0, 0, 0, 300, 128),
    "RAG_QA": TokenBudget(3, 300, 5, 2500, 2000, 1024),
    "LEARNING_EXPLANATION": TokenBudget(3, 300, 0, 0, 1500, 1024),
    "ADVISOR_PLAN": TokenBudget(5, 500, 5, 2500, 4000, 2048),
    "ADVISOR_CHAT": TokenBudget(5, 500, 4, 2000, 3000, 1024),
}

# Ngân sách "bảo thủ" cho intent chưa định nghĩa riêng — KHÔNG unbounded,
# và tối đa bằng RAG_QA (không được rộng hơn 1 intent đã biết cụ thể).
_FALLBACK_BUDGET = TokenBudget(
    max_recent_turns=3, max_summary_chars=300, max_rag_chunks=3, max_rag_chars=1500,
    max_structured_context_chars=1500, max_provider_output_tokens=512,
)


def get_budget_for_intent(intent: str) -> TokenBudget:
    return _INTENT_BUDGETS.get(intent, _FALLBACK_BUDGET)


def trim_conversation_history(turns: List[dict], budget: TokenBudget) -> List[dict]:
    """Cắt LỊCH SỬ HỘI THOẠI (đã sanitize PII ở tầng gọi — hàm này không tự
    khử PII) xuống `max_recent_turns` lượt gần nhất. Thứ tự ưu tiên cắt: hội
    thoại cũ trước (giữ lại các lượt MỚI NHẤT)."""
    if budget.max_recent_turns <= 0:
        return []
    return turns[-budget.max_recent_turns:] if len(turns) > budget.max_recent_turns else list(turns)


def trim_rag_chunks(chunks: List[dict], budget: TokenBudget) -> List[dict]:
    """Cắt RAG chunks xuống `max_rag_chunks`, ưu tiên GIỮ chunk xếp hạng CAO
    (relevance_score cao hơn), cắt chunk xếp hạng THẤP trước."""
    if budget.max_rag_chunks <= 0:
        return []
    sorted_chunks = sorted(chunks, key=lambda c: c.get("relevance_score", 0), reverse=True)
    return sorted_chunks[: budget.max_rag_chunks]


def estimate_context_size_chars(text: str) -> int:
    """Ước lượng kích thước ngữ cảnh theo SỐ KÝ TỰ (không dùng tokenizer thật
    — chưa có tokenizer cụ thể theo provider được tích hợp trong đợt này;
    KHÔNG bịa số token, chỉ báo cáo ký tự thật)."""
    return len(text or "")


def check_structured_context_budget(structured_context: str, budget: TokenBudget) -> BudgetCheckResult:
    """Section 8: ngữ cảnh CÓ CẤU TRÚC (kết quả Calculator/Rule Engine/...)
    KHÔNG BAO GIỜ bị tự động cắt — hàm này chỉ BÁO CÁO khi vượt ngân sách
    (`over_budget=True`), để tầng gọi tự quyết định xử lý (vd. rút gọn định
    dạng hiển thị), KHÔNG tự ý xoá bớt nội dung xác định."""
    size = estimate_context_size_chars(structured_context)
    return BudgetCheckResult(
        over_budget=size > budget.max_structured_context_chars,
        size_chars=size, limit_chars=budget.max_structured_context_chars,
    )
