"""AI Decision Audit Log — FINAL REMAINING-GAPS CLOSURE, Section 10.

Trước đợt này: audit cho các quyết định AI/decision-engine bị PHÂN MẢNH
giữa `audit_log_repository.py` (audit mutation chung, vd. Promote/Rollback
model — không có trường AI-specific nào) và `token_tracker.py` (chi phí/
token — không có correlation_id/tier/rule/regulation/RAG-doc-IDs). Không
nơi nào có ĐỦ để trả lời "cho tôi xem mọi thứ về correlation_id X: tier
nào, rule/regulation nào, RAG doc nào, Validator nói gì, fallback path
nào" trong 1 bản ghi.

Module này HỢP NHẤT — KHÔNG viết 1 đường ghi DB song song mới, mà TÁI SỬ
DỤNG `audit_log_repository.record()` (đã có, đã test, best-effort/không
raise) với 1 payload đầy đủ, có cấu trúc, đóng vai trò "canonical decision-
event contract" mà Section 10 yêu cầu."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional


@dataclass
class AIDecisionAuditEvent:
    correlation_id: str
    tenant_id: Optional[str]
    actor_ref: str  # định danh giả danh (pseudonym) — KHÔNG BAO GIỜ mã số sinh viên thật
    role: str
    intent: str
    tier: Optional[int]
    tools_used: List[str] = field(default_factory=list)
    calculator_version: Optional[str] = None
    rule_id: Optional[str] = None
    rule_version: Optional[int] = None
    regulation_id: Optional[str] = None
    regulation_version: Optional[int] = None
    model_id: Optional[str] = None
    rag_document_ids: List[str] = field(default_factory=list)
    provider: Optional[str] = None
    llm_used: bool = False
    fallback_type: Optional[str] = None
    validator_status: Optional[str] = None
    latency_ms: Optional[float] = None
    token_usage: Optional[dict] = None
    final_status: str = "unknown"


def emit(event: AIDecisionAuditEvent) -> bool:
    """Ghi 1 sự kiện quyết định AI — best-effort, KHÔNG BAO GIỜ raise/chặn
    luồng gọi (tái sử dụng bảo đảm này từ `audit_log_repository.record()`
    gốc). KHÔNG ghi password/secret/access_token/API key — dataclass ở
    trên không có field nào cho các giá trị đó (xem
    `test_never_includes_password_secret_or_token_fields`)."""
    from dss.db.repositories import audit_log_repository

    tenant_int: Optional[int] = None
    if event.tenant_id is not None:
        try:
            tenant_int = int(event.tenant_id)
        except (TypeError, ValueError):
            tenant_int = None

    return audit_log_repository.record(
        action="ai.decision",
        target_type="ai_decision_event",
        target_id=event.correlation_id,
        actor_username=event.actor_ref,
        organization_id=tenant_int,
        after=asdict(event),
    )
