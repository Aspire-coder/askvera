"""Opt-in final-text/quote binding, NOT semantic, safety or publication approval.

The caller supplies already-authorized versioned evidence. A later semantic
check must assess relevance, entailment, required conditions and answer scope.
No production caller is enabled here.
"""
from dataclasses import dataclass
from typing import Sequence

from app.retrieval.source_binding import EvidenceSource, validate_support


@dataclass(frozen=True)
class BoundClaim:
    text: str
    support: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class BoundFinalAnswer:
    answer: str
    claims: tuple[BoundClaim, ...]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(source_id for claim in self.claims for source_id, _ in claim.support))


def bind_final_answer(payload: object, sources: Sequence[EvidenceSource]) -> BoundFinalAnswer:
    """Require all displayed text to match ordered, individually quote-bound claims.

    No missing text is silently removed, no incorrect citation is relocated, and
    no valid quote is assumed to prove the associated claim. Whitespace wrapping
    alone may differ. Friendly nonfactual text needs a separate reviewed contract;
    it is deliberately not silently exempted by this initial experiment.
    """
    if not isinstance(payload, dict) or set(payload) != {'answer', 'claims'}:
        raise ValueError('Expected answer and claims only')
    answer, claims = payload['answer'], payload['claims']
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
        raise ValueError('Invalid or oversized answer')
    if not isinstance(claims, list) or not 1 <= len(claims) <= 24:
        raise ValueError('Expected one to 24 claims')
    bound = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'text', 'support'}:
            raise ValueError('Expected claim text and support only')
        text = claim['text']
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty or invalid claim text')
        validate_support(claim['support'], sources)
        bound.append(BoundClaim(text, tuple((item['source_id'], item['quote']) for item in claim['support'])))
    if ' '.join(answer.split()) != ' '.join(' '.join(claim.text for claim in bound).split()):
        raise ValueError('Displayed answer differs from ordered claims')
    return BoundFinalAnswer(answer, tuple(bound))


def assemble_bound_segments(payload: object, sources: Sequence[EvidenceSource]) -> BoundFinalAnswer:
    """New opt-in contract: generate text once, then assemble without rewriting.

    Never accepts an independent answer field or repairs the legacy contract.
    This applies to source-grounded factual segments only. Refusals and
    clarification responses remain on their existing controlled paths.
    Source eligibility, semantic support and completeness are caller obligations.
    """
    if not isinstance(payload, dict) or set(payload) != {'segments'}:
        raise ValueError('Expected segments only')
    segments = payload['segments']
    if not isinstance(segments, list) or not 1 <= len(segments) <= 24:
        raise ValueError('Expected one to 24 segments')
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {'text', 'support'}:
            raise ValueError('Expected segment text and support only')
        text = segment['text']
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError('Empty or oversized segment text')
    # Existing support validation and total-length bound remain mandatory.
    answer = ' '.join(segment['text'] for segment in segments)
    return bind_final_answer({'answer': answer, 'claims': segments}, sources)
