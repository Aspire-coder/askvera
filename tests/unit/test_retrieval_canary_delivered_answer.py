"""The canary's delivered-answer stage: what the user is actually shown.

Retrieval scoring cannot see anything after a document is selected. On
2026-09-07 every defect found after the selector regression lived downstream of
it, and the canary passed 15/15 while a rank-qualification question failed in
production - answers were discarded at output validation, or delivered with the
governing figure silently removed by numeric repair.

These tests cover the gate's own logic with a stubbed pipeline. They make no
model calls; the live assertions run at deploy time.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_retrieval_canary", PROJECT_ROOT / "scripts" / "run_retrieval_canary.py"
)
canary = importlib.util.module_from_spec(_SPEC)
sys.modules["run_retrieval_canary"] = canary
_SPEC.loader.exec_module(canary)

FALLBACK = "The approved policy documents currently available do not contain enough information."
GOOD_ANSWER = "To become a Recognized Manager you need 120 Open Group Case Credits."


def _case(**overrides):
    case = {
        "id": "case",
        "question": "How can I become a recognized manager?",
        "country": "US",
        "language": "en",
        "role": "new_prospect",
        "expected_title_contains": "Recognized Manager",
        "minimum_confidence": 0.0,
        "evidence_must_be_approved": True,
    }
    case.update(overrides)
    return case


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub retrieval and approval so only the delivered-answer logic is tested."""
    document = SimpleNamespace(
        title="US-EN-Company-Policy.pdf - Sec 5.01: Recognized Manager:",
        metadata={"section_id": "5.01"},
        score=4.3,
    )
    retrieval = SimpleNamespace(documents=[document], confidence=0.95, metadata={})

    class _Service:
        def retrieve(self, *args, **kwargs):
            return retrieval

    monkeypatch.setitem(
        sys.modules, "app.retrieval.service", SimpleNamespace(RetrievalService=_Service)
    )
    monkeypatch.setitem(
        sys.modules,
        "app.evidence",
        SimpleNamespace(approve_evidence=lambda *a, **k: SimpleNamespace(approved=True, reason="")),
    )
    return retrieval


def _answer(text, citations=1):
    return lambda case, sequence: (text, citations)


def test_a_delivered_fallback_fails_the_case(stub_pipeline, monkeypatch):
    """The exact failure the retrieval-only gate could not see."""
    monkeypatch.setattr(canary, "delivered_answer", _answer(FALLBACK, citations=0))
    outcome = canary.run_case_once(
        _case(answer_must_contain=["120"], answer_must_not_contain=["do not contain enough information"]),
        1,
    )
    assert not outcome["passed"]
    assert any("missing '120'" in reason for reason in outcome["failure_reasons"])
    assert any("do not contain enough information" in reason for reason in outcome["failure_reasons"])


def test_a_silently_stripped_figure_fails_the_case(stub_pipeline, monkeypatch):
    """Repair removing the governing number is the quieter, more dangerous failure.

    The answer reads fluently and cites a source; only the figure is gone.
    """
    stripped = "To become a Recognized Manager you must meet the Case Credit requirement."
    monkeypatch.setattr(canary, "delivered_answer", _answer(stripped, citations=1))
    outcome = canary.run_case_once(_case(answer_must_contain=["120"]), 1)

    assert not outcome["passed"]
    assert any("missing '120'" in reason for reason in outcome["failure_reasons"])


def test_a_grounded_answer_passes(stub_pipeline, monkeypatch):
    monkeypatch.setattr(canary, "delivered_answer", _answer(GOOD_ANSWER, citations=1))
    outcome = canary.run_case_once(
        _case(answer_must_contain=["120"], answer_must_cite=True),
        1,
    )
    assert outcome["passed"], outcome["failure_reasons"]
    assert outcome["answer_citations"] == 1


def test_an_uncited_answer_fails_when_a_citation_is_required(stub_pipeline, monkeypatch):
    monkeypatch.setattr(canary, "delivered_answer", _answer(GOOD_ANSWER, citations=0))
    outcome = canary.run_case_once(_case(answer_must_contain=["120"], answer_must_cite=True), 1)

    assert not outcome["passed"]
    assert any("no citation" in reason for reason in outcome["failure_reasons"])


def test_cases_without_answer_requirements_make_no_generation_call(stub_pipeline, monkeypatch):
    """Existing cases stay retrieval-only, so the gate's cost does not jump."""
    def _fail(*args, **kwargs):
        raise AssertionError("delivered_answer must not run for a retrieval-only case")

    monkeypatch.setattr(canary, "delivered_answer", _fail)
    outcome = canary.run_case_once(_case(), 1)

    assert outcome["passed"], outcome["failure_reasons"]
    assert outcome["answer_citations"] == -1


def test_shipped_fixture_has_delivered_answer_coverage():
    """The gate must actually assert a delivered answer somewhere."""
    fixture = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "retrieval_canary.json").read_text(encoding="utf-8"))
    checked = [case for case in fixture["cases"] if case.get("answer_must_contain")]

    assert checked, "no canary case asserts a delivered answer"
    for case in checked:
        assert case.get("answer_must_not_contain"), f"{case['id']} should reject the abstention fallback"
