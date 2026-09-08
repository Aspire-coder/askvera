"""Freezing: what it captures, and whether an interruption costs anything.

Two claims were made about this loop that were not true. It said it captured
the pre-repair answer, but it read the pipeline's final response - which is not
what repair saw, because steps run on both sides of repair. And it said it
checkpointed per turn, but it ran a whole conversation and stored one record,
so an interruption inside a chain lost every turn it had paid for.

Both are now driven by a hook the orchestrator calls at the boundary itself.
These tests stand in for the pipeline entirely: a fake run_pipeline_capture
calls the hook once per turn, which is what the real one causes to happen, so
the loop, the checkpointing and the resume logic are exercised with no model,
no index and no spending.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_grounding_comparison as comparison

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "benchmark_cases.json"


class _Document:
    def __init__(self, content: str):
        self.content = content
        self.title = "DZ-FR-Charges.pdf - Delivery"
        self.country = "DZ"
        self.metadata = {"section_id": "charges-1"}


def _fake_pipeline(monkeypatch, *, turns_per_case: dict[str, int], fail_on: str = ""):
    """A pipeline that calls the capture hook once per turn, then returns.

    fail_on raises part way through that case's turns, which is how an
    interrupted conversation is simulated.
    """
    from app.orchestrator import chat_orchestrator

    calls: list[str] = []

    def _run(case, sequence):
        identifier = case["id"]
        for index in range(turns_per_case.get(identifier, 1)):
            if fail_on == identifier and index == 1:
                raise RuntimeError("interrupted mid-conversation")
            calls.append(f"{identifier}:{index}")
            hook = chat_orchestrator.pre_repair_capture_hook
            assert hook is not None, "freeze must install the hook before running"
            hook(
                f"Answer for {identifier} turn {index}: 900 DZD.",
                [_Document("Delivery charges - DZD\nStandard delivery: 900\n")],
                f"corr-{identifier}-{index}",
            )
        return object()

    import scripts.run_retrieval_canary as canary

    monkeypatch.setattr(canary, "run_pipeline_capture", _run)
    return calls


def _freeze(tmp_path, monkeypatch, **kwargs):
    defaults = {
        "fixture": FIXTURE,
        "repeat": 1,
        "max_turns": 0,
        "checkpoint": tmp_path / "frozen.json",
        "cases_wanted": ["algeria-delivery-cost"],
        "resume": False,
    }
    defaults.update(kwargs)
    return comparison.freeze(**defaults)


# --- the boundary ----------------------------------------------------------


def test_the_capture_comes_from_the_hook_not_the_final_response(tmp_path, monkeypatch) -> None:
    """The defect. A final response is not what repair was given.

    If the loop read the pipeline's return value, this fake - which returns a
    bare object with no answer at all - would produce empty records. It
    produces the hook's text instead.
    """
    _fake_pipeline(monkeypatch, turns_per_case={"algeria-delivery-cost": 1})

    payload = _freeze(tmp_path, monkeypatch)

    assert payload["turns_captured"] == 1
    assert "900 DZD" in payload["runs"][0]["answer"]
    assert payload["captured_at_boundary"] == "pre_numeric_repair"


def test_the_hook_is_removed_afterwards(tmp_path, monkeypatch) -> None:
    """A measurement hook left installed would follow the process around."""
    from app.orchestrator import chat_orchestrator

    _fake_pipeline(monkeypatch, turns_per_case={"algeria-delivery-cost": 1})
    _freeze(tmp_path, monkeypatch)

    assert chat_orchestrator.pre_repair_capture_hook is None


def test_the_hook_is_removed_even_when_the_run_fails(tmp_path, monkeypatch) -> None:
    _fake_pipeline(
        monkeypatch,
        turns_per_case={"belgium-then-germany-market-continuity": 3},
        fail_on="belgium-then-germany-market-continuity",
    )
    from app.orchestrator import chat_orchestrator

    with pytest.raises(RuntimeError):
        _freeze(tmp_path, monkeypatch, cases_wanted=["belgium-then-germany-market-continuity"])

    assert chat_orchestrator.pre_repair_capture_hook is None


def test_grounding_is_not_disabled_during_capture() -> None:
    """Safeguards keep running; the hook only observes.

    The previous version replaced unsupported_numeric_claims with a stub for
    the whole run, which switched a safety check off to take a measurement.
    """
    import inspect

    source = inspect.getsource(comparison.freeze)

    assert "unsupported_numeric_claims" not in source
    assert "Grounding is NOT disabled" in (inspect.getdoc(comparison.freeze) or "")


# --- per-turn checkpointing ------------------------------------------------


def test_every_turn_of_a_conversation_is_captured(tmp_path, monkeypatch) -> None:
    """Three turns are three records, not one.

    Earlier turns cost calls and carry their own expectations, so storing only
    the last one paid for evidence that could not then be adjudicated.
    """
    _fake_pipeline(monkeypatch, turns_per_case={"belgium-then-germany-market-continuity": 3})

    payload = _freeze(
        tmp_path, monkeypatch, cases_wanted=["belgium-then-germany-market-continuity"]
    )

    assert payload["turns_captured"] == 3
    assert [run["turn_index"] for run in payload["runs"]] == [0, 1, 2]
    assert [run["is_final_turn"] for run in payload["runs"]] == [False, False, True]


def test_the_checkpoint_is_written_during_the_run_not_after(tmp_path, monkeypatch) -> None:
    """An interruption must keep the turns already paid for."""
    checkpoint = tmp_path / "frozen.json"
    _fake_pipeline(
        monkeypatch,
        turns_per_case={"belgium-then-germany-market-continuity": 3},
        fail_on="belgium-then-germany-market-continuity",
    )

    with pytest.raises(RuntimeError):
        _freeze(
            tmp_path,
            monkeypatch,
            checkpoint=checkpoint,
            cases_wanted=["belgium-then-germany-market-continuity"],
        )

    assert checkpoint.exists(), "the first turn was paid for and must survive"
    assert len(json.loads(checkpoint.read_text(encoding="utf-8"))["runs"]) == 1


def test_each_turn_carries_its_own_expectation(tmp_path, monkeypatch) -> None:
    """A conversation's turns are judged against their own turn, not the last."""
    _fake_pipeline(monkeypatch, turns_per_case={"belgium-then-germany-market-continuity": 3})

    payload = _freeze(
        tmp_path, monkeypatch, cases_wanted=["belgium-then-germany-market-continuity"]
    )

    required = [tuple(run["expected"].get("required_sections") or []) for run in payload["runs"]]
    assert len(set(required)) > 1, "the turns must not all share one expectation"


