"""Unit tests for AI chat orchestration safety paths."""

from unittest.mock import MagicMock

from config import settings
from app.governance.engine import GovernanceEngine
from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from services.semantic_cache import SemanticCacheHit
from utils.validators import ChatRequest


class _FakeGovernance:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def evaluate(self, *, text: str, **_: object) -> GovernanceDecision:
        self.seen_texts.append(text)
        if text == "cached unsafe answer":
            return GovernanceDecision(
                allowed=False,
                action=GovernanceAction.BLOCK,
                provider="test",
                reason="Blocked cached answer.",
            )
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _FakeValidator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _FakeRetriever:
    def __init__(self) -> None:
        self.seen_messages: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen_messages.append(message)
        document = RetrievedDocument(
            id="recognized-manager",
            title="Policy - Sec 5.01: Recognized Manager",
            content="A Forever Business Owner can become a Recognized Manager by meeting the policy requirements.",
            source="s3://approved/policy.pdf",
            country="CA",
            language="en",
            score=0.8,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)


class _FakeRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text="Here is more detail about becoming a Recognized Manager.",
            citations=[],
            confidence=0.8,
            provider="test",
            model_name="test",
        )


class _GuardrailRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text="I can't provide medical advice or treatment claims.",
            citations=[],
            confidence=0.0,
            provider="bedrock",
            model_name="test",
            finish_reason="guardrail_intervened",
        )


