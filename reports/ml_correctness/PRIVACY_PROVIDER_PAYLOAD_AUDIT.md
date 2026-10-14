# Privacy — AI Provider Payload Audit

Traced exactly what `ai_advisor.py`'s chat path sends as `student_context` to `prompt_security.build_secure_rag_prompt()` → the real LLM provider, field by field.

| Field | Needed? | Sent? | Masked? | Reason / Fix |
|---|---|---|---|---|
| Real name | No | **No** | — | `privacy_service.build_anonymized_student_context()` never includes it |
| Real student ID | No | **No** | Replaced by pseudonym | `generate_pseudonym(student_id)` — a stable, non-reversible-in-practice identifier used instead |
| Email | No | **No** | — | Never included |
| Phone | No | **No** | — | Never included |
| Address / DOB | No | **No** | — | Never included (not even present in the synthetic dataset) |
| GPA (exact) | Partially — explanation needs *some* signal | **No, banded** | Yes | Sent as a range (e.g. "Khá (7.0 ≤ GPA < 8.5) (~7.3)") not the raw exact figure |
| Risk level | Yes (needed for advisor context) | Yes | N/A — not PII | Already a derived category, not personal data |
| Weaknesses / weak topics | Yes (needed for advice) | Yes | **Yes** | Passed through `sanitize_pii_from_text()` before inclusion |
| Attendance rate / progress note | Optional context | Yes, when present | N/A — aggregate numeric, not identifying | — |
| **Recent conversation history (last 5 turns)** | Yes (needed for follow-up coherence) | **Yes, verbatim** | **No** | **Real, disclosed gap found this pass**: `_history_snippet` joins the raw `content` of the last 5 chat turns unmodified. If the student voluntarily typed identifying information (their own name, a phone number, etc.) in an earlier turn of the *same* conversation, it recirculates verbatim on every subsequent turn sent to the same provider. This is lower-severity than a system-side leak (the provider already saw that exact text once, in the same session, from the same student) but is exactly the "full conversation" category the master prompt's Section 21 explicitly names as something that should not be sent unfiltered. **Not fixed this pass** — a real fix would run the same `sanitize_pii_from_text()` pass already used for weaknesses over each history turn before inclusion. |
| Class-level aggregate stats (lecturer/admin context only) | Yes, for staff roles | Yes | N/A — aggregate counts/averages, no individual identifiers | `compute_lecturer_dashboard_overview()`'s output contains only counts and class averages |

## Overall verdict

**Mostly correct, one concrete gap found.** The core per-student context (`_anon_context`) is genuinely well-designed: pseudonymous identifier, banded GPA, PII-sanitized weaknesses, no raw name/ID/email/phone anywhere in the traced path. The one real gap is recent conversation history being appended verbatim without the same sanitization weaknesses already get — a real, disclosed, not-yet-fixed issue, not claimed as closed.

## Recommendation for next pass

Apply `sanitize_pii_from_text()` (already exists, already used for weaknesses) to each line of `_history_snippet` before it is joined into `_full_student_context`. This is a small, well-scoped fix that reuses an existing function rather than introducing a new one — flagged for a dedicated pass rather than rushed in at the tail of this one, since it touches the live chat context-building path that several other fixes this session already modified.
