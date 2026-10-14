# AI Cache Security Audit

## ExactCache (wired into production via `LLMGateway.stream_generate()`)

**P0 found and fixed this session** (commit `3a3cbfa`): the cache key hashed only `prompt + role`, omitting `user_id`. Two different students issuing textually-identical prompts (realistic on this synthetic dataset's limited categorical values) could receive each other's cached, personalized answer — GPA figures, academic-warning text, advisor guidance.

**Fix:** cache key now hashes `prompt + role + user_id`. Cache-entry `dimensions` now also carry `student_pseudonym` (=`user_id`) and `request_type`, which additionally repaired a second, previously-silent gap: `layered_cache.invalidate_student(pseudonym)` could never match any entry created via this path before (dimensions only ever held `{"role": role}`), so a student's cached personalized answer was never invalidated when their underlying data changed — only TTL (up to 1h) ever expired it. Now it can.

**Negative tests, all passing** (`test_llm_gateway_cache_cross_user_isolation.py`):
| Scenario | Result |
|---|---|
| Same prompt text, different `user_id` | Correct **MISS** — provider re-invoked, no cross-user leak |
| Same prompt text, same `user_id` | Correct **HIT** — cache still works for the legitimate case |
| `invalidate_student(pseudonym)` after a cache hit | Correctly clears the entry; next request is a MISS |

**Scoping dimensions present today:** `role`, `user_id` (via the key), `request_type` (in dimensions, not yet in the key itself — see below).
**Scoping dimensions NOT present:** `organization_id`/tenant, `regulation_version`, `document_version`, `model_version`. This is a real, disclosed gap: if the same user asks the same prompt before and after a regulation version change, model swap, or document update, the stale cached answer would still be served until TTL expiry. Not exploited by any test this pass (no multi-tenant student identity exists in the demo chat path today — see the "2 data worlds" gap documented repeatedly in `ai_router.py`/`AI_ROUTING_MATRIX.md`), but flagged rather than silently accepted as safe.

## SemanticCache (embedding-based; NOT wired into production)

Confirmed via `grep -rn "layered_cache\.semantic_cache\|semantic_cache\.lookup\|semantic_cache\.store" dss/` → **zero matches**. This class exists, is unit-tested in isolation, and makes real safety claims in its own docstrings, but is not reachable from any real user request today. Zero current production exposure.

Added this session (`test_semantic_cache_scoping.py`, 5 tests, all passing) to hold it to its own documented claims even while unused, so that *if* it is wired into a real path in a future pass, its safety properties are already regression-tested:
- `CACHE_CLASS_STUDENT` content is never served via similarity match, even for an identical embedding.
- `CACHE_CLASS_STUDENT` `store()` is a genuine no-op (nothing persisted internally).
- `CACHE_CLASS_COURSE` lookups never cross course boundaries.
- A genuine same-course match above threshold still hits (sanity check — the course filter isn't accidentally blocking everything).
- `CACHE_CLASS_GLOBAL` is documented as intentionally course-agnostic (not an oversight).

## Required negative-test matrix (Section 15 of the master prompt) — status

| Test | Status |
|---|---|
| Same prompt / same student | PASS (works, `test_same_user_same_prompt_still_benefits_from_cache`) |
| Same prompt / different student | PASS — fixed and tested this session (the P0) |
| Same prompt / different tenant | **Not tested** — no real multi-tenant identity exists in the chat path to construct this scenario against (same "2 data worlds" gap) |
| Same prompt / different regulation | **Not tested** — `regulation_version` is not part of the cache key or dimensions at all |
| Same prompt after GPA/data update | **Partially tested** — `invalidate_student()` now works (this session's fix) and is proven to clear the cache; whether the *caller* actually invokes `invalidate_student()` when a student's grade data changes was not traced this pass |

## Honest overall verdict

The one *actually reachable* production risk (ExactCache cross-user leak) was found, reproduced with a failing test first, fixed, and closed with passing negative tests. The one *not-yet-reachable* risk (SemanticCache) was brought up to its own documented safety bar defensively. The tenant/regulation-version/model-version/document-version scoping dimensions remain a real, disclosed gap — not exploitable today because no code path constructs those identities in the chat flow, but should be added before any future work connects the "2 data worlds" (demo student ↔ real multi-tenant Postgres), at which point this gap would become live risk rather than a theoretical one.