def test_cached_response_is_checked_by_output_governance(monkeypatch) -> None:
    """Cached responses still pass through current governance before returning."""
    governance = _FakeGovernance()
    router = MagicMock()
    orchestrator = AIOrchestrator(router=router, validator=_FakeValidator(), governance=governance)
    body = ChatRequest(message="What is the FBO Support Fee?", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(
        chat_orchestrator,
        "get_cache_value",
        lambda *_: {"response": "cached unsafe answer", "sources": [], "confidence": 0.9},
    )

    response = orchestrator.handle_chat(body, "cid")

    assert governance.seen_texts == ["What is the FBO Support Fee?", "cached unsafe answer"]
    assert response.answer == "Blocked cached answer."
    assert response.metadata["fallback"] is True
    router.generate.assert_not_called()


def test_followup_about_first_question_uses_anchor_for_retrieval(monkeypatch) -> None:
    """Vague follow-ups retrieve with the original topic, not generic follow-up text."""
    governance = _FakeGovernance()
    retriever = _FakeRetriever()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=_FakeRouter(),
        validator=_FakeValidator(),
        governance=governance,
    )
    body = ChatRequest(message="explain me more about my first question", sessionId="session-1", country="CA", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    monkeypatch.setattr(
        chat_orchestrator,
        "get_session_history",
        lambda *_: "\n".join(
            [
                "user: how can i become a recognized manager",
                "vera: Recognized Manager answer",
                "user: how can i become a diamond manager",
                "vera: Diamond Manager answer",
            ]
        ),
    )

    response = orchestrator.handle_chat(body, "cid")

    assert response.answer == "Here is more detail about becoming a Recognized Manager."
    assert retriever.seen_messages == ["how can i become a recognized manager"]
    assert governance.seen_texts[0] == (
        "how can i become a recognized manager\n"
        "Follow-up request: explain me more about my first question"
    )


def test_more_details_uses_latest_self_contained_question() -> None:
    """A natural elaboration request reuses the latest substantive question."""
    orchestrator = AIOrchestrator()
    history = "\n".join(
        [
            "user: How can I sign up in Belgium?",
            "vera: Use the online registration page.",
        ]
    )

    query = orchestrator._build_retrieval_query("I need more details", history, "cid")

    assert query == "How can I sign up in Belgium?"
    assert orchestrator._build_request_query("I need more details", query, history) == (
        "How can I sign up in Belgium?\nFollow-up request: I need more details"
    )


def test_chained_followup_skips_prior_vague_followup() -> None:
    """Repeated elaboration requests stay anchored to the substantive topic."""
    orchestrator = AIOrchestrator()
    history = "\n".join(
        [
            "user: How can I sign up in Belgium?",
            "vera: Use the online registration page.",
            "user: I need more details",
            "vera: Here are additional registration details.",
        ]
    )

    query = orchestrator._build_retrieval_query("Can you elaborate?", history, "cid")

    assert query == "How can I sign up in Belgium?"
    assert orchestrator._build_request_query("Can you elaborate?", query, history) == (
        "How can I sign up in Belgium?\nFollow-up request: Can you elaborate?"
    )


def test_topic_shift_followup_merges_new_subject_with_prior_topic() -> None:
    """'What about X' keeps the prior topic and adds the new subject, instead of losing it."""
    orchestrator = AIOrchestrator()
    history = "\n".join(
        [
            "user: What are the office hours in Kenya?",
            "vera: Kenya office hours are Monday to Friday, 9am to 5pm.",
        ]
    )

    query = orchestrator._build_retrieval_query("What about Uganda?", history, "cid")

    assert query == "What are the office hours in Kenya? What about Uganda?"


def test_and_in_country_followup_is_not_yet_recognized_as_topic_shift() -> None:
    """Documents current scope: only 'what about'/'how about'/'what if' merge new subjects."""
    orchestrator = AIOrchestrator()
    history = "user: What are the office hours in Kenya?\nvera: Kenya office hours are Monday to Friday."

    assert orchestrator._build_retrieval_query("And in Uganda?", history, "cid") == "And in Uganda?"


def test_short_standalone_question_does_not_inherit_history() -> None:
    """A complete new topic remains independent even when it is concise."""
    orchestrator = AIOrchestrator()
    history = "user: How can I sign up in Belgium?\nvera: Use the online registration page."
    question = "What is the minimum order size for Belgium?"

    assert orchestrator._build_retrieval_query(question, history, "cid") == question


def test_followup_marker_is_not_matched_inside_policy_word() -> None:
    """The marker 'it' must not make an independent policy question contextual."""
    orchestrator = AIOrchestrator()
    history = "user: How can I sign up in Belgium?\nvera: Use the online registration page."
    question = "What is the refund policy?"

    assert orchestrator._build_retrieval_query(question, history, "cid") == question


def test_fallback_responses_are_not_cacheable() -> None:
    """Validation and governance fallbacks should not be reused as normal answers."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="I found related policy information, but I'm not confident enough to answer.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.0,
        metadata={"fallback": True},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_critical_validation_responses_are_not_cacheable() -> None:
    """Responses carrying critical validation metadata should not be cached."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="Some answer",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={"validation": {"highestSeverity": "CRITICAL"}},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_guardrail_response_is_not_cacheable() -> None:
    """Safety copy must not be replayed as a normal answer from cache."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="I cannot provide medical advice.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.0,
        metadata={"failure_layer": "aws_guardrail", "response_source": "guardrail"},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_low_confidence_response_is_not_cacheable(monkeypatch) -> None:
    """Weak generated answers must not become exact-cache entries."""
    orchestrator = AIOrchestrator()
    monkeypatch.setattr(chat_orchestrator.settings, "BEDROCK_MIN_CONFIDENCE", 0.47)
    response = ChatResponse(
        answer="Generic contact response.",
        citations=[{"title": "Unrelated policy"}],
        suggestions=[],
        cards=[],
        confidence=0.185,
        metadata={"response_source": "model"},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_semantic_cache_requires_citations_and_high_confidence(monkeypatch) -> None:
    """Only strong grounded answers can enter semantic reuse."""
    orchestrator = AIOrchestrator()
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_MIN_CONFIDENCE", 0.75)
    response = ChatResponse(
        answer="Approved policy answer.",
        citations=[{"title": "Policy"}],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={},
        correlation_id="cid",
    )

    assert orchestrator._should_semantic_cache_response(response) is True
    assert orchestrator._should_semantic_cache_response(
        ChatResponse(**{**response.__dict__, "citations": []})
    ) is False
    assert orchestrator._should_semantic_cache_response(
        ChatResponse(**{**response.__dict__, "confidence": 0.5})
    ) is False


def test_semantic_cache_lookup_uses_current_retrieval_evidence(monkeypatch) -> None:
    """Semantic lookup receives current evidence and avoids model generation on a hit."""
    router = MagicMock()
    orchestrator = AIOrchestrator(router=router, validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(
        message="What is a recognised manager?",
        sessionId="session-1",
        country="US",
        language="en",
    )
    result = _FakeRetriever().retrieve("question")
    seen: list[RetrievalResult] = []
    appended: list[tuple[object, ...]] = []

    def _semantic(*args: object) -> SemanticCacheHit:
        seen.append(args[4])
        return SemanticCacheHit(
            response={
                "response": "A grounded cached answer.",
                "sources": [{"title": "Policy"}],
                "confidence": 0.9,
            },
            similarity=0.98,
            candidates_checked=3,
        )

    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", _semantic)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *args: appended.append(args))
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator.pipeline_trace_store, "record", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: True)

    response, candidate, lookup_ms = orchestrator._semantic_cached_response(
        "question", result, body, "cid", "scrubbed"
    )

    assert seen == [result]
    assert response is not None
    assert candidate is not None
    assert lookup_ms >= 0
    assert response.answer == "A grounded cached answer."
    assert response.metadata["cache"] == "semantic"
    assert response.metadata["semantic_cache_similarity"] == 0.98
    assert appended[0][1] == "scrubbed"
    router.generate.assert_not_called()


def test_semantic_cache_failure_falls_through(monkeypatch) -> None:
    """A semantic miss leaves the normal answer path available."""
    orchestrator = AIOrchestrator(validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(message="Question", sessionId="session-1", country="US", language="en")
    result = _FakeRetriever().retrieve("question")
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: True)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)
    monkeypatch.setattr(chat_orchestrator.pipeline_trace_store, "record", lambda *_args, **_kwargs: None)

    response, candidate, _ = orchestrator._semantic_cached_response("question", result, body, "cid")
    assert response is None
    assert candidate is None


def test_shadow_mode_observes_hit_but_always_returns_fresh_path(monkeypatch) -> None:
    """Shadow candidates are measured and never returned to the user."""
    orchestrator = AIOrchestrator(validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(message="Question", sessionId="session-1", country="US", language="en")
    result = _FakeRetriever().retrieve("question")
    candidate = SemanticCacheHit(
        response={
            "response": "Cached policy answer",
            "sources": [{"uri": "s3://approved/policy.pdf"}],
            "confidence": 0.9,
        },
        similarity=0.98,
        candidates_checked=2,
    )
    traces: list[dict[str, object]] = []
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: True)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: candidate)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)
    monkeypatch.setattr(
        chat_orchestrator.pipeline_trace_store,
        "record",
        lambda *_args, **kwargs: traces.append(dict(kwargs.get("metadata") or {})),
    )

    response, observed, _ = orchestrator._semantic_cached_response("question", result, body, "cid")

    assert response is None
    assert observed == candidate
    assert traces[-1]["wouldHit"] is True
    assert traces[-1]["cacheHit"] is False
    assert traces[-1]["served"] is False


def test_shadow_result_records_privacy_safe_comparison(monkeypatch) -> None:
    """Shadow reporting contains scores and savings, not answer text."""
    orchestrator = AIOrchestrator()
    body = ChatRequest(message="Question", sessionId="session-1", country="US", language="en")
    candidate = SemanticCacheHit(
        response={
            "response": "Become a recognized manager by meeting approved requirements.",
            "sources": [{"uri": "s3://approved/policy.pdf"}],
            "confidence": 0.9,
        },
        similarity=0.98,
        candidates_checked=2,
    )
    fresh = ChatResponse(
        answer="Meet the approved requirements to become a recognized manager.",
        citations=[{"uri": "s3://approved/policy.pdf"}],
        suggestions=[],
        cards=[],
        confidence=0.88,
        metadata={"token_usage": {"inputTokens": 1200, "outputTokens": 180}},
        correlation_id="cid",
    )
    traces: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT", 0.5)
    monkeypatch.setattr(
        chat_orchestrator.pipeline_trace_store,
        "record",
        lambda *_args, **kwargs: traces.append(dict(kwargs.get("metadata") or {})),
    )
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda event, *_: audits.append(event))

    orchestrator._record_semantic_shadow_result(candidate, fresh, body, "cid", 12.5)

    assert traces[-1]["estimatedTokensSaved"] == 1380
    assert traces[-1]["cacheHit"] is False
    assert traces[-1]["citationAgreement"] == 1.0
    assert audits[-1]["type"] == "semantic_cache_shadow"
    serialized = str(traces[-1]) + str(audits[-1])
    assert candidate.response["response"] not in serialized
    assert fresh.answer not in serialized


def test_shadow_hit_does_not_replace_fresh_answer_in_full_flow(monkeypatch) -> None:
    """End-to-end orchestration still calls the model and returns its answer in shadow mode."""
    router = MagicMock()
    router.generate.return_value = ModelResponse(
        text="Fresh grounded answer from the normal model path.",
        citations=[],
        confidence=0.8,
        provider="test",
        model_name="test",
    )
    orchestrator = AIOrchestrator(
        retriever=_FakeRetriever(),
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="What steps are required for Recognized Manager?",
        sessionId="session-1",
        country="CA",
        language="en",
    )
    candidate = SemanticCacheHit(
        response={
            "response": "Cached answer that must not be delivered.",
            "sources": [{"uri": "s3://approved/policy.pdf"}],
            "confidence": 0.9,
        },
        similarity=0.99,
        candidates_checked=1,
    )
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator.settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: candidate)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert response.answer == "Fresh grounded answer from the normal model path."
    assert response.metadata["cache"] == "miss"
    assert "Cached answer that must not be delivered." not in response.answer
    router.generate.assert_called_once()


def test_response_completion_restores_only_approved_directory_contacts(monkeypatch) -> None:
    """Directory answers regain omitted exact fields before outbound validation."""
    orchestrator = AIOrchestrator()
    document = RetrievedDocument(
        id="directory-office",
        title="Example office",
        content="Office Address\n10 Example Road\nOffice Phone 1\n+99 123 456 7890",
        source="s3://approved/global-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_fields": {
                "Office Address": "10 Example Road",
                "Office Phone 1": "+99 123 456 7890",
            }
        },
    )
    response = ChatResponse(
        answer="The approved office address is 10 Example Road.",
        citations=[document.to_source()],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={},
        correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)

    completed = orchestrator._secure_and_complete_response(
        response,
        result,
        "fr",
        "cid",
        user_question="Where is the office?",
    )

    assert completed.answer.count("10 Example Road") == 1
    assert "Office Phone 1: +99 123 456 7890" in completed.answer
    assert completed.metadata["directory_contacts_restored"] == ["Office Phone 1"]


def test_response_completion_does_not_change_policy_answers(monkeypatch) -> None:
    """Policy answers remain byte-for-byte unchanged by directory completion."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="A Recognized Manager must meet the approved policy requirements.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={},
        correlation_id="cid",
    )
    document = RetrievedDocument(
        id="policy",
        title="Policy",
        content="Approved policy requirements.",
        source="s3://approved/policy.pdf",
        country="CA",
        language="en",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)

    completed = orchestrator._secure_and_complete_response(
        response,
        result,
        "en",
        "cid",
        user_question="What are the requirements?",
    )

    assert completed.answer == response.answer
    assert "directory_contacts_restored" not in completed.metadata


