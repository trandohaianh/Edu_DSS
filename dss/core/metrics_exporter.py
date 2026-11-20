"""/metrics for the health server: request-path counters + business/ops gauges.

Request-path metrics (logins, page views, AI tokens/USD, operations) come from the Streamlit
process through prometheus_client multiprocess files (dss/core/metrics.py). Business gauges
are computed at scrape time from the data root, cached for EDUDSS_METRICS_CACHE_SECONDS:
accounts per role, AI spend today/this month vs budget, infrastructure cost entered by the
admin, the last result of every ops pipeline job, data quality / drift and the backup restore
drill. Access: `Authorization: Bearer $EDUDSS_METRICS_TOKEN`; without a token configured only
loopback clients are served.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from datetime import UTC

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily

_STATUS_VALUE = {"ok": 1.0, "degraded": 0.5, "failed": 0.0}
_SEVERITY_VALUE = {"ok": 0.0, "warn": 1.0, "fail": 2.0}
_cache_lock = threading.Lock()
_cache: dict = {}


def authorized(header: str | None, client_ip: str) -> bool:
    token = os.environ.get("EDUDSS_METRICS_TOKEN", "")
    if not token:
        return client_ip in ("127.0.0.1", "::1")
    supplied = (header or "").removeprefix("Bearer ").strip()
    return bool(supplied) and hmac.compare_digest(supplied, token)


def _business_snapshot() -> dict:
    ttl = float(os.environ.get("EDUDSS_METRICS_CACHE_SECONDS", "30"))
    with _cache_lock:
        hit = _cache.get("business")
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
    snap: dict = {}
    try:
        from dss.services import auth_service

        snap["accounts"] = auth_service.count_users_by_role()
    except Exception:
        snap["accounts"] = None
    try:
        from dss.services import token_tracker

        snap["budget"] = token_tracker.get_system_budget_status()
    except Exception:
        snap["budget"] = None
    try:
        from datetime import datetime, timezone

        from ops import pipeline

        snap["infra_month"] = pipeline.infra_total(datetime.now(UTC).strftime("%Y-%m"))
        snap["runs"] = pipeline.last_runs()
    except Exception:
        snap["infra_month"], snap["runs"] = None, {}
    with _cache_lock:
        _cache["business"] = (time.monotonic(), snap)
    return snap


class BusinessCollector:
    def collect(self):
        snap = _business_snapshot()
        up = GaugeMetricFamily("edudss_exporter_up", "1 when business metrics were collected")
        up.add_metric([], 1.0)
        yield up
        if snap.get("accounts") is not None:
            from dss.core.metrics import role_label

            g = GaugeMetricFamily("edudss_accounts", "Accounts by role", labels=["role"])
            for role, count in snap["accounts"].items():
                g.add_metric([role_label(role)], float(count))
            yield g
        budget = snap.get("budget")
        if budget:
            cost = GaugeMetricFamily("edudss_ai_spend_usd", "AI spend so far in the period", labels=["period"])
            cost.add_metric(["today"], float(budget.get("daily_cost", 0)))
            cost.add_metric(["month"], float(budget.get("monthly_cost", 0)))
            yield cost
            limit = GaugeMetricFamily("edudss_ai_budget_usd", "Configured AI budget", labels=["period"])
            limit.add_metric(["today"], float(budget.get("daily_budget", 0)))
            limit.add_metric(["month"], float(budget.get("monthly_budget", 0)))
            yield limit
        if snap.get("infra_month") is not None:
            infra = GaugeMetricFamily("edudss_infra_cost_month_usd", "Infrastructure cost entered for this month")
            infra.add_metric([], float(snap["infra_month"]))
            yield infra
        runs = snap.get("runs") or {}
        status = GaugeMetricFamily(
            "edudss_pipeline_last_status", "Last run: 1 ok, 0.5 degraded, 0 failed", labels=["task"]
        )
        success = GaugeMetricFamily(
            "edudss_pipeline_last_success_timestamp_seconds", "Unix time of last ok run", labels=["task"]
        )
        duration = GaugeMetricFamily(
            "edudss_pipeline_last_duration_seconds", "Duration of the last run", labels=["task"]
        )
        for job, row in runs.items():
            status.add_metric([job], _STATUS_VALUE.get(row.get("status"), 0.0))
            duration.add_metric([job], float(row.get("duration_s") or 0))
            if row.get("last_success_at"):
                success.add_metric([job], float(row["last_success_at"]))
        yield status
        yield success
        yield duration
        dq = (runs.get("data_quality") or {}).get("detail") or {}
        if dq:
            sev = GaugeMetricFamily("edudss_data_quality_severity", "Worst dataset severity: 0 ok, 1 warn, 2 fail")
            sev.add_metric([], _SEVERITY_VALUE.get(dq.get("worst_severity"), 2.0))
            yield sev
            psi = GaugeMetricFamily("edudss_data_drift_max_psi", "Max feature PSI of newest dataset vs reference")
            psi.add_metric([], float(dq.get("drift_max_psi") or 0))
            yield psi
        bk = (runs.get("backup") or {}).get("detail") or {}
        if bk:
            drill = GaugeMetricFamily(
                "edudss_backup_restore_verified", "1 when the last backup passed its restore drill"
            )
            drill.add_metric([], 1.0 if bk.get("restore_drill") == "VERIFIED" else 0.0)
            yield drill
            size = GaugeMetricFamily("edudss_backup_archive_bytes", "Size of the last backup archive")
            size.add_metric([], float(bk.get("archive_bytes") or 0))
            yield size


def render() -> tuple[bytes, str]:
    from dss.core.metrics import multiprocess_dir

    registry = CollectorRegistry()
    mp_dir = multiprocess_dir()
    if mp_dir:
        from prometheus_client import multiprocess

        multiprocess.MultiProcessCollector(registry, path=mp_dir)
    else:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names):  # in-process (tests / local run)
            try:
                registry.register(collector)
            except ValueError:
                pass
    registry.register(BusinessCollector())
    return generate_latest(registry), CONTENT_TYPE_LATEST
