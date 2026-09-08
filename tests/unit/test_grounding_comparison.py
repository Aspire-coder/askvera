"""The comparison harness, exercised without touching a model or an index.

A measurement tool that has never been run is a guess about what it will
report. The offline half - evaluate and compare - is the half that produces
the numbers a decision gets made on, and it runs entirely from a capture file,
so it can be tested against a fixture that has the answers built into it.

The capture half calls Bedrock and is not tested here. What IS tested is that
it refuses to do so without explicit approval.
"""

from __future__ import annotations

import json

import pytest

from scripts import run_grounding_comparison as comparison

DOCUMENTS = [
    {
        "content": "Delivery charges - DZD\nStandard delivery: 900\n",
        "title": "DZ-FR-Charges.pdf - Delivery",
        "country": "DZ",
        "section_id": "charges-1",
    }
]


def _capture(tmp_path, name: str, runs: list[dict]):
    path = tmp_path / name
    path.write_text(
        json.dumps({"fixture_sha256": "abc", "case_count": len(runs), "runs": runs}),
        encoding="utf-8",
    )
    return path


def _run(**overrides) -> dict:
    record = {
        "id": "algeria-delivery",
        "attempt": 0,
        "question": "How much is delivery?",
        "language": "en",
        "country": "DZ",
        "answer": "Standard delivery costs 900 DZD.",
        "abstained": False,
        "removed_numeric_claims": [],
        "citations": [{"section": "charges-1", "country": "DZ"}],
        "expect_sections": ["charges-1"],
        "expect_contains": ["900"],
        "documents": DOCUMENTS,
    }
    record.update(overrides)
    return record


def test_capture_refuses_without_explicit_approval(tmp_path, capsys, monkeypatch) -> None:
    """The guard that stops an unapproved spend.

    Also asserts nothing was written, because a refusal that still produced a
    file would mean the run happened and only the reporting stopped.
    """
    import sys

    def _must_not_run(*args, **kwargs):
        raise AssertionError("capture ran without approval")

    monkeypatch.setattr(comparison, "capture", _must_not_run)
    argv = sys.argv
    sys.argv = ["x", "--capture", str(tmp_path / "out.json")]
    try:
        assert comparison.main() == 2
    finally:
        sys.argv = argv

    assert "refused" in capsys.readouterr().out
    assert not (tmp_path / "out.json").exists()


def test_a_removed_figure_the_evidence_contains_is_counted_as_a_lost_fact(tmp_path) -> None:
    """The metric the whole exercise exists for.

    900 is in the source. If an arm removed it, a reader lost a fact they
    asked for, and that is the cost side of the stricter rule.
    """
    path = _capture(
        tmp_path,
        "arm.json",
        [_run(answer="Standard delivery costs some amount.", removed_numeric_claims=["900"])],
    )

    totals = comparison.evaluate(path)["totals"]

    assert totals["correct_facts_removed"] == 1
    assert totals["invented_facts_removed"] == 0


def test_a_removed_figure_the_evidence_lacks_is_counted_as_a_correct_removal(
    tmp_path,
) -> None:
    """The benefit side. Counting both as damage measures neither."""
    path = _capture(
        tmp_path,
        "arm.json",
        [_run(answer="Delivery costs something.", removed_numeric_claims=["4500"])],
    )

    totals = comparison.evaluate(path)["totals"]

    assert totals["correct_facts_removed"] == 0
    assert totals["invented_facts_removed"] == 1


def test_a_kept_figure_the_oracle_rejects_is_counted(tmp_path) -> None:
    """"Unsupported facts accepted", measured against a stated rule.

    EUR is nowhere in this source, so the oracle rejects the claim. An arm that
    kept it accepted a unit it had no support for.
    """
    path = _capture(tmp_path, "arm.json", [_run(answer="Standard delivery costs 900 EUR.")])

    totals = comparison.evaluate(path)["totals"]

    assert totals["accepted_but_unsupported_by_oracle"] == 1


def test_a_correctly_denominated_answer_scores_clean(tmp_path) -> None:
    """The control. Without it the metrics above could be counting everything."""
    totals = comparison.evaluate(_capture(tmp_path, "arm.json", [_run()]))["totals"]

    assert totals["accepted_but_unsupported_by_oracle"] == 0
    assert totals["correct_facts_removed"] == 0
    assert totals["runs_missing_expected_text"] == 0
    assert totals["runs_with_uncited_required_section"] == 0


def test_completeness_notices_a_missing_required_fact(tmp_path) -> None:
    path = _capture(tmp_path, "arm.json", [_run(answer="Delivery is charged separately.")])

    assert comparison.evaluate(path)["totals"]["runs_missing_expected_text"] == 1


def test_citation_correctness_notices_a_missing_required_section(tmp_path) -> None:
    path = _capture(tmp_path, "arm.json", [_run(citations=[])])

    assert comparison.evaluate(path)["totals"]["runs_with_uncited_required_section"] == 1


def test_the_comparison_lists_the_figures_whose_decision_changed(tmp_path) -> None:
    """The output a person actually reads.

    Totals say something moved. This says which figure, in which case, so the
    reviewer can look at the section it came from and decide.
    """
    first = _capture(tmp_path, "first.json", [_run()])
    second = _capture(
        tmp_path,
        "second.json",
        [_run(answer="Standard delivery costs some amount.", removed_numeric_claims=["900"])],
    )

    result = comparison.compare(first, second)

    assert len(result["changed_decisions"]) == 1
    change = result["changed_decisions"][0]
    assert change["removed_only_by_second"] == ["900"]
    assert change["newly_removed_but_present_in_source"] == ["900"]


def test_identical_arms_report_no_changed_decisions(tmp_path) -> None:
    """A diff that always finds something is not a diff."""
    first = _capture(tmp_path, "first.json", [_run()])
    second = _capture(tmp_path, "second.json", [_run()])

    assert comparison.compare(first, second)["changed_decisions"] == []


def test_the_comparison_says_the_oracle_is_not_ground_truth(tmp_path) -> None:
    """The result must not be read as "the candidate is correct N times"."""
    first = _capture(tmp_path, "first.json", [_run()])
    second = _capture(tmp_path, "second.json", [_run()])

    assert "not ground truth" in comparison.compare(first, second)["note"]


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Standard delivery costs 900 DZD.", ["900"]),
        ("Orders arrive between 48h and 96h.", ["48", "96"]),
        ("No figures here at all.", []),
    ],
)
def test_figures_are_counted_by_the_validators_own_notion(answer, expected) -> None:
    assert comparison._figures(answer) == expected