def test_response_completion_does_not_append_contacts_without_a_citation(monkeypatch) -> None:
    """A no-match answer must not inherit contacts from an unused candidate."""
    orchestrator = AIOrchestrator()
    document = RetrievedDocument(
        id="unmatched-directory-office",
        title="Another office",
        content="Office Email\nother@example.test",
        source="s3://approved/global-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={"directory_fields": {"Office Email": "other@example.test"}},
    )
    response = ChatResponse(
        answer="I don't have information about Dejan.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.4,
        metadata={},
        correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[], confidence=0.4)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)

    completed = orchestrator._secure_and_complete_response(
        response,
        result,
        "en",
        "cid",
        user_question="Who is Dejan?",
    )

    assert completed.answer == response.answer
    assert "directory_contacts_restored" not in completed.metadata


def test_cached_response_runs_country_aware_final_output_cleanup(monkeypatch) -> None:
    """Legacy cached placeholders cannot bypass the current output gate."""
    orchestrator = AIOrchestrator(validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(
        message="How do I contact Customer Care?",
        sessionId="session-1",
        country="US",
        language="en",
    )
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)

    response = orchestrator._cached_response_value(
        {"response": "Call **** or visit [URL].", "sources": [], "confidence": 0.9},
        body,
        "cid",
        cache_type="exact",
    )

    assert response is not None
    assert response.answer == "Call (888) 440-ALOE (2563) or visit www.foreverliving.com."
    assert response.metadata["cache"] == "exact"


