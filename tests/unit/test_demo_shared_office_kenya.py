"""Demo K: the Kenya/East Africa office serves the countries its record lists.

Owner decision (2026-09-12): the approved International Sponsoring Directory
record ``sponsoring-012-kenya-east-africa`` (``record_country``
"Kenya/East Africa") lists its office as serving Kenya, Uganda, Tanzania,
Burundi, Rwanda, South Sudan and Ethiopia, and its contact, address, hours,
delivery fee and minimum orders apply to all of them.

The relationship lives in ``config/global_directory_markets.json``
(``shared_offices``), never in Python. A listed country that is a configured
market of its own - Uganda, Tanzania, Burundi and Rwanda each have their own
approved directory record - keeps that record; only South Sudan and Ethiopia,
which have no record and no market entry, reach the Kenya/East Africa record.
No other shared-office relationship is inferred (Belgium is not the
Netherlands Benelux record, Sierra Leone/Liberia are not Ghana).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.orchestrator import chat_orchestrator
from app.retrieval import providers as retrieval_providers
from app.retrieval.providers import _planned_retrieval_plan
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.retrieval.opensearch_sections import (
    _directory_record_country_score,
    _directory_target_country_names,
    _directory_text_query,
)
from services import market_config

KENYA_EAST_AFRICA = "Kenya/East Africa"


def _clear_config_caches() -> None:
    for name in ("load_market_config", "load_global_directory_markets", "load_shared_offices"):
        loader = getattr(market_config, name, None)
        if loader is not None:
            loader.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_config_caches():
    _clear_config_caches()
    yield
    _clear_config_caches()


# --- configuration ---------------------------------------------------------


def test_shared_office_entry_is_configured_with_the_owner_decision() -> None:
    offices = market_config.load_shared_offices()
    kenya = [office for office in offices if office["record_country"] == KENYA_EAST_AFRICA]
    assert len(kenya) == 1
    assert kenya[0]["serves"] == [
        "Kenya", "Uganda", "Tanzania", "Burundi", "Rwanda", "South Sudan", "Ethiopia",
    ]
    assert [office["record_country"] for office in offices] == [KENYA_EAST_AFRICA]


def test_shared_office_loader_tolerates_a_missing_key(tmp_path, monkeypatch) -> None:
    path = tmp_path / "global_directory_markets.json"
    path.write_text(json.dumps({"markets": [{"name": "Japan", "code": "JP"}]}), encoding="utf-8")
    monkeypatch.setenv("GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", str(path))
    market_config.load_shared_offices.cache_clear()

    assert market_config.load_shared_offices() == []
    assert market_config.find_shared_office_record_countries("Delivery cost in South Sudan?") == set()


def test_shared_office_loader_tolerates_a_missing_file_and_malformed_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", str(tmp_path / "missing.json"))
    market_config.load_shared_offices.cache_clear()
    assert market_config.load_shared_offices() == []

    path = tmp_path / "malformed.json"
    path.write_text(
        json.dumps(
            {
                "shared_offices": [
                    "not-an-object",
                    {"record_country": "", "serves": ["South Sudan"]},
                    {"record_country": "Kenya/East Africa", "serves": "South Sudan"},
                    {"record_country": "Kenya/East Africa", "serves": ["South Sudan", "", 7]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", str(path))
    market_config.load_shared_offices.cache_clear()
    assert market_config.load_shared_offices() == [
        {"record_country": "Kenya/East Africa", "serves": ["South Sudan"]}
    ]


# --- retrieval targeting ---------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is the delivery cost in South Sudan?",
        "What is the minimum order size in South Sudan?",
        "What is the phone number for Forever South Sudan?",
        "What is the delivery cost in Ethiopia?",
        "What is the minimum order in Ethiopia?",
        "What is the telephone number for the office in Ethiopia?",
    ],
)
@pytest.mark.parametrize("session_country", ["US", "KE"])
def test_served_country_without_its_own_record_targets_kenya_east_africa(question, session_country) -> None:
    assert _directory_target_country_names(question, session_country) == {KENYA_EAST_AFRICA}


def test_kenya_question_is_unchanged() -> None:
    assert _directory_target_country_names("What is the delivery cost in Kenya?", "US") == {"Kenya"}


@pytest.mark.parametrize(
    ("question", "own_record"),
    [
        ("What is the delivery cost in Uganda?", "Uganda"),
        ("What is the minimum order in Tanzania?", "Tanzania"),
        ("What is the phone number in Burundi?", "Burundi"),
        ("What is the delivery cost in Rwanda?", "Rwanda"),
    ],
)
def test_served_country_with_its_own_record_keeps_it(question, own_record) -> None:
    """Uganda, Tanzania, Burundi and Rwanda each have their own approved
    record (sponsoring-025/022/005/018); the shared office never displaces it."""
    targets = _directory_target_country_names(question, "US")
    assert own_record in targets
    assert KENYA_EAST_AFRICA not in targets


@pytest.mark.parametrize(
    ("question", "expected", "forbidden"),
    [
        ("What is the phone number in Belgium?", {"Belgium"}, "Netherlands Benelux"),
        ("What is the phone number in Sierra Leone?", {"Sierra Leone"}, "Ghana"),
        ("What is the phone number in Liberia?", {"Liberia"}, "Ghana"),
        ("What is the delivery cost in Japan?", {"Japan"}, KENYA_EAST_AFRICA),
    ],
)
def test_no_other_shared_office_relationship_is_inferred(question, expected, forbidden) -> None:
    targets = _directory_target_country_names(question, "US")
    assert targets == expected
    assert forbidden not in targets


def test_region_words_alone_do_not_reach_the_shared_office() -> None:
    assert market_config.find_shared_office_record_countries("What is the delivery cost in East Africa?") == set()
    assert market_config.find_shared_office_record_countries("What is the delivery cost in Sudan?") == set()


def test_directory_query_for_south_sudan_is_restricted_to_the_serving_record() -> None:
    targets = _directory_target_country_names("What is the delivery cost in South Sudan?", "US")
    query = _directory_text_query("delivery cost South Sudan", targets)
    filters = query["query"]["bool"]["filter"]
    record_filter = filters[-1]["bool"]["should"]
    assert {"match_phrase": {"metadata.record_country": {"query": "kenya east africa"}}} in record_filter
    assert {
        "match_phrase": {"metadata.record_country": {"query": KENYA_EAST_AFRICA, "boost": 40}}
    } in query["query"]["bool"]["should"]


def _planner_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{
                    "text": '{"queries":["delivery cost"],'
                    '"document_scopes":["locale_policy"],"intent":"knowledge",'
                    '"intent_confidence":0.99}'
                }]
            }
        }
    }
    return runtime


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the delivery cost in South Sudan?", True),
        ("What is the delivery cost in Ethiopia?", True),
        ("What is the delivery cost in East Africa?", False),
    ],
)
def test_planner_opens_global_directory_for_a_served_country(monkeypatch, question, expected) -> None:
    """The planner's scope choice is a hint; a served country opens the global
    directory the same way a configured named market already does."""
    runtime = _planner_runtime()
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))

    plan = _planned_retrieval_plan(question, "US", "en", "shared-office-cid")

    assert plan.include_global_documents is expected


def _directory_row(record_country: str) -> dict:
    return {"document_type": "office_directory", "metadata": {"record_country": record_country}}


def test_serving_record_is_eligible_and_other_served_records_are_not() -> None:
    question = "What is the delivery cost in South Sudan?"
    targets = _directory_target_country_names(question, "US")
    assert _directory_record_country_score(question, _directory_row(KENYA_EAST_AFRICA), targets) == 8.0
    assert _directory_record_country_score(question, _directory_row("Uganda"), targets) < 0


def test_own_record_outranks_the_shared_office_for_uganda() -> None:
    question = "What is the delivery cost in Uganda?"
    targets = _directory_target_country_names(question, "US")
    own = _directory_record_country_score(question, _directory_row("Uganda"), targets)
    shared = _directory_record_country_score(question, _directory_row(KENYA_EAST_AFRICA), targets)
    assert own > shared


# --- customer-care contact supplement --------------------------------------


def _record(record_id: str, record_country: str, phone: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=record_id,
        title=f"Forever {record_country}",
        content=f"Welcome to Forever {record_country}!\nTelephone Office {phone}\n",
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_section": "sponsoring",
            "record_country": record_country,
            "access_scope": "global",
            "document_type": "office_directory",
            "ingestion_id": "v1",
            "directory_fields": {"Telephone Office": phone},
        },
    )


def _kenya_record() -> RetrievedDocument:
    return _record("sponsoring-012-kenya-east-africa", KENYA_EAST_AFRICA, "+254 20 2026869")


_CARE_ANSWER = "You are welcome to place an order directly. Please contact customer care for further help."


def _supplement(monkeypatch, documents, question, country="US"):
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    response = ChatResponse(
        answer=_CARE_ANSWER, citations=[document.to_source() for document in documents], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(
        documents=documents, citations=[document.to_source() for document in documents], confidence=0.8
    )
    return AIOrchestrator()._secure_and_complete_response(
        response, result, "en", "cid", user_question=question, country=country, resolved_request=question,
    )


@pytest.mark.parametrize("question", ["Who do I contact in South Sudan?", "Who do I contact about my Ethiopia order?"])
def test_contact_supplement_uses_kenya_east_africa_for_a_served_country(monkeypatch, question) -> None:
    completed = _supplement(monkeypatch, [_kenya_record()], question)

    assert "Telephone Office: +254 20 2026869" in completed.answer
    assert completed.metadata["support_contact_supplemented"]["record_id"] == "sponsoring-012-kenya-east-africa"


def test_contact_supplement_prefers_ugandas_own_record_and_never_borrows_kenyas(monkeypatch) -> None:
    uganda = _record("sponsoring-025-uganda", "Uganda", "+256 3921 77993")

    only_kenya = _supplement(monkeypatch, [_kenya_record()], "Who do I contact in Uganda?")
    assert "Telephone Office" not in only_kenya.answer

    both = _supplement(monkeypatch, [_kenya_record(), uganda], "Who do I contact in Uganda?")
    assert "Telephone Office: +256 3921 77993" in both.answer
    assert "+254 20 2026869" not in both.answer


@pytest.mark.parametrize(
    ("question", "document"),
    [
        ("Who do I contact in Belgium?", _record("sponsoring-053-netherlands-benelux", "Netherlands Benelux", "+31 88")),
        ("Who do I contact in Sierra Leone?", _record("sponsoring-ghana", "Ghana", "+233 302 000 000")),
        ("Who do I contact in Liberia?", _record("sponsoring-ghana", "Ghana", "+233 302 000 000")),
        ("Who do I contact in East Africa?", _kenya_record()),
        ("Who do I contact in Japan?", _kenya_record()),
    ],
)
def test_contact_supplement_still_rejects_undecided_relationships(monkeypatch, question, document) -> None:
    completed = _supplement(monkeypatch, [document], question)

    assert "Telephone Office" not in completed.answer
    assert "support_contact_supplemented" not in completed.metadata
