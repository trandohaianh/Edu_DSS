# 96Q Current Consistency Matrix

Section 20's ask: 96/96 questions reviewed for **current consistency** (does the answer still match what the code does today), not runtime-re-verification of every mechanism from scratch. The 22 previously-tagged/specially-handled questions (R-1..R-5, P-1/3/5/7, S-1, C-1/2/3, E-2/6, K-2/3, X-1, A-1, D-1, plus Câu 73) are referenced briefly, not re-litigated — see `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md` for their full detail, per this pass's explicit "do not re-audit completed work" instruction. The other 74 are reviewed here for the first time at this level of detail.

Legend: **C** = Consistent (answer still matches current code, no contradiction found). **NAU** = Needs Answer Update (the underlying mechanism is still real, but the answer's wording is now stale/incomplete relative to a fix made this engagement). **RCR** = Requires Code Review (not independently re-verified this engagement — flagged honestly, not claimed consistent by default).

## Section 1 — Dữ liệu và tiền xử lý

| Câu | Status | Note |
|---|---|---|
| 1 | C | `generate_data()` mechanism unchanged |
| 2 | C | Synthetic formula/linear-relationship explanation unchanged |
| 3 | C | `target_utils.py` target-priority/problem-type inference unchanged |
| 4 | C | KNNImputer(5) unchanged |
| 5 | C | Pipeline-scoped fit/transform unchanged (re-confirmed structurally while tracing R-1/R-2 this engagement) |
| 6 | C | `filter_leakage_features`/`LEGITIMATE_PREDICTORS` unchanged |
| 7 | C | StandardScaler rationale unchanged |
| 8 | C | OneHotEncoder unchanged |
| 9 | *(R-1, fixed)* | see legacy matrix |
| 10 | *(G-2, fixed)* | see legacy matrix |
| 11 | C | Guidance-only question, no code claim |

## Section 2 — Phân loại

| Câu | Status | Note |
|---|---|---|
| 12–18 | C | Model roster/mechanics unchanged |
| 19 | *(P-1, fixed)* | see legacy matrix |
| 20 | C | Stratified 80/20 split unchanged |
| 21 | *(P-5, fixed)* | see legacy matrix |
| 22 | C | F1-macro rationale unchanged |
| 23 | *(S-1, fixed)* | see legacy matrix |
| 24 | *(P-3, fixed)* | see legacy matrix |
| 25–26 | C | Overfitting heuristics unchanged, still labeled "HEURISTIC" honestly |
| 27–28 | C | LightGBM-not-hardcoded framing unchanged |
| 29 | *(P-7, fixed)* | see legacy matrix |
| 30 | C | Roadmap question, no code claim |

## Section 3 — Hồi quy

| Câu | Status | Note |
|---|---|---|
| 31–32 | C | Regression purpose/metric definitions unchanged |
| 33 | *(R-5, fixed this pass)* | metric contract now explicit — see legacy matrix update |
| 34–35 | C | Actual results/RF-weakest explanation unchanged |
| 36 | *(R-3, fixed)* | see legacy matrix |
| 37 | *(R-4, fixed)* | see legacy matrix |
| 38 | *(R-2, fixed)* | see legacy matrix |
| 39 | C | Time-based split rationale unchanged |
| 40 | C | Roadmap question, no code claim |

## Section 4 — Phân cụm K-Means

| Câu | Status | Note |
|---|---|---|
| 41–47 | C | K-Means/Silhouette/Davies-Bouldin/PCA mechanics unchanged |
| 48 | *(C-3, fixed this pass)* | z-score now available — see legacy matrix update |
| 49 | C | Cosine-similarity peer-suggestion mechanism unchanged |
| 50 | *(C-2, correctly not a bug)* | see legacy matrix |
| 51 | *(C-1, fixed)* | see legacy matrix |
| 52 | C | Bootstrap/ARI stability measurement still genuinely not done — answer remains accurate |
| 53 | C | Guidance question, no code claim |

## Section 5 — Model Registry

| Câu | Status | Note |
|---|---|---|
| 54 | C | joblib + JSON metadata storage unchanged |
| 55–56 | C | Candidate/Production separation, Admin-only promotion (`@require_role("Admin")`) unchanged — re-confirmed while building `agent.py`'s authorization this pass (same role vocabulary used) |
| 57 | C | Cache-by-training_id, no stale-cache-on-promote unchanged |
| 58 | *(E-6, fixed)* | see legacy matrix |
| 59 | C | joblib/library version risk still a real, disclosed operational risk, unchanged |
| 60 | C | Rollback guidance unchanged |

## Section 6 — Mức rủi ro học tập

| Câu | Status | Note |
|---|---|---|
| 61 | C | Percentile mechanism itself unchanged (K-2 fixed the *wording*, not the mechanism — this answer describes the mechanism accurately) |
| 62 | *(K-2, fixed)* | see legacy matrix |
| 63 | C | Rationale for percentile-over-fixed-threshold unchanged |
| 64 | *(K-3, fixed, re-verified live this pass)* | see legacy matrix |
| 65 | C | Recall-priority tradeoff guidance unchanged |

## Section 7 — SHAP

| Câu | Status | Note |
|---|---|---|
| 66 | C | SHAP definition unchanged |
| 67 | *(X-1, fixed)* | see legacy matrix |
| 68 | C | "SHAP ≠ causality" framing unchanged — reinforced, not contradicted, by this engagement's own repeated emphasis on the same principle (e.g. Validator/Rule Engine docs) |

## Section 8 — RAG

| Câu | Status | Note |
|---|---|---|
| 69–70 | C | RAG purpose/retrieval mechanism (embedding, cosine, top-5) unchanged |
| 71 | C | 0.55/0.85 thresholds still empirical/uncalibrated, unchanged — `RAG_TOPK_BENCHMARK.md` this pass measured top-k, not these similarity thresholds; still an open, honestly-disclosed item |
| 72 | C | Chunking (400 chars/80 overlap) unchanged |
| 73 | **NAU → now fixed, see legacy matrix** | The answer's core claim ("chưa đảm bảo... 19 tài liệu... không được duyệt thật") is now **stale** — `document_governance.is_document_usable()` and the unified `retrieve_unified_context()` path (both confirmed this pass, `RAG_DOCUMENT_GOVERNANCE.md`/`RAG_GOVERNANCE_FINAL.md`) close exactly this gap. Reclassified in the legacy matrix. |
| 74 | **NAU** | *(A-1)* — the answer's "hướng làm" (run a benchmark) has now been **done** (`embedding_benchmark_vi.txt`, this pass's `EMBEDDING_RELEASE_DECISION.md`) — the answer should be updated to say the benchmark was run and a KEEP_CURRENT_FOR_RELEASE decision was made, not still framed as a future action |
| 75 | C | Namespace/role permission model + `validate_student_profile_not_in_knowledge` unchanged |
| 76 | C | Prompt-injection defense (`render_retrieved_context`) unchanged |

