"""Tests for exact case-level Current versus vNext reporting."""

from scripts.compare_retrieval_profiles import comparison_summary


def test_comparison_summary_reports_exact_improvements_and_regressions() -> None:
    current = [
        {"id": "A", "passed": True},
        {"id": "B", "passed": False},
        {"id": "C", "passed": True},
    ]
    candidate = [
        {"id": "A", "passed": True},
        {"id": "B", "passed": True},
        {"id": "C", "passed": False},
    ]

    summary = comparison_summary(current, candidate)

    assert summary["status"] == "failed"
    assert summary["improved_case_ids"] == ["B"]
    assert summary["regressed_case_ids"] == ["C"]
    assert summary["unchanged_case_ids"] == ["A"]


def test_comparison_summary_passes_only_without_regression() -> None:
    current = [{"id": "A", "passed": True}, {"id": "B", "passed": False}]
    candidate = [{"id": "A", "passed": True}, {"id": "B", "passed": True}]

    summary = comparison_summary(current, candidate)

    assert summary["status"] == "passed"
    assert summary["current_passed"] == 1
    assert summary["vnext_passed"] == 2
