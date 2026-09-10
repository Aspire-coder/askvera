"""What the benchmark covers, and - more usefully - what it does not.

A benchmark that is never asked what it omits reports on the questions somebody
happened to write. These assertions turn the omissions into data: the covered
combinations are computed from the fixture, the uncovered ones are named here,
and adding a market or a language makes this file fail until the record is
updated.

Nothing here runs the pipeline or reads the corpus. It reads the case fixture
and the market configuration, which is why it can run locally at all - and why
the gap it reports is mostly "no local source text", not "nobody thought of
it".
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

FIXTURE = Path("tests/fixtures/benchmark_cases.json")


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


# --- the dimensions, and where they stop ------------------------------------


def test_the_covered_markets_are_recorded(cases: list[dict]) -> None:
    """Four markets out of the configured catalogue.

    A case needs source text to assert anything, and source text is what is not
    available locally. Adding a market to the fixture updates this line; adding
    one to config alone does not, which is the intended asymmetry.
    """
    from services.market_config import load_market_config

    covered = {case["country"] for case in cases}
    configured = {
        str(market["code"]).upper()
        for market in load_market_config()["markets"]
        if market.get("enabled", True)
    }

    assert covered == {"DK", "GB", "SE", "US"}
    assert covered < configured
    assert len(configured) - len(covered) > 100, (
        "most markets are unrepresented; this is a coverage gap, not a pass"
    )


def test_only_one_language_is_covered(cases: list[dict]) -> None:
    """Recorded as a gap, and the reason is not that nobody wrote the case.

    Asserting an expected fact in French needs the French record text, which
    has not been dumped. A case written without it would assert an assumption.
    """
    assert {case["language"] for case in cases} == {"en"}


def test_only_one_role_is_covered(cases: list[dict]) -> None:
    """One role case exists, but every case runs as the same role."""
    from config.vera_persona import ROLE_CONTENT_SCOPES

    covered = {case["role"] for case in cases}

    assert covered == {"active_distributor"}
    assert len(ROLE_CONTENT_SCOPES) > 1, "other roles exist and none is exercised"
    assert any(case["intent_group"] == "role_distinction" for case in cases), (
        "role distinctions are asked about within one session role"
    )


def test_the_topics_covered_are_recorded(cases: list[dict]) -> None:
    assert {case["intent_group"] for case in cases} == {
        "conversation",
        "country_clarification",
        "country_scope",
        "cross_market_contrast",
        "directory_fact",
        "role_distinction",
        "safety_refusal",
        "scope_boundary",
    }


def test_follow_up_turns_are_exercised(cases: list[dict]) -> None:
    """A single-turn benchmark cannot see a chain lose its market."""
    conversational = [case for case in cases if case.get("conversation")]

    assert len(conversational) >= 2
    assert any(
        any((turn.get("expected") or {}).get("kind") == "clarify" for turn in case["conversation"])
        for case in conversational
    ), "no chain starts from a clarification"


# --- the three outcomes stay three --------------------------------------------


def test_all_three_outcomes_are_represented(cases: list[dict]) -> None:
    """Incorrect acceptance, unnecessary refusal and clarification.

    Each needs a different fix, so each needs its own cases. A fixture with no
    clarification case cannot tell an over-refusal from a wrong-country answer.
    """
    kinds = Counter(case["expected"]["kind"] for case in cases)

    assert kinds["answer"] >= 1
    assert kinds["abstain"] >= 1
    assert kinds["clarify"] >= 1


def test_a_clarification_case_has_a_negative_control(cases: list[dict]) -> None:
    """Clarifying too much is a defect too, and needs its own case.

    A system that asks which country on every question would pass every
    clarification case and be useless.
    """
    clarification = [case for case in cases if case["intent_group"] == "country_clarification"]

    assert any(case["expected"]["kind"] == "clarify" for case in clarification)
    assert any(case["expected"]["kind"] != "clarify" for case in clarification)


def test_the_scorer_keeps_the_three_apart() -> None:
    """Asserted against the harness, not assumed from the fixture."""
    import inspect
    import re

    from scripts import run_benchmark

    source = re.sub(r"#.*", "", inspect.getsource(run_benchmark.summarise))

    assert "missed_clarification" in source
    assert "clarified_when_it_should_not" in source
    assert "false_abstention" in source
    assert "answered_when_it_should_not" in source


# --- evidence, and the honesty of the labels --------------------------------


def test_every_case_states_what_makes_its_expectation_true(cases: list[dict]) -> None:
    for case in cases:
        assert case["source_evidence"].strip()
        assert case["provenance"].strip()


def test_a_case_never_run_says_so(cases: list[dict]) -> None:
    """An expectation derived from source text is not an observed result.

    Cases whose provenance is repository configuration or a corpus dump have
    never been through the pipeline. Saying so in the case is what stops a
    passing dry run reading as a passing benchmark.
    """
    unvalidated = [
        case["id"] for case in cases if "AWAITING LIVE VALIDATION" in case["provenance"]
    ]

    assert unvalidated, "no case admits to never having been run"


def test_the_held_out_set_is_empty_and_that_is_stated(cases: list[dict]) -> None:
    """Every case was authored or adjusted while fixing something.

    So passing them measures whether known defects stay fixed, not how the
    system behaves on questions it was never tuned against. A case may not be
    relabelled held_out later: it was used, and using it is what spent it.
    """
    by_set = Counter(case["evaluation_set"] for case in cases)

    assert by_set["held_out"] == 0
    assert by_set["development"] == len(cases)


def test_no_case_asserts_a_figure_it_could_not_read(cases: list[dict]) -> None:
    """A case naming no source may not assert a number.

    The Belgium and Germany records have not been dumped locally, so the cases
    touching them assert market names and refusals rather than figures.
    Asserting a figure from an undumped record is inventing it.
    """
    import re

    for case in cases:
        if "has not been dumped" not in case["provenance"]:
            continue
        for required in case["expected"].get("must_contain") or []:
            assert not re.search(r"\d", str(required)), (
                f"{case['id']} asserts a figure from a record nobody read"
            )
