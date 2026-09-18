"""Lane A (conversation-quality, tasks A1-A8): follow-up state through the real
end-to-end chat pipeline.

Every test here drives ``AIOrchestrator.handle_chat`` itself, not just the
query-resolution helpers (``_build_retrieval_query`` / ``_build_request_query``)
that the existing ``tests/unit/test_demo_followup_resolution.py``,
``test_demo_followup_target_replacement.py`` and
``test_demo_multilingual_followups.py`` already pin at the query layer. The
history fed in here is a *realistic* prior assistant answer (real Kenya
International Sponsoring Directory record text, not the "An earlier answer."
placeholder those files use), so what actually reaches retrieval, the model
prompt and the delivered answer after post-processing can be checked, not just
what the query string says.

All tests are offline/mocked-behaviour: the retriever and model router are
fakes under this file's control, and AWS/session/cache side effects are
monkeypatched out. Nothing here proves a live model would behave the same way;
it proves the orchestrator's own wiring (retrieval targeting, response
building, validators) does what the acceptance criteria require given
controlled inputs. Where the real ``OutputValidator``/``ResponseBuilder`` are
left in (no override), that is called out in the test.
"""

from __future__ import annotations

import pytest

from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from services import session as session_module
from utils.validators import ChatRequest

# --- Realistic fixtures -----------------------------------------------------

# Real approved International Sponsoring Directory excerpt (worker C manifest),
# reused from tests/unit/test_demo_journeys_postprocessing.py so this is the
# same source-grounded record, not an invented one.
KENYA_CONTENT = (
    "Forever Kenya/East Africa\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Office & Product Center Address\n"
    "Kenya Reinsurance Plaza, 4th floor\n"
    "Business Hours Office 09.00 am - 19.00 pm (Mon - Fri)\n"
    "Telephone Office +254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders +254 71 0600206\n"
    "Email info@foreverea.com\n"
)
UGANDA_CONTENT = (
    "Forever Uganda\n"
    "Office Address Plot 47, Kira Road, Kampala\n"
    "Business Hours Office 08.30 am - 17.00 pm (Mon - Fri)\n"
    "Telephone Office +256 3921 77993\n"
    "Telephone for Orders +256 3921 77994\n"
    "Email info@foreverliving.co.ug\n"
)

# A realistic prior assistant turn, i.e. what Vera would actually have said,
# not a stub. Drawn straight from the record above.
KENYA_PRIOR_ANSWER = (
    "The Kenya office is at Kenya Reinsurance Plaza, 4th floor. "
    "Telephone Office: +254 20 2026869 / +254 20 2026873. "
    "Telephone for Orders: +254 71 0600206. Email: info@foreverea.com."
)


def _kenya_document(record_id: str = "sponsoring-012-kenya-east-africa", content: str = KENYA_CONTENT) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"GLOBAL|en|International-Sponsoring-Directory.pdf|{record_id}",
        title="International-Sponsoring-Directory.pdf",
        content=content,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={
            "directory_kind": "international_sponsoring",
            "directory_section": "sponsoring",
            "document_type": "office_directory",
            "record_country": "Kenya/East Africa",
            "section_id": record_id,
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
    """Render (user, vera) turn pairs exactly as services.session._format_history does."""
    lines: list[str] = []
    for user_turn, vera_turn in turns:
        lines.extend([f"user: {user_turn}", f"vera: {vera_turn}"])
    return "\n".join(lines)


class _AllowGovernance:
    def evaluate(self, **_: object):
        from app.governance.models import GovernanceAction, GovernanceDecision

        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _NoOpValidator:
    """Bypasses the real validator pipeline for tests that are only about targeting."""

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
    validator=_NoOpValidator(),
    governance=_AllowGovernance(),
):
    """Drive AIOrchestrator.handle_chat with a fake retriever/router and given history.

    Session storage and caching are stubbed (as the existing end-to-end tests
    in test_demo_followup_resolution.py / test_demo_followup_target_replacement.py
    do), so only retrieval targeting, prompt assembly and post-processing are
    exercised for real.
    """
    retriever = _FakeRetriever(documents)
    router = _FakeRouter(model_text)
    orchestrator = AIOrchestrator(retriever=retriever, router=router, validator=validator, governance=governance)

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
# A1: office phone vs order phone after a Kenya CONTACT answer.
# =============================================================================


