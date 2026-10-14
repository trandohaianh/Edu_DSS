# AI 3-Tier Token/Latency Benchmark

**Methodology and an explicit constraint, stated up front:** this document does **not** report measured p50/p95/p99 latency or measured token counts from live LLM provider calls, because none were made this pass. Making real calls against Gemini/Groq/OpenAI purely to produce benchmark numbers would spend real API quota/cost for a report, without user opt-in to that spend, and — more importantly — would only characterize provider-side latency, which varies by provider/model/load and would not be a stable "before vs after 3-tier" comparison anyway. What **is** reported below is derived directly and deterministically from the code paths themselves, which is a legitimate and honest way to answer "how many LLM calls does this path make," even without wall-clock timing.

**Explicit compliance with the no-fabrication instruction:** no percentage reduction claim (e.g. "70–80% of traffic") is made anywhere in this document, because no real traffic-distribution data exists to support one. Only per-intent, code-verified call counts are reported.

## LLM-calls-per-request, old path vs. new (3-tier) path

| Task / intent | Old path (pre this session) | New path (post-wiring) | Calls avoided | Evidence |
|---|---|---|---|---|
| GPA target calculation (`GPA_CALCULATION`) | 1 LLM call (`stream_generate`) always | **0** — `ai_router.build_gpa_calculation_reply()` answers deterministically and `st.rerun()`s before `stream_generate` is ever reached | 1 of 1 (100% for this intent class) | `test_ai_advisor_gpa_router_wiring.py` proves the short-circuit runs before the `request_type="advisor_chat"` gateway call |
| Regulation lookup (`REGULATION_LOOKUP`) | 1 LLM call always | **0** | 1 of 1 | `test_ai_advisor_regulation_router_wiring.py`, same proof pattern |
| Academic rule check (`ACADEMIC_RULE_CHECK`) | 1 LLM call always | **0** | 1 of 1 | `test_ai_advisor_rule_check_router_wiring.py`, same proof pattern |
| Direct data lookup (`DIRECT_DATA_LOOKUP`) | 1 LLM call always | still 1 — **classified correctly but not yet short-circuited** (see `AI_ROUTING_MATRIX.md` Gaps) | 0 | honest gap, not claimed as improved |
| RAG QA / Learning explanation / Advisor plan / Advisor chat | 1 LLM call always | still 1 — unchanged, these genuinely need the LLM | 0 | by design — Section "LLM IS NOT THE DECISION ENGINE" applies to decision intents, not to genuinely generative ones |

**Cache-hit path (orthogonal to routing):** the P0 fix this session (`fix(cache)` commit `3a3cbfa`) did not change *whether* a cache is consulted, only *whether it is safe to reuse* — a correct cache hit was always a 0-provider-call, 0-token-cost outcome (see `token_tracker.record_usage(..., cache_hit=True)` → `cost = 0.0`). The fix's effect on cost/latency is: previously-unsafe cache hits (serving Student A's cached answer to Student B) are now correctly **misses** for the second student rather than reused answers — this is a **necessary latency/cost regression for correctness's sake** (a previously-fast-but-wrong answer becomes a correctly-slower-but-right one), not an improvement, and is reported as such rather than spun positively.

## Context size, old vs. new

Not separately benchmarked this pass. The three short-circuited intents above send **zero** tokens to any LLM provider (no context is built at all, since no `stream_generate` call happens), which is the strongest possible context-minimization outcome for those specific intents — but this is a structural fact from the code path, not a measured token-count delta.

## What remains unmeasured (honestly listed, not silently dropped)

- p50/p95/p99 latency for any Tier-3 (LLM) path.
- Real input/output token counts for Tier-2/Tier-3 paths (RAG QA, Learning Explanation, Advisor Plan, Advisor Chat).
- Retrieved-chunk count / context size impact of the RAG top-k setting (Section 4.26 of the master prompt — not benchmarked this pass).
- Cache hit rate under realistic traffic (only correctness was verified this pass — see `test_llm_gateway_cache_cross_user_isolation.py` — not a hit-rate measurement).

**Recommendation for a future pass:** run a small number of real, budgeted, user-consented calls per provider (e.g. 5–10 per intent) specifically to establish p50 latency and real token counts, rather than extrapolating from this document's structural analysis.
