"""The comparison harness, against the fixture schema it will actually read.

The first version of this harness read case["expect_contains"] and
case["expect_sections"]. Neither field exists in benchmark_cases.json, so
completeness and citation correctness were empty for every case and reported as
zero problems - a measurement that looks like a clean result. These tests read
the real fixture, so a field that does not exist fails here rather than after
someone has paid for a run.

The offline half runs from a frozen file with no model and no index, so it can
be exercised completely. The paid half is covered only by its refusals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_grounding_comparison as comparison

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "benchmark_cases.json"

EVIDENCE = [
    {
        "content": (
            "Delivery charges - DZD\n"
            "Standard delivery: 900\n"
            "Membership charges - EUR\n"
            "Annual membership: 20\n"
        ),
        "title": "DZ-FR-Charges.pdf - Delivery",
        "country": "DZ",
        "section_id": "charges-1",
    }
]

EXPECTED = {
    "kind": "answer",
    "must_contain": ["900"],
    "must_not_contain": ["free of charge"],
    "required_sections": ["charges-1"],
    "must_cite": True,
}


def _frozen(tmp_path, name: str, runs: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "fixture_sha256": "test",
                "turn_executions": len(runs),
                "grounding_neutralised": True,
                "runs": runs,
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(**overrides) -> dict:
    record = {
        "id": "delivery",
        "attempt": 0,
        "turns": 1,
        "language": "en",
        "country": "DZ",
        "answer": "Standard delivery costs 900 DZD.",
        "abstained": False,
        "citations": [{"section": "charges-1", "country": "DZ"}],
        "expected": dict(EXPECTED),
        "documents": EVIDENCE,
    }
    record.update(overrides)
    return record


def _score(tmp_path, runs: list[dict]) -> dict:
    return comparison.score(_frozen(tmp_path, "frozen.json", runs), Path("."))


# --- the fixture schema, read from the fixture ----------------------------


def test_the_expectation_fields_this_harness_reads_exist_in_the_fixture() -> None:
    """The defect that made every completeness metric read zero.

    Asserted against the file rather than against a handwritten dict, because a
    handwritten dict is where the wrong field names came from.
    """
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)
    seen: set[str] = set()
    for case in cases:
        for turn in comparison._turns(case):
            seen.update(key for key, value in turn["expected"].items() if value)

    assert "must_contain" in seen
    assert "required_sections" in seen
    assert "must_not_contain" in seen
    # And the fields the first version invented are nowhere in the fixture.
    assert not any(
        key in case for case in cases for key in ("expect_contains", "expect_sections")
    )


def test_must_cite_is_read_as_a_flag_not_a_list_of_sections() -> None:
    """It is a boolean in the fixture. Treating it as a list raises TypeError,
    which is how this was found - on a preflight, before any spending."""
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)
    citing = [case for case in cases if (case.get("expected") or {}).get("must_cite")]

    assert citing, "the fixture must still contain a case that requires citation"
    assert comparison._expectations(citing[0]["expected"])["must_cite"] is True


def test_a_conversation_case_counts_its_prior_turns_and_its_own_question() -> None:
    """The count that was wrong by one execution per conversation case.

    A conversation case replays its prior turns and then asks its own question,
    so it costs len(conversation) + 1. Returning only the conversation turns
    also scored the answer against the wrong turn's expectation.
    """
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)
    conversational = [case for case in cases if case.get("conversation")]

    assert conversational, "the fixture must still contain a conversation case"
    for case in conversational:
        assert len(comparison._turns(case)) == len(case["conversation"]) + 1
        # The last turn is the case's own question, and carries its expectation.
        assert comparison._turns(case)[-1]["question"] == case["question"]


def test_a_canary_style_string_conversation_is_also_understood() -> None:
    """The two fixtures disagree about what "conversation" holds."""
    case = {"question": "And the minimum?", "conversation": ["First question"], "expected": {}}

    assert [turn["question"] for turn in comparison._turns(case)] == [
        "First question",
        "And the minimum?",
    ]


def test_preflight_counts_turns_not_cases(capsys) -> None:
    """17 cases are 19 turns. Reporting cases as calls understates the run."""
    result = comparison.preflight(FIXTURE, repeat=3, arms=2)

    assert result["cases"] == 17
    assert result["turns"] == 19
    assert result["turn_executions"] == 19 * 3 * 2
    # And it says plainly that a turn is not one paid call.
    assert "lower bound" in result["note"]


# --- scoring, over the real expectation shape -----------------------------


def test_a_missing_required_fact_is_counted(tmp_path) -> None:
    result = _score(tmp_path, [_run(answer="Delivery is charged separately.")])

    assert result["answer_quality_of_the_frozen_sample"]["turns_missing_required_text"] == 1


def test_forbidden_text_is_counted(tmp_path) -> None:
    result = _score(tmp_path, [_run(answer="Delivery is free of charge.")])

    assert result["answer_quality_of_the_frozen_sample"]["turns_with_forbidden_text"] == 1


def test_a_wrong_citation_is_counted(tmp_path) -> None:
    """Citing something is not citing the governing section."""
    result = _score(tmp_path, [_run(citations=[{"section": "unrelated-9", "country": "DZ"}])])

    assert result["answer_quality_of_the_frozen_sample"]["turns_with_uncited_required_section"] == 1


def test_no_citation_at_all_is_counted(tmp_path) -> None:
    result = _score(tmp_path, [_run(citations=[])])

    assert result["answer_quality_of_the_frozen_sample"]["turns_with_uncited_required_section"] == 1


def test_citations_are_not_scored_where_the_case_does_not_require_them(tmp_path) -> None:
    """Scoring a case that never asked for citations invents failures."""
    expected = dict(EXPECTED, must_cite=False)
    result = _score(tmp_path, [_run(citations=[], expected=expected)])

    assert result["answer_quality_of_the_frozen_sample"]["turns_with_uncited_required_section"] == 0


def test_a_correct_answer_scores_clean(tmp_path) -> None:
    """The control. Without it every metric above could be counting everything."""
    result = _score(tmp_path, [_run()])

    assert result["repair"]["figures_removed"] == 0
    quality = result["answer_quality_of_the_frozen_sample"]
    assert quality["turns_missing_required_text"] == 0
    assert quality["turns_with_forbidden_text"] == 0
    assert quality["turns_with_uncited_required_section"] == 0


# --- labels ---------------------------------------------------------------


def test_a_removed_figure_present_in_the_evidence_is_not_labelled_correct(
    tmp_path,
) -> None:
    """The reason the metric names changed.

    "Standard delivery costs 900 EUR" is wrong: the row is DZD. The candidate
    removes it, and 900 does appear in the evidence - so a metric called
    "correct facts removed" would have counted a correct removal as damage.
    The count is mechanical and says only that the string occurs.
    """
    result = _score(tmp_path, [_run(answer="Standard delivery costs 900 EUR.")])

    assert result["repair"]["removed_and_present_in_evidence"] == 1
    assert "correct" not in str(result["repair"])
    assert "only source adjudication can" in result["qualification"]


def test_every_changed_decision_is_marked_unreviewed(tmp_path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(
        json.dumps(
            {
                "frozen": "f",
                "validator_loaded_from": "/a/validator.py",
                "repair": {},
                "runs": [{"id": "x", "attempt": 0, "removed": [], "removed_and_present_in_evidence": []}],
            }
        ),
        encoding="utf-8",
    )
    right.write_text(
        json.dumps(
            {
                "frozen": "f",
                "validator_loaded_from": "/b/validator.py",
                "repair": {},
                "runs": [
                    {
                        "id": "x",
                        "attempt": 0,
                        "removed": ["900"],
                        "removed_and_present_in_evidence": ["900"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = comparison.compare(left, right)

    assert result["changed_decisions"][0]["adjudication"] == "unreviewed"
    assert result["changed_decisions"][0]["removed_only_by_second"] == ["900"]
    assert "ground truth" in result["note"]


# --- guard rails ----------------------------------------------------------


def test_freeze_refuses_without_approval(tmp_path, capsys, monkeypatch) -> None:
    import sys

    monkeypatch.setattr(
        comparison, "freeze", lambda *a, **k: pytest.fail("freeze ran without approval")
    )
    argv = sys.argv
    sys.argv = ["x", "--freeze", str(tmp_path / "out.json")]
    try:
        assert comparison.main() == 2
    finally:
        sys.argv = argv

    assert "refused" in capsys.readouterr().out
    assert not (tmp_path / "out.json").exists()


def test_freeze_refuses_when_approved_but_unbounded(tmp_path, capsys, monkeypatch) -> None:
    """The approval flag acknowledges spending. --max-turns is what bounds it."""
    import sys

    monkeypatch.setattr(
        comparison, "freeze", lambda *a, **k: pytest.fail("freeze ran unbounded")
    )
    argv = sys.argv
    sys.argv = [
        "x",
        "--freeze",
        str(tmp_path / "out.json"),
        "--i-have-approval-for-paid-model-calls",
    ]
    try:
        assert comparison.main() == 2
    finally:
        sys.argv = argv

    assert "does not bound it" in capsys.readouterr().out


def test_comparing_an_arm_with_itself_is_refused(tmp_path) -> None:
    """Two arms that loaded the same file agree perfectly and mean nothing."""
    scored = tmp_path / "arm.json"
    scored.write_text(
        json.dumps(
            {"frozen": "f", "validator_loaded_from": "/a/validator.py", "repair": {}, "runs": []}
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        comparison.compare(scored, scored)


def test_comparing_across_different_frozen_sets_is_refused(tmp_path) -> None:
    """A comparison across different inputs measures the inputs."""
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"frozen": "a", "validator_loaded_from": "/a.py", "repair": {}, "runs": []}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"frozen": "b", "validator_loaded_from": "/b.py", "repair": {}, "runs": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        comparison.compare(first, second)


def test_scoring_reports_the_file_the_validator_actually_loaded(tmp_path) -> None:
    """An arm that silently scored itself must be visible, not assumed."""
    result = _score(tmp_path, [_run()])

    assert result["validator_loaded_from"].endswith("numeric_grounding_validator.py")


def test_repair_results_are_reported_separately_from_answer_quality(tmp_path) -> None:
    """They answer different questions and only one is isolated.

    Repair is a pure function of the frozen input, so it differs between arms
    only because the rule differs. Answer quality describes the captured
    sample, which neither arm produced - it is identical for both by
    construction. One combined block invites reading a fixed number as a
    result.
    """
    result = _score(tmp_path, [_run()])

    assert set(result["repair"]) == {
        "turns",
        "figures_removed",
        "removed_and_present_in_evidence",
        "removed_and_absent_from_evidence",
    }
    assert "note" in result["answer_quality_of_the_frozen_sample"]
    assert "does not measure either arm" in result["answer_quality_of_the_frozen_sample"]["note"]
