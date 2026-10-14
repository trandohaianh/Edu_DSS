# AI Decision Audit Log

## Status: IMPLEMENTED_AND_TESTED (unified contract), wired into 1 of 4 tool orders

`dss/services/ai_decision_audit.py` provides the canonical `AIDecisionAuditEvent` contract Section 10 asks for — one record carrying `correlation_id`, `tenant_id`, `actor_ref` (pseudonymous), `role`, `intent`, `tier`, `tools_used`, `calculator_version`, `rule_id`/`rule_version`, `regulation_id`/`regulation_version`, `model_id`, `rag_document_ids`, `provider`, `llm_used`, `fallback_type`, `validator_status`, `latency_ms`, `token_usage`, `final_status`.

## Design choice: unify, don't duplicate

Rather than building a new database table + migration (a bigger, riskier change given this pass's time budget), `ai_decision_audit.emit()` **reuses** the existing, already-tested `audit_log_repository.record()` — the same function that already handles Promote/Rollback audit trails, already best-effort (never raises/blocks the caller when Postgres isn't configured, confirmed by a dedicated test), already RLS-protected via `organization_id`. The full `AIDecisionAuditEvent` is packed into the existing `after` JSON field with `action="ai.decision"`, `target_type="ai_decision_event"`, `target_id=correlation_id`.

## Wired into the real path, not standalone

`agent.py::run_gpa_calculation()` — the one tool order genuinely wired into the live Student chat path (`AGENT_FINAL_INTEGRATION.md`) — calls `_emit_audit_event()` at **both** exit points (the honest `INSUFFICIENT_DATA` fallback and the successful calculation), not just the happy path. Confirmed by `test_agent_emits_audit_event.py`, which does not merely check the module exists but confirms `run_gpa_calculation()` actually calls it, with the correct `final_status` in each case.

## Confirmed never logged

Traced the dataclass fields directly: no `password`, `secret`, `access_token`, or `api_key` field exists in the contract at all — there is no way to accidentally include one, confirmed by a static field-inspection test.

## Honest remaining gaps

- Only `run_gpa_calculation()` emits events — `run_regulation_or_rule_check()`, `run_risk_explanation()`, and `run_personalized_plan()` do not yet (real follow-up work, not attempted this pass to keep the change bounded and fully tested rather than spreading it thin across 4 functions with less scrutiny each).
- `tier`/`calculator_version`/`model_id`/`rag_document_ids`/`provider`/`latency_ms`/`token_usage` are present in the contract but not all populated by the current call site (e.g., `latency_ms` isn't measured yet, `token_usage` isn't threaded through since this path makes 0 LLM calls). The contract exists and is correct; not every field is populated by every caller yet.
- No query/reporting UI exists over these events yet — they land in the same `audit_logs` table Admin tooling already has some visibility into (per the pre-existing audit trail), but no dedicated "AI decision history" view was built this pass.

## Capability status

| Item | Status |
|---|---|
| Canonical `AIDecisionAuditEvent` contract | **IMPLEMENTED_AND_TESTED** |
| Reuses existing audit infra (no parallel writer) | **IMPLEMENTED_AND_TESTED** |
| Never logs secrets/passwords/tokens | **IMPLEMENTED_AND_TESTED** |
| Wired into `run_gpa_calculation()` | **IMPLEMENTED_AND_TESTED** |
| Wired into the other 3 tool orders | NOT_IMPLEMENTED |
| Dedicated query/reporting UI | NOT_IMPLEMENTED |
