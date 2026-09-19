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
``utils.directory_fields.parse_directory_fields``) rather than a second,
parallel reading of ``RetrievedDocument.metadata``. "Is the field's value
already in the answer text" reuses
``utils.directory_fields._value_is_present`` (the same fuzzy/digit-aware
comparison ``restore_missing_directory_contacts`` uses), so a value that
survived generation in a slightly different format (spacing, punctuation) is
not wrongly reported as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.response.outcome import OutcomeKind
from app.retrieval.models import RetrievedDocument
from utils.directory_fields import (
    _label_canonical_field,
    _requested_directory_field_set,
    _value_is_present,
    parse_directory_fields,
)

__all__ = [
    "FieldCoverage",
    "RenderCopy",
    "assess_field_coverage",
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
    """
    metadata = getattr(document, "metadata", None) or {}
    directory_fields_value = metadata.get("directory_fields")
    if isinstance(directory_fields_value, dict):
        return directory_fields_value
    return parse_directory_fields(getattr(document, "content", "") or "")


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

    answer_text = answer_text or ""
    answered: set[str] = set()
    unsupported: set[str] = set()
    omitted: set[str] = set()
    for field in requested:
        values = values_by_field.get(field)
        if not values:
            unsupported.add(field)
        elif any(_value_is_present(answer_text, value) for value in values):
            answered.add(field)
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
