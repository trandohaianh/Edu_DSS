"""PostgreSQL persistence layer (Phase 1, production-readiness engagement).

This package is ADDITIVE — it does not replace `dss/core/warehouse.py`'s local
JSON/joblib storage, which remains the live storage for the running Streamlit
app in this phase. See `reports/production_readiness/PHASE1_REPORT.md` for the
full migration plan and current scope.
"""
