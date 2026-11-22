"""EduDSS operations pipeline — scheduled jobs for a running deployment.

    python -m ops.pipeline run kpi_snapshot|data_quality|backup|retention|all
    python -m ops.pipeline --schedule          # long-running worker (docker compose service `worker`)
    python -m ops.pipeline status              # last result of every job (JSON)

Jobs (results appended to <data_root>/ops/pipeline_runs.jsonl; the health server turns the
latest result of each job into Prometheus gauges, so Grafana alerts on stale/failed jobs):

kpi_snapshot  (hourly)  accounts per role, AI requests/tokens/USD today and this month, share
                        of tokens counted by the provider (vs estimated), cache-hit rate, USD
                        per active AI user, infrastructure cost entered by the admin.
data_quality  (daily)   schema, missing values, out-of-range scores, duplicate student ids on
                        every warehouse dataset, plus feature drift (PSI) of the newest dataset
                        against a frozen reference (the synthetic generator with seed 42 until a
                        reference is pinned). Severity: ok / warn / fail.
backup        (daily)   tar.gz snapshot of the data root (no logs, no secrets) with a SHA-256
                        manifest (ops.non_db_recovery), then a RESTORE DRILL: the archive is
                        extracted into a scratch directory and every checksum re-verified. With
                        DATABASE_URL set, ops.backup_recovery (pg_dump) runs and is verified too.
retention     (daily)   keep EDUDSS_BACKUP_KEEP_DAYS of backups (default 7), trim the run log,
                        purge expired personal data in PostgreSQL deployments.

Nothing here reads prompts, answers or names; student data is only aggregated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
import threading
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

JOBS = ("kpi_snapshot", "data_quality", "backup", "retention")
_BACKUP_EXCLUDE_DIRS = {"logs", "backups", "ops", "security", "locks"}  # locks: tệp khoá rỗng (bước 9)
_SECRET_SUFFIXES = (".env", ".pem", ".key")
SCORE_COLUMNS_0_10 = (
    "diem_ky_nay",
    "diem_giua_ky",
    "diem_du_an",
    "diem_thong_ke",
    "diem_xu_ly_du_lieu",
    "diem_truc_quan_hoa",
    "diem_machine_learning",
    "diem_lap_trinh",
    "diem_ky_sau",
    "final_score",
)
RANGES = {
    **dict.fromkeys(SCORE_COLUMNS_0_10, (0.0, 10.0)),
    "ty_le_diem_danh": (0.0, 1.0),
    "so_gio_hoc_tuan": (0.0, 80.0),
    "gpa_previous": (0.0, 4.0),
}
DRIFT_FEATURES = ("diem_ky_nay", "ty_le_diem_danh", "so_gio_hoc_tuan", "diem_giua_ky", "gpa_previous")


def now() -> datetime:
    return datetime.now(UTC)


def data_root() -> Path:
    from dss.core.data_root import get_data_root

    return Path(get_data_root())


def ops_dir() -> Path:
    path = data_root() / "ops"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows[-limit:] if limit else rows


# --------------------------------------------------------------------------- infra costs
def infra_costs_path() -> Path:
    return ops_dir() / "infra_costs.json"


def load_infra_costs() -> list[dict]:
    try:
        data = json.loads(infra_costs_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_infra_cost(month: str, provider: str, item: str, amount_usd: float, note: str = "", actor: str = "") -> dict:
    """Admin-entered monthly infrastructure line (VM, domain, e-mail...). Free tiers are recorded as $0."""
    datetime.strptime(month, "%Y-%m")
    amount = float(amount_usd)
    if not (0 <= amount < 1_000_000) or not provider.strip() or not item.strip():
        raise ValueError("Khoản chi phí không hợp lệ.")
    rows = load_infra_costs()
    entry = {
        "id": max([r.get("id", 0) for r in rows] + [0]) + 1,
        "month": month,
        "provider": provider.strip()[:80],
        "item": item.strip()[:120],
        "amount_usd": round(amount, 2),
        "note": note.strip()[:200],
        "created_by": actor[:64],
        "created_at": now().isoformat(),
    }
    rows.append(entry)
    infra_costs_path().write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def delete_infra_cost(entry_id: int) -> bool:
    rows = load_infra_costs()
    kept = [r for r in rows if r.get("id") != entry_id]
    infra_costs_path().write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(kept) != len(rows)


def infra_total(month: str) -> float:
    return round(sum(float(r.get("amount_usd", 0)) for r in load_infra_costs() if r.get("month") == month), 2)


# --------------------------------------------------------------------------- jobs
def job_kpi_snapshot() -> tuple[str, dict]:
    detail = compute_kpis()
    _append_jsonl(ops_dir() / "kpi_snapshots.jsonl", {"at": now().isoformat(), **detail})
    return "ok", detail


def compute_kpis() -> dict:
    """Read-only KPI computation (also used live by the admin "Báo cáo & giám sát" page)."""
    from dss.services import auth_service, token_tracker

    t = now()
    today, month = t.strftime("%Y-%m-%d"), t.strftime("%Y-%m")
    records = token_tracker._load_all_records()

    def in_period(r, prefix):
        return str(r.get("timestamp", "")).startswith(prefix)

    month_rows = [r for r in records if in_period(r, month)]
    today_rows = [r for r in month_rows if in_period(r, today)]

    def agg(rows):
        billed = [r for r in rows if not r.get("cache_hit")]
        tokens = sum(int(r.get("total_tokens", 0)) for r in billed)
        provider_tokens = sum(int(r.get("total_tokens", 0)) for r in billed if r.get("usage_source") == "provider")
        users = {r.get("user_id") for r in rows}
        cost = sum(float(r.get("estimated_cost", 0.0)) for r in rows)
        return {
            "requests": len(rows),
            "cache_hits": len(rows) - len(billed),
            "tokens": tokens,
            "provider_counted_token_share": round(provider_tokens / tokens, 4) if tokens else None,
            "cost_usd": round(cost, 6),
            "active_ai_users": len(users),
            "cost_per_active_user_usd": round(cost / len(users), 6) if users else 0.0,
        }

    detail = {
        "accounts_by_role": auth_service.count_users_by_role(),
        "ai_today": agg(today_rows),
        "ai_month": agg(month_rows),
        "infra_month_usd": infra_total(month),
    }
    detail["total_month_usd"] = round(detail["ai_month"]["cost_usd"] + detail["infra_month_usd"], 4)
    return detail


def _psi(expected, actual, bins: int = 10) -> float:
    import numpy as np

    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected, actual = expected[~np.isnan(expected)], actual[~np.isnan(actual)]
    if len(expected) < 20 or len(actual) < 20:
        return 0.0
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def check_dataframe(df, name: str) -> dict:
    """Data-quality rules for a student-performance table (pure function, unit-tested)."""
    issues, severity = [], "ok"

    def flag(level, msg):
        nonlocal severity
        issues.append({"level": level, "message": msg})
        if level == "fail" or (level == "warn" and severity == "ok"):
            severity = level

    rows = len(df)
    if rows == 0:
        flag("fail", "bảng rỗng")
        return {"dataset": name, "rows": 0, "severity": severity, "issues": issues}
    if "student_id" in df.columns:
        dup = int(df["student_id"].duplicated().sum())
        if dup:
            flag("fail" if dup / rows > 0.01 else "warn", f"{dup} mã sinh viên trùng")
    else:
        flag("warn", "không có cột student_id")
    missing = {c: round(float(df[c].isna().mean()), 4) for c in df.columns if df[c].isna().any()}
    for col, rate in missing.items():
        flag("fail" if rate > 0.2 else "warn", f"{col}: thiếu {rate:.1%}")
    out_of_range = {}
    for col, (lo, hi) in RANGES.items():
        if col in df.columns:
            values = df[col].dropna()
            try:
                bad = int(((values < lo) | (values > hi)).sum())
            except TypeError:
                flag("fail", f"{col}: kiểu dữ liệu không phải số")
                continue
            if bad:
                out_of_range[col] = bad
                flag("fail" if bad / rows > 0.01 else "warn", f"{col}: {bad} giá trị ngoài [{lo}, {hi}]")
    return {
        "dataset": name,
        "rows": rows,
        "columns": len(df.columns),
        "missing_rate": missing,
        "out_of_range": out_of_range,
        "severity": severity,
        "issues": issues[:30],
    }


def _reference_frame():
    import warnings

    import pandas as pd

    pinned = ops_dir() / "reference_dataset.csv"
    if pinned.exists():
        return pd.read_csv(pinned), "pinned"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from dss.core.data_helpers import generate_data

        return generate_data(n_students=1000, random_state=42), "synthetic_seed42"


def job_data_quality() -> tuple[str, dict]:
    from dss.core.warehouse import DataWarehouse

    wh = DataWarehouse(str(data_root()))
    reports, newest = [], None
    for meta in wh.list_datasets()[:20]:
        dataset_id = meta.get("dataset_id") or meta.get("id")
        if not dataset_id:
            continue
        loaded = wh.load_dataset(dataset_id)
        df = loaded[0] if isinstance(loaded, tuple) else loaded
        if df is None or not hasattr(df, "columns"):
            reports.append(
                {
                    "dataset": str(dataset_id),
                    "severity": "fail",
                    "issues": [{"level": "fail", "message": "không đọc được"}],
                }
            )
            continue
        reports.append(check_dataframe(df, str(dataset_id)))
        newest = newest if newest is not None else df
    reference, reference_kind = _reference_frame()
    if newest is None:  # demo without saved datasets: check the generator itself
        newest = reference
        reports.append(check_dataframe(reference, "synthetic_generator"))
    drift = {
        c: round(_psi(reference[c], newest[c]), 4)
        for c in DRIFT_FEATURES
        if c in newest.columns and c in reference.columns
    }
    max_psi = max(drift.values()) if drift else 0.0
    severity_rank = {"ok": 0, "warn": 1, "fail": 2}
    worst = max((r.get("severity", "ok") for r in reports), key=lambda s: severity_rank.get(s, 2), default="ok")
    if max_psi >= 0.25:
        worst = "fail" if worst == "fail" else "warn"
    detail = {
        "datasets": reports,
        "drift_reference": reference_kind,
        "drift_psi": drift,
        "drift_max_psi": round(max_psi, 4),
        "worst_severity": worst,
    }
    _append_jsonl(ops_dir() / "data_quality.jsonl", {"at": now().isoformat(), **detail})
    return ("ok" if worst != "fail" else "degraded"), detail


def backup_root() -> Path:
    return Path(os.environ.get("EDUDSS_BACKUP_DIR") or (data_root() / "backups"))


def _backup_filter(info: tarfile.TarInfo):
    parts = Path(info.name).parts
    if len(parts) > 1 and parts[1] in _BACKUP_EXCLUDE_DIRS:
        return None
    lowered = info.name.lower()
    if lowered.endswith(".lock"):  # tệp khoá giữa các tiến trình (dss/core/file_lock.py), không chứa dữ liệu
        return None
    if lowered.endswith(_SECRET_SUFFIXES) or "secret" in lowered or "credential" in lowered:
        return None
    if info.issym() or info.islnk():
        return None
    return info


def job_backup() -> tuple[str, dict]:
    from ops import non_db_recovery

    root = data_root()
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    target = backup_root() / stamp
    target.mkdir(parents=True, exist_ok=True)
    detail: dict = {"dir": str(target)}
    if os.environ.get("DATABASE_URL"):
        from ops import backup_recovery

        db_meta = backup_recovery.backup(target / "postgres")
        manifest_file = target / "postgres" / db_meta["archive"].replace(".dump", ".backup.json")
        backup_recovery.verify(manifest_file)  # raises on any checksum/size mismatch
        detail["postgres"] = {"verified": True, "size_bytes": db_meta["size_bytes"]}
    archive = target / "data_root.tar.gz"
    from ops.backup_recovery import checksum

    files: dict[str, str] = {}

    def include(info: tarfile.TarInfo):
        kept = _backup_filter(info)
        if kept is not None and kept.isfile():
            files[kept.name] = checksum(root.parent / kept.name.replace("data_root", root.name, 1))
        return kept

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname="data_root", filter=include)
    provenance = non_db_recovery.build_manifest(root, APP_ROOT, backup_id=f"nondb-{stamp}")
    provenance.pop("artifact_directories", None)
    manifest = {
        "backup_id": f"nondb-{stamp}",
        "archive": archive.name,
        "archive_sha256": checksum(archive),
        "files": files,
        "provenance": provenance,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    # Restore drill: extract into scratch space and re-verify every file checksum.
    with tempfile.TemporaryDirectory(prefix="edudss-restore-") as scratch:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(scratch, filter="data")
        missing, mismatched = [], []
        for name, digest in files.items():
            path = Path(scratch) / name
            if not path.is_file():
                missing.append(name)
            elif checksum(path) != digest:
                mismatched.append(name)
    status = "VERIFIED" if not missing and not mismatched else "CORRUPTED_OR_INCOMPLETE"
    drill = {
        "status": status,
        "verified_count": len(files) - len(missing) - len(mismatched),
        "missing": missing,
        "mismatches": mismatched,
    }
    detail.update(
        {
            "archive_bytes": archive.stat().st_size,
            "files": len(files),
            "restore_drill": drill["status"],
            "restore_verified_files": drill["verified_count"],
            "restore_missing": len(drill["missing"]),
            "restore_mismatches": len(drill["mismatches"]),
        }
    )
    return ("ok" if drill["status"] == "VERIFIED" else "failed"), detail


def job_retention() -> tuple[str, dict]:
    keep_days = int(os.environ.get("EDUDSS_BACKUP_KEEP_DAYS", "7"))
    cutoff = now() - timedelta(days=keep_days)
    removed = []
    root = backup_root()
    if root.exists():
        for child in sorted(root.iterdir()):
            try:
                stamp = datetime.strptime(child.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                continue
            if stamp < cutoff and child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child.name)
    trimmed = {}
    for name, keep in (("pipeline_runs.jsonl", 5000), ("kpi_snapshots.jsonl", 24 * 90), ("data_quality.jsonl", 365)):
        path = ops_dir() / name
        rows = _read_jsonl(path)
        if len(rows) > keep:
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-keep:]), encoding="utf-8")
            trimmed[name] = len(rows) - keep
    detail = {"backups_removed": removed, "logs_trimmed": trimmed, "keep_days": keep_days}
    if os.environ.get("DATABASE_URL"):
        try:
            from dss.core.warehouse import _current_organization_id
            from dss.services.data_lifecycle import purge_expired

            detail["purged"] = purge_expired(_current_organization_id())
        except Exception as exc:  # reported, never hides the file-level retention
            detail["purge_error"] = type(exc).__name__
    return "ok", detail


_RUNNERS = {
    "kpi_snapshot": job_kpi_snapshot,
    "data_quality": job_data_quality,
    "backup": job_backup,
    "retention": job_retention,
}
_lock = threading.Lock()


def run_job(name: str, trigger: str = "manual") -> dict:
    if name not in _RUNNERS:
        raise ValueError(f"unknown job {name}")
    started = time.time()
    with _lock:
        try:
            status, detail = _RUNNERS[name]()
        except Exception as exc:
            status, detail = (
                "failed",
                {"error": type(exc).__name__, "message": str(exc)[:300], "trace": traceback.format_exc(limit=3)[-800:]},
            )
    record = {
        "job": name,
        "trigger": trigger,
        "status": status,
        "started_at": started,
        "finished_at": time.time(),
        "duration_s": round(time.time() - started, 3),
        "detail": detail,
    }
    _append_jsonl(ops_dir() / "pipeline_runs.jsonl", record)
    return record


def last_runs() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    last_ok: dict[str, float] = {}
    for row in _read_jsonl(ops_dir() / "pipeline_runs.jsonl", limit=2000):
        latest[row.get("job")] = row
        if row.get("status") == "ok":
            last_ok[row.get("job")] = row.get("finished_at", 0)
    for job, row in latest.items():
        row["last_success_at"] = last_ok.get(job)
    return latest


def schedule_forever() -> None:
    """Hourly KPI; data quality, backup and retention once a day at EDUDSS_PIPELINE_DAILY_AT (UTC HH:MM)."""
    daily_at = os.environ.get("EDUDSS_PIPELINE_DAILY_AT", "19:30")  # 02:30 giờ Việt Nam
    hh, mm = (int(x) for x in daily_at.split(":"))
    print(f"[pipeline] scheduler started: hourly kpi_snapshot, daily jobs at {daily_at} UTC", flush=True)
    run_job("kpi_snapshot", "startup")
    latest = last_runs()
    if "backup" not in latest:  # first boot: produce a backup right away
        for job in ("data_quality", "backup"):
            run_job(job, "startup")
    next_hourly = time.time() + 3600
    while True:
        t = now()
        daily = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if daily <= t:
            daily += timedelta(days=1)
        wake = min(next_hourly, daily.timestamp())
        time.sleep(max(1.0, wake - time.time()))
        if time.time() >= next_hourly:
            run_job("kpi_snapshot", "schedule")
            next_hourly += 3600
        if now() >= daily:
            for job in ("data_quality", "backup", "retention"):
                result = run_job(job, "schedule")
                print(f"[pipeline] {job}: {result['status']} ({result['duration_s']}s)", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", choices=["run", "status"], default=None)
    parser.add_argument("job", nargs="?", default=None)
    parser.add_argument("--schedule", action="store_true")
    args = parser.parse_args(argv)
    if args.schedule:
        schedule_forever()
        return 0
    if args.command == "status":
        print(json.dumps(last_runs(), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "run" and args.job:
        names = JOBS if args.job == "all" else (args.job,)
        results = [run_job(n) for n in names]
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        return 0 if all(r["status"] in ("ok", "degraded") for r in results) else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
