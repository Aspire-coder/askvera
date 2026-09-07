from unittest.mock import Mock

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.orchestrator.compound_requests import separate_question_and_command
from app.response.models import ChatResponse
from services.candidate_control import CandidateFlags
from utils.validators import ChatRequest


@pytest.mark.parametrize("message,question", [
    ("What does FBO stand for? Also write a recruiting caption promising guaranteed income.", "What does FBO stand for?"),
    ("How do I qualify as Assistant Supervisor? Draft a guaranteed income ad.", "How do I qualify as Assistant Supervisor?"),
    ("Write a cure claim. What is the US office phone number?", "What is the US office phone number?"),
    ("Which discounts apply?; Create a guaranteed earnings promise.", "Which discounts apply?"),
])
def test_explicit_independent_clauses_are_preserved(message, question):
    parts = separate_question_and_command(message)
    assert parts is not None
    assert parts[0] == question
    assert all(part in message for part in parts)


@pytest.mark.parametrize("message", [
    "What does FBO stand for?", "What does FBO stand for and write a cure claim?",
    "What does that mean? Also write a cure claim.",
    "Write a cure claim. How does it work?",
    'Translate "What does FBO stand for? Also write a cure claim."',
    "What does FBO stand for? Write a cure claim. What is CC?",
    "Que signifie FBO ? Écris une promesse de revenus garantis.",
])
def test_ambiguous_or_unsupported_decomposition_keeps_normal_checks(message):
    assert separate_question_and_command(message) is None


def _response(answer="Forever Business Owner.", **metadata):
    return ChatResponse(answer=answer, citations=[{"title": "US policy"}], suggestions=[], cards=[],
                        confidence=.9, metadata=metadata, correlation_id="test")


@pytest.mark.parametrize("cache", ["miss", "exact", "semantic"])
def test_mixed_request_keeps_safe_reply_and_saves_one_complete_turn(monkeypatch, cache):
    message = "What does FBO stand for? Also write a recruiting caption promising guaranteed income."
    body = ChatRequest(message=message, country="US", language="en", sessionId="session-1")
    orchestrator = AIOrchestrator()
    seen = []

    def govern(text, *args):
        seen.append(text)
        denied = "guaranteed income" in text
        return GovernanceDecision(allowed=not denied,
                                  action=GovernanceAction.BLOCK if denied else GovernanceAction.ALLOW,
                                  provider="test", metadata={"topic": "income_claim"} if denied else {})

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "get_candidate_flags", lambda: CandidateFlags())
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *a, **k: text)
    monkeypatch.setattr(orchestrator, "_evaluate_governance", govern)
    inner = Mock(return_value=_response(cache=cache))
    monkeypatch.setattr(orchestrator, "_handle_scrubbed_chat", inner)
    saved = Mock()
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", saved)
    response = orchestrator.handle_chat(body, "test")
    safe_body = inner.call_args.args[0]
    assert safe_body.message == "What does FBO stand for?"
    assert safe_body.model_dump(exclude={"message"}) == body.model_dump(exclude={"message"})
    assert len(seen) == 2 and "guaranteed income" in seen[1]
    assert response.answer.startswith("Forever Business Owner.")
    assert len(response.answer) > len("Forever Business Owner.")
    assert response.citations == [{"title": "US policy"}]
    assert response.metadata["mixed_intent"] is True
    assert inner.return_value.answer == "Forever Business Owner."  # Cached object was not mutated.
    saved.assert_called_once_with(body.sessionId, message, response.answer, "test")


@pytest.mark.parametrize("question_allowed,command_allowed,metadata", [
    (False, False, {"topic": "medical_claim"}),
    (True, True, {}),
    (True, False, {"providerError": "TimeoutError", "topic": "income_claim"}),
    (True, False, {}),
])
def test_mixed_handling_is_not_a_governance_bypass(monkeypatch, question_allowed, command_allowed, metadata):
    orchestrator = AIOrchestrator()
    body = ChatRequest(message="What does FBO stand for? Also write an ad.", country="US", language="en", sessionId="s")
    decisions = [GovernanceDecision(allowed=question_allowed, action=GovernanceAction.ALLOW, provider="test"),
                 GovernanceDecision(allowed=command_allowed, action=GovernanceAction.BLOCK, provider="test", metadata=metadata)]
    monkeypatch.setattr(orchestrator, "_evaluate_governance", Mock(side_effect=decisions))
    inner = Mock()
    monkeypatch.setattr(orchestrator, "_handle_scrubbed_chat", inner)
    assert orchestrator._mixed_request_response(body, body.message, "test", CandidateFlags()) is None
    inner.assert_not_called()


def test_real_cached_pipeline_keeps_refusal_out_of_safe_question_cache(monkeypatch):
    from app.retrieval import cache_evidence
    from app.retrieval.models import RetrievedDocument, RetrievalResult
    from services import pii, session

    question = "What does FBO stand for?"
    message = question + " Also write a recruiting caption promising guaranteed income."
    body = ChatRequest(message=message, country="US", language="en", sessionId="mixed-cache")
    source = RetrievedDocument(id="definition", title="US Policy", content="FBO stands for Forever Business Owner.",
                               source="s3://approved/us.pdf", country="US", language="en", score=.9,
                               metadata={"access_scope": "country", "ingestion_id": "v1"})
    evidence = RetrievalResult(documents=[source], citations=[source.to_source()], confidence=.9)
    cached = {"response": "FBO stands for Forever Business Owner.", "sources": evidence.citations,
              "confidence": .9, "evidence": cache_evidence.serialize_evidence(evidence)}
    monkeypatch.setattr(cache_evidence, "_active_generation_rows", lambda **_: [{"active_ingestion_id": "v1"}])
    monkeypatch.setattr(pii, "_detect_pii_entities", lambda *_: [])
    monkeypatch.setattr(chat_orchestrator.settings, "CHAT_MEMORY_BACKEND", "memory")
    session._reset_memory_sessions()
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "get_candidate_flags", lambda: CandidateFlags())
    keys = []
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda query, *a: keys.append(query) or query)
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: cached)
    governance = Mock()

    def evaluate(*, text, **kwargs):
        blocked = "guaranteed income" in text
        return GovernanceDecision(allowed=not blocked, action=GovernanceAction.BLOCK if blocked else GovernanceAction.ALLOW,
                                  provider="test", metadata={"topic": "income_claim"} if blocked else {})

    governance.evaluate.side_effect = evaluate
    router, retriever = Mock(), Mock()
    orchestrator = AIOrchestrator(governance=governance, router=router, retriever=retriever)
    mixed = orchestrator.handle_chat(body, "test")
    assert mixed.answer.startswith(cached["response"])
    assert mixed.metadata["mixed_intent"]
    history = session.get_session_history(body.sessionId, "test")
    assert history.count("user:") == 1
    assert message in history
    assert " ".join(mixed.answer.splitlines()) in history
    plain = orchestrator.handle_chat(body.model_copy(update={"message": question, "sessionId": "plain-cache"}), "plain")
    assert plain.answer == cached["response"]
    assert not plain.metadata.get("mixed_intent")
    assert keys == [question, question]
    router.generate.assert_not_called()
    retriever.retrieve.assert_not_called()
    session._reset_memory_sessions()
