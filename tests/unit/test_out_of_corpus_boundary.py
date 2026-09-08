"""Questions the approved documents can never answer get a straight answer.

Observed live on 2026-09-07: "How much does Forever Aloe Vera Gel cost?"
returned "The approved policy documents currently available do not contain
enough information to answer this question clearly. Please rephrase the
question..." That is neither true nor useful. No rephrasing will help, because
the corpus has never held product pricing.

The prompt already carries a corpus-boundary rule, but evidence approval
rejects these questions before generation runs, so the rule never fires. This
states the same thing on the path that actually executes.
"""

import pytest

from app.evidence import mentions_out_of_corpus_topic
from app.orchestrator.chat_orchestrator import AIOrchestrator


@pytest.fixture
def orchestrator():
    return AIOrchestrator()


def _is_boundary(message: str) -> bool:
    return message.startswith("I don't have product prices")


OUT_OF_CORPUS = [
    "How much does Forever Aloe Vera Gel cost?",
    "What is the price of Aloe Vera Gel?",
    "How much do the products cost?",
    "Is the gel in stock?",
    "Where is my order?",
    "Do you have a catalogue?",
    "What is the order status for my last purchase?",
]

# Answerable from policy or the sponsoring directory. A false match here would
# tell a reader that pricing is unavailable when they asked nothing about it.
IN_CORPUS = [
    "What is the minimum order size for Belgium?",
    "How many Case Credits do I need to reach Supervisor?",
    "How much do I need to order to qualify?",
    "What is the phone number for Forever Uruguay?",
    "How can I become a recognized manager?",
    "When are bonuses paid each month?",
    "Can I return an unopened product, and within what window?",
    "How are foreign FBOs paid their bonus in Kyrgyzstan?",
]


@pytest.mark.parametrize("question", OUT_OF_CORPUS)
def test_an_out_of_corpus_question_gets_the_boundary_answer(orchestrator, question):
    assert _is_boundary(orchestrator._insufficient_evidence_message("en", question)), question


@pytest.mark.parametrize("question", IN_CORPUS)
def test_an_answerable_question_keeps_the_generic_fallback(orchestrator, question):
    assert not _is_boundary(orchestrator._insufficient_evidence_message("en", question)), question


def test_the_boundary_answer_does_not_invite_a_rephrase(orchestrator):
    """The old message asked the reader to try again at something impossible."""
    message = orchestrator._insufficient_evidence_message("en", "What does the gel cost?")

    assert "rephrase" not in message.lower()
    # It must still route them somewhere that can actually help.
    assert "support" in message.lower() or "upline" in message.lower()


def test_the_boundary_answer_never_offers_to_look_a_price_up(orchestrator):
    """The false promise the 2026-09-07 prompt rule was written to remove."""
    message = orchestrator._insufficient_evidence_message("en", "How much is the gel?")

    lowered = message.lower()
    assert "which product" not in lowered
    assert "let me look" not in lowered


def test_no_message_leaves_the_generic_fallback_untouched(orchestrator):
    """Existing callers that pass no question must behave exactly as before."""
    assert not _is_boundary(orchestrator._insufficient_evidence_message("en"))
    assert not _is_boundary(orchestrator._insufficient_evidence_message("en", ""))


def test_terms_are_matched_as_whole_words():
    """A term must not fire inside an unrelated longer word."""
    assert mentions_out_of_corpus_topic("catalogue", "What does it cost?") is True
    # "costs" is a listed term; "costa" is not, and must not match on a prefix.
    assert mentions_out_of_corpus_topic("catalogue", "How do I sponsor in Costa Rica?") is False


def test_an_unknown_topic_matches_nothing():
    assert mentions_out_of_corpus_topic("not-a-configured-topic", "price") is False


def test_a_locale_without_terms_falls_back_to_the_english_list():
    """Readers on non-English markets frequently still ask in English.

    Only English terms ship today. Guessing commerce vocabulary in eleven
    languages risks matching ordinary policy questions, and user-visible copy
    belongs in the wording review.
    """
    assert mentions_out_of_corpus_topic("catalogue", "What is the price?", "de") is True


MARKET_SPECIFIC = [
    "What is the delivery cost for orders in New Zealand?",
    "What is the delivery cost for Sweden?",
    "How much does shipping cost in Germany?",
]


@pytest.mark.parametrize("question", MARKET_SPECIFIC)
def test_a_market_specific_question_keeps_the_ordinary_fallback(orchestrator, question):
    """The boundary answer speaks for the whole corpus and must not over-claim.

    Observed 2026-09-08: "What is the delivery cost for orders in New Zealand?"
    received "those aren't part of the approved documents I work from". The
    sponsoring directory carries per-market commercial detail - minimum order
    sizes are in it and two canary cases prove it - so delivery terms plausibly
    are too, and retrieval may simply have failed.

    An unhelpful "I could not find that" is honest. A confident wrong denial is
    not, and it stops the reader asking again.
    """
    assert not _is_boundary(orchestrator._insufficient_evidence_message("en", question)), question


def test_a_product_price_question_without_a_market_still_gets_the_boundary(orchestrator):
    """The narrowing must not disable the case it was written for."""
    assert _is_boundary(orchestrator._insufficient_evidence_message("en", "How much does Forever Aloe Vera Gel cost?"))
