# Phase 12A observability and monitoring

Base: `291dcef665a747d30c72513ea8cd7271fe9dcb23`. Branch/worktree: `observability-hardening` / `D:\KLTN\edudss-observability`. This branch does not modify Docker, dependency manifests, migrations, database models, RLS or persistence architecture.

| Capability | Before | Implementation | Files | Tests | Security/privacy impact | Remaining limitation |
|---|---|---|---|---|---|---|
| Structured logging | Rotating technical log used plain text | JSON lines on the existing `get_logger(name)` handler; fixed metadata fields, counts and duration | `dss/core/logging_config.py`, `dss/core/observability.py` | `test_observability_phase12a.py` | Phase 8A redaction retained; messages redacted before JSON serialization | Process-local log file; central aggregation requires deployment tooling |
| Correlation IDs | No operation trace ID | Random 128-bit ID per Streamlit script rerun; ContextVar scopes nested service calls | `run_dss.py`, `dss/core/observability.py` | Correlation scope test | No student/account identifier in ID | No HTTP middleware; threads/processes need explicit propagation |
| Operation timing and error counters | Ad hoc duration logs | `perf_counter` timing, success/error counters and bounded in-memory recent duration list | `dss/core/observability.py` | Timing/error tests | Only low-cardinality labels retained | Counters reset on restart and are per process |
| AI provider | Gateway token accounting existed, but latency/error/fallback telemetry was incomplete | Gateway and direct provider stream timing; per-attempt success/error, provider/model, approximate input/output tokens and fallback reason | `dss/services/llm_gateway.py`, `dss/core/models.py` | AI error/secret test and gateway regression | No prompt or key logged; caught exception logged by class only | Direct provider paths that convert errors to text may show a completed stream; gateway attempt metric represents actual failure |
| RAG retrieval and embedding | No shared timing/count telemetry | Retrieval top-k and result count; local/pgvector backend labels at store search, embedding timing; no document payload | `dss/services/rag_service.py`, `dss/services/vector_store.py`, `dss/core/models.py` | RAG privacy and backend tests, store regression | No query or retrieved chunk content logged | The high-level service may use a provider that does not expose a store backend; its backend label is generic |
| CMS/RAG ingestion | No common latency metric | Timing around document and lecture ingestion | `dss/services/document_ingestion.py`, `dss/services/cms_lecture_repository.py` | CMS/RAG regression | No document bytes or text logged | Number of indexed chunks is not yet captured across all stores |
| ML prediction | No prediction latency/batch metric at UI prediction calls | Wrapper around personal, file and batch prediction calls with model class and batch size | `dss/core/observability.py`, `dss/tabs/ml_hub.py` | ML privacy test and prediction regression | No feature row values logged | Training/evaluation prediction calls outside these UI paths are not individually timed |
| Database diagnostics | No unified safe readiness probe | Configured PostgreSQL `SELECT 1` and conditional pgvector extension check with timing; no connection URL or SQL parameter logging | `dss/core/health_diagnostics.py` | Readiness failure test | No credentials emitted | Transaction-level timings and distributed metrics deferred to a later DB observability change |
| Liveness/readiness | Streamlit server health can be green while app dependencies fail | Separate functions for process liveness and configured dependency readiness; AI configuration and artifact checks are passive | `dss/core/health_diagnostics.py` | Liveness/readiness test | No paid provider calls or secrets in result | These are Python diagnostics, not a new HTTP endpoint; app script and authenticated UI checks remain separate |

## Operational use

`get_logger(name)` remains the application logging interface. The existing rotating `technical.log` now contains JSON lines with `timestamp`, `level`, `logger`, `correlation_id`, `message` and optional allowlisted operation fields. `metrics_snapshot()` provides bounded process-local counters and recent durations. `liveness()` reports process reachability; `readiness()` probes only configured required dependencies. The Streamlit health endpoint remains a server liveness check and must not be interpreted as application readiness.

The correlation ID is an operation ID for one Streamlit rerun; it is not an incoming HTTP request ID. Work delegated to a new thread does not inherit a `ContextVar` automatically. Prometheus/OpenTelemetry, exporter endpoint, retention policy, alerting, distributed traces and transaction instrumentation require infrastructure choices and are deferred.

## Verification

All commands below were run from this worktree's `app/` directory with the shared Python environment. Each line is a separate run; counts are not added because some test files overlap.

| Command group | Passed | Skipped | Failed |
|---|---:|---:|---:|
| `test_observability_phase12a.py` | 8 | 0 | 0 |
| `test_security_logging.py test_security_prompt.py` | 5 | 0 | 0 |
| `test_llm_service.py` | 39 | 1 | 0 |
| `test_lms_ai_rag_gateway.py test_lms_cms_integration.py test_prediction_source_of_truth.py` | 34 | 0 | 0 |
| `test_integration_phase1b_security8a.py test_security_upload.py` | 14 | 8 | 0 |
| `test_pgvector_store.py test_lms_cms_integration.py test_rag_source_governance.py` | 12 | 11 | 0 |

`compileall` passed for every changed Python file. The full suite was not completed. A broad multi-file attempt and `test_rag_service.py` were stopped after prolonged execution; that RAG suite loads a real sentence-transformer model and is not counted as passing. PostgreSQL tests requiring a configured database were skipped in the runs above. No Docker acceptance run was made in this branch; another agent owns that gate.

## Integration notes

Likely textual conflicts are in `run_dss.py`, `dss/core/models.py`, `dss/services/llm_gateway.py`, `dss/services/vector_store.py` and `dss/tabs/ml_hub.py` if parallel integration work edits the same entry points. Keep the current integration behavior and reapply the small instrumentation call sites. The new observability, health and test modules are additive. No changes were merged into main or integration.
