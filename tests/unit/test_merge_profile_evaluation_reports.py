"""Tests for bounded correction-report merging."""

import pytest

from scripts.merge_profile_evaluation_reports import merge_reports


def _answer(delivered: bool) -> dict:
    return {
        "answer_delivered": delivered,
        "evidence_approved": delivered,
        "selector_success": delivered,
        "candidate_metrics": {
            "recall_at_1": delivered,
            "recall_at_5": delivered,
            "recall_at_10": delivered,
            "recall_at_20": delivered,
            "reciprocal_rank": 1.0 if delivered else 0.0,
        },
    }


def test_merge_replaces_cases_and_recomputes_summary() -> None:
    base = {
        "manifest": {"commit": "abc"},
        "cases": [
            {"id": "A", "scope": "locale_policy", "current": _answer(False), "candidate": _answer(False)},
            {"id": "B", "scope": "locale_policy", "current": _answer(False), "candidate": _answer(False)},
        ],
    }
    corrections = {
        "manifest": {"commit": "abc"},
        "cases": [
            {"id": "B", "scope": "locale_policy", "current": _answer(True), "candidate": _answer(True)},
        ],
    }

    merged = merge_reports(base, corrections)

    assert merged["cases"][1]["current"]["answer_delivered"] is True
    assert merged["summary"]["current"]["recall_at_1"] == 0.5
    assert merged["manifest"]["corrected_case_ids"] == ["B"]


def test_merge_rejects_unknown_case() -> None:
    base = {"manifest": {}, "cases": [{"id": "A", "scope": "locale_policy", "current": _answer(False), "candidate": _answer(False)}]}
    corrections = {"cases": [{"id": "Z", "scope": "locale_policy", "current": _answer(True), "candidate": _answer(True)}]}

    with pytest.raises(ValueError, match="unknown case IDs"):
        merge_reports(base, corrections)