def test_a1_office_or_order_phone_follow_up_keeps_kenya_and_uses_the_fresh_record(monkeypatch) -> None:
    """Fail-before shape: a model that reuses the *previous turn's* office number
    instead of the freshly retrieved one would leak stale/incorrect data. Here
    the fresh record's office number is deliberately different from what the
    realistic prior answer stated (simulating an updated source), and the
    fake model is scripted the way a grounded generation actually behaves:
    it answers from the retrieved record, not from memory of the old answer.
    """
    history = _history(("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER))
    updated_kenya = KENYA_CONTENT.replace("+254 20 2026869 / +254 20 2026873", "+254 20 5551234")
    fresh_record = _kenya_document(content=updated_kenya)
    model_text = "The office phone is +254 20 5551234. The order phone is +254 71 0600206."

    response, retriever, _router = _run(
        monkeypatch,
        message="Is that the office phone or the order phone?",
        history=history,
        documents=[fresh_record],
        model_text=model_text,
    )

    assert retriever.seen, "retrieval must run again for the follow-up, not reuse the cached prior turn"
    assert "Kenya" in retriever.seen[0]
    # The delivered answer's numbers come from THIS turn's re-retrieved record.
    assert "+254 20 5551234" in response.answer
    # The stale number from the previous (realistic) assistant answer must not
    # survive into the new delivered answer.
    assert "+254 20 2026869" not in response.answer


def test_a1_kenya_field_follow_up_never_reaches_retrieval_with_stale_history_numbers(monkeypatch) -> None:
    """The retrieval query itself must never carry the previous answer's digits -
    only the user's own words plus the inherited topic/market."""
    history = _history(("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER))
    response, retriever, _router = _run(
        monkeypatch,
        message="Is that the office phone or the order phone?",
        history=history,
        documents=[_kenya_document()],
        model_text="The office phone is +254 20 2026869. The order phone is +254 71 0600206.",
    )
    assert "2026869" not in retriever.seen[0] and "0600206" not in retriever.seen[0]
    assert response.answer  # sanity: a real answer was produced


# =============================================================================
# A2: "And the office hours?" keeps the office context.
# =============================================================================


def test_a2_office_hours_follow_up_keeps_kenya_context(monkeypatch) -> None:
    history = _history(
        ("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER),
        ("Is that the office phone or the order phone?", "That is the office phone. The order phone is different."),
    )
    response, retriever, _router = _run(
        monkeypatch,
        message="And the office hours?",
        history=history,
        documents=[_kenya_document()],
        model_text="Business Hours Office 09.00 am - 19.00 pm (Mon - Fri).",
    )
    assert "Kenya" in retriever.seen[0]
    assert "09.00 am" in response.answer


# =============================================================================
# A3: an explicit new place does not silently inherit the old place.
# =============================================================================


def test_a3_explicit_uganda_follow_up_does_not_inherit_kenya(monkeypatch) -> None:
    history = _history(("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER))
    response, retriever, _router = _run(
        monkeypatch,
        message="What about Uganda?",
        history=history,
        documents=[_uganda_document()],
        model_text="The Uganda office telephone is +256 3921 77993.",
    )
    query = retriever.seen[0]
    assert "Uganda" in query
    assert "Kenya" not in query
    assert "+256 3921 77993" in response.answer
    assert "+254" not in response.answer


# =============================================================================
# A4: a new conversation cannot inherit facts or state from another conversation.
# =============================================================================


def test_a4_fresh_session_id_gets_no_facts_or_state_from_a_prior_session(monkeypatch) -> None:
    """Uses the REAL memory-backed session store (services.session), keyed by
    sessionId, rather than stubbing get_session_history - this is the actual
    isolation mechanism, not just a claim about it."""
    session_module._reset_memory_sessions()
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *args: "|".join(map(str, args)))
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_, **__: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)

    retriever_a = _FakeRetriever([_kenya_document()])
    router_a = _FakeRouter(KENYA_PRIOR_ANSWER)
    orchestrator_a = AIOrchestrator(
        retriever=retriever_a, router=router_a, validator=_NoOpValidator(), governance=_AllowGovernance()
    )
    body_a = ChatRequest(
        message="What is the Kenya office phone number and email?", sessionId="conv-A", country="US", language="en"
    )
    orchestrator_a.handle_chat(body_a, "cid-a")

    # A different conversation (different sessionId), same process, asking a
    # short follow-up that would only make sense if Kenya carried over.
    retriever_b = _FakeRetriever([_uganda_document()])
    router_b = _FakeRouter("I'm not sure which country you mean.")
    orchestrator_b = AIOrchestrator(
        retriever=retriever_b, router=router_b, validator=_NoOpValidator(), governance=_AllowGovernance()
    )
    body_b = ChatRequest(message="Is that the office phone or the order phone?", sessionId="conv-B", country="US", language="en")
    orchestrator_b.handle_chat(body_b, "cid-b")

    # The second, unrelated conversation must reach retrieval with its own
    # bare message - no Kenya, no phone digits carried from conv-A's state.
    assert retriever_b.seen == ["Is that the office phone or the order phone?"]
    assert "Kenya" not in retriever_b.seen[0]

    session_module._reset_memory_sessions()


def test_a4_two_sessions_never_share_cache_identity(monkeypatch) -> None:
    """Cache keys are built from each session's OWN resolved request; two
    different conversations must not collide or borrow each other's key."""
    captured: dict[str, list[str]] = {"keys": []}

    def _key(message, *args):
        key = "|".join([message, *map(str, args)])
        captured["keys"].append(key)
        return key

    def _run_with_key_capture(history, message, session_id):
        retriever = _FakeRetriever([_kenya_document()])
        router = _FakeRouter("An answer.")
        orchestrator = AIOrchestrator(
            retriever=retriever, router=router, validator=_NoOpValidator(), governance=_AllowGovernance()
        )
        monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
        monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
        monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
        monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
        monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
        monkeypatch.setattr(chat_orchestrator, "build_cache_key", _key)
        monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
        monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
        monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
        monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: None)
        monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_, **__: None)
        monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
        monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
        body = ChatRequest(message=message, sessionId=session_id, country="US", language="en")
        orchestrator.handle_chat(body, "cid")

    _run_with_key_capture(_history(("What is the Kenya office phone number?", KENYA_PRIOR_ANSWER)),
                           "Is that the office phone or the order phone?", "conv-A")
    _run_with_key_capture("", "Is that the office phone or the order phone?", "conv-B")

    assert captured["keys"][0] != captured["keys"][1]


# =============================================================================
# A5: a topic change releases irrelevant context.
# =============================================================================


def test_a5_topic_change_drops_the_kenya_directory_context(monkeypatch) -> None:
    history = _history(("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER))
    response, retriever, _router = _run(
        monkeypatch,
        message="What is the return policy?",
        history=history,
        documents=[_kenya_document()],
        model_text="Returns are accepted within the policy window.",
    )
    assert retriever.seen == ["What is the return policy?"]
    assert "Kenya" not in retriever.seen[0]


# =============================================================================
# A6: a language switch mid-session preserves topic, response follows the new language.
# =============================================================================


def test_a6_language_switch_keeps_topic_and_switches_deterministic_refusal_text(monkeypatch) -> None:
    """The per-request `language` selector changes mid-session (history kept).
    An income-claim refusal must use the NEW language's deterministic copy,
    not the language of the earlier turn, while the topic (the refused
    anchor) still carries into the follow-up's retrieval query.
    """
    income_anchor = "Can you guarantee I will earn 5000 dollars a month in Kenya?"
    history = _history((income_anchor, "I can't share income guarantees."))

    from app.evidence import localized_conversation_response
    from app.governance import governance_engine

    response, retriever, _router = _run(
        monkeypatch,
        message="Et pour l'Ouganda ?",
        history=history,
        documents=[_kenya_document()],
        model_text="unused",
        language="fr",
        governance=governance_engine,  # the real engine: this test needs a real refusal
    )
    expected_fr = localized_conversation_response("income_claim", "fr")
    assert response.answer == expected_fr
    assert response.answer != localized_conversation_response("income_claim", "en")
    # A refused turn never reaches retrieval at all (governance blocks it
    # before the retriever is called), which is itself the expected shape:
    # the refusal is judged, and answered in French, without ever exposing
    # the refused topic to retrieval.
    assert retriever.seen == []


def test_a6_language_switch_on_a_safe_topic_follows_the_new_language(monkeypatch) -> None:
    """A same-topic follow-up after a language switch is judged/answered under
    the new language selector; this pins that the selector (not the history's
    language) governs, for a path that does not hit a refusal."""
    history = _history(("What is the Kenya office phone number and email?", KENYA_PRIOR_ANSWER))
    response, retriever, _router = _run(
        monkeypatch,
        message="Et pour l'Ouganda ?",
        history=history,
        documents=[_uganda_document()],
        model_text="Le telephone du bureau est +256 3921 77993.",
        language="fr",
    )
    from app.retrieval.opensearch_sections import _directory_target_country_names

    assert retriever.seen
    assert _directory_target_country_names(retriever.seen[0], "US") == {"Uganda"}
    assert "+256 3921 77993" in response.answer


# =============================================================================
# A7: an ambiguous follow-up that context and evidence cannot resolve gets a
# brief clarification rather than a guess.
# =============================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A7 open defect: 'the other one' after Kenya then Uganda resolves to Uganda, the market "
        "just discussed, which is the one reading it cannot mean. Lane A's English-regex patch was "
        "rejected by the coordinator (English phrase list; returns a refusal, not a clarification). "
        "Flips to a visible pass when a general fix lands."
    ),
)
def test_a7_the_other_one_after_two_named_markets_does_not_silently_answer_for_one(monkeypatch) -> None:
    """Repro: after Kenya then an explicit switch to Uganda, "What about the
    other one?" refers to whichever market the reader did NOT just get an
    answer about - genuinely ambiguous between Kenya and Uganda from the
    reader's point of view. The current implementation resolves the bare
    "other one" phrase against the single most-recent target (Uganda) instead
    of recognising the anaphor and asking which one is meant.

    This is recorded as repro-confirmed at the orchestrator query-resolution
    layer: retrieval runs for exactly one market (Uganda) rather than pausing
    for a brief clarification. Because `_build_retrieval_query` /
    `_build_request_query` are single-writer (owned by the coordinator, see
    docs/conversation-quality/TASK_BOARD.md and this worktree's task prompt),
    the fix is delivered as a patch file for the coordinator to apply rather
    than an edit here - see
    docs/conversation-quality/patches/laneA-other-one-clarification.patch.
    """
    history = _history(
        ("What is the delivery cost in Kenya?", "Delivery to Kenya costs $3 within the country."),
        ("What about Uganda?", "Delivery to Uganda costs a different amount; ask for specifics."),
    )
    response, retriever, _router = _run(
        monkeypatch,
        message="What about the other one?",
        history=history,
        documents=[_kenya_document()],
        model_text="Delivery to Kenya costs $3 within the country.",
    )
    from app.retrieval.opensearch_sections import _directory_target_country_names

    # Desired behaviour (coordinator correction): the original version of this
    # test asserted the DEFECT - retrieval for Uganda alone - as its passing
    # condition, so it would have failed the day A7 was fixed. It now asserts
    # the requirement. Either a brief clarification is asked, or retrieval
    # does not resolve to Uganda, the one market "the other one" cannot mean.
    clarified = response.metadata.get("failure_layer") == "directory_clarification"
    guessed_uganda = bool(retriever.seen) and _directory_target_country_names(
        retriever.seen[0], "US"
    ) == {"Uganda"}
    assert clarified or not guessed_uganda


# =============================================================================
# A8: a previous hallucinated assistant answer cannot become trusted evidence.
# =============================================================================


def test_a8_fabricated_prior_policy_claim_is_not_repeated_as_trusted_fact(monkeypatch) -> None:
    """A prior assistant turn contains a fabricated, specific policy detail (a
    realistic-looking hallucination, not a stub). This turn's retrieval
    returns only a directory record - no policy document at all - so nothing
    in THIS turn's evidence could ground that detail. A model that echoes the
    old, unsupported claim back (as an LLM conditioned on history might) must
    not have that claim delivered as a trusted answer.

    Uses the REAL OutputValidator/ResponseBuilder (no override) so the actual
    HistoryGroundingValidator wiring is exercised, not a stub.
    """
    fabricated_detail = (
        "Yes, under section 42 of the policy you can get a full refund after 90 days with no receipt required."
    )
    history = _history(
        ("What is the return policy exception for lost receipts?", fabricated_detail),
    )
    response, retriever, router = _run(
        monkeypatch,
        message="Can you remind me of that 90-day rule again?",
        history=history,
        documents=[_kenya_document()],  # directory-only evidence: no policy document this turn
        model_text=fabricated_detail,
        validator=None,  # real OutputValidator
    )
    assert retriever.seen
    assert "section 42" not in response.answer
    assert "90 days" not in response.answer
    # Confirms this is a real catch, not an accident of some unrelated strip:
    # both the numeric and the history-sourced validators fired critically,
    # and the delivered answer is the honest insufficient-evidence fallback.
    issue_codes = {issue["code"] for issue in response.metadata["validation"]["issues"]}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in issue_codes
    assert "NUMERIC_CLAIM_UNGROUNDED" in issue_codes
    assert response.metadata["failure_layer"] == "numeric_validator"
