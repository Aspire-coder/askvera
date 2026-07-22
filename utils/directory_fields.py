"""Preserve label/value fields from approved global directory records."""

from __future__ import annotations

import re
from collections.abc import Iterable


_FIELD_LABEL_RE = re.compile(
    r"(?:country|name|address|phone(?:\s*\d+)?|fax|toll[ -]?free|mailbox|website|"
    r"contact|title|email|cell#?|territor(?:y|ies)|region|office|product center)$",
    re.IGNORECASE,
)
_CONTACT_FIELD_RE = re.compile(
    r"(?:address|phone(?:\s*\d+)?|fax(?:\s*\d+)?|toll[ -]?free|mailbox|website|email|cell#?)$",
    re.IGNORECASE,
)


def parse_directory_fields(content: str) -> dict[str, str]:
    """Parse the directory's repeated labels while preserving exact field values."""
    lines = [" ".join(line.split()) for line in (content or "").splitlines() if line.strip()]
    fields: dict[str, str] = {}
    index = 1  # The first line is the record title, not a field label.
    while index < len(lines):
        label = lines[index]
        if not _is_field_label(label):
            index += 1
            continue
        index += 1
        values: list[str] = []
        while index < len(lines) and not _is_field_label(lines[index]):
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
    """Restore exact approved contact values omitted by model summarization.

    Only structured fields parsed from retrieved directory evidence are eligible.
    This does not infer, translate, or reconstruct contact information.
    """
    original = (answer or "").strip()
    missing: list[tuple[str, str]] = []
    seen_values: set[str] = set()

    for fields in field_sets:
        for raw_label, raw_value in fields.items():
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

    exact_fields = "\n".join(f"**{label}:** {value}" for label, value in missing)
    separator = "\n\n" if original else ""
    return f"{original}{separator}{exact_fields}", [label for label, _ in missing]


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
