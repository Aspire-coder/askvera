"""Regression: a chain of follow-ups must not weld multiple prior turns together.

Confirmed live (correlation id 4cb3d453-9629-492d-81bd-5c1be4ddbf31, US session):

    1. "Can a company or LLC be an FBO instead of a person?"
    2. "Does this policy apply to me if I live in Canada?"
    3. "Is this the whole contract or are there other documents?"

Turn 3's logged ``ranking_query_used`` welded BOTH prior questions onto the
current one, and inherited "canada" from turn 2 even though turn 3 names no
market at all. That pulled in the North America global-directory record
(country: GLOBAL) instead of the US company policy sections, and the answer
was then correctly gutted by numeric grounding repair because those sections
were never retrieved.

Root cause: ``_carry_forward_market_shift`` welded the ENTIRE text of any
later user turn that named a different market than the anchor, regardless of
whether that later turn was a bare market/topic-shift ellipsis ("What about
Germany?") or a fully independent question that merely happened to also
mention a market ("Does this policy apply to me if I live in Canada?"). The
fix restricts the weld to later turns that are themselves a market/topic-shift
ellipsis (``_contains_topic_shift_marker``), so an anchor never compounds more
than one prior user turn's worth of independent question content.

Follow-up review (2026-09-15): ``_contains_topic_shift_marker`` requires a
marker word ("about", "and in", ...), which a marker-less market swap like
"For Gambia?" or bare "Gambia?" does not carry. Those turns welded before the
fix above landed and stopped welding after, silently dropping the earlier
topic from the anchor. ``_is_market_only_ellipsis`` closes that gap: it
qualifies a later turn as a bare market swap whenever removing the market
name (via ``_without_market_names``) leaves nothing but function words, in
any language -- not by matching an English preposition list -- while a
complete question that merely names a market, like the Canada follow-up
above, still keeps its substantive content and stays excluded.
"""

from __future__ import annotations

from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections

FBO_QUESTION = "Can a company or LLC be an FBO instead of a person?"
CANADA_FOLLOW_UP = "Does this policy apply to me if I live in Canada?"
CONTRACT_FOLLOW_UP = "Is this the whole contract or are there other documents?"


def _history(*turns: str) -> str:
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    request_query = orchestrator._build_request_query(message, retrieval_query, history)
    return retrieval_query, request_query


def _targets(query: str, country: str = "US") -> set[str]:
    return opensearch_sections._directory_target_country_names(query, country)


# --- F1/F2: the reproduction ------------------------------------------------------


def test_third_turn_does_not_weld_both_prior_questions_together() -> None:
    """The confirmed production regression: turn 3 must anchor on at most one prior turn."""
    history = _history(FBO_QUESTION, CANADA_FOLLOW_UP)

    retrieval, request = _resolve(CONTRACT_FOLLOW_UP, history)

    # The current question is always present.
    assert CONTRACT_FOLLOW_UP in retrieval
    # Turn 2's own question text -- and the "canada" it inherited -- must not
    # ride along into turn 3's retrieval query.
    assert "canada" not in retrieval.lower()
    assert CANADA_FOLLOW_UP not in retrieval
    assert request == retrieval or CONTRACT_FOLLOW_UP in request
    assert "canada" not in request.lower()
    # At most one prior user turn is welded on: turn 1's question, not both.
    assert retrieval == f"{FBO_QUESTION}\nFollow-up request: {CONTRACT_FOLLOW_UP}"


def test_third_turn_targets_no_directory_market() -> None:
    """Turn 3 names no market and must not reach directory targeting via Canada."""
    history = _history(FBO_QUESTION, CANADA_FOLLOW_UP)
    retrieval, _ = _resolve(CONTRACT_FOLLOW_UP, history)
    assert _targets(retrieval) == set()


# --- F3: a market named in the CURRENT message still reaches directory targeting --


def test_market_named_in_the_current_message_still_targets_that_market() -> None:
    """The Canada follow-up, asked on its own turn, must still target Canada.

    This guards against over-correcting F2: a market named in the message
    being asked NOW must still steer directory targeting, exactly as before.
    """
    retrieval, _ = _resolve(CANADA_FOLLOW_UP, _history(FBO_QUESTION))
    assert "Canada" in retrieval
    assert _targets(retrieval) == {"Canada"}


