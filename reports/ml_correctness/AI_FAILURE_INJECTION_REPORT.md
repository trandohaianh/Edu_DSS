# AI Failure Injection Report

## What was tested (real, via `test_llm_gateway_circuit_breaker_integration.py`, fake local providers, re-verified this pass)

| Scenario | Result |
|---|---|
| Repeated friendly-error responses from one provider | Circuit opens after threshold (3 consecutive failures); next request skips that provider entirely |
| Provider A fails repeatedly, Provider B healthy | A's circuit opens, B is never affected, B still serves a real answer — AI does not go globally dark because one provider is down |
| Cache cross-user isolation under repeated calls (P0 area) | Confirmed via `test_llm_gateway_cache_cross_user_isolation.py` — different `user_id`, same prompt text → genuine cache miss, no leak |
| Cross-tenant cache attempt | Not directly tested (no real multi-tenant identity exists in the demo chat path — same "2 data worlds" gap) |
| Circuit HALF_OPEN → success → CLOSED | Unit-tested in `test_circuit_breaker.py` |
| Circuit HALF_OPEN → failure → re-OPEN immediately | Unit-tested in `test_circuit_breaker.py` |
| Knowledge Fallback (no RAG evidence) | New this pass: `test_ai_advisor_knowledge_fallback_prevent_before.py` confirms the LLM is never called for a RAG_QA question with zero retrieved chunks |

## What was NOT tested this pass (honestly listed)

- Real HTTP 429/500 from an actual provider SDK (only a fake local provider yielding a friendly-error string was used — this exercises the *gateway's* handling of a friendly error, not a real SDK's exception path).
- Connection failure / real network timeout from an actual provider.
- Malformed/empty response body from a real provider SDK.
- All-3-providers-fail-simultaneously (existing tests cover "A fails repeatedly, B healthy" — not "A, B, and demo mode all fail").
- Circuit Breaker exercised through the new `agent.py` (the Agent doesn't call any LLM-related tool yet — only GPA/Calculator path exists).

## Why real-provider failure injection wasn't attempted

Simulating real 429/500/malformed responses would require either (a) actually calling real provider APIs with deliberately-malformed requests (real cost, real quota spend, and unreliable — providers may not reproduce these conditions on demand), or (b) mocking at the HTTP-client layer beneath the provider SDKs, which is a real, valuable, but separately-scoped piece of test infrastructure not built this pass. The existing fake-provider-at-the-`llm_integration`-boundary tests are real and valuable (they proved the Circuit Breaker genuinely works end-to-end) but sit one layer higher than "genuine SDK-level 429/500."

## Verdict: PARTIALLY_IMPLEMENTED

Core resilience (Circuit Breaker states, cross-provider isolation, cache safety, Knowledge Fallback prevent-before) is real and tested. Genuine SDK-level HTTP failure-mode injection (429/500/malformed/connection-failure) is not — this is a real gap, not silently closed.
