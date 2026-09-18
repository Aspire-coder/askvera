"""Lane A (Phase 2, task A7): unresolved back-references through the real
end-to-end chat pipeline (``AIOrchestrator.handle_chat``).

tests/conversation/test_reference_resolution.py checks
app.orchestrator.reference_resolution.resolve_reference on its own, as a pure
function. This file drives the same scenarios through the real orchestrator
hook (``AIOrchestrator._resolve_unresolved_reference``, called from
``_handle_chat``) to prove the wiring - not just the logic - does what A7
requires: a clarification is actually delivered with cards/candidates and
retrieval never runs for the wrong guess, and a resolvable ordinal actually
reaches retrieval anchored to the right market.

All tests are offline/mocked-behaviour, in the same shape as
test_followup_state_e2e.py: the retriever and model router are fakes under
this file's control, and AWS/session/cache side effects are monkeypatched
out. Every test is labeled deterministic/local or mocked dependency.
"""

from __future__ import annotations

from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from utils.validators import ChatRequest

KENYA_CONTENT = (
    "Forever Kenya/East Africa\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Telephone Office +254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders +254 71 0600206\n"
)
UGANDA_CONTENT = (
    "Forever Uganda\n"
    "Business Hours Office 08.30 am - 17.00 pm (Mon - Fri)\n"
    "Telephone Office +256 3921 77993\n"
    "Telephone for Orders +256 3921 77994\n"
)
KENYA_PRIOR_ANSWER = "Delivery to Kenya costs $3 within the country."
UGANDA_PRIOR_ANSWER = "Delivery to Uganda costs a different amount; ask for specifics."


def _kenya_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="GLOBAL|en|International-Sponsoring-Directory.pdf|sponsoring-012-kenya-east-africa",
        title="International-Sponsoring-Directory.pdf",
        content=KENYA_CONTENT,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={
            "directory_kind": "international_sponsoring",
            "directory_section": "sponsoring",
            "document_type": "office_directory",
            "record_country": "Kenya/East Africa",
            "section_id": "sponsoring-012-kenya-east-africa",
            "access_scope": "global",
            "status": "active",
        },
    )


def _uganda_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="GLOBAL|en|International-Sponsoring-Directory.pdf|sponsoring-025-uganda",
        title="International-Sponsoring-Directory.pdf",
        content=UGANDA_CONTENT,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={
            "directory_kind": "international_sponsoring",
            "directory_section": "sponsoring",
            "document_type": "office_directory",
            "record_country": "Uganda",
            "section_id": "sponsoring-025-uganda",
            "access_scope": "global",
            "status": "active",
        },
    )


def _history(*turns: tuple[str, str]) -> str:
    lines: list[str] = []
    for user_turn, vera_turn in turns:
        lines.extend([f"user: {user_turn}", f"vera: {vera_turn}"])
    return "\n".join(lines)


KENYA_THEN_UGANDA_HISTORY = _history(
    ("What is the delivery cost in Kenya?", KENYA_PRIOR_ANSWER),
    ("What about Uganda?", UGANDA_PRIOR_ANSWER),
)


class _AllowGovernance:
    def evaluate(self, **_: object):
        from app.governance.models import GovernanceAction, GovernanceDecision

        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _NoOpValidator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _FakeRetriever:
    def __init__(self, documents: list[RetrievedDocument]) -> None:
        self.documents = documents
        self.seen: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen.append(message)
        return RetrievalResult(
            documents=list(self.documents),
            citations=[document.to_source() for document in self.documents],
            confidence=0.9,
        )


class _FakeRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def generate(self, *_: object, **__: object) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text=self.text, citations=[], confidence=0.9, provider="test", model_name="test")


def _run(
    monkeypatch,
    *,
    message: str,
    history: str,
    documents: list[RetrievedDocument],
    model_text: str,
    language: str = "en",
    country: str = "US",
    session_id: str = "s",
):
    """Drive AIOrchestrator.handle_chat with a fake retriever/router and given history.

    Mocked dependency: session storage, caching and AWS-adjacent side effects
    are monkeypatched, matching test_followup_state_e2e.py's own harness.
    """
    retriever = _FakeRetriever(documents)
    router = _FakeRouter(model_text)
    orchestrator = AIOrchestrator(
        retriever=retriever, router=router, validator=_NoOpValidator(), governance=_AllowGovernance()
    )

    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *args: "|".join(map(str, args)))
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_, **__: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)

    body = ChatRequest(message=message, sessionId=session_id, country=country, language=language)
    response = orchestrator.handle_chat(body, "cid")
    return response, retriever, router


# =============================================================================
# Contrastive reference: clarification delivered, retrieval never runs.
# =============================================================================


def test_the_other_one_with_three_candidates_clarifies_naming_all_three(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    history = _history(
        ("What is the delivery cost in Kenya?", KENYA_PRIOR_ANSWER),
        ("What about Uganda?", UGANDA_PRIOR_ANSWER),
        ("And Tanzania?", "Delivery to Tanzania costs a different amount too."),
    )
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the other one?",
        history=history,
        documents=[_kenya_document()],
        model_text="unused",
    )
    assert response.metadata.get("failure_layer") == "directory_clarification"
    assert len(response.metadata.get("reference_candidates") or []) == 3
    assert not retriever.seen


# =============================================================================
# Ordinal reference: resolves deterministically and reaches retrieval.
# =============================================================================


