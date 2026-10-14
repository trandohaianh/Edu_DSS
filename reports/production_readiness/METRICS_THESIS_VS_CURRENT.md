# Thesis-Reported vs. Current Engineering Acceptance Metrics

Purpose: this roadmap must never present a thesis-reported historical
figure as if it were freshly re-verified by this session's engineering
work, and must never present a current engineering result as if it were
the thesis's own number. This document draws that line explicitly, per
metric, with citations.

| Metric | Thesis-reported value | In-repo citation | Current status |
|---|---|---|---|
| Classification/regression accuracy | 0.875 | Not found anywhere in this code repository (thesis document only) | **THESIS-REPORTED ONLY** — no automated test or report in the current codebase independently computes an accuracy figure against real data. Not re-verified this session. |
| RMSE | 0.074 | `data_warehouse/metadata/2ae79454fd66_model.json:17` (and 3 duplicate training-run artifacts) records `0.07379060449061378` | **CONSISTENT** — a real, currently-persisted Linear Regression training-run artifact rounds to the same figure. Caveat: this is a training-run output file, not a CI-asserted test threshold; it was not regenerated fresh by this session, only found already present. |
| R² | 0.992 | Same files, e.g. `data_warehouse/metadata/2ae79454fd66_model.json:19` records `0.9922628559730848` | **CONSISTENT**, same caveat as RMSE above. |
| K-Means k | 4 | Not found anywhere in this code repository | **THESIS-REPORTED ONLY** — no current test or report computes a clustering k against real data. |
| Silhouette score | 0.412 | Not found anywhere in this code repository | **THESIS-REPORTED ONLY** — not re-verified. |
| Davies-Bouldin Index (DBI) | 0.831 | Not found anywhere in this code repository | **THESIS-REPORTED ONLY** — not re-verified. |
| Embedding dimension | 384 | `dss/db/models.py:42` (`_EMBEDDING_DIM = 384 # all-MiniLM-L6-v2 output size`); `dss/db/migrations/versions/4915552f6063_initial_schema.py:330` (`VECTOR(dim=384)`); `dss/core/lms_repository.py:225` | **CURRENT ENGINEERING DEFAULT, VERIFIED LIVE** — this is present-day source code, not a historical claim, and matches the thesis figure. |
| RAG top-k | 5 | `dss/config.py:671` (`RAG_TOP_K_DEFAULT = 5`); `dss/services/rag_service.py:24,58`; `dss/services/vector_store.py:40,155,350` | **CURRENT ENGINEERING DEFAULT, VERIFIED LIVE**, matches the thesis figure. |

## How to describe this honestly in the defense/submission

- It is accurate to say: "The regression model's RMSE/R² figures
  reported in the thesis are consistent with a currently-persisted
  training artifact in this repository."
- It is accurate to say: "The system's current embedding dimension
  (384) and RAG retrieval depth (top-k=5) match the thesis's design."
- It is **not** accurate to say "accuracy/silhouette/DBI were
  re-verified this session" — they were not; this document exists
  precisely so that claim is never made by mistake.
- If asked in defense why accuracy/clustering-quality metrics were not
  re-run: the honest answer is that this engineering engagement's scope
  was production-readiness (persistence, security, scale, recovery,
  onboarding, governance), not re-running the original ML experiments —
  those remain the thesis's own reported results, unmodified and
  untouched by this work.

---

## Addendum — C1.1 claim-safety review (2026-09-26, appended; the historical table above is unchanged)

- The persisted artifact that reproduces RMSE 0.074 / R² 0.992 (`2ae79454fd66`) was trained on
  `sample_data_v1`, i.e. `generate_data()` — **synthetic** data — with only 132 training rows, and its
  feature list included **`xep_loai`, a grade band derived from the target** (target leakage).
- Current training code cannot repeat this: `filter_leakage_features` removes `xep_loai`/`grade`/
  `diem_ky_sau`/`final_score` for any of those targets (proved by `tests/test_c1_ml_leakage_regression.py`
  through the real trainers).
- Classification: **THESIS_HISTORICAL_RESULT** (valid as a record of what the thesis reported);
  **not usable as a COMMERCIAL_CLAIM**. No figure in this table is evidence of predictive accuracy on real
  university students. Safe wording: "trên dữ liệu mô phỏng dùng để minh hoạ; độ chính xác trên dữ liệu thật
  sẽ được đánh giá khi triển khai thí điểm".
