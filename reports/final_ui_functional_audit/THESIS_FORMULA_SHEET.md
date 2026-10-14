# EduDSS — Thesis Formula Sheet

All formulas below are either (a) standard textbook formulas as implemented by the
underlying library (scikit-learn/XGBoost/LightGBM/imbalanced-learn), or (b) exact
project-specific formulas read directly from source this session. Where a formula is
project-specific, the source file is cited.

## 1. Preprocessing

**Z-score standardization** (`StandardScaler`): `z = (x - mean) / std`

**Min-Max scaling** (used in some visualization/normalization paths): `x' = (x - min) / (max - min)`

**IQR outlier bound**: `Q1 - 1.5*IQR` to `Q3 + 1.5*IQR`, where `IQR = Q3 - Q1`

**KNNImputer**: missing value replaced by the mean of the `k` nearest neighbors' values
for that feature, distance computed over the other available features.

**SMOTE (Synthetic Minority Over-sampling Technique)**: for a minority-class sample `x_i`,
pick a random neighbor `x_zi` among its `k` nearest minority-class neighbors, generate a
synthetic point: `x_new = x_i + λ * (x_zi - x_i)`, `λ ~ Uniform(0,1)`.

**Critical anti-leakage note (verified in `dss/core/trainers.py`):** `train_test_split`
is applied BEFORE `KNNImputer`/`StandardScaler`/`OneHotEncoder`/SMOTE. All four are wrapped
in a `Pipeline`/`ImbPipeline` fit only inside `GridSearchCV`'s internal training folds — the
test set is never used to fit any preprocessing step. A separate
`filter_leakage_features()` guard removes target-correlated columns before training starts.

## 2. Classification metrics

