"""A market name in a generated answer must not cost the answer its policy figure.

Live trace (held-out case 06, session CA): "Is there a limit on how many case
credits I can order in one month here in Canada?" The governing clause is
CA 13.01(e), 25 Case Credits per calendar month without prior Home Office
approval. The answer entering validation had no "25" and began with a sentence
that referred back to one that was not there. Turn metadata recorded
response_pii_scrubbed and contact_placeholder_actions
["unresolved_placeholder_line_removed"], and nothing else.

Reproduced offline through the real answer-securing editors: Comprehend labels
the bare country name "Canada" as ADDRESS; "Canada" is not in the approved
evidence, so scrub_pii masked it as [ADDRESS]; _PLACEHOLDER_RE then matched
that token and remove_or_replace_contact_placeholders deleted the whole line,
figure and condition included. The fix preserves an ADDRESS/LOCATION entity
only when the entire entity is a configured market name.

No network: Comprehend is faked. The scrubber, placeholder clean-up, output
validator and orchestrator editors are the real ones.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response import ChatResponse
from app.response.quality import remove_or_replace_contact_placeholders
from app.retrieval.models import RetrievedDocument, RetrievalResult
from services.pii import remove_unresolved_pii_placeholders, scrub_pii
from utils.validators import ChatRequest

QUESTION = "Is there a limit on how many case credits I can order in one month here in Canada?"
CLAUSE = (
    "Section 13.01: (a) Preferred Customers and FBOs order directly from the Company at discounted prices.\n"
    "(e) An FBO may not order more than 25 Case Credits in any calendar Month\n"
    "without prior Home Office approval.\n"
    "Orders may be placed through a product center, Customer Care at (888) 440-ALOE (2563), "
    "or via the Internet at www.foreverliving.com."
)
FOLLOW_UP = (
    "If you need to order beyond that amount in a given month, you'll need to contact "
    "the Home Office first to request approval before placing your order."
)
FACT = "An FBO may not order more than 25 Case Credits in any calendar month without prior Home Office approval."
PLACEHOLDER = re.compile(r"\[[A-Z_]+\]")


class _FakeComprehend:
    """DetectPiiEntities stand-in: tags every occurrence of each (text, type) pair."""

    def __init__(self, entities: list[tuple[str, str]]) -> None:
        self.entities = entities
        self.calls = 0

    def detect_pii_entities(self, Text: str, LanguageCode: str) -> dict:  # noqa: N803 - boto3 argument names
        self.calls += 1
        found = []
        for needle, entity_type in self.entities:
            for match in re.finditer(re.escape(needle), Text):
                found.append({"BeginOffset": match.start(), "EndOffset": match.end(), "Type": entity_type, "Score": 0.99})
        return {"Entities": found}


def _retrieval(content: str = CLAUSE) -> RetrievalResult:
    document = RetrievedDocument(
        id="CA|en|CA-EN-Company-Policy.pdf|13.01-e", title="CA-EN-Company-Policy.pdf - Sec 13.01-e", content=content,
        source="opensearch-section://CA-EN-Company-Policy.pdf/13.01-e", country="CA", language="en", score=0.95,
        metadata={"section_id": "13.01-e", "parent_section_id": "13.01", "access_scope": "country"},
    )
    return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.95, metadata={})


def _secure(
    answer: str,
    *,
    entities: list[tuple[str, str]] = (),
    language: str = "en",
    country: str = "CA",
    question: str = QUESTION,
    content: str = CLAUSE,
) -> tuple[ChatResponse, _FakeComprehend]:
    retrieval = _retrieval(content)
    comprehend = _FakeComprehend(list(entities))
    response = ChatResponse(
        answer=answer, citations=list(retrieval.citations), suggestions=[], cards=[], confidence=0.95,
        metadata={}, correlation_id="cid",
    )
    with patch("services.pii.get_aws_clients", return_value=SimpleNamespace(comprehend=comprehend)):
        secured = AIOrchestrator()._secure_and_complete_response(
            response, retrieval, language, "cid", user_question=question, country=country
        )
    return secured, comprehend


def _assert_limit_and_condition(answer: str) -> None:
    assert re.search(r"\b25\b", answer), answer
    assert "calendar month" in answer.casefold()
    assert "home office approval" in answer.casefold()
    assert not PLACEHOLDER.search(answer), answer


# --- Positive: the reproduced case-06 shapes keep the figure and its condition ------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        f"Yes. As an FBO in Canada, you may not order more than 25 Case Credits in any calendar month "
        f"without prior Home Office approval.\n\n{FOLLOW_UP}",
        f"Yes, there is a limit here in Canada. {FACT}\n\n{FOLLOW_UP}",
        "Yes, in Canada there is a monthly limit:\n- An FBO may not order more than 25 Case Credits in any calendar "
        "month without prior Home Office approval.",
    ],
    ids=["country-in-fact-sentence", "country-in-separate-sentence-same-line", "country-in-lead-in-line"],
)
def test_case_06_shapes_keep_the_figure_when_comprehend_tags_the_country(answer):
    secured, comprehend = _secure(answer, entities=[("Canada", "ADDRESS")])

    assert comprehend.calls == 1
    _assert_limit_and_condition(secured.answer)
    assert "Canada" in secured.answer
    assert "contact_placeholder_actions" not in secured.metadata
    assert "response_pii_scrubbed" not in secured.metadata
    assert not secured.metadata.get("empty_after_output_cleanup")


def test_case_06_shape_keeps_the_policy_contact_lines_it_already_kept():
    answer = f"In Canada: {FACT} Customer Care is at (888) 440-ALOE (2563), or order at www.foreverliving.com."

    secured, _ = _secure(answer, entities=[("Canada", "ADDRESS"), ("(888) 440-ALOE (2563)", "PHONE")])

    assert secured.answer == answer


def test_spanish_comprehend_path_keeps_the_localized_market_name_and_figure():
    answer = (
        "Sí. En Canadá, un FBO no puede pedir más de 25 Case Credits en un calendar month "
        "sin la Home Office approval previa."
    )

    secured, comprehend = _secure(answer, entities=[("Canadá", "ADDRESS")], language="es")

    assert comprehend.calls == 1
    assert secured.answer == answer


def test_named_sponsoring_destination_is_kept_as_well():
    answer = "To sponsor someone in the United Kingdom, the United Kingdom policy applies to that FBO."

    secured, _ = _secure(
        answer, entities=[("United Kingdom", "ADDRESS")], question="Can I sponsor someone in the United Kingdom?",
        content="International sponsoring: the FBO follows the policy of the country of residence.",
    )

    assert secured.answer == answer


# --- Negative controls: PII safety is unchanged --------------------------------------------------------------------


def test_a_private_street_address_that_contains_a_country_name_is_still_masked_and_never_delivered():
    answer = f"{FACT}\nShip it to 123 Main Street, Toronto, Canada."

    secured, _ = _secure(answer, entities=[("123 Main Street, Toronto, Canada", "ADDRESS")])

    assert secured.answer == FACT
    assert "Main Street" not in secured.answer
    assert secured.metadata["contact_placeholder_actions"] == ["unresolved_placeholder_line_removed"]


def test_a_city_that_is_not_a_configured_market_is_still_masked():
    answer = f"{FACT}\nThe office is in Mississauga."

    secured, _ = _secure(answer, entities=[("Mississauga", "ADDRESS")])

    assert "Mississauga" not in secured.answer
    assert not PLACEHOLDER.search(secured.answer)
    _assert_limit_and_condition(secured.answer)


@pytest.mark.parametrize(
    ("line", "entities", "private"),
    [
        ("Call Jane at 416-555-0199.", [("416-555-0199", "PHONE")], "416-555-0199"),
        ("Or write to jane.doe.private@example.com.", [], "jane.doe.private@example.com"),
        ("Your upline Alice Tremblay can approve it.", [("Alice Tremblay", "NAME")], "Alice Tremblay"),
    ],
    ids=["phone", "email", "personal-name"],
)
def test_real_personal_data_on_its_own_line_is_still_scrubbed(line, entities, private):
    secured, _ = _secure(f"{FACT}\n{line}", entities=[("Canada", "ADDRESS"), *entities])

    assert private not in secured.answer
    assert not PLACEHOLDER.search(secured.answer)
    _assert_limit_and_condition(secured.answer)


def test_a_person_name_matching_a_market_name_is_still_masked():
    comprehend = MagicMock()
    text = "Ask Jordan in Jordan."
    comprehend.detect_pii_entities.return_value = {
        "Entities": [
            {"BeginOffset": 4, "EndOffset": 10, "Type": "NAME"},
            {"BeginOffset": 14, "EndOffset": 20, "Type": "ADDRESS"},
        ]
    }

    with patch("services.pii.get_aws_clients", return_value=SimpleNamespace(comprehend=comprehend)):
        scrubbed = scrub_pii(text, "cid", "en", allowed_location_texts=["Jordan"])

    assert scrubbed == "Ask [NAME] in Jordan."


def test_without_a_location_allowlist_the_country_is_masked_exactly_as_before():
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {"Entities": [{"BeginOffset": 6, "EndOffset": 12, "Type": "ADDRESS"}]}

    with patch("services.pii.get_aws_clients", return_value=SimpleNamespace(comprehend=comprehend)):
        assert scrub_pii("Visit Canada now.", "cid", "en") == "Visit [ADDRESS] now."
        assert scrub_pii("Visit Canada now.", "cid", "en", allowed_location_texts=["canada"]) == "Visit Canada now."


@pytest.mark.parametrize("answer", ["[NAME]", "**[EMAIL]**", "<ADDRESS>"])
def test_a_line_that_is_only_a_placeholder_is_still_removed(answer):
    cleaned, changes = remove_or_replace_contact_placeholders(f"{FACT}\n{answer}", "CA")

    assert cleaned == FACT
    assert changes == ["unresolved_placeholder_line_removed"]


def test_a_sentence_whose_only_content_is_an_unresolved_placeholder_is_removed():
    secured, _ = _secure(f"{FACT}\n[NAME].", entities=[])

    assert secured.answer == FACT
    assert not PLACEHOLDER.search(remove_unresolved_pii_placeholders("[ADDRESS]."))


@pytest.mark.parametrize(
    ("language", "answer"),
    [
        (
            "fr",
            "Oui. Au Canada, un FBO ne peut pas commander plus de 25 Case Credits par mois civil "
            "sans l'approbation préalable du Home Office.",
        ),
        (
            "nl",
            "Ja. In Canada mag een FBO niet meer dan 25 Case Credits per kalendermaand bestellen "
            "zonder voorafgaande goedkeuring van het Home Office.",
        ),
        (
            "fi",
            "Kyllä. Kanadassa FBO ei saa tilata yli 25 Case Creditiä kalenterikuukaudessa ilman "
            "Home Officen ennakkohyväksyntää.",
        ),
    ],
)
def test_multilingual_answers_keep_the_figure_and_still_scrub_personal_data(language, answer):
    secured, comprehend = _secure(f"{answer}\nprivate.person@example.com", language=language)

    assert comprehend.calls == 0
    assert secured.answer == answer
    assert "private.person@example.com" not in secured.answer


def test_directory_contact_lines_and_phone_placeholder_handling_are_unchanged():
    evidence = "Canada Office\nPhone: +1 604 555 0100\nEmail: canada.office@foreverliving.com"
    answer = "Canada Office\nPhone: +1 604 555 0100\nEmail: canada.office@foreverliving.com"

    secured, _ = _secure(
        answer,
        entities=[("+1 604 555 0100", "PHONE"), ("canada.office@foreverliving.com", "EMAIL")],
        # "contact details" keeps every field; a single-field question is narrowed by
        # remove_unrequested_directory_fields, which this change does not touch.
        question="What are the Canada office contact details?",
        content=evidence,
    )
    assert secured.answer == answer
    assert "contact_placeholder_actions" not in secured.metadata

    replaced, changes = remove_or_replace_contact_placeholders("Call [PHONE] for help.", "US")
    assert replaced == "Call (888) 440-ALOE (2563) for help."
    assert changes == ["phone_replaced"]
    removed, changes = remove_or_replace_contact_placeholders(f"{FACT}\nCall [PHONE] for help.", "CA")
    assert removed == FACT
    assert changes == ["phone_line_removed"]


def test_market_place_names_come_from_configuration_and_hold_no_cities():
    chat_orchestrator._load_public_market_place_names.cache_clear()
    names = set(chat_orchestrator._public_market_place_names())

    assert {"Canada", "United Kingdom", "Canadá"} <= names
    assert "Toronto" not in names and "Mississauga" not in names


def test_a_market_config_failure_preserves_nothing_and_is_not_cached(monkeypatch):
    def broken():
        raise RuntimeError("config unavailable")

    chat_orchestrator._load_public_market_place_names.cache_clear()
    monkeypatch.setattr(chat_orchestrator, "load_market_config", broken)
    try:
        assert chat_orchestrator._public_market_place_names() == ()
        assert chat_orchestrator._load_public_market_place_names.cache_info().currsize == 0
    finally:
        monkeypatch.undo()
        chat_orchestrator._load_public_market_place_names.cache_clear()

    assert "Canada" in chat_orchestrator._public_market_place_names()


# --- Capture: the raw model answer is recorded, off by default, and changes nothing delivered ----------------------

SOURCE = "The service fee is 2.50."
RAW_PRIVATE = "private.person@example.com"
RAW_ANSWER = f"{SOURCE}\nWrite to {RAW_PRIVATE} for help."


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


class _RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, level: str):
        def record(*args: object, **kwargs: object) -> None:
            self.calls.append((level, args, kwargs))

        return record


@pytest.fixture
def ask(monkeypatch):
    sinks: dict[str, list] = {"audit": [], "session": [], "cache": [], "semantic_cache": []}
    logger = _RecordingLogger()
    stubs = {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "build_cache_key": lambda *_: "cache-key",
        "get_cache_value": lambda *_: None,
        "set_cache_value": lambda *args, **kwargs: sinks["cache"].append((args, kwargs)),
        "append_session_turn": lambda *args, **kwargs: sinks["session"].append((args, kwargs)),
        "write_audit_event": lambda *args, **kwargs: sinks["audit"].append((args, kwargs)),
        "get_session_history": lambda *_: "",
        "semantic_cache_active": lambda *_, **__: False,
        "get_semantic_cache_value": lambda *_, **__: None,
        "set_semantic_cache_value": lambda *args, **kwargs: sinks["semantic_cache"].append((args, kwargs)),
        "LOGGER": logger,
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(chat_orchestrator, name, stub)

    def run(answer: str, *, capture: bool):
        monkeypatch.setattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED", capture)
        orchestrator = AIOrchestrator(retriever=_Retriever(), router=_Router(answer), governance=_Governance())
        # English goes to Comprehend; it is faked to find nothing, so only the real pattern scrub edits.
        with patch("services.pii.get_aws_clients", return_value=SimpleNamespace(comprehend=_FakeComprehend([]))):
            response = orchestrator.handle_chat(
                ChatRequest(message="What is the service fee?", sessionId="session-1", country="CA", language="en"),
                "correlation",
            )
        return response

    run.sinks = sinks
    run.logger = logger
    return run


def _delivered(response) -> tuple:
    metadata = {key: value for key, value in response.metadata.items() if key != "diagnostic_capture"}
    return response.answer, response.citations, response.confidence, metadata


def test_raw_model_answer_is_captured_before_any_editor_only_when_capture_is_on(ask):
    off = ask(RAW_ANSWER, capture=False)
    on = ask(RAW_ANSWER, capture=True)

    assert chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED is True  # set by this test only
    assert "diagnostic_capture" not in off.metadata
    capture = on.metadata["diagnostic_capture"]
    assert capture["raw_model_answers"] == [RAW_ANSWER]
    assert RAW_PRIVATE not in on.answer
    assert capture["validations"][-1]["answer_before_validation"] == on.answer
    assert _delivered(on) == _delivered(off)


def test_raw_model_answer_reaches_no_api_cache_session_audit_or_log(ask):
    response = ask(RAW_ANSWER, capture=True)

    assert RAW_PRIVATE in json.dumps(response.metadata["diagnostic_capture"])
    exposed = {
        "api": response.to_api_result(),
        "cache_value": response.to_cache_value(),
        "sinks": ask.sinks,
        "logs": ask.logger.calls,
    }
    for name, value in exposed.items():
        text = json.dumps(value, default=str)
        assert RAW_PRIVATE not in text, name
        assert "raw_model_answers" not in text, name
