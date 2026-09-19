"""Per-turn run capture, one pinned presence function, outcome labels and run identity.

The frozen held-out comparison ran each arm once and could not explain its
changed decisions. Neither artifact recorded the answer numeric repair was
handed, the validator's findings, the approved evidence ids, which document a
citation named, the model, the code revision, a follow-up's earlier turns, or
the publication pointers retrieval filtered on. Repair metrics were classified
with each arm's own presence function, so their deltas were not like-for-like.

Everything tested here is additive. The first two tests pin, by AST, that
score_run, summarise and every legacy field of run_case_once are exactly what
fb22f38 computes (identical at 056ee79 and at the approved 954b4f5c patch).

No network: the canary, the pipeline and git are faked, or read locally.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "scripts" / "run_benchmark.py"

# ast.dump fingerprints taken from fb22f38:scripts/run_benchmark.py.
SCORE_RUN_AST_SHA256 = "6e03f2698976a627445806aeea582685cbf66361359ea0113ab050f851f35817"
SUMMARISE_AST_SHA256 = "a8bbd6068ad38a0fc1b9331ba2400193aae379b6d76c62d4d210497da1730d7b"
RUN_CASE_ONCE_LEGACY_SHA256 = "f617af69b05cbe098abaa2c5b2608942b43bc2f11642f80721995cc99d83f80a"
LEGACY_RUN_FIELDS = (
    "answer", "turn_failures", "citations", "abstained", "failure_layer", "finish_reason",
    "removed_numeric_claims", "removed_but_present_in_source", "top_title", "sections",
    "cited_sections", "confidence", "generation_input_tokens", "generation_output_tokens", "duration_ms",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load("run_benchmark")


@pytest.fixture(autouse=True)
def application_presence_function():
    benchmark.configure_pinned_presence(None)
    yield
    benchmark.configure_pinned_presence(None)


# --- scoring is untouched ----------------------------------------------------------


def _runner_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_score_run_and_summarise_are_unchanged_by_ast():
    assert hashlib.sha256(ast.dump(_runner_function("score_run")).encode()).hexdigest() == SCORE_RUN_AST_SHA256
    assert hashlib.sha256(ast.dump(_runner_function("summarise")).encode()).hexdigest() == SUMMARISE_AST_SHA256


def test_run_case_once_computes_every_legacy_field_exactly_as_before():
    function = _runner_function("run_case_once")
    assigns = [
        ast.dump(statement) for statement in function.body
        if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id in ("response", "metadata", "usage", "documents", "answer")
    ]
    returned = [statement for statement in function.body if isinstance(statement, ast.Return)][-1].value
    entries = [
        [key.value, ast.dump(value)] for key, value in zip(returned.keys, returned.values)
        if key.value in LEGACY_RUN_FIELDS
    ]

    assert len(entries) == len(LEGACY_RUN_FIELDS)
    assert hashlib.sha256(json.dumps([assigns, entries]).encode()).hexdigest() == RUN_CASE_ONCE_LEGACY_SHA256


# --- a fake pipeline run -------------------------------------------------------------


def _document(identifier: str, section: str, parent: str = "", content: str = "Du må være minst 18 år.") -> RetrievedDocument:
    return RetrievedDocument(
        id=identifier, title=f"Policy - Sec {section}", content=content,
        source=f"opensearch-section://policy.pdf/{section}", country="NO", language="no", score=0.7,
        metadata={
            "section_id": section, "parent_section_id": parent, "access_scope": "country",
            "ingestion_id": "ingestion-7", "logical_document_id": "NO-no-policy", "content_hash": f"hash-{identifier}",
        },
    )


def _retrieval(*documents: RetrievedDocument, candidates: bool = True) -> RetrievalResult:
    metadata = {
        "provider": "opensearch_section", "candidate_count": 12, "evidence_selector_applied": True,
        "evidence_selector_confidence": 0.82, "parent_bound_children": ["17.08-c"],
        "conversation_intent": "knowledge",
    }
    if candidates:
        metadata["candidate_sources"] = [document.to_source() for document in documents]
    return RetrievalResult(
        documents=list(documents), citations=[document.to_source() for document in documents],
        confidence=0.8, metadata=metadata,
    )


def _response(answer: str, retrieval: RetrievalResult, *, diagnostic: dict | None = None, **overrides) -> ChatResponse:
    metadata = {
        "provider": "bedrock", "model_name": "model-under-test", "finish_reason": "end_turn",
        "token_usage": {"inputTokens": 40, "outputTokens": 9}, "model_route_mode": "off",
        "evidence_decision": {
            "approved": True, "reason": "approved", "query_intent": "policy_fact",
            "evidence_ids": [document.id for document in retrieval.documents],
        },
    }
    if diagnostic is not None:
        metadata["diagnostic_capture"] = diagnostic
    metadata.update(overrides)
    return ChatResponse(
        answer=answer, citations=[retrieval.documents[0].to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata=metadata, correlation_id="correlation",
    )


def _diagnostic(answer_before: str, retrieval: RetrievalResult) -> dict:
    return {
        "version": 1,
        "retrievals": [{
            "stage": "question", "confidence": 0.8, "metadata": {}, "candidate_sections": [],
            "documents": [
                {"id": document.id, "source": document.source, "section_id": document.metadata["section_id"]}
                for document in retrieval.documents
            ],
        }],
        "validations": [{
            "answer_before_validation": answer_before,
            "issues": [{"code": "NUMERIC_CLAIM_UNGROUNDED", "severity": "CRITICAL", "field": "answer", "message": "36"}],
            "critical": True,
            "outcome": "numeric_repair_accepted",
            "numeric_repair": {
                "removed_numeric_claims": ["36"],
                "removal_reasons": [{"number": "36", "present_in_source": True, "reason": "unsupported_numeric_claim"}],
                "answer_after_repair": "Du må være minst 18 år.",
                "post_repair_issues": [],
                "accepted": True,
            },
        }],
    }


def _pipeline_run(response, retrieval, prior=(), removed=()):
    return SimpleNamespace(
        retrieval=retrieval, response=response, removed_numeric_claims=list(removed),
        duration_ms=12.5, prior_responses=tuple(prior),
    )


def _canary(run) -> SimpleNamespace:
    return SimpleNamespace(run_pipeline_capture=lambda case, sequence: run)


CASE = {
    "id": "follow-up", "question": "Og hva med lederne?", "country": "NO", "language": "no",
    "role": "active_distributor", "intent_group": "follow_up",
    "expected": {"kind": "answer", "must_contain": ["18"], "required_sections": ["NO:17.08-c"], "must_cite": True},
    "conversation": [{"question": "Hvor lenge?", "expected": {"kind": "answer", "required_patterns": [r"\b36\b"]}}],
}


def _follow_up_run():
    first = _retrieval(_document("doc-a", "4.05-b", parent="4.05"))
    final = _retrieval(_document("doc-b", "17.08-c", parent="17.08"), _document("doc-c", "17.09"))
    prior = _response("Etter 36 måneder.", first, diagnostic=_diagnostic("Etter 36 måneder.", first))
    response = _response("Du må være minst 18 år.", final, diagnostic=_diagnostic("Du må være minst 36 og 18 år.", final))
    return _pipeline_run(response, final, prior=[prior], removed=["36"]), final


# --- per-turn capture ---------------------------------------------------------------


def test_a_run_records_every_turn_without_changing_a_legacy_field():
    run, final = _follow_up_run()

    recorded = benchmark.run_case_once(_canary(run), CASE, 1001)

    assert set(recorded) == {*LEGACY_RUN_FIELDS, "removed_but_present_in_source_pinned", "capture"}
    assert recorded["answer"] == "Du må være minst 18 år."
    assert recorded["citations"] == 1
    assert recorded["sections"] == ["17.08-c", "NO:17.08-c", "17.09", "NO:17.09"]
    assert recorded["cited_sections"] == ["17.08", "NO:17.08"]
    assert recorded["removed_but_present_in_source"] == []
    assert (recorded["generation_input_tokens"], recorded["generation_output_tokens"]) == (40, 9)

    capture = recorded["capture"]
    assert capture["version"] == benchmark.CAPTURE_VERSION
    assert capture["orchestrator_capture"] == "enabled"
    first, last = capture["turns"]
    assert (first["turn"], first["answer"]) == ("turn1", "Etter 36 måneder.")
    assert last["turn"] == "final"
    assert last["pre_repair_answer"] == "Du må være minst 36 og 18 år."
    assert [issue["code"] for issue in last["validator_issues"]] == ["NUMERIC_CLAIM_UNGROUNDED"]
    assert last["removed_claims"] == [{"number": "36", "present_in_source": True, "reason": "unsupported_numeric_claim"}]
    assert last["metadata"]["evidence_decision"]["evidence_ids"] == ["doc-b", "doc-c"]
    assert last["metadata"]["model_name"] == "model-under-test"
    assert last["metadata"]["model_route_mode"] == "off"
    assert last["citations"][0]["section"] == "17.08"
    assert (last["citations"][0]["document_id"], last["citations"][0]["document_section_id"]) == ("doc-b", "17.08-c")
    assert first["citations"][0]["document_id"] == "doc-a"
    retrieval = capture["final_retrieval"]
    assert retrieval["metadata"]["evidence_selector_confidence"] == 0.82
    assert retrieval["metadata"]["parent_bound_children"] == ["17.08-c"]
    assert [document["ingestion_id"] for document in retrieval["documents"]] == ["ingestion-7", "ingestion-7"]
    assert [candidate["section"] for candidate in retrieval["candidate_sections"]] == ["17.08", "17.09"]
    assert "passage" not in json.dumps(retrieval) and "minst 18" not in json.dumps(retrieval)
    assert {gap["field"] for gap in capture["gaps"]} == {
        "planner_intent_confidence", "candidate_child_section_ids", "selector_selected_ranks",
    }


def test_scoring_a_captured_run_gives_the_same_verdict_as_the_legacy_fields_alone():
    run, _ = _follow_up_run()
    recorded = benchmark.run_case_once(_canary(run), CASE, 1001)
    legacy_only = {key: recorded[key] for key in LEGACY_RUN_FIELDS}

    with_capture = benchmark.score_run(CASE, recorded)
    without_capture = benchmark.score_run(CASE, legacy_only)

    for key in (*LEGACY_RUN_FIELDS, "passed", "failures", "retrieval_hit", "repair_removed_anything", "repair_damaged"):
        assert with_capture[key] == without_capture[key], key


def test_every_field_the_application_did_not_supply_is_named_with_its_key():
    retrieval = _retrieval(_document("doc-b", "17.08-c", parent="17.08"), candidates=False)
    response = ChatResponse(
        answer="The approved policy documents currently available do not contain enough information.",
        citations=[], suggestions=[], cards=[], confidence=0.0,
        metadata={"fallback": True, "failure_layer": "evidence_gate"}, correlation_id="c",
    )

    capture = benchmark.run_case_once(_canary(_pipeline_run(response, retrieval)), {**CASE, "conversation": []}, 7)["capture"]

    gaps = {gap["field"]: gap for gap in capture["gaps"]}
    assert gaps["pre_repair_answer_validator_findings_and_turn_retrieval"]["proposed_metadata_key"] == "diagnostic_capture"
    assert gaps["approved_evidence_ids"]["proposed_metadata_key"] == "evidence_decision.evidence_ids"
    assert gaps["model_id"]["turns"] == ["final"]
    assert gaps["selector_candidates"]["proposed_metadata_key"] == "candidate_sources"
    assert capture["final_retrieval"]["candidate_sections"] is None
    assert capture["turns"][0]["pre_repair_answer"] is None


def test_the_orchestrator_flag_is_on_only_during_the_run_and_restored_after_a_failure():
    from app.orchestrator import chat_orchestrator

    seen: list[bool] = []

    def failing(case, sequence):
        seen.append(chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED)
        raise RuntimeError("network stopped")

    with pytest.raises(RuntimeError):
        benchmark.run_case_once(SimpleNamespace(run_pipeline_capture=failing), CASE, 1)

    assert seen == [True]
    assert chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED is False


def test_an_application_without_capture_support_is_reported_as_such(monkeypatch):
    from app.orchestrator import chat_orchestrator

    monkeypatch.delattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED")
    run, _ = _follow_up_run()

    assert benchmark.run_case_once(_canary(run), CASE, 1)["capture"]["orchestrator_capture"] == "unsupported_by_application"


# --- one pinned presence function --------------------------------------------------

_VALIDATOR_TEMPLATE = '''
import re


def _normalize(text):
    return " ".join(str(text).split())


def _number_variants(number):
    return {{number{variant}}}


def _unrelated():
    return {unrelated}


def numbers_present_in_sources(numbers, documents):
    sources = [_normalize(getattr(document, "content", "")) for document in documents]
    return {{number: any(re.search(re.escape(v), s) for v in _number_variants(number) for s in sources) for number in numbers}}
'''


def _validator(tmp_path: Path, name: str, variant: str = "", unrelated: str = "1", spacing: str = "") -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(_VALIDATOR_TEMPLATE.format(variant=variant, unrelated=unrelated) + spacing, encoding="utf-8")
    return path


def test_the_presence_identity_follows_the_code_presence_runs_and_nothing_else(tmp_path):
    base = benchmark.presence_function_identity(benchmark.load_presence_function(_validator(tmp_path, "base")))
    unrelated = benchmark.presence_function_identity(
        benchmark.load_presence_function(_validator(tmp_path, "unrelated", unrelated="2")))
    reformatted = benchmark.presence_function_identity(
        benchmark.load_presence_function(_validator(tmp_path, "reformatted", spacing="\n\n# trailing comment\n")))
    widened = benchmark.presence_function_identity(
        benchmark.load_presence_function(_validator(tmp_path, "widened", variant=', number + ".00"')))

    assert base["closure_names"] == ["_normalize", "_number_variants", "numbers_present_in_sources"]
    assert unrelated["closure_sha256"] == base["closure_sha256"]
    assert unrelated["module_sha256"] != base["module_sha256"]
    assert reformatted["closure_sha256"] == base["closure_sha256"]
    assert widened["closure_sha256"] != base["closure_sha256"]


_TRANSITIVE_TEMPLATE = '''
def _boundary(text):
    return text.split("{separator}")


def _source_windows(text, number):
    return [part for part in _boundary(text) if number in part]


def numbers_present_in_sources(numbers, documents):
    return {{number: any(_source_windows(getattr(d, "content", ""), number) for d in documents) for number in numbers}}
'''


def test_the_identity_changes_when_a_callee_of_a_callee_changes_though_the_function_does_not(tmp_path):
    """A validator revision changed helpers behind byte-identical function bodies.

    A hash of numbers_present_in_sources alone would read the two files as the
    same presence function. Both recorded hashes must change instead.
    """
    def load(name: str, separator: str):
        path = tmp_path / f"{name}.py"
        path.write_text(_TRANSITIVE_TEMPLATE.format(separator=separator), encoding="utf-8")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        own = next(ast.dump(node) for node in tree.body if getattr(node, "name", "") == "numbers_present_in_sources")
        return own, benchmark.presence_function_identity(benchmark.load_presence_function(path))

    own_before, before = load("split_on_dot", ".")
    own_after, after = load("split_on_semicolon", ";")

    assert own_before == own_after
    assert before["closure_names"] == ["_boundary", "_source_windows", "numbers_present_in_sources"]
    assert after["closure_sha256"] != before["closure_sha256"]
    assert after["module_sha256"] != before["module_sha256"]


def test_the_run_records_the_repair_function_with_the_helpers_it_calls():
    from config import settings

    identity = benchmark.run_identity(settings)

    repair, presence = identity["numeric_repair_function"], identity["presence_function"]
    assert repair["function"] == "remove_unsupported_numeric_sentences"
    assert {"unsupported_numeric_claims", "_claim_is_supported", "_subject_token_sets"} <= set(repair["closure_names"])
    assert repair["module_sha256"] == presence["module_sha256"]
    assert repair["closure_sha256"] != presence["closure_sha256"]


def test_the_applications_presence_identity_excludes_subject_matching():
    identity = benchmark.pinned_presence_identity()

    assert identity["status"] == "recorded"
    assert identity["module_file"] == "app/validation/validators/numeric_grounding_validator.py"
    assert {"_number_variants", "_source_windows", "_normalize"} <= set(identity["closure_names"])
    assert "_claim_is_supported" not in identity["closure_names"]


def test_a_pinned_function_classifies_removals_beside_the_unchanged_legacy_field(tmp_path):
    retrieval = _retrieval(_document("doc-b", "17.08-c", content="Etter 36 måneder."))
    response = _response("Svar.", retrieval)
    run = _pipeline_run(response, retrieval, removed=["36.00"])
    benchmark.configure_pinned_presence(_validator(tmp_path, "widened_pin", variant=', number.replace(".00", "")'))

    recorded = benchmark.run_case_once(_canary(run), {**CASE, "conversation": []}, 1)

    assert recorded["removed_but_present_in_source"] == []
    assert recorded["removed_but_present_in_source_pinned"] == ["36.00"]
    report = benchmark.pinned_repair_report([{"runs": [recorded]}])
    assert report["repair_removed_supported_figure"] == "1/1 (100.0%)"
    assert report["presence_function"]["module_file"].endswith("widened_pin.py")


def test_a_pinned_validator_without_the_function_stops_the_run_before_any_case(tmp_path, monkeypatch, capsys):
    broken = tmp_path / "broken.py"
    broken.write_text("def something_else():\n    return None\n", encoding="utf-8")
    fixture = tmp_path / "cases.json"
    fixture.write_text(json.dumps({"schema_version": 1, "cases": [{
        **{key: value for key, value in CASE.items() if key != "conversation"},
        "source_evidence": "Section 17.08.", "provenance": "Dumped from the index.",
    }]}), encoding="utf-8")
    calls: list[int] = []
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: calls.append(1))
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py", "--fixture", str(fixture), "--repeat", "1",
                                      "--pinned-presence-validator", str(broken)])

    assert benchmark.main() == 2
    assert calls == []
    assert "numbers_present_in_sources" in capsys.readouterr().err


# --- outcome labels ---------------------------------------------------------------


def _copy(key: str, language: str = "en") -> str:
    from app.evidence import localized_conversation_response

    return localized_conversation_response(key, language) or ""


def _label(answer: str, *, language: str = "en", required=(), **run) -> dict:
    return benchmark.classify_outcome({"answer": answer, **run}, language=language, required_sections=list(required))


def test_refusal_copy_is_labelled_by_the_kind_of_refusal():
    # Updated 2026-09-18 (Phase 3, Lane 4): config/conversation_routes.json
    # now carries a reviewed "cross_market_policy_scope" key for "en" (the
    # CX_LANES.md message-key table), which scripts/run_benchmark.py's
    # classify_outcome already looked up via _cross_market_scope_copy before
    # this key existed anywhere. CROSS_MARKET_POLICY_SCOPE_RESPONSE is the
    # orchestrator's own hardcoded English-only ultimate fallback, used only
    # when no reviewed copy exists for a locale -- no longer true for "en" -
    # so this test now checks the actual reviewed copy classify_outcome sees.
    assert _label(_copy("cross_market_policy_scope"), abstained=True)["outcome"] == "foreign_policy_refusal"
    assert _label(_copy("off_topic"), abstained=True)["outcome"] == "out_of_scope_refusal"
    assert _label(_copy("off_topic", "fr"), language="fr", abstained=True)["outcome"] == "out_of_scope_refusal"
    assert _label(_copy("catalogue_scope"), abstained=True)["basis"] == "catalogue_scope"


def test_an_insufficient_evidence_refusal_is_split_by_what_retrieval_found():
    refusal = _copy("insufficient_evidence")

    assert _label(refusal, abstained=True, sections=[])["outcome"] == "retrieval_failure"
    assert _label(refusal, abstained=True, sections=["UK:17.2"], required=["UK:4.4"])["outcome"] == "retrieval_failure"
    declined_anyway = _label(refusal, abstained=True, sections=["UK:4.4"], required=["UK:4.4"])
    assert (declined_anyway["outcome"], declined_anyway["basis"]) == ("other", "declined_although_documents_were_retrieved")


def test_a_non_english_cross_market_refusal_is_recognised_from_the_captured_evidence_reason():
    """Only English has cross-market copy; other locales send the insufficient-evidence copy."""
    capture = {"turns": [{"metadata": {"evidence_decision": {"reason": "cross_market_policy_request"}}}]}
    refusal = _copy("insufficient_evidence", "nl")

    assert _label(refusal, language="nl", abstained=True, sections=["NL:7.03"], capture=capture)["outcome"] == "foreign_policy_refusal"
    assert _label(refusal, language="nl", abstained=True, sections=["NL:7.03"])["outcome"] == "other"


def test_a_typo_confirmation_is_a_question_not_an_answer():
    template = _copy("country_typo_confirmation")
    label = _label(template.replace("{country}", "Tunisia"))

    assert (label["outcome"], label["basis"]) == ("other", "clarifying_question")


def test_a_reply_that_opens_by_saying_the_source_is_silent_is_safe_not_stated():
    """Case 11's shape, which passed-or-failed scoring records only as "answered"."""
    opens_with_it = "I appreciate the question. However, the directory doesn't specify how long approval takes."
    later_only = "The fee is HK$50. Delivery takes 3 days. The directory does not state the approval time."

    assert _label(opens_with_it)["outcome"] == "safe_not_stated"
    assert _label("I don't have information about a Cliente Premium tier.")["outcome"] == "safe_not_stated"
    assert _label(later_only)["outcome"] == "answered"
    assert _label("The minimum order is 2 Case Credits.")["outcome"] == "answered"


