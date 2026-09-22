"""Structured evidence contract for policy-grounded model answers.

The model is a writer, not a source of policy truth.  When enabled, this
module requires it to identify the approved retrieval sections supporting its
answer before the answer can be released to the user.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

from app.retrieval.models import RetrievedDocument
from utils.sentence_spans import split_sentences


@dataclass(frozen=True)
class EvidenceContractResult:
    """A parsed, validated model answer tied to approved evidence."""

    valid: bool
    answer: str = ""
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""


def parse_evidence_contract(text: str, documents: list[RetrievedDocument]) -> EvidenceContractResult:
    """Validate a compact JSON answer against the retrieval evidence supplied."""
    payload = _parse_json_object(text)
    if payload is None:
        return EvidenceContractResult(False, reason="invalid_json")

    status = str(payload.get("status") or "").strip().lower()
    raw_answer = payload.get("answer")
    if not isinstance(raw_answer, str):
        return EvidenceContractResult(False, reason="invalid_answer_type")
    answer = raw_answer.strip()
    if status != "approved" or not answer:
        return EvidenceContractResult(False, reason="answer_not_approved")

    allowed_ids = {document.id for document in documents if document.id}
    evidence_ids = _string_ids(payload.get("evidence_ids"))
    if not evidence_ids:
        return EvidenceContractResult(False, reason="missing_evidence_ids")
    if not set(evidence_ids).issubset(allowed_ids):
        return EvidenceContractResult(False, reason="unknown_evidence_id")

    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return EvidenceContractResult(False, reason="missing_claims")
    claim_error = _claim_schema_error(claims, evidence_ids)
    if claim_error:
        return EvidenceContractResult(False, reason=claim_error)

    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        return EvidenceContractResult(False, reason="missing_coverage_check")
    omitted_material_facts = coverage.get("omitted_material_facts")
    if coverage.get("complete") is not True:
        return EvidenceContractResult(False, reason="incomplete_answer")
    if not isinstance(omitted_material_facts, list):
        return EvidenceContractResult(False, reason="invalid_coverage_check")
    if any(str(item or "").strip() for item in omitted_material_facts):
        return EvidenceContractResult(False, reason="incomplete_answer")

    # A claim list about different text cannot justify the displayed answer.
    # This is a structural check, not proof of entailment.
    normalized_answer = " ".join(answer.split())
    if any(" ".join(claim["text"].split()) not in normalized_answer for claim in claims):
        return EvidenceContractResult(False, reason="claim_not_in_answer")

    # ...and the reverse direction, which was missing. The check above only
    # required every listed claim to appear in the answer, and said nothing
    # about answer text no claim covers. A model could list one accurate,
    # well-supported definition, append an unsupported sentence beside it, and
    # the contract accepted the pair.
    if _uncovered_sentence(answer, claims):
        return EvidenceContractResult(False, reason="answer_contains_unsupported_claim")

    return EvidenceContractResult(True, answer=answer, evidence_ids=tuple(evidence_ids))


# Share of a sentence's content tokens that must also appear in the claim list
# for that sentence to count as covered. Deliberately not 1.0: a model
# legitimately rephrases and joins claims when writing prose, and demanding
# exact reuse would reject sound answers.
#
# This number is a starting point, not a measured one. It wants tuning against
# a corpus of real approved answers before this contract is enabled in
# production, or it will reject good answers as readily as bad ones.
SENTENCE_COVERAGE_THRESHOLD = 0.5

# A sentence with fewer content tokens than this asserts too little to judge.
# "This applies to all FBOs." carries almost nothing, and scoring it on overlap
# produces noise rather than signal.
MIN_CHECKED_CONTENT_TOKENS = 4

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STRUCTURAL_LINE_RE = re.compile(r"[#>*\-\d.)\s]+")


def _content_tokens(text: str) -> set[str]:
    """Case-folded tokens worth comparing.

    Tokens of one or two characters are dropped as noise, except digits: a bare
    number is exactly the kind of claim that must be supported, and dropping
    "8" or "10" would let an invented figure through unnoticed.

    No stop-word list, deliberately. This module runs on every supported
    language, and an English word list would silently weaken the check
    everywhere else.
    """
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(text.casefold()):
        token = match.group(0)
        if len(token) > 2 or token.isdigit():
            tokens.add(token)
    return tokens


def _is_structural_line(line: str) -> bool:
    """True for markdown scaffolding that asserts nothing on its own."""
    stripped = line.strip()
    if not stripped:
        return True
    # A heading or a bare list bullet is a label, not a policy statement.
    return stripped.startswith("#") or bool(_STRUCTURAL_LINE_RE.fullmatch(stripped))


def _iter_checkable_sentences(
    text: str, min_tokens: int = MIN_CHECKED_CONTENT_TOKENS
) -> Iterator[tuple[str, set[str]]]:
    """Yield each sentence-like segment of ``text`` worth judging, with its tokens.

    Shared by ``_uncovered_sentence`` (checked against a declared claim list)
    and ``unsupported_answer_sentences`` (checked against retrieved evidence
    text directly) so both apply the same structural/length filtering.
    ``min_tokens`` lets a caller raise the bar above ``MIN_CHECKED_CONTENT_TOKENS``;
    see ``unsupported_answer_sentences`` for why the whole-answer check needs a
    higher one than a declared claim list does.
    """
    # utils.sentence_spans instead of a bare "[.!?]\\s" split: a decimal, an
    # abbreviation, an initial, an email or a URL inside a sentence must not
    # become its own "sentence" here, or a real claim is judged one broken
    # fragment at a time and rejected for coverage a whole sentence would
    # have had.
    for sentence in split_sentences(text):
        if _is_structural_line(sentence):
            continue
        tokens = _content_tokens(sentence)
        if len(tokens) < min_tokens:
            continue
        yield sentence, tokens


def _coverage_ratio(tokens: set[str], coverage_tokens: set[str]) -> float:
    """Share of ``tokens`` also present in ``coverage_tokens``."""
    if not tokens:
        return 1.0
    return len(tokens & coverage_tokens) / len(tokens)


def _uncovered_sentence(answer: str, claims: list) -> str:
    """Return the first answer sentence no claim supports, or an empty string."""
    claim_tokens: set[str] = set()
    for claim in claims:
        claim_tokens |= _content_tokens(str(claim.get("text") or ""))

    for sentence, tokens in _iter_checkable_sentences(answer):
        if _coverage_ratio(tokens, claim_tokens) < SENTENCE_COVERAGE_THRESHOLD:
            return sentence
    return ""


# A declared claim list is written by the model to justify one specific
# answer, so every entry in it is already a factual assertion - a short one
# still deserves scrutiny. Checking a whole delivered answer against raw
# evidence tokens is a blunter instrument: an answer legitimately contains
# generic connective or service sentences ("You are welcome to place an order
# directly. Please contact customer care for further help.") that share
# little vocabulary with any evidence on any topic, precisely because they
# assert nothing evidence-specific. A short sentence there is noise, not a
# claim, and flagging it would fail the turns this check must leave alone
# (see HistoryGroundingValidator). Requiring more distinct content tokens
# before judging a sentence lets a real multi-clause factual claim - the kind
# that carried section citations and quoted contract language in the
# reproduced failure - through the filter while generic short remarks stay
# unexamined.
MIN_CHECKED_ANSWER_SENTENCE_TOKENS = 8


def unsupported_answer_sentences(
    answer: str, evidence_texts: list[str], min_tokens: int = MIN_CHECKED_ANSWER_SENTENCE_TOKENS
) -> list[str]:
    """Return delivered-answer sentences this turn's retrieved evidence text does not cover.

    Same sentence-coverage test as ``_uncovered_sentence``, but compared
    directly against the retrieved evidence's own tokens rather than a
    model-declared claim list. History is deliberately excluded from
    ``evidence_texts`` by every caller: the conversation is context for
    interpreting the question, never a source of facts (see
    ``FOLLOWUP_PROMPT`` in ``app/prompts/templates.py``), so a fact that only
    history states and this turn's evidence does not is exactly what this
    catches.
    """
    evidence_tokens: set[str] = set()
    for text in evidence_texts:
        evidence_tokens |= _content_tokens(text or "")
    return [
        sentence
        for sentence, tokens in _iter_checkable_sentences(answer, min_tokens)
        if _coverage_ratio(tokens, evidence_tokens) < SENTENCE_COVERAGE_THRESHOLD
    ]


def _claim_schema_error(claims: list, evidence_ids: list[str]) -> str:
    for claim in claims:
        if not isinstance(claim, dict):
            return "invalid_claim"
        if not isinstance(claim.get("text"), str):
            return "invalid_claim_text_type"
        claim_evidence_ids = _string_ids(claim.get("evidence_ids"))
        if not claim["text"].strip() or not claim_evidence_ids:
            return "claim_missing_support"
        if not set(claim_evidence_ids).issubset(set(evidence_ids)):
            return "claim_uses_unlisted_evidence"
    return ""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Accept a JSON object even when a provider adds a small amount of framing."""
    candidate = (text or "").strip()
    if not candidate:
        return None
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = candidate[start : end + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _string_ids(value: object) -> list[str]:
    """Return unique non-empty evidence identifiers in their declared order."""
    if not isinstance(value, list):
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return []
    ids: list[str] = []
    for item in value:
        identifier = str(item or "").strip()
        if identifier and identifier not in ids:
            ids.append(identifier)
    return ids
