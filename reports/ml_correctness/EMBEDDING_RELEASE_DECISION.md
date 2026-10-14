# Embedding Release Decision

## Decision: **KEEP_CURRENT_FOR_RELEASE**

`all-MiniLM-L6-v2` remains the production embedding model for this release. `paraphrase-multilingual-MiniLM-L12-v2` is **not** migrated, despite winning every measured retrieval-quality metric in the prior pass's benchmark.

## Basis for the decision

| Factor | Assessment |
|---|---|
| Quality gain | Real, measured, favorable: Recall@5 +4.4pp (0.913→0.957), MRR +12.2pp (0.835→0.957), nDCG@5 +10.2pp (0.854→0.957) — see `reports/ml_correctness/embedding_benchmark_vi.txt`. Genuinely not marginal. |
| Latency cost | +17.6ms avg per embedding call (19.0ms→36.7ms) — small in absolute terms, but nearly **2x** relative, on top of a system with no measured end-to-end p95 SLO yet (see `AI_3_TIER_TOKEN_LATENCY_BENCHMARK.md` — this pass still has no live-provider latency baseline to compare against). |
| Re-embedding cost | **Every existing document in every vector store (LocalVectorStore JSON + any PgVectorStore-backed org) would need full re-embedding.** Old and new model embeddings are not comparable vectors — a partial migration would silently corrupt similarity search (mixing incompatible vector spaces in the same store) unless done as an atomic cutover. No re-embedding pipeline/migration script exists today. |
| Index compatibility | Both models output 384-dim vectors (confirmed), so the `pgvector(384)` column schema itself would not need to change — but every row's *values* would need recomputation, which is the expensive part, not the schema. |
| Storage | No material change (same dimensionality). |
| Rollback | **No rollback path exists today.** If a migration ran and then needed reverting, the old embeddings would already be overwritten unless a backup of the pre-migration vector store was taken first — this pass did not design or test a rollback procedure. |
| Migration risk | High, given: no re-embedding pipeline exists, no rollback path exists, no dedicated migration test exists, and the only environment with real documents to migrate is the live 72h-simulation-adjacent Postgres (which must not be touched) or the local dev JSON store (low-stakes, but not representative of a real migration). |

## Why KEEP despite the clear quality win

Section 18 is explicit: "Do NOT migrate automatically" and requires the decision to weigh migration risk, not just quality. The quality gain is real and worth acting on eventually, but doing so **safely** requires building (in a dedicated pass, not squeezed into this one): a re-embedding batch job, a verified rollback/backup step, and a migration test proving the cutover doesn't silently mix incompatible vectors mid-migration. None of that exists yet. Migrating without it would satisfy "the matrix looks better" while introducing a real, untested production risk — exactly what this whole engagement's discipline has repeatedly avoided doing elsewhere (e.g., the ANN index decision below, and the deliberate choice not to auto-migrate in the prior pass either).

## What would flip this decision to MIGRATE_BEFORE_RELEASE

A dedicated follow-up pass that builds and tests: (1) a re-embedding batch script covering both `LocalVectorStore` and `PgVectorStore`, (2) a pre-migration backup/rollback step, (3) a migration integration test proving no mixed-vector-space state is ever queryable mid-migration, and (4) a real end-to-end latency measurement (not currently available — see the token/latency limitations noted throughout this engagement) to confirm the 2x per-call latency increase doesn't push any user-facing path over a real SLO target.

## A-1 (96Q Câu 74) final status

Remains **PARTIALLY_FIXED, non-blocking** — real benchmark evidence exists and is not discarded; the decision not to migrate is deliberate and documented, not an oversight or a stalled task.