# --- resume ---------------------------------------------------------------


def test_a_completed_case_is_not_paid_for_twice(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "frozen.json"
    calls = _fake_pipeline(monkeypatch, turns_per_case={"algeria-delivery-cost": 1})
    _freeze(tmp_path, monkeypatch, checkpoint=checkpoint)
    assert len(calls) == 1

    payload = _freeze(tmp_path, monkeypatch, checkpoint=checkpoint, resume=True)

    assert len(calls) == 1, "a completed case must not be run again"
    assert payload["turns_captured"] == 1


def test_a_half_captured_conversation_is_discarded_and_redone(tmp_path, monkeypatch) -> None:
    """A partial chain scored as though whole would be a silent wrong answer."""
    checkpoint = tmp_path / "frozen.json"
    _fake_pipeline(
        monkeypatch,
        turns_per_case={"belgium-then-germany-market-continuity": 3},
        fail_on="belgium-then-germany-market-continuity",
    )
    with pytest.raises(RuntimeError):
        _freeze(
            tmp_path,
            monkeypatch,
            checkpoint=checkpoint,
            cases_wanted=["belgium-then-germany-market-continuity"],
        )
    assert len(json.loads(checkpoint.read_text(encoding="utf-8"))["runs"]) == 1

    calls = _fake_pipeline(monkeypatch, turns_per_case={"belgium-then-germany-market-continuity": 3})
    payload = _freeze(
        tmp_path,
        monkeypatch,
        checkpoint=checkpoint,
        cases_wanted=["belgium-then-germany-market-continuity"],
        resume=True,
    )

    assert len(calls) == 3, "the interrupted chain must be captured again in full"
    assert payload["turns_captured"] == 3


# --- selection and provenance ---------------------------------------------


def test_a_case_that_is_not_in_the_fixture_is_refused() -> None:
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)

    with pytest.raises(SystemExit):
        comparison._select(cases, ["no-such-case"])


def test_selection_preserves_the_order_asked_for() -> None:
    """A pilot is a chosen list, so it runs in the order it was chosen."""
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)
    wanted = ["france-minimum-order", "algeria-delivery-cost"]

    assert [case["id"] for case in comparison._select(cases, wanted)] == wanted


def test_the_capture_records_what_produced_it(tmp_path, monkeypatch) -> None:
    """A capture with no provenance is a number with no claim attached."""
    _fake_pipeline(monkeypatch, turns_per_case={"algeria-delivery-cost": 1})

    provenance = _freeze(tmp_path, monkeypatch)["provenance"]

    assert provenance["fixture_sha256"]
    for key in (
        "harness_commit",
        "harness_dirty",
        "opensearch_index",
        "bedrock_model_id",
        "chunk_profile",
    ):
        assert key in provenance


def test_an_existing_capture_is_not_overwritten(tmp_path, capsys, monkeypatch) -> None:
    """Overwriting destroys turns somebody paid for."""
    import sys

    existing = tmp_path / "frozen.json"
    existing.write_text('{"runs": []}', encoding="utf-8")
    monkeypatch.setattr(
        comparison, "freeze", lambda *a, **k: pytest.fail("freeze ran over an existing capture")
    )

    argv = sys.argv
    sys.argv = [
        "x",
        "--freeze",
        str(existing),
        "--i-have-approval-for-paid-model-calls",
        "--max-turns",
        "4",
    ]
    try:
        assert comparison.main() == 2
    finally:
        sys.argv = argv

    assert "--resume" in capsys.readouterr().out
