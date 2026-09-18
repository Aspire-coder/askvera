"""R03 controls for truthful follow-up retrieval capture, entirely offline."""

from __future__ import annotations

import json
import sys

import pytest

from app.orchestrator.chat_orchestrator import AIOrchestrator
from scripts.evidence_first_v2 import capture_read_only_retrieval as capture


def _history(question: str) -> str:
    return f"user: {question}\nvera: A source-bound answer."


def test_retrieval_only_capture_rejects_any_case_that_needs_stored_turns() -> None:
    pack = {
        "cases": [
            {"id": "first-turn", "question": "What is the office number?", "conversation": []},
            {
                "id": "follow-up-in-any-language",
                "question": "Entä jos hän on johtaja?",
                "conversation": [{"question": "Mitä Suomessa tapahtuu FBO:lle?"}],
            },
        ]
    }

    with pytest.raises(ValueError, match="follow-up-in-any-language"):
        capture._require_runtime_context_capture(pack)


def test_history_anchors_directory_scope_without_replacing_an_unresolved_place() -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"
    follow_up = "And what about FBOs who live there?"
    history = _history(prior)

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-session-a",
    )

    assert "Tanzania" in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"
    assert provenance["prior_user_turn_id"].startswith("history-user-1-")
    assert orchestrator._scope_query(follow_up, query, history) == query
    assert orchestrator._scope_query(follow_up, query, "") == follow_up

    unresolved = "What about the office in Atlantis?"
    isolated_query, isolated_provenance = orchestrator._build_retrieval_query_with_provenance(
        unresolved, history, "r03", session_id="r03-session-b",
    )
    assert isolated_query == unresolved
    assert isolated_provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_configured_language_follow_up_uses_only_its_own_stored_turn() -> None:
    orchestrator = AIOrchestrator()
    prior = "Mitä Suomessa tapahtuu FBO:lle, joka ei ole ostanut mitään 36 kuukauteen?"
    follow_up = (
        "Entä jos hän on Sponsored Recognized Manager ja hänen tiimissään on "
        "ensimmäisen sukupolven Recognized Managereita?"
    )
    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-session",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"
    standalone, standalone_provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, "", "r03", session_id="r03-finnish-new-session",
    )
    assert standalone == follow_up
    assert standalone_provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize("follow_up", ["Entä jos hän on Atlantisissa?", "Entä jos hän on Berliinissä?"])
def test_finnish_anaphoric_follow_up_with_an_unresolved_place_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-unresolved-place",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_finnish_inflected_configured_market_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on Ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-configured-place",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize("follow_up", ["Entä jos hän asuu atlantisissa?", "Entä jos hän asuu berliinissä?"])
def test_lowercase_finnish_anaphoric_unknown_place_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-unknown-place",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_lowercase_finnish_inflected_configured_market_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-configured-place",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_lowercase_configured_finnish_market_after_on_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-configured-after-on",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu nyt ugandassa?",
        "Entä jos hän on nyt ugandassa?",
        "Entä jos hän työskentelee ugandassa?",
        "Entä jos hän asuu, nyt Ugandassa?",
        "Entä jos hän asuu nyt pysyvästi ugandassa?",
        "Entä jos hän asuu edelleen ugandassa?",
        "Entä jos hän asuu ugandassa ja työskentelee siellä?",
        "ENTÄ JOS HÄN ASUU UGANDASSA?",
    ],
)
def test_bounded_finnish_location_phrase_replaces_the_prior_market(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-location-phrase",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän asuu nyt berliinissä?", "Entä jos hän asuu tiimissä?"],
)
def test_unknown_lowercase_finnish_residence_complement_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-location-unknown",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_finnish_configured_market_matching_uses_exact_tokens_not_substrings() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu pseudougandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-substring-control",
    )

    assert query == follow_up
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu ugandassa tai Atlantisissa?",
        "Entä jos hän asuu Atlantisissa tai ugandassa?",
        "Entä jos hän on Kenya mutta asuu ugandassa?",
        "Entä jos hän asuu ugandassa tai kenyassa?",
    ],
)
def test_finnish_competing_market_or_unknown_signal_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-competing-signals",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän työskentelee nyt pysyvästi atlantisissa?",
        "Entä jos hän on nyt pysyvästi tiimissä?",
    ],
)
def test_unsupported_finnish_place_shape_keeps_context_but_is_unresolved(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-unsupported-shape",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän on atlantisissa?",
        "Entä jos hän on nyt atlantisissa?",
        "Entä jos hän työskentelee atlantisissa?",
        "Entä jos hän työskentelee nyt atlantisissa?",
        "Entä jos hän työskentelee tiimissä?",
        "Entä jos hän työskentelee johdossa?",
        "Entä jos hän työskentelee verkostossa?",
    ],
)
def test_ambiguous_lowercase_finnish_complement_keeps_context(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-ambiguous-complement",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän on nyt tiimissä?", "Entä jos hän on nyt johdossa?", "Entä jos hän on nyt verkostossa?"],
)
def test_bounded_finnish_location_phrase_does_not_scan_ordinary_nouns(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-location-noun",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_bounded_finnish_location_phrase_without_history_stays_standalone() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu nyt ugandassa?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, "", "r03", session_id="r03-finnish-location-no-history",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän on tiimissä?", "Entä jos hän on johdossa?", "Entä jos hän on verkostossa?"],
)
def test_lowercase_finnish_noun_after_on_keeps_context(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-lowercase-noun",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_lowercase_finnish_anaphoric_role_follow_up_without_a_place_keeps_context() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on johtaja?"
    prior = "Mitä Suomessa tapahtuu FBO:lle, joka ei ole ostanut mitään 36 kuukauteen?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-lowercase-role",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_audit_mode_rejects_a_multiturn_pack_before_running_the_audit(monkeypatch, tmp_path, capsys) -> None:
    pack = {"cases": [{"id": "stored-turn", "conversation": [{"question": "Earlier question"}]}]}
    monkeypatch.setattr(capture, "_load_pack", lambda *_: (pack, "pack-hash"))
    monkeypatch.setattr(capture, "_audit_active_index_generations", lambda *_: pytest.fail("audit must not run"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["capture", "--output", str(tmp_path / "capture.json"), "--audit-generations-only"],
    )

    assert capture.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "stored-turn" in payload["detail"]
