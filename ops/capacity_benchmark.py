"""Workstream D capacity/concurrency benchmark (§4.2, §4.3).

Scope decision (read before extending): EduDSS's UI is Streamlit, which
runs one Python script execution per browser session — it is not a
stateless REST API, and simulating N real browser sessions via Playwright
at N=500-1000 would (a) be dominated by browser/Chromium process overhead
rather than the application's own bottleneck, and (b) was judged
impractical on this development machine given the Docker Desktop
instability already observed in this session at far lower load (see
ABC_INTEGRATION_ACCEPTANCE.md). The actual SHARED resource multiple
concurrent users contend for in this architecture is PostgreSQL —
connections, RLS-scoped queries, writes — so this benchmark drives
concurrent REAL database operations (through the same repository
functions the application itself calls, not raw synthetic SQL) via
`ThreadPoolExecutor`, which is the honest way to find this specific
architecture's actual capacity boundary on this specific machine. This
is NOT a claim about frontend/HTTP concurrency limits, which are not what
was tested here.

20,000 REGISTERED students != 20,000 concurrent users. This module tests
concurrency (simultaneously-active operations), never registered-user
counts.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import create_engine, text


@dataclass
class OperationResult:
    latency_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class ConcurrencyLevelResult:
    concurrency: int
    total_operations: int
    duration_seconds: float
    throughput_ops_per_sec: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_count: int
    error_rate: float
    errors_sample: list[str] = field(default_factory=list)
    pg_connections_observed: Optional[int] = None


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _observe_pg_connections(owner_url: str) -> Optional[int]:
    try:
        engine = create_engine(owner_url)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")).scalar_one()
        engine.dispose()
        return int(count)
    except Exception:
        return None


def run_concurrency_level(
    operation: Callable[[], Any],
    concurrency: int,
    operations_per_worker: int,
    owner_url_for_pg_observation: Optional[str] = None,
) -> ConcurrencyLevelResult:
    """Runs `operation` (a zero-arg callable performing ONE real,
    representative unit of work — e.g. a prediction write + a scoped read)
    concurrently across `concurrency` worker threads, `operations_per_worker`
    times each. Returns real measured latency percentiles/throughput/error
    rate — never fabricated."""
    latencies: list[float] = []
    errors: list[str] = []
    started = time.perf_counter()

    def _run_one() -> OperationResult:
        op_start = time.perf_counter()
        try:
            operation()
            return OperationResult((time.perf_counter() - op_start) * 1000, True)
        except Exception as exc:
            return OperationResult((time.perf_counter() - op_start) * 1000, False, f"{type(exc).__name__}: {exc}")

    total_ops = concurrency * operations_per_worker
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_run_one) for _ in range(total_ops)]
        pg_connections = _observe_pg_connections(owner_url_for_pg_observation) if owner_url_for_pg_observation else None
        for future in as_completed(futures):
            result = future.result()
            latencies.append(result.latency_ms)
            if not result.success:
                errors.append(result.error or "unknown error")

    duration = time.perf_counter() - started
    latencies.sort()
    error_count = len(errors)
    return ConcurrencyLevelResult(
        concurrency=concurrency, total_operations=total_ops, duration_seconds=round(duration, 4),
        throughput_ops_per_sec=round(total_ops / duration, 2) if duration > 0 else 0.0,
        p50_ms=round(_percentile(latencies, 0.50), 3), p95_ms=round(_percentile(latencies, 0.95), 3),
        p99_ms=round(_percentile(latencies, 0.99), 3), error_count=error_count,
        error_rate=round(error_count / total_ops, 4) if total_ops else 0.0,
        errors_sample=list(dict.fromkeys(errors))[:5], pg_connections_observed=pg_connections,
    )


@dataclass
class CapacitySlo:
    """Explicit TEST SLO, defined BEFORE interpreting any result — never
    a contractual production SLA, always labeled as an experimental
    threshold for THIS benchmark."""
    max_error_rate: float = 0.01  # 1%
    max_p95_latency_ms: float = 500.0


def meets_slo(result: ConcurrencyLevelResult, slo: CapacitySlo) -> bool:
    return result.error_rate <= slo.max_error_rate and result.p95_ms <= slo.max_p95_latency_ms


def run_capacity_profile(
    operation_factory: Callable[[], Callable[[], Any]],
    concurrency_levels: list[int],
    operations_per_worker: int,
    slo: CapacitySlo,
    owner_url_for_pg_observation: Optional[str] = None,
) -> dict[str, Any]:
    """Runs increasing concurrency levels, stopping as soon as one violates
    the SLO (§4.2: "Try increasing... until a practical boundary... is
    found" — never forces a level the task didn't ask to reach, and never
    keeps climbing past a demonstrated failure just to report a bigger
    number). `operation_factory()` is called once per level to build a
    fresh zero-arg operation closure (e.g. so each level can use a fresh
    DB engine/connection pool)."""
    results: list[ConcurrencyLevelResult] = []
    boundary_concurrency: Optional[int] = None
    for level in concurrency_levels:
        operation = operation_factory()
        result = run_concurrency_level(operation, level, operations_per_worker, owner_url_for_pg_observation)
        results.append(result)
        if not meets_slo(result, slo):
            boundary_concurrency = level
            break
    highest_passing = max((r.concurrency for r in results if meets_slo(r, slo)), default=0)
    return {
        "slo": {"max_error_rate": slo.max_error_rate, "max_p95_latency_ms": slo.max_p95_latency_ms},
        "levels": [r.__dict__ for r in results],
        "highest_concurrency_meeting_slo": highest_passing,
        "first_concurrency_violating_slo": boundary_concurrency,
    }
