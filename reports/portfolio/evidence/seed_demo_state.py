"""Prepare a deterministic DEMO state for portfolio screenshots (isolated data root).

Follows the application's own lifecycle — nothing is injected:
  1. synthetic sample data (generate_data, random_state=42 — the same data the app
     loads as "sample_data_v1" in DEMO mode);
  2. a Lecturer-style training run with the training-screen default features
     (RegressionTrainer, save_model=True -> versions saved as Candidate);
  3. an Admin promotion of the best version (model_registry.promote, RBAC enforced).

Usage (from app/, NEVER against the real data_warehouse):
  EDUDSS_DATA_ROOT=<empty demo folder> python reports/portfolio/evidence/seed_demo_state.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
APP = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP))

root = os.environ.get("EDUDSS_DATA_ROOT")
if not root or Path(root).resolve() == (APP / "data_warehouse").resolve():
    raise SystemExit("Set EDUDSS_DATA_ROOT to an isolated demo folder (refusing to touch the real data_warehouse).")

import streamlit as st  # noqa: E402

from dss.core.data_helpers import generate_data  # noqa: E402
from dss.core.trainers import RegressionTrainer  # noqa: E402
from dss.core.warehouse import DataWarehouse  # noqa: E402
from dss.services import model_registry, model_service  # noqa: E402

DATASET_ID = "sample_data_v1"   # id the app assigns to the auto-loaded sample data
TARGET = "diem_ky_sau"

df = generate_data()
all_cols = list(df.columns)
id_cols = [c for c in all_cols if "id" in c.lower() or "name" in c.lower()]
leaky = model_service.find_leaky_feature_cols(df, TARGET, id_cols)
feats = [c for c in all_cols if c not in set(id_cols + ["grade", "pass_fail", "status", "result"] + list(leaky) + [TARGET])]
feats, _ = model_service.drop_near_duplicate_columns(df, feats)

wh = DataWarehouse()
reg = RegressionTrainer()
results = reg.train_and_evaluate(df, feats, TARGET, list(reg.models), cv_folds=5, save_model=True,
                                 _warehouse=wh, _dataset_id=DATASET_ID)[0]
best = model_service.pick_best_model_name(results, "reg")
versions = model_registry.list_versions(wh, DATASET_ID, TARGET)
candidate = next((v for v in versions if v.get("model_name") == best), None)
if candidate is None:
    raise SystemExit(f"best model {best!r} was not saved; versions={[v.get('model_name') for v in versions]}")

st.session_state["_auth_role"] = "Admin"          # the promotion is an Admin action (RBAC-checked)
st.session_state["_auth_user"] = "admin"
model_registry.promote(wh, candidate["training_id"], promoted_by="admin",
                       promotion_reason="Portfolio demo state: best version by RMSE on simulated data")
prod = model_registry.resolve_production(wh, DATASET_ID, TARGET)
print(json.dumps({
    "data_root": root, "dataset_id": DATASET_ID, "target": TARGET, "features": feats,
    "best_model": best, "promoted_training_id": candidate["training_id"],
    "metrics": {k: results[best].get(k) for k in ("MAE", "RMSE", "R2 Score")},
    "production_status": prod.get("status") if isinstance(prod, dict) else str(prod),
}, ensure_ascii=False, indent=1, default=str))
