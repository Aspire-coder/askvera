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


def test_artifact_checkpoint_is_atomic_and_keeps_completed_cases(tmp_path):
    artifact = tmp_path / "candidate-results.json"
    summary = {"status": "in_progress", "completed_cases": 1}
    cases = [{"id": "case-1", "runs": []}]

    benchmark._write_artifact(artifact, summary, cases)

    assert json.loads(artifact.read_text(encoding="utf-8")) == {
        "summary": summary, "cases": cases,
    }
    assert not artifact.with_suffix(".json.tmp").exists()


def _transport_override(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "transport-overrides.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_transport_override_is_hash_bound_and_global_only(tmp_path):
    case = {**VALID_CASE, "country": "GH", "source": {"country": "GLOBAL"}}
    path = _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": "f" * 64,
        "request_countries": {"case-1": "US"},
    })

    overrides, digest = benchmark.load_transport_overrides(path, [case], "f" * 64)

    assert overrides == {"case-1": "US"}
    assert len(digest) == 64
    execution_case, request_country = benchmark.execution_case_for_request(case, overrides)
    assert request_country == "US"
    assert execution_case["country"] == "US"
    assert case["country"] == "GH"


def test_transport_override_refuses_hash_mismatch_or_local_source(tmp_path):
    path = _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": "wrong",
        "request_countries": {"case-1": "US"},
    })
    global_case = {**VALID_CASE, "source": {"country": "GLOBAL"}}
    with pytest.raises(ValueError, match="frozen fixture hash"):
        benchmark.load_transport_overrides(path, [global_case], "right")

    path = _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": "right",
        "request_countries": {"case-1": "US"},
    })
    with pytest.raises(ValueError, match="only GLOBAL"):
        benchmark.load_transport_overrides(path, [VALID_CASE], "right")


def test_transport_override_refuses_unknown_case_or_request_country(tmp_path):
    global_case = {**VALID_CASE, "source": {"country": "GLOBAL"}}
    path = _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": "right",
        "request_countries": {"missing": "US"},
    })
    with pytest.raises(ValueError, match="unknown case"):
        benchmark.load_transport_overrides(path, [global_case], "right")

    path = _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": "right",
        "request_countries": {"case-1": "ZZ"},
    })
    with pytest.raises(ValueError, match="unsupported request country"):
        benchmark.load_transport_overrides(path, [global_case], "right")


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


def test_regex_expectations_are_validated_and_scored(tmp_path):
    case = copy.deepcopy(VALID_CASE)
    case["expected"] = {
        "kind": "answer",
        "required_patterns": [r"\b2\s+Case Credits\b"],
        "forbidden_patterns": [r"\b3\s+Case Credits\b"],
    }
    benchmark.load_fixture(_fixture(tmp_path, [case]))
    assert benchmark.score_run(case, _run())["passed"]
    assert not benchmark.score_run(case, _run(answer="The minimum is 3 Case Credits."))["passed"]


def test_invalid_regex_is_refused_before_execution(tmp_path):
    case = copy.deepcopy(VALID_CASE)
    case["expected"]["required_patterns"] = ["["]
    with pytest.raises(ValueError, match="invalid required_patterns regex"):
        benchmark.load_fixture(_fixture(tmp_path, [case]))


def test_structured_prior_turn_is_scored():
    reply = type("Reply", (), {"answer": "The minimum is 3 Case Credits.", "metadata": {}})()
    case = copy.deepcopy(VALID_CASE)
    case["conversation"] = [{
        "question": "What is the minimum?",
        "expected": {"kind": "answer", "required_patterns": [r"\b2\s+Case Credits\b"]},
    }]
    failures = benchmark._prior_turn_failures(case, (reply,))
    assert len(failures) == 1
    assert failures[0].startswith("turn 1: missing required pattern")


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


# --- abstention transport: HELDOUT-LOCAL-REFUSAL-TRANSPORT-01 -------------

FROZEN_PACK = PROJECT_ROOT / "tests" / "fixtures" / "held_out_source_linked_pack.json"
TRANSPORT_OVERLAY = PROJECT_ROOT / "tests" / "fixtures" / "held_out_request_country_overrides.json"
FROZEN_PACK_SHA256 = "5eb49a410c37a4f87ef3b60c922bd06dede92007b48e021d6f28fb77ee1ff208"
CASE_23 = "ho-slp-23-portugal-must-not-get-italy-premium-customer-commission-en"
ITALY_PREMIUM_RATE = r"\b25\s?%"
GLOBAL_TRANSPORTS = {
    "ho-slp-01-ghana-preferred-customer-signup-order-en": "US",
    "ho-slp-02-ghana-prospect-fbo-first-order-conditions-en": "US",
    "ho-slp-04-tanzania-foreign-then-local-bonus-follow-up-en": "US",
    "ho-slp-05-benin-accented-fbo-minimum-order-fr": "US",
    "ho-slp-20-poland-first-order-and-delivery-cost-en": "US",
    "ho-slp-21-poland-unregistered-fbo-annual-bonus-payout-en": "US",
}

