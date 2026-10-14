# PERFORMANCE_BEFORE — Learning Explainer cold/warm load, pre-optimization

Measured live, against the running app (`streamlit run run_dss.py --server.port 8765`),
via Playwright timing scripts (browser wall-clock, not synthetic). Python-level timings
cross-checked with dev-only instrumentation (`dss_config.perf_mark`, gated by
`EDUDSS_PERF_DEBUG=1`, never active in production). All values are single/few-run
measurements on one dev machine — reported as ranges where repeat runs varied, not
averaged/fabricated.

## Baseline before this pass

Non-E2E: 444/444. E2E: 38/38 (482/482 total — the PRE-OPTIMIZATION baseline accepted at
the end of the prior "RAG governance" pass).

## Section 1 — Coarse breakdown (Admin role, browser wall-clock)

| Step | Measured | Notes |
|---|---|---|
| A. First paint (login screen) | 6.6–12.4s | Streamlit dev-server first response, not embedding-related |
| B. Login → landing page ready | 3.3–6.5s | Auth + initial rerun |
| C. Landing → Admin home report render | 6.5–8.0s | `admin_reports.py` — see finding #1 below |
| D. → Kho dữ liệu (Data warehouse) | 1.8–11.8s | No embedding use expected |
| E. → Model Registry | 1.6–6.5s | No embedding use expected |
| F. → Trợ lý AI (AI Advisor) tab, first open | 1.6–2.7s | See finding #2 — measured low here only because C or a prior step already paid the import cost in the same process |
| G. → Giải thích Bài giảng (Learning Explainer), Admin/Lecturer view, cold | **60.5–96.5s** | Dominant cost — see finding #3 |
| H. Re-open Learning Explainer (same process) | not cleanly isolated before fix (blocked by finding #3's cost repeating) | |

## Section 1 (E–L) — Fine breakdown of the heavy stack (isolated Python, warm OS disk cache)

Measured directly via `python -c "..."` timing `import dss.config`, `_ensure_local_llm_libs()`,
raw `SentenceTransformer(...)`, and `.encode()`:

| Sub-step | Measured |
|---|---|
| E. `import torch` (inside `_ensure_local_llm_libs`) | 2.4–10.6s (varies with OS disk-cache warmth — see caveat below) |
| F. `import transformers` (`AutoTokenizer/AutoModel`) | 4.1–5.5s |
| G. `import sentence_transformers` | 0.3–0.5s |
| **Total heavy import (`_ensure_local_llm_libs` TOTAL)** | **6.8–16.1s**, one-time per process |
| H. `SentenceTransformer(model_name)` instantiation (local cache, no re-download) | 3.4–4.5s per raw call (this cost is why a shared cache matters — see finding #4) |
| I. Vector-store init (`vector_store.get_vector_store(...)`) | not separately measurable — backed by flat `.npy` files, sub-10ms in practice |
| J. First `encode()` call | 0.45s |
| K. First real retrieval (student asks first question — full path: import + model load + retrieval + LLM call) | not cleanly isolated before fix (see G) |
| L. First LLM request | included in K; external provider latency, not part of this optimization's scope |

**Methodological caveat (honesty, not hedging):** steps E/F showed real run-to-run
variance (2.4s–10.6s for `torch` alone) on the same machine, attributable to Windows
OS-level file-cache/antivirus-scan state, not to any code change. Before/after
comparisons in this pass control for this by taking multiple runs and reporting ranges,
and by measuring "before" and "after" in the same session on the same machine.

## Findings (root causes)

**Finding #1 — `admin_reports.py:199`.** The Admin home page ("Báo cáo hệ thống")
unconditionally called `dss_config._ensure_local_llm_libs()` inside its always-rendered
"Trạng thái hệ thống AI/RAG" panel, just to display whether the embedding model package
is installed — paying the full torch/transformers import cost on a page that never uses
embeddings, contradicting the Section 11 target ("Admin Dashboard → no embedding model
required").

**Finding #2 — `ai_advisor.py:393`.** The "Trợ lý AI" tab (default sub-tab of "🤖 Tư vấn
— AI (LLM)", opened by every role) unconditionally called the same function merely to
list "Hugging Face (Local/Cloud)" as a provider option — again paying the full import
cost just to check package presence, which the cheap `find_spec`-based
`dss_config.HF_AVAILABLE` flag already provides without any import.

**Finding #3 — CMS test-data accumulation (the dominant cost, ~50-85s of the observed
60-96s).** Instrumenting the actual render path (`learning_explainer_tab` →
`_render_lecturer_view` → `_render_lesson_management` / `_render_quiz_review_queue`)
showed `list_lessons()`/`list_pending_quizzes()` themselves were fast (<0.05s for even
743 records — plain JSON parse), but the **unconditional per-item widget rendering loop**
after them was not: `data_warehouse/cms/lessons_registry.json` had accumulated **743
lesson records** (742 of them with `course_id` literally `TEST_COURSE_<uuid>` or
`GOV_COURSE_*`/`GOV_ML_*`/`GOV_HIST_*`, all dated 2026-09-12 — automated-test fixtures
from this session's own pytest/Playwright suites that were never cleaned up, sharing the
same JSON store the manual dev server reads from) and `quiz_review_queue.json` had
**176 items** (175 test-linked). Streamlit's `st.tabs()` renders **all** tab bodies on
every rerun regardless of which tab is visually selected, so opening "📖 Giải thích Bài
giảng (CMS)" as Admin/Lecturer always rendered management UI + a full quiz-review queue
(container, columns, badges, per-question edit fields) for every one of those records —
thousands of Streamlit widgets — every single time, independent of ML/embeddings
entirely. This is real test-isolation debris, not a production-representative number, but
it was the actual number this pass would otherwise have "fixed" by fabricating an
ML-import story around it.

**Finding #4 — model/vector-store ownership (verified correct, no fix needed).**
`init_trainers_and_warehouse()` (`dss/core/init_app.py`) is already `@st.cache_resource`,
giving one shared `MultiAIProvider` (hence one `llm_integration`) per process, not
recreated per rerun. `MultiAIProvider.load_embedding_model()` (`core/models.py:685`) is
already `@st.cache_resource` with a `_self`-prefixed first arg (excluded from Streamlit's
hash key), so the cache is keyed only on `model_name`/`hf_token` — genuinely global, not
per-instance. `core/models.py:1116` (`call_ai_provider`, HF-local branch) is already
correctly lazy (gated by `provider == "huggingface"`). **No duplicate-instantiation bug
existed** — Sections 4/6 were already satisfied by the existing architecture before this
pass; this pass's job was removing the two *unnecessary trigger sites* (#1, #2), not
building new caching.
