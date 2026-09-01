"""Deterministic final-response quality and date-scope protections."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.retrieval.models import RetrievedDocument
_PLACEHOLDER_RE = re.compile(
    r"\*{4,}|(?:\[|\{|<)(?:ADDRESS|EMAIL|NAME|PHONE|PII|URL|WEBSITE|CONTACT|TBD)(?::[^\]\}>]*)?(?:\]|\}|>)",
    flags=re.IGNORECASE,
)
_PHONE_PLACEHOLDER_RE = re.compile(
    r"\*{4,}|(?:\[|\{|<)(?:PHONE|CONTACT)(?::[^\]\}>]*)?(?:\]|\}|>)",
    re.IGNORECASE,
)
_WEBSITE_PLACEHOLDER_RE = re.compile(
    r"(?:\[|\{|<)(?:URL|WEBSITE)(?::[^\]\}>]*)?(?:\]|\}|>)",
    re.IGNORECASE,
)
_EXPLICIT_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_INCOMPLETE_ENGLISH_END_RE = re.compile(
    r"\b(?:a|an|the|at|include|including|in\s+the)\s*[,:;.!?]?\s*$",
    re.IGNORECASE,
)
_INTERNAL_RETRIEVAL_LANGUAGE_RE = re.compile(
    r"\b(?:retrieved|approved)\s+(?:(?:authori[sz]ed|approved)\s+)?"
    r"(?:chunks?|directory\s+records?|evidence\s+chunks?)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _public_contacts() -> dict[str, Any]:
    default_path = Path(__file__).resolve().parents[2] / "config" / "public_contacts.json"
    path = Path(os.environ.get("PUBLIC_CONTACTS_PATH", str(default_path)))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def contact_for_country(country: str) -> dict[str, str]:
    """Return reviewed public contact values for one market."""
    payload = _public_contacts()
    default = payload.get("default", {})
    countries = payload.get("countries", {})
    market = countries.get((country or "").upper(), {}) if isinstance(countries, dict) else {}
    merged = {
        **(default if isinstance(default, dict) else {}),
        **(market if isinstance(market, dict) else {}),
    }
    return {str(key): str(value).strip() for key, value in merged.items() if str(value).strip()}


def remove_or_replace_contact_placeholders(answer: str, country: str) -> tuple[str, list[str]]:
    """Resolve reviewed contact tokens and remove unresolved contact-bearing lines."""
    if not answer:
        return answer, []
    contacts = contact_for_country(country)
    changes: list[str] = []
    lines: list[str] = []
    for line in answer.splitlines():
        updated = line
        if _WEBSITE_PLACEHOLDER_RE.search(updated):
            website = contacts.get("website", "")
            if website:
                updated = _WEBSITE_PLACEHOLDER_RE.sub(website, updated)
                changes.append("website_replaced")
            else:
                changes.append("website_line_removed")
                continue
        if _PHONE_PLACEHOLDER_RE.search(updated):
            phone = contacts.get("customerCarePhone", "")
            if phone:
                updated = _PHONE_PLACEHOLDER_RE.sub(phone, updated)
                changes.append("phone_replaced")
            else:
                changes.append("phone_line_removed")
                continue
        if _PLACEHOLDER_RE.search(updated):
            changes.append("unresolved_placeholder_line_removed")
            continue
        if updated.strip():
            lines.append(updated.rstrip())
    return "\n".join(lines).strip(), sorted(set(changes))


def contains_unresolved_placeholder(answer: str) -> bool:
    """Return whether a user-visible placeholder remains."""
    return bool(_PLACEHOLDER_RE.search(answer or ""))


def has_incomplete_ending(answer: str, language: str = "") -> bool:
    """Detect high-confidence broken endings without rewriting factual content."""
    text = (answer or "").strip()
    if not text:
        return True
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return True
    locale = (language or "en").split("-", 1)[0].lower()
    return locale == "en" and bool(_INCOMPLETE_ENGLISH_END_RE.search(text))


def contains_internal_retrieval_language(answer: str) -> bool:
    """Return whether implementation jargon leaked into customer-facing copy."""
    return bool(_INTERNAL_RETRIEVAL_LANGUAGE_RE.search(answer or ""))


def unsupported_requested_years(question: str, documents: Iterable[RetrievedDocument]) -> list[int]:
    """Return explicit requested years that are absent from dated approved evidence."""
    requested = sorted({int(value) for value in _EXPLICIT_YEAR_RE.findall(question or "")})
    if not requested:
        return []

    evidence_years: set[int] = set()
    effective_years: list[int] = []
    for document in documents:
        evidence_years.update(int(value) for value in _EXPLICIT_YEAR_RE.findall(document.content or ""))
        values = [
            document.document_version,
            document.metadata.get("effective_date", ""),
            document.metadata.get("expiry_date", ""),
            document.metadata.get("document_version", ""),
        ]
        for value in values:
            years = [int(item) for item in _EXPLICIT_YEAR_RE.findall(str(value or ""))]
            evidence_years.update(years)
            effective_years.extend(years)

    # Without dated evidence, leave the normal evidence contract in control.
    if not effective_years:
        return []
    minimum, maximum = min(effective_years), max(effective_years)
    return [year for year in requested if year not in evidence_years and not minimum <= year <= maximum]


def format_period_not_covered(template: str, years: list[int]) -> str:
    """Format a reviewed period-unavailable response without model generation."""
    period = ", ".join(str(year) for year in years)
    return template.replace("{period}", period)
