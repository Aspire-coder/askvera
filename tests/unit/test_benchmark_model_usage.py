"""Capture-gated Bedrock Converse token-usage accumulator (LT5).

The benchmark runner recorded only the final generation call's token usage;
planner and evidence-selector Bedrock calls, which use the same
bedrock-runtime client and the same Converse API, were never counted, so
measured cost understated real spend.

These tests pin: capture is off by default and request-scoped; a handler
exception never raises into the call path; no prompt or response text is ever
recorded, only counts, model id and a coarse structural label; per-run and
summary totals are correct; and the dry-run report is unchanged except for the
documented additive ``case_ids_requested`` key (LT1/Fable ruling c, verified
here only for the token-usage change's blast radius).

No network: real boto3 clients are constructed (client construction is local)
but no AWS API call is ever made; one test manually emits the botocore event
to prove the handler is wired to the real event name without a network call.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest

from services import aws_clients

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("run_benchmark_model_usage", PROJECT_ROOT / "scripts" / "run_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the accumulator itself, in isolation --------------------------------------


def test_capture_disabled_by_default_records_nothing() -> None:
    """Outside capture_bedrock_usage(), the handler is a no-op: nothing to append to."""
    aws_clients._record_bedrock_converse_usage(
        parsed={"usage": {"inputTokens": 10, "outputTokens": 5}}, params={"modelId": "m1"}
    )
    # No context var set: get() returns None, so there is nothing to assert on
    # other than "this did not raise". A second call after a capture block
    # closes must also be silent.
    with aws_clients.capture_bedrock_usage() as records:
        pass
    assert records == []


def test_capture_records_only_while_the_context_is_open() -> None:
    with aws_clients.capture_bedrock_usage() as records:
        aws_clients._record_bedrock_converse_usage(
            parsed={"usage": {"inputTokens": 10, "outputTokens": 5}}, params={"modelId": "m1"}
        )
        assert len(records) == 1
    # After the block exits the context var is reset; a call made "later" (as
    # if from a straggling response) records nothing further into this list.
    aws_clients._record_bedrock_converse_usage(
        parsed={"usage": {"inputTokens": 99, "outputTokens": 99}}, params={"modelId": "m1"}
    )
    assert len(records) == 1


def test_capture_is_request_scoped_not_global() -> None:
    """Two sequential captures never see each other's records."""
    with aws_clients.capture_bedrock_usage() as first:
        aws_clients._record_bedrock_converse_usage(parsed={"usage": {"inputTokens": 1, "outputTokens": 1}}, params={})
    with aws_clients.capture_bedrock_usage() as second:
        aws_clients._record_bedrock_converse_usage(parsed={"usage": {"inputTokens": 2, "outputTokens": 2}}, params={})

    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["input_tokens"] == 1
    assert second[0]["input_tokens"] == 2


@pytest.mark.parametrize(
    "parsed,params",
    [
        (None, None),
        ({"usage": None}, {}),
        ({"usage": "not-a-dict"}, {"modelId": 5}),
        ("not-a-dict", "also-not-a-dict"),
        ({"usage": {"inputTokens": object()}}, {}),
    ],
)
def test_handler_swallows_exceptions_and_never_raises(parsed, params) -> None:
    with aws_clients.capture_bedrock_usage() as records:
        aws_clients._record_bedrock_converse_usage(parsed=parsed, params=params)
    # Malformed input either records nothing or records safely; either way the
    # call above must not have raised, which is what this test actually pins.
    assert isinstance(records, list)


def test_no_usage_field_records_nothing() -> None:
    with aws_clients.capture_bedrock_usage() as records:
        aws_clients._record_bedrock_converse_usage(parsed={"output": {"message": "irrelevant"}}, params={"modelId": "m1"})
    assert records == []


def test_records_hold_only_counts_model_id_and_a_structural_label_never_text() -> None:
    parsed = {
        "usage": {"inputTokens": 123, "outputTokens": 45},
        "output": {"message": {"role": "assistant", "content": [{"text": "the secret answer text"}]}},
        "stopReason": "end_turn",
    }
    params = {
        "modelId": "anthropic.claude-x",
        "messages": [{"role": "user", "content": [{"text": "the secret prompt text"}]}],
        "toolConfig": {"tools": [{"toolSpec": {"name": "evidence_selector"}}]},
    }

    with aws_clients.capture_bedrock_usage() as records:
        aws_clients._record_bedrock_converse_usage(parsed=parsed, params=params)

    assert len(records) == 1
    record = records[0]
    assert record == {
        "model_id": "anthropic.claude-x",
        "input_tokens": 123,
        "output_tokens": 45,
        "call_label": "evidence_selector",
    }
    serialized = json.dumps(record)
    assert "secret" not in serialized
    assert "text" not in serialized


def test_call_label_falls_back_to_generic_without_a_tool_name() -> None:
    with aws_clients.capture_bedrock_usage() as records:
        aws_clients._record_bedrock_converse_usage(
            parsed={"usage": {"inputTokens": 1, "outputTokens": 1}}, params={"modelId": "m1", "messages": []}
        )
    assert records[0]["call_label"] == "converse"


# --- wired to the real event name, no network -----------------------------------


def test_handler_is_reachable_via_the_real_botocore_event_name() -> None:
    """Register exactly as AwsClients.__init__ does; emit the real event; no network call is made."""
    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    client.meta.events.register("after-call.bedrock-runtime.Converse", aws_clients._record_bedrock_converse_usage)

    with aws_clients.capture_bedrock_usage() as records:
        client.meta.events.emit(
            "after-call.bedrock-runtime.Converse",
            parsed={"usage": {"inputTokens": 7, "outputTokens": 3}},
            params={"modelId": "m1"},
        )

    assert records == [{"model_id": "m1", "input_tokens": 7, "output_tokens": 3, "call_label": "converse"}]


