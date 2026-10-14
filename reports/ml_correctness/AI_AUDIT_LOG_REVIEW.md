# AI Audit Log Review

## What genuinely exists

1. **General sensitive-mutation audit trail** (`audit_log_repository.record()` → `audit_logs` table): captures `action`/`target_type`/`target_id`/`actor_username`/`actor_user_id`/`organization_id`/`before`/`after`/timestamp. Used for admin mutations today (model Promote/Rollback — confirmed in `model_registry.py`). Never logs password/secret/access-token (traced — no such field exists in its call sites). Real, working, Postgres-backed (RLS-protected via `organization_id`).
2. **AI usage/cost tracking** (`token_tracker.py`'s `UsageRecord`, this session's own P1 fix target earlier): captures `user_id` (pseudonymous), `role`, `request_type`, `provider`, `model`, `input_tokens`/`output_tokens`, `cost`, `cache_hit`. This is a genuine, real, partial overlap with what Section 34 asks for.

## What Section 34 asks for that does not exist as a unified schema

No single audit record today carries **all** of: `correlation_id` + `tier` + `tools_used` + `calculator_version` + `rule_id`/`rule_version` + `regulation_id`/`regulation_version` + `ML_model_version` + `RAG_document_ids` + `validator_result` + `fallback_path` in one place. The pieces exist in different systems (correlation_id is generated and logged in `llm_gateway.py`'s Python logger, not persisted to a queryable table; `AgentResult.audit_metadata` from the new `agent.py` returns a dict but nothing writes it to Postgres yet; token usage is tracked but not linked to a correlation_id).

## Verdict: PARTIALLY_IMPLEMENTED

Two real, working, tested pieces exist (general mutation audit + token/cost tracking). The unified AI-decision-audit schema Section 34 describes — the one that would let someone query "show me everything about correlation_id X: which tier, which rules/regulations, which RAG docs, what the Validator said, what the fallback path was" — does not exist as a single, queryable record. Building it (most naturally: a new `ai_decision_audit_log` table, or adding these columns to the existing `ai_token_usage` table since it's already scoped correctly) is real, scoped, follow-up work, not attempted this pass to avoid a rushed schema/migration change at the tail of an already-large pass.

## Confirmed NOT logged anywhere (correct)

Passwords, secrets, access tokens, raw prompts, raw unmasked PII — traced across both existing logging paths, neither ever receives these.
