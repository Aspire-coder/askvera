"""Tests for the answer-quality benchmark harness.

The harness decides whether an answer counted as correct, so a bug here is
worse than no benchmark at all: it produces a number everyone trusts and
nobody checks. These tests pin the judging rules and the fixture contract.
"""

from __future__ import annotations

import copy
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


benchmark = _load("run_benchmark")

VALID_CASE = {
    "id": "case-1",
    "question": "What is the minimum order?",
    "country": "US",
    "language": "en",
    "role": "active_distributor",
    "intent_group": "directory",
    "expected": {"kind": "answer", "must_contain": ["2 Case Credits"]},
    "source_evidence": "Policy section 4.2 states the minimum.",
    "provenance": "Dumped from the index on 2026-09-07.",
}


def _fixture(tmp_path: Path, cases: list[dict], **overrides) -> Path:
    payload = {"schema_version": 1, "cases": cases}
    payload.update(overrides)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(**overrides) -> dict:
    run = {
        "answer": "The minimum order is 2 Case Credits.",
        "citations": 1,
        "abstained": False,
        "failure_layer": "",
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


def test_fixture_loads_and_reports_a_content_hash(tmp_path):
    cases, digest = benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE]))
    assert [case["id"] for case in cases] == ["case-1"]
    # A result is only comparable to another if both name the case set they ran.
    assert len(digest) == 64


def test_case_without_provenance_is_refused(tmp_path):
    case = copy.deepcopy(VALID_CASE)
    case["provenance"] = "   "
    with pytest.raises(ValueError, match="provenance"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_answer_case_asserting_nothing_is_refused(tmp_path):
    """A case with no required content would pass on any reply at all."""
    case = copy.deepcopy(VALID_CASE)
    case["expected"] = {"kind": "answer", "must_contain": []}
    with pytest.raises(ValueError, match="asserts nothing"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_duplicate_case_ids_are_refused(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE, copy.deepcopy(VALID_CASE)]))


