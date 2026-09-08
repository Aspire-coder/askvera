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
    response without firing the capture hook, which is what an early return
    does in the real orchestrator.

    Turns go through AIOrchestrator.handle_chat, because that is what the real
    canary calls and what the harness wraps to emit turn events. A fake that
    bypassed it would leave the event path untested.
    """
    from app.orchestrator import chat_orchestrator

    performed: list[str] = []
    plans: dict[str, list[str]] = {}

    class _FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def handle_chat(self, body, correlation_id, *args, **kwargs):
            identifier = plans["current"]
            kinds = plan.get(identifier, ["answer"])
            index = len([entry for entry in performed if entry.startswith(f"{identifier}:")])
            kind = kinds[index] if index < len(kinds) else "answer"
            if fail_after is not None and len(performed) >= fail_after:
                raise RuntimeError("interrupted")
            performed.append(f"{identifier}:{index}:{kind}")
            if kind == "answer":
                hook = chat_orchestrator.pre_repair_capture_hook
                assert hook is not None, "freeze must install the hook"
                hook(
                    f"pre-repair {identifier} turn {index}: 900 DZD.",
                    [_Document("Delivery charges - DZD\nStandard delivery: 900\n")],
                    correlation_id,
                )
                return _Response(correlation_id, f"final {identifier} turn {index}")
            return _Response(correlation_id, "I cannot help with that.", abstained=True)

    def _run(case, sequence):
        identifier = case["id"]
        plans["current"] = identifier
        kinds = plan.get(identifier, ["answer"])
        responses = []
        # Drive handle_chat once per turn, as the canary does.
        orchestrator = chat_orchestrator.AIOrchestrator()
        for index in range(len(kinds)):
            responses.append(
                orchestrator.handle_chat(None, f"corr-{identifier}-{index}")
            )
        return _Run(responses)

    import scripts.run_retrieval_canary as canary

    monkeypatch.setattr(chat_orchestrator, "AIOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(canary, "run_pipeline_capture", _run)
    monkeypatch.setattr(
        comparison, "_instrument_usage", lambda: (_FakeMeter(), lambda: None)
    )
    # Fixed, clean provenance. The real one reads the working tree and the
    # index, and these tests must not depend on either - the dirty-tree and
    # corpus refusals have their own tests, which set those fields explicitly.
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
            "corpus_signature": "active=17896;generations=28;deadbeefdeadbeef",
        },
    )
    return performed


class _FakeMeter:
    def snapshot(self):
        return {
            "by_model": {},
            "application_calls": 0,
            "http_attempts": 0,
            "sdk_retry_attempts": 0,
            "calls_without_reported_tokens": 0,
            "note": "fake",
        }


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
    import os

    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    def _fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _fail)

    with pytest.raises(OSError):
        _freeze(tmp_path)


def test_a_failed_write_does_not_damage_the_previous_checkpoint(
    tmp_path, monkeypatch
) -> None:
    """The reason the swap is atomic.

    Writing in place means an interrupted write truncates the file that already
    held good turns. A temp file plus os.replace leaves either the old
    checkpoint or the new one, never half of either.
    """
    import os

    checkpoint = tmp_path / "frozen.json"
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})
    _freeze(tmp_path, checkpoint=checkpoint)
    good = checkpoint.read_text(encoding="utf-8")
    assert json.loads(good)["turns_recorded"] == 1

    _pipeline(monkeypatch, plan={"france-minimum-order": ["answer"]})
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        _freeze(
            tmp_path,
            checkpoint=checkpoint,
            cases_wanted=["france-minimum-order"],
            resume=True,
        )

    assert checkpoint.read_text(encoding="utf-8") == good


def test_the_checkpoint_is_replaced_atomically() -> None:
    import inspect

    source = inspect.getsource(comparison.freeze)

    assert "os.replace" in source
    assert "fsync" in source


def test_a_turn_that_starts_is_counted_even_if_it_never_returns(
    tmp_path, monkeypatch
) -> None:
    """Turn events come from the request, not from what the request produced.

    The previous exception path counted captures, so a refusal that preceded
    the failure, and the failed request itself, were both missing from the
    accounting - the run under-reported what it had spent.
    """
    checkpoint = tmp_path / "frozen.json"
    _pipeline(
        monkeypatch,
        plan={CONVERSATION: ["refusal", "answer", "answer"]},
        fail_after=2,
    )

    with pytest.raises(RuntimeError):
        _freeze(tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION])

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))

    # Two turns ran (a refusal and an answer) and the third failed.
    assert payload["turns_attempted_this_run"] == 3
    assert payload["turns_started"] == 3
    assert payload["turns_failed"] == 1
    assert payload["turns_completed"] == 2
    assert payload["turns_unaccounted"] == 0


def test_every_completed_turn_survives_an_interruption(tmp_path, monkeypatch) -> None:
    """Evidence is written when a turn completes, not when the chain returns.

    Records used to be built from the runner's return value, so a kill during a
    later turn lost every earlier turn's answer - the completion event survived
    and the text it described did not.

    Here turn 0 refuses, turn 1 answers, turn 2 fails. Both completed turns are
    on disk, including the refusal, which carries no evidence but is still part
    of the account of what ran.
    """
    checkpoint = tmp_path / "frozen.json"
    _pipeline(
        monkeypatch,
        plan={CONVERSATION: ["refusal", "answer", "answer"]},
        fail_after=2,
    )

    with pytest.raises(RuntimeError):
        _freeze(tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION])

    runs = json.loads(checkpoint.read_text(encoding="utf-8"))["runs"]
    kept = sorted(
        (run for run in runs if run.get("attempt_interrupted")),
        key=lambda run: run["turn_index"],
    )

    assert [run["turn_index"] for run in kept] == [0, 1]
    assert [run["reached_repair"] for run in kept] == [False, True]
    assert "900 DZD" in kept[1]["answer"]
    # A partial chain is history, never scored.
    assert all(run["superseded"] for run in kept)
    assert not any(run["is_final_turn"] for run in kept)


def test_an_earlier_turns_answer_is_on_disk_before_the_next_turn_runs(
    tmp_path, monkeypatch
) -> None:
    """The window that mattered: a kill during turn 2 must not cost turn 1."""
    checkpoint = tmp_path / "frozen.json"
    seen: list[int] = []

    _pipeline(monkeypatch, plan={CONVERSATION: ["answer", "answer", "answer"]})
    original = comparison._turn_record

    def _observing(**kwargs):
        # Before this turn's record is built, count what is already durable.
        if checkpoint.exists():
            seen.append(len(json.loads(checkpoint.read_text(encoding="utf-8"))["runs"]))
        return original(**kwargs)

    monkeypatch.setattr(comparison, "_turn_record", _observing)
    _freeze(tmp_path, checkpoint=checkpoint, cases_wanted=[CONVERSATION])

    # Turn 1 saw turn 0 already written; turn 2 saw both.
    assert seen == [0, 1, 2]


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
        "generation_pointer_enabled",
        "corpus_signature",
    ):
        assert key in provenance


def test_usage_is_reported_per_model_with_attempts_separated(tmp_path, monkeypatch) -> None:
    """A total across models cannot be priced, and calls are not HTTP attempts."""
    _pipeline(monkeypatch, plan={"algeria-delivery-cost": ["answer"]})

    usage = _freeze(tmp_path)["usage"]

    for key in (
        "by_model",
        "application_calls",
        "http_attempts",
        "sdk_retry_attempts",
        "calls_without_reported_tokens",
    ):
        assert key in usage


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
