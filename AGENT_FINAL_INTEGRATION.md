# Agent Final Integration

Supersedes `AI_AGENT_ORCHESTRATION.md`. Covers what changed in the FINAL REMAINING-GAPS CLOSURE pass: real authorization, all 4 tool orders, and wiring into the actual Student-facing chat path.

## 1. Real authorization (Section 3)

`agent.authorize(request)` runs **before** any tool executes in every one of the 4 tool-order functions (`run_gpa_calculation`, `run_regulation_or_rule_check`, `run_risk_explanation`, `run_personalized_plan`) — confirmed by a dedicated test per function proving `AuthorizationError` is raised before any tool call, not just that a standalone `authorize()` function exists.

Fail-closed rules, each with a passing test:
- Missing `user_id` or `role` → denied.
- `role` not one of the 3 known values (`Sinh viên`/`Giảng viên / CVHT`/`Admin`) → denied.
- `role == Sinh viên` and `authorized_context["subject_user_id"]` differs from `request.user_id` → denied (**Student A cannot access Student B's data**).
- `request.organization_id` differs from `authorized_context["organization_id"]` (when both present) → denied (**Org A cannot access Org B's data**).
- `intent` in the admin-only set and `role != Admin` → denied (**Student cannot call an Admin-only tool**).
- Identity is **never** read from `request_text` — confirmed by a static-source test.

12 tests in `test_agent_authorization.py`, all passing.

## 2. All 4 tool orders (Section 4)

| Order | Function | Tools called | LLM calls | Status |
|---|---|---|---|---|
| A. GPA | `run_gpa_calculation` | Calculator → Validator | 0 | Real, wired into the live chat path (see §3) |
| B. Regulation/rule | `run_regulation_or_rule_check` | Regulation Resolver → Rule Engine (optional) → Validator | 0 | Real, unit-tested; **not** wired into the live chat path this pass (`ai_router.py`'s existing `build_regulation_lookup_reply`/`build_academic_rule_check_reply` still call the resolver/rule-engine functions directly, not through the Agent — a real remaining gap, not hidden) |
| C. Risk explanation | `run_risk_explanation` | packages pre-computed ML prediction + SHAP evidence | 0 | Real, unit-tested; no live wiring (risk explanation isn't currently a short-circuited chat route at all) |
| D. Personalized plan | `run_personalized_plan` | composes A + B's evidence | 0 (`llm_used=False` always this pass) | Real, unit-tested; no live wiring; **does not yet call an LLM for synthesis** — stated as a real gap, not a fabricated "done" |

11 new tests in `test_agent_tool_orders_bcd.py`, all passing, each including an authorization-enforcement test.

## 3. Wired into the real Student chat path (Section 5)

`ai_router.build_gpa_calculation_reply()` — the actual function `ai_advisor.py`'s live chat handler calls — now internally builds a real `AgentRequest` and calls `agent.run_gpa_calculation()` instead of calling `gpa_calculator.compute_required_remaining_gpa()` directly. `ai_advisor.py`'s call site was updated to pass the student's real pseudonym (`privacy_service.generate_pseudonym(str(student_id_llm))`) and real `role`, not placeholder values.

This means: a real student typing "GPA 6.0, muốn lên 7.5, còn 20 tín chỉ" in the actual chat now genuinely passes through `agent.authorize()` before the Calculator runs — not a parallel, untested calling convention, and not class/unit-test-only.

**Verified**: 
- `test_ai_advisor_passes_real_pseudonym_and_role_to_gpa_reply` — confirms the real call site passes real identity (verify-before-fix: failed on pre-change code, passes after).
- `test_build_gpa_calculation_reply_genuinely_calls_agent_not_calculator_directly` — confirms the Calculator is no longer called directly, and is not even imported directly into this function anymore.
- `test_end_to_end_student_chat_question_reaches_agent_authorization` — a real (non-source-inspection) call proving the correct, expected number still comes out the other end.
- Full existing GPA/router test suite (24 tests) still passes unchanged, plus 1 pre-existing test's overly-strict exact-substring assertion was updated (not weakened — same check, adjusted for the now-multi-line call) with a documented reason.

## 4. What remains honestly not done

- Regulation/RuleCheck/Risk/Plan tool orders exist and are tested but are **not** wired into the live chat path — only GPA is. `ai_router.py`'s `build_regulation_lookup_reply()`/`build_academic_rule_check_reply()` still call `regulation_resolver`/`rule_engine` directly.
- `run_personalized_plan()` never calls an LLM for synthesis (`llm_used` is always `False`) — Section 18-D's "LLM for synthesis only" step doesn't exist yet.
- No bounded retry, no real DB-backed audit write (see `AI_DECISION_AUDIT_LOG.md`), no `organization_id` enforcement beyond the structural consistency check (there is still no real multi-tenant identity flowing into the demo chat session to enforce against).

## Capability status

| Item | Status |
|---|---|
| Real authorization (fail-closed, tested against all 5 named scenarios) | **IMPLEMENTED_AND_TESTED** |
| All 4 tool orders | **IMPLEMENTED_AND_TESTED** |
| Wired into the real Student chat path | **IMPLEMENTED_AND_TESTED (GPA only)** |
| Regulation/RuleCheck/Risk/Plan wired into live chat | NOT_IMPLEMENTED |
| Bounded retry per tool | NOT_IMPLEMENTED |
| Real DB-backed audit write | NOT_IMPLEMENTED |
| Full RBAC (real tenant identity, not just structural consistency) | BLOCKED (2-data-worlds gap) |