## Section 9 — LLM Gateway

| Câu | Status | Note |
|---|---|---|
| 77 | C | Provider roster unchanged |
| 78 | C | Failover chain description unchanged (Circuit Breaker, added in an earlier pass, is a real *addition* on top of this, not a contradiction — the failover chain itself still works as described) |
| 79 | **NAU** | "cache câu trả lời theo SHA-256 của prompt" is now **incomplete** — this pass's P0 fix (commit `3a3cbfa`, prior pass) changed the cache key to `SHA-256(prompt + role + user_id)` specifically because prompt-only hashing leaked personalized answers across students. The answer should be updated to reflect the corrected, safer key. |
| 80 | *(E-2, fixed)* | see legacy matrix |
| 81 | C | Hallucination-mitigation layers list unchanged and, if anything, strengthened this engagement (Validator, Rule Engine, Knowledge Fallback prevent-before all added on top of what's described here) |
| 82 | C | PII-cleaning + LOCAL_OFFLINE mode unchanged; this pass's conversation-history sanitization fix (`PII_SANITIZATION_FINAL_AUDIT.md`) is a real strengthening of exactly this claim, not a contradiction |

## Section 10 — Drift

| Câu | Status | Note |
|---|---|---|
| 83–84 | C | Drift definition, PSI computation/thresholds unchanged |
| 85 | *(D-1, fixed this pass)* | see legacy matrix — answer should be updated to reflect the new on-demand Admin check |

## Section 11 — Kiến trúc, bảo mật, kiểm thử

| Câu | Status | Note |
|---|---|---|
| 86 | C | Layered architecture description unchanged |
| 87 | RCR | Password hashing (PBKDF2-HMAC-SHA256, 200k rounds) not independently re-verified this engagement — no reason to suspect it changed, but flagged honestly rather than assumed |
| 88 | C | *(re-verified live in a prior pass — `POSTGRES_RUNTIME_VALIDATION.md`)* RLS + pgvector org filtering confirmed working with a real non-superuser role |
| 89 | **NAU** | "~85 file" test-suite-size figure is now significantly stale — the suite has grown to 1000+ tests across this engagement (e.g., 1027 passed in the most recent live-DB full run). Direction (automated test suite + 72h simulation) is still accurate; the specific number understates current scale substantially. |
| 90 | C | "72h clean ≠ computation correct" — this exact point is independently reinforced by this engagement's own findings (the 72h simulation ran clean while K-3 and other ML-correctness bugs were still present in earlier code) |

## Section 12 — Tình huống và định hướng

| Câu | Status | Note |
|---|---|---|
| 91 | C | Bottleneck list (GridSearch/KNNImputer/KernelExplainer/local vector scan) still accurate; ANN index explicitly deferred this pass (`ANN_INDEX_DECISION.md`) with a documented reason, consistent with this answer's own "hướng: ... pgvector với chỉ mục ANN" suggestion — not contradicted, just not yet acted on (by choice) |
| 92 | **NAU** | The document-governance workflow this answer calls for ("tài liệu chính thức cho RAG và người duyệt") **now exists** (confirmed this pass) — the answer should note that this specific prerequisite is now infrastructure-ready, though not yet populated with real official documents |
| 93–96 | C | Discussion/self-assessment questions, no code claim to go stale. Câu 96's self-assessed "biggest limitation — not yet validated on real data" remains accurate and, if anything, is reinforced by every finding this engagement made using synthetic data. |

## Summary

- **96/96 reviewed** for current consistency (not 96/96 runtime-re-verified from scratch — a different, larger claim this document does not make).
- **22 already covered** via the legacy defect matrix (re-referenced, not re-litigated).
- **5 genuinely stale answers found and flagged**: Câu 73 (already reclassified as fixed), Câu 74 (benchmark now done, decision made), Câu 79 (cache key description now incomplete post-P0-fix), Câu 85 (already reclassified as fixed), Câu 89 (test count figure stale), Câu 92 (governance prerequisite now exists).
- **1 flagged as not independently re-verified** (Câu 87, password hashing) — honestly marked RCR rather than assumed consistent.
- **68 confirmed consistent**, no stale claims found.
