# PII Sanitization — Final Audit

## The gap found in the prior pass, closed this pass

`PRIVACY_PROVIDER_PAYLOAD_AUDIT.md` (prior pass) found that recent conversation history was sent to the LLM provider verbatim, unsanitized. This pass fixed it, and found something additional while doing so.

## Bonus finding: a genuine, previously dead pattern

`privacy_service.py` already defined `_STUDENT_ID_REGEX = re.compile(r"\b(SV|sv|MSSV|mssv)?[0-9]{5,10}\b")` — but **`sanitize_pii_from_text()` never applied it**. The pattern existed, was clearly intended to catch student IDs, and was simply never wired into the function body. This is a real, concrete defect (not a hypothetical one), found by tracing the actual sanitization code rather than trusting that "a regex exists" means "the regex is used."

## Fix

Added `sanitize_conversation_turn_for_provider()` — a stronger sanitizer specifically for free-form conversation history, which:
1. Reuses `sanitize_pii_from_text()` (email + phone — unchanged behavior for existing callers).
2. **Now applies** `_STUDENT_ID_REGEX` (the previously-dead pattern).
3. Adds a new pattern for common self-introduction phrasings ("tên (tôi/em/mình) là...", "my name is...") — not general-purpose name detection (which is unreliable via regex), but specifically the exact self-disclosure phrasing patterns the master prompt itself named as test cases.

The original `sanitize_pii_from_text()` is **unchanged** — kept narrow (email/phone only) for its existing callers (e.g., the weaknesses list), to avoid an unnecessary regression risk in code that already works correctly for its current use.

## Test evidence

`test_privacy_conversation_history_sanitization.py` (7 tests) — using exactly the four self-disclosure scenarios the master prompt named: "My name is...", "My student ID is...", "My email is...", "My phone number is...", plus a combined-all-four-in-one-turn test, plus a test confirming non-PII facts needed for the answer (GPA figures, course names) survive sanitization, plus a test confirming the original narrower function's behavior is unchanged.

`test_ai_advisor_history_pii_wiring.py` (2 tests, source-inspection) — confirms `ai_advisor.py`'s real chat handler calls the new sanitizer for every history turn before joining into the provider payload. Verify-before-fix: both confirmed FAIL on the pre-fix code, PASS after.

## Remaining honest limitation

No true NER (named-entity recognition) exists — an arbitrarily-phrased self-disclosure that doesn't match the specific patterns above (e.g., "call me [FirstName]" or a name mentioned mid-sentence without an introduction phrase) would not be caught. This is disclosed as a real, bounded limitation of a regex-based approach, not claimed as complete PII elimination.
