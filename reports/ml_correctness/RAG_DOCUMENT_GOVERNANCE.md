# RAG Document Governance

## Finding: governance is already implemented — the 96Q defense answer describing it as a gap is stale

`dss/services/document_governance.py::is_document_usable()` is a hard filter (not an LLM-trusted suggestion) requiring **all** of:
1. `status == APPROVED` **and** a real `approved_by` (not just a self-applied label — this is the exact "4/19 documents self-labeled approved" defect the 96Q document's Câu 73 answer describes, and it is explicitly named as fixed in code: *"chống F-0b"*).
2. Currently in effect (`effective_from <= now`) and not expired (`expires_at > now` or unset).
3. If a content hash is supplied at retrieval time, it must match the hash recorded at approval time — **content edited after approval is treated as no longer valid**, closing a tampering vector the original Câu 73 answer didn't even mention as a risk.

`rag_service.py::retrieve_unified_context()` is the **single canonical retrieval path** (see `RAG_CANONICAL_PATH_AUDIT.md`) and its own docstring states plainly that it **no longer reads the old hardcoded 19-document knowledge base for citation purposes at all** — that gap (tagged `F-0a`/`F-0b`, from an earlier "NHÓM F" remediation project, a different tag namespace than this session's 96Q tags) was closed before this specific closure pass began.

## Status lifecycle

`PENDING_REVIEW` / `APPROVED` / `REJECTED` / `ARCHIVED` (via `regulation_resolver.py`'s shared status constants, reused across regulation documents and RAG documents alike) — confirmed present and enforced at the hard-filter level above, not just declared as an enum with nothing checking it.

## Actionable consequence: the 96Q matrix needs one correction

`96Q_LEGACY_DEFECT_CLOSURE_MATRIX.md`'s Section 8 entry for **Câu 73** currently reads *"DOCUMENTATION_ONLY (known gap, not independently re-verified this pass)"* — that undersells the actual state. Re-verified this pass: **the underlying defect is fixed in code**; only the original defense-document *answer text* (which still says "hiện chưa đảm bảo") is now stale relative to the code. Reclassifying:

| Câu | Old classification | Corrected classification | Evidence |
|---|---|---|---|
| 73 | DOCUMENTATION_ONLY | **FIXED_AND_TESTED** (code) / **NEEDS_ANSWER_UPDATE** (the 96Q document's own prose) | `document_governance.is_document_usable()`, `rag_service.retrieve_unified_context()` docstring's explicit F-0a/F-0b closure note |

This is exactly the "96-question set must not teach stale architecture" risk the master prompt's Section 14 warns about, caught concretely rather than left as a generic sweep result.

## What was not re-verified this pass

- Whether the Admin-facing document-upload UI actually sets `status=PENDING_REVIEW` by default (not independently re-traced — the DB-level default and the retrieval-side enforcement are both confirmed; the upload-time UI default was not re-checked).
- Whether `REJECTED`/`ARCHIVED` documents are fully excluded from all UI listings (not just from citation-eligibility) — only the citation/retrieval hard-filter was verified.
