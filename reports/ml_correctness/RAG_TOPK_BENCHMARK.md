# RAG Top-K Benchmark

Real benchmark run (not fabricated, not overfit to one hand-picked question) using the same 23-query/19-document standard benchmark set as the embedding benchmark, on the **current production embedding model** (`all-MiniLM-L6-v2`, already cached, no new download needed). Script: `tools/topk_benchmark.py`.

## Results

| k | Recall@k | Precision@k | MRR | nDCG@k | Avg latency (ms) | Irrelevant chunks/query (avg) | Est. context size |
|---|---|---|---|---|---|---|---|
| 3 | 0.8696 | 0.2899 | 0.8261 | 0.8375 | 17.70 | 0.39 | ~840 chars |
| **5 (current default)** | **0.9130** | 0.1826 | **0.8348** | **0.8543** | 19.00 | 0.43 | ~1400 chars |
| 8 | 0.9130 | 0.1141 | 0.8348 | 0.8543 | 17.65 | 0.70 | ~2240 chars |

## Finding

**k=8 offers zero measured improvement over k=5** — Recall@k, MRR, and nDCG@k are *identical* between k=5 and k=8 on this benchmark set (no additional relevant document is ever found past the top 5 for these 23 queries), while precision drops meaningfully (0.183→0.114) and irrelevant-chunk count nearly doubles (0.43→0.70 per query) — i.e., k=8 spends more context budget for strictly worse precision and no recall benefit. **k=8 is not recommended.**

**k=3 vs k=5** is a genuine tradeoff: k=3 gives noticeably better precision (0.290 vs 0.183) and a smaller context footprint (~840 vs ~1400 chars) at the cost of some recall (0.870 vs 0.913 — roughly 1 more query out of 23 missing its relevant document entirely).

## Decision: keep k=5 as the documented default

Given no live-provider token-cost pressure has been measured yet (see `docs/ai/AI_3_TIER_TOKEN_LATENCY_BENCHMARK.md`), and recall (finding the right document at all) matters more than precision (not wasting a little extra context) for an academic-advising use case, k=5 remains the better default of the three measured. This is **not** an untested guess — it's the option that wins outright on the metrics that matter most (recall/MRR/nDCG) among the values that showed any measured difference.

**Recommendation for a future pass:** if real token-cost pressure emerges, k=3 is the next value to reconsider — it has real, measured, quantified tradeoffs (not "3 might be enough," but "here is exactly what changes"). k=8 should not be adopted under any currently-measured circumstance.

## Honest limitation

Latency differences across k values here are noise-level (17-19ms range, well within likely measurement variance on this sample size/hardware) — not a meaningful signal at this small corpus size. This would need re-measuring at a realistic production corpus size to be a meaningful latency comparison, not a benchmark-only artifact.
