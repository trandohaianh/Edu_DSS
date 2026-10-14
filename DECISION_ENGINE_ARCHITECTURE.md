# Decision Engine Architecture

**Core principle enforced throughout:** LLM IS NOT THE DECISION ENGINE. The LLM explains and converses; it never independently computes, decides, or selects a regulation version. Every claim below is backed by a specific file/function and a specific test — not an architectural diagram that was never wired to real behavior.

## The five components and their real status

| Component | Role | File | Status | Test evidence |
|---|---|---|---|---|
| **Calculator** | Computes deterministic numeric results (GPA-to-target) | `dss/services/gpa_calculator.py` (`compute_required_remaining_gpa`) | IMPLEMENTED_AND_TESTED, wired into real chat path | `test_ai_router_gpa_wiring.py`, `test_ai_advisor_gpa_router_wiring.py` |
| **Regulation Resolver** | Selects the correct regulation version for org/program/cohort/date | `dss/services/regulation_resolver.py` (`resolve_regulation`) + `dss/services/regulation_store.py` | IMPLEMENTED_AND_TESTED, wired into real chat path (as a real-but-honest "no mapping available" gate — see `AI_ROUTING_MATRIX.md`/`ai_router.py` docstring for the 2-data-worlds gap) | `test_regulation_resolver.py`, `test_regulation_store.py`, `test_ai_router_regulation_wiring.py`, `test_ai_advisor_regulation_router_wiring.py` |
| **Rule Engine** | Decides ALLOW/DENY/WARNING/INSUFFICIENT_DATA for academic-eligibility rules | `dss/services/rule_engine.py` | IMPLEMENTED_AND_TESTED, wired into real chat path (same honest gate as above) | `test_rule_engine.py` (17 tests, incl. the mandatory "LLM cannot override" guard in both directions), `test_ai_router_rule_check_wiring.py`, `test_ai_advisor_rule_check_router_wiring.py` |
| **RAG** | Provides authoritative evidence for content questions | `dss/services/rag_service.py`, `vector_store.py`, `chunking_service.py` | IMPLEMENTED (pre-existing), document-governance gap disclosed in `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md` (Câu 73) | pre-existing test suite |
| **ML** | Predicts (risk level, grade classification) | `dss/core/trainers.py`, `model_service.py` | IMPLEMENTED, K-3 ground-truth-leak bug fixed and re-verified this pass | `test_ai_advisor_prediction_source.py` (10/10, re-run live this pass) |
| **LLM** | Explains and converses — never decides | `dss/services/llm_gateway.py` | Explanation-only role enforced for the 3 wired intents by construction (short-circuit happens before `stream_generate` is ever called) | source-inspection wiring tests (see above) |
| **Validator** | Verifies Calculator/Rule Engine/Regulation Resolver output before it reaches the user | `dss/services/validator.py` | IMPLEMENTED_AND_TESTED, wired as a real gate (not decorative) into all 3 reply-builders | `test_validator.py` (17 tests), `test_ai_router_validator_wiring.py` (proves FAIL suppresses computed content) |
| **Agent/Orchestrator** | Would coordinate the above under RBAC/tenant-scope/tool-allowlist | — | **NOT_IMPLEMENTED** this pass — see "Agent" section below | — |

## The critical guarantee, proven twice

1. **Rule Engine vs LLM:** `rule_engine.decide_final_status(rule_result, llm_suggested_status)` always returns `rule_result.status`, verified in both directions (`test_llm_says_allow_but_rule_engine_says_deny_final_must_stay_deny`, `test_llm_says_deny_but_rule_engine_says_allow_final_must_stay_allow`).
2. **Calculator vs LLM:** `validator.validate_llm_numeric_claim(llm_claimed_value, authoritative_value)` FAILs whenever an LLM-stated number disagrees with the Calculator's real result beyond tolerance, and `decide_safe_fallback_message()` never leaks the wrong number back out (`test_llm_wrong_number_vs_calculator_result_fails_and_blocks`).

In practice, for the three wired intents (GPA/Regulation/RuleCheck), the LLM is **never even called** — the strongest possible enforcement of "cannot override," since there is no LLM output to override with in the first place. The Validator-level guards above exist as defense-in-depth for any *future* path where an LLM might restate one of these numbers in free text (e.g. a Tier-3 explanation that also happens to mention the GPA target).

## Agent/Orchestrator — honest status: NOT_IMPLEMENTED

Per the master prompt's own sequencing rule ("build the Agent ONLY after Calculator/Rules/Resolver/Validator contracts exist"), those four contracts now genuinely exist and are tested. Building a real orchestrator with an explicit tool allowlist, RBAC/tenant-scope enforcement, bounded retry, and audit logging is a substantial standalone piece of work that was not started this pass, for two reasons stated honestly rather than silently skipped:

1. The two data-world gap (no `organization_id`/`program_id`/`cohort` mapping for the demo student, documented repeatedly above) means an Agent today would face the exact same "insufficient tenant context" wall that the Regulation Resolver and Rule Engine wiring already hit — building an orchestrator on top of that gap first would mean building on sand.
2. Given the sheer scope of this closure pass (96-question audit, 72h evidence, isolated Postgres/RLS/pgvector validation, router audit, semantic cache audit all completed this pass already), building a *new*, non-trivial orchestration layer with its own RBAC/audit/allowlist correctness properties deserves a dedicated pass with its own budget, not a rushed addition at the end of an already-large one.

**Recommendation for the next pass:** build `dss/services/agent.py` with an explicit `_ALLOWED_TOOLS` frozenset (mirroring the `_BEHAVIOR_CHANGING_ROUTES` honesty pattern already used in `ai_router.py`), route only the already-tested Calculator/RuleEngine/RegulationResolver/Validator functions through it, and write the "Agent must not have unrestricted DB access" test *first*, TDD-style, before any implementation — consistent with this session's established methodology.