def test_unknown_schema_version_is_refused(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        benchmark.load_fixture(_fixture(tmp_path, [VALID_CASE], schema_version=2))


def test_correct_answer_passes():
    assert benchmark.score_run(VALID_CASE, _run())["passed"]


def test_missing_required_fact_fails():
    scored = benchmark.score_run(VALID_CASE, _run(answer="The minimum order is one case."))
    assert not scored["passed"]
    assert "missing required fact" in scored["failures"][0]


def test_abstaining_on_an_answerable_question_fails():
    scored = benchmark.score_run(VALID_CASE, _run(abstained=True))
    assert scored["failures"] == ["abstained on an answerable question"]


def test_expected_abstention_passes_and_answering_fails():
    """A refusal is a correct outcome when the documents do not cover a question.

    Scoring it as a failure would reward the system for inventing an answer,
    which is the exact behaviour the evidence contract exists to prevent.
    """
    case = {**VALID_CASE, "expected": {"kind": "abstain"}}
    assert benchmark.score_run(case, _run(abstained=True, citations=0))["passed"]
    answered = benchmark.score_run(case, _run(abstained=False))
    assert answered["failures"] == ["answered a question the documents do not cover"]


def test_forbidden_content_fails_even_on_an_abstention():
    case = {**VALID_CASE, "expected": {"kind": "abstain", "must_not_contain": ["£19.99"]}}
    scored = benchmark.score_run(case, _run(abstained=True, answer="I can't help, but it's £19.99."))
    assert not scored["passed"]


def test_wrong_governing_source_is_reported_separately():
    """Retrieval and generation fail differently and need telling apart."""
    case = {**VALID_CASE, "expected": {**VALID_CASE["expected"], "source_title_contains": "UK Policy"}}
    scored = benchmark.score_run(case, _run(top_title="Ireland Policy Manual"))
    assert not scored["retrieval_hit"]
    assert "governing source not retrieved first" in scored["failures"][0]


def test_required_sections_beat_a_title_match():
    """One title covers every market, so a title match is not evidence.

    The sponsoring directory is a single document holding every country's
    record. "Retrieved the right document" is satisfied by the wrong market
    entirely, which is the failure this benchmark exists to catch.
    """
    case = {**VALID_CASE, "expected": {**VALID_CASE["expected"], "required_sections": ["sponsoring-001-algeria"]}}
    scored = benchmark.score_run(case, _run(sections=["sponsoring-053-belgium"]))
    assert scored["retrieval_hit"] is False
    assert "governing sections not retrieved" in scored["failures"][0]


def test_citing_the_wrong_passage_fails_even_when_retrieval_found_it():
    """Citation correctness, not citation count."""
    case = {
        **VALID_CASE,
        "expected": {**VALID_CASE["expected"], "required_sections": ["4.2"], "must_cite": True},
    }
    scored = benchmark.score_run(case, _run(sections=["4.2"], cited_sections=["9.9"], citations=1))
    assert scored["retrieval_hit"] is True
    assert any("not cited" in failure for failure in scored["failures"])


def test_a_case_naming_no_source_leaves_retrieval_unscored():
    """An unscored run must not be averaged in as a success."""
    scored = benchmark.score_run(VALID_CASE, _run())
    assert scored["retrieval_hit"] is None

    results = [{"id": "a", "intent_group": "g", "expected_kind": "answer", "runs_count": 1,
                "passed_runs": 1, "runs": [scored]}]
    summary = benchmark.summarise(results, None)
    assert summary["retrieval_hit"] == "0/0 (n/a)"
    assert summary["retrieval_unscored"] == 1


def test_removing_an_invented_figure_is_not_counted_as_damage():
    """Repair removing a figure means two opposite things.

    Both happened today. Algeria's answer carried an invented "50" that appears
    nowhere in the record, and removing it was the system working. Belgium's
    answer carried "16" and "3743", both verbatim from the record, and losing
    them cost the reader two facts and rolled a deploy back. A metric that
    counts every removal as damage would have scored those identically.
    """
    invented = benchmark.score_run(VALID_CASE, _run(removed_numeric_claims=["50"]))
    assert invented["repair_removed_anything"]
    assert not invented["repair_damaged"]

    supported = benchmark.score_run(
        VALID_CASE,
        _run(removed_numeric_claims=["16", "3743"], removed_but_present_in_source=["16", "3743"]),
    )
    assert supported["repair_removed_anything"] and supported["repair_damaged"]


def test_the_summary_reports_both_kinds_of_removal_separately():
    """One rate cannot answer "is repair working" and "is repair hurting"."""
    runs = [
        _run() | {"passed": True, "retrieval_hit": True,
                  "repair_removed_anything": True, "repair_damaged": False},
        _run() | {"passed": True, "retrieval_hit": True,
                  "repair_removed_anything": True, "repair_damaged": True},
    ]
    results = [{"id": "a", "intent_group": "g", "expected_kind": "answer",
                "runs_count": 2, "passed_runs": 2, "runs": runs}]

    summary = benchmark.summarise(results, None)

    assert summary["repair_fired"] == "2/2 (100.0%)"
    assert summary["repair_removed_invented_figure"] == "1/2 (50.0%)"
    assert summary["repair_removed_supported_figure"] == "1/2 (50.0%)"


def test_summary_states_denominators_and_flags_instability():
    results = [
        {"id": "a", "intent_group": "directory", "expected_kind": "answer", "runs_count": 2,
         "passed_runs": 1, "runs": [_run() | {"passed": True, "retrieval_hit": True, "repair_damaged": False, "repair_removed_anything": False},
                                    _run() | {"passed": False, "retrieval_hit": True, "repair_damaged": False, "repair_removed_anything": False}]},
    ]  # noqa: E501
    summary = benchmark.summarise(results, {"input": 1.0, "output": 5.0})
    assert summary["correct"] == "1/2 (50.0%)"
    # A case that passes sometimes is not a passing case.
    assert summary["unstable_cases"] == ["a"]
    # 200 input + 40 output tokens at $1/$5 per million.
    assert summary["measured_generation_cost_usd"] == pytest.approx(0.0004, abs=1e-6)
    # The name must say what it covers: nine other model calls are not counted.
    assert "query_planner" in summary["cost_excludes"]


def test_cost_is_omitted_when_no_prices_are_supplied():
    """Prices change; a guessed rate would be reported as a measurement."""
    results = [{"id": "a", "intent_group": "g", "expected_kind": "answer", "runs_count": 1,
                "passed_runs": 1, "runs": [_run() | {"passed": True, "retrieval_hit": True, "repair_damaged": False, "repair_removed_anything": False}]}]
    assert "measured_generation_cost_usd" not in benchmark.summarise(results, None)


def test_shipped_pilot_fixture_is_valid():
    cases, _ = benchmark.load_fixture(PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json")
    assert cases
    for case in cases:
        assert case["source_evidence"] and case["provenance"]


def test_benchmark_reuses_the_canary_pipeline_rather_than_copying_it():
    """One implementation of 'ask this like a user would', including cache bypass.

    A second copy would drift, and the copy that drifts is the one not run on
    every deploy.
    """
    source = (PROJECT_ROOT / "scripts" / "run_benchmark.py").read_text(encoding="utf-8")
    assert "canary.run_pipeline_capture" in source
    assert "AIOrchestrator" not in source


def test_canary_tuple_entry_point_still_matches_capture():
    """The gate's own signature must survive the refactor its tests rely on."""
    canary = _load("run_retrieval_canary")
    captured = canary._PipelineRun(
        retrieval="result",
        response=type("R", (), {"answer": "text", "citations": [1, 2]})(),
        removed_numeric_claims=["9"],
        duration_ms=1.0,
    )
    canary.run_pipeline_capture = lambda case, sequence: captured
    assert canary.run_pipeline_once({}, 1) == ("result", "text", 2, ["9"])


def test_a_french_refusal_is_recognised_as_a_refusal():
    """Matching English copy against a French answer invents failures.

    A correct French refusal scored as a wrong answer would make every
    non-English case report a failure the system did not commit, and the whole
    point of the benchmark is covering markets beyond GB/English.
    """
    from app.evidence import localized_conversation_response

    french = localized_conversation_response("insufficient_evidence", "fr") or ""
    assert french, "French refusal copy is required for this test to mean anything"

    assert benchmark._abstained(french, "fr") is True
    # The same text must not be mistaken for an answer just because the
    # English markers do not appear in it.
    assert benchmark._abstained("Le montant minimum est de 2 CC.", "fr") is False


def test_refusal_detection_covers_every_approved_way_of_declining():
    """A refusal route missing from the list scores correct behaviour as failure."""
    from app.evidence import localized_conversation_response

    for key in benchmark._REFUSAL_KEYS:
        copy = localized_conversation_response(key, "en")
        assert copy, f"{key} has no approved English copy"
        assert benchmark._abstained(copy, "en") is True, key


def test_every_answerable_case_names_the_sections_it_depends_on():
    """An answerable case without required_sections scores retrieval on nothing.

    The sponsoring directory is a single document holding every market, so a
    case that does not name its section cannot tell "found the right record"
    from "found some other country's record in the same PDF" - which is the
    failure this benchmark exists to catch.
    """
    cases, _ = benchmark.load_fixture(PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json")
    answerable = [case for case in cases if case["expected"]["kind"] == "answer"]
    assert answerable, "the fixture must contain answerable cases, not only refusals"
    for case in answerable:
        assert case["expected"].get("required_sections"), case["id"]
        # Provenance has to name where the text came from, not just assert it.
        assert "dump" in case["provenance"].lower() or "index" in case["provenance"].lower(), case["id"]


def test_a_country_qualified_section_distinguishes_duplicate_markets():
    """Section IDs repeat across markets, so the ID alone cannot score scope.

    "2-part-1-definition-18" is the FBO Support fee in Denmark, Sweden, Norway
    and Finland - the same identifier holding the same 635 characters in four
    documents - and is "Forever Business Owner (FBO)" in Canada. A Danish
    reader served Sweden's copy gets a correctly grounded, correctly cited
    answer from the wrong country, which is invisible in the answer text.
    """
    case = {
        **VALID_CASE,
        "expected": {
            **VALID_CASE["expected"],
            "required_sections": ["DK:2-part-1-definition-18"],
            "must_cite": True,
        },
    }

    swedish_copy = benchmark.score_run(
        case,
        _run(
            sections=benchmark._section_keys([("2-part-1-definition-18", "SE")]),
            cited_sections=benchmark._section_keys([("2-part-1-definition-18", "SE")]),
        ),
    )
    assert swedish_copy["retrieval_hit"] is False

    danish_copy = benchmark.score_run(
        case,
        _run(
            sections=benchmark._section_keys([("2-part-1-definition-18", "DK")]),
            cited_sections=benchmark._section_keys([("2-part-1-definition-18", "DK")]),
        ),
    )
    assert danish_copy["retrieval_hit"] is True
    assert danish_copy["passed"]


def test_an_unqualified_section_still_matches_any_market():
    """Global directory sections are unambiguous and must stay simple to write."""
    keys = benchmark._section_keys([("sponsoring-001-algeria", "GLOBAL")])
    assert "sponsoring-001-algeria" in keys
    assert "GLOBAL:sponsoring-001-algeria" in keys


def test_an_unsupported_role_is_refused_before_any_model_call(tmp_path):
    """--dry-run exists to catch exactly this, and did not.

    Every case shipped with role "fbo", which ChatRequest rejects. The fixture
    validated cleanly, and the error surfaced only after the run had started
    spending money on a live pipeline. Validating the whole fixture without a
    model call is the flag's entire purpose, so the roles it accepts must come
    from the same source ChatRequest validates against.
    """
    case = copy.deepcopy(VALID_CASE)
    case["role"] = "fbo"
    with pytest.raises(ValueError, match="role"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_an_unknown_country_is_refused_before_any_model_call(tmp_path):
    """The neighbouring mistake: a market code that is not enabled."""
    case = copy.deepcopy(VALID_CASE)
    case["country"] = "ZZ"
    with pytest.raises(ValueError, match="country"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_the_shipped_fixture_uses_roles_the_request_model_accepts():
    """A guard on the cases themselves, not only on the loader."""
    from config.vera_persona import ROLE_CONTENT_SCOPES

    cases, _ = benchmark.load_fixture(PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json")
    for case in cases:
        assert case["role"] in ROLE_CONTENT_SCOPES, case["id"]


@pytest.mark.parametrize("required,cited,expected", [
    ("DK:2-part-1-definition-18", {"2", "DK:2"}, True),
    ("SE:2-part-1-definition-18", {"2", "SE:2"}, True),
    # The market still has to be right. A parent from the wrong country is the
    # failure these cases exist to catch.
    ("DK:2-part-1-definition-18", {"2", "SE:2"}, False),
    # The separator is required, so a parent cannot swallow a sibling.
    ("DK:21.05", {"2", "DK:2"}, False),
    ("sponsoring-001-algeria", {"sponsoring-001-algeria"}, True),
])
def test_a_citation_to_the_parent_section_satisfies_a_leaf_requirement(required, cited, expected):
    """Retrieval keys a document by section_id; a citation reports its parent.

    RetrievedDocument.to_source prefers parent_section_id, which is the
    governing section a reader would look up rather than the chunk the passage
    sits in. So a correct citation for "2-part-1-definition-18" reads "2".

    Comparing those as one namespace made the DK and SE scope cases fail for
    three consecutive runs while the system was doing exactly the right thing -
    retrieving each market's own copy of byte-identical text and citing its
    governing section. The measurement was wrong, not the answer.
    """
    assert benchmark._is_cited(required, cited) is expected


def test_the_scope_pair_passes_when_each_market_cites_its_own_parent():
    """End to end through score_run, not just the helper."""
    case = {
        **VALID_CASE,
        "country": "DK",
        "expected": {
            "kind": "answer",
            "must_contain": ["3"],
            "required_sections": ["DK:2-part-1-definition-18"],
            "must_cite": True,
        },
    }
    answer = "The FBO Support fee is a monthly fee of up to 3 EUR for Assistant Supervisor and above."

    right_market = benchmark.score_run(case, _run(
        answer=answer,
        sections=benchmark._section_keys([("2-part-1-definition-18", "DK")]),
        cited_sections=benchmark._section_keys([("2", "DK")]),
    ))
    assert right_market["passed"], right_market["failures"]

    wrong_market = benchmark.score_run(case, _run(
        answer=answer,
        sections=benchmark._section_keys([("2-part-1-definition-18", "SE")]),
        cited_sections=benchmark._section_keys([("2", "SE")]),
    ))
    assert not wrong_market["passed"]
