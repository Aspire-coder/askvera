from scripts.analyze_profile_failures import analyze_report, classify_profile, repeat_is_stable


def _profile(**overrides):
    profile = {
        "answer_status": "answered",
        "failure_layer": "",
        "candidate_metrics": {
            "candidate_count": 20,
            "recall_at_20": True,
            "first_relevant_rank": 2,
        },
        "selector_success": True,
        "evidence_approved": True,
        "answer_delivered": True,
        "retrieval_repeats": [],
    }
    profile.update(overrides)
    return profile


def test_classification_stops_at_the_earliest_failed_layer() -> None:
    assert classify_profile(_profile(candidate_metrics={"candidate_count": 0})) == "no_candidates"
    assert (
        classify_profile(
            _profile(candidate_metrics={"candidate_count": 20, "recall_at_20": False})
        )
        == "relevant_candidate_missing_top20"
    )
    assert classify_profile(_profile(selector_success=False)) == "selector_miss"
    assert classify_profile(_profile(evidence_approved=False)) == "evidence_gate_rejection"
    assert (
        classify_profile(_profile(answer_delivered=False, failure_layer="numeric_validator"))
        == "numeric_validator"
    )


def test_repeat_stability_uses_selected_sections_and_relevant_rank() -> None:
    stable_repeat = {
        "selector_success": True,
        "candidate_metrics": {"first_relevant_rank": 1},
        "document_sections": ["4.01"],
    }
    assert repeat_is_stable(_profile(retrieval_repeats=[stable_repeat, stable_repeat])) is True

    changed_repeat = {
        **stable_repeat,
        "document_sections": ["8.04-definition-2"],
    }
    assert repeat_is_stable(_profile(retrieval_repeats=[stable_repeat, changed_repeat])) is False


def test_abstention_cases_are_not_reported_as_retrieval_failures() -> None:
    assert classify_profile({"answer_delivered": False}, "abstain") == "expected_abstention"
    assert classify_profile({"answer_delivered": True}, "abstain") == "unsafe_delivery"


def test_report_analysis_keeps_current_and_candidate_separate() -> None:
    report = {
        "manifest": {"retrieval_repeats": 3},
        "cases": [
            {
                "id": "CASE-1",
                "category": "Policy",
                "country": "CA",
                "language": "en",
                "question": "Question",
                "current": _profile(selector_success=False),
                "candidate": _profile(),
            }
        ],
    }

    analysis = analyze_report(report)

    assert analysis["counts"]["current"] == {"selector_miss": 1}
    assert analysis["counts"]["candidate"] == {"delivered": 1}
    assert analysis["cases"][0]["current"]["classification"] == "selector_miss"