def test_a_non_english_not_stated_reply_is_labelled_answered_which_is_the_stated_limit():
    assert _label("Kilden oppgir ikke hvor lang tid godkjenningen tar.", language="no")["outcome"] == "answered"


def test_the_outcome_label_never_changes_passed():
    run, _ = _follow_up_run()
    scored = benchmark.score_run(CASE, benchmark.run_case_once(_canary(run), CASE, 1))

    labelled = benchmark.with_diagnostic_outcome(CASE, scored)

    assert {key: value for key, value in labelled.items() if key != "diagnostic_outcome"} == scored
    assert labelled["diagnostic_outcome"]["method"] == "automated_heuristic"


def test_the_outcome_report_counts_every_label_by_expected_kind():
    results = [
        {"expected_kind": "abstain", "runs": [{"diagnostic_outcome": {"outcome": "safe_not_stated"}}]},
        {"expected_kind": "answer", "runs": [{"diagnostic_outcome": {"outcome": "answered"}}, {}]},
    ]

    report = benchmark.outcome_report(results)

    assert report["runs"] == 2
    assert report["counts"]["safe_not_stated"] == 1 and report["counts"]["answered"] == 1
    assert report["by_expected_kind"]["abstain"]["safe_not_stated"] == 1
    assert "not manual adjudication" in report["note"]


