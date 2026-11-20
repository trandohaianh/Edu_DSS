# EduDSS: university pilot and Ministry allocation roadmap

Status (2026-10-26): Stage 1 plus the Stage 2 classroom learning loop and Stage 3
programme allocation/aggregate-reporting pilot are implemented. Isolated live
PostgreSQL, RLS, concurrency and migration roundtrip checks have passed.
University field validation, actual HLU API/SSO integration and national rollout
remain external acceptance work. A Ministry purchase or funding agreement has
not been established.

Implementation and operational guide: [STAGE23_PILOT_GUIDE.md](../STAGE23_PILOT_GUIDE.md).
Verification evidence: [Stage 2/3 acceptance](../../reports/stage23/ACCEPTANCE.md).

## Stage 1 — trustworthy learning plans at one university

Implemented seams:

- Login hydrates approved model artifacts; it never fits KMeans or evaluates
  whole-dataset silhouette. Manual silhouette evaluation samples at most 2,000
  records with a fixed seed above that size.
- Learning observations are nullable and validated. Missing data and valid zero
  are different. Diagnoses require their supporting observations.
- Plans match approved resources to the exact course/topic. Seed resources are
  marked as demonstration content. Current CMS documents must pass the existing
  document approval/validity gate.
- A student's structured plans and self-reported completion are accessible
  before provider configuration and GPA selection. No LLM is needed.
- Plan history assigns versions per school/student/course, is idempotent by
  plan ID, and retains earlier plans. A later plan starts its own progress.
- History authorization allows students their own records and the dedicated
  school's administrator. Platform allocation access does not grant history
  access. The new classroom service separately authorizes assigned lecturers for class progress.

Pilot data: include student_id and course_id (or course_code) in the dataset.
For a dedicated single-course pilot, an administrator may instead configure
EDUDSS_COURSE_ID. Ambiguous duplicate student/course records must be reconciled;
the UI does not silently use the first one.

Optional measured columns include quiz_score/quiz_average, assignment_score/
assignment_average, exam_score, accuracy_rate, avg_response_time, practice_freq,
session_duration, learning_velocity, active_days, topic_scores (0..10),
subskill_mastery and prerequisite_mastery (0..1). Missing observations stay
unknown. A schedule is a rule-based suggestion, not a validated intervention
dose or a measured confidence estimate.

For development/test, history uses EDUDSS_DATA_ROOT/learning_plans.sqlite3.
Production requires EDUDSS_LEARNING_PLANS_STORE=postgres, a positive
EDUDSS_ORGANIZATION_ID, the configured PostgreSQL database and privacy key.
It stores JSON envelopes in the existing RLS-scoped recommendations table;
no new database migration is required. Database failures never select SQLite.

This stage remains a dedicated-school runtime. The server's organization
configuration is not a selector supplied by students. It does not implement
shared-runtime school selection or a full LMS.

Acceptance: retain plans/progress after a fresh session; reject another
student's or school's records; reject unsupported scopes; serialize concurrent
version creation; retain zero measurements and withhold unsupported diagnoses;
use only appropriate approved content; remain usable without a provider/GPA.

Field validation still needs university data and participating instructors.
Measure data coverage, instructor review/acceptance, time spent, activity use,
and reassessment results separately. Self-completed activities are not proof
of learning. Claims of educational impact need an appropriate comparison.

## Stage 2 — repeat deployment at several universities

Implemented in the classroom pilot: class offerings, official teaching assignments and enrollment authorization;
assessment attempts with question versions; topic evidence and plan revisions;
instructor intervention queues. Connect the first actual LMS after the pilot
school identifies its product/API and grants access. Use the same code image,
canonical records and configuration for subsequent schools.

Separate business logic from Streamlit, add an API boundary where needed, and
dispatch ingestion/sync/analytics via explicit background jobs. Move shared
artifacts to school-scoped object storage. Verify real browser workloads,
recovery, and rollout before stating concurrency capacity.

Gate: a second school uses configuration/adapters rather than a source fork;
cross-school isolation holds for data, cache, downloads and jobs; onboarding,
support and operating costs are measured. Validate models per institution;
do not treat risk scores as comparable school rankings.

## Stage 3 — Ministry programme and school allocations

Schools remain data tenants. The pilot implements Program and SchoolAllocation,
scoped programme memberships, school entitlements, usage budgets, audit and
rollout status. Separate programme managers/analysts from platform operators
and school administrators. Buying/allocating access does not itself authorize
viewing student records or conversations.

The Ministry-facing area covers allocations, adoption, data freshness,
approved shared resource packages, aggregate outcomes and service operations.
Aggregate definitions, denominators, reporting dates and small-group
suppression need explicit rules. Reused teaching material requires school
acceptance and local course/outcome mapping.

Prepare a programme proposal with university evidence, pilot scope, acceptance
metrics, responsibilities, implementation and operating costs, support,
recovery and data export/exit arrangements. Confirm the sponsoring unit,
decision authority, funding and purchasing process with the actual buyer.
Policy alignment alone is not a purchase commitment.

Gate: an agreed programme and evaluation plan; demonstrable repeatability;
reviewed deployment/data boundaries and an operating team. Nationwide scale
is a target to validate, not an implemented capability.
