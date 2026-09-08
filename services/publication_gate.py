"""Decide whether a document may be published, and refuse to be bypassed.

The policy this implements:

    Confirmed missing or unreadable content  -> block until recovered
    Suspicious page, completeness uncertain  -> explicit reviewer resolution
    Verified decorative or genuinely blank   -> allow
    OCR completed                            -> recheck coverage, not approval

Upload and processing are never restricted. The restriction belongs at
publication, so a person can inspect a document and resolve what is wrong with
it rather than being told to try again with no idea what failed.

Two properties this module exists to guarantee, both of them tested:

A contradiction is not waivable. No decision, flag or retry publishes a
document whose expiry precedes its own effective date, because no reading makes
it true. Only correcting the metadata and revalidating clears it.

A resolution belongs to one revision. It records what a named person decided
about a specific document at a specific time, so it cannot survive the document
or its metadata changing underneath it - that would let an approval of one
thing authorise publication of another.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.metadata_conflicts import MetadataFinding, Severity


class PublicationBlocked(Exception):
    """Publication refused. Carries every reason, not just the first."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(" ".join(reasons))


@dataclass(frozen=True)
class ReviewerResolution:
    """A named person's recorded decision about one revision of one document."""

    revision: str
    decided_by: str
    decision: str  # "publish" or "reject"
    reason: str
    decided_at: str

    def is_valid_for(self, revision: str) -> bool:
        """Whether this decision still describes the document being published."""
        return bool(self.revision) and self.revision == revision and self.decision == "publish"


def revision_fingerprint(*, content_hash: str, metadata: dict[str, Any]) -> str:
    """Identify an exact document revision, content and metadata together.

    Metadata is part of the revision, not a label on it. Re-declaring a
    document's country changes what publishing it means, even when the bytes are
    identical, so a resolution taken before that change must not carry over.
    """
    material = json.dumps(
        {"content_hash": str(content_hash or ""), "metadata": _stable(metadata)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _stable(metadata: dict[str, Any]) -> dict[str, str]:
    """Only the fields that change what publication means."""
    fields = ("country", "language", "document_type", "access_scope", "version",
              "effective_date", "expiry_date", "filename")
    return {field: str(metadata.get(field) or "") for field in fields}


def evaluate_publication(
    *,
    findings: list[MetadataFinding],
    extraction_blocking_pages: list[int],
    extraction_uncertain_pages: list[int],
    revision: str,
    resolution: ReviewerResolution | None = None,
) -> None:
    """Raise PublicationBlocked unless this revision may be published now.

    extraction_blocking_pages are pages whose content is confirmed missing or
    unreadable. extraction_uncertain_pages are pages that may be complete and
    may not - a readable heading above something this parser could not read.
    The first blocks; the second requires a decision.
    """
    reasons: list[str] = []

    contradictions = [f for f in findings if f.severity == Severity.CONTRADICTION]
    for finding in contradictions:
        reasons.append(
            f"{finding.field}: {finding.detail} This cannot be waived; correct the "
            "metadata and revalidate."
        )

    if extraction_blocking_pages:
        pages = ", ".join(str(page) for page in extraction_blocking_pages)
        reasons.append(
            f"Content on page(s) {pages} could not be extracted. Publishing would omit it "
            "silently. Recover the content or supply a corrected document."
        )

    unresolved = [f for f in findings if f.severity == Severity.UNRESOLVED]
    needs_decision = bool(unresolved or extraction_uncertain_pages)
    if needs_decision and not (resolution and resolution.is_valid_for(revision)):
        detail: list[str] = [f"{finding.field}: {finding.detail}" for finding in unresolved]
        if extraction_uncertain_pages:
            pages = ", ".join(str(page) for page in extraction_uncertain_pages)
            detail.append(
                f"Page(s) {pages} carry an image and little text, so completeness is "
                "uncertain. Confirm the content is decorative or blank, or recover it."
            )
        if resolution and resolution.revision != revision:
            detail.append(
                "A reviewer decision exists but was made against a different revision of "
                "this document, so it no longer applies. Re-review the current revision."
            )
        reasons.append(
            "Unresolved findings require an explicit reviewer decision before "
            "publication: " + "; ".join(detail)
        )

    if reasons:
        raise PublicationBlocked(reasons)


def record_resolution(
    *, revision: str, decided_by: str, decision: str, reason: str
) -> ReviewerResolution:
    """Build a resolution, refusing the ones that would be meaningless."""
    if decision not in {"publish", "reject"}:
        raise ValueError("A resolution decision must be 'publish' or 'reject'.")
    if not str(decided_by or "").strip():
        raise ValueError("A resolution must record who made it.")
    if not str(reason or "").strip():
        raise ValueError(
            "A resolution must record why. An unexplained approval is indistinguishable "
            "from an accidental one when it is read back a year later."
        )
    if not str(revision or "").strip():
        raise ValueError("A resolution must name the revision it applies to.")
    return ReviewerResolution(
        revision=revision,
        decided_by=str(decided_by).strip()[:320],
        decision=decision,
        reason=str(reason).strip()[:2000],
        decided_at=datetime.now(timezone.utc).isoformat(),
    )
