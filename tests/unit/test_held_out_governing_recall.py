"""Offline governing-passage recall, outcome labels and pinned repair rescoring.

The held-out comparison scored correctness only, so "found the governing
passage" and "answered correctly" were never separated. These tests pin the
recall conventions (strict, as retrieval_hit is scored; parent-covers-child,
as citations are matched), that recall at 30 is never estimated from data
that was not captured, and that the tool only reads.

No network: artifacts, fixtures and extractions are built under tmp_path.
"""

from __future__ import annotations

import hashlib
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


recall = _load("held_out_governing_recall")
benchmark = recall.benchmark()

ANSWER_CASE = {
    "id": "ho-slp-16-norway-reapplication",
    "language": "no",
    "expected": {"kind": "answer", "required_sections": ["NO:17.08-c"], "must_cite": True, "must_contain": ["x"]},
}
ABSTAIN_CASE = {"id": "ho-slp-08-gb-refusal", "language": "en", "expected": {"kind": "abstain"}}


def _keys(*pairs: tuple[str, str]) -> list[str]:
    return benchmark._section_keys(list(pairs))


def test_rank_groups_pair_each_bare_key_with_its_own_qualified_key():
    keys = _keys(("2", "DK"), ("2", "SE"), ("sponsoring-001-algeria", "GLOBAL"))

    assert recall.rank_groups(keys) == [
        ["2", "DK:2"], ["2", "SE:2"], ["sponsoring-001-algeria", "GLOBAL:sponsoring-001-algeria"],
    ]


def test_a_retrieved_parent_counts_only_under_the_stated_parent_reading():
    """Case 16's shape: the parent 17.08 was retrieved, the governing child 17.08-c was not."""
    run = {"sections": _keys(("17.09-c", "NO"), ("17.08", "NO")), "retrieval_hit": False}

    result = recall.run_recall(run, ["NO:17.08-c"])

    assert result["strict_at_1"] == 0.0 and result["strict_at_5"] == 0.0
    assert result["parent_covers_child_at_1"] == 0.0
    assert result["parent_covers_child_at_5"] == 1.0
    assert result["strict_at_5_agrees_with_recorded_retrieval_hit"] is True


@pytest.mark.parametrize("sections", [
    [("17.08", "SE")],        # the same parent id in another market
    [("17.09", "NO")],        # a sibling
    [("17.08-d", "NO")],      # a sibling child
])
def test_nothing_but_the_same_market_parent_or_the_section_itself_covers_it(sections):
    result = recall.run_recall({"sections": _keys(*sections)}, ["NO:17.08-c"])

    assert result["strict_at_5"] == 0.0
    assert result["parent_covers_child_at_5"] == 0.0


def test_rank_one_is_the_first_retrieved_document_only():
    run = {"sections": _keys(("sponsoring-081-norway", "GLOBAL"), ("17.08-c", "NO"))}

    result = recall.run_recall(run, ["NO:17.08-c"])

    assert result["strict_at_1"] == 0.0
    assert result["strict_at_5"] == 1.0


def test_only_the_first_five_documents_count_at_five():
    sections = [(f"9.0{number}", "NO") for number in range(5)] + [("17.08-c", "NO")]

    assert recall.run_recall({"sections": _keys(*sections)}, ["NO:17.08-c"])["strict_at_5"] == 0.0


def test_recall_at_30_is_not_estimated_without_captured_candidates():
    result = recall.run_recall({"sections": _keys(("17.08-c", "NO"))}, ["NO:17.08-c"])

    assert result["parent_covers_child_at_30"] == "not measurable: candidates not captured"


def test_recall_at_30_uses_the_first_thirty_captured_candidates():
    filler = [{"section": f"1.{number}", "country": "NO"} for number in range(30)]
    captured = {"sections": [], "capture": {"final_retrieval": {"candidate_sections": [
        *filler[:10], {"section": "17.08", "country": "NO"}, *filler[10:],
    ]}}}
    beyond = {"sections": [], "capture": {"final_retrieval": {"candidate_sections": [
        *filler, {"section": "17.08", "country": "NO"},
    ]}}}

    assert recall.run_recall(captured, ["NO:17.08-c"])["parent_covers_child_at_30"] == 1.0
    assert recall.run_recall(beyond, ["NO:17.08-c"])["parent_covers_child_at_30"] == 0.0


@pytest.mark.parametrize("sections", [
    [("17.08-c", "NO")],
    [("17.08", "NO")],
    [("17.08-c", "SE")],
    [],
])
def test_strict_recall_at_five_is_the_runners_retrieval_hit(sections):
    """Neighbour check: the strict reading must never drift from score_run."""
    run = {**_scorable_run(), "sections": _keys(*sections)}
    scored = benchmark.score_run({**ANSWER_CASE, "expected": {**ANSWER_CASE["expected"]}}, run)

    result = recall.run_recall(scored, ["NO:17.08-c"])

    assert (result["strict_at_5"] == 1.0) is scored["retrieval_hit"]


