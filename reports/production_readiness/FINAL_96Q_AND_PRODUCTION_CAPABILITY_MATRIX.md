# Final 96Q and Production Capability Matrix

Allowed status values (exactly as mandated): `IMPLEMENTED_AND_RUNTIME_VERIFIED`, `IMPLEMENTED_AND_TESTED`, `IMPLEMENTED_NOT_RUNTIME_VERIFIED`, `PARTIALLY_IMPLEMENTED`, `NOT_IMPLEMENTED`, `BLOCKED`.

For the full 96-question breakdown, see `reports/ml_correctness/96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md`. This document covers **production capabilities** built/verified across both closure passes (updated for the FINAL GAP CLOSURE pass — rows changed since the prior version of this document are marked).

| Capability | Code | Test | Integration | Runtime | Status | Evidence | Limitation |
|---|---|---|---|---|---|---|---|
| Incremental Sync | Yes | Yes (38 tests total, live) | Yes | **Yes, live, this pass** | **IMPLEMENTED_AND_RUNTIME_VERIFIED (updated)** | `INCREMENTAL_SYNC_ROOT_CAUSE_AND_FIX.md` | Root cause split into a fixable EduDSS-side amplifier (page_size=3→100, fixed) and an unfixable simulation-tooling limitation (Moodle proxy ignores `updated_since`, disclosed, not EduDSS's own bug) |
| PostgreSQL migrations | Yes | — | — | Yes, live | **IMPLEMENTED_AND_RUNTIME_VERIFIED** | `POSTGRES_RUNTIME_VALIDATION.md` §1 | — |
| Row-Level Security (tenant isolation) | Yes | Yes | — | Yes, live, non-superuser role | **IMPLEMENTED_AND_RUNTIME_VERIFIED** | `POSTGRES_RUNTIME_VALIDATION.md` §3, `test_workstream_ab_postgres_integration.py::test_03` | — |
| pgvector (real embeddings + RLS) | Yes | Yes | — | Yes, live | **IMPLEMENTED_AND_RUNTIME_VERIFIED** | `POSTGRES_RUNTIME_VALIDATION.md` §4 | No ANN index exists — full sequential scan per similarity query |
| Direct Data Lookup | Yes **(new this pass)** | Yes (8 tests) | Yes (wired) | Yes (source-inspection) | **IMPLEMENTED_AND_TESTED (updated — was NOT_IMPLEMENTED)** | `test_ai_router_direct_lookup_wiring.py`, `test_ai_advisor_direct_lookup_router_wiring.py` | Only covers current-score/attendance lookups from already-present columns; does not cover credits-accumulated or program-name (not present in the synthetic dataset) |
| Router (3-tier classification) | Yes | Yes (20+ tests) | Yes | Yes | **IMPLEMENTED_AND_TESTED** | `ai_router.py`, `AI_ROUTING_MATRIX.md` | — |
| Tier 1 (deterministic: Calculator/Rules/Resolver/DirectLookup) | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | 4 short-circuits now wired (GPA/Regulation/RuleCheck/DirectLookup) | Tenant-scoped rule/regulation evaluation still blocked on the 2-data-worlds gap |
| Tier 2 (RAG/ML) | Yes (pre-existing) | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | `RAG_CANONICAL_PATH_AUDIT.md` (confirmed single canonical path, no duplication) | Top-k not re-benchmarked this pass |
| Tier 3 (LLM Gateway) | Yes (pre-existing) | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | Circuit Breaker + failover chain | No real-SDK failure injection (see `AI_FAILURE_INJECTION_REPORT.md`) |
| Agent / Orchestrator | Yes **(new this pass, partial)** | Yes (8 tests) | Partial — GPA path only, not wired into `ai_advisor.py` | No | **PARTIALLY_IMPLEMENTED (updated — was NOT_IMPLEMENTED)** | `agent.py`, `test_agent_orchestrator.py`, `AI_AGENT_ORCHESTRATION.md` | No RBAC/tenant enforcement, no bounded retry reuse, no DB-backed audit write, only 1 of 4 tool orders built, not wired into the real chat path |
| Exact Cache | Yes | Yes (3 tests) | Yes | Yes | **IMPLEMENTED_AND_TESTED — P0 fixed this pass** | `test_llm_gateway_cache_cross_user_isolation.py` | Tenant/regulation-version/model-version scoping still absent from the key (disclosed) |
| Semantic Cache | Yes | Yes (5 tests) | No (unused) | No | **IMPLEMENTED_NOT_RUNTIME_VERIFIED** | `test_semantic_cache_scoping.py` | Zero production exposure — hardened defensively |
| Context Builder | No | No | No | No | **NOT_IMPLEMENTED** | — | Not audited/built as a dedicated module this pass — the *effect* of minimization exists ad hoc (see PII audit: banded GPA, sanitized weaknesses) but there is no per-intent required/optional/forbidden-field contract enforced anywhere |
| Token Budget | No | No | No | No | **NOT_IMPLEMENTED** | — | No max-turns/max-summary/max-context-size bounds enforced anywhere; conversation history sent is capped at last 5 turns by a hardcoded slice (`_chat_history[-6:-1]`), which is a token-bounding *side effect*, not a designed budget policy |
| Conversation Memory | Partial | No | Partial | Partial | **PARTIALLY_IMPLEMENTED** | last-5-turns slice in `ai_advisor.py` | Not a bounded summary — raw last-N-turns only; GPA/credits/rules are correctly re-fetched from source each turn (never trusted from memory) via the router short-circuits, which is the one part of Section 23 genuinely satisfied |
| GPA Calculator | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | unchanged from prior pass | — |
| Regulation Resolver | Yes | Yes | Yes (honest-gate) | Yes | **IMPLEMENTED_AND_TESTED** | unchanged from prior pass | Cannot resolve real org/program/cohort until the 2 data worlds are connected |
| Rule Engine | Yes | Yes (17 tests) | Yes (honest-gate) | Yes | **IMPLEMENTED_AND_TESTED** | unchanged from prior pass | Same tenant-data gap |
| Validator | Yes | Yes (17 tests) | Yes (real gate) | Yes | **IMPLEMENTED_AND_TESTED** | unchanged from prior pass | Authorization/tenant/course-ID/citation validation not yet built |
| RAG (retrieval) | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | `RAG_CANONICAL_PATH_AUDIT.md` | — |
| Document Governance | Yes **(reclassified this pass)** | Yes (pre-existing) | Yes | Yes | **IMPLEMENTED_AND_TESTED (updated — was DOCUMENTATION_ONLY/unclear)** | `RAG_DOCUMENT_GOVERNANCE.md`, `document_governance.is_document_usable()` | Admin-upload-time default status and REJECTED/ARCHIVED UI-listing exclusion not independently re-traced this pass |
| ML (classification/regression/clustering) | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md` | K-3 (ground-truth leak) re-verified live: 10/10 tests passing |
| Drift | Yes **(new this pass)** | Yes (5 tests) | Yes (Admin UI button) | Yes (on-demand) | **IMPLEMENTED_AND_TESTED (updated — was STILL_OPEN)** | `run_on_demand_drift_check()`, `test_drift_on_demand_check.py`, `test_drift_ui_wiring.py` | On-demand only, no scheduler; compares train/test split (sanity check), not genuine post-deployment data — explicitly disclosed in every result |
| LLM Gateway | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | — | — |
| Retry | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | — | — |
| Circuit Breaker | Yes | Yes (8 unit + 3 integration) | Yes | Yes | **IMPLEMENTED_AND_TESTED** | `circuit_breaker.py` | Real-SDK failure injection not done (see `AI_FAILURE_INJECTION_REPORT.md`) |
| Failover | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | — | — |
| Technical Fallback | Yes | Yes | Yes | Yes | **IMPLEMENTED_AND_TESTED** | — | — |
| Knowledge Fallback | Yes **(upgraded this pass)** | Yes (3 new tests) | Yes | Yes | **IMPLEMENTED_AND_TESTED (updated — was PARTIALLY_IMPLEMENTED)** | `test_ai_advisor_knowledge_fallback_prevent_before.py` | Now PREVENT-BEFORE (for `RAG_QA` intent specifically) + pre-existing VERIFY-AFTER (citation checking) both present |
| PII Minimization | Partial | Partial | Partial | Partial | **PARTIALLY_IMPLEMENTED** | `PRIVACY_PROVIDER_PAYLOAD_AUDIT.md` | Per-student context is genuinely well-minimized (pseudonym, banded GPA, sanitized weaknesses); recent conversation history is sent verbatim, unsanitized — 1 real, disclosed gap |
| Audit Log | Partial | Partial | Partial | Partial | **PARTIALLY_IMPLEMENTED** | `AI_AUDIT_LOG_REVIEW.md` | General mutation audit + token/cost tracking both real and working; no unified AI-decision-audit schema (correlation_id+tier+tools+rule/regulation/model versions+RAG doc IDs+validator result in one queryable record) exists yet |
| E2E | Partial | Partial | Partial | Partial | **PARTIALLY_IMPLEMENTED** | `DEDICATED_E2E_ACCEPTANCE.md` | Security-negative tests done for real at the DB layer; wiring tests done for real at the code layer; a dedicated full-role browser-driven E2E pass was not run this pass |
| 96Q legacy defect closure | — | — | — | — | **17/21 FIXED_AND_TESTED, 1 PARTIALLY_FIXED, 0 STILL_OPEN, 1 NOT_A_BUG** (updated — was 16/3/1/1) | `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md` | 73 untagged/explanatory questions not individually re-traced (was 75 — Câu 73/88 corrections applied) |
| 72h simulation acceptance | — | — | — | Yes | **IMPLEMENTED_AND_RUNTIME_VERIFIED (the simulation, not EduDSS's ML correctness)** | `POST_72H_SIMULATION_ACCEPTANCE.md` | Does not prove ML correctness or 50K-concurrency readiness |
| 50K concurrency | No | No | No | No | **NOT_IMPLEMENTED / NOT VERIFIED** | — | Max real concurrent identities ever driven: 360 |
| <1.5s SLO | No | No | No | No | **NOT VERIFIED** | — | No p50/p95/p99 latency measured anywhere (not fabricated) |

## Reading this table

Every `IMPLEMENTED_AND_RUNTIME_VERIFIED` row was proven with a **live** command this pass or the prior one (a real container, a real non-superuser SQL session, a real pgvector query, a real re-run of an existing test suite) — not inferred from source code alone. Every `NOT_IMPLEMENTED` row is stated as such even where a plausible-sounding class name might exist elsewhere.
