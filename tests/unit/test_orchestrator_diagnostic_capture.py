"""The orchestrator's diagnostic capture records what happened and changes nothing delivered.

Numeric repair replaces the answer and only the removed figures survived in
metadata, so a missing figure could not be told apart from generation variance.
The capture keeps the answer repair was handed, the validator findings and each
removal's reason. It is off by default; the benchmark alone turns it on. With it
on, the delivered answer, citations and repair decision are identical, and the
record appears in neither the public API metadata nor the cache value.

No network: session, consent, caches, audit and the model are faked; the
output validator and numeric repair are the real ones.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from config import settings
from utils.exceptions import SessionExpiredError
from utils.validators import ChatRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = "The service fee is 2.50."
INVENTED = "The delivery fee is 18.75."


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("run_benchmark", PROJECT_ROOT / "scripts" / "run_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Retriever:
    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        document = RetrievedDocument(
            id="fees", title="Policy - Sec 13.01: Fees", content=SOURCE,
            source="opensearch-section://CA-EN-Company-Policy.pdf/13.01", country="CA", language="en", score=0.9,
            metadata={"section_id": "13.01", "access_scope": "country", "ingestion_id": "ingestion-1"},
        )
        return RetrievalResult(
            documents=[document], citations=[document.to_source()], confidence=0.9,
            metadata={"provider": "opensearch_section", "candidate_sources": [document.to_source()],
                      "evidence_selector_confidence": 0.9},
        )


class _Router:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text=self.text, citations=[], confidence=0.9, provider="test", model_name="model-under-test")


@pytest.fixture
def ask(monkeypatch):
    stubs = {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text,
        "build_cache_key": lambda *_: "cache-key",
        "get_cache_value": lambda *_: None,
        "set_cache_value": lambda *_: None,
        "append_session_turn": lambda *_: None,
        "write_audit_event": lambda *_: None,
        "get_session_history": lambda *_: "",
        "semantic_cache_active": lambda *_, **__: False,
        "get_semantic_cache_value": lambda *_, **__: None,
        "set_semantic_cache_value": lambda *_, **__: None,
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(chat_orchestrator, name, stub)

    def run(answer: str, *, capture: bool | None, message: str = "What is the service fee?"):
        # None leaves the flag to whoever set it, such as the benchmark's own switch.
        if capture is not None:
            monkeypatch.setattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED", capture)
        orchestrator = AIOrchestrator(retriever=_Retriever(), router=_Router(answer), governance=_Governance())
        return orchestrator.handle_chat(
            ChatRequest(message=message, sessionId="session-1", country="CA", language="en"), "correlation"
        )

    return run


def _delivered(response) -> tuple:
    metadata = {key: value for key, value in response.metadata.items() if key != "diagnostic_capture"}
    return response.answer, response.citations, response.confidence, metadata


def test_capture_is_off_by_default():
    assert chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED is False


def test_with_capture_off_no_record_is_attached(ask):
    assert "diagnostic_capture" not in ask(SOURCE, capture=False).metadata


def test_capture_changes_nothing_delivered_on_a_grounded_answer(ask):
    off = ask(SOURCE, capture=False)
    on = ask(SOURCE, capture=True)

    assert _delivered(on) == _delivered(off)
    capture = on.metadata["diagnostic_capture"]
    assert capture["version"] == chat_orchestrator.DIAGNOSTIC_CAPTURE_VERSION
    assert [retrieval["stage"] for retrieval in capture["retrievals"]] == ["question"]
    assert capture["retrievals"][0]["documents"][0]["ingestion_id"] == "ingestion-1"
    assert capture["retrievals"][0]["candidate_sections"] == [
        {"section": "13.01", "country": "CA", "uri": "opensearch-section://CA-EN-Company-Policy.pdf/13.01", "score": 0.9},
    ]
    assert capture["validations"][-1]["outcome"] == "no_critical_issue"
    assert capture["validations"][-1]["answer_before_validation"] == on.answer


def test_capture_keeps_the_answer_repair_was_handed_and_why_each_figure_went(ask):
    off = ask(f"{INVENTED} {SOURCE}", capture=False)
    on = ask(f"{INVENTED} {SOURCE}", capture=True)

    assert _delivered(on) == _delivered(off)
    assert "18.75" not in on.answer
    validation = on.metadata["diagnostic_capture"]["validations"][-1]
    assert "18.75" in validation["answer_before_validation"]
    assert "NUMERIC_CLAIM_UNGROUNDED" in {issue["code"] for issue in validation["issues"]}
    repair = validation["numeric_repair"]
    assert validation["outcome"] == "numeric_repair_accepted" and repair["accepted"] is True
    assert repair["removed_numeric_claims"] == ["18.75"]
    assert repair["removal_reasons"] == [{"number": "18.75", "present_in_source": False, "reason": "unsupported_numeric_claim"}]
    assert repair["answer_after_repair"] == on.answer
    assert repair["post_repair_issues"] is not None


def test_the_capture_reaches_neither_the_api_response_nor_the_cache(ask):
    response = ask(f"{INVENTED} {SOURCE}", capture=True)

    for public in (response.to_api_result(), response.to_cache_value()):
        text = json.dumps(public, default=str)
        assert "diagnostic_capture" not in text
        assert "18.75" not in text


def test_the_capture_context_ends_with_the_request_even_when_it_raises(monkeypatch, ask):
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: False)

    with pytest.raises(SessionExpiredError):
        ask(SOURCE, capture=True)

    assert chat_orchestrator._DIAGNOSTIC_CAPTURE.get() is None


def test_the_office_contact_lookup_is_recorded_as_its_own_stage(monkeypatch):
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", True)
    orchestrator = AIOrchestrator(retriever=_Retriever(), governance=_Governance())
    token = chat_orchestrator._DIAGNOSTIC_CAPTURE.set({"version": 1, "retrievals": [], "validations": []})
    try:
        orchestrator._office_contact_addendum(
            ChatRequest(message="Office?", sessionId="session-1", country="CA", language="en"), "correlation"
        )
        capture = chat_orchestrator._DIAGNOSTIC_CAPTURE.get()
    finally:
        chat_orchestrator._DIAGNOSTIC_CAPTURE.reset(token)

    assert [retrieval["stage"] for retrieval in capture["retrievals"]] == ["office_contact_lookup"]


def test_the_benchmark_reads_exactly_what_the_orchestrator_emits(ask):
    """Contract between the two: the runner's per-turn fields come from this record."""
    benchmark = _load_benchmark()

    with benchmark._orchestrator_diagnostic_capture() as status:
        response = ask(f"{INVENTED} {SOURCE}", capture=None)

    assert status == "enabled"
    assert chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED is False
    turn = benchmark.turn_record("final", response)
    assert "18.75" in turn["pre_repair_answer"]
    assert "18.75" not in turn["answer"]
    assert turn["removed_claims"] == [{"number": "18.75", "present_in_source": False, "reason": "unsupported_numeric_claim"}]
    assert turn["validation_outcome"] == "numeric_repair_accepted"
    assert "NUMERIC_CLAIM_UNGROUNDED" in {issue["code"] for issue in turn["validator_issues"]}
    assert turn["metadata"]["model_name"] == "model-under-test"


