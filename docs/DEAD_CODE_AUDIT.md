# EduDSS Dead Code & Legacy Compatibility Audit Report

**Audit Date**: 2026-09-11
**Auditor**: Antigravity Assistant
**Scope**: All source modules, scripts, and artifacts in `dss/`, `tests/`, and root package.

---

## 1. Removed Dead Modules & Artifacts

| Path | Type | Size | Rationale for Removal |
|---|---|---|---|
| `automl_pipeline.pkl` | Binary Pickle | 105 KB | Unreferenced in all codebase; loading untrusted pickles poses arbitrary code execution risks. |
| `extract_notebook_dataset_refs.py` | Python Script | 1.8 KB | One-off scratch script for parsing legacy Jupyter notebooks; zero references in app or test suites. |
| `tools/find_broken_fstring.py` | Python Script | 2.1 KB | Temporary patch script from prior refactoring phases; non-runtime. |
| `tools/fix_dss_package.py` | Python Script | 1.9 KB | Temporary package path migration script; non-runtime. |
| `tools/fix_min_fstring.py` | Python Script | 1.5 KB | Temporary script for f-string formatting; non-runtime. |
| `tools/split_5py.py` | Python Script | 3.2 KB | Legacy splitting utility from monolith decomposition; non-runtime. |

---

## 2. Removed Legacy Compatibility & Weak RAG Logic

1. **Weak RAG Forcing Fallback**:
   - In `dss/core/models.py:853-855`: `similarities = [item for item in similarities if item[1] >= cutoff] or similarities[:1]`.
   - Removed behavior: System previously forced the highest document to be returned even if similarity score was 0.0 or irrelevant.
   - New behavior: System returns an empty list `[]` with status `NO_RELEVANT_EVIDENCE` when score is below confidence floor.
2. **Auto-Promote on Model Training**:
   - In `dss/core/warehouse.py:399`: `should_promote = bool(is_best) if auto_promote is None else bool(auto_promote)`.
   - Removed behavior: Models marked `is_best=True` automatically became `Production`.
   - New behavior: All trained models enter `CANDIDATE` lifecycle. Only an Admin user can explicitly promote a candidate to `Production`.
3. **Interactive Startup Training**:
   - In `dss/main.py:122` & `dss/core/bootstrap_service.py:273`: Background `GridSearchCV` ran automatically on student/lecturer login if a new dataset was active.
   - Removed behavior: Interactive page loads never trigger model training.
   - New behavior: Model training is an explicit, asynchronous or manual job triggered via ML Hub.

---

## 3. UI Calls Bypassing LLMGateway

- In `dss/tabs/ai_advisor.py:854`: Direct call `llm_integration.call_ai_provider` in chat.
- In `dss/tabs/ai_advisor.py:1076`: Direct call `llm_integration.generate_personalized_advice` for HuggingFace.
- In `dss/tabs/home.py:637`: Direct call `llm_integration.generate_personalized_advice`.
- **Status**: Migrated to Centralized `LLMGateway` for unified token accounting, rate limiting, and fallback handling.

---

## 4. Cleanup pass 2026-11-26

Each item below had exactly one occurrence in the repository (its own definition), checked with `git grep -w`.

- Removed 26 unused functions and 10 unused classes (944 lines), e.g. `EnsembleTrainer`, `data_analysis_tab`, `balance_dataset`, the `pass` stubs `model_1_classification_tab` / `model_2_regression_tab`, four unused `ui_kit` cards, and helpers in `feature_utils`, `career_whatif`, `llm_service`, repositories.
- Removed the imports those definitions left unused.
- Removed files: `EduDSS_UI_Reference_Kit/` (duplicate of `ui_reference/`), `dss/requirements.txt` (legacy duplicate), `tools/exp_balance_compare.py`, 8 unused CSVs in `dữ liệu/`, the generated `reports/release_gate/*.json` (now gitignored) and one stray screenshot.
- Kept on purpose: test-only modules that document features (`moodle_connector`, `token_budget`, `context_builder`, `tenant_service`), the ORM model `RolePermission` (removing it needs a migration).
