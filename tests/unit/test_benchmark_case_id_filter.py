"""Tests for --case-id: the runner's only per-case selector.

Without this flag the runner can select only "the first N cases" (--limit) or
whole intent groups (--intent-group); neither can isolate one held-out case for
a targeted live diagnostic run. These tests pin the flag's filtering order
(case-id, then intent-group, then limit), its fail-closed behaviour on an
unknown id, that it never weakens the held-out release validation (which still
runs over the whole loaded fixture), and that it changes nothing when absent.

Also covers the addition of "generation_lookup" to the runner's
_CAPTURED_RETRIEVAL_METADATA tuple.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load("run_benchmark")

BASE_CASE = {
    "question": "What is the minimum order?",
    "country": "US",
    "language": "en",
    "role": "active_distributor",
    "intent_group": "directory",
    "expected": {"kind": "answer", "must_contain": ["2 Case Credits"]},
    "source_evidence": "Policy section 4.2 states the minimum.",
    "provenance": "Dumped from the index on 2026-09-07.",
}


def _case(case_id: str, **overrides) -> dict:
    case = {**BASE_CASE, "id": case_id}
    case.update(overrides)
    return case


def _fixture(tmp_path: Path, cases: list[dict], **overrides) -> Path:
    payload = {"schema_version": 1, "cases": cases}
    payload.update(overrides)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(**overrides) -> dict:
    run = {
        "answer": "The minimum order is 2 Case Credits.",
        "turn_failures": [],
        "citations": 1,
        "abstained": False,
        "failure_layer": "",
        "finish_reason": "",
        "removed_numeric_claims": [],
        "removed_but_present_in_source": [],
        "top_title": "UK Policy Manual",
        "sections": ["4.2", "4.3"],
        "cited_sections": ["4.2"],
        "confidence": 0.9,
        "generation_input_tokens": 100,
        "generation_output_tokens": 20,
        "duration_ms": 500.0,
    }
    run.update(overrides)
    return run


def _replace_canary_import(monkeypatch) -> None:
    """Keep benchmark.main local by replacing its dynamically imported runner."""
    class Loader:
        def exec_module(self, _module):
            return None

    class Spec:
        loader = Loader()

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: Spec())
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda _: object())


def _offline_run(tmp_path, monkeypatch, argv_extra, run_case=None):
    artifact = tmp_path / "case-id-filter.json"
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", run_case or (lambda *_: _run()))
    monkeypatch.setattr(
        sys, "argv",
        ["run_benchmark.py", "--artifact", str(artifact), "--repeat", "1", *argv_extra],
    )
    exit_code = benchmark.main()
    saved = json.loads(artifact.read_text(encoding="utf-8")) if artifact.exists() else None
    return exit_code, saved, artifact


# --- selection ---------------------------------------------------------------


def test_one_case_id_selected_runs_only_that_case(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [_case("case-1"), _case("case-2"), _case("case-3")])
    exit_code, saved, _ = _offline_run(
        tmp_path, monkeypatch, ["--fixture", str(fixture), "--case-id", "case-2"],
    )

    assert exit_code == 0
    assert [case["id"] for case in saved["cases"]] == ["case-2"]
    assert saved["summary"]["case_ids_requested"] == ["case-2"]


def test_two_case_ids_selected_run_both_in_requested_order(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [_case("case-1"), _case("case-2"), _case("case-3")])
    exit_code, saved, _ = _offline_run(
        tmp_path, monkeypatch,
        ["--fixture", str(fixture), "--case-id", "case-3", "--case-id", "case-1"],
    )

    assert exit_code == 0
    assert [case["id"] for case in saved["cases"]] == ["case-3", "case-1"]
    assert saved["summary"]["case_ids_requested"] == ["case-3", "case-1"]


def test_case_id_then_intent_group_then_limit_order(tmp_path, monkeypatch):
    """--case-id selects first; --intent-group narrows it; --limit takes the first N of that."""
    fixture = _fixture(tmp_path, [
        _case("case-1", intent_group="directory"),
        _case("case-2", intent_group="policy"),
        _case("case-3", intent_group="directory"),
    ])
    exit_code, saved, _ = _offline_run(
        tmp_path, monkeypatch,
        [
            "--fixture", str(fixture),
            "--case-id", "case-1", "--case-id", "case-2", "--case-id", "case-3",
            "--intent-group", "directory",
            "--limit", "1",
        ],
    )

    assert exit_code == 0
    assert [case["id"] for case in saved["cases"]] == ["case-1"]


def test_case_id_narrowed_to_empty_by_intent_group_fails_closed(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [
        _case("case-1", intent_group="directory"),
        _case("case-2", intent_group="policy"),
    ])
    exit_code, saved, artifact = _offline_run(
        tmp_path, monkeypatch,
        [
            "--fixture", str(fixture),
            "--case-id", "case-1",
            "--intent-group", "policy",
        ],
    )

    assert exit_code == 2
    assert saved is None
    assert not artifact.exists()


# --- fail-closed on an unknown id ---------------------------------------------


def test_unknown_case_id_fails_closed_with_no_artifact(tmp_path, monkeypatch, capsys):
    fixture = _fixture(tmp_path, [_case("case-1"), _case("case-2")])
    exit_code, saved, artifact = _offline_run(
        tmp_path, monkeypatch,
        ["--fixture", str(fixture), "--case-id", "case-1", "--case-id", "nope-does-not-exist"],
    )

    assert exit_code == 2
    assert saved is None
    assert not artifact.exists()
    stderr = capsys.readouterr().err
    assert "nope-does-not-exist" in stderr
    assert "case-1" not in stderr.split("nope-does-not-exist")[0]  # only the unknown id is listed


def test_unknown_case_id_fails_before_ssm_or_model_work(tmp_path, monkeypatch):
    """The refusal must happen before importing the canary or touching settings."""
    fixture = _fixture(tmp_path, [_case("case-1")])
    called = {"canary_imported": False}

    def _poison_spec_from_file_location(*_args, **_kwargs):
        called["canary_imported"] = True
        raise AssertionError("canary must not be imported before case-id validation")

    monkeypatch.setattr(importlib.util, "spec_from_file_location", _poison_spec_from_file_location)
    monkeypatch.setattr(
        sys, "argv",
        ["run_benchmark.py", "--fixture", str(fixture), "--case-id", "unknown-id", "--repeat", "1"],
    )

    assert benchmark.main() == 2
    assert called["canary_imported"] is False


# --- held-out validation is unweakened ----------------------------------------


def test_full_pack_held_out_validation_still_runs_with_case_id(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [
        _case("ho-1", evaluation_set="held_out"),
        _case("ho-2", evaluation_set="held_out"),
        _case("ho-3", evaluation_set="development"),
    ])
    calls: list[dict] = []

    def fake_validate(payload):
        calls.append(payload)
        return []

    import scripts.validate_held_out_release as validator_module

    monkeypatch.setattr(validator_module, "validate", fake_validate)

    exit_code, saved, _ = _offline_run(
        tmp_path, monkeypatch,
        ["--fixture", str(fixture), "--case-id", "ho-2"],
    )

    assert exit_code == 0
    assert [case["id"] for case in saved["cases"]] == ["ho-2"]
    # The validator was handed the whole payload -- three cases -- not the
    # single case --case-id later selects.
    assert len(calls) == 1
    assert len(calls[0]["cases"]) == 3
    assert {case["id"] for case in calls[0]["cases"]} == {"ho-1", "ho-2", "ho-3"}


def test_full_pack_held_out_validation_runs_even_when_case_id_is_unknown(tmp_path, monkeypatch):
    """Validation of the whole fixture happens before case-id filtering, so it
    still runs (and the fixture is still proven release-ready) even though the
    run itself is refused afterwards for naming an id that does not exist."""
    fixture = _fixture(tmp_path, [
        _case("ho-1", evaluation_set="held_out"),
        _case("ho-2", evaluation_set="held_out"),
    ])
    calls: list[dict] = []

    def fake_validate(payload):
        calls.append(payload)
        return []

    import scripts.validate_held_out_release as validator_module

    monkeypatch.setattr(validator_module, "validate", fake_validate)

    exit_code, saved, artifact = _offline_run(
        tmp_path, monkeypatch,
        ["--fixture", str(fixture), "--case-id", "no-such-case"],
    )

    assert exit_code == 2
    assert saved is None
    assert not artifact.exists()
    assert len(calls) == 1
    assert len(calls[0]["cases"]) == 2


# --- dry run -------------------------------------------------------------------


def test_dry_run_with_case_id_reports_selection_and_writes_nothing(tmp_path, monkeypatch, capsys):
    fixture = _fixture(tmp_path, [_case("case-1"), _case("case-2"), _case("case-3")])
    artifact = tmp_path / "should-not-be-written.json"
    monkeypatch.setattr(sys, "argv", [
        "run_benchmark.py", "--fixture", str(fixture), "--dry-run",
        "--case-id", "case-1", "--case-id", "case-3",
        "--artifact", str(artifact), "--repeat", "2",
    ])

    exit_code = benchmark.main()
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["cases"] == 2
    assert report["runs"] == 4
    assert report["case_ids_requested"] == ["case-1", "case-3"]
    assert not artifact.exists()


def test_dry_run_unknown_case_id_fails_closed_and_writes_nothing(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [_case("case-1")])
    artifact = tmp_path / "should-not-be-written.json"
    monkeypatch.setattr(sys, "argv", [
        "run_benchmark.py", "--fixture", str(fixture), "--dry-run",
        "--case-id", "not-a-real-case",
        "--artifact", str(artifact),
    ])

    assert benchmark.main() == 2
    assert not artifact.exists()


# --- no behaviour change without the flag -------------------------------------


def test_no_case_id_flag_leaves_selection_and_summary_unchanged(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [_case("case-1"), _case("case-2")])
    exit_code, saved, _ = _offline_run(tmp_path, monkeypatch, ["--fixture", str(fixture)])

    assert exit_code == 0
    assert [case["id"] for case in saved["cases"]] == ["case-1", "case-2"]
    # Unconditional: present as [] when --case-id is absent, so a run without
    # the flag never has to be special-cased by a consumer of the summary.
    assert saved["summary"]["case_ids_requested"] == []
    assert saved["summary"]["completed_cases"] == 2


def test_dry_run_without_case_id_reports_the_same_keys_as_before_the_flag_existed(tmp_path, monkeypatch, capsys):
    fixture = _fixture(tmp_path, [_case("case-1")])
    monkeypatch.setattr(
        sys, "argv", ["run_benchmark.py", "--fixture", str(fixture), "--dry-run"],
    )

    assert benchmark.main() == 0
    report = json.loads(capsys.readouterr().out)
    # Unconditional: present as [] when --case-id is absent.
    assert report["case_ids_requested"] == []
    assert report["cases"] == 1


# --- generation_lookup capture -------------------------------------------------


def test_generation_lookup_is_captured_when_present_in_retrieval_metadata():
    from types import SimpleNamespace

    retrieval = SimpleNamespace(
        confidence=0.8,
        documents=[],
        metadata={"provider": "opensearch_section", "generation_lookup": {"generation_id": "gen-7"}},
    )

    record = benchmark.retrieval_record(retrieval)

    assert record["metadata"]["generation_lookup"] == {"generation_id": "gen-7"}


def test_generation_lookup_is_absent_when_not_in_retrieval_metadata():
    from types import SimpleNamespace

    retrieval = SimpleNamespace(
        confidence=0.8,
        documents=[],
        metadata={"provider": "opensearch_section"},
    )

    record = benchmark.retrieval_record(retrieval)

    assert "generation_lookup" not in record["metadata"]


def test_generation_lookup_is_in_the_captured_retrieval_metadata_tuple():
    assert "generation_lookup" in benchmark._CAPTURED_RETRIEVAL_METADATA
    # Membership only: another worker's reviewed change is free to append
    # further capture keys after this one, so position is not pinned here.
    assert benchmark._CAPTURED_RETRIEVAL_METADATA.count("generation_lookup") == 1
    # Every entry from before this change is still present and none was
    # renamed, checked as containment rather than an exact slice so a later
    # reviewed change is free to append further keys without breaking this.
    original_keys = {
        "provider", "candidate_count", "evidence_selector_applied", "evidence_selector_confidence",
        "evidence_selector_rejected", "top_source_directly_answers", "parent_bound_children",
        "conversation_intent", "conversation_subtype", "intent_confidence", "client_action",
        "global_documents_searched", "strong_local_match", "explicit_section_reference",
        "evidence_decision",
    }
    assert original_keys <= set(benchmark._CAPTURED_RETRIEVAL_METADATA)
    # No entry is captured twice under two names or accidentally duplicated.
    assert len(benchmark._CAPTURED_RETRIEVAL_METADATA) == len(set(benchmark._CAPTURED_RETRIEVAL_METADATA))
