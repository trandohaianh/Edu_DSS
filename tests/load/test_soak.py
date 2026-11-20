"""Workstream D — short soak test (§4.5). Sustained load at a concurrency
level already confirmed to meet the capacity SLO
(test_concurrency_capacity.py), watching for degradation/resource-leak
trends over TIME rather than peak concurrency. Duration is chosen
honestly for what this session can sustain, not a token 60-second run —
see WORKSTREAM_D_SCALE_RECOVERY.md for the actual duration used and why.
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

OWNER_URL = os.getenv("WORKSTREAM_D_OWNER_URL")
APP_URL = os.getenv("WORKSTREAM_D_DATABASE_URL")
pytestmark = pytest.mark.skipif(not OWNER_URL or not APP_URL, reason="Workstream D PostgreSQL URLs are required")

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "reports" / "production_readiness" / "workstream_d_evidence"
SOAK_DURATION_SECONDS = int(os.environ.get("WORKSTREAM_D_SOAK_SECONDS", "300"))  # 5 minutes by default
SOAK_CONCURRENCY = int(os.environ.get("WORKSTREAM_D_SOAK_CONCURRENCY", "10"))  # the confirmed SLO-meeting level
SAMPLE_INTERVAL_SECONDS = 15


def _free_memory_mb() -> float | None:
    try:
        import subprocess

        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return round(int(result.stdout.strip()) / 1024, 1) if result.returncode == 0 else None
    except Exception:
        return None


def test_short_soak_at_confirmed_slo_concurrency(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from dss.db.repositories import prediction_repository
    from dss.db.session import reset_engine_for_tests

    monkeypatch.setenv("DATABASE_URL", APP_URL)
    reset_engine_for_tests()

    owner = create_engine(OWNER_URL)
    code = "soak_" + uuid.uuid4().hex[:8]
    with owner.begin() as conn:
        for role in ("Admin", "Giảng viên / CVHT", "Sinh viên"):
            conn.execute(
                text(
                    "INSERT INTO roles (name,created_at,updated_at) VALUES (:r,now(),now()) ON CONFLICT (name) DO NOTHING"
                ),
                {"r": role},
            )
        org_id = conn.execute(
            text(
                "INSERT INTO organizations (org_code,name,is_active,lifecycle_status,deployment_mode,created_at,updated_at) VALUES (:c,:n,true,'ACTIVE','MULTI_TENANT_SAAS',now(),now()) RETURNING id"
            ),
            {"c": code, "n": code},
        ).scalar_one()
    owner.dispose()
    training_id = f"soak_{uuid.uuid4().hex}"

    samples: list[dict] = []
    op_count = 0
    error_count = 0
    latencies: list[float] = []
    start = time.monotonic()
    next_sample_at = start + SAMPLE_INTERVAL_SECONDS
    started_iso = datetime.now(UTC).isoformat()

    def _op():
        op_start = time.perf_counter()
        try:
            prediction_repository.save_prediction(
                organization_id=org_id,
                training_id=training_id,
                prediction_value=round(random.uniform(0, 10), 2),
                confidence=0.9,
            )
            return (time.perf_counter() - op_start) * 1000, True
        except Exception:
            return (time.perf_counter() - op_start) * 1000, False

    with ThreadPoolExecutor(max_workers=SOAK_CONCURRENCY) as executor:
        futures = set()
        while time.monotonic() - start < SOAK_DURATION_SECONDS:
            while len(futures) < SOAK_CONCURRENCY:
                futures.add(executor.submit(_op))
            done = {f for f in futures if f.done()}
            for f in done:
                latency, success = f.result()
                latencies.append(latency)
                op_count += 1
                if not success:
                    error_count += 1
            futures -= done
            if time.monotonic() >= next_sample_at:
                samples.append(
                    {
                        "elapsed_seconds": round(time.monotonic() - start, 1),
                        "operations_so_far": op_count,
                        "errors_so_far": error_count,
                        "recent_p95_ms": round(sorted(latencies[-200:])[int(len(latencies[-200:]) * 0.95) - 1], 3)
                        if len(latencies) >= 20
                        else None,
                        "free_memory_mb": _free_memory_mb(),
                    }
                )
                next_sample_at += SAMPLE_INTERVAL_SECONDS
            time.sleep(0.01)
        for f in futures:
            latency, success = f.result()
            latencies.append(latency)
            op_count += 1
            if not success:
                error_count += 1

    ended_iso = datetime.now(UTC).isoformat()
    actual_duration = round(time.monotonic() - start, 1)
    latencies.sort()

    result = {
        "test": "short_soak",
        "started_utc": started_iso,
        "ended_utc": ended_iso,
        "requested_duration_seconds": SOAK_DURATION_SECONDS,
        "actual_duration_seconds": actual_duration,
        "concurrency": SOAK_CONCURRENCY,
        "total_operations": op_count,
        "total_errors": error_count,
        "error_rate": round(error_count / op_count, 4) if op_count else 0.0,
        "p50_ms": round(latencies[len(latencies) // 2], 3) if latencies else None,
        "p95_ms": round(latencies[int(len(latencies) * 0.95) - 1], 3) if latencies else None,
        "samples_over_time": samples,
        "organization_id": org_id,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / "short_soak.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, sort_keys=True, indent=2)

    print(f"\n--- SHORT SOAK ({actual_duration}s @ concurrency={SOAK_CONCURRENCY}, evidence: {path}) ---")
    print(f"Total operations: {op_count}, errors: {error_count} ({result['error_rate'] * 100:.2f}%)")
    print(f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms")
    for s in samples:
        print(
            f"  t={s['elapsed_seconds']:>6}s ops={s['operations_so_far']:>6} errors={s['errors_so_far']:>3} "
            f"recent_p95={s['recent_p95_ms']}ms free_mem={s['free_memory_mb']}MB"
        )

    reset_engine_for_tests()
    assert result["error_rate"] < 0.05, f"soak test error rate too high: {result['error_rate']}"