GLOBAL_ANSWER_CASE = {**VALID_CASE, "id": "global-answer", "country": "GH", "source": {"country": "GLOBAL"}}
CROSS_MARKET_REFUSAL = {
    **VALID_CASE,
    "id": "pt-italy-refusal",
    "country": "PT",
    "source": {"country": "IT"},
    "expected": {"kind": "abstain", "forbidden_patterns": [ITALY_PREMIUM_RATE]},
}
LOCAL_POLICY_ANSWER = {**VALID_CASE, "id": "it-local-answer", "country": "IT", "source": {"country": "IT"}}


def _abstention_overlay(tmp_path: Path, abstentions, request_countries=None, fixture_sha256="right") -> Path:
    return _transport_override(tmp_path, {
        "schema_version": 1,
        "fixture_sha256": fixture_sha256,
        "request_countries": request_countries or {},
        "abstention_request_countries": abstentions,
    })


def test_abstention_transport_admits_a_cross_market_refusal(tmp_path):
    path = _abstention_overlay(tmp_path, {"pt-italy-refusal": "US"}, {"global-answer": "US"})

    overrides, digest = benchmark.load_transport_overrides(
        path, [GLOBAL_ANSWER_CASE, CROSS_MARKET_REFUSAL], "right")

    assert overrides == {"global-answer": "US", "pt-italy-refusal": "US"}
    assert len(digest) == 64
    execution_case, request_country = benchmark.execution_case_for_request(CROSS_MARKET_REFUSAL, overrides)
    assert request_country == "US"
    assert execution_case["country"] == "US"
    # The frozen case is untouched: its session and expectation are the truth.
    assert CROSS_MARKET_REFUSAL["country"] == "PT"
    assert execution_case["expected"] == CROSS_MARKET_REFUSAL["expected"]


def test_abstention_transport_refuses_a_wrong_fixture_hash(tmp_path):
    path = _abstention_overlay(tmp_path, {"pt-italy-refusal": "US"}, fixture_sha256="wrong")

    with pytest.raises(ValueError, match="frozen fixture hash"):
        benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")


def test_abstention_transport_refuses_an_unknown_case(tmp_path):
    path = _abstention_overlay(tmp_path, {"missing": "US"})

    with pytest.raises(ValueError, match="unknown case"):
        benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")


def test_abstention_transport_refuses_an_unsupported_request_country(tmp_path):
    path = _abstention_overlay(tmp_path, {"pt-italy-refusal": "ZZ"})

    with pytest.raises(ValueError, match="unsupported request country"):
        benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")


@pytest.mark.parametrize("case", [
    LOCAL_POLICY_ANSWER,
    {**CROSS_MARKET_REFUSAL, "id": "pt-italy-answer", "expected": {"kind": "answer", "must_contain": ["25%"]}},
], ids=["local-policy-answer", "cross-market-answer"])
def test_abstention_transport_refuses_a_non_abstention_case(tmp_path, case):
    """A normal local-policy answer, or any answer case, cannot use this path."""
    path = _abstention_overlay(tmp_path, {case["id"]: "US"})

    with pytest.raises(ValueError, match="only abstention cases"):
        benchmark.load_transport_overrides(path, [case], "right")


@pytest.mark.parametrize("kind", ["answer", "abstain"])
def test_abstention_transport_refuses_a_global_source_case(tmp_path, kind):
    """GLOBAL cases already have request_countries; the new path is not a second door."""
    case = {**GLOBAL_ANSWER_CASE, "expected": {"kind": kind, "must_contain": ["x"]}}
    path = _abstention_overlay(tmp_path, {case["id"]: "US"})

    with pytest.raises(ValueError, match="GLOBAL source cases use request_countries"):
        benchmark.load_transport_overrides(path, [case], "right")


def test_abstention_transport_refuses_a_case_already_in_request_countries(tmp_path):
    path = _abstention_overlay(tmp_path, {"global-answer": "US"}, {"global-answer": "US"})

    with pytest.raises(ValueError, match="already has a request_countries transport"):
        benchmark.load_transport_overrides(path, [GLOBAL_ANSWER_CASE], "right")


def test_abstention_transport_refuses_a_case_that_can_run_as_frozen(tmp_path):
    """An Austria session is published, so that refusal must run from Austria."""
    case = {**CROSS_MARKET_REFUSAL, "id": "at-italy-refusal", "country": "AT"}
    path = _abstention_overlay(tmp_path, {case["id"]: "US"})

    with pytest.raises(ValueError, match="already supported"):
        benchmark.load_transport_overrides(path, [case], "right")


def test_abstention_transport_refuses_a_same_market_refusal(tmp_path):
    case = {**CROSS_MARKET_REFUSAL, "id": "pt-pt-refusal", "source": {"country": "PT"}}
    path = _abstention_overlay(tmp_path, {case["id"]: "US"})

    with pytest.raises(ValueError, match="not a cross-market case"):
        benchmark.load_transport_overrides(path, [case], "right")


