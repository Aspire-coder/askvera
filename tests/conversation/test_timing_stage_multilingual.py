"""Phase 2, Lane C (conversation-quality project): the delivery-vs-approval
timing-stage substitution, reproduced in every language
config/timing_stage_vocabulary.py covers. Deterministic/local proof.

Each case pairs the language's own first-listed delivery and approval cue term
(read from the vocabulary table itself, not retyped here, so the test always
matches what the validator actually uses) with that language's day-unit word,
taken from the existing `_MEASURE_WORDS` day pattern in
numeric_grounding_validator.py (unchanged by this project; reused only to
build a realistic sentence). Sentences are minimal and not idiomatic prose -
their only job is to carry one unambiguous stage cue plus a number and a day
unit next to it, the same shape `_classify_stage` and `_measure` read from a
real answer or source sentence.

Reproduced first for every language: stashing this change (git stash /
git stash pop around app/validation/validators/numeric_grounding_validator.py
and config/timing_stage_vocabulary.py) and re-running each of the ten
substitution scenarios below against `unsupported_numeric_claims` returned []
in every case - none was caught before this change.
"""

from types import SimpleNamespace

import pytest

from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims
from config.timing_stage_vocabulary import TIMING_STAGE_VOCABULARY

# The day-unit word this test uses per language, matching the "day" pattern in
# numeric_grounding_validator._MEASURE_WORDS so that _measure reads the claim
# as a day-count timing figure (never changed here; only reused for the test).
_DAY_WORD = {
    "en": "days",
    "fr": "jours",
    "de": "Tagen",
    "nl": "dagen",
    "it": "giorni",
    "pt": "dias",
    "es": "días",
    "fi": "päivää",
    "no": "dager",
    "sv": "dagar",
}


def _document(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, title="doc", id="doc", country="US", metadata={})


def _claim_texts(answer: str, source: str) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, [_document(source)])]


@pytest.mark.parametrize("language", sorted(_DAY_WORD))
def test_delivery_time_does_not_ground_an_approval_claim(language: str) -> None:
    day_word = _DAY_WORD[language]
    approval_term = TIMING_STAGE_VOCABULARY[language]["approval"][0]
    delivery_term = TIMING_STAGE_VOCABULARY[language]["delivery"][0]
    wrong_answer = f"{approval_term.capitalize()} takes 5 {day_word}."
    source = f"{delivery_term.capitalize()} takes 5 {day_word}."
    assert _claim_texts(wrong_answer, source) == ["5"], (language, wrong_answer, source)


@pytest.mark.parametrize("language", sorted(_DAY_WORD))
def test_delivery_time_grounds_a_delivery_claim(language: str) -> None:
    day_word = _DAY_WORD[language]
    delivery_term = TIMING_STAGE_VOCABULARY[language]["delivery"][0]
    answer = f"{delivery_term.capitalize()} takes 5 {day_word}."
    source = f"{delivery_term.capitalize()} takes 5 {day_word}."
    assert _claim_texts(answer, source) == [], (language, answer, source)
