"""Preserve label/value fields from approved global directory records."""

from __future__ import annotations

import re
from collections.abc import Iterable


_FIELD_LABEL_RE = re.compile(
    r"(?:country|name|address|phone(?:\s*\d+)?|telephone(?:\s+(?:for\s+orders|office))?|"
    r"business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?|fax|toll[ -]?free|mailbox|website|"
    r"contact|title|email|cell#?|territor(?:y|ies)|region|office|product center)$",
    re.IGNORECASE,
)
_CONTACT_FIELD_RE = re.compile(
    r"(?:address|phone(?:\s*\d+)?|telephone(?:\s+(?:for\s+orders|office))?|"
    r"fax(?:\s*\d+)?|toll[ -]?free|mailbox|website|email|cell#?)$",
    re.IGNORECASE,
)
_INLINE_FIELD_RE = re.compile(
    r"^(?P<label>business\s+hours\s+(?:office|product\s+(?:centre|center))|"
    r"telephone(?:\s+(?:for\s+orders|office))?|phone(?:\s*\d+)?|"
    r"office\s*(?:&|and)\s*product\s+center\s+address|"
    r"address|fax(?:\s*\d+)?|toll[ -]?free|mailbox|website|email|cell#?)"
    r"\s*[:#-]?\s+(?P<value>.+)$",
    re.IGNORECASE,
)


def parse_directory_fields(content: str) -> dict[str, str]:
    """Parse the directory's repeated labels while preserving exact field values."""
    lines = [
        " ".join(line.replace("\ufffd", " ").split())
        for line in (content or "").splitlines()
        if line.strip()
    ]
    fields: dict[str, str] = {}
    index = 1  # The first line is the record title, not a field label.
    while index < len(lines):
        label = lines[index]
        inline = _INLINE_FIELD_RE.match(label)
        if inline:
            fields[" ".join(inline.group("label").split())] = inline.group("value").strip()
            index += 1
            continue
        if not _is_field_label(label):
            index += 1
            continue
        index += 1
        values: list[str] = []
        while index < len(lines) and not (
            _is_field_label(lines[index]) or _INLINE_FIELD_RE.match(lines[index])
        ):
            values.append(lines[index])
            index += 1
        value = " ".join(values).strip()
        if value:
            fields[label] = value
    return fields


def format_directory_fields(fields: dict[str, object]) -> str:
    """Render non-empty approved fields without inventing placeholders."""
    return "\n".join(
        f"{label}: {str(value).strip()}"
        for label, value in fields.items()
        if str(label).strip() and str(value).strip()
    )


def restore_missing_directory_contacts(
    answer: str,
    field_sets: Iterable[dict[str, object]],
) -> tuple[str, list[str]]:
    """Restore exact contacts from the highest-ranked directory record.

    Only structured fields parsed from retrieved directory evidence are eligible.
    Secondary records must never contribute fields because they may describe a
    different office returned as supporting retrieval evidence.
    """
    original = (answer or "").strip()
    missing: list[tuple[str, str]] = []
    seen_values: set[str] = set()

    primary_fields = next((fields for fields in field_sets if fields), {})
    approved_contacts = [
        str(value).strip()
        for label, value in primary_fields.items()
        if _CONTACT_FIELD_RE.search(str(label).strip()) and str(value).strip()
    ]
    if not any(_value_is_present(original, value) for value in approved_contacts):
        return original, []

    for raw_label, raw_value in primary_fields.items():
        label = str(raw_label).strip()
        value = str(raw_value).strip()
        normalized_value = _normalize_for_comparison(value)
        if (
            not label
            or not value
            or not _CONTACT_FIELD_RE.search(label)
            or not normalized_value
            or normalized_value in seen_values
        ):
            continue
        seen_values.add(normalized_value)
        if not _value_is_present(original, value):
            missing.append((label, value))

    if not missing:
        return original, []

    exact_fields = "\n".join(f"{label}: {value}" for label, value in missing)
    separator = "\n\n" if original else ""
    return f"{original}{separator}{exact_fields}", [label for label, _ in missing]


def restore_missing_requested_directory_fields(
    answer: str,
    field_sets: Iterable[dict[str, object]],
    question: str,
) -> tuple[str, list[str]]:
    """Restore the exact structured directory field explicitly requested.

    Directory prompts can contain a complete field while the generated answer
    accidentally leaves its value blank. Only the requested field is eligible
    here, and only from the highest-ranked record, so unrelated fields and
    neighboring countries cannot be appended.
    """
    original = (answer or "").strip()
    question_text = (question or "").casefold()
    requested_patterns: list[re.Pattern[str]] = []
    if re.search(r"\b(business|office)\s+hours?\b|\bhours?\b", question_text):
        requested_patterns.append(re.compile(r"^business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?$", re.IGNORECASE))
    if not requested_patterns:
        return original, []

    primary_fields = next((fields for fields in field_sets if fields), {})
    missing: list[tuple[str, str]] = []
    for raw_label, raw_value in primary_fields.items():
        label = str(raw_label).strip()
        value = str(raw_value).strip()
        if not label or not value or not any(pattern.search(label) for pattern in requested_patterns):
            continue
        if not _value_is_present(original, value):
            missing.append((label, value))

    if not missing:
        return original, []
    exact_fields = "\n".join(f"{label}: {value}" for label, value in missing)
    separator = "\n\n" if original else ""
    return f"{original}{separator}{exact_fields}", [label for label, _ in missing]


def preserve_directory_role_labels(answer: str, source_texts: Iterable[str]) -> tuple[str, bool]:
    """Keep an explicit directory role label when generation drops it.

    Some country records distinguish an FBO minimum order from a separate
    Preferred Customer first-order statement. If the approved source contains
    the explicit FBO label and the answer shortens it to a generic minimum
    order, restore only that source-backed label.
    """
    if not any(re.search(r"minimum\s+order\s+size\s+fbo\b", text or "", re.IGNORECASE) for text in source_texts):
        return answer, False
    corrected, replacements = re.subn(
        r"(?<!fbo\s)(minimum\s+order\s+size)(?=\s+(?:is|for)\b)",
        r"FBO \1",
        answer or "",
        count=1,
        flags=re.IGNORECASE,
    )
    return corrected, replacements > 0


def _is_field_label(value: str) -> bool:
    return len(value) <= 80 and bool(_FIELD_LABEL_RE.search(value.strip()))


def _value_is_present(answer: str, value: str) -> bool:
    normalized_answer = _normalize_for_comparison(answer)
    normalized_value = _normalize_for_comparison(value)
    if normalized_value and normalized_value in normalized_answer:
        return True

    value_digits = "".join(re.findall(r"\d", value))
    answer_digits = "".join(re.findall(r"\d", answer))
    return len(value_digits) >= 7 and value_digits in answer_digits


def _normalize_for_comparison(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))
