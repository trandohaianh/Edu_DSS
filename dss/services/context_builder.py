"""Context Builder — FINAL REMAINING-GAPS CLOSURE, Section 6.

Xây dựng ngữ cảnh TỐI THIỂU, đã được ủy quyền, cho mỗi intent trước khi
gửi vào Agent/LLM — KHÔNG BAO GIỜ truyền thẳng 1 Student object/DB row
nguyên bản. Mỗi intent có hợp đồng REQUIRED/OPTIONAL/FORBIDDEN tường minh
(Section 6 của master prompt).

QUAN TRỌNG (trung thực về phạm vi): module này CHỈ định nghĩa hợp đồng và
lọc field — nó KHÔNG tự lấy dữ liệu từ DB/session (đó là việc của tầng gọi,
vd. `ai_advisor.py`/`agent.py`). Đây là bước lọc CUỐI CÙNG trước khi dữ liệu
rời khỏi tầng ứng dụng, không phải nơi resolve quyền truy cập (đó là việc
của Authorization — chưa có trong đợt này, xem AGENT_FINAL_INTEGRATION.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set

_COMMON_FORBIDDEN = {
    "name", "email", "phone", "address", "dob", "full_transcript", "full_chat_history",
    # C1.1: định danh trực tiếp của sinh viên không bao giờ đi vào ngữ cảnh gửi ra ngoài.
    "student_id", "student_code", "mssv", "id_card", "national_id", "username",
}

_INTENT_FIELD_CONTRACTS: Dict[str, Dict[str, Set[str]]] = {
    "GPA_CALCULATION": {
        "required": {"current_gpa", "credits_done", "target_gpa", "credits_remaining", "gpa_scale"},
        "optional": set(),
        "forbidden": _COMMON_FORBIDDEN,
    },
    "LEARNING_EXPLANATION": {
        "required": {"prediction", "model_version", "relevant_features", "shap_evidence"},
        "optional": {"minimal_academic_context"},
        "forbidden": _COMMON_FORBIDDEN,
    },
    "REGULATION_LOOKUP": {
        "required": {"organization_id", "program_id", "cohort", "regulation_version", "approved_evidence"},
        "optional": set(),
        "forbidden": _COMMON_FORBIDDEN,
    },
    "ACADEMIC_RULE_CHECK": {
        "required": {"organization_id", "credits_requested_or_status", "rule_id", "regulation_version"},
        "optional": {"approved_evidence"},
        "forbidden": _COMMON_FORBIDDEN,
    },
    "ADVISOR_PLAN": {
        "required": {"authorized_academic_summary"},
        "optional": {"goals", "regulation_context", "rule_results", "ml_results", "rag_evidence"},
        "forbidden": _COMMON_FORBIDDEN,
    },
}


@dataclass
class ContextBuildResult:
    intent: str
    context: dict = field(default_factory=dict)
    included_fields: Set[str] = field(default_factory=set)
    dropped_forbidden_fields: Set[str] = field(default_factory=set)
    missing_required_fields: Set[str] = field(default_factory=set)
    status: str = "ok"  # "ok" | "MISSING_REQUIRED"


def build_context(intent: str, raw_source: dict) -> ContextBuildResult:
    """Lọc `raw_source` (có thể là 1 dict/row THÔ từ DB/session) xuống ngữ
    cảnh tối thiểu theo hợp đồng REQUIRED/OPTIONAL/FORBIDDEN của `intent`.

    Intent không có hợp đồng riêng (chưa định nghĩa trong
    `_INTENT_FIELD_CONTRACTS`) vẫn KHÔNG được để lọt nguyên `raw_source` —
    fail-safe theo mặc định: chỉ loại các trường PII phổ biến
    (`_COMMON_FORBIDDEN`), không tự nhận đã lọc đúng cho intent đó."""
    contract = _INTENT_FIELD_CONTRACTS.get(intent)

    if contract is None:
        context = {k: v for k, v in raw_source.items() if k not in _COMMON_FORBIDDEN}
        return ContextBuildResult(
            intent=intent, context=context, included_fields=set(context.keys()),
            dropped_forbidden_fields=set(raw_source.keys()) & _COMMON_FORBIDDEN,
            missing_required_fields=set(), status="ok",
        )

    allowed = contract["required"] | contract["optional"]
    context = {k: v for k, v in raw_source.items() if k in allowed}
    dropped_forbidden = set(raw_source.keys()) & contract["forbidden"]
    missing_required = contract["required"] - set(context.keys())
    status = "ok" if not missing_required else "MISSING_REQUIRED"

    return ContextBuildResult(
        intent=intent, context=context, included_fields=set(context.keys()),
        dropped_forbidden_fields=dropped_forbidden, missing_required_fields=missing_required,
        status=status,
    )
