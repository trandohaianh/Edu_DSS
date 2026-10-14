# AI Failure Resilience

## Chain: Provider call → timeout → bounded retry → Circuit Breaker → Failover → Safe Fallback

Fully implemented and tested (this session, commit `fd4aa1e` from the prior closure pass plus verification this pass):

- `dss/services/circuit_breaker.py` — pure, thread-safe, per-provider `CLOSED`/`OPEN`/`HALF_OPEN` state machine. `_FAILURE_THRESHOLD = 3` consecutive failures opens the circuit; `_COOLDOWN_SECONDS = 30.0` before a half-open probe; a half-open failure re-opens immediately; a half-open success closes it. 8 unit tests in `test_circuit_breaker.py`, all passing.
- Wired into `LLMGateway.stream_generate()` at all three failure-detection points (friendly-error branch, real-exception branch, demo-mode exclusion) — confirmed via **integration** tests that actually drive `stream_generate()` end-to-end with a fake provider, not just unit tests of the breaker in isolation: `test_llm_gateway_circuit_breaker_integration.py` (3 tests) proves (a) repeated failures open the circuit and the *next request* skips the open provider entirely, (b) a healthy provider is never affected by another provider's open circuit, and (c) one provider failing does not disable AI globally — the chain fails over to the next provider and still returns a real answer.
- Retry/failover chain: `PRIMARY → FALLBACK_1 → FALLBACK_2 → demo`, confirmed never calls all providers simultaneously (sequential, bounded by the 3-provider chain length) and never retries infinitely (each provider gets exactly one attempt per request; repeated failures accumulate toward the circuit threshold across *requests*, not via retry-looping *within* one request).
- Auth/security errors (401/403/PII/injection detection) correctly **do not** fail over to another provider — confirmed by the pre-existing H-3/H-1 fixes from the prior session, re-verified as still present.

## Technical Fallback vs. Knowledge Fallback

**Technical Fallback** (provider A unavailable → try provider B): fully implemented as above — this is exactly what the Circuit Breaker + retry chain does.

**Knowledge Fallback** (no approved evidence → must not let a provider guess): implemented, but via a **different mechanism** than a pre-emptive block, and this difference is reported honestly rather than glossed over:

- The chat path (`ai_advisor.py`) does **not** currently skip the LLM call outright when RAG retrieval returns zero chunks — it still calls the LLM, but (a) the prompt itself instructs the model to say "chưa có tài liệu chính thức được duyệt" when it has no grounding (`rag_service.py`), and (b) **after** the LLM responds, `citation_service.verify_citations()` checks every citation the LLM actually made against the real retrieved-chunk set and returns `is_grounded` / `hallucinated_citations`, which the UI uses to flag the answer (`"hallucinated": ...` field already threaded through `_chat_history` entries, visible in the same code path examined for the router wiring this session).
- This is a **detect-after-the-fact** design, not a **prevent-before-it-happens** design. It is a real, working safety net (an unsupported claim is caught and flagged, not silently trusted), but it is architecturally different from "return `INSUFFICIENT_EVIDENCE` and never call the LLM at all," which is what the master prompt's Section 27 literally asks for.
- **No test exists this pass distinguishing the two paths explicitly** (i.e., a test that drives a provider-timeout scenario through the Circuit Breaker's failover, side-by-side with a zero-RAG-evidence scenario through citation verification, asserting they take genuinely different code branches). This is flagged as a real gap, not silently closed.

**Recommendation for next pass:** add an explicit pre-flight check in the RAG_QA path — when `_chat_docs` is empty AND the router's intent is `RAG_QA` specifically (not the general `ADVISOR_CHAT` fallback, which legitimately may answer from general conversation ability), skip `stream_generate()` entirely and return a fixed `INSUFFICIENT_EVIDENCE`-equivalent message, mirroring the exact short-circuit pattern already used for GPA/Regulation/RuleCheck this session. This would upgrade Knowledge Fallback from "detect after" to "prevent before," consistent with the rest of this session's LLM-is-not-the-decision-engine work.

## Failure-injection results (this pass)

Re-ran the existing Circuit Breaker integration tests (which are themselves a form of failure injection — simulated timeouts/friendly-errors from a fake provider) — all passing. **Not injected this pass** (honestly listed, not silently skipped): real 429/500 responses from an actual provider SDK, malformed/empty response bodies, and a genuine all-providers-fail-simultaneously scenario beyond the 3-provider chain (the existing tests cover "provider A fails repeatedly, provider B is healthy," not "A, B, and demo all fail").
