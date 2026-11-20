# Stage 2/3 pilot acceptance — 2026-10-26

Status: functional pilot implementation complete for the classroom learning loop
and programme allocations. This is technical acceptance against isolated data.
University field validation, HLU integration, procurement and nationwide
deployment have not been accepted.

## Implemented scope

- School/class offerings, official teaching assignments, exact student enrollment,
  atomic CSV roster import, closure/reopening and staff interventions.
- Teacher-authored formative MCQs through plain form fields, optional bulk JSON
  import, editable drafts, published immutable versions and attempt limits.
- Student answer-key redaction, actual topic scores, idempotent submissions,
  atomic attempt/plan storage, class-scoped plan versions, completion and retests.
- Missing observations remain unknown. Latest observed topic scores retain their
  source/time when a later test covers a different subset of topics.
- Current school-approved CMS resources appear in plans. Opening content checks
  class/plan ownership, course/topic, current document version and approval again.
  Withdrawn/replaced/excluded resources stop displaying. No LLM is required.
- Programme registry, explicit manager/analyst membership by school+username,
  seat/AI reservation budgets, allocation status and school seat enforcement.
  AI reservations are metadata, not provider token metering or billing.
- School-admin publication of aggregate snapshots, minimum cohort 5, small-cell
  suppression at publication and read, explicit freshness, allowlisted exports.
  Programme membership does not grant raw classroom/plan/chat access.
- Initial real Admin/Platform Admin bootstrap using the existing password hasher,
  secure interactive prompts, duplicate refusal and no demo account seeding.
- Dataset-independent navigation to classrooms, materials and programmes.
- Dedicated school processes using server-resolved scope; PostgreSQL transactions
  bind RLS settings and serialize programme/school mutations with advisory locks.

## Persistence and rollout contract

The Alembic head is d2e3a6102601. It adds 13 lp_* tables with forced RLS and
the nullable rag_documents.course_code used for external course identifiers.
The existing integer rag_documents.course_id FK is preserved. Known Course
links are backfilled into course_code; unknown old document codes remain unknown.

Expected public table contract: 55 tables including alembic_version.
Production requires PostgreSQL for platform/identity/learning-plan/CMS/RAG stores.
A selected PostgreSQL document store never silently falls back to local content.
Local SQLite is a development store.

Programme offices and participating school app instances must use the same
programme PostgreSQL database. Each app resolves one school from server
configuration and has its own file/CMS artifact root. This release does not
automatically create infrastructure or implement request-selected school login.

## Verification evidence

| Run | Result | Scope |
| --- | --- | --- |
| Full application regression | 1,244 passed; 174 skipped | tests excluding e2e/load; service/schema code verified |
| Final Streamlit UI acceptance | 11 passed | final form authoring/edit/publish, student attempt/plan/retest/content revocation, programme allocation/publication, production navigation without an ML dataset |
| Isolated PostgreSQL acceptance runner | 26 passed | 10 checks use live PostgreSQL; 16 additional bootstrap checks use isolated local/SQLite fixtures |
| Migration roundtrip | passed | fresh upgrade to head, downgrade to previous revision, upgrade again; existing non-platform table row counts preserved |
| Working-tree whitespace check | passed | git diff --check |

The full regression ran before the final plain-question-form polish. All
affected classroom, programme and main-navigation UI tests were rerun afterwards
in the final 11-test UI acceptance above. Results are separate runs, not a sum
of unique tests.

The 10 live PostgreSQL checks cover:
- migrated schema/table contract and FORCE RLS under a non-superuser,
  non-BYPASSRLS app role;
- unscoped/cross-school access, denied foreign writes and transaction scope reset;
- concurrent idempotent attempt/plan writes, limits, ownership and saved progress;
- enrollment races, distinct school seat capacity and atomic failed roster import;
- programme membership boundaries, suppressed school reporting and absence of
  raw student data in central snapshots;
- suspended allocations denying new work while retaining authorized history;
- actual pgvector content indexing/read ordering, school/course/namespace filters,
  and the real PostgreSQL CMS approval-to-plan-resource bridge;
- Stage 1 concurrent history versions/retries and school/course progress isolation;
- owner-only initial identity creation, duplicate refusal and rejected app-role
  provisioning.

The runner creates a fresh labelled loopback-only PostgreSQL container, separates
privileged owner and restricted app credentials, never prints passwords/DSNs,
and removes only its own verified container. Existing edudss-postgres remained
running and was not used by the acceptance run.

Commands from repository root:

    .venv/Scripts/python.exe -B -m pytest app/tests --ignore=app/tests/e2e --ignore=app/tests/load -q
    .venv/Scripts/python.exe -B app/tools/run_stage23_acceptance.py
    .venv/Scripts/python.exe -B -m pytest app/tests/test_stage2_classroom_ui.py app/tests/test_stage3_program_ui.py app/tests/test_stage1_plan_workspace_ui.py -q

Use a fresh --basetemp inside app/.pytest_cache for repeated Windows pytest runs
if old temporary directories are locked.

## External acceptance still required

- HLU has supplied a student portal URL, not an API/SSO integration contract.
  Authorized CSV enrollment works; automatic HLU sync is not implemented.
- Actual instructors must review question/content mapping, usefulness of plans
  and reassessment outcomes. Self-reported activity completion is not proof of learning.
- Full LMS replacement still requires requirement validation for file submissions,
  official gradebook, SCORM/LTI, scheduling, notifications and examinations.
- Browser concurrency/capacity, multi-instance operational rollout, full recovery
  and the buyer's acceptance must be verified before national production claims.
- No Ministry purchasing, budget or programme agreement is implied by the code.

See ../../docs/STAGE23_PILOT_GUIDE.md for operational use.