def test_the_first_one_resolves_to_kenya_and_retrieval_targets_it(monkeypatch) -> None:
    """deterministic/local, mocked dependency. "The first one" is Kenya - the
    market named first, by the user, across the whole session."""
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the first one?",
        history=KENYA_THEN_UGANDA_HISTORY,
        documents=[_kenya_document()],
        model_text="Delivery to Kenya costs $3 within the country.",
    )
    assert retriever.seen, "retrieval must run for a resolved ordinal reference"
    assert "Kenya" in retriever.seen[0]
    assert response.metadata.get("failure_layer") != "directory_clarification"
    assert "Kenya" in response.answer


def test_the_last_one_resolves_to_uganda_and_retrieval_targets_it(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the last one?",
        history=KENYA_THEN_UGANDA_HISTORY,
        documents=[_uganda_document()],
        model_text="The Uganda office telephone is +256 3921 77993.",
    )
    assert retriever.seen
    assert "Uganda" in retriever.seen[0]
    assert "+256 3921 77993" in response.answer


# =============================================================================
# Negative controls, end to end.
# =============================================================================


def test_message_naming_its_own_market_is_never_clarified(monkeypatch) -> None:
    """deterministic/local, mocked dependency. "What about Uganda?" names its
    own market (rule 1); this is the existing A3 behaviour, unaffected."""
    response, retriever, _router = _run(
        monkeypatch,
        message="What about Uganda?",
        history=KENYA_THEN_UGANDA_HISTORY,
        documents=[_uganda_document()],
        model_text="The Uganda office telephone is +256 3921 77993.",
    )
    assert response.metadata.get("failure_layer") != "directory_clarification"
    assert retriever.seen and "Uganda" in retriever.seen[0]


def test_single_candidate_market_is_never_clarified(monkeypatch) -> None:
    """deterministic/local, mocked dependency. Only Kenya has been named so
    far - "the other one" has nothing to disambiguate against (rule 4)."""
    history = _history(("What is the delivery cost in Kenya?", KENYA_PRIOR_ANSWER))
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the other one?",
        history=history,
        documents=[_kenya_document()],
        model_text="Delivery to Kenya costs $3 within the country.",
    )
    assert response.metadata.get("failure_layer") != "directory_clarification"


def test_topic_change_with_no_reference_word_is_never_clarified(monkeypatch) -> None:
    """deterministic/local, mocked dependency. "What about returns?" names no
    market and contains no contrastive/ordinal token."""
    response, retriever, _router = _run(
        monkeypatch,
        message="What about returns?",
        history=KENYA_THEN_UGANDA_HISTORY,
        documents=[_kenya_document()],
        model_text="Returns are accepted within the policy window.",
    )
    assert response.metadata.get("failure_layer") != "directory_clarification"


# =============================================================================
# Preserved references keep resolving as before (not caught by this module).
# =============================================================================


def test_that_number_and_that_requirement_still_resolve_normally(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    for message in ("Is that number still correct?", "Is that requirement the same everywhere?"):
        response, retriever, _router = _run(
            monkeypatch,
            message=message,
            history=KENYA_THEN_UGANDA_HISTORY,
            documents=[_kenya_document()],
            model_text="Yes, that is correct.",
        )
        assert response.metadata.get("failure_layer") != "directory_clarification"


def test_the_order_phone_and_there_still_resolve_normally(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    for message in ("What about the order phone?", "Is there an office nearby?"):
        response, retriever, _router = _run(
            monkeypatch,
            message=message,
            history=KENYA_THEN_UGANDA_HISTORY,
            documents=[_uganda_document()],
            model_text="The order phone is +256 3921 77994.",
        )
        assert response.metadata.get("failure_layer") != "directory_clarification"


# =============================================================================
# Multilingual, end to end: French contrastive, German ordinal.
# =============================================================================


def test_french_contrastive_reference_clarifies_end_to_end(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    history = _history(
        ("Quel est le cout de livraison pour le Kenya?", "..."),
        ("Et pour l'Ouganda?", "..."),
    )
    response, retriever, _router = _run(
        monkeypatch,
        message="Qu'en est-il de l'autre ?",
        history=history,
        documents=[_kenya_document()],
        model_text="unused",
        language="fr",
    )
    assert response.metadata.get("failure_layer") == "directory_clarification"
    assert set(response.metadata.get("reference_candidates") or []) == {"Kenya", "Uganda"}
    assert not retriever.seen


def test_german_ordinal_reference_resolves_end_to_end(monkeypatch) -> None:
    """deterministic/local, mocked dependency."""
    history = _history(
        ("Wie hoch sind die Lieferkosten fuer Kenya?", "..."),
        ("Und fuer Uganda?", "..."),
    )
    response, retriever, _router = _run(
        monkeypatch,
        message="Und was ist mit dem ersten?",
        history=history,
        documents=[_kenya_document()],
        model_text="Die Lieferkosten fuer Kenya betragen $3.",
        language="de",
    )
    assert retriever.seen
    assert "Kenya" in retriever.seen[0]
    assert response.metadata.get("failure_layer") != "directory_clarification"


# =============================================================================
# Language outside this module's coverage: unchanged behaviour end to end.
# =============================================================================


def test_language_outside_reference_vocabulary_scope_is_never_clarified(monkeypatch) -> None:
    """deterministic/local, mocked dependency. Rule 5: "ru" is a real,
    configured widget language (so ChatRequest accepts it), but it is not
    one of the ten languages config/reference_vocabulary.py covers, so it
    must fail conservative - unchanged behaviour, exactly as an unrecognized
    language code would."""
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the other one?",
        history=KENYA_THEN_UGANDA_HISTORY,
        documents=[_kenya_document()],
        model_text="Delivery to Kenya costs $3 within the country.",
        language="ru",
    )
    assert response.metadata.get("failure_layer") != "directory_clarification"
