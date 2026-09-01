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
_SELF_REFERENTIAL_VALUE_RE = re.compile(
    r"^(?:see|as|same as)\s+above$",
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
        # Prefer a complete standalone label such as "Telephone Office" over
        # interpreting "Office" as its inline value. Same-line fields still
        # fall through to the inline parser because they are not standalone
        # labels.
        if inline and not _is_field_label(label):
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
    different office returned as supporting retrieval evidence. When the
    answer already states that same labeled field with a different value -
    a mangled number, a dropped digit, a stale placeholder - that line is
    corrected in place instead of leaving it wrong and appending a duplicate.
    """
    original = (answer or "").strip()
    missing: list[tuple[str, str]] = []
    corrected_labels: list[str] = []
    seen_values: set[str] = set()

    primary_fields = next((fields for fields in field_sets if fields), {})
    contact_fields = [
        (str(label).strip(), str(value).strip())
        for label, value in primary_fields.items()
        if _CONTACT_FIELD_RE.search(str(label).strip())
        and str(value).strip()
        and not _is_self_referential_value(str(value))
    ]
    has_correct_value = any(_value_is_present(original, value) for _, value in contact_fields)
    # A labeled line for one of these exact fields - even holding a wrong or
    # placeholder value - is itself evidence the model was answering this
    # directory question, so a correction is safe even with no correct value
    # already present anywhere else in the answer.
    has_labeled_contact_line = any(
        _replace_labeled_line_value(original, label, value)[1] for label, value in contact_fields
    )
    if not has_correct_value and not has_labeled_contact_line:
        return original, []

    corrected = original
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
            or _is_self_referential_value(value)
        ):
            continue
        seen_values.add(normalized_value)
        if _value_is_present(corrected, value):
            continue
        replaced, replacement_count = _replace_labeled_line_value(corrected, label, value)
        if replacement_count:
            corrected = replaced
            corrected_labels.append(label)
        else:
            missing.append((label, value))

    if not missing and not corrected_labels:
        return original, []

    if missing:
        exact_fields = "\n".join(f"{label}: {value}" for label, value in missing)
        separator = "\n\n" if corrected.strip() else ""
        corrected = f"{corrected}{separator}{exact_fields}"

    return corrected, [*corrected_labels, *(label for label, _ in missing)]


def _replace_labeled_line_value(text: str, label: str, value: str) -> tuple[str, int]:
    """Replace an existing 'Label: wrong-value' line's value with the approved one."""
    pattern = re.compile(
        rf"(?im)^(\s*\**{re.escape(label)}\**\s*[:#-]\s*\**\s*)(.+)$"
    )
    return pattern.subn(lambda match: f"{match.group(1)}{value}", text, count=1)


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


def remove_unrequested_directory_fields(answer: str, question: str) -> tuple[str, bool]:
    """Remove extra labelled directory fields when one field was requested."""
    question_text = (question or "").casefold()
    if re.search(r"\b(all|every|complete)\s+(contact|directory)|\bcontact details?\b", question_text):
        return answer, False

    if re.search(r"\b(phone|telephone)\b", question_text):
        allowed = r"telephone(?!\s+for\s+orders)(?:\s+office)?|phone(?:\s*\d+)?"
    elif re.search(r"\b(email|e-mail)\b", question_text):
        allowed = r"email|e-mail"
    elif re.search(r"\b(website|web site|url)\b", question_text):
        allowed = r"website|web site|url"
    elif re.search(r"\b(address|located|location)\b", question_text):
        allowed = r"(?:office\s*(?:&|and)\s*product\s+center\s+)?address"
    elif re.search(r"\b(business|office)\s+hours?\b|\bhours?\b", question_text):
        allowed = r"business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?"
    elif re.search(r"\b(minimum|ordering|order)\b.*\b(order|size)\b|\border\s+size\b", question_text):
        cleaned, replacements = re.subn(
            r"(?:payment\s+methods?\s+accepted|delivery\s+cost|delivery\s+charge|"
            r"average\s+lead\s+time|business\s+hours?)[^.!?]*(?:[.!?]|$)\s*",
            "",
            answer or "",
            flags=re.IGNORECASE,
        )
        return cleaned.strip(), replacements > 0
    else:
        return answer, False

    labels = (
        r"telephone\s+for\s+orders|telephone(?:\s+office)?|phone(?:\s*\d+)?|"
        r"business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?|"
        r"office\s*(?:&|and)\s*product\s+center\s+address|address|fax|email|website"
    )
    pattern = re.compile(
        rf"(?<!\w)(?!{allowed}\b)(?P<label>{labels})\s*:\s*[^\n]*(?:\n|$)",
        re.IGNORECASE,
    )
    cleaned, replacements = pattern.subn("", answer or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, replacements > 0


def restore_missing_requested_order_size(
    answer: str,
    source_texts: Iterable[str],
    question: str,
) -> tuple[str, bool]:
    """Restore an explicit minimum-order value when another FAQ row was selected."""
    if not re.search(r"\b(minimum|ordering|order)\b.*\b(order|size)\b|\border\s+size\b", question or "", re.IGNORECASE):
        return answer, False
    corrected = answer or ""
    for source in source_texts:
        match = re.search(
            r"minimum\s+order\s+size\s+fbo\s*[:\-]\s*(?P<value>[^.\n]+)",
            source or "",
            re.IGNORECASE,
        )
        if not match:
            continue
        value = " ".join(match.group("value").split()).strip()
        if value and _normalize_for_comparison(value) not in _normalize_for_comparison(corrected):
            separator = "\n\n" if corrected.strip() else ""
            corrected = f"{corrected.strip()}{separator}Minimum order size FBO: {value}."
            return corrected, True
        return corrected, False
    return corrected, False


def correct_directory_source_contradictions(
    answer: str,
    source_texts: Iterable[str],
) -> tuple[str, bool]:
    """Correct generated directory claims that contradict explicit source text."""
    corrected = answer or ""
    changed = False
    for source in source_texts:
        source_text = source or ""
        order_match = re.search(
            r"(?P<cc>\d+(?:[.,]\d+)?\s*CC).*?(?:around|approximately)\s*"
            r"(?P<amount>[\d.,]+)\s*(?P<currency>[A-Z]{3})\b",
            source_text,
            re.IGNORECASE | re.DOTALL,
        )
        if order_match and re.search(re.escape(order_match.group("cc")), corrected, re.IGNORECASE):
            amount = order_match.group("amount")
            currency = order_match.group("currency").upper()
            corrected, replacements = re.subn(
                rf"({re.escape(order_match.group('cc'))}.*?\b(?:around|approximately)\s+)"
                rf"[\d.,]+\s+{re.escape(currency)}\b",
                rf"\g<1>{amount} {currency}",
                corrected,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            changed = changed or replacements > 0

        if re.search(
            r"after\s+sponsorship\s*[:\-]?\s*(?:we\s+)?(?:do\s+not|don't|do\s+not)\s+have\s+a\s+minimum\s+order",
            source_text,
            re.IGNORECASE,
        ):
            corrected, replacements = re.subn(
                r"after\s+sponsorship\s*[:\-]?\s*[^.\n]+(?:\.|$)",
                "After sponsorship: there is no minimum order.",
                corrected,
                count=1,
                flags=re.IGNORECASE,
            )
            changed = changed or replacements > 0

    return corrected, changed


def _is_field_label(value: str) -> bool:
    return len(value) <= 80 and bool(_FIELD_LABEL_RE.search(value.strip()))


def _is_self_referential_value(value: str) -> bool:
    """Detect a print-layout cross-reference such as "(see above)".

    Source documents sometimes point a field at another one already printed
    nearby ("Telephone for Orders: (see above)") - a convention that makes
    sense on a printed page but not as a standalone bullet in a chat answer,
    where there is nothing visible "above" to refer to. Never restored or
    used to correct a line; the field is simply omitted rather than guessed.
    """
    return bool(_SELF_REFERENTIAL_VALUE_RE.match(value.strip().strip("()")))


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
