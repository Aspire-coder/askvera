"""Tests for the held-out, answer-visible profile evaluator."""

from types import SimpleNamespace

import pytest

from scripts.run_paraphrase_profile_evaluation import (
    _conversation_for_case,
    candidate_is_relevant,
    normalize_fixture,
    score_candidates,
)


def _fixture_case(**overrides):
    case = {
        "id": "CASE-1",
        "category": "Policy",
        "question": "How does this work?",
        "country": "UK",
        "language": "en",
        "relevant_sections": ["5"],
        "governing_section": "5",
        "scope": "locale_policy",
        "scoring_rule": "governing",
    }
    case.update(overrides)
    return case


def test_fixture_normalization_maps_uk_to_runtime_gb() -> None:
    normalized, changes = normalize_fixture({"cases": [_fixture_case()]})

    assert normalized["cases"][0]["country"] == "GB"
    assert normalized["cases"][0]["source_country"] == "UK"
    assert any("UK to GB" in change for change in changes)


def test_directory_target_uses_supported_host_market() -> None:
    normalized, _changes = normalize_fixture(
        {"cases": [_fixture_case(country="DZ", scope="global_directory", relevant_sections=["directory-algeria"])]}
    )

    case = normalized["cases"][0]
    assert case["country"] == "CA"
    assert case["target_country"] == "DZ"


def test_global_uk_case_keeps_runtime_gb_as_host_market() -> None:
    normalized, _changes = normalize_fixture(
        {"cases": [_fixture_case(country="UK", scope="global_directory", relevant_sections=["15"])]}
    )

    case = normalized["cases"][0]
    assert case["country"] == "GB"
    assert case["target_country"] == ""


def test_chapter_matching_does_not_confuse_three_with_thirteen() -> None:
    case = normalize_fixture({"cases": [_fixture_case(country="US", relevant_sections=["3"])]})[0]["cases"][0]

    assert candidate_is_relevant(
        {"section_id": "3.02", "country": "US", "access_scope": "country"}, case
    )
    assert not candidate_is_relevant(
        {"section_id": "13.01", "country": "US", "access_scope": "country"}, case
    )


def test_locale_isolation_rejects_same_section_from_wrong_market() -> None:
    case = normalize_fixture({"cases": [_fixture_case(country="IT", language="it", relevant_sections=["5.01"])]})[0]["cases"][0]

    assert candidate_is_relevant(
        {"section_id": "5.01", "country": "IT", "access_scope": "country"}, case
    )
    assert not candidate_is_relevant(
        {"section_id": "5.01", "country": "CA", "access_scope": "country"}, case
    )


def test_global_directory_ground_truth_uses_record_country() -> None:
    case = normalize_fixture(
        {"cases": [_fixture_case(country="NG", scope="global_directory", relevant_sections=["placeholder"])]}
    )[0]["cases"][0]

    assert candidate_is_relevant(
        {"section_id": "p88", "record_country": "NG", "access_scope": "global"}, case
    )
    assert not candidate_is_relevant(
        {"section_id": "p87", "record_country": "NE", "access_scope": "global"}, case
    )


def test_candidate_metrics_report_recall_and_mrr() -> None:
    case = normalize_fixture({"cases": [_fixture_case(country="CA", relevant_sections=["5.01"])]})[0]["cases"][0]
    result = SimpleNamespace(
        metadata={
            "candidate_stages": {
                "fused": [
                    {"section_id": "4.01", "country": "CA", "access_scope": "country"},
                    {"section_id": "5.01-a", "country": "CA", "access_scope": "country"},
                ]
            }
        }
    )

    metrics = score_candidates(result, case)

    assert metrics["recall_at_1"] is False
    assert metrics["recall_at_5"] is True
    assert metrics["first_relevant_rank"] == 2
    assert metrics["reciprocal_rank"] == pytest.approx(0.5)


def test_follow_up_conversation_uses_actual_prior_answer() -> None:
    prior = _fixture_case(id="PRIOR", question="How do I become a Manager?")
    follow_up = _fixture_case(
        id="FOLLOW",
        question="How many points was that again?",
        prior_turn="PRIOR",
    )

    history, question = _conversation_for_case(
        follow_up,
        {"PRIOR": prior, "FOLLOW": follow_up},
        "You need the qualification shown in the approved policy.",
    )

    assert question == follow_up["question"]
    assert "User: How do I become a Manager?" in history
    assert "Assistant: You need the qualification" in history


def test_follow_up_requires_prior_generated_answer() -> None:
    follow_up = _fixture_case(id="FOLLOW", prior_turn="PRIOR")

    with pytest.raises(ValueError, match="requires the generated answer"):
        _conversation_for_case(follow_up, {"PRIOR": _fixture_case(id="PRIOR")})