# --- run identity --------------------------------------------------------------------


def test_the_revision_record_hashes_the_diff_and_untracked_source_but_not_environments(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_bytes(b"def test_x():\n    pass\n")
    (tmp_path / ".venv-benchmark").mkdir()
    (tmp_path / ".venv-benchmark" / "site.py").write_bytes(b"x = 1\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01")
    outputs = {
        ("rev-parse", "HEAD"): b"fb22f38f03f603b17ffa22244ae79f78e53ca767\n",
        ("diff", "HEAD", "--binary"): b"diff --git a/x b/x\n",
        ("status", "--porcelain=v1", "--untracked-files=all"): b" M x\n?? tests/test_new.py\n",
        ("ls-files", "--others", "--exclude-standard", "-z"): b".venv-benchmark/site.py\0blob.bin\0tests/test_new.py\0",
    }

    record = benchmark.app_revision(tmp_path, git=lambda root, *args: outputs.get(args))

    assert record["commit"] == "fb22f38f03f603b17ffa22244ae79f78e53ca767"
    assert record["dirty"] is True
    assert record["tracked_diff_sha256"] == hashlib.sha256(b"diff --git a/x b/x\n").hexdigest()
    assert record["untracked_count"] == 3 and record["untracked_not_hashed"] == 2
    assert record["untracked_hashed"] == [{
        "path": "tests/test_new.py", "sha256": hashlib.sha256(b"def test_x():\n    pass\n").hexdigest(),
    }]


def test_a_tree_without_git_says_so():
    assert benchmark.app_revision(Path("."), git=lambda *_: None) == {
        "status": "unavailable", "reason": "git rev-parse HEAD failed",
    }


def test_this_checkout_records_a_commit():
    record = benchmark.app_revision(PROJECT_ROOT)

    assert record["status"] == "recorded"
    assert len(record["commit"]) == 40


def test_the_generation_snapshot_is_read_from_the_in_process_cache_without_a_query(monkeypatch):
    def forbidden(**_):
        raise AssertionError("the runner must not query knowledge_active_generations")

    rows = [
        {"country": "NO", "language": "no", "document_type": "policy", "access_scope": "country", "active_ingestion_id": "b"},
        {"country": "GLOBAL", "language": "en", "document_type": "directory", "access_scope": "global", "active_ingestion_id": "a"},
    ]
    monkeypatch.setitem(sys.modules, "services.knowledge_generations",
                        SimpleNamespace(_cache_rows=rows, _active_generation_rows=forbidden))
    first = benchmark._generation_snapshot()
    monkeypatch.setitem(sys.modules, "services.knowledge_generations",
                        SimpleNamespace(_cache_rows=list(reversed(rows)), _active_generation_rows=forbidden))
    second = benchmark._generation_snapshot()

    assert first["status"] == "in_process_cache" and first["row_count"] == 2
    assert first["sha256"] == second["sha256"]
    report = benchmark.generation_identity_report([{"runs": [{"capture": {"generation_snapshot": first}}]}])
    assert report["runs_by_snapshot"] == {first["sha256"]: 1}
    assert len(report["snapshots"][first["sha256"]]) == 2

    monkeypatch.delitem(sys.modules, "services.knowledge_generations")
    assert benchmark._generation_snapshot() == {"status": "not_loaded", "sha256": None, "row_count": 0}


# --- the artifact --------------------------------------------------------------------


def _replace_canary_import(monkeypatch) -> None:
    class Loader:
        def exec_module(self, _module):
            return None

    class Spec:
        loader = Loader()

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: Spec())
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda _: object())


