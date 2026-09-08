"""Tests for the answer-quality benchmark harness.

The harness decides whether an answer counted as correct, so a bug here is
worse than no benchmark at all: it produces a number everyone trusts and
nobody checks. These tests pin the judging rules and the fixture contract.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load("run_benchmark")

VALID_CASE = {
    "id": "case-1",
    "question": "What is the minimum order?",
    "country": "GB",
    "language": "en",
    "role": "fbo",
    "intent_group": "directory",
    "expected": {"kind": "answer", "must_contain": ["2 Case Credits"]},
    "source_evidence": "Policy section 4.2 states the minimum.",
    "provenance": "Dumped from the index on 2026-09-07.",
}


def _fixture(tmp_path: Path, cases: list[dict], **overrides) -> Path:
    payload = {"schema_version": 1, "cases": cases}
    payload.update(overrides)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(**overrides) -> dict:
    run = {
        "answer": "The minimum order is 2 Case Credits.",
        "citations": 1,
        "abstained": False,
        "failure_layer": "",
        "removed_numeric_claims": [],
        "top_title": "UK Policy Manual",
        "confidence": 0.9,
        "input_tokens": 100,
        "output_tokens": 20,
        "duration_ms": 500.0,
    }
    run.update(overrides)
    return run


def test_fixture_loads_and_reports_a_content_hash(tmp_path):
    cases, digest = benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE]))
    assert [case["id"] for case in cases] == ["case-1"]
    # A result is only comparable to another if both name the case set they ran.
    assert len(digest) == 64


def test_case_without_provenance_is_refused(tmp_path):
    case = copy.deepcopy(VALID_CASE)
    case["provenance"] = "   "
    with pytest.raises(ValueError, match="provenance"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_answer_case_asserting_nothing_is_refused(tmp_path):
    """A case with no required content would pass on any reply at all."""
    case = copy.deepcopy(VALID_CASE)
    case["expected"] = {"kind": "answer", "must_contain": []}
    with pytest.raises(ValueError, match="asserts nothing"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_duplicate_case_ids_are_refused(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE, copy.deepcopy(VALID_CASE)]))


def test_unknown_schema_version_is_refused(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE], schema_version=2))


def test_correct_answer_passes():
    assert benchmark.score_run(VALID_CASE, _run())["passed"]


def test_missing_required_fact_fails():
    scored = benchmark.score_run(VALID_CASE, _run(answer="The minimum order is one case."))
    assert not scored["passed"]
    assert "missing required fact" in scored["failures"][0]


def test_abstaining_on_an_answerable_question_fails():
    scored = benchmark.score_run(VALID_CASE, _run(abstained=True))
    assert scored["failures"] == ["abstained on an answerable question"]


def test_expected_abstention_passes_and_answering_fails():
    """A refusal is a correct outcome when the documents do not cover a question.

    Scoring it as a failure would reward the system for inventing an answer,
    which is the exact behaviour the evidence contract exists to prevent.
    """
    case = {**VALID_CASE, "expected": {"kind": "abstain"}}
    assert benchmark.score_run(case, _run(abstained=True, citations=0))["passed"]
    answered = benchmark.score_run(case, _run(abstained=False))
    assert answered["failures"] == ["answered a question the documents do not cover"]


def test_forbidden_content_fails_even_on_an_abstention():
    case = {**VALID_CASE, "expected": {"kind": "abstain", "must_not_contain": ["£19.99"]}}
    scored = benchmark.score_run(case, _run(abstained=True, answer="I can't help, but it's £19.99."))
    assert not scored["passed"]


def test_wrong_governing_source_is_reported_separately():
    """Retrieval and generation fail differently and need telling apart."""
    case = {**VALID_CASE, "expected": {**VALID_CASE["expected"], "source_title_contains": "UK Policy"}}
    scored = benchmark.score_run(case, _run(top_title="Ireland Policy Manual"))
    assert not scored["retrieval_hit"]
    assert "governing source not retrieved first" in scored["failures"][0]


def test_grounding_repair_damage_is_recorded_even_when_the_case_passes():
    """Repair silently edits an answer, so its firing must stay visible."""
    scored = benchmark.score_run(VALID_CASE, _run(removed_numeric_claims=["17.00"]))
    assert scored["passed"] and scored["repair_damaged"]


def test_summary_states_denominators_and_flags_instability():
    results = [
        {"id": "a", "intent_group": "directory", "expected_kind": "answer", "runs_count": 2,
         "passed_runs": 1, "runs": [_run() | {"passed": True, "retrieval_hit": True, "repair_damaged": False},
                                    _run() | {"passed": False, "retrieval_hit": True, "repair_damaged": False}]},
    ]
    summary = benchmark.summarise(results, {"input": 1.0, "output": 5.0})
    assert summary["correct"] == "1/2 (50.0%)"
    # A case that passes sometimes is not a passing case.
    assert summary["unstable_cases"] == ["a"]
    # 200 input + 40 output tokens at $1/$5 per million.
    assert summary["measured_cost_usd"] == pytest.approx(0.0004, abs=1e-6)


def test_cost_is_omitted_when_no_prices_are_supplied():
    """Prices change; a guessed rate would be reported as a measurement."""
    results = [{"id": "a", "intent_group": "g", "expected_kind": "answer", "runs_count": 1,
                "passed_runs": 1, "runs": [_run() | {"passed": True, "retrieval_hit": True, "repair_damaged": False}]}]
    assert "measured_cost_usd" not in benchmark.summarise(results, None)


def test_shipped_pilot_fixture_is_valid():
    cases, _ = benchmark.load_fixture(PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json")
    assert cases
    for case in cases:
        assert case["source_evidence"] and case["provenance"]


def test_benchmark_reuses_the_canary_pipeline_rather_than_copying_it():
    """One implementation of 'ask this like a user would', including cache bypass.

    A second copy would drift, and the copy that drifts is the one not run on
    every deploy.
    """
    source = (PROJECT_ROOT / "scripts" / "run_benchmark.py").read_text(encoding="utf-8")
    assert "canary.run_pipeline_capture" in source
    assert "AIOrchestrator" not in source


def test_canary_tuple_entry_point_still_matches_capture():
    """The gate's own signature must survive the refactor its tests rely on."""
    canary = _load("run_retrieval_canary")
    captured = canary._PipelineRun(
        retrieval="result",
        response=type("R", (), {"answer": "text", "citations": [1, 2]})(),
        removed_numeric_claims=["9"],
        duration_ms=1.0,
    )
    canary.run_pipeline_capture = lambda case, sequence: captured
    assert canary.run_pipeline_once({}, 1) == ("result", "text", 2, ["9"])
