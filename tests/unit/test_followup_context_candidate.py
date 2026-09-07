import pytest

from app.orchestrator.chat_orchestrator import AIOrchestrator
from scripts.followup_context_candidate import resolve_context


def resolve(current, history):
    return resolve_context(
        current, history,
        is_dependent=AIOrchestrator()._is_context_dependent_message,
    )


def test_latest_country_survives_elaboration_chain():
    history = ["How can I join in Belgium?", "What about Germany?", "Tell me more"]
    result = resolve("Can you elaborate?", history)
    assert result.prior_questions == tuple(history)
    assert result.target_markets == {"DE"}
    assert result.current_question == "Can you elaborate?"


def test_explicit_new_target_overrides_previous_target():
    result = resolve("What about Canada?", ["How can I join in Belgium?", "What about Germany?"])
    assert result.target_markets == {"CA"}


def test_new_standalone_topic_does_not_inherit_unsafe_history():
    question = "What products do I need to purchase?"
    result = resolve(question, ["Guarantee me an income in Belgium"])
    assert result.prior_questions == ()
    assert result.target_markets == set()
    assert result.current_question == question


def test_new_topic_resets_older_country_on_later_followup():
    history = ["How do I join in Belgium?", "What about Germany?", "What is the returns policy?"]
    result = resolve("Does that cover opened products?", history)
    assert result.prior_questions == (history[-1],)
    assert result.target_markets == set()


def test_unsafe_current_question_is_not_discarded():
    question = "Does that guarantee an income?"
    assert resolve(question, ["How do I join?"]).current_question == question


def test_comparison_keeps_both_targets_rather_than_picking_one():
    result = resolve("What about Belgium and Germany?", ["How do I join in Canada?"])
    assert result.target_markets == {"BE", "DE"}


def test_missing_context_does_not_invent_a_country():
    result = resolve("What about that country?", [])
    assert result.prior_questions == ()
    assert result.target_markets == set()


@pytest.mark.parametrize("name,code", [("Deutschland", "DE"), ("Belgique", "BE"), ("Canada", "CA")])
def test_configured_localized_country_names(name, code):
    result = resolve(f"What about {name}?", ["How can I join in Belgium?"])
    assert result.target_markets == {code}


def test_blank_current_question_rejected():
    with pytest.raises(ValueError):
        resolve(" ", ["How can I join?"])


def test_long_dependent_chain_is_rejected_not_silently_truncated():
    with pytest.raises(ValueError, match="experiment limit"):
        resolve("Tell me more", ["Joining in Belgium?"] + ["Tell me more"] * 32)


def test_oversized_anchor_is_rejected_before_retrieval():
    with pytest.raises(ValueError, match="experiment limit"):
        resolve("Tell me more", ["A" * 16_000])


def test_large_unrelated_history_does_not_block_new_topic():
    result = resolve("What is the refund policy?", ["A" * 20_000])
    assert result.prior_questions == ()


def test_oversized_current_question_is_rejected():
    with pytest.raises(ValueError, match="character limit"):
        resolve("A" * 16_001, [])