def test_the_artifact_carries_the_additive_blocks_and_every_legacy_figure_is_unchanged(tmp_path, monkeypatch):
    run, _ = _follow_up_run()
    case = {**CASE, "source_evidence": "Section 17.08.", "provenance": "Dumped from the index."}
    fixture = tmp_path / "cases.json"
    fixture.write_text(json.dumps({"schema_version": 1, "cases": [case, {**case, "id": "second"}]}), encoding="utf-8")
    artifact = tmp_path / "results.json"
    canary = _canary(run)
    real_run_case_once = benchmark.run_case_once
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda _canary_module, request, sequence: real_run_case_once(canary, request, sequence))
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py", "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1"])

    assert benchmark.main() == 0

    saved = json.loads(artifact.read_text(encoding="utf-8"))
    summary = saved["summary"]
    for key, value in benchmark.summarise(saved["cases"], None).items():
        assert summary[key] == value, key
    assert summary["run_identity"]["version"] == benchmark.RUN_IDENTITY_VERSION
    assert summary["run_identity"]["app_revision"]["status"] == "recorded"
    assert summary["run_identity"]["presence_function"]["status"] == "recorded"
    assert summary["capture_version"] == benchmark.CAPTURE_VERSION
    assert summary["diagnostic_outcomes"]["runs"] == 2
    assert summary["repair_classification_pinned"]["runs_measured"] == 2
    assert summary["generation_identity"]["observed_ingestion_ids"] == ["ingestion-7"]
    for case_record in saved["cases"]:
        assert case_record["runs"][0]["diagnostic_outcome"]["outcome"] in benchmark.OUTCOMES
        assert case_record["runs"][0]["capture"]["turns"][-1]["pre_repair_answer"] == "Du må være minst 36 og 18 år."


