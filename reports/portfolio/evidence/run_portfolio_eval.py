"""Reproducible portfolio evaluation for EduDSS (current working tree).

Uses ONLY the application's own code paths:
  data        dss.core.data_helpers.generate_data()          (synthetic, random_state=42)
  training    dss.core.trainers.ClassificationTrainer / RegressionTrainer (default split/CV)
  ranking     dss.services.model_service.pick_best_model_name / build_metrics_dataframe
  importance  dss.services.model_service.get_production_feature_importance + SHAP (shap lib)
  clustering  dss.services.clustering_service (same defaults as bootstrap_service)

Run from app/:  python reports/portfolio/evidence/run_portfolio_eval.py
Writes reports/portfolio/evidence/portfolio_eval.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
APP = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP))

import numpy as np  # noqa: E402

from dss.core.data_helpers import generate_data, is_synthetic_data  # noqa: E402
from dss.core.trainers import ClassificationTrainer, RegressionTrainer  # noqa: E402
from dss.services import clustering_service, model_service  # noqa: E402

OUT = Path(__file__).with_name("portfolio_eval.json")
started = time.time()
df = generate_data()
data_origin = "SYNTHETIC" if is_synthetic_data(df) else "REAL"
def ui_default_features(target: str) -> list[str]:
    """Same default-feature logic as the training screen (dss/tabs/ml_hub.py):
    drop ID columns, generic outcome columns, target-leaky columns, then
    near-duplicate columns (e.g. gpa_previous == diem_ky_nay / 2.5)."""
    all_cols = list(df.columns)
    id_cols = [c for c in all_cols if "id" in str(c).lower() or "name" in str(c).lower()]
    leaky = model_service.find_leaky_feature_cols(df, target, id_cols)
    exclude = set(id_cols + ["grade", "pass_fail", "status", "result"] + list(leaky) + [target])
    feats_ = [c for c in all_cols if c not in exclude]
    feats_, _dropped = model_service.drop_near_duplicate_columns(df, feats_)
    return feats_


feats_cls = ui_default_features("xep_loai")
feats_reg = ui_default_features("diem_ky_sau")
result: dict = {
    "data": {"origin": data_origin, "generator": "dss.core.data_helpers.generate_data(random_state=42)",
             "rows": int(len(df)), "feature_selection": "training-screen defaults (leakage + near-duplicate removal)",
             "features_classification": feats_cls, "features_regression": feats_reg},
}
feats = feats_cls

# ---------------------------------------------------------------- classification
clf = ClassificationTrainer()
c_res, c_pipes, c_labels, c_used, c_xtest, c_ytest, c_xtrain = clf.train_and_evaluate(
    df, feats, "xep_loai", list(clf.models), cv_folds=5, save_model=False)
cls_rows = {}
for name, m in c_res.items():
    if name.startswith("__") or not isinstance(m, dict) or "Accuracy" not in m:
        continue
    cls_rows[name] = {
        "accuracy": m.get("Accuracy"), "precision_macro": m.get("Precision (Macro)"),
        "recall_macro": m.get("Recall (Macro)"), "f1_macro": m.get("F1 Score (Macro)"),
        "accuracy_train": m.get("Accuracy (Train)"), "confusion_matrix": m.get("Confusion Matrix"),
    }
result["classification"] = {
    "target": "xep_loai", "features_used": list(c_used), "class_labels": [str(x) for x in c_labels],
    "train_size": int(len(c_xtrain)), "test_size": int(len(c_xtest)),
    "class_distribution_full": df["xep_loai"].value_counts().to_dict(),
    "models": cls_rows, "best_model_by_app_ranking": model_service.pick_best_model_name(c_res, "clf"),
}

# ---------------------------------------------------------------- regression
reg = RegressionTrainer()
r_out = reg.train_and_evaluate(df, feats_reg, "diem_ky_sau", list(reg.models), cv_folds=5, save_model=False)
r_res, r_pipes, r_used, r_xtest, r_xtrain = r_out[0], r_out[1], r_out[3], r_out[4], r_out[6]
reg_rows = {name: {"mae": m.get("MAE"), "rmse": m.get("RMSE"), "r2": m.get("R2 Score"),
                   "r2_train": m.get("R2 Score (Train)")}
            for name, m in r_res.items()
            if not name.startswith("__") and isinstance(m, dict) and "RMSE" in m}
best_reg = model_service.pick_best_model_name(r_res, "reg")
result["regression"] = {
    "target": "diem_ky_sau", "features_used": list(r_used), "models": reg_rows,
    "best_model_by_app_ranking": best_reg,
    "train_size": int(len(r_xtrain)), "test_size": int(len(r_xtest)),
}

# leakage check: correlation of each used feature with the targets
corr = {c: round(float(df[c].corr(df["diem_ky_sau"])), 4) for c in r_used if c in df.columns}
result["leakage_check"] = {
    "pearson_r_with_diem_ky_sau": dict(sorted(corr.items(), key=lambda kv: -abs(kv[1]))),
    "target_formula": "diem_ky_sau = 0.60*diem_ky_nay + 0.15*diem_giua_ky + 0.10*diem_du_an + "
                      "0.10*(ty_le_diem_danh*10) + 0.05*(so_gio_hoc_tuan/3.5) + N(0, 0.08), "
                      "then clipped to +/-1.5 of diem_ky_nay; xep_loai = score_to_xep_loai(diem_ky_sau)",
}

# ---------------------------------------------------------------- importance / SHAP
imp = {}
for label, pipes, used, best in (("regression", r_pipes, r_used, best_reg),
                                 ("classification", c_pipes, c_used, result["classification"]["best_model_by_app_ranking"])):
    pipe = pipes.get(best) if best else None
    if pipe is None:
        continue
    fi = model_service.get_production_feature_importance(pipe, list(used), top_n=10)
    imp[label] = {"model": best, "method": "estimator.feature_importances_ (app: get_production_feature_importance)",
                  "top": [{"feature": r["Feature"], "importance_pct": float(r["Importance (%)"])} for _, r in fi.iterrows()]}
try:
    import shap
    pipe = r_pipes[best_reg]
    X = df[list(r_used)]
    Xt = pipe.named_steps["preprocessor"].transform(X) if "preprocessor" in pipe.named_steps else X.values
    explainer = shap.Explainer(pipe.named_steps["model"], Xt[:200])
    sv = explainer(Xt[:300])
    names = model_service._resolve_shap_feature_names(pipe.named_steps.get("preprocessor"), list(r_used), Xt.shape[1])
    mean_abs = np.abs(sv.values).mean(axis=0)
    order = np.argsort(-mean_abs)[:10]
    imp["regression_shap"] = {"model": best_reg, "method": "mean |SHAP value| over 300 rows (shap.Explainer)",
                              "top": [{"feature": str(names[i]), "mean_abs_shap": float(mean_abs[i])} for i in order]}
except Exception as exc:  # report, do not hide
    imp["regression_shap"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
result["explainability"] = imp

# ---------------------------------------------------------------- clustering (bootstrap defaults)
cols = clustering_service.select_default_cluster_features(df)
_, Xp = clustering_service.preprocess_features(df, cols)
k = min(4, max(2, len(df) // 10))
_, labels = clustering_service.run_kmeans(Xp, k)
q = clustering_service.compute_cluster_quality_metrics(Xp, labels)
counts = {int(c): int(n) for c, n in zip(*np.unique(labels, return_counts=True))}
sweep = clustering_service.compute_elbow_silhouette(Xp, 2, 8)
result["clustering"] = {
    "features": cols, "k_selected": k, "k_rule": "bootstrap default: min(4, max(2, n//10))",
    "silhouette": q["silhouette"], "davies_bouldin": q["davies_bouldin"],
    "cluster_sizes": counts, "cluster_pct": {c: round(100 * n / len(df), 1) for c, n in counts.items()},
    "silhouette_sweep_k2_8": dict(zip([int(x) for x in sweep.get("k_list", [])],
                                      [None if s is None else float(s) for s in sweep.get("silhouette", [])])),
}
import datetime as _dt  # noqa: E402
import os as _os  # noqa: E402
import platform as _platform  # noqa: E402
result["meta"] = {
    "evaluated_at": _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z"),
    "git_sha": _os.environ.get("EDUDSS_GIT_SHA", "unknown"),
    "image": _os.environ.get("EDUDSS_IMAGE_REF", ""),
    "python": _platform.python_version(),
    "script": "reports/portfolio/evidence/run_portfolio_eval.py",
}
result["runtime_seconds"] = round(time.time() - started, 1)
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
# Bản snapshot mà tab "Kết quả đánh giá mô hình" (dss/tabs/evaluation_report.py) đọc.
_SNAPSHOT = APP / "dss" / "assets" / "evaluation_snapshot.json"
_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
_SNAPSHOT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
