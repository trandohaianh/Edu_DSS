# AI Routing Matrix

Referenced from `dss/services/ai_router.py`'s own docstring. Traces the real code path for every example question named in the master closure prompt (Section 14), captured by actually calling `ai_router.classify()` — not hand-derived.

**Router output shape** (matches the target example in the prompt, with two additions kept because they proved useful this session: `capability` and `wired_to_real_behavior`):

```python
RouteDecision(
    intent: str, tier: int, capability: str,
    requires_llm: bool, requires_rag: bool, requires_rules: bool, requires_calculator: bool,
    reason: str, wired_to_real_behavior: bool,  # computed, not settable
)
```

## Trace table (A–I, live `classify()` output)

| # | Question | Intent | Tier | LLM | RAG | Rules | Calc | `wired_to_real_behavior` | Validator | Latency/Tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| A | "Điểm hiện tại của em là bao nhiêu?" | `DIRECT_DATA_LOOKUP` | 1 | No | No | No | No | No | not applicable (no reply-builder wired for this route yet — see Gaps below) | not measured (no LLM call — classification only, no live-provider timing collected) |
| B | "GPA 3.05, muốn lên 3.20 thì cần bao nhiêu?" | `GPA_CALCULATION` | 1 | No | No | No | **Yes** | **Yes** | `validate_gpa_value()` gates the reply | no LLM call — deterministic Calculator path, latency not separately profiled this pass |
| C | "Em có được đăng ký môn B không?" | `ACADEMIC_RULE_CHECK` | 1 | No | No | **Yes** | No | **Yes** | `validate_rule_engine_result()` gates the reply | no LLM call |
| D | "Em đủ điều kiện làm khóa luận chưa?" | `ACADEMIC_RULE_CHECK` | 1 | No | No | **Yes** | No | **Yes** | same as C | no LLM call |
| E | "Tại sao em bị đánh giá có nguy cơ?" | `LEARNING_EXPLANATION` | 3 | **Yes** | No | No | No | No | not wired this pass | requires live provider call — not measured (no live LLM calls made this pass, to avoid unnecessary cost/token spend outside a dedicated benchmark run) |
| F | "Quy chế nào đang áp dụng cho em?" | `REGULATION_LOOKUP` | 1 | No | No | No | No | **Yes** | `validate_regulation_resolution()` gates the reply | no LLM call |
| G | "Giải thích điều khoản này." | `ADVISOR_CHAT` (safe generic fallback — no specific pattern matched) | 3 | **Yes** | **Yes** | No | No | No | not wired this pass | requires live provider call — not measured |
| H | "Lập kế hoạch học tập kỳ tới." | `ADVISOR_PLAN` | 3 | **Yes** | **Yes** | No | No | No | not wired this pass | requires live provider call — not measured |
| I | "Em chưa hiểu, giải thích lại dễ hơn." | `LEARNING_EXPLANATION` | 3 | **Yes** | No | No | No | No | not wired this pass | requires live provider call — not measured |

**Router-safety cases** (from `test_ai_router.py`, also live-traced):

| Input | Intent | Notes |
|---|---|---|
| "Tóm tắt tài liệu này" | `RAG_QA` | correctly routes to RAG, not bare LLM |
| "Em cảm thấy kế hoạch này chưa phù hợp, giải thích giúp em" (vague feedback) | `ADVISOR_CHAT` | not `UNKNOWN` — has a safe route, still gets LLM+RAG |
| "asdkjhaskjdh 12903 !!! ???" (gibberish) | `ADVISOR_CHAT` or `UNKNOWN` (test accepts either) | never silently dropped, always `requires_llm=True` |
| "" (empty) | `UNKNOWN` | `requires_llm=True`, does not crash |
| "Điểm của em là 7.5" (only 1 number) | not `GPA_CALCULATION` | correctly rejected — needs ≥2 numbers to be a calculation intent |

## Gap found and fixed this pass

Example E's exact phrasing in this prompt ("Tại sao em **bị đánh giá** có nguy cơ?", passive voice) did **not** match the existing `_LEARNING_EXPLANATION_PHRASES` list (which expected "tại sao hệ thống đánh giá" or "tại sao em có nguy cơ" as contiguous substrings) and fell through to the generic `ADVISOR_CHAT` fallback instead. This was **not unsafe** — `ADVISOR_CHAT` still uses the full LLM+RAG+citation-verification path, it just loses the more specific `LEARNING_EXPLANATION` framing (which is intended to anchor the LLM's explanation to an existing ML/diagnosis result rather than a general chat turn). Fixed by adding "bị đánh giá có nguy cơ" / "em bị đánh giá" to the phrase list; verified FAIL-before-fix (`test_E_alt_phrasing_passive_voice_also_routes_to_learning_explanation` failed on the pre-fix router, passed after) and regression-tested against the full router suite (15/15 pass).

## Honest remaining gaps (not fixed this pass)

- **`DIRECT_DATA_LOOKUP` (A) has no reply-builder wired into `ai_advisor.py`** — the router correctly classifies it and correctly marks `requires_llm=False`, but nothing in the chat handler currently short-circuits on this intent the way GPA/Regulation/RuleCheck do. Today, a `DIRECT_DATA_LOOKUP` question still falls through to the full LLM+RAG path in practice (safe, but not the "Tier 1, no LLM" behavior the classification implies) — this is a real "classification label vs. actual behavior" gap, same category the `wired_to_real_behavior` flag exists to be honest about.
- **E/G/H/I all route through Tier 3 (live LLM)** — none were exercised with a real provider call this pass (see `AI_3_TIER_TOKEN_LATENCY_BENCHMARK.md` for the reasoning on not making speculative live-provider calls outside a dedicated, consented benchmark run). Their Validator coverage (structured-claim checking, citation consistency) is not yet wired for these intents — only the three Tier-1 deterministic routes have a Validator gate today.
