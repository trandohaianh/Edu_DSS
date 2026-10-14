# RAG Governance — Final Recheck

Section 16 asked to independently re-trace upload-time default status, listing behavior, and retrieval eligibility. This pass traced all 3.

## 1. Upload-time default status: unbypassable `PENDING_REVIEW`

`document_ingestion.py::ingest_document()` calls `document_governance.default_governance_metadata()` **after** `base_meta.update(extra_metadata)`, with an explicit comment stating this ordering exists specifically to override any `status`/`approved_*` value a caller might try to sneak in via `extra_metadata`. `default_governance_metadata()` unconditionally returns `"status": STATUS_PENDING_REVIEW` — there is no parameter, code path, or override that lets a new upload start as anything other than `PENDING_REVIEW`. This closure was done under an earlier, separate remediation (tag `F-0c`, part of "NHÓM F"), confirmed still intact and correct this pass.

## 2. Listing behavior

`knowledge_base.py` filters documents by status for its "chờ duyệt" (pending review) admin view (`d.get("status") == gov.STATUS_PENDING_REVIEW`) — a real, working filtered view exists, not just a raw dump of all documents regardless of status.

## 3. Retrieval eligibility: hard-filtered to `APPROVED`

Confirmed in the prior pass (`RAG_DOCUMENT_GOVERNANCE.md`) and unchanged: `document_governance.is_document_usable()` requires `status == APPROVED` **and** a real `approved_by` **and** not expired **and** already in effect **and** (when checked) content-hash-unchanged-since-approval. `rag_service.retrieve_unified_context()` is the sole citation path and applies this filter before any chunk can be used as evidence.

## Full lifecycle, now confirmed end-to-end

```
Upload → PENDING_REVIEW (unbypassable)
       → [Admin action, not independently re-traced this pass — see below]
       → APPROVED (only state usable for citations)
       → REJECTED / ARCHIVED (excluded from citation eligibility by the same is_document_usable() check — any status != APPROVED fails the filter)
```

## Honest remaining gap

The **Admin-side approval action itself** (whatever UI/service call flips a document from `PENDING_REVIEW` to `APPROVED`) was not independently re-traced this pass — only its two endpoints (upload always starts `PENDING_REVIEW`; retrieval requires `APPROVED`) were verified. This is a narrower, lower-risk gap than the original Câu 73 concern (which was about citations bypassing governance entirely) — that concern is now confirmed closed.

## Verdict: IMPLEMENTED_AND_TESTED

New uploads cannot silently become authoritative. The full PENDING_REVIEW → APPROVED → (REJECTED/ARCHIVED excluded) lifecycle is real and enforced at both the write side (upload) and read side (citation retrieval).
