# Workstream A — realistic LMS/CMS simulated integration

## Status and claim boundary

**Status: PASS_WITH_DOCUMENTED_LIMITATIONS.**

EduDSS was validated against a separate simulated LMS/CMS API using real HTTP
communication. This does not claim integration with a live university LMS, SIS, or CMS.
The branch is ready for manual integration with Workstream B's PostgreSQL persistence and
KB lifecycle work.

Base: `10b487dd2e187febc645373ce77e6a1cbb0039d8`.

## Architecture

```text
separate simulator process/container (port 8765)
  ├─ authenticated paginated REST resources
  ├─ deterministic failure scenarios
  └─ signed HTTP webhook delivery with retry
                    ↓ real HTTP
LMSCMSConnector / WebhookReceiver
  ├─ validation, retries, dedupe, tenant checks
  ├─ stable external→internal UUID mapping
  ├─ webhook idempotency and ordering
  └─ IntegrationBoundary
       ├─ InMemoryIntegrationBoundary (tests/demo only)
       └─ Workstream B PostgreSQL adapter (integration point)
                    ↓
         content invalidation/re-index request boundary
```

The simulator imports no EduDSS modules. The connector does not write application tables
directly. `IntegrationBoundary.upsert()` and `on_content_updated()` are the explicit seams
for Workstream B, avoiding a competing persistence architecture or migration.

## Simulator API

Health: `GET /health`.

Authenticated endpoints:

- `GET /api/users`
- `GET /api/students`
- `GET /api/lecturers`
- `GET /api/courses`
- `GET /api/enrollments`
- `GET /api/assignments`
- `GET /api/submissions`
- `GET /api/grades`
- `GET /api/attendance`
- `GET /api/activities`
- `GET /api/content`
- `GET /api/events`
- `POST /api/webhooks/deliver`

Every tenant record carries `organization_id`, a stable resource-specific external ID,
and an ISO-8601 `updated_at`. Relationships use the canonical external IDs. Query
parameters `page`, `page_size`, and `updated_since` provide pagination and incremental
sync. The connector follows `next_page`, validates the envelope and record schema, and
deduplicates stable IDs before returning records.

## Authentication and tenants

The simulator accepts a bearer token and requires `X-Organization-ID`. Tokens are scoped
to one of two deterministic synthetic organizations, `org-a` or `org-b`; requesting a
different tenant returns 403. Tests prove the student ID sets are disjoint and a token
cannot cross tenant boundaries. Static simulator tokens contain no real credentials and
must not be used as a production authentication design.

## Deterministic university data

Each organization contains two lecturers, four students, two courses, eight enrollments,
two assignments, eight submissions, grades, attendance, learning activities, and two CMS
content records. User, student/lecturer, course, enrollment, assignment, submission,
grade, attendance, activity, and content relationships use stable canonical IDs. No real
person or institution data is present.

## Connector behavior

`LMSCMSConnector` performs real `requests` HTTP calls with bearer authentication,
organization scope and an explicit timeout. It provides:

- bounded retry with exponential delay and `Retry-After` support for 429;
- retry classification for transient 5xx and transport timeout;
- structured `IntegrationError` codes without response-body/credential logging;
- page traversal and incremental timestamps;
- response-envelope and record validation;
- deterministic tenant/resource/external-ID → internal UUID mapping;
- response deduplication and idempotent boundary upserts;
- Phase 12 `observed` hooks for page and complete-sync timing.

## Webhooks

The simulator sends webhook events over HTTP to `WebhookReceiver`. Bodies are signed with
HMAC-SHA256. The receiver checks the signature and tenant before `WebhookProcessor`
accepts the event.

Supported events:

- `submission.created` → submissions boundary;
- `grade.updated` → grades boundary;
- `content.updated` → content boundary plus
  `rag.invalidate_and_reindex.requested`.

Processed `event_id` values are retained for idempotency. A per-resource/external-ID
timestamp prevents an older event from overwriting a newer event. Simulator delivery
retries 429 and transient server/transport failures up to three attempts. Tests exercise
normal, duplicate, out-of-order, transient-retry, invalid, wrong-tenant and invalid-HMAC
events.

