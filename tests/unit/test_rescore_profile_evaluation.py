from scripts.rescore_profile_evaluation import rescore_report


def _profile(record_country: str, delivered: bool = True):
    candidate = {
        "rank": 1,
        "id": f"global-{record_country}",
        "section_id": f"sponsoring-001-{record_country.casefold()}",
        "record_country": record_country,
        "country": "GLOBAL",
        "access_scope": "global",
    }
    metrics = {
        "candidate_count": 1,
        "top_candidates": [candidate],
        "recall_at_1": False,
        "recall_at_5": False,
        "recall_at_10": False,
        "recall_at_20": False,
        "first_relevant_rank": None,
        "reciprocal_rank": 0.0,
    }
    return {
        "answer": "Grounded directory answer." if delivered else "Insufficient evidence.",
        "citations": [{"section": candidate["section_id"]}] if delivered else [],
        "model_name": "test",
        "answer_status": "delivered" if delivered else "insufficient_evidence",
        "failure_layer": "" if delivered else "evidence_gate",
        "evidence_approved": delivered,
        "evidence_reason": "approved" if delivered else "below_threshold",
        "confidence": 0.9 if delivered else 0.1,
        "candidate_metrics": metrics,
        "selector_success": False,
        "answer_delivered": delivered,
        "retrieval_repeats": [
            {
                "document_ids": [candidate["id"]],
                "document_sections": [candidate["section_id"]],
                "selector_success": False,
                "candidate_metrics": metrics,
            }
        ],
    }


def test_rescore_corrects_country_code_to_directory_name_false_negative() -> None:
    profile = _profile("Algeria")
    report = {
        "manifest": {},
        "summary": {},
        "cases": [
            {
                "id": "DIR-DZ",
                "scope": "global_directory",
                "expected_behavior": "answer",
                "country": "CA",
                "target_country": "DZ",
                "relevant_sections": ["sponsoring-directory-algeria"],
                "current": profile,
                "candidate": profile,
                "current_expectation_met": False,
                "candidate_expectation_met": False,
            }
        ],
    }

    corrected = rescore_report(report)
    case = corrected["cases"][0]

    assert case["current"]["candidate_metrics"]["recall_at_1"] is True
    assert case["current"]["selector_success"] is True
    assert case["current_expectation_met"] is True
    assert corrected["summary"]["current"]["expectation_passes"] == 1
    assert corrected["manifest"]["offline_rescore"]["source_report_preserved"] is True


def test_rescore_supports_legacy_report_without_expected_behavior() -> None:
    profile = _profile("Nigeria")
    report = {
        "manifest": {},
        "summary": {},
        "cases": [
            {
                "id": "DIR-NG",
                "scope": "global_directory",
                "country": "CA",
                "target_country": "NG",
                "relevant_sections": ["sponsoring-directory-nigeria"],
                "current": profile,
                "candidate": profile,
            }
        ],
    }

    corrected = rescore_report(report)

    assert corrected["cases"][0]["expected_behavior"] == "answer"
    assert corrected["summary"]["candidate"]["expectation_passes"] == 1


def test_rescore_defaults_legacy_out_of_scope_case_to_abstention() -> None:
    profile = _profile("Nigeria", delivered=False)
    report = {
        "manifest": {},
        "summary": {},
        "cases": [
            {
                "id": "OFF-TOPIC",
                "scope": "out_of_scope",
                "country": "CA",
                "target_country": "",
                "relevant_sections": [],
                "current": profile,
                "candidate": profile,
            }
        ],
    }

    corrected = rescore_report(report)

    assert corrected["cases"][0]["expected_behavior"] == "abstain"
    assert corrected["summary"]["current"]["must_abstain_passes"] == 1


def test_rescore_overrides_stale_answer_label_for_out_of_scope_case() -> None:
    profile = _profile("Nigeria", delivered=False)
    report = {
        "manifest": {},
        "summary": {},
        "cases": [
            {
                "id": "OFF-TOPIC",
                "scope": "out_of_scope",
                "expected_behavior": "answer",
                "country": "CA",
                "target_country": "",
                "relevant_sections": [],
                "current": profile,
                "candidate": profile,
            }
        ],
    }

    corrected = rescore_report(report)

    assert corrected["cases"][0]["expected_behavior"] == "abstain"
    assert corrected["summary"]["candidate"]["must_abstain_cases"] == 1
