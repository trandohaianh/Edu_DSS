# Final Must-Not-Say (Claim Control)

This supersedes nothing in `SUBMISSION_MUST_NOT_SAY.md` (Phase 16) — it
adds the claim-control discipline specifically requested for this
round's mandatory quality/security/data-protection acceptance mandate.
Read both.

## Never claim (without independent, direct proof that does not exist)

- ISO/IEC 27001 certified
- NIST certified
- OWASP certified / "OWASP compliant"
- Vietnamese Personal Data Protection Law (91/2025/QH15) compliance certified
- 20,000 concurrent users
- National-scale ready
- Full disaster recovery (say **PARTIAL** — DB restore is now genuinely
  proven with a full inventory; non-DB restore and a combined drill
  remain unexercised)
- Production SLA
- "0% hallucination" (say: observed grounded-answer performance on the
  controlled evaluation set, when one exists)
- "Prompt injection prevented" (say: defense-in-depth, not absolute
  prevention)
- "Encrypted in transit" for this staging environment (it is not — see
  below)

## Always say instead

| Instead of | Say |
|---|---|
| "Tested against ISO 27001 / OWASP ASVS 5.0 / NIST" | "Tested against **selected controls** from ISO 27001 / OWASP ASVS 5.0 / NIST — see `FINAL_COMPLIANCE_TRACEABILITY_MATRIX.csv` for exactly which ones, and note this is a technical self-assessment, not an independent audit" |
| "Compliant with Vietnam's Personal Data Protection Law" | "A technical readiness assessment against selected requirement areas of Law 91/2025/QH15 — see `FINAL_DATA_PROTECTION_MATRIX.csv`. Legal compliance requires legal review this engagement did not perform" |
| "Passwords are secure" | "Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user random salt, verified with constant-time comparison — never logged, never stored in plaintext" |
| "Rate limiting protects against brute force" | "A 5-attempts/15-minute lockout exists, but it is in-process state — it does not persist across an app restart and does not coordinate across multiple app instances. Disclosed as a real limitation, not hidden" |
| "All communication is encrypted" | "This staging environment communicates over plain HTTP throughout (simulator, app, Postgres) — TLS/HTTPS is a production-target requirement that was NOT exercised or verified this engagement" |
| "SQL injection is prevented" | "SQL injection resistance was verified live against one repository method (5 classic payloads, zero matches, zero side effects) and is architecturally expected everywhere else (100% parameterized queries found by code review) — this is not an exhaustive penetration test" |
| "The concurrency ladder proves EduDSS's real capacity" | "A progressive concurrency ladder (1/5/10/25/50) was re-measured fresh on one shared development machine and held through 50 this run — this differs from an earlier measurement (violation at 25) due to real run-to-run variance on shared hardware, not a contradiction. Neither number should be extrapolated to a dedicated production environment" |
| "The ML models meet the release accuracy threshold" | "A deliberately minimal verification pipeline (not the production trainer classes) was run to prove the model governance machinery works end-to-end — its accuracy/F1/RMSE/R²/Silhouette numbers must NOT be read as an assessment of the actual thesis model's quality. See `FINAL_REALISTIC_STAGING_SIMULATION.md` section H" |
| "CMS content can be deleted" | "CMS content can be invalidated (removed from RAG retrieval) via the real, only-implemented `invalidate_content()` primitive — there is no true DELETE event path in this codebase, and that gap is disclosed, not worked around" |
| "University Onboarding actions are audited" | "The audit log write/read capability works and IS used by model promotion (after this round's MODELREG-002 fix) — Stage 2's onboarding actions specifically still do not call it, a disclosed, pre-existing gap" |

## What we verified / partially verified / did not verify / would require independent audit

**WHAT WE VERIFIED** (real, live, reproducible evidence exists this round):
Password hashing/salting; SQL injection resistance (one method, live);
RLS tenant isolation (83/83 tests + live cross-tenant checks); real
model registry promotion with a real audited write (after fixing
MODELREG-002); real drift detection in both directions; real CMS
invalidation lifecycle; real 401/403/429/500/timeout/malformed failure
injection; a real, fully-inventoried DB backup/restore drill;
soak/20K/concurrency re-measured fresh; Docker CPU-only/non-root/image
size/readiness.

**WHAT WE PARTIALLY VERIFIED**: Data minimization and purpose
specification (schema-review level, not a formal DPIA); logging
exposure (spot-checked, not exhaustively scanned); encryption at rest
(not confirmed either way — relies on host/volume-level protection
outside this engagement's scope); non-DB asset recovery (mechanism
exists and is tested in isolation, never combined with the DB restore
in one drill); ML quality thresholds (measured on a non-production
verification pipeline, not the real trainer).

**WHAT WE DID NOT VERIFY**: Encryption in transit (this staging
environment is HTTP-only, by design, disclosed as SIMULATION/LOCAL-
STAGING); live external LMS integration; national-scale load; hosted
CI execution; data-subject deletion rights for student personal data
(no deletion lifecycle exists for it); session-fixation/cross-tenant
session-crossing at the HTTP session layer (RLS covers the database
layer, not this); a formal legal compliance review of Law 91/2025/QH15.

**WHAT WOULD REQUIRE INDEPENDENT AUDIT/CERTIFICATION**: Any ISO 27001,
OWASP, NIST, or Vietnamese legal compliance certification claim;
a formal penetration test beyond this round's single live SQL-injection
check; a formal Data Protection Impact Assessment; TLS/transport-layer
security review for a real production deployment; an independent
load-test at national scale on dedicated infrastructure.
