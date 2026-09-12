"""Preserve label/value fields from approved global directory records."""

from __future__ import annotations

import bisect
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


# --- B1: one requested-field-set helper reused by removal and restoration ---
#
# The old code detected "the one field the question asked about" with an
# if/elif chain, so a compound request such as "phone and email" only ever
# matched the first branch (phone) and treated email as unrequested. A single
# small vocabulary of canonical field keys - each with its own "is this field
# named in the question" pattern and its own "does this directory label mean
# this field" pattern - lets both removal and restoration agree on what was
# actually asked for, including every compound combination, without either
# function guessing from a single first match.
_FIELD_REQUEST_PATTERNS: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"\b(?:phone|telephone)\b", re.IGNORECASE),
    "email": re.compile(r"\b(?:email|e-mail)\b", re.IGNORECASE),
    "website": re.compile(r"\b(?:website|web\s*site|url)\b", re.IGNORECASE),
    "address": re.compile(r"\b(?:address|located|location)\b", re.IGNORECASE),
    "business_hours": re.compile(r"\b(?:business|office)\s+hours?\b|\bhours?\b", re.IGNORECASE),
    "payment_methods": re.compile(r"\bpayment\s+methods?\b", re.IGNORECASE),
    "delivery_cost": re.compile(r"\bdelivery\s+(?:cost|charge|fee)s?\b", re.IGNORECASE),
    "delivery_time": re.compile(
        r"\bdelivery\s+time\b|\blead\s+time\b|\bhow\s+long\b[^.?!]*\bdeliver", re.IGNORECASE
    ),
}
# Order phone is a qualifier of the phone request, not an independent field:
# "office phone" must exclude it, while "office and order phone" or any
# mention of "order" alongside phone/telephone must include it.
_ORDER_PHONE_REQUEST_RE = re.compile(r"\border\b", re.IGNORECASE)

# How each canonical field's directory label is recognised, reused for both
# stripping an unrequested "Label: value" line and restoring a requested one
# from the approved record. Order matters when testing a label against these:
# order_phone must be tried before phone so "Telephone for Orders" is not
# absorbed by phone's broader pattern.
_FIELD_LABEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "order_phone": re.compile(r"^(?:telephone\s+for\s+orders|order\s*phone(?:\s*\d+)?)$", re.IGNORECASE),
    "phone": re.compile(
        r"^(?:telephone(?:\s+office)?|phone(?:\s*\d+)?)$", re.IGNORECASE
    ),
    "email": re.compile(r"^(?:email|e-mail)$", re.IGNORECASE),
    "website": re.compile(r"^(?:website|web\s*site|url)$", re.IGNORECASE),
    "address": re.compile(
        r"^(?:(?:office\s*(?:&|and)\s*product\s+center\s+)?address)$", re.IGNORECASE
    ),
    "business_hours": re.compile(
        r"^business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?$", re.IGNORECASE
    ),
    "payment_methods": re.compile(r"^payment\s+methods?(?:\s+accepted)?$", re.IGNORECASE),
    "delivery_cost": re.compile(r"^delivery\s+(?:cost|charge|fee)s?$", re.IGNORECASE),
    "delivery_time": re.compile(r"^(?:average\s+)?(?:delivery|lead)\s+time$", re.IGNORECASE),
}
# Fragments (no anchors) used only to build the "this label line is allowed to
# stay" negative lookahead in remove_unrequested_directory_fields. Phone must
# exclude "telephone for orders" here even when order_phone is not part of
# the current allowed set - a prefix match against "phone" would otherwise
# also (wrongly) protect the order-phone line's "telephone" prefix.
_FIELD_ALLOWED_LINE_FRAGMENTS: dict[str, str] = {
    "order_phone": r"telephone\s+for\s+orders|order\s*phone(?:\s*\d+)?",
    "phone": r"telephone(?!\s+for\s+orders)(?:\s+office)?|phone(?:\s*\d+)?",
    "email": r"email|e-mail",
    "website": r"website|web\s*site|url",
    "address": r"(?:office\s*(?:&|and)\s*product\s+center\s+)?address",
    "business_hours": r"business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?",
    "payment_methods": r"payment\s+methods?(?:\s+accepted)?",
    "delivery_cost": r"delivery\s+(?:cost|charge|fee)s?",
    "delivery_time": r"(?:average\s+)?(?:delivery|lead)\s+time",
}


def _requested_directory_field_set(question: str) -> set[str] | None:
    """Return the canonical fields a question confidently names, or ``None``.

    ``None`` means the request was not confidently understood - the caller
    must not strip or guess anything in that case, rather than destructively
    acting on a first guessed match the way the old if/elif chain did.
    """
    text = question or ""
    requested: set[str] = set()
    for key, pattern in _FIELD_REQUEST_PATTERNS.items():
        if pattern.search(text):
            requested.add(key)
    if "phone" in requested and _ORDER_PHONE_REQUEST_RE.search(text):
        requested.add("order_phone")
    if not requested:
        return None
    return requested


def _label_canonical_field(label: str) -> str | None:
    """Map a parsed directory label to its canonical field key, if any."""
    normalized = " ".join((label or "").split())
    for key in ("order_phone", "phone", "email", "website", "address",
                "business_hours", "payment_methods", "delivery_cost", "delivery_time"):
        if _FIELD_LABEL_PATTERNS[key].search(normalized):
            return key
    return None


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


