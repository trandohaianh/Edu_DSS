"""ML governance: model/dataset/feature-schema provenance and drift detection
(Workstream C).

Scope and design decisions (read before extending):

- This module is pure computation plus a thin, best-effort persistence
  orchestration layer. It never blocks or changes the behavior of the real
  training/prediction pipeline (dss/core/trainers.py, dss/core/warehouse.py,
  dss/services/model_service.py) — every persistence call here is wrapped so
  a Postgres failure (or Postgres simply not being configured, the default)
  degrades to "provenance not recorded", never to a broken training run.
  See dss/core/persistence_config.py's "ML_PROVENANCE" feature flag.

- Drift metric choice: Population Stability Index (PSI), computed with the
  SAME binning methodology for numeric (quantile bins derived from the
  baseline) and categorical (natural category bins) features. This was
  chosen over separately using e.g. a KS test for numeric and a chi-square
  test for categorical because (a) it gives ONE consistent, bounded,
  well-understood score and ONE threshold system across both feature types
  instead of two incompatible statistical frameworks, and (b) its threshold
  bands (< 0.1 / 0.1-0.25 / >= 0.25) are the de facto production-ML-
  monitoring standard, which makes the WARNING/DRIFT_DETECTED distinction
  something a reviewer can sanity-check against prior art rather than an
  invented scale. scipy (already a pinned dependency — see
  app/requirements.txt) provides `scipy.stats.ks_2samp`, which is reported
  ADDITIONALLY for numeric features as a secondary, non-binning-dependent
  corroborating statistic — it does not drive the status decision.

- This is NOT a claim of statistical certainty for any single evaluation:
  PSI is a heuristic distribution-shift indicator, not a hypothesis test
  with a p-value; small samples are refused via INSUFFICIENT_DATA rather
  than given a falsely confident status.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import subprocess
import sys
from typing import Any, Optional

from dss.core.logging_config import get_logger

_logger = get_logger(__name__)

# PSI thresholds — explicit, configurable (override via function args), not
# hidden constants baked into the decision logic. These specific values are
# the widely-cited production-ML-monitoring convention (Population Stability
# Index bands originating from credit-risk scorecard monitoring, now common
# across ML observability tooling).
DEFAULT_PSI_WARNING_THRESHOLD = 0.10
DEFAULT_PSI_DRIFT_THRESHOLD = 0.25
DEFAULT_MIN_SAMPLES = 20          # drift hiệu năng (performance drift)
# Drift dữ liệu (PSI): dưới 100 mẫu ở mỗi phía, nhiễu lấy mẫu của PSI cỡ ~(bins-1)·(1/n1+1/n2)
# đã vượt ngưỡng 0.10/0.25 -> trả INSUFFICIENT_DATA thay vì một kết luận drift giả.
DEFAULT_DATA_DRIFT_MIN_SAMPLES = 100
DEFAULT_NUMERIC_BINS = 10
# Mỗi bin phân vị (theo baseline) cần ~>= 20 mẫu ở phía NHỎ hơn: số bin thực dùng là
# clamp(n_min // 20, 5, numeric_bins).
_MIN_ROWS_PER_BIN = 20
_MIN_NUMERIC_BINS = 5
# Ngưỡng PSI tự điều chỉnh theo nhiễu lấy mẫu: dưới H0 (cùng phân bố), PSI ≈ (1/n1+1/n2)·χ²(bins-1).
# WARNING chỉ khi PSI vượt cả 0.10 lẫn phân vị 99% của nhiễu; DRIFT khi vượt cả 0.25 lẫn phân vị 99.9%.
PSI_NOISE_QUANTILE_WARNING = 0.99
PSI_NOISE_QUANTILE_DRIFT = 0.999

# Performance-drift thresholds — relative degradation (e.g. 0.10 = a metric
# dropping by 10% *relative to its baseline value* triggers WARNING).
DEFAULT_PERFORMANCE_WARNING_RELATIVE_DROP = 0.05
DEFAULT_PERFORMANCE_DRIFT_RELATIVE_DROP = 0.10

STATUS_NO_DRIFT = "NO_DRIFT"
STATUS_WARNING = "WARNING"
STATUS_DRIFT_DETECTED = "DRIFT_DETECTED"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_NOT_EVALUABLE = "PERFORMANCE_DRIFT_NOT_EVALUABLE"

ACTION_NO_ACTION = "NO_ACTION"
ACTION_REVIEW_REQUIRED = "REVIEW_REQUIRED"
ACTION_RETRAIN_RECOMMENDED = "RETRAIN_RECOMMENDED"

_STATUS_SEVERITY = {
    STATUS_NO_DRIFT: 0,
    STATUS_WARNING: 1,
    STATUS_DRIFT_DETECTED: 2,
}


# ---------------------------------------------------------------------------
# Deterministic fingerprints (§4, §5)
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> str:
    """Stable, deterministic serialization: sorted keys where order is not
    semantically meaningful, but list ORDER is always preserved as-given by
    the caller (feature order is itself part of what must affect the
    fingerprint — see compute_feature_schema_fingerprint)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_feature_schema_fingerprint(
    feature_names: list[str],
    feature_dtypes: dict[str, str],
    feature_roles: dict[str, str],
    target_definition: Optional[str],
    model_task_type: str,
    preprocessing_expectations: Optional[dict] = None,
) -> str:
    """Deterministic SHA-256 fingerprint of a model's input contract.

    Same (names in the SAME order, dtypes, roles, target, task type,
    preprocessing) -> same fingerprint, every time, on any machine (no
    reliance on dict/set iteration order, timestamps, or object identity).
    Changing feature order, adding/removing/renaming a feature, changing a
    dtype or categorical/numeric role, changing the target definition, the
    task type, or the preprocessing recipe all change the fingerprint.
    """
    payload = {
        "feature_names": list(feature_names),  # order preserved, NOT sorted
        "feature_dtypes": {k: str(feature_dtypes.get(k, "")) for k in feature_names},
        "feature_roles": {k: str(feature_roles.get(k, "")) for k in feature_names},
        "target_definition": target_definition,
        "model_task_type": model_task_type,
        "preprocessing_expectations": preprocessing_expectations or {},
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def infer_feature_roles(df, feature_names: list[str]) -> dict[str, str]:
    """Best-effort numeric/categorical role inference from a pandas
    DataFrame's dtypes — mirrors the same numeric/categorical split already
    used by dss/core/trainers.py::DataPreprocessor (KNNImputer+StandardScaler
    for numeric, SimpleImputer+OneHotEncoder for categorical)."""
    import pandas as pd

    roles = {}
    for col in feature_names:
        if col not in df.columns:
            roles[col] = "unknown"
            continue
        roles[col] = "numeric" if pd.api.types.is_numeric_dtype(df[col]) else "categorical"
    return roles


def compute_dataset_fingerprint(
    df,
    target_col: Optional[str] = None,
    feature_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Reproducibility evidence for a dataset WITHOUT storing the dataset
    itself (§4): a schema fingerprint (columns + dtypes, order-sensitive)
    and a content fingerprint derived from per-column summary statistics
    (count/null-count, and for numeric columns mean/std/min/max rounded to
    6 significant figures to stay stable across float repr differences; for
    categorical columns, the sorted set of the top-20 most frequent values
    with their counts). Two datasets with materially different content
    produce different `dataset_fingerprint` values; the same data reproduces
    the same fingerprint deterministically (no randomness, no wall-clock
    dependency, no personal-data leakage beyond a handful of category
    labels/summary stats already visible in the dataset the caller has).
    """
    import pandas as pd

    columns = feature_names or list(df.columns)
    schema_payload = {"columns": columns, "dtypes": {c: str(df[c].dtype) for c in columns if c in df.columns}}
    schema_fingerprint = hashlib.sha256(_canonical_json(schema_payload).encode("utf-8")).hexdigest()

    null_stats: dict[str, int] = {}
    numeric_summary: dict[str, dict[str, float]] = {}
    content_payload: dict[str, Any] = {}

    for col in columns:
        if col not in df.columns:
            continue
        series = df[col]
        null_count = int(series.isna().sum())
        null_stats[col] = null_count
        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                summary = {
                    "mean": round(float(clean.mean()), 6),
                    "std": round(float(clean.std()) if len(clean) > 1 else 0.0, 6),
                    "min": round(float(clean.min()), 6),
                    "max": round(float(clean.max()), 6),
                }
            else:
                summary = {"mean": None, "std": None, "min": None, "max": None}
            numeric_summary[col] = summary
            content_payload[col] = {"null_count": null_count, **summary}
        else:
            value_counts = series.astype(str).value_counts().head(20)
            top_values = sorted(
                ((str(k), int(v)) for k, v in value_counts.items()),
                key=lambda kv: kv[0],
            )
            content_payload[col] = {"null_count": null_count, "top_values": top_values}

    dataset_fingerprint = hashlib.sha256(
        _canonical_json({"row_count": len(df), "columns": content_payload}).encode("utf-8")
    ).hexdigest()

    return {
        "schema_fingerprint": schema_fingerprint,
        "dataset_fingerprint": dataset_fingerprint,
        "row_count": int(len(df)),
        "column_count": len(columns),
        "feature_list": columns,
        "null_stats": null_stats,
        "numeric_summary": numeric_summary,
    }


# ---------------------------------------------------------------------------
# Data drift (§6)
# ---------------------------------------------------------------------------

def _psi_from_proportions(baseline_props: list[float], current_props: list[float]) -> float:
    """Population Stability Index between two discrete probability
    distributions over the SAME bins. Zero-frequency bins are floored to a
    small epsilon (standard PSI practice) so a single empty bin doesn't
    produce a division-by-zero or an infinite/undefined contribution."""
    eps = 1e-6
    psi = 0.0
    for b, c in zip(baseline_props, current_props):
        b = max(b, eps)
        c = max(c, eps)
        psi += (c - b) * math.log(c / b)
    return psi


def _psi_noise_floor(n_bins: int, n1: int, n2: int, quantile: float) -> float:
    """Phân vị `quantile` của PSI khi HAI mẫu cùng phân bố (chỉ do lấy mẫu ngẫu nhiên):
    PSI là J-divergence nên xấp xỉ (1/n1 + 1/n2)·χ²(bins-1); trung bình ≈ (bins-1)·(1/n1+1/n2)."""
    dof = max(int(n_bins) - 1, 1)
    scale = 1.0 / max(int(n1), 1) + 1.0 / max(int(n2), 1)
    try:
        from scipy.stats import chi2

        return float(chi2.ppf(quantile, dof)) * scale
    except Exception:  # pragma: no cover - scipy là phụ thuộc cố định; dự phòng thô
        return (dof + 3.0 * math.sqrt(2.0 * dof)) * scale


def _effective_psi_thresholds(warning_threshold, drift_threshold, n_bins, n1, n2) -> dict:
    """Ngưỡng thực dùng. Ngưỡng do NGƯỜI GỌI truyền rõ (khác None) được dùng nguyên vẹn; ngưỡng
    mặc định (None) = max(0.10/0.25, mức nhiễu lấy mẫu) — 0.10/0.25 cố định cờ drift trên dữ
    liệu cùng phân bố khi n <= ~500."""
    out = {}
    for key, given, default, q in (
        ("warning", warning_threshold, DEFAULT_PSI_WARNING_THRESHOLD, PSI_NOISE_QUANTILE_WARNING),
        ("drift", drift_threshold, DEFAULT_PSI_DRIFT_THRESHOLD, PSI_NOISE_QUANTILE_DRIFT),
    ):
        if given is not None:
            out[key] = float(given)
        else:
            out[key] = round(max(default, _psi_noise_floor(n_bins, n1, n2, q)), 6)
    out["drift"] = max(out["drift"], out["warning"])
    return out


def _psi_status(psi: float, warning_threshold: float, drift_threshold: float) -> str:
    if psi >= drift_threshold:
        return STATUS_DRIFT_DETECTED
    if psi >= warning_threshold:
        return STATUS_WARNING
    return STATUS_NO_DRIFT


def _evaluate_numeric_feature_drift(
    baseline, current, *, bins: int, warning_threshold: Optional[float], drift_threshold: Optional[float],
    min_samples: int,
) -> dict[str, Any]:
    import numpy as np

    baseline = np.asarray(baseline, dtype=float)
    baseline = baseline[~np.isnan(baseline)]
    current = np.asarray(current, dtype=float)
    current = current[~np.isnan(current)]

    if len(baseline) < min_samples or len(current) < min_samples:
        return {
            "feature_type": "numeric",
            "baseline_stats": {"count": int(len(baseline))},
            "current_stats": {"count": int(len(current))},
            "drift_metric": None,
            "threshold": {"warning": warning_threshold, "drift": drift_threshold},
            "status": STATUS_INSUFFICIENT_DATA,
        }

    # Số bin theo cỡ mẫu nhỏ hơn: quá nhiều bin trên ít mẫu làm PSI phình ra vì nhiễu.
    bins = int(max(2, min(int(bins), max(_MIN_NUMERIC_BINS, min(len(baseline), len(current)) // _MIN_ROWS_PER_BIN))))
    # Quantile bin edges from the BASELINE only (current is measured against
    # the baseline's own distribution shape, which is the point of PSI).
    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(baseline, quantiles))
    if len(edges) < 2:
        edges = np.array([baseline.min() - 1e-9, baseline.max() + 1e-9])
    edges[0] = -np.inf
    edges[-1] = np.inf

    baseline_counts, _ = np.histogram(baseline, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)
    baseline_props = (baseline_counts / baseline_counts.sum()).tolist()
    current_props = (current_counts / current_counts.sum()).tolist()
    psi = _psi_from_proportions(baseline_props, current_props)
    thr = _effective_psi_thresholds(warning_threshold, drift_threshold, len(baseline_props), len(baseline), len(current))

    ks_statistic = ks_pvalue = None
    try:
        from scipy.stats import ks_2samp

        ks_result = ks_2samp(baseline, current)
        ks_statistic, ks_pvalue = float(ks_result.statistic), float(ks_result.pvalue)
    except Exception:  # pragma: no cover - scipy is a pinned dependency; defensive only
        _logger.warning("ks_2samp unavailable; reporting PSI only", exc_info=True)

    return {
        "feature_type": "numeric",
        "baseline_stats": {
            "count": int(len(baseline)), "mean": round(float(baseline.mean()), 6),
            "std": round(float(baseline.std()), 6), "min": round(float(baseline.min()), 6),
            "max": round(float(baseline.max()), 6),
        },
        "current_stats": {
            "count": int(len(current)), "mean": round(float(current.mean()), 6),
            "std": round(float(current.std()), 6), "min": round(float(current.min()), 6),
            "max": round(float(current.max()), 6),
        },
        "drift_metric": round(psi, 6),
        "drift_metric_name": "PSI",
        "secondary_metric": {"ks_statistic": ks_statistic, "ks_pvalue": ks_pvalue} if ks_statistic is not None else None,
        "threshold": {"warning": thr["warning"], "drift": thr["drift"], "bins": len(baseline_props)},
        "status": _psi_status(psi, thr["warning"], thr["drift"]),
    }


def _evaluate_categorical_feature_drift(
    baseline, current, *, warning_threshold: Optional[float], drift_threshold: Optional[float], min_samples: int
) -> dict[str, Any]:
    import pandas as pd

    baseline = pd.Series(baseline).dropna().astype(str)
    current = pd.Series(current).dropna().astype(str)

    if len(baseline) < min_samples or len(current) < min_samples:
        return {
            "feature_type": "categorical",
            "baseline_stats": {"count": int(len(baseline))},
            "current_stats": {"count": int(len(current))},
            "drift_metric": None,
            "threshold": {"warning": warning_threshold, "drift": drift_threshold},
            "status": STATUS_INSUFFICIENT_DATA,
        }

    categories = sorted(set(baseline.unique()) | set(current.unique()))
    baseline_counts = baseline.value_counts()
    current_counts = current.value_counts()
    baseline_props = [baseline_counts.get(c, 0) / len(baseline) for c in categories]
    current_props = [current_counts.get(c, 0) / len(current) for c in categories]
    psi = _psi_from_proportions(baseline_props, current_props)
    thr = _effective_psi_thresholds(warning_threshold, drift_threshold, len(categories), len(baseline), len(current))

    return {
        "feature_type": "categorical",
        "baseline_stats": {"count": int(len(baseline)), "distribution": {c: round(p, 6) for c, p in zip(categories, baseline_props)}},
        "current_stats": {"count": int(len(current)), "distribution": {c: round(p, 6) for c, p in zip(categories, current_props)}},
        "drift_metric": round(psi, 6),
        "drift_metric_name": "PSI",
        "secondary_metric": None,
        "threshold": {"warning": thr["warning"], "drift": thr["drift"], "bins": len(categories)},
        "status": _psi_status(psi, thr["warning"], thr["drift"]),
    }


def evaluate_data_drift(
    baseline_df,
    current_df,
    feature_roles: Optional[dict[str, str]] = None,
    *,
    warning_threshold: Optional[float] = None,
    drift_threshold: Optional[float] = None,
    min_samples: int = DEFAULT_DATA_DRIFT_MIN_SAMPLES,
    numeric_bins: int = DEFAULT_NUMERIC_BINS,
) -> dict[str, Any]:
    """Deterministic, PSI-based data-drift evaluation between a baseline and
    a current feature DataFrame (same columns expected in both). Returns a
    dict with a per-feature breakdown and an aggregate `overall_status`
    (the most severe evaluable per-feature status; INSUFFICIENT_DATA only if
    NO feature had enough data to evaluate at all).

    This is a deterministic statistic, not a random score: calling this
    twice with the same two DataFrames always returns the same PSI values.

    Ngưỡng: để None (mặc định) thì mỗi đặc trưng dùng max(0.10/0.25, mức nhiễu lấy mẫu
    theo số bin và cỡ hai mẫu) — xem _effective_psi_thresholds; truyền số cụ thể thì
    dùng đúng số đó. Ngưỡng thực dùng nằm ở per_feature[col]["threshold"].
    """
    columns = [c for c in baseline_df.columns if c in current_df.columns]
    roles = feature_roles or infer_feature_roles(baseline_df, columns)

    per_feature: dict[str, Any] = {}
    for col in columns:
        role = roles.get(col, "categorical")
        if role == "numeric":
            per_feature[col] = _evaluate_numeric_feature_drift(
                baseline_df[col], current_df[col], bins=numeric_bins,
                warning_threshold=warning_threshold, drift_threshold=drift_threshold, min_samples=min_samples,
            )
        else:
            per_feature[col] = _evaluate_categorical_feature_drift(
                baseline_df[col], current_df[col],
                warning_threshold=warning_threshold, drift_threshold=drift_threshold, min_samples=min_samples,
            )

    evaluable_statuses = [f["status"] for f in per_feature.values() if f["status"] != STATUS_INSUFFICIENT_DATA]
    if not evaluable_statuses:
        overall_status = STATUS_INSUFFICIENT_DATA
    else:
        overall_status = max(evaluable_statuses, key=lambda s: _STATUS_SEVERITY.get(s, 0))

    drifted_features = [name for name, f in per_feature.items() if f["status"] == STATUS_DRIFT_DETECTED]
    warning_features = [name for name, f in per_feature.items() if f["status"] == STATUS_WARNING]

    return {
        "evaluation_type": "data_drift",
        "per_feature": per_feature,
        "drifted_features": drifted_features,
        "warning_features": warning_features,
        "overall_status": overall_status,
        "thresholds": {
            "warning": DEFAULT_PSI_WARNING_THRESHOLD if warning_threshold is None else warning_threshold,
            "drift": DEFAULT_PSI_DRIFT_THRESHOLD if drift_threshold is None else drift_threshold,
            "noise_adjusted": warning_threshold is None or drift_threshold is None,
            "min_samples": min_samples, "numeric_bins": numeric_bins,
        },
    }


# ---------------------------------------------------------------------------
# Performance / model drift (§7) — requires real ground truth, never fabricated
# ---------------------------------------------------------------------------

def evaluate_performance_drift(
    task_type: str,
    y_true_baseline=None,
    y_pred_baseline=None,
    y_true_current=None,
    y_pred_current=None,
    *,
    warning_relative_drop: float = DEFAULT_PERFORMANCE_WARNING_RELATIVE_DROP,
    drift_relative_drop: float = DEFAULT_PERFORMANCE_DRIFT_RELATIVE_DROP,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, Any]:
    """Compares real predictive performance between a baseline and a current
    window — ONLY when ground truth is available for both. If either side's
    ground truth is missing or empty, returns
    `PERFORMANCE_DRIFT_NOT_EVALUABLE` rather than inventing a result — this
    function never fabricates labels or performance numbers.
    """
    has_baseline = y_true_baseline is not None and y_pred_baseline is not None and len(y_true_baseline) > 0
    has_current = y_true_current is not None and y_pred_current is not None and len(y_true_current) > 0

    if not has_baseline or not has_current:
        return {
            "evaluation_type": "performance_drift",
            "overall_status": STATUS_NOT_EVALUABLE,
            "reason": "missing_ground_truth_baseline" if not has_baseline else "missing_ground_truth_current",
            "metrics": {},
        }
    if len(y_true_baseline) < min_samples or len(y_true_current) < min_samples:
        return {
            "evaluation_type": "performance_drift",
            "overall_status": STATUS_INSUFFICIENT_DATA,
            "metrics": {"baseline_n": len(y_true_baseline), "current_n": len(y_true_current)},
        }

    if task_type == "classification":
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

        metric_fns = {
            "accuracy": accuracy_score,
            "precision": lambda yt, yp: precision_score(yt, yp, average="weighted", zero_division=0),
            "recall": lambda yt, yp: recall_score(yt, yp, average="weighted", zero_division=0),
            "f1": lambda yt, yp: f1_score(yt, yp, average="weighted", zero_division=0),
        }
    elif task_type == "regression":
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        metric_fns = {
            "rmse": lambda yt, yp: mean_squared_error(yt, yp) ** 0.5,
            "mae": mean_absolute_error,
            "r2": r2_score,
        }
    else:
        return {
            "evaluation_type": "performance_drift",
            "overall_status": STATUS_NOT_EVALUABLE,
            "reason": f"unsupported_task_type:{task_type}",
            "metrics": {},
        }

    metrics: dict[str, Any] = {}
    worst_status = STATUS_NO_DRIFT
    for name, fn in metric_fns.items():
        baseline_value = float(fn(y_true_baseline, y_pred_baseline))
        current_value = float(fn(y_true_current, y_pred_current))
        # For RMSE/MAE, a lower value is better, so "degradation" means an
        # INCREASE; for accuracy/precision/recall/f1/r2, degradation means a
        # DECREASE. Normalize to "relative_drop = how much worse, as a
        # fraction of the baseline magnitude" so one threshold works for all.
        if name in ("rmse", "mae"):
            relative_drop = (current_value - baseline_value) / abs(baseline_value) if baseline_value else float("inf") if current_value else 0.0
        else:
            relative_drop = (baseline_value - current_value) / abs(baseline_value) if baseline_value else (0.0 if current_value >= baseline_value else float("inf"))
        if relative_drop >= drift_relative_drop:
            status = STATUS_DRIFT_DETECTED
        elif relative_drop >= warning_relative_drop:
            status = STATUS_WARNING
        else:
            status = STATUS_NO_DRIFT
        metrics[name] = {
            "baseline": round(baseline_value, 6), "current": round(current_value, 6),
            "relative_drop": round(relative_drop, 6), "status": status,
        }
        if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY.get(worst_status, 0):
            worst_status = status

    return {
        "evaluation_type": "performance_drift",
        "overall_status": worst_status,
        "metrics": metrics,
        "thresholds": {"warning_relative_drop": warning_relative_drop, "drift_relative_drop": drift_relative_drop},
        "baseline_n": len(y_true_baseline),
        "current_n": len(y_true_current),
    }


# ---------------------------------------------------------------------------
# Retraining decision boundary (§10) — a recommendation, never an action
# ---------------------------------------------------------------------------

def recommend_action(data_drift_status: Optional[str], performance_drift_status: Optional[str]) -> str:
    """Pure decision-boundary function. Returns a RECOMMENDATION only —
    nothing in this codebase automatically retrains or promotes a model
    based on this value. The safe lifecycle (drift detected -> review ->
    train -> evaluate -> compare -> explicit Admin promotion decision, via
    dss/services/model_registry.py::promote()) is unchanged; this function
    is purely advisory input to that human decision."""
    if performance_drift_status == STATUS_DRIFT_DETECTED:
        return ACTION_RETRAIN_RECOMMENDED
    if performance_drift_status == STATUS_WARNING:
        return ACTION_REVIEW_REQUIRED
    if data_drift_status == STATUS_DRIFT_DETECTED:
        return ACTION_REVIEW_REQUIRED
    if data_drift_status == STATUS_WARNING:
        return ACTION_REVIEW_REQUIRED
    return ACTION_NO_ACTION


# ---------------------------------------------------------------------------
# Environment/lineage introspection (best-effort, never blocks)
# ---------------------------------------------------------------------------

_KEY_LIBRARIES = ("scikit-learn", "numpy", "pandas", "scipy", "xgboost", "lightgbm", "shap", "torch")


def get_code_commit() -> Optional[str]:
    """Best-effort git commit hash. `EDUDSS_GIT_COMMIT` (settable at deploy
    time, e.g. baked into the Docker image at build time) takes precedence
    since the running container has no .git directory (see .dockerignore) —
    `git rev-parse HEAD` only works in a dev/CI checkout, not inside the
    built image. Returns None, never raises, if neither is available."""
    env_commit = os.environ.get("EDUDSS_GIT_COMMIT", "").strip()
    if env_commit:
        return env_commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_library_versions() -> dict[str, str]:
    versions = {}
    for lib in _KEY_LIBRARIES:
        try:
            versions[lib] = importlib.metadata.version(lib)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def infer_algorithm_name(model_pipeline) -> Optional[str]:
    """Best-effort introspection of a fitted sklearn Pipeline/estimator's
    algorithm class name (e.g. "RandomForestClassifier"). Falls back to the
    pipeline object's own class name, then None — never raises."""
    try:
        if hasattr(model_pipeline, "steps") and model_pipeline.steps:
            return type(model_pipeline.steps[-1][1]).__name__
        if hasattr(model_pipeline, "named_steps") and model_pipeline.named_steps:
            last = list(model_pipeline.named_steps.values())[-1]
            return type(last).__name__
        return type(model_pipeline).__name__
    except Exception:
        return None


def record_training_provenance(
    organization_id: int,
    training_id: str,
    dataset_id: str,
    target_col: str,
    model_name: str,
    model_pipeline,
    feature_cols: list[str],
    metrics: dict,
    status: str,
    model_task_type: str,
    model_sha256: Optional[str] = None,
    model_path: Optional[str] = None,
    X_train=None,
    dataset_version: Optional[str] = None,
    owner: Optional[str] = None,
    created_by: Optional[str] = None,
    preprocessing_expectations: Optional[dict] = None,
) -> Optional[dict]:
    """Best-effort orchestration: compute fingerprints, introspect the
    pipeline, and write everything to Postgres via
    dss.db.repositories.ml_provenance_repository — called ADDITIVELY from
    dss/core/warehouse.py::save_model_training() when
    is_postgres_enabled("ML_PROVENANCE") is true. Returns the recorded
    provenance IDs on success, or None (never raises) on any failure —
    including Postgres being unreachable — since this must never break the
    actual training/save flow it is attached to.
    """
    from dss.core.persistence_config import is_postgres_enabled

    if not is_postgres_enabled("ML_PROVENANCE"):
        return None

    try:
        from dss.db.repositories import ml_provenance_repository as repo

        algorithm = infer_algorithm_name(model_pipeline)
        hyperparameters = infer_hyperparameters(model_pipeline)
        code_commit = get_code_commit()
        python_version = get_python_version()
        library_versions = get_library_versions()

        dataset_provenance_id = None
        feature_dtypes: dict[str, str] = {c: "unknown" for c in feature_cols}
        feature_roles: dict[str, str] = {c: "unknown" for c in feature_cols}
        if X_train is not None:
            fingerprint_info = compute_dataset_fingerprint(X_train, target_col=target_col, feature_names=feature_cols)
            feature_roles = infer_feature_roles(X_train, feature_cols)
            feature_dtypes = {c: str(X_train[c].dtype) for c in feature_cols if c in X_train.columns}
            dataset_provenance_id = repo.record_dataset_provenance(
                organization_id=organization_id,
                dataset_id=dataset_id,
                source_type="training_split",
                schema_fingerprint=fingerprint_info["schema_fingerprint"],
                dataset_fingerprint=fingerprint_info["dataset_fingerprint"],
                row_count=fingerprint_info["row_count"],
                column_count=fingerprint_info["column_count"],
                feature_list=fingerprint_info["feature_list"],
                target_column=target_col,
                null_stats=fingerprint_info["null_stats"],
                numeric_summary=fingerprint_info["numeric_summary"],
            )

        schema_fingerprint = compute_feature_schema_fingerprint(
            feature_names=feature_cols, feature_dtypes=feature_dtypes, feature_roles=feature_roles,
            target_definition=target_col, model_task_type=model_task_type,
            preprocessing_expectations=preprocessing_expectations,
        )
        feature_schema_provenance_id = repo.record_feature_schema_provenance(
            organization_id=organization_id, fingerprint=schema_fingerprint, feature_names=feature_cols,
            feature_dtypes=feature_dtypes, feature_roles=feature_roles, model_task_type=model_task_type,
            target_definition=target_col, preprocessing_expectations=preprocessing_expectations,
        )

        model_version_id = repo.record_model_version(
            organization_id=organization_id, training_id=training_id, model_key=f"{dataset_id}::{target_col}",
            dataset_id=dataset_id, target_col=target_col, model_name=model_name, status=status,
            algorithm=algorithm, dataset_version=dataset_version, owner=owner,
            feature_schema={"feature_cols": feature_cols}, artifact_path=model_path,
            artifact_checksum_sha256=model_sha256, dataset_provenance_id=dataset_provenance_id,
            feature_schema_provenance_id=feature_schema_provenance_id, hyperparameters=hyperparameters,
            code_commit=code_commit, python_version=python_version, library_versions=library_versions,
            created_by=created_by,
        )
        numeric_metrics = {k: v for k, v in (metrics or {}).items() if isinstance(v, (int, float))}
        repo.record_model_metrics(organization_id, model_version_id, numeric_metrics)

        _logger.info(
            "model registered: training_id=%s model_key=%s algorithm=%s status=%s",
            training_id, f"{dataset_id}::{target_col}", algorithm, status,
        )
        return {
            "model_version_id": model_version_id,
            "dataset_provenance_id": dataset_provenance_id,
            "feature_schema_provenance_id": feature_schema_provenance_id,
        }
    except Exception:
        _logger.warning("ML provenance recording failed (non-fatal, training already saved)", exc_info=True)
        return None


def infer_hyperparameters(model_pipeline) -> Optional[dict]:
    """Best-effort sklearn `get_params()` of the final estimator, filtered
    to JSON-serializable scalar/simple values only (drops nested estimator
    objects, callables, etc., which are not meaningfully useful as
    provenance metadata and are not guaranteed to be JSON-serializable)."""
    try:
        estimator = model_pipeline.steps[-1][1] if hasattr(model_pipeline, "steps") else model_pipeline
        if not hasattr(estimator, "get_params"):
            return None
        raw = estimator.get_params(deep=False)
        clean = {}
        for k, v in raw.items():
            if v is None or isinstance(v, (bool, int, float, str)):
                clean[k] = v
            elif isinstance(v, (list, tuple)) and all(isinstance(x, (bool, int, float, str)) for x in v):
                clean[k] = list(v)
        return clean or None
    except Exception:
        return None
