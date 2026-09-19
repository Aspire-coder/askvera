"""CX phase 3, Lane 8: compose the final CX-layered ``ChatResponse``.

``docs/conversation-quality/phase3/CX_LANES.md`` fixes the shared outcome
type (``app/response/outcome.py``, Lane 1) and reserves every user-visible
sentence as a message key Lane 4 (``app/response/cx_render.py``) renders.
Lanes 2, 3 and 4 each built one piece -- field-coverage gap notes, contact
escalation, suggested follow-ups, the personal-account note, localization --
as small pure functions. This module is the single place that assembles all
of them, in one fixed, documented order, for one turn.

It is a pure function: no I/O, no model calls, no orchestrator import. The
coordinator (``app/orchestrator/chat_orchestrator.py``, single writer of
that file) is the one that calls it, from the same choke point that already
derives ``ConversationOutcome`` (``_attach_conversation_outcome``) -- see
``docs/conversation-quality/phase3/CX_LANE8_COMPOSE.md`` for the exact call
site and arguments.

Ordering (never applied more than once, never reordered):

1. ``strip_leading_preamble`` -- remove a detected pure-pleasantry opener.
2. Field coverage (``assess_field_coverage``, then this module's own
   ``_partial_answer_gap_note``) -- append ONE localized gap note when a
   requested directory field went unsupported, and promote the outcome to
   ``PARTIAL_ANSWER`` when that happens.
3. ``detect_personal_account_request`` -- append the ``personal_account_limit``
   note (not a refusal; the answer stays) when the question asked about the
   reader's own account state.
4. ``contact_escalation`` -- offer the reviewed public contact for the
   outcome kinds that call for it, already deduplicated against a contact
   the answer recommends or already quotes.
5. ``international_directory_note`` -- name the record's actual market for
   an ``international_directory`` outcome, unless the answer already names
   it.
6. ``suggest_follow_ups`` -- render at most two follow-up suggestions as
   structured ``ChatResponse.suggestions`` items, never appended to the
   answer text.

Steps 1-3 and 5 only ever run for an answer-shaped outcome (``answer``,
``international_directory``, ``partial_answer``); steps 4 and 6 run for the
answer-shaped kinds AND the fallback kinds
(``evidence_missing``/``cross_market_policy``/``dependency_unavailable``/
``personal_account``) whose own reviewed fallback copy is otherwise left
untouched. ``clarification`` and ``safety_refusal`` get no additions at all,
and neither does a response already marked ``guardrail``/``client_action``
or blocked by a governance/PII failure layer -- see
:data:`_SUPPRESSED_RESPONSE_SOURCES` / :data:`_GOVERNANCE_FAILURE_LAYERS`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.response import cx_render
from app.response.contact_completion import contact_escalation
from app.response.models import ChatResponse
from app.response.outcome import ConversationOutcome, OutcomeKind
from app.response.partial_answer import FieldCoverage, assess_field_coverage
from app.response.personal_account import detect_personal_account_request
from app.response.quality import strip_leading_preamble
from app.response.suggestions import suggest_follow_ups
from app.retrieval.models import RetrievedDocument
from utils.directory_fields import _fold_diacritics

__all__ = ["compose_cx_response"]

# Outcome kinds that keep an existing generated answer and may get the full
# preamble/coverage/personal-account/contact/directory-note treatment.
_ANSWER_LIKE_KINDS = frozenset(
    {OutcomeKind.ANSWER, OutcomeKind.INTERNATIONAL_DIRECTORY, OutcomeKind.PARTIAL_ANSWER}
)

# Outcome kinds whose own reviewed fallback copy (config/conversation_routes.json,
# evidence_missing_detail / cross_market_policy_scope / dependency_unavailable /
# personal_account_limit-adjacent fallbacks) is never touched here -- only
# contact escalation and suggestions may still apply on top of it.
_FALLBACK_KINDS = frozenset(
    {
        OutcomeKind.EVIDENCE_MISSING,
        OutcomeKind.CROSS_MARKET_POLICY,
        OutcomeKind.DEPENDENCY_UNAVAILABLE,
        OutcomeKind.PERSONAL_ACCOUNT,
    }
)

# Outcome kinds that get no CX addition at all (CX_LANES.md / this lane's
# brief: "clarification / safety_refusal: return the response unchanged,
# with no additions at all").
_NO_ADDITION_KINDS = frozenset({OutcomeKind.CLARIFICATION, OutcomeKind.SAFETY_REFUSAL})

# A response already marked as a guardrail intervention or a client-action
# shortcut never gets a CX addition layered on top of it -- matches the same
# check chat_orchestrator.py's own choke points use
# (``metadata.get("response_source") in {"guardrail", "client_action"}``).
_SUPPRESSED_RESPONSE_SOURCES = frozenset({"guardrail", "client_action"})

# The failure_layer values app/response/outcome.py's own table
# (_FAILURE_LAYER_KINDS) already classifies as governance or PII blocks --
# every one of these already maps to OutcomeKind.SAFETY_REFUSAL (see that
# module), so this is a belt-and-suspenders check for a caller that passes a
# response whose metadata still carries one of these values even though the
# outcome object itself was built from something else.
_GOVERNANCE_FAILURE_LAYERS = frozenset(
    {"local_guardrail", "risk_policy", "aws_guardrail", "sensitive_pii_input"}
)

# Every message key this module ever fills leaves no ``{name}``-shaped token
# behind (see app/response/cx_render.py's own placeholder pattern) -- this is
# the final, defensive check "a regex check comes before returning" (this
# lane's brief) rather than a second independent implementation of
# cx_render's own pattern.
_UNFILLED_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _blocked(response: ChatResponse) -> bool:
    """True when ``response`` must never get a CX addition layered on top."""
    metadata = response.metadata or {}
    if metadata.get("response_source") in _SUPPRESSED_RESPONSE_SOURCES:
        return True
    if metadata.get("failure_layer") in _GOVERNANCE_FAILURE_LAYERS:
        return True
    return False


def _unchanged(response: ChatResponse) -> tuple[ChatResponse, dict[str, Any]]:
    return response, {"cx_applied": []}


def _append(answer: str, addition: str) -> str:
    """Append ``addition`` as its own paragraph, separated by a blank line."""
    return f"{answer}\n\n{addition}" if answer else addition


def _answer_names_market(answer_text: str, target: str) -> bool:
    """True when ``answer_text`` already names the ``target`` market.

    A plain, deterministic, accent-folded substring check (the same fold
    :mod:`utils.directory_fields` already uses for its own label/value
    matching) against each ``/``-separated segment of ``target`` (a compound
    directory-target name such as ``"Kenya/East Africa"``) -- never a second
    market-alias resolver. Matching any one segment is enough: an answer
    that names "Kenya" already tells the reader which market the contact is
    for, even when the outcome recorded the fuller directory section name.
    """
    if not target:
        return False
    folded_answer = _fold_diacritics(answer_text or "").casefold()
    segments = [segment.strip() for segment in target.split("/") if segment.strip()]
    return any(_fold_diacritics(segment).casefold() in folded_answer for segment in segments)


def _partial_answer_gap_note(
    coverage: FieldCoverage, language: str, *, render: Callable[..., str]
) -> str | None:
    """Render the ``partial_answer_gap`` note with localized field labels.

    ``app/response/partial_answer.py`` (Lane 2) deliberately reports
    ``FieldCoverage.unsupported`` as raw canonical field ids and never joins
    or localizes them itself (see that module's ``partial_answer_note``
    docstring). This lane's own brief assigns that step here: each
    unsupported field id is rendered through its own ``field_label_<id>``
    message key (Lane 4, ``config/conversation_routes.json``), then joined
    with the locale's list separator (:func:`app.response.cx_render.join_list`)
    before filling the ``{fields}`` placeholder -- never a second, ad hoc
    join.
    """
    if not coverage.unsupported:
        return None
    labels = [render(f"field_label_{field}", language) for field in sorted(coverage.unsupported)]
    joined = cx_render.join_list(labels, language)
    return render("partial_answer_gap", language, fields=joined)


def _render_suggestions(
    outcome: ConversationOutcome,
    *,
    language: str,
    country: str,
    topic_supported: Callable[[str, str], bool],
    render: Callable[..., str],
) -> list[dict[str, Any]]:
    keys = suggest_follow_ups(outcome, language=language, country=country, topic_supported=topic_supported)
    return [{"type": "follow_up", "key": key, "text": render(key, language)} for key in keys]


def compose_cx_response(
    response: ChatResponse,
    outcome: ConversationOutcome,
    *,
    question: str,
    language: str,
    country: str,
    evidence_documents: Sequence[RetrievedDocument],
    topic_supported: Callable[[str, str], bool],
    render: Callable[..., str] = cx_render.render,
) -> tuple[ChatResponse, dict[str, Any]]:
    """Apply every CX addition due for this turn's outcome, exactly once each.

    Returns the new ``ChatResponse`` (unchanged citations and every existing
    metadata key except ``metadata["outcome"]`` -- refreshed when field
    coverage promotes the outcome to ``partial_answer`` -- and the new
    ``metadata["cx_applied"]``) plus the same small ``{"cx_applied": [...]}``
    dict, for a caller (or a test) that wants it without re-reading
    ``response.metadata``.

    ``evidence_documents`` must already be this turn's APPROVED evidence
    (e.g. ``EvidenceDecision.evidence`` -- the same value
    ``app/response/partial_answer.py`` itself documents), never re-approved
    or re-ranked here. ``topic_supported`` is the injected predicate
    :func:`app.response.suggestions.suggest_follow_ups` already documents.
    """
    if outcome.kind in _NO_ADDITION_KINDS:
        return _unchanged(response)
    if _blocked(response):
        return _unchanged(response)

    applied: list[str] = []
    answer = response.answer
    current_outcome = outcome

    if outcome.kind in _ANSWER_LIKE_KINDS:
        stripped = strip_leading_preamble(answer, language)
        if stripped != answer:
            applied.append("preamble_stripped")
        answer = stripped

        coverage = assess_field_coverage(
            question=question,
            language=language,
            answer_text=answer,
            evidence_documents=list(evidence_documents),
        )
        note = _partial_answer_gap_note(coverage, language, render=render)
        if note:
            answer = _append(answer, note)
            applied.append("partial_note")
            current_outcome = replace(
                outcome,
                kind=OutcomeKind.PARTIAL_ANSWER,
                fields_answered=coverage.answered,
                fields_unsupported=coverage.unsupported,
            )

        if detect_personal_account_request(question, language):
            answer = _append(answer, render("personal_account_limit", language))
            applied.append("personal_account_limit")

    elif outcome.kind not in _FALLBACK_KINDS:
        # Fail closed: an outcome kind this module does not recognise (a
        # future addition to OutcomeKind not yet wired here) gets no
        # addition at all rather than a guessed-at treatment.
        return _unchanged(response)

    contact_note = contact_escalation(
        current_outcome, country=country, language=language, answer_text=answer, render=render,
    )
    if contact_note:
        answer = _append(answer, contact_note)
        applied.append("contact_offer")

    if outcome.kind == OutcomeKind.INTERNATIONAL_DIRECTORY and outcome.directory_target:
        if not _answer_names_market(answer, outcome.directory_target):
            directory_note = render("international_directory_note", language, country=outcome.directory_target)
            answer = _append(answer, directory_note)
            applied.append("international_directory_note")

    suggestion_items = _render_suggestions(
        current_outcome, language=language, country=country, topic_supported=topic_supported, render=render,
    )
    if suggestion_items:
        applied.append("suggestions")

    if _UNFILLED_PLACEHOLDER_RE.search(answer):
        # Never expected: every render() call above filled its own
        # placeholders. Fail loud rather than deliver broken copy -- the
        # same "must never happen" stance chat_orchestrator.py's own
        # delivered-placeholder check takes.
        raise ValueError(f"cx_compose: unfilled placeholder left in composed answer: {answer!r}")

    metadata = dict(response.metadata or {})
    metadata["outcome"] = current_outcome.to_metadata()
    metadata["cx_applied"] = applied

    new_response = replace(response, answer=answer, suggestions=suggestion_items, metadata=metadata)
    return new_response, {"cx_applied": applied}
