"""Freezing: turn accounting, resume validation, and what an interruption costs.

Three claims about this loop have been wrong in turn, and the last one is the
subtle one. Counting turns by counting capture-hook calls looked equivalent to
counting turns, and is not: a turn that refuses early, or answers from cache,
never reaches numeric repair and so never fires the hook. Counting hook calls
therefore

  - gave a later answer the expectation belonging to an earlier turn,
  - undercounted the requests actually made against --max-turns, and
  - let the last captured turn mark a conversation complete when its real
    final turn was never captured.

Turn identity now comes from the conversation runner, which is the only thing
that knows how many turns it performed. The hook contributes evidence and
nothing else.

The fake pipeline below returns what the real one returns - prior responses
plus a final response, each with a correlation id - so the reconciliation, the
checkpointing and the resume rules are exercised with no model and no spending.
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


class _Response:
    def __init__(self, correlation_id: str, answer: str, abstained: bool = False):
        self.correlation_id = correlation_id
        self.answer = answer
        self.citations = [{"section": "charges-1", "country": "DZ"}]
        self.metadata = {"fallback": abstained}


class _Run:
    def __init__(self, responses):
        self.prior_responses = tuple(responses[:-1])
        self.response = responses[-1]
        self.retrieval = None
        self.removed_numeric_claims: list[str] = []
        self.duration_ms = 1.0


def _pipeline(monkeypatch, *, plan: dict[str, list[str]], fail_after: int | None = None):
    """A pipeline whose turns are described by a plan.

    plan maps a case id to a list of "answer" or "refusal". A refusal returns a
    response without ever firing the capture hook, which is exactly what an
    early return does in the real orchestrator.
    """
    from app.orchestrator import chat_orchestrator

    performed: list[str] = []

    def _run(case, sequence):
        identifier = case["id"]
        kinds = plan.get(identifier, ["answer"])
        responses = []
        for index, kind in enumerate(kinds):
            if fail_after is not None and len(performed) >= fail_after:
                raise RuntimeError("interrupted")
            correlation_id = f"corr-{identifier}-{index}"
            performed.append(f"{identifier}:{index}:{kind}")
            if kind == "answer":
                hook = chat_orchestrator.pre_repair_capture_hook
                assert hook is not None, "freeze must install the hook"
                hook(
                    f"pre-repair {identifier} turn {index}: 900 DZD.",
                    [_Document("Delivery charges - DZD\nStandard delivery: 900\n")],
                    correlation_id,
                )
                responses.append(_Response(correlation_id, f"final {identifier} turn {index}"))
            else:
                responses.append(
                    _Response(correlation_id, "I cannot help with that.", abstained=True)
                )
        return _Run(responses)

    import scripts.run_retrieval_canary as canary

    monkeypatch.setattr(canary, "run_pipeline_capture", _run)
    monkeypatch.setattr(
        comparison,
        "_count_model_calls",
        lambda: ({"calls": 0, "input_tokens": 0, "output_tokens": 0}, lambda: None),
    )
    # Fixed, clean provenance. The real one reads the working tree, and these
    # tests must not pass or fail depending on whether it happens to be dirty -
    # the dirty-tree refusal has its own test, which sets the flag explicitly.
    monkeypatch.setattr(
        comparison,
        "_provenance",
        lambda fixture_hash: {
            "harness_commit": "abc123",
            "harness_dirty": False,
            "fixture_sha256": fixture_hash,
            "opensearch_index": "askvera-policy-sections",
            "bedrock_model_id": "us.anthropic.claude-sonnet-4-5",
            "chunk_profile": "current",
            "generation_pointer_enabled": True,
        },
    )
    return performed


def _freeze(tmp_path, **kwargs):
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


CONVERSATION = "belgium-then-germany-market-continuity"


# --- turn accounting -------------------------------------------------------


def test_a_turn_that_never_reaches_repair_is_still_recorded(tmp_path, monkeypatch) -> None:
    """Omitting it is what shifted every later expectation."""
    _pipeline(monkeypatch, plan={CONVERSATION: ["refusal", "answer", "answer"]})

    payload = _freeze(tmp_path, cases_wanted=[CONVERSATION])

    assert payload["turns_recorded"] == 3
    assert [run["reached_repair"] for run in payload["runs"]] == [False, True, True]
    assert payload["turns_that_reached_repair"] == 2


def test_a_refusal_followed_by_an_answer_keeps_expectations_aligned(
    tmp_path, monkeypatch
) -> None:
    """The defect, stated as a test.

    Turn 0 refuses and fires no hook. Under hook-counting, turn 1's answer was
    filed as turn 0 and scored against turn 0's expectation.
    """
    _pipeline(monkeypatch, plan={CONVERSATION: ["refusal", "answer", "answer"]})

    runs = _freeze(tmp_path, cases_wanted=[CONVERSATION])["runs"]

    assert [run["turn_index"] for run in runs] == [0, 1, 2]
    for index, run in enumerate(runs):
        assert run["correlation_id"] == f"corr-{CONVERSATION}-{index}"
    # The answer captured at turn 1 is filed as turn 1, not turn 0.
    assert "turn 1" in runs[1]["answer"]


def test_an_answer_followed_by_a_refusal_marks_the_right_final_turn(
    tmp_path, monkeypatch
) -> None:
    """The other order, and the one that corrupted resume.

    The last CAPTURED turn is turn 0, but the last turn PERFORMED is turn 2.
    Marking the captured one complete would let resume treat a chain whose
    final turn never happened as finished.
    """
    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "refusal", "refusal"]})

    runs = _freeze(tmp_path, cases_wanted=[CONVERSATION])["runs"]

    assert [run["is_final_turn"] for run in runs] == [False, False, True]
    assert runs[-1]["reached_repair"] is False


def test_the_turn_count_is_the_requests_made_not_the_captures(tmp_path, monkeypatch) -> None:
    """--max-turns has to bound work actually performed."""
    _pipeline(monkeypatch, plan={CONVERSATION: ["refusal", "refusal", "answer"]})

    payload = _freeze(tmp_path, cases_wanted=[CONVERSATION])

    assert payload["turns_attempted_this_run"] == 3
    assert payload["turns_that_reached_repair"] == 1


def test_max_turns_counts_whole_cases_of_attempted_requests(tmp_path, monkeypatch) -> None:
    performed = _pipeline(
        monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]}
    )

    payload = _freeze(tmp_path, cases_wanted=[CONVERSATION], max_turns=2)

    assert payload["status"] == "max_turns reached"
    assert performed == [], "a case that would exceed the bound must not start"


def test_the_final_answer_is_kept_beside_the_pre_repair_text(tmp_path, monkeypatch) -> None:
    """They are different strings and only one of them is what a reader saw."""
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    run = _freeze(tmp_path)["runs"][0]

    assert run["answer"].startswith("pre-repair")
    assert run["final_answer"].startswith("final")


# --- the hook --------------------------------------------------------------


def test_the_capture_comes_from_the_hook_not_the_final_response(tmp_path, monkeypatch) -> None:
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    payload = _freeze(tmp_path)

    assert "900 DZD" in payload["runs"][0]["answer"]
    assert payload["captured_at_boundary"] == "pre_numeric_repair"


def test_the_hook_is_removed_afterwards(tmp_path, monkeypatch) -> None:
    from app.orchestrator import chat_orchestrator

    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path)

    assert chat_orchestrator.pre_repair_capture_hook is None


def test_the_hook_is_removed_even_when_the_run_fails(tmp_path, monkeypatch) -> None:
    from app.orchestrator import chat_orchestrator

    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]}, fail_after=1)

    with pytest.raises(RuntimeError):
        _freeze(tmp_path, cases_wanted=[CONVERSATION])

    assert chat_orchestrator.pre_repair_capture_hook is None


def test_grounding_is_not_disabled_during_capture() -> None:
    import inspect

    source = inspect.getsource(comparison.freeze)

    assert "unsupported_numeric_claims" not in source
    assert "Grounding is NOT disabled" in (inspect.getdoc(comparison.freeze) or "")


# --- checkpointing and resume ---------------------------------------------


def test_the_checkpoint_is_written_during_the_run(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]})
    _freeze(tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION])

    assert len(json.loads(checkpoint.read_text(encoding="utf-8"))["runs"]) == 3


def test_a_completed_case_is_not_paid_for_twice(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "frozen.json"
    performed = _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)
    assert len(performed) == 1

    payload = _freeze(tmp_path, checkpoint=checkpoint, resume=True)

    assert len(performed) == 1, "a completed case must not run again"
    assert payload["turns_recorded"] == 1


def test_an_incomplete_attempt_is_preserved_not_replaced(tmp_path, monkeypatch) -> None:
    """It is evidence of what was paid for and what happened.

    Deleting it and replaying would silently substitute new evidence for the
    record of the first attempt.
    """
    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]}, fail_after=2)
    with pytest.raises(RuntimeError):
        _freeze(tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION])

    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]})
    payload = _freeze(
        tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION], resume=True
    )

    superseded = [run for run in payload["runs"] if run.get("superseded")]
    fresh = [run for run in payload["runs"] if not run.get("superseded")]
    assert superseded, "the interrupted attempt must be kept as history"
    assert len(fresh) == 3, "and the chain captured again in full"


def test_a_resume_across_a_different_fixture_is_refused(tmp_path, monkeypatch) -> None:
    """Mixing two fixtures produces one file describing no experiment."""
    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["provenance"]["fixture_sha256"] = "a-different-fixture"
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        _freeze(tmp_path, checkpoint=checkpoint, resume=True)

    assert "fixture_sha256" in str(raised.value)


@pytest.mark.parametrize(
    "field", ["harness_commit", "opensearch_index", "bedrock_model_id", "chunk_profile"]
)
def test_a_resume_across_different_conditions_is_refused(tmp_path, monkeypatch, field) -> None:
    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["provenance"][field] = "something-else"
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        _freeze(tmp_path, checkpoint=checkpoint, resume=True)

    assert field in str(raised.value)


def test_the_resume_check_happens_before_any_model_call(tmp_path, monkeypatch) -> None:
    """An incompatible resume must cost nothing."""
    checkpoint = tmp_path / "frozen.json"
    performed = _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)
    calls_before = len(performed)

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["provenance"]["opensearch_index"] = "another-index"
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit):
        _freeze(tmp_path, checkpoint=checkpoint, resume=True, cases_wanted=["france-minimum-order"])

    assert len(performed) == calls_before


def test_a_dirty_tree_cannot_be_resumed_across(tmp_path, monkeypatch) -> None:
    """The commit can match while the code does not."""
    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["provenance"]["harness_dirty"] = True
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        _freeze(tmp_path, checkpoint=checkpoint, resume=True)

    assert "dirty" in str(raised.value)


def test_a_checkpoint_write_failure_surfaces(tmp_path, monkeypatch) -> None:
    """A silent write failure would leave a run that paid for nothing durable."""
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    def _fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _fail)

    with pytest.raises(OSError):
        _freeze(tmp_path)


# --- selection, provenance and accounting ---------------------------------


def test_a_case_that_is_not_in_the_fixture_is_refused() -> None:
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)

    with pytest.raises(SystemExit):
        comparison._select(cases, ["no-such-case"])


def test_selection_preserves_the_order_asked_for() -> None:
    import scripts.run_benchmark as benchmark

    cases, _ = benchmark.load_fixture(FIXTURE)
    wanted = ["france-minimum-order", "algeria-delivery-cost"]

    assert [case["id"] for case in comparison._select(cases, wanted)] == wanted


def test_the_capture_records_what_produced_it(tmp_path, monkeypatch) -> None:
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    provenance = _freeze(tmp_path)["provenance"]

    assert provenance["fixture_sha256"]
    for key in (
        "harness_commit",
        "harness_dirty",
        "opensearch_index",
        "bedrock_model_id",
        "chunk_profile",
    ):
        assert key in provenance


def test_model_calls_are_counted_rather_than_estimated(tmp_path, monkeypatch) -> None:
    """A turn limit bounds work, not spending. This counts what was invoked."""
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    payload = _freeze(tmp_path)

    for key in ("model_calls_this_run", "input_tokens_this_run", "output_tokens_this_run"):
        assert key in payload


def test_the_counter_wraps_the_client_and_restores_it() -> None:
    """Including retries, because it counts invocations rather than turns."""
    import inspect

    source = inspect.getsource(comparison._count_model_calls)

    assert "converse" in source
    assert "retries included" in source


def test_an_existing_capture_is_not_overwritten(tmp_path, capsys, monkeypatch) -> None:
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
