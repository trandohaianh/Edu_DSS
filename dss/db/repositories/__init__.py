"""Repository layer — thin, transactional wrappers over the ORM models in
`dss/db/models.py`. Each repository method opens its own transaction via
`dss.db.session.session_scope()` and either fully commits or fully rolls back.

This phase wires exactly ONE repository into real use
(`AuditLogRepository`, called from `dss/services/model_registry.py`) since it
is a pure net-new capability (Phase 0 found no audit trail exists at all) and
therefore carries zero risk of regressing the live JSON-backed auth/RBAC/
warehouse flows. See PHASE1_REPORT.md for the rest of the migration plan.
"""
