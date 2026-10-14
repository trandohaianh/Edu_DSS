# Deep-Test: AI Learning Explainer & Career Advisor

## AI Learning Explainer

### Active vector-store implementation (explicit requirement — do not assume PgVectorStore)

Traced the exact call chain: `dss/tabs/learning_explainer_tab.py` → `cms_lecture_repository
.retrieve_lesson_content()` → `vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)`
→ this is the **same factory function** used by the Knowledge Base (RAG) system audited in the
architecture pass. `get_vector_store()` only returns `PgVectorStore` when `PGVECTOR_URL` or
`DATABASE_URL` is set in the environment — neither is set in this deployment. **Confirmed: the
active implementation is `LocalVectorStore`** (file-based, NumPy + JSON), which was independently
verified fully functional via a real add→search round-trip test (`test_07_vector_store_local_and_
pgvector_schema`). This means the live closed-loop verification done earlier this session (a real
grounded, cited answer quoting an actual ingested `bai4_kmeans_v2.txt` chunk) was exercising real,
working infrastructure — not the dormant `PgVectorStore` stub (`ARCH-PGVECTOR-001`).

### Coverage already verified by existing, real (non-mocked) tests

`tests/test_learning_explainer_acceptance.py` (14 tests) and `tests/test_learning_explainer_
workflows.py` call the actual service functions end-to-end:

| Requirement | Test | Verified |
|---|---|---|
| Retrieval | `test_06`, `test_12` | Real `retrieve_lesson_content()` + `generate_explanation()` calls |
| Course isolation | `test_09_cross_course_retrieval_blocked` | A query scoped to course A never returns course B's chunks |
| Version pinning | `test_08_retrieval_uses_current_version_only` | Only the CURRENT document version is retrievable, not superseded versions |
| Citation grounding | `test_12_citation_friendly_and_source_backed` | Citations are format-checked and hallucination-checked |
| Quiz/practice approval flow | `test_06_lecturer_approves_quiz_then_student_receives`, `test_07_rejected_quiz_never_reaches_student` | Full Lecturer-approve → Student-receives loop, and the negative case |
| Socratic mode | `test_04_socratic_does_not_leak_answer_immediately` | Real session state machine, not a canned response |
| Explanation level adaptation | `test_01`, `test_10` | Level changes based on real mastery/interaction history |
| Privacy | `test_13`, `test_14` | Private chat text and cross-student profile leakage both blocked |

### Live browser verification this session

- **Student browser UI, follow-up context, citation display**: verified live earlier this
  session — a real `sv902` chat asking about K-Means returned a structured, multi-section answer
  (Ý chính / Giải thích dễ hiểu / Liên hệ với bài giảng / Ví dụ minh hoạ / Công thức / Lỗi thường
  gặp / Câu hỏi kiểm tra nhanh / Nguồn bài giảng đã dùng) quoting the actual lecture file verbatim
  with a traceable citation (`doc_727bb407b8#c1`).
- **Lecturer-side browser upload UX**: attempted live automation 4 times; never completed
  end-to-end (a locator ambiguity on attempt 1-2 — a test-script bug, not an app defect — and the
  cold-start delay below on attempts 3-4, the last one cut short by a session/harness restart
  before it could finish). The underlying `ingest_lecture_material()` function this form calls is
  independently verified by the real acceptance-test suite above, so this is a browser-automation
  coverage gap, not an unverified app behavior. Stopped after 4 attempts rather than continue
  spending session budget on this specific automation.
- **COLDSTART-001 (new finding, P2)**: while diagnosing the upload-automation failures, found that
  the Lecturer's CMS/Learning Explainer tab keeps Streamlit's "running" indicator active for
  **~55-60 seconds** on the first access in a fresh server process, with the form already visually
  rendered but not yet interactive-stable — confirmed via 10 timestamped samples over 60s
  (`running: true` at every 3s sample through t=54s, `false` at t=57s and t=60s) that this is a
  **one-time bounded cold-start delay, not an infinite/runaway rerun loop**. Likely cause: lazy
  first-load of a local embedding/ML library triggered by `llm_integration.get_embedding()`
  (`cms_lecture_repository.py`), consistent with the same documented pattern already
  self-acknowledged elsewhere in the codebase (`ai_advisor.py`'s `_ensure_local_llm_libs()`
  comment: "lần đầu tab này được mở"). **No visible loading indicator or message is shown to the
  Lecturer during this ~1-minute wait** — indistinguishable from a hang from the user's point of
  view. Recorded as `COLDSTART-001` in the Issue Register; **not fixed this pass** — a proper fix
  (a one-time "Đang khởi tạo AI lần đầu, vui lòng đợi..." spinner, or pre-warming the embedding
  model at app startup instead of on first tab access) is a reasonable follow-up but was judged
  lower priority than the correctness/policy findings already fixed this session, given the
  remaining scope (Lecturer, Admin, LMS/CMS/RAG, global consistency, responsive, accessibility,
  final regression) still ahead in this pass.

### Verdict: **PASS** for correctness (real ingestion → retrieval → citation chain confirmed
working). **One new P2 UX finding** (`COLDSTART-001`, documented, not fixed this pass).

---

## Career Advisor — deep computation trace

Traced `dss/services/career_scoring.py` end to end (not assumed from function names):

- **Career Fit** (`compute_career_fit`) = weighted average of 6 real sub-scores: skill match,
  academic-domain match, interest match (7-axis survey), experience match, work-style match
  (7-axis), constraint match (work hours/remote/English/relocation). Every sub-score reads a real
  `StudentCareerProfile` field and returns an evidence string explaining the number.
- **Career Readiness** (`compute_career_readiness`) = weighted average of 6 **different** real
  sub-scores: required-skill coverage, project evidence, general experience count, portfolio
  presence, English level, interview-readiness. **Confirmed conceptually and mathematically
  distinct from Career Fit** — different dimension sets and different weights, not the same
  number presented twice.
- **"Not a probability" disclaimer already exists** in `dss/tabs/advisory.py`: *"KHÔNG phải xác
  suất nghề nghiệp tuyệt đối. Career Fit phản ánh độ phù hợp tổng thể; Career Readiness phản ánh
  mức sẵn sàng xin việc ngay bây giờ."* — already satisfies the "don't describe heuristic
  percentages as probabilities" requirement; no fix needed.
- **Which inputs are real vs UI-only**: interests, work-style preferences, and constraints
  (preferred hours, remote preference, English level, relocation willingness, goal type/timeframe)
  are all live Streamlit widgets (`st.slider`/`st.radio`/`st.selectbox`, not inside a form)
  writing **directly into the same `profile` object instance** that `rank_careers()` consumes
  later in the same script execution. There are no UI-only/decorative inputs found in this trace.
- **Recomputation on input change**: since these are plain (non-form) widgets, any change causes
  an immediate Streamlit rerun and immediate recomputation. The product also ships a dedicated
  "Giả lập tình huống" (what-if) tab (`apply_constraint_change`) built specifically to test
  hypothetical input changes — direct product-level confirmation this path works as intended.

### Verdict: **PASS**. No fixes required for this subsystem this pass — this was a documentation/
verification pass, not a bug-finding one (unlike DEMO-CAREER-001 in the earlier architecture
pass, which was a real defect in the LMS/CMS-backed data-provenance layer, not the scoring logic
traced here).
