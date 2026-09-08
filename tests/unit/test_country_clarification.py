"""Asking which country, instead of answering for the wrong one.

The matcher stops "Upper Congo" resolving to the Republic of Congo. That made
it return nothing - and nothing was indistinguishable from "the reader named no
country", so the request fell through to retrieval on the SESSION's country. A
US reader asking about Upper Congo was answered from US policy: the same
wrong-country answer, reached by a different route.

These cover the decision points deterministically. They do not establish what a
delivered answer looks like; that needs the bounded end-to-end run.
"""

from __future__ import annotations

import pytest

from app.orchestrator.chat_orchestrator import AIOrchestrator
from utils.validators import ChatRequest


def _request(message: str, country: str = "US") -> ChatRequest:
    return ChatRequest(
        message=message, sessionId="s", country=country, language="en", role="active_distributor"
    )


def _orchestrator() -> AIOrchestrator:
    return AIOrchestrator()


# --- clarify rather than substitute ----------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is the delivery cost in Upper Congo?",
        "Upper Congo delivery?",
        "What are the charges in Mainland China?",
    ],
)
def test_an_unresolved_country_is_asked_about_not_answered(question: str) -> None:
    """The control: a US session must not answer these from US policy."""
    response = _orchestrator()._early_conversation_response(question, _request(question), "cid")

    assert response is not None, "the request would have fallen through to session-country retrieval"
    assert (response.metadata or {}).get("response_source") == "country_clarification"
    assert "which country" in response.answer.lower()


def test_the_clarification_names_the_phrase_it_could_not_resolve() -> None:
    question = "What is the delivery cost in Upper Congo?"

    response = _orchestrator()._early_conversation_response(question, _request(question), "cid")

    assert "upper congo" in response.answer.lower()
    assert (response.metadata or {}).get("unresolved_market_mention") == "upper congo"


def test_the_clarification_never_names_the_country_inside_the_phrase() -> None:
    """"Upper Congo" contains "Congo" and may mean either Congo. Suggesting one
    would be the substitution this exists to prevent, wearing a question mark."""
    question = "What is the delivery cost in Upper Congo?"

    answer = _orchestrator()._early_conversation_response(question, _request(question), "cid").answer

    assert "Republic of Congo" not in answer
    assert "United States" not in answer


def test_clarification_happens_before_any_country_specific_answer() -> None:
    """It must precede the exact cache, the semantic cache and retrieval.

    A cached answer is as country-specific as a fresh one, so clarifying after
    a cache hit would serve the wrong country's answer from memory.
    """
    import inspect

    source = inspect.getsource(AIOrchestrator._handle_scrubbed_chat)
    early = source.index("_early_conversation_response")

    for later in ("_cached_response", "self.retriever.retrieve"):
        assert early < source.index(later), f"{later} runs before clarification"


# --- ordinary questions are unaffected -------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What are the delivery charges?",
        "How do I sponsor someone?",
        "What is the minimum order size?",
    ],
)
def test_a_question_naming_no_country_is_not_interrupted(question: str) -> None:
    """These must keep using the session's own market, as before."""
    response = _orchestrator()._early_conversation_response(question, _request(question), "cid")

    assert response is None


@pytest.mark.parametrize(
    "question",
    ["What is the delivery cost in Belgium?", "Delivery cost in DR Congo?", "Charges in Congo?"],
)
def test_a_question_naming_a_known_country_is_not_interrupted(question: str) -> None:
    response = _orchestrator()._early_conversation_response(question, _request(question), "cid")

    assert response is None


# --- the reply resumes the original question -------------------------------


@pytest.mark.parametrize("reply", ["DRC", "the DRC", "Democratic Republic of the Congo"])
def test_a_bare_country_reply_resumes_the_original_question(reply: str) -> None:
    """Otherwise the reader must retype everything after being asked to clarify."""
    orchestrator = _orchestrator()
    history = "user: What is the delivery cost in Upper Congo?\nvera: Which country do you mean?"

    assert orchestrator._needs_history_context(reply, history) is True
    query = orchestrator._build_retrieval_query(reply, history, "cid")
    assert "delivery" in query.lower(), query


def test_a_country_reply_resolves_the_market_it_names() -> None:
    from services.market_config import find_market_mentions

    assert find_market_mentions("DRC") == {"CD"}


def test_a_follow_up_question_keeps_its_existing_handling() -> None:
    """"And in Uganda?" is a question, and is deliberately left to the
    follow-up markers - this change must not quietly widen when history is
    inherited."""
    orchestrator = _orchestrator()
    history = "user: What are the office hours in Kenya?\nvera: Monday to Friday."

    assert orchestrator._needs_history_context("And in Uganda?", history) is False


def test_a_country_name_with_no_history_is_not_treated_as_a_reply() -> None:
    assert _orchestrator()._needs_history_context("DRC", "") is False


# --- a governance gap, recorded rather than assumed away --------------------


def test_the_clarification_copy_is_reviewed_for_english_only() -> None:
    """Eleven other locales fall back to a live translation of the English.

    localized_conversation_response returns reviewed copy when a locale has it,
    and otherwise translates the English at request time. That is right for a
    reader, who needs an answer in their language either way, and it means this
    wording is not reviewed for those markets - the same gap already recorded
    for insufficient_evidence copy.

    Whether an unreviewed translation is acceptable for approved policy
    communication is a governance decision, not a technical one. Recorded here
    so shipping this does not quietly assume the answer.
    """
    import json
    from pathlib import Path

    routes = json.loads(
        Path("config/conversation_routes.json").read_text(encoding="utf-8")
    )["locales"]
    reviewed = [
        locale
        for locale, value in routes.items()
        if "country_clarification" in (value.get("responses") or {})
    ]

    assert reviewed == ["en"]
    assert len(routes) > 1, "other locales exist and will receive translated copy"