def _scorable_run() -> dict:
    return {
        "answer": "x", "turn_failures": [], "citations": 1, "abstained": False, "failure_layer": "",
        "removed_numeric_claims": [], "removed_but_present_in_source": [], "top_title": "",
        "sections": [], "cited_sections": [], "confidence": 0.5, "generation_input_tokens": 1,
        "generation_output_tokens": 1, "duration_ms": 1.0,
    }


def _artifact(runs_by_case: dict[str, list[dict]]) -> dict:
    return {"summary": {"correct": "0/0"}, "cases": [
        {"id": identifier, "runs": runs} for identifier, runs in runs_by_case.items()
    ]}


def test_the_report_states_denominators_and_leaves_abstentions_unmeasured():
    pack_cases = {ANSWER_CASE["id"]: ANSWER_CASE, ABSTAIN_CASE["id"]: ABSTAIN_CASE}
    artifact = _artifact({
        ANSWER_CASE["id"]: [{"sections": _keys(("17.08-c", "NO")), "retrieval_hit": True}],
        ABSTAIN_CASE["id"]: [{"sections": _keys(("17.2", "UK"))}],
    })

    report = recall.recall_report(artifact, pack_cases)

    aggregate = report["aggregate"]
    assert (aggregate["cases_measured"], aggregate["cases_not_applicable"], aggregate["runs_measured"]) == (1, 1, 1)
    assert aggregate["strict_at_5"]["full_hits"] == "1/1"
    assert aggregate["parent_covers_child_at_30"] == "not measurable: candidates not captured"
    assert report["cases"][1] == {"id": ABSTAIN_CASE["id"], "status": "not_applicable", "reason": "expects an abstention"}


def test_an_artifact_case_the_fixture_does_not_know_is_refused():
    with pytest.raises(ValueError, match="not in the fixture"):
        recall.recall_report(_artifact({"unknown": [{"sections": []}]}), {ANSWER_CASE["id"]: ANSWER_CASE})


def test_outcomes_are_labelled_offline_for_artifacts_that_predate_the_label():
    # Updated 2026-09-18 (Phase 3, Lane 4): config/conversation_routes.json
    # now carries a reviewed "cross_market_policy_scope" key for "en" (the
    # CX_LANES.md message-key table), which scripts/run_benchmark.py's
    # classify_outcome already looked up via _cross_market_scope_copy before
    # this key existed anywhere. That reviewed copy is what a live run
    # produces now, not the orchestrator's English-only fallback constant
    # (CROSS_MARKET_POLICY_SCOPE_RESPONSE), so this offline-labelling fixture
    # uses the same reviewed copy classify_outcome resolves.
    from app.evidence import configured_conversation_response

    cross_market_scope_copy = configured_conversation_response("cross_market_policy_scope", "en")[0]

    pack_cases = {ABSTAIN_CASE["id"]: ABSTAIN_CASE, ANSWER_CASE["id"]: ANSWER_CASE}
    recorded = {"outcome": "answered", "basis": "recorded", "declining_copy": None}
    artifact = _artifact({
        ABSTAIN_CASE["id"]: [{"answer": cross_market_scope_copy, "abstained": True, "passed": True}],
        ANSWER_CASE["id"]: [{"answer": "x", "passed": False, "diagnostic_outcome": recorded}],
    })

    report = recall.outcomes_report(artifact, pack_cases)

    first, second = report["runs_detail"]
    assert (first["outcome"], first["label_source"]) == ("foreign_policy_refusal", "computed_offline")
    assert (second["outcome"], second["label_source"]) == ("answered", "recorded_by_runner")
    assert report["counts"]["foreign_policy_refusal"] == 1
    assert "not manual adjudication" in report["method"]