_CONTACT_REQUEST_RE = re.compile(
    r"\b(phone|telephone|number|email|e-mail|website|web\s+site|url|address|located|location|"
    r"fax|contact|reach)\b",
    re.IGNORECASE,
)
_NON_CONTACT_REQUEST_RE = re.compile(
    r"\b(business\s+hours?|office\s+hours?|hours?|open|opening|minimum\s+order|order\s+size|"
    r"delivery|bonus|payment|sponsor\w*)\b",
    re.IGNORECASE,
)


def _asks_only_for_a_non_contact_field(question: str) -> bool:
    """True when the question names a directory field that is not a contact.

    Restoring a phone number and a street address into an answer about opening
    hours adds facts nobody asked for, and every one of them then has to
    survive subject-aware grounding in a sentence about hours. On 2026-09-08
    that cost the Belgium office-hours answer its address and phone number:
    both were verbatim from the record - removal diagnostics reported them
    present in the source - and repair deleted them along with their sentences,
    failing the release gate.

    Contact restoration exists to correct a mangled or dropped contact value in
    an answer that is about contacts. It has no business in an answer that is
    not.
    """
    text = question or ""
    return bool(_NON_CONTACT_REQUEST_RE.search(text)) and not _CONTACT_REQUEST_RE.search(text)


