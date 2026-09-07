"""Conservative English activity-rule experiment; does not approve evidence.

Not wired into the live provider. Unsupported languages and ambiguous/mixed
questions preserve ranking. Country/global authorization must occur upstream.
"""

import re
from typing import Any, Sequence


def asks_activity_qualification(question: str, language: str) -> bool:
    if language.lower().split("-")[0] != "en":
        return False
    text = " ".join(question.lower().split())
    if re.search(r"\band\b|;", text) or text.count("?") > 1:
        return False
    # Benefits, retention and termination are different targets, even when
    # 'Active' is mentioned as context. Defer compound cases to the baseline.
    if re.search(r"\b(?:bonus(?:es)?|incentive|payments?|terminated?|termination|lose|losing|retain|retention)\b", text):
        return False
    return bool(re.search(
        r"\b(?:qualify|qualifying|qualified)\s+(?:again\s+)?(?:as|to\s+be)\s+active\b"
        r"|\b(?:automatically|considered|become|becoming|stay|staying|remain|remaining)\s+active\b"
        r"|\b(?:active\s+status|activity\s+qualification)\b",
        text,
    ))


def is_activity_governing_clause(row: dict[str, Any]) -> bool:
    if row.get("access_scope") != "country" or row.get("document_type") != "policy":
        return False
    title = " ".join(str(row.get("section_title", "")).lower().split()).strip(". ")
    content = " ".join(str(row.get("content", "")).lower().split())
    # Match the actual property definition, not a passage about an incentive
    # whose requirements merely include being Active.
    defining_text = bool(re.search(r"\bto be considered active\b.{0,180}\bmust\b", content))
    governing_title = title in {"activity qualification", "active", "active status"}
    defining_title = title.startswith("to be considered active")
    return defining_text and (governing_title or defining_title)


def prioritize_activity_rule(
    question: str, rows: Sequence[dict[str, Any]], language: str,
) -> list[dict[str, Any]]:
    """Stable partition of eligible passages; scores and approval remain untouched."""
    if not asks_activity_qualification(question, language):
        return list(rows)
    governing, other = [], []
    for row in rows:
        (governing if is_activity_governing_clause(row) else other).append(row)
    return [*governing, *other]
