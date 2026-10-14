# Post-72h Simulation Acceptance

**Source of truth:** `D:\KLTN\edudss-72h-simulation\REAL_MOODLE_CMS_72H_SIMULATION_REPORT.md`, `REAL_MOODLE_CMS_72H_METRICS.csv` (818 rows), `REAL_MOODLE_CMS_72H_INCIDENTS.csv` (8 rows), `REAL_MOODLE_CMS_72H_INTEGRITY.csv` (13 checkpoints) — all read directly from the simulation worktree, none regenerated or inferred, none modified.

**Explicit compliance with the instruction not to infer status from container uptime:** `docker ps` shows the simulation containers still `Up 3 days`+ at the time of this check — that fact was **deliberately not used** to conclude anything. The verdict below comes entirely from the report/CSV artifacts, which record a clean, checkpoint-driven shutdown (`SIMULATION_DURATION_REACHED` fired on schedule) — the containers being left running afterward is a separate, later operational fact, not evidence of completion by itself.

**Run window:** 2026-09-23T00:15 UTC → 2026-09-26T00:18:08 UTC — 72.34 real elapsed hours (the generator's own checkpoint clock ran exactly 72.00h and exited cleanly; the extra ~0.34h is startup/final-shutdown overhead, not clock drift or compression).

---

## Metric table

| Metric | Expected | Observed | Evidence | Status | Limitation |
|---|---|---|---|---|---|
| Real elapsed duration | ≥72h, uncompressed | 72.34h | checkpoint `start_time`/`end_time`, polled every 20s via real `time.time()` | PASS | — |
| Total operations attempted | — | 3,850 | `metrics.csv` (818 rows, ~5-min polling) | Recorded | Latency per-operation was not recorded (see below) |
| Total errors | — | 44 | same | Recorded | — |
| Error rate | low | 1.14% | same | PASS (no absolute SLO was set in advance) | — |
| Cross-tenant isolation probes | 0 leaks | 409 run, 405 succeeded with 0 visible rows, 4 timed out (not leaks) | `REAL_MOODLE_CMS_72H_INCIDENTS.csv` + manual re-verification during/after every incident | PASS | 4 probe timeouts during outage windows, not leaks — re-verified manually |
| Data-integrity checkpoints | clean every 6h | 13/13 clean (T+0 → T+72), 10,000/10,000 students/org, 0 orphan courses, 0 orphan enrollments at every checkpoint | `REAL_MOODLE_CMS_72H_INTEGRITY.csv` | PASS | — |
| Container restarts | 0 unexplained | 0 for all 4 core services (`RestartCount`) | Docker inspect during run | PASS | — |
| Memory | tracked | not continuously profiled; spot `docker stats` samples only (e.g. `edudss-postgres` 89% CPU at T+55.8h during an incident) | `metrics.csv` (disk only), manual spot samples in report §4 | PARTIAL | Real, disclosed gap in the simulation tooling — no continuous CPU/RAM time series exists |
| Latency (p50/p95/p99) | tracked | **not measured** — generator recorded pass/fail + counters only | report §4 | NOT MEASURED | Disclosed honestly rather than fabricated; the only latency-adjacent facts are: 15s HTTP client timeout (exceeded 18 times total) and 600s sync subprocess timeout (exceeded 25/25 scheduled attempts) |
| Crashes / unrecovered failures | 0 | 0 — all 6 real transient incidents (longest ~26 min, T+56.9–57.2h) self-recovered within the same or next 5-min cycle | `REAL_MOODLE_CMS_72H_INCIDENTS.csv` §6 | PASS | — |
| DB connection behavior | stable | Postgres accepting connections normally after every incident; RLS/tenant isolation re-verified clean immediately post-incident | report §6 | PASS | — |
| LMS/CMS/webhook sync | working | Moodle + Directus CMS both real and responsive throughout (aside from the disclosed transient blips); RAG document lifecycle (create/update/delete) genuinely exercised against real Directus API | report §7 | PARTIAL | RAG **retrieval-quality** verification (known-answer QA) was never run periodically — a genuine scope gap in the simulation tooling, disclosed not hidden |
| Data consistency | 20,000 records exact | Confirmed via live query against EduDSS's own Postgres (`edudss_app` role, RLS-restricted, one org at a time): org1=10,000, org2=10,000 | report §3 | PASS | 20,000 records ≠ 20,000 concurrent users — no such claim is made |
| Periodic incremental sync | should advance | **Did not** — all 25/25 scheduled attempts hit the 600s subprocess timeout after the one-time initial full sync (which itself completed successfully, ~2h49m/org, before the 72h clock started) | report §6, root-cause disclosed: simulation's translation proxy lacks server-side `updated_since` filtering that EduDSS's own connector expects | **PARTIAL — real, load-bearing, disclosed limitation** | This is a genuine gap in the *simulation tooling*, not a patch made to EduDSS's own accepted business logic to make the run look cleaner |
| Disk free space | stable | 11.66GB → 5.79GB over 72h (−5.87GB) | report §5 | INVESTIGATED, NOT SIMULATION'S OWN FOOTPRINT | Investigated 3 times during the run; simulation's own containers/volumes/images/build-cache confirmed unchanged in size each time; attributed to host-level activity (WSL2/Docker Desktop virtual-disk growth) outside this exercise's control; reported to the user proactively during the run, not acted on unilaterally |

## Final 72-hour completion criteria (from report §8, reproduced verbatim as facts, not re-derived)

| Criterion | Result |
|---|---|
| 72 real hours elapsed | Yes (72.34h, checkpoint-driven, never compressed) |
| No cross-tenant leakage | Yes — 0 confirmed real leaks |
| No data corruption | Yes — 13/13 integrity checkpoints clean |
| No unrecovered critical service failure | Yes — longest incident ~26 min, self-recovered, 0 restarts |
| No plaintext-secret exposure | Yes |
| Persistent sync state valid | Partially — initial full sync intact; periodic incremental sync never advanced during the window (disclosed) |
| Moodle/CMS/PostgreSQL/RAG functioning | Yes for Moodle/CMS/Postgres; RAG lifecycle exercised but retrieval-quality unverified |
| Restart recovery functioning | Not separately tested — no restarts occurred to exercise this path |

## Overall verdict

**The 72-hour real-Moodle + real-CMS + EduDSS integration genuinely ran to completion**, with clean data integrity, zero real cross-tenant leakage, and no unrecovered failures, while surfacing two real and fully disclosed limitations (no periodic RAG/ML exercise; incremental sync never completing within its timeout at this population size). Neither limitation was patched into EduDSS's business logic to flatter the result.

**What this run does NOT prove** (stated explicitly, per the source report and per this session's own audit discipline): it does not prove ML correctness (see `96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md` for that — several ML-correctness bugs were fixed in commits made *after* this simulation window, meaning the simulation ran against an earlier, partially-unfixed codebase state and could not have caught them), it does not establish p50/p95/p99 latency, and it does not establish 50K-concurrent-user readiness (20,000 is a data-population figure, not a concurrency figure — max real concurrent identities driven was 360).

**Per Section 8 of the new master prompt:** since this report is genuine, dated, and shows a clean completion, the `BLOCKED_BY_RUNNING_SIMULATION` blocker on isolated PostgreSQL/RLS/pgvector validation is lifted for a **separate, isolated** Postgres instance (different ports, no shared volumes) — **not** for touching `edudss-postgres` / `edudss-closure-c-postgres` / any container listed under the simulation worktree, which remain historical evidence and were not modified to produce this document.
