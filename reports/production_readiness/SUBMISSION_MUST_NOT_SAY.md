# Submission claims: prohibited and safe wording

Use the safe wording in reports, slides and demonstrations. Do not turn a
bounded test result into a broader production claim.

| MUST NOT SAY | SAFE WORDING |
|---|---|
| EduDSS supports 20,000 concurrent users. | The batch prediction pipeline processed 20,000 records within the accepted threshold in the tested environment. |
| EduDSS is fully migrated to PostgreSQL. | PostgreSQL is operational; users/auth, activity history, AI token usage and admin AI configuration are PostgreSQL-primary-with-fallback, while other domains retain their documented current states. |
| EduDSS provides full disaster recovery. | PostgreSQL database backup, checksum verification and clean restore are verified; external and non-database assets remain recovery gaps. |
| Production RPO/RTO is guaranteed. | Provisional recovery objectives are documented, but no production RPO/RTO SLA has been measured or guaranteed. |
| EduDSS is fully integrated with a production LMS/SIS/CMS. | Internal LMS/CMS flows and integration boundaries are tested; a live external production integration is not proven. |
| EduDSS is 100% protected against prompt injection. | The system applies tested defense-in-depth controls and treats retrieved content as untrusted; absolute prevention is not claimed. |
| EduDSS is fully production ready. | The accepted architecture passed the documented correctness, security, integration, recovery, performance and Docker gates in the tested environment, with listed operational limitations. |
| All application data is protected by database backup. | The database archive protects PostgreSQL state; model binaries, datasets, external CMS uploads, local fallback stores and secrets require separate protection. |
| pgvector performance is proven at production scale. | Real server-side pgvector persistence and `<=>` retrieval are verified with deterministic integration fixtures. |
| All AI providers are production healthy. | Provider selection, fallback and safe error behavior are tested without requiring paid live calls. |
| Multi-tenant isolation is universally proven. | Non-superuser PostgreSQL RLS tests cover current tenant-scoped database domains and cross-tenant SELECT/INSERT/UPDATE/DELETE. |
| CI proves the production deployment. | CI validates the committed software on disposable services; production infrastructure and operations require separate acceptance. |

## Additions from the Stage 1-5 closure roadmap (Phase 16 update)

| MUST NOT SAY | SAFE WORDING |
|---|---|
| University Onboarding actions are audited. | The audit log write/read capability itself works and is used by other subsystems; Stage 2's onboarding actions specifically do not yet write audit entries (confirmed while building Stage 5) — a disclosed, known gap. |
| Database restore was only checksum-verified, not actually restored. | This is now out of date: Stage 5 performed a genuine restore into a fresh, empty database and independently queried the restored data. Full (combined DB+non-DB) disaster recovery remains unverified, but DB restore itself is no longer just a checksum check. |
| The thesis's reported accuracy/K-Means-k/Silhouette/DBI figures were re-verified by this engineering engagement. | They were not. RMSE/R² are additionally consistent with a currently-persisted training artifact; accuracy, K-Means k, Silhouette, and DBI were not independently re-run against real data this session — see `METRICS_THESIS_VS_CURRENT.md`. |
| The concurrency/capacity numbers were the maximum the system can handle. | They are the boundary found on one development machine's default (untuned) connection pool before the SLO was violated — a starting point for tuning, not a hard ceiling. |

## Required qualifiers

- Say **batch records**, never concurrent users, for the 20k benchmark.
- Say **database recovery verified**, never full disaster recovery.
- Say **defense in depth**, never absolute prompt-injection prevention.
- Keep repository-ready, fallback and PostgreSQL-primary states distinct.
- Describe RPO/RTO values as provisional targets unless a real operational SLA
  and full-scale drill later establish otherwise.
- Identify synthetic fixtures and the tested environment when presenting
  performance, RLS, recovery and vector-search evidence.
