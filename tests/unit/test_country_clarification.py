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


# --- access restrictions survive the clarification --------------------------
#
# Clarifying a country must not turn a question the reader may not have
# answered into one they may. These run against approve_evidence now rather
# than waiting for the expansion candidate, and are meant to be reused by it.


from app.evidence import approve_evidence  # noqa: E402
from app.retrieval.models import RetrievalResult, RetrievedDocument  # noqa: E402


def _document(country: str, access_scope: str, language: str = "en") -> RetrievedDocument:
    return RetrievedDocument(
        id="section-1",
        title="Company Policy",
        content="Delivery costs 6EUR and the FBO support fee is 3 EUR per month.",
        source="s3://bucket/doc.pdf",
        country=country,
        language=language,
        score=0.9,
        metadata={"access_scope": access_scope, "section_id": "section-1"},
    )


def _result(*documents: RetrievedDocument) -> RetrievalResult:
    return RetrievalResult(documents=list(documents), citations=[], confidence=0.9)


def test_a_us_session_cannot_reach_belgiums_local_company_policy() -> None:
    """The restriction that must not move."""
    decision = approve_evidence(
        "What is the company policy in Belgium?",
        _result(_document("BE", "country")),
        "US",
        "en",
    )

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_a_us_session_may_use_approved_global_sponsoring_evidence() -> None:
    """Global directory content is approved for any market, and must stay so."""
    decision = approve_evidence(
        "How do I sponsor someone in Belgium?",
        _result(_document("GLOBAL", "global")),
        "US",
        "en",
    )

    assert decision.approved is True


def test_a_clarified_country_does_not_unlock_a_foreign_local_policy() -> None:
    """The control for this change.

    The reader asked for a local company policy in a country that had to be
    clarified. Once "DRC" resolves, the anchored question still names a foreign
    market, and the restriction must apply exactly as if they had named it
    outright.
    """
    orchestrator = _orchestrator()
    history = (
        "user: What is the local company policy in Upper Congo?\n"
        "vera: Which country do you mean?"
    )
    resumed = orchestrator._build_retrieval_query("DRC", history, "cid")

    from services.market_config import find_market_mentions

    assert find_market_mentions(resumed) == {"CD"}, resumed

    decision = approve_evidence(resumed, _result(_document("CD", "country")), "US", "en")

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_the_resumed_question_keeps_the_original_intent() -> None:
    """Anchoring appends rather than replaces, so the question is not lost."""
    orchestrator = _orchestrator()
    history = (
        "user: What is the delivery cost in Upper Congo?\nvera: Which country do you mean?"
    )

    resumed = orchestrator._build_retrieval_query("DRC", history, "cid")

    assert "delivery" in resumed.lower()
    assert "drc" in resumed.lower()


# --- history anchoring depends on a pending clarification ------------------


def test_a_bare_country_does_not_revive_an_unrelated_question() -> None:
    """Anchoring on any history would answer a question the reader never asked.

    "How do I sponsor someone?" ... "DRC" must not become "how do I sponsor
    someone in the DRC". The signal is the previous user message carrying a
    country phrase that could not be resolved - not the assistant's wording,
    which is translated per locale.
    """
    orchestrator = _orchestrator()
    unrelated = "user: How do I sponsor someone?\nvera: Here is how sponsoring works."

    assert orchestrator._needs_history_context("DRC", unrelated) is False
    assert orchestrator._build_retrieval_query("DRC", unrelated, "cid") == "DRC"


def test_a_bare_country_resumes_only_a_pending_clarification() -> None:
    orchestrator = _orchestrator()
    pending = "user: What is the delivery cost in Upper Congo?\nvera: Which country do you mean?"

    assert orchestrator._needs_history_context("DRC", pending) is True


# --- translated copy: failure behaviour ------------------------------------


def test_a_failed_translation_falls_back_to_the_reviewed_english(monkeypatch) -> None:
    """Request-time translation can fail or be slow. It must not take the
    clarification down with it - an untranslated question still asks the
    reader which country they mean, which is better than an error."""
    import app.evidence as evidence

    monkeypatch.setattr(evidence, "localize_reviewed_copy", lambda *a, **k: None)

    text = evidence.localized_conversation_response("country_clarification", "fr")

    assert text and "which country" in text.lower()