def test_abstention_transport_refuses_the_source_market_as_request_country(tmp_path):
    """Sending Italy's policy question from Italy would make Italy's rule answerable."""
    path = _abstention_overlay(tmp_path, {"pt-italy-refusal": "IT"})

    with pytest.raises(ValueError, match="in-market question"):
        benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")


def test_abstention_transport_refuses_a_malformed_mapping(tmp_path):
    path = _abstention_overlay(tmp_path, ["pt-italy-refusal"])

    with pytest.raises(ValueError, match="must be an object"):
        benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")


def test_the_transport_cannot_turn_the_refusal_into_italian_policy(tmp_path):
    """Portugal must not inherit Italy's Cliente Premium commission.

    The transport changes only the session. The case is still scored against
    its frozen expectation, so an answer quoting Italy's 25% fails however it
    was requested, and only a refusal passes.
    """
    path = _abstention_overlay(tmp_path, {"pt-italy-refusal": "US"})
    overrides, _ = benchmark.load_transport_overrides(path, [CROSS_MARKET_REFUSAL], "right")
    execution_case, _ = benchmark.execution_case_for_request(CROSS_MARKET_REFUSAL, overrides)

    inherited = benchmark.score_run(CROSS_MARKET_REFUSAL, _run(
        answer="Forever Italy pays an FBO a 25% commission on Cliente Premium orders.",
        abstained=False))
    refused = benchmark.score_run(CROSS_MARKET_REFUSAL, _run(
        answer="That local company policy is only available to readers in that market.",
        abstained=True, citations=0, cited_sections=[]))

    assert execution_case["expected"]["kind"] == "abstain"
    assert execution_case["expected"]["forbidden_patterns"] == [ITALY_PREMIUM_RATE]
    assert inherited["passed"] is False
    assert "answered a question the documents do not cover" in inherited["failures"]
    assert any("forbidden pattern" in failure for failure in inherited["failures"])
    assert refused["passed"] is True


def test_the_frozen_pack_hash_is_unchanged():
    import hashlib

    assert hashlib.sha256(FROZEN_PACK.read_bytes()).hexdigest() == FROZEN_PACK_SHA256


def test_the_real_overlay_admits_case_23_and_keeps_the_global_entries():
    cases, fixture_hash = benchmark.load_fixture(FROZEN_PACK)
    overrides, _ = benchmark.load_transport_overrides(TRANSPORT_OVERLAY, cases, fixture_hash)
    payload = json.loads(TRANSPORT_OVERLAY.read_text(encoding="utf-8"))
    case_23 = next(case for case in cases if case["id"] == CASE_23)
    execution_case, request_country = benchmark.execution_case_for_request(case_23, overrides)

    assert fixture_hash == FROZEN_PACK_SHA256
    assert payload["fixture_sha256"] == FROZEN_PACK_SHA256
    assert payload["request_countries"] == GLOBAL_TRANSPORTS
    assert payload["abstention_request_countries"] == {CASE_23: "US"}
    # The execution record names all three: source PT, request US, abstain.
    assert (str(case_23["country"]).upper(), request_country, case_23["expected"]["kind"]) == (
        "PT", "US", "abstain")
    assert execution_case["expected"] == case_23["expected"]


def test_every_frozen_case_now_has_a_supported_request_country():
    cases, fixture_hash = benchmark.load_fixture(FROZEN_PACK)
    overrides, _ = benchmark.load_transport_overrides(TRANSPORT_OVERLAY, cases, fixture_hash)
    supported = benchmark._chat_request_countries()

    unsupported = [
        case["id"] for case in cases
        if benchmark.execution_case_for_request(case, overrides)[1] not in supported
    ]

    assert len(cases) == 24
    assert unsupported == []


@pytest.mark.parametrize("with_overlay", [True, False])
def test_the_dry_run_names_requests_the_chat_api_would_refuse(monkeypatch, capsys, with_overlay):
    """The no-model check that production preflight needed and the dry run lacked."""
    import sys

    argv = ["run_benchmark.py", "--fixture", str(FROZEN_PACK), "--dry-run", "--repeat", "1"]
    if with_overlay:
        argv += ["--transport-overrides", str(TRANSPORT_OVERLAY)]
    monkeypatch.setattr(sys, "argv", argv)

    exit_code = benchmark.main()
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["fixture_sha256"] == FROZEN_PACK_SHA256
    assert report["note"] == "No model calls were made."
    if with_overlay:
        assert report["unsupported_request_countries"] == []
        assert report["transport_override_cases"] == 7
    else:
        assert CASE_23 in report["unsupported_request_countries"]


def test_the_chat_request_countries_are_narrower_than_the_market_catalog():
    """Why the abstention transport cannot use ``_valid_countries()``.

    Portugal is an enabled market in the catalog but not a country the chat API
    accepts. Checking against the catalog is what let a request production
    refused pass locally.
    """
    catalog = benchmark._valid_countries()
    chat = benchmark._chat_request_countries()

    assert chat < catalog
    assert "PT" in catalog and "PT" not in chat
    assert {"US", "AT", "IT"} <= chat