# --- labelling makes no model call ---------------------------------------------------
#
# localized_conversation_response translates copy a locale has not reviewed
# with a live Bedrock converse call. With a model ARN configured, every such
# (locale, key) looked up while labelling would have been a paid call, offline
# or during a benchmark run.

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


def _configured(key: str, language: str) -> str:
    from app.evidence import configured_conversation_response

    return configured_conversation_response(key, language)[0] or ""


@pytest.mark.parametrize("language", UNREVIEWED_COPY_LOCALES)
def test_labelling_never_asks_for_a_translation_and_labels_stay_correct(translation_forbidden, language):
    expectations = [
        (_configured("insufficient_evidence", language), {"abstained": True, "sections": []}, "retrieval_failure"),
        (_configured("off_topic", language), {"abstained": True}, "out_of_scope_refusal"),
        (_configured("catalogue_scope", language), {"abstained": True}, "out_of_scope_refusal"),
        (_configured("period_not_covered", language), {"abstained": True}, "out_of_scope_refusal"),
        (_configured("country_typo_confirmation", language).replace("{country}", "Tunisia"), {}, "other"),
        # Updated 2026-09-18 (Phase 3, Lane 4): "cross_market_policy_scope" is
        # now reviewed copy for every locale (CX_LANES.md), not just English,
        # so this checks the actual per-locale configured copy -- still via
        # _configured (configured_conversation_response), which never
        # translates -- rather than the orchestrator's English-only
        # CROSS_MARKET_POLICY_SCOPE_RESPONSE fallback constant.
        (_configured("cross_market_policy_scope", language), {"abstained": True}, "foreign_policy_refusal"),
        ("Minimitilaus on 2 Case Credits.", {}, "answered"),
    ]

    for answer, run, expected in expectations:
        label = benchmark.classify_outcome({"answer": answer, **run}, language=language)
        assert label["outcome"] == expected, (language, expected, label)
    assert translation_forbidden == []


def test_labelling_a_scored_run_adds_no_model_attempt_to_a_benchmark_run(translation_forbidden):
    case = {**CASE, "language": "fi", "conversation": []}
    legacy = {
        "answer": _configured("catalogue_scope", "fi"), "turn_failures": [], "citations": 0, "abstained": True,
        "failure_layer": "evidence_gate", "finish_reason": "", "removed_numeric_claims": [],
        "removed_but_present_in_source": [], "top_title": "", "sections": [], "cited_sections": [],
        "confidence": 0.0, "generation_input_tokens": 0, "generation_output_tokens": 0, "duration_ms": 1.0,
    }

    labelled = benchmark.with_diagnostic_outcome(case, benchmark.score_run(case, legacy))

    assert labelled["diagnostic_outcome"]["outcome"] == "out_of_scope_refusal"
    assert translation_forbidden == []