def test_gambia_after_mali_market_shift_still_welds_the_ellipsis_turn() -> None:
    """W7 (test_demo_followup_target_replacement): a genuine market-shift ellipsis
    two turns back must still be carried forward -- only non-ellipsis full
    questions are excluded from the weld.
    """
    orchestrator = AIOrchestrator()
    belgium = "How do I sponsor someone in Belgium?"
    germany_ellipsis = "What about Germany?"
    history = _history(belgium, germany_ellipsis)

    retrieval = orchestrator._build_retrieval_query("Tell me more.", history, "cid")

    assert _targets(retrieval) == {"Germany"}
    assert "sponsor someone" in retrieval and "Tell me more." in retrieval


# --- F4: locale/policy country filter is untouched --------------------------------


def test_marker_less_market_ellipsis_still_welds_the_prior_topic() -> None:
    """Review finding (2026-09-15): a market swap with no marker word ("For
    Gambia?") must weld the same as a marked one ("What about Gambia?") --
    _contains_topic_shift_marker alone missed it, so the delivery-cost topic
    was dropping out of the anchor and Mali was leaking in alongside it.
    """
    mali_question = "What is the delivery cost in Mali?"
    gambia_ellipsis = "For Gambia?"
    retrieval, _ = _resolve(gambia_ellipsis, _history(mali_question))

    assert "delivery cost" in retrieval
    assert "Mali" not in retrieval
    assert _targets(retrieval) == {"Gambia"}


def test_bare_market_name_ellipsis_still_welds_the_prior_topic() -> None:
    """Same as above for the even sparser "Gambia?" with no leading word at all."""
    mali_question = "What is the delivery cost in Mali?"
    retrieval, _ = _resolve("Gambia?", _history(mali_question))

    assert "delivery cost" in retrieval
    assert "Mali" not in retrieval
    assert _targets(retrieval) == {"Gambia"}


def test_third_turn_after_marker_less_ellipsis_keeps_topic_and_new_market_only() -> None:
    """The topic must survive an extra turn past a marker-less ellipsis:
    Mali topic question -> marker-less "For Gambia?" -> a field follow-up.
    The field follow-up's retrieval query must keep the delivery-cost topic
    and target only Gambia, never Mali.
    """
    history = _history("What is the delivery cost in Mali?", "For Gambia?")
    retrieval, _ = _resolve("What about the lead time?", history)

    assert "delivery cost" in retrieval
    assert "lead time" in retrieval
    assert "Mali" not in retrieval
    assert _targets(retrieval) == {"Gambia"}


def test_marker_less_market_ellipsis_welds_in_german_too() -> None:
    """The remainder test is judged on how little substance is left, not on an
    English preposition list, so a German marker-less ellipsis ("Und Gambia?")
    must weld exactly like the English one.
    """
    mali_question = "What is the delivery cost in Mali?"
    retrieval, _ = _resolve("Und Gambia?", _history(mali_question))

    assert "delivery cost" in retrieval
    assert "Mali" not in retrieval
    assert _targets(retrieval) == {"Gambia"}


def test_market_named_full_question_is_not_treated_as_a_bare_ellipsis() -> None:
    """Boundary check for _is_market_only_ellipsis itself: a complete question
    that happens to name a market ("What is the minimum order in Germany?")
    must not be misread as a bare market swap -- it has substantive content
    left once the market name is removed.
    """
    orchestrator = AIOrchestrator()
    assert orchestrator._is_market_only_ellipsis("What is the minimum order in Germany?") is False
    assert orchestrator._is_market_only_ellipsis("For Gambia?") is True
    assert orchestrator._is_market_only_ellipsis("Gambia?") is True


def test_us_session_policy_question_never_retrieves_another_markets_policy_scope() -> None:
    """A US-session policy question that names a foreign market must still be
    refused at the evidence gate -- the locale/policy country filter this fix
    must not touch. (A follow-up that names no market at all, like
    CONTRACT_FOLLOW_UP above, correctly reaches only the US record instead --
    that is the fix working, not a gap in this guard.)
    """
    from app.evidence import approve_evidence
    from app.retrieval.models import RetrievedDocument, RetrievalResult

    retrieval, _ = _resolve("What about Canada's company policy on returns?", _history(FBO_QUESTION))
    assert "Canada" in retrieval

    documents = [
        RetrievedDocument(
            id="CA:9.01", title="t", content="Returns policy.", source="s3://a", country="CA",
            language="en", score=0.95, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
        RetrievedDocument(
            id="US:9.01", title="t", content="Returns policy.", source="s3://b", country="US",
            language="en", score=0.9, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
    ]
    decision = approve_evidence(retrieval, RetrievalResult(documents=documents, citations=[], confidence=0.9), "US", "en")
    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