class _Exploding:
    """Stands in for something recording iterates, and fails the moment it is used."""

    def __iter__(self):
        raise RuntimeError("diagnostic recording bug")


def test_a_failing_retrieval_record_never_changes_the_delivered_response(ask, monkeypatch):
    monkeypatch.setattr(chat_orchestrator, "_CAPTURED_RETRIEVAL_METADATA", _Exploding())

    off = ask(SOURCE, capture=False)
    on = ask(SOURCE, capture=True)

    assert _delivered(on) == _delivered(off)
    capture = on.metadata["diagnostic_capture"]
    assert capture["retrievals"] == []
    assert capture["errors"] == ["question"]


@pytest.mark.parametrize("answer", [SOURCE, f"{INVENTED} {SOURCE}"], ids=["no-critical-issue", "numeric-repair"])
def test_a_failing_validation_record_never_changes_the_delivered_response(ask, monkeypatch, answer):
    def explode(*_args, **_kwargs):
        raise RuntimeError("diagnostic recording bug")

    monkeypatch.setattr(chat_orchestrator, "_captured_issues", explode)

    off = ask(answer, capture=False)
    on = ask(answer, capture=True)

    assert _delivered(on) == _delivered(off)
    capture = on.metadata["diagnostic_capture"]
    assert capture["validations"] == []
    assert capture["errors"] and all(stage.startswith("validation:") for stage in capture["errors"])