def _extraction_root(tmp_path: Path) -> Path:
    folder = tmp_path / "outputs" / "chunk-comparison-full" / "current" / "NO" / "no"
    folder.mkdir(parents=True)
    (folder / "policy.sections.jsonl").write_text(
        json.dumps({"section_id": "17.01", "content": "Du må være minst 18 år for å bli FBO."}) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_removed_figures_are_rescored_with_each_named_function(tmp_path):
    from app.validation.validators.numeric_grounding_validator import numbers_present_in_sources

    root = _extraction_root(tmp_path)
    case = {**ANSWER_CASE, "id": "ho-slp-24-norway-age"}
    artifact = _artifact({case["id"]: [{
        "removed_numeric_claims": ["18", "99"],
        "removed_but_present_in_source": ["18", "99"],
        "sections": _keys(("17.01", "NO"), ("9.99", "NO")),
    }]})
    functions = {
        "application": numbers_present_in_sources,
        "everything": lambda numbers, documents: dict.fromkeys(numbers, True),
    }

    report = recall.pinned_repair_report(artifact, {case["id"]: case}, recall.ExtractionIndex(root, {}), functions)

    row = report["runs_detail"][0]
    assert row["present_by_function"] == {"application": ["18"], "everything": ["18", "99"]}
    assert row["sections_unavailable"] == ["NO:9.99"]
    assert report["incomplete_rows"] == [f"{case['id']}#1"]
    assert report["aggregate"]["application"]["repair_removed_supported_figure"] == "1/1 (100.0%)"


def test_the_cli_writes_a_versioned_report_once_and_never_replaces_it(tmp_path):
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"cases": [ANSWER_CASE]}), encoding="utf-8")
    artifact = tmp_path / "results.json"
    artifact_bytes = json.dumps(_artifact({ANSWER_CASE["id"]: [{"sections": [], "retrieval_hit": False}]})).encode()
    artifact.write_bytes(artifact_bytes)
    output = tmp_path / "report.json"
    argv = ["--artifact", f"B={artifact}", "--fixture", str(pack), "--output", str(output)]

    assert recall.main(argv) == 0
    written = output.read_bytes()
    report = json.loads(written)
    assert report["version"] == recall.REPORT_VERSION
    assert report["artifacts"]["B"]["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert report["artifacts"]["B"]["pinned_repair"] == "not computed: no --extraction-root given"

    assert recall.main(argv) == 2
    assert output.read_bytes() == written
    assert artifact.read_bytes() == artifact_bytes


def test_the_cli_refuses_an_unlabelled_artifact(tmp_path, capsys):
    assert recall.main(["--artifact", str(tmp_path / "results.json")]) == 2
    assert "LABEL=PATH" in capsys.readouterr().err


# --- the report makes no model call --------------------------------------------------

UNREVIEWED_COPY_LOCALES = ("fi", "it", "no", "fr", "nl")


@pytest.fixture
def translation_forbidden(monkeypatch):
    import app.evidence as evidence
    import services.controlled_copy as controlled_copy

    attempts: list[tuple] = []

    def forbidden(*args, **_kwargs):
        attempts.append(args)
        raise AssertionError(f"copy translation attempted: {args[1:]}")

    def no_clients(*_args, **_kwargs):
        attempts.append(("get_aws_clients",))
        raise AssertionError("an AWS client was requested")

    monkeypatch.setattr(evidence, "localize_reviewed_copy", forbidden)
    monkeypatch.setattr(controlled_copy, "localize_reviewed_copy", forbidden)
    monkeypatch.setattr(controlled_copy, "get_aws_clients", no_clients)
    return attempts


def _refusal_artifact() -> tuple[dict, dict]:
    from app.evidence import configured_conversation_response

    pack_cases, runs = {}, {}
    for number, language in enumerate(UNREVIEWED_COPY_LOCALES):
        identifier = f"ho-slp-9{number}-{language}-refusal"
        pack_cases[identifier] = {"id": identifier, "language": language, "expected": {"kind": "abstain"}}
        runs[identifier] = [
            {"answer": configured_conversation_response("insufficient_evidence", language)[0],
             "abstained": True, "sections": [], "passed": True},
            {"answer": configured_conversation_response("catalogue_scope", language)[0],
             "abstained": True, "sections": ["X:1"], "passed": True},
        ]
    return _artifact(runs), pack_cases


def test_the_outcomes_report_asks_for_no_translation_in_any_locale(translation_forbidden):
    artifact, pack_cases = _refusal_artifact()

    report = recall.outcomes_report(artifact, pack_cases)

    assert [row["outcome"] for row in report["runs_detail"]] == ["retrieval_failure", "out_of_scope_refusal"] * 5
    assert translation_forbidden == []


def test_the_cli_report_states_that_no_translation_was_attempted(tmp_path, translation_forbidden):
    artifact, pack_cases = _refusal_artifact()
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"cases": list(pack_cases.values())}), encoding="utf-8")
    results = tmp_path / "results.json"
    results.write_text(json.dumps(artifact), encoding="utf-8")
    output = tmp_path / "report.json"

    assert recall.main(["--artifact", f"A={results}", "--fixture", str(pack), "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["translation_attempts_blocked"] == 0
    assert report["artifacts"]["A"]["outcomes"]["counts"]["retrieval_failure"] == 5
    assert translation_forbidden == []


def test_the_offline_guard_intercepts_a_translation_and_restores_the_translator(translation_forbidden):
    import app.evidence as evidence

    forbidden = evidence.localize_reviewed_copy
    with recall.offline_copy() as guard:
        copy = evidence.localized_conversation_response("catalogue_scope", "fi")

    assert guard["translation_attempts_blocked"] == 1
    assert copy == evidence.configured_conversation_response("catalogue_scope", "fi")[0]
    assert evidence.localize_reviewed_copy is forbidden
    assert translation_forbidden == []
