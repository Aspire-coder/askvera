"""Tests for the held-out, answer-visible profile evaluator."""

from types import SimpleNamespace

import pytest

from scripts.run_paraphrase_profile_evaluation import (
    ProfileAnswer,
    _conversation_for_case,
    candidate_is_relevant,
    normalize_fixture,
    profile_meets_expectation,
    score_candidates,
    summarize_profile,
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


def test_exact_index_alias_does_not_broaden_to_neighboring_subsections() -> None:
    case = normalize_fixture(
        {
            "cases": [
                _fixture_case(
                    country="CA",
                    relevant_sections=["14.01-a"],
                    relevant_section_ids=["14.01"],
                )
            ]
        }
    )[0]["cases"][0]

    assert candidate_is_relevant(
        {"section_id": "14.01", "country": "CA", "access_scope": "country"}, case
    )
    assert not candidate_is_relevant(
        {"section_id": "14.01-b", "country": "CA", "access_scope": "country"}, case
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


@pytest.mark.parametrize(
    ("target_code", "record_country"),
    (("DZ", "Algeria"), ("NG", "Nigeria"), ("BD", "Bangladesh")),
)
def test_global_directory_ground_truth_matches_configured_country_name(
    target_code: str,
    record_country: str,
) -> None:
    case = normalize_fixture(
        {
            "cases": [
                _fixture_case(
                    country=target_code,
                    scope="global_directory",
                    relevant_sections=[f"directory-{record_country.casefold()}"],
                )
            ]
        }
    )[0]["cases"][0]

    assert candidate_is_relevant(
        {
            "section_id": f"directory-{record_country.casefold()}",
            "record_country": record_country,
            "access_scope": "global",
        },
        case,
    )
    assert not candidate_is_relevant(
        {
            "section_id": "directory-neighbor",
            "record_country": "Niger",
            "access_scope": "global",
        },
        case,
    )


def test_global_directory_ground_truth_can_require_the_governing_directory() -> None:
    case = normalize_fixture(
        {
            "cases": [
                _fixture_case(
                    country="CA",
                    scope="global_directory",
                    target_country="China",
                    relevant_sections=["sponsoring-029-china"],
                    required_source_files=["International-Sponsoring-Directory.pdf"],
                )
            ]
        }
    )[0]["cases"][0]

    assert candidate_is_relevant(
        {
            "section_id": "sponsoring-029-china",
            "source_file": "International-Sponsoring-Directory.pdf",
            "record_country": "China",
            "access_scope": "global",
        },
        case,
    )
    assert not candidate_is_relevant(
        {
            "section_id": "office-019-china",
            "source_file": "International-Office-Directory-April-2026.pdf",
            "record_country": "China",
            "access_scope": "global",
        },
        case,
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


def _profile_answer(*, delivered: bool, selector_success=True, recall_at_20=True):
    return ProfileAnswer(
        answer="A grounded answer." if delivered else "I do not have enough approved information.",
        citations=[{"section": "1.01"}] if delivered else [],
        model_name="test",
        answer_status="delivered" if delivered else "insufficient_evidence",
        failure_layer="" if delivered else "evidence_gate",
        evidence_approved=delivered,
        evidence_reason="test",
        confidence=0.9 if delivered else 0.0,
        candidate_metrics={"recall_at_20": recall_at_20},
        selector_success=selector_success,
        answer_delivered=delivered,
        retrieval_repeats=[],
    )


def test_fixture_normalization_defaults_to_answer_expectation() -> None:
    normalized, _changes = normalize_fixture({"cases": [_fixture_case()]})

    assert normalized["cases"][0]["expected_behavior"] == "answer"


def test_fixture_normalization_defaults_out_of_scope_to_abstention() -> None:
    normalized, _changes = normalize_fixture(
        {"cases": [_fixture_case(scope="out_of_scope", relevant_sections=[])]}
    )

    assert normalized["cases"][0]["expected_behavior"] == "abstain"


def test_fixture_normalization_rejects_unknown_expectation() -> None:
    with pytest.raises(ValueError, match="expected_behavior"):
        normalize_fixture({"cases": [_fixture_case(expected_behavior="guess")]})


def test_must_abstain_case_passes_only_when_no_answer_is_delivered() -> None:
    case = normalize_fixture(
        {"cases": [_fixture_case(expected_behavior="abstain", relevant_sections=[])]}
    )[0]["cases"][0]

    assert profile_meets_expectation(_profile_answer(delivered=False), case)
    assert not profile_meets_expectation(_profile_answer(delivered=True), case)


def test_must_answer_case_requires_relevant_selected_evidence() -> None:
    case = normalize_fixture({"cases": [_fixture_case()]})[0]["cases"][0]

    assert profile_meets_expectation(_profile_answer(delivered=True), case)
    assert not profile_meets_expectation(
        _profile_answer(delivered=True, selector_success=False), case
    )
    assert not profile_meets_expectation(
        _profile_answer(delivered=True, recall_at_20=False), case
    )


def test_must_answer_case_requires_expected_answer_phrase() -> None:
    case = normalize_fixture(
        {
            "expected_answer_any": ["no minimum capital investment"],
            "cases": [_fixture_case()],
        }
    )[0]["cases"][0]

    assert not profile_meets_expectation(_profile_answer(delivered=True), case)
    matching_answer = _profile_answer(delivered=True)
    object.__setattr__(
        matching_answer,
        "answer",
        "The policy states that no minimum capital investment is required.",
    )
    assert profile_meets_expectation(matching_answer, case)


def test_summary_reports_answer_and_abstention_gates_separately() -> None:
    answer = _profile_answer(delivered=True)
    abstention = _profile_answer(delivered=False, selector_success=None, recall_at_20=False)
    rows = [
        {
            "scope": "locale_policy",
            "expected_behavior": "answer",
            "current": answer.__dict__,
            "current_expectation_met": True,
        },
        {
            "scope": "locale_policy",
            "expected_behavior": "abstain",
            "current": abstention.__dict__,
            "current_expectation_met": True,
        },
    ]

    summary = summarize_profile(rows, "current")

    assert summary["must_answer_passes"] == 1
    assert summary["must_abstain_passes"] == 1
    assert summary["expectation_passes"] == 2
    assert summary["retrieval_eligible_cases"] == 1