- **Accuracy** = `(TP + TN) / (TP + TN + FP + FN)`
- **Precision** = `TP / (TP + FP)`
- **Recall** = `TP / (TP + FN)`
- **F1** = `2 * (Precision * Recall) / (Precision + Recall)`
- (Multi-class: scikit-learn `average='weighted'` or `'macro'` per the code's metric call)

## 3. Regression metrics

- **MAE** = `(1/n) * Σ|y_i - ŷ_i|`
- **MSE** = `(1/n) * Σ(y_i - ŷ_i)²`
- **RMSE** = `sqrt(MSE)`
- **R²** = `1 - (Σ(y_i - ŷ_i)² / Σ(y_i - ȳ)²)`

## 4. Clustering

- **K-Means objective (inertia)**: minimize `Σ_k Σ_{x∈C_k} ||x - μ_k||²`
- **Elbow method**: plot inertia vs `k`, pick the `k` where marginal inertia reduction
  drops off (visual heuristic, not a closed-form optimum).
- **Silhouette score** for a point `i`: `s(i) = (b(i) - a(i)) / max(a(i), b(i))`, where
  `a(i)` = mean intra-cluster distance, `b(i)` = mean nearest-cluster distance. Averaged
  over all points for the overall score, range `[-1, 1]`.
- **Davies-Bouldin index**: `DB = (1/k) * Σ_i max_{j≠i} ((σ_i + σ_j) / d(c_i, c_j))`,
  lower is better (`σ` = average intra-cluster distance, `d(c_i,c_j)` = distance between
  cluster centroids).

## 5. SHAP (SHapley Additive exPlanations)

Shapley value for feature `j` on instance `x`:
`φ_j = Σ_{S⊆F\{j}} [|S|!(|F|-|S|-1)! / |F|!] * [f(S∪{j}) - f(S)]`

Interpretation used in this project: `φ_j` is the marginal contribution of feature `j` to
moving the prediction away from the baseline (expected) prediction, averaged over all
possible feature subset orderings. **This is a contribution decomposition, not a causal
statement** — SHAP explains what the trained model used, not what causes the outcome in
reality.

## 6. Retrieval (RAG)

- **Cosine similarity**: `cos(A,B) = (A·B) / (||A|| * ||B||)`, used to rank document chunks
  against the query embedding.
- **Precision@k** = `(relevant items in top-k) / k`
- **Recall@k** = `(relevant items in top-k) / (total relevant items)`
- **MRR (Mean Reciprocal Rank)** = `(1/|Q|) * Σ (1 / rank_of_first_relevant_result)`
- **Retrieval gate actually implemented** (`dss/config.py`):
  `RAG_TOP_K_DEFAULT=5`, `RAG_RELATIVE_THRESHOLD=0.85` (a candidate must score within 85%
  of the top hit's score to be kept), `RAG_LOW_CONFIDENCE_FLOOR=0.55` (absolute minimum
  similarity; below this, the system returns NO_RELEVANT_EVIDENCE rather than a forced
  citation).

## 7. Token / cost estimation

`estimated_cost = (input_tokens * price_per_input_token) + (output_tokens * price_per_output_token)`,
tracked per call in `dss/services/token_tracker.py`. Prices are configured constants, not
a live pricing API integration — must be described as "a real token-count-based estimate,"
not "billing-accurate cost tracking."

## 8. Classification algorithm grids (exact, verified `dss/core/trainers.py` this session)

| Algorithm | Grid | Combinations | CV | Total fits |
|---|---|---|---|---|
| Random Forest Classifier | `n_estimators:[100,200] × max_depth:[10,20,None] × min_samples_split:[2,5] × min_samples_leaf:[1,2]` | 24 | 5-fold | **120** |
| XGBoost Classifier | fixed params (`n_estimators=200, max_depth=5, learning_rate=0.1`), **no GridSearchCV** | 1 | none | **1** |
| LightGBM Classifier | `n_estimators:[100,200] × max_depth:[3,5] × learning_rate:[0.1,0.2]` | 8 | 5-fold | **40** |
| Logistic Regression (Softmax) | `C:[0.1,1.0,10.0] × solver:[lbfgs]` | 3 | 5-fold | **15** |

XGBoost Classifier skips `GridSearchCV` due to a documented workaround: rare multi-class
CV folds can produce "Invalid classes inferred from unique values of y" crashes when a
class becomes non-contiguous within a fold. This is a real, intentional engineering
tradeoff — must be disclosed, not hidden.

## 9. Regression algorithm grids (exact, verified `dss/core/trainers.py`, single source of
truth per `ML-REG-001`)

| Algorithm | Combinations | CV | Total fits |
|---|---|---|---|
| Random Forest Regressor | 12 | 5-fold | **60** |
| XGBoost Regressor | 18 | 5-fold | **90** |
| LightGBM Regressor | 18 | 5-fold | **90** |
| Linear Regression | 0 (no hyperparameters tuned) | n/a | **1** |

**Do not restore the historical claim of a 36-combination Random Forest grid — it was
never actually executed; the current, single source of truth is 12 combinations / 60 fits.**

## 10. Synthetic target formula (sample dataset), exact from `dss/core/data_helpers.py::generate_data()`

```
diem_ky_sau = 0.60 * diem_ky_nay
            + 0.15 * diem_giua_ky
            + 0.10 * diem_du_an
            + 0.10 * (ty_le_diem_danh * 10)
            + 0.05 * (so_gio_hoc_tuan / 3.5)
            + noise(σ = 0.08)
```
Result clipped to `[0, 10]`, then further clamped to within `±1.5` of `diem_ky_nay`.

This is why regression models trained on the bundled sample dataset show a very high R² —
the target is a deterministic linear combination of the inputs plus a small noise term,
not an independent real-world measurement. The code's own docstring already warns this
must not be read as evidence of real-world predictive accuracy. This is a **synthetic-data
construction artifact**, not a data-leakage bug in the traditional sense (a dedicated
`filter_leakage_features()` guard does run and does remove target-correlated columns
before training).
