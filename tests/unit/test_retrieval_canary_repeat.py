"""Repeat runs and the observed-only tier.

A single run of a case that fails one time in three is close to meaningless.
The kyrgyzstan-foreign-fbo-bonus case failed roughly 4 times in 14 deploy runs
on 2026-09-07, each time recoverable by retrying the deploy unchanged -- which
is how a real regression gets waved through.

These tests cover the gate's own aggregation with a stubbed pipeline. They make
no model calls.
"""

import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_retrieval_canary_repeat", PROJECT_ROOT / "scripts" / "run_retrieval_canary.py"
)
canary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(canary)


def _case(**overrides):
    case = {
        "id": "case",
        "question": "q",
        "country": "US",
        "language": "en",
        "role": "new_prospect",
        "expected_title_contains": "T",
        "minimum_confidence": 0.0,
        "evidence_must_be_approved": True,
    }
    case.update(overrides)
    return case


def _stub_runs(monkeypatch, outcomes):
    """Make run_case_once yield the given pass/fail sequence."""
    remaining = list(outcomes)

    def fake_run_once(case, sequence):
        passed = remaining.pop(0)
        return {
            "id": case["id"],
            "passed": passed,
            "confidence": 0.9 if passed else 0.7,
            "top_title": "T" if passed else "WRONG",
            "top_section": "",
            "evidence_approved": True,
            "failure_reasons": [] if passed else ["top title 'WRONG' does not contain 'T'"],
            "typo_ranking_applied": False,
            "ranking_query_used": "q",
            "document_scores": [],
            "answer_citations": -1,
            "answer_extract": "",
        }

    monkeypatch.setattr(canary, "run_case_once", fake_run_once)


def test_case_passes_only_when_every_run_passes(monkeypatch):
    _stub_runs(monkeypatch, [True, True, True])
    result = canary.run_case(_case(), 1, 3)
    assert result["passed"] is True
    assert result["runs"] == 3
    assert result["passed_runs"] == 3
    assert result["flaky"] is False


def test_one_failure_in_three_fails_the_case(monkeypatch):
    """The exact shape that was previously waved through by retrying."""
    _stub_runs(monkeypatch, [True, False, True])
    result = canary.run_case(_case(), 1, 3)
    assert result["passed"] is False
    assert result["passed_runs"] == 2
    assert result["flaky"] is True


def test_uniform_failure_is_not_reported_as_flaky(monkeypatch):
    """Reliably wrong and intermittently wrong want different responses."""
    _stub_runs(monkeypatch, [False, False, False])
    result = canary.run_case(_case(), 1, 3)
    assert result["passed"] is False
    assert result["flaky"] is False


def test_failure_reasons_describe_an_actual_failed_run(monkeypatch):
    """Reporting the first run would show an empty reason list for a flaky case."""
    _stub_runs(monkeypatch, [True, False, True])
    result = canary.run_case(_case(), 1, 3)
    assert result["failure_reasons"], "expected the failing run's reasons to be reported"


def test_per_case_repeat_overrides_the_default(monkeypatch):
    _stub_runs(monkeypatch, [True, True, True, True, True])
    result = canary.run_case(_case(repeat=5), 1, 1)
    assert result["runs"] == 5


def test_default_repeat_of_one_preserves_existing_behaviour(monkeypatch):
    _stub_runs(monkeypatch, [True])
    result = canary.run_case(_case(), 1, 1)
    assert result["runs"] == 1
    assert result["passed"] is True


def test_cases_are_blocking_unless_stated_otherwise(monkeypatch):
    _stub_runs(monkeypatch, [True])
    assert canary.run_case(_case(), 1, 1)["blocking"] is True

    _stub_runs(monkeypatch, [True])
    assert canary.run_case(_case(blocking=False), 1, 1)["blocking"] is False


def _validate(cases):
    payload = {"schema_version": 1, "cases": cases}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        path = Path(handle.name)
    return canary.load_fixture(path)


def test_non_blocking_case_must_state_a_reason():
    """The observed-only tier must not become where failures go to be forgotten."""
    with pytest.raises(ValueError, match="non_blocking_reason"):
        _validate([_case(blocking=False)])

    cases, _ = _validate([_case(blocking=False, non_blocking_reason="unverified against live index")])
    assert cases[0]["blocking"] is False


@pytest.mark.parametrize("bad", [0, -1, True, "3", 1.5])
def test_repeat_must_be_a_positive_integer(bad):
    with pytest.raises(ValueError, match="repeat"):
        _validate([_case(repeat=bad)])


@pytest.mark.parametrize("bad", ["no", 0, None])
def test_blocking_must_be_a_boolean(bad):
    with pytest.raises(ValueError, match="blocking"):
        _validate([_case(blocking=bad)])


def test_shipped_fixture_is_valid_and_every_new_case_is_justified():
    cases, _ = canary.load_fixture(PROJECT_ROOT / "tests" / "fixtures" / "retrieval_canary.json")
    for case in cases:
        if case.get("blocking") is False:
            assert case.get("non_blocking_reason", "").strip()
