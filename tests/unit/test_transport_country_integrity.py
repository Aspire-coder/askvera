"""Transported held-out cases must not be counted as run in their declared session.

ORCH2-A-HARNESS-INTEGRITY. The request-country overlay sends seven frozen
held-out cases from ``US`` because their declared session countries (GH, TZ,
BJ, PL, PT) are not countries the chat API accepts. Scoring stays bound to the
frozen expectation, which is correct. What the runner did not say is which
cases were transported, or that five of the pack's twelve "new session
countries" were never used as a session at all. The per-case field
``source_country`` also holds the *declared session*, not the source market
(case 23 reads ``PT`` although its source market is ``IT``).

These tests pin an additive, versioned disclosure: a per-case ``transport``
record and a summary ``transport_report`` that counts coverage by the session
actually requested. No existing field or score changes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FROZEN_PACK = PROJECT_ROOT / "tests" / "fixtures" / "held_out_source_linked_pack.json"
TRANSPORT_OVERLAY = PROJECT_ROOT / "tests" / "fixtures" / "held_out_request_country_overrides.json"
FROZEN_PACK_SHA256 = "5eb49a410c37a4f87ef3b60c922bd06dede92007b48e021d6f28fb77ee1ff208"
OVERLAY_SHA256 = "cf626c03b5d431d77121e623b757d5f65d818f66b6bdb036ece29283cd456c61"

CASE_08 = "ho-slp-08-gb-must-not-get-canada-discrepancy-rule-en"
CASE_22 = "ho-slp-22-austria-must-not-get-italy-promoter-commission-en"
CASE_23 = "ho-slp-23-portugal-must-not-get-italy-premium-customer-commission-en"
GLOBAL_TRANSPORTS = {
    "ho-slp-01-ghana-preferred-customer-signup-order-en": "GH",
    "ho-slp-02-ghana-prospect-fbo-first-order-conditions-en": "GH",
    "ho-slp-04-tanzania-foreign-then-local-bonus-follow-up-en": "TZ",
    "ho-slp-05-benin-accented-fbo-minimum-order-fr": "BJ",
    "ho-slp-20-poland-first-order-and-delivery-cost-en": "PL",
    "ho-slp-21-poland-unregistered-fbo-annual-bonus-payout-en": "PL",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load("run_benchmark")


def _dry_run(monkeypatch, capsys, with_overlay: bool = True) -> dict:
    argv = ["run_benchmark.py", "--fixture", str(FROZEN_PACK), "--dry-run", "--repeat", "1"]
    if with_overlay:
        argv += ["--transport-overrides", str(TRANSPORT_OVERLAY)]
    monkeypatch.setattr(sys, "argv", argv)
    assert benchmark.main() == 0
    return json.loads(capsys.readouterr().out)


def _fake_run(**overrides) -> dict:
    run = {
        "answer": "That local company policy is only available to readers in that market.",
        "turn_failures": [],
        "citations": 0,
        "abstained": True,
        "failure_layer": "",
        "finish_reason": "",
        "removed_numeric_claims": [],
        "removed_but_present_in_source": [],
        "top_title": "",
        "sections": [],
        "cited_sections": [],
        "confidence": 0.5,
        "generation_input_tokens": 10,
        "generation_output_tokens": 5,
        "duration_ms": 100.0,
    }
    run.update(overrides)
    return run


def _replace_canary_import(monkeypatch) -> None:
    class Loader:
        def exec_module(self, _module):
            return None

    class Spec:
        loader = Loader()

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: Spec())
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda _: object())


def _offline_full_run(tmp_path, monkeypatch, run_case=None) -> tuple[int, dict]:
    artifact = tmp_path / "transport-integrity.json"
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", run_case or (lambda *_: _fake_run()))
    monkeypatch.setattr(sys, "argv", [
        "run_benchmark.py", "--fixture", str(FROZEN_PACK),
        "--transport-overrides", str(TRANSPORT_OVERLAY),
        "--artifact", str(artifact), "--repeat", "1",
    ])
    exit_code = benchmark.main()
    return exit_code, json.loads(artifact.read_text(encoding="utf-8"))


def test_frozen_inputs_are_unchanged():
    assert hashlib.sha256(FROZEN_PACK.read_bytes()).hexdigest() == FROZEN_PACK_SHA256
    assert hashlib.sha256(TRANSPORT_OVERLAY.read_bytes()).hexdigest() == OVERLAY_SHA256


def test_the_dry_run_names_every_transported_case_and_its_declared_session(monkeypatch, capsys):
    report = _dry_run(monkeypatch, capsys)["transport_report"]

    assert report["version"] == 1
    transported = {entry["id"]: entry for entry in report["transported_cases"]}
    assert set(transported) == set(GLOBAL_TRANSPORTS) | {CASE_23}
    for identifier, declared in GLOBAL_TRANSPORTS.items():
        assert transported[identifier]["declared_session_country"] == declared
        assert transported[identifier]["request_country"] == "US"
        assert transported[identifier]["source_market"] == "GLOBAL"
        assert transported[identifier]["mapping"] == "request_countries"
    assert transported[CASE_23] == {
        "id": CASE_23,
        "declared_session_country": "PT",
        "request_country": "US",
        "source_market": "IT",
        "mapping": "abstention_request_countries",
        "expected_kind": "abstain",
        "coverage": ["local_policy", "cross_market_refusal", "new_country"],
        "cross_market_after_transport": True,
    }


def test_new_session_coverage_is_counted_by_the_session_actually_requested(monkeypatch, capsys):
    """Five of the twelve declared new session countries never ran as a session."""
    sessions = _dry_run(monkeypatch, capsys)["transport_report"]["coverage_as_executed"]["new_country_sessions"]

    assert sessions["declared"] == sorted(["GH", "TZ", "BJ", "CA", "IT", "FI", "NO", "NL", "LU", "PL", "AT", "PT"])
    assert sessions["executed_as_declared"] == ["AT", "CA", "FI", "IT", "LU", "NL", "NO"]
    assert sessions["transported_only"] == ["BJ", "GH", "PL", "PT", "TZ"]


def test_a_transported_cross_market_refusal_is_reported_separately(monkeypatch, capsys):
    report = _dry_run(monkeypatch, capsys)["transport_report"]
    refusals = report["coverage_as_executed"]["cross_market_refusal"]

    assert refusals["declared"] == [CASE_08, CASE_22, CASE_23]
    assert refusals["executed_as_declared"] == [CASE_08, CASE_22]
    assert refusals["transported"] == [CASE_23]
    tags = report["coverage_as_executed"]["tags"]
    assert tags["cross_market_refusal"] == {"declared": 3, "executed_as_declared": 2, "transported": 1}
    assert tags["new_country"] == {"declared": 18, "executed_as_declared": 11, "transported": 7}


def test_executed_session_countries_are_disclosed(monkeypatch, capsys):
    report = _dry_run(monkeypatch, capsys)["transport_report"]

    assert report["executed_session_countries"] == ["AT", "CA", "FI", "GB", "IT", "LU", "NL", "NO", "US"]
    assert report["declared_sessions_never_executed"] == ["BJ", "GH", "PL", "PT", "TZ"]


def test_without_an_overlay_nothing_is_reported_as_transported(monkeypatch, capsys):
    report = _dry_run(monkeypatch, capsys, with_overlay=False)["transport_report"]

    assert report["transported_cases"] == []
    sessions = report["coverage_as_executed"]["new_country_sessions"]
    assert sessions["executed_as_declared"] == sessions["declared"]
    assert sessions["transported_only"] == []


def test_release_validator_counts_declared_sessions_not_executed_ones(monkeypatch, capsys):
    """Characterises the gap: READY on the pack, below the minimum as executed.

    The release validator is frozen and read-only. It judges the pack's
    structure, so it is right to count declared sessions; the runner is the
    only place that knows what was executed, so it must say so.
    """
    validator = _load("validate_held_out_release")
    payload = json.loads(FROZEN_PACK.read_text(encoding="utf-8"))
    executed = _dry_run(monkeypatch, capsys)["transport_report"]["coverage_as_executed"]

    assert validator.validate(payload) == []
    assert len(executed["new_country_sessions"]["declared"]) == validator.MINIMUMS["new_country"]
    assert len(executed["new_country_sessions"]["executed_as_declared"]) < validator.MINIMUMS["new_country"]


def test_each_case_record_carries_its_transport_and_keeps_the_legacy_field(tmp_path, monkeypatch):
    exit_code, saved = _offline_full_run(tmp_path, monkeypatch)
    cases = {case["id"]: case for case in saved["cases"]}

    assert exit_code == 0
    assert cases[CASE_23]["transport"] == {
        "version": 1,
        "transported": True,
        "declared_session_country": "PT",
        "request_country": "US",
        "source_market": "IT",
        "mapping": "abstention_request_countries",
    }
    assert cases[CASE_22]["transport"]["transported"] is False
    assert cases[CASE_22]["transport"]["mapping"] is None
    assert cases[CASE_22]["transport"]["request_country"] == "AT"
    # Unchanged, for comparison with the frozen artifacts: this legacy field
    # has always held the declared session country, not the source market.
    assert cases[CASE_23]["source_country"] == "PT"
    assert cases[CASE_23]["request_country"] == "US"
    assert sum(1 for case in saved["cases"] if case["transport"]["transported"]) == 7


def test_the_summary_carries_the_report_and_scoring_is_unchanged(tmp_path, monkeypatch):
    exit_code, saved = _offline_full_run(tmp_path, monkeypatch)
    summary = saved["summary"]

    assert exit_code == 0
    assert summary["transport_report"]["version"] == 1
    assert summary["transport_override_cases"] == 7
    # Every pre-existing scoring figure is exactly what summarise() computes.
    legacy = benchmark.summarise(saved["cases"], None)
    for key, value in legacy.items():
        assert summary[key] == value


def test_a_stopped_run_still_discloses_the_transport(tmp_path, monkeypatch):
    calls = {"count": 0}

    def run_case(*_):
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("network stopped")
        return _fake_run()

    artifact = tmp_path / "transport-integrity.json"
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    monkeypatch.setattr(sys, "argv", [
        "run_benchmark.py", "--fixture", str(FROZEN_PACK),
        "--transport-overrides", str(TRANSPORT_OVERLAY),
        "--artifact", str(artifact), "--repeat", "1",
    ])

    assert benchmark.main() == 1
    summary = json.loads(artifact.read_text(encoding="utf-8"))["summary"]
    assert summary["status"] == "stopped"
    assert len(summary["transport_report"]["transported_cases"]) == 7


@pytest.mark.parametrize("identifier", [CASE_23, *GLOBAL_TRANSPORTS])
def test_transport_never_changes_the_frozen_expectation(identifier):
    cases, fixture_hash = benchmark.load_fixture(FROZEN_PACK)
    overrides, _ = benchmark.load_transport_overrides(TRANSPORT_OVERLAY, cases, fixture_hash)
    case = next(case for case in cases if case["id"] == identifier)

    execution_case, request_country = benchmark.execution_case_for_request(case, overrides)

    assert request_country == "US"
    assert execution_case["expected"] == case["expected"]
    assert execution_case["coverage"] == case["coverage"]
