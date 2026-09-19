from types import SimpleNamespace

from app.evidence import approve_evidence
from app.orchestrator.chat_orchestrator import AIOrchestrator, CROSS_MARKET_POLICY_SCOPE_RESPONSE
from app.retrieval.models import RetrievalResult


def _orchestrator_stub():
    return SimpleNamespace(
        _insufficient_evidence_message=lambda language, message="", country="": (
            AIOrchestrator._insufficient_evidence_message(None, language, message, country)
        )
    )


# Updated 2026-09-18 (Phase 3, Lane 4): config/conversation_routes.json now
# carries a reviewed "cross_market_policy_scope" key for every locale (the
# CX_LANES.md message-key table; docs/conversation-quality/phase3/CX_LANES.md),
# which is the same key name `_cross_market_scope_message`
# (app/orchestrator/chat_orchestrator.py) already looked up via
# `configured_conversation_response` before this key existed anywhere. Once
# the key exists, `configured_conversation_response` returns it as
# reviewed-for-locale for every one of the 12 route locales (including "en"),
# so `_cross_market_scope_message` now returns that reviewed copy instead of
# falling through to `CROSS_MARKET_POLICY_SCOPE_RESPONSE` (English) or
# `_insufficient_evidence_message` (every other route locale) as it did when
# the key was absent. This is the intended integration point per CX_LANES.md
# ("cross_market_policy_scope | {country} | outcome cross_market_policy");
# `CROSS_MARKET_POLICY_SCOPE_RESPONSE` itself is untouched and still used as
# the ultimate fallback for a configured language outside the 12 route
# locales with no reviewed copy at all.
#
# Known gap, left for the coordinator's orchestrator wiring (outside Lane 4's
# write scope, which is config/conversation_routes.json and
# app/response/cx_render.py only): `_cross_market_scope_message` calls
# `configured_conversation_response` directly rather than
# `app.response.cx_render.render`, so the returned copy's "{country}"
# placeholder is not filled here. The reviewed copy is still correct,
# reviewed English/French text with a literal, unfilled "{country}" token
# until that wiring is updated to call `cx_render.render(...,
# country=country)` instead.
EN_CROSS_MARKET_POLICY_SCOPE = (
    "I can only answer using the policy documents approved for your own "
    "market. For {country}'s policy specifically, please check with a local "
    "Forever Living office or Customer Care."
)
FR_CROSS_MARKET_POLICY_SCOPE = (
    "Je ne peux répondre qu'à partir des documents de politique "
    "approuvés pour votre propre marché. Pour la politique de "
    "{country} en particulier, veuillez contacter un bureau local Forever "
    "Living ou le service Client."
)


def test_foreign_policy_is_refused_with_scope_explanation_in_english() -> None:
    decision = approve_evidence(
        "What is the company policy on returns in Belgium?",
        RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={}),
        country="US",
        language="en",
    )

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    # No single other market named: the generic English copy, unchanged.
    assert AIOrchestrator._cross_market_scope_message(_orchestrator_stub(), "en") == (
        CROSS_MARKET_POLICY_SCOPE_RESPONSE
    )
    # One other market named: the reviewed copy, naming it, never a placeholder.
    named = AIOrchestrator._cross_market_scope_message(
        _orchestrator_stub(), "en", "What is the company policy on returns in Belgium?", "US"
    )
    assert named == EN_CROSS_MARKET_POLICY_SCOPE.replace("{country}", "Belgium")
    assert "{" not in named


def test_non_english_scope_refusal_now_uses_reviewed_locale_copy() -> None:
    message = AIOrchestrator._cross_market_scope_message(_orchestrator_stub(), "fr", "Belgium")

    assert "only available to readers" not in message
    assert message == FR_CROSS_MARKET_POLICY_SCOPE.replace("{country}", "Belgium")
    assert "{" not in message
    assert message != AIOrchestrator._insufficient_evidence_message(None, "fr", "Belgium")


def test_session_market_and_multiple_markets_never_fill_the_name() -> None:
    # The session market itself is not "another market"; two named markets are
    # ambiguous. Both keep the pre-CX behaviour and never deliver a placeholder.
    own = AIOrchestrator._cross_market_scope_message(_orchestrator_stub(), "en", "Belgium returns?", "BE")
    two = AIOrchestrator._cross_market_scope_message(
        _orchestrator_stub(), "en", "Belgium or Sweden returns?", "US"
    )
    assert own == two == CROSS_MARKET_POLICY_SCOPE_RESPONSE