def restore_missing_directory_contacts(
    answer: str,
    field_sets: Iterable[dict[str, object]],
    question: str = "",
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
    if _asks_only_for_a_non_contact_field(question):
        return original, []
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
    """Restore the exact structured directory field(s) explicitly requested.

    Directory prompts can contain a complete field while the generated answer
    accidentally leaves its value blank. Only fields the question confidently
    names are eligible, and only from the highest-ranked (primary) record, so
    unrelated fields and neighboring countries can never be appended. A
    request naming several fields (e.g. "payment methods and delivery cost")
    restores each one found in the primary record and silently skips any
    field the record does not have - it never invents the missing one.
    """
    original = (answer or "").strip()
    requested = _requested_directory_field_set(question)
    if not requested:
        return original, []

    primary_fields = next((fields for fields in field_sets if fields), {})
    missing: list[tuple[str, str]] = []
    for raw_label, raw_value in primary_fields.items():
        label = str(raw_label).strip()
        value = str(raw_value).strip()
        if not label or not value:
            continue
        canonical = _label_canonical_field(label)
        if canonical is None or canonical not in requested:
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


_DANGLING_LEAD_END = re.compile(
    r"(?:,\s*)?\b(?:the|a|an|and|or|with|for|to|at|in|of|from|that)\s*$",
    re.IGNORECASE,
)
_SCAFFOLDING_LEAD = re.compile(
    r"\s*(?:"
    r"(?:if|when)\s+you(?:\s*'re|\s+are)?\s+order(?:ing)?\s+online"
    r"|(?:for|with)\s+online\s+orders?"
    r"|when\s+ordering\s+online"
    r"|(?:please\s+)?keep\s+in\s+mind(?:\s+that)?"
    r")\s*,?\s*(?:the|a|an)?\s*",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _remove_field_sentences(answer: str, pattern: re.Pattern) -> tuple[str, int]:
    """Remove an unrequested field without leaving a broken lead-in behind."""
    spans: list[tuple[int, int, str]] = []
    boundaries = [match.end() for match in _SENTENCE_END.finditer(answer)]
    for match in pattern.finditer(answer):
        start, end = match.start(), match.end()
        lead_start = max((boundary for boundary in boundaries if boundary <= start), default=0)
        lead = answer[lead_start:start]
        if lead.strip() and _DANGLING_LEAD_END.search(lead):
            if _SCAFFOLDING_LEAD.fullmatch(lead):
                spans.append((lead_start, end, " " if lead[:1].isspace() else ""))
                continue
            trimmed = lead
            while True:
                shorter = _DANGLING_LEAD_END.sub("", trimmed).rstrip()
                if shorter == trimmed.rstrip():
                    break
                trimmed = shorter
            trimmed = trimmed.rstrip()
            if trimmed and not trimmed.endswith((".", "!", "?")):
                trimmed += "."
            spans.append((lead_start, end, trimmed + " "))
            continue
        spans.append((start, end, ""))

    if not spans:
        return answer, 0
    repaired = answer
    for start, end, replacement in reversed(spans):
        repaired = repaired[:start] + replacement + repaired[end:]
    repaired = re.sub(r"[ \t]{2,}", " ", repaired)
    return re.sub(r"\n{3,}", "\n\n", repaired), len(spans)


def remove_unrequested_directory_fields(
    answer: str,
    question: str,
    *,
    keep_labels: Iterable[str] = (),
) -> tuple[str, bool]:
    """Remove extra labelled directory fields when only some were requested.

    ``keep_labels`` names exact labels (as they appear in the answer, e.g.
    ``"Office Phone"``) that must never be removed even though the question
    does not name their field - used to protect an explicitly approved
    supplemental contact block (see :func:`build_support_contact_supplement`)
    from being deleted again by this cleanup pass.
    """
    question_text = (question or "").casefold()
    protected = {str(label).strip().casefold() for label in keep_labels if str(label).strip()}
    # Remove only a standalone French orders sentence for a single-field request.
    if (re.search(r"\b(?:téléphone|numéro)\b", question_text)
            and re.search(r"\b(?:bureau|réception)\b", question_text)
            and not re.search(r"\b(?:commandes?|tous|toutes|deux)\b", question_text)):
        focused, count = re.subn(
            r"(?m)^\s*Le numéro pour les commandes(?: en [\w -]+)? est le\s+"
            r"\*{0,2}\+?[\d ()-]+\*{0,2}\.[ \t]*$", "", answer, flags=re.I,
        )
        if count:
            return re.sub(r"\n{3,}", "\n\n", focused).strip(), True
    if re.search(r"\b(all|every|complete)\s+(contact|directory)|\bcontact details?\b", question_text):
        return answer, False

    # A dedicated minimum-order question is not one of the nine directory
    # fields this helper set covers; it keeps its own narrow, unaffected path
    # so an order-size answer still sheds unrelated payment/delivery/hours
    # prose exactly as before.
    if re.search(r"\b(minimum|ordering|order)\b.*\b(order|size)\b|\border\s+size\b", question_text):
        cleaned, replacements = _remove_field_sentences(
            answer or "",
            re.compile(
                r"(?:payment\s+methods?\s+accepted|delivery\s+cost|delivery\s+charge|"
                r"average\s+lead\s+time|business\s+hours?)[^.!?]*(?:[.!?]|$)\s*",
                re.IGNORECASE,
            ),
        )
        return cleaned.strip(), replacements > 0

    requested = _requested_directory_field_set(question_text)
    if not requested:
        # The request is not confidently understood as naming a specific
        # field - do not destructively strip anything based on a guess.
        return answer, False

    allowed_parts = [_FIELD_ALLOWED_LINE_FRAGMENTS[key] for key in requested if key in _FIELD_ALLOWED_LINE_FRAGMENTS]
    allowed = "|".join(allowed_parts) if allowed_parts else r"(?!)"

    labels = (
        r"telephone\s+for\s+orders|telephone(?:\s+office)?|phone(?:\s*\d+)?|"
        r"business\s+hours(?:\s+(?:office|product\s+(?:centre|center)))?|"
        r"office\s*(?:&|and)\s*product\s+center\s+address|address|fax|email|website|"
        r"payment\s+methods?(?:\s+accepted)?|delivery\s+(?:cost|charge|fee)s?|"
        r"(?:average\s+)?(?:delivery|lead)\s+time"
    )

    def _strip_unless_protected(match: re.Match[str]) -> str:
        if match.group("label").strip().casefold() in protected:
            return match.group(0)
        return ""

    # An unrequested label that sits inside a parenthetical aside within a
    # sentence - "...at +223 44 90 05 41 (Business Hours: 08:00 am - 12:00
    # pm)." - must not be handled by the line-wide removal below: cutting
    # from "Business Hours:" to end-of-line leaves the sentence ending on an
    # unmatched "(", which the output validator then flags as an incomplete
    # answer (see tests/unit/test_demo_directory_field_parentheses.py). Remove
    # the unrequested clauses of those asides first (every such label in the
    # paragraph, not just the first - see _strip_unrequested_parenthetical),
    # and let the generic line-start removal below continue to handle every
    # other case exactly as before.
    label_start_pattern = re.compile(
        rf"(?<!\w)(?!{allowed}\b)(?P<label>{labels})\s*:", re.IGNORECASE,
    )
    # Work paragraph-by-paragraph (split on a blank line) rather than one
    # line at a time: a parenthetical aside can itself wrap onto a second
    # physical line ("(Business Hours: 08:00 am\n- 12:00 pm)"), and scanning
    # only within a single line can never find that aside's true closing
    # ")" - see tests/unit/test_demo_directory_field_parentheses.py. Stopping
    # at a blank line keeps an unrelated later record from ever being treated
    # as "inside" an earlier paren. (An aside whose own ")" only appears after
    # a blank line is therefore treated as unclosed - a documented residual.)
    paragraphs = re.split(r"(\n\s*\n)", answer or "")
    paren_changes = 0
    for index, chunk in enumerate(paragraphs):
        if index % 2:
            continue  # the blank-line separator itself; leave untouched
        paragraphs[index], removed = _strip_unrequested_parenthetical(
            chunk, label_start_pattern, protected, labels
        )
        paren_changes += removed
    de_parenthesized = "".join(paragraphs)

    pattern = re.compile(
        rf"(?<!\w)(?!{allowed}\b)(?P<label>{labels})\s*:\s*[^\n]*(?:\n|$)",
        re.IGNORECASE,
    )
    cleaned, replacements = pattern.subn(_strip_unless_protected, de_parenthesized)

    # Only "Label: value" lines are removed. This runs on every answer, and a
    # sentence-level pass cut policy prose ("Returns are free, but the delivery
    # cost is not refunded." became "Returns are free, but.") and split
    # "09.00 am" at its dot (tests/unit/test_demo_directory_prose_preservation.py).
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, replacements > 0 or paren_changes > 0


_PAREN_EVENT_RE = re.compile(r"[()\n]")
_PAREN_CLAUSE_CHAR_RE = re.compile(r"[()\[\];,.!?\n]")
# An abbreviation that introduces what follows ("(e.g. Fax: ...)") is never a
# clause boundary, even before a label: splitting there would leave a bare,
# meaningless "(e.g.)" once the unrequested clause after it is dropped.
_PAREN_INTRODUCER_ABBREVIATION_RE = re.compile(
    r"(?<![\w.])(?:e\.g|i\.e|cf|viz|vs|no)\.$", re.IGNORECASE,
)
# A short token ("Sat.", "ext.", "Mob.", "pm."), a dotted abbreviation
# ("a.m.", "p.m.") or a known longer abbreviation is a continuation of the
# value it sits in, not a sentence end - unless a directory label follows.
_PAREN_SHORT_ABBREVIATION_RE = re.compile(
    r"(?<![\w.])(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"ext|mob|tel|fax|st|rd|ave|dr|mr|mrs|ms|hr|hrs|min|etc|approx|"
    r"(?:[^\W\d_]\.)+[^\W\d_])\.$",
    re.IGNORECASE,
)
# "am."/"pm." (or "a.m."/"p.m.") close an hours value: a capitalised word
# that follows them and is not a continuation word starts new prose.
_PAREN_MERIDIEM_RE = re.compile(r"(?<![\w.])(?:a\.?m|p\.?m)\.$", re.IGNORECASE)
_PAREN_NEXT_WORD_RE = re.compile(r"\s*([^\W\d_][\w'’-]*)")
# Capitalised words that continue an hours/contact value after a "." rather
# than starting new prose: "(Business Hours: 8-12. Saturday 9-1)" or
# "(Business Hours: 8-12. Mobile 0722 123 456)" is one unrequested clause.
_PAREN_CONTINUATION_WORDS = frozenset({
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
    "weekdays", "weekends", "weekend",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "mobile", "mob", "cell", "cellphone", "tel", "telephone", "phone", "whatsapp",
    "ext", "extension", "sms", "hotline", "toll", "fax",
    "closed", "open", "opening", "except", "excluding", "including", "holidays",
    "holiday", "public", "lunch", "noon", "midnight", "am", "pm",
    "and", "or", "to", "until", "till", "through",
})


def _is_paren_clause_boundary(
    text: str, index: int, start: int, stop: int, label_follow_re: re.Pattern[str]
) -> bool:
    """Decide whether the ";", ",", ".", "!" or "?" at ``index`` ends a clause.

    ";" always does. "," only does when another known directory label follows
    (so "08:00 am - 12:00 pm, Monday-Friday" stays one value). "!"/"?" do when
    followed by whitespace or the end of the aside. "." is the ambiguous one -
    "9 a.m. - 5 p.m.", "Sat. 9-1", "ext. 12", "Mob. 0722 ..." all contain a
    "." + space that is not a sentence end - so it only ends a clause when a
    directory label follows it, or when what follows clearly starts new prose
    (a capitalised word that is not a weekday, month or contact/hours
    continuation word) and the "." does not close an abbreviation. When in
    doubt the text stays in the same clause: for an unrequested clause that
    means its whole value is removed rather than a fragment of it kept.
    """
    char = text[index]
    if char == ";":
        return True
    if char in ",\n":
        # A "Label: value" line inside a multi-line aside is its own clause.
        return label_follow_re.match(text, index + 1, stop) is not None
    following = index + 1
    if following < stop and not text[following].isspace():
        return False
    if char != "." or following >= stop:
        return True
    window = max(start, index - 16)
    if _PAREN_INTRODUCER_ABBREVIATION_RE.search(text, window, following):
        return False
    if label_follow_re.match(text, following, stop):
        return True
    if (not _PAREN_MERIDIEM_RE.search(text, window, following)
            and _PAREN_SHORT_ABBREVIATION_RE.search(text, window, following)):
        return False
    word = _PAREN_NEXT_WORD_RE.match(text, following, stop)
    if not word or not word.group(1)[:1].isupper():
        return False
    return word.group(1).rstrip(".").casefold() not in _PAREN_CONTINUATION_WORDS


def _paren_clause_bounds(
    text: str,
    start: int,
    stop: int,
    child_spans: list[tuple[int, int]],
    close_of: dict[int, int],
    label_follow_re: re.Pattern[str],
) -> list[tuple[int, int]]:
    """Split ``text[start:stop]`` (an aside's inner text) into clause ranges.

    Only characters at bracket depth 0 can end a clause. Already-processed
    nested asides (``child_spans``) are skipped as atomic units, a matched
    nested "(...)" or "[...]" raises the depth, and an unmatched stray "("
    (an emoticon, a typo) does not - so it can never stop every later clause
    boundary from being seen. The boundary character stays attached to the
    clause before it, so a dropped clause takes its terminator with it.
    """
    bounds: list[tuple[int, int]] = []
    clause_start = start
    depth = 0
    position = start
    for span_start, span_stop in [*child_spans, (stop, stop)]:
        for found in _PAREN_CLAUSE_CHAR_RE.finditer(text, position, span_start):
            index = found.start()
            char = text[index]
            if char == "(":
                if index in close_of:
                    depth += 1
            elif char == "[":
                depth += 1
            elif char in ")]":
                if depth:
                    depth -= 1
            elif not depth and _is_paren_clause_boundary(text, index, start, stop, label_follow_re):
                bounds.append((clause_start, index + 1))
                clause_start = index + 1
        position = span_stop
    bounds.append((clause_start, stop))
    return bounds


def _rstrip_parts(parts: list[str], chars: str | None) -> None:
    while parts:
        stripped = parts[-1].rstrip(chars)
        if stripped:
            parts[-1] = stripped
            return
        parts.pop()


def _render_paren_span(
    text: str,
    start: int,
    stop: int,
    kids: list[int],
    nodes: list[list],
    results: list[tuple[str | None, bool, str] | None],
) -> str:
    """Render ``text[start:stop]`` with its processed nested asides applied.

    A kept aside is substituted with its rewritten "(...)". A dropped closed
    aside is removed together with the spaces before it; a dropped unclosed
    aside (which ran to the end of its line) also takes trailing whitespace
    and re-terminates the sentence before it with "." when needed. A dropped
    aside that carried one half of a "**" bold pair leaves one "**" at the
    seam so the bold markers stay balanced.
    """
    parts: list[str] = []
    position = start
    seam = ""

    def _append_text(piece: str) -> None:
        nonlocal seam
        if seam:
            # The dropped aside's odd "**" paired with one right outside it:
            # cancel that one instead of writing "****".
            if parts and parts[-1].endswith("**"):
                parts[-1] = parts[-1][:-2]
            elif piece.lstrip(" \t").startswith("**"):
                piece = piece.replace("**", "", 1)
            else:
                parts.append(seam)
            seam = ""
        parts.append(piece)

    for kid in kids:
        opener, kid_stop, _closed = nodes[kid]
        _append_text(text[position:opener])
        kept, closed, bold = results[kid]
        if kept is not None:
            _append_text(kept)
        elif closed:
            _rstrip_parts(parts, " \t")
            seam = bold
        else:
            _rstrip_parts(parts, None)
            seam = bold
            if not parts or parts[-1][-1] not in ".!?":
                _append_text(".")
        position = kid_stop
    _append_text(text[position:stop])
    return "".join(parts)


def _match_parens(text: str) -> dict[int, int]:
    """Map every "(" that has a matching ")" to that ")" in one stack pass."""
    close_of: dict[int, int] = {}
    pending: list[int] = []
    for event in _PAREN_EVENT_RE.finditer(text):
        index = event.start()
        if text[index] == "(":
            pending.append(index)
        elif text[index] == ")" and pending:
            close_of[pending.pop()] = index
    return close_of


def _paren_label_owner(
    open_stack: list[tuple[int, int]],
    line_start: int,
    extended_opener: dict[int, int],
) -> tuple[int, bool] | None:
    """Return ``(opener, closed)`` for the aside a label sits in, or ``None``.

    ``open_stack`` holds the "(" still open at the label, each paired with the
    innermost *matched* "(" at or below it. The innermost matched "(" wins;
    otherwise the nearest unmatched "(" on the label's own line, taking a run
    of directly adjacent unmatched "(((" together. A stray "(" on an earlier
    line, or none at all, leaves the label to the caller's line-wide pass.
    """
    if not open_stack:
        return None
    innermost_matched = open_stack[-1][1]
    if innermost_matched >= 0:
        return innermost_matched, True
    top = open_stack[-1][0]
    if top < line_start:
        return None
    opener = extended_opener.get(top)
    if opener is None:
        level = len(open_stack) - 1
        while level > 0:
            below = open_stack[level - 1][0]
            # Only a run of directly adjacent "((("; a separate stray such
            # as the "(" of "Call :( (" keeps its own text.
            if below < line_start or below + 1 != open_stack[level][0]:
                break
            level -= 1
        opener = open_stack[level][0]
        extended_opener[top] = opener
    return opener, False


def _assign_paren_owners(
    text: str, label_starts: list[int], close_of: dict[int, int]
) -> tuple[dict[int, list[int]], dict[int, bool], list[int]]:
    """Assign each label start to its aside's opener in one linear sweep.

    Also returns the newlines that sit outside every matched "(...)" - the
    places an unclosed aside can end.
    """
    owned: dict[int, list[int]] = {}
    closed_owner: dict[int, bool] = {}
    extended_opener: dict[int, int] = {}
    open_stack: list[tuple[int, int]] = []
    depth0_newlines: list[int] = []
    line_start = 0
    label_index = 0
    events = [event.start() for event in _PAREN_EVENT_RE.finditer(text)]
    events.append(len(text))
    for index in events:
        while label_index < len(label_starts) and label_starts[label_index] < index:
            owner = _paren_label_owner(open_stack, line_start, extended_opener)
            if owner is not None:
                owned.setdefault(owner[0], []).append(label_starts[label_index])
                closed_owner[owner[0]] = owner[1]
            label_index += 1
        char = text[index : index + 1]
        if char == "(":
            innermost = index if index in close_of else (open_stack[-1][1] if open_stack else -1)
            open_stack.append((index, innermost))
        elif char == ")":
            if open_stack:
                open_stack.pop()
        elif char == "\n":
            if not open_stack or open_stack[-1][1] < 0:
                depth0_newlines.append(index)
            line_start = index + 1
    return owned, closed_owner, depth0_newlines


def _unclosed_aside_stop(text: str, opener: int, depth0_newlines: list[int]) -> int:
    """An unclosed aside runs to the end of its line (before any "\\r\\n")."""
    newline = bisect.bisect_right(depth0_newlines, opener)
    if newline >= len(depth0_newlines):
        return len(text)
    stop = depth0_newlines[newline]
    return stop - 1 if stop > opener + 1 and text[stop - 1] == "\r" else stop


def _build_paren_nodes(
    text: str,
    owned: dict[int, list[int]],
    closed_owner: dict[int, bool],
    close_of: dict[int, int],
    depth0_newlines: list[int],
) -> tuple[list[list], list[list[int]], list[list[int]], list[int], list[int]]:
    """Build the nesting tree of affected asides (in opener order)."""
    nodes: list[list] = []
    node_labels: list[list[int]] = []
    for opener in sorted(owned):
        closed = closed_owner[opener]
        stop = close_of[opener] + 1 if closed else _unclosed_aside_stop(text, opener, depth0_newlines)
        nodes.append([opener, stop, closed])
        node_labels.append(owned[opener])

    children: list[list[int]] = [[] for _ in nodes]
    root_children: list[int] = []
    order: list[int] = []
    chain: list[int] = []
    for node_index, (opener, stop, _closed) in enumerate(nodes):
        while chain and nodes[chain[-1]][1] <= opener:
            chain.pop()
        if chain and stop > nodes[chain[-1]][1]:
            continue  # not properly nested; leave that aside untouched
        (children[chain[-1]] if chain else root_children).append(node_index)
        chain.append(node_index)
        order.append(node_index)
    return nodes, node_labels, children, root_children, order


def _append_bold_before_separators(piece: str) -> str:
    body = piece.rstrip(" \t\r\n;,")
    return body + "**" + piece[len(body):]


def _prepend_bold_after_separators(piece: str) -> str:
    body = piece.lstrip(" \t\r\n;,")
    return piece[: len(piece) - len(body)] + "**" + body


def _rewrite_paren_node(
    text: str,
    node_index: int,
    tree: tuple[list[list], list[list[int]], list[list[int]]],
    results: list[tuple[str | None, bool, str] | None],
    close_of: dict[int, int],
    label_follow_re: re.Pattern[str],
) -> None:
    """Drop the clauses of one aside that hold its own unrequested labels.

    Nested affected asides must already have a result. A dropped run of
    clauses that carried an odd number of "**" leaves one "**" at the seam:
    after the kept text when that text has an unclosed bold, otherwise just
    before the next kept clause - never "****".
    """
    nodes, node_labels, children = tree
    opener, stop, closed = nodes[node_index]
    kids = children[node_index]
    bounds = _paren_clause_bounds(
        text,
        opener + 1,
        stop - 1 if closed else stop,
        [(nodes[kid][0], nodes[kid][1]) for kid in kids],
        close_of,
        label_follow_re,
    )
    labels_here = node_labels[node_index]
    kept_parts: list[str] = []
    kept_bold = 0
    pending_bold = 0
    kid_cursor = 0
    for clause_start, clause_stop in bounds:
        kid_end = kid_cursor
        while kid_end < len(kids) and nodes[kids[kid_end]][0] < clause_stop:
            kid_end += 1
        piece = _render_paren_span(text, clause_start, clause_stop, kids[kid_cursor:kid_end], nodes, results)
        kid_cursor = kid_end
        label_at = bisect.bisect_left(labels_here, clause_start)
        if label_at < len(labels_here) and labels_here[label_at] < clause_stop:
            pending_bold ^= piece.count("**") & 1
            continue
        if not piece.strip(" \t\r\n;,"):
            continue
        if pending_bold and kept_bold & 1:
            kept_parts[-1] = _append_bold_before_separators(kept_parts[-1])
            kept_bold += 1
        elif pending_bold:
            piece = _prepend_bold_after_separators(piece)
        pending_bold = 0
        kept_parts.append(piece)
        kept_bold += piece.count("**")
    if pending_bold and kept_parts:
        kept_parts[-1] = _append_bold_before_separators(kept_parts[-1])
        pending_bold = 0

    new_inner = "".join(kept_parts).strip()
    new_inner = re.sub(r"^[;,]\s*", "", new_inner).rstrip(" ;,").strip()
    if new_inner:
        results[node_index] = ("(" + new_inner + ")", closed, "")
        return
    if closed:
        # Take a now-empty enclosing "(...)" ("((Fax: 1))") with it rather
        # than leaving "()" behind.
        while opener > 0 and text[opener - 1] == "(" and close_of.get(opener - 1) == stop:
            opener -= 1
            stop += 1
        nodes[node_index][0], nodes[node_index][1] = opener, stop
    results[node_index] = (None, closed, "**" if pending_bold else "")


def _strip_unrequested_parenthetical(
    text: str, label_start_pattern: re.Pattern[str], protected: set[str], labels: str
) -> tuple[str, int]:
    """Remove only the unrequested labels' own clauses inside "(...)" asides.

    Every unrequested, unprotected label in ``text`` (one paragraph) is
    considered - a label at the start of a line, or one named in
    ``keep_labels``, is skipped rather than ending the scan, so a later
    parenthetical label in the same paragraph is still handled here (the
    caller's end-of-line removal would otherwise cut it to a dangling "(").

    Bracket matching is computed once, in one linear stack pass. A label
    belongs to the innermost "(" before it that has a matching ")" after it;
    if no enclosing "(" is matched, to the nearest unmatched "(" on the same
    line (see :func:`_paren_label_owner`), with the aside running to the end
    of that line. A stray "(" on an earlier line - "Prices (see below",
    "Sorry :(" - therefore never swallows a later, real aside. Labels outside
    any aside are left for the caller's line-wide removal.

    Each affected aside is split into clauses (see
    :func:`_paren_clause_bounds`); only clauses holding one of its own
    unrequested labels are dropped, so a requested field or plain prose in
    the same aside survives. If nothing meaningful survives, the whole aside
    (and the spaces before it, and any now-empty enclosing "(...)") goes; an
    unclosed aside that keeps something is closed with ")". Nested affected
    asides are processed innermost-first.

    Returns the rewritten text and the number of asides changed.
    """
    label_starts = [
        found.start()
        for found in label_start_pattern.finditer(text)
        if found.group("label").strip().casefold() not in protected
    ]
    if not label_starts:
        return text, 0
    close_of = _match_parens(text)
    owned, closed_owner, depth0_newlines = _assign_paren_owners(text, label_starts, close_of)
    if not owned:
        return text, 0
    nodes, node_labels, children, root_children, order = _build_paren_nodes(
        text, owned, closed_owner, close_of, depth0_newlines
    )
    label_follow_re = re.compile(rf"\s*(?:{labels})\s*:", re.IGNORECASE)
    results: list[tuple[str | None, bool, str] | None] = [None] * len(nodes)
    for node_index in reversed(order):
        _rewrite_paren_node(text, node_index, (nodes, node_labels, children), results, close_of, label_follow_re)
    return _render_paren_span(text, 0, len(text), root_children, nodes, results), len(order)


# A minimum-order field value is a figure with at most a currency equivalent,
# such as "0,200CC (7 800DZD)". Anything materially longer is record prose that
# the capture ran into rather than a value worth restoring.
_MAX_RESTORED_VALUE_CHARS = 80

# --- B2: minimum amount to start as an FBO --------------------------------
#
# The old capture used `[^.\n]+`, which stops at the *first* period - so a
# decimal value like "9.440 TND" was truncated to "9" and everything after
# the point was dropped. A period is only a genuine field boundary when it is
# not itself part of a number (i.e. not immediately preceded AND followed by
# a digit, as in "9.440"); `_scan_order_size_value` below walks the source
# character by character to tell the two apart, rather than trying to encode
# that distinction in one regex.
_MINIMUM_WORD = r"min[ui]{1,2}mum|minimun"
_ORDER_SIZE_QUESTION_RE = re.compile(
    rf"\b(?:{_MINIMUM_WORD})\b[^.?!\n]*\b(?:orders?|amount|cc|size)\b"
    rf"|\b(?:orders?|amount|cc)\b[^.?!\n]*\b(?:{_MINIMUM_WORD})\b"
    r"|\border\s+size\b"
    r"|\bhow\s+much\b[^.?!\n]*\b(?:start|begin|ordering|order)\b[^.?!\n]*\bfbo\b"
    r"|\bhow\s+much\b[^.?!\n]*\bneed\b[^.?!\n]*\bstart\b"
    r"|\b(?:smallest|least)\b[^.?!\n]*\border\b",
    re.IGNORECASE,
)
# Rank qualification and the joining/registration fee are distinct fields
# from the minimum order size, even though a question about either can also
# contain the word "minimum" or "CC". Never answer one with the other.
_RANK_QUALIFICATION_RE = re.compile(
    r"\b(?:rank|qualify|qualification|supervisor|assistant\s+supervisor|manager|"
    r"soaring\s+manager|executive)\b",
    re.IGNORECASE,
)
_FEE_ONLY_RE = re.compile(r"\b(?:joining|registration|sign[- ]?up)\s+fee\b", re.IGNORECASE)
_ONGOING_ORDER_QUESTION_RE = re.compile(
    r"\bongoing\b|\bsubsequent\s+orders?\b|\breorder(?:ing)?\b|\brepeat\s+orders?\b|"
    r"after\s+(?:the\s+)?first\s+order|\bcontinu\w*\s+(?:order|purchas\w*)\b",
    re.IGNORECASE,
)
_PREFERRED_CUSTOMER_QUESTION_RE = re.compile(r"\bpreferred\s+customer\b", re.IGNORECASE)
_FBO_ROLE_QUESTION_RE = re.compile(r"\bfbo\b|\bforever\s+business\s+owner\b|\bdistributor\b", re.IGNORECASE)

_FIRST_ORDER_LABEL_RE = re.compile(r"minimum\s+order\s+size\s+fbo\s*[:\-]\s*", re.IGNORECASE)
_ONGOING_ORDER_LABEL_RE = re.compile(
    r"(?:after\s+sponsorship|ongoing\s+(?:minimum\s+)?orders?|subsequent\s+orders?)\s*[:\-]\s*",
    re.IGNORECASE,
)
_ORDER_SIZE_ROLE_HEADING_RE = re.compile(
    r";\s*(?:preferred\s+customer|supervisor|assistant\s+supervisor|manager|home\s+office|fbo)\b",
    re.IGNORECASE,
)


def _is_order_size_question(question_text: str) -> bool:
    """True only for a minimum-order-size request, never a fee or rank one."""
    if _RANK_QUALIFICATION_RE.search(question_text) or _FEE_ONLY_RE.search(question_text):
        return False
    return bool(_ORDER_SIZE_QUESTION_RE.search(question_text))


_ORDER_SIZE_ABBREVIATION_RE = re.compile(
    r"(?<![^\W\d_])(?:excl|incl|approx|min|max|e\.g|i\.e|etc|vs)$",
    re.IGNORECASE,
)


def _scan_order_size_value(source: str, label_pattern: re.Pattern[str]) -> str | None:
    """Return the field value after ``label_pattern``, stopping at its true end.

    A stop is: a newline; a semicolon immediately introducing a different
    role's heading (so a decimal field followed by ``"; Preferred Customer:
    ..."`` never absorbs the next role's text); or a period that is not part
    of a number - i.e. not both immediately preceded and immediately followed
    by a digit, which is what distinguishes a decimal point ("9.440") from an
    ordinary sentence-ending period. Everything else, including an explicit
    approximate-equivalent parenthetical such as "(around 750 MAD)" or
    "(≈€65)", stays part of the value.
    """
    match = label_pattern.search(source or "")
    if not match:
        return None
    text = source
    start = match.end()
    index = start
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\n":
            break
        if char == ".":
            prev_digit = index > 0 and text[index - 1].isdigit()
            next_digit = index + 1 < length and text[index + 1].isdigit()
            # "€50,00 in products excl. VAT and excl. literature." - an
            # abbreviation's period continues the value when more of the same
            # line follows it.
            continues_line = index + 1 < length and text[index + 1] not in "\r\n"
            if not (prev_digit and next_digit) and not (
                continues_line and _ORDER_SIZE_ABBREVIATION_RE.search(text, 0, index)
            ):
                break
        elif char == ";" and _ORDER_SIZE_ROLE_HEADING_RE.match(text, index):
            break
        index += 1
    value = " ".join(text[start:index].split()).strip().rstrip(",;")
    return value or None


def restore_missing_requested_order_size(
    answer: str,
    source_texts: Iterable[str],
    question: str,
) -> tuple[str, bool]:
    """Restore an explicit minimum-order value when another FAQ row was selected.

    Resolves whether the question asks about the first order or an ongoing
    (subsequent) minimum and restores only the matching source field. Never
    restores an FBO-labelled figure into a question that names only the
    Preferred Customer role - the field is a different one and none of the
    recognised source labels here carries a Preferred Customer figure.
    """
    question_text = question or ""
    if not _is_order_size_question(question_text):
        return answer, False
    if (_PREFERRED_CUSTOMER_QUESTION_RE.search(question_text)
            and not _FBO_ROLE_QUESTION_RE.search(question_text)):
        return answer, False

    ongoing = bool(_ONGOING_ORDER_QUESTION_RE.search(question_text))
    label_pattern = _ONGOING_ORDER_LABEL_RE if ongoing else _FIRST_ORDER_LABEL_RE
    field_label = "After sponsorship" if ongoing else "Minimum order size FBO"

    corrected = answer or ""
    for source in source_texts:
        value = _scan_order_size_value(source or "", label_pattern)
        if value is None:
            continue
        # The scan stops at the field's true boundary, but a record with no
        # boundary at all before the next real sentence (no period, no
        # newline) still runs on into unrelated prose. Appending that as a
        # sentence would end the answer mid-phrase - which is how the
        # Algeria answer came to end on the word "the" and be discarded whole
        # by the output validator as structurally incomplete. A field value
        # is short; a paragraph is not this function's to append.
        if len(value) > _MAX_RESTORED_VALUE_CHARS:
            return corrected, False
        if _normalize_for_comparison(value) in _normalize_for_comparison(corrected):
            return corrected, False
        separator = "\n\n" if corrected.strip() else ""
        corrected = f"{corrected.strip()}{separator}{field_label}: {value}."
        return corrected, True
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
        # Deliberately NOT re.DOTALL: `.` must not cross a newline here. A
        # non-greedy `.*?` under DOTALL will happily bridge past an unrelated
        # record boundary to the *nearest* "around/approximately CUR" phrase
        # anywhere later in the string, pairing one country's CC value with
        # another country's currency equivalent. Bounding the match to a
        # single line/sentence keeps it to the record that actually states
        # both the CC value and its equivalent together.
        order_match = re.search(
            r"(?P<cc>\d+(?:[.,]\d+)?\s*CC).*?(?:around|approximately)\s*"
            r"(?P<amount>[\d.,]+)\s*(?P<currency>[A-Z]{3})\b",
            source_text,
            re.IGNORECASE,
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
                flags=re.IGNORECASE,
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


# --- B3: helpful customer-care contact block, without losing the answer ----


def build_support_contact_supplement(
    answer: str,
    approved_fields: dict[str, object],
    recommends_customer_care: bool,
    *,
    hours_requested: bool = False,
) -> tuple[str, list[str]] | None:
    """Return a short supplemental contact block, or ``None``.

    ``approved_fields`` must be the primary approved directory record - the
    same "selected applicable record" contract used elsewhere in this module.
    Returns ``None`` when the answer does not recommend customer care, or
    when no approved contact exists in ``approved_fields`` at all: this is a
    pure echo of already-approved fields and never invents a phone, email,
    website or hours, never fetches from the web, and never exposes a
    private contact.

    At most one phone is kept (the office label and any international
    prefix are preserved exactly as parsed - an order phone is never chosen
    as the supplemental contact), at most one email or approved website, and
    business hours only when ``hours_requested`` is true. The caller is
    responsible for resolving which office is actually responsible for this
    answer (home-market policy vs. a destination's serving office) before
    passing that office's record here; this function does not choose between
    records.
    """
    if not recommends_customer_care or not approved_fields:
        return None

    picked: list[tuple[str, str]] = []
    have_kind: set[str] = set()
    for raw_label, raw_value in approved_fields.items():
        label = str(raw_label).strip()
        value = str(raw_value).strip()
        if not label or not value or _is_self_referential_value(value):
            continue
        canonical = _label_canonical_field(label)
        if canonical == "phone":
            kind = "phone"
        elif canonical in ("email", "website"):
            kind = "contact_point"
        elif canonical == "business_hours" and hours_requested:
            kind = "business_hours"
        else:
            continue
        if kind in have_kind:
            continue
        have_kind.add(kind)
        picked.append((label, value))

    if not picked:
        return None
    block = "\n".join(f"{label}: {value}" for label, value in picked)
    return block, [label for label, _ in picked]


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
