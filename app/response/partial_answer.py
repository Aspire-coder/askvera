"""Partial-answer field coverage: which requested directory fields survived
to the final answer, and the one-time gap note for the fields that did not.

CX phase 3 (docs/conversation-quality/phase3/CX_DESIGN.md, Lane 2 write
scope, docs/conversation-quality/phase3/CX_LANES.md). Pure functions only:
no I/O, no model calls. The coordinator (``app/orchestrator/chat_orchestrator.py``,
single writer) decides *when* to call these; see
``docs/conversation-quality/phase3/CX_LANE2_PARTIAL_AND_QUALITY.md`` for the
recommended hook call sites.

Vocabulary discipline (CX_LANES.md "No duplicated vocabularies"): this module
introduces no new field vocabulary. "Which fields did the question ask for"
is answered by the existing ``utils.directory_fields._requested_directory_field_set``
(13-language table in ``config/directory_field_vocabulary.py``). "Does an
approved evidence document carry a value for a field" reuses the same
label -> canonical-field mapping and label parsing
``app/orchestrator/chat_orchestrator.py`` already uses for its own directory
field repairs (``_support_contact_approved_fields``,
``utils.directory_fields._label_canonical_field``,
``utils.directory_fields.parse_directory_fields``) plus, for the bulleted
fact lines ``parse_directory_fields`` does not parse (payment methods,
delivery cost/time, minimum order -- see
:func:`_label_line_field_values` below), the same
``utils.directory_fields._FIELD_ALLOWED_LINE_FRAGMENTS`` label vocabulary
``remove_unrequested_directory_fields`` already uses -- never a second,
parallel field vocabulary. "Is the field's value already in the answer
text" reuses ``utils.directory_fields._value_is_present`` (the same
fuzzy/digit-aware comparison ``restore_missing_directory_contacts`` uses),
so a value that survived generation in a slightly different format
(spacing, punctuation) is not wrongly reported as unsupported.

Fix (coordinator BLOCKER report, 2026-09-19, wiring `cx/lane2b-20260918`
onto the merged `cx/conversation-experience-20260918`): the real Kenya
directory record states payment methods, delivery cost, delivery time and
minimum order as bulleted "• Label: value" lines
(``app/retrieval/opensearch_sections.py:2424``'s own
``metadata["directory_fields"]`` is built with the same
``parse_directory_fields`` this module already called, and that parser --
see its own docstring and ``_INLINE_FIELD_RE`` -- only recognises the
contact-style fields, never a bullet). Reading only that structured map
therefore marked every such field ``unsupported`` even when the record
plainly stated it, which would have shown the reader "I couldn't find
payment methods" under a correct answer. Two changes fix this:
:func:`_label_line_field_values` reads the bulleted fact lines too, and
:func:`assess_field_coverage` only ever reports a field ``unsupported``
when it can be reasonably sure the field is truly absent -- see that
function's own docstring for the exact safety rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.response.outcome import OutcomeKind, _is_directory_shaped
from app.retrieval.models import RetrievedDocument
from utils.directory_fields import (
    _FIELD_ALLOWED_LINE_FRAGMENTS,
    _label_canonical_field,
    _requested_directory_field_set,
    _value_is_present,
    parse_directory_fields,
)

__all__ = [
    "FieldCoverage",
    "RenderCopy",
    "assess_field_coverage",
    "evidenced_fields",
    "partial_answer_note",
]


@dataclass(frozen=True)
class FieldCoverage:
    """One turn's requested-directory-field coverage, for diagnostics and copy.

    ``requested`` -- canonical field keys the question confidently named
    (see :func:`utils.directory_fields._requested_directory_field_set`).
    ``answered`` -- of those, the ones whose approved value already appears
    in the final answer text.
    ``unsupported`` -- of those, the ones no approved evidence document
    carries a value for at all. These are what :func:`partial_answer_note`
    renders a gap note for.
    ``omitted`` -- of those, the ones an approved document DOES carry a
    value for, but the value never made it into the answer text. This is a
    distinct state from ``unsupported`` on purpose: the answer is not
    missing evidence, generation (or a later edit) dropped a fact that was
    available. The existing contact-completion/supplement path
    (``app/response/contact_completion.py``, Lane 3) may go on to fill an
    ``omitted`` field back in; this module only reports it and never fills
    it itself.
    """

    requested: frozenset[str]
    answered: frozenset[str]
    unsupported: frozenset[str]
    omitted: frozenset[str]


class RenderCopy(Protocol):
    """The localized-copy renderer Lane 4 owns (``app/response/cx_render.py``,
    which does not exist yet in this branch/lane). Callers pass their own
    implementation; tests pass a fake. See
    ``docs/conversation-quality/phase3/CX_LANES.md``'s message-key table:
    ``render`` fills a template's placeholders AFTER localization and joins
    a list placeholder (like ``fields`` below) with the locale's list
    separator -- this module never joins or localizes a field id itself.
    """

    def __call__(self, key: str, language: str, **placeholders: Any) -> str: ...


# The canonical field keys this module can ever place in FieldCoverage, in a
# fixed order used only for documentation -- membership, not this order,
# drives every actual comparison. Copied from the closed set
# utils.directory_fields._label_canonical_field already recognises (its own
# lookup order comment lists the same nine keys); listed again here only so
# the "Lane 4 must provide these field_label_<field> keys" requirement in
# this lane's doc has one place to point at.
KNOWN_FIELD_IDS: tuple[str, ...] = (
    "order_phone",
    "phone",
    "email",
    "website",
    "address",
    "business_hours",
    "payment_methods",
    "delivery_cost",
    "delivery_time",
)

# OutcomeKind values a gap note may ever render for. Reused unchanged from
# app/response/outcome.py (Lane 1) -- see that module's docstring for why
# every lane reads OutcomeKind rather than adding a parallel status field.
_ANSWER_LIKE_OUTCOME_KINDS = frozenset({OutcomeKind.ANSWER, OutcomeKind.PARTIAL_ANSWER})


def _document_field_values(document: RetrievedDocument) -> dict[str, str]:
    """Return one retrieved document's parsed directory label/value map.

    Identical in shape to
    ``app/orchestrator/chat_orchestrator.py``'s own
    ``_support_contact_approved_fields``: prefer the already-structured
    ``metadata["directory_fields"]`` dict retrieval attaches, and fall back
    to parsing the raw content with the same
    :func:`utils.directory_fields.parse_directory_fields` the orchestrator
    uses, rather than inventing a second reader of directory content.

    Covers only the contact-style fields ``parse_directory_fields`` itself
    recognises (see that function's docstring); the bulleted fact lines
    (payment methods, delivery cost/time, minimum order) are a second,
    complementary source -- see :func:`_label_line_field_values`.
    """
    metadata = getattr(document, "metadata", None) or {}
    directory_fields_value = metadata.get("directory_fields")
    if isinstance(directory_fields_value, dict):
        return directory_fields_value
    return parse_directory_fields(getattr(document, "content", "") or "")


# A leading bullet, dash or asterisk marker (plus whitespace) that a directory
# record's fact lines carry ("• Payment methods accepted: ...") but that
# utils.directory_fields.parse_directory_fields's own label recognition does
# not strip before matching a label. Stripped here only for this function's
# own bulleted-line matching -- parse_directory_fields itself is untouched.
_BULLET_PREFIX_RE = re.compile(r"^[\s•*–—-]+")


def _is_directory_label_line(stripped_line: str) -> bool:
    """True when ``stripped_line`` (bullet already removed) opens with any
    known field label -- used only to stop a value's continuation lines at
    the next labeled fact, never to classify a field itself."""
    return any(
        re.match(rf"(?:{fragment})\s*[:#-]", stripped_line, re.IGNORECASE)
        for fragment in _FIELD_ALLOWED_LINE_FRAGMENTS.values()
    )


def _label_line_field_values(content: str) -> dict[str, list[str]]:
    """Extract "Label: value" fact lines a directory record states as bullets.

    ``utils.directory_fields.parse_directory_fields`` only recognises the
    contact-style fields (phone, email, website, address, business hours --
    see its own docstring and ``_INLINE_FIELD_RE``); it never sees a
    bulleted fact like "• Payment methods accepted: Bank deposit, Credit
    Card, Mobile Money Transfer (Mpesa)." -- the real shape
    ``app/retrieval/opensearch_sections.py`` produces for Kenya's record.
    This reuses the SAME label vocabulary
    (``utils.directory_fields._FIELD_ALLOWED_LINE_FRAGMENTS``, the fragments
    ``remove_unrequested_directory_fields`` already matches against) rather
    than inventing a second one, only tolerant of a leading bullet/dash/
    asterisk marker before the label. The value is the text after the
    line's ":"/"#"/"-" separator, plus any following non-blank lines up to
    (but not including) the next labeled line -- a cheap continuation, not a
    full re-implementation of ``parse_directory_fields``'s own multi-line
    value collection.
    """
    lines = (content or "").splitlines()
    values: dict[str, list[str]] = {}
    total = len(lines)
    for index, raw_line in enumerate(lines):
        stripped = _BULLET_PREFIX_RE.sub("", raw_line).strip()
        if not stripped:
            continue
        matched_field: str | None = None
        matched_value = ""
        for field, fragment in _FIELD_ALLOWED_LINE_FRAGMENTS.items():
            match = re.match(rf"(?:{fragment})\s*[:#-]\s*(?P<value>.+)$", stripped, re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group("value").strip()
                break
        if matched_field is None:
            continue
        parts = [matched_value] if matched_value else []
        cursor = index + 1
        while cursor < total:
            continuation = _BULLET_PREFIX_RE.sub("", lines[cursor]).strip()
            if not continuation or _is_directory_label_line(continuation):
                break
            parts.append(continuation)
            cursor += 1
        value = " ".join(part for part in parts if part).strip()
        if value:
            values.setdefault(matched_field, []).append(value)
    return values


def evidenced_fields(evidence_documents) -> frozenset[str]:
    """Canonical directory fields that carry a value in ANY of the documents,
    from both the structured/contact parser and the bulleted fact lines.

    Public so the orchestrator can decide which follow-up topics this turn's
    evidence supports with the same reader as field coverage.
    """
    fields: set[str] = set()
    for document in evidence_documents or ():
        for raw_label, raw_value in _document_field_values(document).items():
            canonical = _label_canonical_field(str(raw_label))
            if canonical and str(raw_value).strip():
                fields.add(canonical)
        fields.update(_label_line_field_values(getattr(document, "content", "") or ""))
    return frozenset(fields)


def _field_mentioned_anywhere(evidence_documents: list[RetrievedDocument], fields: set[str]) -> set[str]:
    """Return the subset of ``fields`` whose label appears ANYWHERE in any
    document's content, even where no clean "Label: value" line could be
    parsed. Used only by the ``unsupported`` safety rule below -- a field
    the record merely mentions (in prose, an odd layout, a run-on line) must
    never be reported as missing outright, only left unclassified as a
    value ("omitted", see :func:`assess_field_coverage`)."""
    remaining = set(fields)
    mentioned: set[str] = set()
    if not remaining:
        return mentioned
    for document in evidence_documents:
        content = getattr(document, "content", "") or ""
        for field in list(remaining):
            fragment = _FIELD_ALLOWED_LINE_FRAGMENTS.get(field)
            if fragment and re.search(fragment, content, re.IGNORECASE):
                mentioned.add(field)
                remaining.discard(field)
        if not remaining:
            break
    return mentioned


def _all_evidence_is_directory_shaped(evidence_documents: list[RetrievedDocument]) -> bool:
    """True only when there IS evidence and every document is directory-shaped.

    Reuses ``app.response.outcome``'s own directory-record predicate (Lane 1)
    rather than a second copy. Deliberately ``False`` for an empty
    ``evidence_documents`` -- "no evidence at all" is an ``evidence_missing``
    outcome elsewhere in the pipeline, never a partial answer, so this
    module must not report an ``unsupported`` field for it either (see the
    safety rule in :func:`assess_field_coverage`).
    """
    if not evidence_documents:
        return False
    return all(
        _is_directory_shaped(getattr(document, "metadata", None) or {})
        for document in evidence_documents
    )


def assess_field_coverage(
    *,
    question: str,
    language: str,
    answer_text: str,
    evidence_documents: list[RetrievedDocument],
) -> FieldCoverage:
    """Classify every requested directory field as answered/unsupported/omitted.

    ``evidence_documents`` must already be the APPROVED evidence for this
    turn (e.g. ``EvidenceDecision.evidence``, or ``RetrievalResult.documents``
    after evidence approval) -- this function does no approval or ranking of
    its own; that decision belongs entirely to the pipeline that already
    made it (``app/evidence.py``).

    When the question does not confidently name any directory field (
    :func:`utils.directory_fields._requested_directory_field_set` returns
    ``None``/empty -- a plain policy question, an ambiguous or compound
    request that function itself declines to guess at), every set here is
    empty: nothing is a "gap" for a question that never asked for a field.

    Field values are read from two complementary sources, merged: the
    contact-style structured map (:func:`_document_field_values`, via
    ``parse_directory_fields``/``metadata["directory_fields"]``) and the
    bulleted fact lines that parser does not see
    (:func:`_label_line_field_values` -- payment methods, delivery cost/
    time, minimum order).

    **Safety rule for ``unsupported``** (coordinator BLOCKER fix,
    2026-09-19): a field is only ever placed in ``unsupported`` when BOTH
    (a) every approved evidence document is directory-shaped
    (:func:`_all_evidence_is_directory_shaped`, reusing
    ``app.response.outcome``'s own predicate), AND (b) the field's label
    does not appear ANYWHERE in any document's content at all
    (:func:`_field_mentioned_anywhere`), not merely in a shape this module's
    two extractors failed to parse into a clean value. Every other case --
    no evidence at all, any non-directory (prose/policy) evidence present,
    or a directory record that merely mentions the field in some
    unparsed shape -- falls back to ``omitted`` instead: never a confident
    "this fact does not exist" claim, only "no value collected for it
    here" (which triggers no partial-answer gap note --
    :func:`partial_answer_note` only reads ``unsupported``). This is
    deliberately the SAFE direction: it can only ever under-report a gap
    the reader should be told about, never fabricate one for a fact the
    evidence actually states -- the exact defect this fix corrects (the
    real Kenya record states payment methods, delivery cost and delivery
    time as bulleted facts; misreading that as "no evidence" would have
    shown the reader "I couldn't find payment methods" under an otherwise
    correct, complete answer).
    """
    requested = _requested_directory_field_set(question, language=language) or set()
    if not requested:
        empty: frozenset[str] = frozenset()
        return FieldCoverage(requested=empty, answered=empty, unsupported=empty, omitted=empty)

    values_by_field: dict[str, list[str]] = {}
    for document in evidence_documents:
        for raw_label, raw_value in _document_field_values(document).items():
            canonical = _label_canonical_field(str(raw_label))
            value = str(raw_value).strip()
            if canonical is None or canonical not in requested or not value:
                continue
            values_by_field.setdefault(canonical, []).append(value)

        content = getattr(document, "content", "") or ""
        for field, field_values in _label_line_field_values(content).items():
            if field not in requested:
                continue
            for value in field_values:
                if value:
                    values_by_field.setdefault(field, []).append(value)

    fields_without_a_value = requested - set(values_by_field)
    directory_only_evidence = _all_evidence_is_directory_shaped(evidence_documents)
    mentioned_without_a_value = (
        _field_mentioned_anywhere(evidence_documents, fields_without_a_value)
        if directory_only_evidence and fields_without_a_value
        else set()
    )

    answer_text = answer_text or ""
    answered: set[str] = set()
    unsupported: set[str] = set()
    omitted: set[str] = set()
    for field in requested:
        values = values_by_field.get(field)
        if values:
            if any(_value_is_present(answer_text, value) for value in values):
                answered.add(field)
            else:
                omitted.add(field)
            continue
        if directory_only_evidence and field not in mentioned_without_a_value:
            unsupported.add(field)
        else:
            omitted.add(field)

    return FieldCoverage(
        requested=frozenset(requested),
        answered=frozenset(answered),
        unsupported=frozenset(unsupported),
        omitted=frozenset(omitted),
    )


def partial_answer_note(
    coverage: FieldCoverage,
    language: str,
    *,
    render: RenderCopy,
    outcome_kind: OutcomeKind | None = None,
) -> str | None:
    """Render the ``partial_answer_gap`` note, or ``None`` when none is due.

    A partial answer NEVER deletes supported content -- this function only
    ever returns text to append once; it never edits ``coverage`` or any
    answer text itself. Returns ``None`` when there is nothing unsupported,
    or when ``outcome_kind`` is given and is not answer-shaped (an
    evidence_missing/clarification/refusal turn never gets a "some details
    are missing" note layered on top of its own copy). Passing no
    ``outcome_kind`` trusts the caller to have already gated the call to an
    answer-shaped turn -- the coordinator's hook (see this lane's doc) does
    that from ``ConversationOutcome.kind``.

    ``fields`` is passed to ``render`` as the RAW sorted field ids (e.g.
    ``["email", "phone"]``), sorted for determinism -- never pre-localized
    or pre-joined here. Field-id -> localized-label lookup and joining with
    the locale's list separator both belong to
    ``app/response/cx_render.py`` (Lane 4); see this lane's doc for the
    exact ``field_label_<field>`` keys Lane 4 must provide.
    """
    if not coverage.unsupported:
        return None
    if outcome_kind is not None and outcome_kind not in _ANSWER_LIKE_OUTCOME_KINDS:
        return None
    return render("partial_answer_gap", language, fields=sorted(coverage.unsupported))