# --- run_benchmark: capture_record, bedrock_usage_report and diagnostic_summary --
#
# score_run and summarise are pinned by AST hash in test_benchmark_capture.py
# (SCORE_RUN_AST_SHA256 / SUMMARISE_AST_SHA256) and run_case_once's returned
# run dict is pinned to exactly LEGACY_RUN_FIELDS plus
# removed_but_present_in_source_pinned and capture -- so token usage is not a
# new top-level run field or a change to summarise(). It lives inside
# capture_record()'s "capture" dict (capture_record is not AST-pinned; only
# its "version" key is asserted elsewhere) and is totalled by the new
# bedrock_usage_report(), folded into diagnostic_summary()'s additive summary
# blocks -- never merged over a summarise() key.


def test_capture_record_folds_bedrock_usage_records_into_the_capture_dict() -> None:
    benchmark = _load_benchmark()
    run = SimpleNamespace(retrieval=None, response=SimpleNamespace(answer="", metadata={}, citations=[]), prior_responses=())

    capture = benchmark.capture_record(
        run,
        "enabled",
        [
            {"model_id": "m1", "input_tokens": 10, "output_tokens": 2, "call_label": "converse"},
            {"model_id": "m1", "input_tokens": 5, "output_tokens": 1, "call_label": "evidence_selector"},
        ],
    )

    assert capture["bedrock_usage"] == {
        "input_tokens": 15,
        "output_tokens": 3,
        "call_count": 2,
        "calls": [
            {"model_id": "m1", "input_tokens": 10, "output_tokens": 2, "call_label": "converse"},
            {"model_id": "m1", "input_tokens": 5, "output_tokens": 1, "call_label": "evidence_selector"},
        ],
    }


def test_capture_record_without_usage_records_is_all_zero() -> None:
    benchmark = _load_benchmark()
    run = SimpleNamespace(retrieval=None, response=SimpleNamespace(answer="", metadata={}, citations=[]), prior_responses=())

    capture = benchmark.capture_record(run, "enabled", None)

    assert capture["bedrock_usage"] == {"input_tokens": 0, "output_tokens": 0, "call_count": 0, "calls": []}


def _case_with_bedrock_usage(*usages: dict) -> dict:
    runs = [{"capture": {"bedrock_usage": usage}} for usage in usages]
    return {"id": "c1", "runs": runs}


def test_bedrock_usage_report_totals_are_correct() -> None:
    benchmark = _load_benchmark()
    usage_a = {"input_tokens": 30, "output_tokens": 6, "call_count": 2, "calls": []}
    usage_b = {"input_tokens": 15, "output_tokens": 3, "call_count": 1, "calls": []}
    results = [_case_with_bedrock_usage(usage_a), _case_with_bedrock_usage(usage_b)]

    report = benchmark.bedrock_usage_report(results, rates=None)

    assert report == {"input_tokens": 45, "output_tokens": 9, "calls": 3}


def test_bedrock_usage_report_cost_uses_the_full_totals_when_rates_given() -> None:
    benchmark = _load_benchmark()
    usage = {"input_tokens": 1_000_000, "output_tokens": 2_000_000, "call_count": 1, "calls": []}
    results = [_case_with_bedrock_usage(usage)]

    report = benchmark.bedrock_usage_report(results, rates={"input": 3.0, "output": 15.0})

    assert report["measured_cost_usd"] == pytest.approx(3.0 + 30.0)
    assert report["cost_per_case_usd"] == pytest.approx(33.0)


def test_bedrock_usage_report_of_nothing_captured_is_zero_and_free() -> None:
    """A run with no real bedrock-runtime client (e.g. a stubbed canary) totals zero, not an error."""
    benchmark = _load_benchmark()
    results = [_case_with_bedrock_usage({"input_tokens": 0, "output_tokens": 0, "call_count": 0, "calls": []})]

    report = benchmark.bedrock_usage_report(results, rates={"input": 3.0, "output": 15.0})

    assert report["input_tokens"] == 0
    assert report["measured_cost_usd"] == 0.0


def test_diagnostic_summary_carries_bedrock_usage_as_a_new_additive_key() -> None:
    """diagnostic_summary's block is additive over summarise()'s keys, which it never touches (see the AST pin)."""
    benchmark = _load_benchmark()
    results = [_case_with_bedrock_usage({"input_tokens": 7, "output_tokens": 1, "call_count": 1, "calls": []})]

    additive = benchmark.diagnostic_summary(results, identity={}, rates=None)

    # A key summarise() also produces (per its docstring/comment, this block
    # is "never merged over a key summarise() produces"); bedrock_usage is new.
    assert "run_identity" in additive
    assert additive["bedrock_usage"] == {"input_tokens": 7, "output_tokens": 1, "calls": 1}


# --- dry run is unchanged except the documented additive key --------------------


def test_dry_run_report_carries_no_bedrock_usage_keys(tmp_path, monkeypatch, capsys) -> None:
    """A dry run makes no model calls, so no bedrock usage key of any kind appears."""
    benchmark = _load_benchmark()
    fixture = {
        "schema_version": 1,
        "cases": [
            {
                "id": "c1", "question": "q", "country": "US", "language": "en", "role": "active_distributor",
                "intent_group": "g", "evaluation_set": "development",
                "expected": {"kind": "answer", "must_contain": ["x"]},
                "source_evidence": "s", "provenance": "p",
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py", "--fixture", str(fixture_path), "--dry-run"])

    exit_code = benchmark.main()

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert not [key for key in report if "bedrock" in key.lower()]
    assert report["case_ids_requested"] == []
