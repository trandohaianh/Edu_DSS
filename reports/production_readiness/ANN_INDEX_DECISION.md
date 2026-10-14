# pgvector ANN Index Decision

## Decision: **DEFER** (do not add this pass)

## Basis

- Current corpus size in every environment exercised this engagement (demo dataset, isolated Postgres validation) is small — a handful to dozens of documents, not thousands.
- No measured retrieval-latency bottleneck exists at this scale: the live pgvector validation in a prior pass (`POSTGRES_RUNTIME_VALIDATION.md`) executed a real cosine-similarity query with correct tenant scoping without any observed slowness worth noting.
- No production traffic exists yet to characterize real query patterns (query frequency, corpus growth rate, acceptable latency) that would justify choosing between `ivfflat` and `hnsw`, or sizing their parameters (`lists`, `m`, `ef_construction`) correctly. Choosing these blindly, without that data, risks either an index that doesn't help (badly-sized `lists`) or wasted build/maintenance overhead for no measured benefit.
- Section 19's own explicit instruction: "Do not add infrastructure just to turn a matrix green."

## When this should be revisited

Once real documents accumulate at meaningful scale (hundreds+) or a real, measured retrieval-latency complaint appears, add an index **informed by actual query-pattern and corpus-size data at that time** — not preemptively. This is the same "no fabrication, no premature optimization" discipline applied elsewhere in this engagement (e.g., the embedding migration decision, the token-budget default values).

## Status

Documented as a deliberate, deferred optimization — not an oversight, not converted to a false "done." Matches `FINAL_96Q_AND_PRODUCTION_CAPABILITY_MATRIX.md`'s existing `pgvector` row limitation note.
