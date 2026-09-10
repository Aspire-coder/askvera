"""Detect missing or contradictory document metadata before publication.

Nothing here invents a value. Where metadata is absent or disagrees with the
document it describes, that is reported for a person to resolve; guessing a
country from a filename, or stamping today's date on a policy with no stated
effective date, would put a fabricated fact into the corpus wearing the
authority of approved content.

The distinction that matters is between a contradiction and an absence.

A document whose expiry precedes its effective date cannot be correct under any
reading. That is not waivable: publication stays blocked until the metadata is
corrected and the document revalidated, because there is no decision a reviewer
could make that renders it true.

A document with no effective date may be entirely fine - 15 of 28 documents in
the corpus have none - and needs a recorded decision rather than a rejection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Policy and directory filenames in this corpus carry the market and language
# they belong to: "DK-EN-Company-Policy.pdf", "SE-SV-Company-Policy.pdf". The
# prefix is evidence about the document, not a value to adopt - a mismatch is
# reported, never silently used to overwrite what the uploader declared.
_FILENAME_LOCALE_RE = re.compile(r"^(?P<country>[A-Z]{2})-(?P<language>[A-Z]{2})-", re.ASCII)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Severity:
    """How a finding must be handled before the document is published."""

    # Cannot be correct under any reading, and is NOT WAIVABLE. Publication is
    # blocked until the metadata is corrected and the document revalidated - a
    # reviewer cannot decide their way past an expiry that precedes its own
    # effective date, because there is no reading under which it is true.
    CONTRADICTION = "contradiction"
    # May be correct. Requires an explicit reviewer decision, recorded, before
    # publication. Not a warning to be scrolled past.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class MetadataFinding:
    """One problem found in a document's declared metadata."""

    field: str
    severity: str
    detail: str


def detect_metadata_conflicts(
    *,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    version: str = "",
    effective_date: str = "",
    expiry_date: str = "",
    today: date | None = None,
) -> list[MetadataFinding]:
    """Return everything wrong or unestablished about this document's metadata."""
    findings: list[MetadataFinding] = []
    findings.extend(_filename_findings(filename, country, language))
    findings.extend(_date_findings(effective_date, expiry_date, today or date.today()))

    if not str(version or "").strip():
        findings.append(
            MetadataFinding(
                "version",
                Severity.UNRESOLVED,
                "No human-readable version was supplied. A replacement may still be "
                "distinguishable by content hash, ingestion id or generation pointer - "
                "check those before treating this as ambiguous. What is lost is the "
                "version a reviewer can read and cite.",
            )
        )
    if not str(document_type or "").strip():
        findings.append(
            MetadataFinding("document_type", Severity.UNRESOLVED, "No document type was supplied.")
        )
    return findings


def _filename_findings(filename: str, country: str, language: str) -> list[MetadataFinding]:
    """Compare the declared market and language against the filename's own claim."""
    match = _FILENAME_LOCALE_RE.match(Path(filename or "").name.upper())
    if not match:
        return []

    findings: list[MetadataFinding] = []
    declared_country = str(country or "").strip().upper()
    declared_language = str(language or "").strip().upper()
    named_country = match.group("country")
    named_language = match.group("language")

    # A market code and its document country can legitimately differ - the GB
    # market is served by documents tagged UK - so an alias is resolved before
    # a mismatch is reported rather than after.
    if declared_country and named_country not in _document_countries_for(declared_country):
        findings.append(
            MetadataFinding(
                "country",
                Severity.UNRESOLVED,
                f"The filename suggests {named_country}; the upload declares "
                f"{declared_country}. A filename is a clue about a document, not "
                "metadata about it - it is written by whoever saved the file. Resolve "
                "against the document's own content. The declared country is never "
                "overridden from a filename.",
            )
        )
    if declared_language and named_language != declared_language:
        findings.append(
            MetadataFinding(
                "language",
                Severity.UNRESOLVED,
                f"The filename suggests {named_language}; the upload declares "
                f"{declared_language}. Resolve against the document's own content; the "
                "filename is a clue and is never adopted automatically.",
            )
        )
    return findings


def _document_countries_for(market: str) -> set[str]:
    """Document country codes this market's documents may legitimately carry."""
    try:
        from services.market_config import get_document_country_codes

        codes = {str(code).upper() for code in get_document_country_codes(market)}
    except Exception:  # noqa: BLE001 - configuration problems are reported elsewhere.
        codes = set()
    return codes or {market}


def _date_findings(effective_date: str, expiry_date: str, today: date) -> list[MetadataFinding]:
    """Check the dates against each other and against the calendar."""
    findings: list[MetadataFinding] = []
    effective = str(effective_date or "").strip()
    expiry = str(expiry_date or "").strip()

    if not effective:
        findings.append(
            MetadataFinding(
                "effective_date",
                Severity.UNRESOLVED,
                "No effective date was supplied, so historical applicability cannot be "
                "verified: nothing establishes which period this document governs. "
                "Date-scope checks key off effective_date and document_version, so they "
                "have nothing to act on here. What a dated question actually returns "
                "depends on the rest of the pipeline and is not asserted by this check. "
                "The date is not inferred.",
            )
        )
    for field, value in (("effective_date", effective), ("expiry_date", expiry)):
        if value and not _ISO_DATE_RE.match(value):
            findings.append(
                MetadataFinding(field, Severity.CONTRADICTION, f"{value!r} is not an ISO date.")
            )

    parsed_effective = _parse(effective)
    parsed_expiry = _parse(expiry)
    if parsed_effective and parsed_expiry and parsed_expiry < parsed_effective:
        findings.append(
            MetadataFinding(
                "expiry_date",
                Severity.CONTRADICTION,
                f"Expiry {expiry} precedes effective {effective}. The document would never "
                "have been in force.",
            )
        )
    if parsed_effective and parsed_effective > today:
        findings.append(
            MetadataFinding(
                "effective_date",
                Severity.UNRESOLVED,
                f"Effective {effective} is in the future. Staging is legitimate; what "
                "needs deciding is whether this document may answer current-policy "
                "questions before that date, and what a question about the future period "
                "should return. Neither behaviour is defined by this check.",
            )
        )
    return findings


def _parse(value: str) -> date | None:
    if not _ISO_DATE_RE.match(value or ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def blocking_findings(findings: list[MetadataFinding]) -> list[MetadataFinding]:
    """The findings no reviewer decision can make acceptable."""
    return [finding for finding in findings if finding.severity == Severity.CONTRADICTION]
