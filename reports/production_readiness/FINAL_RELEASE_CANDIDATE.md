# Final Release Candidate

## Release decision: PASS_WITH_DOCUMENTED_LIMITATIONS

None of the automatic-FAIL conditions occurred: no unresolved critical/
high security vulnerability was found (one real defect, MODELREG-002,
was found, reproduced, fixed, and regression-tested — see
`FINAL_CD_INTEGRATION_ACCEPTANCE.md` §2); no reproducible cross-tenant
data leak (RLS held in every test, including under the MODELREG-002
failure mode, which failed CLOSED — the audit write was silently
dropped, not leaked to another tenant); no privilege escalation; no
plaintext password/secret exposure (confirmed by code review and a live
log spot-check); no corrupted persistent data; no failed mandatory
migration; no failed required backup/restore claim (the claim made is
PARTIAL, matching the evidence exactly); no critical E2E journey
failure (39/39 passed on the clean re-run); the candidate started
correctly from a genuinely fresh, detached checkout.

## Explicit final answers (section 15 requirements)

| Question | Answer |
|---|---|
| Live external LMS integration | **NO** |
| Simulated LMS/CMS integration | **YES** |
| PostgreSQL-backed LMS/CMS | **YES** |
| Multi-tenant university onboarding | **YES** |
| CMS->RAG->pgvector lifecycle | **YES** (including the real invalidation/delete-equivalent primitive) |
| Workstream C ML/AI governance | **YES** (provenance, drift, model registry all genuinely exercised — and one real defect, MODELREG-002, found and fixed in the process) |
| Workstream D load/recovery verification | **YES** (re-measured fresh this round, not reused blindly) |
| 20K batch inference | **PASS** (2.5498s, 7,843.8 predictions/sec) |
| 20K concurrent users | **NOT_VERIFIED** (never attempted or claimed — this figure is batch inference only) |
| Full disaster recovery | **PARTIAL** (DB backup/restore now has a full, independently-queried asset inventory on the restored database; non-DB assets are separately recoverable but never exercised in a combined drill) |
| National-scale deployment | **NOT_VERIFIED** (explicitly an architectural projection, never load-tested) |

## Fresh checkout — what was genuinely fresh vs. disclosed reuse

A new, detached git worktree was created from this branch's final
commit (`6dd96b8` at the time of this checkout — see the STOP report
for the literal final commit hash after this document is committed).

**Genuinely fresh this gate**:
- The git checkout itself (new worktree, detached HEAD).
- The Docker image build (`docker compose ... up --build`) — a real
  build from this exact commit's `Dockerfile`/`requirements.txt`,
  producing a running container verified healthy, non-root (uid 999),
  `torch==2.9.1+cpu` with `cuda_available=False`, zero NVIDIA/CUDA
  packages, image size 3.66GB.
- Alembic migration ran zero-configuration inside the fresh container,
  reaching the single expected head `35d62f0c6002`.
- The Postgres app-role init script (`01-app-role.sh`) executed
  correctly on this fresh checkout, confirming the Stage 5
  `.gitattributes` CRLF fix holds on yet another independent checkout.

**Disclosed reuse, not fresh** (per instruction: "disclose anything
reused... do not present reused dependencies as a from-scratch
installation"):
- The Python virtual environment was a Windows junction pointing at
  the venv already built fresh, from scratch, in Stage 7's own
  from-scratch install (torch+full requirements.txt, verified there via
  a genuine `pip install` with no cached wheels reused across venvs).
  `requirements.txt` has not changed since Stage 7, so re-running that
  exact install again here would have re-proven the same fact at
  significant extra time cost with no new information — reuse was
  chosen deliberately and is disclosed here rather than silently
  presented as fresh.
- The Playwright browser binaries were reused from the same scratch
  directory Stage 7 downloaded them into (also unchanged).

**Verified from this fresh checkout, using the (disclosed, reused)
venv**: imports (`dss`, `torch`), test discovery (771 tests), RLS
(15/15 including the new SQL-injection test), full non-E2E regression
(569 passed, 0 failed), and a 4-test role-E2E subset (login success/
failure across Admin/Lecturer/Student, all passed).

## What remains genuinely unverified or not implemented

- Live external LMS/CMS integration.
- National-scale load.
- Hosted/cloud CI execution.
- TLS/HTTPS — this entire engagement's staging environment communicates
  over plain HTTP.
- A combined DB+non-DB disaster-recovery drill in one exercise.
- Formal legal/compliance certification of any kind (ISO 27001, OWASP,
  NIST, Vietnam Law 91/2025/QH15) — see
  `FINAL_COMPLIANCE_TRACEABILITY_MATRIX.csv` for exactly which selected
  controls were tested instead.
- A dedicated known-answer RAG evaluation set (grounded-answer quality
  was not separately scored this round beyond confirming retrieval/
  invalidation mechanics work).
- Data-subject deletion rights for student personal data (no deletion
  lifecycle exists for it — only CMS content has an invalidation
  primitive).

## READY FOR FINAL MAIN MERGE: NO (decision deferred to the user)

Per the standing instruction governing this entire engagement, `main`
was never modified and no merge into `main` was performed. All work is
committed on `integration/final-candidate-v2`, evidence-complete and
reviewable. The decision of whether and when to merge is explicitly
left to the user.