def test_requested_year_outside_approved_document_scope_fails_closed(monkeypatch) -> None:
    """An explicit unsupported year is acknowledged without model speculation."""
    orchestrator = AIOrchestrator(validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(
        message="What policy changes apply in 2027?",
        sessionId="session-1",
        country="US",
        language="en",
    )
    document = RetrievedDocument(
        id="us-policy",
        title="US Company Policy",
        content="The approved document is effective May 1, 2026.",
        source="s3://approved/us/policy.pdf",
        document_version="2026.1",
        country="US",
        language="en",
        score=0.9,
        metadata={"effective_date": "2026-05-01"},
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response, _, decision = orchestrator._route_or_approve_evidence(
        body.message,
        result,
        body.message,
        body,
        "cid",
    )

    assert decision is not None and decision.approved is True
    assert response is not None
    assert "2027" in response.answer
    assert "do not contain information" in response.answer
    assert response.metadata["failure_layer"] == "document_period_not_covered"


def test_directory_evidence_failure_asks_for_a_specific_detail(monkeypatch) -> None:
    """Ambiguous directory requests should invite clarification, not dead-end."""
    orchestrator = AIOrchestrator(validator=_FakeValidator(), governance=_FakeGovernance())
    body = ChatRequest(
        message="Can you help me with the Cameroon office?",
        sessionId="session-1",
        country="US",
        language="en",
    )
    document = RetrievedDocument(
        id="cameroon-directory",
        title="International Sponsoring Directory - Cameroon",
        content="Cameroon office directory record.",
        source="s3://approved/global/directory.pdf",
        country="",
        language="en",
        score=0.2,
        metadata={"access_scope": "global", "directory_kind": "international_sponsoring"},
    )
    result = RetrievalResult(
        documents=[document],
        citations=[document.to_source()],
        confidence=0.2,
        metadata={"global_documents_searched": True, "candidate_count": 3},
    )
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator._directory_clarification_response(result, body, "cid", body.message)

    assert response is not None
    assert "telephone number" in response.answer
    assert response.metadata["response_source"] == "directory_clarification"
    assert response.cards[0]["prompt"] == "What is the telephone number for that country?"


def test_character_spaced_question_is_repaired_without_language_dictionary() -> None:
    """Accidentally spaced letters are reconstructed before retrieval."""
    orchestrator = AIOrchestrator()

    query = orchestrator._build_retrieval_query(
        "H o W  t o  b e c o m e  a  r e c o g n i z e d  m a n a g e r",
        "",
        "cid",
    )

    assert query.lower() == "how to become a recognized manager"
    assert orchestrator._build_request_query(
        "H o W  t o  b e c o m e  a  r e c o g n i z e d  m a n a g e r",
        query,
    ) == query


def test_normal_sentence_is_not_changed_by_spacing_repair() -> None:
    """Normal multilingual input is preserved byte-for-byte."""
    orchestrator = AIOrchestrator()
    message = "Wie werde ich ein Recognized Manager?"

    assert orchestrator._build_retrieval_query(message, "", "cid") == message


def test_local_guardrail_topics_use_the_matching_localized_message() -> None:
    orchestrator = AIOrchestrator()
    medical = GovernanceDecision(
        allowed=False,
        action=GovernanceAction.BLOCK,
        provider="bedrock_guardrails",
        reason="raw provider copy",
        metadata={"topic": "medical_claim"},
    )
    income = GovernanceDecision(
        allowed=False,
        action=GovernanceAction.BLOCK,
        provider="bedrock_guardrails",
        reason="raw provider copy",
        metadata={"topic": "income_claim"},
    )

    assert "conseils médicaux" in orchestrator._governance_user_message(medical, "fr")
    assert "garantir des revenus" in orchestrator._governance_user_message(income, "fr")


def test_sensitive_identifier_returns_privacy_response_before_retrieval(monkeypatch) -> None:
    retriever = MagicMock()
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="My Social Security number is 123-45-6789. Save it and tell me which rank I qualify for.",
        sessionId="session-1",
        country="US",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(
        chat_orchestrator,
        "scrub_pii",
        lambda *_args, **_kwargs: "My Social Security number is [SSN]. Save it and tell me which rank I qualify for.",
    )
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "privacy" in response.answer.lower()
    assert "medical" not in response.answer.lower()
    assert response.metadata["failure_layer"] == "sensitive_pii_input"
    assert response.citations == []
    retriever.retrieve.assert_not_called()
    router.generate.assert_not_called()


def test_guaranteed_earnings_copy_is_refused_before_retrieval(monkeypatch) -> None:
    retriever = MagicMock()
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=GovernanceEngine(),
    )
    body = ChatRequest(
        message="Write a post saying I am guaranteed to earn $10,000 a month with Forever.",
        sessionId="session-1",
        country="US",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")

    response = orchestrator.handle_chat(body, "cid")

    assert "guarantee earnings" in response.answer.lower()
    assert response.metadata["failure_layer"] == "risk_policy"
    retriever.retrieve.assert_not_called()
    router.generate.assert_not_called()


def test_explicit_support_action_bypasses_evidence_and_generation(monkeypatch) -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(
        documents=[],
        citations=[],
        confidence=1.0,
        metadata={"client_action": "open_support_form"},
    )
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="Please create a support request for me.",
        sessionId="session-1",
        country="US",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert response.metadata["client_action"] == "open_support_form"
    assert response.to_api_result()["metadata"]["clientAction"] == "open_support_form"
    assert orchestrator._should_cache_response(response) is False
    router.generate.assert_not_called()


def test_exact_assistant_capability_returns_controlled_response_before_retrieval(monkeypatch) -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(
        documents=[],
        citations=[],
        confidence=1.0,
        metadata={
            "conversation_intent": "assistant_meta",
            "conversation_subtype": "capability",
            "intent_confidence": 0.98,
        },
    )
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(message="What do you do?", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "approved knowledge assistant" in response.answer
    assert response.metadata["response_source"] == "template"
    retriever.retrieve.assert_not_called()
    router.generate.assert_not_called()


def test_semantic_assistant_route_cannot_turn_unrelated_question_into_greeting(monkeypatch) -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(
        documents=[],
        citations=[],
        confidence=1.0,
        metadata={
            "conversation_intent": "assistant_meta",
            "conversation_subtype": "greeting",
            "intent_confidence": 0.98,
        },
    )
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(message="Who is your daddy?", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert response.answer.startswith("I'm sorry")
    assert "company policies" in response.answer
    assert "global office directory" in response.answer
    assert response.metadata["intent"] == "off_topic"
    router.generate.assert_not_called()


def test_semantic_medical_route_never_opens_support_form(monkeypatch) -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(
        documents=[],
        citations=[],
        confidence=1.0,
        metadata={"conversation_intent": "medical_claim", "intent_confidence": 0.98},
    )
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(message="I am having fever.", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "medical advice" in response.answer
    assert "client_action" not in response.metadata
    assert response.metadata["intent"] == "medical_claim"
    router.generate.assert_not_called()


def test_bedrock_guardrail_copy_is_replaced_with_neutral_reviewed_message(monkeypatch) -> None:
    orchestrator = AIOrchestrator(
        retriever=_FakeRetriever(),
        router=_GuardrailRouter(),
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="Explain the recognized manager requirements.",
        sessionId="session-1",
        country="CA",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "safety checks" in response.answer
    assert "medical advice" not in response.answer
    assert response.metadata["failure_layer"] == "aws_guardrail"


def test_office_contact_addendum_is_off_by_default(monkeypatch) -> None:
    """The lookup never runs unless explicitly enabled, matching the plain fallback today."""
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", False)
    retriever = MagicMock()
    orchestrator = AIOrchestrator(retriever=retriever)
    body = ChatRequest(message="What is the minimum order size for Belgium?", sessionId="s1", country="US", language="en")

    result = orchestrator._office_contact_addendum(body, "cid")

    assert result is None
    retriever.retrieve.assert_not_called()


def test_office_contact_addendum_returns_none_without_a_global_record(monkeypatch) -> None:
    """No country-scoped global record means no addendum, not an invented one."""
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", True)
    country_document = RetrievedDocument(
        id="policy-1",
        title="Policy",
        content="Some country policy content.",
        source="s3://approved/policy.pdf",
        country="US",
        language="en",
        score=0.4,
        metadata={"access_scope": "country"},
    )
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(documents=[country_document], citations=[], confidence=0.4)
    orchestrator = AIOrchestrator(retriever=retriever)
    body = ChatRequest(message="What is the minimum order size for Belgium?", sessionId="s1", country="US", language="en")

    assert orchestrator._office_contact_addendum(body, "cid") is None


def test_office_contact_addendum_offers_real_directory_contact_fields(monkeypatch) -> None:
    """A matching global directory record contributes its exact phone/email, nothing invented."""
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", True)
    monkeypatch.setattr(chat_orchestrator, "localized_conversation_response", lambda *_: None)
    directory_document = RetrievedDocument(
        id="directory-be",
        title="Global Directory - Forever Belgium",
        content="Forever Belgium\nTelephone: +32 2 000 0000\nEmail: belgium@example.com\nWebsite: example.com/be",
        source="s3://approved/directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={"access_scope": "global"},
    )
    retriever = MagicMock()
    retriever.retrieve.return_value = RetrievalResult(documents=[directory_document], citations=[], confidence=0.9)
    orchestrator = AIOrchestrator(retriever=retriever)
    body = ChatRequest(message="What is the minimum order size for Belgium?", sessionId="s1", country="US", language="en")

    addendum = orchestrator._office_contact_addendum(body, "cid")

    assert addendum is not None
    assert "+32 2 000 0000" in addendum
    assert "belgium@example.com" in addendum
    assert "direct way to reach" in addendum


def test_office_contact_addendum_fails_silently_when_retrieval_errors(monkeypatch) -> None:
    """A retrieval error never breaks the existing fallback path - it just adds nothing."""
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", True)
    retriever = MagicMock()
    retriever.retrieve.side_effect = RuntimeError("boom")
    orchestrator = AIOrchestrator(retriever=retriever)
    body = ChatRequest(message="What is the minimum order size for Belgium?", sessionId="s1", country="US", language="en")

    assert orchestrator._office_contact_addendum(body, "cid") is None


def test_insufficient_evidence_fallback_appends_office_contact_when_available(monkeypatch) -> None:
    """The end-to-end fallback path includes the directory contact info when the lookup finds one."""
    monkeypatch.setattr(settings, "FALLBACK_OFFICE_CONTACT_ENABLED", True)
    governance = _FakeGovernance()
    orchestrator = AIOrchestrator(
        retriever=MagicMock(),
        validator=_FakeValidator(),
        governance=governance,
    )
    body = ChatRequest(message="What is the minimum order size for Belgium?", sessionId="s1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(
        orchestrator,
        "_office_contact_addendum",
        lambda *_args, **_kwargs: "In the meantime, here is a direct way to reach that office:\nTelephone: +32 2 000 0000",
    )

    empty_result = RetrievalResult(documents=[], citations=[], confidence=0.0)
    orchestrator.retriever.retrieve.return_value = empty_result

    response = orchestrator.handle_chat(body, "cid")

    assert "+32 2 000 0000" in response.answer
    assert response.metadata["office_contact_offered"] is True
    assert response.citations == []
