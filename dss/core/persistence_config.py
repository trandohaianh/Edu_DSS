"""Explicit, fail-closed selectors for incremental PostgreSQL cutover.

Two gating functions, kept deliberately separate rather than unified, because
they answer different questions for different call-site shapes:

- `repository_for(feature)` — IDENTITY/SUBSCRIPTION, pre-dates Phase 1B.
  IDENTITY is now wired for real (Phase 1C): returns a
  `dss.db.repositories.user_repository.UserRepository` instance bound to the
  server-resolved organization when `EDUDSS_IDENTITY_STORE=postgres`, `None`
  for local (auth_service.py's exact original contract — never a truthy
  value for "use local storage"). SUBSCRIPTION here is UNCHANGED and still
  raises — subscriptions already have their own real, wired gate via
  `is_postgres_enabled("SUBSCRIPTION")` (see the note below); nothing calls
  `repository_for("SUBSCRIPTION")`.
- `is_postgres_enabled(feature)` — Phase 1B's simpler boolean gate for the
  domains that now DO have a real, tested Postgres repository
  (dss/db/repositories/*). Call sites branch on the boolean and call the
  repository module's functions directly with an explicit organization_id —
  there is no repository *object* to hand back (see
  reports/production_readiness/PHASE1B_RUNTIME_CUTOVER.md for why this is a
  deliberately simpler shape than repository_for()'s).
"""
from __future__ import annotations

import os

_IDENTITY_SUBSCRIPTION_FEATURES = {"IDENTITY", "SUBSCRIPTION"}


def _resolve_organization_id() -> int:
    """Single-tenant deployment resolution — the one organization this
    running app instance serves — same pattern as
    dss/core/warehouse.py::_current_organization_id() and every other
    Phase 1B/1C repository wiring. Server-side env var only; NEVER derived
    from a UI field or request parameter, so a normal user can never select
    another organization's id."""
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        raise RuntimeError(
            "EDUDSS_ORGANIZATION_ID is required when EDUDSS_IDENTITY_STORE=postgres."
        )
    return int(raw)

# Domains with a real, tested dss/db/repositories/* implementation as of
# Phase 1B. Selecting EDUDSS_<FEATURE>_STORE=postgres for anything NOT in this
# set raises NotImplementedError — fail loudly, never silently fall through.
#
# NOTE on "SUBSCRIPTION" appearing in both gates: repository_for("SUBSCRIPTION")
# (above) is the OLDER, still-unwired reservation from before Phase 1B — no
# application code calls it. is_postgres_enabled("SUBSCRIPTION") below is the
# real, wired Phase 1B gate that dss/services/subscription_service.py actually
# uses. Both read the SAME env var (EDUDSS_SUBSCRIPTION_STORE) by construction,
# so there is no behavioral conflict — only one of the two gates is ever
# actually consulted by live code for this feature.
_IMPLEMENTED_POSTGRES_FEATURES = {
    "PREDICTIONS", "CONSULTATIONS", "SUBSCRIPTION", "RAG", "ACADEMIC", "CMS",
    # Phase 1C additions:
    "ACTIVITY", "ADMIN_AI_CONFIG", "AI_TOKEN_USAGE",
    # Workstream C addition: unlike every feature above, this one is NOT
    # "either local JSON or Postgres" — the joblib/JSON artifact store in
    # dss/core/warehouse.py is ALWAYS the primary store, unconditionally.
    # This flag only gates an ADDITIONAL, best-effort metadata mirror to
    # Postgres for governance/queryability (model/dataset/feature-schema
    # provenance, drift history) — see warehouse.py::save_model_training
    # and dss/services/ml_provenance.py. Off by default, matching every
    # other flag here; when off, behavior is unchanged from before
    # Workstream C.
    "ML_PROVENANCE",
}


def repository_for(feature: str):
    if feature not in _IDENTITY_SUBSCRIPTION_FEATURES:
        raise ValueError("unknown persistence feature")
    mode = os.environ.get(f"EDUDSS_{feature}_STORE", "local").strip().lower()
    if mode == "local":
        return None
    if mode != "postgres":
        raise ValueError(f"EDUDSS_{feature}_STORE must be local or postgres")
    if feature == "IDENTITY":
        from dss.db.repositories.user_repository import UserRepository  # lazy: see module docstring

        return UserRepository(_resolve_organization_id())
    raise NotImplementedError(
        "PostgreSQL subscription cutover via repository_for() is incomplete; "
        "subscriptions use is_postgres_enabled('SUBSCRIPTION') instead — see module docstring."
    )


def is_postgres_enabled(feature: str) -> bool:
    """True if `feature` should read/write PostgreSQL as its PRIMARY backend
    (EDUDSS_<FEATURE>_STORE=postgres AND a real repository exists for it).
    False means: preserve current local-storage behavior exactly — callers
    must not dual-write. Defaults to local (False) when unset, matching every
    other persistence flag in this codebase."""
    all_known = _IDENTITY_SUBSCRIPTION_FEATURES | _IMPLEMENTED_POSTGRES_FEATURES | {"ACADEMIC", "CMS", "RAG"}
    if feature not in all_known:
        raise ValueError(f"unknown persistence feature: {feature}")
    mode = os.environ.get(f"EDUDSS_{feature}_STORE", "local").strip().lower()
    if mode == "local":
        return False
    if mode != "postgres":
        raise ValueError(f"EDUDSS_{feature}_STORE must be local or postgres")
    if feature not in _IMPLEMENTED_POSTGRES_FEATURES:
        raise NotImplementedError(
            f"PostgreSQL backend for {feature} is not implemented yet — use local storage "
            f"(leave EDUDSS_{feature}_STORE unset, or set it to 'local')."
        )
    return True