The event store is process-local in Workstream A. Workstream B must persist event IDs and
ordering state atomically with its database updates before multi-process operation.

## CMS to RAG boundary

`content.updated` is schema/tenant validated, upserted through the integration boundary,
and invokes `on_content_updated()`. The test boundary records both the content update and
an invalidation/re-index request using the same `content_external_id`. Workstream A does
not modify pgvector tables or migrations; Workstream B owns the final transactional CMS
and KB lifecycle implementation.

## Failure simulation

Deterministic modes cover:

| Scenario | Simulator/connector behavior | Evidence |
|---|---|---|
| 401 | Missing/invalid bearer token | structured `unauthorized` test |
| 403 | Token requests another organization | `tenant_forbidden` test |
| 404 | Unknown API resource | `not_found` test |
| 429 | First two attempts fail with `Retry-After`, third succeeds | retry test |
| 500 | Bounded retries then structured retryable error | server-error test |
| Timeout | Delayed response exceeds explicit connector timeout | timeout test |
| Malformed JSON/payload | Truncated JSON and missing required stable ID | malformed-json and schema-validation tests |
| Duplicate record | Duplicate page item | stable-ID deduplication test |
| Duplicate event | Same `event_id` delivered twice | one application update |
| Out-of-order event | Older timestamp after newer update | older update ignored |

## Role journeys

- **Admin:** checks simulator health, starts a complete sync and inspects boundary audit
  records and failure results.
- **Lecturer:** resolves synchronized courses and sees related students through
  enrollments, grades, attendance and learning activity.
- **Student:** resolves only records keyed to the selected synchronized student, including
  enrollment, grades, attendance and activity. Existing personalized downstream services
  can consume this boundary after Workstream B supplies canonical runtime persistence.
- **CMS/RAG:** a content change arrives over signed HTTP and reaches the explicit
  invalidation/re-index seam.

These are automated service-level integration journeys. A final browser journey against
the PostgreSQL adapter belongs to the A+B integration gate.

## Test and runtime evidence

- Test discovery: **685 tests** (baseline 662 plus 23 new tests).
- New real-HTTP suite: **23 passed in 5.97 s**.
- LMS/CMS/RAG affected group: **55 passed, 12 skipped in 27.45 s**. The skips are
  pre-existing database-conditioned cases without a configured PostgreSQL URL; they are
  not counted as positive evidence.
- Security/auth/RBAC group: **69 passed in 19.36 s**.
- Python compile: PASS.
- Docker Compose simulation profile syntax: PASS.

## Docker

`simulator/Dockerfile` builds a dedicated image with no application dependency install.
The verified image `edudss-lms-cms-simulator:workstream-a` ran separately as non-root
`uid=999(simulator)`, became healthy, and served port 8765 (host proof used 18765).
EduDSS connector code reached that container over HTTP, authenticated as `org-a`, received
health `ok`, and traversed a paginated two-course response. `docker-compose.yml` exposes
the service under the `simulation` profile and provides
`LMS_CMS_SIMULATOR_URL=http://lms-cms-simulator:8765` to the Streamlit container.

## Limitations and A+B integration contract

- This is a deterministic simulator, not a live external university system.
- Workstream A's in-memory boundary is a test/demo adapter. Workstream B must implement
  PostgreSQL upserts, mappings, sync cursors and persistent webhook inbox/order state.
- No PostgreSQL schema or migration was changed. If Workstream B needs connector-state
  tables, it owns their design and migration.
- Final A+B verification must prove browser-visible Admin/Lecturer/Student data, database
  restart persistence, cross-tenant RLS, and content update through real pgvector
  invalidation/re-index/retrieval.
- Static bearer/HMAC values are synthetic staging fixtures. Production integrations need
  managed secrets, rotation and the university provider's actual authentication scheme.
- No live external LMS, SIS or CMS availability, contract or SLA is claimed.

## Decision

**SIMULATED LMS/CMS INTEGRATION: VERIFIED**

**READY FOR A+B INTEGRATION: YES**
